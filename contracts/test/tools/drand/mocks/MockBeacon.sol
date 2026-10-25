// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// Test stand-in for DrandBeacon that needs no EIP-2537 precompiles. A signature is "valid" for a round only if the
/// test registered it (`register`, or `post` for a synthetic one), so the controller logic can be tested on any EVM
/// version. `mode` makes it fail the way a broken verifier would. The time functions and the cache semantics are those
/// of DrandBeacon. Tests install its runtime at the canonical beacon address with `vm.etch`, after the controller's
/// constructor has seen the real beacon code there.
contract MockBeacon {
    enum Mode {
        Normal, // accepts exactly the registered (round, signature) pairs
        Broken, // check says false for everything (a chain without the precompiles)
        Reverting, // check reverts
        ShortReturn, // check answers with 32 bytes only
        WrongRandomness, // check says ok but returns a randomness that is not SHA-256(signature)
        Lax // also accepts the registered signature with the sort flag flipped (two randomness values per round)
    }

    bytes32 public constant CHAIN_HASH = 0x52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971;
    uint256 public constant GENESIS = 1692803367;
    uint256 public constant PERIOD = 3;

    Mode public mode;
    mapping(uint64 round => bytes32) public randomnessOf;
    uint64 public latestVerifiedRound;
    mapping(bytes32 => bool) public registered;

    event RoundVerified(uint64 indexed round, bytes32 randomness);

    error InvalidSignature(uint64 round);

    function setMode(Mode m) external {
        mode = m;
    }

    /// A synthetic 48-byte signature with the compressed-G1 flag 0x80; flipping its sort flag gives 0xa0.
    function sigFor(uint64 round) public pure returns (bytes memory) {
        bytes31 a = bytes31(keccak256(abi.encode(round)));
        bytes16 b = bytes16(keccak256(abi.encode(round, uint8(1))));
        return bytes.concat(hex"80", a, b);
    }

    function register(uint64 round, bytes calldata sig) external {
        registered[keccak256(abi.encode(round, sig))] = true;
    }

    /// Register and verify the synthetic signature of `round`: "somebody posted this round to the beacon".
    function post(uint64 round) external {
        bytes memory s = sigFor(round);
        registered[keccak256(abi.encode(round, s))] = true;
        this.verify(round, s);
    }

    function verify(uint64 round, bytes calldata sig) external returns (bytes32 randomness) {
        randomness = randomnessOf[round];
        if (randomness != 0) {
            if (sha256(sig) != randomness) revert InvalidSignature(round);
            return randomness;
        }
        if (!_ok(round, sig)) revert InvalidSignature(round);
        randomness = sha256(sig);
        randomnessOf[round] = randomness;
        if (round > latestVerifiedRound) latestVerifiedRound = round;
        emit RoundVerified(round, randomness);
    }

    function check(uint64 round, bytes calldata sig) external view returns (bool ok, bytes32 randomness) {
        if (mode == Mode.Reverting) revert("beacon broken");
        if (mode == Mode.ShortReturn) {
            assembly ("memory-safe") {
                mstore(0, 1)
                return(0, 32)
            }
        }
        ok = _ok(round, sig);
        if (ok) randomness = mode == Mode.WrongRandomness ? bytes32(uint256(sha256(sig)) ^ 1) : sha256(sig);
    }

    function quicknetTime(uint64 round) public pure returns (uint256) {
        if (round == 0) return GENESIS;
        return GENESIS + PERIOD * (uint256(round) - 1);
    }

    function roundAt(uint256 timestamp) public pure returns (uint64) {
        if (timestamp < GENESIS) return 0;
        return uint64((timestamp - GENESIS) / PERIOD + 1);
    }

    function _ok(uint64 round, bytes calldata sig) private view returns (bool) {
        if (mode == Mode.Broken) return false;
        if (registered[keccak256(abi.encode(round, sig))]) return true;
        if (mode == Mode.Lax && sig.length == 48) {
            bytes memory flipped = sig;
            flipped[0] ^= 0x20;
            return registered[keccak256(abi.encode(round, flipped))];
        }
        return false;
    }
}
