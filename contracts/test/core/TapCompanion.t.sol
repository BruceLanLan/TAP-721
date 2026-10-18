// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapCompanion} from "../../src/interfaces/ITapCompanion.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {Owned} from "../../src/vendor/Owned.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapPermutation} from "../../src/core/TapPermutation.sol";
import {CoreBase} from "./CoreBase.sol";
import {MerkleBuilder} from "./CoreHelpers.sol";
import {MockContainer, MockLegacy721, MockLegacyNoFreeze, MockLegacyWeird} from "./CoreHelpers.sol";

contract TapCompanionTest is CoreBase {
    bytes4 constant URI_FROZEN = bytes4(keccak256("uriFrozen()"));

    MockLegacy721 legacy;
    TapCompanion comp;
    address alice = makeAddr("alice");

    function setUp() public {
        _buildPools(30);
        legacy = new MockLegacy721();
        comp = new TapCompanion(address(legacy), URI_FROZEN, address(this));
    }

    function _commitReveal(TapCompanion c) internal {
        c.commitManifest(MANIFEST, FIRST, supply, _pools());
        c.reveal(SEED);
    }

    function test_basics() public view {
        assertEq(comp.collection(), address(legacy));
        assertEq(comp.uriFrozenSelector(), URI_FROZEN);
        assertEq(comp.owner(), address(this));
        assertTrue(comp.supportsInterface(type(ITapNetlistNFT).interfaceId));
        assertTrue(comp.supportsInterface(0x01ffc9a7));
        assertTrue(comp.supportsInterface(0x49064906));
        assertFalse(comp.supportsInterface(0x80ac58cd)); // the companion is not the ERC-721
        assertTrue(comp.supportsInterface(type(ITapCompanion).interfaceId));
        assertEq(type(ITapCompanion).interfaceId, bytes4(0xf4fbaf58) ^ bytes4(0xe64fa534));
        assertEq(comp.endorsedBy(), address(0));
        assertFalse(comp.frozen());
        assertFalse(comp.isSealed());
        assertFalse(comp.legacyUriFrozen());
    }

    function test_constructorRejectsZeroLegacy() public {
        vm.expectRevert(TapCompanion.ZeroAddress.selector);
        new TapCompanion(address(0), URI_FROZEN, address(this));
    }

    function test_poolSeedUsesLegacyAddress() public {
        _commitReveal(comp);
        assertEq(comp.poolSeed(0), TapPermutation.poolSeed(SEED, uint64(block.chainid), address(legacy), "IMAGE_V1"));
    }

    function test_bindAndStore() public {
        _commitReveal(comp);
        uint256 t = _tokenWithNetlist(comp, sha256(xorFile));
        vm.expectEmit(address(comp));
        emit IERC4906.MetadataUpdate(t);
        _bind(comp, t, 1);
        _bind(comp, t, 0);
        comp.storeNetlist(xorFile);
        assertEq(comp.netlistOf(t), xorFile);
        assertTrue(comp.imageHashOf(t) != 0);
    }

    function test_sealThenLegacyFreeze() public {
        _commitReveal(comp);
        legacy.setOwner(address(this));
        comp.endorse();
        vm.recordLogs();
        comp.seal();
        assertEq(vm.getRecordedLogs().length, 1); // OwnershipTransferred only: legacy not frozen yet
        assertTrue(comp.isSealed());
        assertEq(comp.owner(), address(0));
        assertFalse(comp.frozen());
        assertFalse(comp.announceFrozen());

        legacy.freezeBaseURI();
        assertFalse(comp.frozen()); // frozen() reports the latched state only
        vm.expectEmit(address(comp));
        emit ITapNetlistNFT.Frozen();
        vm.expectEmit(address(comp));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        assertTrue(comp.announceFrozen());
        vm.recordLogs();
        assertTrue(comp.announceFrozen());
        assertEq(vm.getRecordedLogs().length, 0);

        assertTrue(comp.frozen());
        // latched: stays frozen even if the legacy getter later fails
        vm.etch(address(legacy), hex"fe");
        assertTrue(comp.frozen());

        bytes memory unauthorized = abi.encodeWithSelector(Owned.Unauthorized.selector, address(this));
        vm.expectRevert(unauthorized);
        comp.reveal(keccak256("x"));
        vm.expectRevert(unauthorized);
        comp.scheduleBlockhashReveal(block.number + 1);
        vm.expectRevert(unauthorized);
        comp.seal();
    }

    function test_legacyFreezeThenSeal() public {
        legacy.freezeBaseURI();
        assertTrue(comp.legacyUriFrozen());
        assertFalse(comp.frozen()); // not committed / revealed / sealed
        _commitReveal(comp);
        comp.endorse(); // this test contract deployed the legacy mock, so it is its owner
        assertFalse(comp.frozen());
        vm.expectEmit(address(comp));
        emit ITapNetlistNFT.Frozen();
        comp.seal();
        assertTrue(comp.frozen());
    }

    function test_endorseThroughContainer() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector); // endorse a fixed manifest only
        comp.endorse();
        comp.commitManifest(MANIFEST, FIRST, supply, _pools());
        MockContainer container = new MockContainer();
        legacy.setOwner(address(container));
        assertEq(comp.legacyOwner(), address(container));

        vm.expectRevert(abi.encodeWithSelector(TapCompanion.NotCollectionOwner.selector, address(this)));
        comp.endorse();
        vm.prank(alice);
        vm.expectRevert("not holder");
        container.execute(address(comp), 0, abi.encodeCall(TapCompanion.endorse, ()), 0);

        vm.expectEmit(address(comp));
        emit ITapCompanion.Endorsed(address(container));
        container.execute(address(comp), 0, abi.encodeCall(TapCompanion.endorse, ()), 0);
        assertTrue(comp.endorsed());
        assertEq(comp.endorsedBy(), address(container));

        vm.recordLogs(); // idempotent
        container.execute(address(comp), 0, abi.encodeCall(TapCompanion.endorse, ()), 0);
        assertEq(vm.getRecordedLogs().length, 0);
        vm.expectRevert(abi.encodeWithSelector(TapCompanion.NotCollectionOwner.selector, address(this)));
        comp.endorse(); // still owner-only after endorsement
    }

    function test_frozenRequiresEndorsement() public {
        _commitReveal(comp);
        legacy.freezeBaseURI();
        comp.seal();
        assertFalse(comp.frozen()); // sealed + legacy frozen, but not endorsed
        assertFalse(comp.announceFrozen());
        vm.expectEmit(address(comp));
        emit ITapNetlistNFT.Frozen(); // endorsing last completes the freeze
        comp.endorse(); // works after the legacy URI freeze and after seal
        assertTrue(comp.frozen());
    }

    function test_endorseWithoutOwnerGetterReverts() public {
        TapCompanion c = new TapCompanion(address(new MockLegacyNoFreeze()), URI_FROZEN, address(this));
        c.commitManifest(MANIFEST, FIRST, supply, _pools());
        assertEq(c.legacyOwner(), address(0));
        vm.expectRevert(abi.encodeWithSelector(TapCompanion.NotCollectionOwner.selector, address(this)));
        c.endorse();
    }

    function test_noRevealCompanion() public {
        comp.commitManifestNoReveal(MANIFEST, FIRST, supply, _pools());
        assertEq(comp.entryIndexOf(FIRST + 5, 1), 5);
        comp.bind(FIRST + 5, 1, _one(netValues[5]), MerkleBuilder.proof(netLeaves, 5));
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        comp.reveal(SEED);
        comp.endorse();
        legacy.freezeBaseURI();
        vm.expectEmit(address(comp));
        emit ITapNetlistNFT.Frozen();
        comp.seal();
        assertTrue(comp.frozen());
    }

    function test_cannotRenounceByTransfer() public {
        vm.expectRevert(TapNetlistCore.ZeroOwner.selector);
        comp.transferOwnership(address(0));
    }

    function test_sealReverts() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        comp.seal();
        comp.commitManifest(MANIFEST, FIRST, supply, _pools());
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        comp.seal();
        comp.reveal(SEED);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        comp.seal();
    }

    function test_legacyWithoutGetterNeverFreezes() public {
        TapCompanion c = new TapCompanion(address(new MockLegacyNoFreeze()), URI_FROZEN, address(this));
        _commitReveal(c);
        c.seal();
        assertFalse(c.endorsed());
        assertFalse(c.legacyUriFrozen());
        assertFalse(c.frozen());
        assertFalse(c.announceFrozen());
    }

    function test_malformedGetterCountsAsNotFrozen() public {
        TapCompanion c = new TapCompanion(address(new MockLegacyWeird()), URI_FROZEN, address(this));
        assertFalse(c.legacyUriFrozen()); // returns 2, not a bool true
        TapCompanion eoa = new TapCompanion(alice, URI_FROZEN, address(this));
        assertFalse(eoa.legacyUriFrozen()); // empty return data
    }

    function test_customSelector() public {
        TapCompanion c = new TapCompanion(address(legacy), legacy.uriFrozen.selector, address(this));
        legacy.freezeBaseURI();
        assertTrue(c.legacyUriFrozen());
        TapCompanion wrong = new TapCompanion(address(legacy), bytes4(keccak256("frozen()")), address(this));
        assertFalse(wrong.legacyUriFrozen());
    }
}
