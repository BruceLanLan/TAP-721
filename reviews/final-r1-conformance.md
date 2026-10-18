# Final round r1: does the code match the text?

What was reviewed: `TAPs/TAP-draft-netlist-bound-nft.md` (TAP-721 core §1–§8.2 and the extensions §8.3–§8.6) and `TAPs/TAP-draft-netlist-nft-bridging.md` (MUST level only). These were checked against `contracts/src/core/*`, `contracts/src/tools/*`, `contracts/src/bridge/*` and `assets/tap-netlist-bound-nft/tapnft.py`.

Test runs, on the final tree including the new tests below:
- `forge test`: 24 suites, **194 passed, 0 failed**. This includes `test/audit/AuditPass4.t.sol`, which someone else added while this review was running.
- `python3 -m pytest` in `assets/tap-netlist-bound-nft`: **31 passed**.

New tests are in `contracts/test/audit/AuditFinalR1.t.sol`, 8 tests, all passing. Tests named `*_gap_*` or `*_conflict_*` record what the code does today where it differs from the text. When a fix lands, change their assertions. The Python checks were run inline and not saved. Their results are quoted in rows C16 and C22.

Status key:
- **OK**: implemented and tested.
- **GAP**: missing code or missing test.
- **CONFLICT**: the code and the text disagree, or the text disagrees with itself.
- **N/A**: the duty falls on a tool UI, a network-reading verifier or the publisher. No reference code is expected. These rows are counted separately.

Totals: **OK 66 · GAP 4 · CONFLICT 3 · N/A 13**. By document: core 41/3/3/9, bridging 25/1/0/4.

---

## 1. TAP-721 core and extensions

