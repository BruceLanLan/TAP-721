// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title Single-owner access control. Renouncing (owner = address(0)) is permanent.
abstract contract Owned {
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    error Unauthorized(address account);

    address private _owner;

    constructor(address initialOwner) {
        _setOwner(initialOwner);
    }

    modifier onlyOwner() {
        if (msg.sender != _owner) revert Unauthorized(msg.sender);
        _;
    }

    function owner() public view virtual returns (address) {
        return _owner;
    }

    /// @notice Transfer ownership; `newOwner` = address(0) renounces it for good.
    function transferOwnership(address newOwner) public virtual onlyOwner {
        _setOwner(newOwner);
    }

    function _setOwner(address newOwner) internal virtual {
        emit OwnershipTransferred(_owner, newOwner);
        _owner = newOwner;
    }
}
