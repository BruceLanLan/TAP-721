// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Evaluator for tapnet/1 files: one beat of TAP-02 §4 with the bit packing of TAP-02 §5
/// @notice Signals: 0 = const 0, 1 = const 1, 2..2+nIn−1 = inputs, then one signal per element in order.
///         NAND outputs NOT(a AND b) of earlier signals; LATCH k (k-th LATCH in file order) outputs state
///         bit k; after the pass, new state bit k = the value of LATCH k's input signal. Outputs are the
///         last nOut signals. Bits are packed LSB first (bit i in byte i/8, position i%8).
///         The file is validated while it runs (same rules as TapNetlistCheck, except the 2^24-signal
///         bound, which memory limits enforce first), so malformed bytes revert rather than read garbage.
///         `eval` and `step` are public: the library is deployed once per chain and linked, which keeps
///         TapNetlistNFT under the EIP-170 code size limit.
library TapNetlistVM {
    error VMBadFile();

    /// @notice Combinational evaluation. Reverts "has latch: use step" if the file has LATCHes.
    function eval(bytes memory file, bytes memory inputs) public pure returns (bytes memory outputs) {
        bytes memory newState;
        (newState, outputs) = _run(file, "", inputs, false);
    }

    /// @notice One beat from `state`.
    function step(bytes memory file, bytes memory state, bytes memory inputs)
        public
        pure
        returns (bytes memory newState, bytes memory outputs)
    {
        return _run(file, state, inputs, true);
    }

    function _run(bytes memory file, bytes memory state, bytes memory inputs, bool allowLatch)
        private
        pure
        returns (bytes memory newState, bytes memory outputs)
    {
        uint256 len = file.length;
        if (len < 17) revert VMBadFile();
        uint256 w;
        assembly ("memory-safe") {
            w := mload(add(file, 0x20))
        }
        if (bytes8(bytes32(w)) != bytes8("TAPNET\x01\x00")) revert VMBadFile();
        uint256 nIn = (w >> 160) & 0xffffffff;
        uint256 nOut = (w >> 128) & 0xffffffff;
        if (nIn > 1 << 16 || nOut == 0 || nOut > 1 << 16) revert VMBadFile();

        // One byte per signal; upper bound on the signal count: every record is at least 4 bytes.
        bytes memory sig = new bytes(2 + nIn + (len - 16) / 4);
        _loadInputs(sig, inputs, nIn);
        (uint256 next, uint256 latches) = _pass(file, sig, state, 2 + nIn);
        if (next - 2 - nIn < nOut) revert VMBadFile();
        newState = latches == 0 ? new bytes(0) : _newState(file, sig, next, latches); // validates LATCH inputs
        if (latches != 0 && !allowLatch) revert("has latch: use step");
        outputs = _packOutputs(sig, next - nOut, nOut);
    }

    /// sig[0] = 0, sig[1] = 1, sig[2 + i] = input bit i (missing bytes read as 0).
    function _loadInputs(bytes memory sig, bytes memory inputs, uint256 nIn) private pure {
        assembly ("memory-safe") {
            let s := add(sig, 0x20)
            mstore8(add(s, 1), 1)
            let inLen := mload(inputs)
            let inPtr := add(inputs, 0x20)
            for { let i := 0 } lt(i, nIn) { i := add(i, 1) } {
                let bi := shr(3, i)
                if lt(bi, inLen) {
                    mstore8(add(s, add(2, i)), and(shr(and(i, 7), byte(0, mload(add(inPtr, bi)))), 1))
                }
            }
        }
    }

    /// Evaluates every element in order. Returns the signal count and the number of LATCHes.
    function _pass(bytes memory file, bytes memory sig, bytes memory state, uint256 next)
        private
        pure
        returns (uint256, uint256 latches)
    {
        bool bad;
        assembly ("memory-safe") {
            let s := add(sig, 0x20)
            let stLen := mload(state)
            let stPtr := add(state, 0x20)
            let end := add(add(file, 0x20), mload(file))
            for { let p := add(file, 0x30) } lt(p, end) { next := add(next, 1) } {
                let w := mload(p)
                switch shr(248, w)
                case 0 {
                    let a := and(shr(224, w), 0xffffff)
                    let b := and(shr(200, w), 0xffffff)
                    if or(or(gt(add(p, 7), end), iszero(lt(a, next))), iszero(lt(b, next))) {
                        bad := 1
                        break
                    }
                    mstore8(add(s, next), iszero(and(byte(0, mload(add(s, a))), byte(0, mload(add(s, b))))))
                    p := add(p, 7)
                }
                case 1 {
                    if gt(add(p, 4), end) {
                        bad := 1
                        break
                    }
                    let bi := shr(3, latches)
                    if lt(bi, stLen) {
                        mstore8(add(s, next), and(shr(and(latches, 7), byte(0, mload(add(stPtr, bi)))), 1))
                    }
                    latches := add(latches, 1)
                    p := add(p, 4)
                }
                default {
                    bad := 1
                    break
                }
            }
        }
        if (bad) revert VMBadFile();
        return (next, latches);
    }

    function _packOutputs(bytes memory sig, uint256 first, uint256 n) private pure returns (bytes memory out) {
        out = new bytes((n + 7) >> 3);
        assembly ("memory-safe") {
            let s := add(add(sig, 0x20), first)
            let o := add(out, 0x20)
            for { let i := 0 } lt(i, n) { i := add(i, 1) } {
                if byte(0, mload(add(s, i))) {
                    let q := add(o, shr(3, i))
                    mstore8(q, or(byte(0, mload(q)), shl(and(i, 7), 1)))
                }
            }
        }
    }

    /// New state bit k = value of the k-th LATCH's input signal after the pass.
    function _newState(bytes memory file, bytes memory sig, uint256 nSig, uint256 latches)
        private
        pure
        returns (bytes memory ns)
    {
        ns = new bytes((latches + 7) >> 3);
        bool bad;
        assembly ("memory-safe") {
            let s := add(sig, 0x20)
            let o := add(ns, 0x20)
            let end := add(add(file, 0x20), mload(file))
            let k := 0
            for { let p := add(file, 0x30) } lt(p, end) {} {
                let w := mload(p)
                switch shr(248, w)
                case 0 { p := add(p, 7) }
                default {
                    let d := and(shr(224, w), 0xffffff)
                    if iszero(lt(d, nSig)) {
                        bad := 1
                        break
                    }
                    if byte(0, mload(add(s, d))) {
                        let q := add(o, shr(3, k))
                        mstore8(q, or(byte(0, mload(q)), shl(and(k, 7), 1)))
                    }
                    k := add(k, 1)
                    p := add(p, 4)
                }
            }
        }
        if (bad) revert VMBadFile();
    }
}
