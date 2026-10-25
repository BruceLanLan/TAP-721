// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {DrandKitBase} from "./DrandKitBase.sol";
import {DrandBeacon} from "../../../src/tools/drand/DrandBeacon.sol";

/// DrandBeacon against real quicknet rounds recorded from two relays (test/fixtures/drand-quicknet-rounds.json).
/// Everything that needs the EIP-2537 precompiles skips itself on an EVM without them; the default `forge test`
/// (shanghai) therefore runs the fail-closed tests only. Run the rest with
///     forge test --hardfork prague --match-path "test/tools/drand/*"
contract DrandBeaconTest is DrandKitBase {
    DrandBeacon internal beacon;

    // Base field modulus p, 48 bytes
    bytes constant P48 =
        hex"1a0111ea397fe69a4b1ba7b6434bacd764774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab";

    event RoundVerified(uint64 indexed round, bytes32 randomness);

    function setUp() public {
        _loadRounds();
        _installRealBeacon(); // the canonical bytes at the canonical address
        beacon = DrandBeacon(BEACON);
    }

    // ------------------------------------------------------------------ constants and time (no precompiles)

    function test_constants() public view {
        assertEq(beacon.CHAIN_HASH(), 0x52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971);
        assertEq(beacon.GENESIS(), 1692803367);
        assertEq(beacon.PERIOD(), 3);
        assertEq(beacon.latestVerifiedRound(), 0);
    }

    function test_quicknetTimeAndRoundAt() public view {
        assertEq(beacon.quicknetTime(0), GENESIS);
        assertEq(beacon.quicknetTime(1), GENESIS);
        assertEq(beacon.quicknetTime(2), GENESIS + 3);
        assertEq(beacon.roundAt(GENESIS - 1), 0);
        assertEq(beacon.roundAt(GENESIS), 1);
        assertEq(beacon.roundAt(GENESIS + 2), 1);
        assertEq(beacon.roundAt(GENESIS + 3), 2);
        // the recorded rounds are real: round 33,145,012 was produced in October 2026
        assertEq(beacon.quicknetTime(33_145_012), GENESIS + 3 * 33_145_011);
    }

    function testFuzz_roundAtInvertsQuicknetTime(uint64 round, uint8 offset) public view {
        round = uint64(bound(round, 1, type(uint48).max));
        offset = uint8(bound(offset, 0, 2));
        uint256 t = beacon.quicknetTime(round);
        assertEq(beacon.roundAt(t + offset), round);
        assertEq(beacon.roundAt(t - 1), round - 1);
    }

    function test_fixtureIsComplete() public view {
        assertEq(recorded.length, 49);
        uint256 a0;
        uint256 a1;
        for (uint256 i; i < recorded.length; ++i) {
            bytes memory s = sigOf[recorded[i]];
            assertEq(s.length, 48);
            assertEq(sha256(s), randOf[recorded[i]], "randomness = SHA-256(signature)");
            if (uint8(s[0]) & 0xe0 == 0xa0) ++a1;
            else ++a0;
        }
        assertGt(a0, 5, "fixture has signatures with sort flag 0");
        assertGt(a1, 5, "fixture has signatures with sort flag 1");
    }

    // ------------------------------------------------------------------ fails closed

    function test_gasTooLowIsNotAnInvalidSignature() public {
        bytes memory sig = sigOf[BASE];
        (bool ok, bytes memory ret) =
            address(beacon).staticcall{gas: 150_000}(abi.encodeCall(DrandBeacon.check, (BASE, sig)));
        assertFalse(ok);
        assertEq(bytes4(ret), DrandBeacon.GasTooLow.selector);
        (ok, ret) = address(beacon).call{gas: 150_000}(abi.encodeCall(DrandBeacon.verify, (BASE, sig)));
        assertFalse(ok);
        assertEq(bytes4(ret), DrandBeacon.GasTooLow.selector);
        assertEq(beacon.randomnessOf(BASE), 0);
    }

    /// Without EIP-2537 a real, valid signature must never verify and nothing may be cached.
    function test_withoutPrecompilesNothingVerifies() public {
        if (_hasBls()) vm.skip(true, "this EVM has the EIP-2537 precompiles");
        for (uint256 i; i < recorded.length; i += 7) {
            uint64 r = recorded[i];
            (bool ok, bytes32 rnd) = beacon.check{gas: 3_000_000}(r, sigOf[r]);
            assertFalse(ok);
            assertEq(rnd, 0);
            vm.expectRevert(abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, r));
            beacon.verify{gas: 3_000_000}(r, sigOf[r]);
            assertEq(beacon.randomnessOf(r), 0);
        }
        assertEq(beacon.latestVerifiedRound(), 0);
    }

    // ------------------------------------------------------------------ real rounds (EIP-2537)

    function test_verifiesEveryRecordedRound() public needsBls {
        uint64 highest;
        for (uint256 i; i < recorded.length; ++i) {
            uint64 r = recorded[i];
            (bool ok, bytes32 rnd) = beacon.check{gas: 3_000_000}(r, sigOf[r]);
            assertTrue(ok, "check");
            assertEq(rnd, randOf[r], "check randomness");
            vm.expectEmit(true, false, false, true, address(beacon));
            emit RoundVerified(r, randOf[r]);
            assertEq(beacon.verify{gas: 3_000_000}(r, sigOf[r]), randOf[r], "verify");
            assertEq(beacon.randomnessOf(r), randOf[r], "stored");
            if (r > highest) highest = r;
            assertEq(beacon.latestVerifiedRound(), highest, "latest = highest so far, in any order");
        }
        assertEq(beacon.latestVerifiedRound(), 33_145_012);
    }

    function test_checkStoresNothing() public needsBls {
        (bool ok,) = beacon.check{gas: 3_000_000}(BASE, sigOf[BASE]);
        assertTrue(ok);
        assertEq(beacon.randomnessOf(BASE), 0);
        assertEq(beacon.latestVerifiedRound(), 0);
    }

    function test_cachePath() public needsBls {
        bytes memory sig = sigOf[BASE];
        uint256 g = gasleft();
        beacon.verify{gas: 3_000_000}(BASE, sig);
        uint256 first = g - gasleft();
        g = gasleft();
        assertEq(beacon.verify(BASE, sig), randOf[BASE]);
        uint256 cached = g - gasleft();
        emit log_named_uint("verify, first call (gas)", first);
        emit log_named_uint("verify, cached round (gas)", cached);
        assertLt(cached, 40_000, "cached path compares one SHA-256 and does no BLS");
        assertGt(first, cached * 5);

        // a cached round accepts exactly its signature: other bytes, the flipped sort flag, another round's bytes
        vm.expectRevert(abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, BASE));
        beacon.verify(BASE, _flip(sig));
        vm.expectRevert(abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, BASE));
        beacon.verify(BASE, sigOf[BASE + 1]);
        vm.expectRevert(abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, BASE));
        beacon.verify(BASE, "");

        // check() ignores the cache: it is the verifier's self-test and always runs the full check
        g = gasleft();
        (bool ok, bytes32 rnd) = beacon.check{gas: 3_000_000}(BASE, sig);
        uint256 checkGas = g - gasleft();
        emit log_named_uint("check (gas)", checkGas);
        assertTrue(ok);
        assertEq(rnd, randOf[BASE]);
        assertGt(checkGas, 100_000);
        (ok,) = beacon.check{gas: 3_000_000}(BASE, _flip(sig));
        assertFalse(ok, "check still rejects the flipped copy of a cached round");
    }

    function test_gasOfAFirstVerification() public needsBls {
        uint256 g = gasleft();
        beacon.verify{gas: 3_000_000}(BASE + 1, sigOf[BASE + 1]);
        uint256 used = g - gasleft();
        emit log_named_uint("verify, new round (gas)", used);
        assertLt(used, 450_000);
    }

    // ------------------------------------------------------------------ malformed and wrong signatures

    function _rejected(uint64 round, bytes memory sig, string memory why) internal {
        (bool ok, bytes32 rnd) = beacon.check{gas: 3_000_000}(round, sig);
        assertFalse(ok, why);
        assertEq(rnd, 0, why);
        vm.expectRevert(abi.encodeWithSelector(DrandBeacon.InvalidSignature.selector, round));
        beacon.verify{gas: 3_000_000}(round, sig);
        assertEq(beacon.randomnessOf(round), 0, why);
    }

    function _with(bytes memory sig, uint8 keepMask, uint8 setBits) internal pure returns (bytes memory out) {
        out = bytes.concat(sig); // a copy
        out[0] = bytes1((uint8(out[0]) & keepMask) | setBits);
    }

    function test_rejectsWrongLengths() public needsBls {
        bytes memory s = sigOf[BASE];
        _rejected(BASE, "", "empty");
        _rejected(BASE, new bytes(47), "47 zero bytes");
        _rejected(BASE, new bytes(49), "49 zero bytes");
        _rejected(BASE, bytes.concat(s, hex"00"), "valid signature plus a byte");
        bytes memory shortSig = new bytes(47);
        for (uint256 i; i < 47; ++i) shortSig[i] = s[i];
        _rejected(BASE, shortSig, "valid signature minus a byte");
        _rejected(BASE, bytes.concat(s, s), "two signatures");
    }

    function test_rejectsBadFlagBytes() public needsBls {
        bytes memory s = sigOf[BASE];
        _rejected(BASE, _with(s, 0x1f, 0x00), "uncompressed flag (compression bit clear)");
        _rejected(BASE, _with(s, 0x1f, 0x20), "sort flag without the compression bit");
        _rejected(BASE, _with(s, 0x1f, 0x40), "infinity flag without the compression bit");
        _rejected(BASE, _with(s, 0x1f, 0xc0), "infinity flag set");
        _rejected(BASE, _with(s, 0x1f, 0xe0), "infinity and sort flags set");
        bytes memory inf = new bytes(48);
        inf[0] = 0xc0;
        _rejected(BASE, inf, "the point at infinity");
        _rejected(BASE, new bytes(48), "48 zero bytes");
    }

    function test_rejectsOutOfFieldAndOffCurveX() public needsBls {
        bytes memory x = bytes.concat(P48); // x = p: not reduced
        x[0] = bytes1(uint8(x[0]) | 0x80);
        _rejected(BASE, x, "x = p");
        bytes memory big = new bytes(48);
        for (uint256 i; i < 48; ++i) big[i] = 0xff;
        big[0] = 0x9f; // compressed, x = 2^381 - 1 > p
        _rejected(BASE, big, "x > p");
        bytes memory one = new bytes(48);
        one[0] = 0x80;
        one[47] = 0x01; // x = 1: x^3 + 4 = 5 is not a square mod p
        _rejected(BASE, one, "x = 1, not on the curve");
        // x = 4: x^3 + 4 = 68; on curve or not, the pairing must reject a point that is not the right signature
        bytes memory four = new bytes(48);
        four[0] = 0x80;
        four[47] = 0x04;
        _rejected(BASE, four, "arbitrary small x");
    }

    /// x' = x + p with the same flags is the same point modulo p but another encoding. If the beacon reduced x instead of
    /// requiring x < p, one round would have two signatures and so two randomness values.
    function test_rejectsTheNonReducedCopyOfX() public needsBls {
        uint256 tested;
        for (uint256 i; i < recorded.length; ++i) {
            uint64 r = recorded[i];
            (bool fits, bytes memory aliased) = _addP(sigOf[r]);
            if (!fits) continue; // x + p must still fit in the 381 bits below the flag bits
            ++tested;
            _rejected(r, aliased, "x + p");
        }
        assertGt(tested, 5, "enough recorded rounds have x < 2^381 - p");
    }

    function _addP(bytes memory sig) internal pure returns (bool fits, bytes memory out) {
        uint256 hi = uint256(uint128(bytes16(sig)));
        uint256 lo;
        assembly ("memory-safe") {
            lo := mload(add(sig, 48))
        }
        uint256 flags = hi & ~uint256(0x1fffffffffffffffffffffffffffffff);
        uint256 xHi = hi & 0x1fffffffffffffffffffffffffffffff;
        uint256 pHi = 0x1a0111ea397fe69a4b1ba7b6434bacd7;
        uint256 pLo = 0x64774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab;
        uint256 lo2;
        unchecked {
            lo2 = lo + pLo;
        }
        uint256 hi2 = xHi + pHi + (lo2 < lo ? 1 : 0);
        fits = hi2 <= 0x1fffffffffffffffffffffffffffffff;
        out = abi.encodePacked(uint128(flags | hi2), lo2);
    }

    function test_rejectsValidPointsThatAreNotTheSignature() public needsBls {
        bytes memory s = sigOf[BASE];
        _rejected(BASE, _flip(s), "the negated point (sort flag flipped)");
        _rejected(BASE, sigOf[BASE + 1], "the signature of the next round");
        _rejected(BASE + 1, s, "the signature of the previous round");
        _rejected(BASE - 1, s, "round - 1");
        _rejected(0, s, "round 0 is never valid");
        _rejected(type(uint64).max, s, "a round far in the future");
        // single-bit damage inside x: either off the curve or a different point
        for (uint256 i = 1; i < 48; i += 9) {
            bytes memory d = bytes.concat(s);
            d[i] = bytes1(uint8(d[i]) ^ 0x01);
            _rejected(BASE, d, "one flipped bit");
        }
    }

    function test_failedVerifyLeavesNoTraceAndAValidOneStillWorks() public needsBls {
        bytes memory s = sigOf[BASE];
        _rejected(BASE, _flip(s), "negated");
        assertEq(beacon.latestVerifiedRound(), 0);
        assertEq(beacon.verify{gas: 3_000_000}(BASE, s), randOf[BASE], "the right signature is unaffected");
    }
}
