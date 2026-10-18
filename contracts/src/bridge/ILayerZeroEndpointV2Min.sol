// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title The part of LayerZero V2 EndpointV2 the adapter uses, written from its public interface
/// @notice Structs and selectors match ILayerZeroEndpointV2 (LayerZero-v2 protocol package). No LayerZero code is copied.
struct MessagingParams {
    uint32 dstEid;
    bytes32 receiver;
    bytes message;
    bytes options;
    bool payInLzToken;
}

struct MessagingFee {
    uint256 nativeFee;
    uint256 lzTokenFee;
}

struct MessagingReceipt {
    bytes32 guid;
    uint64 nonce;
    MessagingFee fee;
}

struct Origin {
    uint32 srcEid;
    bytes32 sender;
    uint64 nonce;
}

interface ILayerZeroEndpointV2Min {
    function quote(MessagingParams calldata params, address sender) external view returns (MessagingFee memory);

    function send(MessagingParams calldata params, address refundAddress)
        external
        payable
        returns (MessagingReceipt memory);

    function setDelegate(address delegate) external;

    /// @notice True while `sender` follows the endpoint owner's default send library towards `dstEid`.
    function isDefaultSendLibrary(address sender, uint32 dstEid) external view returns (bool);

    /// @notice The receive library `receiver` uses for `srcEid`, and whether it is the default.
    function getReceiveLibrary(address receiver, uint32 srcEid) external view returns (address lib, bool isDefault);

    /// @notice A previous receive library that stays valid until block `expiry` (grace period after a switch).
    function receiveLibraryTimeout(address receiver, uint32 srcEid) external view returns (address lib, uint256 expiry);

    function eid() external view returns (uint32);
}

/// @notice ULN (ReceiveUln302) verification config of one OApp for one remote eid.
struct UlnConfig {
    uint64 confirmations; // 0 = follow the default
    uint8 requiredDVNCount; // 0 = follow the default; 255 = explicitly none (optional DVNs only)
    uint8 optionalDVNCount;
    uint8 optionalDVNThreshold;
    address[] requiredDVNs;
    address[] optionalDVNs;
}

/// @notice The part of ReceiveUln302 the adapter reads: the OApp's own (not default-merged) config.
interface IReceiveUlnMin {
    function getAppUlnConfig(address oapp, uint32 remoteEid) external view returns (UlnConfig memory);
}

/// @notice What EndpointV2 calls on a receiving OApp.
interface ILayerZeroReceiverMin {
    function allowInitializePath(Origin calldata origin) external view returns (bool);

    function nextNonce(uint32 srcEid, bytes32 sender) external view returns (uint64);

    function lzReceive(
        Origin calldata origin,
        bytes32 guid,
        bytes calldata message,
        address executor,
        bytes calldata extraData
    ) external payable;
}
