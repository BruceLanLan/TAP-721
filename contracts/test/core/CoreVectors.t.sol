// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {LibHarness, MerkleBuilder} from "./CoreHelpers.sol";

/// Cross-check against the Python reference: test/fixtures/core-vectors.json is written by
/// test/fixtures/make_core_fixtures.py from assets/tap-draft-netlist-bound-nft/tapnft.py.
contract CoreVectorsTest is Test {
    LibHarness h;
    string json;

    function setUp() public {
        h = new LibHarness();
        json = vm.readFile(string.concat(vm.projectRoot(), "/test/fixtures/core-vectors.json"));
    }

    function _k(string memory a, uint256 i, string memory b) internal pure returns (string memory) {
        return string.concat(a, "[", vm.toString(i), "]", b);
    }

    function _count(string memory key) internal view returns (uint256 n) {
        while (vm.keyExistsJson(json, _k(key, n, ""))) ++n;
    }

    function test_permuteMatchesPython() public view {
        uint256 cases = _count(".permute");
        assertEq(cases, 20);
        uint256 checked;
        for (uint256 c; c < cases; ++c) {
            bytes32 seed = vm.parseJsonBytes32(json, _k(".permute", c, ".seed"));
            uint256 n = vm.parseJsonUint(json, _k(".permute", c, ".n"));
            uint256[] memory idx = vm.parseJsonUintArray(json, _k(".permute", c, ".indices"));
            uint256[] memory out = vm.parseJsonUintArray(json, _k(".permute", c, ".outputs"));
            for (uint256 i; i < idx.length; ++i) {
                assertEq(h.permute(seed, n, idx[i]), out[i], "permute");
                ++checked;
            }
        }
        assertGt(checked, 100);
    }

    function test_poolSeedMatchesPython() public view {
        uint256 cases = _count(".poolSeed");
        assertEq(cases, 4);
        for (uint256 c; c < cases; ++c) {
            bytes32 ms = vm.parseJsonBytes32(json, _k(".poolSeed", c, ".masterSeed"));
            uint256 chainId = vm.parseJsonUint(json, _k(".poolSeed", c, ".chainId"));
            address coll = vm.parseJsonAddress(json, _k(".poolSeed", c, ".collection"));
            string memory label = vm.parseJsonString(json, _k(".poolSeed", c, ".label"));
            bytes32 want = vm.parseJsonBytes32(json, _k(".poolSeed", c, ".seed"));
            assertEq(h.poolSeed(ms, uint64(chainId), coll, label), want, "poolSeed");
        }
    }

    function test_leafHashMatchesPython() public view {
        uint256 cases = _count(".leafHash");
        assertEq(cases, 3);
        for (uint256 c; c < cases; ++c) {
            uint256 index = vm.parseJsonUint(json, _k(".leafHash", c, ".index"));
            bytes32[] memory values = vm.parseJsonBytes32Array(json, _k(".leafHash", c, ".values"));
            assertEq(h.leafHash(index, values), vm.parseJsonBytes32(json, _k(".leafHash", c, ".leaf")));
        }
    }

    function test_merkleMatchesPython() public view {
        uint256 cases = _count(".merkle");
        assertEq(cases, 8);
        for (uint256 c; c < cases; ++c) {
            uint256 size = vm.parseJsonUint(json, _k(".merkle", c, ".size"));
            bytes32 root = vm.parseJsonBytes32(json, _k(".merkle", c, ".root"));
            bytes32[] memory leaves = vm.parseJsonBytes32Array(json, _k(".merkle", c, ".leaves"));
            uint256[] memory idx = vm.parseJsonUintArray(json, _k(".merkle", c, ".indices"));
            assertEq(MerkleBuilder.root(leaves), root, "root");
            for (uint256 i; i < idx.length; ++i) {
                bytes32[] memory proof = size == 1
                    ? new bytes32[](0)
                    : vm.parseJsonBytes32Array(
                        json, string.concat(_k(".merkle", c, ".proofs"), "[", vm.toString(i), "]")
                    );
                assertTrue(h.verify(root, size, idx[i], leaves[idx[i]], proof), "python proof");
                bytes32[] memory mine = MerkleBuilder.proof(leaves, idx[i]);
                assertEq(keccak256(abi.encode(mine)), keccak256(abi.encode(proof)), "builder proof");
            }
        }
    }

    function test_validFilesMatchPython() public view {
        _checkValid(".files", 5);
        _checkValid(".edgeFiles", 3);
    }

    function _checkValid(string memory key, uint256 expected) internal view {
        uint256 cases = _count(key);
        assertEq(cases, expected);
        for (uint256 c; c < cases; ++c) {
            bytes memory file = vm.parseJsonBytes(json, _k(key, c, ".file"));
            assertEq(sha256(file), vm.parseJsonBytes32(json, _k(key, c, ".sha256")));
            assertEq(file.length, vm.parseJsonUint(json, _k(key, c, ".bytes")));
            (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) = h.check(file);
            assertEq(nIn, vm.parseJsonUint(json, _k(key, c, ".nIn")));
            assertEq(nOut, vm.parseJsonUint(json, _k(key, c, ".nOut")));
            assertEq(nand, vm.parseJsonUint(json, _k(key, c, ".nand")));
            assertEq(latch, vm.parseJsonUint(json, _k(key, c, ".latch")));
            assertEq(file.length, 16 + 7 * nand + 4 * latch);
        }
    }

    function test_invalidFilesRejectedLikePython() public view {
        uint256 cases = _count(".invalidFiles");
        assertEq(cases, 16);
        for (uint256 c; c < cases; ++c) {
            bytes memory file = vm.parseJsonBytes(json, _k(".invalidFiles", c, ".file"));
            try h.check(file) {
                revert(string.concat("accepted: ", vm.parseJsonString(json, _k(".invalidFiles", c, ".name"))));
            } catch {}
        }
    }

    /// Full lifecycle at the address and chain id the Python side used: commit, reveal, entryIndexOf,
    /// bind with Python-built proofs, store the real files.
    function test_endToEndMatchesPython() public {
        address coll = vm.parseJsonAddress(json, ".e2e.collection");
        vm.chainId(vm.parseJsonUint(json, ".e2e.chainId"));
        deployCodeTo("TapNetlistNFT.sol:TapNetlistNFT", abi.encode("T", "T", "ipfs://x/", address(this)), coll);
        TapNetlistNFT nft = TapNetlistNFT(coll);

        uint256 first = vm.parseJsonUint(json, ".e2e.firstTokenId");
        uint256 supply = vm.parseJsonUint(json, ".e2e.supply");
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](2);
        for (uint256 p; p < 2; ++p) {
            ps[p] = ITapNetlistNFT.Pool({
                label: vm.parseJsonString(json, _k(".e2e.pools", p, ".label")),
                fields: uint8(vm.parseJsonUint(json, _k(".e2e.pools", p, ".fields"))),
                root: vm.parseJsonBytes32(json, _k(".e2e.pools", p, ".root"))
            });
        }
        nft.commitManifest(vm.parseJsonBytes32(json, ".e2e.manifestHash"), first, supply, ps);
        nft.reveal(vm.parseJsonBytes32(json, ".e2e.masterSeed"));
        for (uint256 p; p < 2; ++p) {
            assertEq(nft.poolSeed(p), vm.parseJsonBytes32(json, _k(".e2e.poolSeeds", p, "")));
        }

        for (uint256 t; t < supply; ++t) {
            string memory tk = _k(".e2e.tokens", t, "");
            uint256 tokenId = vm.parseJsonUint(json, string.concat(tk, ".tokenId"));
            for (uint256 p; p < 2; ++p) {
                string memory pk = _k(string.concat(tk, ".pools"), p, "");
                uint256 entry = vm.parseJsonUint(json, string.concat(pk, ".entryIndex"));
                assertEq(nft.entryIndexOf(tokenId, p), entry, "entryIndexOf");
                bytes32[] memory values = vm.parseJsonBytes32Array(json, string.concat(pk, ".values"));
                bytes32[] memory proof = vm.parseJsonBytes32Array(json, string.concat(pk, ".proof"));
                nft.bind(tokenId, p, values, proof);
                if (p == 0) assertEq(nft.imageHashOf(tokenId), values[0]);
                else assertEq(nft.netlistHashOf(tokenId), values[0]);
            }
        }

        bytes memory xor = vm.parseJsonBytes(json, ".files[0].file");
        bytes memory tff = vm.parseJsonBytes(json, ".files[1].file");
        assertEq(nft.storeNetlist(xor), sha256(xor));
        assertEq(nft.storeNetlist(tff), sha256(tff));
        assertEq(nft.netlistFile(sha256(xor)), xor);
        assertEq(nft.netlistFile(sha256(tff)), tff);
        bytes memory gas1204 = vm.parseJsonBytes(json, ".files[2].file");
        vm.expectRevert(abi.encodeWithSignature("UnknownNetlist(bytes32)", sha256(gas1204)));
        nft.storeNetlist(gas1204);
    }
}
