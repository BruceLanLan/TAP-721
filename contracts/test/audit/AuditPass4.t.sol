// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TokenSetPack} from "../core/CoreHelpers.sol";
import {console2} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapGateway} from "../../src/bridge/TapGateway.sol";
import {TapContainerLock, IERC721Min, IContainerOpener, IDomainBinding} from "../../src/tools/TapContainerLock.sol";
import {MockAdapter} from "../bridge/mocks/MockAdapter.sol";
import {MockLegacy721} from "../bridge/mocks/MockERC721s.sol";
import {CoreBase} from "../core/CoreBase.sol";

contract LyingOpener is IContainerOpener {
    address public answer;

    constructor(address a) {
        answer = a;
    }

    function accountOf(address, uint256) external view returns (address) {
        return answer;
    }
}

/// Fourth pass: re-review of the P3-1 / P3-2 / P3-3 fixes and the TapContainerLock opener check.
contract AuditPass4Test is CoreBase {
    uint256 constant TX_CAP = 16_777_216;

    /// P3-3: a token set of exactly MAX_TOKENS ids loads in chunks that each fit a 16,777,216-gas transaction,
    /// including the completing chunk that re-reads and hashes the whole set. One more id is refused at commit.
    function test_audit_maxTokenSetLoadFitsTxCap() public {
        _buildPools(3);
        TapNetlistNFT c = new TapNetlistNFT("T", "T", "", address(this));
        uint256 n = c.MAX_TOKENS();
        uint256 per = c.IDS_PER_PAGE();
        uint32[] memory all = new uint32[](n);
        bytes memory packed = new bytes(4 * n);
        for (uint256 i; i < n; ++i) {
            uint32 id = uint32(1 + 2 * i); // sparse ids
            all[i] = id;
            assembly {
                mstore(add(add(packed, 0x20), mul(i, 4)), shl(224, id))
            }
        }
        bytes32 setHash = sha256(packed);
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("P", 2, bytes32(uint256(1)));

        TapNetlistNFT c2 = new TapNetlistNFT("T", "T", "", address(this));
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        c2.commitManifestTokenSet(MANIFEST, setHash, n + 1, ps, false);

        c.commitManifestTokenSet(MANIFEST, setHash, n, ps, false);
        uint256 maxg;
        uint256 lastg;
        for (uint256 off; off < n; off += per) {
            uint256 end = off + per < n ? off + per : n;
            uint32[] memory part = new uint32[](end - off);
            for (uint256 i; i < part.length; ++i) {
                part[i] = all[off + i];
            }
            uint256 g = gasleft();
            assertTrue(c.loadTokenSetChunk(off, TokenSetPack.pack(part)));
            uint256 used = g - gasleft();
            if (used > maxg) maxg = used;
            lastg = used;
        }
        console2.log("token set n=100000: max chunk gas", maxg);
        console2.log("  completing chunk gas", lastg);
        assertLt(maxg, TX_CAP);
        assertEq(c.tokenAt(n - 1), 2 * n - 1);
        assertEq(c.indexOf(2 * n - 1), n - 1);
        uint256 g2 = gasleft();
        c.indexOf(99_999);
        console2.log("indexOf binary search over 100000 (view)", g2 - gasleft());
    }

    /// P3-1 + P3-3: a set member that is not bound but whose pools are loaded departs with the loaded hashes, so
    /// the mirror can mark its netlist known. (Since the R1 conformance fix the gateway requires every field the
    /// manifest defines, so both the image and the netlist pool are loaded here.)
    function test_audit_gatewaySetModeLoadedPoolDepartsWithHashes() public {
        _buildPools(3);
        vm.chainId(196);
        MockLegacy721 legacy = new MockLegacy721();
        TapCompanion comp = new TapCompanion(address(legacy), bytes4(keccak256("uriFrozen()")), address(this));
        uint32[] memory ids = new uint32[](3);
        ids[0] = 5;
        ids[1] = 10;
        ids[2] = 20;
        comp.commitManifestTokenSet(
            MANIFEST, sha256(abi.encodePacked(uint32(5), uint32(10), uint32(20))), 3, _pools(), false
        );
        comp.loadTokenSet(TokenSetPack.pack(ids));
        comp.reveal(SEED);
        bytes32[] memory nets = netValues;
        comp.loadPool(1, nets);
        bytes32[] memory imgs = imgValues;
        comp.loadPool(0, imgs);

        TapGateway gw = new TapGateway(address(legacy), address(comp), address(this));
        MockAdapter a = new MockAdapter(address(gw), 0);
        a.setRemote(56, address(0xB5C));
        address[] memory ads = new address[](1);
        ads[0] = address(a);
        gw.setRoute(56, 1, ads, address(0xB5C));

        address alice = makeAddr("alice");
        legacy.mint(alice, 20);
        bytes32 h = comp.netlistHashOf(20);
        assertEq(h, netValues[comp.entryIndexOf(20, 1)]);
        assertTrue(h != 0);
        vm.startPrank(alice);
        legacy.setApprovalForAll(address(gw), true);
        gw.bridge(20, 56, alice, false, new bytes[](0));
        vm.stopPrank();
        assertEq(gw.locationOf(20), 56);
        // markKnown is idempotent and harmless when called repeatedly by anyone
        vm.prank(address(0xBAD));
        assertEq(comp.markKnown(20), h);
        assertEq(comp.markKnown(20), h);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, uint256(11)));
        comp.markKnown(11); // not in the set
    }

    /// Lock opener check (regression): the constructor still trusts the opener it is given, but now records it
    /// in the public `opener()` getter, so tools can compare it with the chain's canonical opener.
    function test_audit_lockOpenerIsRecorded() public {
        address fakeContainer = address(0xC0FFEE);
        LyingOpener o = new LyingOpener(fakeContainer);
        TapContainerLock lock =
            new TapContainerLock(IERC721Min(address(0x8E0b)), 1, fakeContainer, o, IDomainBinding(address(0xD0)), "x");
        assertEq(lock.container(), fakeContainer);
        assertEq(address(lock.opener()), address(o)); // observable: not the canonical opener
    }
}
