# TAP-721 implementer's guide

A concise guide to implementing **TAP-721 · Netlist-Bound NFT**. "TAP-721" is the proposal name; the
submission requests number 721 and the TAPs editors assign the real number. The normative text of the flagship
standard is [`TAPs/TAP-draft-netlist-bound-nft.md`](../TAPs/TAP-draft-netlist-bound-nft.md); section numbers (§)
below refer to it. Where this guide and the draft differ, the draft wins.

## The TAP-721 family at a glance

| Part | Where | What you implement |
|---|---|---|
| Core (L0 / L1) | Flagship §1–§8.2 | §1–§3 below |
| TAP-721 Companion extension | Flagship §8.3 | §4.1 below |
| TAP-721 Eval extension | Flagship §8.4 | §4.3 below |
| TAP-721 TokenSet extension | Flagship §8.5 | §4.2 below |
| TAP-721 container hosting and locking | Flagship §8.6, §7.5 | §4.4 below |
| Extension TAP B — bridging | separate TAP | §4.5 below |
| Extension TAP C — PoD attributes | separate TAP (Application) | §4.5 below |
| Extension TAP D — structural hash | separate TAP | §4.5 below |

As with ERC-721, a wallet or marketplace that implements the core can display every TAP-721 collection; the
extensions add capabilities on top and never weaken the core.

## 0. Pick a level

| You have | Target | Contract work |
|---|---|---|
| A new collection | **L1** native (reference: `contracts/src/core/TapNetlistNFT.sol`) | Implement `ITapNetlistNFT` + ERC-165 + ERC-4906 |
| An existing ERC-721 that can only change its base URI | **L0**, then optionally **L1 via a Companion** (`TapCompanion.sol`) | None for L0; deploy a companion for L1 |
| A copy of a collection on another TapeOut chain | Mirror profile of the bridging draft (`TapMirror.sol`) | See [`TAPs/TAP-draft-netlist-nft-bridging.md`](../TAPs/TAP-draft-netlist-nft-bridging.md) |

Interface identifiers (ERC-165):

| Interface | Id | Required for |
|---|---|---|
| `ITapNetlistNFT` | `0x282b67f6` | L1 |
| ERC-165 | `0x01ffc9a7` | L1 |
| ERC-4906 | `0x49064906` | L1 |
| `ITapNetlistTokenSet` | `0x3f7177c7` | L1 collections in set mode (§5.4, §8.5); optional in range mode |
| `ITapCompanion` | `0x12b40a6c` | every companion (§8.3) |
| `ITapNetlistEval` | `0xec7d7e20` | optional Eval extension (§8.4) |

The draft opens its Specification with a conformance summary table (core, conditional and optional parts);
selectors and event topics are in its Test Cases section.

## 1. Core: every conforming collection (L0 and L1)

### 1.1 Netlist files (§2)

- [ ] Files are `tapnet/1`: `"TAPNET"`, version `0x01`, reserved `0x00`, `u32be nIn`, `u32be nOut`, then TAP-02
      records — NAND (`0x00 a:u24 b:u24`, 7 bytes) and LATCH (`0x01 d:u24`, 4 bytes) only. REF makes the file invalid.
- [ ] At least one record; records valid per TAP-02 §3; file length = `16 + 7·nand + 4·latch`.
- [ ] `netlistHash = SHA-256(file)`; metrics `nIn`, `nOut`, `nand`, `latch` are derived from the file.
- [ ] From a source circuit: `"TAPNET" 01 00 ‖ u32(nIn) ‖ u32(nOut) ‖ netlist(id)` (`tapnft.file_from_chain`).
- Reference: `assets/tap-netlist-bound-nft/tapnft.py` (`check_file`, `netlist_hash`); vectors in `vectors.json`.

### 1.2 Source circuits (§3), optional per token

- [ ] If declared, `tap.source` names chain, processor, circuit id, TAP-10 name and block.
- [ ] Verifiers check `isCPU(processor)` on the factory listed by TAP-10, read `circuitInfo`/`netlist` at the
      block, rebuild the file and compare hashes; a declared container must equal `accountOf(processor, id)`.
- Provenance confers no right to the source circuit, its container or its rewards.

### 1.3 Identifier and metadata (§4, §7)

