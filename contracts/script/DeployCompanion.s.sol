// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {console2 as console} from "forge-std/console2.sol";
import {DeployBase, MerkleBuilder} from "./DeployBase.s.sol";
import {TapCompanion} from "../src/core/TapCompanion.sol";
import {ITapCompanion} from "../src/interfaces/ITapCompanion.sol";
import {ITapNetlistNFT} from "../src/interfaces/ITapNetlistNFT.sol";
import {ERC721Min} from "../src/vendor/ERC721Min.sol";
import {Owned} from "../src/vendor/Owned.sol";

/// @notice Stand-in for a legacy ERC-721 such as TapeCode-Test1: owner(), a base URI the owner can freeze,
///         and the `uriFrozen()` getter the companion probes. Deployed only when LEGACY_COLLECTION is not set.
///         Not part of the standard; a test fixture that lives in script/ on purpose.
contract ExampleLegacy721 is ERC721Min, Owned {
    string public baseURI;
    bool public uriFrozen;

    constructor(string memory name_, string memory symbol_, string memory baseURI_, address owner_)
        ERC721Min(name_, symbol_)
        Owned(owner_)
    {
        baseURI = baseURI_;
    }

    function mint(address to, uint256 tokenId) external onlyOwner {
        _mint(to, tokenId);
    }

    function freezeURI() external onlyOwner {
        uriFrozen = true;
    }

    function tokenURI(uint256 tokenId) public view override returns (string memory) {
        _requireOwned(tokenId);
        return string.concat(baseURI, vm_toString(tokenId));
    }

    function vm_toString(uint256 v) private pure returns (string memory s) {
        uint256 len = 1;
        for (uint256 t = v; t >= 10; t /= 10) {
            ++len;
        }
        bytes memory b = new bytes(len);
        for (; len > 0; v /= 10) {
            b[--len] = bytes1(uint8(48 + v % 10));
        }
        return string(b);
    }
}

/// @title Test deployment of the TAP-721 companion (TapCompanion for an existing ERC-721)
/// @notice Without LEGACY_COLLECTION, deploys ExampleLegacy721 (8 tokens to the deployer, URI frozen) and a
///         companion for it, then commits the example manifest, reveals, binds, stores the netlists, endorses
///         (the deployer is the legacy owner) and seals, so frozen() latches true. With LEGACY_COLLECTION set,
///         deploys the companion for that contract and commits + reveals only: endorse() must then be called by
///         the legacy owner, and seal() by the deployer, outside this script.
///
///         Environment: PRIVATE_KEY (required), LEGACY_COLLECTION, URI_FROZEN_SELECTOR (default uriFrozen()),
///         BASE_URI (optional).
///
///         forge script script/DeployCompanion.s.sol --rpc-url "$RPC_URL" --broadcast
contract DeployCompanion is DeployBase {
    function run() external {
        _loadDeployer();
        Example memory e = _loadExample();

        address legacy = vm.envOr("LEGACY_COLLECTION", address(0));
        bytes4 selector = bytes4(vm.envOr("URI_FROZEN_SELECTOR", bytes32(bytes4(keccak256("uriFrozen()")))));
        string memory baseURI_ = vm.envOr("BASE_URI", string("https://example.invalid/tap-example/legacy/"));
        bool example = legacy == address(0);

        vm.startBroadcast(deployerKey);

        if (example) {
            ExampleLegacy721 l = new ExampleLegacy721("TAP-721 Example Legacy", "TAP721L", baseURI_, deployer);
            for (uint256 t = EXAMPLE_FIRST; t < EXAMPLE_FIRST + EXAMPLE_SUPPLY; ++t) {
                l.mint(deployer, t);
            }
            l.freezeURI();
            legacy = address(l);
        }

        TapCompanion c = new TapCompanion(legacy, selector, deployer);
        c.commitManifest(e.manifestHash, EXAMPLE_FIRST, EXAMPLE_SUPPLY, e.pools);
        c.reveal(EXAMPLE_SEED);
        for (uint256 t = EXAMPLE_FIRST; t < EXAMPLE_FIRST + EXAMPLE_SUPPLY; ++t) {
            uint256 ei = c.entryIndexOf(t, 0);
            c.bind(t, 0, _one(e.imageValues[ei]), MerkleBuilder.proof(e.imageLeaves, ei));
            uint256 en = c.entryIndexOf(t, 1);
            c.bind(t, 1, _one(e.netlistValues[en]), MerkleBuilder.proof(e.netlistLeaves, en));
        }
        bytes[] memory files = _exampleNetlistFiles(e);
        for (uint256 i; i < files.length; ++i) {
            c.storeNetlist(files[i]);
        }
        if (example) {
            c.endorse(); // deployer == legacy owner
            c.seal(); // latches frozen(): sealed + endorsed + legacy uriFrozen()
        }

        vm.stopBroadcast();

        console.log("legacy        ", legacy, example ? "(ExampleLegacy721)" : "(given)");
        console.log("TapCompanion  ", address(c));
        console.log("endorsed      ", c.endorsed());
        console.log("isSealed      ", c.isSealed());
        console.log("frozen        ", c.frozen());

        string memory obj = "companion";
        _sectionHeader(obj);
        vm.serializeAddress(obj, "TapCompanion", address(c));
        vm.serializeAddress(obj, "collection", legacy);
        vm.serializeBool(obj, "exampleLegacy", example);
        vm.serializeString(obj, "uriFrozenSelector", vm.toString(abi.encodePacked(selector)));
        vm.serializeBytes32(obj, "manifestHash", c.manifestHash());
        vm.serializeBytes32(obj, "masterSeed", c.masterSeed());
        vm.serializeBool(obj, "endorsed", c.endorsed());
        vm.serializeBool(obj, "sealed", c.isSealed());
        vm.serializeBool(obj, "frozen", c.frozen());
        vm.serializeString(obj, "ITapCompanion", vm.toString(abi.encodePacked(type(ITapCompanion).interfaceId)));
        string memory json =
            vm.serializeString(obj, "ITapNetlistNFT", vm.toString(abi.encodePacked(type(ITapNetlistNFT).interfaceId)));
        _writeSection("companion", json);
    }
}
