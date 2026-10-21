> Copied from the working folder by `scripts/sync-from-drafts.sh`; repository paths are rewritten to resolve from `docs/`.

> Copied from the working folder by [`scripts/sync-from-drafts.sh`](../scripts/sync-from-drafts.sh); repository paths are rewritten to resolve from `docs/`.
>
> These are the working notes used while the drafts were written (status of the drafts: Draft, submitted
> 2026-10-18 as TapeOutProtocol/TAPs#66–#70). Where they differ from the drafts in [`TAPs/`](../TAPs/), the drafts and
> [ARCHITECTURE.md](../ARCHITECTURE.md) win; §8 in particular has been superseded on two points (noted there).

# Design contract for the netlist-NFT TAP drafts (working notes, not a TAP)

Every agent working in `tap-drafts/` follows this file. If something here is wrong or missing, say so
in your report instead of silently diverging. English is used for all normative text and code; the
user-facing Chinese translations come last.

## 0. Ground truth already established (do not re-derive, do not contradict)

- TapeOut chains = TAP-10 §2.1 chain table: BNB Smart Chain 56 (no area code), Base 8453 (area code 3),
  X Layer 196 (area code 2). New chains are appended by TAP-10, never by these drafts.
- Netlist format = TAP-02: records NAND `0x00 a:u24 b:u24` (7 bytes), LATCH `0x01 d:u24` (4 bytes),
  REF `0x02 …`. Signals: 0 = const 0, 1 = const 1, 2..2+nIn-1 inputs, then element outputs.
  Read-only processor functions: `circuitInfo(uint256)` → (nIn, nOut, nState, gateCount),
  `netlist(uint256)` → bytes. TAP-02 reference implementation: [`assets/tap-draft-netlist-bound-nft/tap02_reference.py`](../assets/tap-draft-netlist-bound-nft/tap02_reference.py).
- PoD mining (BSC only) bans REF in miner circuits, so every BEM miner netlist is REF-free.
  Mining contract `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46` (ERC-1967 proxy; `owner()` = 0 and `isSealed()` = true since block 121,815,032 — renounced via a 48 h timelock; implementation `0xa3dbe873…f898`, source not publicly verified).
  `getMiner(minerKey(circuits,id))` returns (circuits, circuitId, taskId, gateCount, stateCount, depth, area,
  mult, since, status, registrant, nandBurn, latchBurn, bstar, bonus, optimal, commitBlock, firstUnusedId,
  stopBlock, verifWeight, unverWeight, debt). Formula (tapeout.net/pod): b* = n + λ_burn·m; A = g + λ·s;
  C = A·max(d,1)^β; q = clamp(C_ref/C, 1/Q, Q); H = (b* + K_task·q)·P. Getters `lambda()`, `beta()`,
  `lambdaBurn()`, `processorMultiplier(address)`, `getTask(uint32)`. Observed: status 1 = mining;
  verified ⇔ verifWeight > 0. Community shorthand "C/N/L" = 电容 (Container), NAND, LATCH — the three TapeOut primitives (confirmed by the user 2026-10-18; "电容" is the community nickname for a TapeOut container). An earlier inference (C = design cost) was wrong.
- Official rig bridge already live: BSC vault `0x48D43345656f0f9510dC3c06CBa99dFf597617C2` (one EIP-1167 escrow
  per rig), X Layer voucher `0x9cfc959cd42B2e1d39a0d850c528210E818AE520` ("TapeOut Rig"/RIG, proxy, owner
  `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138`), messages over LayerZero V2, endpoint
  `0x1a44076050125825900e736c501f859c50fE728c`, eids BSC 30102, X Layer 30274. BEM OFT on X Layer
  `0x60e62Efa9405d6873C5deaBD4E6CC91c25363952`, BSC BEM bridge `0xa84B8D3893De6e9922f2B29bE1e1b115845F5E72`.
- TAP-10 DeWEB hub (`0xe61A9C7213a6Aa616C246a2B569e555B417b25ee`, same on every chain) stores a message
  only on the sender's chain (inbox + outbox + `Sent` event, payload ≤ 16,000 bytes, author = a circuit's
  container, writer = current circuit holder). It delivers nothing to another chain; a destination contract
  cannot read it without a relayer plus some proof/attestation.
