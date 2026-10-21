// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Checks of LATCH-free tapnet/1 files for proven credentials
///        (TAP draft "Soulbound Netlist Credentials" §4.2, §4.3)
/// @notice Every function expects a file that already passed TapNetlistCheck.check with latch = 0;
///         `nand` is its number of NAND records. The records start at byte 16, 7 bytes each.
library TapCredentialCheck {
    bytes private constant TAG_TRUTH_TABLE = "tap-credential-truth-table/1\x00"; // 29 bytes
    bytes private constant TAG_DESIGN_KEY = "tap-credential-design-key/1\x00"; // 28 bytes

    /// @notice truthTableHash (§4.2) by bit-sliced evaluation: 256 input vectors per word, one NAND per word.
    function truthTableHash(bytes memory file, uint256 nIn, uint256 nOut, uint256 nand)
        internal
        pure
        returns (bytes32 h)
    {
        require(nIn <= 16, "nIn > 16");
        uint256 nSig = 2 + nIn + nand;
        uint256 chunks = nIn >= 8 ? 1 << (nIn - 8) : 1;
        uint256 colLen = nIn >= 3 ? (1 << nIn) >> 3 : 1;
        uint256 hdr = 37;
        uint256 total = hdr + nOut * colLen;
        bytes memory head = abi.encodePacked(TAG_TRUTH_TABLE, uint32(nIn), uint32(nOut));
        bytes memory buf = new bytes(total + 64);
        uint256[] memory sig = new uint256[](nSig);
        uint256[] memory pairs = new uint256[](nand);
        uint256[8] memory pat = [
            0x5555555555555555555555555555555555555555555555555555555555555555,
            0x3333333333333333333333333333333333333333333333333333333333333333,
            0x0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f,
            0x00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff00ff,
            0x0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff0000ffff,
            0x00000000ffffffff00000000ffffffff00000000ffffffff00000000ffffffff,
            0x0000000000000000ffffffffffffffff0000000000000000ffffffffffffffff,
            0x00000000000000000000000000000000ffffffffffffffffffffffffffffffff
        ];
        uint256 topMask = nIn >= 8 ? type(uint256).max : type(uint256).max << (256 - (1 << nIn));
        assembly ("memory-safe") {
            let sigp := add(sig, 0x20)
            // header
            mstore(add(buf, 0x20), mload(add(head, 0x20)))
            mstore(add(buf, 0x40), mload(add(head, 0x40)))
            // decode NAND records into (address of a << 128) | address of b
            let rec := add(file, 0x30)
            let pp := add(pairs, 0x20)
            for { let k := 0 } lt(k, nand) { k := add(k, 1) } {
                let w := mload(add(rec, mul(k, 7)))
                let a := and(shr(224, w), 0xffffff)
                let b := and(shr(200, w), 0xffffff)
                mstore(add(pp, shl(5, k)), or(shl(128, add(sigp, shl(5, a))), add(sigp, shl(5, b))))
            }
            let outBase := add(sigp, shl(5, sub(nSig, nOut)))
            let colBase := add(add(buf, 0x20), hdr)
            let gateBase := add(sigp, shl(5, add(2, nIn)))
            let maskLow := 0xffffffffffffffffffffffffffffffff
            for { let c := 0 } lt(c, chunks) { c := add(c, 1) } {
                mstore(sigp, 0)
                mstore(add(sigp, 0x20), not(0))
                for { let i := 0 } lt(i, nIn) { i := add(i, 1) } {
                    let v
                    switch lt(i, 8)
                    case 1 { v := mload(add(pat, shl(5, i))) }
                    default { v := sub(0, and(shr(sub(i, 8), c), 1)) }
                    mstore(add(sigp, shl(5, add(2, i))), v)
                }
                let out := gateBase
                for { let k := 0 } lt(k, nand) { k := add(k, 1) } {
                    let pr := mload(add(pp, shl(5, k)))
                    mstore(out, not(and(mload(shr(128, pr)), mload(and(pr, maskLow)))))
                    out := add(out, 0x20)
                }
                for { let j := 0 } lt(j, nOut) { j := add(j, 1) } {
                    mstore(add(colBase, add(mul(j, colLen), shl(5, c))), and(mload(add(outBase, shl(5, j))), topMask))
                }
            }
            mstore(buf, total)
        }
        h = sha256(buf);
    }

    /// @notice designKey (§4.3): the structural labels of the outputs, under a domain tag.
    function designKey(bytes memory file, uint256 nIn, uint256 nOut, uint256 nand)
        internal
        view
        returns (bytes32 h)
    {
        uint256 nSig = 2 + nIn + nand;
        bytes32[] memory lab = new bytes32[](nSig);
        bytes memory scratch = new bytes(96);
        bytes memory buf = new bytes(36 + 32 * nOut);
        bytes memory head = abi.encodePacked(TAG_DESIGN_KEY, uint32(nIn), uint32(nOut));
        assembly ("memory-safe") {
            let lp := add(lab, 0x20)
            let sp := add(scratch, 0x20)
            // L(x) = SHA-256("TAPSH1" ‖ x)
            mstore(sp, shl(208, 0x544150534831)) // "TAPSH1"
            mstore8(add(sp, 6), 0x00)
            mstore8(add(sp, 7), 0x00)
            if iszero(staticcall(gas(), 2, sp, 8, lp, 32)) { revert(0, 0) }
            mstore8(add(sp, 7), 0x01)
            if iszero(staticcall(gas(), 2, sp, 8, add(lp, 0x20), 32)) { revert(0, 0) }
            let rec := add(file, 0x30)
            let firstGate := add(2, nIn)
            for { let k := 0 } lt(k, nand) { k := add(k, 1) } {
                let w := mload(add(rec, mul(k, 7)))
                let s0 := and(shr(224, w), 0xffffff)
                let s1 := and(shr(200, w), 0xffffff)
                let la := mload(add(lp, shl(5, s0)))
                let lb := mload(add(lp, shl(5, s1)))
                // input labels, computed on first use: L(0x01 ‖ u32be(i))
                if and(iszero(la), lt(s0, firstGate)) {
                    mstore(sp, shl(208, 0x544150534831))
                    mstore8(add(sp, 6), 0x01)
                    mstore(add(sp, 7), shl(224, sub(s0, 2)))
                    if iszero(staticcall(gas(), 2, sp, 11, add(lp, shl(5, s0)), 32)) { revert(0, 0) }
                    la := mload(add(lp, shl(5, s0)))
                }
                if and(iszero(lb), lt(s1, firstGate)) {
                    mstore(sp, shl(208, 0x544150534831))
                    mstore8(add(sp, 6), 0x01)
                    mstore(add(sp, 7), shl(224, sub(s1, 2)))
                    if iszero(staticcall(gas(), 2, sp, 11, add(lp, shl(5, s1)), 32)) { revert(0, 0) }
                    lb := mload(add(lp, shl(5, s1)))
                }
                if gt(la, lb) {
                    let t := la
                    la := lb
                    lb := t
                }
                mstore(sp, shl(208, 0x544150534831))
                mstore8(add(sp, 6), 0x02)
                mstore(add(sp, 7), la)
                mstore(add(sp, 39), lb)
                if iszero(staticcall(gas(), 2, sp, 71, add(lp, shl(5, add(firstGate, k))), 32)) { revert(0, 0) }
            }
            let bp := add(buf, 0x20)
            mstore(bp, mload(add(head, 0x20)))
            mstore(add(bp, 0x20), mload(add(head, 0x40)))
            let ob := add(lp, shl(5, sub(nSig, nOut)))
            for { let j := 0 } lt(j, nOut) { j := add(j, 1) } {
                mstore(add(add(bp, 36), shl(5, j)), mload(add(ob, shl(5, j))))
            }
        }
        h = sha256(buf);
    }
}