| # | Requirement (line) | Code | Test | Status |
|---|---|---|---|---|
| C1 | L38/§8.2: L1 implements ITapNetlistNFT + ERC-165 + ERC-4906 and reports `0x282b67f6`, `0x01ffc9a7`, `0x49064906` | `TapNetlistCore.supportsInterface` L522; `TapNetlistNFT` L91 | `TapNetlistNFT.t` test_constructorAndInterfaces; **new** `test_r1_specLiteralIdsAndTopics` (before it, the ids were only compared with `type(X).interfaceId`, which proves nothing) | OK |
| C2 | §2.2 items 1–4: header, non-empty, NAND/LATCH only (no REF), TAP-02 §3 well-formed incl. pin bounds | `TapNetlistCheck.check`; `tapnft.check_file` | CoreVectors test_invalidFilesRejectedLikePython / test_validFilesMatchPython; TapLibraries test_revert*; py `test_invalid_files` | OK |
| C3 | L110: tools MUST NOT produce invalid files | `tapnft.encode_file` wraps any records without checking them (`file_from_chain` does check). Probe: `encode_file(b'',1,1)` returns a file that `check_file` rejects ("no records") | none | GAP (low) |
| C4 | L110: check record lengths before reading; bound records before allocating | `TapNetlistCheck` streams with no allocation; `TapNetlistVM._run` allocates `(len−16)/4`, which the file length bounds; `tap02_reference` | AuditVM fuzz; TapNetlistEval testFuzz_vmRandomBytes / Records | OK |
| C5 | §2.2/§7.3.2: `bytes = 16 + 7·nand + 4·latch` | `check_metadata`, `check_netlist_against_metadata` | py test_netlist_checks, metadata invalid vectors | OK |
| C6 | §3.2 items 1–5: `isCPU`, reads, rebuild, hash, `container == accountOf` | only steps 3–4 (`file_from_chain`); 1, 2 and 5 need the network and have no reference verifier | py test_chain_circuits (steps 3–4) | N/A |
| C7 | §4.1: CAIP-19 form, lowercase address, no leading zeros | `TOKEN_ID` regex (tapnft L264) | metadata invalid vectors | OK |
| C8 | §4.1: multi-chain tools MUST NOT use the bare token id | UI | — | N/A |
| C9 | §4.2: check the SHA-256 of fetched bytes | `check_netlist_against_metadata`, `check_token_set` | py netlistChecks, tokenSets errors | OK |
| C10 | §5.1: a revealing or L1 collection MUST publish a manifest | `_reveal` / `scheduleBlockhashReveal` revert `NotCommitted` | test_revealReverts, test_scheduleReverts | OK |
| C11 | §5.1: 1 ≤ n ≤ 2^32 | `check_manifest`; `_commitManifest` (supply ≥ 1; `MAX_TOKENS` = 100,000, a stricter implementation limit) | test_commitReverts; manifest invalid vectors | OK (limit not mentioned in the text) |
| C12 | §5.1/§5.2/§7.1: tools MUST ignore unknown members | checkers never reject extra keys | implicit (no dedicated vector) | OK |
| C13 | §5.1: range mode or set mode, never both | `check_manifest` L466 | manifest invalid vectors | OK |
| C14 | §5.2: label 1–64 printable ASCII, unique | `_validLabel`, `_commitManifest` L161; `check_manifest` | test_labelRules; test_audit_duplicateLabelsRejected; py | OK |
| C15 | §5.2: entries exactly n; values and roots MUST NOT be zero | Python checks all. On chain, root ≠ 0 is checked and `bind` rejects a zero value, but **`loadPool` accepts a zero value**, and that token then answers zero forever | **new** `test_r1_gap_loadPoolAcceptsZeroValue` | GAP (low) |
| C16 | §5.2 L211: "a manifest has one pool (both fields) or two pools (one field each)". §7.1 revealed metadata needs both `image` and `netlist` | `check_manifest` and `_commitManifest` both **accept a manifest whose only pool is `["image"]`** (or `["netlist"]`). Such tokens can never reach a valid `revealed` state | **new** `test_r1_gap_imageOnlyManifestAccepted`; Python probe: "image-only manifest: ACCEPTED" | CONFLICT |
| C17 | §5.2: every netlist hash belongs to a valid file | cannot be checked offline (docstring says so); enforced on chain at `storeNetlist` | — | N/A |
| C18 | §5.3: leaf, node, tree, proof, `verify` | `TapMerkle`; `tapnft.merkle_*`; the frontier accumulator `_accumulate` / `_finishLoad` | CoreVectors test_merkleMatchesPython; TapLibraries; TapPoolLoad | OK |
| C19 | §5.4: ids ascending and < 2^32; length 4·count; hash; tools MUST reject otherwise | `check_token_set`; `_loadSetChunk` (takes `uint32[]`, checks ascending order and hash) | TapTokenSet test_loadReverts / test_pythonCrossCheck7000; py tokenSets errors | OK |
| C20 | §5.4/§6.1.3: token set fixed before the seed | `commitManifestTokenSet` commits the hash before any reveal | TapTokenSet | OK |
| C21 | §5.4: tokens outside the set MUST NOT carry `tap.image` / `tap.netlist` | `check_metadata(outside_token_set=True)` | py test_placeholders | OK |
| C22 | §5.4 says an outside-set token "MAY carry a placeholder ERC-721 `image`", which implies it may be absent. §7.1 says metadata MUST contain `image`. §7.2's "placeholder `image` member … MUST be absent for a token outside the token set" does not say whether it means `tap.image` or the ERC-721 `image` | Python follows §7.1: probe "outside-set w/o ERC-721 image: REJECTED" | py test_placeholders | CONFLICT (inside the text) |
| C23 | §5.4/§8.2.2: an uncovered token returns zero hashes forever and `entryIndexOf` reverts | `_tryIndexOf`, `indexOf`, `_loadedField` | TapTokenSet test_smallSetBindLoadMint | OK |
| C24 | §5.4: don't display an outside-set token as awaiting reveal | UI | — | N/A |
| C25 | §6.1: reject `vrf` | `check_manifest` L479 | manifest invalid vectors | OK |
| C26 | §6.1.1: L1 commit comes before the seed | `_reveal` requires the commit; a block-hash reveal must be scheduled for a future block. The owner's `reveal(seed)` for drand cannot be proven on chain | test_revealReverts, test_blockhashReveal | OK (trust boundary, as the text allows) |
| C27 | §6.1.2: one seed only; no second manifest | `AlreadyRevealed`, `AlreadyCommitted`, `RevealIsScheduled` | test_revealReverts; test_audit_blockhashRevealCannotBeRerolled; test_blockhashRevealMissedWindowIsFinal | OK |
| C28 | §6.1.3: inputs fixed by the manifest | publisher | — | N/A |
| C29 | §6.1.7: drand `randomness = SHA-256(signature)`, two relays | no reference helper (network) | — | N/A |
| C30 | §6.1.8: L1 MUST NOT record 0 or all-ones as a random seed | `_reveal` L538 | test_revealRejectsSentinel, test_blockhashNeverYieldsSentinel, test_audit_revealWithNoRevealSentinelReverts | OK |
| C31 | §6.2/§6.3: pool seed and permutation | `TapPermutation`; `tapnft.pool_seed` / `permute` | CoreVectors test_permuteMatchesPython / test_poolSeedMatchesPython; TapLibraries bijection; py | OK |
| C32 | §6.4: editions (counting); MUST NOT renumber (publisher) | `check_editions` | py test_editions | OK |
| C33 | §7.1: `name`, `image`, `tap` and member types | `check_metadata`, `_check_optional` | metadata vectors | OK |
| C34 | §7.2: unrevealed means `netlist` absent and `manifest` present | `check_metadata` L371 | metadata invalid vectors | OK |
| C35 | §7.3.3: revealed values equal the pool entries; an indexer MUST check editions | `assignment`, `check_editions` | py test_collection, test_editions (§7.3.1 image bytes: network) | OK |
| C36 | §7.4: minimum token check | `check_metadata` + `check_netlist_against_metadata` (displaying the level is UI) | py test_netlist_checks | OK |
| C37 | §7.5 items 1–2: derive the container from `name`; check files against `tap.*.sha256` | no reference tool (network) | — | N/A |
| C38 | §8.1: label "L0 (metadata only)" | UI | — | N/A |
| C39 | §8.2.1: manifest, seed, pools and range never change once set | single-shot setters; `transferOwnership(0)` forbidden | test_commitReverts, test_revealReverts, test_audit_renounceOnlyThroughFreeze | OK |
| C40 | §8.2.2: `entryIndexOf` returns, reverts, sets the `none` sentinel | `entryIndexOf` L241, `_setNoReveal` | test_entryIndexOfReverts, test_noRevealIdentityAndImmediateBind, TapTokenSet test_noRevealSetUsesRanks | OK |
| C41 | §8.2.3: `bind` (any caller, proof at the entry index, idempotent); whole-pool record checks the root | `bind` L390; `loadPool` / `loadPoolChunk` | test_bindIsIdempotent, test_bindReverts, test_bindCombinedPool; TapPoolLoad | OK |
| C42a | §8.2.4: a hash is known "when it is a value of a netlist field of a pool recorded under item 3" | `knownNetlist` is only `_known`, which only `bind` and `markKnown(tokenId)` set. `markKnown` needs the seed. So after `loadPool`, `storeNetlist` reverts `UnknownNetlist` until a token-specific extra call that the text never mentions, and before the reveal there is no path at all | TapPoolLoad test_loadPool (asserts the revert); **new** `test_r1_conflict_loadedPoolValueNotKnown` | CONFLICT |
| C42b | §8.2.4: ≤ 49,152 bytes; validity MUST be checked when Eval is implemented | `TapNetlistStore.storeNetlist` L39; `_beforeStoreNetlist` is fixed in Core | test_maxFileSize, test_contentCheckIsMandatory, test_audit_maxFileFitsTxGasCap | OK |
| C43 | §8.2.5: `frozen()` semantics, monotonic | `TapNetlistNFT.freeze` (needs commit and seed; clears the owner) | test_freeze, test_freezeEndsMinterPowers, test_freezeReverts | OK |
| C44 | §8.2.6: emit ERC-4906 on "commit, reveal, bind, recording a pool or a token set, freeze" | reveal, bind, freeze and `setBaseURI` emit. **`_commitManifest` emits only `ManifestCommitted`**, except on the no-reveal path. Pool and token-set loads emit only after the reveal, which is acceptable because nothing a token returns changes before then | **new** `test_r1_gap_commitEmitsNoMetadataUpdate`; TapPoolLoad test_loadAfterRevealEmitsBatchUpdate | GAP |
| C45 | §8.2: L1 `tokenURI` values equal the interface | off-chain content | — | N/A |
| C46 | §8.2/§8.5: set-mode L1 MUST implement TokenSet | Core always reports `0x3f7177c7` | TapTokenSet test_rangeModeGetters, test_companionSet | OK |
| C47 | §8.2 bridged copies: hashes are zero only while unknown | `TapMirror` keeps hashes after the burn | TapBridge test_mirror_materialize_and_netlistOf | OK |
| C48 | §8.3: every companion implements ITapCompanion `0x12b40a6c` | `TapCompanion.supportsInterface` | test_basics; new literal test | OK |
| C49 | §8.3: `endorse` rules (owner at call time, first call recorded, later calls no-op) | `TapCompanion.endorse` | test_endorseThroughContainer, test_endorseWithoutOwnerGetterReverts | OK |
| C50 | §8.3: companion `frozen()` conditions, MUST latch, permissionless latch | `announceFrozen`, `_frozenLatched` | test_sealThenLegacyFreeze, test_legacyFreezeThenSeal, test_frozenRequiresEndorsement, test_audit_companionFrozenNeverReverts | OK |
| C51 | §8.4.1: one beat equals TAP-02, packing | `TapNetlistVM` | CoreVectors (17851 / 3151 / 17852), AuditVM fuzz vs reference | OK |
| C52 | §8.4.2: `evalOf` / `evalFile` revert on LATCH | VM `allowLatch=false` | test_evalOfLatchReverts | OK |
| C53 | §8.4.3: revert when not stored, or no hash for the token | `netlistFile`, `_boundNetlist` | test_notBoundOrNotStoredReverts | OK |
| C54 | §8.5: `tokenRange()=(0,count)`, `tokenSetHash`, `entryIndexOf` reverts until recorded; range-mode getters | `tokenAt`, `indexOf`, `_tryIndexOf` | TapTokenSet test_loadReverts, test_rangeModeGetters | OK |
| C55 | §8.6 (SHOULD): lock contract; content check | `TapContainerLock` (opener check, `locked()`) | fork/ContainerLock.t.sol; AuditPass4 | OK |

