# Security review: tap-drafts reference contracts

Date: 2026-10-18. Scope: `contracts/src/` (`core/`, `bridge/`, `tools/`, `vendor/`, `interfaces/`) at the working tree of `main` (dc3d0dd, plus the untracked `tap-drafts/` folder). Specs used: `DESIGN.md`, `TAPs/TAP-draft-netlist-bound-nft.md` (§2, §5 to §8), `TAPs/TAP-draft-netlist-nft-bridging.md`, and TAP-02.

## Fourth pass (re-review of P3 fixes, 2026-10-18 UTC)

Scope: only what changed since the third pass: the P3-1, P3-2 and P3-3 fixes and the TapContainerLock opener check.

- **Tests:** `forge test` passes 185/185: 182 from the coordinator plus 3 new tests in `test/audit/AuditPass4.t.sol`.

| Finding | Status | What changed / what was checked | Test |
|---|---|---|---|
| P3-1 Gateway `NotBound` in set mode | Fixed | `_covered` probes ERC-165 for ITapNetlistTokenSet (Core reports it). When `tokenSetHash() != 0`, it reverts `NotBound` until `tokenAt(0)` succeeds (fail closed), then uses `try indexOf`. Range mode and data sources without the interface fall back to `tokenRange()`. The rule still applies only after the reveal and only when both hashes are zero, so a member whose pool is loaded departs with the loaded hashes. Making `indexOf` run out of gas inside the `try` leaves only 1/64 of the gas for the rest of `bridge` (adapter send and storage writes), so it cannot be used to skip the rule. The caller is in any case the holder or an approved account | `test_audit_gatewaySetModeUsesWrongRange` (now a regression test), `test_audit_gatewaySetModeLoadedPoolDepartsWithHashes` |
| P3-2 LZ seal accepts NIL values | Fixed | `_onSeal` rejects confirmations of 0 or `type(uint64).max`, `requiredDVNCount` of 0 or 255, and `requiredDVNs.length != requiredDVNCount`. Residual (Info): the optional DVN fields are not checked. An app `optionalDVNCount` of 0 makes ULN302 use the library owner's default optional DVNs and threshold. Required DVNs must still all verify, so this cannot forge a message, but the library owner can add optional DVNs that never verify and so block delivery. Optionally require `optionalDVNCount` to be 255 (NIL) or an explicit non-zero value | `test_audit_lzSealAcceptsNilDvnConfig` (now a regression test) |
| P3-3 Large sets, knownNetlist scan | Fixed, but see P4-1 | `MAX_TOKENS = 100,000` applies to `_commitManifest`, so it covers range mode, set mode and pools. Measured for a 100,000-id set: the completing chunk uses 5.58M gas and the largest chunk 14.5M (the measurement includes test-harness ABI encoding), both below 16,777,216. `indexOf` costs about 44k gas. `knownNetlist` is now an O(1) mapping read. `markKnown(tokenId)` records `netlistHashOf(tokenId)`: the bound value, or the loaded-pool value once revealed and covered; otherwise it reverts `NotBound`. It can only mark hashes committed in the manifest. It is idempotent, so front-running it or calling it repeatedly gains nothing, and the caller pays. `storeNetlist` still re-hashes the file and runs the full check. Bound and loaded values for a token are proven against the same root at the same entry, and the netlist field lives in a single pool, so `bind`, `loadPool` and `markKnown` cannot disagree. Behaviour change: storing a loaded-only hash now needs `markKnown` first; document this for tools. Info: the cap also limits range-mode collections, for example a legacy collection with more than 100k ids cannot use a companion | `test_audit_maxTokenSetLoadFitsTxCap`, `TapPoolLoad.t.sol` `markKnown` tests, `TapNetlistNFT.t.sol` cap test |
| I-8 Lock opener check | Fixed, with a residual (Info) | The constructor requires `opener.accountOf(processor, circuitId) == container`. The opener is chosen by the deployer and is not stored, so a lock deployed with a fake opener passes, and an observer cannot tell which opener was used. Store `opener` as an immutable, or hard-code the canonical opener per chain, and keep the tool-side `accountOf` check | `test_audit_lockOpenerIsCallerChosen` |

**New finding (fourth pass)**

**P4-1 (Low, liveness): token-set chunks cannot go through a standard mempool.**
- Location: `TapNetlistCore.loadTokenSet` and `loadTokenSetChunk` (`uint32[] calldata ids`).
- ABI encoding pads each `uint32` to 32 bytes. Every chunk except the last must hold a multiple of `IDS_PER_PAGE` (6,143) ids, so the smallest such chunk is 196,676 bytes of calldata.
- Geth-derived transaction pools, including BSC and OP-stack nodes, reject transactions larger than 128 KiB (131,072 bytes). A one-call load of the 7,000-id TapeCode-Test1 set is about 224 KB.
- So any set above about 4,090 ids can be loaded only by sending the transaction straight to a block builder or sequencer. The calldata blow-up is also why one chunk uses about 14.5M gas, close to the 16.7M cap.
- Pool chunks are not affected: 767 × 32 bytes is about 24.5 KB.
- Fix: take the ids as `bytes` of packed u32be values. That is 4 bytes per id, 24,572 bytes per page, and the same bytes as the hash preimage. Alternatively, let a chunk hold less than one page, for example by staging partial pages.

## Third pass (2026-10-18 02:20 UTC)

Scope: the new token-set mode, pool loading, the linked TapNetlistVM library, the gateway's per-route accounting, the N-1/N-2/N-3 fixes, and the LayerZero seal pinning.

- **Tests:** `forge test` passes 180/180 in one run: 178 from the coordinator plus 2 new third-pass tests in `test/audit/AuditPass3.t.sol`.
- **Python cross-check:** `test_pythonCrossCheck7000` reproduces `core-tokenset.json` (ranks, `tokenAt`, entries, and the excluded ids 0 and 10001).
- **Slither:** still not installed.

**Status of the second-pass findings**

