<!--
PR body for TapeOutProtocol/TAPs — extension TAP D. Title: "Add TAP-draft-netlist-structural-hash: structural hash of flat netlists (TAP-721 extension)"
Placeholders: #<ISSUE>, <COMMIT>, <CORE_PR>.
Files: TAPs/TAP-draft-netlist-structural-hash.md, TAPs/TAP-draft-netlist-structural-hash.zh.md, assets/tap-netlist-structural-hash/.
Before opening: set `discussions-to`; make the Summary one sentence (it currently has two); substitute the flagship's number in
`requires` if assigned.
-->

**What this pull request does:** new TAP draft — extension TAP of the TAP-721 family: *Structural Hash of Flat Netlists* (Standards, `tap: TBD`).

**Idea issue or discussion:** #<ISSUE> (family discussion); builds on the flagship in <CORE_PR>.

**Summary.** A canonical form and hash for flat (REF-free) TapeOut netlists that stays the same when a design is renumbered, has NAND inputs swapped, is padded with dead elements or has elements duplicated, so that copies cannot be passed off as different designs. TAP-721 tokens may declare it as `tap.netlist.structuralHash`, letting indexers count designs and not only files.

**Why a separate TAP.** It specifies an algorithm that may evolve and depends only on TAP-02; it is useful for any netlist, not only for NFTs.

**Files.**

- `TAPs/TAP-draft-netlist-structural-hash.md` and `.zh.md`
- `assets/tap-netlist-structural-hash/`: reference implementation `canon.py` (MIT, imports the flagship's `tapnft.py` and `tap02_reference.py` unchanged), deterministic generator, `vectors.json` (37 cases and 3 mainnet circuits; SHA-256 `35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa`) and a test suite (18 tests)

An independent implementation written only from the Specification reproduced every vector (`reviews/editorial.md` in the reference repository).

**Reference implementation** (background): https://github.com/BruceLanLan/TAP-721/tree/<COMMIT>/assets/tap-netlist-structural-hash

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [ ] One topic; the Summary is one sentence (to fix before opening: the Summary has two sentences)
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Open questions** (also in the draft): a quasi-linear canonical labelling of the feedback region, a flattening rule for REF circuits, a second pin-order-free hash, and named sound simplifications as a separate hash.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
