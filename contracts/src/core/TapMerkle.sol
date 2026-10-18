// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Pool leaves and Merkle proofs of TAP draft "Netlist-Bound NFTs" §5
/// @notice SHA-256 tree with domain-separated leaves (0x00) and nodes (0x01). At each level nodes are
///         paired (0,1), (2,3), …; an odd last node moves up unchanged and contributes no proof element.
///         Bit-identical to `tapnft.leaf_hash` and `tapnft.merkle_verify`.
library TapMerkle {
    /// @notice SHA-256(0x00 ‖ u32be(index) ‖ values[0] ‖ … ‖ values[k−1]).
    function leafHash(uint256 index, bytes32[] memory values) internal pure returns (bytes32) {
        return sha256(abi.encodePacked(bytes1(0x00), uint32(index), values));
    }

    /// @notice SHA-256(0x01 ‖ left ‖ right).
    function nodeHash(bytes32 left, bytes32 right) internal pure returns (bytes32) {
        return sha256(abi.encodePacked(bytes1(0x01), left, right));
    }

    /// @notice True iff `proof` proves `leaf` at `index` of a tree of `size` leaves with root `root`.
    ///         The proof must be consumed exactly.
    function verify(bytes32 root, uint256 size, uint256 index, bytes32 leaf, bytes32[] memory proof)
        internal
        pure
        returns (bool)
    {
        if (index >= size) return false;
        bytes32 h = leaf;
        uint256 p;
        uint256 len = proof.length;
        uint256 i = index;
        for (uint256 width = size; width > 1; width = (width + 1) >> 1) {
            if (i & 1 == 1) {
                if (p >= len) return false;
                h = nodeHash(proof[p++], h);
            } else if (i + 1 < width) {
                if (p >= len) return false;
                h = nodeHash(h, proof[p++]);
            }
            i >>= 1;
        }
        return p == len && h == root;
    }
}
