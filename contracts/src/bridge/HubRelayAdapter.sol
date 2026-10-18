// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TapAdapterBase} from "./TapAdapterBase.sol";

/// @notice The part of the TAP-10 DeWEB hub (§13.5) this adapter uses.
interface IOwnerOfMin {
    function ownerOf(uint256 tokenId) external view returns (address);
}

interface IDeWebHubMin {
    function send(address circuits, uint256 tokenId, bytes32 to, bytes32 ref, bytes calldata payload)
        external
        returns (uint256 inboxIndex);
    function outboxCount(address from) external view returns (uint256);
    function accountOf(address circuits, uint256 tokenId) external view returns (address);
}

/// @title TAP-10 hub relay adapter [Open]
/// @notice Source side: writes the payload to the local DeWEB hub as the container of a circuit this adapter holds,
///         with `ref = keccak256(payload)`, addressed to the endpoint ID of the remote adapter.
///         Destination side: accepts a relayed payload only with K-of-N EIP-712 signatures of a fixed attester set
///         over (srcChainId, hub, fromContainer, outboxIndex, digest), digest = keccak256(ref ‖ keccak256(payload))
///         as in TAP-10 §13.6. The attester set is one possible verifier; it is replaced by nothing else here.
contract HubRelayAdapter is TapAdapterBase {
    bytes32 public constant LAYER_ID = keccak256("TAP-NFT adapter TAP-10 hub relay v1");
    bytes32 public constant HUB_MESSAGE_TYPEHASH = keccak256(
        "HubMessage(uint64 srcChainId,address hub,address fromContainer,uint256 outboxIndex,bytes32 digest)"
    );
    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    uint256 private constant HALF_N = 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0;

    /// @notice The DeWEB hub; the same address on every TapeOut chain (TAP-10 §13.2).
    IDeWebHubMin public immutable hub;
    uint256 public immutable threshold;
    bytes32 private immutable _cachedDomainSeparator;
    uint256 private immutable _cachedChainId;
    address[] internal _attesters; // strictly ascending, fixed at deployment

    /// @notice The circuit whose container writes for this adapter; set once, the adapter must hold it.
    address public circuits;
    uint256 public circuitId;

    /// @notice Per remote chain, set once: the remote adapter (recipient of our messages) and the container
    ///         that writes for it there (accepted author of its messages).
    mapping(uint64 => address) public remoteAdapter;
    mapping(uint64 => address) public remoteContainer;
    mapping(bytes32 => bool) public delivered;

    event RemoteSet(uint64 indexed chainId, address adapter, address container, address remoteEndpoint);
    event CircuitSet(address circuits, uint256 circuitId, address container);
    event Relayed(uint64 indexed srcChainId, uint256 indexed outboxIndex, bytes32 digest);

    error BadAttesters();
    error BadSignatures();
    error UnknownChain(uint64 chainId);
    error AlreadyDelivered();
    error BadRef();
    error ValueNotAccepted();
    error NotCircuitHolder();

    constructor(address endpoint_, address hub_, address owner_, address[] memory attesters_, uint256 threshold_)
        TapAdapterBase(endpoint_, owner_)
    {
        if (threshold_ == 0 || threshold_ > attesters_.length) revert BadAttesters();
        for (uint256 i = 1; i < attesters_.length; ++i) {
            if (attesters_[i] <= attesters_[i - 1]) revert BadAttesters();
        }
        if (attesters_[0] == address(0)) revert BadAttesters();
        hub = IDeWebHubMin(hub_);
        _attesters = attesters_;
        threshold = threshold_;
        _cachedChainId = block.chainid;
        _cachedDomainSeparator = _buildDomainSeparator();
    }

    // ------------------------------------------------------------------ configuration (once)

    function setCircuit(address circuits_, uint256 circuitId_) external onlyOwner {
        if (circuits != address(0)) revert AlreadySet();
        if (IOwnerOfMin(circuits_).ownerOf(circuitId_) != address(this)) revert NotCircuitHolder();
        circuits = circuits_;
        circuitId = circuitId_;
        emit CircuitSet(circuits_, circuitId_, hub.accountOf(circuits_, circuitId_));
    }

    function setRemote(uint64 chainId, address adapter, address container_, address remoteEndpoint_)
        external
        onlyOwner
    {
        if (remoteAdapter[chainId] != address(0)) revert AlreadySet();
        if (chainId == 0 || chainId == localChainId || adapter == address(0) || container_ == address(0)) {
            revert WrongPeer();
        }
        remoteAdapter[chainId] = adapter;
        remoteContainer[chainId] = container_;
        _setRemoteEndpoint(chainId, remoteEndpoint_);
        emit RemoteSet(chainId, adapter, container_, remoteEndpoint_);
    }

    function attesters() external view returns (address[] memory) {
        return _attesters;
    }

    /// @notice This adapter's own container, the author of its hub messages.
    function container() public view returns (address) {
        return hub.accountOf(circuits, circuitId);
    }

    // ------------------------------------------------------------------ ITapBridgeAdapter

    function layerId() external pure returns (bytes32) {
        return LAYER_ID;
    }

    /// @notice The hub charges no fee; the relayer pays destination gas.
    function quote(uint64 dstChainId, bytes calldata, bytes calldata) external view returns (uint256) {
        if (remoteAdapter[dstChainId] == address(0)) revert UnknownChain(dstChainId);
        return 0;
    }

    /// @return transportId the TAP-10 §17 message ID of the hub entry.
    function send(uint64 dstChainId, bytes calldata payload, bytes calldata, address)
        external
        payable
        onlyEndpoint
        returns (bytes32 transportId)
    {
        if (msg.value != 0) revert ValueNotAccepted();
        address remote = remoteAdapter[dstChainId];
        if (remote == address(0)) revert UnknownChain(dstChainId);
        // recipient: the TAP-10 endpoint id of the remote adapter's container, uint32(0) ‖ uint64 ‖ address
        bytes32 to = bytes32((uint256(dstChainId) << 160) | uint160(remoteContainer[dstChainId]));
        // ref = the message id: keccak256(this adapter's endpoint ‖ payload)
        uint256 inboxIndex = hub.send(circuits, circuitId, to, keccak256(abi.encodePacked(endpoint, payload)), payload);
        transportId =
            keccak256(abi.encodePacked("TAP-10/msg/v2", block.chainid, address(hub), to, inboxIndex));
    }

    // ------------------------------------------------------------------ destination

    /// @notice Permissionless relay of hub message `outboxIndex` of the remote adapter's container on `srcChainId`.
    /// @param signatures concatenated 65-byte (r, s, v) signatures, signers strictly ascending.
    function deliver(
        uint64 srcChainId,
        uint256 outboxIndex,
        bytes32 ref,
        bytes calldata payload,
        bytes calldata signatures
    ) external {
        address from = remoteContainer[srcChainId];
        if (from == address(0)) revert UnknownChain(srcChainId);
        bytes32 key = keccak256(abi.encode(srcChainId, outboxIndex));
        if (delivered[key]) revert AlreadyDelivered();
        if (ref != keccak256(abi.encodePacked(remoteEndpoint[srcChainId], payload))) revert BadRef();
        bytes32 digest = keccak256(abi.encodePacked(ref, keccak256(payload)));
        _checkSignatures(hubMessageHash(srcChainId, from, outboxIndex, digest), signatures);
        delivered[key] = true;
        emit Relayed(srcChainId, outboxIndex, digest);
        _deliver(srcChainId, payload);
    }

    /// @notice EIP-712 domain separator; recomputed if the chain id changes (chain fork).
    function domainSeparator() public view returns (bytes32) {
        return block.chainid == _cachedChainId ? _cachedDomainSeparator : _buildDomainSeparator();
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("TAP-NFT Hub Relay"), keccak256("1"), block.chainid, address(this))
        );
    }

    function hubMessageHash(uint64 srcChainId, address fromContainer, uint256 outboxIndex, bytes32 digest)
        public
        view
        returns (bytes32)
    {
        bytes32 structHash =
            keccak256(abi.encode(HUB_MESSAGE_TYPEHASH, srcChainId, address(hub), fromContainer, outboxIndex, digest));
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
    }

    function _checkSignatures(bytes32 h, bytes calldata sigs) internal view {
        uint256 k = threshold;
        if (sigs.length != 65 * k) revert BadSignatures();
        address last;
        uint256 j; // cursor in the sorted attester list
        uint256 n = _attesters.length;
        for (uint256 i; i < k; ++i) {
            bytes32 r = bytes32(sigs[i * 65:i * 65 + 32]);
            bytes32 s = bytes32(sigs[i * 65 + 32:i * 65 + 64]);
            uint8 v = uint8(sigs[i * 65 + 64]);
            if (uint256(s) > HALF_N || (v != 27 && v != 28)) revert BadSignatures();
            address signer = ecrecover(h, v, r, s);
            if (signer == address(0) || signer <= last) revert BadSignatures();
            while (j < n && _attesters[j] < signer) ++j;
            if (j == n || _attesters[j] != signer) revert BadSignatures();
            last = signer;
        }
    }
}
