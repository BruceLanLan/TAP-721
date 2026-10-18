# Editorial review of the four netlist-NFT TAP drafts

Reviewer stance: TAPs editor (format, completeness, coherence, one topic; TAP-01 §4) plus an implementer's check (can an independent team interoperate from the text alone). The drafts were not edited.

Files reviewed (line numbers are those of the current files):

| Short | File |
|---|---|
| A | `TAPs/TAP-draft-netlist-bound-nft.md` (+ `.zh.md`) |
| B | `TAPs/TAP-draft-netlist-nft-bridging.md` (+ `.zh.md`) |
| C | `TAPs/TAP-draft-pod-attributes.md` (+ `.zh.md`) |
| D | `TAPs/TAP-draft-netlist-structural-hash.md` (+ `.zh.md`) |

Rules applied: TAPs `README.md`, `CONTRIBUTING.md` §2–§4, `TAP-template.md`, TAP-01 §3, §5, §6, §7, §10; tone and precision of the editor comments on issue #21 and PR #23; TAP-02, TAP-10, TAP-11 as merged precedent.

## 0. Summary

| Draft | Blocker | Should fix | Nit |
|---|---|---|---|
| A Netlist-Bound NFTs | 5 | 15 | 6 |
| B Bridging | 3 | 13 | 4 |
| C PoD attributes | 4 | 8 | 4 |
| D Structural hash | 2 | 4 | 3 |
| Cross-cutting / process | 1 | 3 | 3 |

Top 5 blockers:

1. **All four:** `discussions-to: TBD` is not a URL (TAP-01 §7.1), and `requires:` names an unnumbered draft (B, C) or omits it (D). Editors will not merge in this state.
2. **C §4.3 and §5.4 item 6** treat `frozen` as a token state "defined" in A §7.2, while A §7.2 says the opposite (frozen is not a metadata state; it is read from the chain).
3. **A §6.1 `source: none` against §8.2 item 2:** an L1 collection without a reveal never has a non-zero `masterSeed()`, so `entryIndexOf` always reverts, `bind` is impossible and `frozen()` can never be true.
4. **A §5.2 manifest entry `uris`:** the text says "an object keyed by field name"; the vectors, the example manifest and `tapnft.py` use an array. Text and vectors contradict each other.
5. **B §4.1 (B:100):** the payload omits the sending endpoint's address, so after a pre-seal endpoint replacement (nonce restarts at 0) a legitimate message can be byte-identical to an executed one and is rejected as `Replay`: the token is lost. The text claims message ids never repeat.

Other blockers: C §5.1 depends on ERC-7496 "master branch" (not a fixed version); C §3.5 both defines `"restartable"` for status 3 and forbids guessing; A §6.1 `vrf`/`chainHash` and A §8.3 endorsement are not specified enough to verify; B errors have no signatures; D omits A from `requires`.

## 1. What was recomputed and found correct

So the editors see what does not need re-checking:

- **Selectors (all `cast sig`):** every selector in A (13 `ITapNetlistNFT`, 4 `ITapNetlistEval`, `endorse()`), B (5 `ITapBridgeEndpoint`, 9 `ITapBridgeTransfer`, 3 `ITapBridgeMirror`, 3 `ITapBridgeAdapter`, `NotHomeCollection()`, `setPeer`, EndpointV2 `send`/`quote`/`lzReceive`/`allowInitializePath`/`nextNonce`/`setDelegate`, hub `send`, `setCircuit`, `setRemote`, `deliver`, `hubMessageHash`) and C (13 mining/processor getters, 4 ERC-7496 functions) matches.
- **ERC-165 ids (XOR):** `0x282b67f6`, `0xec7d7e20`, `0x3d6a52e3`, `0xdbc2d1d3`, `0xdba6a55e`, `0xaa621a3e`, ERC-7496 `0xaf332f3e`: all match.
- **Event topics (`cast keccak`):** all six of A, `MetadataUpdate(uint256)`, all five of B: match.
- **Labels:** B layer ids (`TAP-NFT adapter LayerZeroV2 v1`, `… TAP-10 hub relay v1`), B collection key for TapeCode-Test1 (`0x8755…b4bd`), all 15 C trait keys: match.
- **B §4.3 worked example:** netlist hash of the 23-byte file, SHA-256 of `example image` / `example manifest`, the 320-byte `abi.encode`, and `messageId = 0x11c7…7497`: all reproduce. LayerZero default options for 400,000 gas reproduce.
- **Vector files:** SHA-256 of all four `vectors.json` and of `trait-metadata.json` match the values quoted in the drafts and READMEs; all four generators reproduce them byte for byte in a scratch copy, and all test suites pass (A 20, D 18, C 19 tests; B `--check`).
- **Independent implementations from the text alone:** (a) A `poolSeed`, `permute`, Merkle root and the token assignment of the 8-token example, plus the manifest hash: all match the vectors; (b) D's full canonicalization (liveness, A/C labels, rounds, merge, depth order, output tail, copy records, hash) written only from §3–§7 reproduces the canonical file, structural hash, `live`, `nodes` and `rounds` of all 37 cases and 3 mainnet circuits. D is implementable as written.
- **C Test Cases table:** A = g + λs, b* = n + λ_burn·m, C = A·max(d,1)^β, bonus = ⌊K·clamp(C_ref/C, 1/4, 4)⌋ and verifWeight = (b* + bonus)·P hold for all seven rows; `minerKey` = keccak256(processor ‖ uint256 id) reproduces `0xa13a…464e` for #17851; block 128,200,681 timestamp 1792253755 = 2026-10-17 16:15:55 UTC (read from chain).
- **D Test Cases table:** all 21 rows agree with `vectors.json`.
- **Cross-references that exist and say what is claimed:** TAP-10 §1, §2.1 (finality tags), §3.1, §3.2, §5, §8.8, §12.1, §13.2, §13.3 (`deweb.hub.v1`), §13.4 (opened), §13.6 (digest), §13.8, §17, §18.3; TAP-02 §2, §3 conditions 3–8, §4, §5, §6, §7 requirements 1–2, Deployments (BSC factory not sealed); A §2.2, §2.3, §4.1, §4.2, §6.2, §7.1 (`structuralHash`), §7.3 item 4, §8.2, §8.3 as cited by B, C, D. The one broken reference is A §7.2 as cited by C (Blocker C-2).
- **Types and layering (TAP-01 §3):** A and B are correctly Standards (contract interfaces, byte formats, verification rules); C is correctly Application (a metadata convention on top of A); D is Standards (see D-6). No requirement of A is weakened by C: C §2 item 3 re-affirms A in full, C §4.3 and §5.4 only add rules, and C §5.4 item 4 is stricter than ERC-7496, which TAP-01 §3 permits. B does not weaken A either; its mirror profile uses the bridged-copy allowance of A §8.2 (but see A-14, B-8).
- **Examples are marked as examples** where they occur (B:110 "Example values", A:151 "e.g.", C:66 "for example", C:269 "such as", B:404 "for example"); no example carries an unstated requirement.
- **Supply and numbers:** 10,000 everywhere; no 7,000 supply in any draft or translation (the only "7,000" is a gas figure, A:414). Block 128,200,681 is used consistently.
- **Format:** key-words paragraph verbatim in all four English files; Summary one sentence without key words in all four; section order as in the template; `license: CC0-1.0` and Copyright section present; no self-assigned number (`tap: TBD`, `# TAP-TBD:`); RFC 2119 words outside Specification only at A:431 and A:433.

