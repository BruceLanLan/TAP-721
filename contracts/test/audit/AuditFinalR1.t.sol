// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Vm} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {ITapNetlistTokenSet} from "../../src/interfaces/ITapNetlistTokenSet.sol";
import {ITapNetlistEval} from "../../src/interfaces/ITapNetlistEval.sol";
import {ITapCompanion} from "../../src/interfaces/ITapCompanion.sol";
import {ITapBridgeEndpoint} from "../../src/interfaces/ITapBridge.sol";
import {ITapBridgeTransfer} from "../../src/interfaces/ITapBridgeTransfer.sol";
import {ITapBridgeMirror} from "../../src/interfaces/ITapBridgeMirror.sol";
import {ITapBridgeAdapterSealed} from "../../src/interfaces/ITapBridgeAdapterSealed.sol";
import {ITapBridgeAdapter} from "../../src/interfaces/ITapBridge.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapMirror} from "../../src/bridge/TapMirror.sol";
import {TapBridgeEndpoint} from "../../src/bridge/TapBridgeEndpoint.sol";
import {CoreBase} from "../core/CoreBase.sol";
import {MerkleBuilder} from "../core/CoreHelpers.sol";
import {BridgeFixture} from "../bridge/BridgeFixture.sol";
import {TapAdapterBase} from "../../src/bridge/TapAdapterBase.sol";
import {LayerZeroV2Adapter} from "../../src/bridge/LayerZeroV2Adapter.sol";

/// Final-round conformance review (reviews/final-r1-conformance.md), core side.
/// Each review item that conflicted with the TAP text was resolved (text or code); these tests pin the
/// resulting conforming behaviour.
contract AuditFinalR1CoreTest is CoreBase {
    TapNetlistNFT nft;

    function setUp() public {
        _buildPools(16);
        nft = new TapNetlistNFT("Tape", "TAPE", "ipfs://base/", address(this));
    }

    /// Test Cases table: spec-literal ERC-165 ids, selectors and event topics (not `type(X).interfaceId`
    /// against itself).
    function test_r1_specLiteralIdsAndTopics() public pure {
        assertEq(type(ITapNetlistNFT).interfaceId, bytes4(0x282b67f6));
        assertEq(type(ITapNetlistTokenSet).interfaceId, bytes4(0x3f7177c7));
        assertEq(type(ITapCompanion).interfaceId, bytes4(0x12b40a6c));
        assertEq(type(ITapNetlistEval).interfaceId, bytes4(0xec7d7e20));
        assertEq(
            ITapNetlistNFT.ManifestCommitted.selector,
            bytes32(0x283da7c24290f991388adb4188dab383e865d9edad5d228e8b95805b85bba620)
        );
        assertEq(
            ITapNetlistNFT.Revealed.selector,
            bytes32(0xd5e62fe0c4e6bd40a7736fb2ab572a9a0f5e742f27741505011b9bc89c7ead19)
        );
        assertEq(
            ITapNetlistNFT.Bound.selector, bytes32(0x2893e106f460291bc3157184f05db4c33b0b5f3f34eccce325296bfaaa71436a)
        );
        assertEq(
            ITapNetlistNFT.NetlistStored.selector,
            bytes32(0x4095b27949435770a1b733b92eb73b92fb8d0c052ef06cf5db328010d57a64ed)
        );
        assertEq(
            ITapNetlistNFT.Frozen.selector, bytes32(0xa8cab3d1893ed53071b052fafa843143492f25d1d6b0170d460789f7ab1954be)
        );
        assertEq(
            ITapCompanion.Endorsed.selector, bytes32(0x403ec5d7987cb23abdef39abe83a6e7f084b84f0809eeda3c3a5b64df6679c56)
        );
        assertEq(
            IERC4906.MetadataUpdate.selector,
            bytes32(0xf8e1a15aba9398e019f0b49df1a4fde98ee17ae345cb5f6b5e2c27f5033e8ce7)
        );
        // bridging TAP
        assertEq(type(ITapBridgeEndpoint).interfaceId, bytes4(0x3d6a52e3));
        assertEq(type(ITapBridgeTransfer).interfaceId, bytes4(0xdbc2d1d3));
        assertEq(type(ITapBridgeMirror).interfaceId, bytes4(0xdba6a55e));
        assertEq(type(ITapBridgeAdapter).interfaceId, bytes4(0xaa621a3e));
        assertEq(type(ITapBridgeAdapterSealed).interfaceId, bytes4(0xceebf7ce));
        assertEq(
            ITapBridgeAdapterSealed.AdapterSealed.selector,
            bytes32(0x16ce24d3a7b82addfa23f273f6be525d4610ab33551f22d0ca872db8e9ffbe9e)
        );
        assertEq(TapMirror.NotHomeCollection.selector, bytes4(0xbbfa1ada));
    }

    /// Regression (§8.2 item 6): every commit emits ERC-4906 BatchMetadataUpdate over the covered range,
    /// (0, max) in token-set mode.
    function test_r1_commitEmitsMetadataUpdate() public {
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.ManifestCommitted(MANIFEST);
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.commitManifest(MANIFEST, FIRST, supply, ps);

        TapNetlistNFT b = new TapNetlistNFT("T", "T", "", address(this));
        vm.expectEmit(address(b));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        b.commitManifestNoReveal(MANIFEST, FIRST, supply, ps);

        TapNetlistNFT c = new TapNetlistNFT("T", "T", "", address(this));
        vm.expectEmit(address(c));
        emit ITapNetlistNFT.ManifestCommitted(MANIFEST);
        vm.expectEmit(address(c));
        emit IERC4906.BatchMetadataUpdate(0, type(uint256).max);
        c.commitManifestTokenSet(MANIFEST, keccak256("set"), supply, ps, false);
    }

    /// §5.2: a manifest whose single pool carries one field is valid; the field no pool carries stays zero
    /// (its value is fixed in metadata). Accepted on chain and by the Python checker.
    function test_r1_singleFieldManifest() public {
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("IMAGE_V1", 1, MerkleBuilder.root(imgLeaves));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
        nft.reveal(SEED);
        assertEq(nft.netlistHashOf(FIRST), 0); // can never get a netlist
    }

    /// Regression (§5.2 "entry values MUST NOT be zero"): loadPool and loadPoolChunk reject a zero value, as bind does.
    function test_r1_loadPoolRejectsZeroValue() public {
        bytes32[] memory vals = new bytes32[](supply);
        bytes32[] memory leaves = new bytes32[](supply);
        for (uint256 i; i < supply; ++i) {
            vals[i] = i == 3 ? bytes32(0) : netValues[i];
            leaves[i] = TapMerkle.leafHash(i, _one(vals[i]));
        }
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](2);
        ps[0] = ITapNetlistNFT.Pool("IMAGE_V1", 1, MerkleBuilder.root(imgLeaves));
        ps[1] = ITapNetlistNFT.Pool("NETLIST_V1", 2, MerkleBuilder.root(leaves));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadPool(1, vals);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadPoolChunk(1, 0, vals);
        assertFalse(nft.poolLoaded(1));
        nft.reveal(SEED);
        bytes32[] memory proof = MerkleBuilder.proof(leaves, 3);
        uint256 t;
        for (t = FIRST; t < FIRST + supply; ++t) {
            if (nft.entryIndexOf(t, 1) == 3) break;
        }
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.bind(t, 1, _one(bytes32(0)), proof);
    }

    /// §8.2 item 4: after loadPool and reveal, a netlist value becomes known only via markKnown(tokenId)
    /// (or bind); storeNetlist reverts until then, and before the reveal no path exists at all.
    function test_r1_loadedPoolNeedsMarkKnown() public {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        bytes32[] memory nets = netValues;
        nft.loadPool(1, nets);
        assertFalse(nft.knownNetlist(sha256(xorFile)));
        vm.expectRevert(); // NotBound: markKnown needs the seed
        nft.markKnown(FIRST);
        nft.reveal(SEED);
        assertFalse(nft.knownNetlist(sha256(xorFile)));
    }
}

