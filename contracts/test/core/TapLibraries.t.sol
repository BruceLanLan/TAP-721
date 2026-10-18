// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console2} from "forge-std/Test.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";
import {TapPermutation} from "../../src/core/TapPermutation.sol";
import {LibHarness, MerkleBuilder, Tapnet} from "./CoreHelpers.sol";

contract TapPermutationTest is Test {
    LibHarness h = new LibHarness();

    function _assertBijection(bytes32 seed, uint256 n) internal view {
        bool[] memory hit = new bool[](n);
        for (uint256 x; x < n; ++x) {
            uint256 y = h.permute(seed, n, x);
            assertLt(y, n);
            assertFalse(hit[y], "collision");
            hit[y] = true;
        }
    }

    /// Exhaustive: every n in 1..300, every x.
    function test_bijectionExhaustiveUpTo300() public view {
        bytes32 seed = sha256("tap-core-vectors");
        for (uint256 n = 1; n <= 300; ++n) {
            _assertBijection(seed, n);
        }
    }

    function testFuzz_bijection(bytes32 seed, uint256 n) public view {
        _assertBijection(seed, bound(n, 1, 300));
    }

    function testFuzz_inRange(bytes32 seed, uint256 n, uint256 x) public view {
        n = bound(n, 1, TapPermutation.MAX_SIZE);
        x = bound(x, 0, n - 1);
        assertLt(h.permute(seed, n, x), n);
    }

    function test_sizeOneIsIdentity() public view {
        assertEq(h.permute(bytes32(uint256(1)), 1, 0), 0);
    }

    function test_maxSizeAccepted() public view {
        assertLt(h.permute(bytes32(uint256(7)), 1 << 32, (1 << 32) - 1), 1 << 32);
    }

    function test_revertIndexOutOfRange() public {
        vm.expectRevert(abi.encodeWithSelector(TapPermutation.IndexOutOfRange.selector, 10, 10));
        h.permute(0, 10, 10);
        vm.expectRevert(abi.encodeWithSelector(TapPermutation.IndexOutOfRange.selector, 0, 0));
        h.permute(0, 0, 0);
        vm.expectRevert(abi.encodeWithSelector(TapPermutation.IndexOutOfRange.selector, 0, (1 << 32) + 1));
        h.permute(0, (1 << 32) + 1, 0);
    }

    function test_seedChangesPermutation() public view {
        uint256 same;
        for (uint256 x; x < 100; ++x) {
            if (h.permute(bytes32(uint256(1)), 100, x) == h.permute(bytes32(uint256(2)), 100, x)) ++same;
        }
        assertLt(same, 10);
    }

    function test_poolSeedLayout() public view {
        bytes32 m = bytes32(uint256(0xabc));
        address a = address(0x1234);
        assertEq(h.poolSeed(m, 196, a, "NETLIST_V1"), sha256(abi.encodePacked(m, uint64(196), a, "NETLIST_V1")));
        assertTrue(h.poolSeed(m, 196, a, "A") != h.poolSeed(m, 56, a, "A"));
    }
}

contract TapMerkleTest is Test {
    LibHarness h = new LibHarness();

    function _leaves(uint256 n, bytes32 salt) internal pure returns (bytes32[] memory l) {
        l = new bytes32[](n);
        for (uint256 i; i < n; ++i) {
            bytes32[] memory v = new bytes32[](1);
            v[0] = keccak256(abi.encode(salt, i));
            l[i] = TapMerkle.leafHash(i, v);
        }
    }

    function testFuzz_builderProofsVerify(uint256 n, uint256 index, bytes32 salt) public view {
        n = bound(n, 1, 200);
        index = bound(index, 0, n - 1);
        bytes32[] memory l = _leaves(n, salt);
        bytes32 root = MerkleBuilder.root(l);
        bytes32[] memory p = MerkleBuilder.proof(l, index);
        assertTrue(h.verify(root, n, index, l[index], p));
        // wrong index, wrong size, wrong leaf, extra element all fail
        if (n > 1) assertFalse(h.verify(root, n, (index + 1) % n, l[index], p));
        assertFalse(h.verify(root, n, index, bytes32(uint256(l[index]) ^ 1), p));
        assertFalse(h.verify(root, n, n, l[index], p));
        bytes32[] memory longer = new bytes32[](p.length + 1);
        for (uint256 i; i < p.length; ++i) {
            longer[i] = p[i];
        }
        assertFalse(h.verify(root, n, index, l[index], longer));
        if (p.length > 0) {
            bytes32[] memory shorter = new bytes32[](p.length - 1);
            for (uint256 i; i < shorter.length; ++i) {
                shorter[i] = p[i];
            }
            assertFalse(h.verify(root, n, index, l[index], shorter));
        }
    }

    function test_singleLeafRootIsLeaf() public view {
        bytes32[] memory l = _leaves(1, 0);
        assertEq(MerkleBuilder.root(l), l[0]);
        assertTrue(h.verify(l[0], 1, 0, l[0], new bytes32[](0)));
    }

    function test_oddNodePromotedWithoutProofElement() public view {
        bytes32[] memory l = _leaves(5, "x");
        // leaf 4 moves up twice unchanged: proof is just the root of leaves 0..3
        bytes32[] memory p = MerkleBuilder.proof(l, 4);
        assertEq(p.length, 1);
        assertEq(p[0], TapMerkle.nodeHash(TapMerkle.nodeHash(l[0], l[1]), TapMerkle.nodeHash(l[2], l[3])));
        assertTrue(h.verify(MerkleBuilder.root(l), 5, 4, l[4], p));
    }

    function test_leafAndNodeLayout() public view {
        bytes32[] memory v = new bytes32[](2);
        v[0] = bytes32(uint256(1));
        v[1] = bytes32(uint256(2));
        assertEq(h.leafHash(7, v), sha256(abi.encodePacked(bytes1(0), uint32(7), v[0], v[1])));
        assertEq(TapMerkle.nodeHash(v[0], v[1]), sha256(abi.encodePacked(bytes1(0x01), v[0], v[1])));
    }
}

