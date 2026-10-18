// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapCompanion} from "../interfaces/ITapCompanion.sol";
import {TapNetlistCore} from "./TapNetlistCore.sol";

/// @title ITapNetlistNFT companion for an existing ERC-721 that cannot be changed
/// @notice Holds the manifest, pools, seed, bindings and netlist files for `collection()`, a legacy
///         contract such as TapeCode-Test1 on X Layer. ERC-4906 events are emitted by this contract
///         (the legacy contract has none); indexers that only watch the collection address miss them.
///
///         Two-way binding: the legacy collection's `owner()` calls `endorse()` once (for TapeCode-Test1 the
///         ERC-6551 container, through `execute`); this works even after the legacy base URI is frozen.
///
///         frozen() is true once the manifest is committed, the seed is set, the companion is sealed
///         (owner renounced), it is endorsed, and the legacy contract reports its token URIs frozen: a
///         staticcall of `uriFrozenSelector` returning ABI-encoded `true`. A failing or malformed call
///         counts as not frozen. frozen() reports only the latched state: `seal`, `endorse` and the
///         permissionless `announceFrozen` latch it when all conditions hold, so it never returns to false.
///         Endorse only after the manifest is committed; the companion cannot stop the legacy owner from
///         endorsing other companions. For TapeCode-Test1, endorse and freezeBaseURI before the container's
///         circuit is locked away, or the container can no longer call them.
contract TapCompanion is TapNetlistCore, ITapCompanion {
    address private immutable _legacy;
    /// Selector of the legacy contract's `bool` freeze getter, e.g. bytes4(keccak256("uriFrozen()")).
    bytes4 public immutable uriFrozenSelector;

    bool private _sealed;
    bool private _frozenLatched;
    address private _endorsedBy;

    error ZeroAddress();
    error NotCollectionOwner(address account);

    constructor(address legacy, bytes4 uriFrozenSelector_, address initialOwner) TapNetlistCore(initialOwner) {
        if (legacy == address(0)) revert ZeroAddress();
        _legacy = legacy;
        uriFrozenSelector = uriFrozenSelector_;
    }

    /// @notice Renounce ownership after the manifest and the seed are set. Manifest, pools and seed can
    ///         then never change.
    function seal() external onlyOwner {
        if (!_isCommitted()) revert NotCommitted();
        if (!_isRevealed()) revert NotRevealed();
        _sealed = true;
        _setOwner(address(0));
        announceFrozen();
    }

    /// @notice Endorse this companion as the ITapNetlistNFT data contract of the legacy collection.
    ///         Only the legacy collection's `owner()` (selector 0x8da5cb5b); idempotent.
    function endorse() external {
        if (msg.sender != legacyOwner()) revert NotCollectionOwner(msg.sender);
        if (!_isCommitted()) revert NotCommitted();
        if (_endorsedBy != address(0)) return;
        _endorsedBy = msg.sender;
        emit Endorsed(msg.sender);
        announceFrozen();
    }

    /// @notice The legacy collection's `owner()`, or address(0) if the call fails or is malformed.
    function legacyOwner() public view returns (address result) {
        (bool ok, bytes memory ret) = _legacy.staticcall{gas: 100_000}(abi.encodeWithSelector(0x8da5cb5b));
        if (ok && ret.length == 32 && uint256(bytes32(ret)) >> 160 == 0) result = abi.decode(ret, (address));
    }

    /// @notice Permissionless. Latches frozen() and emits Frozen + BatchMetadataUpdate the first time
    ///         the conditions hold (e.g. after the legacy owner froze its base URI). Returns frozen().
    function announceFrozen() public returns (bool) {
        if (_frozenLatched) return true;
        if (!_sealed || _endorsedBy == address(0) || !legacyUriFrozen()) return false;
        _frozenLatched = true;
        emit Frozen();
        _emitAllMetadataUpdate();
        return true;
    }

    function endorsedBy() external view returns (address) {
        return _endorsedBy;
    }

    /// @notice True once the legacy collection's owner has endorsed this companion.
    function endorsed() public view returns (bool) {
        return _endorsedBy != address(0);
    }

    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(ITapCompanion).interfaceId || super.supportsInterface(interfaceId);
    }

    function collection() public view override returns (address) {
        return _legacy;
    }

    function isSealed() external view returns (bool) {
        return _sealed;
    }

    function frozen() external view returns (bool) {
        return _frozenLatched;
    }

    /// @notice The legacy contract's freeze getter; false if the call fails or does not return a bool true.
    function legacyUriFrozen() public view returns (bool result) {
        (bool ok, bytes memory ret) = _legacy.staticcall{gas: 100_000}(abi.encodeWithSelector(uriFrozenSelector));
        if (ok && ret.length == 32) result = abi.decode(ret, (uint256)) == 1;
    }
}
