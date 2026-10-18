// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console2} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {MerkleBuilder, Tapnet} from "./CoreHelpers.sol";

/// Gas of the main operations for a 10,000-token collection (run with -vv to see the numbers).
/// With `isolate = true` (foundry.toml) every external call from the test runs as its own
/// transaction, so the figures are full transaction gas: 21,000 + calldata + cold storage access.
/// Run with FOUNDRY_ISOLATE=false for execution gas inside one transaction.
contract CoreGasTest is Test {
    uint256 constant N = 10000;
    uint256 constant FIRST = 1;
    TapNetlistNFT nft;
    bytes[3] files;
    bytes32[][] netLevels;
    bytes32[] netValue; // by entry index
    ITapNetlistNFT.Pool[] pools;

    function setUp() public {
        files[0] = Tapnet.chain(1204, 0); // 8,444 bytes
        files[1] = Tapnet.chain(3424, 4); // 24,000 bytes
        files[2] = Tapnet.chain(7016, 6); // 49,152 bytes = MAX_FILE (3 chunks)
        bytes32[3] memory h = [sha256(files[0]), sha256(files[1]), sha256(files[2])];
        bytes32[] memory img = new bytes32[](N);
        bytes32[] memory net = new bytes32[](N);
        for (uint256 i; i < N; ++i) {
            img[i] = TapMerkle.leafHash(i, _one(keccak256(abi.encode(i))));
            net[i] = TapMerkle.leafHash(i, _one(h[i % 3]));
        }
        bytes32[][] memory lv = MerkleBuilder.levels(net);
        for (uint256 d; d < lv.length; ++d) {
            netLevels.push(lv[d]);
        }
        pools.push(ITapNetlistNFT.Pool("IMAGE_V1", 1, MerkleBuilder.root(img)));
        pools.push(ITapNetlistNFT.Pool("NETLIST_V1", 2, lv[lv.length - 1][0]));
        nft = new TapNetlistNFT("Tape", "TAPE", "ipfs://b/", address(this));
    }

    function _one(bytes32 v) internal pure returns (bytes32[] memory a) {
        a = new bytes32[](1);
        a[0] = v;
    }

    function _proof(uint256 e) internal view returns (bytes32[] memory) {
        bytes32[][] memory lv = new bytes32[][](netLevels.length);
        for (uint256 d; d < lv.length; ++d) {
            lv[d] = netLevels[d];
        }
        return MerkleBuilder.proofFromLevels(lv, e);
    }

    function test_gas() public {
        ITapNetlistNFT.Pool[] memory ps = pools;
        uint256 g = gasleft();
        nft.commitManifest(keccak256("m"), FIRST, N, ps);
        console2.log("commitManifest (2 pools)        ", g - gasleft());
        g = gasleft();
        nft.reveal(keccak256("seed"));
        console2.log("reveal (2 pools)                ", g - gasleft());

        // entryIndexOf, N = 10,000: average and maximum over 500 tokens
        uint256 total;
        uint256 maxg;
        for (uint256 t = FIRST; t < FIRST + 500; ++t) {
            g = gasleft();
            nft.entryIndexOf(t, 1);
            uint256 used = g - gasleft();
            total += used;
            if (used > maxg) maxg = used;
        }
        console2.log("entryIndexOf n=10000, avg       ", total / 500);
        console2.log("entryIndexOf n=10000, max       ", maxg);

        // bind: find one token per file
        uint256[3] memory tok;
        uint256 found;
        for (uint256 t = FIRST + 500; found < 7; ++t) {
            uint256 k = nft.entryIndexOf(t, 1) % 3;
            if (tok[k] == 0) {
                tok[k] = t;
                found |= 1 << k;
            }
        }
        for (uint256 k; k < 3; ++k) {
            uint256 e = nft.entryIndexOf(tok[k], 1);
            bytes32[] memory proof = _proof(e);
            bytes32[] memory v = _one(sha256(files[k]));
            g = gasleft();
            nft.bind(tok[k], 1, v, proof);
            if (k == 0) console2.log("bind netlist, proof depth 14, first bind (new hash)", g - gasleft());
            if (k == 0) console2.log("  proof length", proof.length);
        }
        uint256 t2 = tok[0] + 1;
        while (t2 == tok[1] || t2 == tok[2] || nft.entryIndexOf(t2, 1) % 3 != 0) ++t2;
        bytes32[] memory p2 = _proof(nft.entryIndexOf(t2, 1));
        bytes32[] memory v2 = _one(sha256(files[0]));
        g = gasleft();
        nft.bind(t2, 1, v2, p2);
        console2.log("bind netlist, hash already known", g - gasleft());
        bytes memory f = files[0];
        g = gasleft();
        nft.storeNetlist(f);
        console2.log("storeNetlist 8,444 B (1,204 gates)", g - gasleft());
        f = files[1];
        g = gasleft();
        nft.storeNetlist(f);
        console2.log("storeNetlist 24,000 B (1 chunk) ", g - gasleft());
        f = files[2];
        g = gasleft();
        nft.storeNetlist(f);
        console2.log("storeNetlist 49,152 B (MAX_FILE)", g - gasleft());

        g = gasleft();
        nft.netlistOf(tok[0]);
        console2.log("netlistOf 8,444 B (view)        ", g - gasleft());
        g = gasleft();
        nft.netlistOf(tok[2]);
        console2.log("netlistOf 49,152 B (view)       ", g - gasleft());
    }
}

