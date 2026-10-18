// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, Vm} from "forge-std/Test.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {TapMirror} from "../../src/bridge/TapMirror.sol";
import {TapBridgeEndpoint} from "../../src/bridge/TapBridgeEndpoint.sol";
import {LayerZeroV2Adapter} from "../../src/bridge/LayerZeroV2Adapter.sol";
import {HubRelayAdapter} from "../../src/bridge/HubRelayAdapter.sol";
import {MockEndpointV2, MockReceiveUln} from "./mocks/MockEndpointV2.sol";
import {UlnConfig} from "../../src/bridge/ILayerZeroEndpointV2Min.sol";
import {MockHub} from "./mocks/MockHub.sol";
import {MockAdapter} from "./mocks/MockAdapter.sol";
import {MockLegacy721, MockCircuits, MockDataSource} from "./mocks/MockERC721s.sol";

/// @notice Three simulated chains in one EVM, switched with vm.chainId:
///         X Layer 196 = home (a TapeCode-Test1-like legacy collection + companion data source),
///         BNB Smart Chain 56 and Base 8453 = remote mirrors.
abstract contract BridgeFixture is Test {
    uint64 constant XL = 196;
    uint64 constant BSC = 56;
    uint64 constant BASE = 8453;
    uint8 constant ONE = 1;
    uint8 constant ALL = 2;

    address owner = makeAddr("owner");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address carol = makeAddr("carol");
    address relayer = makeAddr("relayer");

    MockLegacy721 legacy;
    MockDataSource ds;
    TapGateway gw;
    TapMirror mBsc;
    TapMirror mBase;

    // mock layers A and B
    MockAdapter aXL;
    MockAdapter aBSC;
    MockAdapter aBASE;
    MockAdapter bXL;
    MockAdapter bBSC;
    MockAdapter bBASE;

    // LayerZero
    MockEndpointV2 lzXL;
    MockEndpointV2 lzBSC;
    MockEndpointV2 lzBASE;
    LayerZeroV2Adapter lXL;
    LayerZeroV2Adapter lBSC;
    LayerZeroV2Adapter lBASE;

    // TAP-10 hub relay
    MockHub hubXL;
    MockHub hubBSC;
    MockHub hubBASE;
    HubRelayAdapter hXL;
    HubRelayAdapter hBSC;
    HubRelayAdapter hBASE;
    uint256[] attesterKeys;
    address[] attesterAddrs;

    /// tapnet/1: "TAPNET" 01 00, nIn = 2, nOut = 1, one NAND(2, 3)
    bytes constant NETLIST_FILE = hex"5441504e45540100000000020000000100000002000003";
    bytes32 constant NETLIST = sha256(NETLIST_FILE);
    bytes32 constant IMAGE = keccak256("image-7");
    bytes32 constant MANIFEST = keccak256("manifest");

    function setUp() public virtual {
        _attesters();

        vm.chainId(XL);
        legacy = new MockLegacy721();
        ds = new MockDataSource(address(legacy));
        gw = new TapGateway(address(legacy), address(ds), owner);
        aXL = new MockAdapter(address(gw), 0.0001 ether);
        bXL = new MockAdapter(address(gw), 0.0002 ether);
        lzXL = new MockEndpointV2(30274);
        lXL = new LayerZeroV2Adapter(address(gw), address(lzXL), owner, owner, 400_000);
        hubXL = new MockHub();
        hXL = new HubRelayAdapter(address(gw), address(hubXL), owner, attesterAddrs, 2);

        vm.chainId(BSC);
        mBsc = new TapMirror(XL, address(legacy), "TapeCode-Test1", "TCT1", "ipfs://mirror/", 1, 10000, owner);
        aBSC = new MockAdapter(address(mBsc), 0.0001 ether);
        bBSC = new MockAdapter(address(mBsc), 0.0002 ether);
        lzBSC = new MockEndpointV2(30102);
        lBSC = new LayerZeroV2Adapter(address(mBsc), address(lzBSC), owner, owner, 400_000);
        hubBSC = new MockHub();
        hBSC = new HubRelayAdapter(address(mBsc), address(hubBSC), owner, attesterAddrs, 2);

        vm.chainId(BASE);
        mBase = new TapMirror(XL, address(legacy), "TapeCode-Test1", "TCT1", "", 1, 10000, owner);
        aBASE = new MockAdapter(address(mBase), 0.0001 ether);
        bBASE = new MockAdapter(address(mBase), 0.0002 ether);
        lzBASE = new MockEndpointV2(30184);
        lBASE = new LayerZeroV2Adapter(address(mBase), address(lzBASE), owner, owner, 400_000);
        hubBASE = new MockHub();
        hBASE = new HubRelayAdapter(address(mBase), address(hubBASE), owner, attesterAddrs, 2);

        _wireMock();
        _wireLz();
        _wireHub();

        vm.chainId(XL);
        legacy.mint(alice, 7);
        legacy.mint(alice, 8);
        ds.set(7, NETLIST, IMAGE);
        ds.setManifest(MANIFEST);
        vm.deal(alice, 10 ether);
        vm.deal(bob, 10 ether);
        vm.deal(carol, 10 ether);
    }

    function _attesters() internal {
        for (uint256 i = 1; i <= 3; ++i) {
            attesterKeys.push(0xA11CE + i);
            attesterAddrs.push(vm.addr(0xA11CE + i));
        }
        // sort ascending by address (keys follow)
        for (uint256 i; i < 3; ++i) {
            for (uint256 j = i + 1; j < 3; ++j) {
                if (attesterAddrs[j] < attesterAddrs[i]) {
                    (attesterAddrs[i], attesterAddrs[j]) = (attesterAddrs[j], attesterAddrs[i]);
                    (attesterKeys[i], attesterKeys[j]) = (attesterKeys[j], attesterKeys[i]);
                }
            }
        }
    }

    /// @dev Each mock adapter learns which endpoint its counterpart serves on each other chain.
    function _wireMock() internal {
        MockAdapter[3] memory a = [aXL, aBSC, aBASE];
        MockAdapter[3] memory b = [bXL, bBSC, bBASE];
        uint64[3] memory ids = [XL, BSC, BASE];
        for (uint256 i; i < 3; ++i) {
            for (uint256 j; j < 3; ++j) {
                if (i == j) continue;
                a[i].setRemote(ids[j], a[j].endpoint());
                b[i].setRemote(ids[j], b[j].endpoint());
            }
        }
    }

    /// @dev As the LayerZero delegate: pin send and receive libraries and an explicit receive ULN config
    ///      (2 required DVNs, 15 confirmations) for every configured remote eid, so that `seal()` can succeed.
    function _pinLz(LayerZeroV2Adapter a, MockEndpointV2 ep, uint32[] memory eids) internal {
        vm.chainId(a.localChainId());
        MockReceiveUln uln = new MockReceiveUln(address(ep));
        address[] memory req = new address[](2);
        req[0] = address(0xD1);
        req[1] = address(0xD2);
        vm.startPrank(owner);
        for (uint256 i; i < eids.length; ++i) {
            ep.setSendLibrary(address(a), eids[i], address(0x5E7D));
            ep.setReceiveLibrary(address(a), eids[i], address(uln), 0);
            ep.setUlnConfig(address(a), eids[i], UlnConfig(15, 2, 0, 0, req, new address[](0)));
        }
        vm.stopPrank();
    }

    function _wireLz() internal {
        vm.startPrank(owner);
        vm.chainId(XL);
        lXL.setPeer(BSC, 30102, _b32(address(lBSC)), address(mBsc));
        lXL.setPeer(BASE, 30184, _b32(address(lBASE)), address(mBase));
        vm.chainId(BSC);
        lBSC.setPeer(XL, 30274, _b32(address(lXL)), address(gw));
        lBSC.setPeer(BASE, 30184, _b32(address(lBASE)), address(mBase));
        vm.chainId(BASE);
        lBASE.setPeer(XL, 30274, _b32(address(lXL)), address(gw));
        lBASE.setPeer(BSC, 30102, _b32(address(lBSC)), address(mBsc));
        vm.stopPrank();
    }

    function _wireHub() internal {
        HubRelayAdapter[3] memory h = [hXL, hBSC, hBASE];
        MockHub[3] memory hubs = [hubXL, hubBSC, hubBASE];
        uint64[3] memory ids = [XL, BSC, BASE];
        address[3] memory containers;
        for (uint256 i; i < 3; ++i) {
            vm.chainId(ids[i]);
            MockCircuits c = new MockCircuits();
            c.mint(address(h[i]), 1); // the adapter holds the circuit whose container writes for it
            vm.prank(owner);
            h[i].setCircuit(address(c), 1);
            containers[i] = hubs[i].accountOf(address(c), 1);
        }
        for (uint256 i; i < 3; ++i) {
            vm.chainId(ids[i]);
            for (uint256 j; j < 3; ++j) {
                if (i == j) continue;
                address remoteEp = h[j].endpoint();
                vm.prank(owner);
                h[i].setRemote(ids[j], address(h[j]), containers[j], remoteEp);
            }
        }
    }

    // ------------------------------------------------------------------ route helpers

    function _route(TapBridgeEndpoint e, uint64 chainId, uint8 policy, address a0, address a1, address peer)
        internal
    {
        address[] memory ads;
        if (a1 == address(0)) {
            ads = new address[](1);
            ads[0] = a0;
        } else {
            ads = new address[](2);
            ads[0] = a0;
            ads[1] = a1;
        }
        vm.chainId(e.localChainId());
        vm.prank(owner);
        e.setRoute(chainId, policy, ads, peer);
    }

    /// @dev Mock layer A, ONE, on every pair.
    function _routesMockOne() internal {
        _route(gw, BSC, ONE, address(aXL), address(0), address(mBsc));
        _route(gw, BASE, ONE, address(aXL), address(0), address(mBase));
        _route(mBsc, XL, ONE, address(aBSC), address(0), address(gw));
        _route(mBase, XL, ONE, address(aBASE), address(0), address(gw));
    }

    function _routesLzOne() internal {
        _route(gw, BSC, ONE, address(lXL), address(0), address(mBsc));
        _route(gw, BASE, ONE, address(lXL), address(0), address(mBase));
        _route(mBsc, XL, ONE, address(lBSC), address(0), address(gw));
        _route(mBase, XL, ONE, address(lBASE), address(0), address(gw));
    }

    function _routesLzHubAll() internal {
        _route(gw, BSC, ALL, address(lXL), address(hXL), address(mBsc));
        _route(mBsc, XL, ALL, address(lBSC), address(hBSC), address(gw));
    }

    // ------------------------------------------------------------------ actions

    function _bridge(TapBridgeEndpoint e, address who, uint256 id, uint64 dst, address to)
        internal
        returns (bytes32 messageId)
    {
        vm.chainId(e.localChainId());
        bytes[] memory opts = new bytes[](0);
        (uint256 total,) = e.quoteBridge(id, dst, to, opts);
        vm.prank(who);
        messageId = e.bridge{value: total}(id, dst, to, false, opts);
    }

    function _deliverMock(MockAdapter src, MockAdapter dst) internal {
        bytes memory frame = src.lastPayload();
        vm.chainId(dst.localChainId());
        dst.deliver(src.localChainId(), frame);
    }

    function _deliverLz(MockEndpointV2 src, MockEndpointV2 dst, uint64 dstChain) internal {
        MockEndpointV2.Packet memory p = src.getPacket(src.packetCount() - 1);
        vm.chainId(dstChain);
        dst.deliver(p);
    }

    struct HubMsg {
        uint64 srcChainId;
        uint256 outboxIndex;
        bytes32 ref;
        bytes frame;
    }

    /// @dev Reads the last `Sent` log of `hub` from recorded logs (vm.recordLogs must be active).
    function _lastHubMsg(MockHub hub, uint64 srcChainId) internal returns (HubMsg memory m) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        bytes32 topic = keccak256("Sent(bytes32,address,bytes32,uint256,uint256,bytes)");
        for (uint256 i = logs.length; i > 0; --i) {
            Vm.Log memory l = logs[i - 1];
            if (l.emitter == address(hub) && l.topics[0] == topic) {
                (, uint256 outboxIndex, bytes memory payload) = abi.decode(l.data, (uint256, uint256, bytes));
                return HubMsg(srcChainId, outboxIndex, l.topics[3], payload);
            }
        }
        revert("no Sent log");
    }

    function _sign(HubRelayAdapter dst, HubMsg memory m, address fromContainer, uint256[] memory keyIdx)
        internal
        view
        returns (bytes memory sigs)
    {
        bytes32 digest = keccak256(abi.encodePacked(m.ref, keccak256(m.frame)));
        bytes32 h = dst.hubMessageHash(m.srcChainId, fromContainer, m.outboxIndex, digest);
        for (uint256 i; i < keyIdx.length; ++i) {
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(attesterKeys[keyIdx[i]], h);
            sigs = abi.encodePacked(sigs, r, s, v);
        }
    }

    function _deliverHub(HubRelayAdapter dst, HubMsg memory m) internal {
        uint256[] memory k = new uint256[](2);
        k[0] = 0;
        k[1] = 2;
        vm.chainId(dst.localChainId());
        bytes memory sigs = _sign(dst, m, dst.remoteContainer(m.srcChainId), k);
        vm.prank(relayer);
        dst.deliver(m.srcChainId, m.outboxIndex, m.ref, m.frame, sigs);
    }

    function _b32(address a) internal pure returns (bytes32) {
        return bytes32(uint256(uint160(a)));
    }

    function _approveGw(address who, uint256 id) internal {
        vm.chainId(XL);
        vm.prank(who);
        legacy.approve(address(gw), id);
    }
}
