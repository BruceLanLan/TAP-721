# Changelog

All notable changes to this repository. The TAP texts are drafts; their numbers are assigned by the TAPs
editors. Dates are UTC+8.

## Unreleased

- **PoD attributes: metadata example repaired (PR #69, `2b2cc7c`).** `vectors.json`'s `metadataExample.document`
  lacked the ERC-721 `image` and `tap.image`, so the core reference check `tapnft.check_metadata` rejected it
  although Test Cases said it passed; `test_pod.py` and the family checker test both added the members before
  calling it. `make_vectors.py` now writes `example-image.png` (a 1×1 PNG from a stored deflate block, 72 bytes, SHA-256
  `47dfc2f9…`) and gives the example `image` and `tap.image {sha256, uris}`; generation runs the core check, and
  `test_pod.py` gains two tests (core check on the vector as stored, image hash and reproduction): 26 → 28 tests.
  `vectors.json` SHA-256 `ade615b1…` → `651b660886847443e0bbdd9b4cd542c1f99491f566a680fe094a3f7c9017a102`;
  `trait-metadata.json` unchanged. The family checker test uses the vector as is (47 tests). Draft EN/ZH: Test Cases,
  Reference Implementation (reference folder at `d84cd99`), `updated: 2026-10-22`.

- **Family checker (`tools/family-checker/`).** `tapfam.py`, a reference implementation of the tool-side display
  rules of the whole family: `token` (conformance level by ERC-165, manifest / mint-bound / no-manifest / bridged-copy
  classification, reveal and frozen state read from the chain per core §7.2, netlist verified / unverifiable / invalid
  with the reason per §7.4 and §2.5, structural hash v1/v2, source verification §3.2, assignment §6, editions §6.4,
  PoD snapshot display and re-verification, credit facts vs claims, credential kind labels and status), `metadata`
  (offline), `bundle` and `credential`; text and `--json` output, every line tagged with the section it implements.
  Chain access is a stdlib JSON-RPC client (read-only); `--offline` answers from `fixtures/recorded-rpc.json`, built by
  `make_fixture.py` from `chain-reads.json`, `chain-snapshot.json` and the vectors (synthetic contracts marked as such).
  `test_family_checker.py`: 47 offline tests over the vectors of every asset folder. CI runs it in the Python matrix.

- **Mint-bound collections profile implemented in Solidity (core §8.2).** New `contracts/src/core/TapMintBoundNFT.sol`:
  an L1 collection without a manifest (ERC-721 + `ITapNetlistNFT` + ERC-165 + ERC-4906 + ERC-173) that records
  the netlist hash, and optionally the image hash, of each token id at its first mint and never changes them.
  `manifestHash()`, `masterSeed()` are zero and `pools()` is empty permanently; `entryIndexOf` and `bind` revert
  (`NoManifest`); `tokenRange()` is fixed at construction (`supply` = 0 for an unbounded collection); a burned id
  can be re-minted only with the identical hashes, and `netlistHashOf` keeps answering for it; `storeNetlist`
  reuses `TapNetlistStore` with the on-chain validity check and accepts only hashes recorded at a mint (known
  after a burn too); `frozen()` latches when `freeze()` locks the base URI, does not end minting (`endMinting()`
  does) and never returns to false; ownership can be renounced only once frozen. ERC-165 does not report the
  Eval, TokenSet or Companion extensions. `contracts/test/core/TapMintBoundNFT.t.sol` adds 19 tests (16 unit and
  gas tests, 3 differential tests that read `assets/tap-draft-netlist-bound-nft/vectors.json`: `tapnet`,
  `invalidFiles`, `noManifest`); the Foundry suite grows from 198 to 217 tests in 26 suites. The core fixtures
  are unchanged. No interface, selector, ERC-165 id or event of the draft changed.

## v0.2 (draft) — 2026-10-21

This repository becomes the home of the whole TAP-721 family. All PRs are marked ready for review; numbers 721,
7007, 5375 and 5192 are requested and the TAPs editors assign the final numbers.

| Draft | Idea | PR (head) | Vectors SHA-256 |
|---|---|---|---|
| TAP-721 flagship, Netlist-Bound NFTs (revised) | [#66](https://github.com/TapeOutProtocol/TAPs/issues/66) | [#67](https://github.com/TapeOutProtocol/TAPs/pull/67) (`6a05d1b`) | `9808f32ae21d911e377de09aa9f5df862715e9d1286041033f225a54c70031e8` |
| Extension B, bridging (unchanged) | #66 | [#68](https://github.com/TapeOutProtocol/TAPs/pull/68) (`3b57b4d`) | `bcfd12c1a2f6d875ce602da32632c260afcd6c5b560a97297044f1f690224f51` |
| Extension C, PoD attributes (metadata example repaired on 2026-10-22, see Unreleased) | #66 | [#69](https://github.com/TapeOutProtocol/TAPs/pull/69) (`2b2cc7c`) | `651b660886847443e0bbdd9b4cd542c1f99491f566a680fe094a3f7c9017a102` |
| Extension D, structural hash (version 2 added) | #66 | [#70](https://github.com/TapeOutProtocol/TAPs/pull/70) (`3efe452`) | v1 `35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa`, v2 `06bd3c06961bb4d87b60d3837591696f762b78ddd931cb5eb3a31a8c4564dbe8` |
| TAP-7007, Large Netlists and Verifiable Execution (new; [own repository](https://github.com/BruceLanLan/tap-large-netlists) at `4fa0c0b`) | [#71](https://github.com/TapeOutProtocol/TAPs/issues/71) | [#74](https://github.com/TapeOutProtocol/TAPs/pull/74) (`7425789`) | `b6ba365e912f149e1ab8e292588fac7f934cdb1fa1ba6d8d1b8ac3dabfd9f2d6` |
| TAP-5375, Design Credits and Lineage for TapeOut Netlists (new) | [#72](https://github.com/TapeOutProtocol/TAPs/issues/72) | [#75](https://github.com/TapeOutProtocol/TAPs/pull/75) (`91819d8`) | `de1eda4fa7f1ca31449bb73af72a55e1f4416c00d20fd63512873858b11aae8c` |
| TAP-5192, Soulbound Netlist Credentials (new) | [#73](https://github.com/TapeOutProtocol/TAPs/issues/73) | [#76](https://github.com/TapeOutProtocol/TAPs/pull/76) (`d13582c`) | `f33709c7e436ba68d89df9adb60f3251172397d82800ab2a0b2592a8f2a64e9b` |

- **Core revision (#67).** §2.5 other netlist formats (tools show a netlist in an unsupported format as
  unverifiable, never as invalid or verified); §8.2 mint-bound collections (L1 without a manifest for a contract
  that records each token's netlist hash once, at mint); `tap.freeze` for L0 collections without a manifest; no
  editions without a manifest, and `tap.manifest` on every token or on none (§6.4, §7.1); informative tables of
  `tap.*` names and format values. Breaking for collections without a manifest (the previous checker required
  `tap.edition` there). `tapnft.py` gains `netlist_status`, `check_manifest_consistency`, `check_freeze_probes` and
  `Unverifiable`; 39 tests. No interface, selector, ERC-165 id or event changed.
- **Solidity status at v0.2:** the mint-bound collections profile (§8.2) had no reference contract in `contracts/`
  at this release (added after it, see Unreleased: `TapMintBoundNFT`). The existing contracts conform to the
  revision (they use a manifest, and `storeNetlist` accepts only `tapnet/1` files, as the revision requires); the
  Foundry suite and the core fixtures needed no change for it.
- **Structural hash version 2 (#70).** `tap-structural-hash/2` for `tapnet/2` files with ROM records, ROM read
  ports and RAM, as a conservative extension (§9 item 6, §10): files without ROM or RAM hash exactly as in version 1.
  New `canon2.py`, `make_vectors2.py`, `test_canon2.py`, `vectors2.json` (35 tests); the asset folder now holds
  unchanged copies of `tapnft.py`, `tap02_reference.py`, `tapnet2.py` and `examples.py` so that it runs on its own.
- **New drafts.** `TAPs/TAP-draft-design-credits.md` and `TAPs/TAP-draft-soulbound-credentials.md` with Chinese
  translations and their asset folders, including the Solidity reference of the soulbound credentials
  (`assets/tap-draft-soulbound-credentials/contracts/`, 29 Foundry tests). TAP-7007 is kept in its own repository.
- Chinese translations of #67, #70, #75 and #76 match the submitted English section by section, including the
  submission edits (`discussions-to`, asset paths, included copies).
- CI runs the new Python suites (structural hash v2, design credits, soulbound credentials, with `eth-account`
  for the optional cross-checks) and the soulbound Foundry tests, which link the existing forge-std submodule.
- `scripts/sync-from-drafts.sh` lists the six family drafts and aborts if the source lacks one; `docs/submission/`
  holds the live bodies of #66–#76.
- The bodies of #67–#70 still link the reference implementation at commit `e4b9229`, which predates this revision;
  the texts and reference implementations in the PRs, mirrored here, are authoritative.

## v0.1.1 (draft) — 2026-10-18

Submitted to [TapeOutProtocol/TAPs](https://github.com/TapeOutProtocol/TAPs): Idea issue
[#66](https://github.com/TapeOutProtocol/TAPs/issues/66) (number 721 requested for the flagship), flagship PR
[#67](https://github.com/TapeOutProtocol/TAPs/pull/67), extension PRs
[#68](https://github.com/TapeOutProtocol/TAPs/pull/68) (bridging), [#69](https://github.com/TapeOutProtocol/TAPs/pull/69)
(PoD attributes) and [#70](https://github.com/TapeOutProtocol/TAPs/pull/70) (structural hash). The PRs link the
reference implementation at commit `e4b9229`.

- `discussions-to` of every draft points at #66; `docs/submission/` holds the texts as posted.
- Final review round r2 (`reviews/final-r2-summary.md`): no high, medium or low issue.
- PoD vectors: the `verifiedButWrong` example is synthetic; the real instance is withheld until disclosed to the
  TapeOut team. Per-token holder data and internal working documents are not published.
- Contact: X [@BruceBlue](https://x.com/BruceBlue).

## v0.1 (draft) — 2026-10-18

First public snapshot of **TAP-721 · Netlist-Bound NFTs** and its companion drafts. Not deployed. Audited
internally only.

### Standards (`TAPs/`, English normative, Chinese translations)

Organised as the **TAP-721 family**, like ERC-721: one flagship standard with in-document extensions, plus three
extension TAPs (as ERC-4906 and ERC-7496 relate to ERC-721). Number 721 is requested for the flagship; the TAPs
editors assign the real numbers.

- **Flagship — TAP-721 · Netlist-Bound NFTs** (Standards): `tapnet/1` file format and SHA-256 netlist hash;
  source-circuit verification (`isCPU`, `circuitInfo`/`netlist`, container via `accountOf`); CAIP-19
  identifiers; the `tap` metadata member; manifest with Merkle-committed pools and token sets; drand-seeded
  keyed-permutation reveal with all assignment inputs fixed before the seed; conformance levels L0 (metadata)
  and L1 (`ITapNetlistNFT` `0x282b67f6`).
  - In-document extensions: Companion (§8.3, `ITapCompanion` `0x12b40a6c`), Eval (§8.4, `ITapNetlistEval`
    `0xec7d7e20`), TokenSet (§8.5, `ITapNetlistTokenSet` `0x3f7177c7`), container hosting and locking (§8.6).
- **Extension TAP B — Bridging** (Standards): Gateway / Mirror endpoints in hub-and-spoke, payload v1,
  `messageId = keccak256(srcEndpoint ‖ payload)`, ONE/ALL route policies, sealed adapters, LayerZero V2 and
  TAP-10 hub-relay profiles (hub profile [Open]).
- **Extension TAP C — PoD attributes** (Application): fixed-block snapshot of Proof-of-Design mining facts into
  `tap.pod` and ERC-7496 traits, including a functional check against the task's reference circuit.
- **Extension TAP D — Structural hash** (Standards): a hash of flat netlists invariant under renumbering, input
  swaps, dead and duplicated elements.

### Reference implementation

- Python reference implementations, deterministic generators and test vectors for A, B, C and D (`assets/`).
- Foundry project (`contracts/`): `TapNetlistNFT` and `TapCompanion` (shared core with `loadPool` eager pool loading),
  `TapNetlistVM`, Merkle/permutation/check libraries, bridge endpoints and adapters, `TapContainerLock`;
  198 tests in 24 suites including review PoCs and an X Layer fork test.
- Tools: collection pipeline with drand reveal and functional check (`tools/collection/`), container uploader
  (`tools/uploader/`), server-side TAP-10 gateway (`tools/gateway/`), token-set owner scan (`tools/tokenset/`).

### Reviews

- Editorial review against the TAPs editors' rules (`reviews/editorial.md`).
- Internal contract security review in four passes: first pass 0 critical / 0 high / 3 medium / 9 low / 11 info;
  medium and low findings fixed or accepted, later findings addressed (`reviews/security-contracts.md`,
  [docs/SECURITY.md](docs/SECURITY.md)).
- Alternative architecture and cross-chain trust reviews (`reviews/alt-*.md`). A fairness and economics review
  is withheld pending disclosure to the TapeOut team.

### Repository

- Submission texts (`docs/submission/`: Idea issue and four PR bodies).
- Bilingual README, implementer's guide ([docs/STANDARD.md](docs/STANDARD.md)), architecture, on-chain facts,
  testing and security docs.
- CI for the offline suites; network suites behind a manual flag.
- Licences: TAP texts and data CC0-1.0, code MIT (see [NOTICE](NOTICE)).