/// loadPool for n = 10,000 in one transaction (single-field and two-field pools).
contract PoolLoadGasTest is Test {
    uint256 constant N = 10000;

    function _setup(uint8 fields) internal returns (TapNetlistNFT c, bytes32[] memory flat) {
        uint256 k = fields == 3 ? 2 : 1;
        flat = new bytes32[](N * k);
        bytes32[] memory leaves = new bytes32[](N);
        bytes32[] memory v = new bytes32[](k);
        for (uint256 i; i < N; ++i) {
            for (uint256 j; j < k; ++j) {
                v[j] = keccak256(abi.encode(i, j));
                flat[i * k + j] = v[j];
            }
            leaves[i] = TapMerkle.leafHash(i, v);
        }
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("P", fields, MerkleBuilder.root(leaves));
        c = new TapNetlistNFT("T", "T", "", address(this));
        c.commitManifest(keccak256("m"), 1, N, ps);
        c.reveal(keccak256("s"));
    }

    function test_gas_loadPool10000() public {
        (TapNetlistNFT c, bytes32[] memory flat) = _setup(2);
        uint256 g = gasleft();
        c.loadPool(0, flat);
        console2.log("loadPool n=10000, 1 field (netlist), one tx", g - gasleft());
        console2.log("  calldata bytes", flat.length * 32 + 68);
        g = gasleft();
        c.netlistHashOf(5000);
        console2.log("netlistHashOf after load (view)", g - gasleft());
        g = gasleft();
        c.markKnown(5000);
        console2.log("markKnown after load", g - gasleft());
    }

    function test_gas_loadPool10000TwoFields() public {
        (TapNetlistNFT c, bytes32[] memory flat) = _setup(3);
        uint256 g = gasleft();
        c.loadPool(0, flat);
        console2.log("loadPool n=10000, 2 fields, one tx", g - gasleft());
        console2.log("  calldata bytes", flat.length * 32 + 68);
    }

    /// Mempool size: 5 pages of a single-field pool (3,835 values) per loadPoolChunk stay under 128 KiB;
    /// a whole 10,000-entry pool in one loadPool does not.
    function test_calldataSizes() public pure {
        bytes32[] memory five = new bytes32[](767 * 5);
        bytes32[] memory six = new bytes32[](767 * 6);
        bytes32[] memory all = new bytes32[](N);
        uint256 c5 = abi.encodeCall(TapNetlistCore.loadPoolChunk, (0, 0, five)).length;
        uint256 c6 = abi.encodeCall(TapNetlistCore.loadPoolChunk, (0, 0, six)).length;
        uint256 cAll = abi.encodeCall(TapNetlistCore.loadPool, (0, all)).length;
        console2.log("loadPoolChunk 5 pages (3,835 values) calldata", c5);
        console2.log("loadPoolChunk 6 pages calldata", c6);
        console2.log("loadPool 10,000 values calldata", cAll);
        assertLe(c5, 131_072);
        assertGt(c6, 131_072);
        assertGt(cAll, 131_072);
    }

    function test_gas_loadPoolChunks() public {
        (TapNetlistNFT c, bytes32[] memory flat) = _setup(2);
        uint256 step = 767 * 2; // 1,534 entries = 49,088 bytes of values per transaction
        uint256 maxg;
        uint256 total;
        for (uint256 off; off < N; off += step) {
            uint256 end = off + step < N ? off + step : N;
            bytes32[] memory part = new bytes32[](end - off);
            for (uint256 i; i < part.length; ++i) {
                part[i] = flat[off + i];
            }
            uint256 g = gasleft();
            c.loadPoolChunk(0, off, part);
            uint256 used = g - gasleft();
            total += used;
            if (used > maxg) maxg = used;
        }
        assertTrue(c.poolLoaded(0));
        console2.log("loadPoolChunk n=10000, 1 field, 7 tx of <=1534 entries: total", total);
        console2.log("  max per tx", maxg);
    }
}
