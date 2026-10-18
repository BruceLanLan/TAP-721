// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../interfaces/ITapNetlistNFT.sol";

/// @title On-chain storage of tapnet/1 files (TAP draft "Netlist-Bound NFTs" §8)
/// @notice Implements `storeNetlist` and `netlistFile` with SSTORE2-style code storage: each data
///         contract's runtime code is 0x00 (STOP) ‖ data, so it cannot be called. Files larger than
///         24,575 bytes are split into chunks; the pointer of a chunked file is an index contract whose
///         data is the concatenated 20-byte chunk addresses. Derived contracts register the hashes that
///         may be stored with `_addKnownNetlistHash` (on bind, or on arrival of a bridge message).
abstract contract TapNetlistStore is ITapNetlistNFT {
    /// Maximum data bytes per code contract (EIP-170 limit 24,576 minus the STOP byte).
    uint256 internal constant CHUNK_SIZE = 24575;
    /// Largest file `storeNetlist` accepts (48 KiB), so that storing with the content check fits a
    /// 16,777,216-gas transaction (BNB Smart Chain, EIP-7825).
    uint256 public constant MAX_FILE = 49152;

    struct StoredNetlist {
        address pointer; // data contract (chunks == 1) or index contract (chunks > 1)
        uint32 size;
        uint16 chunks;
    }

    error UnknownNetlist(bytes32 netlistHash);
    error NetlistNotStored(bytes32 netlistHash);
    error NetlistTooLarge(uint256 size);
    error StoreFailed();

    mapping(bytes32 netlistHash => bool) private _known;
    mapping(bytes32 netlistHash => StoredNetlist) private _stored;

    /// @inheritdoc ITapNetlistNFT
    /// @dev Idempotent: storing an already stored file returns its hash without a new event.
    function storeNetlist(bytes calldata file) external virtual returns (bytes32 netlistHash) {
        netlistHash = sha256(file);
        if (_stored[netlistHash].pointer != address(0)) return netlistHash;
        uint256 size = file.length;
        if (size > MAX_FILE) revert NetlistTooLarge(size);
        if (!knownNetlist(netlistHash)) revert UnknownNetlist(netlistHash);
        _beforeStoreNetlist(file);

        uint256 chunks = size == 0 ? 1 : (size + CHUNK_SIZE - 1) / CHUNK_SIZE;
        uint256 offset;
        assembly ("memory-safe") {
            offset := file.offset
        }
        address pointer;
        if (chunks == 1) {
            pointer = _deployFromCalldata(offset, size);
        } else {
            bytes memory index = new bytes(20 * chunks);
            for (uint256 i; i < chunks; ++i) {
                uint256 start = i * CHUNK_SIZE;
                uint256 len = size - start < CHUNK_SIZE ? size - start : CHUNK_SIZE;
                address chunk = _deployFromCalldata(offset + start, len);
                assembly ("memory-safe") {
                    mstore(add(add(index, 0x20), mul(i, 20)), shl(96, chunk))
                }
            }
            pointer = _deployFromMemory(index);
        }
        _stored[netlistHash] = StoredNetlist(pointer, uint32(size), uint16(chunks));
        emit NetlistStored(netlistHash, pointer);
    }

    /// @inheritdoc ITapNetlistNFT
    function netlistFile(bytes32 netlistHash) public view virtual returns (bytes memory file) {
        StoredNetlist memory s = _stored[netlistHash];
        if (s.pointer == address(0)) revert NetlistNotStored(netlistHash);
        file = new bytes(s.size);
        address pointer = s.pointer;
        if (s.chunks == 1) {
            assembly ("memory-safe") {
                extcodecopy(pointer, add(file, 0x20), 1, mload(file))
            }
        } else {
            uint256 chunks = s.chunks;
            bytes memory index = new bytes(20 * chunks);
            assembly ("memory-safe") {
                extcodecopy(pointer, add(index, 0x20), 1, mload(index))
                let dst := add(file, 0x20)
                for { let i := 0 } lt(i, chunks) { i := add(i, 1) } {
                    let chunk := shr(96, mload(add(add(index, 0x20), mul(i, 20))))
                    let len := sub(extcodesize(chunk), 1)
                    extcodecopy(chunk, dst, 1, len)
                    dst := add(dst, len)
                }
            }
        }
    }

    /// @notice True if a file with this hash may be stored (some entry this contract knows carries it).
    function knownNetlist(bytes32 netlistHash) public view virtual returns (bool) {
        return _known[netlistHash];
    }

    /// @notice Where a stored file lives: data contract (chunks = 1) or chunk index contract (chunks > 1).
    function netlistPointer(bytes32 netlistHash) external view returns (address pointer, uint256 size, uint256 chunks) {
        StoredNetlist memory s = _stored[netlistHash];
        return (s.pointer, s.size, s.chunks);
    }

    function _addKnownNetlistHash(bytes32 netlistHash) internal virtual {
        _known[netlistHash] = true;
    }

    /// @dev Content check before storing. Default: none (the hash is committed by the manifest).
    ///      TapNetlistCore, which implements ITapNetlistEval, fixes it to `TapNetlistCheck.check`.
    function _beforeStoreNetlist(bytes calldata file) internal view virtual {}

    /// @dev 10-byte init code `61 <size:2> 80 60 0a 3d 39 3d f3` (PUSH2 size, DUP1, PUSH1 10,
    ///      RETURNDATASIZE, CODECOPY, RETURNDATASIZE, RETURN) followed by the runtime 0x00 ‖ data.
    function _deployFromCalldata(uint256 offset, uint256 len) internal returns (address pointer) {
        assembly ("memory-safe") {
            let p := mload(0x40)
            mstore(p, shl(168, or(or(shl(80, 0x61), shl(64, add(len, 1))), 0x80600a3d393df300)))
            calldatacopy(add(p, 11), offset, len)
            pointer := create(0, p, add(len, 11))
        }
        if (pointer == address(0)) revert StoreFailed();
    }

    function _deployFromMemory(bytes memory data) internal returns (address pointer) {
        assembly ("memory-safe") {
            let len := mload(data)
            let p := mload(0x40)
            mstore(p, shl(168, or(or(shl(80, 0x61), shl(64, add(len, 1))), 0x80600a3d393df300)))
            pop(staticcall(gas(), 0x04, add(data, 0x20), len, add(p, 11), len))
            pointer := create(0, p, add(len, 11))
        }
        if (pointer == address(0)) revert StoreFailed();
    }
}
