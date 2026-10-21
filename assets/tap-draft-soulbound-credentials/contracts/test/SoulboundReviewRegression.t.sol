// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, Vm, console} from "forge-std/Test.sol";
import {SoulboundNetlistCredential} from "../src/SoulboundNetlistCredential.sol";
import {ITapCredentialProven, ITapCredentialAttested} from "../src/interfaces/ITapCredential.sol";

/// @notice The second review's reproductions (Attack3.t.sol), ported as regression tests. Tests 1, 2 and 6 showed
///         defects of the earlier draft and now check the fixes; tests 3, 4, 5, 7 and 8 document behaviour the
///         specification now states.
contract SoulboundReviewRegressionTest is Test {
    SoulboundNetlistCredential internal sbt;
    /// "TAPNET" ‖ version ‖ nIn 2 ‖ nOut 1 ‖ two NAND records (an AND gate)
    bytes internal constant BADGE = hex"5441504e4554010000000002000000010000000200000300000004000004";

    function setUp() public {
        sbt = new SoulboundNetlistCredential("x", "x", "x/");
    }

    function _file(uint32 nIn, uint32 nOut, uint256 n) internal pure returns (bytes memory r) {
        r = new bytes(16 + 7 * n);
        bytes memory h = bytes.concat("TAPNET", hex"0100", bytes4(nIn), bytes4(nOut));
        for (uint256 i; i < 16; i++) {
            r[i] = h[i];
        }
        for (uint256 k; k < n; k++) {
            uint256 hi = 2 + nIn + k;
            uint256 a = (k * 7919 + 1) % hi;
            uint256 b = (k * 104729 + 3) % hi;
            uint256 o = 16 + 7 * k;
            r[o + 1] = bytes1(uint8(a >> 16));
            r[o + 2] = bytes1(uint8(a >> 8));
            r[o + 3] = bytes1(uint8(a));
            r[o + 4] = bytes1(uint8(b >> 16));
            r[o + 5] = bytes1(uint8(b >> 8));
            r[o + 6] = bytes1(uint8(b));
        }
    }

    function _spec(uint32 nIn, uint32 nOut, bytes32 target, uint32 maxG, address auth, bool uniq, bytes32 series, uint64 t0)
        internal
        view
        returns (ITapCredentialProven.Spec memory s)
    {
        s.registrant = address(this);
        s.nIn = nIn;
        s.nOut = nOut;
        s.target = target;
        s.maxGates = maxG;
        s.commitStart = t0;
        s.commitEnd = t0 + 10;
        s.revealEnd = t0 + 20;
        s.recoveryAuthority = auth;
        s.unique = uniq;
        s.series = series;
    }

    function _commit(bytes32 id, address u, bytes memory f, uint64 t0) internal {
        bytes32 c = sbt.commitmentOf(id, u, 0, sha256(f), bytes32(0));
        vm.warp(t0);
        vm.prank(u);
        sbt.commit(id, c);
        vm.warp(t0 + 10);
    }

    function _commitReveal(bytes32 id, address u, bytes memory f, uint64 t0) internal returns (uint256 t, uint256 gas) {
        _commit(id, u, f, t0);
        uint256 g = gasleft();
        t = sbt.reveal(id, u, 0, f, bytes32(0));
        gas = g - gasleft();
    }

    function _signRebind(uint256 pk, ITapCredentialProven.Rebind memory r) internal view returns (bytes memory) {
        (uint8 v, bytes32 rr, bytes32 ss) = vm.sign(pk, sbt.rebindDigest(r));
        return abi.encodePacked(rr, ss, v);
    }

    /// 1 (M1). A stale pending request no longer locks the recovery path: it lapses REBIND_DELAY after it became
    /// ready, and a new authority-signed Rebind replaces it, with a fresh delay and veto window.
    function test_stalePendingRebindNoLongerLocks() public {
        uint256 pk = 0xA0;
        address auth = vm.addr(pk);
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, auth, false, 0, 10));
        address victim = address(0x1001);
        (uint256 tv,) = _commitReveal(id, victim, f, 10);
        address x = address(0xBAD);
        ITapCredentialProven.Rebind memory r = ITapCredentialProven.Rebind(auth, tv, x, 0, bytes32(uint256(1)));
        bytes memory sigr = _signRebind(pk, r);
        vm.prank(x);
        uint64 readyX = sbt.requestRebind(r, sigr);
        // X never completes; a year later X can no longer complete, and the authority signs for Y
        vm.warp(block.timestamp + 365 days);
        vm.prank(x);
        vm.expectRevert(SoulboundNetlistCredential.RebindLapsed.selector);
        sbt.completeRebind(tv);
        address y = address(0x600D);
        ITapCredentialProven.Rebind memory r2 = ITapCredentialProven.Rebind(auth, tv, y, 0, bytes32(uint256(2)));
        bytes memory sigr2 = _signRebind(pk, r2);
        vm.prank(y);
        uint64 readyY = sbt.requestRebind(r2, sigr2);
        assertEq(readyY, uint64(block.timestamp) + sbt.REBIND_DELAY());
        assertGt(readyY, readyX);
        // a replacement within the delay restarts it; the replaced holder cannot complete
        vm.warp(block.timestamp + 1 days);
        address z = address(0x2002);
        ITapCredentialProven.Rebind memory r3 = ITapCredentialProven.Rebind(auth, tv, z, 0, bytes32(uint256(3)));
        bytes memory sigr3 = _signRebind(pk, r3);
        vm.prank(z);
        uint64 readyZ = sbt.requestRebind(r3, sigr3);
        vm.warp(readyY);
        vm.prank(y);
        vm.expectRevert(SoulboundNetlistCredential.NotRecipient.selector);
        sbt.completeRebind(tv);
        vm.warp(readyZ);
        vm.prank(z);
        uint256 nt = sbt.completeRebind(tv);
        assertEq(sbt.ownerOf(nt), z);
        assertEq(sbt.statusOf(tv), 4);
    }

    /// 1b (M1). Renouncing the old token ends a pending request.
    function test_renounceEndsPendingRebind() public {
        uint256 pk = 0xA0;
        address auth = vm.addr(pk);
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, auth, false, 0, 10));
        address holder = address(0x1001);
        (uint256 t,) = _commitReveal(id, holder, f, 10);
        address n = address(0x1002);
        ITapCredentialProven.Rebind memory r = ITapCredentialProven.Rebind(auth, t, n, 0, bytes32(uint256(1)));
        bytes memory sigr = _signRebind(pk, r);
        vm.prank(n);
        uint64 ready = sbt.requestRebind(r, sigr);
        vm.prank(holder);
        sbt.renounce(t);
        (address pendingHolder,) = sbt.pendingRebind(t);
        assertEq(pendingHolder, address(0));
        vm.warp(ready);
        vm.prank(n);
        vm.expectRevert(SoulboundNetlistCredential.NoPendingRebind.selector);
        sbt.completeRebind(t);
    }

    /// 2 (M2). A unique round sees designs revealed in an earlier non-unique round of the same series.
    function test_uniqueSeesNonUniqueEarlierRound() public {
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 series = keccak256("s");
        bytes32 id1 = sbt.registerSpec(_spec(2, 1, tt, 4, address(0), false, series, 10));
        bytes32 id2 = sbt.registerSpec(_spec(2, 1, tt, 4, address(0), true, series, 100));
        _commitReveal(id1, address(0xA), f, 10);
        _commit(id2, address(0xB), f, 100);
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.DuplicateDesign.selector, id1));
        sbt.reveal(id2, address(0xB), 0, f, bytes32(0));
    }

    /// 3. The largest valid file (49,152 bytes, three code chunks): stored, read back, and claimed within limits.
    function test_maxFileThreeChunks() public {
        // 7016 NAND + 6 LATCH = 49,112 + 24 = 49,136 record bytes -> 49,152 bytes in all
        bytes memory recs = new bytes(7 * 7016 + 4 * 6);
        for (uint256 k; k < 7016; k++) {
            recs[7 * k + 3] = bytes1(uint8(2));
            recs[7 * k + 6] = bytes1(uint8(3));
        }
        for (uint256 k; k < 6; k++) {
            uint256 o = 7 * 7016 + 4 * k;
            recs[o] = 0x01;
            recs[o + 3] = bytes1(uint8(2));
        }
        bytes memory f = bytes.concat("TAPNET", hex"0100", bytes4(uint32(2)), bytes4(uint32(1)), recs);
        assertEq(f.length, 49152);
        uint256 g = gasleft();
        bytes32 h = sbt.storeNetlist(f);
        uint256 used = g - gasleft();
        console.log("storeNetlist 49,152 bytes (3 chunks) gas", used);
        assertEq(sbt.netlistFile(h), f);
        SoulboundNetlistCredential s2 = new SoulboundNetlistCredential("y", "y", "y/");
        g = gasleft();
        s2.claim(f, bytes32(0), bytes32(0), 0);
        used = g - gasleft();
        console.log("claim 49,152 bytes gas", used);
        // EIP-7623 calldata floor for 49,152 non-zero bytes: 10 * 4 * 49,152 + 21,000 < 2,000,000
        assertLt(used + 2_000_000, 16_777_216);
    }

    /// 4. Gas corners not covered by SoulboundGas.t.sol, with a non-zero series (the design-key SSTORE included).
    function test_extraGasCorners() public {
        uint32[6] memory nIns = [uint32(15), 11, 13, 16, 4, 1];
        for (uint256 i; i < nIns.length; i++) {
            uint32 nIn = nIns[i];
            uint32 maxG = uint32(sbt.MAX_GATE_WORK() / sbt.gateWork(nIn, 1));
            uint32 nOut = uint32(sbt.MAX_TABLE_BYTES() / sbt.tableBytes(nIn, 1));
            if (nOut > maxG) nOut = maxG;
            bytes memory f = _file(nIn, nOut, maxG);
            (, bytes32 tt) = sbt.inspect(f);
            uint64 t0 = uint64(1000 * (i + 1));
            bytes32 id = sbt.registerSpec(_spec(nIn, nOut, tt, maxG, address(0), true, keccak256(abi.encode(i)), t0));
            (, uint256 gas) = _commitReveal(id, address(uint160(0x5000 + i)), f, t0);
            console.log("nIn", nIn, "nOut", nOut);
            console.log("   gates", maxG, "reveal gas", gas);
            assertLe(gas, 12_000_000);
        }
    }

    /// 5 (MINOR-3). Attested credentials of one issuer and scope accumulate, and an expired one can be re-issued
    /// to another account, which supersedes it (§5.4, §5.6).
    function test_attestedAccumulateAndReissueExpired() public {
        uint256 pk = 0xB0;
        address issuer = vm.addr(pk);
        bytes32 art = sbt.storeNetlist(BADGE);
        address bob = address(0xB0B);
        address eve = address(0xE5E);
        vm.warp(1000);
        ITapCredentialAttested.Attestation memory a =
            ITapCredentialAttested.Attestation(issuer, bob, 0, sha256("s"), art, 0, 900, 2000, 0, 0, bytes32(uint256(1)));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, sbt.attestationDigest(a));
        vm.prank(bob);
        uint256 t1 = sbt.redeem(a, abi.encodePacked(r, s, v));
        vm.warp(3000);
        assertEq(sbt.statusOf(t1), 2);
        ITapCredentialAttested.Attestation memory b =
            ITapCredentialAttested.Attestation(issuer, eve, 0, sha256("s"), art, 0, 2900, 0, 0, t1, bytes32(uint256(2)));
        (v, r, s) = vm.sign(pk, sbt.attestationDigest(b));
        vm.prank(eve);
        uint256 t2 = sbt.redeem(b, abi.encodePacked(r, s, v));
        assertEq(sbt.statusOf(t1), 4);
        assertEq(sbt.statusOf(t2), 1);
        ITapCredentialAttested.Attestation memory c =
            ITapCredentialAttested.Attestation(issuer, eve, 0, sha256("s"), art, 0, 2900, 0, 0, 0, bytes32(uint256(3)));
        (v, r, s) = vm.sign(pk, sbt.attestationDigest(c));
        vm.prank(eve);
        sbt.redeem(c, abi.encodePacked(r, s, v));
        (uint256[] memory ids,) = sbt.credentialsOf(eve, 2, issuer, sha256("s"), true, 0, 10);
        assertEq(ids.length, 2);
    }

    /// 6 (MINOR-2). credentialsOf cursors after a renounce; the Python model now uses the same cursor.
    function test_cursorAfterRenounce() public {
        address u = address(0xCAFE);
        vm.startPrank(u);
        uint256 a = sbt.claim(BADGE, bytes32(0), 0, 0);
        uint256 b = sbt.claim(BADGE, bytes32(uint256(1)), 0, 0);
        uint256 c = sbt.claim(BADGE, bytes32(uint256(2)), 0, 0);
        sbt.renounce(a);
        vm.stopPrank();
        (uint256[] memory ids, uint256 next) = sbt.credentialsOf(u, 3, address(0), 0, false, 0, 1);
        assertEq(ids[0], b);
        assertEq(next, 2);
        (ids, next) = sbt.credentialsOf(u, 3, address(0), 0, false, next, 1);
        assertEq(ids[0], c);
        assertEq(next, 0);
    }

    /// 7. A copied reveal mints to the recipient; the recipient's own reveal then reverts.
    function test_revealCopyReverts() public {
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, address(0), false, 0, 10));
        address u = address(0x77);
        (uint256 t,) = _commitReveal(id, u, f, 10);
        assertEq(sbt.ownerOf(t), u);
        vm.prank(u);
        (bool ok,) = address(sbt).call(abi.encodeCall(sbt.reveal, (id, u, 0, f, bytes32(0))));
        assertFalse(ok);
    }

    /// 8. A contract issuer that approves every digest is accepted: the issuer decides what it signs (§5.3).
    function test_erc1271AcceptAll() public {
        AcceptAll w = new AcceptAll();
        bytes32 art = sbt.storeNetlist(BADGE);
        address bob = address(0xB0B);
        ITapCredentialAttested.Attestation memory a = ITapCredentialAttested.Attestation(
            address(w), bob, 0, sha256("s"), art, 0, 1, 0, 0, 0, bytes32(uint256(1))
        );
        vm.warp(10);
        vm.prank(bob);
        uint256 t = sbt.redeem(a, new bytes(65));
        assertEq(sbt.credentialOf(t).issuer, address(w));
    }

    /// MINOR-6: a bad subject reverts with BadSubject in reveal and claim.
    function test_badSubject() public {
        bytes memory f = _file(2, 1, 4);
        (, bytes32 tt) = sbt.inspect(f);
        bytes32 id = sbt.registerSpec(_spec(2, 1, tt, 4, address(0), false, 0, 10));
        vm.warp(20);
        vm.expectRevert(SoulboundNetlistCredential.BadSubject.selector);
        sbt.reveal(id, address(0x77), 2, f, bytes32(0));
        vm.expectRevert(SoulboundNetlistCredential.BadSubject.selector);
        sbt.claim(BADGE, bytes32(0), bytes32(0), 2);
    }

    /// MINOR-1: status changes emit CredentialStatusChanged only; no ERC-4906 MetadataUpdate.
    function test_noMetadataUpdate() public {
        uint256 pk = 0xB0;
        address issuer = vm.addr(pk);
        bytes32 art = sbt.storeNetlist(BADGE);
        address bob = address(0xB0B);
        vm.warp(1000);
        ITapCredentialAttested.Attestation memory a =
            ITapCredentialAttested.Attestation(issuer, bob, 0, sha256("s"), art, 0, 900, 0, 0, 0, bytes32(uint256(1)));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(pk, sbt.attestationDigest(a));
        vm.prank(bob);
        sbt.redeem(a, abi.encodePacked(r, s, v));
        vm.recordLogs();
        vm.prank(issuer);
        sbt.revokeAttestation(a);
        bytes32 metadataUpdate = keccak256("MetadataUpdate(uint256)");
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; i++) {
            assertTrue(logs[i].topics[0] != metadataUpdate);
        }
        assertFalse(sbt.supportsInterface(0x49064906));
    }
}

contract AcceptAll {
    function isValidSignature(bytes32, bytes calldata) external pure returns (bytes4) {
        return 0x1626ba7e;
    }
}
