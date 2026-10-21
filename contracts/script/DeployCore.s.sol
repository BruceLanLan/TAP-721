// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {console2 as console} from "forge-std/console2.sol";
import {DeployBase, MerkleBuilder} from "./DeployBase.s.sol";
import {TapNetlistNFT} from "../src/core/TapNetlistNFT.sol";
import {ITapNetlistNFT} from "../src/interfaces/ITapNetlistNFT.sol";
import {ITapNetlistEval} from "../src/interfaces/ITapNetlistEval.sol";
import {ITapNetlistTokenSet} from "../src/interfaces/ITapNetlistTokenSet.sol";

/// @title Test deployment of the TAP-721 reference collection (TapNetlistNFT + TapNetlistVM library)
/// @notice Deploys the collection with the worked example of assets/tap-draft-netlist-bound-nft/example and runs
///         its whole lifecycle, so that every getter an editor checks (docs/deploy/VERIFY.md) has a value:
///         commitManifest → mint 1..8 → reveal(example seed) → bind every token in both pools → storeNetlist of
///         the three example files → freeze (unless FREEZE=false).
///         The TapNetlistVM library is deployed and linked by forge itself (the first transaction of the run); its
///         address is read back from the collection's runtime code and recorded.
///
///         Environment: PRIVATE_KEY (required, test key), NAME, SYMBOL, BASE_URI, MINT_TO, FREEZE (optional).
///
///         forge script script/DeployCore.s.sol --rpc-url "$RPC_URL" --broadcast
contract DeployCore is DeployBase {
    function run() external {
        _loadDeployer();
        Example memory e = _loadExample();

        string memory name_ = vm.envOr("NAME", string("TAP-721 Example Collection"));
        string memory symbol_ = vm.envOr("SYMBOL", string("TAP721X"));
        string memory baseURI_ = vm.envOr("BASE_URI", string("https://example.invalid/tap-example/token/"));
        address mintTo = vm.envOr("MINT_TO", deployer);
        bool doFreeze = vm.envOr("FREEZE", true);

        vm.startBroadcast(deployerKey);

        TapNetlistNFT nft = new TapNetlistNFT(name_, symbol_, baseURI_, deployer);
        nft.commitManifest(e.manifestHash, EXAMPLE_FIRST, EXAMPLE_SUPPLY, e.pools);
        for (uint256 t = EXAMPLE_FIRST; t < EXAMPLE_FIRST + EXAMPLE_SUPPLY; ++t) {
            nft.mint(mintTo, t);
        }
        nft.reveal(EXAMPLE_SEED);
        for (uint256 t = EXAMPLE_FIRST; t < EXAMPLE_FIRST + EXAMPLE_SUPPLY; ++t) {
            uint256 ei = nft.entryIndexOf(t, 0);
            nft.bind(t, 0, _one(e.imageValues[ei]), MerkleBuilder.proof(e.imageLeaves, ei));
            uint256 en = nft.entryIndexOf(t, 1);
            nft.bind(t, 1, _one(e.netlistValues[en]), MerkleBuilder.proof(e.netlistLeaves, en));
        }
        bytes[] memory files = _exampleNetlistFiles(e);
        for (uint256 i; i < files.length; ++i) {
            nft.storeNetlist(files[i]);
        }
        if (doFreeze) nft.freeze();

        // TODO(mint-bound): when the mint-bound collection (TAP-721 §8.2 reference, another branch) lands under
        // src/core/, deploy it here after the manifest collection, e.g.
        //   TapMintBoundNFT mb = new TapMintBoundNFT(name_, symbol_, baseURI_, deployer);
        // and add a "mintBound" section to deployments/<chainId>.json with the same getters as below.

        vm.stopBroadcast();

        address vmLib = _linkedLibrary(address(nft));
        _report(nft, vmLib, e, doFreeze);
    }

    /// The TapNetlistVM address linked into `nft`: the library is called with DELEGATECALL, so its address is the
    /// only 20-byte PUSH20 immediate in the runtime code that holds code and is not the collection itself.
    function _linkedLibrary(address nft) internal view returns (address lib) {
        bytes memory code = nft.code;
        for (uint256 i; i + 21 <= code.length; ++i) {
            if (code[i] != 0x73) continue; // PUSH20
            address a;
            assembly ("memory-safe") {
                a := shr(96, mload(add(add(code, 0x20), add(i, 1))))
            }
            if (a != address(0) && a != nft && a.code.length > 0) return a;
        }
    }

    function _report(TapNetlistNFT nft, address vmLib, Example memory e, bool doFreeze) internal {
        (uint256 first, uint256 supply) = nft.tokenRange();
        console.log("TapNetlistVM  ", vmLib);
        console.log("TapNetlistNFT ", address(nft));
        console.log("manifestHash  ", vm.toString(nft.manifestHash()));
        console.log("masterSeed    ", vm.toString(nft.masterSeed()));
        console.log("tokenRange    ", first, supply);
        console.log("frozen        ", nft.frozen());

        string memory obj = "core";
        _sectionHeader(obj);
        vm.serializeAddress(obj, "TapNetlistVM", vmLib);
        vm.serializeAddress(obj, "TapNetlistNFT", address(nft));
        vm.serializeString(obj, "name", nft.name());
        vm.serializeString(obj, "symbol", nft.symbol());
        vm.serializeString(obj, "baseURI", nft.baseURI());
        vm.serializeBytes32(obj, "manifestHash", nft.manifestHash());
        vm.serializeString(obj, "manifestFile", EXAMPLE_MANIFEST);
        vm.serializeBytes32(obj, "masterSeed", nft.masterSeed());
        vm.serializeUint(obj, "firstTokenId", first);
        vm.serializeUint(obj, "supply", supply);
        vm.serializeBytes32(obj, "pool0Root", e.pools[0].root);
        vm.serializeBytes32(obj, "pool1Root", e.pools[1].root);
        vm.serializeBool(obj, "frozen", doFreeze);
        vm.serializeString(obj, "ITapNetlistNFT", vm.toString(abi.encodePacked(type(ITapNetlistNFT).interfaceId)));
        vm.serializeString(obj, "ITapNetlistEval", vm.toString(abi.encodePacked(type(ITapNetlistEval).interfaceId)));
        string memory json = vm.serializeString(
            obj, "ITapNetlistTokenSet", vm.toString(abi.encodePacked(type(ITapNetlistTokenSet).interfaceId))
        );
        _writeSection("core", json);
    }
}
