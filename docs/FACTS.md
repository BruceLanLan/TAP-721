# Verified on-chain facts

Facts the drafts rely on, collected from [DESIGN.md](DESIGN.md) §0, `reviews/security-contracts.md`,
`reviews/editorial.md` and `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`. Each entry says when it was read and how to re-check
it. Read dates are 2026-10-17/18 unless stated. Chain state changes: re-run the check before relying on a value.

Re-check commands use Foundry `cast` with public nodes:

```bash
export BSC=https://bsc-dataseed.bnbchain.org
export XL=https://rpc.xlayer.tech
IMPL=0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc   # ERC-1967 implementation slot
BEACON=0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50 # ERC-1967 beacon slot
```

## 1. Chains (TAP-10 §2.1)

| Chain | Chain id | TAP-10 area code | LayerZero V2 eid |
|---|---|---|---|
| BNB Smart Chain | 56 | none | 30102 |
| Base | 8453 | 3 | 30184 (from LayerZero docs; marked "verify" in DESIGN.md §8) |
| X Layer | 196 | 2 | 30274 |

New chains are appended by TAP-10, never by these drafts.

## 2. PoD mining (BNB Smart Chain)

| Fact | Value | Re-check |
|---|---|---|
| Mining contract | `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46` (ERC-1967 proxy) | `cast storage 0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46 $IMPL --rpc-url $BSC` |
| Implementation | `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898` (source not publicly verified) | same command; also `mining.implementationSlot` in `assets/tap-draft-netlist-bound-nft/chain-snapshot.json` |
| Ownership | `owner()` = 0 and `isSealed()` = true since block 121,815,032 (renounced through a 48 h timelock) | `cast call 0x7E2E…7b46 "owner()(address)" --rpc-url $BSC`; `"isSealed()(bool)"` |
| Parameters at block 128,200,681 | `lambda()` = 6, `beta()` = 3, `lambdaBurn()` = 1, task count 267 | `cast call 0x7E2E…7b46 "lambda()(uint256)" --block 128200681 --rpc-url <archive node>` |
| `processorMultiplier` | processor 30 "TapeOut" `0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C` = 1; `0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c` ("Blonskr_No1") = 6 | `cast call 0x7E2E…7b46 "processorMultiplier(address)(uint256)" <processor> --rpc-url $BSC` |
| Formula (tapeout.net/pod) | b* = n + λ_burn·m; A = g + λ·s; C = A·max(d,1)^β; q = clamp(C_ref/C, 1/Q, Q); H = (b* + K_task·q)·P | Recomputed for all seven rows of draft C's Test Cases (`reviews/editorial.md` §1) |
| Status semantics (observed) | status 1 = mining; verified ⇔ `verifWeight` > 0 | `getMiner(minerKey(circuits,id))` |
| "C/N/L" | community shorthand for the three TapeOut primitives: **C = 电容** (community nickname for a TapeOut container), **N = NAND**, **L = LATCH** (confirmed 2026-10-18; an earlier reading "C = design cost" was wrong) | DESIGN.md §0 |
| REF ban | PoD mining rejects REF records in miner circuits, so every BEM miner netlist is REF-free | draft A §3 |
| Snapshot block | 128,200,681, timestamp 1792253755 = 2026-10-17 16:15:55 UTC | `cast block 128200681 timestamp --rpc-url $BSC` |
| `minerKey` example | circuit #17851 of processor 30 → `0xa13a5bd9630a45d0308786747431d473f749348c02d5128e66d48cc2cec6464e` = keccak256(processor ‖ uint256 id) | `cast keccak $(cast abi-encode --packed "f(address,uint256)" 0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C 17851)` (run 2026-10-18, matches) |

Circuits in `assets/tap-draft-netlist-bound-nft/chain-snapshot.json` (block 128,200,681):

| Processor | Circuit | Gates | Task | Depth | Area | b* | verifWeight |
|---|---|---|---|---|---|---|---|
| 30 TapeOut | 17851 | 4 | 3 | 3 | 4 | 4 | 4 |
| 30 TapeOut | 17852 | 10 | 220 | 1 | 64 | 10 | 10 |
| 30 TapeOut | 3151 | 55 | 48 | 16 | 55 | 55 | 55 |
| 1 Blonskr_No1 | 38 | 1204 | — | — | — | — | 0 (miner status 0) |

Regenerate with `python3 tools/fetch_chain.py` (needs an archive node for the pinned block; public BSC nodes
prune state after about a minute, see `assets/tap-draft-pod-attributes/README.md`).

## 3. Official rig bridge (already live, not part of these drafts)

