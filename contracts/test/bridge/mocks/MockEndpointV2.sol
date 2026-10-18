// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {
    MessagingParams,
    MessagingFee,
    MessagingReceipt,
    Origin,
    ILayerZeroReceiverMin,
    UlnConfig
} from "../../../src/bridge/ILayerZeroEndpointV2Min.sol";

/// @notice ReceiveUln302 stand-in: stores each OApp's own ULN config (set through the endpoint).
contract MockReceiveUln {
    address public immutable endpoint;
    mapping(address => mapping(uint32 => UlnConfig)) internal _app;

    constructor(address endpoint_) {
        endpoint = endpoint_;
    }

    function setAppUlnConfig(address oapp, uint32 eid, UlnConfig calldata c) external {
        require(msg.sender == endpoint, "only endpoint");
        _app[oapp][eid] = c;
    }

    function getAppUlnConfig(address oapp, uint32 eid) external view returns (UlnConfig memory) {
        return _app[oapp][eid];
    }
}

/// @notice One instance per simulated chain. `send` queues packets; `deliver` on the destination instance
///         plays the executor: it checks allowInitializePath and calls lzReceive as EndpointV2 would.
contract MockEndpointV2 {
    struct Packet {
        uint32 srcEid;
        bytes32 sender;
        uint32 dstEid;
        bytes32 receiver;
        uint64 nonce;
        bytes32 guid;
        bytes message;
        bytes options;
    }

    uint32 public immutable eid;
    uint256 public baseFee = 0.001 ether;
    uint256 public perByteFee = 1 gwei;
    mapping(address => address) public delegates;
    mapping(bytes32 => uint64) public outboundNonce;
    Packet[] public packets;

    constructor(uint32 eid_) {
        eid = eid_;
    }

    mapping(address => mapping(uint32 => address)) public sendLibrary; // 0 = default
    mapping(address => mapping(uint32 => address)) public receiveLibrary; // 0 = default
    address public defaultReceiveLibrary = address(0xDEF);

    function setDelegate(address d) external {
        delegates[msg.sender] = d;
    }

    modifier onlyDelegate(address oapp) {
        require(msg.sender == oapp || msg.sender == delegates[oapp], "not delegate");
        _;
    }

    function setSendLibrary(address oapp, uint32 eid, address lib) external onlyDelegate(oapp) {
        sendLibrary[oapp][eid] = lib;
    }

    function setReceiveLibrary(address oapp, uint32 eid, address lib, uint256) external onlyDelegate(oapp) {
        receiveLibrary[oapp][eid] = lib;
    }

    /// @dev Simplified setConfig: ULN config (type 2) only, written to the OApp's receive library.
    function setUlnConfig(address oapp, uint32 eid, UlnConfig calldata c) external onlyDelegate(oapp) {
        MockReceiveUln(receiveLibrary[oapp][eid]).setAppUlnConfig(oapp, eid, c);
    }

    mapping(address => mapping(uint32 => uint256)) public timeoutExpiry;

    function setReceiveLibraryTimeout(address oapp, uint32 eid, address, uint256 expiry) external onlyDelegate(oapp) {
        timeoutExpiry[oapp][eid] = expiry;
    }

    function receiveLibraryTimeout(address oapp, uint32 eid) external view returns (address, uint256) {
        return (address(0), timeoutExpiry[oapp][eid]);
    }

    function isDefaultSendLibrary(address oapp, uint32 eid) external view returns (bool) {
        return sendLibrary[oapp][eid] == address(0);
    }

    function getReceiveLibrary(address oapp, uint32 eid) external view returns (address lib, bool isDefault) {
        lib = receiveLibrary[oapp][eid];
        if (lib == address(0)) return (defaultReceiveLibrary, true);
        return (lib, false);
    }

    function quote(MessagingParams calldata p, address) public view returns (MessagingFee memory f) {
        f.nativeFee = baseFee + perByteFee * p.message.length;
    }

    function send(MessagingParams calldata p, address refundAddress)
        external
        payable
        returns (MessagingReceipt memory r)
    {
        uint256 fee = quote(p, msg.sender).nativeFee;
        require(msg.value >= fee, "fee");
        bytes32 sender = bytes32(uint256(uint160(msg.sender)));
        bytes32 path = keccak256(abi.encode(eid, sender, p.dstEid, p.receiver));
        uint64 nonce = ++outboundNonce[path];
        bytes32 guid = keccak256(abi.encodePacked(nonce, eid, sender, p.dstEid, p.receiver));
        packets.push(Packet(eid, sender, p.dstEid, p.receiver, nonce, guid, p.message, p.options));
        if (msg.value > fee) {
            (bool ok,) = refundAddress.call{value: msg.value - fee}("");
            require(ok, "refund");
        }
        r = MessagingReceipt(guid, nonce, MessagingFee(fee, 0));
    }

    function packetCount() external view returns (uint256) {
        return packets.length;
    }

    function getPacket(uint256 i) external view returns (Packet memory) {
        return packets[i];
    }

    /// @notice Executor role on the destination endpoint.
    function deliver(Packet calldata p) external {
        require(p.dstEid == eid, "wrong dst");
        address receiver = address(uint160(uint256(p.receiver)));
        Origin memory o = Origin(p.srcEid, p.sender, p.nonce);
        require(ILayerZeroReceiverMin(receiver).allowInitializePath(o), "path not allowed");
        ILayerZeroReceiverMin(receiver).lzReceive(o, p.guid, p.message, msg.sender, "");
    }

    /// @notice Raw call for negative tests (a forged origin).
    function deliverRaw(address receiver, Origin calldata o, bytes calldata message) external {
        ILayerZeroReceiverMin(receiver).lzReceive(o, bytes32(0), message, msg.sender, "");
    }
}