## 2. Draft A — Netlist-Bound NFTs

### Blockers

**A-1. `discussions-to` is not a URL** — A:6

> `discussions-to: TBD`

TAP-01 §7.1 requires a URL, and CONTRIBUTING §2.2 says to set it to the idea issue. Same in B:6, C:6, D:6 and in every `.zh.md`.
Proposed: `discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/<nn>` (the Idea issue opened for this package; one issue per draft, or one shared issue cited by all four).

**A-2. Manifest entry `uris`: text contradicts vectors** — A:168

> "An entry MAY carry `uris` (content locations of each field, as an object keyed by field name)"

`example/manifest.json`, `vectors.json` and `tapnft.py` use a plain array (`"uris": ["https://example.invalid/…/0.png"]`). An implementer following the text rejects the reference example. The two-field pool case is not covered by the array form either.
Proposed: "An entry MAY carry `uris`: in a one-field pool, a non-empty array of URI strings for that field's content; in a two-field pool, an object with the members `image` and `netlist`, each a non-empty array of URI strings." Add a two-field example entry to the vectors.

**A-3. `source: none` cannot work at L1** — A:200 against A:293 and A:296

> A:200 "`none` | — | No reveal: pool entry `i` goes to token `firstTokenId + i`"
> A:293 "`entryIndexOf(t, p)` returns `permute(poolSeed_p, supply, t − firstTokenId)` (§6.3) once `masterSeed()` is non-zero, and reverts before"
> A:296 "`frozen()` returns true only when the manifest is committed, the seed is set …"

With `none` there is never a seed, so an L1 collection without a reveal can never `bind`, never serve hashes and never be frozen.
Proposed (add to §8.2 item 2): "If the manifest's `reveal.source` is `none`, `masterSeed()` returns `0x00…01` from the moment the manifest is committed, `entryIndexOf(t, p)` returns `t − firstTokenId`, and item 5 treats the seed as set." Or forbid it: "An L1 collection MUST NOT use `source: none`."

**A-4. Seed sources are not specified precisely enough to verify** — A:197–199

> "`drand` | `chainHash` (hex), `round` (number)"; "`vrf` | `chainId`, `coordinator`, `requestTx` or `requestId` | The first random word delivered for that request"

(1) `chainHash` "(hex)": the example manifest writes it without `0x`, while every other hex value in this TAP has `0x`. (2) `vrf`: no VRF version, no type for `requestId` (number? decimal string? it is a uint256), no rule for choosing between `requestTx` and `requestId`, and no event or call from which a verifier reads "the first random word delivered". Two verifiers can disagree. (3) Where the seed is set on chain at L1, and by whom, is not stated (the interface has no commit/reveal function; the reference has `RevealIsScheduled`, `BlockhashUnavailable`).
Proposed: "`chainHash`: 64 lowercase hexadecimal digits without `0x`, as published by drand." For VRF either remove it from version 1 ("`vrf` is reserved; tools MUST reject a manifest that uses it") or specify: "`vrf`: `chainId` (number), `coordinator` (address), `requestId` (decimal string); the master seed is `randomWords[0]` of the `RandomWordsFulfilled(uint256 indexed requestId, …)` event of Chainlink VRF v2.5 (<fixed commit>) emitted by `coordinator` for `requestId`, as a 32-byte big-endian integer." Add one sentence to §8.2: "How the master seed is written on chain is implementation-defined; an L1 contract MUST set it to the value §6.1 defines for the manifest's source, and `Revealed(masterSeed)` lets anyone compare."

**A-5. Companion endorsement cannot be checked interoperably** — A:339

> "a companion MUST offer a function that only that address can call and that records the endorsement permanently, emitting `Endorsed(address by)` (the reference implementation names it `endorse()`)"

