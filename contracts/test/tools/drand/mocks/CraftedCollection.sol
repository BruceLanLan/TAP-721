// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// A collection whose constructor takes the arguments the controller appends (name, symbol, baseURI, owner) and that
/// reports the controller as its owner, so it passes every on-chain check of TapDrandReveal and the factory, while
/// it has a hidden minter. It shows why the kit's claims need the off-chain comparison of `collectionInitCodeHash`
/// with a reference build (docs/DRAND_REVEAL.md, "Construction is proven off chain").
contract CraftedCollection {
    address public owner;
    address public immutable plantedMinter;

    constructor(string memory, string memory, string memory, address owner_) {
        owner = owner_;
        plantedMinter = tx.origin;
    }

    function mint(address, uint256) external view {
        require(msg.sender == owner || msg.sender == plantedMinter, "no");
    }
}
