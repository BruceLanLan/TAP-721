// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TapAdapterBase} from "./TapAdapterBase.sol";
import {
    ILayerZeroEndpointV2Min,
    ILayerZeroReceiverMin,
    MessagingParams,
    MessagingReceipt,
    Origin,
    UlnConfig,
    IReceiveUlnMin
} from "./ILayerZeroEndpointV2Min.sol";

/// @title LayerZero V2 adapter (minimal OApp written against EndpointV2)
/// @notice Peers (chainId ↔ eid ↔ remote adapter) are set once per chain and never change.
///         The delegate registered with EndpointV2 can choose message libraries and DVNs for this OApp;
///         renouncing it (setDelegate(0)) freezes that configuration.
contract LayerZeroV2Adapter is TapAdapterBase, ILayerZeroReceiverMin {
    bytes32 public constant LAYER_ID = keccak256("TAP-NFT adapter LayerZeroV2 v1");

    ILayerZeroEndpointV2Min public immutable lzEndpoint;
    /// @notice lzReceive gas used when the caller passes no options.
    uint128 public immutable defaultGas;

    mapping(uint64 => uint32) public eidOf;
    mapping(uint32 => uint64) public chainOf;
    mapping(uint32 => bytes32) public peers;
    uint32[] internal _eids; // every configured remote eid, for the seal check

    event PeerSet(uint64 indexed chainId, uint32 indexed eid, bytes32 peer, address remoteEndpoint);

    error NotLzEndpoint();
    error UnknownChain(uint64 chainId);
    error ValueNotAccepted();
    error NotPinned(uint32 eid);

    constructor(address endpoint_, address lzEndpoint_, address owner_, address delegate_, uint128 defaultGas_)
        TapAdapterBase(endpoint_, owner_)
    {
        lzEndpoint = ILayerZeroEndpointV2Min(lzEndpoint_);
        defaultGas = defaultGas_;
        ILayerZeroEndpointV2Min(lzEndpoint_).setDelegate(delegate_);
    }

    // ------------------------------------------------------------------ configuration

    /// @notice Once per chain: bind `chainId` to LayerZero `eid`, the remote adapter `peer` and the endpoint
    ///         `remoteEndpoint_` that remote adapter serves.
    function setPeer(uint64 chainId, uint32 eid, bytes32 peer, address remoteEndpoint_) external onlyOwner {
        if (eidOf[chainId] != 0 || chainOf[eid] != 0 || peers[eid] != 0) revert AlreadySet();
        if (chainId == 0 || eid == 0 || peer == 0 || chainId == localChainId) revert WrongPeer();
        eidOf[chainId] = eid;
        chainOf[eid] = chainId;
        peers[eid] = peer;
        _eids.push(eid);
        _setRemoteEndpoint(chainId, remoteEndpoint_);
        emit PeerSet(chainId, eid, peer, remoteEndpoint_);
    }

    function setDelegate(address delegate) external onlyOwner {
        lzEndpoint.setDelegate(delegate);
    }

    /// @dev Sealing requires that, for every configured remote eid, the send and receive libraries are pinned
    ///      (not the endpoint owner's defaults) and the receive ULN config sets confirmations and the DVN set
    ///      explicitly; then it removes the EndpointV2 delegate. With the owner gone, nothing can be changed again,
    ///      and the endpoint owner's later changes of defaults no longer apply to this adapter.
    function _onSeal() internal override {
        uint256 n = _eids.length;
        if (n == 0) revert NotPinned(0);
        for (uint256 i; i < n; ++i) {
            uint32 eid = _eids[i];
            if (lzEndpoint.isDefaultSendLibrary(address(this), eid)) revert NotPinned(eid);
            (address lib, bool isDefault) = lzEndpoint.getReceiveLibrary(address(this), eid);
            if (isDefault || lib == address(0)) revert NotPinned(eid);
            (, uint256 expiry) = lzEndpoint.receiveLibraryTimeout(address(this), eid);
            if (expiry > block.number) revert NotPinned(eid); // an old library is still accepted
            UlnConfig memory c = IReceiveUlnMin(lib).getAppUlnConfig(address(this), eid);
            // 0 = follow the default; type(uint64).max and 255 are ULN302's NIL values (zero confirmations,
            // no required DVNs — verification would then fall to optional, possibly default, DVNs).
            if (
                c.confirmations == 0 || c.confirmations == type(uint64).max || c.requiredDVNCount == 0
                    || c.requiredDVNCount == 255 || c.requiredDVNs.length != c.requiredDVNCount
            ) revert NotPinned(eid);
        }
        lzEndpoint.setDelegate(address(0));
    }

    // ------------------------------------------------------------------ ITapBridgeAdapter

    function layerId() external pure returns (bytes32) {
        return LAYER_ID;
    }

    function quote(uint64 dstChainId, bytes calldata payload, bytes calldata options)
        external
        view
        returns (uint256)
    {
        return lzEndpoint.quote(_params(dstChainId, payload, options), address(this)).nativeFee;
    }

    function send(uint64 dstChainId, bytes calldata payload, bytes calldata options, address refundTo)
        external
        payable
        onlyEndpoint
        returns (bytes32)
    {
        MessagingReceipt memory r = lzEndpoint.send{value: msg.value}(_params(dstChainId, payload, options), refundTo);
        return r.guid;
    }

    // ------------------------------------------------------------------ OApp receiver

    function allowInitializePath(Origin calldata origin) external view returns (bool) {
        return peers[origin.srcEid] == origin.sender && origin.sender != 0;
    }

    /// @notice 0: unordered delivery (EndpointV2 default).
    function nextNonce(uint32, bytes32) external pure returns (uint64) {
        return 0;
    }

    function lzReceive(Origin calldata origin, bytes32, bytes calldata message, address, bytes calldata)
        external
        payable
    {
        if (msg.sender != address(lzEndpoint)) revert NotLzEndpoint();
        if (msg.value != 0) revert ValueNotAccepted();
        bytes32 peer = peers[origin.srcEid];
        if (peer == 0 || peer != origin.sender) revert WrongPeer();
        _deliver(chainOf[origin.srcEid], message);
    }

    // ------------------------------------------------------------------ internals

    /// @dev Default options: TYPE_3 ‖ executor worker (1) ‖ length 17 ‖ LZ_RECEIVE (1) ‖ uint128 gas.
    function defaultOptions() public view returns (bytes memory) {
        return abi.encodePacked(uint16(3), uint8(1), uint16(17), uint8(1), defaultGas);
    }

    function _params(uint64 dstChainId, bytes calldata payload, bytes calldata options)
        internal
        view
        returns (MessagingParams memory)
    {
        uint32 eid = eidOf[dstChainId];
        if (eid == 0) revert UnknownChain(dstChainId);
        return MessagingParams({
            dstEid: eid,
            receiver: peers[eid],
            message: payload,
            options: options.length == 0 ? defaultOptions() : options,
            payInLzToken: false
        });
    }
}