A tool can neither call the endorsement nor read it without scanning logs; "that address" is `owner()` at which moment is not stated (the Test1 owner is a container whose controller follows circuit #1).
Proposed: "A companion MUST implement `endorse()` (`0xf4fbaf58`), which reverts unless `msg.sender` equals the collection's `owner()` (ERC-173) at the time of the call, records the caller permanently and emits `Endorsed(address by)`; and `endorsedBy() returns (address)` (`0xe64fa534`), which returns the recorded address or zero. A later change of the collection's owner does not undo an endorsement." Decide whether these two functions are part of the ERC-165 id or a separate interface, and say so in Test Cases.

### Should fix

**A-6. `requires` incomplete** — A:10

> `requires: TAP-02, TAP-10, ERC-721, ERC-165, ERC-4906`

§8.3 relies on ERC-173 `owner()`; §4.1 uses the CAIP-19 form (A-7).
Proposed: `requires: TAP-02, TAP-10, ERC-165, ERC-173, ERC-721, ERC-4906, CAIP-19`.

**A-7. The token identifier is CAIP-19; say so** — A:115–121

> "`eip155:<chainId>/erc721:<collection address>/<tokenId>`"

This is exactly CAIP-19 asset id syntax. Editors will ask "use an existing specification" (TAP-01 §10).
Proposed: "The global identifier of a netlist-bound NFT is its CAIP-19 asset ID (CAIP-19, <fixed commit>), `eip155:<chainId>/erc721:<collection address>/<tokenId>`, with the address in lowercase …" and one Rationale line: "CAIP-19 rather than a new form: wallets and indexers already parse it."

**A-8. Source verification: which block** — A:94, A:98–103

> A:94 "together with the block number at which it was read"; A:98 "reading the source chain under the rules of TAP-10 §5 (independent nodes, one pinned block)"

TAP-10 §5.3 pins a recent block (max lag 400 blocks), while the declared `block` is usually old and pruned on public BSC nodes. The text does not say at which block the verifier reads, nor give the `isCPU` selector.
Proposed: "A verifier reads at one block `B'` pinned under TAP-10 §5.3, or at the declared `block` if it has archive access, and reports which. Because stored netlists have no setter (TAP-02 §3), a confirmation at any block at or after the declared one is a confirmation. Step 1 calls `isCPU(address)` (`0x5f5a364f`) on the factory."

**A-9. Publication time of an L0 manifest is not checkable as written** — A:155

> "by uploading the manifest to a TapeOut container (TAP-10 records each file's SHA-256 in the site store, in a block) … A tool checks that this block precedes the moment the master seed became known"

TAP-10 does not define how to find the block in which a file was written, and a file can be overwritten later.
Proposed: name the site-store event and field (e.g. "the earliest `FileSet`-type event of the site store with this container, path and SHA-256", with its exact signature from TAP-10 or the site-store source) or say "a tool that cannot find the write block treats publication time as unproven and says so".

**A-10. Merkle proof verification is described, not specified** — A:185

> "Verifying a proof requires the root, the pool size, the index, the leaf and the proof, and succeeds only if every sibling is consumed …"

The root construction is precise; the verify loop (how `size` decides at each level whether a sibling is consumed, and left/right order) is left to inference.
Proposed (add pseudocode; checked: it accepts all 38 proofs in `vectors.json` and rejects all 4 negatives): "`if index ≥ size: fail. h = leaf; i = index; n = size; k = 0; while n > 1: if i is odd: h = SHA-256(0x01 ‖ proof[k] ‖ h); k += 1 elif i + 1 < n: h = SHA-256(0x01 ‖ h ‖ proof[k]); k += 1; i = i >> 1; n = (n + 1) >> 1. Succeed iff k = len(proof) and h = root.`"

**A-11. `pools()` "non-zero"** — A:292

> "`manifestHash()`, `pools()`, `tokenRange()` and `masterSeed()`, once non-zero, never change"

Proposed: "`manifestHash()` and `masterSeed()` once non-zero, and `pools()` and `tokenRange()` once set (non-empty, `supply` ≥ 1), never change. `pools()[i]` equals the label, field mask and root of the manifest's `pools[i]`."

**A-12. L1 errors and the meaning of "known"** — A:293–295

> "reverts before"; "`storeNetlist` accepts only files whose SHA-256 is a netlist hash the contract already knows"

No error names or selectors are given, so clients cannot distinguish "not revealed" from "not bound" or "unknown netlist"; "knows" is undefined.
Proposed: "A netlist hash is known when `netlistHashOf(t)` returns it for some token `t`." Either add an errors table with signatures and selectors (the reference already has `NotRevealed()`, `NotBound(uint256)`, `UnknownNetlist(bytes32)`, `NetlistTooLarge(uint256)`, `InvalidProof()` …), or state: "Revert data is not part of this interface."

**A-13. `NetlistStored.pointer` layout incomplete** — A:295

> "otherwise a contract whose data is the concatenated 20-byte addresses of the chunk contracts"

The chunk size (24,575 bytes in `TapNetlistStore.sol`), the chunk order and the `0x00` prefix of the index contract (present in the reference: `_deployFromMemory` writes runtime `0x00 ‖ data`) are not stated. Either specify or make it informative.
Proposed: "… otherwise the file is split into consecutive chunks of 24,575 bytes (the last one shorter), each stored as runtime code `0x00 ‖ chunk`, and `pointer` is a contract with runtime code `0x00 ‖ address_0 ‖ … ‖ address_{k−1}`." Or: "The layout behind `pointer` is informative; clients read files through `netlistFile`."

**A-14. Bridged copies: three values conflict with B** — A:153, A:301, A:299

> A:153 "`supply` MUST satisfy 1 ≤ `supply` ≤ 2^32"; A:299 "the values in its metadata MUST equal what the interface returns"

B §5.3 (B:199, B:206) has a mirror return `tokenRange()` with `supply = 0` when the range is not fixed, `collection()` = the mirror itself, and metadata whose `tap.id` names the home token. Extend A's bridged-copy paragraph so B does not contradict A.
Proposed (append to A:301): "In such a copy, `collection()` returns the copy itself, `tokenRange()` MAY return `supply` = 0 for an unbounded range, `frozen()` MAY stay false, and the metadata's `tap.id` is the identifier of the home token (§4.1)."

**A-15. `companion` member vs endorsement path** — A:260 against A:339

> A:260 "`companion` | when an L1 companion exists"; A:339 "The second way works even after the collection's URI is frozen."

If the URI is frozen, the metadata cannot gain `tap.companion`, so the "when" rule cannot be met on the very path that §8.3 offers for frozen collections.
Proposed: "`companion` | when the collection names its companion through metadata (§8.3, way 1)".

**A-16. Required sub-members not stated** — A:254–256

The table lists members of `manifest`, `image`, `netlist` but only says "optionally" for `structuralHash`. `tapnft.py` requires non-empty `uris`.
Proposed: "In `manifest`, `image` and `netlist`, every listed member is required except `structuralHash`; `uris` is a non-empty array of URI strings."

**A-17. JSON range of token ids** — A:148, A:262

`firstTokenId` is a JSON number, and numbers are limited to 2^53 − 1, while ERC-721 token ids are uint256 and `source.circuitId` is already a decimal string.
Proposed: "`firstTokenId` (decimal string)" or "`firstTokenId` (number, at most 2^53 − 1 − `supply`)".

**A-18. Key words in Security Considerations** — A:431, A:433

> A:431 "A collection that declares `structuralHash` SHOULD give it for every netlist"; A:433 "Tools SHOULD show whether the container … is locked."

Move both into the Specification (§7.1 and §4.2) and keep lowercase pointers here, as TAP-02 does.
Proposed for A:431: "… declare both; §7.1 asks collections that declare `structuralHash` to declare it for every netlist." Add to §7.1: "A collection that gives `structuralHash` for one netlist SHOULD give it for every netlist." Same pattern for A:433 into §4.2.

**A-19. ERC-4906 interface id not written out** — A:290

> "reporting the interface identifier of `ITapNetlistNFT`, ERC-165 itself and ERC-4906"

Proposed: "… `ITapNetlistNFT` (`0x282b67f6`), ERC-165 (`0x01ffc9a7`) and ERC-4906 (`0x49064906`)".

### Editor objections to pre-empt (A)

- **"One topic?"** A covers the file format, source check, identifier, manifest and Merkle pools, reveal, metadata, L0/L1, companions and an evaluation extension. Expect the question; PR #23 already showed editors read for this. Pre-empt in Rationale: "These parts are one topic: each is needed for a wallet to check one token end to end, and L1 adds on-chain reads to the same rules as L0, nothing else." Offer the evaluation extension (§8.4) as the first candidate to split out if asked, and say in the PR that `tapnet/1` could stand alone (D already depends only on it).
- **"Use an existing ERC."** Add one Rationale paragraph: why `netlistHashOf`/`imageHashOf` are not ERC-7496 traits (C uses ERC-7496 for PoD facts, so editors will ask why A does not), why CAIP-19 (A-7), and why no existing reveal standard is used.
- **"Who sets the seed and commits the manifest?"** The interface has no admin functions (A-4 item 3). State it is implementation-defined and covered by events.

### Should fix — process (applies to A, B, C)

**A-20. Code outside `assets/`** — A:403, A:419 (also B:367–387, D none)

> "`contracts/test/fixtures/core-vectors.json`"; "Solidity: `contracts/src/core/`"

CONTRIBUTING §2.4: the pull request adds only the TAP file and its `assets/` files. Either move the Foundry project under `assets/tap-<short>/contracts/` or link it as a reference implementation in an external repository at a fixed commit (TAP-01 §6.2).

### Nits

- **A:399** "`permute` outputs for pool sizes from 1 to 10,000" overclaims; README lists n = 1, 2, 3, 7, 10, 255, 256, 257, 1000 plus the first 64 of 10,000. Proposed: "for pool sizes 1, 2, 3, 7, 10, 255, 256, 257 and 1,000 in full, and for 10,000 the first 64 outputs and a hash of the whole permutation".
- **A:206** "X Layer and Base are such chains at the time of writing" — give a date: "(as of 2026-10-17)".
- **A:28** "Two community write-ups" — name them with dates as background (not normative), or drop the sentence.
- **A:372** "checked on 2026-10-18" — state UTC (see B-12).
- No worked example of a `tap` object in the text; a short one (marked "Example") in §7.1 would help readers who do not open `vectors.json`.
- Reference naming: A calls D "the structural hash TAP", B and D call A "the Netlist-Bound NFTs draft", C uses `TAP-draft-netlist-bound-nft`. Use the file name form in all four until numbers are assigned.

## 3. Draft B — Moving Netlist-Bound NFTs between TapeOut chains

### Blockers

**B-1. `discussions-to` and `requires`** — B:6, B:10

> `discussions-to: TBD`; `requires: TAP-10, TAP-draft-netlist-bound-nft, ERC-721, ERC-165, ERC-4906, LayerZero V2`

`requires` takes TAP names (TAP-01 §7.1); an unnumbered draft has none, so B cannot be merged before A. "LayerZero V2" has no version. EIP-712 (§10) and EIP-7702 (§5.1) are used normatively and missing.
Proposed: submit A first; then `requires: TAP-10, TAP-<A>, ERC-165, ERC-721, ERC-4906, EIP-712, EIP-7702, LayerZero V2 EndpointV2 (deployed bytecode, code hashes in Deployments)`. Say in the PR that B waits for A's number.

**B-2. Message ids can repeat; the stated guarantee is false** — B:100

> "Because `(srcChainId, sending endpoint, nonce)` never repeats, message ids do not repeat."

The payload does not contain the sending endpoint's address. If an endpoint is replaced before sealing (a route's `peer` changes, which §7 recovery path 2 and §11 allow), the new endpoint's nonce starts at 0; the same token sent to the same recipient with the same hashes produces a byte-identical payload, and the destination rejects it as `Replay` (B:145): the token is burned or escrowed and never arrives.
Proposed: add the source endpoint to the payload (`address srcEndpoint` after `srcChainId`, making it 352 bytes) or require "A replacement endpoint MUST be deployed with an initial nonce greater than every nonce its predecessor used; `nextNonce()` of the old endpoint is read for this." Then restate: "Because `(srcChainId, srcEndpoint, nonce)` never repeats …".

