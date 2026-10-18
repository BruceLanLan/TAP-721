# Alternative review: cross-chain design and trust for the netlist-NFT drafts

Date: 2026-10-18. Reviewer role: cross-chain security architect, asked to find better designs, not to polish the current one.
Scope: `DESIGN.md` §0 and §8, `TAPs/TAP-draft-netlist-nft-bridging.md` (draft B), `TAPs/TAP-draft-netlist-bound-nft.md` (draft A), `contracts/src/bridge/**`, `contracts/src/tools/TapContainerLock.sol`, `reviews/security-contracts.md`, and TAP-10 (chain table, §13 hub, Deployments).
Method: read-only. I used `cast call`, `cast storage` and `cast codesize`, plus `eth_call` simulations with `--from` (no transaction was signed or sent). I also used LayerZero's public metadata API and one web search. No existing file was edited.

---

## 0. Bottom line

| # | Recommendation | Verdict | Effort |
|---|---|---|---|
| 1 | Take bridging out of v1. Ship drafts A, C and D for TapeCode-Test1 on X Layer. Keep draft B as a Draft with no official deployment. Spend the effort on things that protect Test1 holders today (§4, §3.3). | **ADOPT NOW** | Negative: removes about 1,100 lines of unaudited bridge code from the v1 audit |
| 2 | When bridging is needed, build it on LayerZero's **ONFT721Adapter** (home, lock) and an **ONFT721** subclass (mirror), with a thin TAP profile: three hashes appended to the message, the `ITapNetlistNFT` mirror profile and `materialize`. Get the "ALL" property from ULN302's **required-DVN set**, not from a multi-adapter endpoint. Use **hub-and-spoke routing with per-chain accounting** (mirrors send only home), so that one bad route cannot drain the escrow. Drop the custom endpoint/adapter framework, the `ALL` adapter policy and the hub-relay adapter. | **LATER** (design decision: ADOPT NOW, in the draft) | About 1 to 2 weeks plus an audit of a delta of about 200 to 300 lines, against about 1,100 custom lines today |
| 3 | Do not use the TAP-10 hub as a bridge leg. It adds trust in a **single EOA** (the hub owner `0x571d…F15` on all three chains) and in the unsealed factory, and it attests to nothing that the gateway's own `departed` storage does not already prove. Cross-chain hub verification: OP-stack storage proofs for X Layer ↔ Base are **LATER**. No trust-minimised path for BNB Smart Chain exists today: zk light-client DVNs are **REJECT** (Polyhedra marked deprecated), Hashi is **REJECT**, and native OP messaging is **REJECT** for v1. | **REJECT** (hub leg) / **LATER** (storage proofs) | — |

Supporting findings that came out of the live reads:

- **X Layer is an OP-Stack chain now.** The L1Block predeploy `0x4200…0015` on X Layer returns `version()` = `"1.8.0+custom-gas-token"` and `number()` = 26,213,929, and the EIP-2935 history contract is present. Secondary source: a Cryptowisser report dated 2025-12-09 that OKX migrated X Layer from Polygon CDK to the OP Stack. Arguments in the drafts or elsewhere that treat X Layer as a Polygon-CDK validium are out of date.
- **TapeOut's production LayerZero stack is the standard LZ library, not custom code.** The BSC BEM bridge `0xa84B…5E72` is a stock `OFTAdapter`: `oAppVersion()` = (1, 2), `oftVersion()` = `0x02e49c2c`, `approvalRequired()` = true, `token()` = BEM. The rig bridge is not a separate OApp. The vault `0x48D4…17C2` has `adapter()` = that same OFTAdapter, has `lzCompose`, and has no `lzReceive`. So rigs ride as **compose messages on the BEM OFT**. TapeOut's own precedent for "custom payload over LZ" is therefore "stock OApp library plus an extension", which is recommendation 2.
- **Production DVN configuration** (BEM OFT, pinned libraries, delegate = 3/5 Safe):
  - BSC side, receiving from X Layer: required {Nethermind, LayerZero Labs}, plus optional {Horizen, Canary} with threshold 1.
  - X Layer side, receiving from BSC: required {LayerZero Labs}, plus optional {Canary, Nethermind, Horizen} with threshold 2.
  - **20 block confirmations in both directions.** Twenty X Layer blocks are far short of X Layer's `safe` head, which needs the batch posted on L1. So on X Layer → BSC, BEM and rig deliveries rely on the X Layer sequencer not reorging. That is below what draft B itself recommends (§9: confirmations at least as deep as the finality tag). This is a production finding for TapeOut. It is not in our code.
