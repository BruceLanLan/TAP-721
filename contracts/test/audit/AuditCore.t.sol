// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {CoreBase} from "../core/CoreBase.sol";
import {MerkleBuilder, Tapnet} from "../core/CoreHelpers.sol";

/// Legacy collection whose freeze flag can be cleared again (upgradeable / non-monotonic getter).
contract FlippingLegacy {
    address public owner = msg.sender;
    bool public uriFrozen;

    function set(bool v) external {
        uriFrozen = v;
    }
}

/// Regression tests for the core findings of reviews/security-contracts.md (formerly PoCs C-1..C-7).
contract AuditCoreTest is CoreBase {
    TapNetlistNFT nft;
    address minter = makeAddr("minter");

    function setUp() public {
        _buildPools(64);
        nft = new TapNetlistNFT("Tape", "TAPE", "ipfs://base/", address(this));
    }

    /// M-1 (C-1): minting ends at the reveal, so nobody can pick ids after entryIndexOf becomes public.
    function test_audit_mintAfterRevealReverts() public {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        nft.setMinter(minter, true);
        nft.reveal(SEED);
        uint256 target = type(uint256).max;
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            if (nft.entryIndexOf(t, 1) == 0) target = t;
        }
        vm.prank(minter);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.mint(minter, target);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.mint(address(this), target);
    }

    /// M-2 (C-2): a blockhash reveal is one-shot; a missed window cannot be rescheduled (no reroll).
    function test_audit_blockhashRevealCannotBeRerolled() public {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        vm.roll(1000);
        nft.scheduleBlockhashReveal(1001);
        vm.roll(1001 + 257);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.RevealIsScheduled.selector, 1001));
        nft.scheduleBlockhashReveal(1300);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BlockhashUnavailable.selector, 1001));
        nft.revealFromBlockhash(1001);
        assertEq(nft.masterSeed(), 0);
    }

    /// L-5 (C-3): the scheduled block is bounded; an absurd value is refused instead of bricking the reveal.
    function test_audit_scheduleIsBounded() public {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, type(uint256).max));
        nft.scheduleBlockhashReveal(type(uint256).max);
        uint256 far = block.number + nft.MAX_REVEAL_DELAY() + 1;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, far));
        nft.scheduleBlockhashReveal(far);
        nft.reveal(SEED); // still revealable
        nft.freeze();
        assertTrue(nft.frozen());
    }

    /// L-6 (C-4): duplicate labels are refused, so the two pools never share a pool seed.
    function test_audit_duplicateLabelsRejected() public {
        ITapNetlistNFT.Pool[] memory ps = _pools();
        ps[1].label = ps[0].label;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 1));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
    }

    /// L-8 (C-5): ownership cannot be renounced by transfer; freeze() is the only way, and it ends minting.
    function test_audit_renounceOnlyThroughFreeze() public {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        nft.setMinter(minter, true);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.ZeroOwner.selector);
        nft.transferOwnership(address(0));
        nft.freeze();
        assertTrue(nft.frozen());
        vm.prank(minter);
        vm.expectRevert(TapNetlistNFT.IsFrozen.selector);
        nft.mint(minter, FIRST + 3);
    }

    /// L-4 (C-6): TapCompanion.frozen() reports the latched state only; it never returns to false.
    function test_audit_companionFrozenNeverReverts() public {
        FlippingLegacy legacy = new FlippingLegacy();
        TapCompanion c = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), address(this));
        c.commitManifest(MANIFEST, FIRST, supply, _pools());
        c.reveal(SEED);
        c.endorse(); // this test contract is legacy.owner()
        c.seal();
        assertFalse(c.frozen());
        legacy.set(true);
        assertFalse(c.frozen()); // not latched yet
        legacy.set(false);
        assertFalse(c.announceFrozen()); // condition no longer holds: nothing latched
        legacy.set(true);
        assertTrue(c.announceFrozen());
        legacy.set(false);
        assertTrue(c.frozen()); // stays true
    }

    /// L-7 (C-7): MAX_FILE = 49,152 bytes; storing a MAX_FILE netlist with the check fits a
    /// 16,777,216-gas transaction, and larger files are refused.
    function test_audit_maxFileFitsTxGasCap() public {
        bytes memory f = Tapnet.chain(7016, 6); // 49,152 bytes
        assertEq(f.length, 49152);
        TapNetlistNFT n2 = _oneFile(f);
        uint256 g = gasleft();
        n2.storeNetlist(f);
        uint256 used = g - gasleft();
        emit log_named_uint("storeNetlist gas, 49,152-byte file", used);
        assertLt(used, 15_000_000);

        bytes memory big = Tapnet.chain(14041, 0); // 98,303 bytes
        TapNetlistNFT n3 = _oneFile(big);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistTooLarge.selector, big.length));
        n3.storeNetlist(big);
    }

    function _oneFile(bytes memory f) internal returns (TapNetlistNFT n2) {
        bytes32[] memory v = _one(sha256(f));
        n2 = new TapNetlistNFT("T", "T", "", address(this));
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("N", 2, TapMerkle.leafHash(0, v));
        n2.commitManifest(MANIFEST, 1, 1, ps);
        n2.reveal(SEED);
        n2.bind(1, 0, v, new bytes32[](0));
    }
}
