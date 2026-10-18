// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../interfaces/ITapNetlistNFT.sol";
import {ITapNetlistTokenSet} from "../interfaces/ITapNetlistTokenSet.sol";
import {TapBridgeEndpoint} from "./TapBridgeEndpoint.sol";
import {TapBridgePayload} from "./TapBridgePayload.sol";

interface IERC721Escrow {
    function ownerOf(uint256 tokenId) external view returns (address);
    function getApproved(uint256 tokenId) external view returns (address);
    function isApprovedForAll(address owner, address operator) external view returns (bool);
    function transferFrom(address from, address to, uint256 tokenId) external;
}

/// @title Home-chain endpoint: escrows tokens of an unmodified ERC-721 collection
/// @notice Works with any ERC-721, including legacy collections that cannot change (e.g. TapeCode-Test1).
///         The netlist, image and manifest hashes carried in each payload are read from `dataSource`, an
///         ITapNetlistNFT implementation whose `collection()` is the home collection (the collection itself
///         or its companion). With no data source the hashes are zero.
contract TapGateway is TapBridgeEndpoint {
    ITapNetlistNFT public immutable dataSource;
    /// @notice The chain an escrowed token departed to and is recorded on; 0 when not escrowed. Mirrors send only
    ///         to the home chain (hub-and-spoke), so this is where the token lives, and only the route from that
    ///         chain can release it.
    mapping(uint256 => uint64) public locationOf;

    error NotEscrowed(uint256 tokenId);
    error AlreadyEscrowed(uint256 tokenId);
    error NotBound(uint256 tokenId);
    error NotOnRoute(uint256 tokenId, uint64 srcChainId);
    error EscrowFailed(uint256 tokenId);
    error WrongDataSource();
    error NotAuthorized();

    constructor(address homeContract_, address dataSource_, address owner_)
        TapBridgeEndpoint(uint64(block.chainid), homeContract_, owner_)
    {
        if (dataSource_ != address(0) && ITapNetlistNFT(dataSource_).collection() != homeContract_) {
            revert WrongDataSource();
        }
        dataSource = ITapNetlistNFT(dataSource_);
    }

    function supportsInterface(bytes4 id) external pure returns (bool) {
        return id == 0x01ffc9a7 || _isBridgeInterface(id);
    }

    function _depart(uint256 tokenId, address caller, uint64 dstChainId) internal override returns (bytes32, bytes32, bytes32) {
        IERC721Escrow c = IERC721Escrow(homeContract);
        address holder = c.ownerOf(tokenId);
        // Independent of the collection's approval semantics: an escrowed token never departs twice.
        if (locationOf[tokenId] != 0 || holder == address(this)) revert AlreadyEscrowed(tokenId);
        if (caller != holder && !c.isApprovedForAll(holder, caller) && c.getApproved(tokenId) != caller) {
            revert NotAuthorized();
        }
        c.transferFrom(holder, address(this), tokenId);
        if (c.ownerOf(tokenId) != address(this)) revert EscrowFailed(tokenId);
        locationOf[tokenId] = dstChainId;
        (bytes32 n, bytes32 i, bytes32 m) = _hashesOf(tokenId);
        // After the reveal a token covered by the manifest is bound with `bind`; bind first, so that mirrors can
        // serve its netlist. Ids the manifest does not cover can never be bound and depart with zero hashes.
        if ((n == 0 || i == 0) && address(dataSource) != address(0) && dataSource.masterSeed() != 0) {
            // every field the manifest defines must be bound: netlist (bit 2) and image (bit 1) of the pool masks
            uint8 fields = _poolFields();
            if (((fields & 2 != 0 && n == 0) || (fields & 1 != 0 && i == 0)) && _covered(tokenId)) {
                revert NotBound(tokenId);
            }
        }
        return (n, i, m);
    }

    /// @dev Whether the manifest covers `tokenId` (draft §4.2). Set mode: the data source reports
    ///      ITapNetlistTokenSet through ERC-165 and its tokenSetHash() is non-zero. In set mode the token set must be
    ///      recorded on chain (`tokenAt(0)` succeeds), otherwise this reverts NotBound (fail closed); a token is
    ///      covered iff `indexOf` does not revert. Range mode: the data source's `tokenRange()`.
    function _covered(uint256 tokenId) internal view returns (bool) {
        if (_supports(address(dataSource), type(ITapNetlistTokenSet).interfaceId)) {
            ITapNetlistTokenSet ts = ITapNetlistTokenSet(address(dataSource));
            if (ts.tokenSetHash() != 0) {
                try ts.tokenAt(0) returns (uint256) {}
                catch {
                    revert NotBound(tokenId); // token set not recorded yet
                }
                try ts.indexOf(tokenId) returns (uint256) {
                    return true;
                } catch {
                    return false;
                }
            }
        }
        (uint256 first, uint256 supply) = dataSource.tokenRange();
        return tokenId >= first && tokenId - first < supply;
    }

    function _poolFields() internal view returns (uint8 fields) {
        ITapNetlistNFT.Pool[] memory ps = dataSource.pools();
        for (uint256 k; k < ps.length; ++k) {
            fields |= ps[k].fields;
        }
    }

    function _supports(address target, bytes4 id) private view returns (bool) {
        (bool ok, bytes memory ret) = target.staticcall{gas: 30_000}(abi.encodeWithSelector(0x01ffc9a7, id));
        return ok && ret.length == 32 && abi.decode(ret, (uint256)) == 1;
    }

    function _arrive(TapBridgePayload.Payload memory p) internal override {
        IERC721Escrow c = IERC721Escrow(homeContract);
        uint64 at = locationOf[p.tokenId];
        if (at == 0 || c.ownerOf(p.tokenId) != address(this)) revert NotEscrowed(p.tokenId);
        if (at != p.srcChainId) revert NotOnRoute(p.tokenId, p.srcChainId);
        locationOf[p.tokenId] = 0;
        c.transferFrom(address(this), p.to, p.tokenId);
        // The hashes in a returning payload are ignored: the home data source is authoritative.
    }

    function _hashesOf(uint256 tokenId) internal view override returns (bytes32 n, bytes32 i, bytes32 m) {
        if (address(dataSource) == address(0)) return (0, 0, 0);
        n = dataSource.netlistHashOf(tokenId);
        i = dataSource.imageHashOf(tokenId);
        m = dataSource.manifestHash();
    }
}
