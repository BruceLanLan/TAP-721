// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Adapter seal (TAP draft "Moving Netlist-Bound NFTs between TapeOut chains")
/// @notice An adapter reports true once nothing that affects how it authenticates messages can change any more:
///         no owner, no peer or remote-endpoint changes, and for LayerZero no EndpointV2 delegate.
///         An endpoint's `sealRoutes()` requires every adapter listed on its routes to report true.
interface ITapBridgeAdapterSealed {
    function adapterSealed() external view returns (bool);

    event AdapterSealed();
}
