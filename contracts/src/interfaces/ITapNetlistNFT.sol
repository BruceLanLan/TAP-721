// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

/// @title Netlist-Bound NFT, L1 interface (TAP draft "Netlist-Bound NFTs" §8)
/// @notice Implemented by the ERC-721 collection itself, or by a companion contract bound to an
///         existing ERC-721 (then `collection()` returns that contract; otherwise it returns address(this)).
///         Implementations MUST also support ERC-165 and ERC-4906; the collection MUST support ERC-721.
interface ITapNetlistNFT {
    /// Pool description. `fields` is a bit mask: 1 = image hash, 2 = netlist hash.
    struct Pool {
        string label;
        uint8 fields;
        bytes32 root;
    }

    /// @notice The ERC-721 contract whose tokens this interface describes.
    function collection() external view returns (address);

    /// @notice First token id and number of tokens covered by the manifest.
    function tokenRange() external view returns (uint256 firstTokenId, uint256 supply);

    /// @notice SHA-256 of the manifest file. Zero until committed; never changes once non-zero.
    function manifestHash() external view returns (bytes32);

    /// @notice The pools committed with the manifest, in manifest order.
    function pools() external view returns (Pool[] memory);

    /// @notice The reveal seed. Zero until revealed; never changes once non-zero.
    function masterSeed() external view returns (bytes32);

    /// @notice Index of the pool entry that `tokenId` receives from pool `poolIndex`.
    ///         Reverts before the reveal and for tokens not covered by the manifest (outside the range in
    ///         range mode; not in the token set in set mode, see ITapNetlistTokenSet).
    function entryIndexOf(uint256 tokenId, uint256 poolIndex) external view returns (uint256);

    /// @notice Record the entry a token received, proven against the pool root. Permissionless and
    ///         idempotent; reverts if the proof or the index is wrong. `values` holds the entry's
    ///         32-byte field values in field order (image, then netlist).
    function bind(uint256 tokenId, uint256 poolIndex, bytes32[] calldata values, bytes32[] calldata proof) external;

    /// @notice Netlist hash bound to `tokenId`; zero while no hash is known for the token.
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);

    /// @notice Image hash bound to `tokenId`; zero while no hash is known for the token.
    function imageHashOf(uint256 tokenId) external view returns (bytes32);

    /// @notice Store a tapnet/1 file on chain. Permissionless. MUST revert unless SHA-256(file) equals the
    ///         netlist hash this contract knows: bound to a token, marked from a pool loaded on chain, or carried
    ///         in by a bridge message.
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);

    /// @notice The stored tapnet/1 file with this hash; reverts if not stored.
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);

    /// @notice The tapnet/1 file bound to `tokenId`; reverts if not bound or not stored.
    function netlistOf(uint256 tokenId) external view returns (bytes memory);

    /// @notice True once the manifest is committed, the seed is set, and no account can change
    ///         `tokenURI`, the manifest, the pools or the seed any more. Never returns to false.
    function frozen() external view returns (bool);

    event ManifestCommitted(bytes32 indexed manifestHash);
    event Revealed(bytes32 masterSeed);
    event Bound(uint256 indexed tokenId, uint256 indexed poolIndex, uint256 entryIndex);
    event NetlistStored(bytes32 indexed netlistHash, address pointer);
    event Frozen();
}