**B-3. Errors are named but not specified** — B:137–148, B:192–206, B:237

> "revert (`ContractRecipient`)", "(`WrongPeer`)", "(`Replay`)", "(`NotEscrowed`)", "(`AlreadyLive`)", "(`OutOfRange`)", "(`ManifestConflict`)"

Without signatures the selectors are undefined, and the reference uses parameters (`WrongPeer(address)`, `Replay(bytes32)`, `ContractRecipient(address)`). Retry logic (§9 "Retry") depends on telling these apart.
Proposed: an errors table with full signatures and selectors in the style of TAP-10 §13.5, and add them to `vectors.json`; or "Revert data is not part of this interface" (then §9 must not rely on it).

### Should fix

**B-4. Summary calls the token a "circuit NFT"** — B:18

> "This TAP lets the owner of a circuit NFT move it …"

In TAP-10/TAP-02 terms a circuit NFT is a processor contract's token, which B does not bridge (B:352).
Proposed: "This TAP lets the owner of a netlist-bound NFT move it from the chain where it was created to another TapeOut chain and back, with its netlist and image travelling along, while making sure that only one usable copy exists at any time."

**B-5. A second, unspecified design: native burn-and-mint** — B:66

> "A native collection MAY play the gateway role itself by burning on departure and minting on return, provided it emits and accepts the payloads of this TAP"

