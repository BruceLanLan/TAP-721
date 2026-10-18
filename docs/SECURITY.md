# Security

**Nothing in this repository is deployed or externally audited.** The contracts are reference implementations
of draft standards (TAP-721 and its extension TAPs, status Draft). They have had four internal review passes and
two final rounds (r1, r2); r2 found no high, medium or low issue, and the one accepted low finding (L-9) is
disclosed below. Do not deploy them with real value before an independent audit.

## Reporting a vulnerability

Open an issue in this repository's GitHub issue tracker. For a problem in a draft's specification (as opposed to
this code), use the Idea issue [TapeOutProtocol/TAPs#66](https://github.com/TapeOutProtocol/TAPs/issues/66)
(every draft's `discussions-to`) or the draft's PR (#67–#70). Because nothing is deployed, there are no
funds at risk and public disclosure is fine. If you believe a finding also affects a live TapeOut contract
(listed in [FACTS.md](FACTS.md)), do not post it publicly first: send a direct message to the maintainer on X
([@BruceBlue](https://x.com/BruceBlue)) or contact that contract's operators, and only describe it here once
they have had a chance to respond. Maintainer: GitHub [@BruceLanLan](https://github.com/BruceLanLan).

## Internal review summary

Source: [`reviews/security-contracts.md`](../reviews/security-contracts.md), four passes on 2026-10-18. It is an
internal review, **not an audit**. Scope: `contracts/src/` (`core/`, `bridge/`, `tools/`, `vendor/`, `interfaces/`).
Method: manual review against the drafts and DESIGN.md, PoC and fuzz tests (`contracts/test/audit/`),
read-only chain checks. Slither was not run.

**First pass:** 0 critical, 0 high, 3 medium, 9 low, 11 info. No way was found to double-mint, replay a message,
or bypass the ALL policy when the endpoint and adapter code are honest and correctly configured.

| Finding | Status |
|---|---|
| M-1 mint after reveal | Fixed (`mint` reverts once a random seed is set) |
| M-2 blockhash reveal reroll | Fixed (one-shot schedule) |
| M-3 adapters not sealed | Fixed (`ITapBridgeAdapterSealed`; `sealRoutes()` requires sealed adapters) |
| L-1 … L-8 | Fixed (endpoint recipients rejected; `messageId = keccak256(srcEndpoint ‖ payload)`; `escrowed[id]`; latched companion `frozen()`; bounded reveal delay; label checks; `MAX_FILE` lowered to 49,152 bytes; renounce only via `freeze()`/`seal()`) |
| L-9 lock depends on upgradeable TapeOut contracts | Accepted, documented in NatSpec |
| I-1 no per-chain accounting at the gateway | Fixed in the third pass: hub and spoke routing, `locationOf[id]`, release only to the departure chain |
| Other info items | Fixed, mitigated or accepted individually (see the review) |

**Second pass (re-audit):** N-1 `reveal(NO_REVEAL)` re-opened minting — fixed. N-2 gateway `NotBound` stranded
out-of-range ids — fixed in range mode (set mode: see P3-1). N-3 adapter seal did not prove the LayerZero config is
pinned — mostly fixed (see P3-2).

**Third pass** (token-set mode, pool loading, linked `TapNetlistVM`, per-route accounting):

| Finding | Severity | Status in the current code |
|---|---|---|
| P3-1 gateway `NotBound` exemption used `tokenRange()` in set mode | Low | Addressed: membership decided with `ITapNetlistTokenSet.indexOf` when the data source supports it |
| P3-2 LayerZero `seal()` accepted ULN302 NIL values (255 DVNs, `uint64.max` confirmations) | Low | Addressed: NIL values and DVN-count mismatches revert |
| P3-3 large token sets could not finish loading; `knownNetlist` scan grows with pool size | Low | Addressed: incremental (frontier) commitment for the set; `markKnown(tokenId)` |
| EIP-170 margin: `TapNetlistNFT` runtime 24,231 of 24,576 bytes | Info | Open; a CI size check is recommended |
| Linked `TapNetlistVM` runs by DELEGATECALL | Info | Deployment must link the canonical library (CREATE2, documented address and code hash) |

**Fourth pass** (re-review of the P3 fixes): P3-1 and P3-2 confirmed fixed; P3-3 fixed with `MAX_TOKENS` = 100,000
(a 100,000-id set loads within the 16,777,216-gas cap); the lock now checks its container against the opener.
Residual info: optional LayerZero DVN fields are not checked at seal. One new low finding:

| Finding | Severity | Status in the current code |
|---|---|---|
| P4-1 token-set chunks (`uint32[]` calldata) exceeded the 128 KiB mempool limit for sets above ~4,090 ids | Low (liveness) | Addressed: `loadTokenSet` / `loadTokenSetChunk` take packed `bytes` (4 bytes per id) |
| I-8 residual: lock opener not stored | Info | Addressed: `opener` is an immutable |

The P4-1 and opener changes were made after the fourth pass and were re-reviewed in the final round r2. The PoCs in
`AuditCore.t.sol`, `AuditBridge.t.sol`, `AuditFixes.t.sol`, `AuditPass3.t.sol` and `AuditPass4.t.sol` assert the
fixed behaviour.

**Final conformance round r1** ([`reviews/final-r1-conformance.md`](../reviews/final-r1-conformance.md)) checked
the code against the flagship and bridging texts. Every gap it found was resolved, in the code (`loadPool` rejects
a zero value, a commit emits ERC-4906, an adapter drops its owner only through `seal()`, a gateway requires every
manifest field) or in the text; `contracts/test/audit/AuditFinalR1.t.sol` asserts the resulting behaviour.
**Final round r2** ([`reviews/final-r2-summary.md`](../reviews/final-r2-summary.md)) found no high, medium or low
issue; three of its informational notes were applied (no duplicate ERC-4906 event on a no-reveal commit, an adapter
constructor rejects a zero owner, test names). L-9 remains accepted and disclosed (NatSpec and the trust map below).
After r2: `forge test` 198/198 in 24 suites, X Layer fork test 2/2, Python 31 / 18 / 26 (see [TESTING.md](TESTING.md)).

### Withheld review

One further review (fairness and economics of PoD-based rarity) is **withheld from this repository pending
disclosure to the TapeOut team**, because it names specific miner circuits whose netlists compute a different
function than their task's reference circuit despite being marked verified on chain. It will be published once
the TapeOut team has had the chance to respond. The general rule it motivated (rankings should require a
functional check, `functionCheck` in draft C) is in the drafts. The `verifiedButWrong` example in
`assets/tap-draft-pod-attributes/synthetic/verified-but-wrong.json` is **synthetic** (hand-built, fictional processor and
id), not chain data; no real instance is published here.

### Not in this repository

Per-token holder data from the TapeCode-Test1 owner scan (`owners.json`, `owner_classes.json`,
`transfers_sample.json`; only their SHA-256 hashes are in `tools/tokenset/README.md`) and internal working
documents (an operations handbook for the first adopter and internal reviews) are not published.

## Trust map

What a holder or integrator must trust today, from most to least contained:

| Component | Who controls it | Power | Mitigation in the drafts / code |
|---|---|---|---|
| `TapNetlistNFT` before `freeze()` | collection owner, minters | commit manifest, reveal, mint, set base URI | `freeze()` clears owner and minters; `frozen()` is read from chain, never from metadata |
| `TapCompanion` before `seal()` | companion owner; legacy collection owner endorses | bind content for an existing ERC-721 | `seal()`, `endorse()`, latched `frozen()` |
| Bridge endpoints before `sealRoutes()` | endpoint owner | change routes, policies, peers | `sealRoutes()` (no ownership transfer, so a lost key before sealing is unrepairable) |
| Bridge adapters (even after endpoint seal) | adapter owner; LayerZero delegate | before `seal()`, under ONE: release the escrowed tokens on that route's chain (the gateway tracks `locationOf`), mint non-live tokens on its mirror | Adapter `seal()` clears owner and delegate and requires pinned LayerZero libraries; `sealRoutes()` requires sealed adapters; use `ALL` on routes into the gateway; ≥ 2 required DVNs |
| LayerZero V2 | DVNs and executors pinned by the delegate before sealing; EndpointV2 owner for anything left on defaults | deliver or forge messages for the route | ALL policy with a second, independent adapter |
| TAP-10 hub relay profile | fixed K-of-N attester set | attest relayed hub messages | Marked **[Open]** until hub messages can be verified on chain |
| TapeOut processor and container beacons | processor factory/beacon owner (unsealed circuit beacon `0xf70d…991c`); container beacon owned by 3/5 multisig `0xB3D8…3138` | change `ownerOf`/transfer logic, write as any container | Out of scope for these drafts; tools should display it (L-9, I-5) |
| `SiteRegistry`, `DomainBinding` | single EOA `0xE4fc…283d` (UUPS proxies) | upgrades could add admin writes or change fees | `TapContainerLock` freezes writes and allows anyone to renew; residual trust documented |
| PoD mining contract | nobody (`owner()` = 0, sealed) | — | Implementation source not publicly verified; draft C reads values at a fixed block |
| HTTPS gateway (`tools/gateway`) | whoever runs it | serve any bytes | ≥ 2 node operators at one pinned block, SHA-256 checks; clients must re-hash content themselves |
| drand quicknet | drand League of Entropy | randomness | Round announced in the manifest before it is produced; the reference pipeline checks `randomness = SHA-256(signature)` but not the BLS signature |

## Scope notes

- `contracts/src/vendor/` (minimal ERC-721, `Owned`) is written for this project; it was in scope of the review.
- `forge-std` (submodule) is used only by tests.
- The Python and JavaScript tools were not part of the security review.
