// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";
import {TapPermutation} from "../../src/core/TapPermutation.sol";

/// Builds trees exactly like tapnft.merkle_root / merkle_proof (test helper, not gas-optimised).
library MerkleBuilder {
    function root(bytes32[] memory leaves) internal pure returns (bytes32) {
        bytes32[] memory level = leaves;
        while (level.length > 1) level = _up(level);
        return level[0];
    }

    function proof(bytes32[] memory leaves, uint256 index) internal pure returns (bytes32[] memory out) {
        bytes32[] memory buf = new bytes32[](64);
        uint256 n;
        bytes32[] memory level = leaves;
        uint256 i = index;
        while (level.length > 1) {
            if (i % 2 == 1) buf[n++] = level[i - 1];
            else if (i + 1 < level.length) buf[n++] = level[i + 1];
            level = _up(level);
            i /= 2;
        }
        out = new bytes32[](n);
        for (uint256 k; k < n; ++k) {
            out[k] = buf[k];
        }
    }

    /// All levels of the tree, leaves first (build once, then take many proofs).
    function levels(bytes32[] memory leaves) internal pure returns (bytes32[][] memory lv) {
        uint256 depth = 1;
        for (uint256 w = leaves.length; w > 1; w = (w + 1) / 2) {
            ++depth;
        }
        lv = new bytes32[][](depth);
        lv[0] = leaves;
        for (uint256 d = 1; d < depth; ++d) {
            lv[d] = _up(lv[d - 1]);
        }
    }

    function proofFromLevels(bytes32[][] memory lv, uint256 index) internal pure returns (bytes32[] memory out) {
        bytes32[] memory buf = new bytes32[](lv.length);
        uint256 n;
        uint256 i = index;
        for (uint256 d; d + 1 < lv.length; ++d) {
            if (i % 2 == 1) buf[n++] = lv[d][i - 1];
            else if (i + 1 < lv[d].length) buf[n++] = lv[d][i + 1];
            i /= 2;
        }
        out = new bytes32[](n);
        for (uint256 k; k < n; ++k) {
            out[k] = buf[k];
        }
    }

    function _up(bytes32[] memory level) private pure returns (bytes32[] memory nxt) {
        uint256 w = level.length;
        nxt = new bytes32[]((w + 1) / 2);
        for (uint256 k; k + 1 < w; k += 2) {
            nxt[k / 2] = TapMerkle.nodeHash(level[k], level[k + 1]);
        }
        if (w % 2 == 1) nxt[w / 2] = level[w - 1];
    }
}

/// tapnet/1 builders.
library Tapnet {
    function header(uint256 nIn, uint256 nOut) internal pure returns (bytes memory) {
        return abi.encodePacked("TAPNET", uint8(1), uint8(0), uint32(nIn), uint32(nOut));
    }

    function nand(uint256 a, uint256 b) internal pure returns (bytes memory) {
        return abi.encodePacked(uint8(0), uint24(a), uint24(b));
    }

    function latch(uint256 d) internal pure returns (bytes memory) {
        return abi.encodePacked(uint8(1), uint24(d));
    }

    /// Same as make_core_fixtures.chain_file: nNand NANDs fed by the two previous signals, then nLatch
    /// LATCHes on the last signal; nIn = 2, nOut = 1.
    function chain(uint256 nNand, uint256 nLatch) internal pure returns (bytes memory f) {
        f = new bytes(16 + 7 * nNand + 4 * nLatch);
        bytes memory h = header(2, 1);
        for (uint256 i; i < 16; ++i) {
            f[i] = h[i];
        }
        uint256 p = 16;
        uint256 nxt = 4;
        for (uint256 i; i < nNand; ++i) {
            uint256 a = nxt - 1;
            uint256 b = nxt - 2;
            f[p + 1] = bytes1(uint8(a >> 16));
            f[p + 2] = bytes1(uint8(a >> 8));
            f[p + 3] = bytes1(uint8(a));
            f[p + 4] = bytes1(uint8(b >> 16));
            f[p + 5] = bytes1(uint8(b >> 8));
            f[p + 6] = bytes1(uint8(b));
            p += 7;
            ++nxt;
        }
        uint256 last = nxt + nLatch - 1;
        for (uint256 i; i < nLatch; ++i) {
            f[p] = 0x01;
            f[p + 1] = bytes1(uint8(last >> 16));
            f[p + 2] = bytes1(uint8(last >> 8));
            f[p + 3] = bytes1(uint8(last));
            p += 4;
        }
    }

    /// BSC circuit #17851 (XOR, nIn 2, nOut 1) as a tapnet/1 file.
    function xor17851() internal pure returns (bytes memory) {
        return bytes.concat(header(2, 1), hex"00000002000003000000020000040000000300000400000005000006");
    }
}

