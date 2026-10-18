// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TapBridgePayload} from "../../src/bridge/TapBridgePayload.sol";
import {LayerZeroV2Adapter} from "../../src/bridge/LayerZeroV2Adapter.sol";
import {HubRelayAdapter} from "../../src/bridge/HubRelayAdapter.sol";
import {MockEndpointV2} from "./mocks/MockEndpointV2.sol";
import {IDeWebHubMin} from "../../src/bridge/HubRelayAdapter.sol";
import {ILayerZeroEndpointV2Min} from "../../src/bridge/ILayerZeroEndpointV2Min.sol";
import {ITapBridgeAdapter, ITapBridgeEndpoint} from "../../src/interfaces/ITapBridge.sol";
import {ITapBridgeTransfer} from "../../src/interfaces/ITapBridgeTransfer.sol";
import {ITapBridgeMirror} from "../../src/interfaces/ITapBridgeMirror.sol";
import {ITapBridgeAdapterSealed} from "../../src/interfaces/ITapBridgeAdapterSealed.sol";
import {TapBridgeEndpoint} from "../../src/bridge/TapBridgeEndpoint.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {TapMirror} from "../../src/bridge/TapMirror.sol";
import {TapAdapterBase} from "../../src/bridge/TapAdapterBase.sol";

/// @notice Checks the Solidity implementation against assets/tap-netlist-nft-bridging/vectors.json.
contract TapBridgeVectorsTest is Test {
    string json;

    function setUp() public {
        json = vm.readFile("../assets/tap-netlist-nft-bridging/vectors.json");
    }

    function _s(string memory path) internal view returns (string memory) {
        return vm.parseJsonString(json, path);
    }

    function _p(uint256 i, string memory k) internal pure returns (string memory) {
        return string.concat(".validPayloads[", vm.toString(i), "].", k);
    }

    function test_collectionKeys() public view {
        for (uint256 i; i < 2; ++i) {
            string memory b = string.concat(".collectionKeys[", vm.toString(i), "].");
            uint64 chainId = uint64(vm.parseJsonUint(json, string.concat(b, "homeChainId")));
            address c = vm.parseJsonAddress(json, string.concat(b, "homeContract"));
            assertEq(TapBridgePayload.collectionKey(chainId, c), vm.parseJsonBytes32(json, string.concat(b, "collectionKey")));
        }
    }

    function test_validPayloads() public view {
        uint256 n;
        for (uint256 i; vm.keyExistsJson(json, _p(i, "payload")); ++i) {
            TapBridgePayload.Payload memory p = TapBridgePayload.Payload({
                collectionKey: vm.parseJsonBytes32(json, _p(i, "fields.collectionKey")),
                tokenId: vm.parseUint(_s(_p(i, "fields.tokenId"))),
                to: vm.parseJsonAddress(json, _p(i, "fields.to")),
                netlistHash: vm.parseJsonBytes32(json, _p(i, "fields.netlistHash")),
                imageHash: vm.parseJsonBytes32(json, _p(i, "fields.imageHash")),
                manifestHash: vm.parseJsonBytes32(json, _p(i, "fields.manifestHash")),
                srcChainId: uint64(vm.parseUint(_s(_p(i, "fields.srcChainId")))),
                dstChainId: uint64(vm.parseUint(_s(_p(i, "fields.dstChainId")))),
                nonce: uint64(vm.parseUint(_s(_p(i, "fields.nonce"))))
            });
            bytes memory enc = TapBridgePayload.encode(p);
            bytes memory expected = vm.parseJsonBytes(json, _p(i, "payload"));
            assertEq(enc, expected, "payload");
            assertEq(keccak256(enc), vm.parseJsonBytes32(json, _p(i, "payloadHash")), "payload hash");
            address src = vm.parseJsonAddress(json, _p(i, "srcEndpoint"));
            bytes32 mid = TapBridgePayload.messageId(src, enc);
            assertEq(mid, vm.parseJsonBytes32(json, _p(i, "messageId")), "messageId");
            assertEq(
                keccak256(abi.encodePacked(mid, keccak256(enc))),
                vm.parseJsonBytes32(json, _p(i, "hubDigest")),
                "hub digest"
            );
            TapBridgePayload.Payload memory d = this.decodeExt(expected);
            assertEq(keccak256(abi.encode(d)), keccak256(abi.encode(p)), "decode");
            ++n;
        }
        assertEq(n, 4);
    }

    function test_invalidPayloads() public {
        uint256 n;
        for (uint256 i;; ++i) {
            string memory path = string.concat(".invalidPayloads[", vm.toString(i), "].payload");
            if (!vm.keyExistsJson(json, path)) break;
            bytes memory bad = vm.parseJsonBytes(json, path);
            vm.expectRevert(TapBridgePayload.BadPayload.selector);
            this.decodeExt(bad);
            ++n;
        }
        assertEq(n, 9);
    }

    function test_layerZeroOptionsAndLayerIds() public {
        MockEndpointV2 ep = new MockEndpointV2(30102);
        LayerZeroV2Adapter a = new LayerZeroV2Adapter(address(1), address(ep), address(this), address(this), 400000);
        assertEq(a.defaultOptions(), vm.parseJsonBytes(json, ".layerZero.defaultOptions[0].options"));
        assertEq(a.layerId(), vm.parseJsonBytes32(json, ".layerZero.layerId"));
    }

    function test_hubRelayEip712() public {
        address where = vm.parseJsonAddress(json, ".hubRelay.eip712.domain.verifyingContract");
        address hub = vm.parseJsonAddress(json, ".hubRelay.eip712.message.hub");
        address[] memory att = new address[](1);
        att[0] = address(0x1234);
        vm.chainId(56);
        deployCodeTo("HubRelayAdapter.sol:HubRelayAdapter", abi.encode(address(1), hub, address(this), att, 1), where);
        HubRelayAdapter h = HubRelayAdapter(where);
        assertEq(h.HUB_MESSAGE_TYPEHASH(), vm.parseJsonBytes32(json, ".hubRelay.eip712.hubMessageTypehash"));
        assertEq(h.domainSeparator(), vm.parseJsonBytes32(json, ".hubRelay.eip712.domainSeparator"));
        assertEq(
            h.hubMessageHash(
                196,
                vm.parseJsonAddress(json, ".hubRelay.eip712.message.fromContainer"),
                5,
                vm.parseJsonBytes32(json, ".hubRelay.eip712.message.digest")
            ),
            vm.parseJsonBytes32(json, ".hubRelay.eip712.signingHash")
        );
        assertEq(h.layerId(), vm.parseJsonBytes32(json, ".hubRelay.layerId"));
    }

    function test_interfaceIdsAndSelectors() public view {
        assertEq(type(ITapBridgeAdapter).interfaceId, _id("ITapBridgeAdapter"));
        assertEq(type(ITapBridgeEndpoint).interfaceId, _id("ITapBridgeEndpoint"));
        assertEq(type(ITapBridgeTransfer).interfaceId, _id("ITapBridgeTransfer"));
        assertEq(type(ITapBridgeMirror).interfaceId, _id("ITapBridgeMirror"));
        assertEq(type(ITapBridgeAdapterSealed).interfaceId, _id("ITapBridgeAdapterSealed"));
        assertEq(TapBridgeEndpoint.Replay.selector, _err("Replay(bytes32)"));
        assertEq(TapBridgeEndpoint.WrongPeer.selector, _err("WrongPeer(address)"));
        assertEq(TapBridgeEndpoint.EndpointRecipient.selector, _err("EndpointRecipient(address)"));
        assertEq(TapBridgeEndpoint.AdapterNotSealed.selector, _err("AdapterNotSealed(address)"));
        assertEq(TapGateway.AlreadyEscrowed.selector, _err("AlreadyEscrowed(uint256)"));
        assertEq(TapGateway.NotBound.selector, _err("NotBound(uint256)"));
        assertEq(TapMirror.ManifestConflict.selector, _err("ManifestConflict(bytes32,bytes32)"));
        assertEq(TapMirror.NotHomeCollection.selector, _err("NotHomeCollection()"));
        assertEq(TapAdapterBase.WrongPeer.selector, _err("WrongPeer()"));
        assertEq(TapBridgePayload.BadPayload.selector, _err("BadPayload()"));
        assertEq(LayerZeroV2Adapter.lzReceive.selector, _sel("lzReceive((uint32,bytes32,uint64),bytes32,bytes,address,bytes)"));
        assertEq(LayerZeroV2Adapter.allowInitializePath.selector, _sel("allowInitializePath((uint32,bytes32,uint64))"));
        assertEq(HubRelayAdapter.deliver.selector, _sel("deliver(uint64,uint256,bytes32,bytes,bytes)"));
        assertEq(IDeWebHubMin.send.selector, _sel("send(address,uint256,bytes32,bytes32,bytes)"));
        assertEq(ILayerZeroEndpointV2Min.send.selector, _sel("send((uint32,bytes32,bytes,bytes,bool),address)"));
        assertEq(ITapBridgeEndpoint.Departed.selector, _topic("Departed(bytes32,uint256,uint64,address)"));
        assertEq(ITapBridgeEndpoint.Confirmed.selector, _topic("Confirmed(bytes32,address)"));
        assertEq(ITapBridgeEndpoint.Arrived.selector, _topic("Arrived(bytes32,uint256,uint64,address)"));
    }

    function _id(string memory name) internal view returns (bytes4) {
        return bytes4(vm.parseJsonBytes(json, string.concat(".interfaces.interfaceIds.", name)));
    }

    function _sel(string memory sig) internal view returns (bytes4) {
        return bytes4(vm.parseJsonBytes(json, string.concat(".interfaces.selectors['", sig, "']")));
    }

    function _err(string memory sig) internal view returns (bytes4) {
        return bytes4(vm.parseJsonBytes(json, string.concat(".interfaces.errors['", sig, "']")));
    }

    function _topic(string memory sig) internal view returns (bytes32) {
        return vm.parseJsonBytes32(json, string.concat(".interfaces.eventTopics['", sig, "']"));
    }

    function decodeExt(bytes calldata b) external pure returns (TapBridgePayload.Payload memory) {
        return TapBridgePayload.decode(b);
    }
}