| Finding | Status | What changed | Test |
|---|---|---|---|
| N-1 `reveal(NO_REVEAL)` | Fixed | `_reveal` rejects a seed equal to 0 or to `NO_REVEAL`. This also covers a block hash equal to `NO_REVEAL` | `test_audit_revealWithNoRevealSentinelReverts` |
| N-2 `NotBound` strands out-of-range ids | Fixed in range mode, regressed in set mode | The exemption uses `dataSource.tokenRange()`, but in set mode that returns `(0, count)`. See P3-1 | `test_audit_gatewayNotBoundStrandsTokensOutsideManifestRange` |
| N-3 Adapter seal does not prove the config is pinned | Mostly fixed | `_onSeal` requires, for every eid: a pinned send library and receive library, no receive-library timeout still open, and a non-zero app ULN confirmations and required-DVN count. It still accepts ULN302's NIL values. See P3-2 | `TapBridge.t.sol` NotPinned tests, `test_audit_adapterDelegateChangeableAfterSeal` |
| I-1 No per-chain accounting at the gateway | Fixed | Mirrors may now route only to the home chain (hub and spoke, `setRoute` rejects anything else). The gateway records `locationOf[id]` and releases a token only to the chain it departed to (`NotOnRoute`). A compromised route can now drain only the tokens on its own chain | existing bridge tests |
| I-8 Lock not bound to its container | Fixed (re-checked) | Constructor checks `opener.accountOf(processor, circuitId) == container` | fork tests |

**New findings (third pass)**

**P3-1 (Low): the gateway's `NotBound` exemption reads the wrong range in token-set mode.**
- Location: `src/bridge/TapGateway.sol:62-65`.
- When the data source uses set mode, `tokenRange()` returns `(0, count)`, so the check `tokenId - first < supply` tests the id against the count, not against set membership. Two effects:
  - A real token that is not in the set but has an id below `count` is treated as bindable. It can never be bound (`NotInTokenSet`), so the gateway reverts `NotBound` and the token can never be bridged.
  - A set member with an id at or above `count` departs unbound, carrying zero hashes. That is the I-2 problem the rule was meant to prevent.
- For a TapeCode-Test1-shaped set (7,000 of ids 1–10,000), ids 1–6,999 that are not in the set are stranded, and set members 7,000–10,000 skip the rule.
- PoC: `AuditPass3CoreTest.test_audit_gatewaySetModeUsesWrongRange`.
- Fix: decide membership with the data source's own rank function. Probe `supportsInterface(type(ITapNetlistTokenSet).interfaceId)`; if it is supported, `try indexOf(tokenId)` and apply `NotBound` only when the call succeeds. Otherwise fall back to `tokenRange()`. If the token set is not loaded yet, refuse the departure, or treat the token as covered.

**P3-2 (Low): LayerZero `seal()` accepts ULN302's NIL values.**
- Location: `src/bridge/LayerZeroV2Adapter.sol:74-80`.
- In ULN302 config, `requiredDVNCount = 255` means "no required DVNs", and `confirmations = type(uint64).max` means "zero confirmations". Both pass the `!= 0` checks.
- With no required DVNs, verification falls to the optional DVNs. When the optional fields are 0, those are the defaults of the library owner, which is exactly the dependency the seal is meant to remove. Zero confirmations also contradicts the bridging draft's finality requirement.
- PoC: `AuditPass3BridgeTest.test_audit_lzSealAcceptsNilDvnConfig`.
- Fix: require `requiredDVNCount != 0 && requiredDVNCount != 255`, `requiredDVNs.length == requiredDVNCount`, and `confirmations != type(uint64).max`. Optionally also require `optionalDVNCount != 0` whenever `optionalDVNThreshold != 0`, or require it to be explicitly NIL. Consider a minimum number of confirmations per remote chain.

**P3-3 (Low): token-set loading cannot finish for large sets; the knownNetlist scan grows with pool size.**
- Location: `TapNetlistCore._loadSetChunk` (final step) and `knownNetlist`.
- Token-set loading:
  - The chunk that completes the set copies all `4·count` bytes into memory and hashes them in one transaction. Memory cost grows quadratically: 3·w + w²/512 gas for w words.
  - Within a 16.7M-gas transaction (TAP-02 quotes this cap for BNB Smart Chain), after one page deploy of about 4.9M gas, only about 11M gas is left for memory. That means about 70k words, roughly 550,000 ids. This is computed, not measured.
  - `commitManifestTokenSet` accepts up to 2^32 ids. A larger set can never be loaded, so `entryIndexOf`, `bind` and `mint` never work for that collection.
- knownNetlist scan:
  - `knownNetlist` scans every page of a loaded netlist pool when the hash was not bound. That costs about 25k gas per 767-entry page (an estimate): about 0.35M gas for 10,000 entries, but more than 16.7M for pools above about 500k entries.
  - `storeNetlist` of a hash known only through a loaded pool then becomes impossible; binding first still works.
  - These costs fall on the caller only, so nobody can grief someone else.
- Fix:
  - Cap `count` in set mode, for example at 2^19, and document the cap.
  - Or commit the set with an incremental hash (a keccak chain over the pages, or a Merkle root) so the final check needs no memory proportional to the whole set.
  - For pools, add `markKnown(tokenId)`, which records `netlistHashOf(tokenId)` in `_known` in O(1), or keep a mapping filled while pages are loaded.

**Info (third pass)**
- **EIP-170 margin:** TapNetlistNFT's runtime is 24,231 bytes, against the 24,576-byte limit: 345 bytes of margin. Any addition, or a different optimizer or `via_ir` setting, can push it over. TapCompanion is 21,431 bytes and TapMirror 21,345. All initcode is far below the EIP-3860 limit. Add a CI size check.
- **Linked TapNetlistVM:**
  - `eval` and `step` are `public pure` and the library has no storage or `selfdestruct`. Calling it directly therefore has no effect.
  - The collection reaches it with DELEGATECALL, so the linked address has full write access to the collection's storage. The deployment must link the canonical library: deploy it with CREATE2 at a documented address and code hash, and verify the linked address in the deployed bytecode.
  - A missing library makes the empty return data fail to decode, so `evalOf` reverts instead of returning garbage.