| Contract | Chain | Address |
|---|---|---|
| Rig vault (one EIP-1167 escrow per rig) | BSC | `0x48D43345656f0f9510dC3c06CBa99dFf597617C2` |
| "TapeOut Rig" / RIG voucher (proxy) | X Layer | `0x9cfc959cd42B2e1d39a0d850c528210E818AE520` |
| Voucher owner (3/5 multisig) | X Layer | `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138` |
| LayerZero EndpointV2 | both | `0x1a44076050125825900e736c501f859c50fE728c` |
| BEM OFT | X Layer | `0x60e62Efa9405d6873C5deaBD4E6CC91c25363952` |
| BEM bridge | BSC | `0xa84B8D3893De6e9922f2B29bE1e1b115845F5E72` |

Re-check: `cast call 0x9cfc959cd42B2e1d39a0d850c528210E818AE520 "owner()(address)" --rpc-url $XL`, `"name()(string)"`.

## 4. TAP-10 DeWEB hub

`0xe61A9C7213a6Aa616C246a2B569e555B417b25ee`, same address on every TapeOut chain. A message is stored only on
the sender's chain (inbox + outbox + `Sent` event, payload ≤ 16,000 bytes; author = a circuit's container,
writer = the current circuit holder). It delivers nothing to another chain, which is why draft B's hub profile
is **[Open]**.

## 5. TapeCode-Test1 (X Layer)

| Fact | Value | Re-check |
|---|---|---|
| Contract | `0x0e91460d6823c711643e650a9a4c0cc21de41614`, name "TapeCode-Test1", symbol "TCT1" | `cast call 0x0e91…1614 "name()(string)" --rpc-url $XL` |
| Supply | `MAX_SUPPLY` = `totalSupply` = 10,000, token ids 1..10000 | `"totalSupply()(uint256)"` |
| URI | `tokenURI = baseURI + decimal id` (no suffix; empty while baseURI is empty); `baseURI()` = "" and `uriFrozen()` = false (read 2026-10-17) | `"baseURI()(string)"`, `"uriFrozen()(bool)"` |
| Setters | `setBaseURI(string)`, `freezeBaseURI()`; no ERC-4906, no per-token setter; no transfer/renounce-ownership selector (inferred) | selectors from the deployed bytecode |
| `freezeBaseURI()` while empty | reverts `EmptyURI` (`0xd07b00d6`) ✓ | `cast call 0x0e91…1614 "freezeBaseURI()" --from <owner> --rpc-url $XL` |
| Events | `BaseURISet(string)`, `BaseURIFrozen()` | |
| Owner | `0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9`, a TapeOut container (EIP-1167 clone of X Layer account implementation `0xac4f791353ee9f06e2c50ae4c34680d28ea52a57`) of circuit #1 of processor 282 "testBlonskr" `0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF` → on-chain name `1.2.282.tape` | `"owner()(address)"` |
| Circuit holder | `0x1183a1a0f98Dd2eF8f66895C6811bbf43032843e` at the time of reading; owner actions go through the container's ERC-6551 `execute` (fee 0.0013 OKB) | `cast call 0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF "ownerOf(uint256)(address)" 1 --rpc-url $XL` |
| Container logic | `0xac4f…2a57` is a beacon proxy; beacon `0x9b135f586f7850a3fa92210c298f732b20bc8f44` ✓ owned by the 3/5 multisig `0xB3D8…3138` (upgradeable) | `cast call 0x9b135f586f7850a3fa92210c298f732b20bc8f44 "owner()(address)" --rpc-url $XL` |
| Deployment | X Layer block 72,863,247 (2026-10-10 11:38:03 UTC); first claim 11:39:29 UTC; sold out 19:25:21 UTC the same day | `cast block 72863247 timestamp --rpc-url $XL` |
| "30 days" | a marketplace listing rule, not in the contract | |
| Bridging collection key | `keccak256(abi.encode("TAP-NFT collection v1", 196, 0x0e91…1614))` = `0x8755cf608e750f9bd55ba6ac4c0e655dffffc199774518f82624273f5217b4bd` | `assets/tap-draft-netlist-nft-bridging/vectors.json` |

✓ = re-verified by the lead.

## 6. Containers, site store and locking (X Layer fork tests at block ≈ 73,488,000)

Source: `contracts/test/fork/ContainerLock.t.sol` (2/2 pass, see [TESTING.md](TESTING.md)) and the security review.

- Site-store writes (`putFile`, `appendChunk`, `removeFile`, `setFallback`, `setOperator`) accept only the
  circuit holder or a site operator (`operatorOf`, with TTL).
