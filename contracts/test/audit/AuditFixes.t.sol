// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {MockAdapter} from "../bridge/mocks/MockAdapter.sol";
import {MockLegacy721} from "../bridge/mocks/MockERC721s.sol";
import {CoreBase} from "../core/CoreBase.sol";

/// Re-audit after fixes (reviews/security-contracts.md, "New findings after fixes").
contract AuditFixesTest is CoreBase {
    address minter = makeAddr("minter");

    function setUp() public {
        _buildPools(64);
    }

    /// N-1 (regression): the NO_REVEAL sentinel is refused as a random seed, so a random-reveal collection
    /// cannot be "revealed" into identity assignment with minting still open.
    function test_audit_revealWithNoRevealSentinelReverts() public {
        TapNetlistNFT nft = new TapNetlistNFT("Tape", "TAPE", "", address(this));
        nft.commitManifest(MANIFEST, FIRST, supply, _pools()); // random-reveal manifest
        nft.setMinter(minter, true);
        bytes32 sentinel = nft.NO_REVEAL();
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.reveal(sentinel);
        assertEq(nft.masterSeed(), 0);
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.entryIndexOf(FIRST, 1);
    }

    /// N-2 (regression): the NotBound rule applies only inside the data source's tokenRange(); a token outside
    /// the manifest range (it can never be bound) still departs, with zero hashes.
    function test_audit_gatewayNotBoundStrandsTokensOutsideManifestRange() public {
        vm.chainId(196);
        MockLegacy721 legacy = new MockLegacy721();
        TapCompanion comp = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), address(this));
        comp.commitManifest(MANIFEST, FIRST, supply, _pools()); // ids 1..64 only
        comp.reveal(SEED);
        TapGateway gw = new TapGateway(address(legacy), address(comp), address(this));
        MockAdapter a = new MockAdapter(address(gw), 0);
        a.setRemote(56, address(0xB5C));
        address[] memory ads = new address[](1);
        ads[0] = address(a);
        gw.setRoute(56, 1, ads, address(0xB5C));

        address alice = makeAddr("alice");
        legacy.mint(alice, 500); // a real token of the collection, outside the manifest range
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, uint256(500)));
        comp.entryIndexOf(500, 0); // it can never be bound ...
        vm.startPrank(alice);
        legacy.approve(address(gw), 500);
        gw.bridge(500, 56, alice, false, new bytes[](0)); // ... so it departs with zero hashes (N-2 fixed)
        vm.stopPrank();
        assertEq(gw.locationOf(500), 56);
        // inside the range the bind-first rule still applies
        legacy.mint(alice, 5);
        vm.startPrank(alice);
        legacy.approve(address(gw), 5);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotBound.selector, uint256(5)));
        gw.bridge(5, 56, alice, false, new bytes[](0));
        vm.stopPrank();
    }
}
