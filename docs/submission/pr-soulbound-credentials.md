**What this pull request does:** new TAP draft of the TAP-721 family (#66), *Soulbound Netlist Credentials* (Standards, `tap: TBD`; number 5192 requested in the Idea issue).

**Idea issue or discussion:** #73 (family discussion: #66)

**Summary.** Non-transferable TAP-721 tokens (ERC-5192 locked, netlist bound at mint, L0 collections without a manifest) that record a skill, a result or a contribution together with a netlist, and always say whether the credential was **proven** by an on-chain check (a LATCH-free netlist of at most 16 inputs against a committed specification, by truth-table hash within published work bounds, commit-reveal per committer, an optional design key equivalent to the structural hash), **attested** by a named issuer (EIP-712, EOA or ERC-1271, expiry and revocation) or **claimed** by its holder. Consent of the recipient for every mint, renouncing at any time, re-issue instead of transfer (with a delay and veto for proven credentials). Interfaces `ITapCredential` (`0x5558759c`), `ITapCredentialProven` (`0x07aaf2dc`), `ITapCredentialAttested` (`0x7587c9da`), `ITapCredentialClaimed` (`0x11e35684`); the `tap.credential` metadata member; display rules; explicit non-claims (no income, tokens, rewards or other payment).

**Dependencies.** `requires` names `TAP-draft-netlist-bound-nft` (#67: metadata, §6.4 no editions without a manifest, and the `tap.*` name table, all in the 2026-10-21 update of #67) and `TAP-draft-design-credits` (#72: claim scopes and the statements a claimed credential carries).

**Files.**

- `TAPs/TAP-draft-soulbound-credentials.md` (normative). A Chinese translation, kept section by section in sync, is not in this PR (CONTRIBUTING.md §2.4) and will be added as `TAP-<nn>.zh.md` once a number is assigned.
- `assets/tap-draft-soulbound-credentials/README.md`
- `assets/tap-draft-soulbound-credentials/soulbound.py` (reference implementation, MIT, standard library only, including an executable model of the reference contract)
- `assets/tap-draft-soulbound-credentials/make_vectors.py`, `test_soulbound.py`
- `assets/tap-draft-soulbound-credentials/vectors.json` (SHA-256 `f33709c7e436ba68d89df9adb60f3251172397d82800ab2a0b2592a8f2a64e9b`; synthetic data, public test keys only)
- `assets/tap-draft-soulbound-credentials/canon.py`, `tapnft.py`, `tap02_reference.py`, `credits.py`: unchanged copies from #70, #67 and the Design Credits draft so that the folder runs on its own (origin and SHA-256 in the README)
- `assets/tap-draft-soulbound-credentials/contracts/`: Solidity reference (`src/SoulboundNetlistCredential.sol`, `src/TapCredentialCheck.sol`, `src/interfaces/ITapCredential.sol`, `src/vendor/`), Foundry tests (`test/`), `foundry.toml`, `.gitignore`. forge-std is not included; the README says how to install v1.17.0 locally without a submodule.

**Reproduce.** Python 3.9+, standard library only (optional cross-checks with `eth_account` and Foundry `cast` when installed):

```
cd assets/tap-draft-soulbound-credentials
python3 make_vectors.py --check && python3 test_soulbound.py
```

Foundry (Solidity 0.8.28; the tests read `../vectors.json`):

```
cd assets/tap-draft-soulbound-credentials/contracts
git clone --depth 1 --branch v1.17.0 https://github.com/foundry-rs/forge-std lib/forge-std
forge test
```

Measured on this branch: `vectors.json up to date`; `test_soulbound.py` OK (21 test functions, 3,250 checks, optional cross-checks installed); `forge test --offline` with forge-std 1.17.0: 29 tests passed, 0 failed, 0 skipped (6 suites).

**Reference implementation.** In this repository, under `assets/tap-draft-soulbound-credentials/`. Not deployed; reviewed internally; not externally audited.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Notes for editors.** We request number **5192** (proposal name TAP-5192), mirroring ERC-5192 (minimal soulbound NFTs), which every credential contract implements. The Motivation explains the request; the file keeps `tap: TBD` and the name `TAP-draft-soulbound-credentials`, and any number the editors assign replaces it. Open questions are listed at the end of the draft.

**Ready for review.** The draft is complete: Specification, Rationale, Backwards Compatibility, Test Cases, Reference Implementation and Security Considerations are all written. Test vectors exist and the reference implementation in `assets/tap-draft-soulbound-credentials/` reproduces them byte for byte (Python: 3,250 checks; Solidity: 29 Foundry tests replaying the same vectors). Nothing is deployed, so Deployments has nothing to verify. The open questions (the mint-bound profile and L1, a gasless consent path, ERC-5484, a large-netlist interface, the rebind delay as a specification field, a registry of contract code hashes, on-chain agent registry links) are listed, and none of them blocks the format review. The authors consider the draft ready for editor review now.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

