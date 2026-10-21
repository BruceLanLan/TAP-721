// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {console2 as console} from "forge-std/console2.sol";
import {DeployBase} from "./DeployBase.s.sol";
import {TapContainerLock, IERC721Min, IContainerOpener, IDomainBinding} from "../src/tools/TapContainerLock.sol";

/// @notice Mocks of the TapeOut contracts a lock talks to, for the anvil dry run only (chain id 31337). On a
///         real chain the lock needs the processor, container opener and payment contract that TAP-10 lists,
///         which exist on the mainnets (BNB Smart Chain, Base, X Layer) and not on the testnets.
contract MockProcessor is IERC721Min {
    mapping(uint256 => address) public owners;

    function set(uint256 id, address o) external {
        owners[id] = o;
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        return owners[tokenId];
    }
}

contract MockOpener is IContainerOpener {
    address public immutable account;

    constructor(address a) {
        account = a;
    }

    function accountOf(address, uint256) external view returns (address) {
        return account;
    }
}

contract MockBinding is IDomainBinding {
    mapping(address => uint256) public containerPaidUntil;

    function monthlyFee() external pure returns (uint256) {
        return 0;
    }

    function bind(string calldata, address container, uint256 months) external payable {
        uint256 from = containerPaidUntil[container] > block.timestamp ? containerPaidUntil[container] : block.timestamp;
        containerPaidUntil[container] = from + months * 30 days;
    }
}

/// @title Deployment of a TapContainerLock (tool, not part of a standard)
/// @notice Reads the container's coordinates from the environment: PROCESSOR, CIRCUIT_ID, CONTAINER, OPENER,
///         BINDING, ON_CHAIN_NAME. The constructor checks `OPENER.accountOf(PROCESSOR, CIRCUIT_ID) == CONTAINER`.
///         Deploying the lock moves nothing: the holder transfers the circuit NFT to it afterwards, by hand.
///         On anvil (31337) and without PROCESSOR set, mocks are deployed so the script can be dry-run.
///
///         forge script script/DeployContainerLock.s.sol --rpc-url "$RPC_URL" --broadcast
contract DeployContainerLock is DeployBase {
    function run() external {
        _loadDeployer();

        address processor = vm.envOr("PROCESSOR", address(0));
        uint256 circuitId = vm.envOr("CIRCUIT_ID", uint256(1));
        address container = vm.envOr("CONTAINER", address(0));
        address opener = vm.envOr("OPENER", address(0));
        address binding = vm.envOr("BINDING", address(0));
        string memory name_ = vm.envOr("ON_CHAIN_NAME", string("1.2.282.tape"));
        bool mocked;

        vm.startBroadcast(deployerKey);

        if (processor == address(0)) {
            require(
                block.chainid == ANVIL,
                "DeployContainerLock: set PROCESSOR/CONTAINER/OPENER/BINDING (mocks are anvil-only)"
            );
            mocked = true;
            MockProcessor p = new MockProcessor();
            container = address(uint160(uint256(keccak256("example container"))));
            p.set(circuitId, deployer);
            processor = address(p);
            opener = address(new MockOpener(container));
            binding = address(new MockBinding());
        }

        TapContainerLock lock = new TapContainerLock(
            IERC721Min(processor), circuitId, container, IContainerOpener(opener), IDomainBinding(binding), name_
        );

        vm.stopBroadcast();

        console.log("TapContainerLock", address(lock));
        console.log("locked          ", lock.locked());

        string memory obj = "containerLock";
        _sectionHeader(obj);
        vm.serializeAddress(obj, "TapContainerLock", address(lock));
        vm.serializeAddress(obj, "processor", processor);
        vm.serializeUint(obj, "circuitId", circuitId);
        vm.serializeAddress(obj, "container", container);
        vm.serializeAddress(obj, "opener", opener);
        vm.serializeAddress(obj, "binding", binding);
        vm.serializeString(obj, "onChainName", name_);
        vm.serializeBool(obj, "mocked", mocked);
        string memory json = vm.serializeBool(obj, "locked", lock.locked());
        _writeSection("containerLock", json);
    }
}