- TapeCode-Test1: X Layer `0x0e91460d6823c711643e650a9a4c0cc21de41614`, name "TapeCode-Test1", symbol
  "TCT1", MAX_SUPPLY = totalSupply = 10,000, token ids 1..10000, `tokenURI = baseURI + decimal id` (no
  suffix; empty while baseURI is empty), `setBaseURI(string)`, `freezeBaseURI()`, `uriFrozen()` = false,
  `baseURI()` = "" (read 2026-10-17). No ERC-4906, no per-token setter. Owner `0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9`
  is a TapeOut container (EIP-1167 clone of X Layer account implementation `0xac4f…2a57`) of circuit #1 of
  processor 282 "testBlonskr" `0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF` on X Layer → on-chain name
  `1.2.282.tape`; that circuit's holder is `0x1183a1a0f98Dd2eF8f66895C6811bbf43032843e`. So owner actions go through
  the container's ERC-6551 `execute`. The "30 days" is a marketplace listing rule, not in the contract.
- More Test1 facts (profile agent, verified by lead where marked ✓): `freezeBaseURI()` reverts `EmptyURI`
  (`0xd07b00d6`) while baseURI is empty ✓; events `BaseURISet(string)`, `BaseURIFrozen()`; no
  transferOwnership/renounceOwnership selector (inferred) → control follows circuit #1 of processor 282;
  container `execute` requires a 0.0013 OKB fee; the container implementation `0xac4f…2a57` is a beacon
  proxy, beacon `0x9b135f586f7850a3fa92210c298f732b20bc8f44` ✓ owned by the 3/5 multisig `0xB3D8…3138`
  (so container logic is upgradeable). Deployed X Layer block 72,863,247 (2026-10-10 11:38:03 UTC), first
  claim 11:39:29 UTC, sold out 19:25:21 UTC the same day.

- Container files and locking (lead, X Layer fork tests at block ~73,488,000, [`contracts/test/fork/ContainerLock.t.sol`](../contracts/test/fork/ContainerLock.t.sol)):
  site-store writes (`putFile`, `appendChunk`, `removeFile`, `setFallback`, `setOperator`) accept only the
  circuit's holder or a site operator (`operatorOf`, TTL). Activation is NOT permanent: `DomainBinding.monthlyFee()`
  = 0 on BSC and X Layer, but each container has `paidUntil` (1.2.282.tape: 2027-10-01) and only the holder can
  `bind`; at most ~120 months ahead (`MAX_AHEAD` = 311,040,000 s). Moving the circuit into its own container
  with `safeTransferFrom` reverts `SelfOwnership`; plain `transferFrom` succeeds and then `owner()` = 0, every
  write and `execute` reverts, reads still work — but nobody can ever renew, so official shells show `unpaid`
  after the expiry. `TapContainerLock` ([`contracts/src/tools/`](../contracts/src/tools/)) holds the circuit instead: same write freeze,
  plus anyone can `renew()`. Remaining trust: `SiteRegistry` and `DomainBinding` are UUPS proxies owned by a
  single EOA `0xE4fc10592FA8ad7c408B81e99CfC54Ef4B14283d` (no admin write function in current selectors, but an
  upgrade can add one); the container beacon is owned by the 3/5 multisig. putFile gas on X Layer ≈ 300k + 220/byte
  (1 KB 0.52M, 4 KB 1.18M, 24 KB 5.58M); X Layer gas price 0.02 gwei, BSC 0.05 gwei (2026-10-18).
  Marketplaces fetch metadata server-side; TAP-10 gateways are Service Workers (browser only). Reference
  server-side gateway: [`tools/gateway/`](../tools/gateway/) (Cloudflare Worker + Node; live-verified on 1.2.282.tape/index.html,
  sha256 0x108677f2…2208). hashport's `cname.hashport.org` is a real server-side host but requires a paid BNB
  Chain binding + `_tapeout` TXT; X Layer support, SHA-256 checking and CORS unverified. Pitfall: a container
  with a fallback path returns that page (HTTP 200) for a missing `meta/<id>` under TAP-10 §7.2 4c — the content
  container must not set a fallback, and the metadata gateway runs with `SPA_FALLBACK=0`.