- **Signer overlap in the 3/5 Safe `0xB3D8…3138`** (Safe 1.4.1, threshold 3, five EOA owners; owners and threshold read on BSC, X Layer and Base; no modules and no guard on BSC and Base). Two of the five signers are `0x571d…F15` (the hub owner and payments-table deployer) and `0x1183…843e` (the holder of circuit 1.2.282, which controls TapeCode-Test1). The Test1 issuer is therefore one of the three signatures that can upgrade every processor and container.

---

## 1. Custom gateway and mirror vs LayerZero ONFT721 / ONFT721Adapter

### 1.1 What the custom design actually adds

| Claimed differentiator (draft B Motivation/Rationale) | Does ONFT721 lack it? | Assessment |
|---|---|---|
| Lock-and-mint for legacy collections | No. `ONFT721Adapter` is lock-and-mint over an unchanged ERC-721 (`transferFrom` into the adapter, `approvalRequired()` = true), and only one adapter per token, on the home chain. | Not a differentiator. Draft B's "as LayerZero's ONFT721 does in its native form" undersells the adapter form. |
| Netlist, image and manifest hashes in the payload | No. Override `_buildMsgAndOptions` (send) and `_lzReceive` (receive) to append 3 words after the standard `(bytes32 to, uint256 tokenId)`, or put them in `composeMsg`. TapeOut already does the compose variant for rigs. (Before relying on the override route, check that `_buildMsgAndOptions` and `_lzReceive` are `virtual` in `ONFT721Core` of `@layerzerolabs/onft-evm`. The docs fetch did not confirm it.) | Not a differentiator. Only peers decode the message, so a non-stock encoding is fine. |
| `materialize`, the `ITapNetlistNFT` mirror profile, ERC-4906 | Not in ONFT, but these are mirror-contract features that are independent of transport. | Keep them, as a subclass of ONFT721. |
| `ALL` policy across message layers | Yes, ONFT knows one layer. | But ULN302 already gives "every required verifier must attest the same payload hash" (required DVNs) and an optional M-of-N on top. That is the same safety property across independent verifier operators. The only thing `ALL(LZ, hub)` adds is independence from LayerZero's endpoint and ULN302 **code**, both of which are non-upgradeable (read: no ERC-1967 slot on the endpoint on all three chains, or on ULN302 send/receive on BSC and Base; the X Layer ULN302 slots were not read). And the second layer does not exist (§2). |
| Set-once peers and `sealRoutes()` | Yes. OApp `setPeer` stays owner-mutable until ownership is renounced. | This is real. The equivalent with ONFT is: configure, then `setDelegate(final)` (or 0) and `renounceOwnership()`, which also freezes `setEnforcedOptions` and the mirror's `setBaseURI`. Or keep the owner behind a timelock (see 1.3). That is a deployment procedure, not a reason for a new standard. |
| Independence from any one layer's library | — | It cuts both ways. The custom code is about 1,100 lines and unaudited. It is already drifting: the TAP text §4.1 says `messageId = keccak256(payload)`, while `TapBridgePayload.messageId` hashes `srcEndpoint ‖ payload`, a fix for review L-2. Every such fix re-opens the spec and the vectors. |

### 1.2 Interoperability, audit surface, upgrade and configuration trust

