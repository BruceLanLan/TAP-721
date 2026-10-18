// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../interfaces/ITapNetlistNFT.sol";
import {ITapBridgeMirror} from "../interfaces/ITapBridgeMirror.sol";
import {ERC721Min} from "../vendor/ERC721Min.sol";
import {TapNetlistStore} from "../core/TapNetlistStore.sol";
import {TapNetlistCheck} from "../core/TapNetlistCheck.sol";
import {TapBridgeEndpoint} from "./TapBridgeEndpoint.sol";
import {TapBridgePayload} from "./TapBridgePayload.sol";

/// @title Remote-chain endpoint: an ERC-721 whose tokens exist only while bridged in
/// @notice Mints on arrival and burns on departure. Stores the hashes each payload carries, accepts the
///         matching tapnet/1 files permissionlessly (storage: core TapNetlistStore; validity: TapNetlistCheck),
///         and serves them through ITapNetlistNFT. ERC-721 and ERC-4906 come from vendor/ERC721Min.
///         The manifest, pools and reveal live on the home chain only: on a mirror `pools()` is empty,
///         `masterSeed()` is zero, `frozen()` is false and `entryIndexOf` / `bind` revert.
contract TapMirror is TapBridgeEndpoint, ERC721Min, TapNetlistStore, ITapBridgeMirror {
    struct TokenHashes {
        bytes32 netlist;
        bytes32 image;
    }

    uint256 internal immutable _firstTokenId;
    uint256 internal immutable _supply;
    string internal _baseURI;

    /// @inheritdoc ITapNetlistNFT
    bytes32 public override(ITapNetlistNFT, ITapBridgeMirror) manifestHash;

    mapping(uint256 => TokenHashes) internal _hashes;

    /// @notice entryIndexOf / bind on a bridged copy: the reveal lives in the home collection only.
    error NotHomeCollection();
    error AlreadyLive(uint256 tokenId);
    error OutOfRange(uint256 tokenId);
    error ManifestConflict(bytes32 stored, bytes32 received);
    error NotBound(uint256 tokenId);
    error SameChain();

    /// @param supply_ 0 if the home collection has no fixed range (then any token id is accepted).
    constructor(
        uint64 homeChainId_,
        address homeContract_,
        string memory name_,
        string memory symbol_,
        string memory baseURI_,
        uint256 firstTokenId_,
        uint256 supply_,
        address owner_
    ) TapBridgeEndpoint(homeChainId_, homeContract_, owner_) ERC721Min(name_, symbol_) {
        if (homeChainId_ == block.chainid) revert SameChain();
        _baseURI = baseURI_;
        _firstTokenId = firstTokenId_;
        _supply = supply_;
    }

    // ------------------------------------------------------------------ ERC-165 / metadata

    function supportsInterface(bytes4 id) public view override returns (bool) {
        return super.supportsInterface(id) // ERC-165, ERC-721, ERC-721 Metadata, ERC-4906
            || id == type(ITapNetlistNFT).interfaceId || id == type(ITapBridgeMirror).interfaceId
            || _isBridgeInterface(id);
    }

    /// @notice baseURI ‖ decimal token id; the base URI is fixed at deployment (may be empty).
    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        ownerOf(tokenId);
        bytes memory b = bytes(_baseURI);
        if (b.length == 0) return "";
        return string.concat(_baseURI, _toString(tokenId));
    }

    // ------------------------------------------------------------------ bridge hooks

    /// @dev The token's hashes are kept after the burn: netlistHashOf / imageHashOf / netlistOf keep answering
    ///      with the values last carried in (ownerOf reverts). A later arrival overwrites them.
    function _depart(uint256 tokenId, address caller, uint64) internal override returns (bytes32, bytes32, bytes32) {
        address holder = ownerOf(tokenId);
        if (!_isAuthorized(holder, caller, tokenId)) revert ERC721NotAuthorized(caller, tokenId);
        _burn(tokenId);
        return _hashesOf(tokenId);
    }

    function _arrive(TapBridgePayload.Payload memory p) internal override {
        uint256 id = p.tokenId;
        if (_ownerOf(id) != address(0)) revert AlreadyLive(id);
        if (_supply != 0 && (id < _firstTokenId || id - _firstTokenId >= _supply)) revert OutOfRange(id);
        if (p.manifestHash != 0) {
            bytes32 m = manifestHash;
            if (m == 0) {
                manifestHash = p.manifestHash;
                emit ManifestCommitted(p.manifestHash);
            } else if (m != p.manifestHash) {
                revert ManifestConflict(m, p.manifestHash);
            }
        }
        TokenHashes storage h = _hashes[id];
        if (h.netlist != p.netlistHash) h.netlist = p.netlistHash;
        if (h.image != p.imageHash) h.image = p.imageHash;
        if (p.netlistHash != 0 && !knownNetlist(p.netlistHash)) _addKnownNetlistHash(p.netlistHash);
        _mint(p.to, id);
        emit MetadataUpdate(id);
    }

    function _hashesOf(uint256 tokenId) internal view override returns (bytes32, bytes32, bytes32) {
        TokenHashes storage h = _hashes[tokenId];
        return (h.netlist, h.image, manifestHash);
    }

    // ------------------------------------------------------------------ ITapNetlistNFT

    function collection() external view override returns (address) {
        return address(this);
    }

    function tokenRange() external view override returns (uint256 firstTokenId, uint256 supply) {
        return (_firstTokenId, _supply);
    }

    function pools() external pure override returns (Pool[] memory p) {
        return p;
    }

    function masterSeed() external pure override returns (bytes32) {
        return 0;
    }

    function entryIndexOf(uint256, uint256) external pure override returns (uint256) {
        revert NotHomeCollection();
    }

    function bind(uint256, uint256, bytes32[] calldata, bytes32[] calldata) external pure override {
        revert NotHomeCollection();
    }

    function netlistHashOf(uint256 tokenId) external view override returns (bytes32) {
        return _hashes[tokenId].netlist;
    }

    function imageHashOf(uint256 tokenId) external view override returns (bytes32) {
        return _hashes[tokenId].image;
    }

    /// @inheritdoc ITapBridgeMirror
    function knownNetlist(bytes32 netlistHash) public view override(TapNetlistStore, ITapBridgeMirror) returns (bool) {
        return super.knownNetlist(netlistHash);
    }

    /// @inheritdoc ITapBridgeMirror
    /// @dev Same as storeNetlist (which is external in TapNetlistStore, hence the self-call).
    function materialize(bytes calldata file) external override returns (bytes32) {
        return this.storeNetlist(file);
    }

    /// @dev Full tapnet/1 check (draft A §2) before storing.
    function _beforeStoreNetlist(bytes calldata file) internal view override {
        TapNetlistCheck.check(file);
    }

    function netlistOf(uint256 tokenId) external view override returns (bytes memory) {
        bytes32 h = _hashes[tokenId].netlist;
        if (h == 0) revert NotBound(tokenId);
        return netlistFile(h);
    }

    function frozen() external pure override returns (bool) {
        return false;
    }

    // ------------------------------------------------------------------ utils

    function _toString(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 t = v; t != 0; t /= 10) ++len;
        bytes memory s = new bytes(len);
        while (v != 0) {
            s[--len] = bytes1(uint8(48 + v % 10));
            v /= 10;
        }
        return string(s);
    }
}
