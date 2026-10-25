// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../interfaces/ITapNetlistNFT.sol";

/// The functions of DrandBeacon (DrandBeacon.sol in this folder) that the kit uses.
interface IDrandBeacon {
    /// quicknet 52db9ba7…e971 (read by tools only)
    function CHAIN_HASH() external view returns (bytes32);
    function randomnessOf(uint64 round) external view returns (bytes32);
    function latestVerifiedRound() external view returns (uint64);
    function verify(uint64 round, bytes calldata sig) external returns (bytes32 randomness);
    function check(uint64 round, bytes calldata sig) external view returns (bool ok, bytes32 randomness);
    function quicknetTime(uint64 round) external pure returns (uint256);
    function roundAt(uint256 timestamp) external pure returns (uint64);
}

/// The owner surface of the reference TapNetlistNFT that the controller forwards, and nothing else.
/// (setMinter, transferOwnership, commitManifestNoReveal, commitManifestTokenSet and scheduleBlockhashReveal are
/// deliberately absent: the controller has no code path to them.)
interface ITapReferenceCollection {
    function owner() external view returns (address);
    function manifestHash() external view returns (bytes32);
    function masterSeed() external view returns (bytes32);
    function commitManifest(
        bytes32 manifestHash,
        uint256 firstTokenId,
        uint256 supply,
        ITapNetlistNFT.Pool[] calldata pools
    ) external;
    function mint(address to, uint256 tokenId) external;
    function reveal(bytes32 seed) external;
    function setBaseURI(string calldata baseURI) external;
    function freeze() external;
}

/// @title drand reveal controller for a reference TAP-721 collection (TAP draft "Netlist-Bound NFTs" §6.1)
/// @notice The controller creates the collection, is its only owner and, with the reference initcode, its only minter,
///         and writes the master seed only as the drand quicknet randomness of a round R that nobody could know while
///         tokens were minted. Two clocks are separated on purpose:
///         - REVEAL_DELAY (10 min) is the gateway cutoff of fixed mode: no mint once R is closer than that to clock();
///         - scheduleDelay (an immutable, 1 hour to 7 days) is how far ahead of clock() `scheduleReveal` puts R in
///           deferred mode.
///         Chain time and drand time can disagree (a lagging chain clock); the residuals are stated per function.
///         The kit's claims hold only for the reference collection initcode, which is NOT verified on chain: see
///         `collectionInitCodeHash` and the factory.
interface ITapDrandReveal {
    // ------------------------------------------------------------------ events

    /// Emitted by the constructor. `collectionInitCodeHash` is keccak256 of the initcode the controller was GIVEN; it
    /// is evidence for an off-chain comparison with a reference build, NOT proof that the collection is the reference
    /// one.
    event CollectionCreated(address indexed collection, bytes32 collectionInitCodeHash);
    event MinterAllowed(address indexed account, bool allowed);
    /// revealRound = 0: deferred mode (R fixed later by scheduleReveal)
    event Committed(bytes32 indexed manifestHash, uint64 revealRound, uint64 selfTestRound);
    /// by = address(0) when the last id was minted (sold out)
    event MintClosed(uint64 minted, address by);
    /// Emitted once: at the commit (fixed mode) or by scheduleReveal (deferred mode). newestRound = the newest drand
    /// round known on chain when R was fixed (0 if none).
    event RevealScheduled(uint64 round, uint256 roundTime, uint64 newestRound);
    event RevealedVerified(uint64 round, bytes32 seed, address by);
    event RevealedUnverified(uint64 round, bytes signature, bytes32 seed);

    // ------------------------------------------------------------------ errors

    error Unauthorized();
    /// no DrandBeacon code at DRAND_BEACON
    error BadBeacon();
    /// scheduleDelay outside [MIN_SCHEDULE_DELAY, MAX_SCHEDULE_DELAY]
    error BadDelay();
    /// CREATE failed or the new contract does not report the controller as its owner
    error BadCollection();
    error AlreadyCommitted();
    error NotCommitted();
    /// the verifier rejected a fresh round, accepted it with the sort flag flipped, or the round is over a day old
    error SelfTestFailed();
    /// fixed mode: R <= roundAt(clock() + MIN_FIXED_LEAD) or more than MAX_FIXED_LEAD ahead
    error BadRound();
    error MintingClosed();
    /// scheduleReveal before minting is over
    error MintingOpen();
    error AlreadyScheduled();
    error NotScheduled();
    error AlreadyRevealed();
    /// emergency path before quicknetTime(R) + FALLBACK_DELAY
    error TooEarly();
    /// emergency path while the beacon holds R: use revealDrand
    error RoundCached();
    /// emergency path while the beacon still passes its commit-time self-test
    error VerifierWorks();
    /// emergency path: not 48 bytes, or not a canonical compressed-G1 flag byte (0x80 / 0xa0)
    error BadSignature();
    /// too little gas left to give the self-test SELFTEST_GAS
    error GasTooLow();

    // ------------------------------------------------------------------ constants

