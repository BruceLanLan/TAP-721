// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TokenSetPack} from "./CoreHelpers.sol";
import {console2} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {ITapNetlistTokenSet} from "../../src/interfaces/ITapNetlistTokenSet.sol";
import {ERC721Min} from "../../src/vendor/ERC721Min.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {CoreBase} from "./CoreBase.sol";
import {MerkleBuilder, MockLegacy721} from "./CoreHelpers.sol";

/// Explicit token sets (ITapNetlistTokenSet), cross-checked against tapnft.py on a 7,000-of-10,000 set.
contract TapTokenSetTest is CoreBase {
    string json;
    uint32[] bigIds;
    bytes32 bigHash;

    function setUp() public {
        json = vm.readFile(string.concat(vm.projectRoot(), "/test/fixtures/core-tokenset.json"));
        uint256[] memory ids = vm.parseJsonUintArray(json, ".tokenSet.ids");
        for (uint256 i; i < ids.length; ++i) {
            bigIds.push(uint32(ids[i]));
        }
        bigHash = vm.parseJsonBytes32(json, ".tokenSet.tokenSetHash");
    }

    function _pool1(uint8 f, bytes32 root) internal pure returns (ITapNetlistNFT.Pool[] memory ps) {
        ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("NETLIST_V1", f, root);
    }

    function _hashOf(uint32[] memory ids) internal pure returns (bytes32) {
        bytes memory b;
        for (uint256 i; i < ids.length; ++i) {
            b = bytes.concat(b, bytes4(ids[i]));
        }
        return sha256(b);
    }

    function test_pythonCrossCheck7000() public {
        address coll = vm.parseJsonAddress(json, ".tokenSet.collection");
        deployCodeTo("TapNetlistNFT.sol:TapNetlistNFT", abi.encode("T", "T", "", address(this)), coll);
        TapNetlistNFT nft = TapNetlistNFT(coll);
        nft.commitManifestTokenSet(MANIFEST, bigHash, 7000, _pool1(2, bytes32(uint256(1))), false);
        bytes memory file = vm.parseJsonBytes(json, ".tokenSet.tokenSetFile"); // Python's token set file
        assertEq(file, TokenSetPack.pack(bigIds));
        assertEq(sha256(file), bigHash);
        uint256 cd = abi.encodeCall(TapNetlistCore.loadTokenSet, (file)).length;
        console2.log("loadTokenSet 7,000 ids, calldata bytes", cd);
        assertLe(cd, 131_072);
        uint256 g = gasleft();
        nft.loadTokenSet(file);
        console2.log("loadTokenSet 7,000 ids, one tx", g - gasleft());
        nft.reveal(vm.parseJsonBytes32(json, ".tokenSet.masterSeed"));
        assertEq(nft.poolSeed(0), vm.parseJsonBytes32(json, ".tokenSet.poolSeed"));
        assertEq(nft.tokenSetHash(), bigHash);
        assertEq(nft.tokenCount(), 7000);
        (uint256 first, uint256 n) = nft.tokenRange();
        assertEq(first, 0);
        assertEq(n, 7000);

        uint256[] memory tids = vm.parseJsonUintArray(json, ".tokenSet.sampleTokenIds");
        uint256[] memory ranks = vm.parseJsonUintArray(json, ".tokenSet.sampleRanks");
        uint256[] memory entries = vm.parseJsonUintArray(json, ".tokenSet.sampleEntries");
        uint256 gi;
        uint256 ge;
        for (uint256 i; i < tids.length; ++i) {
            g = gasleft();
            uint256 r = nft.indexOf(tids[i]);
            gi += g - gasleft();
            assertEq(r, ranks[i], "rank");
            assertEq(nft.tokenAt(ranks[i]), tids[i], "tokenAt");
            g = gasleft();
            uint256 e = nft.entryIndexOf(tids[i], 0);
            ge += g - gasleft();
            assertEq(e, entries[i], "entry");
        }
        console2.log("indexOf n=7000 avg", gi / tids.length);
        console2.log("entryIndexOf n=7000 avg", ge / tids.length);
        uint256[] memory excl = vm.parseJsonUintArray(json, ".tokenSet.excludedSample");
        for (uint256 i; i < excl.length; ++i) {
            vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotInTokenSet.selector, excl[i]));
            nft.entryIndexOf(excl[i], 0);
            assertEq(nft.netlistHashOf(excl[i]), 0);
        }
    }

    function test_chunkedLoad7000() public {
        TapNetlistNFT nft = new TapNetlistNFT("T", "T", "", address(this));
        nft.commitManifestTokenSet(MANIFEST, bigHash, 7000, _pool1(2, bytes32(uint256(1))), false);
        uint32[] memory a = new uint32[](6143);
        uint32[] memory b = new uint32[](857);
        for (uint256 i; i < 6143; ++i) {
            a[i] = bigIds[i];
        }
        for (uint256 i; i < 857; ++i) {
            b[i] = bigIds[6143 + i];
        }

        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        nft.loadTokenSetChunk(0, TokenSetPack.pack(b)); // not a page multiple, not final
        uint256 g = gasleft();
        assertTrue(nft.loadTokenSetChunk(0, TokenSetPack.pack(a)));
        uint256 g1 = g - gasleft();
        // wrong final chunk: session reset, no revert
        uint32[] memory bad = b;
        bad[856] = bad[856] + 1;
        vm.expectEmit(address(nft));
        emit TapNetlistCore.TokenSetLoadFailed(address(this));
        assertFalse(nft.loadTokenSetChunk(6143, TokenSetPack.pack(bad)));
        bad[856] = bad[856] - 1;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        nft.loadTokenSetChunk(6143, TokenSetPack.pack(b));
        assertTrue(nft.loadTokenSetChunk(0, TokenSetPack.pack(a)));
        g = gasleft();
        vm.expectEmit(address(nft));
        emit TapNetlistCore.TokenSetLoaded(bigHash);
        assertTrue(nft.loadTokenSetChunk(6143, TokenSetPack.pack(b)));
        uint256 g2 = g - gasleft();
        console2.log("loadTokenSetChunk 6,143 ids", g1);
        console2.log("loadTokenSetChunk final 857 ids (incl. hash check)", g2);
        assertEq(nft.indexOf(bigIds[6143]), 6143);
        assertEq(nft.tokenAt(6142), bigIds[6142]);
        assertTrue(nft.loadTokenSetChunk(0, TokenSetPack.pack(a))); // idempotent once loaded
    }

    function test_loadReverts() public {
        uint32[] memory ids = new uint32[](3);
        (ids[0], ids[1], ids[2]) = (3, 5, 9);
        TapNetlistNFT nft = new TapNetlistNFT("T", "T", "", address(this));
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.loadTokenSet(TokenSetPack.pack(ids));
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifestTokenSet(MANIFEST, 0, 3, _pool1(2, bytes32(uint256(1))), false);
        nft.commitManifestTokenSet(MANIFEST, _hashOf(ids), 3, _pool1(2, bytes32(uint256(1))), false);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.TokenSetNotLoaded.selector);
        nft.entryIndexOf(5, 0);
        vm.expectRevert(TapNetlistCore.TokenSetNotLoaded.selector);
        nft.indexOf(5);
        vm.expectRevert(TapNetlistCore.TokenSetNotLoaded.selector);
        nft.tokenAt(0);

        uint32[] memory two = new uint32[](2);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadTokenSet(TokenSetPack.pack(two)); // wrong count
        uint32[] memory desc = new uint32[](3);
        (desc[0], desc[1], desc[2]) = (3, 9, 5);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadTokenSet(TokenSetPack.pack(desc));
        uint32[] memory dup = new uint32[](3);
        (dup[0], dup[1], dup[2]) = (3, 5, 5);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadTokenSet(TokenSetPack.pack(dup));
        uint32[] memory other = new uint32[](3);
        (other[0], other[1], other[2]) = (3, 5, 10);
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.loadTokenSet(TokenSetPack.pack(other));

        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.loadTokenSet(bytes.concat(TokenSetPack.pack(ids), hex"00")); // not 4 bytes per id
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BadChunk.selector, 0));
        nft.loadTokenSetChunk(0, hex"0000000300"); // length % 4 != 0
        vm.expectEmit(address(nft));
        emit TapNetlistCore.TokenSetLoaded(_hashOf(ids));
        nft.loadTokenSet(TokenSetPack.pack(ids));
        vm.recordLogs();
        nft.loadTokenSet(TokenSetPack.pack(ids)); // idempotent
        assertEq(vm.getRecordedLogs().length, 0);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, 3));
        nft.tokenAt(3);

        TapNetlistNFT range = new TapNetlistNFT("T", "T", "", address(this));
        range.commitManifest(MANIFEST, 1, 3, _pool1(2, bytes32(uint256(1))));
        vm.expectRevert(TapNetlistCore.NotTokenSetMode.selector);
        range.loadTokenSet(TokenSetPack.pack(ids));
    }

    function test_rangeModeGetters() public {
        TapNetlistNFT nft = new TapNetlistNFT("T", "T", "", address(this));
        nft.commitManifest(MANIFEST, 100, 5, _pool1(2, bytes32(uint256(1))));
        assertEq(nft.tokenSetHash(), 0);
        assertEq(nft.tokenCount(), 5);
        assertEq(nft.tokenAt(4), 104);
        assertEq(nft.indexOf(102), 2);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, 105));
        nft.indexOf(105);
        assertTrue(nft.supportsInterface(type(ITapNetlistTokenSet).interfaceId));
        console2.log("ITapNetlistTokenSet interfaceId");
        console2.logBytes4(type(ITapNetlistTokenSet).interfaceId);
    }

    /// Small set: bind, loadPool reads, mint rules, NO_REVEAL and the companion all use ranks.
    function _smallSet() internal pure returns (uint32[] memory ids) {
        ids = new uint32[](5);
        (ids[0], ids[1], ids[2], ids[3], ids[4]) = (3, 5, 9, 10, 20);
    }

    function _smallPool(uint256 n) internal pure returns (bytes32[] memory vals, bytes32[] memory leaves) {
        vals = new bytes32[](n);
        leaves = new bytes32[](n);
        for (uint256 i; i < n; ++i) {
            vals[i] = keccak256(abi.encode("net", i));
            bytes32[] memory one = new bytes32[](1);
            one[0] = vals[i];
            leaves[i] = TapMerkle.leafHash(i, one);
        }
    }

    function test_smallSetBindLoadMint() public {
        uint32[] memory ids = _smallSet();
        (bytes32[] memory vals, bytes32[] memory leaves) = _smallPool(5);
        TapNetlistNFT nft = new TapNetlistNFT("T", "T", "", address(this));
        nft.commitManifestTokenSet(MANIFEST, _hashOf(ids), 5, _pool1(2, MerkleBuilder.root(leaves)), false);
        vm.expectRevert(TapNetlistCore.TokenSetNotLoaded.selector);
        nft.mint(address(this), 9);
        nft.loadTokenSet(TokenSetPack.pack(ids));
        nft.mint(address(1), 9);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotInTokenSet.selector, 4));
        nft.mint(address(1), 4);
        nft.loadPool(0, vals);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.mint(address(1), 10);
        bool[] memory hit = new bool[](5);
        for (uint256 i; i < 5; ++i) {
            uint256 e = nft.entryIndexOf(ids[i], 0);
            assertFalse(hit[e]);
            hit[e] = true;
            assertEq(nft.netlistHashOf(ids[i]), vals[e]); // from the loaded pool
        }
        uint256 e9 = nft.entryIndexOf(9, 0);
        bytes32[] memory one = new bytes32[](1);
        one[0] = vals[e9];
        nft.bind(9, 0, one, MerkleBuilder.proof(leaves, e9));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotInTokenSet.selector, 4));
        nft.bind(4, 0, one, new bytes32[](0));
        assertEq(nft.netlistHashOf(4), 0);
        nft.freeze();
        assertTrue(nft.frozen());
    }

    function test_noRevealSetUsesRanks() public {
        uint32[] memory ids = _smallSet();
        TapNetlistNFT nft = new TapNetlistNFT("T", "T", "", address(this));
        nft.commitManifestTokenSet(MANIFEST, _hashOf(ids), 5, _pool1(2, bytes32(uint256(1))), true);
        assertEq(nft.masterSeed(), nft.NO_REVEAL());
        nft.loadTokenSet(TokenSetPack.pack(ids));
        for (uint256 i; i < 5; ++i) {
            assertEq(nft.entryIndexOf(ids[i], 0), i);
        }
    }

    function test_companionSet() public {
        uint32[] memory ids = _smallSet();
        TapCompanion c = new TapCompanion(address(new MockLegacy721()), bytes4(keccak256("uriFrozen()")), address(this));
        c.commitManifestTokenSet(MANIFEST, _hashOf(ids), 5, _pool1(2, bytes32(uint256(1))), false);
        c.loadTokenSet(TokenSetPack.pack(ids));
        c.reveal(SEED);
        assertEq(c.indexOf(20), 4);
        assertLt(c.entryIndexOf(20, 0), 5);
        assertTrue(c.supportsInterface(type(ITapNetlistTokenSet).interfaceId));
    }
}
