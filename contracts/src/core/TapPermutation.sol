// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Pool seeds and the keyed permutation of TAP draft "Netlist-Bound NFTs" §6
/// @notice permute(seed, n, ·) is a bijection of [0, n): a 4-round Feistel network over a 4^h ≥ n domain
///         (round function SHA-256), restricted to [0, n) by cycle walking. Bit-identical to
///         `tapnft.pool_seed` and `tapnft.permute`.
library TapPermutation {
    /// Pool sizes are limited to 2^32 so that half-blocks fit the u32 round input and leaf indices fit u32.
    uint256 internal constant MAX_SIZE = 1 << 32;

    error IndexOutOfRange(uint256 index, uint256 n);

    /// @notice SHA-256(masterSeed ‖ u64be(chainId) ‖ collection ‖ UTF-8(label)).
    function poolSeed(bytes32 masterSeed, uint64 chainId, address collection, string memory label)
        internal
        pure
        returns (bytes32)
    {
        return sha256(abi.encodePacked(masterSeed, chainId, collection, label));
    }

    /// @notice The entry that position `x` of a pool of size `n` receives.
    function permute(bytes32 seed, uint256 n, uint256 x) internal view returns (uint256 y) {
        if (x >= n || n > MAX_SIZE) revert IndexOutOfRange(x, n);
        if (n == 1) return 0;
        uint256 h = (_bitLength(n - 1) + 1) >> 1; // n ≥ 2 so bitlen ≥ 1
        y = _feistel(seed, x, h);
        while (y >= n) y = _feistel(seed, y, h);
    }

    function _feistel(bytes32 seed, uint256 v, uint256 h) private view returns (uint256) {
        uint256 mask = (1 << h) - 1;
        uint256 l = v >> h;
        uint256 r = v & mask;
        for (uint256 i; i < 4; ++i) {
            (l, r) = (r, l ^ (_round(seed, i, r) & mask));
        }
        return (l << h) | r;
    }

    /// @dev uint256(SHA-256(seed ‖ u8(round) ‖ u32be(r))), via the precompile on scratch memory.
    function _round(bytes32 seed, uint256 round, uint256 r) private view returns (uint256 out) {
        assembly ("memory-safe") {
            let p := mload(0x40)
            mstore(p, seed)
            mstore(add(p, 0x20), or(shl(248, round), shl(216, r)))
            if iszero(staticcall(gas(), 0x02, p, 37, 0x00, 0x20)) { revert(0, 0) }
            out := mload(0x00)
        }
    }

    function _bitLength(uint256 v) private pure returns (uint256 b) {
        while (v != 0) {
            v >>= 1;
            ++b;
        }
    }
}
