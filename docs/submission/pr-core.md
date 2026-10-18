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

🤖 Generated with [Claude Code](https://claude.com/claude-code)



