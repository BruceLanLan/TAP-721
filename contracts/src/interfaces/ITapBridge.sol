// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Message adapter (TAP draft "Moving Netlist-Bound NFTs between TapeOut chains")
/// @notice One adapter per message layer (LayerZero V2, TAP-10 hub relay, …) per chain. It carries opaque
///         payloads between endpoints and authenticates the sending endpoint on the source chain.
interface ITapBridgeAdapter {
    /// @notice Stable identifier of the message layer, e.g. keccak256("TAP-NFT adapter LayerZeroV2 v1").
    function layerId() external view returns (bytes32);

    /// @notice Native fee to send `payload` to `dstChainId`.
    function quote(uint64 dstChainId, bytes calldata payload, bytes calldata options) external view returns (uint256);

    /// @notice Send `payload` to the peer endpoint on `dstChainId`. Only the local endpoint may call.
    function send(uint64 dstChainId, bytes calldata payload, bytes calldata options, address refundTo)
        external
        payable
        returns (bytes32 transportId);
}

/// @title Bridge endpoint (gateway on the home chain, mirror elsewhere)
interface ITapBridgeEndpoint {
    enum Policy {
        NONE, // route closed
        ONE, // exactly one adapter is listed for the route; it alone delivers
        ALL // every listed adapter must deliver the identical payload before it takes effect
    }

    /// @notice Called by a listed adapter when a payload from `srcChainId` arrives. `srcEndpoint` is the sending
    ///         endpoint as authenticated by the adapter; the endpoint checks it against `route(srcChainId).peer`.
    function receivePayload(uint64 srcChainId, address srcEndpoint, bytes calldata payload) external;

    /// @notice keccak256(abi.encode("TAP-NFT collection v1", homeChainId, homeContract)).
    function collectionKey() external view returns (bytes32);

    function homeChainId() external view returns (uint64);

    /// @notice Route configuration towards / from `chainId`.
    function route(uint64 chainId) external view returns (Policy policy, address[] memory adapters, address peer);

    /// @notice True once routes can no longer be changed.
    function routesSealed() external view returns (bool);

    event Departed(bytes32 indexed messageId, uint256 indexed tokenId, uint64 dstChainId, address to);
    event Confirmed(bytes32 indexed messageId, address indexed adapter);
    event Arrived(bytes32 indexed messageId, uint256 indexed tokenId, uint64 srcChainId, address to);
}
