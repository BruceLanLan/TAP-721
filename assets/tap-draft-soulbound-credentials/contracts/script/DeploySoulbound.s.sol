// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2 as console} from "forge-std/console2.sol";
import {SoulboundNetlistCredential} from "../src/SoulboundNetlistCredential.sol";
import {
    ITapCredential,
    ITapCredentialProven,
    ITapCredentialAttested,
    ITapCredentialClaimed
} from "../src/interfaces/ITapCredential.sol";

/// @title Test deployment of the soulbound netlist credential (TAP draft "Soulbound Credentials", ERC-5192)
/// @notice Deploys SoulboundNetlistCredential(name, symbol, baseURI) and stores the `xor` example file of
///         ../vectors.json (permissionless storeNetlist), so that netlistFile(h) answers. No credential is issued:
///         issuing needs a specification window or an issuer's signature, which are the author's to run.
///         The rebind delay is the contract constant REBIND_DELAY = 7 days (not a constructor argument).
///
///         Environment: PRIVATE_KEY (required, test key), NAME, SYMBOL, BASE_URI (optional), ALLOW_MAINNET.
///         Writes deployments/<chainId>.json (section "soulbound").
///
///         forge script script/DeploySoulbound.s.sol --rpc-url "$RPC_URL" --broadcast
contract DeploySoulbound is Script {
    uint256 internal constant ANVIL = 31337;
    uint256 internal constant XLAYER_TESTNET = 1952;
    uint256 internal constant BSC_TESTNET = 97;

    function run() external {
        uint256 key = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(key);
        _checkChain();
        console.log("chain id      ", block.chainid);
        console.log("deployer      ", deployer);
        console.log("balance (wei) ", deployer.balance);

        string memory name_ = vm.envOr("NAME", string("TAP-5192 Example Credential"));
        string memory symbol_ = vm.envOr("SYMBOL", string("TAP5192X"));
        string memory baseURI_ = vm.envOr("BASE_URI", string("https://example.invalid/tap-5192/"));

        string memory json = vm.readFile("../vectors.json");
        bytes memory xorFile = vm.parseJsonBytes(json, ".files.xor.file");
        bytes32 xorHash = vm.parseJsonBytes32(json, ".files.xor.netlistHash");
        require(sha256(xorFile) == xorHash, "vectors: xor hash mismatch");

        vm.startBroadcast(key);
        SoulboundNetlistCredential c = new SoulboundNetlistCredential(name_, symbol_, baseURI_);
        bytes32 stored = c.storeNetlist(xorFile);
        vm.stopBroadcast();
        require(stored == xorHash, "storeNetlist returned another hash");

        (uint256 maxGateWork, uint256 maxTableBytes) = c.checkBounds();
        console.log("SoulboundNetlistCredential", address(c));
        console.log("REBIND_DELAY (s)", c.REBIND_DELAY());
        console.log("stored netlist  ", vm.toString(stored));

        string memory obj = "soulbound";
        vm.serializeAddress(obj, "deployer", deployer);
        vm.serializeUint(obj, "block", block.number);
        vm.serializeUint(obj, "timestamp", block.timestamp);
        vm.serializeAddress(obj, "SoulboundNetlistCredential", address(c));
        vm.serializeString(obj, "name", name_);
        vm.serializeString(obj, "symbol", symbol_);
        vm.serializeString(obj, "baseURI", baseURI_);
        vm.serializeUint(obj, "REBIND_DELAY", c.REBIND_DELAY());
        vm.serializeUint(obj, "MAX_GATE_WORK", maxGateWork);
        vm.serializeUint(obj, "MAX_TABLE_BYTES", maxTableBytes);
        vm.serializeUint(obj, "MAX_FILE_BYTES", c.MAX_FILE_BYTES());
        vm.serializeBytes32(obj, "domainSeparator", c.domainSeparator());
        vm.serializeBytes32(obj, "storedNetlistHash", stored);
        vm.serializeString(obj, "IERC5192", "0xb45a3c0e");
        vm.serializeString(obj, "ITapCredential", _id(type(ITapCredential).interfaceId));
        vm.serializeString(obj, "ITapCredentialProven", _id(type(ITapCredentialProven).interfaceId));
        vm.serializeString(obj, "ITapCredentialAttested", _id(type(ITapCredentialAttested).interfaceId));
        string memory section =
            vm.serializeString(obj, "ITapCredentialClaimed", _id(type(ITapCredentialClaimed).interfaceId));

        string memory path = string.concat("deployments/", vm.toString(block.chainid), ".json");
        if (!vm.exists(path)) {
            string memory root = "root";
            vm.serializeUint(root, "chainId", block.chainid);
            vm.writeJson(vm.serializeString(root, "chain", _chainName()), path);
        }
        vm.writeJson(section, path, ".soulbound");
        console.log("wrote section soulbound to", path);
    }

    function _id(bytes4 id) internal pure returns (string memory) {
        return vm.toString(abi.encodePacked(id));
    }

    function _checkChain() internal view {
        uint256 id = block.chainid;
        if (id == ANVIL || id == XLAYER_TESTNET || id == BSC_TESTNET) return;
        bool mainnet = id == 1 || id == 56 || id == 196 || id == 8453;
        if (mainnet && !vm.envOr("ALLOW_MAINNET", false)) {
            revert(
                "DeploySoulbound: mainnet chain id; this package is for testnets (set ALLOW_MAINNET=true to override)"
            );
        }
        console.log("WARNING: chain id is not one this package was written for; continuing");
    }

    function _chainName() internal view returns (string memory) {
        uint256 id = block.chainid;
        if (id == ANVIL) return "anvil";
        if (id == XLAYER_TESTNET) return "X Layer Testnet";
        if (id == BSC_TESTNET) return "BNB Smart Chain Testnet";
        return "unknown";
    }
}
