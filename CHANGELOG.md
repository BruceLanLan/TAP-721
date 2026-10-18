# Changelog

All notable changes to this repository. The TAP texts are drafts; their numbers are assigned by the TAPs
editors. Dates are UTC+8.

## v0.1.1 (draft) — 2026-10-18

Submitted to [TapeOutProtocol/TAPs](https://github.com/TapeOutProtocol/TAPs): Idea issue
[#66](https://github.com/TapeOutProtocol/TAPs/issues/66) (number 721 requested for the flagship), flagship PR
[#67](https://github.com/TapeOutProtocol/TAPs/pull/67), extension PRs
[#68](https://github.com/TapeOutProtocol/TAPs/pull/68) (bridging), [#69](https://github.com/TapeOutProtocol/TAPs/pull/69)
(PoD attributes) and [#70](https://github.com/TapeOutProtocol/TAPs/pull/70) (structural hash). The PRs link the
reference implementation at commit `23dc425`.

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
  testing and security docs; introductory article in `docs/article/`.
- CI for the offline suites; network suites behind a manual flag.
- Licences: TAP texts and data CC0-1.0, code MIT (see [NOTICE](NOTICE)).
