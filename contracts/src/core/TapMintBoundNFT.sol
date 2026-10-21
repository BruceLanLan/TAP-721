// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../interfaces/ITapNetlistNFT.sol";
import {ERC721Min} from "../vendor/ERC721Min.sol";
import {Owned} from "../vendor/Owned.sol";
import {TapNetlistCheck} from "./TapNetlistCheck.sol";
import {TapNetlistStore} from "./TapNetlistStore.sol";

/// @title Reference mint-bound Netlist-Bound NFT collection (TAP draft "Netlist-Bound NFTs" §8.2, mint-bound profile)
/// @notice ERC-721 + ITapNetlistNFT + ERC-165 + ERC-4906 + ERC-173 in one contract, without a manifest:
///         the netlist hash (and optionally the image hash) of every token id is recorded at mint, once over
///         the contract's lifetime, and no function changes it. `collection()` is itself.
///
///         - `manifestHash()` and `masterSeed()` are zero and `pools()` is empty, permanently;
///         - `entryIndexOf` and `bind` revert for every token (`NoManifest`);
///         - a burned id may be minted again only with the same netlist hash and the same image hash
///           (the hashes recorded at the first mint are kept, so `netlistHashOf` answers after a burn);
///         - `storeNetlist` accepts a valid tapnet/1 file (checked on chain) of at most 49,152 bytes whose
///           SHA-256 was recorded at a mint; the hash stays known after a burn;
///         - `tokenRange()` is fixed at construction: `(firstTokenId, supply)` limits the ids that can ever be
///           minted, and `supply` = 0 means unbounded (then `(0, 0)` is returned);
///         - `frozen()` latches when `freeze()` locks the base URI. Minting and burning continue after a
///           freeze (the profile says a freeze does not imply that minting has ended); `endMinting()` ends them
///           for good. Ownership is kept after the freeze (only the minter set and the end of minting remain in
///           the owner's power) and can be renounced only once frozen, so the contract is never orphaned
///           unfrozen; after `freeze()`, `endMinting()` and a renounce nothing can ever change or mint again.
///
///         tokenURI = baseURI ‖ decimal token id. The contract does not implement the Eval or TokenSet
///         extensions and reports neither through ERC-165.
contract TapMintBoundNFT is ERC721Min, TapNetlistStore, Owned {
    /// ERC-173 interface id: owner() ^ transferOwnership(address).
    bytes4 internal constant INTERFACE_ERC173 = 0x7f5828d0;

    event MinterSet(address indexed account, bool allowed);
    event BaseURISet(string baseURI);
    /// Emitted once per token id, at its first mint (the hashes never change afterwards).
    event NetlistRecorded(uint256 indexed tokenId, bytes32 indexed netlistHash, bytes32 imageHash);
    event MintingEnded();

    error NoManifest();
    error IsFrozen();
    error MintingHasEnded();
    error ZeroNetlistHash();
    error ImageHashNotRecorded();
    error ImageHashRequired();
    error TokenOutOfRange(uint256 tokenId);
    error HashMismatch(uint256 tokenId, bytes32 recorded, bytes32 given);
    error NotBound(uint256 tokenId);
    error ZeroOwner();
    error InvalidRange();

    /// First token id and number of ids this contract may ever mint; `supply` = 0 means unbounded.
    uint256 private immutable _firstTokenId;
    uint256 private immutable _supply;
    /// Whether every token records an image hash at mint (`imageHashOf` non-zero) or none does (zero permanently).
    bool public immutable recordsImageHash;

    string private _baseURI;
    bool private _frozen;
    bool private _mintingEnded;
    mapping(address account => bool) public isMinter;
    mapping(uint256 tokenId => bytes32) private _netlistHash;
    mapping(uint256 tokenId => bytes32) private _imageHash;

    /// @param firstTokenId_ First mintable id (ignored when `supply_` is 0).
    /// @param supply_ Number of mintable ids, or 0 for an unbounded collection.
    /// @param recordsImageHash_ True if every mint records an image hash, false if none does.
    constructor(
        string memory name_,
        string memory symbol_,
        string memory baseURI_,
        uint256 firstTokenId_,
        uint256 supply_,
        bool recordsImageHash_,
        address initialOwner
    ) ERC721Min(name_, symbol_) Owned(initialOwner) {
        if (initialOwner == address(0)) revert ZeroOwner();
        if (supply_ != 0 && firstTokenId_ > type(uint256).max - (supply_ - 1)) revert InvalidRange();
        _baseURI = baseURI_;
        _firstTokenId = supply_ == 0 ? 0 : firstTokenId_;
        _supply = supply_;
        recordsImageHash = recordsImageHash_;
    }

    // ------------------------------------------------------------------ owner

    function setMinter(address account, bool allowed) external onlyOwner {
        isMinter[account] = allowed;
        emit MinterSet(account, allowed);
    }

    function setBaseURI(string calldata baseURI_) external onlyOwner {
        if (_frozen) revert IsFrozen();
        _baseURI = baseURI_;
        emit BaseURISet(baseURI_);
        emit BatchMetadataUpdate(0, type(uint256).max);
    }

    /// @notice Permanently fix tokenURI. The recorded hashes can never change, so after this no account can
    ///         change `tokenURI` or a recorded hash: `frozen()` becomes true and never returns to false.
    ///         Minting is not ended by a freeze.
    function freeze() external onlyOwner {
        if (_frozen) revert IsFrozen();
        _frozen = true;
        emit Frozen();
        emit BatchMetadataUpdate(0, type(uint256).max);
    }

    /// @notice End minting for good (burned ids included). Independent of the freeze.
    function endMinting() external onlyOwner {
        if (_mintingEnded) revert MintingHasEnded();
        _mintingEnded = true;
        emit MintingEnded();
    }

    /// @notice Ownership can be transferred at any time and renounced (ERC-173, `newOwner` = address(0)) only
    ///         once frozen, so that no account can ever hold the power to change `tokenURI` after a renounce.
    function transferOwnership(address newOwner) public virtual override onlyOwner {
        if (newOwner == address(0) && !_frozen) revert ZeroOwner();
        _setOwner(newOwner);
    }

    // ------------------------------------------------------------------ minting and burning

    /// @notice Mint `tokenId` to `to` with its netlist hash and, if the contract records one, its image hash.
    ///         Owner or minters. The first mint of an id records its hashes for the contract's lifetime; a
    ///         burned id can be minted again only with the identical hashes.
    function mint(address to, uint256 tokenId, bytes32 netlistHash, bytes32 imageHash) external {
        if (msg.sender != owner() && !isMinter[msg.sender]) revert Unauthorized(msg.sender);
        if (_mintingEnded) revert MintingHasEnded();
        if (netlistHash == 0) revert ZeroNetlistHash();
        if (recordsImageHash) {
            if (imageHash == 0) revert ImageHashRequired();
        } else if (imageHash != 0) {
            revert ImageHashNotRecorded();
        }
        if (_supply != 0 && (tokenId < _firstTokenId || tokenId - _firstTokenId >= _supply)) {
            revert TokenOutOfRange(tokenId);
        }
        bytes32 recorded = _netlistHash[tokenId];
        if (recorded == 0) {
            _netlistHash[tokenId] = netlistHash;
            if (imageHash != 0) _imageHash[tokenId] = imageHash;
            _addKnownNetlistHash(netlistHash);
            emit NetlistRecorded(tokenId, netlistHash, imageHash);
        } else {
            if (recorded != netlistHash) revert HashMismatch(tokenId, recorded, netlistHash);
            bytes32 img = _imageHash[tokenId];
            if (img != imageHash) revert HashMismatch(tokenId, img, imageHash);
        }
        _mint(to, tokenId); // reverts if the token exists
        emit MetadataUpdate(tokenId);
    }

    /// @notice Burn `tokenId` (owner or approved). The recorded hashes stay.
    function burn(uint256 tokenId) external {
        address holder = _requireOwned(tokenId);
        if (!_isAuthorized(holder, msg.sender, tokenId)) revert ERC721NotAuthorized(msg.sender, tokenId);
        _burn(tokenId);
    }

    // ------------------------------------------------------------------ ITapNetlistNFT

    function collection() external view returns (address) {
        return address(this);
    }

    /// @inheritdoc ITapNetlistNFT
    /// @dev The ids this contract may mint, fixed at construction; `(0, 0)` for an unbounded collection.
    function tokenRange() external view returns (uint256 firstTokenId, uint256 supply) {
        return (_firstTokenId, _supply);
    }

    function manifestHash() external pure returns (bytes32) {
        return 0;
    }

    function pools() external pure returns (Pool[] memory) {
        return new Pool[](0);
    }

    function masterSeed() external pure returns (bytes32) {
        return 0;
    }

    function entryIndexOf(uint256, uint256) external pure returns (uint256) {
        revert NoManifest();
    }

    function bind(uint256, uint256, bytes32[] calldata, bytes32[] calldata) external pure {
        revert NoManifest();
    }

    /// @inheritdoc ITapNetlistNFT
    /// @dev The hash recorded at the id's first mint; kept after a burn. Zero for an id never minted.
    function netlistHashOf(uint256 tokenId) public view returns (bytes32) {
        return _netlistHash[tokenId];
    }

    /// @inheritdoc ITapNetlistNFT
    /// @dev Zero permanently if `recordsImageHash` is false (the field no pool carries, §5.2).
    function imageHashOf(uint256 tokenId) external view returns (bytes32) {
        return _imageHash[tokenId];
    }

    function netlistOf(uint256 tokenId) external view returns (bytes memory) {
        bytes32 h = _netlistHash[tokenId];
        if (h == 0) revert NotBound(tokenId);
        return netlistFile(h);
    }

    function frozen() external view returns (bool) {
        return _frozen;
    }

    // ------------------------------------------------------------------ views

    function mintingEnded() external view returns (bool) {
        return _mintingEnded;
    }

    function baseURI() external view returns (string memory) {
        return _baseURI;
    }

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);
        string memory base = _baseURI;
        if (bytes(base).length == 0) return "";
        return string.concat(base, _toString(tokenId));
    }

    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(ITapNetlistNFT).interfaceId || interfaceId == INTERFACE_ERC173
            || ERC721Min.supportsInterface(interfaceId);
    }

    // ------------------------------------------------------------------ internal

    /// @dev Every stored file is checked on chain (§2.2); the contract commits to no manifest that could
    ///      have pinned the file's validity.
    function _beforeStoreNetlist(bytes calldata file) internal pure override {
        TapNetlistCheck.check(file);
    }

    function _toString(uint256 v) private pure returns (string memory s) {
        uint256 len = 1;
        for (uint256 t = v; t >= 10; t /= 10) {
            ++len;
        }
        bytes memory b = new bytes(len);
        for (; len > 0; v /= 10) {
            b[--len] = bytes1(uint8(48 + v % 10));
        }
        return string(b);
    }
}
