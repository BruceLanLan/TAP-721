// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IOwnerOf {
    function ownerOf(uint256) external view returns (address);
}

/// @notice TAP-10 hub stand-in: enforces "writer = current circuit holder", keeps an outbox and emits Sent.
contract MockHub {
    struct OutEntry {
        bytes32 to;
        uint32 inboxIndex;
        bytes32 digest;
    }

    mapping(bytes32 => uint256) public inboxCount;
    mapping(address => OutEntry[]) internal _outbox;

    event Sent(
        bytes32 indexed to,
        address indexed from,
        bytes32 indexed ref,
        uint256 inboxIndex,
        uint256 outboxIndex,
        bytes payload
    );

    function accountOf(address circuits, uint256 tokenId) public pure returns (address) {
        return address(uint160(uint256(keccak256(abi.encode("container", circuits, tokenId)))));
    }

    function send(address circuits, uint256 tokenId, bytes32 to, bytes32 ref, bytes calldata payload)
        external
        returns (uint256 inboxIndex)
    {
        require(uint256(to) >> 224 == 0 && uint64(uint256(to) >> 160) != 0, "BadEndpoint");
        require(payload.length != 0 && payload.length <= 16000, "payload");
        require(IOwnerOf(circuits).ownerOf(tokenId) == msg.sender, "NotHolder");
        address from = accountOf(circuits, tokenId);
        inboxIndex = inboxCount[to]++;
        bytes32 digest = keccak256(abi.encodePacked(ref, keccak256(payload)));
        _outbox[from].push(OutEntry(to, uint32(inboxIndex), digest));
        emit Sent(to, from, ref, inboxIndex, _outbox[from].length - 1, payload);
    }

    function outboxCount(address from) external view returns (uint256) {
        return _outbox[from].length;
    }

    function outboxAt(address from, uint256 i) external view returns (OutEntry memory) {
        return _outbox[from][i];
    }
}
