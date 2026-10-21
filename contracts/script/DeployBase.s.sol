// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2 as console} from "forge-std/console2.sol";
import {VmSafe} from "forge-std/Vm.sol";
import {TapMerkle} from "../src/core/TapMerkle.sol";
import {ITapNetlistNFT} from "../src/interfaces/ITapNetlistNFT.sol";

/// @title Shared pieces of the test-deployment scripts (DEPLOY.md)
/// @notice Every script reads `PRIVATE_KEY` from the environment (a TEST key, never a mainnet key: see the
///         safety note of DEPLOY.md), refuses mainnet chain ids unless `ALLOW_MAINNET=true`, and records what it
///         deployed in `deployments/<chainId>.json` (one section per script; the file is created on first use
///         and merged afterwards). Nothing here holds a key: the key is the caller's, read at run time only.
abstract contract DeployBase is Script {
    /// Chain ids this package is written for. Anything else is accepted with a warning; mainnets need
    /// `ALLOW_MAINNET=true`.
    uint256 internal constant ANVIL = 31337;
    uint256 internal constant XLAYER_TESTNET = 1952;
    uint256 internal constant BSC_TESTNET = 97;

    /// Example collection of assets/tap-draft-netlist-bound-nft/example (vectors.json "example"): 8 tokens,
    /// pool 0 IMAGE_V1 (fields 1), pool 1 NETLIST_V1 (fields 2). The manifest hash is SHA-256 of the file exactly
    /// as written; the master seed is the example's fixed value (bytes 0x00..0x1f), not a real reveal.
    string internal constant EXAMPLE_MANIFEST = "../assets/tap-draft-netlist-bound-nft/example/manifest.json";
    string internal constant EXAMPLE_NETLISTS = "../assets/tap-draft-netlist-bound-nft/example/netlists/";
    bytes32 internal constant EXAMPLE_SEED = 0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f;
    uint256 internal constant EXAMPLE_FIRST = 1;
    uint256 internal constant EXAMPLE_SUPPLY = 8;

    uint256 internal deployerKey;
    address internal deployer;

    struct Example {
        bytes32 manifestHash;
        ITapNetlistNFT.Pool[] pools;
        bytes32[] imageValues; // entry order
        bytes32[] netlistValues; // entry order
        bytes32[] imageLeaves;
        bytes32[] netlistLeaves;
    }

    // ------------------------------------------------------------------ key, chain

    function _loadDeployer() internal {
        deployerKey = vm.envUint("PRIVATE_KEY");
        deployer = vm.addr(deployerKey);
        _checkChain();
        console.log("chain id      ", block.chainid);
        console.log("deployer      ", deployer);
        console.log("balance (wei) ", deployer.balance);
    }

    function _checkChain() internal view {
        uint256 id = block.chainid;
        if (id == ANVIL || id == XLAYER_TESTNET || id == BSC_TESTNET) return;
        bool mainnet = id == 1 || id == 56 || id == 196 || id == 8453;
        if (mainnet && !vm.envOr("ALLOW_MAINNET", false)) {
            revert("DeployBase: mainnet chain id; this package is for testnets (set ALLOW_MAINNET=true to override)");
        }
        console.log("WARNING: chain id is not one this package was written for; continuing");
    }

    function _chainName() internal view returns (string memory) {
        uint256 id = block.chainid;
        if (id == ANVIL) return "anvil";
        if (id == XLAYER_TESTNET) return "X Layer Testnet";
        if (id == BSC_TESTNET) return "BNB Smart Chain Testnet";
        if (id == 196) return "X Layer";
        if (id == 56) return "BNB Smart Chain";
        if (id == 8453) return "Base";
        return "unknown";
    }

    // ------------------------------------------------------------------ deployments/<chainId>.json

    function _deploymentsPath() internal view returns (string memory) {
        return string.concat("deployments/", vm.toString(block.chainid), ".json");
    }

    /// Write `sectionJson` (a serialized object) under key `section` of deployments/<chainId>.json, keeping the
    /// other sections. The directory `deployments/` needs read-write permission in foundry.toml.
    function _writeSection(string memory section, string memory sectionJson) internal {
        string memory path = _deploymentsPath();
        if (!vm.exists(path)) {
            string memory root = "root";
            vm.serializeUint(root, "chainId", block.chainid);
            string memory base = vm.serializeString(root, "chain", _chainName());
            vm.writeJson(base, path);
        }
        vm.writeJson(sectionJson, path, string.concat(".", section));
        console.log("wrote section", section, "to", path);
    }

    /// Common members of every section.
    function _sectionHeader(string memory obj) internal {
        vm.serializeAddress(obj, "deployer", deployer);
        vm.serializeUint(obj, "block", block.number);
        vm.serializeUint(obj, "timestamp", block.timestamp);
    }

    // ------------------------------------------------------------------ example manifest

    function _loadExample() internal view returns (Example memory e) {
        string memory text = vm.readFile(EXAMPLE_MANIFEST);
        e.manifestHash = sha256(bytes(text));
        e.pools = new ITapNetlistNFT.Pool[](2);
        e.pools[0] = ITapNetlistNFT.Pool({
            label: vm.parseJsonString(text, ".pools[0].label"),
            fields: 1,
            root: vm.parseJsonBytes32(text, ".pools[0].root")
        });
        e.pools[1] = ITapNetlistNFT.Pool({
            label: vm.parseJsonString(text, ".pools[1].label"),
            fields: 2,
            root: vm.parseJsonBytes32(text, ".pools[1].root")
        });
        e.imageValues = new bytes32[](EXAMPLE_SUPPLY);
        e.netlistValues = new bytes32[](EXAMPLE_SUPPLY);
        e.imageLeaves = new bytes32[](EXAMPLE_SUPPLY);
        e.netlistLeaves = new bytes32[](EXAMPLE_SUPPLY);
        for (uint256 i; i < EXAMPLE_SUPPLY; ++i) {
            string memory idx = vm.toString(i);
            e.imageValues[i] = vm.parseJsonBytes32(text, string.concat(".pools[0].entries[", idx, "].image"));
            e.netlistValues[i] = vm.parseJsonBytes32(text, string.concat(".pools[1].entries[", idx, "].netlist"));
            e.imageLeaves[i] = TapMerkle.leafHash(i, _one(e.imageValues[i]));
            e.netlistLeaves[i] = TapMerkle.leafHash(i, _one(e.netlistValues[i]));
        }
        require(MerkleBuilder.root(e.imageLeaves) == e.pools[0].root, "example: image root mismatch");
        require(MerkleBuilder.root(e.netlistLeaves) == e.pools[1].root, "example: netlist root mismatch");
    }

    /// The three distinct tapnet/1 files of the example, read from assets (entries repeat them A B C A B C A B).
    function _exampleNetlistFiles(Example memory e) internal view returns (bytes[] memory files) {
        files = new bytes[](3);
        for (uint256 i; i < 3; ++i) {
            bytes32 h = e.netlistValues[i];
            files[i] = vm.readFileBinary(string.concat(EXAMPLE_NETLISTS, _hex(h), ".tapnet"));
            require(sha256(files[i]) == h, "example: netlist file hash mismatch");
        }
    }

    function _one(bytes32 v) internal pure returns (bytes32[] memory a) {
        a = new bytes32[](1);
        a[0] = v;
    }

    /// Lower-case hex of a bytes32 without 0x (file names of example/netlists).
    function _hex(bytes32 h) internal pure returns (string memory) {
        bytes memory alphabet = "0123456789abcdef";
        bytes memory s = new bytes(64);
        for (uint256 i; i < 32; ++i) {
            s[2 * i] = alphabet[uint8(h[i]) >> 4];
            s[2 * i + 1] = alphabet[uint8(h[i]) & 0x0f];
        }
        return string(s);
    }
}

/// Merkle tree of TapMerkle leaves, as the standard pairs them (duplicate-free: an odd last node is carried up).
/// Same construction as test/core/CoreHelpers.sol, copied so that scripts do not depend on test code.
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

    function _up(bytes32[] memory level) private pure returns (bytes32[] memory next) {
        uint256 w = (level.length + 1) / 2;
        next = new bytes32[](w);
        for (uint256 i; i < level.length; i += 2) {
            next[i / 2] = i + 1 < level.length ? TapMerkle.nodeHash(level[i], level[i + 1]) : level[i];
        }
    }
}
