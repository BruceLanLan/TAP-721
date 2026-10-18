// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, console2} from "forge-std/Test.sol";
import {ITapNetlistEval} from "../../src/interfaces/ITapNetlistEval.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {TapNetlistVM} from "../../src/core/TapNetlistVM.sol";
import {LibHarness, MerkleBuilder, MockLegacy721, Tapnet} from "./CoreHelpers.sol";

contract VMHarness {
    function eval(bytes calldata f, bytes calldata i) external pure returns (bytes memory) {
        return TapNetlistVM.eval(f, i);
    }

    function step(bytes calldata f, bytes calldata s, bytes calldata i)
        external
        pure
        returns (bytes memory, bytes memory)
    {
        return TapNetlistVM.step(f, s, i);
    }

    function evalGas(bytes calldata f, bytes calldata i) external view returns (uint256 used) {
        bytes memory fm = f;
        bytes memory im = i;
        uint256 g = gasleft();
        TapNetlistVM.eval(fm, im);
        used = g - gasleft();
    }
}

/// ITapNetlistEval against the Python reference (tap02_reference.beat) on BSC circuits 17851 (XOR),
/// 3151 (popcount8) and 17852 (Johnson counter).
contract TapNetlistEvalTest is Test {
    string json;
    bytes xorF;
    bytes popF;
    bytes johF;
    TapNetlistNFT nft;
    TapCompanion comp;
    mapping(address => uint256[3]) toks; // per collection: token holding xor, pop, johnson
    uint256[3] tok;
    VMHarness vmh = new VMHarness();
    LibHarness lib = new LibHarness();

    function setUp() public {
        json = vm.readFile(string.concat(vm.projectRoot(), "/test/fixtures/core-vectors.json"));
        xorF = vm.parseJsonBytes(json, ".eval[0].file");
        popF = vm.parseJsonBytes(json, ".eval[1].file");
        johF = vm.parseJsonBytes(json, ".johnson.file");
        nft = new TapNetlistNFT("T", "T", "", address(this));
        comp = new TapCompanion(address(new MockLegacy721()), bytes4(keccak256("uriFrozen()")), address(this));
        _setup(nft);
        _setup(comp);
    }

    function _setup(TapNetlistCore c) internal {
        bytes32[3] memory hs = [sha256(xorF), sha256(popF), sha256(johF)];
        bytes32[] memory leaves = new bytes32[](3);
        for (uint256 i; i < 3; ++i) {
            leaves[i] = TapMerkle.leafHash(i, _one(hs[i]));
        }
        ITapNetlistNFT.Pool[] memory ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("NETLIST_V1", 2, MerkleBuilder.root(leaves));
        c.commitManifest(keccak256("m"), 1, 3, ps);
        c.reveal(keccak256("s"));
        for (uint256 t = 1; t <= 3; ++t) {
            uint256 e = c.entryIndexOf(t, 0);
            c.bind(t, 0, _one(hs[e]), MerkleBuilder.proof(leaves, e));
            toks[address(c)][e] = t;
        }
        c.storeNetlist(xorF);
        c.storeNetlist(popF);
        c.storeNetlist(johF);
    }

    function _one(bytes32 v) internal pure returns (bytes32[] memory a) {
        a = new bytes32[](1);
        a[0] = v;
    }

    function _checkCombinational(TapNetlistCore c) internal {
        tok = toks[address(c)];
        for (uint256 k; k < 2; ++k) {
            string memory key = string.concat(".eval[", vm.toString(k), "]");
            bytes32 h = vm.parseJsonBytes32(json, string.concat(key, ".sha256"));
            bytes[] memory inputs = vm.parseJsonBytesArray(json, string.concat(key, ".inputs"));
            bytes[] memory outputs = vm.parseJsonBytesArray(json, string.concat(key, ".outputs"));
            assertEq(inputs.length, k == 0 ? 4 : 256);
            for (uint256 i; i < inputs.length; ++i) {
                bytes memory input = inputs[i];
                bytes memory want = outputs[i];
                assertEq(c.evalOf(tok[k], input), want, "evalOf");
                assertEq(c.evalFile(h, input), want, "evalFile");
                (bytes memory ns, bytes memory out) = c.stepOf(tok[k], "", input);
                assertEq(out, want, "stepOf");
                assertEq(ns.length, 0);
            }
        }
    }

    function _checkJohnson(TapNetlistCore c) internal {
        tok = toks[address(c)];
        bytes32 h = sha256(johF);
        bytes memory st = "";
        bytes[] memory states = vm.parseJsonBytesArray(json, ".johnson.states");
        bytes[] memory outs = vm.parseJsonBytesArray(json, ".johnson.outputs");
        assertEq(states.length, 20);
        for (uint256 i; i < 20; ++i) {
            (bytes memory ns, bytes memory out) = c.stepOf(tok[2], st, "");
            (bytes memory ns2, bytes memory out2) = c.stepFile(h, st, hex"ff"); // nIn = 0: inputs ignored
            assertEq(ns, states[i], "state");
            assertEq(out, outs[i], "outputs");
            assertEq(ns2, ns);
            assertEq(out2, out);
            st = ns;
        }
    }

    function test_collectionMatchesPython() public {
        _checkCombinational(nft);
        _checkJohnson(nft);
    }

    function test_companionMatchesPython() public {
        _checkCombinational(comp);
        _checkJohnson(comp);
    }

    function test_interfaceIds() public view {
        assertTrue(nft.supportsInterface(type(ITapNetlistEval).interfaceId));
        assertTrue(comp.supportsInterface(type(ITapNetlistEval).interfaceId));
        console2.log("ITapNetlistNFT interfaceId");
        console2.logBytes4(type(ITapNetlistNFT).interfaceId);
        console2.log("ITapNetlistEval interfaceId");
        console2.logBytes4(type(ITapNetlistEval).interfaceId);
    }

    function test_evalOfLatchReverts() public {
        tok = toks[address(nft)];
        vm.expectRevert(bytes("has latch: use step"));
        nft.evalOf(tok[2], "");
        bytes32 h = sha256(johF);
        vm.expectRevert(bytes("has latch: use step"));
        nft.evalFile(h, "");
    }

    function test_notBoundOrNotStoredReverts() public {
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, 99));
        nft.evalOf(99, "");
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, 99));
        nft.stepOf(99, "", "");
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, bytes32(uint256(1))));
        nft.evalFile(bytes32(uint256(1)), "");
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, bytes32(uint256(1))));
        nft.stepFile(bytes32(uint256(1)), "", "");
    }

    function test_lenientInputsAndExactOutputs() public {
        tok = toks[address(nft)];
        assertEq(nft.evalOf(tok[0], ""), hex"00"); // missing bytes read as 0
        assertEq(nft.evalOf(tok[0], hex"fd"), hex"01"); // bits 2..7 ignored: inputs 1,0
        assertEq(nft.evalOf(tok[0], hex"03ffff"), hex"00"); // extra bytes ignored
        assertEq(nft.evalOf(tok[1], hex"ffaa"), hex"08"); // popcount(0xff) = 8, 4 output bits
        (bytes memory ns,) = nft.stepOf(tok[2], hex"ffffffffff", ""); // 9 state bits, extra ignored
        assertEq(ns.length, 2);
        assertEq(uint8(ns[1]) & 0xfe, 0); // high bits zero
    }

    function test_malformedFilesRevert() public {
        bytes memory h = Tapnet.header(2, 1);
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(bytes.concat(h, Tapnet.nand(2, 4)), ""); // self reference
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(bytes.concat(h, hex"02"), ""); // REF
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(bytes.concat(h, hex"000000"), ""); // truncated
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(h, ""); // no records
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(bytes.concat(Tapnet.header(2, 2), Tapnet.nand(2, 3)), ""); // nOut > elements
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.step(bytes.concat(Tapnet.header(1, 1), Tapnet.latch(4)), "", ""); // latch input ≥ signals
        vm.expectRevert(TapNetlistVM.VMBadFile.selector);
        vmh.eval(bytes.concat(bytes8("TAPNET\x02\x00"), bytes8(0), Tapnet.nand(0, 0)), "");
    }

    function testFuzz_xorMatchesSolidity(uint8 x) public view {
        uint8 a = x & 1;
        uint8 b = (x >> 1) & 1;
        assertEq(uint8(vmh.eval(xorF, abi.encodePacked(x))[0]), a ^ b);
    }

    function testFuzz_popcountMatchesSolidity(uint8 x) public view {
        uint8 c;
        for (uint8 v = x; v != 0; v >>= 1) {
            c += v & 1;
        }
        assertEq(uint8(vmh.eval(popF, abi.encodePacked(x))[0]), c);
    }

    /// The VM accepts exactly the files TapNetlistCheck accepts, and otherwise reverts with one of its
    /// two errors; on success the output lengths are exact.
    function _differential(bytes memory file, bytes memory state, bytes memory inputs) internal view {
        bool valid;
        uint256 nOut;
        uint256 latch;
        try lib.check(file) returns (uint256, uint256 o, uint256, uint256 l) {
            (valid, nOut, latch) = (true, o, l);
        } catch {}
        try vmh.step(file, state, inputs) returns (bytes memory ns, bytes memory out) {
            assertTrue(valid, "VM accepted an invalid file");
            assertEq(out.length, (nOut + 7) / 8);
            assertEq(ns.length, (latch + 7) / 8);
        } catch (bytes memory err) {
            assertFalse(valid, "VM rejected a valid file");
            assertEq(bytes4(err), TapNetlistVM.VMBadFile.selector);
        }
        try vmh.eval(file, inputs) returns (bytes memory out) {
            assertTrue(valid && latch == 0);
            assertEq(out.length, (nOut + 7) / 8);
        } catch (bytes memory err) {
            if (valid) {
                assertEq(keccak256(err), keccak256(abi.encodeWithSignature("Error(string)", "has latch: use step")));
            } else {
                assertEq(bytes4(err), TapNetlistVM.VMBadFile.selector);
            }
        }
    }

    /// forge-config: default.fuzz.runs = 5000
    function testFuzz_vmRandomBytes(bytes calldata file, bytes calldata state, bytes calldata inputs) public view {
        _differential(file, state, inputs);
    }

    /// forge-config: default.fuzz.runs = 5000
    /// Valid header plus random records biased towards NAND/LATCH with near-valid references.
    function testFuzz_vmRandomRecords(uint8 nIn, uint8 nOut, uint256 seed, uint8 count, bytes calldata state)
        public
        view
    {
        bytes memory f = Tapnet.header(nIn % 9, nOut % 6);
        uint256 next = 2 + nIn % 9;
        for (uint256 i; i < count % 40; ++i) {
            uint256 r = uint256(keccak256(abi.encode(seed, i)));
            uint256 kind = r % 16;
            if (kind < 10) f = bytes.concat(f, Tapnet.nand((r >> 8) % (next + 1), (r >> 40) % (next + 1)));
            else if (kind < 15) f = bytes.concat(f, Tapnet.latch((r >> 8) % (next + 8)));
            else f = bytes.concat(f, abi.encodePacked(uint8(r >> 8)));
            ++next;
        }
        _differential(f, state, abi.encodePacked(seed));
    }

    function test_gas() public {
        tok = toks[address(nft)];
        bytes memory input = hex"b7";
        uint256 g = gasleft();
        nft.evalOf(tok[1], input);
        uint256 total = g - gasleft();
        uint256 vmOnly = vmh.evalGas(popF, input);
        console2.log("evalOf popcount8 (55 gates), call gas incl. storage read:", total);
        console2.log("  per gate:", total / 55);
        console2.log("TapNetlistVM.eval only, popcount8:", vmOnly);
        console2.log("  per gate:", vmOnly / 55);
        uint256 big = vmh.evalGas(Tapnet.chain(1204, 0), hex"03");
        console2.log("TapNetlistVM.eval only, 1,204 gates:", big);
        console2.log("  per gate:", big / 1204);
    }
}
