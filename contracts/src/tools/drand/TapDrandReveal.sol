// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../interfaces/ITapNetlistNFT.sol";
import {IDrandBeacon, ITapReferenceCollection, ITapDrandReveal} from "./ITapDrandReveal.sol";

/// @title drand reveal controller for a reference TAP-721 collection
/// @notice Creates a collection in its constructor from the initcode it is given, with itself as `initialOwner`. With
///         the reference TapNetlistNFT initcode the collection never has a minter and only this contract can mint,
///         commit, reveal, set the base URI and freeze; the controller never calls setMinter, transferOwnership,
///         commitManifestNoReveal, commitManifestTokenSet or scheduleBlockhashReveal. THE INITCODE IS NOT VERIFIED ON
///         CHAIN: the constructor only checks that the new contract reports this controller as its owner, so a crafted
///         initcode (a planted minter, a different mint rule) is accepted. Everything claimed here holds for the
///         reference initcode only, and that is proven by comparing `collectionInitCodeHash` (and the collection
///         runtime) with a reference build OFF chain, as an off-chain checker does (initcode hash, collection
///         runtime, VM runtime). The master seed can only be the drand quicknet randomness of one round R:
///         - R is fixed once, at the commit (fixed mode: the round in the manifest, TAP-721 §6.1, more than
///           MIN_FIXED_LEAD ahead of clock()) or by `scheduleReveal` after minting is over (deferred mode: the first
///           round more than `scheduleDelay` ahead of clock());
///         - clock() = max(chain time + lagAtCommit, time of the newest drand round verified in the beacon): the lag
///           the commit saw is never forgotten, and a posted round only moves the clock forward;
///         - every mint goes through `mint` here and only while R is unset or still more than REVEAL_DELAY ahead of
///           clock(), so, short of an unseen chain lag (below), no token is minted once the seed can be known;
///         - `revealDrand` (anyone) writes the beacon's BLS-verified randomness of R; the caller picks the moment only;
///         - `revealUnverified` (the admin, emergency) opens 72 h after R and only while the beacon fails the
///           self-test it passed at the commit; its bytes are published, so a checker sees whether they are R's.
///         Residuals that no on-chain clock removes (chain time can trail real time and the contract cannot see it):
///         - fixed mode: a chain clock that trails real time by more than MIN_FIXED_LEAD at the commit lets the admin
///           commit an already-public R; a clock that falls behind by more than REVEAL_DELAY after the commit,
///           beyond the lag the commit saw, with no real-time round posted to the beacon, leaves the gateway open
///           after R is public;
///         - deferred mode: see `scheduleReveal`.
contract TapDrandReveal is ITapDrandReveal {
    /// DrandBeacon (the upstream TAP-721 recipe: solc 0.8.28, runs 10000, shanghai, no metadata) at its CREATE2
    /// address through the deterministic deployer 0x4e59b44847b379578588920cA78FbF26c0B4956C with salt 0: the same
    /// address on every chain
    IDrandBeacon public constant DRAND_BEACON = IDrandBeacon(0x777D3Ece3CB4E7D3782Da938CbCf8c2c8AcE55Ca);
    /// keccak256 of that beacon's runtime code (an ownerless contract with no immutables)
    bytes32 public constant DRAND_BEACON_CODEHASH = 0x5af33305a251aaeff7728080afdf2cdf71d97395115d0a4faa98dd8c9f951fe9;
    /// The gateway cutoff (fixed mode): a mint needs R >= roundAt(clock() + REVEAL_DELAY) + 1. It does NOT place a
    /// deferred R (that is `scheduleDelay`) and is not the fixed-mode commit bound (that is MIN_FIXED_LEAD).
    uint256 public constant REVEAL_DELAY = 10 minutes;
    /// fixed mode, at the commit: R > roundAt(clock() + MIN_FIXED_LEAD). Above the 12 h OP Stack sequencing window,
    /// so a chain clock that trails real time by less than this cannot make an already-public round a valid R
    uint256 public constant MIN_FIXED_LEAD = 13 hours;
    /// fixed mode: the furthest R may lie ahead at the commit (a guard against an irreversible typo)
    uint256 public constant MAX_FIXED_LEAD = 365 days;
    /// bounds of the constructor argument `scheduleDelay`
    uint256 public constant MIN_SCHEDULE_DELAY = 1 hours;
    uint256 public constant MAX_SCHEDULE_DELAY = 7 days;
    /// deferred mode: anyone may schedule the reveal this long after minting closed (liveness without the admin)
    uint256 public constant PUBLIC_SCHEDULE_DELAY = 1 days;
    /// emergency path: not before quicknetTime(R) + FALLBACK_DELAY
    uint256 public constant FALLBACK_DELAY = 72 hours;
    /// the self-test round at the commit is at most this old
    uint256 public constant SELFTEST_MAX_AGE = 1 days;
    /// gas given to the beacon to re-run the self-test: well above a full check under any listed price schedule
    uint256 public constant SELFTEST_GAS = 2_000_000;

    ITapReferenceCollection public immutable collection;
    address public immutable admin;
    /// deferred mode: `scheduleReveal` fixes R = roundAt(clock() + scheduleDelay) + 1. In [MIN_SCHEDULE_DELAY,
    /// MAX_SCHEDULE_DELAY]; fixed mode never reads it. Pick it above the longest chain-clock stall you accept.
    uint256 public immutable scheduleDelay;
    /// keccak256 of the collection initcode the constructor was given (without the arguments it appends). Evidence for
    /// an off-chain comparison with a reference build; NOT proof that the collection is the reference one.
    bytes32 public immutable collectionInitCodeHash;

    // slot: the mint path
    uint64 public supply; // non-zero once committed (the reference rejects supply 0)
    uint64 public minted;
    uint48 public lastMintAt;
    uint48 public closedAt;
    bool public fixedRound;
    // slot: the round and the reveal
    uint64 public revealRound;
    uint48 public revealedAt;
    bool public verifiedOnChain;
    uint48 public committedAt;
    uint48 public scheduledAt;
    /// max(0, quicknetTime(selfTestRound) - block.timestamp) at the commit; added to block.timestamp in clock(). Shares
    /// the slot with revealRound and revealedAt, which every mint reads anyway.
    uint40 public lagAtCommit;
    // slot: the evidence
    uint64 public newestRoundAtSchedule;
    uint64 public selfTestRound;
    bytes public selfTestSig;

    mapping(address account => bool) public isMinter;

    /// @notice Creates the collection: CREATE(collectionInitCode ‖ abi.encode(name_, symbol_, baseURI_, this)).
    ///         Reverts BadBeacon unless DRAND_BEACON holds the pinned beacon, Unauthorized for admin_ = 0, BadDelay
    ///         unless scheduleDelay_ is in [MIN_SCHEDULE_DELAY, MAX_SCHEDULE_DELAY] (checked in fixed mode too, which
    ///         never reads it: pass MIN_SCHEDULE_DELAY), and BadCollection unless the creation succeeded and the new
    ///         contract reports this contract as its owner. The initcode itself is NOT verified: any initcode whose
    ///         contract answers owner() with this address is accepted. Kit proof compares collectionInitCodeHash with
    ///         a reference build off chain.
    constructor(
        address admin_,
        uint256 scheduleDelay_,
        bytes memory collectionInitCode,
        string memory name_,
        string memory symbol_,
        string memory baseURI_
    ) {
        if (address(DRAND_BEACON).codehash != DRAND_BEACON_CODEHASH) revert BadBeacon();
        if (admin_ == address(0)) revert Unauthorized();
        if (scheduleDelay_ < MIN_SCHEDULE_DELAY || scheduleDelay_ > MAX_SCHEDULE_DELAY) revert BadDelay();
        bytes memory initCode =
            abi.encodePacked(collectionInitCode, abi.encode(name_, symbol_, baseURI_, address(this)));
        address c;
        assembly ("memory-safe") {
            c := create(0, add(initCode, 0x20), mload(initCode))
        }
        if (c == address(0)) revert BadCollection();
        (bool ok, bytes memory ret) = c.staticcall(abi.encodeCall(ITapReferenceCollection.owner, ()));
        if (!ok || ret.length != 32 || bytes32(ret) != bytes32(uint256(uint160(address(this))))) revert BadCollection();
        collection = ITapReferenceCollection(c);
        admin = admin_;
        scheduleDelay = scheduleDelay_;
        bytes32 h = keccak256(collectionInitCode);
        collectionInitCodeHash = h;
        emit CollectionCreated(c, h);
    }

    // ------------------------------------------------------------------ derived views

    /// @notice max(block.timestamp + lagAtCommit, quicknetTime(latestVerifiedRound)): the later of the chain clock
    ///         (corrected by the lag the commit proved) and the newest drand round anyone verified in the beacon.
    function clock() public view returns (uint256) {
        uint256 chainTime = block.timestamp + lagAtCommit;
        uint256 drandTime = DRAND_BEACON.quicknetTime(DRAND_BEACON.latestVerifiedRound());
        return drandTime > chainTime ? drandTime : chainTime;
    }

    /// @notice The gateway cutoff: the first round produced more than REVEAL_DELAY after clock().
    function earliestRound() public view returns (uint64) {
        return DRAND_BEACON.roundAt(clock() + REVEAL_DELAY) + 1;
    }

    /// @notice The round scheduleReveal would fix now (deferred mode): the first round produced more than
    ///         scheduleDelay after clock().
    function scheduleRound() public view returns (uint64) {
        return DRAND_BEACON.roundAt(clock() + scheduleDelay) + 1;
    }

    function mintOpen() public view returns (bool) {
        if (supply == 0 || closedAt != 0 || revealedAt != 0 || minted >= supply) return false;
        uint64 round = revealRound;
        return round == 0 || round >= earliestRound();
    }

    function verifierWorks() external view returns (bool) {
        return _verifierWorks();
    }

    function manifestHash() external view returns (bytes32) {
        return collection.manifestHash();
    }

    // ------------------------------------------------------------------ admin

    function allowMinter(address account, bool allowed) external {
        if (msg.sender != admin) revert Unauthorized();
        isMinter[account] = allowed;
        emit MinterAllowed(account, allowed);
    }

    /// @notice Commit the manifest (range mode), once. The beacon must accept a fresh quicknet signature (at most
    ///         SELFTEST_MAX_AGE old, randomness = SHA-256 of the bytes) and reject the same bytes with the sort flag
    ///         flipped. The self-test round, if it is ahead of the block, proves the chain clock trails real time by at
    ///         least that much: the difference is stored as lagAtCommit and counted in clock() from then on.
    ///         round != 0 fixes R now (fixed mode): R must lie more than MIN_FIXED_LEAD (13 h) ahead of clock() and at
    ///         most MAX_FIXED_LEAD ahead. A chain clock that trails real time by more than MIN_FIXED_LEAD at this
    ///         moment, with no real-time round in the beacon, can still be used to commit an already-public R: the
    ///         contract cannot see such a lag. round = 0: deferred mode.
    function commit(
        bytes32 manifestHash_,
        uint256 firstTokenId,
        uint256 supply_,
        ITapNetlistNFT.Pool[] calldata pools,
        uint64 round,
        uint64 selfTestRound_,
        bytes calldata selfTestSig_
    ) external {
        if (msg.sender != admin) revert Unauthorized();
        if (committedAt != 0) revert AlreadyCommitted();
        _selfTest(selfTestRound_, selfTestSig_);
        committedAt = uint48(block.timestamp);
        if (round != 0) _fixRound(round, selfTestRound_);
        collection.commitManifest(manifestHash_, firstTokenId, supply_, pools);
        supply = uint64(supply_); // the reference caps supply at MAX_TOKENS (100,000)
        emit Committed(manifestHash_, round, selfTestRound_);
    }

    function setBaseURI(string calldata baseURI) external {
        if (msg.sender != admin) revert Unauthorized();
        collection.setBaseURI(baseURI); // reverts in the collection once frozen
    }

    /// @notice Freeze the collection; the reference requires the reveal and renounces ownership, so every power
    ///         forwarded by this contract ends.
    function freeze() external {
        if (msg.sender != admin) revert Unauthorized();
        collection.freeze();
    }

    /// @notice Emergency path: FALLBACK_DELAY after round R, R not cached in the beacon, and the beacon failing the
    ///         self-test it passed at the commit (given SELFTEST_GAS whatever the caller sends). The seed is SHA-256 of
    ///         the 48 published bytes; while the verifier works, revealDrand is the only way, so nobody can write a
    ///         seed of their choosing.
    function revealUnverified(bytes calldata signature) external {
        if (msg.sender != admin) revert Unauthorized();
        uint64 round = revealRound;
        if (round == 0) revert NotScheduled();
        if (revealedAt != 0) revert AlreadyRevealed();
        if (block.timestamp < DRAND_BEACON.quicknetTime(round) + FALLBACK_DELAY) revert TooEarly();
        if (DRAND_BEACON.randomnessOf(round) != 0) revert RoundCached();
        if (_verifierWorks()) revert VerifierWorks();
        if (signature.length != 48) revert BadSignature();
        uint8 flags = uint8(signature[0]) & 0xe0;
        if (flags != 0x80 && flags != 0xa0) revert BadSignature();
        bytes32 seed = sha256(signature);
        revealedAt = uint48(block.timestamp);
        collection.reveal(seed);
        emit RevealedUnverified(round, signature, seed);
    }

    // ------------------------------------------------------------------ minters

    /// @notice The reference mint, gated: minters only, while mintOpen(). Closes the gateway at the last id.
    function mint(address to, uint256 tokenId) external {
        if (!isMinter[msg.sender]) revert Unauthorized();
        if (!mintOpen()) revert MintingClosed();
        uint64 n = minted + 1;
        minted = n;
        lastMintAt = uint48(block.timestamp);
        if (n == supply) {
            closedAt = uint48(block.timestamp);
            emit MintClosed(n, address(0));
        }
        collection.mint(to, tokenId); // reverts for duplicate or out-of-range ids, undoing the count
    }

    // ------------------------------------------------------------------ admin or a minter

    /// @notice Close minting for good (a sale can close itself).
    function closeMint() external {
        if (msg.sender != admin && !isMinter[msg.sender]) revert Unauthorized();
        if (committedAt == 0) revert NotCommitted();
        if (closedAt != 0 || revealedAt != 0) revert MintingClosed();
        closedAt = uint48(block.timestamp);
        emit MintClosed(minted, msg.sender);
    }

    // ------------------------------ admin; anyone from closedAt + PUBLIC_SCHEDULE_DELAY

    /// @notice Deferred mode, once, after minting is over: R = scheduleRound() = roundAt(clock() + scheduleDelay) + 1.
    ///         The scheduler picks the block, never the value for a given block. Post the newest drand round to the
    ///         beacon in the same batch so that the clock is real time.
    ///         RESIDUAL, not removable on chain: if the chain clock trails real time by MORE than scheduleDelay (a
    ///         sequencer stall followed by catch-up) and no real-time drand round has been posted to the beacon, R may
    ///         already be public when it is fixed. The scheduler (the admin, or anyone from closedAt +
    ///         PUBLIC_SCHEDULE_DELAY) can then post an older round that looks fresh by the chain clock and choose among
    ///         the blocks of that window, i.e. among rounds already public, so the seed is no longer independent of
    ///         the scheduler. scheduleDelay only sets how long a stall that takes (at least 1 hour, chosen by the
    ///         deployer); a keeper that posts the newest round to the beacon every minute pins clock() to real time
    ///         while it runs.
    function scheduleReveal() external {
        if (committedAt == 0) revert NotCommitted();
        if (revealRound != 0) revert AlreadyScheduled();
        uint48 closed = closedAt;
        if (closed == 0) revert MintingOpen();
        if (msg.sender != admin && block.timestamp < uint256(closed) + PUBLIC_SCHEDULE_DELAY) revert Unauthorized();
        uint64 round = scheduleRound();
        _schedule(round, DRAND_BEACON.quicknetTime(round), DRAND_BEACON.latestVerifiedRound());
    }

    // ------------------------------------------------------------------ anyone

    /// @notice Reveal with the drand quicknet signature of R: seed = the beacon's BLS-verified (or cached) randomness.
    function revealDrand(bytes calldata signature) external {
        uint64 round = revealRound;
        if (round == 0) revert NotScheduled();
        if (revealedAt != 0) revert AlreadyRevealed();
        bytes32 seed = DRAND_BEACON.verify(round, signature);
        revealedAt = uint48(block.timestamp);
        verifiedOnChain = true;
        collection.reveal(seed);
        emit RevealedVerified(round, seed, msg.sender);
    }

    // ------------------------------------------------------------------ internal

    /// The commit-time self-test: the beacon accepts a fresh signature (randomness = SHA-256 of it) and rejects the
    /// same bytes with the sort flag flipped. Stores the evidence and lagAtCommit. A signed round cannot come from
    /// the future, so a round that is ahead of the block proves the chain clock trails real time by at least the
    /// difference; it is kept (capped at the type, which no real round reaches) and clock() counts it from now on.
    function _selfTest(uint64 round, bytes calldata sig) private {
        uint256 tRound = DRAND_BEACON.quicknetTime(round);
        if (tRound + SELFTEST_MAX_AGE < block.timestamp) revert SelfTestFailed();
        (bool ok, bytes32 rnd) = DRAND_BEACON.check(round, sig);
        if (!ok || rnd != sha256(sig)) revert SelfTestFailed();
        bytes memory flipped = sig;
        flipped[0] ^= 0x20;
        (bool okFlipped,) = DRAND_BEACON.check(round, flipped);
        if (okFlipped) revert SelfTestFailed();
        selfTestRound = round;
        selfTestSig = sig;
        uint256 lag = tRound > block.timestamp ? tRound - block.timestamp : 0;
        lagAtCommit = lag > type(uint40).max ? type(uint40).max : uint40(lag);
    }

    /// Fixed mode: R must lie more than MIN_FIXED_LEAD ahead of clock() (which already counts the lag just stored, so
    /// it is at least the self-test round's time) and at most MAX_FIXED_LEAD ahead.
    function _fixRound(uint64 round, uint64 selfTestRound_) private {
        uint64 newest = DRAND_BEACON.latestVerifiedRound();
        if (selfTestRound_ > newest) newest = selfTestRound_;
        uint256 t = clock();
        uint256 roundTime = DRAND_BEACON.quicknetTime(round);
        if (round <= DRAND_BEACON.roundAt(t + MIN_FIXED_LEAD) || roundTime > t + MAX_FIXED_LEAD) revert BadRound();
        fixedRound = true;
        _schedule(round, roundTime, newest);
    }

    function _schedule(uint64 round, uint256 roundTime, uint64 newest) private {
        revealRound = round;
        scheduledAt = uint48(block.timestamp);
        newestRoundAtSchedule = newest;
        emit RevealScheduled(round, roundTime, newest);
    }

    /// The commit-time self-test with exactly SELFTEST_GAS: true iff the beacon still accepts the stored round and
    /// bytes with randomness = SHA-256 of them. A revert, a short answer or a rejection all count as failing.
    function _verifierWorks() private view returns (bool) {
        bytes memory sig = selfTestSig;
        bytes memory data = abi.encodeCall(IDrandBeacon.check, (selfTestRound, sig));
        // the call gets its full gas whatever the caller sends, so a failure cannot be forced by starving it
        if (gasleft() < SELFTEST_GAS + SELFTEST_GAS / 63 + 50_000) revert GasTooLow();
        (bool success, bytes memory ret) = address(DRAND_BEACON).staticcall{gas: SELFTEST_GAS}(data);
        if (!success || ret.length != 64) return false;
        (uint256 ok, bytes32 rnd) = abi.decode(ret, (uint256, bytes32));
        return ok == 1 && rnd == sha256(sig);
    }
}