contract TapNetlistCheckTest is Test {
    LibHarness h = new LibHarness();

    function test_xor17851() public view {
        (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) = h.check(Tapnet.xor17851());
        assertEq(abi.encode(nIn, nOut, nand, latch), abi.encode(2, 1, 4, 0));
    }

    function test_latchMayReferToLaterSignal() public view {
        bytes memory f = bytes.concat(Tapnet.header(1, 1), Tapnet.latch(4), Tapnet.nand(2, 3));
        (,,, uint256 latch) = h.check(f);
        assertEq(latch, 1);
    }

    function test_revertHeader() public {
        vm.expectRevert(TapNetlistCheck.TapnetBadHeader.selector);
        h.check(hex"544150");
        bytes memory f = Tapnet.xor17851();
        f[7] = 0x01;
        vm.expectRevert(TapNetlistCheck.TapnetBadHeader.selector);
        h.check(f);
    }

    function test_revertPins() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadPins.selector, 2, 0));
        h.check(bytes.concat(Tapnet.header(2, 0), Tapnet.nand(2, 3)));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadPins.selector, 65537, 1));
        h.check(bytes.concat(Tapnet.header(65537, 1), Tapnet.nand(2, 3)));
    }

    function test_revertNoRecords() public {
        vm.expectRevert(TapNetlistCheck.TapnetNoRecords.selector);
        h.check(Tapnet.header(2, 1));
    }

    function test_revertTruncated() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetTruncated.selector, 23));
        h.check(bytes.concat(Tapnet.header(2, 1), Tapnet.nand(2, 3), hex"010000"));
    }

    function test_revertRefAndUnknownOpcode() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadOpcode.selector, 16, 2));
        h.check(bytes.concat(Tapnet.header(2, 1), hex"02"));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadOpcode.selector, 23, 0xff));
        h.check(bytes.concat(Tapnet.header(2, 1), Tapnet.nand(2, 3), hex"ff"));
    }

    function test_revertForwardReference() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetForwardReference.selector, 16, 4));
        h.check(bytes.concat(Tapnet.header(2, 1), Tapnet.nand(4, 2)));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetForwardReference.selector, 16, 4));
        h.check(bytes.concat(Tapnet.header(2, 1), Tapnet.nand(2, 4)));
    }

    function test_revertLatchOutOfRange() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetLatchOutOfRange.selector, 5, 5));
        h.check(bytes.concat(Tapnet.header(1, 1), Tapnet.latch(5), Tapnet.nand(2, 3)));
    }

    function test_revertTooFewOutputs() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetTooFewOutputs.selector, 4, 5));
        h.check(bytes.concat(Tapnet.header(2, 5), hex"00000002000003000000020000040000000300000400000005000006"));
    }

    function test_maxPinsAccepted() public view {
        // The 2^24-signal bound needs ~16.7M records and cannot be exercised in a test.
        (uint256 nIn,,,) = h.check(bytes.concat(Tapnet.header(65536, 65536), _nands(65536)));
        assertEq(nIn, 65536);
    }

    function _nands(uint256 n) internal pure returns (bytes memory f) {
        f = new bytes(7 * n); // NAND(0, 0) records: all-zero bytes
    }

    function test_gas() public view {
        console2.log("check gas, xor-17851 (4 gates):", h.checkGas(Tapnet.xor17851()));
        console2.log("check gas, 1,204 gates (8,444 B):", h.checkGas(Tapnet.chain(1204, 0)));
        console2.log("check gas, 3,428 gates (24,000 B):", h.checkGas(Tapnet.chain(3424, 4)));
    }
}