- **Set mode before loading:** `freeze()` does not require the token set to be loaded. Until someone loads it, `entryIndexOf`, `bind` and `mint` revert. Loading is permissionless, the file is public, and its hash was committed before the seed, so this is liveness only.
- **Chunked loads:** sessions are per caller and per pool, so a third party cannot disturb or front-run another loader. A wrong final hash or root resets only the caller's own session. Their deployed pages are wasted at their own cost. Loads that are already complete return early.
- **Pool accumulator:** the binary-counter fold reproduces the draft's tree, where an odd node moves up unchanged (checked by hand for n = 1, 3, 5, 6, 7 and by the existing `testFuzz_chunkedMatchesSingle`). Leaf and node preimages match TapMerkle. Page sizes (767 × 32 and 383 × 64 bytes) and `IDS_PER_PAGE · 4 = 24,572` fit CHUNK_SIZE.
- **Rank and binary search:** the search is correct on the half-open interval `[lo, hi)`. Ids must be strictly ascending, checked across chunk boundaries through `ss.next`, and `uint32` calldata bounds every id below 2^32.
- **Mirror token range in set mode:** a mirror deployed with `(first, supply)` copied from a set-mode home, which reports `(0, count)`, would reject set ids at or above `count` (`OutOfRange`). Deploy set-mode mirrors with `supply = 0`, and document this in the bridging draft (§5.3).

## Status after fixes (2026-10-18, second pass)

I re-audited the current `contracts/src` after the core, bridge and tools fixes. `forge test`: 156/156 pass in one full run (154 from the coordinator plus 2 new re-audit tests in `test/audit/AuditFixes.t.sol`). The X Layer fork test passes 2/2. The original PoCs in `AuditCore.t.sol` and `AuditBridge.t.sol` are now regression tests that assert each fix.

| Finding | Status | What changed | Test |
|---|---|---|---|
| M-1 Mint after the reveal | Fixed, but see N-1 | `mint` reverts once a random seed is set. Collections committed with `commitManifestNoReveal` can keep minting until `freeze()` | `test_audit_mintAfterRevealReverts` |
| M-2 Blockhash reveal reroll | Fixed | `scheduleBlockhashReveal` is one-shot. A missed window leaves the collection unrevealed for good, and the NatSpec says so | `test_audit_blockhashRevealCannotBeRerolled` |
| M-3 Adapters not sealed | Fixed, with a residual (N-3) | New `ITapBridgeAdapterSealed`. `seal()` clears the owner, and for LayerZero also the delegate. `sealRoutes()` requires every listed adapter to report sealed and at least one open route | `test_audit_adapterDelegateChangeableAfterSeal` |
| L-1 Recipient is an endpoint | Fixed | `bridge` reverts `EndpointRecipient` for `to == peer` or `to == this`. `receivePayload` reverts when `p.to == this`. `decode` rejects `to == 0` | `test_audit_recipientIsDestinationEndpoint_tokenLost`, `test_audit_recipientIsGateway_tokenLost` |
| L-2 Message-id collision after redeploy | Fixed | `messageId = keccak256(srcEndpoint ‖ payload)` for departure, resend and arrival. The spec is updated | `test_audit_redeployedEndpointMessageIdCollision` |
| L-3 Escrowed token departs again | Fixed | New `escrowed[id]` mapping. `_depart` reverts `AlreadyEscrowed` when `escrowed[id]` is set or the gateway holds the token. `_arrive` requires `escrowed` | `test_audit_staleApprovalRedepartsEscrowedToken` |
| L-4 Companion `frozen()` can return to false | Fixed | `frozen()` returns only the latched state | `test_audit_companionFrozenNeverReverts` |
| L-5 Schedule overflow bricks the reveal | Fixed | The scheduled block must be at most `MAX_REVEAL_DELAY` (1,000,000 blocks) ahead | `test_audit_scheduleIsBounded` |
| L-6 Duplicate or invalid labels | Fixed | Labels must be 1–64 printable ASCII bytes and unique | `test_audit_duplicateLabelsRejected` |
| L-7 MAX_FILE above the 16.7M tx gas cap | Fixed | MAX_FILE is now 49,152. Storing a maximum-size file measures below 15M gas | `test_audit_maxFileFitsTxGasCap` |
| L-8 Renouncing without `freeze()` | Fixed | `transferOwnership(0)` reverts `ZeroOwner` in Core, so NFT and companion can only renounce through `freeze()` or `seal()` | `test_audit_renounceOnlyThroughFreeze` |
| L-9 Lock depends on upgradeable contracts | Accepted (documented) | NatSpec now names the processor, container, site-store and payment proxies. The `renew` refund is unchanged (refunded with `msg.value − fee`) | — (fork tests 2/2) |
| I-1 No per-chain accounting at the gateway | Accepted | Design choice: tokens may hop mirror to mirror | — |
| I-2 Stale hashes on mirrors | Mitigated | The gateway now refuses to depart an unbound token after the reveal (`NotBound`), but see N-2 | — |
| I-3 Plain `transferFrom` into the gateway | Accepted; hardened | The token can no longer be released even by a compromised route, because `escrowed` is false for it | — |
| I-4 LZ options with a native value | Accepted | Recoverable by re-execution | — |
| I-5 Hub authorship | Partly fixed | `setCircuit` requires the adapter to hold the circuit (`NotCircuitHolder`). What attesters must check remains operational | existing bridge tests |
| I-6 Hub domain after a chain fork | Fixed | `domainSeparator()` is recomputed when `block.chainid` changes | existing vectors |
| I-7 Companion endorsement and ordering | Accepted | `endorsedBy()` was added (`ITapCompanion`). The ordering caveat for TapeCode-Test1 still applies | — |
| I-8 Lock not bound to its container | Fixed | The constructor checks `opener.accountOf(processor, circuitId) == container` | fork tests |
| I-9 `_checkReceiver` decoding | Fixed | Low-level call; short or failed return data → `ERC721InvalidReceiver` | existing ERC-721 tests |
| I-10 Owner footguns before sealing | Partly fixed | `sealRoutes()` requires an open route. Changing a peer before sealing still orphans pending messages (owner trust) | existing bridge tests |
| I-11 Unused gates allowed | Accepted | Matches TAP-02 | — |

### New findings after fixes

