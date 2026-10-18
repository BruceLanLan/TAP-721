// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapBridgeAdapter, ITapBridgeEndpoint} from "../interfaces/ITapBridge.sol";
import {ITapBridgeTransfer} from "../interfaces/ITapBridgeTransfer.sol";
import {ITapBridgeAdapterSealed} from "../interfaces/ITapBridgeAdapterSealed.sol";
import {TapBridgePayload} from "./TapBridgePayload.sol";

/// @title Common part of TapGateway and TapMirror: routes, policies, replay protection, dispatch
/// @dev The local chain id is `block.chainid` captured at construction.
abstract contract TapBridgeEndpoint is ITapBridgeEndpoint, ITapBridgeTransfer {
    uint256 internal constant MAX_ADAPTERS = 8;

    struct Route {
        Policy policy;
        address[] adapters;
        address peer;
    }

    uint64 public immutable override homeChainId;
    uint64 public immutable localChainId;
    address public immutable homeContract;
    bytes32 public immutable override collectionKey;

    /// @notice May set routes until `sealRoutes()`, which also clears it. No other power.
    address public owner;
    bool public override routesSealed;
    uint64 public override nextNonce;

    mapping(uint64 => Route) internal _routes;
    uint64[] internal _chains; // every chain id ever passed to setRoute, for sealRoutes
    mapping(bytes32 => bool) public override departed;
    mapping(bytes32 => bool) public override executed;
    mapping(bytes32 => mapping(address => bool)) public override confirmedBy;

    uint256 private _entered;
    mapping(uint64 => bool) private _known;

    error NotOwner();
    error Sealed();
    error BadRoute();
    error RouteClosed(uint64 chainId);
    error NotAdapter(address caller);
    error WrongSource();
    error WrongPeer(address srcEndpoint);
    error WrongDestination();
    error WrongCollection();
    error Replay(bytes32 messageId);
    error AlreadyConfirmed(bytes32 messageId, address adapter);
    error NotDeparted(bytes32 messageId);
    error ZeroRecipient();
    error EndpointRecipient(address to);
    error AdapterNotSealed(address adapter);
    error ContractRecipient(address to);
    error BadOptions();
    error InsufficientFee(uint256 required, uint256 provided);
    error RefundFailed();
    error Reentrancy();

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier nonReentrant() {
        if (_entered == 1) revert Reentrancy();
        _entered = 1;
        _;
        _entered = 0;
    }

    constructor(uint64 homeChainId_, address homeContract_, address owner_) {
        homeChainId = homeChainId_;
        homeContract = homeContract_;
        localChainId = uint64(block.chainid);
        collectionKey = TapBridgePayload.collectionKey(homeChainId_, homeContract_);
        owner = owner_;
    }

    // ------------------------------------------------------------------ routes

    function route(uint64 chainId) external view override returns (Policy, address[] memory, address) {
        Route storage r = _routes[chainId];
        return (r.policy, r.adapters, r.peer);
    }

    function setRoute(uint64 chainId, uint8 policy, address[] calldata adapters, address peer)
        external
        override
        onlyOwner
    {
        if (routesSealed) revert Sealed();
        if (chainId == 0 || chainId == localChainId || policy > uint8(Policy.ALL)) revert BadRoute();
        // Hub-and-spoke: a mirror routes only to the home chain, so the gateway knows where each token is.
        if (localChainId != homeChainId && chainId != homeChainId) revert BadRoute();
        Policy p = Policy(policy);
        if (p == Policy.NONE) {
            if (adapters.length != 0) revert BadRoute();
        } else {
            if (peer == address(0)) revert BadRoute();
            if (p == Policy.ONE && adapters.length != 1) revert BadRoute();
            if (p == Policy.ALL && (adapters.length < 2 || adapters.length > MAX_ADAPTERS)) revert BadRoute();
            for (uint256 i; i < adapters.length; ++i) {
                if (adapters[i] == address(0)) revert BadRoute();
                for (uint256 j; j < i; ++j) {
                    if (adapters[i] == adapters[j]) revert BadRoute();
                }
            }
        }
        if (!_known[chainId]) {
            _known[chainId] = true;
            _chains.push(chainId);
        }
        _routes[chainId] = Route(p, adapters, peer);
        emit RouteSet(chainId, policy, adapters, peer);
    }

    /// @dev Requires at least one open route and every adapter listed on any route to be sealed
    ///      (ITapBridgeAdapterSealed), so that sealing the endpoint also freezes how messages are authenticated.
    function sealRoutes() external override onlyOwner {
        bool open;
        for (uint256 c; c < _chains.length; ++c) {
            Route storage r = _routes[_chains[c]];
            if (r.policy != Policy.NONE) open = true;
            for (uint256 a; a < r.adapters.length; ++a) {
                if (!_adapterSealed(r.adapters[a])) revert AdapterNotSealed(r.adapters[a]);
            }
        }
        if (!open) revert BadRoute();
        routesSealed = true;
        owner = address(0);
        emit RoutesSealed();
    }

    // ------------------------------------------------------------------ outgoing

    function quoteBridge(uint256 tokenId, uint64 dstChainId, address to, bytes[] calldata options)
        external
        view
        override
        returns (uint256 total, uint256[] memory fees)
    {
        Route storage r = _openRoute(dstChainId);
        (bytes32 n, bytes32 i, bytes32 m) = _hashesOf(tokenId);
        bytes memory payload = _payload(tokenId, dstChainId, to, n, i, m, nextNonce);
        uint256 k = r.adapters.length;
        if (options.length != 0 && options.length != k) revert BadOptions();
        fees = new uint256[](k);
        for (uint256 a; a < k; ++a) {
            fees[a] = ITapBridgeAdapter(r.adapters[a]).quote(dstChainId, payload, _opt(options, a));
            total += fees[a];
        }
    }

    function bridge(uint256 tokenId, uint64 dstChainId, address to, bool contractRecipientOk, bytes[] calldata options)
        external
        payable
        override
        nonReentrant
        returns (bytes32 messageId)
    {
        if (to == address(0)) revert ZeroRecipient();
        if (!contractRecipientOk && _isContract(to)) revert ContractRecipient(to);
        Route storage r = _openRoute(dstChainId);
        if (to == r.peer || to == address(this)) revert EndpointRecipient(to);
        if (options.length != 0 && options.length != r.adapters.length) revert BadOptions();

        bytes memory payload;
        {
            (bytes32 n, bytes32 i, bytes32 m) = _depart(tokenId, msg.sender, dstChainId);
            payload = _payload(tokenId, dstChainId, to, n, i, m, nextNonce++);
        }
        messageId = TapBridgePayload.messageId(address(this), payload);
        departed[messageId] = true;
        emit Departed(messageId, tokenId, dstChainId, to);
        _refund(msg.value - _sendAll(r, dstChainId, payload, options));
    }

    function _sendAll(Route storage r, uint64 dstChainId, bytes memory payload, bytes[] calldata options)
        private
        returns (uint256 spent)
    {
        uint256 k = r.adapters.length;
        for (uint256 a; a < k; ++a) {
            ITapBridgeAdapter ad = ITapBridgeAdapter(r.adapters[a]);
            bytes calldata o = _opt(options, a);
            uint256 fee = ad.quote(dstChainId, payload, o);
            spent += fee;
            if (spent > msg.value) revert InsufficientFee(spent, msg.value);
            ad.send{value: fee}(dstChainId, payload, o, msg.sender);
        }
    }

    function resend(bytes calldata payload, uint256 adapterIndex, bytes calldata options)
        external
        payable
        override
        nonReentrant
        returns (bytes32 transportId)
    {
        bytes32 messageId = TapBridgePayload.messageId(address(this), payload);
        if (!departed[messageId]) revert NotDeparted(messageId);
        TapBridgePayload.Payload memory p = TapBridgePayload.decode(payload);
        Route storage r = _openRoute(p.dstChainId);
        if (adapterIndex >= r.adapters.length) revert BadRoute();
        ITapBridgeAdapter ad = ITapBridgeAdapter(r.adapters[adapterIndex]);
        uint256 fee = ad.quote(p.dstChainId, payload, options);
        if (fee > msg.value) revert InsufficientFee(fee, msg.value);
        transportId = ad.send{value: fee}(p.dstChainId, payload, options, msg.sender);
        _refund(msg.value - fee);
    }

    // ------------------------------------------------------------------ incoming

    function receivePayload(uint64 srcChainId, address srcEndpoint, bytes calldata payload)
        external
        override
        nonReentrant
    {
        Route storage r = _routes[srcChainId];
        if (r.policy == Policy.NONE) revert RouteClosed(srcChainId);
        uint256 k = r.adapters.length;
        bool listed;
        for (uint256 a; a < k; ++a) {
            if (r.adapters[a] == msg.sender) {
                listed = true;
                break;
            }
        }
        if (!listed) revert NotAdapter(msg.sender);
        if (srcEndpoint != r.peer) revert WrongPeer(srcEndpoint);

        TapBridgePayload.Payload memory p = TapBridgePayload.decode(payload);
        if (p.srcChainId != srcChainId) revert WrongSource();
        if (p.dstChainId != localChainId) revert WrongDestination();
        if (p.collectionKey != collectionKey) revert WrongCollection();
        if (p.to == address(this)) revert EndpointRecipient(p.to);

        bytes32 messageId = TapBridgePayload.messageId(srcEndpoint, payload);
        if (executed[messageId]) revert Replay(messageId);
        emit Confirmed(messageId, msg.sender);
        if (r.policy == Policy.ALL) {
            // Confirmations are tracked per (messageId, adapter address), so a route change before sealing
            // cannot shift them; the current route's adapter list decides when the payload takes effect.
            if (confirmedBy[messageId][msg.sender]) revert AlreadyConfirmed(messageId, msg.sender);
            confirmedBy[messageId][msg.sender] = true;
            for (uint256 a; a < k; ++a) {
                if (!confirmedBy[messageId][r.adapters[a]]) return; // wait for the other adapters
            }
        }
        executed[messageId] = true;
        _arrive(p);
        emit Arrived(messageId, p.tokenId, srcChainId, p.to);
    }

    // ------------------------------------------------------------------ hooks

    /// @dev Check that `caller` may move `tokenId`, take it out of circulation, return the hashes to carry.
    function _depart(uint256 tokenId, address caller, uint64 dstChainId)
        internal
        virtual
        returns (bytes32 netlistHash, bytes32 imageHash, bytes32 manifestHash);

    /// @dev Put the token back into circulation for `p.to`.
    function _arrive(TapBridgePayload.Payload memory p) internal virtual;

    /// @dev The hashes `_depart` would carry, for quoting.
    function _hashesOf(uint256 tokenId)
        internal
        view
        virtual
        returns (bytes32 netlistHash, bytes32 imageHash, bytes32 manifestHash);

    // ------------------------------------------------------------------ internals

    /// @dev Code other than an EIP-7702 delegation designator (0xef0100 ‖ 20 bytes) counts as a contract.
    function _isContract(address a) internal view returns (bool) {
        uint256 len = a.code.length;
        if (len == 0) return false;
        if (len == 23) {
            bytes memory c = a.code;
            if (c[0] == 0xef && c[1] == 0x01 && c[2] == 0x00) return false;
        }
        return true;
    }

    function _adapterSealed(address a) private view returns (bool) {
        try ITapBridgeAdapterSealed(a).adapterSealed() returns (bool s) {
            return s;
        } catch {
            return false;
        }
    }

    function _isBridgeInterface(bytes4 id) internal pure returns (bool) {
        return id == type(ITapBridgeEndpoint).interfaceId || id == type(ITapBridgeTransfer).interfaceId;
    }

    function _openRoute(uint64 chainId) internal view returns (Route storage r) {
        r = _routes[chainId];
        if (r.policy == Policy.NONE) revert RouteClosed(chainId);
    }

    function _payload(uint256 tokenId, uint64 dst, address to, bytes32 n, bytes32 i, bytes32 m, uint64 nonce)
        internal
        view
        returns (bytes memory)
    {
        return TapBridgePayload.encode(
            TapBridgePayload.Payload({
                collectionKey: collectionKey,
                tokenId: tokenId,
                to: to,
                netlistHash: n,
                imageHash: i,
                manifestHash: m,
                srcChainId: localChainId,
                dstChainId: dst,
                nonce: nonce
            })
        );
    }

    function _opt(bytes[] calldata options, uint256 a) private pure returns (bytes calldata o) {
        o = options.length == 0 ? msg.data[0:0] : options[a];
    }

    function _refund(uint256 amount) private {
        if (amount == 0) return;
        (bool ok,) = msg.sender.call{value: amount}("");
        if (!ok) revert RefundFailed();
    }
}