- Site-store behaviour seen on the fork by the uploader ([`tools/uploader/`](../tools/uploader/)): operator TTL capped at 30 days
  (`TooLarge`), operators cannot appoint operators and stop working when the circuit changes hands; during a
  multi-chunk upload `fileInfo.size` counts bytes so far while the hash is the full-file hash (readers see
  `incomplete`); `FileSet` fires on every chunk; `putFile` on an existing path resets it to one chunk; empty files
  are accepted. Gas: new `putFile` ≈ 296k + 217/byte, replace ≈ 160k + 217/byte, `appendChunk` ≈ 174k + 217/byte,
  `setOperator` ≈ 100k. Container 1.2.282 has `state()` = 0 (never executed a call, so no approvals granted).

- From the cross-chain review (live reads): X Layer is now an OP Stack chain (L1Block predeploy version
  `1.8.0+custom-gas-token`); the TAP-10 hub owner `0x571d447f4f24688eC35Ccf07f1D6993655F6aF15` is an EOA on all
  three chains, and both it and the Test1 circuit holder `0x1183…843e` are signers of the 3/5 Safe
  `0xB3D8…3138` that upgrades processors and containers; the production BEM/rig LayerZero config uses 20
  confirmations, below X Layer's `safe` head. X Layer has the BLS12-381 precompiles (0x0b–0x11), so on-chain drand
  verification is possible later.
- From the fairness review: some PoD-verified miners compute the wrong function despite `verifWeight > 0`
  (re-checked independently on chain); collections must check functional correctness (draft C `functionCheck`).

## 1. Drafts and file ownership

| Draft (working file name) | Type | Requires | Owner |
|---|---|---|---|
| A [`TAPs/TAP-draft-netlist-bound-nft.md`](../TAPs/TAP-draft-netlist-bound-nft.md) — Netlist-Bound NFTs | Standards | ERC-721, ERC-165, ERC-4906, TAP-02, TAP-10 | lead |
| B [`TAPs/TAP-draft-netlist-nft-bridging.md`](../TAPs/TAP-draft-netlist-nft-bridging.md) — Moving Netlist-Bound NFTs between TapeOut Chains | Standards | A, TAP-10, ERC-721 | bridge agent |
| C [`TAPs/TAP-draft-pod-attributes.md`](../TAPs/TAP-draft-pod-attributes.md) — Proof-of-Design attributes for Netlist-Bound NFTs | Application | A, ERC-7496 | lead (tools by python agent) |
| D [`TAPs/TAP-draft-netlist-structural-hash.md`](../TAPs/TAP-draft-netlist-structural-hash.md) — Structural hash of flat netlists | Standards | TAP-02, A, `TAP-draft-large-netlists` (version 2) | canon agent |
| E [`TAPs/TAP-draft-design-credits.md`](../TAPs/TAP-draft-design-credits.md) — Design Credits and Lineage for TapeOut Netlists (number 5375 requested) | Application | TAP-02, TAP-10, A, D, EIP-712, ERC-721, ERC-1271 | lead |
| F [`TAPs/TAP-draft-soulbound-credentials.md`](../TAPs/TAP-draft-soulbound-credentials.md) — Soulbound Netlist Credentials (number 5192 requested) | Standards | TAP-02, A, E, ERC-165, ERC-721, ERC-1271, ERC-5192, EIP-712 | lead |

`TAP-draft-large-netlists` (Large Netlists and Verifiable Execution, number 7007 requested; it defines `tapnet/2` under
A §2.5) is kept in its own repository, https://github.com/BruceLanLan/tap-large-netlists.

