// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistEval} from "../interfaces/ITapNetlistEval.sol";
import {ITapNetlistNFT} from "../interfaces/ITapNetlistNFT.sol";
import {ITapNetlistTokenSet} from "../interfaces/ITapNetlistTokenSet.sol";
import {IERC4906} from "../vendor/IERC4906.sol";
import {Owned} from "../vendor/Owned.sol";
import {TapMerkle} from "./TapMerkle.sol";
import {TapNetlistCheck} from "./TapNetlistCheck.sol";
import {TapNetlistStore} from "./TapNetlistStore.sol";
import {TapNetlistVM} from "./TapNetlistVM.sol";
import {TapPermutation} from "./TapPermutation.sol";

/// @title Manifest, reveal and binding logic shared by the collection and the companion
/// @notice Lifecycle: the owner commits the manifest once (`commitManifest`), then sets the reveal seed
///         once (`reveal`, or the scheduled `revealFromBlockhash`). Afterwards anyone may `bind` the
///         entries a token received, proven against the pool roots, and `storeNetlist` the bound files.
///         Stored files can be run by any contract through the ITapNetlistEval extension; therefore
///         `storeNetlist` always runs the full tapnet/1 validity check (TapNetlistCheck), not just the hash.
///
///         The seed's provenance (drand round, VRF request, …) is declared in the manifest's `reveal`
///         object and verified off chain; this contract only guarantees the seed is set after the manifest
///         is committed and never changes.
abstract contract TapNetlistCore is TapNetlistStore, ITapNetlistEval, ITapNetlistTokenSet, Owned, IERC4906 {
    /// masterSeed() of a collection committed with reveal source "none" (identity assignment).
    bytes32 public constant NO_REVEAL = bytes32(type(uint256).max);
    /// Reference-implementation limit on supply (token sets and pools). The standard allows up to 2^32;
    /// this bound keeps whole-set hashing and loading within one block on every TapeOut chain.
    uint256 public constant MAX_TOKENS = 100_000;
    /// Furthest a block-hash reveal may be scheduled ahead of the scheduling block.
    uint256 public constant MAX_REVEAL_DELAY = 1_000_000;
    uint8 internal constant FIELD_IMAGE = 1;
    uint8 internal constant FIELD_NETLIST = 2;

    event RevealScheduled(uint256 blockNumber);
    event PoolLoaded(uint256 indexed poolIndex);
    event TokenSetLoaded(bytes32 tokenSetHash);
    event TokenSetLoadFailed(address indexed loader);
    event PoolLoadFailed(uint256 indexed poolIndex, address indexed loader);

    error AlreadyCommitted();
    error NotCommitted();
    error AlreadyRevealed();
    error NotRevealed();
    error InvalidManifest();
    error InvalidPool(uint256 poolIndex);
    error TokenOutOfRange(uint256 tokenId);
    error PoolOutOfRange(uint256 poolIndex);
    error InvalidValues();
    error InvalidProof();
    error NotBound(uint256 tokenId);
    error RevealIsScheduled(uint256 blockNumber);
    error InvalidRevealBlock(uint256 blockNumber);
    error BlockhashUnavailable(uint256 blockNumber);
    error NoRevealCollection();
    error ZeroOwner();
    error BadChunk(uint256 expectedOffset);
    error NotInTokenSet(uint256 tokenId);
    error TokenSetNotLoaded();
    error NotTokenSetMode();

    bytes32 private _manifestHash;
    uint256 private _firstTokenId;
    uint256 private _supply;
    Pool[] private _pools;
    bytes32 private _masterSeed;
    bytes32[] private _poolSeeds;
    uint256 private _revealBlock;

    mapping(uint256 tokenId => bytes32) private _imageHash;
    mapping(uint256 tokenId => bytes32) private _netlistHash;

    /// Loaded pools: field values in entry order, as SSTORE2 pages of `_perPage(k)` entries each.
    mapping(uint256 poolIndex => address[]) private _poolPages;

    struct LoadSession {
        uint256 count; // entries loaded so far
        bytes32[33] frontier; // pending left nodes; level L is set iff bit L of count is set
        address[] pages;
    }

    /// Token-set mode: ascending valid ids, packed u32be, in SSTORE2 pages of IDS_PER_PAGE ids.
    uint256 public constant IDS_PER_PAGE = 6143;
    bytes32 private _tokenSetHash;
    address[] private _setPages;

    struct SetSession {
        uint256 count;
        uint256 next; // smallest id the next one may be (last id + 1)
        address[] pages;
    }

    mapping(address loader => SetSession) private _setSessions;

    /// One session per (pool, loader), so nobody can disturb another account's loading.
    mapping(uint256 poolIndex => mapping(address loader => LoadSession)) private _sessions;

    constructor(address initialOwner) Owned(initialOwner) {}

    // ------------------------------------------------------------------ owner, once each

    /// @notice Commit the manifest. Field masks must be non-empty, use only bits 1 and 2 and be disjoint
    ///         across pools, so each token has at most one image and one netlist hash.
    function commitManifest(bytes32 manifestHash_, uint256 firstTokenId, uint256 supply, Pool[] calldata pools_)
        external
        virtual
        onlyOwner
    {
        _commitManifest(manifestHash_, firstTokenId, supply, pools_);
    }

    /// @notice Commit a manifest with `reveal.source = "none"`: masterSeed() becomes NO_REVEAL at once,
    ///         token firstTokenId + i receives entry i of every pool, and `bind` works immediately.
    ///         Every reveal path then reverts (AlreadyRevealed).
    function commitManifestNoReveal(bytes32 manifestHash_, uint256 firstTokenId, uint256 supply, Pool[] calldata pools_)
        external
        virtual
        onlyOwner
    {
        _commitManifest(manifestHash_, firstTokenId, supply, pools_);
        _setNoReveal();
    }

    /// @notice Commit a manifest whose tokens are an explicit set of `supply` ids (ITapNetlistTokenSet),
    ///         committed by `tokenSetHash`; `noReveal` as for commitManifestNoReveal. Token positions are
    ///         ranks in the set, which must be loaded (`loadTokenSet`) before entryIndexOf answers.
    function commitManifestTokenSet(
        bytes32 manifestHash_,
        bytes32 tokenSetHash_,
        uint256 supply,
        Pool[] calldata pools_,
        bool noReveal
    ) external virtual onlyOwner {
        if (tokenSetHash_ == 0) revert InvalidManifest();
        _tokenSetHash = tokenSetHash_; // before the commit, so its ERC-4906 event uses set-mode bounds
        _commitManifest(manifestHash_, 0, supply, pools_);
        if (noReveal) _setNoReveal();
    }

    function _setNoReveal() private {
        _masterSeed = NO_REVEAL;
        emit Revealed(NO_REVEAL); // the commit in the same call already emitted ERC-4906
    }

    function _commitManifest(bytes32 manifestHash_, uint256 firstTokenId, uint256 supply, Pool[] calldata pools_)
        internal
    {
        if (_manifestHash != 0) revert AlreadyCommitted();
        if (
            manifestHash_ == 0 || supply == 0 || supply > MAX_TOKENS || pools_.length == 0
                || firstTokenId > type(uint256).max - (supply - 1)
        ) revert InvalidManifest();
        uint8 seen;
        for (uint256 i; i < pools_.length; ++i) {
            uint8 f = pools_[i].fields;
            if (f == 0 || f > 3 || f & seen != 0 || pools_[i].root == 0 || !_validLabel(pools_[i].label)) {
                revert InvalidPool(i);
            }
            if (i == 1 && keccak256(bytes(pools_[1].label)) == keccak256(bytes(pools_[0].label))) {
                revert InvalidPool(1);
            }
            seen |= f;
            Pool storage p = _pools.push();
            p.label = pools_[i].label;
            p.fields = f;
            p.root = pools_[i].root;
        }
        _manifestHash = manifestHash_;
        _firstTokenId = firstTokenId;
        _supply = supply;
        emit ManifestCommitted(manifestHash_);
        _emitAllMetadataUpdate();
    }

    /// @notice Set the master seed. Disabled once a block-hash reveal is scheduled.
    function reveal(bytes32 seed) external virtual onlyOwner {
        if (_revealBlock != 0) revert RevealIsScheduled(_revealBlock);
        _reveal(seed);
    }

    /// @notice NOT RECOMMENDED on single-sequencer chains (the sequencer chooses block hashes).
    ///         Schedule, exactly once, a block whose hash becomes the seed: after the current block (hence
    ///         after the manifest commit) and at most MAX_REVEAL_DELAY blocks ahead. There is no second
    ///         chance: if nobody calls `revealFromBlockhash` within the 256 blocks after it, the collection
    ///         can never be revealed (nor frozen). Choosing a second seed would let the owner reroll.
    function scheduleBlockhashReveal(uint256 blockNumber) external virtual onlyOwner {
        if (_manifestHash == 0) revert NotCommitted();
        if (_masterSeed != 0) revert AlreadyRevealed();
        if (_revealBlock != 0) revert RevealIsScheduled(_revealBlock);
        if (blockNumber <= block.number || blockNumber - block.number > MAX_REVEAL_DELAY) {
            revert InvalidRevealBlock(blockNumber);
        }
        _revealBlock = blockNumber;
        emit RevealScheduled(blockNumber);
    }

    /// @notice NOT RECOMMENDED on single-sequencer chains. Permissionless: seed = blockhash(blockNumber)
    ///         of the scheduled block, callable during the 256 blocks after it.
    function revealFromBlockhash(uint256 blockNumber) external virtual {
        if (blockNumber == 0 || blockNumber != _revealBlock) revert InvalidRevealBlock(blockNumber);
        bytes32 seed = blockhash(blockNumber);
        if (seed == 0) revert BlockhashUnavailable(blockNumber);
        _reveal(seed);
    }

    // ------------------------------------------------------------------ ITapNetlistNFT views

    function collection() public view virtual returns (address);

    function tokenRange() public view virtual returns (uint256 firstTokenId, uint256 supply) {
        return (_firstTokenId, _supply);
    }

    function manifestHash() public view virtual returns (bytes32) {
        return _manifestHash;
    }

    function pools() external view virtual returns (Pool[] memory) {
        return _pools;
    }

    function masterSeed() public view virtual returns (bytes32) {
        return _masterSeed;
    }

    /// @notice The block scheduled for a block-hash reveal, 0 if none.
    function revealBlock() external view returns (uint256) {
        return _revealBlock;
    }

    /// @notice poolSeed of pool `poolIndex` (TapPermutation.poolSeed), available after the reveal.
    ///         Reverts for a NO_REVEAL collection, which has no pool seeds.
    function poolSeed(uint256 poolIndex) public view returns (bytes32) {
        if (_masterSeed == 0) revert NotRevealed();
        if (_masterSeed == NO_REVEAL) revert NoRevealCollection();
        if (poolIndex >= _poolSeeds.length) revert PoolOutOfRange(poolIndex);
        return _poolSeeds[poolIndex];
    }

    function entryIndexOf(uint256 tokenId, uint256 poolIndex) public view virtual returns (uint256) {
        bytes32 m = _masterSeed;
        if (m == 0) revert NotRevealed();
        if (poolIndex >= _pools.length) revert PoolOutOfRange(poolIndex);
        uint256 x = indexOf(tokenId);
        if (m == NO_REVEAL) return x;
        return TapPermutation.permute(_poolSeeds[poolIndex], _supply, x);
    }

    // ------------------------------------------------------------------ ITapNetlistTokenSet

    function tokenSetHash() external view returns (bytes32) {
        return _tokenSetHash;
    }

    function tokenCount() external view returns (uint256) {
        return _supply;
    }

    function tokenAt(uint256 index) public view returns (uint256) {
        if (index >= _supply) revert TokenOutOfRange(index);
        if (_tokenSetHash == 0) return _firstTokenId + index;
        if (_setPages.length == 0) revert TokenSetNotLoaded();
        return _setId(index);
    }

    function indexOf(uint256 tokenId) public view returns (uint256 x) {
        bool ok;
        (ok, x) = _tryIndexOf(tokenId);
        if (!ok) {
            if (_tokenSetHash == 0) revert TokenOutOfRange(tokenId);
            if (_setPages.length == 0) revert TokenSetNotLoaded();
            revert NotInTokenSet(tokenId);
        }
    }

    /// @notice Load the token set in one call. `ids` is the token set file: u32be ids, ascending, 4 bytes
    ///         each, whose SHA-256 is tokenSetHash. 7,000 ids = 28,000 bytes; one transaction stays under the
    ///         128 KiB mempool limit of geth-based chains up to about 32,000 ids.
    function loadTokenSet(bytes calldata ids) external virtual {
        if (_setPages.length != 0) return;
        _requireSetMode();
        delete _setSessions[msg.sender];
        if (ids.length != 4 * _supply) revert InvalidValues();
        if (!_loadSetChunk(0, ids)) revert InvalidProof();
    }

    /// @notice Load the token set over several calls (per caller): consecutive slices of the token set file.
    ///         Every slice but the last holds a multiple of IDS_PER_PAGE ids (24,572 bytes). On a hash mismatch
    ///         at the end the caller's session is reset and false is returned.
    function loadTokenSetChunk(uint256 offset, bytes calldata ids) external virtual returns (bool) {
        if (_setPages.length != 0) return true;
        return _loadSetChunk(offset, ids);
    }

    function _requireSetMode() private view {
        if (_manifestHash == 0) revert NotCommitted();
        if (_tokenSetHash == 0) revert NotTokenSetMode();
    }

    function _loadSetChunk(uint256 offset, bytes calldata ids) private returns (bool) {
        _requireSetMode();
        SetSession storage ss = _setSessions[msg.sender];
        uint256 m = ids.length / 4;
        uint256 n = _supply;
        if (
            offset != ss.count || m == 0 || ids.length != 4 * m || offset + m > n
                || (m % IDS_PER_PAGE != 0 && offset + m != n)
        ) revert BadChunk(ss.count);
        uint256 next = ss.next;
        uint256 base;
        assembly ("memory-safe") {
            base := ids.offset
        }
        for (uint256 j; j < m; ++j) {
            uint256 id;
            assembly ("memory-safe") {
                id := shr(224, calldataload(add(base, mul(j, 4))))
            }
            if (id < next) revert InvalidValues(); // ascending, no duplicates
            next = id + 1;
        }
        for (uint256 i; i < m; i += IDS_PER_PAGE) {
            uint256 e = m - i < IDS_PER_PAGE ? m - i : IDS_PER_PAGE;
            ss.pages.push(_deployFromCalldata(base + 4 * i, 4 * e));
        }
        ss.next = next;
        ss.count = offset + m;
        if (offset + m != n) return true;

        // Complete: hash the whole stored file once.
        address[] memory pages = ss.pages;
        bytes memory all = new bytes(4 * n);
        assembly ("memory-safe") {
            let dst := add(all, 0x20)
            for { let i := 0 } lt(i, mload(pages)) { i := add(i, 1) } {
                let pg := mload(add(pages, mul(add(i, 1), 0x20)))
                let len := sub(extcodesize(pg), 1)
                extcodecopy(pg, dst, 1, len)
                dst := add(dst, len)
            }
        }
        bool ok = sha256(all) == _tokenSetHash;
        if (ok) _setPages = pages;
        delete _setSessions[msg.sender];
        if (!ok) {
            emit TokenSetLoadFailed(msg.sender);
            return false;
        }
        emit TokenSetLoaded(_tokenSetHash);
        if (_masterSeed != 0) _emitAllMetadataUpdate();
        return true;
    }

    function _setId(uint256 index) private view returns (uint256 id) {
        address page = _setPages[index / IDS_PER_PAGE];
        uint256 off = 1 + (index % IDS_PER_PAGE) * 4;
        assembly ("memory-safe") {
            mstore(0x00, 0)
            extcodecopy(page, 0x00, off, 4)
            id := shr(224, mload(0x00))
        }
    }

    /// @dev Rank of `tokenId` (binary search in set mode); ok = false if not covered or set not loaded.
    function _tryIndexOf(uint256 tokenId) internal view returns (bool ok, uint256 x) {
        uint256 n = _supply;
        if (_tokenSetHash == 0) {
            uint256 first = _firstTokenId;
            if (tokenId < first || tokenId - first >= n) return (false, 0);
            return (true, tokenId - first);
        }
        if (_setPages.length == 0) return (false, 0);
        uint256 lo;
        uint256 hi = n;
        while (lo < hi) {
            uint256 mid = (lo + hi) >> 1;
            uint256 v = _setId(mid);
            if (v == tokenId) return (true, mid);
            if (v < tokenId) lo = mid + 1;
            else hi = mid;
        }
        return (false, 0);
    }

    /// @dev ERC-4906 update for every token: the id range, or all ids in token-set mode.
    function _emitAllMetadataUpdate() internal {
        if (_tokenSetHash != 0) emit BatchMetadataUpdate(0, type(uint256).max);
        else emit BatchMetadataUpdate(_firstTokenId, _firstTokenId + (_supply - 1));
    }

    // ------------------------------------------------------------------ binding

    /// @dev Values must be non-zero (zero means "not bound"). The proof is checked on every call; state
    ///      changes and events happen only on the first successful call for (tokenId, poolIndex).
    function bind(uint256 tokenId, uint256 poolIndex, bytes32[] calldata values, bytes32[] calldata proof)
        external
        virtual
    {
        uint256 entry = entryIndexOf(tokenId, poolIndex);
        Pool storage pool = _pools[poolIndex];
        uint8 fields = pool.fields;
        uint256 k = fields == 3 ? 2 : 1;
        if (values.length != k) revert InvalidValues();
        for (uint256 i; i < k; ++i) {
            if (values[i] == 0) revert InvalidValues();
        }
        if (!TapMerkle.verify(pool.root, _supply, entry, TapMerkle.leafHash(entry, values), proof)) {
            revert InvalidProof();
        }

        bool changed;
        if (fields & FIELD_IMAGE != 0 && _imageHash[tokenId] == 0) {
            _imageHash[tokenId] = values[0];
            changed = true;
        }
        if (fields & FIELD_NETLIST != 0 && _netlistHash[tokenId] == 0) {
            bytes32 h = values[k - 1];
            _netlistHash[tokenId] = h;
            _addKnownNetlistHash(h);
            changed = true;
        }
        if (changed) {
            emit Bound(tokenId, poolIndex, entry);
            emit MetadataUpdate(tokenId);
        }
    }

    /// @dev Bound value, else the value from a loaded pool once revealed, else zero.
    function netlistHashOf(uint256 tokenId) public view virtual returns (bytes32 h) {
        h = _netlistHash[tokenId];
        if (h == 0) h = _loadedField(tokenId, FIELD_NETLIST);
    }

    function imageHashOf(uint256 tokenId) public view virtual returns (bytes32 h) {
        h = _imageHash[tokenId];
        if (h == 0) h = _loadedField(tokenId, FIELD_IMAGE);
    }

    // ------------------------------------------------------------------ pool loading (optional)

    /// @notice Load every entry of a pool at once: `values` = all field values in entry order (k per entry).
    ///         Calldata is 32 bytes per value: one transaction stays under the 128 KiB mempool limit of
    ///         geth-based chains up to about 4,000 values; use `loadPoolChunk` for larger pools.
    ///         Reverts unless they rebuild the committed root. Afterwards netlistHashOf / imageHashOf answer
    ///         for every token from storage once revealed, without per-token `bind`. Permissionless, idempotent.
    function loadPool(uint256 poolIndex, bytes32[] calldata values) external virtual {
        if (_poolPages[poolIndex].length != 0) return;
        delete _sessions[poolIndex][msg.sender];
        if (values.length != _supply * _fieldCount(poolIndex)) revert InvalidValues();
        if (!_loadChunk(poolIndex, 0, values)) revert InvalidProof();
    }

    /// @notice Load a pool over several transactions. `offset` must equal the caller's progress; every chunk
    ///         but the last must hold a multiple of `poolPageSize(poolIndex)` entries. At most 5 pages per
    ///         call (3,835 values) keep a transaction under 128 KiB; 2 pages keep it under 16.7M gas.
    ///         The chunk completing the pool checks the root: on success the pool is loaded (returns true); on mismatch the caller's
    ///         session is reset (returns false, emits PoolLoadFailed) so it can start again.
    function loadPoolChunk(uint256 poolIndex, uint256 offset, bytes32[] calldata values)
        external
        virtual
        returns (bool loaded)
    {
        if (_poolPages[poolIndex].length != 0) return true;
        return _loadChunk(poolIndex, offset, values);
    }

    /// @notice Entries per storage page of a pool (767 for one field, 383 for two).
    function poolPageSize(uint256 poolIndex) public view returns (uint256) {
        return CHUNK_SIZE / (32 * _fieldCount(poolIndex));
    }

    function poolLoaded(uint256 poolIndex) public view returns (bool) {
        return _poolPages[poolIndex].length != 0;
    }

    /// @notice Entries the caller-supplied `loader` has loaded into its unfinished session.
    function loadProgress(uint256 poolIndex, address loader) external view returns (uint256) {
        return _sessions[poolIndex][loader].count;
    }

    /// @notice Value `field` (FIELD_IMAGE or FIELD_NETLIST) of entry `entry` of a loaded pool.
    function loadedValue(uint256 poolIndex, uint256 entry, uint8 field) public view returns (bytes32 v) {
        address[] storage pages = _poolPages[poolIndex];
        uint8 fields = _pools[poolIndex].fields;
        if (pages.length == 0 || fields & field == 0 || entry >= _supply) return 0;
        uint256 k = fields == 3 ? 2 : 1;
        uint256 per = CHUNK_SIZE / (32 * k);
        address page = pages[entry / per];
        uint256 off = 1 + ((entry % per) * k + (field == FIELD_NETLIST && k == 2 ? 1 : 0)) * 32;
        assembly ("memory-safe") {
            extcodecopy(page, 0x00, off, 0x20)
            v := mload(0x00)
        }
    }

    function netlistOf(uint256 tokenId) external view virtual returns (bytes memory) {
        return netlistFile(_boundNetlist(tokenId));
    }

    // ------------------------------------------------------------------ ITapNetlistEval

    function evalOf(uint256 tokenId, bytes calldata inputs) external view virtual returns (bytes memory) {
        return TapNetlistVM.eval(netlistFile(_boundNetlist(tokenId)), inputs);
    }

    function stepOf(uint256 tokenId, bytes calldata state, bytes calldata inputs)
        external
        view
        virtual
        returns (bytes memory newState, bytes memory outputs)
    {
        return TapNetlistVM.step(netlistFile(_boundNetlist(tokenId)), state, inputs);
    }

    function evalFile(bytes32 netlistHash, bytes calldata inputs) external view virtual returns (bytes memory) {
        return TapNetlistVM.eval(netlistFile(netlistHash), inputs);
    }

    function stepFile(bytes32 netlistHash, bytes calldata state, bytes calldata inputs)
        external
        view
        virtual
        returns (bytes memory newState, bytes memory outputs)
    {
        return TapNetlistVM.step(netlistFile(netlistHash), state, inputs);
    }

    // ------------------------------------------------------------------ ERC-165

    function supportsInterface(bytes4 interfaceId) public view virtual returns (bool) {
        return interfaceId == type(ITapNetlistNFT).interfaceId || interfaceId == type(ITapNetlistEval).interfaceId
            || interfaceId == type(ITapNetlistTokenSet).interfaceId || interfaceId == 0x01ffc9a7 // ERC-165
            || interfaceId == 0x49064906; // ERC-4906
    }

    // ------------------------------------------------------------------ internal

    /// @dev (chainId, collection) mixed into every pool seed; the manifest's `collection` object.
    function _seedDomain() internal view virtual returns (uint64 chainId, address coll) {
        return (uint64(block.chainid), collection());
    }

    function _reveal(bytes32 seed) internal virtual {
        if (_manifestHash == 0) revert NotCommitted();
        if (_masterSeed != 0) revert AlreadyRevealed();
        if (seed == 0 || seed == NO_REVEAL) revert InvalidValues(); // also covers a block hash equal to it
        _masterSeed = seed;
        (uint64 chainId, address coll) = _seedDomain();
        for (uint256 i; i < _pools.length; ++i) {
            _poolSeeds.push(TapPermutation.poolSeed(seed, chainId, coll, _pools[i].label));
        }
        emit Revealed(seed);
        _emitAllMetadataUpdate();
    }

    function _fieldCount(uint256 poolIndex) internal view returns (uint256) {
        if (_manifestHash == 0) revert NotCommitted();
        if (poolIndex >= _pools.length) revert PoolOutOfRange(poolIndex);
        return _pools[poolIndex].fields == 3 ? 2 : 1;
    }

    function _loadChunk(uint256 poolIndex, uint256 offset, bytes32[] calldata values) private returns (bool) {
        uint256 k = _fieldCount(poolIndex);
        uint256 per = CHUNK_SIZE / (32 * k);
        LoadSession storage ss = _sessions[poolIndex][msg.sender];
        uint256 m = values.length / k;
        if (
            offset != ss.count || m == 0 || values.length != m * k || offset + m > _supply
                || (m % per != 0 && offset + m != _supply)
        ) revert BadChunk(ss.count);
        for (uint256 i; i < values.length; ++i) {
            if (values[i] == 0) revert InvalidValues(); // entry values are never zero (zero = unbound)
        }
        bytes32[33] memory fr = _accumulate(ss, offset, values, k);
        _storePages(ss, values, m, k, per);
        if (ss.count != _supply) return true;
        return _finishLoad(poolIndex, ss, fr);
    }

    /// @dev Folds the chunk's leaves into the caller's frontier (binary-counter Merkle accumulator).
    function _accumulate(LoadSession storage ss, uint256 offset, bytes32[] calldata values, uint256 k)
        private
        returns (bytes32[33] memory fr)
    {
        uint256 count = offset;
        for (uint256 l; l < 33; ++l) {
            if ((count >> l) & 1 == 1) fr[l] = ss.frontier[l];
        }
        uint256 end = count + values.length / k;
        uint256 len = 5 + 32 * k;
        assembly ("memory-safe") {
            // Scratch memory beyond the free pointer: leaf = SHA-256(0x00 ‖ u32(i) ‖ values), node =
            // SHA-256(0x01 ‖ left ‖ right), exactly TapMerkle.leafHash / nodeHash, without allocations.
            let p := mload(0x40)
            let cd := values.offset
            for {} lt(count, end) { count := add(count, 1) } {
                mstore(p, shl(216, count)) // byte 0 = 0x00, bytes 1..4 = u32be(count)
                calldatacopy(add(p, 5), cd, sub(len, 5))
                cd := add(cd, sub(len, 5))
                if iszero(staticcall(gas(), 2, p, len, 0x00, 0x20)) { revert(0, 0) }
                let h := mload(0x00)
                let l := 0
                for {} and(shr(l, count), 1) { l := add(l, 1) } {
                    mstore(p, shl(248, 1))
                    mstore(add(p, 1), mload(add(fr, mul(l, 0x20))))
                    mstore(add(p, 0x21), h)
                    if iszero(staticcall(gas(), 2, p, 65, 0x00, 0x20)) { revert(0, 0) }
                    h := mload(0x00)
                }
                mstore(add(fr, mul(l, 0x20)), h)
            }
        }
        for (uint256 l; l < 33; ++l) {
            if ((count >> l) & 1 == 1) ss.frontier[l] = fr[l];
        }
        ss.count = count;
    }

    /// @dev One SSTORE2 page per `per` entries.
    function _storePages(LoadSession storage ss, bytes32[] calldata values, uint256 m, uint256 k, uint256 per) private {
        uint256 base;
        assembly ("memory-safe") {
            base := values.offset
        }
        for (uint256 i; i < m; i += per) {
            uint256 e = m - i < per ? m - i : per;
            ss.pages.push(_deployFromCalldata(base + i * k * 32, e * k * 32));
        }
    }

    /// @dev Root of the complete pool: pending left nodes combine from the lowest level up (odd nodes
    ///      moved up unchanged). Loads the pool on a match; resets the caller's session otherwise.
    function _finishLoad(uint256 poolIndex, LoadSession storage ss, bytes32[33] memory fr) private returns (bool ok) {
        uint256 count = ss.count;
        bytes32 root;
        bool started;
        for (uint256 l; l < 33; ++l) {
            if ((count >> l) & 1 == 1) {
                root = started ? TapMerkle.nodeHash(fr[l], root) : fr[l];
                started = true;
            }
        }
        ok = root == _pools[poolIndex].root;
        if (ok) _poolPages[poolIndex] = ss.pages;
        delete _sessions[poolIndex][msg.sender];
        if (!ok) {
            emit PoolLoadFailed(poolIndex, msg.sender);
            return false;
        }
        emit PoolLoaded(poolIndex);
        if (_masterSeed != 0) _emitAllMetadataUpdate();
    }

    /// @dev Value of `field` for `tokenId` from a loaded pool; zero if none applies or before the reveal.
    function _loadedField(uint256 tokenId, uint8 field) internal view returns (bytes32) {
        if (_masterSeed == 0) return 0;
        (bool ok,) = _tryIndexOf(tokenId);
        if (!ok) return 0;
        for (uint256 p; p < _pools.length; ++p) {
            if (_pools[p].fields & field != 0 && _poolPages[p].length != 0) {
                return loadedValue(p, entryIndexOf(tokenId, p), field);
            }
        }
        return 0;
    }

    /// @notice Mark the netlist hash `tokenId` receives from a loaded pool as known, so `storeNetlist`
    ///         accepts its file (O(1); `bind` marks automatically). Permissionless; reverts if no hash yet.
    function markKnown(uint256 tokenId) external returns (bytes32 h) {
        h = _boundNetlist(tokenId);
        _addKnownNetlistHash(h);
    }

    /// @notice Ownership can only be renounced through `freeze()` / `seal()`, never by a plain transfer.
    function transferOwnership(address newOwner) public virtual override onlyOwner {
        if (newOwner == address(0)) revert ZeroOwner();
        _setOwner(newOwner);
    }

    /// @dev 1..64 printable ASCII bytes (0x20..0x7e).
    function _validLabel(string calldata label) private pure returns (bool) {
        bytes calldata b = bytes(label);
        if (b.length == 0 || b.length > 64) return false;
        for (uint256 i; i < b.length; ++i) {
            if (b[i] < 0x20 || b[i] > 0x7e) return false;
        }
        return true;
    }

    /// @dev Mandatory for ITapNetlistEval implementations; deliberately not overridable.
    function _beforeStoreNetlist(bytes calldata file) internal pure override {
        TapNetlistCheck.check(file);
    }

    function _boundNetlist(uint256 tokenId) internal view returns (bytes32 h) {
        h = netlistHashOf(tokenId);
        if (h == 0) revert NotBound(tokenId);
    }

    function _isCommitted() internal view returns (bool) {
        return _manifestHash != 0;
    }

    function _isRevealed() internal view returns (bool) {
        return _masterSeed != 0;
    }

    /// @dev True once a random seed is known (not for NO_REVEAL collections, which hide nothing).
    function _isRandomlyRevealed() internal view returns (bool) {
        return _masterSeed != 0 && _masterSeed != NO_REVEAL;
    }
}
