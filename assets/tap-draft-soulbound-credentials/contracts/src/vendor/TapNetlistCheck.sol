// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title On-chain validity check of tapnet/1 files (TAP draft "Netlist-Bound NFTs" §2)
/// @notice Full decode: header (magic, version, reserved byte), TAP-02 records restricted to NAND and
///         LATCH, and TAP-02 §3 well-formedness: pin ranges, signal limit, NAND inputs refer to earlier
///         signals, LATCH inputs refer to existing signals, at least nOut element outputs.
///         Accepts exactly the files `tapnft.check_file` accepts. Optional: hashes in a manifest already
///         pin file contents, so contracts need not call it.
library TapNetlistCheck {
    error TapnetBadHeader();
    error TapnetBadPins(uint256 nIn, uint256 nOut);
    error TapnetNoRecords();
    error TapnetTruncated(uint256 offset);
    error TapnetBadOpcode(uint256 offset, uint256 opcode); // includes REF (0x02)
    error TapnetForwardReference(uint256 offset, uint256 signal);
    error TapnetLatchOutOfRange(uint256 signal, uint256 signals);
    error TapnetTooFewOutputs(uint256 elements, uint256 nOut);
    error TapnetTooManySignals(uint256 signals);

    bytes8 private constant HEADER = "TAPNET\x01\x00";
    uint256 private constant MAX_PINS = 1 << 16;
    uint256 private constant MAX_SIGNALS = 1 << 24;

    function check(bytes memory file) internal pure returns (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) {
        uint256 len = file.length;
        if (len < 16) revert TapnetBadHeader();
        uint256 w;
        assembly ("memory-safe") {
            w := mload(add(file, 0x20))
        }
        if (bytes8(bytes32(w)) != HEADER) revert TapnetBadHeader();
        nIn = (w >> 160) & 0xffffffff;
        nOut = (w >> 128) & 0xffffffff;
        if (nIn > MAX_PINS || nOut == 0 || nOut > MAX_PINS) revert TapnetBadPins(nIn, nOut);
        if (len == 16) revert TapnetNoRecords();

        uint256 next = 2 + nIn; // index of the signal the current element produces
        uint256 maxLatchInput;
        uint256 err; // 1 truncated, 2 bad opcode, 3 forward reference
        uint256 errAt;
        uint256 errVal;
        assembly ("memory-safe") {
            let base := add(file, 0x20)
            let end := add(base, len)
            let p := add(base, 16)
            for {} lt(p, end) { next := add(next, 1) } {
                w := mload(p)
                let op := shr(248, w)
                switch op
                case 0 {
                    if gt(add(p, 7), end) {
                        err := 1
                        break
                    }
                    let a := and(shr(224, w), 0xffffff)
                    let b := and(shr(200, w), 0xffffff)
                    if iszero(lt(a, next)) {
                        err := 3
                        errVal := a
                        break
                    }
                    if iszero(lt(b, next)) {
                        err := 3
                        errVal := b
                        break
                    }
                    p := add(p, 7)
                    nand := add(nand, 1)
                }
                case 1 {
                    if gt(add(p, 4), end) {
                        err := 1
                        break
                    }
                    let d := and(shr(224, w), 0xffffff)
                    if gt(d, maxLatchInput) { maxLatchInput := d }
                    p := add(p, 4)
                    latch := add(latch, 1)
                }
                default {
                    err := 2
                    errVal := op
                    break
                }
            }
            errAt := sub(p, base)
        }
        if (err == 1) revert TapnetTruncated(errAt);
        if (err == 2) revert TapnetBadOpcode(errAt, errVal);
        if (err == 3) revert TapnetForwardReference(errAt, errVal);
        if (next > MAX_SIGNALS) revert TapnetTooManySignals(next);
        if (latch != 0 && maxLatchInput >= next) revert TapnetLatchOutOfRange(maxLatchInput, next);
        if (nand + latch < nOut) revert TapnetTooFewOutputs(nand + latch, nOut);
    }
}
