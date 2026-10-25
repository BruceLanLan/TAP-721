// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title drand quicknet beacon, verified on chain
/// @notice Ownerless cache of drand quicknet randomness. `verify(round, sig)` checks the round's BLS signature with
///         the EIP-2537 precompiles and stores randomness = SHA-256(signature), as drand defines it.
///         Scheme bls-unchained-g1-rfc9380: signature on G1, group public key on G2, message = SHA-256(u64be(round)),
///         hash to G1 per RFC 9380 (expand_message_xmd with SHA-256, MAP_FP_TO_G1 twice, G1ADD; the precompile
///         clears the cofactor). Check: e(sig, -g2) * e(H(m), pk) == 1.
///         Only the canonical 48-byte compressed encoding is accepted (compression flag set, infinity flag clear,
///         x < p as given, sort flag matching y), so a round has exactly one randomness value.
contract DrandBeacon {
    /// quicknet as published by api.drand.sh and drand.cloudflare.com (checked 2026-10-25)
    bytes32 public constant CHAIN_HASH = 0x52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971;
    uint256 public constant GENESIS = 1692803367;
    uint256 public constant PERIOD = 3;

    // Base field modulus p (381 bits): high 16 bytes and low 32 bytes; (p - 1) / 2 the same way.
    uint256 private constant P_HI = 0x1a0111ea397fe69a4b1ba7b6434bacd7;
    uint256 private constant P_LO = 0x64774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab;
    uint256 private constant HALF_HI = 0x0d0088f51cbff34d258dd3db21a5d66b;
    uint256 private constant HALF_LO = 0xb23ba5c279c2895fb39869507b587b120f55ffff58a9ffffdcff7fffffffd555;

    bytes private constant P48 =
        hex"1a0111ea397fe69a4b1ba7b6434bacd764774b84f38512bf6730d2a0f6b0f6241eabfffeb153ffffb9feffffffffaaab";
    /// (p + 1) / 4: square roots in Fp, p = 3 mod 4
    bytes private constant SQRT_EXP =
        hex"0680447a8e5ff9a692c6e9ed90d2eb35d91dd2e13ce144afd9cc34a83dac3d8907aaffffac54ffffee7fbfffffffeaab";
    /// DST ‖ u8(len(DST)) of expand_message_xmd; len = 43 = '+'
    bytes private constant DST_PRIME = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_+";
    /// -g2 in EIP-2537 encoding (x.c0, x.c1, y.c0, y.c1, each 64 bytes)
    bytes private constant NEG_G2 =
        hex"00000000000000000000000000000000024aa2b2f08f0a91260805272dc51051"
        hex"c6e47ad4fa403b02b4510b647ae3d1770bac0326a805bbefd48056c8c121bdb8"
        hex"0000000000000000000000000000000013e02b6052719f607dacd3a088274f65"
        hex"596bd0d09920b61ab5da61bbdc7f5049334cf11213945d57e5ac7d055d042b7e"
        hex"000000000000000000000000000000000d1b3cc2c7027888be51d9ef691d77bc"
        hex"b679afda66c73f17f9ee3837a55024f78c71363275a75d75d86bab79f74782aa"
        hex"0000000000000000000000000000000013fa4d4a0ad8b1ce186ed5061789213d"
        hex"993923066dddaf1040bc3ff59f825c78df74f2d75467e25e0f55f8a00fa030ed";
    /// quicknet group public key 83cf0f28…ece45a in EIP-2537 encoding
    bytes private constant PK =
        hex"000000000000000000000000000000000d1fec758c921cc22b0e17e63aaf4bcb"
        hex"5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a"
        hex"0000000000000000000000000000000003cf0f2896adee7eb8b5f01fcad39122"
        hex"12c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d106451"
        hex"000000000000000000000000000000000e5db2b6bfbb01c867749cadffca88b3"
        hex"6c24f3012ba09fc4d3022c5c37dce0f977d3adb5d183c7477c442b1f04515273"
        hex"0000000000000000000000000000000001a714f2edb74119a2f2b0d5a7c75ba9"
        hex"02d163700a61bc224ededd8e63aef7be1aaf8e93d7a9718b047ccddb3eb5d68b";

    address private constant MODEXP = address(0x05);
    address private constant G1ADD = address(0x0b);
    address private constant PAIRING = address(0x0f);
    address private constant MAP_FP_TO_G1 = address(0x10);

    // Gas caps per precompile call. An EIP-2537 error burns all gas it was given, so the caps bound what a bad
    // input costs its submitter; they are set well above both price schedules a chain may run, because the
    // contract is immutable: the square-root modexp costs 4,536 under EIP-2565 and 36,432 under EIP-7883 (Osaka,
    // OP Stack "Karst"); MAP_FP_TO_G1 5,500, G1ADD 375 and PAIRING k=2 102,900 under EIP-2537.
    uint256 private constant GAS_MODEXP = 200_000;
    uint256 private constant GAS_G1ADD = 20_000;
    uint256 private constant GAS_MAP = 60_000;
    uint256 private constant GAS_PAIRING = 500_000;

    /// Randomness of a verified round; zero until verified.
    mapping(uint64 round => bytes32) public randomnessOf;
    /// Highest round verified so far (the reveal controller reads it for its clock).
    uint64 public latestVerifiedRound;

    event RoundVerified(uint64 indexed round, bytes32 randomness);

    error InvalidSignature(uint64 round);
    /// The caller left too little gas for a precompile call; retried with more gas the same input may verify.
    error GasTooLow();

    /// @notice Verify and cache a round. Anyone may call. For a cached round only the 48 bytes are compared with
    ///         the stored hash, so `sig` must still be exactly that round's signature. Reverts GasTooLow rather
    ///         than InvalidSignature when the gas left cannot cover the precompiles (give the call about 600k gas).
    function verify(uint64 round, bytes calldata sig) external returns (bytes32 randomness) {
        randomness = randomnessOf[round];
        if (randomness != 0) {
            if (sha256(sig) != randomness) revert InvalidSignature(round);
            return randomness;
        }
        if (!_valid(round, sig)) revert InvalidSignature(round);
        randomness = sha256(sig);
        randomnessOf[round] = randomness;
        if (round > latestVerifiedRound) latestVerifiedRound = round;
        emit RoundVerified(round, randomness);
    }

    /// @notice Check a signature without storing anything. Always runs the full check, even for a cached round,
    ///         so it serves as the self-test of a deployed verifier. `ok = false` always means a bad input: too
    ///         little gas reverts GasTooLow instead.
    function check(uint64 round, bytes calldata sig) external view returns (bool ok, bytes32 randomness) {
        ok = _valid(round, sig);
        if (ok) randomness = sha256(sig);
    }

    /// @notice Time at which quicknet round `round` is produced; genesis for round 0, as in drand's TimeOfRound.
    function quicknetTime(uint64 round) public pure returns (uint256) {
        if (round == 0) return GENESIS;
        return GENESIS + PERIOD * (uint256(round) - 1);
    }

    /// @notice The latest quicknet round produced at or before `timestamp`; zero before genesis.
    function roundAt(uint256 timestamp) public pure returns (uint64) {
        if (timestamp < GENESIS) return 0;
        return uint64((timestamp - GENESIS) / PERIOD + 1);
    }

    function _valid(uint64 round, bytes calldata sig) private view returns (bool) {
        if (round == 0) return false;
        (bool ok, bytes memory sigPoint) = _decompress(sig);
        if (!ok) return false;
        bytes memory h;
        (ok, h) = _hashToG1(round);
        if (!ok) return false;
        bytes memory out;
        (ok, out) = _precompile(PAIRING, GAS_PAIRING, abi.encodePacked(sigPoint, NEG_G2, h, PK), 32);
        return ok && abi.decode(out, (uint256)) == 1;
    }

    /// Canonical compressed G1 point → EIP-2537 encoding (x, y as 64-byte words). Subgroup membership is left to
    /// the pairing precompile, which checks it.
    function _decompress(bytes calldata sig) private view returns (bool, bytes memory) {
        if (sig.length != 48) return (false, "");
        uint256 flags = uint8(sig[0]) & 0xe0;
        if (flags != 0x80 && flags != 0xa0) return (false, ""); // compressed and not infinity
        uint256 xHi;
        uint256 xLo;
        assembly ("memory-safe") {
            xHi := and(shr(128, calldataload(sig.offset)), 0x1fffffffffffffffffffffffffffffff)
            xLo := calldataload(add(sig.offset, 16))
        }
        if (!_lt(xHi, xLo, P_HI, P_LO)) return (false, ""); // x < p as encoded, never reduced
        // rhs = x^3 + 4 mod p
        (bool ok, uint256 rHi, uint256 rLo) = _modexp(abi.encodePacked(uint128(xHi), xLo), hex"03");
        if (!ok) return (false, "");
        unchecked {
            rLo += 4;
            if (rLo < 4) ++rHi;
        }
        if (!_lt(rHi, rLo, P_HI, P_LO)) (rHi, rLo) = _sub(rHi, rLo, P_HI, P_LO);
        uint256 yHi;
        uint256 yLo;
        (ok, yHi, yLo) = _modexp(abi.encodePacked(uint128(rHi), rLo), SQRT_EXP);
        if (!ok) return (false, "");
        (bool ok2, uint256 sHi, uint256 sLo) = _modexp(abi.encodePacked(uint128(yHi), yLo), hex"02");
        if (!ok2 || sHi != rHi || sLo != rLo) return (false, ""); // x is not on the curve
        bool sortFlag = flags == 0xa0;
        if (yHi == 0 && yLo == 0) {
            if (sortFlag) return (false, "");
        } else if (_lt(HALF_HI, HALF_LO, yHi, yLo) != sortFlag) {
            (yHi, yLo) = _sub(P_HI, P_LO, yHi, yLo);
        }
        return (true, abi.encode(xHi, xLo, yHi, yLo));
    }

    /// RFC 9380 hash_to_curve for G1 with message SHA-256(u64be(round)).
    function _hashToG1(uint64 round) private view returns (bool, bytes memory) {
        bytes32 m = sha256(abi.encodePacked(round));
        bytes32 b0 = sha256(abi.encodePacked(bytes32(0), bytes32(0), m, hex"008000", DST_PRIME));
        bytes32 b1 = sha256(abi.encodePacked(b0, hex"01", DST_PRIME));
        bytes32 b2 = sha256(abi.encodePacked(b0 ^ b1, hex"02", DST_PRIME));
        bytes32 b3 = sha256(abi.encodePacked(b0 ^ b2, hex"03", DST_PRIME));
        bytes32 b4 = sha256(abi.encodePacked(b0 ^ b3, hex"04", DST_PRIME));
        (bool ok0, bytes memory q0) = _mapToG1(abi.encodePacked(b1, b2));
        (bool ok1, bytes memory q1) = _mapToG1(abi.encodePacked(b3, b4));
        if (!ok0 || !ok1) return (false, "");
        return _precompile(G1ADD, GAS_G1ADD, abi.encodePacked(q0, q1), 128);
    }

    /// 64 uniform bytes → reduce mod p → MAP_FP_TO_G1.
    function _mapToG1(bytes memory uniform) private view returns (bool, bytes memory) {
        (bool ok, uint256 uHi, uint256 uLo) = _modexp(uniform, hex"01");
        if (!ok) return (false, "");
        return _precompile(MAP_FP_TO_G1, GAS_MAP, abi.encode(uHi, uLo), 128);
    }

    /// base^exponent mod p, returned as (high 16 bytes, low 32 bytes).
    function _modexp(bytes memory base, bytes memory exponent) private view returns (bool ok, uint256 hi, uint256 lo) {
        bytes memory out;
        (ok, out) = _precompile(
            MODEXP, GAS_MODEXP, abi.encodePacked(base.length, exponent.length, uint256(48), base, exponent, P48), 48
        );
        if (!ok) return (false, 0, 0);
        assembly ("memory-safe") {
            hi := shr(128, mload(add(out, 0x20)))
            lo := mload(add(out, 0x30))
        }
    }

    /// Static call that succeeds only if the precompile returned exactly `outLen` bytes: an address without a
    /// precompile returns success with no data, which must not pass. The call always gets its full cap (63/64 rule
    /// included), so a failure means a bad input, never starvation.
    function _precompile(address target, uint256 gasCap, bytes memory input, uint256 outLen)
        private
        view
        returns (bool ok, bytes memory out)
    {
        if (gasleft() < gasCap + gasCap / 63 + 2_000) revert GasTooLow();
        out = new bytes(outLen);
        assembly ("memory-safe") {
            ok := staticcall(gasCap, target, add(input, 0x20), mload(input), add(out, 0x20), outLen)
            if iszero(eq(returndatasize(), outLen)) { ok := 0 }
        }
    }

    function _lt(uint256 aHi, uint256 aLo, uint256 bHi, uint256 bLo) private pure returns (bool) {
        return aHi < bHi || (aHi == bHi && aLo < bLo);
    }

    /// a - b for a >= b (two-word numbers below 2^384).
    function _sub(uint256 aHi, uint256 aLo, uint256 bHi, uint256 bLo) private pure returns (uint256 hi, uint256 lo) {
        unchecked {
            lo = aLo - bLo;
            hi = aHi - bHi - (aLo < bLo ? 1 : 0);
        }
    }
}
