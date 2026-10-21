// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {SoulboundNetlistCredential} from "../src/SoulboundNetlistCredential.sol";
import {ITapCredentialProven} from "../src/interfaces/ITapCredential.sol";

/// @notice Worst-case gas of `reveal` (check, design key, truth table, storage, mint) at the corners of the work
///         bounds of §4.4 item 2, each in its own unique series (so the design-key SSTORE of §4.6 is included). Every case must stay at or below 12,000,000 gas of execution, plus intrinsic
///         calldata cost, so that the transaction fits 16,777,216 gas (EIP-7825).
contract SoulboundGasTest is Test {
    SoulboundNetlistCredential internal sbt;
    uint256 internal constant BUDGET = 12_000_000;

    function setUp() public {
        sbt = new SoulboundNetlistCredential("g", "g", "g/");
    }

    /// A file with `n` NAND records over `nIn` inputs and `nOut` outputs, with pseudo-random wiring.
    function _file(uint32 nIn, uint32 nOut, uint256 n) internal pure returns (bytes memory r) {
        r = new bytes(16 + 7 * n);
        bytes memory h = bytes.concat("TAPNET", hex"0100", bytes4(nIn), bytes4(nOut));
        for (uint256 i; i < 16; i++) {
            r[i] = h[i];
        }
        for (uint256 k; k < n; k++) {
            uint256 hi = 2 + nIn + k;
            uint256 a = (k * 7919 + 1) % hi;
            uint256 b = (k * 104729 + 3) % hi;
            uint256 o = 16 + 7 * k;
            r[o + 1] = bytes1(uint8(a >> 16));
            r[o + 2] = bytes1(uint8(a >> 8));
            r[o + 3] = bytes1(uint8(a));
            r[o + 4] = bytes1(uint8(b >> 16));
            r[o + 5] = bytes1(uint8(b >> 8));
            r[o + 6] = bytes1(uint8(b));
        }
    }

    function _calldataGas(bytes memory f) internal pure returns (uint256 g) {
        g = 21_000;
        for (uint256 i; i < f.length; i++) {
            g += f[i] == 0 ? 4 : 16;
        }
    }

    function _reveal(uint32 nIn, uint32 nOut, uint32 gates, string memory what) internal returns (uint256 used) {
        bytes memory f = _file(nIn, nOut, gates);
        (, bytes32 tt) = sbt.inspect(f);
        ITapCredentialProven.Spec memory s;
        s.registrant = address(this);
        s.nIn = nIn;
        s.nOut = nOut;
        s.target = tt;
        s.maxGates = gates;
        s.commitStart = uint64(block.timestamp);
        s.commitEnd = uint64(block.timestamp) + 10;
        s.revealEnd = uint64(block.timestamp) + 20;
        s.infoHash = keccak256(bytes(what));
        // a non-zero series adds the design-key SSTORE of §4.6, the costliest path of a reveal
        s.unique = true;
        s.series = keccak256(bytes(what));
        bytes32 id = sbt.registerSpec(s);
        address u = address(uint160(uint256(keccak256(bytes(what)))));
        bytes32 c = sbt.commitmentOf(id, u, 0, sha256(f), bytes32(0));
        vm.prank(u);
        sbt.commit(id, c);
        vm.warp(block.timestamp + 10);
        uint256 g = gasleft();
        sbt.reveal(id, u, 0, f, bytes32(0));
        used = g - gasleft();
        console.log(what);
        console.log("  reveal execution gas", used, "intrinsic+calldata", _calldataGas(f));
        assertLe(used, BUDGET, what);
        assertLt(used + _calldataGas(f) + 1_000_000, 16_777_216, what);
        vm.warp(block.timestamp + 20);
    }

    /// The largest maxGates the gate-work bound allows for nIn inputs.
    function _maxGates(uint32 nIn) internal view returns (uint32) {
        return uint32(sbt.MAX_GATE_WORK() / sbt.gateWork(nIn, 1));
    }

    function test_gasRevealCorners() public {
        // nIn 16: 237 gates; with 16 outputs the table bound is reached too (16 x 8192 bytes = 2^17)
        _reveal(16, 1, _maxGates(16), "nIn 16, nOut 1, 237 gates (gate work bound)");
        _reveal(16, 16, _maxGates(16), "nIn 16, nOut 16, 237 gates (both bounds)");
        _reveal(14, 64, _maxGates(14), "nIn 14, nOut 64, 780 gates (both bounds)");
        _reveal(13, 128, _maxGates(13), "nIn 13, nOut 128, 1260 gates (both bounds)");
        _reveal(12, 256, _maxGates(12), "nIn 12, nOut 256, 1820 gates (both bounds)");
        _reveal(10, 1024, _maxGates(10), "nIn 10, nOut 1024, 2730 gates (both bounds)");
        _reveal(9, 2048, _maxGates(9), "nIn 9, nOut 2048, 2978 gates (both bounds)");
        _reveal(8, 3120, _maxGates(8), "nIn 8, nOut 3120, 3120 gates (gate work bound)");
        _reveal(8, 1, _maxGates(8), "nIn 8, nOut 1, 3120 gates (gate work bound)");
        _reveal(2, 3120, _maxGates(2), "nIn 2, nOut 3120, 3120 gates (gate work bound)");
        _reveal(0, 3120, _maxGates(0), "nIn 0, nOut 3120, 3120 gates (gate work bound)");
    }

    function test_boundsRejectBeyond() public {
        ITapCredentialProven.Spec memory s;
        s.registrant = address(this);
        s.target = bytes32(uint256(1));
        s.commitStart = 1;
        s.commitEnd = 2;
        s.revealEnd = 3;
        s.nIn = 16;
        s.nOut = 1;
        s.maxGates = 238; // (256 + 20) x 238 > 2^16
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "gate work"));
        sbt.registerSpec(s);
        s.nOut = 17; // 17 x 8192 bytes > 2^17
        s.maxGates = 17;
        s.nIn = 16;
        vm.expectRevert(abi.encodeWithSelector(SoulboundNetlistCredential.BadSpec.selector, "table size"));
        sbt.registerSpec(s);
        s.nIn = 13;
        s.nOut = 4096; // the reviewer's case: 4096 x 1024 bytes
        s.maxGates = 4096;
        vm.expectRevert();
        sbt.registerSpec(s);
        (uint256 w, uint256 t) = sbt.checkBounds();
        assertEq(w, 1 << 16);
        assertEq(sbt.gateWork(16, 237), 276 * 237);
        assertEq(sbt.tableBytes(16, 16), 1 << 17);
        assertEq(t, 1 << 17);
    }
}
