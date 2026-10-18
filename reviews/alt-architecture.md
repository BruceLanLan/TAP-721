# Alternative architecture review: TapeCode-Test1 and the netlist-NFT drafts

Date: 2026-10-18. Scope: data model and product architecture (not editorial, not a contract audit).
Inputs read: `README.md`, `DESIGN.md` (§0 taken as ground truth), drafts A–D (English), `profiles/tapecode-test1.zh.md`,
`reviews/editorial.md`, `reviews/security-contracts.md`, `contracts/src/**`, `tools/{collection,uploader,gateway}/README.md`.
No existing file was edited. No transaction was sent. Every chain number below comes from a read-only `eth_call` / `cast` call. X Layer
reads used `https://rpc.xlayer.tech` until it returned a CloudFront 403 partway through the session, then `https://xlayerrpc.okx.com`
(blocks ~73,490,000–73,491,479). BSC reads used `https://tapeout.net/rpc`. Gas figures are from `forge test` in `contracts/`
and from one scratch test kept outside the repo. Prices assume X Layer at 0.02 gwei (1 M gas = 0.00002 OKB).

## 0. Summary

| # | Idea | Verdict | One line |
|---|---|---|---|
| 1 | **Eager pool loading**: the Companion rebuilds the netlist-pool Merkle root on chain from a packed index once, so no `bind` is needed | **ADOPT NOW** | One tx of about 60–90 M gas (≈ 0.002 OKB) replaces 20,000 `bind` txs (2.52 × 10⁹ gas). Every token can be evaluated the moment `reveal` lands |
| 2 | **Freeze `baseURI` to `ipfs://<CID>/`**. The X Layer container stays the TapeOut-native, hash-checked copy | **ADOPT NOW** (only after OKX confirms it resolves `ipfs://`) | A frozen HTTPS gateway domain is a permanent single point of failure. A frozen CID depends on no domain |
| 3 | **Do not lock 1.2.282**. Move circuit #1 to a multisig, and add a spec rule that the companion named in frozen metadata (or the first endorsement) wins | **ADOPT NOW** | After `freezeBaseURI` the TCT1 owner has no power left (selector scan). A lock only destroys the collection's native voice (hub author, `1.2.282.tape` site) |
| 4 | **drand evmnet instead of quicknet** in the manifest. A permissionless on-chain seed check comes later | **ADOPT NOW** (switch) / LATER (verifier) | evmnet is BN254, and BN254 precompiles answer on X Layer, so the seed becomes verifiable on chain. Switching costs nothing today and keeps that option open after `seal` |
| 5 | **Hybrid image**: the avatar stays `image`; a deterministic netlist die-shot renderer (hash-committed before the seed) supplies an overlay or `animation_url` | **ADOPT NOW** (renderer spec + file) / LATER (stored composites, `tap.render` in draft A) | Makes the avatar↔netlist binding visible without breaking draft A §7.3 item 1 |
| 6 | Avatar generated purely from the netlist | REJECT | Editions of 4–10 tokens would get identical pictures, and the founder asked for avatars |
| 7 | Fully on-chain SVG renderer contract | LATER | TCT1 `tokenURI` cannot point at a contract, so it is reachable only through a gateway or `eth_call`. Use is limited to games and explorers |
| 8 | One ERC-6551 TapeOut container per TCT1 token | REJECT (not feasible without a protocol change) | Opener `open()` reverts for TCT1; a registry-made account with the TapeOut implementation reverts `NotPaid`; `SiteRegistry.canEdit` returns false |
| 9 | Generic ERC-6551 account per token (inventory for games) | LATER | Registry is on X Layer (≈ 96 k gas per account, ≈ 0.019 OKB for 10,000). No implementation is deployed there, and the accounts carry no TapeOut narrative |
| 10 | **"Foundry" processor**: re-tape the ~1,794 distinct netlists as real X Layer circuits on a dedicated TapeCode processor | **LATER** (right after the deadline) | ≈ 2.4 OKB (not ≈ 330 OKB as one might fear). Every design gets a `tape://` name, native `eval`/`step`, and can be REF'd by other circuits: the strongest native narrative and game anchor |
| 11 | Live reference instead of bytes as the binding | REJECT as primary | X Layer cannot read BSC. The bytes stay authoritative; live anchors (#10, RIG voucher) are added beside them |
| 12 | **Design table** (netlistHash → source, taskId, metrics) committed before the seed | **ADOPT NOW** (data) / LATER (on-chain `DesignBook`) | Games need the task of each design on chain; today the source sits only in the off-chain JSON |
| 13 | Three gameplay mechanics on `ITapNetlistEval` (Task Trial, Clock Duel, Fab Line), rewards limited to badges, Elo and traits | LATER (contracts) / NOW (data prerequisites #1, #12) | Gas budgets of 0.2–11 M per action. No yield path |
| 14 | `evalMany` / `stepMany` in the Companion | REJECT for the Companion; LATER as a helper | `netlistFile` + `TapNetlistVM` is the real primitive, and any game can link the library. Do not delay deployment for it |
| 15 | L0 + Companion split | KEEP (with #1) | A wrapper or new collection splits the holders; L0 alone gives games nothing |
| 16 | **Fix the netlist size cap mismatch** (49,152 vs 98,304) | **ADOPT NOW (blocker)** | `build_pools.py` accepts files that the Companion will refuse to store, so those tokens could never run on chain |
| 17 | Correct draft C §6: `tap.rig` *can* be cross-checked on X Layer | ADOPT NOW (text) | Voucher `rigs(id)` returns the BSC processor and circuit id (rig #1 → processor 30 #12,400, a mining miner) |
| 18 | BSC container, or IPFS only, as the authoritative store | REJECT | BSC gas is 2.5× and on the wrong chain; IPFS-only loses the community narrative. Hashes are what is authoritative anyway |

---

## 1. Binding: netlist bytes vs live circuit vs both

**Current.** The token binds `SHA-256(tapnet/1 file)`. The source `(chain, processor, circuitId, block)` is provenance only (draft A §3).

**Alternatives examined**

| Option | What binds | On X Layer, can a contract use it? | Survives source transfer / upgrade | Verdict |
|---|---|---|---|---|
| A. Bytes (current) | file hash; bytes in Companion (SSTORE2) | yes: `netlistFile`, `evalOf` | yes (immutable code storage) | **keep** |
| B. Live reference to the BSC miner | `(56, processor, id)` | **no**: X Layer cannot read BSC without a bridge or oracle; BSC processors are beacon proxies behind an unsealed factory | no | REJECT as primary |
| C. Bytes + X Layer live anchor | hash, plus a pointer to an X Layer object that is the same design | yes | the bytes do; the anchor is "best effort" | **LATER** (#10, #17) |

**Why C, and which anchor.** Two anchors exist on X Layer today:

1. **The official RIG voucher** `0x9cfc…E520` (ERC-1967 proxy, 16 tokens). `rigs(1)` returns words equal to `0xb102…a14c` (BSC processor 30) and `0x3070` = 12,400. BSC `getMiner(minerKey(0xb102…, 12400))` returns circuitId 12,400, status 1 and verifWeight > 0, so this is a verified, mining miner. An X Layer contract can therefore match a TCT1 token's source with a voucher on chain, **if the source is on chain** (see #12). I resolved only those two words; the others (`0x6ac4f81e`, `2`) are undecoded. The proxy is upgradeable by the 3/5 multisig. The voucher has `powerHeld` / `payeeAt` (BEM accounting), so any mechanic that touches it is close to a yield claim. Cosmetic use only, LATER.
2. **A Foundry circuit** (#10): the same bytes taped out on an X Layer processor. Its `netlist(id)` can be checked against the bound hash on chain (`sha256("TAPNET"01 00 ‖ nIn ‖ nOut ‖ netlist(id))`, about 50–100 k gas per check), so the anchor is permissionless and verifiable.

**Cost / effort.** No change to draft A. The anchor lives in an extension contract. The only thing to do now is #12 (commit the source and task data before the seed).

---

## 2. Image: from the netlist, separate, or hybrid

**Constraint found in draft A §7.3 item 1.** The ERC-721 `image` MUST hash to `tap.image.sha256`, which is a pool value committed before the seed. A composite (avatar × netlist) depends on the assignment, so it cannot be committed before the seed. Therefore:

| Option | Changes | Benefit | Cost | Risk | Verdict |
|---|---|---|---|---|---|
| 2a. Netlist-only generated art | replaces 10,000 avatars | no art budget; fully deterministic | renderer only | each edition (4–10 tokens, profile §3.2) shares one picture; the founder wants avatars | **REJECT** |
| 2b. Separate avatars (current) | — | simple | 0.24–4.57 OKB of avatar storage (profile §3.6) | the link avatar↔netlist is invisible: two independent permutations | keep as base |
| **2c. Hybrid** | `image` = avatar (unchanged). New: `tapnet-render/1`, a deterministic renderer whose source SHA-256 goes into the manifest (before the seed). `animation_url` (and an informative `tap.render` member, which tools ignore today) points at the die-shot / chip-frame view of the token's netlist around its avatar | the binding becomes visible; edition-mates differ through the avatar; anyone recomputes `render(netlist)` byte for byte; no draft change | client-side rendering: one ~20–50 KB HTML/JS file, ≈ 11.5 M gas for 50 KB in the container (≈ 0.0002 OKB). Storing pre-rendered SVGs instead: 1,794 × ~15 KB ≈ 6.9 × 10⁹ gas ≈ 0.14 OKB | **(1)** The reference gateway sends `Content-Security-Policy: default-src 'none'; sandbox` on every file, so a renderer page served through it **runs no script**. Serve `animation_url` from IPFS, or add a path-scoped CSP exemption (`sandbox allow-scripts`, `connect-src` to the same gateway) to `tools/gateway`. **(2)** OKX support for HTML `animation_url` is unverified | **ADOPT NOW** (spec + file); stored composites LATER |
| 2d. Fully on-chain SVG (`svgOf(netlistHash)` view reading `netlistFile`) | new contract | most "on-chain" story | view cost is roughly a levelization pass (~300 gas/gate) plus string building (~2–5 k gas/cell): ≈ 2.5–6.5 M gas for 1,204 gates, within typical `eth_call` caps | TCT1 `tokenURI` = `baseURI + id`, so marketplaces can reach it only through a gateway; OKX handling of `data:` SVG unverified | **LATER** (explorers, games) |

**Renderer outline (deterministic, SVG text output so bytes are reproducible).** Levelize: inputs and LATCH outputs at depth 0, `depth(NAND) = 1 + max(depth(a), depth(b))`. Column = depth, row = order within its level. NAND and LATCH get fixed colours. Wires are drawn as fixed-width straight segments, capped at K per cell. Fixed palette, size and number formatting. Depth falls out of the same pass, so the renderer can also display draft C's `C = A·max(d,1)^β` as a caption.

---

## 3. One ERC-6551 container per NFT

**Checked on X Layer (read-only):**

| Check | Result |
|---|---|
| Canonical ERC-6551 registry `0x0000…6551…5758` | deployed |
| TapeOut opener `0x536a…0106`: `registry()`, `implementation()` | `0x0000…6551…5758`, `0xAC4F…2a57`; `FEE()` = **0.08 OKB** per `open` |
| `opener.accountOf(TCT1, 1)` | `0xae37…95cc` (counterfactual; `isDeployed` = false) |
| `opener.open(TCT1, 1)` simulated from the token's holder (balance overridden) | **reverts**, custom error `0x5c69a867` (not decoded) |
| Registry `createAccount(0xAC4F…, 0, 196, TCT1, 1)` | `cast estimate` succeeds: **95,889 gas** |
| That account (code overridden at its address): `token()`, `owner()` | (196, TCT1, 1), owner = token holder ✓ |
| `execute(...)` from the holder, with or without 0.0013 OKB | **reverts `NotPaid`** (the TapeOut account needs DomainBinding activation, i.e. an on-chain name, i.e. a processor circuit) |
| `SiteRegistry.canEdit(account, holder)` | **false** (sanity: `canEdit(1.2.282 container, 0x1183…)` = true) |
| DeWEB hub implementation | exposes `accountOf`, `circuitImplementation`, `circuitBeacon`: also bound to circuit containers |
| tokenbound AccountV3 / AccountProxy (`0x2D25…3358`, `0x5526…E7F`) | not deployed on X Layer |

**Conclusion.** A per-token TapeOut container (its own `tape://` site and hub endpoint) is **not feasible** without the TapeOut team changing SiteRegistry, the hub and DomainBinding (UUPS, owner EOA `0xE4fc…283d`) to accept non-processor collections. **REJECT** for this deadline. Ask TapeOut core whether a "foreign collection" container class is planned.

A generic 6551 account per token (a game inventory) needs an implementation deployment (~3–4 M gas) plus about 96 k gas per account: ≈ 0.019 OKB for all 10,000, and accounts can stay counterfactual until used. Its narrative value is low: it is not a TapeOut container. **LATER**, and only if a game needs per-token custody.

**Better native alternative: #10 (Foundry).** One real TapeOut circuit per *design*, not per token. Opening a container for a design costs 0.08 OKB (all 1,794: 143.5 OKB; the 26 mythic designs only: 2.08 OKB).

---

## 4. Where the authoritative content lives, and locking

**Principle (unchanged and correct).** The hashes are authoritative: the manifest hash, the pool roots in the Companion, and `FileSet` logs that record each path's SHA-256 in a block. Every host is just a location.

| Host | For | Against | Verdict |
|---|---|---|---|
| X Layer content container (current) | TapeOut-native; same chain; `tape://` verified reads; 0.44–4.76 OKB all-in | X Layer TapeOut contracts are "test phase, unsealed"; marketplaces need a server-side gateway | **keep as the native, authoritative copy** |
| BSC container | BSC contracts more used; next to the source miners | 0.05 vs 0.02 gwei (2.5× cost); wrong chain for the collection | REJECT |
| IPFS only | simplest | loses the "images in TapeOut containers" narrative the community asked for | REJECT |

**What `baseURI` should be when frozen (change).** The profile prefers a frozen HTTPS gateway (`https://<gw>/<name>.tape/tct1/meta/`) and falls back to an HTTPS IPFS gateway. Both freeze a **domain** forever. The TCT1 owner can never fix it afterwards, because the only owner functions are `setBaseURI` and `freezeBaseURI` (selector scan, §9). Recommendation:

- Freeze `baseURI` = `ipfs://<CIDv1 of meta/>/`, which is domain-independent. Inside each JSON, list `tap.*.uris` with `tape://` first (draft A §4.2), and keep `image` as `ipfs://…` too. The JSON is frozen along with the base URI, so an HTTPS `image` would freeze a domain as well; losing it would hide only the thumbnail, while the hash and `tape://` would still resolve.
- **Before freezing**, test that OKX resolves `ipfs://` for `tokenURI` and `image`, including the *extensionless* JSON files (`baseURI + id` has no suffix, so IPFS gateways sniff the type or serve `application/octet-stream`). `setBaseURI` is reversible until the freeze, so this can be tried during the blind-box phase. If OKX does not resolve it, fall back to the profile's choice.

**Locking the content container: keep `TapContainerLock`.** It removes the holder's power to write and keeps renewal open. An extra on-chain "upload root" in the Companion adds little: the per-path SHA-256 is already in `FileSet` logs, which a SiteRegistry upgrade cannot rewrite. REJECT as unnecessary.

**Locking 1.2.282 (profile §4 step 13): drop it (change).**
- TCT1's owner-only functions are `setBaseURI` and `freezeBaseURI`; the rest is standard ERC-721 plus `claim` (sold out). So after `freezeBaseURI`, the owner container has **no power over TCT1** (inferred from the selector scan; the source is not verified). The Companion's admin is gone after `seal`.
- The one residual power is that the legacy owner can `endorse` *another* companion (the TapCompanion natspec says so). Close it in draft A §8.3 instead: "if `tap.companion` appears in the token metadata it is authoritative; otherwise the earliest `Endorsed` event wins."
- A lock permanently kills 1.2.282's hub authorship (the collection's native broadcast identity), updates to the `1.2.282.tape` homepage, and the ability to move any assets in that container. Put circuit #1 in a multisig instead.
- Cost: zero; it removes one irreversible step. Risk: the community may read "not locked" as "not renounced". Explain in the announcement that nothing about TCT1 can change after the freeze.

---

## 5. "Miner gameplay on X Layer" with `ITapNetlistEval`

**Measured primitives** (`forge test`, this repo):

| Operation | Gas |
|---|---|
| `evalOf` popcount8, 55 gates, call level incl. file read | 30,547 (555/gate) |
| `TapNetlistVM.eval` only, 55 gates | 17,994 (327/gate) |
| `TapNetlistVM.eval` only, 1,204 gates | 322,950 (268/gate) |
| `netlistOf` 8,444 B / 49,152 B (view) | 53,315 / 976,101 |
| `entryIndexOf` n = 10,000, call level | 23,456 avg / 33,032 max (the draft's 7,000 / 16,600 are execution-only figures; state which one is meant) |

For small circuits the file read dominates. A game should therefore read `netlistFile` once and run `TapNetlistVM` itself for many vectors. No Companion change is needed (#14).

**Guardrails for all three mechanics.** Rewards are non-transferable points, Elo, badges and ERC-7496 traits on a *game* contract (the Companion is sealed). There are no entry fees into prize pools, no token emissions, no staking, and the game contract holds no assets. Copy follows draft C §7. Netlists are public, so token ownership (`TCT1.ownerOf`) is what gates play; that is the NFT's utility.

**G1: Task Trial ("boot your miner on X Layer").** Prerequisite: #12. A `TaskBook` contract stores, per task, a root of test vectors that the collection generates by evaluating the task's reference circuit (`getTask` gives `refCircuits` / `refCircuitId`), which anyone can reproduce. Do not use the mining contract's `vectorsRoot`: its leaf format is unpublished, because the implementation source is not verified. A trial samples k = 8 vectors from a seed (a future evmnet round or block) and verifies each vector's Merkle proof (~9 k gas) and evaluation. Budget: 55 gates ≈ 0.2 M gas; 1,204 gates ≈ 53 k + 8 × 330 k ≈ 2.7 M gas (≈ 0.00005 OKB); an exhaustive 256 vectors × 1,204 gates ≈ 85 M (X Layer only). Outcome: a per-token "Booted on X Layer" flag and XP. Every genuine miner passes, so this is an activation ritual and a harness. Its real use comes when *player-submitted* netlists are judged by the same TaskBook (feeds G3).

**G2: Clock Duel (sequential) and Signal Duel (combinational).** Two tokens, and a seed fixed when the challenge is accepted. For N beats, A's inputs = B's previous outputs and vice versa (bits truncated or zero-padded under TAP-02 §5). Score = popcount, or a match against a seed-derived target pattern. Edition-mates are mechanically identical, so salt the initial state with the token id. Budget: N = 16, small circuits 16 × 2 × 10–30 k ≈ 0.3–1 M gas; 1,204 gates 16 × 2 × 350 k ≈ 11 M gas. Output: Elo on chain. LATCH tokens get a natural "living" mode (the state is kept in the game contract and anyone can tick it), which the §2 renderer can show as LEDs.

**G3: Fab Line puzzles (composition).** A weekly target function is published with a test-set root. A player submits a pipeline of up to 4 tokens they hold, plus a wiring map (output bit → input bit or constant). The contract evaluates 16 sampled vectors. The leaderboard ranks by total area `A = g + λ·s` (λ = 6, the same as PoD but display only) and then depth. Budget: 4 × 100 gates × 330 × 16 ≈ 2.1 M gas plus 4 file reads. The winning pipeline flattens into a `tapnet/1` file that can be taped out on the Foundry processor (#10) as a new real X Layer circuit with its own name. This closes the loop with TapeOut's REF-composition story.

**Optional G4 (LATER, cosmetic only): Resonance.** A badge when one address holds a TCT1 token and a RIG voucher whose `rigs(v)` equals the token's source. High yield-confusion risk (§1); ship only with the draft C §7 notice.

---

## 6. Is L0 / L1 / Companion the simplest viable design?

| Alternative | Verdict | Reason |
|---|---|---|
| New L1 collection + wrapping TCT1 | REJECT | Splits holders and listings; 10,000 wrap txs; the founder wants the existing collection |
| L0 only; each game stores the mapping itself | REJECT | Every game would trust an off-chain mapping; no common source |
| **Companion with eager pool loading (#1)** | **ADOPT NOW** | Same interface; `bind` becomes an idempotent no-op for the eager pool |
| Merge image and netlist pools | REJECT | Both write-ups required independent rarities (draft A Rationale) |

**#1 in detail.** The Companion gains `loadPool(p, bytes packedIdx, bytes32[] distinctValues)`. It rebuilds leaf `SHA-256(0x00 ‖ u32be(i) ‖ value)` for i < 10,000, folds the tree with draft A §5.3, requires equality with the committed root, and stores the packed index (2 bytes per entry, SSTORE2) and the distinct values. `netlistHashOf(t)` = `values[idx[permute(poolSeed, n, t − first)]]`.

Scratch measurement (forge, 1,794 designs, 10,000 entries, Shanghai):
- `load` + root check: **88,227,487 gas** in one tx. About 40 M of that is SSTORE of the design list; with SSTORE2 instead (3 chunks) it is ≈ 55–60 M.
- `netlistHashOf`: **19,793 avg / 27,409 max**, with no `bind`.
- Calldata ≈ 77 KB, under a typical 128 KB tx-size cap (the X Layer tx-size and per-tx gas caps are **unverified**; dry-run on a fork).

The image pool has 10,000 distinct values (320 KB): ≥ 3 staging txs plus a verify tx, ≈ 115–120 M gas in total. Simpler: load **only the netlist pool** eagerly (that is what games need) and keep lazy `bind` for images.

Cost: ≈ 0.001–0.002 OKB, against 20,000 binds at 2.52 × 10⁹ gas (≈ 0.05 OKB) plus a 20,000-tx batch job on a rate-limited RPC. Trust: none added, because the root must match. Effort: 1–2 days of code and tests before the Companion is deployed (K1.5, 10-27), reusing `tapnft.py` vectors. Risk: new unaudited code on the critical path, so keep `bind` as the fallback path.

---

## 7. What the team missed

1. **Size cap mismatch (blocker).** Draft A (English) §8.2 and `TapNetlistStore.MAX_FILE` = 49,152 bytes. `tools/collection/_paths.py` (`MAX_NETLIST_BYTES = 98304`, commented "draft A §8.2"), `build_pools.py`, the `.zh.md` of A and profile §3.3 / checklist item 2 all say 98,304. Files of 49,153–98,304 bytes would be committed in the manifest but could never be stored on chain, so those tokens could never run. Set the pipeline to 49,152 before the snapshot rerun.
2. **Locking 1.2.282 achieves nothing for TCT1 and costs the native voice** (§4).
3. **Unbudgeted costs for the new content circuit and its funding.** A new circuit on processor 282 needs transistors at 0.00066 OKB each plus 0.00066 OKB per mint tx (measured: `mint(0,2)` needs 1.98 × 10¹⁵ wei, `mint(0,10)` 7.26 × 10¹⁵), plus `TAPEOUT_FEE` 0.0013 OKB (tapeout burns NAND/LATCH ERC-1155 equal to the gates, simulated), plus `open` 0.08 OKB. The holder `0x1183…843e` has **0.3324 OKB**, against 0.44–4.76 OKB of uploads. Plan the funding now.
4. **Draft C §6 is too pessimistic.** `tap.rig` can be cross-checked on X Layer through `rigs(id)` (§1). Say so, keep "informative", and add the upgradeability and yield-proximity caveats.
5. **Source and task are not on chain.** The netlist leaf commits only the hash, so a game cannot learn a token's task or source on chain. Publish a design table now (1,794 rows: netlistHash, source chain/processor/circuitId/block, taskId, task name, nIn, nOut, nand, latch, depth). Put its SHA-256 in the manifest (an unknown member, ignored by tools, committed before the seed) and deploy an immutable `DesignBook(root)` LATER. Hashing a 172 KB table on chain costs only ≈ 65 k gas in the SHA-256 precompile.
6. **Gateway CSP blocks renderer scripts** (§2): serve `animation_url` from IPFS, or add a path-scoped exemption.
7. **drand evmnet** (`bls-bn254-unchained-on-g1`, chain `04f1e906…c8c3`, period 3 s, genesis 1,727,521,075) is live (served by api.drand.sh, api2.drand.sh and the independent drand.cloudflare.com), its randomness = SHA-256(64-byte signature) (checked on round 21,579,789), and X Layer answers the BN254 precompiles (ecAdd correct; empty ecPairing = 1; 66,845 gas incl. tx). Picking evmnet in the manifest lets a later `SeedAttestor` confirm `masterSeed()` on chain without trusting the owner (estimated 0.2–0.4 M gas; the pairing floor is 113 k). `tools/collection/drand.py` assumes a 48-byte signature and must be adapted before K2 (10-28). The profile's "on-chain drand verification is too costly" holds for quicknet (BLS12-381), not for evmnet.
8. **Rarity tiers come from an unseen config** (profile §9.3). Derive them by a published formula from recorded design facts (draft C §8: `q = cRef/C` within a task, task scarcity), so "Mythic" can be checked rather than being curator opinion.
9. **RPC operational risk.** `rpc.xlayer.tech` returned a CloudFront 403 mid-session. It is the default in `tapup` and a default operator in the gateway. Add a private or independent endpoint before the upload window.
10. **X Layer per-tx limits are unverified** (gas cap and tx size) for the eager load and any big calldata. Measure on a fork.
11. **Processors on X Layer already expose `eval` / `step`** (TAP-02 native). The Companion's VM is still the right authoritative copy (processors are beacon proxies behind an unsealed factory), but this is what makes #10 cheap to exploit.

### #10 "Foundry" processor, numbers

- `createCPU(name, symbol, story, mintPrice = 0, supplyCap)` simulates successfully for `deployFee` = 0.0066 OKB (supplyCap up to 10⁹ accepted in simulation).
- On 282's transistor contract the price is `n × mintPrice + protocolFee` (0.00066 OKB per tx). With `mintPrice = 0`, all transistors cost a handful of 0.00066 OKB txs. This is inferred for a new CPU from the same implementation; verify on a fork.
- 1,794 tapeouts × 0.0013 OKB = **2.33 OKB**, plus gas for the netlist bytes (unmeasured; ~2 KB average gives ~10⁹ gas ≈ 0.02 OKB). Total ≈ **2.4 OKB**.
- By contrast, taping out on 282 itself costs 0.00066 OKB per gate, and its supplyCap is 100,000 with 201 minted: about 330 OKB at 2 KB per design, and over the cap. Do not use 282.
- Circuits are held by an ownerless vault (no second tradable asset). Containers are opened only where wanted (0.08 OKB each).
- A permissionless `FoundryIndex` maps netlistHash → circuitId after an on-chain SHA-256 check.
- Benefits: every design gets `<id>.2.<proc#>.tape`, native `eval`, REF-composability and a page site. Per-token hub messaging is still not possible.
- Effort: 3–5 days plus a fork rehearsal. Not on the 30-day path.

---

## 8. Inconsistencies noticed (for the owners)

| Where | Issue |
|---|---|
| A (en) §8.2 vs A (zh) §8.2, profile §3.3 and checklist item 2, `tools/collection/_paths.py`, `build_pools.py`, `tools/collection/README.md` | 49,152 vs 98,304 byte cap (#16) |
| A Test Cases vs measured | `entryIndexOf` 7,000/16,600 (execution) vs 23,456/33,032 (call level). Label which is meant |
| Draft C §6 | "no way to verify" vs `rigs(id)` on X Layer |
| Profile §0 / §4 step 13 | "locking 1.2.282 = renunciation" while TCT1 has no owner power left after the freeze |
| Profile §3.6 | content-circuit creation costs (open 0.08 OKB, tapeout fee, transistors) are missing from the budget |

## 9. Chain checks performed (read-only)

X Layer:
- `cast code` registry 6551 ✓, CREATE2 deployer ✓, CreateX ✓, tokenbound v3 ✗.
- Opener: `implementation` / `registry` / `FEE` / `accountOf` / `isDeployed`; `open(TCT1, 1)` simulation reverts.
- Override-code simulations of a TCT1 6551 account: `token`, `owner`, `execute` (`NotPaid`), `canEdit` false, `putFile` reverts.
- Hub implementation selectors.
- Processor implementation selectors (`tapeout`, `TAPEOUT_FEE` = 0.0013 OKB, `eval`, `step`); tapeout simulation (ERC-1155 burn).
- Factory `deployFee` = 0.0066, `protocolFee` = 0.00066, `cpuCount` = 364; `createCPU` simulation.
- Transistor `mintPrice` / `supplyCap` / `minted` and the mint price probes.
- TCT1 selector scan; RIG voucher `rigs(1)` / `bonds` / `totalPower`.
- BN254 precompiles; holder balance 0.332370 OKB at block 73,491,479; gas price 20,000,001 wei.

BSC (archive `tapeout.net/rpc`): `minerKey` / `getMiner` for processor 30 #12,400, `ownerOf`, `circuitInfo`.

drand: `/chains`, evmnet `/info`, latest beacon.

Forge: `CoreGas`, `TapNetlistEval` gas tests; scratch eager-load test (outside the repo).
