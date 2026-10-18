// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Netlist-Bound NFT, optional L1 evaluation extension (TAP draft "Netlist-Bound NFTs")
/// @notice Runs a stored tapnet/1 file with the semantics of TAP-02 §4 (one beat: LATCH outputs read the
///         previous state, the new state is the latch inputs after the pass) and TAP-02 §5 (LSB-first bit
///         packing; `inputs` and `state` are read leniently — missing bytes read as 0, extra bytes and bits
///         are ignored; `outputs` and `newState` are exactly ceil(n/8) bytes with unused high bits zero).
///         Reverts if the file is not stored. Implementations MUST report this interface via ERC-165.
interface ITapNetlistEval {
    /// @notice Evaluate the netlist bound to `tokenId`. Reverts "has latch: use step" if it has LATCHes.
    function evalOf(uint256 tokenId, bytes calldata inputs) external view returns (bytes memory outputs);

    /// @notice One beat of the netlist bound to `tokenId`.
    function stepOf(uint256 tokenId, bytes calldata state, bytes calldata inputs)
        external
        view
        returns (bytes memory newState, bytes memory outputs);

    /// @notice As `evalOf`, for a stored file identified by its netlist hash.
    function evalFile(bytes32 netlistHash, bytes calldata inputs) external view returns (bytes memory outputs);

    /// @notice As `stepOf`, for a stored file identified by its netlist hash.
    function stepFile(bytes32 netlistHash, bytes calldata state, bytes calldata inputs)
        external
        view
        returns (bytes memory newState, bytes memory outputs);
}
