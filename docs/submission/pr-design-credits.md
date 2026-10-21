**What this pull request does:** new TAP draft of the TAP-721 family (#66), *Design Credits and Lineage for TapeOut Netlists* (Application, `tap: TBD`; number 5375 requested in the Idea issue).

**Idea issue or discussion:** #72 (family discussion: #66)

**Summary.** Tools show who first put a circuit on chain as a checked fact and who says they designed it as a signed claim, and never present the second as the first. The facts layer holds the *publication fact* of a circuit (mint recipient, chain, processor, circuit id, block, transaction, log) with an exact verification procedure, and refutable *earliest known occurrence* statements by netlist hash or structural hash over a declared scope. The claims layer holds EIP-712 statements (*Credit*, *Lineage*, *Revocation*) signed by an externally owned account or an ERC-1271 account under a chain-agnostic domain. Both travel in a credit bundle, standalone or as `tap.credits` in TAP-721 metadata; display rules keep them apart. The TAP grants no royalty, payment, exclusivity or identity verification.

**Dependencies.** `requires` names `TAP-draft-netlist-bound-nft` (#67, for `tap.credits` and the metadata it extends; the `tap.*` name table of the 2026-10-21 update of #67 lists `tap.credits`) and `TAP-draft-netlist-structural-hash` (#70, for design references by structural hash). `TAP-draft-soulbound-credentials` (#73) builds on this draft.

**Files.**

- `TAPs/TAP-draft-design-credits.md` (normative). A Chinese translation, kept section by section in sync, is not in this PR (CONTRIBUTING.md §2.4) and will be added as `TAP-<nn>.zh.md` once a number is assigned.
- `assets/tap-draft-design-credits/README.md`
- `assets/tap-draft-design-credits/credits.py` (reference implementation, MIT, standard library only: keccak-256, secp256k1, EIP-712, verification, revocation, publication facts, earliest occurrences, anchors, display order)
- `assets/tap-draft-design-credits/make_vectors.py`, `test_credits.py`
- `assets/tap-draft-design-credits/vectors.json` (SHA-256 `de1eda4fa7f1ca31449bb73af72a55e1f4416c00d20fd63512873858b11aae8c`)
- `assets/tap-draft-design-credits/chain-reads.json`, `occurrences.json`: recorded read-only reads of the worked example (BNB Smart Chain block 128,542,889 on three operators; X Layer block 73,638,715 on two) and the occurrence scan of processors 30 and 635; no transaction was sent
- `assets/tap-draft-design-credits/fetch_reads.py`, `scan_occurrences.py`: the scripts that recorded them (network, read-only; not needed to run the tests)
- `assets/tap-draft-design-credits/canon.py`, `tapnft.py`, `tap02_reference.py`: unchanged copies from #70 and #67 so that the folder runs on its own (origin and SHA-256 in the README)

All private keys in `vectors.json` are public test keys (`keccak256("tap-design-credits test key <n>")`).

**Reproduce** (Python 3.9+, standard library only; optional cross-checks use pycryptodome, eth_keys, eth_account and Foundry `cast` when installed):

```
cd assets/tap-draft-design-credits
python3 make_vectors.py --check && python3 test_credits.py
```

Measured on this branch with every optional cross-check installed: `vectors.json up to date`, `426 checks passed; vectors.json sha256 de1eda4f…ae8c` (427 with the translation present, which adds one Appendix A check).

**Reference implementation.** In this repository, under `assets/tap-draft-design-credits/`. No contract is part of this draft; the credit log of §5.2 is an informative pattern.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Notes for editors.** We request number **5375** (proposal name TAP-5375), mirroring ERC-5375, which lets NFT authors give EIP-712 signed consent to being named and states that consent is not proof of authorship; this draft applies the same idea to TapeOut netlists. The Motivation explains the request; the file keeps `tap: TBD` and the name `TAP-draft-design-credits`, and any number the editors assign replaces it. Appendix A quotes a test vector verbatim; its display name contains non-ASCII characters on purpose (a Unicode test case). Open questions are listed at the end of the draft.

**Ready for review.** The draft is complete: Specification, Rationale, Backwards Compatibility, Test Cases, Reference Implementation and Security Considerations are all written. Test vectors exist and the reference implementation in `assets/tap-draft-design-credits/` reproduces them byte for byte (426 checks pass). Nothing is deployed, so Deployments has nothing to verify. The open questions (REF circuits once a flattening rule exists, a shared credit log, signed earliest-occurrence statements, ERC-6492, the TAP-02 description of `nextId()`, further roles) are listed, and none of them blocks the format review. The authors consider the draft ready for editor review now.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

