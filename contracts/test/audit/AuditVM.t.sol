// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TapNetlistVM} from "../../src/core/TapNetlistVM.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";

contract VMHarness {
    function step(bytes calldata f, bytes calldata s, bytes calldata i) external pure returns (bytes memory, bytes memory) {
        return TapNetlistVM.step(f, s, i);
    }

    function eval(bytes calldata f, bytes calldata i) external pure returns (bytes memory) {
        return TapNetlistVM.eval(f, i);
    }

    function check(bytes calldata f) external pure returns (uint256, uint256, uint256, uint256) {
        return TapNetlistCheck.check(f);
    }
}

/// Differential fuzz of TapNetlistVM against a straightforward TAP-02 §4/§5 evaluator, plus
/// check/VM agreement on arbitrary bytes. Supports reviews/security-contracts.md "checked and sound".
contract AuditVMTest is Test {
    VMHarness h = new VMHarness();

    function _bit(bytes memory v, uint256 i) internal pure returns (uint8) {
        if (i / 8 >= v.length) return 0;
        return uint8(v[i / 8] >> (i % 8)) & 1;
    }

    function _gen(uint256 seed) internal pure returns (bytes memory f, uint256 nIn, uint256 nOut, uint256 nLatch) {
        nIn = seed % 9;
        uint256 r = 1 + (seed >> 8) % 40;
        nOut = 1 + (seed >> 16) % r;
        uint256 S = 2 + nIn + r;
        f = abi.encodePacked("TAPNET", uint8(1), uint8(0), uint32(nIn), uint32(nOut));
        uint256 next = 2 + nIn;
        for (uint256 k; k < r; ++k) {
            uint256 x = uint256(keccak256(abi.encode(seed, k)));
            if (x % 4 == 0) {
                f = abi.encodePacked(f, uint8(1), uint24((x >> 8) % S));
                ++nLatch;
            } else {
                f = abi.encodePacked(f, uint8(0), uint24((x >> 8) % next), uint24((x >> 40) % next));
            }
            ++next;
        }
    }

    function _u24(bytes memory f, uint256 p) internal pure returns (uint256) {
        return (uint256(uint8(f[p])) << 16) | (uint256(uint8(f[p + 1])) << 8) | uint256(uint8(f[p + 2]));
    }

    /// Reference beat: returns the signal vector after the pass and the LATCH input list.
    function _pass(bytes memory f, uint256 nIn, bytes memory st, bytes memory inp)
        internal
        pure
        returns (uint8[] memory s, uint256[] memory ds, uint256 next)
    {
        s = new uint8[](2 + nIn + (f.length - 16) / 4);
        ds = new uint256[]((f.length - 16) / 4);
        s[1] = 1;
        for (uint256 i; i < nIn; ++i) s[2 + i] = _bit(inp, i);
        next = 2 + nIn;
        uint256 k;
        for (uint256 p = 16; p < f.length; ++next) {
            if (f[p] == 0x00) {
                s[next] = 1 - (s[_u24(f, p + 1)] & s[_u24(f, p + 4)]);
                p += 7;
            } else {
                ds[k] = _u24(f, p + 1);
                s[next] = _bit(st, k);
                ++k;
                p += 4;
            }
        }
        assembly {
            mstore(ds, k)
        }
    }

    function _ref(bytes memory f, uint256 nIn, uint256 nOut, bytes memory st, bytes memory inp)
        internal
        pure
        returns (bytes memory ns, bytes memory out)
    {
        (uint8[] memory s, uint256[] memory ds, uint256 next) = _pass(f, nIn, st, inp);
        ns = new bytes((ds.length + 7) / 8);
        for (uint256 j; j < ds.length; ++j) if (s[ds[j]] == 1) ns[j / 8] |= bytes1(uint8(1 << (j % 8)));
        out = new bytes((nOut + 7) / 8);
        for (uint256 j; j < nOut; ++j) if (s[next - nOut + j] == 1) out[j / 8] |= bytes1(uint8(1 << (j % 8)));
    }

    function testFuzz_audit_vmMatchesReference(uint256 seed, bytes calldata st, bytes calldata inp) public view {
        (bytes memory f, uint256 nIn, uint256 nOut, uint256 nLatch) = _gen(seed);
        (,,, uint256 latch) = h.check(f); // generator only makes valid files
        assertEq(latch, nLatch);
        _compare(f, nIn, nOut, nLatch, st, inp);
    }

    function _compare(bytes memory f, uint256 nIn, uint256 nOut, uint256 nLatch, bytes memory st, bytes memory inp)
        internal
        view
    {
        (bytes memory ns2, bytes memory out2) = _ref(f, nIn, nOut, st, inp);
        (bytes memory ns, bytes memory out) = h.step(f, st, inp);
        assertEq(ns, ns2);
        assertEq(out, out2);
        if (nLatch == 0) assertEq(h.eval(f, inp), out2);
    }

    /// On arbitrary bytes behind a valid header, the VM never accepts a file the check rejects.
    function testFuzz_audit_vmRejectsWhatCheckRejects(uint16 nIn, uint16 nOut, bytes calldata body) public view {
        bytes memory f = abi.encodePacked("TAPNET", uint8(1), uint8(0), uint32(nIn % 6), uint32(nOut % 6), body);
        bool okCheck;
        try h.check(f) {
            okCheck = true;
        } catch {}
        bool okVm;
        try h.step(f, "", "") {
            okVm = true;
        } catch {}
        assertEq(okVm, okCheck);
    }
}