**Behaviour the text does not mention but that matters for interop** (not counted above):
- `markKnown(tokenId)` must be called before `storeNetlist` on loaded pools. This is the substance of C42a.
- Implementation-defined entry points that clients will see: `commitManifestNoReveal`, `commitManifestTokenSet`, `loadTokenSet[Chunk]`, `loadPool[Chunk]`, `scheduleBlockhashReveal` / `revealFromBlockhash` (bounded by `MAX_REVEAL_DELAY` = 1,000,000), `poolSeed(i)`, and the limit `MAX_TOKENS` = 100,000. The Reference Implementation section should name them.
- Minting ends at a random reveal (`TapNetlistNFT.mint` L65). This is stricter than the SHOULD in §6.1 item 4, which is fine.

## 2. Bridging TAP (MUSTs)

| # | Requirement | Code | Test | Status |
|---|---|---|---|---|
| B1 | §3: same `collectionKey` / `homeChainId`; reject a foreign key | `TapBridgeEndpoint` ctor; `receivePayload` L236 | test_collectionKeys (vector incl. `0x8755cf60…`); test_wrongSource_wrongDestination_wrongCollection | OK |
| B2 | §4.1: strict 320-byte decode, `BadPayload` | `TapBridgePayload.decode` | TapBridgeVectors | OK |
| B3 | §4.2: gateway fills hashes from the data source | `TapGateway._hashesOf` | test_gateway_bindFirstAfterReveal_andEscrowFlag | OK |
| B4 | §4.2: `NotBound` after the reveal for covered tokens, using range or set coverage; fails closed while the set is unrecorded | `_depart` L63, `_covered` | test_gateway_bindFirstAfterReveal…; AuditPass3 test_audit_gatewaySetModeUsesWrongRange; AuditFixes | OK |
| B5 | §4.2: mirror sends the values it holds | `TapMirror._depart` | test_roundTrip_home_remote_home | OK |
| B6 | §4.2: gateway ignores arriving hashes | `TapGateway._arrive` | round-trip tests (implicit) | OK |
| B7 | §5.1: `setRoute` validation | `setRoute` | test_routeValidation | OK |
| B8 | §5.1: `sealRoutes` needs an open route and all adapters sealed | `sealRoutes` | test_sealedRoutes; AuditBridge | OK |
| B9 | §5.1: departure checks 1–5 in order | `bridge` L155 | test_zeroRecipient_andClosedRoute, test_contractRecipient_needsAcknowledgement, AuditBridge test_audit_recipientIs*, test_fees_quote_refund_insufficient | OK |
| B10 | §5.1: arrival checks 1–6 in order; ALL uses the current list | `receivePayload` | test_wrongAdapter_rejected, test_lz_wrongPeer_rejected, test_lz_replay_rejected, test_all_* | OK |
| B11 | §5.1: `resend` requires `departed`; payload unchanged | `resend` | test_all_stuckAdapter_recoveredByResendBeforeSeal | OK |
| B12 | §5.2: gateway ctor rejects a data source whose `collection()` ≠ home | `TapGateway` ctor | TapBridge (WrongDataSource) | OK |
| B13 | §5.2: departure reverts `AlreadyEscrowed`; MUST revert unless `ownerOf` is then the gateway; records location | `_depart` L53–59 | AlreadyEscrowed: TapBridgeVectors / AuditBridge. **`EscrowFailed` has no test** | GAP (test) |
| B14 | §5.2: arrival `NotEscrowed` / `NotOnRoute`; MUST NOT use `safeTransferFrom` | `_arrive` | test_doubleMint_and_notEscrowed_guards; test_gateway_perRouteAccounting | OK |
| B15 | §5.2: gateway MUST NOT implement `onERC721Received` | (absent) | **new** `test_r1_gatewayRejectsSafeTransfer` | OK |
| B16 | §5.2: client checks gateway identity; reachable mirror only | client | — | N/A |
| B17 | §5.3: set-mode mirror MUST deploy with `supply = 0` | deployment (ctor cannot check) | — | N/A |
| B18 | §5.3: arrival `AlreadyLive`, `OutOfRange`, `ManifestConflict`; stores hashes; mints without callback; emits 4906 | `TapMirror._arrive` | test_doubleMint…, test_mirror_manifestConflict_and_range, test_mirror_emitsERC4906_onArrival | OK |
| B19 | §5.3: `storeNetlist` / `materialize`: known, ≤ 49,152 bytes, valid | `TapNetlistStore` + `TapMirror._beforeStoreNetlist` | test_mirror_materialize_and_netlistOf, test_mirror_badFile_rejected, test_mirror_largeNetlist_chunked | OK |
| B20 | §5.3: mirror `tokenURI` document byte-identical to home | deployment / content | — | N/A |
| B21 | §5.3: `entryIndexOf` / `bind` revert `NotHomeCollection` (`0xbbfa1ada`) | `TapMirror` L129–135 | test_mirror_interfaces_and_emptyRevealSurface; new literal test | OK |
| B22 | §5.3: mirror on a non-home chain | ctor `SameChain` | **new** `test_r1_mirrorOnHomeChainReverts` | OK |
| B23 | §7: no fallback from ALL | no code path | test_all_hubAlone_doesNotMint_thenLzCompletes | OK |
| B24 | §8.2: adapter passes the configured remote endpoint; reverts if none | `TapAdapterBase._deliver` | test_lz_wrongPeer_rejected | OK |
| B25 | §8.3: `adapterSealed` semantics; LZ not sealed on defaults | `seal`, `_onSeal` | test_lz_sealRequiresPinnedConfig; AuditPass3 test_audit_lzSealAcceptsNilDvnConfig; AuditBridge test_audit_adapterDelegateChangeableAfterSeal | OK (see P2-3) |
| B26 | §9: `setPeer` once per chain, eid and slot | `setPeer` | test_lz_peersSetOnce_andOnlyEndpointSends | OK |
| B27 | §9: `lzReceive` checks caller, value 0, peer | `lzReceive` | TapBridge (NotLzEndpoint, ValueNotAccepted, WrongPeer) | OK |
| B28 | §9: seal sets the delegate to zero | `_onSeal` | test_lz_sealRequiresPinnedConfig | OK |
| B29 | §9: `seal` `NotPinned` conditions | `_onSeal` | test_lz_sealRequiresPinnedConfig; AuditPass3 | OK |
| B30 | §9: delegate MUST pin libraries before seal | operator duty (the seal enforces it) | — | N/A |

