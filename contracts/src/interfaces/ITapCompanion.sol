// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Companion endorsement (TAP draft "Netlist-Bound NFTs")
/// @notice A companion implementing ITapNetlistNFT for an existing ERC-721 is bound in both directions once
///         the collection's owner endorses it. Works even after the collection's metadata is frozen.
interface ITapCompanion {
    /// @notice Reverts unless msg.sender == collection().owner() at call time. Records the caller
    ///         permanently; later calls by the owner have no effect.
    function endorse() external;

    /// @notice The account that endorsed this companion, or address(0).
    function endorsedBy() external view returns (address);

    event Endorsed(address by);
}
