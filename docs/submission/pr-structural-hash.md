**What this pull request does:** new TAP draft — extension TAP of the TAP-721 family: *Structural Hash of Flat Netlists* (Standards, `tap: TBD`).

**Idea issue or discussion:** #66 (family discussion); builds on the flagship in #67.

**Summary.** A canonical form and hash for flat (REF-free) TapeOut netlists that stays the same when a design is renumbered, has NAND inputs swapped, is padded with dead elements or has elements duplicated, so that copies cannot be passed off as different designs. TAP-721 tokens may declare it as `tap.netlist.structuralHash`, letting indexers count designs and not only files.

**Why a separate TAP.** It specifies an algorithm that may evolve and depends only on TAP-02; it is useful for any netlist, not only for NFTs.

**Files.**

- `TAPs/TAP-draft-netlist-structural-hash.md` (normative). The Chinese translation is at https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/TAPs/TAP-draft-netlist-structural-hash.zh.md; per CONTRIBUTING.md §2.4 it is not in this PR and will be added as `TAP-<nn>.zh.md` after a number is assigned.
- `assets/tap-draft-netlist-structural-hash/`: reference implementation `canon.py` (MIT, imports the flagship's `tapnft.py` and `tap02_reference.py` unchanged), deterministic generator, `vectors.json` (37 cases and 3 mainnet circuits; SHA-256 `35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa`) and a test suite (18 tests)

An independent implementation written only from the Specification reproduced every vector (`reviews/editorial.md` in the reference repository).

**Asset dependency.** The scripts in this folder import `assets/tap-draft-netlist-bound-nft/` and read `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`, which are added by #67; run the tests after #67 is merged (or on a checkout of both branches).

**Reference implementation** (background): https://github.com/BruceLanLan/TAP-721/tree/e4b922969521d21525940bf1dda0634c38a05b4e/assets/tap-draft-netlist-structural-hash

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Open questions** (also in the draft): a quasi-linear canonical labelling of the feedback region, a flattening rule for REF circuits, a second pin-order-free hash, and named sound simplifications as a separate hash.

**Update (2026-10-18).** Proofreading and format fixes pushed: asset folder renamed to `assets/tap-draft-<short-title>/` (the chain snapshot now lives in `assets/tap-draft-netlist-bound-nft/`), REQUIRED/RECOMMENDED replaced by the TAP-01 §7.2 key words, section references corrected. Vector hashes are unchanged. Reference-implementation links now point to commit `e4b9229`.

**Update (2026-10-21).** Version 2 of the structural hash pushed, for the `tapnet/2` format of `TAP-draft-large-netlists` (#74).

- **§9 item 6.** A later version may keep the label prefix `TAPSH1` only if it is a **conservative extension**: it leaves the canonical file and the structural hash of every input that has a version-1 hash unchanged, adds only new label tags for new record kinds, leaves every file with records it does not define without a structural hash, and uses a new domain tag for canonical files that contain the new kinds.
- **§9 item 2** aligned with the core revision of #67: `structuralHash` is defined for formats and files for which this TAP defines one, next to `sha256` or the member that replaces it under core §2.5.
- **New §10 `tap-structural-hash/2`** (10.1–10.11), a conservative extension: ROM records, ROM read ports and RAM ports become nodes (one ROM column per output bit, after a label-driven pin reduction; each RAM bank bit is a plane refined like a LATCH, with its write list). A file without a live ROM or RAM node hashes exactly as in version 1 (`tapnet/1` canonical file, domain `/1`), so the output for files without ROM/RAM is unchanged; canonical files with ROM or RAM nodes use the domain `tap-structural-hash/2`. Files with records §10 does not define are rejected. Rationale, Backwards Compatibility, Test Cases, Reference Implementation and three new open questions added; `requires` adds `TAP-draft-large-netlists`.
- **Assets.** New `canon2.py`, `make_vectors2.py`, `test_canon2.py` and `vectors2.json` (SHA-256 `06bd3c06961bb4d87b60d3837591696f762b78ddd931cb5eb3a31a8c4564dbe8`). Version-1 files and `vectors.json` (`35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa`) are unchanged. The folder is now self-contained: it holds unchanged copies of `tapnft.py` and `tap02_reference.py` (#67) and of `tapnet2.py` and `examples.py` (`TAP-draft-large-netlists`), with origin and SHA-256 in its README, so the "Asset dependency" note above no longer applies and the tests run on this branch alone.

`cd assets/tap-draft-netlist-structural-hash && python3 make_vectors.py && python3 test_canon.py && python3 make_vectors2.py --check && python3 test_canon2.py`: 18 + 35 tests pass, both vector files reproduce byte for byte. The Chinese translation was revised in the same places and will be added as `TAP-<nn>.zh.md` once a number is assigned.

**Ready for review.** The draft is complete: Specification, Rationale, Backwards Compatibility, Test Cases, Reference Implementation and Security Considerations are all written. Test vectors exist and the reference implementation in `assets/tap-draft-netlist-structural-hash/` reproduces them byte for byte (53 tests pass: 18 for version 1, 35 for version 2). Nothing is deployed, so Deployments has nothing to verify. The open questions are listed at the end of the draft, and none of them blocks the format review. The authors consider the draft ready for editor review now.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

