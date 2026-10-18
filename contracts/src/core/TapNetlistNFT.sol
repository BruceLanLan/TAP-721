// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC721Min} from "../vendor/ERC721Min.sol";
import {TapNetlistCore} from "./TapNetlistCore.sol";

/// @title Reference L1 Netlist-Bound NFT collection (TAP draft "Netlist-Bound NFTs" §8)
/// @notice ERC-721 + ITapNetlistNFT + ERC-165 + ERC-4906 in one contract; `collection()` is itself.
///         commitManifest → mint → reveal → bind / storeNetlist (anyone) → freeze. Minting ends at the
///         reveal, since entryIndexOf then shows which unminted id receives which entry; a collection
///         committed with `commitManifestNoReveal` hides nothing and may keep minting until `freeze()`.
///         `freeze()` ends minting, base URI changes and every owner power for good.
///         tokenURI = baseURI ‖ decimal token id.
contract TapNetlistNFT is ERC721Min, TapNetlistCore {
    event MinterSet(address indexed account, bool allowed);
    event BaseURISet(string baseURI);

    error IsFrozen();

    string private _baseURI;
    bool private _frozen;
    mapping(address account => bool) public isMinter;

    constructor(string memory name_, string memory symbol_, string memory baseURI_, address initialOwner)
        ERC721Min(name_, symbol_)
        TapNetlistCore(initialOwner)
    {
        _baseURI = baseURI_;
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
        if (_isCommitted()) _emitAllMetadataUpdate();
        else emit BatchMetadataUpdate(0, type(uint256).max);
    }

    /// @notice Permanently fix tokenURI, manifest, pools and seed; renounces ownership. Requires the
    ///         manifest and the seed.
    function freeze() external onlyOwner {
        if (!_isCommitted()) revert NotCommitted();
        if (!_isRevealed()) revert NotRevealed();
        _frozen = true;
        _setOwner(address(0));
        emit Frozen();
        _emitAllMetadataUpdate();
    }

    // ------------------------------------------------------------------ minting

    /// @notice Mint `tokenId` (within the committed token range) to `to`. Owner or minters, after the
    ///         commit and before the reveal (NO_REVEAL collections: until frozen).
    function mint(address to, uint256 tokenId) external {
        if (msg.sender != owner() && !isMinter[msg.sender]) revert Unauthorized(msg.sender);
        if (_frozen) revert IsFrozen();
        if (!_isCommitted()) revert NotCommitted();
        if (_isRandomlyRevealed()) revert AlreadyRevealed();
        indexOf(tokenId); // reverts unless covered by the manifest (range or loaded token set)
        _mint(to, tokenId);
    }

    // ------------------------------------------------------------------ views

    function collection() public view override returns (address) {
        return address(this);
    }

    function frozen() external view returns (bool) {
        return _frozen;
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

    function supportsInterface(bytes4 interfaceId) public view override(ERC721Min, TapNetlistCore) returns (bool) {
        return ERC721Min.supportsInterface(interfaceId) || TapNetlistCore.supportsInterface(interfaceId);
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
