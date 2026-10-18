**What this pull request does:** new TAP draft — extension TAP of the TAP-721 family: *Proof-of-Design Attributes for Netlist-Bound NFTs* (Application, `tap: TBD`).

**Idea issue or discussion:** #66 (family discussion); builds on the flagship in #67.

**Summary.** How a TAP-721 token whose netlist comes from a BEM miner circuit records that circuit's Proof-of-Design facts as a labelled snapshot at a pinned BNB Smart Chain block (`tap.pod`, split into stable facts and volatile `standing`), optionally exposed as ERC-7496 traits (pinned to ethereum/ERCs commit `b7520ddde9f659fa40cda2e0849d987a4ff88bf5`), with a functional check against the task's reference circuit so that "verified on chain" is never shown as "correct". It adds members and rules only; nothing in the flagship is weakened, and it makes no claim that a token earns or owns anything.

**Why a separate TAP.** It is an application convention on top of the flagship (TAP-01 §3) and depends on the BNB Smart Chain mining contract `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46`, whose implementation source is not publicly verified.

**Files.**

- `TAPs/TAP-draft-pod-attributes.md` (normative). The Chinese translation is at https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/TAPs/TAP-draft-pod-attributes.zh.md; per CONTRIBUTING.md §2.4 it is not in this PR and will be added as `TAP-<nn>.zh.md` after a number is assigned.
- `assets/tap-draft-pod-attributes/`: snapshot tool (`pod_snapshot.py`), validator (`pod_validate.py`), functional check (`function_check.py`), recorded reads under `raw/`, `vectors.json`, `trait-metadata.json`, and a test suite (26 tests, no network) that regenerates the vectors byte for byte

**Asset dependency.** The scripts in this folder import `assets/tap-draft-netlist-bound-nft/` and read `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`, which are added by #67; run the tests after #67 is merged (or on a checkout of both branches).

**Reference implementation** (background): https://github.com/BruceLanLan/TAP-721/tree/e4b922969521d21525940bf1dda0634c38a05b4e/assets/tap-draft-pod-attributes and `tools/collection/verify_function.py`.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Open questions** (also in the draft): meaning of status codes other than 1, the unverified mining implementation, naming `refArea` as K_task, whether `taskId` is stable across restarts, sequential-check semantics, a rig-voucher mapping, and repeating single-operator reads with a second archive operator before Review.

**Update (2026-10-18).** Proofreading and format fixes pushed: asset folder renamed to `assets/tap-draft-<short-title>/` (the chain snapshot now lives in `assets/tap-draft-netlist-bound-nft/`), REQUIRED/RECOMMENDED replaced by the TAP-01 §7.2 key words, section references corrected. Vector hashes are unchanged. Reference-implementation links now point to commit `e4b9229`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)



