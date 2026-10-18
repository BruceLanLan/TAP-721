// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC4906} from "./IERC4906.sol";

interface IERC721Receiver {
    function onERC721Received(address operator, address from, uint256 tokenId, bytes calldata data)
        external
        returns (bytes4);
}

/// @title Minimal ERC-721 with the metadata extension, ERC-165 and ERC-4906 events
/// @notice All balance and ownership changes go through `_update`, the single override point for
///         derived contracts (mint: from = 0, burn: to = 0). `tokenURI` is left to the derived contract.
abstract contract ERC721Min is IERC4906 {
    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event ApprovalForAll(address indexed owner, address indexed operator, bool approved);

    error ERC721NonexistentToken(uint256 tokenId);
    error ERC721TokenExists(uint256 tokenId);
    error ERC721IncorrectOwner(address from, uint256 tokenId, address owner);
    error ERC721InvalidReceiver(address receiver);
    error ERC721InvalidOwner(address owner);
    error ERC721NotAuthorized(address operator, uint256 tokenId);

    bytes4 internal constant INTERFACE_ERC165 = 0x01ffc9a7;
    bytes4 internal constant INTERFACE_ERC721 = 0x80ac58cd;
    bytes4 internal constant INTERFACE_ERC721_METADATA = 0x5b5e139f;
    bytes4 internal constant INTERFACE_ERC4906 = 0x49064906;

    string private _name;
    string private _symbol;

    mapping(uint256 tokenId => address) private _owners;
    mapping(address owner => uint256) private _balances;
    mapping(uint256 tokenId => address) private _tokenApprovals;
    mapping(address owner => mapping(address operator => bool)) private _operatorApprovals;

    constructor(string memory name_, string memory symbol_) {
        _name = name_;
        _symbol = symbol_;
    }

    // ------------------------------------------------------------------ ERC-165

    function supportsInterface(bytes4 interfaceId) public view virtual returns (bool) {
        return interfaceId == INTERFACE_ERC165 || interfaceId == INTERFACE_ERC721
            || interfaceId == INTERFACE_ERC721_METADATA || interfaceId == INTERFACE_ERC4906;
    }

    // ------------------------------------------------------------------ metadata

    function name() public view virtual returns (string memory) {
        return _name;
    }

    function symbol() public view virtual returns (string memory) {
        return _symbol;
    }

    function tokenURI(uint256 tokenId) public view virtual returns (string memory);

    // ------------------------------------------------------------------ ERC-721

    function balanceOf(address owner) public view virtual returns (uint256) {
        if (owner == address(0)) revert ERC721InvalidOwner(address(0));
        return _balances[owner];
    }

    function ownerOf(uint256 tokenId) public view virtual returns (address) {
        return _requireOwned(tokenId);
    }

    function getApproved(uint256 tokenId) public view virtual returns (address) {
        _requireOwned(tokenId);
        return _tokenApprovals[tokenId];
    }

    function isApprovedForAll(address owner, address operator) public view virtual returns (bool) {
        return _operatorApprovals[owner][operator];
    }

    function approve(address to, uint256 tokenId) public virtual {
        address owner = _requireOwned(tokenId);
        if (msg.sender != owner && !isApprovedForAll(owner, msg.sender)) {
            revert ERC721NotAuthorized(msg.sender, tokenId);
        }
        _tokenApprovals[tokenId] = to;
        emit Approval(owner, to, tokenId);
    }

    function setApprovalForAll(address operator, bool approved) public virtual {
        _operatorApprovals[msg.sender][operator] = approved;
        emit ApprovalForAll(msg.sender, operator, approved);
    }

    function transferFrom(address from, address to, uint256 tokenId) public virtual {
        address owner = _requireOwned(tokenId);
        if (owner != from) revert ERC721IncorrectOwner(from, tokenId, owner);
        if (to == address(0)) revert ERC721InvalidReceiver(address(0));
        if (!_isAuthorized(owner, msg.sender, tokenId)) revert ERC721NotAuthorized(msg.sender, tokenId);
        _update(to, tokenId);
    }

    function safeTransferFrom(address from, address to, uint256 tokenId) public virtual {
        safeTransferFrom(from, to, tokenId, "");
    }

    function safeTransferFrom(address from, address to, uint256 tokenId, bytes memory data) public virtual {
        transferFrom(from, to, tokenId);
        _checkReceiver(from, to, tokenId, data);
    }

    // ------------------------------------------------------------------ internal

    /// @dev Owner of `tokenId`, or address(0) if it does not exist. Never reverts.
    function _ownerOf(uint256 tokenId) internal view virtual returns (address) {
        return _owners[tokenId];
    }

    function _requireOwned(uint256 tokenId) internal view returns (address owner) {
        owner = _ownerOf(tokenId);
        if (owner == address(0)) revert ERC721NonexistentToken(tokenId);
    }

    function _isAuthorized(address owner, address spender, uint256 tokenId) internal view virtual returns (bool) {
        return spender == owner || isApprovedForAll(owner, spender) || _tokenApprovals[tokenId] == spender;
    }

    /// @dev Moves `tokenId` to `to` (address(0) burns), clears its approval, emits Transfer.
    ///      Performs no authorisation checks. Returns the previous owner (address(0) on mint).
    function _update(address to, uint256 tokenId) internal virtual returns (address from) {
        from = _owners[tokenId];
        if (from != address(0)) {
            delete _tokenApprovals[tokenId];
            unchecked {
                _balances[from] -= 1;
            }
        }
        if (to != address(0)) {
            unchecked {
                _balances[to] += 1;
            }
        }
        _owners[tokenId] = to;
        emit Transfer(from, to, tokenId);
    }

    function _mint(address to, uint256 tokenId) internal virtual {
        if (to == address(0)) revert ERC721InvalidReceiver(address(0));
        if (_ownerOf(tokenId) != address(0)) revert ERC721TokenExists(tokenId);
        _update(to, tokenId);
    }

    function _safeMint(address to, uint256 tokenId, bytes memory data) internal virtual {
        _mint(to, tokenId);
        _checkReceiver(address(0), to, tokenId, data);
    }

    function _burn(uint256 tokenId) internal virtual {
        _requireOwned(tokenId);
        _update(address(0), tokenId);
    }

    function _checkReceiver(address from, address to, uint256 tokenId, bytes memory data) private {
        if (to.code.length == 0) return;
        (bool ok, bytes memory ret) =
            to.call(abi.encodeCall(IERC721Receiver.onERC721Received, (msg.sender, from, tokenId, data)));
        if (!ok || ret.length < 32 || bytes4(ret) != IERC721Receiver.onERC721Received.selector) {
            revert ERC721InvalidReceiver(to);
        }
    }
}
