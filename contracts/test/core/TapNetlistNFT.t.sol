// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {ITapNetlistNFT} from "../../src/interfaces/ITapNetlistNFT.sol";
import {IERC4906} from "../../src/vendor/IERC4906.sol";
import {ERC721Min} from "../../src/vendor/ERC721Min.sol";
import {Owned} from "../../src/vendor/Owned.sol";
import {TapCompanion} from "../../src/core/TapCompanion.sol";
import {TapMerkle} from "../../src/core/TapMerkle.sol";
import {TapNetlistCore} from "../../src/core/TapNetlistCore.sol";
import {TapNetlistNFT} from "../../src/core/TapNetlistNFT.sol";
import {TapNetlistCheck} from "../../src/core/TapNetlistCheck.sol";
import {TapNetlistStore} from "../../src/core/TapNetlistStore.sol";
import {TapPermutation} from "../../src/core/TapPermutation.sol";
import {Vm} from "forge-std/Vm.sol";
import {CoreBase} from "./CoreBase.sol";
import {BadReceiver, GoodReceiver, ShortReceiver, MerkleBuilder, Tapnet} from "./CoreHelpers.sol";

contract TapNetlistNFTTest is CoreBase {
    TapNetlistNFT nft;
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address minter = makeAddr("minter");

    function setUp() public {
        _buildPools(20);
        nft = new TapNetlistNFT("Tape", "TAPE", "ipfs://base/", address(this));
    }

    function _commit() internal {
        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
    }

    function _commitReveal() internal {
        _commit();
        nft.reveal(SEED);
    }

    function _pool(uint8 f, bytes32 root) internal pure returns (ITapNetlistNFT.Pool[] memory ps) {
        ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool("P", f, root);
    }

    // ------------------------------------------------------------------ basics

    function test_constructorAndInterfaces() public view {
        assertEq(nft.name(), "Tape");
        assertEq(nft.symbol(), "TAPE");
        assertEq(nft.owner(), address(this));
        assertEq(nft.collection(), address(nft));
        assertEq(nft.baseURI(), "ipfs://base/");
        assertTrue(nft.supportsInterface(0x01ffc9a7));
        assertTrue(nft.supportsInterface(0x80ac58cd));
        assertTrue(nft.supportsInterface(0x5b5e139f));
        assertTrue(nft.supportsInterface(0x49064906));
        assertTrue(nft.supportsInterface(type(ITapNetlistNFT).interfaceId));
        assertFalse(nft.supportsInterface(0xffffffff));
        assertFalse(nft.frozen());
        assertEq(nft.manifestHash(), 0);
        assertEq(nft.masterSeed(), 0);
    }

    // ------------------------------------------------------------------ commit

    function test_commitManifest() public {
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.ManifestCommitted(MANIFEST);
        _commit();
        assertEq(nft.manifestHash(), MANIFEST);
        (uint256 first, uint256 n) = nft.tokenRange();
        assertEq(first, FIRST);
        assertEq(n, supply);
        ITapNetlistNFT.Pool[] memory ps = nft.pools();
        assertEq(ps.length, 2);
        assertEq(ps[0].label, "IMAGE_V1");
        assertEq(ps[1].fields, 2);
        assertEq(ps[1].root, MerkleBuilder.root(netLeaves));
    }

    function test_commitReverts() public {
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);

        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifest(0, FIRST, supply, ps);
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifest(MANIFEST, FIRST, 0, ps);
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifest(MANIFEST, FIRST, 100_001, ps); // above MAX_TOKENS
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifest(MANIFEST, FIRST, supply, new ITapNetlistNFT.Pool[](0));
        vm.expectRevert(TapNetlistCore.InvalidManifest.selector);
        nft.commitManifest(MANIFEST, type(uint256).max, 2, ps);

        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _pool(0, bytes32(uint256(1))));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _pool(4, bytes32(uint256(1))));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _pool(2, 0));
        ps[1].fields = 3; // overlaps pool 0's image field
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 1));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);

        nft.commitManifest(MANIFEST, FIRST, supply, _pools());
        ps = _pools(); // builds the tree with sha256 precompile calls, so not inside expectRevert
        vm.expectRevert(TapNetlistCore.AlreadyCommitted.selector);
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
    }

    // ------------------------------------------------------------------ mint and tokenURI

    function test_mint() public {
        _commit();
        nft.mint(alice, FIRST);
        nft.setMinter(minter, true);
        vm.prank(minter);
        nft.mint(bob, FIRST + supply - 1);
        assertEq(nft.ownerOf(FIRST), alice);
        assertEq(nft.ownerOf(FIRST + supply - 1), bob);
        assertEq(nft.balanceOf(alice), 1);
        assertTrue(nft.isMinter(minter));
    }

    function test_mintReverts() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.mint(alice, FIRST);
        _commit();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.mint(alice, FIRST);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, 0));
        nft.mint(alice, 0);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, FIRST + supply));
        nft.mint(alice, FIRST + supply);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(0)));
        nft.mint(address(0), FIRST);
        nft.mint(alice, FIRST);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721TokenExists.selector, FIRST));
        nft.mint(bob, FIRST);
        nft.setMinter(minter, true);
        nft.setMinter(minter, false);
        vm.prank(minter);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, minter));
        nft.mint(bob, FIRST + 1);
    }

    function test_setMinterOnlyOwner() public {
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.setMinter(alice, true);
    }

    function test_tokenURI() public {
        _commit();
        nft.mint(alice, 12);
        assertEq(nft.tokenURI(12), "ipfs://base/12");
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 13));
        nft.tokenURI(13);
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.setBaseURI("");
        assertEq(nft.tokenURI(12), "");
        nft.setBaseURI("ar://x/");
        assertEq(nft.tokenURI(12), "ar://x/12");
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.setBaseURI("evil");
    }

    function test_tokenURIZeroAndLargeIds() public {
        TapNetlistNFT c = new TapNetlistNFT("T", "T", "u/", address(this));
        vm.expectEmit(address(c));
        emit IERC4906.BatchMetadataUpdate(0, type(uint256).max);
        c.setBaseURI("b/");
        c.commitManifest(MANIFEST, 0, c.MAX_TOKENS(), _pool(1, bytes32(uint256(1))));
        c.mint(alice, 0);
        c.mint(alice, 99_999);
        assertEq(c.tokenURI(0), "b/0");
        assertEq(c.tokenURI(99_999), "b/99999");
        TapNetlistNFT d = new TapNetlistNFT("T", "T", "b/", address(this));
        d.commitManifest(MANIFEST, type(uint256).max, 1, _pool(1, bytes32(uint256(1))));
        d.mint(alice, type(uint256).max);
        assertEq(
            d.tokenURI(type(uint256).max),
            "b/115792089237316195423570985008687907853269984665640564039457584007913129639935"
        );
    }

    /// CI guard: both deployable contracts stay within EIP-170 (24,576 bytes of runtime code).
    function test_runtimeSizesWithinEIP170() public {
        TapCompanion comp = new TapCompanion(address(1), bytes4(0), address(this));
        emit log_named_uint("TapNetlistNFT runtime bytes", address(nft).code.length);
        emit log_named_uint("TapCompanion runtime bytes", address(comp).code.length);
        assertLe(address(nft).code.length, 24_576);
        assertLe(address(comp).code.length, 24_576);
    }

    // ------------------------------------------------------------------ reveal

    function test_reveal() public {
        _commit();
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.Revealed(SEED);
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.reveal(SEED);
        assertEq(nft.masterSeed(), SEED);
        assertEq(nft.poolSeed(1), TapPermutation.poolSeed(SEED, uint64(block.chainid), address(nft), "NETLIST_V1"));
    }

    function test_revealReverts() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.reveal(SEED);
        _commit();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.reveal(0);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.reveal(keccak256("other"));
    }

    function test_blockhashReveal() public {
        _commit();
        uint256 target = block.number + 5;
        vm.expectEmit(address(nft));
        emit TapNetlistCore.RevealScheduled(target);
        nft.scheduleBlockhashReveal(target);
        assertEq(nft.revealBlock(), target);

        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.RevealIsScheduled.selector, target));
        nft.reveal(SEED);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.RevealIsScheduled.selector, target));
        nft.scheduleBlockhashReveal(target + 10);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, target + 1));
        nft.revealFromBlockhash(target + 1);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BlockhashUnavailable.selector, target));
        nft.revealFromBlockhash(target); // not mined yet

        vm.roll(target + 1);
        bytes32 bh = blockhash(target);
        vm.assume(bh != 0);
        vm.prank(alice); // permissionless
        nft.revealFromBlockhash(target);
        assertEq(nft.masterSeed(), bh);
    }

    /// One shot: a missed window cannot be rescheduled (no second seed), and manual reveal stays disabled.
    function test_blockhashNeverYieldsSentinel() public {
        _commit();
        uint256 target = block.number + 1;
        nft.scheduleBlockhashReveal(target);
        vm.roll(target + 1);
        vm.setBlockhash(target, bytes32(type(uint256).max));
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.revealFromBlockhash(target);
        assertEq(nft.masterSeed(), 0);
    }

    function test_revealRejectsSentinel() public {
        _commit();
        bytes32 sentinel = nft.NO_REVEAL();
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.reveal(sentinel);
    }

    function test_blockhashRevealMissedWindowIsFinal() public {
        _commit();
        uint256 target = block.number + 1;
        nft.scheduleBlockhashReveal(target);
        vm.roll(target + 257);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.BlockhashUnavailable.selector, target));
        nft.revealFromBlockhash(target);
        uint256 next = block.number + 3;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.RevealIsScheduled.selector, target));
        nft.scheduleBlockhashReveal(next);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.RevealIsScheduled.selector, target));
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.freeze();
    }

    function test_scheduleReverts() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.scheduleBlockhashReveal(block.number + 1);
        _commit();
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, block.number));
        nft.scheduleBlockhashReveal(block.number);
        uint256 far = block.number + nft.MAX_REVEAL_DELAY() + 1;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, far));
        nft.scheduleBlockhashReveal(far);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, type(uint256).max));
        nft.scheduleBlockhashReveal(type(uint256).max);
        TapNetlistNFT c = new TapNetlistNFT("T", "T", "", address(this));
        c.commitManifest(MANIFEST, FIRST, supply, _pools());
        c.scheduleBlockhashReveal(block.number + c.MAX_REVEAL_DELAY());
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.scheduleBlockhashReveal(block.number + 1);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, 0));
        nft.revealFromBlockhash(0);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.scheduleBlockhashReveal(block.number + 1);
    }

    // ------------------------------------------------------------------ entryIndexOf

    function test_entryIndexOfIsPermutation() public {
        _commitReveal();
        bool[] memory hit = new bool[](supply);
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            uint256 e = nft.entryIndexOf(t, 1);
            assertFalse(hit[e]);
            hit[e] = true;
            assertEq(e, TapPermutation.permute(nft.poolSeed(1), supply, t - FIRST));
        }
    }

    function test_entryIndexOfReverts() public {
        _commit();
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.entryIndexOf(FIRST, 0);
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.poolSeed(0);
        nft.reveal(SEED);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, 0));
        nft.entryIndexOf(0, 0);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, FIRST + supply));
        nft.entryIndexOf(FIRST + supply, 0);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.PoolOutOfRange.selector, 2));
        nft.entryIndexOf(FIRST, 2);
    }

    // ------------------------------------------------------------------ bind

    function test_bindAllTokens() public {
        _commitReveal();
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            uint256 ei = nft.entryIndexOf(t, 0);
            vm.expectEmit(address(nft));
            emit ITapNetlistNFT.Bound(t, 0, ei);
            vm.expectEmit(address(nft));
            emit IERC4906.MetadataUpdate(t);
            _bind(nft, t, 0);
            _bind(nft, t, 1);
            assertEq(nft.imageHashOf(t), imgValues[ei]);
            assertEq(nft.netlistHashOf(t), netValues[nft.entryIndexOf(t, 1)]);
            assertTrue(nft.knownNetlist(nft.netlistHashOf(t)));
        }
    }

    function test_bindIsIdempotent() public {
        _commitReveal();
        _bind(nft, 5, 1);
        vm.recordLogs();
        _bind(nft, 5, 1);
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_bindWorksForUnmintedToken() public {
        _commitReveal();
        _bind(nft, 7, 0);
        assertTrue(nft.imageHashOf(7) != 0);
    }

    function test_bindReverts() public {
        _commit();
        bytes32[] memory none = new bytes32[](0);
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.bind(FIRST, 0, none, none);
        nft.reveal(SEED);
        (bytes32[] memory v, bytes32[] memory p) = _bindArgs(nft, 3, 1);

        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, 0));
        nft.bind(0, 1, v, p);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.PoolOutOfRange.selector, 9));
        nft.bind(3, 9, v, p);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.bind(3, 1, none, p);
        bytes32[] memory two = new bytes32[](2);
        two[0] = v[0];
        two[1] = v[0];
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.bind(3, 1, two, p);
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        nft.bind(3, 1, new bytes32[](1), p);
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.bind(3, 0, v, p); // netlist values against the image pool
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.bind(4, 1, v, p); // another token's entry
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.bind(3, 1, v, none);
        nft.bind(3, 1, v, p);
        // even after binding, a wrong proof still reverts
        vm.expectRevert(TapNetlistCore.InvalidProof.selector);
        nft.bind(3, 1, v, none);
    }

    function test_bindCombinedPool() public {
        uint256 n = 7;
        bytes32[] memory leaves = new bytes32[](n);
        bytes32[][] memory vals = new bytes32[][](n);
        for (uint256 i; i < n; ++i) {
            vals[i] = new bytes32[](2);
            vals[i][0] = keccak256(abi.encode("i", i));
            vals[i][1] = keccak256(abi.encode("n", i));
            leaves[i] = TapMerkle.leafHash(i, vals[i]);
        }
        TapNetlistNFT c = new TapNetlistNFT("T", "T", "", address(this));
        c.commitManifest(MANIFEST, 100, n, _pool(3, MerkleBuilder.root(leaves)));
        c.reveal(SEED);
        for (uint256 t = 100; t < 100 + n; ++t) {
            uint256 e = c.entryIndexOf(t, 0);
            c.bind(t, 0, vals[e], MerkleBuilder.proof(leaves, e));
            assertEq(c.imageHashOf(t), vals[e][0]);
            assertEq(c.netlistHashOf(t), vals[e][1]);
        }
        vm.expectRevert(TapNetlistCore.InvalidValues.selector);
        c.bind(100, 0, _one(vals[0][0]), new bytes32[](0));
    }

    // ------------------------------------------------------------------ netlist storage

    function test_storeNetlistAfterBind() public {
        _commitReveal();
        bytes32 h = sha256(xorFile);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.UnknownNetlist.selector, h));
        nft.storeNetlist(xorFile);

        uint256 t = _tokenWithNetlist(nft, h);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.NotBound.selector, t));
        nft.netlistOf(t);
        _bind(nft, t, 1);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, h));
        nft.netlistOf(t);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistNotStored.selector, h));
        nft.netlistFile(h);

        vm.recordLogs();
        vm.prank(alice); // permissionless
        assertEq(nft.storeNetlist(xorFile), h);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        assertEq(logs.length, 1);
        assertEq(logs[0].topics[0], ITapNetlistNFT.NetlistStored.selector);
        assertEq(logs[0].topics[1], h);
        (address pointer, uint256 size, uint256 chunks) = nft.netlistPointer(h);
        assertEq(abi.decode(logs[0].data, (address)), pointer);
        assertEq(size, xorFile.length);
        assertEq(chunks, 1);
        assertEq(pointer.code, bytes.concat(hex"00", xorFile));

        assertEq(nft.netlistFile(h), xorFile);
        assertEq(nft.netlistOf(t), xorFile);

        vm.recordLogs();
        assertEq(nft.storeNetlist(xorFile), h); // idempotent
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_storeChunkedNetlist() public {
        _commitReveal();
        bytes32 h = sha256(bigFile);
        uint256 t = _tokenWithNetlist(nft, h);
        _bind(nft, t, 1);
        nft.storeNetlist(bigFile);
        (address pointer, uint256 size, uint256 chunks) = nft.netlistPointer(h);
        assertEq(size, 49150);
        assertEq(chunks, 2);
        assertEq(pointer.code.length, 1 + 2 * 20);
        assertEq(keccak256(nft.netlistOf(t)), keccak256(bigFile));
    }

    function test_storeExactChunkBoundaries() public {
        // 24,575 bytes = one chunk; 24,576 bytes = two chunks; 49,150 = two full chunks.
        bytes[3] memory fs = [Tapnet.chain(3505, 6), Tapnet.chain(3508, 1), Tapnet.chain(7014, 9)];
        uint256[3] memory sizes = [uint256(24575), 24576, 49150];
        uint256[3] memory want = [uint256(1), 2, 2];
        for (uint256 k; k < 3; ++k) {
            bytes memory f = fs[k];
            assertEq(f.length, sizes[k]);
            TapNetlistNFT c = _singleFileCollection(f);
            c.storeNetlist(f);
            (,, uint256 chunks) = c.netlistPointer(sha256(f));
            assertEq(chunks, want[k]);
            assertEq(keccak256(c.netlistOf(1)), keccak256(f));
        }
    }

    /// A file whose hash is bound but whose content is not valid tapnet/1 is refused.
    function test_contentCheckIsMandatory() public {
        bytes memory good = xorFile;
        bytes memory bad = bytes.concat(Tapnet.header(2, 1), hex"02"); // REF
        bytes32[] memory leaves = new bytes32[](2);
        leaves[0] = TapMerkle.leafHash(0, _one(sha256(good)));
        leaves[1] = TapMerkle.leafHash(1, _one(sha256(bad)));
        TapNetlistNFT c = new TapNetlistNFT("C", "C", "", address(this));
        c.commitManifest(MANIFEST, 1, 2, _pool(2, MerkleBuilder.root(leaves)));
        c.reveal(SEED);
        for (uint256 t = 1; t <= 2; ++t) {
            uint256 e = c.entryIndexOf(t, 0);
            c.bind(t, 0, _one(e == 0 ? sha256(good) : sha256(bad)), MerkleBuilder.proof(leaves, e));
        }
        c.storeNetlist(good);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCheck.TapnetBadOpcode.selector, 16, 2));
        c.storeNetlist(bad);
    }

    function _singleFileCollection(bytes memory f) internal returns (TapNetlistNFT c) {
        c = new TapNetlistNFT("T", "T", "", address(this));
        c.commitManifest(MANIFEST, 1, 1, _pool(2, TapMerkle.leafHash(0, _one(sha256(f)))));
        c.reveal(SEED);
        c.bind(1, 0, _one(sha256(f)), new bytes32[](0));
    }

    function test_maxFileSize() public {
        bytes memory f = Tapnet.chain(7016, 6); // 49,152 bytes = MAX_FILE
        assertEq(f.length, 49152);
        TapNetlistNFT c = _singleFileCollection(f);
        assertEq(c.MAX_FILE(), 49152);
        uint256 g = gasleft();
        c.storeNetlist(f);
        uint256 used = g - gasleft();
        emit log_named_uint("storeNetlist 49,152 B (MAX_FILE, 3 chunks)", used);
        assertLt(used, 15_000_000);
        (,, uint256 chunks) = c.netlistPointer(sha256(f));
        assertEq(chunks, 3); // 2 full chunks of 24,575 bytes + 2 bytes
        assertEq(keccak256(c.netlistOf(1)), keccak256(f));

        bytes memory big = Tapnet.chain(7019, 1); // 49,153 bytes
        TapNetlistNFT d = _singleFileCollection(big);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistStore.NetlistTooLarge.selector, 49153));
        d.storeNetlist(big);
    }

    function test_mintEndsAtReveal() public {
        _commit();
        nft.setMinter(minter, true);
        nft.mint(alice, 1);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.mint(alice, 2);
        vm.prank(minter);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.mint(alice, 3);
    }

    function test_labelRules() public {
        ITapNetlistNFT.Pool[] memory ps = _pools();
        ps[1].label = ps[0].label;
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 1));
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _labelled(""));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _labelled("tab\there"));
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _labelled(unicode"网表"));
        bytes memory l65 = new bytes(65);
        for (uint256 i; i < 65; ++i) {
            l65[i] = "A";
        }
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidPool.selector, 0));
        nft.commitManifest(MANIFEST, FIRST, supply, _labelled(string(l65)));
        bytes memory l64 = new bytes(64);
        for (uint256 i; i < 64; ++i) {
            l64[i] = bytes1(uint8(0x20 + i)); // includes space and '~'-range
        }
        nft.commitManifest(MANIFEST, FIRST, supply, _labelled(string(l64)));
    }

    function _labelled(string memory label) internal pure returns (ITapNetlistNFT.Pool[] memory ps) {
        ps = new ITapNetlistNFT.Pool[](1);
        ps[0] = ITapNetlistNFT.Pool(label, 2, bytes32(uint256(1)));
    }

    function test_cannotRenounceByTransfer() public {
        vm.expectRevert(TapNetlistCore.ZeroOwner.selector);
        nft.transferOwnership(address(0));
    }

    // ------------------------------------------------------------------ reveal source "none"

    function test_noRevealIdentityAndImmediateBind() public {
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.ManifestCommitted(MANIFEST);
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.Revealed(nft.NO_REVEAL());
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, ps);
        assertEq(nft.masterSeed(), bytes32(type(uint256).max));
        for (uint256 t = FIRST; t < FIRST + supply; ++t) {
            assertEq(nft.entryIndexOf(t, 0), t - FIRST);
            assertEq(nft.entryIndexOf(t, 1), t - FIRST);
        }
        // bind right after the commit
        uint256 t0 = FIRST + 3;
        nft.bind(t0, 1, _one(netValues[3]), MerkleBuilder.proof(netLeaves, 3));
        nft.bind(t0, 0, _one(imgValues[3]), MerkleBuilder.proof(imgLeaves, 3));
        assertEq(nft.netlistHashOf(t0), netValues[3]);
        vm.expectRevert(TapNetlistCore.NoRevealCollection.selector);
        nft.poolSeed(0);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.PoolOutOfRange.selector, 2));
        nft.entryIndexOf(FIRST, 2);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.TokenOutOfRange.selector, FIRST + supply));
        nft.entryIndexOf(FIRST + supply, 0);
    }

    function test_noRevealRevealPathsRevert() public {
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, _pools());
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.reveal(SEED);
        vm.expectRevert(TapNetlistCore.AlreadyRevealed.selector);
        nft.scheduleBlockhashReveal(block.number + 1);
        vm.expectRevert(abi.encodeWithSelector(TapNetlistCore.InvalidRevealBlock.selector, block.number));
        nft.revealFromBlockhash(block.number);
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.expectRevert(TapNetlistCore.AlreadyCommitted.selector);
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, ps);
        vm.expectRevert(TapNetlistCore.AlreadyCommitted.selector);
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, ps);
    }

    function test_noRevealMintsUntilFreeze() public {
        nft.commitManifestNoReveal(MANIFEST, FIRST, supply, _pools());
        nft.mint(alice, 1); // nothing hidden: minting continues after the commit
        nft.freeze();
        assertTrue(nft.frozen());
        assertEq(nft.masterSeed(), nft.NO_REVEAL());
        uint256 t = FIRST; // entry 0 is the xor file (i % 3 == 0)
        nft.bind(t, 1, _one(netValues[0]), MerkleBuilder.proof(netLeaves, 0));
        nft.storeNetlist(xorFile);
        assertEq(nft.evalOf(t, hex"01"), hex"01");
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, address(this)));
        nft.mint(alice, 2);
    }

    // ------------------------------------------------------------------ freeze

    function test_freeze() public {
        _commit();
        nft.mint(alice, 2);
        nft.reveal(SEED);
        vm.expectEmit(address(nft));
        emit Owned.OwnershipTransferred(address(this), address(0));
        vm.expectEmit(address(nft));
        emit ITapNetlistNFT.Frozen();
        vm.expectEmit(address(nft));
        emit IERC4906.BatchMetadataUpdate(FIRST, FIRST + supply - 1);
        nft.freeze();
        assertTrue(nft.frozen());
        assertEq(nft.owner(), address(0));

        bytes memory unauthorized = abi.encodeWithSelector(Owned.Unauthorized.selector, address(this));
        vm.expectRevert(unauthorized);
        nft.setBaseURI("x");
        vm.expectRevert(unauthorized);
        nft.reveal(keccak256("x"));
        ITapNetlistNFT.Pool[] memory ps = _pools();
        vm.expectRevert(unauthorized);
        nft.commitManifest(MANIFEST, FIRST, supply, ps);
        vm.expectRevert(unauthorized);
        nft.setMinter(alice, true);
        vm.expectRevert(unauthorized);
        nft.mint(alice, 3);
        vm.expectRevert(unauthorized);
        nft.freeze();
        assertEq(nft.tokenURI(2), "ipfs://base/2");

        // binding and storage stay permissionless
        uint256 t = _tokenWithNetlist(nft, sha256(xorFile));
        _bind(nft, t, 1);
        nft.storeNetlist(xorFile);
        assertEq(nft.netlistOf(t), xorFile);
    }

    function test_freezeEndsMinterPowers() public {
        _commitReveal();
        nft.setMinter(minter, true);
        nft.freeze();
        vm.prank(minter);
        vm.expectRevert(TapNetlistNFT.IsFrozen.selector);
        nft.mint(alice, 3);
    }

    function test_freezeReverts() public {
        vm.expectRevert(TapNetlistCore.NotCommitted.selector);
        nft.freeze();
        _commit();
        vm.expectRevert(TapNetlistCore.NotRevealed.selector);
        nft.freeze();
        nft.reveal(SEED);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, alice));
        nft.freeze();
    }

    function test_transferOwnership() public {
        nft.transferOwnership(alice);
        assertEq(nft.owner(), alice);
        vm.expectRevert(abi.encodeWithSelector(Owned.Unauthorized.selector, address(this)));
        nft.transferOwnership(bob);
    }

    // ------------------------------------------------------------------ ERC-721

    function test_erc721Transfers() public {
        _commit();
        nft.mint(alice, 1);
        nft.mint(alice, 2);

        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NotAuthorized.selector, bob, 1));
        vm.prank(bob);
        nft.transferFrom(alice, bob, 1);

        vm.prank(alice);
        nft.approve(bob, 1);
        assertEq(nft.getApproved(1), bob);
        vm.prank(bob);
        nft.transferFrom(alice, bob, 1);
        assertEq(nft.ownerOf(1), bob);
        assertEq(nft.getApproved(1), address(0));

        vm.prank(alice);
        nft.setApprovalForAll(bob, true);
        assertTrue(nft.isApprovedForAll(alice, bob));
        vm.prank(bob);
        nft.approve(minter, 2); // operator may approve
        vm.prank(minter);
        nft.safeTransferFrom(alice, minter, 2);
        assertEq(nft.ownerOf(2), minter);
        assertEq(nft.balanceOf(alice), 0);
    }

    function test_erc721Reverts() public {
        _commit();
        nft.mint(alice, 1);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidOwner.selector, address(0)));
        nft.balanceOf(address(0));
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 2));
        nft.ownerOf(2);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NonexistentToken.selector, 2));
        nft.getApproved(2);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721IncorrectOwner.selector, bob, 1, alice));
        nft.transferFrom(bob, alice, 1);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(0)));
        nft.transferFrom(alice, address(0), 1);
        vm.prank(bob);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721NotAuthorized.selector, bob, 1));
        nft.approve(bob, 1);
    }

    function test_safeTransferReceivers() public {
        _commit();
        nft.mint(alice, 1);
        GoodReceiver good = new GoodReceiver();
        BadReceiver bad = new BadReceiver();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(bad)));
        nft.safeTransferFrom(alice, address(bad), 1);
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(nft)));
        nft.safeTransferFrom(alice, address(nft), 1, "data"); // no onERC721Received
        ShortReceiver short = new ShortReceiver();
        vm.prank(alice);
        vm.expectRevert(abi.encodeWithSelector(ERC721Min.ERC721InvalidReceiver.selector, address(short)));
        nft.safeTransferFrom(alice, address(short), 1); // short return data: clean error (review I-9)
        vm.prank(alice);
        nft.safeTransferFrom(alice, address(good), 1, "data");
        assertEq(nft.ownerOf(1), address(good));
    }
}
