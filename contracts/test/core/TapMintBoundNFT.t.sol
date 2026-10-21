// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test, Vm} from "forge-std/Test.sol";
import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {ERC721Min} from "../../src/vendor/ERC721Min.sol";
import {Owned} from "../../src/vendor/Owned.sol";
import {TapMintBoundNFT} from "../../src/core/TapMintBoundNFT.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {LibHarness, Tapnet} from "./CoreHelpers.sol";

/// Mint-bound profile of TAP-721 §8.2: an L1 collection without a manifest.
contract TapMintBoundNFTTest is Test {
    TapMintBoundNFT nft;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address minter = makeAddr("minter");

    bytes xorFile;
    bytes bigFile; // 49,150 bytes, 2 chunks
    bytes32 xorHash;
    bytes32 constant IMG = keccak256("image");
    bytes32 constant NET = keccak256("netlist");

    function setUp() public {
        xorFile = Tapnet.xor17851();
        bigFile = Tapnet.chain(7014, 9);
        xorHash = sha256(xorFile);
        nft = new TapMintBoundNFT("Tape", "TAPE", "ipfs://base/", 0, 0, true, address(this));
    }

    // ------------------------------------------------------------------ basics

    function test_constructorAndInterfaces() public view {
        assertEq(nft.name(), "Tape");
        assertEq(nft.symbol(), "TAPE");
        assertEq(nft.owner(), address(this));
        assertEq(nft.collection(), address(nft));
        assertEq(nft.baseURI(), "ipfs://base/");
        assertTrue(nft.recordsImageHash());
        // ERC-165, ERC-721, ERC-721 Metadata, ERC-4906, ITapNetlistNFT, ERC-173
        assertTrue(nft.supportsInterface(0x01ffc9a7));
        assertTrue(nft.supportsInterface(0x80ac58cd));
        assertTrue(nft.supportsInterface(0x5b5e139f));
        assertTrue(nft.supportsInterface(0x49064906));
        assertTrue(nft.supportsInterface(0x282b67f6));
        assertEq(bytes32(type(ITapNetlistNFT).interfaceId), bytes32(bytes4(0x282b67f6)));
        assertTrue(nft.supportsInterface(0x7f5828d0));
        // not the Eval, TokenSet or Companion extensions, not 0xffffffff
        assertFalse(nft.supportsInterface(0xec7d7e20));
        assertFalse(nft.supportsInterface(0x3f7177c7));
        assertFalse(nft.supportsInterface(0x12b40a6c));
        assertFalse(nft.supportsInterface(0xffffffff));
        // the profile's permanent values
        assertEq(nft.manifestHash(), 0);
        assertEq(nft.masterSeed(), 0);
        assertEq(nft.pools().length, 0);
        (uint256 first, uint256 supply) = nft.tokenRange();
        assertEq(first, 0);
        assertEq(supply, 0);
        assertFalse(nft.frozen());
        assertFalse(nft.mintingEnded());
        assertEq(nft.MAX_FILE(), 49152);
        // tools read frozen() at L1 (§7.2); its selector as listed in Test Cases
        assertEq(bytes32(TapMintBoundNFT.frozen.selector), bytes32(bytes4(0x054f7d9c)));
    }

    function test_constructorReverts() public {
        vm.expectRevert(TapMintBoundNFT.ZeroOwner.selector);
        new TapMintBoundNFT("T", "T", "", 0, 0, true, address(0));
        vm.expectRevert(TapMintBoundNFT.InvalidRange.selector);
        new TapMintBoundNFT("T", "T", "", type(uint256).max, 2, true, address(this));
        // the largest valid range
        new TapMintBoundNFT("T", "T", "", type(uint256).max - 1, 2, true, address(this));
    }

    // ------------------------------------------------------------------ minting

    function test_mintRecordsHashes() public {
        vm.expectEmit(address(nft));
        emit TapMintBoundNFT.NetlistRecorded(7, xorHash, IMG);
        vm.expectEmit(address(nft));
        emit ERC721Min.Transfer(address(0), alice, 7);
        vm.expectEmit(address(nft));
        emit IERC4906.MetadataUpdate(7);
        nft.mint(alice, 7, xorHash, IMG);
        assertEq(nft.ownerOf(7), alice);
        assertEq(nft.balanceOf(alice), 1);
        assertEq(nft.netlistHashOf(7), xorHash);
        assertEq(nft.imageHashOf(7), IMG);
        assertTrue(nft.knownNetlist(xorHash));
        assertEq(nft.tokenURI(7), "ipfs://base/7");
        // an id never minted
        assertEq(nft.netlistHashOf(8), 0);
        assertEq(nft.imageHashOf(8), 0);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 8));
        nft.tokenURI(8);
    }

    function test_mintReverts() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.mint(alice, 1, NET, IMG);

        vm.expectRevert(TapMintBoundNFT.ZeroNetlistHash.selector);
        nft.mint(alice, 1, 0, IMG);
        vm.expectRevert(TapMintBoundNFT.ImageHashRequired.selector);
        nft.mint(alice, 1, NET, 0);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(0)));
        nft.mint(address(0), 1, NET, IMG);

        nft.mint(alice, 1, NET, IMG);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721TokenExists.selector, 1));
        nft.mint(bob, 1, NET, IMG);
        // an existing token: the hash check comes first, so another hash is reported as a mismatch
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.HashMismatch.selector, 1, NET, xorHash));
        nft.mint(bob, 1, xorHash, IMG);

        // minters
        vm.expectEmit(address(nft));
        emit TapMintBoundNFT.MinterSet(minter, true);
        nft.setMinter(minter, true);
        vm.prank(minter);
        nft.mint(bob, 2, NET, IMG);
        assertEq(nft.ownerOf(2), bob);
        nft.setMinter(minter, false);
        vm.prank(minter);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, minter));
        nft.mint(bob, 3, NET, IMG);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.setMinter(alice, true);
    }

    function test_noImageHashCollection() public {
        TapMintBoundNFT c = new TapMintBoundNFT("T", "T", "", 0, 0, false, address(this));
        assertFalse(c.recordsImageHash());
        vm.expectRevert(TapMintBoundNFT.ImageHashNotRecorded.selector);
        c.mint(alice, 1, NET, IMG);
        c.mint(alice, 1, NET, 0);
        assertEq(c.netlistHashOf(1), NET);
        assertEq(c.imageHashOf(1), 0); // the field no pool carries: zero permanently (§5.2)
        assertEq(c.tokenURI(1), ""); // empty base URI
    }

    function test_tokenRangeFixedAtConstruction() public {
        TapMintBoundNFT c = new TapMintBoundNFT("T", "T", "", 100, 5, true, address(this));
        (uint256 first, uint256 supply) = c.tokenRange();
        assertEq(first, 100);
        assertEq(supply, 5);
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.TokenOutOfRange.selector, 99));
        c.mint(alice, 99, NET, IMG);
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.TokenOutOfRange.selector, 105));
        c.mint(alice, 105, NET, IMG);
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.TokenOutOfRange.selector, 0));
        c.mint(alice, 0, NET, IMG);
        c.mint(alice, 100, NET, IMG);
        c.mint(alice, 104, NET, IMG);
        c.freeze();
        (first, supply) = c.tokenRange();
        assertEq(first, 100);
        assertEq(supply, 5);
        // an unbounded collection ignores firstTokenId and accepts any id
        TapMintBoundNFT u = new TapMintBoundNFT("T", "T", "", 100, 0, true, address(this));
        (first, supply) = u.tokenRange();
        assertEq(first, 0);
        assertEq(supply, 0);
        u.mint(alice, 0, NET, IMG);
        u.mint(alice, type(uint256).max, NET, IMG);
    }

    // ------------------------------------------------------------------ burn and re-mint

    function test_burnKeepsHashesAndRemintNeedsTheSameOnes() public {
        nft.mint(alice, 1, NET, IMG);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NotAuthorized.selector, bob, 1));
        nft.burn(1);
        vm.prank(alice);
        nft.burn(1);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 1));
        nft.ownerOf(1);
        assertEq(nft.balanceOf(alice), 0);
        // the hashes recorded at the first mint stay
        assertEq(nft.netlistHashOf(1), NET);
        assertEq(nft.imageHashOf(1), IMG);
        assertTrue(nft.knownNetlist(NET));

        // re-mint with another netlist hash, or another image hash: never
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.HashMismatch.selector, 1, NET, xorHash));
        nft.mint(bob, 1, xorHash, IMG);
        bytes32 otherImg = keccak256("other image");
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.HashMismatch.selector, 1, IMG, otherImg));
        nft.mint(bob, 1, NET, otherImg);

        // re-mint with the identical hashes: allowed, records nothing new
        vm.recordLogs();
        nft.mint(bob, 1, NET, IMG);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        for (uint256 i; i < logs.length; ++i) {
            assertTrue(logs[i].topics[0] != TapMintBoundNFT.NetlistRecorded.selector, "recorded twice");
        }
        assertEq(nft.ownerOf(1), bob);
        assertEq(nft.netlistHashOf(1), NET);

        // an approved operator may burn
        vm.prank(bob);
        nft.approve(alice, 1);
        vm.prank(alice);
        nft.burn(1);
        vm.prank(bob);
        nft.setApprovalForAll(alice, true);
        nft.mint(bob, 1, NET, IMG);
        vm.prank(alice);
        nft.burn(1);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 1));
        nft.burn(1);
    }

    function test_burnedIdNotRemintedAfterMintingEnded() public {
        nft.mint(alice, 1, NET, IMG);
        vm.prank(alice);
        nft.burn(1);
        vm.expectEmit(address(nft));
        emit TapMintBoundNFT.MintingEnded();
        nft.endMinting();
        assertTrue(nft.mintingEnded());
        vm.expectRevert(TapMintBoundNFT.MintingHasEnded.selector);
        nft.mint(alice, 1, NET, IMG);
        vm.expectRevert(TapMintBoundNFT.MintingHasEnded.selector);
        nft.mint(alice, 2, NET, IMG);
        vm.expectRevert(TapMintBoundNFT.MintingHasEnded.selector);
        nft.endMinting();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.endMinting();
        assertEq(nft.netlistHashOf(1), NET); // still recorded
    }

    // ------------------------------------------------------------------ no manifest

    function test_entryIndexOfAndBindRevert() public {
        nft.mint(alice, 1, NET, IMG);
        bytes32[] memory v = new bytes32[](1);
        v[0] = NET;
        bytes32[] memory p = new bytes32[](0);
        uint256[3] memory ids = [uint256(1), 2, type(uint256).max];
        uint256[3] memory poolIdx = [uint256(0), 1, type(uint256).max];
        for (uint256 i; i < 3; ++i) {
            for (uint256 j; j < 3; ++j) {
                vm.expectRevert(TapMintBoundNFT.NoManifest.selector);
                nft.entryIndexOf(ids[i], poolIdx[j]);
                vm.expectRevert(TapMintBoundNFT.NoManifest.selector);
                nft.bind(ids[i], poolIdx[j], v, p);
            }
        }
        // still no manifest after mints and a freeze
        nft.freeze();
        assertEq(nft.manifestHash(), 0);
        assertEq(nft.masterSeed(), 0);
        assertEq(nft.pools().length, 0);
        vm.expectRevert(TapMintBoundNFT.NoManifest.selector);
        nft.entryIndexOf(1, 0);
    }

    // ------------------------------------------------------------------ storeNetlist

    function test_storeNetlist() public {
        // unknown until a token is minted with the hash
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, xorHash));
        nft.storeNetlist(xorFile);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, xorHash));
        nft.netlistFile(xorHash);
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.NotBound.selector, 1));
        nft.netlistOf(1);

        nft.mint(alice, 1, xorHash, IMG);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, xorHash));
        nft.netlistOf(1); // bound but not stored
        vm.prank(bob); // permissionless
        bytes32 h = nft.storeNetlist(xorFile);
        assertEq(h, xorHash);
        assertEq(nft.netlistFile(xorHash), xorFile);
        assertEq(nft.netlistOf(1), xorFile);
        (address pointer, uint256 size, uint256 chunks) = nft.netlistPointer(xorHash);
        assertTrue(pointer != address(0));
        assertEq(size, 44);
        assertEq(chunks, 1);

        // idempotent: no second event
        vm.recordLogs();
        assertEq(nft.storeNetlist(xorFile), xorHash);
        assertEq(vm.getRecordedLogs().length, 0);

        // a two-chunk file, and a second token sharing a stored file
        bytes32 bigHash = sha256(bigFile);
        nft.mint(alice, 2, bigHash, IMG);
        nft.mint(bob, 3, xorHash, IMG);
        vm.expectEmit(true, false, false, false, address(nft));
        emit ITapNetlistNFT.NetlistStored(bigHash, address(0));
        nft.storeNetlist(bigFile);
        assertEq(nft.netlistOf(2), bigFile);
        assertEq(nft.netlistOf(3), xorFile);
        (, size, chunks) = nft.netlistPointer(bigHash);
        assertEq(size, 49150);
        assertEq(chunks, 2);

        // the hash stays known after the token is burned
        bytes32 tffHash = sha256(_tff());
        nft.mint(alice, 4, tffHash, IMG);
        vm.prank(alice);
        nft.burn(4);
        assertEq(nft.storeNetlist(_tff()), tffHash);
        assertEq(nft.netlistOf(4), _tff()); // the recorded hash still resolves
    }

    function test_storeNetlistRejects() public {
        // too large (49,159 bytes), even with the hash minted
        bytes memory tooBig = Tapnet.chain(7017, 6);
        assertEq(tooBig.length, 49159);
        nft.mint(alice, 1, sha256(tooBig), IMG);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistTooLarge.selector, 49159));
        nft.storeNetlist(tooBig);
        // exactly MAX_FILE: accepted
        bytes memory max = Tapnet.chain(7016, 6);
        assertEq(max.length, 49152);
        nft.mint(alice, 2, sha256(max), IMG);
        assertEq(nft.storeNetlist(max), sha256(max));

        // invalid files are rejected on chain even though a token was minted with their hash
        bytes memory noRecords = Tapnet.header(2, 1);
        nft.mint(alice, 3, sha256(noRecords), IMG);
        vm.expectRevert(TapNetlistCheck.TapnetNoRecords.selector);
        nft.storeNetlist(noRecords);
        bytes memory refRecord = bytes.concat(Tapnet.header(2, 1), Tapnet.nand(2, 3), hex"02", new bytes(33));
        nft.mint(alice, 4, sha256(refRecord), IMG);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadOpcode.selector, 23, 2));
        nft.storeNetlist(refRecord);
        bytes memory forward = bytes.concat(Tapnet.header(2, 1), Tapnet.nand(2, 5));
        nft.mint(alice, 5, sha256(forward), IMG);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetForwardReference.selector, 16, 5));
        nft.storeNetlist(forward);
        // a valid file whose hash no token carries
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, sha256(_tff())));
        nft.storeNetlist(_tff());
        // nothing was stored
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, sha256(noRecords)));
        nft.netlistOf(3);
    }

    // ------------------------------------------------------------------ frozen

    function test_frozenTransitions() public {
        assertFalse(nft.frozen());
        nft.mint(alice, 1, NET, IMG);
        vm.expectEmit(address(nft));
        emit TapMintBoundNFT.BaseURISet("ipfs://v2/");
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(0, type(uint256).max);
        nft.setBaseURI("ipfs://v2/");
        assertEq(nft.tokenURI(1), "ipfs://v2/1");
        assertFalse(nft.frozen());

        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.freeze();
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.Frozen();
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(0, type(uint256).max);
        nft.freeze();
        assertTrue(nft.frozen());

        // nothing can change tokenURI or a recorded hash any more
        vm.expectRevert(TapMintBoundNFT.IsFrozen.selector);
        nft.setBaseURI("ipfs://v3/");
        vm.expectRevert(TapMintBoundNFT.IsFrozen.selector);
        nft.freeze();
        vm.expectRevert(abi.encodeWithSelector(TapMintBoundNFT.HashMismatch.selector, 1, NET, xorHash));
        nft.mint(bob, 1, xorHash, IMG);
        assertEq(nft.tokenURI(1), "ipfs://v2/1");

        // a freeze does not end minting or burning (§8.2); frozen() stays true through all of it
        nft.mint(bob, 2, xorHash, IMG);
        assertTrue(nft.frozen());
        assertEq(nft.tokenURI(2), "ipfs://v2/2");
        vm.prank(bob);
        nft.burn(2);
        assertTrue(nft.frozen());
        nft.mint(bob, 2, xorHash, IMG);
        nft.setMinter(minter, true);
        vm.prank(minter);
        nft.mint(bob, 3, xorHash, IMG);
        assertTrue(nft.frozen());

        // ownership stays (minter set, end of minting) and can move
        assertEq(nft.owner(), address(this));
        nft.transferOwnership(alice);
        assertEq(nft.owner(), alice);
        assertTrue(nft.frozen());
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, address(this)));
        nft.setBaseURI("ipfs://v3/");
        vm.prank(alice);
        vm.expectRevert(TapMintBoundNFT.IsFrozen.selector);
        nft.setBaseURI("ipfs://v3/");
        vm.prank(alice);
        nft.endMinting();
        assertTrue(nft.frozen());
        assertTrue(nft.mintingEnded());

        // the terminal state: renounced after the freeze, nothing can change or mint again
        vm.prank(alice);
        nft.transferOwnership(address(0));
        assertEq(nft.owner(), address(0));
        assertTrue(nft.frozen());
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.setMinter(alice, true);
        vm.prank(minter); // the minter set is fixed, but minting has ended
        vm.expectRevert(TapMintBoundNFT.MintingHasEnded.selector);
        nft.mint(bob, 4, xorHash, IMG);
        assertEq(nft.tokenURI(1), "ipfs://v2/1");
    }

    function test_renounceOnlyWhenFrozen() public {
        vm.expectRevert(TapMintBoundNFT.ZeroOwner.selector);
        nft.transferOwnership(address(0));
        nft.transferOwnership(alice);
        vm.prank(alice);
        vm.expectRevert(TapMintBoundNFT.ZeroOwner.selector);
        nft.transferOwnership(address(0));
        vm.prank(alice);
        nft.setMinter(minter, true);
        vm.prank(alice);
        nft.freeze();
        vm.prank(alice);
        nft.transferOwnership(address(0));
        assertEq(nft.owner(), address(0));
        assertTrue(nft.frozen());
        // without endMinting, the fixed minter set keeps minting after the renounce (frozen() does not imply
        // that minting has ended); nobody else can
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, address(this)));
        nft.mint(bob, 1, NET, IMG);
        vm.prank(minter);
        nft.mint(bob, 1, NET, IMG);
        assertEq(nft.netlistHashOf(1), NET);
        assertTrue(nft.frozen());
    }

    function test_freezeBeforeAnyMint() public {
        nft.freeze();
        assertTrue(nft.frozen());
        nft.mint(alice, 1, NET, IMG);
        assertTrue(nft.frozen());
        assertEq(nft.tokenURI(1), "ipfs://base/1");
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, xorHash));
        nft.storeNetlist(xorFile); // a freeze makes no hash known
    }

    // ------------------------------------------------------------------ ERC-721 plumbing

    function test_transfers() public {
        nft.mint(alice, 1, NET, IMG);
        vm.prank(alice);
        nft.transferFrom(alice, bob, 1);
        assertEq(nft.ownerOf(1), bob);
        assertEq(nft.netlistHashOf(1), NET); // binding follows the id, not the holder
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NotAuthorized.selector, alice, 1));
        nft.transferFrom(bob, alice, 1);
        vm.prank(bob);
        nft.safeTransferFrom(bob, alice, 1);
        assertEq(nft.ownerOf(1), alice);
    }

    // ------------------------------------------------------------------ gas

    /// Execution gas inside one transaction (no `isolate`): mint and storeNetlist (run with -vv).
    function test_gas() public {
        bytes memory f1204 = Tapnet.chain(1204, 0); // 8,444 bytes
        bytes memory fmax = Tapnet.chain(7016, 6); // 49,152 bytes, 3 chunks
        uint256 g = gasleft();
        nft.mint(alice, 1, xorHash, IMG);
        emit log_named_uint("mint (first mint of an id, image hash)   ", g - gasleft());
        g = gasleft();
        nft.mint(alice, 2, xorHash, IMG);
        emit log_named_uint("mint (same netlist hash, new id)         ", g - gasleft());
        vm.prank(alice);
        nft.burn(2);
        g = gasleft();
        nft.mint(alice, 2, xorHash, IMG);
        emit log_named_uint("mint (re-mint of a burned id)            ", g - gasleft());
        nft.mint(alice, 3, sha256(f1204), IMG);
        nft.mint(alice, 4, sha256(fmax), IMG);
        g = gasleft();
        nft.storeNetlist(xorFile);
        emit log_named_uint("storeNetlist 44 B (XOR #17851)           ", g - gasleft());
        g = gasleft();
        nft.storeNetlist(f1204);
        emit log_named_uint("storeNetlist 8,444 B (1,204 gates)       ", g - gasleft());
        g = gasleft();
        nft.storeNetlist(fmax);
        emit log_named_uint("storeNetlist 49,152 B (MAX_FILE, 3 chunks)", g - gasleft());
        TapMintBoundNFT c = new TapMintBoundNFT("T", "T", "ipfs://b/", 0, 0, false, address(this));
        g = gasleft();
        c.mint(alice, 1, xorHash, 0);
        emit log_named_uint("mint (first mint of an id, no image hash)", g - gasleft());
    }

    // ------------------------------------------------------------------ helpers

    /// T flip-flop, as in make_core_fixtures.py: latch(7) nand(2,3) nand(2,4) nand(3,4) nand(5,6), nIn 1, nOut 1.
    function _tff() internal pure returns (bytes memory) {
        return bytes.concat(
            Tapnet.header(1, 1),
            Tapnet.latch(7),
            Tapnet.nand(2, 3),
            Tapnet.nand(2, 4),
            Tapnet.nand(3, 4),
            Tapnet.nand(5, 6)
        );
    }
}

