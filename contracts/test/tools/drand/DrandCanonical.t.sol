// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {DrandKitBase} from "./DrandKitBase.sol";
import {DrandBeacon} from "../../../src/tools/drand/DrandBeacon.sol";
import {TapDrandReveal} from "../../../src/tools/drand/TapDrandReveal.sol";
import {TapDrandRevealFactory} from "../../../src/tools/drand/TapDrandRevealFactory.sol";
import {TapNetlistNFT} from "../../../src/core/TapNetlistNFT.sol";

/// The kit's bytecode and its canonical addresses are pinned here. The pinned values are those of the independent
/// build of the same sources (solc 0.8.28, optimizer 10,000 runs, shanghai, no metadata; the recipe of this
/// repository's foundry.toml): any change to the three contracts changes a hash below and fails this suite. They need
/// no EIP-2537 precompiles.
contract DrandCanonicalTest is DrandKitBase {
    bytes32 constant ARACHNID_CODEHASH = 0x2fa86add0aed31f33a762c9d88e807c475bd51d0f52bd0955754b2608f7e4989;
    bytes private constant ARACHNID_RUNTIME =
        hex"7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffe0360160008160208237"
        hex"8035828234f58015156039578182fd5b8082525050506014600cf3";

    address constant BEACON_ADDR = 0x777D3Ece3CB4E7D3782Da938CbCf8c2c8AcE55Ca;
    address constant FACTORY_ADDR = 0x1cE83c28a85574f9E16032B8B5f14794a9312f4B;
    bytes32 constant BEACON_INIT = 0x815fdcaf3572e2e7272a212e34c6e6df32ebd68775228c35402ebb9a5ec564f5;
    bytes32 constant BEACON_RUNTIME = 0x5af33305a251aaeff7728080afdf2cdf71d97395115d0a4faa98dd8c9f951fe9;
    bytes32 constant FACTORY_INIT = 0x31a39fa170899453db448f80241eeac0da2730cb919a42807058481dd4c4e5de;
    bytes32 constant FACTORY_RUNTIME = 0x8910380b54a0f2057836bebd6a496fbeef1f27921feb725b2dfa5a17de66dc80;
    address constant VM_ADDR = 0x82aF8337aa103e35b4A9C6cF11195E36E77Fa036;
    bytes32 constant VM_INIT = 0xcffcf55318d77d492dc26abdc3d28274a62860d59e2ffb886878eface8f2aac9;
    /// the reference TapNetlistNFT with the VM at VM_ADDR in its four library slots, without constructor arguments
    bytes32 constant NFT_INIT_LINKED = 0x5f3a1464d0c3400e402b50a15641848d08428edb741c690c517cadffb2da12ec;
    bytes32 constant NFT_RUNTIME_LINKED = 0x5e5920740042fabf31851307d510b67e7ba34dbf2e46c6e9ce55695648f80b69;
    bytes32 constant CONTROLLER_INIT = 0x98eea72e358d06a31b0302b4cbad3a31092361721c1f27fc26b4e73409a464ac;
    /// runtime with the 19 immutable ranges zeroed (what `type(C).runtimeCode` returns)
    bytes32 constant CONTROLLER_RUNTIME_MASKED = 0xce064e712ea7e2701cb51615240eb3ed9e42be291b7724a140cdd7f2b8920cd1;

    /// The controller's runtime with its 19 immutable ranges zero, from the compiler artifact (`type(C).runtimeCode`
    /// is not available for contracts with immutables).
    function _controllerRuntime() internal view returns (bytes memory) {
        return vm.getDeployedCode("TapDrandReveal.sol:TapDrandReveal");
    }

    function _create2(bytes memory initcode) internal pure returns (address) {
        bytes32 h = keccak256(abi.encodePacked(bytes1(0xff), ARACHNID, bytes32(0), keccak256(initcode)));
        return address(uint160(uint256(h)));
    }

    function test_pinnedBytecodeHashes() public canonicalRecipeOnly {
        assertEq(keccak256(type(DrandBeacon).creationCode), BEACON_INIT, "beacon initcode");
        assertEq(keccak256(type(DrandBeacon).runtimeCode), BEACON_RUNTIME, "beacon runtime");
        assertEq(keccak256(type(TapDrandRevealFactory).creationCode), FACTORY_INIT, "factory initcode");
        assertEq(keccak256(type(TapDrandRevealFactory).runtimeCode), FACTORY_RUNTIME, "factory runtime");
        assertEq(keccak256(type(TapDrandReveal).creationCode), CONTROLLER_INIT, "controller initcode");
        assertEq(keccak256(_controllerRuntime()), CONTROLLER_RUNTIME_MASKED, "controller runtime (immutables masked)");
    }

    /// The recorded runtime that the other suites install is the compiled contract and the pinned one.
    function test_beaconFixtureIsTheCompiledBeacon() public canonicalRecipeOnly {
        _installRealBeacon();
        assertEq(BEACON.codehash, BEACON_RUNTIME);
        assertEq(BEACON.codehash, keccak256(type(DrandBeacon).runtimeCode));
        assertEq(BEACON.code, type(DrandBeacon).runtimeCode);
    }

    /// Holds under every build: the recorded runtime is the canonical one.
    function test_beaconFixtureHashIsPinned() public {
        _installRealBeacon();
        assertEq(BEACON.codehash, BEACON_RUNTIME);
        assertEq(BEACON.code.length, 5841);
    }

    function _writeAddress(bytes memory code, uint256 offset, address a) internal pure {
        bytes20 v = bytes20(a);
        for (uint256 i; i < 20; ++i) {
            code[offset + i] = v[i];
        }
    }

    /// The collection that `factory.create` is given is the reference TapNetlistNFT linked to the canonical VM, and the
    /// VM is the one at 0x82aF... Forge links the library at a test-local address; the four slots (offsets in the
    /// initcode 5246, 5987, 7399, 10066; in the runtime 4357, 5098, 6510, 9177) are overwritten with the canonical one.
    function test_referenceCollectionHashes() public canonicalRecipeOnly {
        bytes memory vmInit = vm.getCode("TapNetlistVM.sol:TapNetlistVM");
        assertEq(keccak256(vmInit), VM_INIT, "TapNetlistVM initcode");
        assertEq(_create2(vmInit), VM_ADDR, "TapNetlistVM CREATE2 address");

        bytes memory init = _refInitCode();
        uint256[4] memory initSlots = [uint256(5246), 5987, 7399, 10066];
        for (uint256 i; i < 4; ++i) {
            _writeAddress(init, initSlots[i], VM_ADDR);
        }
        assertEq(keccak256(init), NFT_INIT_LINKED, "TapNetlistNFT initcode, VM linked");

        TapNetlistNFT c = new TapNetlistNFT("N", "N", "", address(this));
        bytes memory runtime = address(c).code;
        uint256[4] memory runtimeSlots = [uint256(4357), 5098, 6510, 9177];
        for (uint256 i; i < 4; ++i) {
            _writeAddress(runtime, runtimeSlots[i], VM_ADDR);
        }
        assertEq(runtime.length, 23815);
        assertEq(keccak256(runtime), NFT_RUNTIME_LINKED, "TapNetlistNFT runtime, VM linked");
    }

    function test_sizes() public canonicalRecipeOnly {
        assertEq(type(DrandBeacon).runtimeCode.length, 5841);
        assertEq(type(TapDrandRevealFactory).runtimeCode.length, 15726);
        assertEq(_controllerRuntime().length, 12834);
        assertLe(type(TapDrandRevealFactory).runtimeCode.length, 24576, "EIP-170");
        assertLe(type(TapDrandRevealFactory).creationCode.length, 49152, "EIP-3860");
    }

    function test_canonicalCreate2Addresses() public canonicalRecipeOnly {
        assertEq(_create2(type(DrandBeacon).creationCode), BEACON_ADDR);
        assertEq(_create2(type(TapDrandRevealFactory).creationCode), FACTORY_ADDR);
    }

    /// Deploy through the deterministic deployer exactly as on a real chain, then run the whole create path.
    function test_deployThroughArachnid() public canonicalRecipeOnly {
        vm.etch(ARACHNID, ARACHNID_RUNTIME);
        assertEq(ARACHNID.codehash, ARACHNID_CODEHASH, "deterministic deployer runtime");

        (bool ok,) = ARACHNID.call(abi.encodePacked(bytes32(0), type(DrandBeacon).creationCode));
        assertTrue(ok, "beacon deploy");
        assertEq(BEACON_ADDR.codehash, BEACON_RUNTIME, "beacon code hash at the canonical address");

        (ok,) = ARACHNID.call(abi.encodePacked(bytes32(0), type(TapDrandRevealFactory).creationCode));
        assertTrue(ok, "factory deploy");
        assertEq(FACTORY_ADDR.codehash, FACTORY_RUNTIME, "factory code hash at the canonical address");

        TapDrandRevealFactory f = TapDrandRevealFactory(FACTORY_ADDR);
        (TapDrandReveal ctrl, TapNetlistNFT coll) = _create(f, admin, 1 hours);
        assertEq(address(ctrl.DRAND_BEACON()), BEACON_ADDR);
        assertEq(ctrl.DRAND_BEACON_CODEHASH(), BEACON_RUNTIME);
        assertEq(coll.owner(), address(ctrl));
        assertEq(f.controllerOf(address(coll)), address(ctrl));
        assertEq(address(coll), vm.computeCreateAddress(address(ctrl), 1), "collection = CREATE(controller, 1)");
        assertEq(ctrl.collectionInitCodeHash(), keccak256(_refInitCode()));
    }

    /// The controller never delegates, self-destructs or creates contracts after construction (its constructor creates
    /// the collection; that code is not in the runtime).
    function test_controllerRuntimeHasNoDangerousOpcodes() public canonicalRecipeOnly {
        assertEq(_forbiddenOpcodes(_controllerRuntime()), 0, "no DELEGATECALL/CALLCODE/SELFDESTRUCT/CREATE/CREATE2");
    }
}