    function DRAND_BEACON() external view returns (IDrandBeacon);
    function DRAND_BEACON_CODEHASH() external view returns (bytes32);
    /// gateway cutoff (fixed mode): a mint needs R >= earliestRound() = roundAt(clock() + REVEAL_DELAY) + 1. Not used
    /// to place R in deferred mode (that is scheduleDelay).
    function REVEAL_DELAY() external view returns (uint256);
    /// fixed mode: at the commit R must lie more than this ahead of clock(): above the 12 h OP Stack sequencing window,
    /// so a chain clock that lags real time by less than this cannot make R a round that is already public
    function MIN_FIXED_LEAD() external view returns (uint256);
    /// fixed mode: the furthest R may lie ahead at the commit (a guard against an irreversible typo)
    function MAX_FIXED_LEAD() external view returns (uint256);
    /// bounds of the constructor argument scheduleDelay
    function MIN_SCHEDULE_DELAY() external view returns (uint256);
    function MAX_SCHEDULE_DELAY() external view returns (uint256);
    /// deferred mode: anyone may schedule the reveal this long after minting closed (liveness without the admin)
    function PUBLIC_SCHEDULE_DELAY() external view returns (uint256);
    function FALLBACK_DELAY() external view returns (uint256);
    function SELFTEST_MAX_AGE() external view returns (uint256);
    function SELFTEST_GAS() external view returns (uint256);

    // ------------------------------------------------------------------ immutables

    function collection() external view returns (ITapReferenceCollection);
    function admin() external view returns (address);
    /// deferred mode: scheduleReveal fixes R = roundAt(clock() + scheduleDelay) + 1. Set once by the constructor. Fixed
    /// mode never reads it.
    function scheduleDelay() external view returns (uint256);
    /// keccak256 of the collection initcode GIVEN to the constructor, without the constructor arguments the controller
    /// appends. Not verified on chain: kit proof needs this hash compared off chain with a reference build.
    function collectionInitCodeHash() external view returns (bytes32);

    // ------------------------------------------------------------------ state

    /// gateway minters (the collection itself has none when it is the reference collection)
    function isMinter(address account) external view returns (bool);
    function committedAt() external view returns (uint48);
    /// true: R came with the commit (fixed mode)
    function fixedRound() external view returns (bool);
    /// from the committed token range
    function supply() external view returns (uint64);
    /// every token of the collection, all minted through the gateway
    function minted() external view returns (uint64);
    function lastMintAt() external view returns (uint48);
    /// set once, by closeMint or by minting the last id; never cleared
    function closedAt() external view returns (uint48);
    /// R; 0 until fixed
    function revealRound() external view returns (uint64);
    /// block time when R was fixed (the commit in fixed mode)
    function scheduledAt() external view returns (uint48);
    function newestRoundAtSchedule() external view returns (uint64);
    function revealedAt() external view returns (uint48);
    /// false only after revealUnverified
    function verifiedOnChain() external view returns (bool);
    function selfTestRound() external view returns (uint64);
    /// the 48 bytes that passed the self-test at the commit
    function selfTestSig() external view returns (bytes memory);
    /// max(0, quicknetTime(selfTestRound) - block.timestamp) at the commit: a lower bound of how far the chain clock
    /// trailed real time then (a signed round cannot come from the future). It is added to block.timestamp in clock()
    /// from then on, so the lag seen once is never forgotten. Fail-safe: if the chain later catches up, the gateway
    /// closes (and a deferred R lies) up to this much early. Zero when the commit round was behind the block.
    function lagAtCommit() external view returns (uint40);

    // ------------------------------------------------------------------ derived views

    /// max(block.timestamp + lagAtCommit, quicknetTime(DRAND_BEACON.latestVerifiedRound()))
    function clock() external view returns (uint256);
    /// roundAt(clock() + REVEAL_DELAY) + 1: the first quicknet round produced more than REVEAL_DELAY after clock().
    /// The gateway's cutoff (mintOpen); it does not place a deferred R.
    function earliestRound() external view returns (uint64);
    /// roundAt(clock() + scheduleDelay) + 1: the round scheduleReveal would fix as R now (deferred mode)
    function scheduleRound() external view returns (uint64);
    /// committed, not closed, not revealed, minted < supply, and R unset or R >= earliestRound()
    function mintOpen() external view returns (bool);
    /// re-runs the commit-time self-test with SELFTEST_GAS (for tools; reverts GasTooLow if starved)
    function verifierWorks() external view returns (bool);
    /// collection.manifestHash(), so a sale written for the reference collection can point at the controller
    function manifestHash() external view returns (bytes32);

    // ------------------------------------------------------------------ admin

    function allowMinter(address account, bool allowed) external;
    /// Once. Runs the self-test, records lagAtCommit, fixes R when round != 0 (fixed mode: R > roundAt(clock() +
    /// MIN_FIXED_LEAD)), then forwards commitManifest (range mode).
    function commit(
        bytes32 manifestHash_,
        uint256 firstTokenId,
        uint256 supply_,
        ITapNetlistNFT.Pool[] calldata pools,
        uint64 round,
        uint64 selfTestRound_,
        bytes calldata selfTestSig_
    ) external;
    /// until frozen (the reference reverts once the collection is frozen)
    function setBaseURI(string calldata baseURI) external;
    /// after the reveal (the reference requires it); renounces the collection's ownership
    function freeze() external;
    /// emergency path for a broken verifier
    function revealUnverified(bytes calldata signature) external;

    // ------------------------------------------------------------------ minters

    /// Same selector as the reference collection's mint. Counts, records lastMintAt, closes at minted == supply.
    function mint(address to, uint256 tokenId) external;

    // ------------------------------------------------------------------ admin or a minter

    function closeMint() external;

    // ------------------------------ admin; anyone from closedAt + PUBLIC_SCHEDULE_DELAY

    /// Deferred mode only, once, after minting is over: R = scheduleRound(). Residual: see the implementation.
    function scheduleReveal() external;

    // ------------------------------------------------------------------ anyone

    /// seed = DRAND_BEACON.verify(R, signature), then collection.reveal(seed).
    function revealDrand(bytes calldata signature) external;
}
