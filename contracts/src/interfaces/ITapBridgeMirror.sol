// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title What a bridge mirror can honestly promise (TAP draft "Moving Netlist-Bound NFTs between TapeOut chains")
/// @notice A mirror has no manifest, pools or reveal of its own; it only stores the hashes bridge messages carried.
///         It also implements ITapNetlistNFT, where the reveal functions are defined as empty (see the draft).
///         Proposed as the smaller ERC-165 interface clients test for on a remote chain.
interface ITapBridgeMirror {
    /// @notice True once some arriving payload carried this netlist hash.
    function knownNetlist(bytes32 netlistHash) external view returns (bool);

    /// @notice The first non-zero manifest hash any payload carried; zero before. Never changes once non-zero.
    function manifestHash() external view returns (bytes32);

    /// @notice Same as ITapNetlistNFT.storeNetlist: store a tapnet/1 file whose SHA-256 is a known netlist hash.
    function materialize(bytes calldata file) external returns (bytes32 netlistHash);
}