- Activation is not permanent. `DomainBinding.monthlyFee()` = 0 on BSC and X Layer, but each container has
  `paidUntil` (1.2.282.tape: 2027-10-01); only the holder can `bind`, at most ~120 months ahead
  (`MAX_AHEAD` = 311,040,000 s).
- DomainBinding `0x68809Fd2fb343aA57D0aeB7f33Defe477c9666f9` (X Layer) is an ERC-1967 proxy, implementation
  `0x5eBF29b80789e548907C707530C3C7607C4347Df`. `cast storage 0x68809Fd2fb343aA57D0aeB7f33Defe477c9666f9 $IMPL --rpc-url $XL`.
- `SiteRegistry` and `DomainBinding` are UUPS proxies owned by the single EOA
  `0xE4fc10592FA8ad7c408B81e99CfC54Ef4B14283d` (no admin write function in current selectors, but an upgrade can add one).
- Processor `0x8E0b…60cF` is an ERC-1967 beacon proxy behind beacon `0xf70d1ed4…991c`, the unsealed circuit
  beacon listed in TAP-02. `cast storage 0x8E0bb87998a9239daa79551ef7dbf78C9b0C60cF $BEACON --rpc-url $XL`.
- Moving the circuit into its own container with `safeTransferFrom` reverts `SelfOwnership`; plain `transferFrom`
  succeeds, after which `owner()` = 0, every write and `execute` revert, reads still work, and nobody can renew.
  `TapContainerLock` holds the circuit instead: same write freeze, plus anyone can `renew()`.
- `putFile` gas on X Layer ≈ 300k + 220/byte (1 KB 0.52M, 4 KB 1.18M, 24 KB 5.58M). Gas price X Layer 0.02 gwei,
  BSC 0.05 gwei (2026-10-18).
- Marketplaces fetch metadata server-side, while TAP-10 gateways are Service Workers (browser only). The
  reference server-side gateway (`tools/gateway/`) was live-verified on `1.2.282.tape/index.html`, SHA-256
  `0x108677f22b768bfc77b1aa55234a74e2a14f11f3431297a4254597888aa02208`.
- Pitfall: a container with a fallback path returns that page (HTTP 200) for a missing `meta/<id>` under TAP-10
  §7.2 4c. The content container must not set a fallback; run the metadata gateway with `SPA_FALLBACK=0`.
- hashport's `cname.hashport.org` is a real server-side host but needs a paid BNB Chain binding and a `_tapeout`
  TXT record; X Layer support, SHA-256 checking and CORS are unverified.

## 6a. Site store as seen by the uploader (anvil fork of X Layer)

- Operator TTL is capped at 30 days (`TooLarge`); operators cannot appoint operators and stop working when the
  circuit changes hands.
- During a multi-chunk upload `fileInfo.size` counts the bytes so far while the hash is the full-file hash
  (readers see `incomplete`); `FileSet` fires on every chunk; `putFile` on an existing path resets it to one chunk;
  empty files are accepted.
- Gas: new `putFile` ≈ 296k + 217/byte, replace ≈ 160k + 217/byte, `appendChunk` ≈ 174k + 217/byte,
  `setOperator` ≈ 100k. Container 1.2.282 has `state()` = 0 (it never executed a call, so no approvals were granted).
- Source: `tools/uploader/test_e2e.py` (36 checks).

## 6b. Cross-chain environment (from `reviews/alt-crosschain-trust.md`, live reads)

- X Layer is now an OP Stack chain (L1Block predeploy version `1.8.0+custom-gas-token`).
- The TAP-10 hub owner `0x571d447f4f24688eC35Ccf07f1D6993655F6aF15` is an EOA on all three chains. Both it and the
  Test1 circuit holder `0x1183…843e` are signers of the 3/5 Safe `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138` that
  upgrades processors and containers.
- The production BEM/rig LayerZero config uses 20 confirmations, below X Layer's `safe` head.
- X Layer has the BLS12-381 precompiles (0x0b–0x11), so on-chain drand verification is possible later.
- Re-check: `cast call 0xe61A9C7213a6Aa616C246a2B569e555B417b25ee "owner()(address)" --rpc-url $XL`;
  `cast code 0x571d447f4f24688eC35Ccf07f1D6993655F6aF15 --rpc-url $XL` (empty = EOA);
  `cast call 0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138 "getOwners()(address[])" --rpc-url $XL`.

## 7. drand

The collection pipeline uses drand quicknet, chain hash
`52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971`. Genesis, period and public key are always
fetched from `/<chainhash>/info` and checked against this hash (`tools/collection/drand.py`). The pipeline test
uses past round 33,145,012 (produced 2026-10-17T12:00:00Z).