**N-1 (Low): `reveal(NO_REVEAL)` re-opens minting after the reveal.**
- Location: `src/core/TapNetlistCore.sol` `_reveal` (accepts any non-zero seed) together with `TapNetlistNFT.mint` (`_isRandomlyRevealed()`).
- The sentinel `NO_REVEAL = 2^256−1` is accepted as an ordinary seed by `reveal()`. A collection committed for a random reveal can therefore be "revealed" with it. `_isRandomlyRevealed()` then stays false, so minting continues. Meanwhile `entryIndexOf` returns the identity assignment, which everyone knows. The owner or the minters can then mint exactly the ids they want, which is M-1 again.
- The manifest's declared seed source would expose this off chain, but the on-chain fix for M-1 is bypassed.
- PoC: `AuditFixesTest.test_audit_revealWithNoRevealSentinelReopensMinting`.
- Fix: `if (seed == 0 || seed == NO_REVEAL) revert InvalidValues();` in `_reveal`, which covers `reveal` and `revealFromBlockhash`. Alternatively, keep a separate `bool _noReveal` set only by `commitManifestNoReveal`, and use it in place of the sentinel comparison.

**N-2 (Low): the gateway's `NotBound` rule can strand tokens for good.**
- Location: `src/bridge/TapGateway.sol` `_depart` (the `n == 0 && i == 0 && masterSeed() != 0` check).
- After the data source's reveal, a token whose hashes are both zero cannot depart. Some tokens can never be bound: ids outside the data source's `tokenRange()`, for example a companion whose manifest covers only part of a legacy collection. Such tokens can never be bridged.
- Neither the spec nor the contract restricts gateways to collections whose ids are all in the manifest range.
- PoC: `AuditFixesTest.test_audit_gatewayNotBoundStrandsTokensOutsideManifestRange`.
- Fix: apply the rule only to ids inside `dataSource.tokenRange()`. Alternatively, require at construction that the data source's range covers the collection, and document the restriction in §4.2/§5.2 of the bridging draft.

**N-3 (Low): `adapterSealed()` promises more than the LayerZero adapter can guarantee.**
- Location: `src/bridge/LayerZeroV2Adapter.sol` `_onSeal`.
- The interface and the spec (§8.3) say a sealed adapter means nobody can change how it authenticates messages. `_onSeal` only zeroes the delegate. If the delegate never pinned the send and receive libraries and the DVN config before sealing, the adapter keeps following EndpointV2's defaults. The LayerZero endpoint owner can change those defaults, and so can still change the DVNs for this OApp after the endpoint is sealed.
- Fix: in `_onSeal`, for every configured eid, read `EndpointV2.getReceiveLibrary(address(this), eid)` (and the send library) and revert if `isDefault` is true. Alternatively, reword `adapterSealed` in the interface and the spec so that it excludes the EndpointV2 owner's defaults, and keep the existing DVN pinning SHOULD.

**Info, new:**
- `HubRelayAdapter.seal()` does not require `setCircuit` or `setRemote` to have run first. Sealing early leaves the route dead, a liveness problem only.
- `ERC721Min._checkReceiver` now forwards all gas and copies all return data. A receiver that returns a huge blob raises the transfer's memory cost, but only the caller who chose that `to` pays for it.
- Open question 3 of the Netlist-Bound NFTs draft still says "above 98,304 bytes"; it should say 49,152. Netlists of 49,153–98,304 bytes that a manifest already committed can no longer be stored by the reference contracts.
- `_adapterSealed` trusts each adapter's own report. A custom adapter can return true while keeping powers. This is acceptable because the endpoint owner chose the adapters, but clients should only recognise the reference adapters.

No regressions found in the fixed areas. The checks above re-ran:
- message id derivation is consistent across `bridge`, `resend` and `receivePayload`;
- ALL-policy confirmations are keyed by the new id;
- `escrowed` is set and cleared on every path;
- the hub's dynamic domain is used both for signing and for verification;
- the companion latch is still reached through `seal`, `endorse` and `announceFrozen`;
- duplicate labels are checked for at most two pools, which the disjoint field masks guarantee;
- the MAX_FILE change applies to the mirror too, through TapNetlistStore.

The VM differential fuzz still passes.

---

## Original review (findings as first reported; locations refer to the pre-fix code)

No source or existing test file was modified. New PoC and fuzz tests are under `contracts/test/audit/`:

| File | Content |
|---|---|
| `test/audit/AuditCore.t.sol` | PoCs C-1 to C-7 (core) |
| `test/audit/AuditBridge.t.sol` | PoCs B-1 to B-4 (bridge), plus a soundness test for hub signatures |
| `test/audit/AuditFixes.t.sol` | Re-audit PoCs N-1 and N-2 (added after the fixes) |
| `test/audit/AuditPass3.t.sol` | Third-pass PoCs P3-1 and P3-2 |
| `test/audit/AuditPass4.t.sol` | Fourth-pass checks: MAX_TOKENS set load gas, set-mode departure with loaded hashes and markKnown, lock opener residual |
| `test/audit/AuditVM.t.sol` | Differential fuzz of TapNetlistVM against an independent TAP-02 evaluator, and a fuzz test that the check and the VM accept the same files |

## Tooling results

- `forge build`: OK (solc 0.8.28). There are only lint notes and one mutability warning (`TapMirror._beforeStoreNetlist` could be `pure`).
- `forge test` (original review): 144/144 pass in one full run (129 existing plus 15 new audit tests; run the new ones alone with `forge test --match-path 'test/audit/*'`). The VM differential fuzz passed 3,000 runs.
- Fork test (`XLAYER_RPC=https://rpc.xlayer.tech forge test --evm-version cancun --match-path test/fork/ContainerLock.t.sol`): 2/2 pass.
- Slither: skipped because it is not installed.
- Read-only chain checks on X Layer (`cast storage`):
  - The processor `0x8E0b…60cF` is an ERC-1967 beacon proxy. Its beacon is `0xf70d1ed4…991c`, the unsealed circuit beacon listed in TAP-02.
  - DomainBinding `0x6880…66f9` is an ERC-1967 proxy (implementation `0x5ebf…47df`).
  - `monthlyFee()` returns 0.

## Summary

| Severity | Count |
|---|---|
| Critical | 0 |
| High | 0 |
| Medium | 3 |
| Low | 9 |
| Info | 11 |

I found no way to double-mint, replay a message, or bypass the ALL policy when the endpoint and adapter code are honest and correctly configured. The bridge state machine follows the spec closely.

The findings fall into four groups:

- Fairness of the reveal (minting after the reveal, rerolling a blockhash reveal).
- Trust that survives `sealRoutes()` because adapters are not sealed with the endpoints.
- Ways a token can be lost for good: the recipient is an endpoint, or two message ids collide after an endpoint is redeployed.
- Gaps against the spec (duplicate pool labels, a companion `frozen()` that can return to false, the MAX_FILE gas cost).