/// External wrappers so reverts inside internal library code can be caught with vm.expectRevert.
contract LibHarness {
    function permute(bytes32 seed, uint256 n, uint256 x) external view returns (uint256) {
        return TapPermutation.permute(seed, n, x);
    }

    function poolSeed(bytes32 m, uint64 c, address a, string calldata l) external pure returns (bytes32) {
        return TapPermutation.poolSeed(m, c, a, l);
    }

    function leafHash(uint256 i, bytes32[] calldata v) external pure returns (bytes32) {
        return TapMerkle.leafHash(i, v);
    }

    function verify(bytes32 root, uint256 size, uint256 index, bytes32 leaf, bytes32[] calldata proof)
        external
        pure
        returns (bool)
    {
        return TapMerkle.verify(root, size, index, leaf, proof);
    }

    function check(bytes calldata file) external pure returns (uint256, uint256, uint256, uint256) {
        return TapNetlistCheck.check(file);
    }

    function checkGas(bytes calldata file) external view returns (uint256 used) {
        bytes memory f = file;
        uint256 g = gasleft();
        TapNetlistCheck.check(f);
        used = g - gasleft();
    }
}

/// Mimics TapeCode-Test1: tokenURI = baseURI ‖ id, setBaseURI, freezeBaseURI, uriFrozen.
contract MockLegacy721 {
    address public owner = msg.sender;
    string public baseURI;
    bool public uriFrozen;

    function setBaseURI(string calldata b) external {
        require(msg.sender == owner && !uriFrozen);
        baseURI = b;
    }

    function freezeBaseURI() external {
        require(msg.sender == owner);
        uriFrozen = true;
    }

    function setOwner(address o) external {
        require(msg.sender == owner);
        owner = o;
    }
}

/// Minimal ERC-6551-style account: its holder makes calls through `execute`.
contract MockContainer {
    address public holder = msg.sender;

    function execute(address to, uint256 value, bytes calldata data, uint8 operation)
        external
        payable
        returns (bytes memory)
    {
        require(msg.sender == holder && operation == 0, "not holder");
        (bool ok, bytes memory ret) = to.call{value: value}(data);
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }
        return ret;
    }
}

/// A legacy contract without any freeze getter.
contract MockLegacyNoFreeze {
    function name() external pure returns (string memory) {
        return "x";
    }
}

/// A legacy contract whose freeze getter returns malformed data.
contract MockLegacyWeird {
    fallback() external {
        assembly {
            mstore(0, 2)
            return(0, 32)
        }
    }
}

contract GoodReceiver {
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return this.onERC721Received.selector;
    }
}

contract BadReceiver {
    function onERC721Received(address, address, uint256, bytes calldata) external pure returns (bytes4) {
        return 0xdeadbeef;
    }
}

/// Returns fewer than 32 bytes from onERC721Received.
contract ShortReceiver {
    fallback() external {
        assembly {
            mstore(0, 0x150b7a0200000000000000000000000000000000000000000000000000000000)
            return(0, 4)
        }
    }
}

/// Token set file: u32be ids, 4 bytes each (the calldata format of loadTokenSet / loadTokenSetChunk).
library TokenSetPack {
    function pack(uint32[] memory ids) internal pure returns (bytes memory b) {
        b = new bytes(4 * ids.length);
        for (uint256 i; i < ids.length; ++i) {
            uint32 v = ids[i];
            assembly {
                mstore(
                    add(add(b, 0x20), mul(i, 4)),
                    or(shl(224, v), and(mload(add(add(b, 0x20), mul(i, 4))), shr(32, not(0))))
                )
            }
        }
    }
}
