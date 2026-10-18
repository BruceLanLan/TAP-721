// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {TapAdapterBase} from "../../../src/bridge/TapAdapterBase.sol";
import {ITapBridgeEndpoint} from "../../../src/interfaces/ITapBridge.sol";

/// @notice Test transport: `send` records payloads; anyone may `deliver` (no authentication — tests only).
contract MockAdapter is TapAdapterBase {
    uint256 public fee;
    bytes[] public payloads;
    uint64[] public dsts;
    /// @notice Light mode stores nothing and only emits the payload, to measure endpoint gas without mock storage.
    bool public light;

    event Sent(bytes payload);

    constructor(address endpoint_, uint256 fee_) TapAdapterBase(endpoint_, msg.sender) {
        fee = fee_;
    }

    function setLight(bool on) external {
        light = on;
    }

    function setRemote(uint64 chainId, address remote) external onlyOwner {
        _setRemoteEndpoint(chainId, remote);
    }

    function layerId() external pure returns (bytes32) {
        return keccak256("TAP-NFT adapter Mock v1");
    }

    function quote(uint64, bytes calldata, bytes calldata) external view returns (uint256) {
        return fee;
    }

    function send(uint64 dst, bytes calldata payload, bytes calldata, address)
        external
        payable
        onlyEndpoint
        returns (bytes32)
    {
        require(msg.value == fee, "fee");
        if (light) {
            emit Sent(payload);
            return bytes32(0);
        }
        payloads.push(payload);
        dsts.push(dst);
        return keccak256(payload);
    }

    function lastPayload() external view returns (bytes memory) {
        return payloads[payloads.length - 1];
    }

    function deliver(uint64 srcChainId, bytes calldata payload) external {
        _deliver(srcChainId, payload);
    }

    /// @notice Hands the endpoint an arbitrary claimed source endpoint (negative tests).
    function deliverAs(uint64 srcChainId, address srcEndpoint, bytes calldata payload) external {
        ITapBridgeEndpoint(endpoint).receivePayload(srcChainId, srcEndpoint, payload);
    }
}
