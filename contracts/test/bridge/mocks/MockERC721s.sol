// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ERC721Min} from "../../../src/vendor/ERC721Min.sol";
import {ITapNetlistNFT} from "../../../src/interfaces/ITapNetlistNFT.sol";

/// @notice Shaped like TapeCode-Test1 (X Layer 0x0e91…1614): tokenURI = baseURI ‖ decimal id, empty while
///         baseURI is empty; setBaseURI / freezeBaseURI by the owner; no ERC-4906, no per-token setter.
contract MockLegacy721 is ERC721Min {
    address public owner;
    string public baseURI;
    bool public uriFrozen;
    uint256 public constant MAX_SUPPLY = 10000;
    uint256 public totalSupply;

    constructor() ERC721Min("TapeCode-Test1", "TCT1") {
        owner = msg.sender;
    }

    function mint(address to, uint256 id) external {
        require(msg.sender == owner && id >= 1 && id <= MAX_SUPPLY, "mint");
        totalSupply++;
        _mint(to, id);
    }

    function setBaseURI(string calldata u) external {
        require(msg.sender == owner && !uriFrozen, "uri");
        baseURI = u;
    }

    function freezeBaseURI() external {
        require(msg.sender == owner, "owner");
        uriFrozen = true;
    }

    /// @dev TapeCode-Test1 has no ERC-4906.
    function supportsInterface(bytes4 id) public pure override returns (bool) {
        return id == 0x01ffc9a7 || id == 0x80ac58cd || id == 0x5b5e139f;
    }

    function tokenURI(uint256 id) public view override returns (string memory) {
        ownerOf(id);
        if (bytes(baseURI).length == 0) return "";
        return string.concat(baseURI, _dec(id));
    }

    function _dec(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 t = v; t != 0; t /= 10) ++len;
        bytes memory s = new bytes(len);
        while (v != 0) {
            s[--len] = bytes1(uint8(48 + v % 10));
            v /= 10;
        }
        return string(s);
    }
}

/// @notice A collection whose transferFrom silently does nothing (for the gateway's EscrowFailed check).
contract NoOpTransfer721 {
    mapping(uint256 => address) public ownerOf;
    mapping(uint256 => address) public getApproved;
    mapping(address => mapping(address => bool)) public isApprovedForAll;

    function mint(address to, uint256 id) external {
        ownerOf[id] = to;
    }

    function transferFrom(address, address, uint256) external {}
}

/// @notice A TapeOut processor contract stand-in (circuit NFTs), for the hub mock.
contract MockCircuits is ERC721Min {
    constructor() ERC721Min("Processor", "CPU") {}

    function mint(address to, uint256 id) external {
        _mint(to, id);
    }

    function tokenURI(uint256) public pure override returns (string memory) {
        return "";
    }
}

/// @notice Stand-in for the draft-A companion of a legacy collection: only the hash getters matter here.
contract MockDataSource is ITapNetlistNFT {
    address public immutable override collection;
    bytes32 public override manifestHash;
    mapping(uint256 => bytes32) public override netlistHashOf;
    mapping(uint256 => bytes32) public override imageHashOf;

    constructor(address collection_) {
        collection = collection_;
    }

    function set(uint256 id, bytes32 netlist, bytes32 image) external {
        netlistHashOf[id] = netlist;
        imageHashOf[id] = image;
    }

    function setManifest(bytes32 m) external {
        manifestHash = m;
    }

    function tokenRange() external pure returns (uint256, uint256) {
        return (1, 10000);
    }

    uint8 public poolFields = 3; // one pool holding image and netlist by default

    function setPoolFields(uint8 f) external {
        poolFields = f;
    }

    function pools() external view returns (Pool[] memory p) {
        if (poolFields == 0) return p;
        p = new Pool[](1);
        p[0] = Pool("POOL", poolFields, bytes32(uint256(1)));
    }

    bytes32 public masterSeed;

    function setSeed(bytes32 s_) external {
        masterSeed = s_;
    }

    function entryIndexOf(uint256, uint256) external pure returns (uint256) {
        revert();
    }

    function bind(uint256, uint256, bytes32[] calldata, bytes32[] calldata) external pure {
        revert();
    }

    function storeNetlist(bytes calldata) external pure returns (bytes32) {
        revert();
    }

    function netlistFile(bytes32) external pure returns (bytes memory) {
        revert();
    }

    function netlistOf(uint256) external pure returns (bytes memory) {
        revert();
    }

    function frozen() external pure returns (bool) {
        return false;
    }
}
