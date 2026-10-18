// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TokenSetPack} from "../core/CoreHelpers.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {UlnConfig} from "../../src/bridge/ILayerZeroEndpointV2Min.sol";
import {MockAdapter} from "../bridge/mocks/MockAdapter.sol";
import {MockLegacy721} from "../bridge/mocks/MockERC721s.sol";
import {MockReceiveUln} from "../bridge/mocks/MockEndpointV2.sol";
import {BridgeFixture} from "../bridge/BridgeFixture.sol";
import {LayerZeroV2Adapter} from "../../src/bridge/LayerZeroV2Adapter.sol";
import {CoreBase} from "../core/CoreBase.sol";

/// Third pass (token-set mode, pool loading, per-route gateway, LZ seal pinning).
contract AuditPass3CoreTest is CoreBase {
    /// P3-1 (regression): in token-set mode the gateway decides membership with the data source's indexOf, not
    /// tokenRange(): a token outside the set departs with zero hashes; an unbound set member is refused.
    function test_audit_gatewaySetModeUsesWrongRange() public {
        _buildPools(3);
        vm.chainId(196);
        MockLegacy721 legacy = new MockLegacy721();
        TapCompanion comp = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), address(this));
        uint32[] memory ids = new uint32[](3);
        ids[0] = 5;
        ids[1] = 10;
        ids[2] = 20;
        bytes32 setHash = sha256(abi.encodePacked(uint32(5), uint32(10), uint32(20)));
        comp.commitManifestTokenSet(MANIFEST, setHash, 3, _pools(), false);
        comp.loadTokenSet(TokenSetPack.pack(ids));
        comp.reveal(SEED);
        (uint256 first, uint256 n) = comp.tokenRange();
        assertEq(first, 0);
        assertEq(n, 3);

        TapGateway gw = new TapGateway(address(legacy), address(comp), address(this));
        MockAdapter a = new MockAdapter(address(gw), 0);
        a.setRemote(56, address(0xB5C));
        address[] memory ads = new address[](1);
        ads[0] = address(a);
        gw.setRoute(56, 1, ads, address(0xB5C));

        address alice = makeAddr("alice");
        legacy.mint(alice, 1); // not in the set, id < count
        legacy.mint(alice, 20); // in the set, id >= count, unbound
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotInTokenSet.selector, uint256(1)));
        comp.entryIndexOf(1, 0); // id 1 can never be bound ...
        vm.startPrank(alice);
        legacy.setApprovalForAll(address(gw), true);
        gw.bridge(1, 56, alice, false, new bytes[](0)); // ... so it departs, with zero hashes
        assertEq(gw.locationOf(1), 56);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotBound.selector, uint256(20)));
        gw.bridge(20, 56, alice, false, new bytes[](0)); // a set member must be bound first
        vm.stopPrank();
        assertEq(comp.netlistHashOf(20), 0);

        _failClosedWhileSetNotRecorded(legacy, setHash, ids, alice);
    }

    function _failClosedWhileSetNotRecorded(MockLegacy721 legacy, bytes32 setHash, uint32[] memory ids, address alice)
        internal
    {
        // fail closed: while a committed token set is not recorded on chain, nothing departs unbound
        TapCompanion comp2 = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), address(this));
        comp2.commitManifestTokenSet(MANIFEST, setHash, 3, _pools(), false);
        comp2.reveal(SEED);
        TapGateway gw2 = new TapGateway(address(legacy), address(comp2), address(this));
        MockAdapter a2 = new MockAdapter(address(gw2), 0);
        a2.setRemote(56, address(0xB5C));
        address[] memory ads = new address[](1);
        ads[0] = address(a2);
        gw2.setRoute(56, 1, ads, address(0xB5C));
        legacy.mint(alice, 2);
        vm.startPrank(alice);
        legacy.setApprovalForAll(address(gw2), true);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotBound.selector, uint256(2)));
        gw2.bridge(2, 56, alice, false, new bytes[](0));
        vm.stopPrank();
        comp2.loadTokenSet(TokenSetPack.pack(ids)); // once recorded, the non-member departs
        vm.prank(alice);
        gw2.bridge(2, 56, alice, false, new bytes[](0));
        assertEq(gw2.locationOf(2), 56);
    }
}

contract AuditPass3BridgeTest is BridgeFixture {
    /// P3-2 (regression): LayerZero seal() rejects ULN302's NIL values (requiredDVNCount = 255, confirmations =
    /// type(uint64).max) as well as zero (default) values.
    function test_audit_lzSealAcceptsNilDvnConfig() public {
        vm.chainId(XL);
        MockReceiveUln uln = new MockReceiveUln(address(lzXL));
        vm.startPrank(owner);
        uint32[2] memory eids = [uint32(30102), uint32(30184)];
        address[] memory req = new address[](2);
        req[0] = address(0xD1);
        req[1] = address(0xD2);
        for (uint256 i; i < 2; ++i) {
            lzXL.setSendLibrary(address(lXL), eids[i], address(0x5E7D));
            lzXL.setReceiveLibrary(address(lXL), eids[i], address(uln), 0);
        }
        UlnConfig[3] memory bad = [
            UlnConfig(type(uint64).max, 255, 0, 0, new address[](0), new address[](0)), // both NIL
            UlnConfig(15, 255, 0, 0, new address[](0), new address[](0)), // NIL required DVNs
            UlnConfig(type(uint64).max, 2, 0, 0, req, new address[](0)) // NIL confirmations
        ];
        for (uint256 k; k < 3; ++k) {
            lzXL.setUlnConfig(address(lXL), 30102, bad[k]);
            lzXL.setUlnConfig(address(lXL), 30184, UlnConfig(15, 2, 0, 0, req, new address[](0)));
            vm.expectRevert(abi.encodeWithSelector(LayerZeroV2Adapter.NotPinned.selector, uint32(30102)));
            lXL.seal();
        }
        lzXL.setUlnConfig(address(lXL), 30102, UlnConfig(15, 2, 0, 0, req, new address[](0)));
        lXL.seal();
        vm.stopPrank();
        assertTrue(lXL.adapterSealed());
        assertEq(lzXL.delegates(address(lXL)), address(0));
    }
}
