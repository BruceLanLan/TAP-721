// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TapDrandReveal} from "./TapDrandReveal.sol";

/// @title Factory of drand reveal controllers
/// @notice Deployed once per chain through the deterministic deployer 0x4e59b44847b379578588920cA78FbF26c0B4956C with
///         salt 0, so its address pins its initcode (and the TapDrandReveal code inside it), and every controller it
///         records ran the real constructor. No constructor, no owner, no other state.
///
///         WHAT THE FACTORY DOES NOT PROVE. It accepts ANY collection initcode: the controller only checks that the new
///         contract reports itself as its owner. `controllerOf` and `Created` therefore say "this factory built this
///         controller with this (unchecked) initcode", NOT "this collection is the reference TAP-721 and has no hidden
///         minter". A collection built from crafted initcode (a planted minter, byte-identical reference runtime) is
///         recorded here exactly like an honest one. Kit proof needs an OFF-chain check of the initcode hash that
///         `Created` and the controller's `collectionInitCodeHash()` carry, against a reference build (an off-chain
///         checker does it). An indexer or marketplace that trusts `controllerOf` or `Created` alone, or compares
///         only the collection's runtime code hash, can be misled.
contract TapDrandRevealFactory {
    /// A controller was built. `collectionInitCodeHash` is keccak256 of the initcode the caller GAVE (the factory does
    /// not compare it with anything): it is the input of the off-chain proof, not the proof. The controller's
    /// immutable deferred-mode delay is `controller.scheduleDelay()`.
    event Created(
        address indexed controller,
        address indexed collection,
        address indexed admin,
        bytes32 collectionInitCodeHash
    );

    /// The controller that created `collection` (and owns it until the freeze); zero for a collection made elsewhere.
    /// A record of provenance only: it does not say that the collection runs reference code (see above).
    mapping(address collection => address controller) public controllerOf;

    /// @notice new TapDrandReveal(admin, scheduleDelay, collectionInitCode, name, symbol, baseURI); the controller
    ///         creates the collection with itself as owner. Anyone may call. scheduleDelay must lie in
    ///         [MIN_SCHEDULE_DELAY, MAX_SCHEDULE_DELAY] (1 hour to 7 days); fixed mode never reads it, so pass the
    ///         minimum there. The collectionInitCode is NOT verified (see above).
    function create(
        address admin,
        uint256 scheduleDelay,
        bytes calldata collectionInitCode,
        string calldata name,
        string calldata symbol,
        string calldata baseURI
    ) external returns (address controller, address collection) {
        controller = address(new TapDrandReveal(admin, scheduleDelay, collectionInitCode, name, symbol, baseURI));
        collection = address(TapDrandReveal(controller).collection());
        controllerOf[collection] = controller;
        emit Created(controller, collection, admin, TapDrandReveal(controller).collectionInitCodeHash());
    }
}
