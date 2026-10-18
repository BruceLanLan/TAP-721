// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

interface IERC721Min {
    function ownerOf(uint256 tokenId) external view returns (address);
}

interface IContainerOpener {
    function accountOf(address circuits, uint256 tokenId) external view returns (address);
}

interface IDomainBinding {
    function bind(string calldata nameOrDomain, address container, uint256 months) external payable;
    function containerPaidUntil(address container) external view returns (uint256);
    function monthlyFee() external view returns (uint256);
}

/// @title Lock for a TapeOut container's files
/// @notice Holds the circuit NFT of one TapeOut container forever. Once the NFT is transferred here, nobody can
///         write, replace or remove the container's files, set an operator, or move the container's assets:
///         the site store and the container accept only the circuit's holder, and this contract has no code
///         path that calls them. The only thing it can do is renew the container's activation with
///         `DomainBinding.bind`, which anyone may trigger and pay for, so the site stays displayable for as long
///         as someone renews it. There is no owner, no upgrade and no way to get the NFT back.
/// @dev    Transfer the NFT with `transferFrom` or `safeTransferFrom`; `onERC721Received` accepts only the
///         configured circuit. Before transferring, the holder SHOULD clear any site-store operator
///         (`setOperator(container, 0, 0)`) and any ERC-721 operator approval that the container itself granted.
///         The lock is only as permanent as the contracts it relies on: the processor (a beacon proxy), the
///         container implementation (a beacon proxy) and the site store and payment contract (UUPS proxies)
///         can still be upgraded by their owners. `onChainName` is not checked; a wrong name only makes
///         `renew` revert.
contract TapContainerLock {
    IERC721Min public immutable processor;
    uint256 public immutable circuitId;
    address public immutable container;
    IDomainBinding public immutable binding;
    /// The container opener the constructor checked `container` against (tools verify it is the chain's).
    IContainerOpener public immutable opener;
    string public onChainName;

    error WrongToken();
    error WrongContainer();
    error RefundFailed();

    event Renewed(address indexed by, uint256 months, uint256 paid, uint256 paidUntil);

    /// @param opener_ The chain's TapeOut container opener (TAP-10 Deployments). The constructor checks that
    ///        `container_` is the container of (`processor_`, `circuitId_`), so a lock cannot claim another container.
    constructor(
        IERC721Min processor_,
        uint256 circuitId_,
        address container_,
        IContainerOpener opener_,
        IDomainBinding binding_,
        string memory name_
    ) {
        if (opener_.accountOf(address(processor_), circuitId_) != container_) {
            revert WrongContainer();
        }
        processor = processor_;
        circuitId = circuitId_;
        container = container_;
        binding = binding_;
        opener = opener_;
        onChainName = name_;
    }

    /// @notice True once this contract holds the circuit, i.e. the container's files can no longer change.
    function locked() external view returns (bool) {
        return processor.ownerOf(circuitId) == address(this);
    }

    /// @notice Renew the container's activation by `months`. Anyone may call; the fee is `months × monthlyFee()`
    ///         as the payment contract sets it at call time (currently zero on BNB Smart Chain and X Layer),
    ///         paid from `msg.value`. Excess value is refunded. The payment contract caps how far ahead a
    ///         container can be paid (about ten years); call again later to extend further.
    function renew(uint256 months) external payable {
        uint256 fee = months * binding.monthlyFee();
        binding.bind{value: fee}(onChainName, container, months);
        uint256 rest = msg.value - fee;
        if (rest > 0) {
            (bool ok,) = msg.sender.call{value: rest}("");
            if (!ok) revert RefundFailed();
        }
        emit Renewed(msg.sender, months, fee, binding.containerPaidUntil(container));
    }

    function onERC721Received(address, address, uint256 tokenId, bytes calldata) external view returns (bytes4) {
        if (msg.sender != address(processor) || tokenId != circuitId) revert WrongToken();
        return this.onERC721Received.selector;
    }
}
