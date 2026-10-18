// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {console2, Vm} from "forge-std/Test.sol";
import {BridgeFixture} from "./BridgeFixture.sol";
import {TapBridgeEndpoint} from "../../src/bridge/TapBridgeEndpoint.sol";
import {TapBridgePayload} from "../../src/bridge/TapBridgePayload.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {TapMirror} from "../../src/bridge/TapMirror.sol";
import {TapAdapterBase} from "../../src/bridge/TapAdapterBase.sol";
import {LayerZeroV2Adapter} from "../../src/bridge/LayerZeroV2Adapter.sol";
import {HubRelayAdapter} from "../../src/bridge/HubRelayAdapter.sol";
import {Origin} from "../../src/bridge/ILayerZeroEndpointV2Min.sol";
import {MockAdapter} from "./mocks/MockAdapter.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";
import {MockEndpointV2, MockReceiveUln} from "./mocks/MockEndpointV2.sol";
import {MockLegacy721, MockDataSource, NoOpTransfer721} from "./mocks/MockERC721s.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {ITapBridgeEndpoint} from "../../src/interfaces/ITapBridge.sol";
import {ITapBridgeTransfer} from "../../src/interfaces/ITapBridgeTransfer.sol";
import {ITapBridgeMirror} from "../../src/interfaces/ITapBridgeMirror.sol";