---

## Medium

### M-1 Owner and minters can mint after the reveal and pick the "rare" token ids
- **Location:** `src/core/TapNetlistNFT.sol:59-66` (`mint`). Nothing there checks `_isRevealed()`.
- **Description:** `mint` checks that the manifest is committed, that the collection is not frozen and that the id is in range. It does not check whether the seed is already set. After `reveal()`, `entryIndexOf(t, p)` is public, so anyone can see which unminted token id receives which pool entry. The owner, or any address with `isMinter`, can mint exactly the ids that receive a chosen entry. The class doc says "commitManifest → mint → reveal", and the draft's whole premise (§6: a seed fixed after the manifest, so the assignment is fair) assumes the minted set is fixed before the seed is known.
- **Exploit:** The collection reveals while part of the supply is unminted, for example during a public mint run through a minter contract that lets the buyer choose an id, or with team allocations kept back. The team or the buyers compute `entryIndexOf` for every free id and mint the ids that receive the scarce netlist or image.
- **PoC:** `AuditCoreTest.test_audit_mintAfterRevealSnipesChosenEntry`. The minter mints the id that receives netlist entry 0 after `reveal()` and binds it.
- **Fix:** Add `if (_isRevealed()) revert AlreadyRevealed();` to `mint`. Alternatively, have `_reveal` require that the whole range is minted (track `totalMinted == _supply`). Also state in the draft that minting must be complete, or closed, before the seed can be known.

### M-2 A blockhash reveal can be rerolled by skipping the reveal window
- **Location:** `src/core/TapNetlistCore.sol:98-106` (`scheduleBlockhashReveal`, which allows a reschedule once `block.number > previous + 256`), and `:110-115`.
- **Description:** `revealFromBlockhash` can only be called while `blockhash(_revealBlock)` is available. If nobody calls it within 256 blocks, the owner may schedule a new block. This is a second seed, which the draft forbids (§6.1 requirement 2: "MUST NOT request or choose a second seed").
- **Exploit:** The owner sees `blockhash(B)`, computes the assignment off chain and dislikes it. The owner does not call the permissionless reveal and waits 257 blocks. If no third party called it, the owner reschedules and draws again. This repeats until the owner gets an assignment it likes. A sequencer that cooperates, or plain lack of attention on a quiet chain, makes this practical. The manifest's `reveal.blockNumber` would no longer match the on-chain block, but the contract accepts the change and emits only a new `RevealScheduled`.
- **PoC:** `AuditCoreTest.test_audit_blockhashRevealCanBeRerolled`.
- **Fix:** Make the first schedule final; one option is to store a "missed" flag and refuse any further reveal. Better, derive the seed of a missed window deterministically, for example from `blockhash` of the first block in which `revealFromBlockhash` is called after the window, mixed with `B`. Better still, drop the blockhash source from the reference contract. In all cases, require that `blockNumber` equals a value committed in the manifest, for example by passing it to `commitManifest`.

### M-3 `sealRoutes()` does not seal the adapters: their owner keeps message-forging power under a sealed ONE route
- **Location:**
  - `src/bridge/LayerZeroV2Adapter.sol:56-58` (`setDelegate`, owner only, no lock)
  - `src/bridge/TapAdapterBase.sol:44-47` (`transferOwnership`)
  - `LayerZeroV2Adapter.setPeer` / `HubRelayAdapter.setRemote` / `HubRelayAdapter.setCircuit` for chains or circuits that are not yet set
- **Description:** After an endpoint is sealed, the adapter owner can still:
  - Call `setDelegate(x)` at any time. The delegate picks the receive library and DVNs, so with a library or DVN under its control it can satisfy `origin.sender == peer` for an arbitrary payload.
  - Undo a `setDelegate(0)`, because the owner can set a delegate again. Calling `setDelegate(0)` is therefore not the freeze the spec describes unless ownership is renounced in the same step.
  - Configure the peer for any chain that a sealed route lists but whose adapter peer was never set, and so choose who may speak for that route.

  Under ONE, the spec (Security Considerations) says this means the adapter owner can release every escrowed token and mint any token that is not live. The bridging draft's rationale "Why routes are sealed, not governed" reads as if sealing removes that owner power, but on chain `routesSealed()` says nothing about the adapters. §11 lists the delegate power, but nothing combines the two into one observable "sealed" state.
- **PoC:** `AuditBridgeTest.test_audit_adapterDelegateChangeableAfterSeal`. After `gw.sealRoutes()`, `lXL.setDelegate(attacker)` succeeds.
- **Fix:**
  - Add an adapter `seal()` that requires every chain the adapter will serve to be configured. It should set `delegate` to a chosen final value (or 0) and clear `owner` atomically, and expose `adapterSealed()`.
  - Have `TapBridgeEndpoint.sealRoutes()`, or the clients, require every listed adapter to report sealed.
  - At minimum, document that a collection is sealed only when the endpoint is sealed, every adapter owner has renounced, and the LZ delegate is final.

## Low

### L-1 A recipient equal to an endpoint loses the token for good
- **Location:** `src/bridge/TapBridgeEndpoint.sol:140-141` (`bridge`: only checks for zero and contract recipients), `src/bridge/TapMirror.sol:85-104` and `src/bridge/TapGateway.sol:52-57` (`_arrive`).
- **Description:**
  - `bridge` accepts any non-zero `to`, including the destination endpoint (`route.peer`), or the source endpoint itself on a mirror-to-mirror hop.
  - The contract-recipient check runs on the source chain. There, the destination endpoint's address normally has no code, so the check cannot catch this case and `contractRecipientOk` makes no difference. (The PoC sets the flag only because the fixture runs three chains in one EVM.)
  - On a mirror, the token is minted to the mirror. The mirror never calls `approve` or `setApprovalForAll` on itself and is never the `msg.sender` of `bridge`, so by inspection nobody can ever move or bridge the token again.
  - On the gateway, `transferFrom(gw, gw, id)` succeeds and the token stays in escrow with no pending departure.

  One wrong field in a UI or integration loses the token, with no attacker gain.