## 3. Prioritized fixes

### P1-1 (C42a, CONFLICT): loaded-pool hashes are not "known"

Fix the text. Scanning a pool for a hash with no token in hand is infeasible on chain. Replace §8.2 item 4, first sentence, with:

> A netlist hash is known when `bind` has recorded it; when, after `masterSeed()` is set, it is the netlist value that a pool recorded under item 3 assigns to some token and an implementation-defined permissionless call naming that token has marked it (the reference implementation's `markKnown(uint256 tokenId)`); or when it arrived with a token under a bridging TAP.

Then add `markKnown`, `loadPool` / `loadPoolChunk` and `loadTokenSet` / `loadTokenSetChunk` to the Reference Implementation section.

Alternative: change the code so a pool can be marked known without a reveal, for example `markKnownEntry(poolIndex, entry)` reading `loadedValue`. That is O(1), has no seed dependency, and could be called from `markKnown`. If you do this, change the text to "…when it is the value at some entry of a netlist field of a pool recorded under item 3 and has been marked by a permissionless call naming that entry".

### P1-2 (C44, GAP): no ERC-4906 event on commit

Change the code. In `TapNetlistCore`, emit the update from each `commit*` wrapper after the commit is fully recorded:
- `commitManifest`: call `_emitAllMetadataUpdate();` after `_commitManifest(...)`.
- `commitManifestTokenSet`: call `_emitAllMetadataUpdate();` after `_tokenSetHash = tokenSetHash_;`. This order matters, so that the event covers `0 … 2^256 − 1`. Skip the call when `noReveal` is set, because `_setNoReveal` already emits.
- `commitManifestNoReveal`: no change, because `_setNoReveal` already emits. Flip `test_r1_gap_commitEmitsNoMetadataUpdate` and `TapNetlistNFT.t` test_commitManifest to `expectEmit` it.

Alternative, text only: drop "commit" from the list in §8.2 item 6, because before the reveal a revealing collection's `tokenURI` content is set by the base URI, which already emits.

### P1-3 (C16, CONFLICT): a manifest with only one field is accepted

Both implementations clearly mean to allow this. About eight existing tests commit a single netlist-only pool (`fields = 2`), for example TapNetlistEval L68, TapPoolLoad L157, TapTokenSet L32, TapNetlistNFT L40/L578, AuditCore L137, AuditPass4 L49 and CoreGas L143. So the text is what lags behind.

- **Text (recommended).** Replace §5.2 L211 "Each field appears in at most one pool, so a manifest has one pool (both fields) or two pools (one field each)." with:

  > Each field appears in at most one pool, so a manifest has one pool or two. A field that no pool carries is not assigned by the reveal: the collection fixes it in the token metadata, and §7.3 item 3 does not apply to it.

  In §7.3 item 3, write "…equal the values of the pool entries the token receives under §6 for every field that a pool carries…". No code change is needed.
- **Code (alternative).** Require both fields. Add `_req(used == {"image","netlist"}, ...)` in `check_manifest` and `if (seen != 3) revert InvalidManifest();` in `_commitManifest`, plus an invalid vector, and rewrite every test listed above to use two pools.

### P2-1 (C22, CONFLICT inside the text): placeholder `image`

Replace in §7.2:

> A placeholder `image` member MAY be present for a token awaiting a reveal and MUST be absent for a token outside the token set

with:

> A placeholder `tap.image` MAY be present for a token awaiting a reveal and MUST be absent for a token outside the token set

In §7.1, make the ERC-721 `image` "MUST … except for a token outside the token set (§5.4), where it MAY be omitted". Or keep §7.1 strict and change §5.4 to "carries a placeholder ERC-721 `image`". Either way, Python already rejects a missing ERC-721 `image`. If the first option is chosen, relax `check_metadata` L349 when `outside_token_set=True`.

### P2-2 (C15, GAP): `loadPool` stores zero values

In `_accumulate` or `_storePages`, reject a zero word, for example in the leaf loop add `if iszero(calldataload(...)) { revert }`, or check in Solidity before `_accumulate`. A spec-valid manifest never has zeros, so the effect is only consistency with `bind`. Flip `test_r1_gap_loadPoolAcceptsZeroValue`.

### P2-3 (interop, bridging §8.3): renouncing an adapter without sealing

`TapAdapterBase.transferOwnership(address(0))` renounces without sealing. Its docstring says "or renounce (address 0)", so this is deliberate: the review disagrees with the design, not with an oversight. `adapterSealed()` then stays false forever, so the endpoint can never `sealRoutes`, and the LayerZero delegate stays set. Mirror what the core does: add `if (newOwner == address(0)) revert NotOwner();` (or a new `ZeroOwner()` error) so that `seal()` is the only way to renounce. Flip `test_r1_gap_adapterRenounceWithoutSeal`.

### P2-4 (interop, bridging §4.2): partly bound tokens depart without their netlist

The gateway reverts `NotBound` only when **both** hashes are zero. In a two-pool collection, a token bound only in the image pool departs with `netlistHash = 0`, and the mirror can never serve its netlist. Proposed text:

> …and MUST revert (`NotBound`) if … the token is covered, and `netlistHashOf(tokenId)` is zero while the data source has a pool with the netlist field, or `imageHashOf(tokenId)` is zero while it has a pool with the image field.

Code: in `_depart`, check each field against the data source's `pools()` masks.

### P3-1 (B13, GAP test): `EscrowFailed` is untested

Add a mock ERC-721 whose `transferFrom` is a no-op, then `vm.expectRevert(abi.encodeWithSelector(TapGateway.EscrowFailed.selector, id))`.

### P3-2 (C3, GAP low): `encode_file` can produce invalid files

Rename `tapnft.encode_file` to `_encode_unchecked`, or have it call `check_file` before returning. `make_vectors.py` builds invalid files on purpose, so it should keep an unchecked private helper.

### P3-3 (N/A rows): network-only checks

The reference library covers none of the network-only tool MUSTs: §3.2 steps 1, 2 and 5, the publication block in §5.1, drand in §6.1.7, and §7.5. One sentence in Reference Implementation, such as "network checks of §3.2, §5.1, §6.1 item 7 and §7.5 are not implemented by the reference library", would prevent over-reading. A pure helper `check_drand_beacon(randomness, signature)` (randomness = SHA-256(signature)) would be cheap to add.
