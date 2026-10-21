// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {SoulboundNetlistCredential} from "../src/SoulboundNetlistCredential.sol";
import {ITapCredentialProven} from "../src/interfaces/ITapCredential.sol";

/// @notice The reviewer's attack tests (Attack.t.sol, Attack2.t.sol), ported as regression tests: each attack
///         worked against the earlier draft and MUST now fail.
contract SoulboundAttackRegressionTest is Test {
    SoulboundNetlistCredential internal sbt;

    function setUp() public {
        sbt = new SoulboundNetlistCredential("x", "x", "x/");
    }

    function _file(uint32 nIn, uint32 nOut, uint256 n) internal pure returns (bytes memory recs) {
        for (uint256 k; k < n; k++) {
            uint256 hi = 2 + nIn + k;
            recs = bytes.concat(recs, hex"00", bytes3(uint24((k * 7919) % hi)), bytes3(uint24((k * 104729 + 3) % hi)));
        }
        recs = bytes.concat("TAPNET", hex"0100", bytes4(nIn), bytes4(nOut), recs);
    }

    function _spec(uint32 nIn, uint32 nOut, bytes32 target, uint32 maxG, address auth)
        internal
        view
        returns (ITapCredentialProven.Spec memory s)
    {
        s.registrant = address(this);
        s.nIn = nIn;
        s.nOut = nOut;
        s.target = target;
        s.maxGates = maxG;
        s.commitStart = 10;
        s.commitEnd = 20;
        s.revealEnd = 30;
        s.recoveryAuthority = auth;
    }

    /// B1, Attack.t.sol test_commitSquat: copying a victim's commitment from the mempool no longer locks it out.
    function test_commitSquatFails() public {
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, address(0)));
        address victim = address(0xA11CE);
        address attacker = address(0xBAD);
        bytes32 c = sbt.commitmentOf(id, victim, 0, sha256(f), keccak256("salt"));
        vm.warp(10);
        vm.prank(attacker);
        sbt.commit(id, c); // front-run: recorded for the attacker only
        vm.prank(victim);
        sbt.commit(id, c); // the victim's own commit still succeeds
        assertTrue(sbt.committed(id, victim, c));
        assertTrue(sbt.committed(id, attacker, c));
        vm.warp(20);
        uint256 t = sbt.reveal(id, victim, 0, f, keccak256("salt"));
        assertEq(sbt.ownerOf(t), victim);
        // the attacker's copy names the victim inside, so it cannot mint to the attacker either
        bytes32 salt = keccak256("salt");
        vm.expectRevert(SoulboundNetlistCredential.NoCommitment.selector);
        sbt.reveal(id, attacker, 0, f, salt);
    }

    /// M1, Attack.t.sol test_exhaustiveManyOutputs: specifications with huge truth-table buffers are refused.
    function test_exhaustiveManyOutputsRefused() public {
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "gate work"));
        sbt.registerSpec(_spec(13, 4096, bytes32(uint256(1)), 4096, address(0)));
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "gate work"));
        sbt.registerSpec(_spec(16, 512, bytes32(uint256(1)), 512, address(0)));
        // 8 inputs, 4096 outputs: 4096 gates are beyond the gate-work bound (21 x 4096 > 2^16)
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "gate work"));
        sbt.registerSpec(_spec(8, 4096, bytes32(uint256(1)), 4096, address(0)));
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "table size"));
        sbt.registerSpec(_spec(16, 17, bytes32(uint256(1)), 17, address(0)));
    }

    /// B2, Attack.t.sol test_optimisticHugeInputsChallenge and Attack2.t.sol test_worst/mid/small/tiny:
    /// there is no optimistic mode and no challenge; specifications with more than 16 inputs are refused.
    function test_optimisticModeGone() public {
        uint32[5] memory nIns = [uint32(65536), 32768, 16384, 4096, 17];
        for (uint256 i; i < nIns.length; i++) {
            vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "pins"));
            sbt.registerSpec(_spec(nIns[i], 1, bytes32(uint256(1)), 1, address(0)));
        }
        (bool ok,) = address(sbt).call(abi.encodeWithSignature("challenge(uint256,bytes)", 1, hex"01"));
        assertFalse(ok);
        (ok,) = address(sbt).call(abi.encodeWithSignature("finalize(uint256)", 1));
        assertFalse(ok);
    }

    /// B2, Attack2.t.sol test_finalizeRefutedDuplicate: a wrong netlist can no longer be accepted at all,
    /// because every accepted netlist passed the exhaustive check at its reveal.
    function test_wrongNetlistNeverAccepted() public {
        bytes memory ref = bytes.concat("TAPNET", hex"0100", bytes4(uint32(2)), bytes4(uint32(1)), hex"00", bytes3(uint24(2)), bytes3(uint24(3)));
        bytes memory cand = bytes.concat("TAPNET", hex"0100", bytes4(uint32(2)), bytes4(uint32(1)), hex"00", bytes3(uint24(2)), bytes3(uint24(2)));
        (, bytes32 tt) = sbt.inspect(ref);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 1, address(0)));
        address a = address(0xA);
        address b = address(0xB);
        vm.warp(10);
        bytes32 ca = sbt.commitmentOf(id, a, 0, sha256(cand), 0);
        bytes32 cb = sbt.commitmentOf(id, b, 0, sha256(cand), bytes32(uint256(1)));
        vm.prank(a);
        sbt.commit(id, ca);
        vm.prank(b);
        sbt.commit(id, cb);
        vm.warp(20);
        vm.expectRevert(SoulboundNetlistCredential.WrongFunction.selector);
        sbt.reveal(id, a, 0, cand, 0);
        vm.expectRevert(SoulboundNetlistCredential.WrongFunction.selector);
        sbt.reveal(id, b, 0, cand, bytes32(uint256(1)));
    }

    /// M2: a rebind cannot give an account a second credential of the same specification.
    function test_rebindOntoHolderRefused() public {
        uint256 pk = 0xA0;
        address auth = vm.addr(pk);
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, auth));
        address u = address(0x1001);
        address v = address(0x1002);
        vm.warp(10);
        bytes32 cu = sbt.commitmentOf(id, u, 0, sha256(f), bytes32(uint256(1)));
        bytes32 cv = sbt.commitmentOf(id, v, 0, sha256(f), bytes32(uint256(2)));
        vm.prank(u);
        sbt.commit(id, cu);
        vm.prank(v);
        sbt.commit(id, cv);
        vm.warp(20);
        uint256 tu = sbt.reveal(id, u, 0, f, bytes32(uint256(1)));
        sbt.reveal(id, v, 0, f, bytes32(uint256(2)));
        ITapCredentialProven.Rebind memory r = ITapCredentialProven.Rebind(auth, tu, v, 0, bytes32(0));
        (uint8 sv, bytes32 sr, bytes32 ss) = vm.sign(pk, sbt.rebindDigest(r));
        vm.prank(v);
        vm.expectRevert(SoulboundNetlistCredential.AlreadyHolds.selector);
        sbt.requestRebind(r, abi.encodePacked(sr, ss, sv));
    }
}