- **PoC:** `AuditBridgeTest.test_audit_recipientIsDestinationEndpoint_tokenLost` and `test_audit_recipientIsGateway_tokenLost`.
- **Fix:** In `bridge`, revert when `to == r.peer` or `to == address(this)`. In `_arrive`, revert when `p.to == address(this)`. The arrival then fails and can be retried after a fix, instead of executing.

### L-2 Message ids collide when an endpoint is redeployed, so the token is stuck in escrow
- **Location:** `src/bridge/TapBridgePayload.sol:30-43`; `src/bridge/TapBridgeEndpoint.sol:148` (`nextNonce` starts at 0); replay guard `:216`.
- **Description:** The payload binds `(collectionKey, srcChainId, nonce)` but not the source endpoint's address. The draft (§4.1) claims ids never repeat because "(srcChainId, sending endpoint, nonce) never repeats", but the endpoint address is not part of the hash. A second gateway for the same collection, or a redeployed mirror for the same collection on the same chain, starts again at nonce 0. If its first departures repeat an earlier `(tokenId, to, hashes, dst)` with the same nonce, the message id is the same. The destination's `executed[id]` is already set, so the arrival reverts `Replay`, and the token stays in the new endpoint's escrow (or burned on a mirror) with no recovery.
- **PoC:** `AuditBridgeTest.test_audit_redeployedEndpointMessageIdCollision`. The operator redeploys the gateway and re-points the mirror's route before sealing. Alice's first bridge from the new gateway has the same message id as her first bridge from the old one, and the arrival reverts `Replay`.
- **Fix:** Put the source endpoint address into the payload (one word, so the payload becomes payload v2), or mix it into the message id: `messageId = keccak256(srcEndpoint ‖ payload)`. Another option is a per-deployment salt, such as the endpoint address, in the starting nonce. At minimum, document "never redeploy an endpoint of a collection once any route has carried tokens".

### L-3 The gateway accepts `holder == gateway` in `_depart`, so an escrowed token can be re-departed on non-standard collections
- **Location:** `src/bridge/TapGateway.sol:41-50`.
- **Description:** `_depart` does not reject `ownerOf(tokenId) == address(this)`. With a standard ERC-721 no caller can pass the authorisation check for an escrowed token, because the per-token approval is cleared on transfer. Some legacy, pre-standard or custom collections keep the per-token approval after a transfer. With such a collection, the previously approved account passes the check `c.getApproved(tokenId) == caller`. The call `transferFrom(gw, gw, id)` succeeds because the gateway is the owner, and a second payload for the same token departs. That breaks the §2 invariant: two live copies.
- **PoC:** `AuditBridgeTest.test_audit_staleApprovalRedepartsEscrowedToken`. The test uses `StaleApproval721`, and the same token departs to BNB Smart Chain and then to Base.
- **Fix:** Add `if (holder == address(this)) revert AlreadyEscrowed(tokenId);` before the authorisation check. It costs one comparison and makes the invariant independent of the collection's approval semantics.

### L-4 `TapCompanion.frozen()` can return true and then false
- **Location:** `src/core/TapCompanion.sol:86-88`.
- **Description:** The view returns `_frozenLatched || (_sealed && endorsed && legacyUriFrozen())`. Until someone calls `announceFrozen()`, the live branch can flip back if the legacy getter is not monotonic: an upgradeable collection, an owner-togglable flag, or a getter that runs out of gas when the caller forwards little gas, because of the fixed 100k-gas staticcall. Draft §8.2 item 5 and §8.3 require that once true it never returns false, and that the first true observed is latched.
- **PoC:** `AuditCoreTest.test_audit_companionFrozenCanRevert`.
- **Fix:** Make `frozen()` return `_frozenLatched` only, and rely on the permissionless `announceFrozen()`, which `seal()` and `endorse()` already call. Optionally also latch from `bind` and `storeNetlist`.

### L-5 `scheduleBlockhashReveal` can make the reveal impossible for good
- **Location:** `src/core/TapNetlistCore.sol:98-106`.
- **Description:** `blockNumber` has no upper bound.
  - A value near 2^256 makes `previous + 256` overflow, so every later reschedule panics.
  - A value far in the future, such as a mistyped extra digit, blocks the reveal for that long.

  In both cases `reveal()` is disabled from then on (`RevealIsScheduled`), so the collection can never be revealed or frozen. This is the owner harming itself, but it cannot be undone.
- **PoC:** `AuditCoreTest.test_audit_scheduleOverflowBricksReveal`.
- **Fix:** Require `blockNumber <= block.number + MAX_DELAY` (for example 7 days of blocks), and compute the reschedule condition without the possible overflow.

### L-6 Duplicate or invalid pool labels are accepted
- **Location:** `src/core/TapNetlistCore.sol:72-81`.
- **Description:** Draft §5.2 requires labels of 1–64 printable ASCII bytes, unique within the manifest. The contract does not check this. Two pools with the same label get the same `poolSeed`, so image and netlist assignments use the same permutation and the independence the two-pool design promises is lost. An empty or very long label is also accepted. The manifest hash makes this detectable off chain, but the L1 contract is supposed to be the checkable surface.
- **PoC:** `AuditCoreTest.test_audit_duplicateLabelsShareSeed`.
- **Fix:** In `commitManifest`, check `1 <= bytes(label).length <= 64`, that every byte is in 0x20–0x7e, and, when there are two pools, that `keccak256(label0) != keccak256(label1)`.

### L-7 A MAX_FILE netlist cannot be stored within a 16,777,216-gas transaction
- **Location:** `src/core/TapNetlistStore.sol:16` (`MAX_FILE = 98304`).
- **Description:** Storing a 98,303-byte valid file costs 24,867,149 gas (measured, including the check). TAP-02 quotes a 16,777,216-gas transaction cap on BNB Smart Chain, and EIP-7825 sets the same cap. At about 252 gas per byte, files above roughly 66 KB cannot be stored there. A bound token whose committed netlist is larger can never be materialised on such a chain, neither on the home chain nor on a mirror there, although the interface promises that files up to MAX_FILE are accepted.
- **PoC:** `AuditCoreTest.test_audit_maxFileStorageGas`. It logs the gas and asserts it is above 16,777,216.
- **Fix:** Lower MAX_FILE to fit 16.7M with margin (about 60 KB). Alternatively, add staged storage: one transaction per chunk, then `finalize`, which re-hashes by reading the chunks back. Also state the per-chain limit in the draft (§8.2 item 4 and Open question 3).

