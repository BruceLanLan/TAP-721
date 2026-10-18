// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {CoreBase} from "./CoreBase.sol";
import {MerkleBuilder, MockLegacy721} from "./CoreHelpers.sol";

contract TapPoolLoadTest is CoreBase {
    TapNetlistNFT nft;
    address bob = makeAddr("bob");

    function setUp() public {
        _buildPools(20);
        nft = new TapNetlistNFT("T", "T", "", address(this));
    }

    function _commit(TapNetlistCore c) internal {
        c.commitManifest(MANIFEST, FIRST, supply, _pools());
    }

    function test_loadThenReadAfterRevealWithoutBind() public {
        _commit(nft);
        bytes32[] memory nets = netValues;
        bytes32[] memory imgs = imgValues;
        vm.expectEmit(address(nft));
        emit TapNetlistCore.PoolLoaded(1);
        nft.loadPool(1, nets);
        nft.loadPool(0, imgs);
        assertTrue(nft.poolLoaded(0) && nft.poolLoaded(1));
        assertEq(nft.loadedValue(1, 7, 2), netValues[7]);
        assertEq(nft.loadedValue(1, 7, 1), 0); // pool 1 has no image field
        assertEq(nft.netlistHashOf(FIRST), 0); // not revealed yet

        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.reveal(SEED);
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            assertEq(nft.netlistHashOf(t), netValues[nft.entryIndexOf(t, 1)]);
            assertEq(nft.imageHashOf(t), imgValues[nft.entryIndexOf(t, 0)]);
        }
        assertEq(nft.netlistHashOf(FIRST + supply), 0); // out of range

        // a loaded hash becomes known in O(1) through markKnown (no bind, no scan)
        uint256 t0 = _tokenWithNetlist(nft, sha256(xorFile));
        assertFalse(nft.knownNetlist(sha256(xorFile)));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, sha256(xorFile)));
        nft.storeNetlist(xorFile);
        vm.prank(bob); // permissionless
        assertEq(nft.markKnown(t0), sha256(xorFile));
        assertTrue(nft.knownNetlist(sha256(xorFile)));
        nft.storeNetlist(xorFile);
        assertEq(nft.netlistOf(t0), xorFile);
        assertEq(nft.evalOf(t0, hex"02"), hex"01");

        // bind still works and agrees
        _bind(nft, t0, 1);
        assertEq(nft.netlistHashOf(t0), sha256(xorFile));
    }

    function test_loadAfterRevealEmitsBatchUpdate() public {
        _commit(nft);
        nft.reveal(SEED);
        bytes32[] memory nets = netValues;
        vm.expectEmit(address(nft));
        emit TapNetlistCore.PoolLoaded(1);
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.loadPool(1, nets);
        vm.recordLogs();
        nft.loadPool(1, nets); // idempotent
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_markKnownReverts() public {
        _commit(nft);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, FIRST));
        nft.markKnown(FIRST); // nothing loaded or bound
        nft.reveal(SEED);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, FIRST + supply));
        nft.markKnown(FIRST + supply);
    }

    function test_loadReverts() public {
        bytes32[] memory nets = netValues;
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.loadPool(1, nets);
        _commit(nft);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.PoolOutOfRange.selector, 2));
        nft.loadPool(2, nets);
        nets[5] = keccak256("wrong");
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.loadPool(1, nets);
        bytes32[] memory short = new bytes32[](supply - 1);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadPool(1, short);
        assertFalse(nft.poolLoaded(1));
    }

    function test_noRevealCollection() public {
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, _pools());
        bytes32[] memory nets = netValues;
        nft.loadPool(1, nets);
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            assertEq(nft.netlistHashOf(t), netValues[t - FIRST]);
        }
        assertEq(nft.imageHashOf(FIRST), 0); // image pool not loaded
    }

    function test_companionLoad() public {
        TapCompanion c = new TapCompanion(address(new MockLegacy721()), bytes4(keccak256("uriFrozen()")), address(this));
        _commit(c);
        c.reveal(SEED);
        bytes32[] memory nets = netValues;
        c.loadPool(1, nets);
        assertEq(c.netlistHashOf(FIRST + 2), netValues[c.entryIndexOf(FIRST + 2, 1)]);
    }

    function test_twoFieldPool() public {
        uint256 n = 7;
        bytes32[] memory leaves = new bytes32[](n);
        bytes32[] memory flat = new bytes32[](2 * n);
        for (uint256 i; i < n; ++i) {
            bytes32[] memory v = new bytes32[](2);
            v[0] = keccak256(abi.encode("i", i));
            v[1] = keccak256(abi.encode("n", i));
            (flat[2 * i], flat[2 * i + 1]) = (v[0], v[1]);
            leaves[i] = TapMerkle.leafHash(i, v);
        }
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("BOTH", 3, MerkleBuilder.root(leaves));
        nft.commitManifest(MANIFEST, 100, n, ps);
        nft.reveal(SEED);
        assertEq(nft.poolPageSize(0), 383);
        nft.loadPool(0, flat);
        for (uint256 t = 100; t < 100 + n; ++t) {
            uint256 e = nft.entryIndexOf(t, 0);
            assertEq(nft.imageHashOf(t), flat[2 * e]);
            assertEq(nft.netlistHashOf(t), flat[2 * e + 1]);
        }
    }

    function _bigSingle(uint256 n) internal returns (TapNetlistNFT c, bytes32[] memory vals) {
        vals = new bytes32[](n);
        bytes32[] memory leaves = new bytes32[](n);
        for (uint256 i; i < n; ++i) {
            vals[i] = keccak256(abi.encode(i));
            bytes32[] memory one = new bytes32[](1);
            one[0] = vals[i];
            leaves[i] = TapMerkle.leafHash(i, one);
        }
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("NETLIST_V1", 2, MerkleBuilder.root(leaves));
        c = new TapNetlistNFT("T", "T", "", address(this));
        c.commitManifest(MANIFEST, 1, n, ps);
    }

    function _slice(bytes32[] memory a, uint256 from, uint256 to) internal pure returns (bytes32[] memory r) {
        r = new bytes32[](to - from);
        for (uint256 i; i < r.length; ++i) {
            r[i] = a[from + i];
        }
    }

    function test_chunkedLoad() public {
        (TapNetlistNFT c, bytes32[] memory vals) = _bigSingle(1000); // pages of 767
        bytes32[] memory part1 = _slice(vals, 0, 767);
        bytes32[] memory part2 = _slice(vals, 767, 1000);
        bytes32[] memory bad = _slice(vals, 0, 500);

        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        c.loadPoolChunk(0, 0, bad); // not a page multiple and not final
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        c.loadPoolChunk(0, 767, part2); // wrong offset
        assertTrue(c.loadPoolChunk(0, 0, part1));
        assertEq(c.loadProgress(0, address(this)), 767);

        // another account's session is independent
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        c.loadPoolChunk(0, 767, part2);

        // a wrong final chunk resets the session instead of reverting
        bytes32[] memory wrong = _slice(vals, 767, 1000);
        wrong[0] = keccak256("x");
        vm.expectEmit(address(c));
        emit TapNetlistCore.PoolLoadFailed(0, address(this));
        assertFalse(c.loadPoolChunk(0, 767, wrong));
        assertEq(c.loadProgress(0, address(this)), 0);
        assertFalse(c.poolLoaded(0));

        assertTrue(c.loadPoolChunk(0, 0, part1));
        vm.expectEmit(address(c));
        emit TapNetlistCore.PoolLoaded(0);
        assertTrue(c.loadPoolChunk(0, 767, part2));
        assertTrue(c.poolLoaded(0));
        assertTrue(c.loadPoolChunk(0, 0, part1)); // idempotent once loaded
        c.reveal(SEED);
        assertEq(c.netlistHashOf(999), vals[c.entryIndexOf(999, 0)]);
        assertEq(c.loadedValue(0, 766, 2), vals[766]);
        assertEq(c.loadedValue(0, 767, 2), vals[767]);
    }

    function testFuzz_chunkedMatchesSingle(uint256 n, uint256 pagesPerChunk) public {
        n = bound(n, 1, 2000);
        pagesPerChunk = bound(pagesPerChunk, 1, 3);
        (TapNetlistNFT c, bytes32[] memory vals) = _bigSingle(n);
        uint256 step = 767 * pagesPerChunk;
        bool loaded;
        for (uint256 off; off < n; off += step) {
            uint256 end = off + step < n ? off + step : n;
            loaded = c.loadPoolChunk(0, off, _slice(vals, off, end));
        }
        assertTrue(loaded);
        assertTrue(c.poolLoaded(0));
        assertEq(c.loadedValue(0, n - 1, 2), vals[n - 1]);
    }
}
