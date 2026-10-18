// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title User-facing part of a bridge endpoint (TAP draft "Moving Netlist-Bound NFTs between TapeOut chains")
/// @notice Added next to ITapBridgeEndpoint (ITapBridge.sol), which it does not change. Implemented by
///         TapGateway (home chain) and TapMirror (remote chains).
interface ITapBridgeTransfer {
    /// @notice Native fee for moving `tokenId` to `to` on `dstChainId`: the total, and one entry per adapter
    ///         of the route in route order. `options[i]` is passed to adapter i (empty = adapter default).
    function quoteBridge(uint256 tokenId, uint64 dstChainId, address to, bytes[] calldata options)
        external
        view
        returns (uint256 total, uint256[] memory fees);

    /// @notice Lock (home) or burn (remote) `tokenId` and send the payload through every adapter of the route.
    ///         The caller MUST be the owner of the token or approved for it. Excess value goes back to the caller.
    ///         Reverts if `to` has code on this chain (other than an EIP-7702 delegation designator) unless
    ///         `contractRecipientOk` is true: a contract wallet here may not exist, or not be controlled by the same
    ///         party, at the same address on the destination chain, and the destination cannot check this.
    function bridge(uint256 tokenId, uint64 dstChainId, address to, bool contractRecipientOk, bytes[] calldata options)
        external
        payable
        returns (bytes32 messageId);

    /// @notice Send an already departed payload again through adapter `adapterIndex` of the current route.
    ///         Permissionless; idempotent at the destination. Used to recover from a lost adapter delivery.
    function resend(bytes calldata payload, uint256 adapterIndex, bytes calldata options)
        external
        payable
        returns (bytes32 transportId);

    /// @notice True if this endpoint sent the payload with this message id.
    function departed(bytes32 messageId) external view returns (bool);

    /// @notice True once the payload with this message id took effect here.
    function executed(bytes32 messageId) external view returns (bool);

    /// @notice Under an ALL route: true if `adapter` has delivered the payload with this message id here.
    ///         Not recorded under ONE (there `executed` is the only record).
    function confirmedBy(bytes32 messageId, address adapter) external view returns (bool);

    /// @notice Next outgoing nonce of this endpoint.
    function nextNonce() external view returns (uint64);

    /// @notice Owner only, before `sealRoutes()`. `policy` ONE needs exactly one adapter, ALL two to eight.
    ///         `peer` is the endpoint contract on `chainId`. Policy NONE closes the route.
    function setRoute(uint64 chainId, uint8 policy, address[] calldata adapters, address peer) external;

    /// @notice Owner only. Irreversible: afterwards no route can change.
    function sealRoutes() external;

    event RouteSet(uint64 indexed chainId, uint8 policy, address[] adapters, address peer);
    event RoutesSealed();
}