- **Explorers.** LayerZero Scan indexes every EndpointV2 packet, so a custom OApp is visible too. ONFT gains nothing here. LZ devtools (`lz:oapp:wire`, config checkers, `lz:oapp:config:get`) assume the OApp standard surface (`peers`, `enforcedOptions`, `setDelegate`). The custom adapter mimics part of it (`peers(uint32)`, `allowInitializePath`, `nextNonce`) but not `setPeer(uint32,bytes32)` or `enforcedOptions`, so the tooling only partly works.
- **Marketplaces.** These are neutral. OKX, OpenSea and Element index a mirror as a separate ERC-721 either way. Neither design gets the mirror recognised as "the same collection". That needs per-marketplace listing work, and the `tap.id` home identifier in metadata (draft A §4.1) is what helps.
- **Audit surface.** ONFT721 plus OAppCore are LayerZero-maintained and audited (taken from LZ's documentation, not checked here). Our delta would be the hash extension, the mirror profile and per-chain accounting, about 200 to 300 lines. The custom framework is endpoint (331), gateway (78), mirror (184), payload (78), adapter base (76), LZ adapter (134), LZ interface (57), hub adapter (203) and interfaces, all of it new.
- **Upgrade and configuration trust.** They are identical in substance. In both designs the decisive power is the **EndpointV2 delegate** (library and DVN choice) plus whoever can change peers. The custom design pins peers per chain but still needs a delegate, and `seal()` sets it to 0 (`LayerZeroV2Adapter._onSeal`). ONFT has the same knobs. Neither design is upgradeable unless you choose an upgradeable variant (don't).

### 1.3 Recommended TAP profile (when bridging is in scope)

1. **Home (X Layer for Test1):** a `TapONFT721Adapter is ONFT721Adapter`. On send it reads the three hashes from the data source (the companion), as draft B §4.2 does, and appends them to the message.
2. **Mirror:** a `TapONFT721 is ONFT721` with `ITapNetlistNFT` (mirror profile), `ITapBridgeMirror` (`knownNetlist`, `manifestHash`, `materialize`), ERC-4906 and the `ManifestConflict` latch. Keep draft B §5.3 almost verbatim. It is good, transport-independent text.
3. **Hub-and-spoke with per-chain accounting (new, fixes review I-1).** Mirrors may send only to the home eid. The home adapter records `locationOf[tokenId] = dstEid` on departure. On arrival it releases only if `origin.srcEid == locationOf[tokenId]`. A compromise of the Base route can then release only tokens that are on Base, not the whole escrow. Mirror → mirror becomes two hops through home, which costs two fees and is rare for NFTs. Draft B's mirror-to-mirror hops make this accounting impossible, which is why the current design has the property that "the weakest route drains everything".
4. **"ALL" means required DVNs.** At least 3 required DVNs from different operators that exist on all three chains (from LZ metadata: LayerZero Labs, Nethermind, Horizen, P2P, 01node, Nansen and Deutsche Telekom are listed on BSC, Base and X Layer), optional threshold 0. Confirmations at least the finality tag: BSC about 15 to 20 blocks covers fast finality. For X Layer and Base, `safe` means L1 inclusion, so it is minutes of blocks, not 20.
5. **Configuration custody.** Rather than renouncing everything on day one, put owner and delegate behind a `TimelockController` (for example 7 days) held by a multisig whose signers are **not** the collection issuer. Holders get an exit window before any DVN or peer change, and a dead DVN can still be replaced. Renounce later, for collections that want it. This replaces draft B's `sealRoutes()` versus stuck-`ALL` dilemma (draft B §7, path 3: tokens permanently lost).
6. **Message id and replay:** EndpointV2's GUID and per-path nonce bookkeeping already make a message execute at most once. The custom `executed[messageId]` is redundant under one layer.

Verdict for 1: **REJECT** the custom gateway/mirror/endpoint framework as the standard. **ADOPT** an ONFT721-based profile when bridging is in scope (**LATER**). The draft should say this now.

---

## 2. Making TAP-10 hub messages verifiable on another chain

Ground truth that the options depend on (TAP-10 §13.6): the hub stores `Entry{from, blockNumber, timestamp, digest}` with `digest = keccak256(ref ‖ keccak256(payload))`, and the payload itself only in the `Sent` log. A verifier therefore needs either a **storage proof** of the inbox or outbox entry (and then checks the digest against a supplied payload), or a **receipt proof** of the `Sent` log, in both cases against a trusted source block or state root.

The more important point is what a hub proof proves: that the holder of a circuit on an unsealed processor wrote an entry into an unsealed hub. Today both the factory owner (the 3/5 Safe, via the circuit beacon) and the hub owner (single EOA `0x571d…F15`, read `owner()` on all three chains, `code` = 0) can make that statement true at will (TAP-10 §13.4, §13.8). For the bridge, a proof of the **gateway's own `departed[messageId]` slot** is strictly better. It has the same proof machinery and none of the hub's admin trust. So the hub is the wrong thing to verify for bridging, whatever the verifier.

| Option | Feasibility on BSC / X Layer / Base today | Cost and latency | Trust | Verdict |
|---|---|---|---|---|
| **Storage proofs against relayed block hashes, OP-stack anchored (X Layer ↔ Base)** | Both are OP-Stack L2s of Ethereum: X Layer per the L1Block predeploy read above, Base natively. On the destination, read the current L1 block hash from `L1Block.hash()` (only the latest L1 origin, so the proof must land within that window, or a small "L1 header store" contract must snapshot it). Prove the source chain's output root in its L1 contracts (DisputeGameFactory or L2OutputOracle: **not verified** which one X Layer uses, nor whether its proofs are permissionless). Open the output root preimage (`version, stateRoot, withdrawalStorageRoot, blockHash`), then do an account proof and a storage proof of the gateway's `departed` slot or the hub entry. Audited MPT verifiers exist (Optimism's `MerkleTrie`/`SecureMerkleTrie`, MIT). | Estimate 0.6 to 1.0 M gas on the destination (two nested MPT proofs plus header RLP). Pennies on Base and X Layer at current gas prices. **Latency is the challenge window** (about 7 days on fault-proof OP chains), or trust in the proposer if X Layer's proposals are permissioned. | Inherits each rollup's own upgrade keys and security council. Independent of LZ. | **LATER.** It is the only real candidate for an independent second leg. It covers only 2 of 3 chains, not BSC, and the days-long latency makes it a slow lane, not a UX path. About 3 to 5 weeks plus an audit. |
| **Native OP-stack messaging (X Layer ↔ Ethereum, then Ethereum ↔ Base)** | X Layer → L1 withdrawal (prove plus finalize) then an L1 → Base deposit. Ethereum is not a TapeOut chain. X Layer is not in the Superchain interop set (not verified, but nothing indicates interop between X Layer and Base). | L1 gas for prove, finalize and deposit, roughly 0.5 M L1 gas. About 7 days. | Same as the storage-proof row. | **REJECT** for v1. It is functionally the storage-proof row with worse UX and extra L1 gas. |
| **Polygon-CDK / AggLayer native messaging** | It was the premise when X Layer was a CDK chain. X Layer now reports an OP-Stack L1Block. Whether X Layer is still attached to AggLayer is unverified. Base and BSC are not on AggLayer. | — | — | **REJECT.** Wrong premise for 2026, and it would not reach BSC or Base anyway. |
| **zk light client of BSC** (verify Parlia fast-finality BLS votes on X Layer or Base) | No production verifier that I could confirm. LayerZero metadata lists both Polyhedra zkBridge DVN entries as **deprecated** on BSC, Base and X Layer, which is a negative signal for the one known zk-DVN path. A self-built verifier would need BLS12-381 (EIP-2537) on the destination and tracking of the BSC validator set every epoch. | Proving infrastructure plus continuous operation. Months. | Strongest in theory. | **REJECT** (for this project's scale). Revisit if a maintained BSC zk verifier appears as a DVN. |
| **zk light client of Ethereum** (for example SP1-Helios-style) on X Layer or Base, combined with the storage-proof row | It replaces "trust `L1Block`" with "trust a zk proof", which gains nothing on an L2 that already gets L1 hashes natively. | — | — | **REJECT** (redundant on OP-stack destinations). |
| **Hashi-style multi-bridge aggregation** | Hashi (Yaho/Yaru/Hashi plus per-bridge adapters) is the generalised form of draft B's `ALL`, applied to block headers. I found no deployment or adapters for X Layer (not exhaustively verified). It needs at least two independent header oracles per path, and for BSC the only ones are DVN-style committees anyway. | Deploy and operate the full Hashi stack. Weeks. | Max over K bridges. | **REJECT.** It duplicates required-DVN semantics with more code and no BSC-capable independent oracle. |
| **LayerZero lzRead** (destination reads `hub.inboxAt(...)` or `gateway.departed(id)` on the source chain) | `readLib1002` is listed for **BSC and Base but not X Layer** in LZ deployment metadata (`xlayer-mainnet` v2 has no `readLib1002`). Only one lzRead-compatible DVN (Curve) is listed on X Layer. Whether BSC or Base read channels support X Layer as a **target** is unverified. | One LZ fee. Seconds to minutes. | **LZ DVN trust again.** It cannot be the independent second leg of `ALL`. | **LATER**, and only for *reading* (§4: games on BSC that want to know a Test1 holder's netlist without moving the token), never as a bridge leg. |
| **TapeOut-run DVN** (a DVN worker that checks the source chain the way the hub attesters would) | DVN contracts are permissionless to deploy, and LZ publishes reference workers. Add it as one of the required DVNs. | Ops cost of one more always-on signer set. | Adds TapeOut as a veto without a second transport. | **LATER** (optional). It is the clean replacement for the hub-relay attester set: same trust, no hub, no relayer-incentive problem (draft B Open Q2). |

**Concrete recommended path.**
1. v1: none. No bridge (§4).
2. When bridging: LayerZero only, with at least 3 independent required DVNs and finality-tag confirmations, optionally plus a TapeOut DVN.
3. If an LZ-independent leg is later demanded for X Layer ↔ Base, build the OP-stack storage-proof verifier against the **gateway's own `departed` slot**, as a slow, permissionless "escape hatch". Never base it on the hub.
4. For BSC, accept DVN trust and say so plainly. Delete draft B §10 (hub profile) and its open questions 1 and 2, or move them to TAP-10 as a messaging-layer topic.

---

## 3. Trust map (live reads, read-only)

Blocks: BNB Smart Chain about 128,213,556 (via `tapeout.net/rpc`), Base about 52,735,104 (`mainnet.base.org`), X Layer 73,490,448 at the start. X Layer reads span a few minutes after that, because `rpc.xlayer.tech` rate-limited (HTTP 403) and the reads were retried slowly. Each value comes from one node, not strict agreement. ERC-1967 implementation slot `0x3608…2bbc`, admin slot `0xb531…6103`, beacon slot `0xa3f0…3d50`.

### 3.1 TapeOut contracts

| Contract (chain) | Address | Form (read) | Controller (read) | Power over Test1 / bridge holders |
|---|---|---|---|---|
| Processor factory (all 3) | BSC `0x6822…F7e2`; Base/XL `0x1f09…0761` | UUPS proxy, impl BSC `0xa68c…6422`, L2 `0x7495…d17b`; `isSealed()` = false | `owner()` = **3/5 Safe `0xB3D8…3138`** | Owns the circuit beacon, so it can replace processor logic (`ownerOf`, transfers) for every circuit. It can move circuit 1.2.282 (the owner of Test1's container) and write to the hub as any container. |
| Circuit beacon | BSC `0xf8D6…8156`; Base/XL `0xf70d…991C` | Beacon; impl BSC `0x8E1D…6068`, L2 `0x977f…29B2` (both match TAP-10 seal constants) | `owner()` = the factory | As above. |
| Processor 282 "testBlonskr" (XL) | `0x8E0b…60cF` | Beacon proxy → `0xf70d…991C` | Via the factory | Holds circuit #1, which controls Test1. |
| Container implementation (XL) | `0xAC4F…2a57` | Beacon proxy (beacon address hard-coded in bytecode) → beacon `0x9b13…8f44` → impl `0x6B6f…996B` | Beacon `owner()` = **3/5 Safe** (X Layer read; the BSC and Base container beacons were not read) | Can replace `execute` logic for every container, including Test1's owner container `0xa8ed…f9b6`, and so call `setBaseURI` on Test1 until the base URI is frozen. |
| Test1's owner container (XL) | `0xa8ed…f9b6` | EIP-1167 clone → `0xAC4F…` | `owner()` = `0x1183…843e` (holder of circuit #1) | `setBaseURI`/`freezeBaseURI` on Test1. |
| TapeCode-Test1 (XL) | `0x0e91…1614` | **Not a proxy** (5,120 bytes, empty ERC-1967 slots) | `owner()` = container `0xa8ed…` | Base URI only. `uriFrozen()` = false, `baseURI()` = "" (DESIGN §0). |
| Container opener (XL) | `0x536a…0106` | Not a proxy; has `implementation()`, `treasury()`, `FEE()` getters | No owner getter | Fee and treasury (not read further). |
| Container payments table | BSC `0xc0C6…fa4c`; XL `0x13b8…4858` | Not a proxy; immutable `deployer()` = **`0x571d…F15`** | `setOpener` is one-shot: simulated on BSC, it reverts `OpenerAlreadySet()` from the deployer and `NotDeployer()` from anyone else | None now (opener already set). |
| SiteRegistry (all 3) | BSC `0xd006…E5e6`; Base/XL `0xd6EF…ADB6` | UUPS, impl BSC `0x1d27…c261`, L2 `0xa85c…a45f` | `owner()` = **single EOA `0xE4fc…283d`** (code 0 on BSC and XL) | An upgrade can add a writer and rewrite any container's files (the `TapContainerLock` claims, the metadata host). |
| DomainBinding (all 3) | BSC `0x861E…3DB7`; Base/XL `0x6880…66f9` | UUPS, impl BSC `0xaa22…9bCE`, L2 `0x5eBF…47Df` | **single EOA `0xE4fc…283d`** | Can change fees and activation, which makes sites show `unpaid`. Can break `TapContainerLock.renew` (review L-9). |
| DeWEB hub (all 3) | `0xe61A…25ee` | UUPS; impl BSC `0x80aF…EE85`, Base `0x38A2…3867`, XL `0xdCC5…F9C6` (match TAP-10); `isSealed()` = false | `owner()` = **single EOA `0x571d…F15`** on all three chains (code 0) | Can rewrite outbox and inbox entries. That is the root of trust of draft B's hub profile. |
| Mining (BSC) | `0x7E2E…7b46` | ERC-1967, impl `0xa3db…f898` (source not publicly verified) | `owner()` = 0, `isSealed()` = true | None, provided the unverified implementation honours its seal. Draft C's PoD attributes read it. |
| Rig vault (BSC) | `0x48D4…17C2` | UUPS (`upgradeToAndCall`), impl `0xeb3f…6463`, `isSealed()` = false | `owner()` = **3/5 Safe** | Has `rescue(uint256,address)` and `rescueFromCell(...)`. `adapter()` = the BEM OFTAdapter (rigs ride OFT compose). |
| Rig voucher (XL) | `0x9cfc…E520` | ERC-1967, impl `0x66fb…85e1`, `isSealed()` = false | `owner()` = **3/5 Safe** | Upgradeable voucher. Its direct LZ config is the default (dead DVN, no delegate), which fits compose-only receipt; the voucher's selectors were not read. |
| BEM OFTAdapter (BSC) / BEM OFT (XL) | `0xa84B…5E72` / `0x60e6…3952` | Not proxies. Stock LZ OFT v1 (`oAppVersion` 1.2) | `owner()` and EndpointV2 `delegates()` = **3/5 Safe** | Can re-peer and re-configure DVNs, so it can mint BEM on X Layer or release BEM on BSC at will. Rigs inherit this. |
| 3/5 Safe | `0xB3D8…3138` (same on 3 chains) | Safe 1.4.1, threshold 3; no modules and no guard (read on BSC and Base) | Owners: `0x571d…F15`, `0x1183…843e`, `0x1023…3eFa`, `0x9e51…8789`, `0x847F…1bc5` (all EOAs) | Two signers are the hub-owner EOA and the Test1 issuer's holder key. |

### 3.2 LayerZero

| Item | Read | Meaning |
|---|---|---|
| EndpointV2 `0x1a44…728c` | No ERC-1967 slot on any chain (non-upgradeable). `owner()`: BSC `0xEFAC…1350`, Base `0xa039…9B7E`, XL `0xE590…3942` | The owner registers libraries and sets **defaults** only. |
| Endpoint owner type | BSC and Base: a 7,197-byte contract with `threshold()` = 5, `getSigners()` = 7 addresses and a `seed()` (a OneSig-style 5-of-7 multisig). X Layer: not read (rate limit). | Controls defaults. Irrelevant to OApps that pinned their libraries and config. |
| ULN302 send/receive | Not proxies. `owner()` = the endpoint owner on each chain (XL receive `0x2367…8312` → `0xE590…3942`) | Fixed code. The owner manages default configs and the treasury, not pinned OApp configs. |
| Executor (BSC `0x3ebd…4859`) | Transparent proxy, impl `0x43c6…dda2`, admin `0xa380…2d57` | Liveness only. A bad executor can refuse delivery but cannot forge a message (DVNs verify). |
| DVNs (Nethermind `0x31F7…1A73`, LZ Labs `0xfD68…15f0` on BSC) | Not proxies | Each DVN's own signer quorum is the trust unit. |
| Metadata | `deployments` SHA-256 `d1898aa5…a18f9` (same as draft B cites). `dvns` SHA-256 `894bab43…f8de` (fetched 2026-10-18) | — |

### 3.3 What a Test1 holder should check (in order of impact)

1. **`uriFrozen()` on Test1.** Until it is true, the circuit holder `0x1183…`, and the 3/5 Safe through a container-beacon upgrade, can repoint every token's metadata. `freezeBaseURI()` reverts while the base URI is empty, so the issuer must set the final base URI (a content-addressed or TAP-10 `meta/` path) and freeze. **This is the single most valuable holder protection, and it needs no bridge.**
2. **Factory `isSealed()` and circuit-beacon implementation** on X Layer: is it still `0x977f…29B2`? Any change can move circuit #1 and with it control of Test1's owner container.
3. **Container beacon `0x9b13…8f44`:** owner and `implementation()` (`0x6B6f…996B` today). A change re-defines `execute` for Test1's owner.
4. **SiteRegistry and DomainBinding** implementation slots and owner (`0xE4fc…`, single EOA). They matter only if metadata or the netlist files are served from a TAP-10 container.
5. If a bridge ever exists:
   - the home adapter's `owner()` and EndpointV2 `delegates(adapter)`;
   - `getConfig(adapter, receiveLib, eid, 2)`: number of required DVNs, confirmations, and that `isDefault` is false;
   - `peers(eid)` on both sides;
   - a timelock on any owner.

   The Base and BSC mirror's `owner()` and `setBaseURI` power also count.
6. **Not relevant to Test1:** mining (sealed), the rig vault and voucher, BEM.

---

## 4. Should bridging be in v1?

Test: name one v1 user story that needs a Test1 token to *live* on BSC or Base.

- **Content verification** (netlist, image, manifest hashes): reads X Layer state and files. No bridge is needed (draft A §8 L1 conformance works on the home chain).
- **PoD attributes** (draft C): computed from BSC mining reads, then published as metadata or as a companion on X Layer. That is a cross-chain read, done off-chain by tools. No token movement.
- **Trading:** Test1's market is on X Layer (the 30-day listing rule is a marketplace rule). Mirrors would fragment liquidity into separate marketplace collections.
- **Mining:** Test1 tokens are not rigs and cannot be registered as miners.
- **Games on BSC that want to see a holder's netlist:** solvable without moving the token. They can read X Layer off-chain, or later use lzRead from BSC targeting X Layer (if supported; §2), or the game can accept a signed snapshot.

No v1 story passes. Meanwhile bridging brings the largest unaudited code surface in the drafts (the security review's three Mediums included one bridge item, M-3), an unsolved open question that the draft itself marks **[Open]** (hub verifier), and a permanent-loss mode (`ALL` after `sealRoutes()`).

**Verdict: ADOPT NOW, descoping.** Keep draft B as Draft and mark it "not for v1 deployment". Re-base it on ONFT721 (§1.3) before any deployment. Spend v1 effort on §3.3 item 1 (final base URI plus freeze), on the companion (draft A §8.3), and on asking TapeOut to timelock the 3/5 Safe's beacon and factory powers and to move `0x571d…`/`0xE4fc…` ownership from single EOAs to the multisig.

---

## 5. Notes on the existing security review vs the current tree

`reviews/security-contracts.md` predates several fixes now in `contracts/src/bridge/`:

- **M-3:** fixed. `sealRoutes()` requires `adapterSealed()` on every listed adapter. `TapAdapterBase.seal()` runs `_onSeal()` (LZ: `setDelegate(0)`) and clears the owner in one call.
- **L-1:** fixed. `bridge` and `receivePayload` reject `to == peer` and `to == address(this)`.
- **L-2:** fixed in code. `messageId = keccak256(srcEndpoint ‖ payload)`.
- **Spec drift:** draft B §4.1, §4.3 and §5.1 still say `messageId = keccak256(payload)`. Check the vectors against the new definition.

These fixes do not change the recommendations above. They show the custom stack is still moving, which is itself a cost of maintaining a bespoke bridge standard.

---

## Evidence log (commands, all read-only)

- `cast storage <addr> <ERC-1967 impl/admin/beacon slot>`, `cast call <addr> 'owner()(address)' / 'isSealed()(bool)'` for every contract in §3, on all three RPCs.
- Safe: `getThreshold()` = 3 and `getOwners()` (5 EOAs, `codesize` 0) on BSC and X Layer.
- LayerZero: `EndpointV2.delegates(oapp)`, `getReceiveLibrary`, `isDefaultSendLibrary`, and `getConfig(oapp, lib, eid, 2)` decoded as `(uint64 confirmations, uint8 required, uint8 optional, uint8 optionalThreshold, address[] required, address[] optional)`:
  - BSC BEM: `(20, 2, 2, 1, [Nethermind 0x31F7…, LZ Labs 0xfD68…], [Horizen 0x2476…, Canary 0xfA9b…])`.
  - XL BEM: `(20, 1, 3, 2, [LZ Labs 0x9c06…], [Canary 0x047d…, Nethermind 0x28af…, Horizen 0xdd7b…])`.
  - DVN names from `metadata.layerzero-api.com/v1/metadata/dvns`.
- OP-stack: `0x4200…0015.version()` = `1.8.0+custom-gas-token`, `number()` = 26,213,929; `0x4200…0016` code present; EIP-2935 `0x0000F908…2935` codesize 83 on X Layer.
- Payments: `eth_call` simulation of `setOpener(0x…01)` from the deployer → `OpenerAlreadySet()`, from another address → `NotDeployer()`. No transaction was sent.
- Sources: LayerZero ONFT quickstart (docs.layerzero.network/v2/developers/evm/onft/quickstart); Cryptowisser, "OKX migrates XLayer to the OP Stack" (cryptowisser.com/news/okx-migrates-xlayer-to-the-op-stack).
