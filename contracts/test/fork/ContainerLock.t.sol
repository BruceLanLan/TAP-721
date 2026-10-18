// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {TapContainerLock, IERC721Min, IDomainBinding, IContainerOpener} from "../../src/tools/TapContainerLock.sol";

interface IProcessor {
    function ownerOf(uint256) external view returns (address);
    function transferFrom(address, address, uint256) external;
    function safeTransferFrom(address, address, uint256) external;
}

interface ISiteRegistry {
    function canEdit(address container, address who) external view returns (bool);
    function putFile(address container, string calldata path, string calldata contentType, bytes32 sha, bytes calldata data) external;
    function removeFile(address container, string calldata path) external;
    function setOperator(address container, address op, uint256 ttl) external;
    function pathCount(address container) external view returns (uint256);
    function read(address container, string calldata path) external view returns (bytes memory);
}

interface IContainer {
    function owner() external view returns (address);
    function execute(address to, uint256 value, bytes calldata data, uint8 op) external payable returns (bytes memory);
}

interface IDomainBindingFull is IDomainBinding {
    function isContainerLive(address container) external view returns (bool);
}

/// Fork tests against X Layer mainnet state, using the container that owns TapeCode-Test1
/// (circuit #1 of processor 282, on-chain name 1.2.282.tape). Nothing is broadcast.
/// Run: XLAYER_RPC=https://rpc.xlayer.tech forge test --match-path test/fork/ContainerLock.t.sol
contract ContainerLockForkTest is Test {
    IProcessor constant PROC = IProcessor(0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF);
    address constant CONTAINER = 0xa8Edd3B032D33aA0657a3E151a7F8c3e5F71F6B9;
    address constant HOLDER = 0x1183a1a0f98Dd2eF8f66895C6811bbf43032843e;
    ISiteRegistry constant SITES = ISiteRegistry(0xd6EFb7adCc9c83dC4924Ad56f6a8E4e969b9ADB6);
    IDomainBindingFull constant BINDING = IDomainBindingFull(0x68809Fd2fb343aA57D0aeB7f33Defe477c9666f9);
    address constant OPENER = 0x536adD8F30f03b69f6fbF29d425A816A0dC50106;
    address constant TEST1 = 0x0e91460D6823C711643e650A9a4C0cc21DE41614;
    uint256 constant EXEC_FEE = 0.0013 ether;

    bool forked;

    function setUp() public {
        string memory rpc = vm.envOr("XLAYER_RPC", string(""));
        if (bytes(rpc).length == 0) return;
        vm.createSelectFork(rpc);
        forked = true;
        vm.deal(HOLDER, 10 ether);
    }

    function test_selfOwnershipLocksButCannotRenew() public {
        if (!forked) return;
        vm.prank(HOLDER);
        vm.expectRevert(); // the container rejects its own circuit through the ERC-721 hook (SelfOwnership)
        PROC.safeTransferFrom(HOLDER, CONTAINER, 1);

        vm.prank(HOLDER);
        PROC.transferFrom(HOLDER, CONTAINER, 1); // no hook: the cycle is created
        assertEq(IContainer(CONTAINER).owner(), address(0));
        assertFalse(SITES.canEdit(CONTAINER, HOLDER));

        vm.prank(HOLDER);
        vm.expectRevert();
        SITES.removeFile(CONTAINER, "index.html");

        vm.prank(address(0xb0));
        vm.expectRevert(); // nobody can renew a self-owned container: activation ends at its paid-until date
        BINDING.bind("1.2.282.tape", CONTAINER, 12);
    }

    function test_lockContractFreezesFilesAndKeepsRenewing() public {
        if (!forked) return;
        TapContainerLock lock =
            new TapContainerLock(
            IERC721Min(address(PROC)), 1, CONTAINER, IContainerOpener(OPENER), IDomainBinding(address(BINDING)), "1.2.282.tape"
        );
        vm.expectRevert(TapContainerLock.WrongContainer.selector);
        new TapContainerLock(
            IERC721Min(address(PROC)), 2, CONTAINER, IContainerOpener(OPENER), IDomainBinding(address(BINDING)), "x"
        );
        uint256 before = SITES.pathCount(CONTAINER);
        bytes memory index = SITES.read(CONTAINER, "index.html");

        vm.prank(HOLDER);
        PROC.safeTransferFrom(HOLDER, address(lock), 1);
        assertTrue(lock.locked());
        assertEq(IContainer(CONTAINER).owner(), address(lock));

        // the old holder lost every write path
        assertFalse(SITES.canEdit(CONTAINER, HOLDER));
        bytes32 h = sha256("hi");
        vm.startPrank(HOLDER);
        vm.expectRevert();
        SITES.putFile(CONTAINER, "x.txt", "text/plain", h, "hi");
        vm.expectRevert();
        SITES.removeFile(CONTAINER, "index.html");
        vm.expectRevert();
        SITES.setOperator(CONTAINER, HOLDER, 3600);
        vm.expectRevert();
        IContainer(CONTAINER).execute{value: EXEC_FEE}(TEST1, 0, abi.encodeWithSignature("setBaseURI(string)", "https://x/"), 0);
        vm.stopPrank();

        // files are unchanged and readable
        assertEq(SITES.pathCount(CONTAINER), before);
        assertEq(keccak256(SITES.read(CONTAINER, "index.html")), keccak256(index));

        // anyone can keep the activation alive, now and in ten years
        vm.prank(address(0xb0));
        lock.renew(12);
        assertTrue(BINDING.isContainerLive(CONTAINER));
        vm.warp(block.timestamp + 3650 days);
        assertFalse(BINDING.isContainerLive(CONTAINER));
        vm.prank(address(0xb1));
        lock.renew(12);
        assertTrue(BINDING.isContainerLive(CONTAINER));
    }
}
