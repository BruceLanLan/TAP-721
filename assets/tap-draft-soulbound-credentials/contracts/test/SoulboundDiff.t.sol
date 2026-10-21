// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console} from "forge-std/Test.sol";
import {SoulboundNetlistCredential} from "../src/SoulboundNetlistCredential.sol";

/// @notice Differential test: the Solidity truth-table hash and design key against the Python reference, on the
///         random files of the `differential` section of ../vectors.json (the reviewer's generator, seed 2026).
contract SoulboundDiffTest is Test {
    function test_pythonVsSolidity_inspect() public {
        SoulboundNetlistCredential sbt = new SoulboundNetlistCredential("d", "d", "d/");
        string memory json = vm.readFile("../vectors.json");
        uint256 n;
        while (vm.keyExistsJson(json, string.concat(".differential[", vm.toString(n), "]"))) n++;
        assertGt(n, 0);
        uint256 bad;
        for (uint256 i; i < n; i++) {
            string memory p = string.concat(".differential[", vm.toString(i), "]");
            (bytes32 dk, bytes32 tt) = sbt.inspect(vm.parseJsonBytes(json, string.concat(p, ".file")));
            if (dk != vm.parseJsonBytes32(json, string.concat(p, ".designKey"))
                    || tt != vm.parseJsonBytes32(json, string.concat(p, ".truthTableHash"))) {
                bad++;
                console.log("mismatch in differential case", i);
            }
        }
        console.log("differential cases", n, "mismatches", bad);
        assertEq(bad, 0);
    }
}