Assets: `assets/tap-<short>/`. Contracts (one Foundry project): `contracts/src/core/*` (core agent),
`contracts/src/bridge/*` (bridge agent), `contracts/src/interfaces/*` (lead; agents may ADD files, not edit
others'). Tests in `contracts/test/core/*`, `contracts/test/bridge/*`. Python under the asset folders. The soulbound reference
contracts (draft F) are a separate Foundry project under [`assets/tap-draft-soulbound-credentials/contracts/`](../assets/tap-draft-soulbound-credentials/contracts/).
Nobody edits another owner's files; ask the lead.

## 2. Netlist file `tapnet/1` (draft A §2)

```
offset 0  6 bytes  ASCII "TAPNET"
offset 6  1 byte   version = 0x01
offset 7  1 byte   reserved = 0x00 (MUST be zero)
offset 8  4 bytes  nIn,  u32 big-endian
offset 12 4 bytes  nOut, u32 big-endian
offset 16 …        TAP-02 records, NAND and LATCH only (REF MUST be rejected)
```
Valid iff header correct, ≥ 1 record, records well-formed per TAP-02 §3 (conditions 1–5, 7, 8; condition
6 cannot arise). `netlistHash = SHA-256(file)`. Metrics: nIn, nOut, nand, latch, gates = nand + latch;
file length = 16 + 7·nand + 4·latch. Source circuit → file: `"TAPNET" 01 00 ‖ u32(nIn) ‖ u32(nOut) ‖ netlist(id)`.
Python: [`assets/tap-draft-netlist-bound-nft/tapnft.py`](../assets/tap-draft-netlist-bound-nft/tapnft.py) (`check_file`, `netlist_hash`, `file_from_chain`).

## 3. Manifest, pools, Merkle (draft A §5)

Manifest = one JSON file per collection, committed by `manifestHash = SHA-256(file bytes as published)`.
```json
{
  "tapManifest": 1,
  "collection": {"chainId": 196, "address": "0x…", "firstTokenId": 1, "supply": 10000},
  "reveal": {"source": "drand" | "vrf" | "blockhash" | "none", "...": "source parameters"},
  "pools": [
    {"label": "IMAGE_V1",   "fields": ["image"],   "root": "0x…", "entries": [{"image": "0x…", "uris": [...], "attributes": [...]}, …]},
    {"label": "NETLIST_V1", "fields": ["netlist"], "root": "0x…", "entries": [{"netlist": "0x…", "uris": [...], "source": {...}, "attributes": [...]}, …]}
  ]
}
```
Each pool has exactly `supply` entries. Field bit mask: image = 1, netlist = 2; a pool holds image, netlist
or both (mask 3). Field order inside a leaf is image then netlist.
- leaf(i) = SHA-256(0x00 ‖ u32be(i) ‖ value_1 ‖ … ‖ value_k) (each value 32 bytes)
- node = SHA-256(0x01 ‖ left ‖ right); at each level pairs (0,1),(2,3)…; an odd last node moves up unchanged.
- Proof = siblings bottom-up, skipping levels where the node moved up unchanged. Verify needs (root, size, index, leaf, proof).
Python: `leaf_hash`, `merkle_root`, `merkle_proof`, `merkle_verify`.

## 4. Reveal and the keyed permutation (draft A §6)

- `masterSeed` (32 bytes) from the declared source: drand (`randomness` of an announced round of an
  announced chain hash), Chainlink VRF (uint256 word, big-endian), or a future block hash (NOT RECOMMENDED
  on single-sequencer chains). The manifest hash MUST be published before the seed can be known.
- `poolSeed = SHA-256(masterSeed ‖ u64be(chainId) ‖ collection address (20 bytes) ‖ UTF-8(label))`.
- Token `t` (index `x = t − firstTokenId`) receives entry `permute(poolSeed, supply, x)` of each pool.
- `permute(seed, n, x)`: if n = 1 return 0. `b = max(1, bitlen(n − 1))`, `h = ceil(b/2)`,
  `mask = 2^h − 1`. `E(v)`: `L = v >> h`, `R = v & mask`; for r in 0..3: `(L, R) = (R, L xor F(r, R))`;
  return `(L << h) | R`, where `F(r, R) = uint256(SHA-256(seed ‖ u8(r) ‖ u32be(R))) & mask`.
  `y = E(x)`; while `y ≥ n`: `y = E(y)`; return y. (Cycle walking over a 4^h ≥ n domain.)
Python: `pool_seed`, `permute`. Solidity MUST reproduce Python exactly (cross-checked by vectors).

## 5. Metadata `tap` object (draft A §7)

```
"tap": {
  "v": 1,
  "id": "eip155:<chainId>/erc721:<lowercase address>/<tokenId>",
  "state": "unrevealed" | "revealed",          frozenness is read from chain, never written in metadata
  "manifest": {"sha256": "0x…", "uris": [...]},               REQUIRED if the collection uses a manifest
  "image":    {"sha256": "0x…", "uris": [...]},               REQUIRED unless unrevealed
  "netlist":  {"format": "tapnet/1", "sha256": "0x…", "bytes": N, "nIn", "nOut", "nand", "latch", "uris": [...]},
  "edition":  {"index": k, "of": n},                          REQUIRED when the netlist hash occurs n > 1 times
  "source":   {"chainId", "processor", "circuitId": "<decimal>", "name": "<TAP-10 name>", "block"},
  "license":  {"image": "<SPDX id or URI>", "netlist": "…"},
  "companion": {"chainId", "address"},                        L1 data contract for a legacy ERC-721
  "pod": {...}                                                defined by draft C
}
```
Hex = `0x` + 64 lowercase hex. Edition index = rank of the token id among the collection's token ids that
received the same netlist hash, ascending, starting at 1. Tools ignore unknown members.
Python: `check_metadata`, `check_netlist_against_metadata`.

## 6. Conformance (draft A §8)

- **L0 metadata**: JSON rules + manifest + off-chain reveal. Freeze = owner gives up URI changes
  (e.g. `freezeBaseURI()`); tools label L0 as "metadata only".
- **L1 on chain**: the contract (or a companion bound to an existing ERC-721) implements
  `ITapNetlistNFT` (§7), ERC-165, ERC-4906; netlist bytes readable on chain.

## 7. Solidity interfaces (lead writes [`contracts/src/interfaces/`](../contracts/src/interfaces/))

`ITapNetlistNFT` — see [`contracts/src/interfaces/ITapNetlistNFT.sol`](../contracts/src/interfaces/ITapNetlistNFT.sol) (authoritative).
`ITapBridgeAdapter`, `ITapBridgeEndpoint` — see [`contracts/src/interfaces/ITapBridge.sol`](../contracts/src/interfaces/ITapBridge.sol) (authoritative).
Solidity 0.8.28, optimizer on 10,000 runs, EVM `shanghai` (X Layer and BSC support it; avoid `cancun`
opcodes such as MCOPY/transient storage so one build deploys on all three chains). No external libraries
besides forge-std for tests; write minimal ERC-721 yourself or copy a small MIT implementation into
[`contracts/src/vendor/`](../contracts/src/vendor/) with its licence header.

## 8. Bridging (draft B) — summary for the bridge agent

- Home chain = the chain of the original collection. Home endpoint = `TapGateway` (locks a legacy or
  native ERC-721 token in escrow; a native collection MAY burn instead). Remote endpoint = `TapMirror`
  (ERC-721 + `ITapNetlistNFT` + ERC-4906; mints on arrival, burns on departure). Superseded: routing is hub and
  spoke — a remote→remote move is two transfers through the home chain, and the gateway tracks `locationOf[id]`.
  Invariant: for each tokenId at most one non-escrowed live token across all chains.
- `collectionKey = keccak256(abi.encode("TAP-NFT collection v1", homeChainId, homeContract))`.
- Payload v1 = `abi.encode(uint8 1, bytes32 collectionKey, uint256 tokenId, address to, bytes32 netlistHash,
  bytes32 imageHash, bytes32 manifestHash, uint64 srcChainId, uint64 dstChainId, uint64 nonce)`;
  `messageId = keccak256(srcEndpoint ‖ payload)` (superseded the earlier `keccak256(payload)`, review L-2);
  destination rejects a messageId it has seen.
- Mirror stores the hashes it receives; `materialize(bytes tapnet)` (permissionless) stores netlist bytes if
  `sha256(bytes)` equals a hash some token holds, so `netlistOf` works on every chain.
- Adapters behind one interface; per route (src, dst) a policy: `ONE` (exactly one enabled adapter, default)
  or `ALL` (every listed adapter must deliver the identical payload before the mint; dual attestation).
  `ANY` is not offered (security = weakest adapter).
- LayerZero V2 profile: raw OApp-style integration against EndpointV2 `0x1a44…728c` (no LayerZero library
  dependency in the reference code; write the minimal interface), eids from the table above plus Base 30184
  (verify against LayerZero docs and say so), peers set once then frozen, ≥ 2 required DVNs RECOMMENDED.
- TAP-10 hub profile: source side writes the payload with `hub.send` from the gateway's own circuit
  container (the adapter holds a circuit NFT); destination side accepts a relayed payload only with
  K-of-N EIP-712 attestations over (srcChainId, hub, from-container, outboxIndex, digest) from a fixed
  attester set. Mark the attester model as one possible verifier and the whole profile **[Open]** until
  an on-chain way to verify hub messages exists. Implement it so `ALL(LayerZero, Hub)` works in tests.