### L-8 Renouncing through `transferOwnership(0)` instead of `freeze()` leaves minters in place for good
- **Location:** `src/vendor/Owned.sol:26-28`, inherited by `TapNetlistNFT` (and `TapCompanion`).
- **Description:** `transferOwnership(address(0))` is public and permanent. On `TapNetlistNFT` it leaves `_frozen == false`, so every address with `isMinter` can still mint, and nobody can revoke them. `frozen()` stays false for ever, and the base URI is stuck at its current value. On `TapCompanion`, renouncing before `seal()` means `_sealed` never becomes true and `frozen()` never becomes true.
- **PoC:** `AuditCoreTest.test_audit_renounceWithoutFreezeLeavesMinters`.
- **Fix:** Override `transferOwnership` in both contracts to reject `address(0)`, so that renouncing goes only through `freeze()` or `seal()`. Alternatively, make `freeze()` the only way to renounce.

### L-9 `TapContainerLock` is only as permanent as the processor beacon and DomainBinding proxies
- **Location:** `src/tools/TapContainerLock.sol:14-20` (claims), `:45-47` (`locked`), `:53-62` (`renew`).
- **Description:**
  - The processor `0x8E0b…60cF` is a beacon proxy behind the unsealed circuit beacon `0xf70d…991c`, as read on chain. Whoever controls the factory or beacon can change `ownerOf` or transfer logic and move the circuit out of the lock, or write as any container. That contradicts the doc's "no way to get the NFT back" as a property of the system, as opposed to a property of the lock alone.
  - DomainBinding is an ERC-1967 proxy. If a future implementation refunds part of `msg.value` to the caller (for example when the ten-year cap is reached) or changes the fee semantics, `renew` reverts, because the lock has no `receive()`. The lock is immutable and cannot adapt.
  - ETH sent to the lock by force (selfdestruct or coinbase) is stuck for good.
- **PoC:** none (read-only `cast storage` evidence above; the fork test passes today with fee 0).
- **Fix:**
  - Document the beacon and binding trust in the NatSpec and in tools that show "locked".
  - Refund the balance difference (`address(this).balance` after `bind`, minus the balance before the call less `msg.value`) instead of `msg.value - fee`, and add a `receive()` that accepts ETH only during `renew` (use a storage flag, or a transient one under cancun; `foundry.toml` pins shanghai).

## Info

- **I-1 No per-chain accounting at the gateway.** `TapGateway._arrive` releases any escrowed token to any route that delivers a payload for it. A compromise of the weakest route (any ONE route to any mirror) can therefore drain every escrowed token, not only those bridged to that chain. Mirror-to-mirror hops make per-chain accounting impossible as designed. The spec acknowledges this under "Double mint". Consider recommending ALL on every route into the gateway, or dropping mirror-to-mirror hops so that the gateway can record `locationOf[tokenId]`.
- **I-2 Stale hashes on mirrors.** A token bridged before `bind` carries zero hashes. The mirror keeps them until the token goes home and back. A later arrival with zero hashes overwrites non-zero ones (`TapMirror.sol:98-100`). This matches the spec, but UIs should show the "unbound on the home chain at departure" state.
- **I-3 Plain `transferFrom` into the gateway is unrecoverable.** The spec documents this (§5.2). Only an adapter compromise can release such a token.
- **I-4 Caller-supplied LZ options with a native `lzReceive` value** make `lzReceive` revert (`ValueNotAccepted`, `LayerZeroV2Adapter.sol:100`). The message can be recovered by a permissionless re-execution with zero value. Consider rejecting such options in `send`.
- **I-5 Hub relay authorship trust.**
  - `setCircuit` (`HubRelayAdapter.sol:77-82`) does not check that the adapter holds the circuit. `remoteContainer` is the only author binding on the destination.
  - If the real TAP-10 hub lets a container's operator, or the container itself via `execute`, write messages, then whoever holds that operator role can author bridge payloads that attesters would sign. Attesters should check that the hub entry was written while `ownerOf(circuit) == adapter`, and that no operator is set.
  - While the processor factory is unsealed, its owner can write as any container (the spec notes this).
- **I-6 `HubRelayAdapter.domainSeparator` is immutable** and computed with `block.chainid` at deployment. After a chain fork, signatures are valid on both forks. Consider recomputing it when `block.chainid` changes.
- **I-7 Companion endorsement and ordering.**
  - `endorse()` is not unique: the legacy owner can endorse several companions with different manifests.
  - It can be called before `commitManifest`, so it endorses a contract whose content is not yet fixed.
  - For TapeCode-Test1 the legacy owner is the container of circuit #1. Once that circuit is moved into `TapContainerLock`, the container can never call `endorse()` or `freezeBaseURI()` again. Do both before locking, or the companion can never become frozen.
- **I-8 `TapContainerLock` does not bind `container` to `(processor, circuitId)`, and does not check `onChainName`.** `locked()` checks only the circuit. A lock can be deployed whose `container` is unrelated to the locked circuit, which can mislead tools that show a container as "locked". Have tools check `hub.accountOf(processor, circuitId) == container`.
- **I-9 ERC721Min `_checkReceiver`** (`ERC721Min.sol:166-173`). A receiver that returns fewer than 32 bytes makes the call revert with a decode error outside the `catch` instead of `ERC721InvalidReceiver`. The transfer still reverts, so this only affects error reporting.
- **I-10 Owner trust before sealing.** The owner can change routes, policies and peers before sealing. Changing a peer while messages are pending makes them fail with `WrongPeer`. `sealRoutes()` succeeds even with no routes configured, which bricks the endpoint. Endpoints have no transfer of ownership, so a lost key before sealing leaves routes unrepairable. These are all owner trust or footguns, as specified.
- **I-11 `TapNetlistCheck` and `TapNetlistVM` accept files with records that produce more signals than `nOut` needs.** Unused gates are allowed. This matches TAP-02 and is only relevant for "fake scarcity" (draft Security Considerations).

---

## Checked and found sound