- [ ] Token id is CAIP-19: `eip155:<chainId>/erc721:<lowercase address>/<tokenId>`.
- [ ] `tokenURI` JSON keeps the usual `name`, `image`, `attributes` and adds `tap` with `v`, `id`, `state`,
      `manifest`, `image`, `netlist` (`format`, `sha256`, `bytes`, `nIn`, `nOut`, `nand`, `latch`, `uris`,
      optional `structuralHash`), `edition` when a netlist hash occurs more than once, optional `source`,
      `license`, `companion`, and optional `content` (§7.5, files in a TapeOut container).
- [ ] URI lists SHOULD hold at least one `tape://` URL (TAP-10 §3.2) and one content-addressed URI (`ipfs://`,
      `ar://`); add `https://` for marketplaces that fetch server-side. Every fetched byte is checked by SHA-256.
- [ ] Hashes are `0x` + 64 lowercase hex; addresses `0x` + 40 lowercase hex; integers ≤ 2^53 − 1.
- [ ] `state` is `unrevealed` (no `netlist`, `manifest` present) or `revealed`. Never write frozenness into metadata.
- [ ] Consistency (§7.3): every URI serves the declared bytes; `bytes` matches the metrics; revealed hashes equal
      the assigned pool entries; editions are ranked by token id starting at 1.
- Reference: `tapnft.check_metadata`, `check_editions`; example collection in `assets/tap-netlist-bound-nft/example/`.

### 1.4 Manifest, pools and reveal (§5, §6), for collections that reveal

- [ ] Publish one manifest JSON; `manifestHash = SHA-256(bytes as published)`. Never re-save the file.
- [ ] Each pool has exactly one entry per covered token; labels 1–64 printable ASCII, unique; field mask image = 1,
      netlist = 2.
- [ ] Merkle: `leaf(i) = SHA-256(0x00 ‖ u32be(i) ‖ values…)`, `node = SHA-256(0x01 ‖ l ‖ r)`, odd last node moves up.
- [ ] Non-contiguous tokens: set mode with a token-set file of ascending `u32be` ids (§5.4), published at
      `tokenSet.uris`; a token's index is its rank. Tokens outside the set get no entry, ever: serve them an
      `unrevealed` placeholder without `tap.image`/`tap.netlist`.
- [ ] Seed source declared in the manifest (drand RECOMMENDED; blockhash NOT RECOMMENDED on single-sequencer
      chains). The manifest, and every input that affects assignment or labels (pool order, rarity and filter
      rules, attribute snapshot block, token set), is fixed **before** the seed can be known. One seed, used once.
- [ ] `poolSeed = SHA-256(masterSeed ‖ u64be(chainId) ‖ address ‖ label)`; token index `x` gets entry
      `permute(poolSeed, n, x)` (4-round Feistel with cycle walking).
- Reference: `tapnft.pool_seed`, `permute`, `merkle_*`; pipeline in `tools/collection/`.

## 2. L0 checklist (metadata only, §8.1)

- [ ] All of §1 above, served from `baseURI + id`.
- [ ] Give up URI changes irreversibly (e.g. `freezeBaseURI()`) and name that probe in the manifest's `freeze`.
- [ ] Host content where it cannot silently change: content-addressed URIs, or a TapeOut container whose
      circuit is locked (`contracts/src/tools/TapContainerLock.sol`). A metadata container must not set an SPA
      fallback (a missing `meta/<id>` would return HTTP 200).
- Tools label such collections **"L0 (metadata only)"** and never as verified on chain.

## 3. L1 checklist (on-chain interface, §8.2)

- [ ] Implement `ITapNetlistNFT`, ERC-165 (reporting `0x282b67f6`, `0x01ffc9a7`, `0x49064906`) and ERC-4906.
- [ ] `manifestHash`, `masterSeed` (once non-zero) and `pools`, `tokenRange` (once set) never change; `pools()[i]`
      matches the manifest.
- [ ] `entryIndexOf` reverts before the seed, then returns `permute(...)`. For `reveal.source = none`, set
      `masterSeed` to `0xff…ff` at commit and return the index itself.
- [ ] `bind` is permissionless, verifies a Merkle proof, and is idempotent. Optionally record a whole pool in one
      or several calls after rebuilding its root on chain (`loadPool` / `loadPoolChunk` in the reference); then
      `netlistHashOf` / `imageHashOf` answer for every covered token without `bind`.
