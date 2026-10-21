**What this pull request does:** new TAP draft, *Large Netlists and Verifiable Execution* (Standards, `tap: TBD`; number 7007 requested in the Idea issue). It relates to the TAP-721 family (#66, #67) but does not require it.

**Idea issue or discussion:** #71

**Summary.** The `tapnet/2` netlist format (TAP-02 NAND and LATCH records plus a mask-ROM record `0x10`, ROM read ports `0x13` and RAM read and write ports `0x11` / `0x12`, files up to 64 MiB, no REF), the chunked netlist hash `netlistHash2 = SHA-256(0x03 ‖ u64be(length) ‖ chunkRoot)` over 16,384-byte chunks with an optional staged on-chain store `ITapLargeNetlistStore` (ERC-165 `0x8230af7f`), and the commitments, canonical segmentation, one-step verifiers (`verify_segment`, `verify_beat_end`, fixed witness encoding) and dispute rules that let a contract settle disagreements about runs of netlists far larger than one transaction. It requires TAP-02 and ERC-165 only.

**Dependencies.** The informative §8 (use with netlist-bound NFTs) relies on §2.5 "Other netlist formats" of `TAP-draft-netlist-bound-nft`, proposed in the 2026-10-21 update of #67 and not yet merged; nothing normative in this draft depends on it. Version 2 of the structural hash (#70, updated) is defined for `tapnet/2` files of this draft.

**Files.**

- `TAPs/TAP-draft-large-netlists.md` (normative). A Chinese translation, kept section by section in sync, is not in this PR (CONTRIBUTING.md §2.4) and will be added as `TAP-<nn>.zh.md` once a number is assigned.
- `assets/tap-draft-large-netlists/README.md`
- `assets/tap-draft-large-netlists/tapnet2.py` (reference implementation, MIT, standard library only)
- `assets/tap-draft-large-netlists/bisect_sim.py` (the dispute of §7 between simulated parties, with the claim layer of §7.1)
- `assets/tap-draft-large-netlists/examples.py`
- `assets/tap-draft-large-netlists/make_vectors.py`
- `assets/tap-draft-large-netlists/test_tapnet2.py` (50 tests)
- `assets/tap-draft-large-netlists/test_ram.py` (18 tests)
- `assets/tap-draft-large-netlists/vectors.json` (SHA-256 `b6ba365e912f149e1ab8e292588fac7f934cdb1fa1ba6d8d1b8ac3dabfd9f2d6`)

The folder imports nothing outside itself except the optional independent TAP-02 evaluator `assets/tap-02/reference.py`, which is already in this repository.

**Reproduce** (Python 3.9+, standard library only):

```
cd assets/tap-draft-large-netlists
python3 make_vectors.py --check && python3 test_tapnet2.py && python3 test_ram.py
```

Measured on this branch: `vectors.json matches sha256: b6ba365e…f2d6`, 50 tests OK, 18 tests OK (68 tests, none skipped).

**Reference implementation** (background, not normative): https://github.com/BruceLanLan/tap-large-netlists at commit `4fa0c0baf2c1d226b38814aed0d0f58c244cad24`: Solidity store, verifiers and an informative dispute game, including RAM ports and ROM read ports (89 Foundry tests, including 118 end-to-end dispute scenarios and every vector replayed with the same result as the Python reference), a game-cartridge demo, and the measurements of Appendix B. Not deployed; reviewed internally; not externally audited.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Notes for editors.** We request number **7007** (proposal name TAP-7007), mirroring ERC-7007, which standardises verifiable AI-generated content settled by zkML or opML proofs with a challenge period; this draft provides the same kind of settlement for runs of TapeOut netlists. The Motivation explains the request; the file keeps `tap: TBD` and the name `TAP-draft-large-netlists`, and any number the editors assign replaces it. Open questions are listed at the end of the draft.

**Ready for review.** The draft is complete: Specification, Rationale, Backwards Compatibility, Test Cases, Reference Implementation and Security Considerations are all written. Test vectors exist and the reference implementation in `assets/tap-draft-large-netlists/` reproduces them byte for byte (68 tests pass). Nothing is deployed, so Deployments has nothing to verify. The open questions (ROM opcode coordination with TAP-02, the structural-hash treatment of ROM, which #70 now answers in its version 2, adoption of the §2.5 hook of #67, budget values, the dispute game as a separate Application TAP, initial memory contents, invalidity and input-inconsistency proofs, dispute eligibility of mint-bound collections) are listed, and none of them blocks the format review. The authors consider the draft ready for editor review now.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

