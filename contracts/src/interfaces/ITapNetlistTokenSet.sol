// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Explicit token sets (TAP draft "Netlist-Bound NFTs")
/// @notice For collections whose valid token ids are not a contiguous range. The manifest commits
///         tokenSetHash = SHA-256(u32be(id_0) ‖ u32be(id_1) ‖ …) over the valid ids in ascending order, and
///         the position x of token t in every pool permutation is its rank in that list. In range mode
///         (no token set) tokenSetHash() is zero and the functions describe the range
///         firstTokenId .. firstTokenId + supply − 1.
interface ITapNetlistTokenSet {
    /// @notice SHA-256 of the packed ascending id list; zero in range mode.
    function tokenSetHash() external view returns (bytes32);

    /// @notice Number of tokens covered by the manifest (= supply).
    function tokenCount() external view returns (uint256);

    /// @notice The token id of rank `index` (0-based). Reverts if out of range or the set is not loaded.
    function tokenAt(uint256 index) external view returns (uint256);

    /// @notice The rank of `tokenId`. Reverts if it is not covered or the set is not loaded.
    function indexOf(uint256 tokenId) external view returns (uint256);
}