- [ ] For any source other than `none`, never record zero or `0xff…ff` as the master seed.
- [ ] `storeNetlist` accepts only known netlist hashes (bound, in a recorded pool, or arrived by bridging) and files ≤ 49,152 bytes (fits a 16,777,216-gas
      transaction); SHOULD check validity on chain (MUST with the evaluation extension).
- [ ] `frozen()` is true only when nothing that affects `tokenURI`, manifest, pools or seed can change, and never
      returns to false. A contract behind a live upgrade path is not frozen.
- [ ] Emit `MetadataUpdate` / `BatchMetadataUpdate` on commit, reveal, bind, recording a pool or token set, and freeze.
- [ ] `tokenURI` still follows §7 and agrees with the interface.
- [ ] Do not allow minting after a random seed is set (review finding M-1).
- [ ] Keep the covered range or set within what the chain can process; the reference caps it at
      `MAX_TOKENS` = 100,000 so that loading fits a 16,777,216-gas transaction.

## 4. Extensions

### 4.1 TAP-721 Companion extension: an existing ERC-721 (§8.3)

- [ ] Separate contract implementing `ITapNetlistNFT` with `collection()` = the existing contract, plus `ITapCompanion`.
- [ ] Report `0x12b40a6c`. Two-way binding: metadata carries `tap.companion`, or the collection's `owner()` calls
      `endorse()` (first success recorded permanently, later calls no effect; `endorsedBy()`).
- [ ] `frozen()` only when the companion is frozen, endorsed or named, and the existing contract can no longer
      change `tokenURI`; latch the first `true` and offer a permissionless latch.
- Note: ERC-4906 events come from the companion's address.

### 4.2 TAP-721 TokenSet extension (§5.4, §8.5)

- [ ] Implement `ITapNetlistTokenSet` (`0x3f7177c7`); `tokenRange()` returns `(0, count)`, `tokenSetHash()` the
      file hash; `entryIndexOf` reverts until the token-set file is recorded and matches `tokenSet.sha256`.
- [ ] Range-mode contracts MAY implement it too, returning zero from `tokenSetHash()`.
- Tool: `tools/tokenset/` reads `ownerOf` for every token at one pinned block to find unmovable tokens.

### 4.3 TAP-721 Eval extension (§8.4)

- [ ] `evalOf` / `evalFile` (combinational; revert on any LATCH) and `stepOf` / `stepFile` (one beat with state),
      byte-exact with TAP-02 §4–§5; revert when the file is not stored on this chain.
- Reference: `contracts/src/core/TapNetlistVM.sol`, differential-fuzzed against an independent evaluator.

### 4.4 TAP-721 container hosting and locking (§4.2, §7.5, §8.6)

- [ ] Describe files in `tap.content` (`chainId`, `container`, `name`, `paths`, optional `lock`); keep `uris`.
- [ ] After upload and checking: clear any site operator and move the circuit into a lock contract
      (`TapContainerLock`), not into its own container (that stops renewals).
- [ ] Tools derive the container from `name`, check files against `tap.*.sha256`, and show "locked" only after
      reading `ownerOf` of the circuit.

### 4.5 Extension TAPs

| Draft | Adds | Implement when |
|---|---|---|
| [Bridging](../TAPs/TAP-draft-netlist-nft-bridging.md) | Gateway / Mirror endpoints, payload v1, ONE/ALL routes | Tokens must move between TapeOut chains |
| [PoD attributes](../TAPs/TAP-draft-pod-attributes.md) | `tap.pod`, ERC-7496 traits from a fixed-block mining snapshot, `functionCheck` | Netlists come from PoD miners and you show mining facts or rank by them |
| [Structural hash](../TAPs/TAP-draft-netlist-structural-hash.md) | `tap.netlist.structuralHash` | You advertise netlist rarity (count designs, not only files) |

## 5. Checking a token (tools, §7.4)

MUST: parse metadata and apply the offline rules; fetch the netlist from `tap.netlist.uris`; check its SHA-256,
validity and metrics; display the conformance level; never show L0 as verified on chain.
SHOULD: fetch the manifest (and the token-set file in set mode), check their hashes and recompute the assignment;
verify a declared source.

```bash
python3 assets/tap-netlist-bound-nft/tapnft.py token.json manifest.json file.tapnet   # checks each file on its own
python3 tools/collection/verify_collection.py --manifest <url|file> --base-url <meta dir>/ --beacon beacon.json
```
