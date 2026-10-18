// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BridgeFixture} from "../bridge/BridgeFixture.sol";
import {TapBridgeEndpoint} from "../../src/bridge/TapBridgeEndpoint.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {TapMirror} from "../../src/bridge/TapMirror.sol";
import {MockAdapter} from "../bridge/mocks/MockAdapter.sol";
import {HubRelayAdapter} from "../../src/bridge/HubRelayAdapter.sol";
import {ERC721Min} from "../../src/vendor/ERC721Min.sol";
import {TapBridgePayload} from "../../src/bridge/TapBridgePayload.sol";
import {TapAdapterBase} from "../../src/bridge/TapAdapterBase.sol";

/// A legacy-style ERC-721 that does NOT clear the per-token approval on transfer (pre-standard behaviour).
contract StaleApproval721 {
    mapping(uint256 => address) public ownerOf;
    mapping(uint256 => address) public getApproved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;

    function mint(address to, uint256 id) external {
        ownerOf[id] = to;
    }

    function approve(address to, uint256 id) external {
        require(msg.sender == ownerOf[id]);
        getApproved[id] = to;
    }

    function setApprovalForAll(address op, bool ok) external {
        isApprovedForAll[msg.sender][op] = ok;
    }

    function transferFrom(address from, address to, uint256 id) external {
        address o = ownerOf[id];
        require(o == from && to != address(0));
        require(msg.sender == o || isApprovedForAll[o][msg.sender] || getApproved[id] == msg.sender, "auth");
        ownerOf[id] = to; // approval intentionally kept
    }
}

