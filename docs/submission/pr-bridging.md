**What this pull request does:** new TAP draft — extension TAP of the TAP-721 family: *Moving Netlist-Bound NFTs between TapeOut chains* (Standards, `tap: TBD`).

**Idea issue or discussion:** #66 (family discussion); builds on the flagship in #67.

**Summary.** A lock-and-mint bridge for TAP-721 tokens in hub-and-spoke form: a gateway on the home chain escrows the token and records where it went, a mirror on each other chain mints and burns it, and at most one live token exists per id across all chains. One 320-byte payload (`messageId = keccak256(srcEndpoint ‖ payload)`), a per-route policy `ONE` or `ALL` (every listed adapter must deliver the identical payload), adapters that must be sealed before routes are sealed, a normative LayerZero V2 profile (EndpointV2 `0x1a44076050125825900e736c501f859c50fE728c`, code hashes in Deployments) and an informative TAP-10 hub profile marked **[Open]**.

**Why a separate TAP.** It depends on a message layer and upgradeable contracts; under TAP-01 §5.1 that would keep the flagship at Candidate. The first TAP-721 collection does not deploy bridging in v1.

**Files.**

- `TAPs/TAP-draft-netlist-nft-bridging.md` (normative). The Chinese translation is at https://github.com/BruceLanLan/TAP-721/blob/e4b922969521d21525940bf1dda0634c38a05b4e/TAPs/TAP-draft-netlist-nft-bridging.zh.md; per CONTRIBUTING.md §2.4 it is not in this PR and will be added as `TAP-<nn>.zh.md` after a number is assigned.
- `assets/tap-netlist-nft-bridging/`: dependency-free vector generator (own keccak) and `vectors.json` (collection keys, valid and invalid payloads, LayerZero options, EIP-712 values, selectors, interface ids, event topics); `make_vectors.py --check` reproduces it byte for byte

**Reference implementation** (background): https://github.com/BruceLanLan/TAP-721/tree/e4b922969521d21525940bf1dda0634c38a05b4e/contracts/src/bridge — `TapGateway`, `TapMirror`, `TapBridgeEndpoint`, `LayerZeroV2Adapter`, `HubRelayAdapter`, with 42 bridge tests plus review PoCs reading the same vectors. Not deployed; reviewed internally only.

Checklist for authors (editors check the same list, CONTRIBUTING.md §4):

- [x] The preamble is complete (TAP-01 §7.1); `tap: TBD` for a new draft
- [x] One topic; the Summary is one sentence
- [x] Motivation and Specification are present
- [x] RFC 2119 key words are capitalised and used only for real requirements
- [x] Nothing normative depends on an external link, except references at a fixed commit or version
- [x] I can dedicate this text to the public domain under CC0 1.0

**Open questions** (also in the draft): who runs and replaces hub attesters, and how relayers are paid.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
