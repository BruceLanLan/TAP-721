// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Vm} from "forge-std/Vm.sol";
import {DrandKitBase} from "./DrandKitBase.sol";
import {MockBeacon} from "./mocks/MockBeacon.sol";
import {CraftedCollection} from "./mocks/CraftedCollection.sol";
import {ITapNetlistNFT} from "../../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistNFT} from "../../../src/core/TapNetlistNFT.sol";
import {TapNetlistCore} from "../../../src/core/TapNetlistCore.sol";
import {Owned} from "../../../src/vendor/Owned.sol";
import {TapDrandReveal} from "../../../src/tools/drand/TapDrandReveal.sol";
import {TapDrandRevealFactory} from "../../../src/tools/drand/TapDrandRevealFactory.sol";
import {ITapDrandReveal} from "../../../src/tools/drand/ITapDrandReveal.sol";

/// The reveal controller and its factory, on a MockBeacon at the canonical beacon address, so that every test runs on
/// the default EVM (shanghai) with no EIP-2537 precompiles. The controller logic never looks inside a signature: it
/// asks the beacon. The same flows with real quicknet signatures are in TapDrandRevealBLS.t.sol.
contract TapDrandRevealTest is DrandKitBase {
    TapDrandRevealFactory internal factory;
    TapDrandReveal internal ctrl;
    TapNetlistNFT internal coll;
    MockBeacon internal mock;

    uint64 internal constant S = BASE; // the self-test round
    uint256 internal constant SUPPLY = 10;
    bytes32 internal constant MANIFEST = keccak256("manifest");
    uint256 internal T0; // block time of the commit: 10 s after round S

    function setUp() public {
        T0 = qt(S) + 10;
        vm.warp(T0);
        _fresh(1 hours);
    }

    /// A new controller (real beacon code is present while the constructor pins it, then the mock takes its place).
    function _fresh(uint256 delay) internal {
        _installRealBeacon();
        factory = new TapDrandRevealFactory();
        (ctrl, coll) = _create(factory, admin, delay);
        _installMockBeacon();
        mock = MockBeacon(BEACON);
        vm.prank(admin);
        ctrl.allowMinter(sale, true);
    }

    /// The synthetic signature MockBeacon.sigFor makes, computed locally so that no external call sits between a
    /// cheatcode (prank, expectRevert) and the call it is meant for.
    function _sig(uint64 round) internal pure returns (bytes memory) {
        bytes31 a = bytes31(keccak256(abi.encode(round)));
        bytes16 b = bytes16(keccak256(abi.encode(round, uint8(1))));
        return bytes.concat(hex"80", a, b);
    }

    function _commit(uint64 round) internal {
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        vm.prank(admin);
        ctrl.commit(MANIFEST, 1, SUPPLY, _pools(), round, S, sig);
    }

    function _minFixed() internal view returns (uint64) {
        return roundAt(ctrl.clock() + MIN_LEAD) + 1;
    }

    function _mint(uint256 id) internal {
        vm.prank(sale);
        ctrl.mint(alice, id);
    }

    function _deferredClosed() internal {
        _commit(0);
        _mint(1);
        vm.prank(admin);
        ctrl.closeMint();
    }

    // ================================================================== factory and construction

    function test_create_state() public view {
        assertEq(coll.owner(), address(ctrl), "the controller is the collection's only owner");
        assertEq(address(ctrl.collection()), address(coll));
        assertEq(address(coll), vm.computeCreateAddress(address(ctrl), 1));
        assertEq(factory.controllerOf(address(coll)), address(ctrl));
        assertEq(ctrl.admin(), admin);
        assertEq(ctrl.scheduleDelay(), 1 hours);
        assertEq(ctrl.collectionInitCodeHash(), keccak256(_refInitCode()));
        assertEq(coll.name(), "Kit");
        assertEq(coll.baseURI(), "https://example.invalid/meta/");
        assertFalse(coll.isMinter(address(ctrl)), "the reference collection has no minter");
        assertFalse(coll.isMinter(admin));
        assertEq(ctrl.committedAt(), 0);
        assertEq(address(ctrl.DRAND_BEACON()), BEACON);
        assertFalse(ctrl.mintOpen());
        assertEq(ctrl.manifestHash(), 0);
    }

    function test_create_emitsCreated() public {
        _installRealBeacon();
        bytes memory init = _refInitCode();
        vm.recordLogs();
        (address c, address n) = factory.create(alice, 2 hours, init, "A", "B", "u/");
        Vm.Log[] memory logs = vm.getRecordedLogs();
        bool seen;
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter == address(factory) && logs[i].topics[0] == TapDrandRevealFactory.Created.selector) {
                seen = true;
                assertEq(address(uint160(uint256(logs[i].topics[1]))), c);
                assertEq(address(uint160(uint256(logs[i].topics[2]))), n);
                assertEq(address(uint160(uint256(logs[i].topics[3]))), alice);
                assertEq(abi.decode(logs[i].data, (bytes32)), keccak256(init));
            }
        }
        assertTrue(seen);
    }

    function test_create_scheduleDelayBounds() public {
        _installRealBeacon();
        bytes memory init = _refInitCode();
        vm.expectRevert(ITapDrandReveal.BadDelay.selector);
        factory.create(admin, 0, init, "A", "B", "");
        vm.expectRevert(ITapDrandReveal.BadDelay.selector);
        factory.create(admin, 1 hours - 1, init, "A", "B", "");
        vm.expectRevert(ITapDrandReveal.BadDelay.selector);
        factory.create(admin, 7 days + 1, init, "A", "B", "");
        (address c,) = factory.create(admin, 1 hours, init, "A", "B", "");
        assertEq(TapDrandReveal(c).scheduleDelay(), 1 hours);
        (c,) = factory.create(admin, 7 days, init, "A", "B", "");
        assertEq(TapDrandReveal(c).scheduleDelay(), 7 days);
    }

    function test_create_rejectsZeroAdmin() public {
        _installRealBeacon();
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        factory.create(address(0), 1 hours, _refInitCode(), "A", "B", "");
    }

    function test_create_requiresThePinnedBeacon() public {
        bytes memory init = _refInitCode();
        vm.etch(BEACON, "");
        vm.expectRevert(ITapDrandReveal.BadBeacon.selector);
        factory.create(admin, 1 hours, init, "A", "B", "");
        _installMockBeacon(); // some other code at the address
        vm.expectRevert(ITapDrandReveal.BadBeacon.selector);
        factory.create(admin, 1 hours, init, "A", "B", "");
    }

    function test_create_rejectsInitcodeThatIsNotOwnedByTheController() public {
        _installRealBeacon();
        vm.expectRevert(ITapDrandReveal.BadCollection.selector);
        factory.create(admin, 1 hours, hex"60006000fd", "A", "B", ""); // reverts
        vm.expectRevert(ITapDrandReveal.BadCollection.selector);
        factory.create(admin, 1 hours, hex"00", "A", "B", ""); // empty contract: owner() answers nothing
    }

    /// The residual the docs state: the chain cannot tell a crafted collection from the reference one, so the kit's
    /// claims need the off-chain comparison of collectionInitCodeHash.
    function test_craftedInitcodeIsAcceptedOnChainButItsHashDiffers() public {
        _installRealBeacon();
        (address c, address n) = factory.create(admin, 1 hours, type(CraftedCollection).creationCode, "A", "B", "");
        assertEq(CraftedCollection(n).owner(), c);
        assertEq(factory.controllerOf(n), c, "recorded exactly like an honest one");
        bytes32 refHash = keccak256(_refInitCode());
        assertTrue(TapDrandReveal(c).collectionInitCodeHash() != refHash, "initcode hash differs from the reference");
        assertEq(TapDrandReveal(c).collectionInitCodeHash(), keccak256(type(CraftedCollection).creationCode));
    }

    // ================================================================== unreachable owner powers

    function test_controllerHasNoCodePathToTheOtherOwnerFunctions() public {
        string[5] memory sigs = [
            "setMinter(address,bool)",
            "transferOwnership(address)",
            "commitManifestNoReveal(bytes32,uint256,uint256,(string,uint8,bytes32)[])",
            "commitManifestTokenSet(bytes32,bytes32,uint256,(string,uint8,bytes32)[],bool)",
            "scheduleBlockhashReveal(uint256)"
        ];
        bytes memory code = vm.getDeployedCode("TapDrandReveal.sol:TapDrandReveal");
        for (uint256 i; i < sigs.length; ++i) {
            bytes4 sel = bytes4(keccak256(bytes(sigs[i])));
            // not a callable selector of the controller ...
            vm.prank(admin);
            (bool ok,) = address(ctrl).call(abi.encodePacked(sel, new bytes(256)));
            assertFalse(ok, sigs[i]);
            // ... and not even a constant in its code
            assertFalse(_contains(code, abi.encodePacked(sel)), sigs[i]);
        }
        assertEq(_forbiddenOpcodes(code), 0);
        // `reveal(bytes32)` is the one owner function it does call, but only from revealDrand / revealUnverified: the
        // controller itself answers no such selector
        vm.prank(admin);
        (bool ok2,) = address(ctrl).call(abi.encodeWithSignature("reveal(bytes32)", keccak256("seed")));
        assertFalse(ok2, "reveal(bytes32) on the controller");
    }

    function _contains(bytes memory hay, bytes memory needle) internal pure returns (bool) {
        for (uint256 i; i + needle.length <= hay.length; ++i) {
            uint256 j;
            while (j < needle.length && hay[i + j] == needle[j]) ++j;
            if (j == needle.length) return true;
        }
        return false;
    }

    function test_nobodyButTheControllerCanCallTheCollection() public {
        _commit(_minFixed());
        address[3] memory who = [admin, sale, eve];
        for (uint256 i; i < who.length; ++i) {
            vm.startPrank(who[i]);
            bytes memory unauthorized = abi.encodeWithSelector(Owned.Unauthorized.selector, who[i]);
            vm.expectRevert(unauthorized);
            coll.setMinter(who[i], true);
            vm.expectRevert(unauthorized);
            coll.transferOwnership(who[i]);
            vm.expectRevert(unauthorized);
            coll.reveal(keccak256("my seed"));
            vm.expectRevert(unauthorized);
            coll.scheduleBlockhashReveal(block.number + 5);
            vm.expectRevert(unauthorized);
            coll.setBaseURI("https://evil.invalid/");
            vm.expectRevert(unauthorized);
            coll.freeze();
            vm.expectRevert(unauthorized);
            coll.mint(who[i], 5);
            vm.expectRevert(unauthorized);
            coll.commitManifestNoReveal(MANIFEST, 1, SUPPLY, _pools());
            vm.stopPrank();
        }
    }

    /// revealFromBlockhash is permissionless in the reference, but needs a block scheduled by the owner; the
    /// controller cannot schedule one, so it reverts for every block number.
    function test_revealFromBlockhashIsUnreachable() public {
        _commit(_minFixed());
        vm.roll(1000);
        uint256[4] memory blocks = [uint256(0), 1, block.number - 1, block.number];
        for (uint256 i; i < blocks.length; ++i) {
            vm.prank(eve);
            vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, blocks[i]));
            coll.revealFromBlockhash(blocks[i]);
        }
        assertEq(coll.revealBlock(), 0);
        assertEq(coll.masterSeed(), 0);
    }

    // ================================================================== commit

    function test_commit_onlyAdminOnce() public {
        mock.register(S, _sig(S));
        bytes memory sig = _sig(S);
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, sig);
        vm.prank(admin);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, sig);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.AlreadyCommitted.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, sig);
    }

    function test_commit_recordsTheEvidenceAndForwardsTheManifest() public {
        uint64 r = _minFixed();
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.RevealScheduled(r, qt(r), S);
        vm.expectEmit(true, false, false, true, address(ctrl));
        emit ITapDrandReveal.Committed(MANIFEST, r, S);
        vm.prank(admin);
        ctrl.commit(MANIFEST, 1, SUPPLY, _pools(), r, S, sig);
        assertEq(ctrl.committedAt(), T0);
        assertEq(ctrl.supply(), SUPPLY);
        assertEq(ctrl.revealRound(), r);
        assertTrue(ctrl.fixedRound());
        assertEq(ctrl.scheduledAt(), T0);
        assertEq(ctrl.selfTestRound(), S);
        assertEq(ctrl.selfTestSig(), sig);
        assertEq(ctrl.lagAtCommit(), 0, "the self-test round is behind the block");
        assertEq(ctrl.newestRoundAtSchedule(), S);
        assertEq(coll.manifestHash(), MANIFEST);
        assertEq(ctrl.manifestHash(), MANIFEST);
        (uint256 first, uint256 supply_) = coll.tokenRange();
        assertEq(first, 1);
        assertEq(supply_, SUPPLY);
        assertEq(coll.pools().length, 2);
    }

    function test_commit_selfTestRejectsABadVerifier() public {
        bytes memory good = _sig(S);
        ITapNetlistNFT.Pool[] memory ps = _pools();
        // unknown signature
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, good);
        mock.register(S, good);
        // a verifier that also accepts the sort-flipped copy (two randomness values per round)
        mock.setMode(MockBeacon.Mode.Lax);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, good);
        // a verifier whose randomness is not SHA-256(signature)
        mock.setMode(MockBeacon.Mode.WrongRandomness);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, good);
        // a verifier without the precompiles
        mock.setMode(MockBeacon.Mode.Broken);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, good);
        mock.setMode(MockBeacon.Mode.Normal);
        vm.prank(admin);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, good);
    }

    function test_commit_selfTestRoundMustBeFresh() public {
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.warp(qt(S) + 1 days + 1);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.SelfTestFailed.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, sig);
        vm.warp(qt(S) + 1 days);
        vm.prank(admin);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 0, S, sig);
    }

    function test_commit_fixedRoundWindow() public {
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        ITapNetlistNFT.Pool[] memory ps = _pools();
        uint64 min = _minFixed();
        assertEq(min, S + 15_604, "the smallest round for a commit 10 s after round S");
        vm.startPrank(admin);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, min - 1, S, sig);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, S, S, sig);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, 1, S, sig);
        uint64 max = roundAt(T0 + 365 days);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, max + 1, S, sig);
        ctrl.commit(MANIFEST, 1, SUPPLY, ps, max, S, sig);
        vm.stopPrank();
        assertEq(ctrl.revealRound(), max);
    }

    function test_commit_fixedMinimumIsAccepted() public {
        _commit(_minFixed());
        assertEq(ctrl.revealRound(), S + 15_604);
        assertTrue(ctrl.mintOpen());
    }

    function testFuzz_fixedCommitAcceptsExactlyTheWindow(uint64 r) public {
        r = uint64(bound(r, S, S + 40_000_000));
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        bool expected = r > roundAt(T0 + MIN_LEAD) && qt(r) <= T0 + 365 days;
        vm.prank(admin);
        (bool ok,) = address(ctrl).call(abi.encodeCall(ctrl.commit, (MANIFEST, 1, SUPPLY, _pools(), r, S, sig)));
        assertEq(ok, expected);
    }

    // ================================================================== the mint gateway

    function test_mint_onlyAllowedMinters() public {
        _commit(_minFixed());
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.mint(eve, 1);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.mint(admin, 1); // the admin has no mint right of its own
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.allowMinter(eve, true);
        vm.expectEmit(true, false, false, true, address(ctrl));
        emit ITapDrandReveal.MinterAllowed(eve, true);
        vm.prank(admin);
        ctrl.allowMinter(eve, true);
        vm.prank(eve);
        ctrl.mint(eve, 1);
        assertEq(coll.ownerOf(1), eve);
        vm.prank(admin);
        ctrl.allowMinter(eve, false);
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.mint(eve, 2);
    }

    function test_mint_notBeforeTheCommit() public {
        assertFalse(ctrl.mintOpen());
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 1);
    }

    function test_mint_countsAndRecords() public {
        _commit(_minFixed());
        vm.warp(T0 + 100);
        _mint(1);
        _mint(2);
        assertEq(ctrl.minted(), 2);
        assertEq(ctrl.lastMintAt(), T0 + 100);
        assertEq(coll.ownerOf(2), alice);
    }

    function test_mint_failedMintsDoNotCount() public {
        _commit(_minFixed());
        _mint(1);
        vm.prank(sale);
        vm.expectRevert(); // duplicate id
        ctrl.mint(alice, 1);
        vm.prank(sale);
        vm.expectRevert(); // outside the committed range 1..10
        ctrl.mint(alice, 11);
        vm.prank(sale);
        vm.expectRevert();
        ctrl.mint(alice, 0);
        assertEq(ctrl.minted(), 1);
    }

    function test_mint_selloutClosesTheGateway() public {
        _commit(0);
        for (uint256 i = 1; i < SUPPLY; ++i) _mint(i);
        assertTrue(ctrl.mintOpen());
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.MintClosed(uint64(SUPPLY), address(0));
        _mint(SUPPLY);
        assertEq(ctrl.closedAt(), T0);
        assertFalse(ctrl.mintOpen());
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 1);
    }

    function test_fixed_gatewayClosesBeforeR() public {
        uint64 r = _minFixed();
        _commit(r);
        vm.warp(qt(r) - 601);
        assertTrue(ctrl.mintOpen());
        _mint(1);
        vm.warp(qt(r) - 600);
        assertFalse(ctrl.mintOpen());
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
        vm.warp(qt(r) + 1 days);
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
        assertEq(ctrl.earliestRound(), roundAt(qt(r) + 1 days + 600) + 1);
    }

    function testFuzz_fixed_gatewayBoundary(uint256 dt) public {
        uint64 r = _minFixed();
        _commit(r);
        uint256 t = qt(r) - 3000 + bound(dt, 0, 6000);
        vm.warp(t);
        bool expected = t + REVEAL_DELAY < qt(r);
        assertEq(ctrl.mintOpen(), expected);
        vm.prank(sale);
        (bool ok,) = address(ctrl).call(abi.encodeCall(ctrl.mint, (alice, 1)));
        assertEq(ok, expected);
    }

    /// Anyone can post a round to the beacon; the controller's clock then moves forward even if the chain's does not.
    function test_fixed_aPostedRoundClosesTheGatewayEarly() public {
        uint64 r = _minFixed();
        _commit(r);
        assertTrue(ctrl.mintOpen());
        mock.post(r - 10);
        assertEq(ctrl.clock(), qt(r - 10));
        assertFalse(ctrl.mintOpen(), "R is only 30 s after the newest posted round");
    }

    function test_fixed_aPostedRoundBehindTheChainChangesNothing() public {
        _commit(_minFixed());
        mock.post(S + 1);
        assertEq(ctrl.clock(), T0);
        assertTrue(ctrl.mintOpen());
    }

    function test_closeMint() public {
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.NotCommitted.selector);
        ctrl.closeMint();
        _commit(0);
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.closeMint();
        _mint(1);
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.MintClosed(1, sale);
        vm.prank(sale); // a minter (the sale) can close
        ctrl.closeMint();
        assertEq(ctrl.closedAt(), T0);
        assertFalse(ctrl.mintOpen());
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.closeMint();
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
    }

    // ================================================================== deferred mode

    function test_deferred_roundIsFixedAfterTheClose() public {
        _commit(0);
        assertFalse(ctrl.fixedRound());
        assertEq(ctrl.revealRound(), 0);
        vm.warp(T0 + 30 days);
        assertTrue(ctrl.mintOpen(), "no clock closes a deferred sale");
        _mint(1);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.MintingOpen.selector);
        ctrl.scheduleReveal();
        vm.prank(admin);
        ctrl.closeMint();
        uint256 t = T0 + 31 days;
        vm.warp(t);
        uint64 expected = roundAt(t + 1 hours) + 1;
        assertEq(ctrl.scheduleRound(), expected);
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.RevealScheduled(expected, qt(expected), 0);
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), expected);
        assertEq(ctrl.scheduledAt(), t);
        assertGt(qt(expected), t + 1 hours - 1);
        assertLe(qt(expected), t + 1 hours + 3);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.AlreadyScheduled.selector);
        ctrl.scheduleReveal();
    }

    function test_deferred_scheduleBeforeCommit() public {
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.NotCommitted.selector);
        ctrl.scheduleReveal();
    }

    function test_deferred_publicSchedulingAfterADay() public {
        _deferredClosed();
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.scheduleReveal();
        vm.warp(T0 + 1 days - 1);
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.scheduleReveal();
        vm.warp(T0 + 1 days);
        vm.prank(eve);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), roundAt(T0 + 1 days + 1 hours) + 1);
    }

    function test_deferred_selloutCanBeScheduledWithoutAnyAdminCall() public {
        _commit(0);
        for (uint256 i = 1; i <= SUPPLY; ++i) _mint(i);
        vm.warp(T0 + 1 days);
        vm.prank(eve);
        ctrl.scheduleReveal();
        assertGt(ctrl.revealRound(), 0);
    }

    function test_deferred_scheduleDelayMovesR() public {
        _fresh(7 days);
        _deferredClosed();
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), roundAt(T0 + 7 days) + 1);
    }

    function test_deferred_postedRoundMovesTheClockThenR() public {
        _deferredClosed();
        uint64 posted = S + 20_000;
        mock.post(posted);
        vm.warp(T0 + 1 hours);
        assertEq(ctrl.clock(), qt(posted));
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), roundAt(qt(posted) + 1 hours) + 1);
        assertEq(ctrl.newestRoundAtSchedule(), posted);
    }

    function test_deferred_mintsStopAtTheCloseAndAfterTheSchedule() public {
        _deferredClosed();
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
        vm.prank(admin);
        ctrl.scheduleReveal();
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
    }

    // ================================================================== reveal and freeze

    function _fixedReady() internal returns (uint64 r, bytes memory sigR) {
        r = _minFixed();
        _commit(r);
        _mint(1);
        sigR = _sig(r);
        mock.register(r, sigR);
    }

    function test_reveal_beforeRIsFixed() public {
        _commit(0);
        vm.expectRevert(ITapDrandReveal.NotScheduled.selector);
        ctrl.revealDrand(hex"80");
    }

    function test_reveal_isPermissionlessAndWritesOnlyTheBeaconsRandomness() public {
        (uint64 r, bytes memory sigR) = _fixedReady();
        vm.warp(qt(r));
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.RevealedVerified(r, sha256(sigR), eve);
        vm.prank(eve);
        ctrl.revealDrand(sigR);
        assertEq(coll.masterSeed(), sha256(sigR));
        assertEq(mock.randomnessOf(r), sha256(sigR));
        assertTrue(ctrl.verifiedOnChain());
        assertEq(ctrl.revealedAt(), qt(r));
        vm.prank(alice);
        vm.expectRevert(ITapDrandReveal.AlreadyRevealed.selector);
        ctrl.revealDrand(sigR);
        // minting ended with the reveal
        assertFalse(ctrl.mintOpen());
        vm.prank(sale);
        vm.expectRevert(ITapDrandReveal.MintingClosed.selector);
        ctrl.mint(alice, 2);
    }

    function test_reveal_wrongRoundOrSignatureReverts() public {
        (uint64 r, bytes memory sigR) = _fixedReady();
        vm.warp(qt(r));
        bytes memory other = _sig(r + 1);
        mock.register(r + 1, other); // a real signature, but of the next round
        bytes memory err = abi.encodeWithSelector(MockBeacon.InvalidSignature.selector, r);
        vm.expectRevert(err);
        ctrl.revealDrand(other);
        vm.expectRevert(err);
        ctrl.revealDrand(_flip(sigR)); // the sort-flipped copy
        vm.expectRevert(err);
        ctrl.revealDrand(hex"");
        vm.expectRevert(err);
        ctrl.revealDrand(_sig(S)); // the self-test round's signature
        assertEq(coll.masterSeed(), 0);
        assertFalse(ctrl.verifiedOnChain());
        ctrl.revealDrand(sigR);
        assertEq(coll.masterSeed(), sha256(sigR));
    }

    function test_reveal_cachedRoundStillNeedsItsExactSignature() public {
        (uint64 r, bytes memory sigR) = _fixedReady();
        mock.post(r); // somebody posted R's round to the beacon (synthetic signature, registered)
        vm.warp(qt(r));
        vm.expectRevert(abi.encodeWithSelector(MockBeacon.InvalidSignature.selector, r));
        ctrl.revealDrand(_flip(sigR));
        ctrl.revealDrand(sigR);
        assertEq(coll.masterSeed(), sha256(sigR));
    }

    function test_freezeAndBaseURI() public {
        (uint64 r, bytes memory sigR) = _fixedReady();
        vm.prank(admin);
        ctrl.setBaseURI("https://a.invalid/");
        assertEq(coll.baseURI(), "https://a.invalid/");
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.setBaseURI("https://evil.invalid/");
        vm.prank(admin);
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        ctrl.freeze();
        vm.warp(qt(r));
        ctrl.revealDrand(sigR);
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.freeze();
        vm.prank(admin);
        ctrl.setBaseURI("https://final.invalid/");
        vm.prank(admin);
        ctrl.freeze();
        assertTrue(coll.frozen());
        assertEq(coll.owner(), address(0), "every power the controller forwarded has ended");
        vm.prank(admin);
        vm.expectRevert();
        ctrl.setBaseURI("https://late.invalid/");
        assertEq(coll.tokenURI(1), "https://final.invalid/1");
    }

    // ================================================================== emergency path

    function _emergencyReady() internal returns (uint64 r, uint256 open) {
        r = _minFixed();
        _commit(r);
        open = qt(r) + 72 hours;
    }

    function test_emergency_onlyWhileTheVerifierFailsItsSelfTest() public {
        (uint64 r, uint256 open) = _emergencyReady();
        bytes memory sig = _sig(r);
        vm.startPrank(admin);
        vm.warp(open);
        assertTrue(ctrl.verifierWorks());
        vm.expectRevert(ITapDrandReveal.VerifierWorks.selector);
        ctrl.revealUnverified(sig);
        vm.stopPrank();
        // every way a verifier can fail opens the path
        MockBeacon.Mode[4] memory modes =
            [
                MockBeacon.Mode.Broken,
                MockBeacon.Mode.Reverting,
                MockBeacon.Mode.ShortReturn,
                MockBeacon.Mode.WrongRandomness
            ];
        for (uint256 i; i < modes.length; ++i) {
            uint256 snap = vm.snapshotState();
            mock.setMode(modes[i]);
            assertFalse(ctrl.verifierWorks());
            vm.prank(admin);
            ctrl.revealUnverified(sig);
            assertEq(coll.masterSeed(), sha256(sig));
            assertTrue(vm.revertToState(snap));
        }
    }

    function test_emergency_result() public {
        (uint64 r, uint256 open) = _emergencyReady();
        mock.setMode(MockBeacon.Mode.Broken);
        bytes memory sig = _sig(r);
        vm.warp(open);
        vm.expectEmit(false, false, false, true, address(ctrl));
        emit ITapDrandReveal.RevealedUnverified(r, sig, sha256(sig));
        vm.prank(admin);
        ctrl.revealUnverified(sig);
        assertEq(coll.masterSeed(), sha256(sig));
        assertFalse(ctrl.verifiedOnChain());
        assertEq(ctrl.revealedAt(), open);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.AlreadyRevealed.selector);
        ctrl.revealUnverified(sig);
        vm.expectRevert(ITapDrandReveal.AlreadyRevealed.selector);
        ctrl.revealDrand(sig);
    }

    function test_emergency_preconditions() public {
        bytes memory sig = _sig(S + 99_999);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.NotScheduled.selector);
        ctrl.revealUnverified(sig);

        (uint64 r, uint256 open) = _emergencyReady();
        mock.setMode(MockBeacon.Mode.Broken);
        sig = _sig(r);
        vm.prank(eve);
        vm.expectRevert(ITapDrandReveal.Unauthorized.selector);
        ctrl.revealUnverified(sig);
        vm.warp(open - 1);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.TooEarly.selector);
        ctrl.revealUnverified(sig);
        vm.warp(open);
        vm.startPrank(admin);
        vm.expectRevert(ITapDrandReveal.BadSignature.selector);
        ctrl.revealUnverified(new bytes(47));
        vm.expectRevert(ITapDrandReveal.BadSignature.selector);
        ctrl.revealUnverified(new bytes(49));
        vm.expectRevert(ITapDrandReveal.BadSignature.selector);
        ctrl.revealUnverified(bytes.concat(hex"00", new bytes(47))); // not compressed
        vm.expectRevert(ITapDrandReveal.BadSignature.selector);
        ctrl.revealUnverified(bytes.concat(hex"c0", new bytes(47))); // infinity flag
        ctrl.revealUnverified(sig);
        vm.stopPrank();
    }

    function test_emergency_closedWhileTheBeaconHoldsR() public {
        (uint64 r, uint256 open) = _emergencyReady();
        mock.post(r); // anybody cached R while the verifier still worked
        mock.setMode(MockBeacon.Mode.Broken);
        vm.warp(open);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.RoundCached.selector);
        ctrl.revealUnverified(_sig(r));
        // revealDrand keeps working: a cached round is compared by SHA-256 only
        ctrl.revealDrand(_sig(r));
        assertEq(coll.masterSeed(), sha256(_sig(r)));
    }

    function test_emergency_deferredNeedsTheScheduledRound() public {
        _deferredClosed();
        mock.setMode(MockBeacon.Mode.Broken);
        vm.warp(T0 + 100 days);
        vm.prank(admin);
        vm.expectRevert(ITapDrandReveal.NotScheduled.selector);
        ctrl.revealUnverified(_sig(1));
    }

    function test_emergency_verifierCheckCannotBeStarved() public {
        (uint64 r, uint256 open) = _emergencyReady();
        vm.warp(open);
        (bool ok, bytes memory ret) = address(ctrl).staticcall{gas: 500_000}(abi.encodeCall(ctrl.verifierWorks, ()));
        assertFalse(ok);
        assertEq(bytes4(ret), ITapDrandReveal.GasTooLow.selector);
        vm.prank(admin);
        (ok, ret) = address(ctrl).call{gas: 500_000}(abi.encodeCall(ctrl.revealUnverified, (_sig(r))));
        assertFalse(ok, "the emergency path reverts rather than treat a starved self-test as a failed one");
        assertEq(coll.masterSeed(), 0);
        // the same call with enough gas, against a verifier that really fails, goes through
        mock.setMode(MockBeacon.Mode.Broken);
        vm.prank(admin);
        ctrl.revealUnverified{gas: 3_000_000}(_sig(r));
        assertEq(coll.masterSeed(), sha256(_sig(r)));
    }

    // ================================================================== chain-clock lag

    function test_lag_theCommitRecordsHowFarTheChainTrailsAndCountsItFromThen() public {
        vm.warp(qt(S) - 1800); // the chain is 30 minutes behind round S
        bytes memory sig = _sig(S);
        mock.register(S, sig);
        uint64 expectedMin = roundAt(block.timestamp + 1800 + MIN_LEAD) + 1;
        vm.startPrank(admin);
        vm.expectRevert(ITapDrandReveal.BadRound.selector);
        ctrl.commit(MANIFEST, 1, SUPPLY, _pools(), expectedMin - 1, S, sig);
        ctrl.commit(MANIFEST, 1, SUPPLY, _pools(), expectedMin, S, sig);
        vm.stopPrank();
        assertEq(ctrl.lagAtCommit(), 1800);
        assertEq(ctrl.clock(), qt(S));
        // the gateway closes 1,800 s early by the chain's clock: it counts the lag it saw
        vm.warp(qt(expectedMin) - 600 - 1800);
        assertFalse(ctrl.mintOpen());
        vm.warp(qt(expectedMin) - 601 - 1800);
        assertTrue(ctrl.mintOpen());
    }

    function test_lag_aSelfTestRoundBehindTheBlockRecordsNone() public {
        vm.warp(qt(S) + 3600);
        _commit(_minFixed());
        assertEq(ctrl.lagAtCommit(), 0);
        assertEq(ctrl.clock(), qt(S) + 3600);
    }

    /// Deferred mode, the residual of docs/DRAND_REVEAL.md: a chain clock that trails real time by MORE than
    /// scheduleDelay, with no real-time round posted to the beacon, fixes an R that is already public. Posting the
    /// newest round first removes it; a lag below the delay is harmless either way.
    function test_lag_deferredResidualAndItsMitigation() public {
        uint256 real = qt(S + 20_000);
        _deferredClosed();

        uint256 snap = vm.snapshotState();
        vm.warp(real - 2 hours); // the chain trails by 2 h > scheduleDelay (1 h)
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertLe(ctrl.revealRound(), roundAt(real), "the residual: R is already public in real time");
        assertTrue(vm.revertToState(snap));

        vm.warp(real - 2 hours);
        mock.post(roundAt(real)); // somebody posts the newest real round first
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertGt(ctrl.revealRound(), roundAt(real));
        assertGe(qt(ctrl.revealRound()), real + 1 hours);
        assertTrue(vm.revertToState(snap));

        vm.warp(real - 30 minutes); // a lag below the delay needs no post
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertGt(ctrl.revealRound(), roundAt(real));
        assertGe(qt(ctrl.revealRound()), real + 30 minutes);
    }

    function test_lag_aChainClockAheadOfRealTimeOnlyMakesRLater() public {
        _deferredClosed();
        vm.warp(T0 + 3 hours); // 3 h "ahead" of anything real
        vm.prank(admin);
        ctrl.scheduleReveal();
        assertEq(ctrl.revealRound(), roundAt(T0 + 3 hours + 1 hours) + 1);
    }

    // ================================================================== gas (logged for docs/DRAND_REVEAL.md)

    function test_gas_gatewayOverhead() public {
        // direct mint by the owner of a plain reference collection
        TapNetlistNFT plain = new TapNetlistNFT("P", "P", "u/", address(this));
        plain.commitManifest(MANIFEST, 1, SUPPLY, _pools());
        uint256 g = gasleft();
        plain.mint(alice, 1);
        uint256 d1 = g - gasleft();
        g = gasleft();
        plain.mint(alice, 2);
        uint256 d2 = g - gasleft();

        // through the gateway, fixed mode
        _commit(_minFixed());
        g = gasleft();
        _mint(1);
        uint256 f1 = g - gasleft();
        g = gasleft();
        _mint(2);
        uint256 f2 = g - gasleft();

        // through the gateway, deferred mode
        _fresh(1 hours);
        _commit(0);
        g = gasleft();
        _mint(1);
        uint256 e1 = g - gasleft();
        g = gasleft();
        _mint(2);
        uint256 e2 = g - gasleft();

        emit log_named_uint("mint direct, 1st (gas)", d1);
        emit log_named_uint("mint direct, 2nd (gas)", d2);
        emit log_named_uint("mint via gateway, fixed, 1st (gas)", f1);
        emit log_named_uint("mint via gateway, fixed, 2nd (gas)", f2);
        emit log_named_uint("mint via gateway, deferred, 1st (gas)", e1);
        emit log_named_uint("mint via gateway, deferred, 2nd (gas)", e2);
        emit log_named_uint("gateway overhead per mint, fixed (gas)", f2 - d2);
        emit log_named_uint("gateway overhead per mint, deferred (gas)", e2 - d2);
        assertLt(f2 - d2, 40_000);
        assertLt(e2 - d2, 30_000);
    }

    function test_gas_factoryCreateAndScheduling() public {
        _installRealBeacon();
        bytes memory init = _refInitCode();
        uint256 g = gasleft();
        factory.create(admin, 1 hours, init, "Kit", "KIT", "https://example.invalid/meta/");
        uint256 createGas = g - gasleft();
        _installMockBeacon();
        emit log_named_uint("factory.create with the reference initcode (gas)", createGas);
        assertLt(createGas, 16_000_000, "under the EIP-7825 transaction gas cap");

        _deferredClosed();
        g = gasleft();
        vm.prank(admin);
        ctrl.scheduleReveal();
        emit log_named_uint("scheduleReveal (gas)", g - gasleft());
    }
}