/// Security-review PoCs for bridge/ (reviews/security-contracts.md).
contract AuditBridgeTest is BridgeFixture {
    /// B-1 (L-1, fixed): a recipient equal to the destination endpoint, or to the sending endpoint, is refused at
    /// departure (EndpointRecipient), and an arriving payload whose recipient is the receiving endpoint reverts
    /// instead of minting to it.
    function test_audit_recipientIsDestinationEndpoint_tokenLost() public {
        _routesMockOne();
        _approveGw(alice, 7);
        vm.chainId(XL);
        bytes[] memory opts = new bytes[](0);
        (uint256 fee,) = gw.quoteBridge(7, BSC, address(mBsc), opts);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.EndpointRecipient.selector, address(mBsc)));
        gw.bridge{value: fee}(7, BSC, address(mBsc), true, opts);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.EndpointRecipient.selector, address(gw)));
        gw.bridge{value: fee}(7, BSC, address(gw), true, opts);
        assertEq(legacy.ownerOf(7), alice);
        // arrival side: a payload naming the mirror itself as recipient does not execute
        _bridge(gw, alice, 7, BSC, bob);
        TapBridgePayload.Payload memory p = this.decodeExt(aXL.lastPayload());
        p.to = address(mBsc);
        p.nonce = 77;
        vm.chainId(BSC);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.EndpointRecipient.selector, address(mBsc)));
        aBSC.deliver(XL, TapBridgePayload.encode(p));
    }

    /// B-1b (fixed): on the way home, the gateway as recipient is refused at the mirror.
    function test_audit_recipientIsGateway_tokenLost() public {
        _routesMockOne();
        _approveGw(alice, 7);
        _bridge(gw, alice, 7, BSC, bob);
        _deliverMock(aXL, aBSC);
        vm.chainId(BSC);
        bytes[] memory opts = new bytes[](0);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.EndpointRecipient.selector, address(gw)));
        mBsc.bridge{value: 0.0001 ether}(7, XL, address(gw), true, opts);
        assertEq(mBsc.ownerOf(7), bob);
    }

    /// B-2 (L-2, fixed): the message id is keccak256(srcEndpoint ‖ payload). After the gateway is replaced before
    /// sealing, the new gateway's nonce restarts at 0 and its payload is byte-identical to the old one's, but the
    /// message id differs, so the legitimate message executes.
    function test_audit_redeployedEndpointMessageIdCollision() public {
        _routesMockOne();
        _approveGw(alice, 7);
        bytes32 id1 = _bridge(gw, alice, 7, BSC, bob);
        bytes memory payload1 = aXL.lastPayload();
        _deliverMock(aXL, aBSC);
        _bridge(mBsc, bob, 7, XL, alice);
        _deliverMock(aBSC, aXL);

        vm.chainId(XL);
        TapGateway gw2 = new TapGateway(address(legacy), address(ds), owner);
        MockAdapter a2XL = new MockAdapter(address(gw2), 0.0001 ether);
        a2XL.setRemote(BSC, address(mBsc));
        vm.chainId(BSC);
        MockAdapter a2BSC = new MockAdapter(address(mBsc), 0.0001 ether);
        a2BSC.setRemote(XL, address(gw2));
        _route(TapBridgeEndpoint(address(gw2)), BSC, ONE, address(a2XL), address(0), address(mBsc));
        _route(mBsc, XL, ONE, address(a2BSC), address(0), address(gw2));

        vm.chainId(XL);
        vm.prank(alice);
        legacy.approve(address(gw2), 7);
        bytes32 id2 = _bridge(TapBridgeEndpoint(address(gw2)), alice, 7, BSC, bob);
        assertEq(gw2.nextNonce(), 1, "nonce restarted");
        assertEq(keccak256(a2XL.lastPayload()), keccak256(payload1), "byte-identical payload");
        assertTrue(id1 != id2, "different message ids");
        _deliverMock(a2XL, a2BSC);
        assertEq(mBsc.ownerOf(7), bob);
        assertTrue(mBsc.executed(id2));
    }

    /// B-3 (L-3, fixed): with a home collection that keeps per-token approvals across transfers, the gateway
    /// still refuses to lock a token it already holds in escrow (AlreadyEscrowed).
    function test_audit_staleApprovalRedepartsEscrowedToken() public {
        vm.chainId(XL);
        StaleApproval721 c = new StaleApproval721();
        TapGateway g = new TapGateway(address(c), address(0), owner);
        MockAdapter ax = new MockAdapter(address(g), 0);
        ax.setRemote(BSC, address(0xB5C));
        ax.setRemote(BASE, address(0xBA5E));
        address[] memory ads = new address[](1);
        ads[0] = address(ax);
        vm.startPrank(owner);
        g.setRoute(BSC, ONE, ads, address(0xB5C));
        g.setRoute(BASE, ONE, ads, address(0xBA5E));
        vm.stopPrank();

        c.mint(alice, 1);
        vm.startPrank(alice);
        c.setApprovalForAll(address(g), true);
        c.approve(bob, 1); // e.g. an old marketplace listing
        g.bridge(1, BSC, alice, false, new bytes[](0));
        vm.stopPrank();
        assertEq(c.ownerOf(1), address(g));

        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(TapGateway.AlreadyEscrowed.selector, uint256(1)));
        g.bridge(1, BASE, bob, false, new bytes[](0));
        assertEq(g.locationOf(1), BSC);
        assertEq(ax.dsts(0), BSC);
    }

    /// B-4 (M-3, fixed): sealRoutes() requires every listed adapter to be sealed; sealing the LayerZero adapter
    /// removes the EndpointV2 delegate and the owner, so neither the delegate nor peers can change afterwards.
    function test_audit_adapterDelegateChangeableAfterSeal() public {
        _routesLzOne();
        vm.chainId(XL);
        vm.prank(owner);
        vm.expectRevert(abi.encodeWithSelector(TapBridgeEndpoint.AdapterNotSealed.selector, address(lXL)));
        gw.sealRoutes();
        uint32[] memory eids = new uint32[](2);
        eids[0] = 30102;
        eids[1] = 30184;
        _pinLz(lXL, lzXL, eids); // N-3: libraries and receive config pinned before the seal
        vm.chainId(XL);
        vm.prank(owner);
        lXL.seal();
        assertEq(lzXL.delegates(address(lXL)), address(0));
        vm.prank(owner);
        gw.sealRoutes();
        assertTrue(gw.routesSealed());
        address attacker = makeAddr("attacker");
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.NotOwner.selector);
        lXL.setDelegate(attacker);
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.NotOwner.selector);
        lXL.setPeer(10, 30110, bytes32(uint256(1)), address(1));
        vm.prank(owner);
        vm.expectRevert(TapAdapterBase.NotOwner.selector);
        lXL.transferOwnership(attacker);
        assertEq(lzXL.delegates(address(lXL)), address(0));
    }

    /// Sound: high-s (malleated) signatures and signatures made for another destination adapter's domain
    /// are rejected; the honest pair is accepted.
    function test_audit_hubRejectsMalleatedAndForeignDomainSignatures() public {
        _routesLzHubAll();
        _approveGw(alice, 7);
        vm.recordLogs();
        _bridge(gw, alice, 7, BSC, bob);
        HubMsg memory m = _lastHubMsg(hubXL, XL);
        vm.chainId(BSC);
        address from = hBSC.remoteContainer(XL);
        uint256[] memory k = new uint256[](2);
        k[0] = 0;
        k[1] = 1;
        bytes memory good = _sign(hBSC, m, from, k);

        // malleate the first signature: s' = n - s, v' = v ^ 1 (recovers the same signer)
        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes memory bad = bytes.concat(good);
        uint256 sv;
        assembly {
            sv := mload(add(bad, 0x40))
        }
        uint256 s2 = n - sv;
        assembly {
            mstore(add(bad, 0x40), s2)
        }
        bad[64] = bad[64] == bytes1(uint8(27)) ? bytes1(uint8(28)) : bytes1(uint8(27));
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, bad);

        // signatures over the Base adapter's domain do not verify on BNB Smart Chain
        vm.chainId(BASE);
        bytes memory foreign = _sign(hBASE, m, from, k);
        vm.chainId(BSC);
        vm.expectRevert(HubRelayAdapter.BadSignatures.selector);
        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, foreign);

        hBSC.deliver(XL, m.outboxIndex, m.ref, m.frame, good);
        assertTrue(mBsc.confirmedBy(TapBridgePayload.messageId(address(gw), m.frame), address(hBSC)));
    }

    function decodeExt(bytes calldata b) external pure returns (TapBridgePayload.Payload memory) {
        return TapBridgePayload.decode(b);
    }
}