/// Bridging TAP MUSTs without a dedicated test elsewhere.
contract AuditFinalR1BridgeTest is BridgeFixture {
    /// §5.2: the gateway MUST NOT implement onERC721Received, so safeTransferFrom into escrow fails.
    function test_r1_gatewayRejectsSafeTransfer() public {
        vm.chainId(XL);
        vm.prank(alice);
        vm.expectRevert();
        legacy.safeTransferFrom(alice, address(gw), 7);
        assertEq(legacy.ownerOf(7), alice);
    }

    /// §5.3: a mirror is deployed on a chain other than the home chain.
    function test_r1_mirrorOnHomeChainReverts() public {
        vm.chainId(XL);
        vm.expectRevert(TapMirror.SameChain.selector);
        new TapMirror(XL, address(legacy), "x", "x", "", 1, 10, owner);
    }

    /// P2-3 (regression, §8.3): an adapter cannot renounce outside seal(); seal() is the only way to drop the owner.
    function test_r1_adapterRenounceOnlyViaSeal() public {
        vm.chainId(XL);
        address o = aXL.owner();
        vm.prank(o);
        vm.expectRevert(TapAdapterBase.ZeroOwner.selector);
        aXL.transferOwnership(address(0));
        assertEq(aXL.owner(), o);
        vm.prank(o);
        aXL.seal();
        assertEq(aXL.owner(), address(0));
        assertTrue(aXL.adapterSealed());
    }

    /// Round 2 I-2 (§8.3): an adapter is never deployed ownerless-but-unsealed.
    function test_r2_adapterConstructorRejectsZeroOwner() public {
        vm.expectRevert(TapAdapterBase.ZeroOwner.selector);
        new LayerZeroV2Adapter(address(1), address(2), address(0), address(this), 400000);
    }
}
