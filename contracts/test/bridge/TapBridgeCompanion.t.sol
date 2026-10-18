// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {BridgeFixture} from "./BridgeFixture.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {MockAdapter} from "./mocks/MockAdapter.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";

/// @notice The legacy-collection path end to end with the real draft-A companion (src/core/TapCompanion.sol)
///         as the gateway's data source: commit manifest → reveal → bind → bridge → materialize on the mirror.
contract TapBridgeCompanionTest is BridgeFixture {
    function test_legacy_withRealCompanion_toMirror() public {
        bytes memory fileA = NETLIST_FILE;
        bytes memory fileB = hex"5441504e45540100000000020000000100000003000002"; // NAND(3, 2)
        bytes32[2] memory img = [keccak256("img-a"), keccak256("img-b")];
        bytes32[2] memory net = [sha256(fileA), sha256(fileB)];

        vm.chainId(XL);
        TapCompanion comp = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), owner);
        bytes32[2] memory leaves;
        for (uint256 i; i < 2; ++i) {
            bytes32[] memory v = new bytes32[](2);
            v[0] = img[i];
            v[1] = net[i];
            leaves[i] = TapMerkle.leafHash(i, v);
        }
        ITapNetlistNFT.Pool[] memory pools = new ITapNetlistNFT.Pool[](1);
        pools[0] = ITapNetlistNFT.Pool("PAIR_V1", 3, TapMerkle.nodeHash(leaves[0], leaves[1]));
        vm.startPrank(owner);
        comp.commitManifest(MANIFEST, 7, 2, pools); // tokens 7 and 8
        comp.reveal(keccak256("seed"));
        vm.stopPrank();

        uint256 e = comp.entryIndexOf(7, 0);
        bytes32[] memory vals = new bytes32[](2);
        vals[0] = img[e];
        vals[1] = net[e];
        bytes32[] memory proof = new bytes32[](1);
        proof[0] = leaves[1 - e];
        comp.bind(7, 0, vals, proof);
        assertEq(comp.netlistHashOf(7), net[e]);

        TapGateway g2 = new TapGateway(address(legacy), address(comp), owner);
        MockAdapter a2 = new MockAdapter(address(g2), 0.0001 ether);
        a2.setRemote(BSC, address(mBsc));
        vm.chainId(BSC);
        MockAdapter b2 = new MockAdapter(address(mBsc), 0);
        b2.setRemote(XL, address(g2));
        _route(g2, BSC, ONE, address(a2), address(0), address(mBsc));
        // the mirror must point at this gateway; same collection key, so reuse mBsc with a fresh route peer
        _route(mBsc, XL, ONE, address(b2), address(0), address(g2));
        vm.chainId(XL);
        vm.prank(alice);
        legacy.approve(address(g2), 7);
        _bridge(g2, alice, 7, BSC, bob);
        _deliverMock(a2, b2);

        assertEq(mBsc.ownerOf(7), bob);
        assertEq(mBsc.netlistHashOf(7), net[e]);
        assertEq(mBsc.imageHashOf(7), img[e]);
        assertEq(mBsc.manifestHash(), MANIFEST);
        mBsc.materialize(e == 0 ? fileA : fileB);
        assertEq(mBsc.netlistOf(7), e == 0 ? fileA : fileB);
    }
}
