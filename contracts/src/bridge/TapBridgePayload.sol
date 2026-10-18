// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Payload v1 of the netlist-NFT bridge
/// @notice payload = abi.encode(uint8 1, bytes32 collectionKey, uint256 tokenId, address to, bytes32 netlistHash,
///         bytes32 imageHash, bytes32 manifestHash, uint64 srcChainId, uint64 dstChainId, uint64 nonce):
///         exactly 10 words (320 bytes). messageId = keccak256(srcEndpoint (20 bytes) ‖ payload), where srcEndpoint
///         is the sending endpoint, so ids stay unique when an endpoint is replaced and its nonce restarts.
library TapBridgePayload {
    uint8 internal constant VERSION = 1;
    uint256 internal constant LENGTH = 320;

    struct Payload {
        bytes32 collectionKey;
        uint256 tokenId;
        address to;
        bytes32 netlistHash;
        bytes32 imageHash;
        bytes32 manifestHash;
        uint64 srcChainId;
        uint64 dstChainId;
        uint64 nonce;
    }

    error BadPayload();

    function collectionKey(uint64 homeChainId, address homeContract) internal pure returns (bytes32) {
        return keccak256(abi.encode("TAP-NFT collection v1", homeChainId, homeContract));
    }

    function messageId(address srcEndpoint, bytes memory payload) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(srcEndpoint, payload));
    }

    function encode(Payload memory p) internal pure returns (bytes memory) {
        return abi.encode(
            VERSION,
            p.collectionKey,
            p.tokenId,
            p.to,
            p.netlistHash,
            p.imageHash,
            p.manifestHash,
            p.srcChainId,
            p.dstChainId,
            p.nonce
        );
    }

    /// @dev Strict: the length must be 320, `to` non-zero, and every word canonical (version 1, address and uint64
    ///      high bits zero),
    ///      so one payload has exactly one encoding and therefore one message id.
    function decode(bytes calldata data) internal pure returns (Payload memory p) {
        if (data.length != LENGTH) revert BadPayload();
        uint256 v;
        uint256 to;
        uint256 s;
        uint256 d;
        uint256 n;
        assembly {
            v := calldataload(data.offset)
            to := calldataload(add(data.offset, 0x60))
            s := calldataload(add(data.offset, 0xe0))
            d := calldataload(add(data.offset, 0x100))
            n := calldataload(add(data.offset, 0x120))
        }
        if (v != VERSION || to == 0 || to >> 160 != 0 || s >> 64 != 0 || d >> 64 != 0 || n >> 64 != 0) revert BadPayload();
        p.collectionKey = bytes32(data[0x20:0x40]);
        p.tokenId = uint256(bytes32(data[0x40:0x60]));
        p.to = address(uint160(to));
        p.netlistHash = bytes32(data[0x80:0xa0]);
        p.imageHash = bytes32(data[0xa0:0xc0]);
        p.manifestHash = bytes32(data[0xc0:0xe0]);
        p.srcChainId = uint64(s);
        p.dstChainId = uint64(d);
        p.nonce = uint64(n);
    }
}