No interface, ERC-165 reporting, state or discovery is specified (and Open question 5 asks whether to). This is the "two designs in one text" objection of #21.
Proposed: delete the sentence and Open question 5, or replace with "Native collections that burn instead of escrowing are out of scope of this version."

**B-6. The hub profile is an [Open] design with normative text** — B:289–321

The profile depends on a verifier that does not exist on chain, carries MUSTs, and has its own fee and relayer questions. Editors are likely to ask for it to be split out or made informative.
Proposed: move §10 into a separate draft ("TAP-10 hub relay adapter") or mark it "informative in this version; adapters following it are not conforming until a verifier is specified", and keep only the adapter interface (§8) normative. Keep `ALL` policy since it is layer-independent.

**B-7. Hub profile: recipient and what attesters check** — B:299, B:319

> B:299 "`to = uint32(0) ‖ uint64(dstChainId) ‖ remote adapter` (a TAP-10 §12.1 endpoint id)"; B:319 "checking that the entry's digest equals `digest` and that its `Sent` log carries `ref` and `payload`"

TAP-10 §12.1 defines the endpoint id over a container address, not an arbitrary contract; and attesters do not check the entry's `to`, so a message from the same container to another chain's adapter is not excluded by the attestation itself (only by the payload's `dstChainId`).
Proposed: "`to` is the endpoint id of the remote adapter's container (`setRemote`)"; and add to B:319 "and that the entry's `to` equals that endpoint id".

**B-8. Mirror range conflicts with A** — B:199, B:206

> "`supply` = 0 when the range is not fixed"; "`tokenRange()` = the deployed range"

A:153 requires `supply` ≥ 1. Fix in A (A-14) or here: "`supply` = 0 means unbounded; this is the bridged-copy case of the Netlist-Bound NFTs draft §8.2".

**B-9. Mirror metadata source is undefined** — B:204

> "`baseURI ‖ decimal tokenId` … The base URI is fixed at deployment. Metadata served for a mirrored token MUST identify the token by its home identifier"

Who serves that document, and must it equal the home document? For TapeCode-Test1 the home base URI is still empty, so a mirror deployed now fixes a URI before the home metadata exists.
Proposed: "The document at a mirror's `tokenURI` MUST be byte-identical to the home collection's document for the same token, or differ only in members the Netlist-Bound NFTs draft allows to differ; a mirror SHOULD NOT be deployed before the home collection's metadata location is final."

**B-10. Gateway discovery turns Deployments into a registry** — B:216, B:331

> B:216 "The canonical mirror of a collection on chain `c` is `peer` of the gateway's `route(c)`"; B:331 "A deployment is recognised by this TAP only when it is listed under Deployments."

There is no way to find a collection's gateway except this TAP's Deployments, so every collection needs a pull request against B. Expect an objection.
Proposed: define discovery from the home side (e.g. a `tap.bridge` member `{ "chainId", "gateway" }` in the home metadata, or a function on the companion), and keep Deployments for the TapeCode-Test1 endpoints only.

**B-11. Confirmations are not a number** — B:285

> "SHOULD set block confirmations at least as deep as the source chain's finality tag in TAP-10 §2.1 (`finalized` on BNB Smart Chain, `safe` on Base and X Layer)"

LayerZero ULN confirmations are a block count; a tag is not.
Proposed: give counts measured against each tag with the date, e.g. "at least N_bnb, N_base, N_xlayer blocks (the depth of `finalized`/`safe` measured on 2026-10-17)".

**B-12. Measurement date contradicts the block numbers** — B:408

> "**Measured** read-only on 2026-10-18 … X Layer blocks 73,484,955–73,486,332 … BNB Smart Chain blocks 128,201,222–128,204,265"

Block headers read from chain: BSC 128,201,222 = 2026-10-17 16:19:58 UTC, 128,204,265 = 16:42:48 UTC; X Layer 73,484,955 = 2026-10-17 16:19:51 UTC. The date is local time (UTC+8).
Proposed: "Measured read-only on 2026-10-17 between 16:19 and 16:43 UTC …". Apply the same UTC rule to A:372 and C:192.

**B-13. Roadmap and proposals inside the TAP** — B:345, B:404, B:444

> B:345 "**Recommendation.** Start with LayerZero V2 under `ONE` … add the hub route, and move high-value routes to `ALL` …"; B:404 "The authors propose that the official endpoints for TapeCode-Test1 be deployed … (for example TapeOut's 3/5 multisig …)"; B:444 "the first routes would be X Layer ↔ BNB Smart Chain"

TAP-01 §7.3 keeps roadmaps out; PR #23 asked to remove "Next steps". The deployer/owner question is the same one raised on #21.
Proposed: move all three to the pull request description. Keep in Deployments only facts: "None of the contracts of this TAP is deployed. An owner is a constructor argument; until a pull request adds an address here, clients accept no deployment." In Rationale keep one sentence: "`ONE` is the default; `ALL` exists for routes that must not trust a single layer."

**B-14. "Use an existing ERC" for the adapter** — B:340

Rationale discusses ONFT721 but not ERC-7786 (cross-chain messaging gateway, Draft), which an editor will raise for `ITapBridgeAdapter`.
Proposed: add "ERC-7786 defines a generic cross-chain gateway interface; this TAP does not use it because it is a Draft and its attributes model does not fix the payload or the policy across adapters" (or adopt it).

**B-15. Code outside `assets/`** — B:367–389. Same as A-20.

**B-16. Gateway with a data source but unbound token** — B:104

> "fill `netlistHash`, `imageHash` and `manifestHash` from `netlistHashOf(tokenId)` …"

If `bind` was never called, the token travels with zero hashes and the mirror can never serve its netlist until it returns.
Proposed: "A gateway with a data source MUST revert if `netlistHashOf(tokenId)` and `imageHashOf(tokenId)` are both zero while the data source's `masterSeed()` is non-zero; callers bind first."

### Nits

- **B:3** title capitalisation: "Moving Netlist-Bound NFTs Between TapeOut Chains" (other titles are in title case).
- **B:163** `route` returns `uint8 policy`; the Solidity interface declares an enum `Policy`. Add "(`uint8` in the ABI)".
- **B:180–186** `Departed`, `Confirmed`, `Arrived` are listed after the `ITapBridgeTransfer` table but declared in `ITapBridgeEndpoint` in the source; say which interface declares them.
- **B:92** "`to` … non-zero" is in the table but not in the strict-decoding list of B:100; add "the `to` word is non-zero".

## 4. Draft C — Proof-of-Design Attributes

### Blockers

**C-1. `discussions-to`, `requires`** — C:6, C:10

> `requires: TAP-draft-netlist-bound-nft, TAP-02, ERC-7496`

Same as B-1. C also uses TAP-10 §5 normatively (C:61, C:182). ERC-7496 has no version (see C-3).
Proposed: `requires: TAP-02, TAP-10, TAP-<A>, ERC-7496 (ethereum/ERCs at commit <hash>)`.

**C-2. `frozen` used as a token state that A abolished** — C:186, C:244

> C:186 "A collection whose token is `frozen` (TAP-draft-netlist-bound-nft §7.2) keeps its snapshot as it is."
> C:244 "Once a token is `frozen` (TAP-draft-netlist-bound-nft §7.2), its traits of §5.2 MUST NOT be written again."

A:269: "Whether content can still change is not a metadata state … Tools derive it from the chain (§8): `frozen()` at L1, or for L0 the probe the manifest names in `freeze`." Freezing is per collection, not per token.
Proposed C:186: "Once the collection is frozen (`frozen()` returns true at L1, or the manifest's `freeze` probe returns its `expect` value at L0; TAP-draft-netlist-bound-nft §7.2, §8.2), its snapshots are not replaced." Proposed C:244: "Once the collection is frozen in that sense, the traits of §5.2 MUST NOT be written again."

**C-3. Normative dependency on a moving Draft ERC** — C:192

> "had status **Draft** when read on 2026-10-18 from eips.ethereum.org and the master branch of the ethereum/ERCs repository; the names, interface identifier and schema below are those of that text"

CONTRIBUTING §4: nothing normative may depend on an external link except at a fixed commit or version.
Proposed: "This TAP uses ERC-7496 as of commit `<40-hex>` of ethereum/ERCs (`ERCS/erc-7496.md`, SHA-256 `<…>`), status Draft."

**C-4. Status 3: defined and forbidden at once** — C:122, C:132, C:160, C:356

> C:122 "`"mining"` for 1, `"restartable"` for 3, `"unknown"` for every other code"
> C:132 "Status codes other than 1 have no confirmed meaning … A tool MUST show `statusLabel` `"unknown"` together with the raw code and MUST NOT guess."
> C:356 "The meaning "restartable" for 3 comes from an observation … and could not be confirmed"

§3.7 item 3 makes the label a well-formedness rule, so implementers who follow C:132 reject vectors produced under C:122.
Proposed C:122: "`"mining"` for 1, `"unknown"` for every other code". Keep the observation about 3 in Open question 1 only.

### Should fix

**C-5. "Informative" section with requirements** — C:251–263

> "### 6. Rig reference (`tap.rig`, informative)" followed by "a tool MUST NOT present it as verified", "MUST label it", "MUST NOT be used as an input to rarity"

Proposed heading: "### 6. Rig reference (`tap.rig`)" and first sentence: "`tap.rig` is an unverified reference: …". §8 "(informative)" is fine but would sit better in Rationale.

**C-6. Collection-specific statement in a general TAP** — C:270

> "The 10,000 tokens of TapeCode-Test1 … were given out free of charge and are not backed by rigs. … a collection MUST NOT suggest otherwise."

A TAP states rules for every collection; facts and promises about one collection belong in its profile. "Given out free of charge" is also not verifiable from the text.
Proposed: delete item 4, or replace with "Example: a collection whose tokens are not backed by rigs does not become backed by adding `tap.rig`."

**C-7. `cachedDepth.live` is unknown here but used as a check in D** — C:313, C:357 against D:214

> C:313 "its third value (`live`: 4, 10, 51) is not the depth and is not used (Open questions)"
> D:214 "the 51 live elements agree with the `live` count that the PoD mining contract caches for this circuit (`cachedDepth.live` …), an independent check of §3"

D's live counts are 4, 10, 51 for the same three circuits. One package should not call the value unknown in one draft and an independent check in another.
Proposed C:313: "… its third value (`live`: 4, 10, 51) equals the number of live elements under the structural hash draft's §3 for these three circuits; this is an observation, not a published rule." Mark D:214 the same way ("observed, not documented").

**C-8. Open question 7 is answered by the package** — C:362

> "#38 … had no miner record at block 128200681. Was it a miner earlier, or is another circuit meant?"

A's vectors and D:206 state #38 contains REF records, and the mining contract rejects REF circuits.
Proposed: "Circuit #38 of Blonskr_No1 contains REF records (assets of the Netlist-Bound NFTs draft) and therefore cannot be a miner; it is kept as the no-record vector." Remove the open question.

**C-9. On-chain traits for legacy collections** — C:194

The motivating collection cannot add ERC-7496 functions; a companion is a different contract, and marketplaces read ERC-7496 from the token contract.
Proposed: add "ERC-7496 traits are read from the token contract; a companion (TAP-draft-netlist-bound-nft §8.3) cannot carry them. A legacy collection publishes `tap.pod` in metadata only."

**C-10. `cost` is a "recorded design fact" computed with a current parameter** — C:63, C:113, C:158

> C:63 "`area` and `bstar` were computed with the parameters in force at registration"; C:113 "`cost` | derived: `area` · max(`depth`, 1)^`params.beta`"

If β changed after registration, `cost` would move while `area` did not, so it is not a stable design fact; nor would it equal the cost used for the slot at registration.
Proposed: "`cost` uses β at block `B` (`params.beta`). Because the mining contract reports itself sealed since block 121,815,032 (Deployments), β cannot change by upgrade after that block; snapshots of blocks before it may use another β."

**C-11. Who writes traits** — C:243

> "`setTrait` for these keys MUST be restricted to the collection's authorised writer."

"Authorised writer" is undefined; ERC-7496 does not define it either.
Proposed: "… restricted to an account the collection designates; the collection SHOULD expose it as `owner()` (ERC-173) or document it in the trait metadata."

**C-12. Single-source reads in Test Cases** — C:301

Reads for #3151, #38 and all contract parameters came from one archive operator only. Fine for Draft; before Review (CONTRIBUTING §4) re-read with a second operator or state the limitation in the vector file.

### Nits

- **C:47** field names come from "the official PoD front end (tapeout.net/pod)", a moving website. The selectors and tuple positions make the text self-contained; add "names only; positions and selectors in §3.4 and §3.6 are normative".
- **C:233** a `decimal` trait cannot hold `cost` ≥ 2^256 (possible only for large β). Add "if a value does not fit in 256 bits the collection MUST NOT publish traits for that token".
- **C:192** date "2026-10-18": state UTC.
- **C:22** the Abstract lists every PoD member in one long sentence; consider trimming the list to a few examples.

## 5. Draft D — Structural Hash of Flat Netlists

### Blockers

**D-1. `discussions-to`** — D:6. As A-1.

**D-2. `requires` omits the draft it depends on** — D:10, D:50

> D:10 `requires: TAP-02`; D:50 "valid as defined by the Netlist-Bound NFTs draft (§2). An implementation MUST reject a file that is not valid there"

D's input format, validity rule and canonical output are `tapnet/1` from A. The preamble is incomplete (TAP-01 §7.1), and DESIGN.md §1 repeats the omission.
Proposed: `requires: TAP-02, TAP-<A>` (after A is numbered). Alternatively make D self-contained by restating the 16-byte header and the validity rule, then `requires: TAP-02` is correct.

### Should fix

**D-3. Summary overclaims** — D:18 against D:226

> D:18 "so that a collection cannot pass off one design as many"
> D:226 "Anyone can change the structural hash without changing the function, for example by inserting a double negation …"

Proposed: "This TAP gives every flat TapeOut netlist a fingerprint that stays the same when the same design is merely renumbered, reordered, padded with unused gates or duplicated, so that such copies cannot be passed off as different designs."

**D-4. Format identifier with no use** — D:122

> "The format identifier of this version is `tapsh/1`."

Nothing carries it: A §7.1 has a bare `structuralHash`. Either add a member in A (e.g. `structuralHashFormat: "tapsh/1"`) or delete the sentence; the domain tag already versions the hash (D:144).

**D-5. Observation presented as a check** — D:214. See C-7. Proposed: "… agree with the third value of `cachedDepth` that the PoD mining contract stores for this circuit, which appears to be the same count (observed for three circuits; the contract source is not published)."

**D-6. Type** — D:8 `type: Standards`. Correct in my reading (a data format that independent verifiers must reproduce byte for byte, with vectors), but expect the question since D defines no contract and only rarity tools consume it. Pre-empt in Rationale: "Standards rather than Application: two tools that count designs differently disagree on the same collection, which is an interoperability failure, not a convention."

### Nits

- **D:39** `u32(x)` while A uses `u32be(x)` for the same thing; use one name across the package.
- **D:22, D:26, D:50, D:140** "the Netlist-Bound NFTs draft" — use `TAP-draft-netlist-bound-nft` until A has a number.
- No Deployments section: correct (template marks it as required only for TAPs that depend on deployed contracts); one line "This TAP depends on no deployed contract" would answer the question before it is asked, as A:425 and C:330 do.

## 6. Cross-draft and process

### Blocker

**X-1. Submission order.** B and C cannot be merged while they `require` an unnumbered draft, and D depends on A's format. Submit A (and D, if made self-contained) first, wait for A's number, then rename references in B, C, D (`TAP-draft-netlist-bound-nft` → `TAP-<nn>`, "Netlist-Bound NFTs draft" → `TAP-<nn>`), and open B and C. Say this in each PR description.

### Should fix

**X-2. Translations in a draft PR.** TAP-01 §6.2 and the template comment ("Translations go in TAPs/TAP-<nn>.<lang>.md once the TAP has a number") and CONTRIBUTING §2.4 ("a pull request that adds only that file and its assets") mean the four `.zh.md` files should be held back until numbers are assigned, then added as `TAP-<nn>.zh.md` (TAP-02 and TAP-11 did this).

**X-3. Asset folder names and cross-imports.** `assets/tap-<short>/` must become `assets/tap-<nn>/` (TAP-01 §6.2); D's `canon.py` imports `../tap-netlist-bound-nft/tapnft.py`, which breaks on rename. Plan the rename and update the import with the number.

**X-4. Dates in UTC.** B:408 (see B-12), A:372 and C:192 say 2026-10-18 for reads whose blocks are 2026-10-17 UTC. `created: 2026-10-18` is fine.

### Nits

- Names are otherwise consistent: "netlist hash" = SHA-256 of a `tapnet/1` file; metadata member `sha256`, interface and payload `netlistHash`, manifest entry member `netlist`. A §1 defines the term once; fine.
- Block numbers are written both as `128200681` and `128,200,681` (C:66, C:301, D:206); pick one style per draft.
- DESIGN.md §1 lists D as `Requires: TAP-02` and A as not requiring ERC-173; update with D-2 and A-6 (working notes, not a TAP).

## 7. Translations

Scripted comparison (headings, heading levels and numbering, table rows and cell counts, fenced code blocks, backticked tokens, hex constants, numbers) of each `.zh.md` against its English file:

| Pair | Headings | Table rows | Code blocks identical | Backticked tokens | Hex constants | Numbers |
|---|---|---|---|---|---|---|
| A | 44 / 44 | 47 / 47 | 8 / 8 | identical | identical | EN `24.9`, `2.28` (million) = ZH `2490 万`, `228 万`: same values |
| B | 33 / 33 | 97 / 97 | 5 / 5 | identical (ZH adds its own file name in the notice line) | identical | identical |
| C | 37 / 37 | 101 / 101 | 1 / 1 | identical except one extra `bestSlot` in C.zh:289, a faithful expansion | identical | identical |
| D | 21 / 21 | 34 / 34 | 2 / 2 | identical | identical | identical |

The only other differences are the notice line ("本文是…的中文译文，仅供参考…（TAP-01 §6.2）"), as in TAP-11.zh. The key-words paragraph is translated with the English key words kept, as in TAP-11.zh; acceptable.

Spot-check of meaning (40 paragraphs, mostly normative): A.zh 76, 108, 131, 155, 172, 187, 208, 216, 239, 243, 268, 271, 282, 288, 298, 301, 343; B.zh 66, 102, 141, 147, 149, 154, 247, 251, 289, 321; C.zh 62, 67, 68, 134, 188, 243, 246; D.zh 58, 78, 97, 108, 133, 137. No meaning errors found: conditions, orders ("按以下顺序"), negations and key words are preserved, including B's departure order and C's refresh rules.

Nits (translations):

- "Collection" has three renderings: A.zh 藏品 (33×) and 集合 (A.zh:131, 133, 435), B.zh 集合 (41×), C.zh 合集 (22×), D.zh 合集 (10×) and 集合 (4×). Pick one (藏品 or 合集) for all four.
- A.zh:268 "`netlist` MUST 不出现" — prefer "`netlist` MUST NOT 出现" or "MUST 缺省" to keep the key word intact.
- When the English changes for the Blockers above, the translations must follow section by section (CONTRIBUTING §6); every fix in this report touches a normative sentence that has a ZH counterpart.

## 8. Expected editor comments, in the style of #21 and PR #23

What an editor would most likely write on the first pass, and the pre-emption:

1. "Please set `discussions-to` to the Idea issue; `requires` must name TAPs." → A-1, B-1, C-1, D-2, X-1.
2. "Translations come after the number." → X-2.
3. "Remove roadmap and deployment proposals." → B-13, C-6.
4. "Who deploys and who owns the endpoints?" → B-13 (state constructor-argument owner, no proposal), B-10 (discovery), and in the PR, the answer given on #21 as a model: CREATE2 from published init code, recognised only when listed.
5. "Two designs in one text" → B-5 (native burn), B-6 (hub profile [Open]), A one-topic paragraph (§2 "Editor objections").
6. "Use an existing ERC/spec" → A-7 (CAIP-19), A ERC-7496 paragraph, B-14 (ERC-7786); C already does this well.
7. "The Specification is not coherent" → A-2, A-3, C-2, C-4, B-2: fix these before opening the PRs; each is a contradiction an editor can point at with two line numbers.
