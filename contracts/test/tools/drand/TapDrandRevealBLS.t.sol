// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {DrandKitBase} from "./DrandKitBase.sol";
import {MockBeacon} from "./mocks/MockBeacon.sol";
import {TapNetlistNFT} from "../../../src/core/TapNetlistNFT.sol";
import {DrandBeacon} from "../../../src/tools/drand/DrandBeacon.sol";
import {TapDrandReveal} from "../../../src/tools/drand/TapDrandReveal.sol";
import {TapDrandRevealFactory} from "../../../src/tools/drand/TapDrandRevealFactory.sol";
import {ITapDrandReveal} from "../../../src/tools/drand/ITapDrandReveal.sol";

/// The kit with the real DrandBeacon and real quicknet rounds (test/fixtures/drand-quicknet-rounds.json): the BLS
/// signature of the self-test round and of R are checked by the EIP-2537 precompiles. Every test skips itself on an EVM
/// without them; run with `forge test --hardfork prague --match-path "test/tools/drand/*"`.
contract TapDrandRevealBLSTest is DrandKitBase {
    TapDrandRevealFactory internal factory;
    TapDrandReveal internal ctrl;
    TapNetlistNFT internal coll;
    DrandBeacon internal beacon = DrandBeacon(BEACON);

    uint64 internal constant S = BASE;
    uint64 internal constant R_MIN = BASE + 15_604; // the smallest fixed-mode R for a commit 10 s after round S
    uint256 internal constant SUPPLY = 10;
    bytes32 internal constant MANIFEST = keccak256("manifest");
    uint256 internal T0;

    function setUp() public {
        _loadRounds();
        T0 = qt(S) + 10;
        vm.warp(T0);
        _installRealBeacon();
        factory = new TapDrandRevealFactory();
        (ctrl, coll) = _create(factory, admin, 1 hours);
        vm.prank(admin);
        ctrl.allowMinter(sale, true);
    }

    function _commit(uint64 round) internal {
        bytes memory sig = sigOf[S];
        vm.prank(admin);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), round, S, sig);
    }

    function _mint(uint256 id) internal {
        vm.prank(sale);
        ctrl.mint(alice, id);
    }

    // ------------------------------------------------------------------ fixed mode, end to end

    function test_fixedMode_endToEnd() public needsBls {
        uint256 g = gasleft();
        _commit(R_MIN);
        emit log_named_uint("commit, fixed mode, real self-test (gas)", g - gasleft());
        assertEq(ctrl.lagAtCommit(), 0);
        assertEq(ctrl.selfTestRound(), S);
        assertEq(ctrl.selfTestSig(), sigOf[S]);
        assertEq(ctrl.revealRound(), R_MIN);
        assertTrue(ctrl.verifierWorks{gas: 3_000_000}());

        _mint(1);
        _mint(2);
        vm.warp(qt(R_MIN) - 601);
        _mint(3);
        vm.warp(qt(R_MIN) - 600);
        assertFalse(ctrl.mintOpen(), "the gateway closes 600 s before R");
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 4);

        vm.warp(qt(R_MIN));
        bytes memory sigR = sigOf[R_MIN];
        g = gasleft();
        vm.prank(eve);
        ctrl.revealDrand{gas: 3_000_000}(sigR);
        emit log_named_uint("revealDrand, R not yet in the beacon (gas)", g - gasleft());

        assertEq(coll.masterSeed(), randOf[R_MIN], "the seed is the randomness both relays published for R");
        assertEq(coll.masterSeed(), sha256(sigR));
        assertEq(beacon.randomnessOf(R_MIN), randOf[R_MIN]);
        assertEq(beacon.latestVerifiedRound(), R_MIN);
        assertTrue(ctrl.verifiedOnChain());
        assertEq(coll.entryIndexOf(1, 0) < SUPPLY, true);

        vm.prank(admin);
        ctrl.freeze();
        assertEq(coll.owner(), address(0));
    }

    function test_fixedMode_revealWhenRIsAlreadyCached() public needsBls {
        _commit(R_MIN);
        beacon.verify{gas: 3_000_000}(R_MIN, sigOf[R_MIN]); // anybody posts the round first
        uint256 g = gasleft();
        ctrl.revealDrand(sigOf[R_MIN]);
        emit log_named_uint("revealDrand, R already cached (gas)", g - gasleft());
        assertEq(coll.masterSeed(), randOf[R_MIN]);
    }

    function test_fixedMode_theMinimumRoundIsExact() public needsBls {
        bytes memory sig = sigOf[S];
        vm.startPrank(admin);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), R_MIN - 1, S, sig);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), R_MIN, S, sig);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------ wrong rounds and signatures

    function test_reveal_onlyRsOwnSignatureWritesTheSeed() public needsBls {
        _commit(R_MIN);
        bytes memory err = abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, R_MIN);
        bytes[] memory bad = new bytes[](7);
        bad[0] = sigOf[R_MIN + 1]; // a real signature, of the next round
        bad[1] = sigOf[S]; // a real signature, of the self-test round
        bad[2] = _flip(sigOf[R_MIN]); // R's signature with the sort flag flipped (the negated point)
        bad[3] = "";
        bad[4] = new bytes(47);
        bad[5] = new bytes(48);
        bad[6] = bytes.concat(sigOf[R_MIN], hex"00");
        for (uint256 i; i < bad.length; ++i) {
            vm.expectRevert(err);
            ctrl.revealDrand{gas: 3_000_000}(bad[i]);
        }
        assertEq(coll.masterSeed(), 0);
        assertFalse(ctrl.verifiedOnChain());
        assertEq(beacon.randomnessOf(R_MIN), 0);
        ctrl.revealDrand{gas: 3_000_000}(sigOf[R_MIN]);
        assertEq(coll.masterSeed(), randOf[R_MIN]);
    }

    function test_commit_selfTestRejectsWrongRealSignatures() public needsBls {
        vm.startPrank(admin);
        // the signature of another round
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), 0, S, sigOf[S + 1]);
        // the right signature with the sort flag flipped
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), 0, S, _flip(sigOf[S]));
        // a round the signature is not for
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), 0, S + 1, sigOf[S]);
        // garbage
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), 0, S, new bytes(48));
        // the right one
        ctrl.commit{gas: 3_000_000}(MANIFEST, 1, SUPPLY, _pools(), 0, S, sigOf[S]);
        vm.stopPrank();
        assertEq(ctrl.committedAt(), T0);
    }

    // ------------------------------------------------------------------ deferred mode, end to end

    function test_deferredMode_endToEnd() public needsBls {
        _commit(0);
        assertEq(ctrl.revealRound(), 0);
        _mint(1);
        _mint(2);
        vm.prank(admin);
        ctrl.closeMint();

        uint64 target = BASE + 20_000; // pick the block time so that the round scheduleReveal fixes is a recorded one
        uint256 t = qt(target - 1) - 1 hours;
        vm.warp(t);
        assertEq(ctrl.scheduleRound(), target);
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), target);
        assertGt(qt(target), t + 1 hours);

        vm.warp(qt(target));
        vm.prank(alice);
        ctrl.revealDrand{gas: 3_000_000}(sigOf[target]);
        assertEq(coll.masterSeed(), randOf[target]);
        assertEq(ctrl.revealedAt(), qt(target));
        vm.prank(admin);
        ctrl.freeze();
        assertTrue(coll.frozen());
    }

    // ------------------------------------------------------------------ clock and lag with real rounds

    function test_lag_aSelfTestRoundAheadOfTheBlockIsRecorded() public needsBls {
        vm.warp(qt(S) - 1800);
        _commit(0);
        assertEq(ctrl.lagAtCommit(), 1800);
        assertEq(ctrl.clock(), qt(S));
    }

    function test_clock_aPostedRealRoundMovesIt() public needsBls {
        _commit(R_MIN);
        assertEq(ctrl.clock(), T0);
        beacon.verify{gas: 3_000_000}(S + 7, sigOf[S + 7]);
        assertEq(ctrl.clock(), qt(S + 7));
        assertGt(qt(S + 7), T0);
    }

    // ------------------------------------------------------------------ emergency path against the real verifier

    function test_emergency_isClosedWhileTheRealVerifierWorks() public needsBls {
        _commit(R_MIN);
        vm.warp(qt(R_MIN) + 72 hours);
        assertTrue(ctrl.verifierWorks{gas: 3_000_000}());
        // even with R's real bytes at hand, and the whole 72 h gone
        bytes memory sigR = sigOf[R_MIN];
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.VerifierWorks.selector);
        ctrl.revealUnverified{gas: 3_000_000}(sigR);
        // and the admin cannot slip in a seed of its choosing: any 48 bytes with a valid flag byte are refused too
        bytes memory chosen = bytes.concat(hex"80", keccak256("chosen"), bytes15(0));
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.VerifierWorks.selector);
        ctrl.revealUnverified{gas: 3_000_000}(chosen);
        assertEq(coll.masterSeed(), 0);
        // revealDrand is the way
        ctrl.revealDrand{gas: 3_000_000}(sigR);
        assertEq(coll.masterSeed(), randOf[R_MIN]);
    }

    /// Commit with the real beacon, then the chain loses the precompiles (a verifier that fails): the path opens.
    function test_emergency_opensWhenTheVerifierStopsWorking() public needsBls {
        _commit(R_MIN);
        _installMockBeacon();
        MockBeacon(BEACON).setMode(MockBeacon.Mode.Broken);
        vm.warp(qt(R_MIN) + 72 hours);
        assertFalse(ctrl.verifierWorks{gas: 3_000_000}());
        bytes memory sigR = sigOf[R_MIN];
        vm.prank(admin);
        ctrl.revealUnverified{gas: 3_000_000}(sigR);
        assertEq(coll.masterSeed(), randOf[R_MIN], "with R's real bytes the seed is R's randomness");
        assertFalse(ctrl.verifiedOnChain());
    }
}
