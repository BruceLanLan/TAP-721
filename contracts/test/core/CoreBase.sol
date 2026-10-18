// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {MerkleBuilder, Tapnet} from "./CoreHelpers.sol";

/// A collection's pools built in Solidity: pool 0 = images (mask 1), pool 1 = netlists (mask 2).
abstract contract CoreBase is Test {
    uint256 constant FIRST = 1;
    bytes32 constant MANIFEST = keccak256("manifest");
    bytes32 constant SEED = keccak256("seed");

    uint256 supply;
    bytes32[] imgValues;
    bytes32[] netValues;
    bytes32[] imgLeaves;
    bytes32[] netLeaves;
    bytes xorFile;
    bytes bigFile; // 49,150 bytes, 2 chunks

    function _buildPools(uint256 n) internal {
        supply = n;
        xorFile = Tapnet.xor17851();
        bigFile = Tapnet.chain(7014, 9);
        delete imgValues;
        delete netValues;
        delete imgLeaves;
        delete netLeaves;
        for (uint256 i; i < n; ++i) {
            imgValues.push(keccak256(abi.encode("img", i)));
            bytes32 net = i % 3 == 0 ? sha256(xorFile) : i % 3 == 1 ? sha256(bigFile) : keccak256(abi.encode("n", i));
            netValues.push(net);
            imgLeaves.push(TapMerkle.leafHash(i, _one(imgValues[i])));
            netLeaves.push(TapMerkle.leafHash(i, _one(net)));
        }
    }

    function _pools() internal view returns (ITapNetlistNFT.Pool[] memory ps) {
        ps = new ITapNetlistNFT.Pool[](2);
        ps[0] = ITapNetlistNFT.Pool("IMAGE_V1", 1, MerkleBuilder.root(imgLeaves));
        ps[1] = ITapNetlistNFT.Pool("NETLIST_V1", 2, MerkleBuilder.root(netLeaves));
    }

    function _one(bytes32 v) internal pure returns (bytes32[] memory a) {
        a = new bytes32[](1);
        a[0] = v;
    }

    /// Values and proof for binding `tokenId` in `pool` of collection `c`.
    function _bindArgs(TapNetlistCore c, uint256 tokenId, uint256 pool)
        internal
        view
        returns (bytes32[] memory values, bytes32[] memory proof)
    {
        uint256 e = c.entryIndexOf(tokenId, pool);
        if (pool == 0) return (_one(imgValues[e]), MerkleBuilder.proof(imgLeaves, e));
        return (_one(netValues[e]), MerkleBuilder.proof(netLeaves, e));
    }

    function _bind(TapNetlistCore c, uint256 tokenId, uint256 pool) internal {
        (bytes32[] memory v, bytes32[] memory p) = _bindArgs(c, tokenId, pool);
        c.bind(tokenId, pool, v, p);
    }

    /// A token whose netlist entry is the given file hash (searches the revealed permutation).
    function _tokenWithNetlist(TapNetlistCore c, bytes32 h) internal view returns (uint256) {
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            if (netValues[c.entryIndexOf(t, 1)] == h) return t;
        }
        revert("none");
    }
}
