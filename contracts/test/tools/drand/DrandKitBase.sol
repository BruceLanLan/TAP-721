// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../../src/interfaces/ITapNetlistNFT.sol";
import {TapNetlistNFT} from "../../../src/core/TapNetlistNFT.sol";
import {DrandBeacon} from "../../../src/tools/drand/DrandBeacon.sol";
import {TapDrandReveal} from "../../../src/tools/drand/TapDrandReveal.sol";
import {TapDrandRevealFactory} from "../../../src/tools/drand/TapDrandRevealFactory.sol";
import {ITapDrandReveal} from "../../../src/tools/drand/ITapDrandReveal.sol";
import {MockBeacon} from "./mocks/MockBeacon.sol";

/// Its runtime contains MCOPY (0x5e) only when the project is compiled for Cancun or later.
contract RecipeProbe {
    function join(bytes memory a, bytes memory b) external pure returns (bytes memory) {
        return bytes.concat(a, b);
    }
}

/// Shared helpers of the drand reveal kit tests: the recorded quicknet rounds
/// (test/fixtures/drand-quicknet-rounds.json, made by fetch_drand_rounds.py), the EIP-2537 probe the BLS tests use to
/// skip themselves, quicknet time arithmetic, and the deployment of a kit collection with the reference initcode.
abstract contract DrandKitBase is Test {
    address internal constant BEACON = 0x777D3Ece3CB4E7D3782Da938CbCf8c2c8AcE55Ca;
    address internal constant ARACHNID = 0x4e59b44847b379578588920cA78FbF26c0B4956C;
    uint256 internal constant GENESIS = 1692803367;
    uint256 internal constant PERIOD = 3;
    /// the base of the recorded rounds; "now" in most tests is just after its time
    uint64 internal constant BASE = 33_000_000;
    uint256 internal constant MIN_LEAD = 13 hours;
    uint256 internal constant REVEAL_DELAY = 10 minutes;

    address internal admin = makeAddr("admin");
    address internal sale = makeAddr("sale");
    address internal alice = makeAddr("alice");
    address internal eve = makeAddr("eve");

    bytes internal beaconRuntime;
    mapping(uint64 round => bytes) internal sigOf;
    mapping(uint64 round => bytes32) internal randOf;
    uint64[] internal recorded;

    // ------------------------------------------------------------------ fixture and capability probes

    function _loadRounds() internal {
        string memory json = vm.readFile("test/fixtures/drand-quicknet-rounds.json");
        uint256 n = vm.parseJsonUint(json, ".count");
        for (uint256 i; i < n; ++i) {
            string memory p = string.concat(".rounds[", vm.toString(i), "].");
            uint64 r = uint64(vm.parseJsonUint(json, string.concat(p, "round")));
            sigOf[r] = vm.parseJsonBytes(json, string.concat(p, "signature"));
            randOf[r] = vm.parseJsonBytes32(json, string.concat(p, "randomness"));
            recorded.push(r);
        }
        assertEq(recorded.length, n);
    }

    /// True iff this EVM has the precompiles DrandBeacon calls: G1ADD (0x0b), PAIRING (0x0f), MAP_FP_TO_G1 (0x10).
    function _hasBls() internal view returns (bool) {
        (bool ok1, bytes memory r1) = address(0x0b).staticcall(new bytes(256));
        (bool ok2, bytes memory r2) = address(0x10).staticcall(new bytes(64));
        (bool ok3, bytes memory r3) = address(0x0f).staticcall(new bytes(384));
        return ok1 && r1.length == 128 && ok2 && r2.length == 128 && ok3 && r3.length == 32;
    }

    /// Skips the calling test (reported as skipped, not passed) on an EVM without EIP-2537.
    modifier needsBls() {
        if (!_hasBls()) {
            vm.skip(true, "EIP-2537 precompiles absent: run with --hardfork prague");
        }
        _;
    }

    // ------------------------------------------------------------------ quicknet time

    function qt(uint64 round) internal pure returns (uint256) {
        return round == 0 ? GENESIS : GENESIS + PERIOD * (uint256(round) - 1);
    }

    function roundAt(uint256 t) internal pure returns (uint64) {
        return t < GENESIS ? 0 : uint64((t - GENESIS) / PERIOD + 1);
    }

    // ------------------------------------------------------------------ deployment

    /// The canonical beacon runtime (test/fixtures/drand-beacon-code.json), not the freshly compiled one: under
    /// `--evm-version prague` the compiler emits other bytes and the controller's code hash pin would reject them.
    function _installRealBeacon() internal {
        if (beaconRuntime.length == 0) {
            string memory json = vm.readFile("test/fixtures/drand-beacon-code.json");
            beaconRuntime = vm.parseJsonBytes(json, ".DrandBeacon.runtime");
        }
        vm.etch(BEACON, beaconRuntime);
    }

    /// True iff this build uses the repository recipe (shanghai): the byte-for-byte pins hold only then.
    function _canonicalRecipe() internal pure returns (bool) {
        bytes memory code = type(RecipeProbe).runtimeCode;
        uint256 i;
        while (i < code.length) {
            uint8 op = uint8(code[i]);
            if (op >= 0x60 && op <= 0x7f) {
                i += uint256(op) - 0x5f + 1;
                continue;
            }
            if (op == 0x5e) return false; // MCOPY
            ++i;
        }
        return true;
    }

    modifier canonicalRecipeOnly() {
        if (!_canonicalRecipe()) {
            vm.skip(true, "bytecode pins hold for the repository recipe (shanghai); this build targets a later EVM");
        }
        _;
    }

    function _installMockBeacon() internal {
        vm.etch(BEACON, type(MockBeacon).runtimeCode);
    }

    function _pools() internal pure returns (ITapNetlistNFT.Pool[] memory ps) {
        ps = new ITapNetlistNFT.Pool[](2);
        ps[0] = ITapNetlistNFT.Pool("IMAGE_V1", 1, keccak256("image pool root"));
        ps[1] = ITapNetlistNFT.Pool("NETLIST_V1", 2, keccak256("netlist pool root"));
    }

    /// The reference collection's initcode without constructor arguments (forge links the TapNetlistVM library).
    function _refInitCode() internal pure returns (bytes memory) {
        return type(TapNetlistNFT).creationCode;
    }

    /// Create a kit collection through a new factory. The real beacon code must be at BEACON (the constructor pins it).
    function _create(TapDrandRevealFactory f, address admin_, uint256 delay)
        internal
        returns (TapDrandReveal ctrl, TapNetlistNFT coll)
    {
        (address c, address n) = f.create(admin_, delay, _refInitCode(), "Kit", "KIT", "https://example.invalid/meta/");
        ctrl = TapDrandReveal(c);
        coll = TapNetlistNFT(n);
    }

    /// Counts the opcodes among DELEGATECALL, CALLCODE, SELFDESTRUCT, CREATE, CREATE2 outside PUSH data.
    function _forbiddenOpcodes(bytes memory code) internal pure returns (uint256 n) {
        uint256 i;
        while (i < code.length) {
            uint8 op = uint8(code[i]);
            if (op >= 0x60 && op <= 0x7f) {
                i += uint256(op) - 0x5f + 1;
                continue;
            }
            if (op == 0xf4 || op == 0xf2 || op == 0xff || op == 0xf0 || op == 0xf5) ++n;
            ++i;
        }
    }

    function _flip(bytes memory sig) internal pure returns (bytes memory out) {
        out = bytes.concat(sig); // a copy
        out[0] = bytes1(uint8(out[0]) ^ 0x20);
    }
}