**Bridge**
- `TapBridgePayload.decode` requires exactly 320 bytes, version word == 1, and zero high bits in the address and uint64 words. Every field is read from fixed offsets, so each payload has exactly one encoding. Test vectors match.
- `receivePayload` checks, in this order:
  - the route is not NONE;
  - `msg.sender` is a listed adapter;
  - `srcEndpoint` is the route's peer;
  - `p.srcChainId == srcChainId`, `p.dstChainId == localChainId` and `p.collectionKey` matches;
  - replay via `executed`.

  The adapters derive `srcChainId` and `srcEndpoint` from their own set-once tables (LZ `chainOf[srcEid]`, `remoteEndpoint`; hub `remoteContainer`), so a listed adapter cannot claim another chain.
- ALL policy:
  - Confirmations are keyed by (messageId, adapter address), so they cannot be shifted to another adapter or chain.
  - The same adapter confirming twice reverts.
  - Mismatched payloads produce different ids and never execute.
  - `executed` is set before `_arrive`.
  - If the final confirmation reverts, its `confirmedBy` entry is rolled back with it, so it can be retried.
  - A route change while a message is pending is the spec's recovery path, available to the owner only before sealing.
- Replay: `executed` covers both policies. A message that executed earlier cannot execute again after the token has left the chain once more, because each departure has a fresh nonce.
- Reentrancy:
  - `bridge`, `resend` and `receivePayload` share one `nonReentrant` lock, and the refund runs inside it.
  - Mirror mint and burn and gateway escrow use no ERC-721 receiver hooks (`_mint`, `_burn`, `transferFrom`).
  - Adapters forward exactly the quoted fee. Endpoints have no `receive` and keep no balance.
- `_isContract` treats the 23-byte EIP-7702 designator correctly.
- LayerZero adapter:
  - `lzReceive` checks the caller is EndpointV2, `msg.value == 0`, and a non-zero peer equal to `origin.sender`.
  - `allowInitializePath` rejects a zero sender.
  - Peer, eid and chain mappings are set once, and their three slots are checked independently.
- Hub relay adapter:
  - EIP-712 domain binds name, version, chainid and the adapter address; the struct hash matches the type string.
  - `v` must be 27 or 28 and `s <= n/2`; HALF_N is correct.
  - Exactly `65·K` bytes of signatures; signers strictly ascending; a monotonic cursor over the sorted attester list; a zero recovered address is rejected.
  - Replay key `(srcChainId, outboxIndex)`; `ref == keccak256(payload)`.
  - Signatures made for another chain's adapter domain fail. Tested in `test_audit_hubRejectsMalleatedAndForeignDomainSignatures`, together with high-s malleability.
  - A hub message addressed to another chain is stopped by the payload's `dstChainId`; one addressed to another collection is stopped by `collectionKey`.
- Mirror `_arrive` handles `AlreadyLive`, `OutOfRange` and the manifest latch and conflict. The mirror's `_depart` checks authorisation, then burns, which clears the approval.

**Core**
- `TapMerkle.verify`:
  - `index < size`;
  - odd-node promotion consumes no sibling;
  - the proof must be consumed exactly;
  - leaf and node domain tags (0x00/0x01) and the different preimage lengths (37/69 vs 65 bytes) rule out second preimages;
  - the index inside the leaf ties each value to its position;
  - entry indices are below 2^32, so `uint32(index)` does not truncate.
- `TapPermutation`:
  - matches the draft's `h = ceil(bitlen(n−1)/2)` and the byte layout of the F input;
  - is a bijection (the existing exhaustive and fuzz tests);
  - its cycle walk has domain `4^h < 4n`, so the expected number of steps is at most 4, and for n = 2^32 the maximum over all tokens is about 90 Feistel calls in practice. A seed cannot realistically be ground to cause an out-of-gas.
- Bind:
  - checks value count and non-zero values;
  - the proof is checked on every call;
  - first write wins per field;
  - field masks are disjoint, so each token's hashes are unique and cannot be overwritten.
- `storeNetlist`:
  - checks size before hash membership before content;
  - is idempotent, so front-running or griefing gains nothing;
  - only known hashes are accepted;
  - the SSTORE2 init code (`61 len+1 80 60 0a 3d 39 3d f3 00`) is correct (len+1 ≤ 24,576 fits in PUSH2);
  - the 0x00 prefix makes the data contracts uncallable and avoids EIP-3541;
  - chunk pointers come only from the contract's own `create`, so they cannot be forged;
  - read-back by `extcodesize − 1` is correct.
- Freeze: after `freeze()` on TapNetlistNFT, `commitManifest`, `reveal`, `schedule…`, `setMinter`, `setBaseURI` and `mint` are all unreachable (owner is 0, `_frozen` is set). `_beforeStoreNetlist` cannot be overridden in Core.

**TapNetlistCheck and TapNetlistVM**
- Both read the header at the right offsets and enforce the pin bounds of TAP-02 §2.
- Record lengths are checked before fields are used. Out-of-bounds `mload`s are read-only and only reach bytes beyond `end` after the length check fails.
- The VM's `sig` allocation `2 + nIn + (len−16)/4` bounds the number of signals because every record is at least 4 bytes. `nIn` is validated before allocation.
- Semantics match TAP-02 §4 and §5:
  - NAND inputs refer backward only;
  - a LATCH outputs its previous state bit, and its new state bit is `s[d]` after the pass, with `d < S` checked;
  - outputs are the last `nOut` signals;
  - inputs and state are read leniently;
  - outputs and new state are exactly `ceil(n/8)` bytes with zero padding.
- Confirmed by `AuditVMTest.testFuzz_audit_vmMatchesReference`, a differential test against an independent evaluator over 3,000 runs with random state and input lengths, and by `testFuzz_audit_vmRejectsWhatCheckRejects`. The VM is only reachable through ITapNetlistEval on stored files, which have already passed the check.

**TapContainerLock**
- The lock has no code path that calls the processor other than `ownerOf`.
- `onERC721Received` checks both `msg.sender == processor` and `tokenId == circuitId`.
- `renew`: `msg.value − fee` underflow reverts; reentering through the refund is harmless (it holds no state).
- Fork tests confirm the old holder loses every write path.

**ERC721Min / vendor**
- All changes go through `_update`, which clears the approval and keeps balances consistent with ownership (the unchecked arithmetic is safe for that reason).
- `transferFrom` checks owner, receiver and authorisation.
- `safeTransferFrom` runs the receiver hook after the state change, which is standard.
- `approve` is limited to the owner or an operator.
