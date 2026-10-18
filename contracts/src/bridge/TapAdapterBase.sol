// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapBridgeAdapter, ITapBridgeEndpoint} from "../interfaces/ITapBridge.sol";
import {ITapBridgeAdapterSealed} from "../interfaces/ITapBridgeAdapterSealed.sol";

/// @title Common part of the adapters
/// @notice An adapter serves exactly one endpoint (immutable) and transports the bare 320-byte payload.
///         Because the remote adapter, too, serves exactly one endpoint, an authenticated remote adapter
///         identifies the sending endpoint: `remoteEndpoint[chainId]`, set once together with the peer.
///         The adapter passes it to `receivePayload`, and the endpoint checks it against its route's peer.
abstract contract TapAdapterBase is ITapBridgeAdapter, ITapBridgeAdapterSealed {
    address public immutable endpoint;
    uint64 public immutable localChainId;
    /// @notice Configures remote peers once per chain; see each adapter for any further power.
    address public owner;

    error NotEndpoint();
    error NotOwner();
    error WrongPeer();
    error AlreadySet();
    error ZeroOwner();

    /// @notice The endpoint served by the peer adapter on each remote chain; set once.
    mapping(uint64 => address) public remoteEndpoint;

    event OwnerChanged(address indexed previousOwner, address indexed newOwner);

    modifier onlyEndpoint() {
        if (msg.sender != endpoint) revert NotEndpoint();
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address endpoint_, address owner_) {
        if (owner_ == address(0)) revert ZeroOwner();
        endpoint = endpoint_;
        localChainId = uint64(block.chainid);
        owner = owner_;
    }

    /// @inheritdoc ITapBridgeAdapterSealed
    bool public adapterSealed;

    /// @notice Irreversible: clears the owner (no further peer, remote-endpoint or other configuration) and runs
    ///         the adapter-specific freeze (`_onSeal`, e.g. removing the LayerZero delegate).
    function seal() external onlyOwner {
        _onSeal();
        adapterSealed = true;
        emit OwnerChanged(owner, address(0));
        owner = address(0);
        emit AdapterSealed();
    }

    function _onSeal() internal virtual {}

    /// @notice Hand over the owner role. Renouncing is only possible through `seal()`, so that an adapter without
    ///         an owner always reports sealed.
    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroOwner();
        emit OwnerChanged(owner, newOwner);
        owner = newOwner;
    }

    function _setRemoteEndpoint(uint64 chainId, address remote) internal {
        if (remoteEndpoint[chainId] != address(0)) revert AlreadySet();
        if (remote == address(0)) revert WrongPeer();
        remoteEndpoint[chainId] = remote;
    }

    function _deliver(uint64 srcChainId, bytes calldata payload) internal {
        address src = remoteEndpoint[srcChainId];
        if (src == address(0)) revert WrongPeer();
        ITapBridgeEndpoint(endpoint).receivePayload(srcChainId, src, payload);
    }
}