/// Differential check against the Python reference's vectors (assets/tap-draft-netlist-bound-nft/vectors.json):
/// the chain side of a collection without a manifest accepts exactly the files tapnft.check_file accepts, and
/// its getters return what the `noManifest` metadata declares.
contract TapMintBoundVectorsTest is Test {
    string json;
    LibHarness h;
    bytes32 constant IMG = keccak256("image");

    function setUp() public {
        json = vm.readFile("../assets/tap-draft-netlist-bound-nft/vectors.json");
        h = new LibHarness();
    }

    function _k(string memory a, uint256 i, string memory b) internal pure returns (string memory) {
        return string.concat(a, "[", vm.toString(i), "]", b);
    }

    function _count(string memory key) internal view returns (uint256 n) {
        while (vm.keyExistsJson(json, _k(key, n, ""))) ++n;
    }

    /// `tapnet`: the four mainnet circuits. A token minted with each hash makes the hash known; storeNetlist
    /// then accepts exactly the valid files and reports the Python metrics.
    function test_tapnetFilesMatchPython() public {
        TapMintBoundNFT nft = new TapMintBoundNFT("T", "T", "", 0, 0, true, address(this));
        uint256 cases = _count(".tapnet");
        assertEq(cases, 4);
        uint256 valid;
        for (uint256 c; c < cases; ++c) {
            bytes memory file = vm.parseJsonBytes(json, _k(".tapnet", c, ".file"));
            bytes32 hash = vm.parseJsonBytes32(json, _k(".tapnet", c, ".netlistHash"));
            assertEq(sha256(file), hash, "netlistHash");
            uint256 tokenId = c + 1;
            nft.mint(address(this), tokenId, hash, IMG);
            assertEq(nft.netlistHashOf(tokenId), hash);
            if (vm.parseJsonBool(json, _k(".tapnet", c, ".valid"))) {
                assertEq(nft.storeNetlist(file), hash);
                assertEq(nft.netlistOf(tokenId), file);
                (uint256 nIn, uint256 nOut, uint256 nand, uint256 latch) = h.check(file);
                assertEq(nIn, vm.parseJsonUint(json, _k(".tapnet", c, ".metrics.nIn")));
                assertEq(nOut, vm.parseJsonUint(json, _k(".tapnet", c, ".metrics.nOut")));
                assertEq(nand, vm.parseJsonUint(json, _k(".tapnet", c, ".metrics.nand")));
                assertEq(latch, vm.parseJsonUint(json, _k(".tapnet", c, ".metrics.latch")));
                assertEq(file.length, vm.parseJsonUint(json, _k(".tapnet", c, ".metrics.bytes")));
                ++valid;
            } else {
                // #38 holds a REF record: minted, known, but never storable
                assertTrue(nft.knownNetlist(hash));
                vm.expectRevert();
                nft.storeNetlist(file);
                vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, hash));
                nft.netlistOf(tokenId);
            }
        }
        assertEq(valid, 3);
    }

    /// `invalidFiles`: one file per rule of §2.2. Minting with their hashes is allowed (the contract cannot
    /// know the file at mint); storing them is not.
    function test_invalidFilesRejectedLikePython() public {
        TapMintBoundNFT nft = new TapMintBoundNFT("T", "T", "", 0, 0, true, address(this));
        uint256 cases = _count(".invalidFiles");
        assertEq(cases, 13);
        for (uint256 c; c < cases; ++c) {
            bytes memory file = vm.parseJsonBytes(json, _k(".invalidFiles", c, ".file"));
            nft.mint(address(this), c + 1, sha256(file), IMG);
            try nft.storeNetlist(file) {
                revert(string.concat("accepted: ", vm.parseJsonString(json, _k(".invalidFiles", c, ".name"))));
            } catch {}
        }
    }

    /// `noManifest`: the metadata of mint-bound tokens at the chain id and address the Python side used. The
    /// getters return the declared hashes, the collection has no manifest, and two tokens with the same netlist
    /// hash are both minted without an edition (§6.4).
    function test_noManifestMetadataMatchesChain() public {
        vm.chainId(196);
        address coll = address(uint160(0xaa));
        deployCodeTo(
            "TapMintBoundNFT.sol:TapMintBoundNFT",
            abi.encode("Example", "EX", "https://example.invalid/token/", uint256(0), uint256(0), true, address(this)),
            coll
        );
        TapMintBoundNFT nft = TapMintBoundNFT(coll);
        assertEq(nft.collection(), coll);

        // the valid documents without tap.manifest
        uint256 cases = _count(".noManifest.valid");
        assertEq(cases, 3);
        uint256 mintBound;
        for (uint256 c; c < cases; ++c) {
            string memory doc = _k(".noManifest.valid", c, ".document");
            if (vm.keyExistsJson(json, string.concat(doc, ".tap.manifest"))) continue; // not a mint-bound token
            assertEq(vm.parseJsonString(json, string.concat(doc, ".tap.state")), "revealed");
            assertEq(
                vm.parseJsonString(json, string.concat(doc, ".tap.id")),
                "eip155:196/erc721:0x00000000000000000000000000000000000000aa/1"
            );
            assertFalse(vm.keyExistsJson(json, string.concat(doc, ".tap.edition")));
            ++mintBound;
        }
        assertEq(mintBound, 2);

        // editions.documents: tokens 1 and 2 with the same netlist hash
        cases = _count(".noManifest.editions.documents");
        assertEq(cases, 2);
        assertTrue(vm.parseJsonBool(json, ".noManifest.editions.valid"));
        bytes32 shared;
        for (uint256 c; c < cases; ++c) {
            string memory doc = _k(".noManifest.editions.documents", c, "");
            bytes32 net = vm.parseJsonBytes32(json, string.concat(doc, ".tap.netlist.sha256"));
            bytes32 img = vm.parseJsonBytes32(json, string.concat(doc, ".tap.image.sha256"));
            uint256 tokenId = c + 1;
            string memory id = vm.parseJsonString(json, string.concat(doc, ".tap.id"));
            assertEq(
                id, string.concat("eip155:196/erc721:0x00000000000000000000000000000000000000aa/", vm.toString(tokenId))
            );
            if (c == 0) shared = net;
            else assertEq(net, shared, "same netlist hash");
            nft.mint(address(this), tokenId, net, img);
            assertEq(nft.netlistHashOf(tokenId), net, "netlistHashOf = tap.netlist.sha256");
            assertEq(nft.imageHashOf(tokenId), img, "imageHashOf = tap.image.sha256");
            assertFalse(vm.keyExistsJson(json, string.concat(doc, ".tap.manifest")));
            assertFalse(vm.keyExistsJson(json, string.concat(doc, ".tap.edition")));
            // §7.3 item 2 on the declared metrics
            uint256 nand = vm.parseJsonUint(json, string.concat(doc, ".tap.netlist.nand"));
            uint256 latch = vm.parseJsonUint(json, string.concat(doc, ".tap.netlist.latch"));
            assertEq(vm.parseJsonUint(json, string.concat(doc, ".tap.netlist.bytes")), 16 + 7 * nand + 4 * latch);
        }
        assertEq(nft.manifestHash(), 0);
        // the L0 freeze probe the documents name is for collections without ITapNetlistNFT; at L1 tools read frozen()
        assertEq(vm.parseJsonString(json, ".noManifest.freezeProbe.probe.call"), "uriFrozen()");
        assertEq(vm.parseJsonUint(json, ".noManifest.freezeProbe.probe.chainId"), block.chainid);
        assertEq(vm.parseJsonAddress(json, ".noManifest.freezeProbe.probe.contract"), coll);
        assertFalse(nft.frozen());
        nft.freeze();
        assertTrue(nft.frozen());
    }
}
