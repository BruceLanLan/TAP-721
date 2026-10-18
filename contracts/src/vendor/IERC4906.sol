// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title ERC-4906 metadata update events (interface id 0x49064906)
interface IERC4906 {
    event MetadataUpdate(uint256 _tokenId);
    event BatchMetadataUpdate(uint256 _fromTokenId, uint256 _toTokenId);
}
