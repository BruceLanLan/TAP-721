**What this pull request does:** new TAP draft — the flagship of the TAP-721 family, *Netlist-Bound NFTs* (`tap: TBD`; number 721 requested in the Idea issue).

**Idea issue or discussion:** #66

**Summary.** An ERC-721 extension that binds each token to a verifiable, REF-free TapeOut netlist (`tapnet/1`) and an image, with one identifier (CAIP-19), one metadata member (`tap`), one fair reveal procedure (Merkle-committed manifest, drand seed, keyed permutation) and two conformance levels: L0 (metadata only) and L1 (`ITapNetlistNFT`, `0x282b67f6`). In-document extensions: Companion (`ITapCompanion`, `0x12b40a6c`), Eval (`ITapNetlistEval`, `0xec7d7e20`), TokenSet (`ITapNetlistTokenSet`, `0x3f7177c7`) and container hosting and locking. Bridging, PoD attributes and the structural hash follow as separate extension TAPs.

**Files.**

- `TAPs/TAP-draft-netlist-bound-nft.md` (normative). A Chinese translation, kept section by section in sync, is at https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/TAPs/TAP-draft-netlist-bound-nft.zh.md; following CONTRIBUTING.md §2.4 it is not in this PR and will be added as `TAP-<nn>.zh.md` once a number is assigned.
- `assets/tap-draft-netlist-bound-nft/`: Python reference implementation (`tapnft.py`, standard library only) with the TAP-02 reference `tap02_reference.py`, the vector generator, `vectors.json`, a unittest suite (31 tests) and an 8-token worked example
- `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`: read-only BNB Smart Chain snapshot at block 128,200,681 used by the vectors

**Reference implementation and tests** (background, not normative): https://github.com/BruceLanLan/TAP-721/tree/e4b922969521d21525940bf1dda0634c38a05b4e — Solidity interfaces and contracts (`TapNetlistNFT`, `TapCompanion`, `TapNetlistVM`, `TapContainerLock`), 198 Foundry tests that read the same vectors as the Python suite, and an X Layer fork test. Nothing is deployed; the contracts have had four internal review passes, not an external audit.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Notes for editors.** The text uses "TAP-721" as a proposal name and explains the number request in Motivation; we will replace it with whatever number you assign. Open questions are listed at the end of the draft.

**Update (2026-10-18).** Proofreading and format fixes pushed: asset folder renamed to `assets/tap-draft-<short-title>/` (the chain snapshot now lives in `assets/tap-draft-netlist-bound-nft/`), REQUIRED/RECOMMENDED replaced by the TAP-01 §7.2 key words, section references corrected. Vector hashes are unchanged. Reference-implementation links now point to commit `e4b9229`.

**Update (2026-10-21).** Core revision pushed, collecting the changes the companion drafts rely on; EN text and Python reference changed together, `example/` byte-identical, no interface, selector, ERC-165 id or event changed.

- **§2.5 Other netlist formats (new).** Another Standards TAP may define a netlist format. Its byte 6 and `tap.netlist.format` must differ from `tapnet/1` and from every format defined before, and its hash space must be disjoint from theirs. Pool entries, `netlistHashOf` and known hashes then carry that format's hash. A tool that does not support the format still fetches the file and rejects it if it is not a `TAPNET` file of another version; otherwise it shows the netlist, and the edition check, as **unverifiable, not invalid**, and never as verified. A format string equal to `tapnet/1` up to case or whitespace is invalid. `storeNetlist`, `netlistFile`, `netlistOf`, source verification, Eval and TAPs written for `tapnet/1` stay `tapnet/1`-only. `TAP-draft-large-netlists` (#74) defines `tapnet/2` under this hook.
- **§8.2 Mint-bound collections (new profile).** A contract that records each token id's netlist hash at most once, at mint, may implement `ITapNetlistNFT` without a manifest: no function changes a recorded hash, a burned id is never re-minted with another hash, manifest hash and seed are zero and pools empty permanently, and `frozen()` does not imply that minting has ended. §5.1, §5.2 and §8.2 item 4 are aligned; Security Considerations note that such a contract commits to no Merkle root.
- **`tap.freeze`.** An L0 collection without a manifest may name its freeze probe in `tap.freeze`; it must point at the collection's own chain and contract and be the same on every token; tools ignore it with a manifest or at L1 (§5.1, §7.1, §7.2).
- **§6.4: no editions without a manifest.** Collections without a manifest form no editions and their metadata must not contain `tap.edition`. §7.1 adds a collection-wide rule: `tap.manifest` is on every token with one hash or on none (at L1 equal to `manifestHash()`), and a mixed collection is invalid. §8.1: tools label such collections as having no manifest.
- **Rationale.** Informative tables of the `tap.*` (and manifest) names already used by other drafts (`bridge`, `pod`, `rig`, `credits`, `credential`) and of the format values taken under §2.5 (`tapnet/1`: byte 6 `0x01`, preimage starting `0x54`; `tapnet/2`: byte 6 `0x02`, preimage starting `0x03`); why `poolSeed` and `F` need no domain tag; the size-limit paragraph now points to `TAP-draft-large-netlists`. Open question 1 reworded for later formats; the staged-upload question removed.
- **Review fixes** from a second internal pass (mixed manifest collections, unknown format strings, `tap.freeze` scope, getters of fields no pool carries, mint-bound wording, L0 labelling without a manifest).

**Compatibility.** The change is **breaking for collections without a manifest**: the previous reference checker required `tap.edition` on tokens that share a netlist hash even without a manifest, and §6.4 now forbids it. For collections with a manifest the producer rules are unchanged, but tools gain two requirements (§7.2: no `tap.freeze` for a token with `tap.manifest`; §7.1: reject collections that mix tokens with and without `tap.manifest`).

**Vectors and tests.** `vectors.json` changed from `bb77433f…3fe` to `9808f32ae21d911e377de09aa9f5df862715e9d1286041033f225a54c70031e8`: one invalid vector that expected a `tapnet/2` token to be rejected (which §2.5 now forbids) is replaced in place; new sections `noManifest` and `otherFormats` (a real `tapnet/2` token from the large-netlists vectors, reported as `unverifiable`); `editions` gains collection-level failures. `tapnft.py` gains `netlist_status()`, `check_manifest_consistency()`, `check_freeze_probes()` and an `Unverifiable` result distinct from `Invalid`. `cd assets/tap-draft-netlist-bound-nft && python3 make_vectors.py && python3 test_tapnft.py`: 39 tests pass, and regeneration leaves every file byte-identical. The Chinese translation was revised in the same places and will be added as `TAP-<nn>.zh.md` once a number is assigned. The background links still point to commit `e4b9229`, which predates this revision; the text and the Python reference in this PR are authoritative.

**Ready for review.** The draft is complete: Specification, Rationale, Backwards Compatibility, Test Cases, Reference Implementation and Security Considerations are all written. Test vectors exist and the reference implementation in `assets/tap-draft-netlist-bound-nft/` reproduces them byte for byte (39 tests pass). Nothing is deployed, so Deployments has nothing to verify. The open questions are listed at the end of the draft, and none of them blocks the format review. The authors consider the draft ready for editor review now.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