contract TapBridgeTest is BridgeFixture {
    // ================================================================== round trips (mock layer, ONE)

    function test_roundTrip_home_remote_home() public {
        _routesMockOne();
        _approveGw(alice, 7);
        bytes32 id1 = _bridge(gw, alice, 7, BSC, bob);
        vm.chainId(XL);
        assertEq(legacy.ownerOf(7), address(gw), "escrowed");
        assertTrue(gw.departed(id1));

        _deliverMock(aXL, aBSC);
        assertEq(mBsc.ownerOf(7), bob);
        assertTrue(mBsc.executed(id1));
        assertEq(mBsc.netlistHashOf(7), NETLIST);
        assertEq(mBsc.imageHashOf(7), IMAGE);
        assertEq(mBsc.manifestHash(), MANIFEST);
        assertTrue(mBsc.knownNetlist(NETLIST));
        assertEq(mBsc.tokenURI(7), "ipfs://mirror/7");

        bytes32 id2 = _bridge(mBsc, bob, 7, XL, carol);
        vm.expectRevert();
        mBsc.ownerOf(7); // burned
        _deliverMock(aBSC, aXL);
        assertEq(legacy.ownerOf(7), carol);
        assertTrue(gw.executed(id2));
        assertTrue(id1 != id2);
    }

    /// Hub-and-spoke: a mirror routes only to the home chain; BSC → Base is two hops through home.
    function test_remoteToRemote_hops() public {
        _routesMockOne();
        address[] memory ads = new address[](1);
        ads[0] = address(aBSC);
        vm.chainId(BSC);
        vm.prank(owner);
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        mBsc.setRoute(BASE, ONE, ads, address(mBase));
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, alice);
        _deliverMock(aXL, aBSC);
        _bridge(mBsc, alice, 7, XL, alice);
        _deliverMock(aBSC, aXL);
        vm.chainId(XL);
        vm.prank(alice);
        legacy.approve(address(gw), 7);
        _bridge(gw, alice, 7, BASE, bob);
        _deliverMock(aXL, aBASE);
        assertEq(mBase.ownerOf(7), bob);
        assertEq(mBase.netlistHashOf(7), NETLIST);
        assertEq(mBase.manifestHash(), MANIFEST);
        _bridge(mBase, bob, 7, XL, carol);
        _deliverMock(aBASE, aXL);
        vm.chainId(XL);
        assertEq(legacy.ownerOf(7), carol);
    }

    function test_approvedOperatorCanBridge_strangerCannot() public {
        _routesMockOne();
        vm.chainId(XL);
        vm.prank(alice);
        legacy.setApprovalForAll(address(gw), true);
        bytes[] memory o = new bytes[](0);
        vm.prank(bob);
        vm.expectRevert(TapGateway.NotAuthorized.selector);
        gw.bridge{value: 0.0001 ether}(7, BSC, bob, false, o);
        vm.prank(alice);
        legacy.setApprovalForAll(bob, true);
        vm.prank(bob);
        gw.bridge{value: 0.0001 ether}(7, BSC, bob, false, o);
        assertEq(legacy.ownerOf(7), address(gw));
    }

    function test_zeroRecipient_andClosedRoute() public {
        _routesMockOne();
        _approveGw(alice, 7);
        bytes[] memory o = new bytes[](0);
        vm.prank(alice);
        vm.expectRevert(TapBridgeEndpoint.ZeroRecipient.selector);
        gw.bridge{value: 1 ether}(7, BSC, address(0), false, o);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.RouteClosed.selector, uint64(10)));
        gw.bridge{value: 1 ether}(7, 10, bob, false, o);
    }

    function test_contractRecipient_needsAcknowledgement() public {
        _routesMockOne();
        _approveGw(alice, 7);
        bytes[] memory o = new bytes[](0);
        address wallet = address(new MockAdapter(address(1), 0)); // any contract
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.ContractRecipient.selector, wallet));
        gw.bridge{value: 0.0001 ether}(7, BSC, wallet, false, o);
        // an EIP-7702 delegated account counts as a plain account
        address eoa7702 = makeAddr("7702");
        vm.etch(eoa7702, abi.encodePacked(hex"ef0100", address(0xD00D)));
        vm.prank(alice);
        gw.bridge{value: 0.0001 ether}(7, BSC, eoa7702, false, o);
        _deliverMock(aXL, aBSC);
        assertEq(mBsc.ownerOf(7), eoa7702);
        // explicit acknowledgement lets a contract recipient through
        _approveGw(alice, 8);
        vm.prank(alice);
        gw.bridge{value: 0.0001 ether}(8, BSC, wallet, true, o);
        _deliverMock(aXL, aBSC);
        assertEq(mBsc.ownerOf(8), wallet);
    }

    function test_gateway_bindFirstAfterReveal_andEscrowFlag() public {
        _routesMockOne();
        _approveGw(alice, 8);
        vm.chainId(XL);
        ds.setSeed(keccak256("seed")); // revealed; token 8 has no hashes bound
        bytes[] memory o = new bytes[](0);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotBound.selector, uint256(8)));
        gw.bridge{value: 0.0001 ether}(8, BSC, bob, false, o);
        ds.set(8, NETLIST, IMAGE); // bound now (both fields the manifest defines)
        vm.prank(alice);
        gw.bridge{value: 0.0001 ether}(8, BSC, bob, false, o);
        assertEq(gw.locationOf(8), BSC);
        _deliverMock(aXL, aBSC);
        _bridge(mBsc, bob, 8, XL, alice);
        _deliverMock(aBSC, aXL);
        assertEq(gw.locationOf(8), 0);
        assertEq(legacy.ownerOf(8), alice);
    }

    /// Per-route accounting: a token recorded on BSC cannot be released by a message on the Base route.
    function test_gateway_perRouteAccounting() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        TapBridgePayload.Payload memory p = TapBridgePayload.Payload({
            collectionKey: gw.collectionKey(),
            tokenId: 7,
            to: carol,
            netlistHash: 0,
            imageHash: 0,
            manifestHash: 0,
            srcChainId: BASE,
            dstChainId: XL,
            nonce: 0
        });
        vm.chainId(XL);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotOnRoute.selector, uint256(7), BASE));
        aXL.deliver(BASE, TapBridgePayload.encode(p)); // e.g. a compromised Base route
        assertEq(gw.locationOf(7), BSC);
    }

    /// N-3: a LayerZero adapter cannot be sealed while any configured eid follows default libraries or config.
    function test_lz_sealRequiresPinnedConfig() public {
        vm.chainId(XL);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(LayerZeroV2Adapter.NotPinned.selector, uint32(30102)));
        lXL.seal();
        uint32[] memory one = new uint32[](1);
        one[0] = 30102;
        _pinLz(lXL, lzXL, one); // BSC pinned, Base still default
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(LayerZeroV2Adapter.NotPinned.selector, uint32(30184)));
        lXL.seal();
        // a pinned library with a default (zero) confirmations config is not enough either
        vm.startPrank(owner);
        lzXL.setSendLibrary(address(lXL), 30184, address(0x5E7D));
        MockReceiveUln uln = new MockReceiveUln(address(lzXL));
        lzXL.setReceiveLibrary(address(lXL), 30184, address(uln), 0);
        vm.expectRevert(abi.encodeWithSelector(LayerZeroV2Adapter.NotPinned.selector, uint32(30184)));
        lXL.seal();
        vm.stopPrank();
        one[0] = 30184;
        _pinLz(lXL, lzXL, one);
        // a previous receive library still in its grace period blocks the seal
        vm.prank(owner);
        lzXL.setReceiveLibraryTimeout(address(lXL), 30184, address(0xBEEF), block.number + 10);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(LayerZeroV2Adapter.NotPinned.selector, uint32(30184)));
        lXL.seal();
        vm.roll(block.number + 11);
        vm.prank(owner);
        lXL.seal();
        assertTrue(lXL.adapterSealed());
        assertEq(lzXL.delegates(address(lXL)), address(0));
    }

    /// A partly bound token (image only, while the manifest also defines netlists) does not depart.
    function test_gateway_everyManifestFieldMustBeBound() public {
        _routesMockOne();
        _approveGw(alice, 8);
        vm.chainId(XL);
        ds.setSeed(keccak256("seed"));
        ds.set(8, 0, IMAGE); // image bound, netlist not
        bytes[] memory o = new bytes[](0);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotBound.selector, uint256(8)));
        gw.bridge{value: 0.0001 ether}(8, BSC, bob, false, o);
        ds.setPoolFields(1); // an image-only manifest: the image alone suffices
        vm.prank(alice);
        gw.bridge{value: 0.0001 ether}(8, BSC, bob, false, o);
        assertEq(gw.locationOf(8), BSC);
    }

    /// §5.2: the gateway reverts unless ownerOf is the gateway after transferFrom.
    function test_gateway_escrowFailed() public {
        vm.chainId(XL);
        NoOpTransfer721 c = new NoOpTransfer721();
        TapGateway g = new TapGateway(address(c), address(0), owner);
        MockAdapter ad = new MockAdapter(address(g), 0);
        ad.setRemote(BSC, address(mBsc));
        address[] memory ads = new address[](1);
        ads[0] = address(ad);
        vm.prank(owner);
        g.setRoute(BSC, ONE, ads, address(mBsc));
        c.mint(alice, 1);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.EscrowFailed.selector, uint256(1)));
        g.bridge(1, BSC, alice, false, new bytes[](0));
    }

    function test_adapter_cannotRenounceWithoutSeal() public {
        vm.chainId(XL);
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.ZeroOwner.selector);
        lXL.transferOwnership(address(0));
    }

    function test_hubAdapter_seal() public {
        vm.chainId(XL);
        vm.prank(owner);
        hXL.seal();
        assertTrue(hXL.adapterSealed());
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.NotOwner.selector);
        hXL.setRemote(10, address(1), address(2), address(3));
    }

    // ================================================================== fees

    function test_fees_quote_refund_insufficient() public {
        _route(gw, BSC, ALL, address(aXL), address(bXL), address(mBsc));
        _approveGw(alice, 7);
        bytes[] memory o = new bytes[](0);
        (uint256 total, uint256[] memory fees) = gw.quoteBridge(7, BSC, bob, o);
        assertEq(total, 0.0003 ether);
        assertEq(fees.length, 2);
        assertEq(fees[1], 0.0002 ether);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.InsufficientFee.selector, total, total - 1));
        gw.bridge{value: total - 1}(7, BSC, bob, false, o);
        uint256 before = alice.balance;
        vm.prank(alice);
        gw.bridge{value: 1 ether}(7, BSC, bob, false, o);
        assertEq(before - alice.balance, total, "excess refunded");
        bytes[] memory bad = new bytes[](1);
        vm.prank(alice);
        vm.expectRevert(TapBridgeEndpoint.BadOptions.selector);
        gw.bridge{value: 1 ether}(8, BSC, bob, false, bad);
    }

    // ================================================================== LayerZero ONE

    function test_lz_one_roundTrip_withGas() public {
        _routesLzOne();
        _approveGw(alice, 7);
        vm.chainId(XL);
        bytes[] memory o = new bytes[](0);
        (uint256 fee,) = gw.quoteBridge(7, BSC, bob, o);
        assertEq(fee, 0.001 ether + 1 gwei * 320, "message = the 320-byte payload");
        uint256 g = gasleft();
        vm.prank(alice);
        gw.bridge{value: fee}(7, BSC, bob, false, o);
        console2.log("gas LZ ONE gateway.bridge (lock+send, mock endpoint)", g - gasleft());

        MockEndpointV2.Packet memory p = lzXL.getPacket(0);
        assertEq(p.dstEid, 30102);
        assertEq(p.receiver, _b32(address(lBSC)));
        assertEq(p.options, lXL.defaultOptions());
        assertEq(p.options, hex"00030100110100000000000000000000000000061a80");
        vm.chainId(BSC);
        g = gasleft();
        lzBSC.deliver(p);
        console2.log("gas LZ ONE mirror arrival (lzReceive->mint)", g - gasleft());
        assertEq(mBsc.ownerOf(7), bob);

        _bridge(mBsc, bob, 7, XL, alice);
        _deliverLz(lzBSC, lzXL, XL);
        assertEq(legacy.ownerOf(7), alice);
    }

    function test_lz_replay_rejected() public {
        _routesLzOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        MockEndpointV2.Packet memory p = lzXL.getPacket(0);
        vm.chainId(BSC);
        lzBSC.deliver(p);
        vm.expectRevert();
        lzBSC.deliver(p);
        // even after the token left again, the old message cannot re-mint it
        _bridge(mBsc, bob, 7, XL, alice);
        vm.chainId(BSC);
        bytes32 mid = TapBridgePayload.messageId(address(gw), p.message);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.Replay.selector, mid));
        lzBSC.deliver(p);
    }

    function test_lz_wrongPeer_rejected() public {
        _routesLzOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        MockEndpointV2.Packet memory p = lzXL.getPacket(0);
        vm.chainId(BSC);
        // forged origin: right eid, wrong sender
        Origin memory o = Origin(30274, _b32(address(0xBEEF)), 1);
        assertFalse(lBSC.allowInitializePath(o));
        vm.expectRevert(TapAdapterBase.WrongPeer.selector);
        lzBSC.deliverRaw(address(lBSC), o, p.message);
        // only the endpoint may call lzReceive
        vm.expectRevert(LayerZeroV2Adapter.NotLzEndpoint.selector);
        lBSC.lzReceive(Origin(30274, _b32(address(lXL)), 1), bytes32(0), p.message, address(0), "");
        // a listed adapter that names a source endpoint other than the route's peer is refused by the endpoint
        vm.prank(address(lBSC));
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.WrongPeer.selector, address(0xBAD)));
        mBsc.receivePayload(XL, address(0xBAD), p.message);
    }

    function test_lz_peersSetOnce_andOnlyEndpointSends() public {
        vm.chainId(BSC);
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.AlreadySet.selector);
        lBSC.setPeer(XL, 30274, _b32(address(1)), address(gw));
        vm.expectRevert(TapAdapterBase.NotEndpoint.selector);
        lBSC.send(XL, new bytes(320), "", address(this));
        assertEq(lzBSC.delegates(address(lBSC)), owner);
        assertEq(lBSC.nextNonce(30274, _b32(address(lXL))), 0);
    }

    // ================================================================== ALL (LayerZero + hub)

    function test_all_lzAndHub_requiresBoth() public {
        _routesLzHubAll();
        _approveGw(alice, 7);
        vm.recordLogs();
        bytes32 mid = _bridge(gw, alice, 7, BSC, bob);
        HubMsg memory hm = _lastHubMsg(hubXL, XL);
        assertEq(hm.ref, mid, "ref = messageId");

        _deliverLz(lzXL, lzBSC, BSC);
        assertTrue(mBsc.confirmedBy(mid, address(lBSC)));
        assertFalse(mBsc.executed(mid));
        vm.expectRevert();
        mBsc.ownerOf(7); // LayerZero alone does not mint

        uint256 g = gasleft();
        _deliverHub(hBSC, hm);
        console2.log("gas ALL second confirmation (hub deliver, 2-of-3 sigs, mint)", g - gasleft());
        assertTrue(mBsc.executed(mid));
        assertEq(mBsc.ownerOf(7), bob);
    }

    function test_all_hubAlone_doesNotMint_thenLzCompletes() public {
        _routesLzHubAll();
        _approveGw(alice, 7);
        vm.recordLogs();
        bytes32 mid = _bridge(gw, alice, 7, BSC, bob);
        HubMsg memory hm = _lastHubMsg(hubXL, XL);
        _deliverHub(hBSC, hm);
        assertTrue(mBsc.confirmedBy(mid, address(hBSC)));
        assertFalse(mBsc.executed(mid));
        _deliverLz(lzXL, lzBSC, BSC);
        assertEq(mBsc.ownerOf(7), bob);

        // and back home under ALL
        vm.recordLogs();
        bytes32 back = _bridge(mBsc, bob, 7, XL, alice);
        HubMsg memory hb = _lastHubMsg(hubBSC, BSC);
        _deliverLz(lzBSC, lzXL, XL);
        vm.chainId(XL);
        assertEq(legacy.ownerOf(7), address(gw));
        _deliverHub(hXL, hb);
        assertEq(legacy.ownerOf(7), alice);
        assertTrue(gw.executed(back));
    }

    function test_all_mismatchedPayloads_neverExecute() public {
        _route(gw, BSC, ALL, address(aXL), address(bXL), address(mBsc));
        _route(mBsc, XL, ALL, address(aBSC), address(bBSC), address(gw));
        _approveGw(alice, 7);
        bytes32 mid = _bridge(gw, alice, 7, BSC, bob);
        bytes memory frameA = aXL.lastPayload();
        // layer B delivers a payload that differs in one field (recipient)
        bytes memory payload = frameA;
        TapBridgePayload.Payload memory p = this.decodeExt(payload);
        p.to = carol;
        bytes memory frameB = TapBridgePayload.encode(p);
        vm.chainId(BSC);
        aBSC.deliver(XL, frameA);
        bBSC.deliver(XL, frameB);
        bytes32 midB = TapBridgePayload.messageId(address(gw), TapBridgePayload.encode(p));
        assertFalse(mBsc.executed(mid));
        assertFalse(mBsc.executed(midB));
        assertTrue(mBsc.confirmedBy(mid, address(aBSC)));
        assertTrue(mBsc.confirmedBy(midB, address(bBSC)));
        vm.expectRevert();
        mBsc.ownerOf(7);
    }

    function test_all_sameAdapterTwice_rejected() public {
        _route(gw, BSC, ALL, address(aXL), address(bXL), address(mBsc));
        _approveGw(alice, 7);
        bytes32 mid = _bridge(gw, alice, 7, BSC, bob);
        bytes memory frameA = aXL.lastPayload();
        vm.chainId(BSC);
        // route on the mirror side must exist for the incoming direction
        _route(mBsc, XL, ALL, address(aBSC), address(bBSC), address(gw));
        vm.chainId(BSC);
        aBSC.deliver(XL, frameA);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.AlreadyConfirmed.selector, mid, address(aBSC)));
        aBSC.deliver(XL, frameA);
    }

    // ================================================================== stuck adapter and resend

    function test_all_stuckAdapter_recoveredByResendBeforeSeal() public {
        _route(gw, BSC, ALL, address(aXL), address(bXL), address(mBsc));
        _route(mBsc, XL, ALL, address(aBSC), address(bBSC), address(gw));
        _approveGw(alice, 7);
        bytes32 mid = _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC); // layer B never delivers
        assertFalse(mBsc.executed(mid));

        // owner replaces layer B with a new layer C on both sides (possible only before sealing)
        vm.chainId(XL);
        MockAdapter cXL = new MockAdapter(address(gw), 0);
        vm.chainId(BSC);
        MockAdapter cBSC = new MockAdapter(address(mBsc), 0);
        cXL.setRemote(BSC, address(mBsc));
        cBSC.setRemote(XL, address(gw));
        _route(gw, BSC, ALL, address(aXL), address(cXL), address(mBsc));
        _route(mBsc, XL, ALL, address(aBSC), address(cBSC), address(gw));

        // anyone resends the departed payload through layer C
        bytes memory payload = aXL.lastPayload();
        vm.chainId(XL);
        vm.prank(carol);
        gw.resend(payload, 1, "");
        _deliverMock(cXL, cBSC);
        assertTrue(mBsc.executed(mid));
        assertEq(mBsc.ownerOf(7), bob);

        // resend only for payloads this endpoint really sent
        payload[100] = 0x01;
        vm.chainId(XL);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.NotDeparted.selector, TapBridgePayload.messageId(address(gw), payload)));
        gw.resend(payload, 1, "");
    }

    // ================================================================== authentication at the endpoint

    function test_wrongAdapter_rejected() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        bytes memory frame = aXL.lastPayload();
        vm.chainId(BSC);
        // layer B adapter exists for the mirror but is not listed on the route
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.NotAdapter.selector, address(bBSC)));
        bBSC.deliver(XL, frame);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.NotAdapter.selector, address(this)));
        mBsc.receivePayload(XL, address(gw), frame);
    }

    function test_wrongSource_wrongDestination_wrongCollection() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        TapBridgePayload.Payload memory p = this.decodeExt(aXL.lastPayload());
        vm.chainId(BSC);
        // claims to come from Base while the frame arrives on the X Layer route
        TapBridgePayload.Payload memory q = p;
        q.srcChainId = BASE;
        vm.expectRevert(TapBridgeEndpoint.WrongSource.selector);
        aBSC.deliver(XL, TapBridgePayload.encode(q));
        q = this.decodeExt(aXL.lastPayload());
        q.dstChainId = BASE;
        vm.expectRevert(TapBridgeEndpoint.WrongDestination.selector);
        aBSC.deliver(XL, TapBridgePayload.encode(q));
        q = this.decodeExt(aXL.lastPayload());
        q.collectionKey = keccak256("other");
        vm.expectRevert(TapBridgeEndpoint.WrongCollection.selector);
        aBSC.deliver(XL, TapBridgePayload.encode(q));
        // non-canonical encodings are rejected
        bytes memory bad = TapBridgePayload.encode(p);
        bad[0] = 0x01; // high byte of the version word
        vm.expectRevert(TapBridgePayload.BadPayload.selector);
        aBSC.deliver(XL, bad);
        vm.expectRevert(TapBridgePayload.BadPayload.selector);
        aBSC.deliver(XL, abi.encodePacked(TapBridgePayload.encode(p), bytes1(0)));
    }

    function test_doubleMint_and_notEscrowed_guards() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC);
        // a second, different message for the same live token (only a broken/compromised layer could send it)
        TapBridgePayload.Payload memory p = this.decodeExt(aXL.lastPayload());
        p.nonce = 99;
        vm.chainId(BSC);
        vm.expectRevert(abi.encodeWithSelector(TapMirror.AlreadyLive.selector, uint256(7)));
        aBSC.deliver(XL, TapBridgePayload.encode(p));
        // a message releasing a token the gateway does not hold
        TapBridgePayload.Payload memory r = TapBridgePayload.Payload({
            collectionKey: gw.collectionKey(),
            tokenId: 8,
            to: bob,
            netlistHash: 0,
            imageHash: 0,
            manifestHash: 0,
            srcChainId: BSC,
            dstChainId: XL,
            nonce: 5
        });
        vm.chainId(XL);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.NotEscrowed.selector, uint256(8)));
        aXL.deliver(BSC, TapBridgePayload.encode(r));
    }

    function test_mirror_manifestConflict_and_range() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC);
        TapBridgePayload.Payload memory p = this.decodeExt(aXL.lastPayload());
        p.tokenId = 9;
        p.manifestHash = keccak256("another manifest");
        vm.chainId(BSC);
        vm.expectRevert(
            abi.encodeWithSelector(TapMirror.ManifestConflict.selector, MANIFEST, keccak256("another manifest"))
        );
        aBSC.deliver(XL, TapBridgePayload.encode(p));
        p.manifestHash = MANIFEST;
        p.tokenId = 10001;
        vm.expectRevert(abi.encodeWithSelector(TapMirror.OutOfRange.selector, uint256(10001)));
        aBSC.deliver(XL, TapBridgePayload.encode(p));
    }

    // ================================================================== route sealing

    function test_sealedRoutes() public {
        _routesMockOne();
        vm.chainId(XL);
        vm.prank(alice);
        address[] memory ads = new address[](1);
        ads[0] = address(aXL);
        vm.expectRevert(TapBridgeEndpoint.NotOwner.selector);
        gw.setRoute(BSC, ONE, ads, address(mBsc));
        // every adapter on any route must be sealed first
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.AdapterNotSealed.selector, address(aXL)));
        gw.sealRoutes();
        aXL.seal();
        assertTrue(aXL.adapterSealed());
        assertEq(aXL.owner(), address(0));
        vm.expectRevert(TapAdapterBase.NotOwner.selector);
        aXL.setRemote(10, address(1)); // no configuration after the adapter seal
        vm.prank(owner);
        gw.sealRoutes();
        assertTrue(gw.routesSealed());
        assertEq(gw.owner(), address(0));
        vm.prank(owner);
        vm.expectRevert(TapBridgeEndpoint.NotOwner.selector);
        gw.setRoute(BSC, ONE, ads, address(mBsc));
        // routes keep working after sealing
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC);
        assertEq(mBsc.ownerOf(7), bob);
    }

    function test_routeValidation() public {
        vm.chainId(XL);
        address[] memory two = new address[](2);
        two[0] = address(aXL);
        two[1] = address(aXL);
        vm.startPrank(owner);
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        gw.setRoute(BSC, ONE, two, address(mBsc)); // ONE needs exactly one
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        gw.setRoute(BSC, ALL, two, address(mBsc)); // duplicate adapter
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        gw.setRoute(XL, ONE, new address[](1), address(mBsc)); // own chain
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        gw.setRoute(BSC, 3, new address[](0), address(0)); // ANY does not exist
        two[1] = address(bXL);
        vm.expectRevert(TapBridgeEndpoint.BadRoute.selector);
        gw.setRoute(BSC, ALL, two, address(0)); // peer required
        gw.setRoute(BSC, ALL, two, address(mBsc));
        gw.setRoute(BSC, 0, new address[](0), address(0)); // close
        vm.stopPrank();
        (ITapBridgeEndpoint.Policy pol, address[] memory ads,) = gw.route(BSC);
        assertEq(uint8(pol), 0);
        assertEq(ads.length, 0);
    }

    // ================================================================== netlist on the mirror

    function test_mirror_materialize_and_netlistOf() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC);
        vm.chainId(BSC);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, NETLIST));
        mBsc.netlistOf(7);
        bytes memory other = hex"5441504e45540100000000020000000100000003000003";
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, sha256(other)));
        mBsc.materialize(other);
        vm.prank(carol); // permissionless
        uint256 g = gasleft();
        bytes32 h = mBsc.materialize(NETLIST_FILE);
        console2.log("gas materialize (23-byte tapnet/1)", g - gasleft());
        assertEq(h, NETLIST);
        assertEq(mBsc.netlistOf(7), NETLIST_FILE);
        assertEq(mBsc.netlistFile(NETLIST), NETLIST_FILE);
        assertEq(mBsc.storeNetlist(NETLIST_FILE), NETLIST); // idempotent
        // token 8 has no netlist bound at home
        vm.expectRevert(abi.encodeWithSelector(TapMirror.NotBound.selector, uint256(8)));
        mBsc.netlistOf(8);
    }

    function test_mirror_largeNetlist_chunked() public {
        // 7,000 NAND records = 16 + 49,000 bytes: three SSTORE2 chunks
        bytes memory file = new bytes(16 + 7 * 7000);
        bytes memory head = abi.encodePacked(hex"5441504e4554010000000002", uint32(1));
        for (uint256 i; i < 16; ++i) {
            file[i] = head[i];
        }
        for (uint256 i; i < 7000; ++i) {
            uint256 o = 16 + 7 * i;
            uint256 b = 3 + i; // NAND(2, 3 + i): input 2 and the previous element
            file[o + 3] = 0x02;
            file[o + 4] = bytes1(uint8(b >> 16));
            file[o + 5] = bytes1(uint8(b >> 8));
            file[o + 6] = bytes1(uint8(b));
        }
        bytes32 h = sha256(file);
        vm.chainId(XL);
        ds.set(8, h, 0);
        _routesMockOne();
        _approveGw(alice, 8);
        _bridge(gw, alice, 8, BSC, bob);
        _deliverMock(aXL, aBSC);
        vm.chainId(BSC);
        uint256 g = gasleft();
        mBsc.materialize(file);
        console2.log("gas materialize (49,016-byte tapnet/1)", g - gasleft());
        assertEq(keccak256(mBsc.netlistOf(8)), keccak256(file));
    }

    function test_mirror_badFile_rejected() public {
        bytes memory bad = hex"5441504e45540200000000020000000100000002000003"; // version 2
        vm.chainId(XL);
        ds.set(8, sha256(bad), 0);
        _routesMockOne();
        _approveGw(alice, 8);
        _bridge(gw, alice, 8, BSC, bob);
        _deliverMock(aXL, aBSC);
        vm.chainId(BSC);
        vm.expectRevert(TapNetlistCheck.TapnetBadHeader.selector);
        mBsc.materialize(bad);
    }

    function test_mirror_interfaces_and_emptyRevealSurface() public {
        vm.chainId(BSC);
        assertTrue(mBsc.supportsInterface(0x80ac58cd));
        assertTrue(mBsc.supportsInterface(0x5b5e139f));
        assertTrue(mBsc.supportsInterface(0x49064906));
        assertTrue(mBsc.supportsInterface(0x01ffc9a7));
        assertTrue(mBsc.supportsInterface(type(ITapNetlistNFT).interfaceId));
        assertTrue(mBsc.supportsInterface(type(ITapBridgeMirror).interfaceId));
        assertTrue(mBsc.supportsInterface(type(ITapBridgeEndpoint).interfaceId));
        assertTrue(mBsc.supportsInterface(type(ITapBridgeTransfer).interfaceId));
        assertFalse(mBsc.supportsInterface(0xffffffff));
        assertEq(mBsc.collection(), address(mBsc));
        assertEq(mBsc.pools().length, 0);
        assertEq(mBsc.masterSeed(), 0);
        assertFalse(mBsc.frozen());
        vm.expectRevert(TapMirror.NotHomeCollection.selector);
        mBsc.entryIndexOf(1, 0);
        (uint256 first, uint256 supply) = mBsc.tokenRange();
        assertEq(first, 1);
        assertEq(supply, 10000);
        assertEq(mBsc.collectionKey(), keccak256(abi.encode("TAP-NFT collection v1", uint64(196), address(legacy))));
        assertEq(mBsc.collectionKey(), gw.collectionKey());
        vm.chainId(XL);
        assertTrue(gw.supportsInterface(type(ITapBridgeEndpoint).interfaceId));
    }

    function test_mirror_emitsERC4906_onArrival() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        bytes memory frame = aXL.lastPayload();
        vm.chainId(BSC);
        vm.expectEmit(address(mBsc));
        emit IERC4906.MetadataUpdate(7);
        aBSC.deliver(XL, frame);
    }

    // ================================================================== legacy collection

    function test_legacy_collection_withCompanion() public {
        vm.chainId(XL);
        // the legacy contract keeps its own owner-controlled base URI and can freeze it; the gateway does not care
        legacy.setBaseURI("ipfs://tct1/");
        legacy.freezeBaseURI();
        assertEq(legacy.tokenURI(7), "ipfs://tct1/7");
        vm.expectRevert(bytes("uri"));
        legacy.setBaseURI("x");
        // a data source bound to another collection is refused
        MockDataSource wrong = new MockDataSource(address(0xC0FFEE));
        vm.expectRevert(TapGateway.WrongDataSource.selector);
        new TapGateway(address(legacy), address(wrong), owner);
        // no data source at all: zero hashes travel
        TapGateway plain = new TapGateway(address(legacy), address(0), owner);
        assertEq(plain.collectionKey(), gw.collectionKey());
        assertEq(address(gw.dataSource()), address(ds));
        // safeTransferFrom to the gateway is refused (no receiver hook), so nothing enters escrow by accident
        vm.prank(alice);
        vm.expectRevert();
        legacy.safeTransferFrom(alice, address(gw), 8);
    }

    // ================================================================== hub adapter specifics

    function test_hub_signatures() public {
        _routesLzHubAll();
        _approveGw(alice, 7);
        vm.recordLogs();
        _bridge(gw, alice, 7, BSC, bob);
        HubMsg memory m = _lastHubMsg(hubXL, XL);
        vm.chainId(BSC);
        address from = hBSC.remoteContainer(XL);

        uint256[] memory one = new uint256[](1);
        one[0] = 1;
        bytes memory s1 = _sign(hBSC, m, from, one);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, s1); // below threshold

        uint256[] memory desc = new uint256[](2);
        desc[0] = 2;
        desc[1] = 0;
        bytes memory sd = _sign(hBSC, m, from, desc);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, sd); // not ascending

        uint256[] memory dup = new uint256[](2);
        dup[0] = 1;
        dup[1] = 1;
        bytes memory sdup = _sign(hBSC, m, from, dup);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, sdup);

        _expectNonAttesterRejected(m, from);

        // signatures over another outbox index do not transfer
        uint256[] memory ok = new uint256[](2);
        ok[0] = 0;
        ok[1] = 1;
        bytes memory good = _sign(hBSC, m, from, ok);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex + 1, m.ref, m.frame, good);

        // ref must be the message id keccak256(srcEndpoint ‖ payload)
        vm.expectRevert(HubRelayAdapter.BadRef.selector);
        hBSC.deliver(XL, m.outboxIndex, bytes32(uint256(m.ref) ^ 1), m.frame, good);

        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, good);
        vm.expectRevert(HubRelayAdapter.AlreadyDelivered.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, good);
    }

    function test_hub_adapterMustHoldCircuit_andRejectsValue() public {
        _route(gw, BSC, ONE, address(hXL), address(0), address(mBsc));
        vm.chainId(XL);
        assertEq(hXL.quote(BSC, new bytes(320), ""), 0);
        // a hub adapter whose circuit is held by someone else cannot write
        HubRelayAdapter loose = new HubRelayAdapter(address(gw), address(hubXL), owner, attesterAddrs, 2);
        vm.prank(owner);
        vm.expectRevert(HubRelayAdapter.NotCircuitHolder.selector);
        loose.setCircuit(address(legacy), 7); // alice holds token 7, not the adapter
        vm.deal(address(gw), 1);
        vm.prank(address(gw));
        vm.expectRevert(HubRelayAdapter.ValueNotAccepted.selector);
        hXL.send{value: 1}(BSC, new bytes(320), "", address(0));
    }

    function test_hub_one_roundTrip_withGas() public {
        _route(gw, BSC, ONE, address(hXL), address(0), address(mBsc));
        _route(mBsc, XL, ONE, address(hBSC), address(0), address(gw));
        _approveGw(alice, 7);
        vm.recordLogs();
        vm.chainId(XL);
        bytes[] memory o = new bytes[](0);
        uint256 g = gasleft();
        vm.prank(alice);
        gw.bridge(7, BSC, bob, false, o);
        console2.log("gas HUB ONE gateway.bridge (lock + hub.send, mock hub)", g - gasleft());
        HubMsg memory m = _lastHubMsg(hubXL, XL);
        g = gasleft();
        _deliverHub(hBSC, m);
        console2.log("gas HUB ONE mirror arrival incl. 2 sigs (mint)", g - gasleft());
        assertEq(mBsc.ownerOf(7), bob);
    }

    // ================================================================== gas: mock layer baseline

    /// @dev Endpoint-only cost: the mock adapter stores nothing (light mode), so the numbers are the gateway /
    ///      mirror work (ERC-721 lock/burn/mint/release, data-source reads, payload, replay bookkeeping) plus
    ///      two external calls; add the message layer's own cost on top.
    function test_gas_endpointOnly() public {
        _routesMockOne();
        aXL.setLight(true);
        aBSC.setLight(true);
        _approveGw(alice, 7);
        vm.chainId(XL);
        bytes[] memory o = new bytes[](0);
        vm.recordLogs();
        uint256 g = gasleft();
        vm.prank(alice);
        gw.bridge{value: 0.0001 ether}(7, BSC, bob, false, o);
        console2.log("gas endpoint-only gateway.bridge (lock + payload)", g - gasleft());
        bytes memory frame = _lastFrameLog();
        vm.chainId(BSC);
        g = gasleft();
        aBSC.deliver(XL, frame);
        console2.log("gas endpoint-only mirror receive (ONE, mint + hashes)", g - gasleft());
        g = gasleft();
        vm.prank(bob);
        mBsc.bridge{value: 0.0001 ether}(7, XL, alice, false, o);
        console2.log("gas endpoint-only mirror.bridge (burn + payload)", g - gasleft());
        frame = _lastFrameLog();
        vm.chainId(XL);
        g = gasleft();
        aXL.deliver(BSC, frame);
        console2.log("gas endpoint-only gateway receive (ONE, release)", g - gasleft());
        assertEq(legacy.ownerOf(7), alice);
    }

    function _lastFrameLog() internal returns (bytes memory) {
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i = logs.length; i > 0; --i) {
            if (logs[i - 1].topics[0] == MockAdapter.Sent.selector) return abi.decode(logs[i - 1].data, (bytes));
        }
        revert("no frame");
    }

    // ================================================================== helpers

    function _expectNonAttesterRejected(HubMsg memory m, address from) internal {
        bytes32 h = hBSC.hubMessageHash(XL, from, m.outboxIndex, keccak256(abi.encodePacked(m.ref, keccak256(m.frame))));
        bytes memory a = _sig(attesterKeys[0], h);
        bytes memory b = _sig(0xBADBAD, h);
        bytes memory mixed = vm.addr(0xBADBAD) > attesterAddrs[0] ? abi.encodePacked(a, b) : abi.encodePacked(b, a);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, mixed);
    }

    function _sig(uint256 key, bytes32 h) internal pure returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, h);
        return abi.encodePacked(r, s, v);
    }

    function decodeExt(bytes calldata payload) external pure returns (TapBridgePayload.Payload memory) {
        return TapBridgePayload.decode(payload);
    }

}
