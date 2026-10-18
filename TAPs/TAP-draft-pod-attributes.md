---
tap: TBD
title: Proof-of-Design Attributes for Netlist-Bound NFTs
description: How a netlist-bound NFT whose netlist comes from a BEM miner circuit records that circuit's Proof-of-Design facts as a labelled snapshot at a pinned BNB Smart Chain block, in metadata and optionally as ERC-7496 traits.
author: Bruce (@BruceLanLan)
discussions-to: TBD
status: Draft
type: Application
created: 2026-10-18
requires: TAP-02, TAP-10, TAP-draft-netlist-bound-nft, ERC-7496 (ethereum/ERCs commit b7520ddde9f659fa40cda2e0849d987a4ff88bf5)
license: CC0-1.0
---

<!-- `requires`: `TAP-draft-netlist-bound-nft` is TAP-721, the requested number of the core draft; if editors assign another, this draft takes that number. -->

# TAP-TBD: Proof-of-Design Attributes for Netlist-Bound NFTs

## Summary

This TAP extends TAP-721 (Netlist-Bound NFTs) so that a TAP-721 token built from a TapeOut mining circuit can show how that circuit scored in Proof-of-Design mining, as a dated record that anyone can check against the chain, without suggesting that the NFT earns or owns anything.

## Abstract

This TAP is an extension of TAP-721 (Netlist-Bound NFTs, `TAP-draft-netlist-bound-nft`): it adds Proof-of-Design attributes to TAP-721 tokens and changes nothing in TAP-721 itself. A TAP-721 token can name a source circuit. When that circuit is registered as a miner in the BEM Proof-of-Design (PoD) mining contract on BNB Smart Chain, its PoD facts (for example its task, NAND and LATCH burn, design cost and optimal-first flag) are of interest to collectors. This TAP defines the `tap.pod` member of the token metadata: a snapshot of those facts read at one pinned block, with each field tied to the exact getter it comes from, split into recorded design facts and time-varying standing, and labelled with its block. It defines how a verifier re-reads and confirms a snapshot, fifteen ERC-7496 trait keys with their value encoding for collections that also publish the snapshot on chain, an optional unverified reference `tap.rig` to a rig voucher on X Layer, the claims a collection must not make, and, informatively, how collections can derive rarity from these attributes. It deploys no contract.

## Motivation

The collections that motivate TAP-721 draw their netlists from circuits that were mined under PoD. Collectors and marketplaces want to show what made those circuits notable: the task they solve, how many NAND and LATCH elements they burn, their design cost compared with the task's reference, whether they held the optimal-first slot. Today these facts are passed around as screenshots, often next to the community shorthand "C/N/L" for the three TapeOut primitives, of which only N and L are PoD facts. A miner's "verified" status is also often read as proof that the design works, although it only reports the mining contract's sampled check.

Three things go wrong without a convention. First, most of these facts change: the optimal-first slot can be taken over at any time, a miner can stop, and weights follow. A value copied into metadata without a block number becomes wrong without anyone noticing. Second, the facts are only meaningful together with the getter and the formula that produced them; "cost 108" means nothing without β and the depth. Third, a PoD attribute next to a rig or a token can easily be read as a claim on mining income. A shared format, a verification procedure and explicit non-claims address all three. ERC-7496 already defines on-chain traits for ERC-721 tokens, so this TAP uses it rather than defining a new interface (TAP-01 §10).

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

### 1. Terms and notation

| Term | Meaning |
|---|---|
| TAP-721 token (netlist-bound NFT), `tap` member, source circuit, `tap.source`, `tap.netlist` | As defined in TAP-draft-netlist-bound-nft (§1, §3, §7.1 of that draft) |
| Mining contract | The BEM PoD mining contract on BNB Smart Chain (chainId 56), proxy `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46` (Deployments) |
| Miner record | The tuple returned by `getMiner(minerKey(processor, circuitId))` for a circuit; a circuit **has a miner record** when that tuple's `taskId` is non-zero and its `circuits` equals the processor contract |
| Snapshot | A `tap.pod` object (§3): the facts of one miner record and the parameters they depend on, all read at one block |
| Snapshot block | The block of a snapshot (`tap.pod.block`) |
| Producer | Whoever writes a snapshot into a token's metadata or traits (normally the collection) |
| Verifier | Software that checks a snapshot against the chain (§4.2) |
| Live value | A value read at a block later than the snapshot block, for display next to a snapshot |

The names of `getMiner`, `minerKey`, `bestSlot`, `bonusOf`, `cachedDepth` and `processorMultiplier` and of the `getMiner` tuple members are those of the mining contract ABI fragments in the official PoD front end (tapeout.net/pod). `getTask`, `lambda()`, `beta()`, `lambdaBurn()` and `circuitBurn` do not appear there; their signatures were established by direct reads, and the `getTask` member names follow the `TaskAdded` event of the front end (`refArea`, `refCost`), whose meaning was confirmed numerically (Test Cases). These sources supply names only; the tuple positions in §3.4 and §3.5 and the selectors in §3.6 are normative. Decimal string: a JSON string of ASCII digits without sign, exponent or leading zeros (`"0"` for zero). Address: `0x` followed by 40 lowercase hexadecimal digits. Hash: `0x` followed by 64 lowercase hexadecimal digits. JSON numbers are integers between 0 and 2^53 − 1, as in TAP-draft-netlist-bound-nft §7.1.

### 2. Scope

1. This TAP applies to a TAP-721 token whose `tap.source` names a circuit on BNB Smart Chain that has a miner record at the snapshot block. Only circuits of processor contracts of the BNB Smart Chain processor factory (TAP-02, TAP-10) can be the source of a token that carries `tap.pod`; sources on other chains (TAP-draft-netlist-bound-nft §3) have no PoD facts.
2. A token MUST carry at most one `tap.pod` member, and it MUST describe the circuit named in `tap.source`. `tap.source` is REQUIRED when `tap.pod` is present, and `tap.source.chainId` MUST be `56`.
3. Every requirement of TAP-draft-netlist-bound-nft continues to apply. `tap.pod` and `tap.rig` are further members of `tap` in the sense of §7.1 of that draft; tools that do not implement this TAP ignore them.
4. A snapshot describes the source circuit, not the NFT. Its facts describe the NFT's netlist only when the source is confirmed (TAP-draft-netlist-bound-nft §3.2). A tool MUST NOT present PoD facts as facts about the NFT's netlist when the source is not confirmed; it MAY show them as "declared by the collection, not verified".

### 3. The `tap.pod` object

#### 3.1 Snapshot rule

1. All values of one snapshot MUST be read at one block `B` of BNB Smart Chain, given as `block`. `B` MUST be a block at which the circuit has a miner record.
2. The producer SHOULD choose `B` no later than the `finalized` block at the time of reading, SHOULD read from at least two independent node operators that agree (TAP-10 §5), and SHOULD record `blockHash`. An old `B` can only be read from archive nodes; public BNB Smart Chain nodes keep state for a short time only, so a producer that reads a recent block SHOULD cross-check it immediately.
3. Members are grouped by how they behave over time:
   - `design` holds **recorded design facts**: values stored in the miner record when the circuit was registered, and the cost derived from them. They do not change while the miner record exists, unless the mining contract's behaviour changes (Deployments). `area` and `bstar` were computed with the parameters in force at registration; `cost` uses β at `B` (`params.beta`). Because the mining contract reports itself sealed since block 121815032 (Deployments), β cannot change by upgrade after that block; snapshots of earlier blocks may use another β.
   - `params` holds the contract parameters at `B`.
   - `standing` holds **volatile facts**: status, optimal-first flag, bonus, multiplier, weights, `since` and `stopBlock`. They can change at any later block. The optimal-first slot in particular passes to another miner whenever a design with strictly smaller cost is registered for the same (task, processor) pair, and a holder can be removed from the slot after a counterexample ("kick"); the slot holder is therefore not always the design with the smallest cost (Test Cases).
4. A tool that displays any `standing` value MUST label it with the snapshot block (and SHOULD add the block's date), for example "optimal first at block 128200681 (2026-10-17 UTC)". It MUST NOT present a `standing` value as current. It MAY read and show live values next to the snapshot, labelled as live with their own block.
5. This TAP sets no maximum age for a snapshot. Tools SHOULD show its age.

#### 3.2 Members

| Member | Required | Type | Content |
|---|---|---|---|
| `v` | yes | number | `1` |
| `chainId` | yes | number | `56` |
| `block` | yes | number | The snapshot block `B` |
| `blockHash` | no (RECOMMENDED) | hash | Hash of block `B` |
| `timestamp` | no | number | Timestamp of block `B` (seconds) |
| `mining` | yes | address | `0x7e2e0dc66a3bd9103e69b766afa62d9f7b697b46` |
| `implementation` | no (RECOMMENDED) | address | The mining proxy's ERC-1967 implementation at `B` (storage slot `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`) |
| `processor` | yes | address | Processor contract of the source circuit; MUST equal `tap.source.processor` |
| `circuitId` | yes | decimal string | Circuit id; MUST equal `tap.source.circuitId` |
| `minerKey` | yes | hash | `minerKey(processor, circuitId)` at `B` |
| `params` | yes | object | §3.3 |
| `design` | yes | object | §3.4 |
| `standing` | yes | object | §3.5 |
| `functionCheck` | no (§3.9) | object | Result of an independent functional check against the task's reference circuit (§3.9) |

Members not listed here MAY appear; tools MUST ignore members they do not know. In the tables below, values whose ABI type is wider than 32 bits are decimal strings, and narrower values are JSON numbers.

#### 3.3 `params`

| Member | Type | Getter at `B` | Formula symbol |
|---|---|---|---|
| `lambda` | number | `lambda()` → `uint16` | λ |
| `beta` | number | `beta()` → `uint8` | β |
| `lambdaBurn` | number | `lambdaBurn()` → `uint16` | λ_burn |
| `processorMultiplier` | decimal string | `processorMultiplier(processor)` → `uint256` | P (current value for the processor) |

#### 3.4 `design` (recorded design facts)

Positions refer to the 22-member tuple returned by `getMiner(bytes32)`, counted from 0: `circuits` 0, `circuitId` 1, `taskId` 2, `gateCount` 3, `stateCount` 4, `depth` 5, `area` 6, `mult` 7, `since` 8, `status` 9, `registrant` 10, `nandBurn` 11, `latchBurn` 12, `bstar` 13, `bonus` 14, `optimal` 15, `commitBlock` 16, `firstUnusedId` 17, `stopBlock` 18, `verifWeight` 19, `unverWeight` 20, `debt` 21.

| Member | Type | Source | Meaning |
|---|---|---|---|
| `taskId` | number | `getMiner` [2] `taskId` (`uint32`) | The task the miner was registered for |
| `gateCount` | number | `getMiner` [3] `gateCount` (`uint32`) | g, elements counted for area |
| `stateCount` | number | `getMiner` [4] `stateCount` (`uint32`) | s, state elements |
| `nandBurn` | number | `getMiner` [11] `nandBurn` (`uint32`) | n, NAND elements burned |
| `latchBurn` | number | `getMiner` [12] `latchBurn` (`uint32`) | m, LATCH elements burned |
| `depth` | number | `getMiner` [5] `depth` (`uint32`) | d, logic depth as computed by the contract |
| `area` | decimal string | `getMiner` [6] `area` (`uint64`) | A = g + λ·s, as stored |
| `bstar` | decimal string | `getMiner` [13] `bstar` (`uint64`) | b* = n + λ_burn·m (burn basis), as stored |
| `cost` | decimal string | derived: `area` · max(`depth`, 1)^`params.beta`, exact integer | C, the design cost |
| `task` | object, optional | `getTask(taskId)` | `name` (string, tuple member 7), `kTask` (decimal string, tuple member 8, `refArea`), `cRef` (decimal string, tuple member 9, `refCost`) |

`cost` is not stored in the miner record; it MUST be computed exactly as above with `params.beta`, the value of β at `B` (§3.1 item 3). For the miner that holds the optimal-first slot, `bestSlot(taskId, processor)` returns the same value as `cost` (Test Cases). In `task`, `kTask` is the task's K_task (the reference implementation's burn basis) and `cRef` its C_ref, both frozen when the task was created; the front end displays `refArea` as K_task.

#### 3.5 `standing` (volatile facts)

| Member | Type | Source | Meaning |
|---|---|---|---|
| `status` | number | `getMiner` [9] `status` (`uint8`) | Raw status code |
| `statusLabel` | string | derived from `status` | `"mining"` for 1, `"unknown"` for every other code |
| `optimal` | boolean | `getMiner` [15] `optimal` | Held the optimal-first slot at `B` |
| `bonus` | decimal string | `getMiner` [14] `bonus` (`uint64`) | Design bonus K_task·q credited at `B` (0 when not optimal, as observed) |
| `multiplier` | number | `getMiner` [7] `mult` (`uint32`) | P applied to this miner |
| `verified` | boolean | derived: `verifWeight` > 0 | PoD sampling status at `B`: the mining contract's sampled vectors were accepted. It does not state that the netlist computes the task's function (§3.9) |
| `verifWeight` | decimal string | `getMiner` [19] `verifWeight` (`uint128`) | Verified weight H = (b* + bonus)·P |
| `unverWeight` | decimal string | `getMiner` [20] `unverWeight` (`uint128`) | Unverified weight |
| `since` | decimal string | `getMiner` [8] `since` (`uint64`) | Time the miner started (Unix seconds, as observed) |
| `stopBlock` | decimal string | `getMiner` [18] `stopBlock` (`uint64`) | Stop block, 0 if not stopped |

Status codes other than 1 have no confirmed meaning (Open questions). For them a tool MUST show `statusLabel` `"unknown"` together with the raw code and MUST NOT guess a meaning. `registrant`, `commitBlock`, `firstUnusedId` and `debt` are not attributes under this TAP; producers SHOULD NOT copy them into `tap.pod`, and `debt` (reward accounting) MUST NOT be presented as an attribute of the NFT.

#### 3.6 Getters and selectors

All are `view` or `pure` calls on the mining contract except `circuitInfo` and `netlist`, which are called on the processor contract. No transaction is needed to produce or verify a snapshot.

| Function | Selector | Returns |
|---|---|---|
| `minerKey(address,uint256)` | `0x10eafa00` | `bytes32` |
| `getMiner(bytes32)` | `0x0527edc2` | the 22-member tuple of §3.4 |
| `getTask(uint32)` | `0x57342d74` | `(uint8 kind, uint32 cycles, uint32 nIn, uint32 nOut, uint32 vectorCount, bool active, bytes32 vectorsRoot, string name, uint64 refArea, uint256 refCost, address refCircuits, uint64 refCircuitId)` |
| `lambda()` | `0xdad0be61` | `uint16` |
| `beta()` | `0x9faa3c91` | `uint8` |
| `lambdaBurn()` | `0xfd1b18bb` | `uint16` |
| `processorMultiplier(address)` | `0x0f03daba` | `uint256` |
| `circuitBurn(address,uint256)` | `0x6687aabd` | `(uint32 nandBurn, uint32 latchBurn)`, cross-check |
| `cachedDepth(address,uint256)` | `0xa18136f6` | `(bool cached, uint32 depth, uint32 live)`, cross-check |
| `bestSlot(uint32,address)` | `0x11d5a55c` | `(uint64 holderPlus1, uint256 cost)`, cross-check |
| `bonusOf(uint32,uint256)` | `0x500446c4` | `uint64`, cross-check |
| `isSealed()` | `0x631f9852` | `bool` (Deployments) |
| `circuitInfo(uint256)` (processor) | `0x084d60f1` | `(nIn, nOut, nState, gateCount)` |

#### 3.7 Consistency rules

A snapshot is **well-formed** when it follows §3.2–§3.5 and:

1. `design.cost` equals `design.area` · max(`design.depth`, 1)^`params.beta`;
2. `standing.verified` equals (`standing.verifWeight` ≠ `"0"`);
3. `standing.statusLabel` follows the table in §3.5.

A tool MUST reject a snapshot that is not well-formed. The following relations held for every miner read for this TAP but are not published rules of the mining contract; a tool SHOULD report a snapshot that breaks one of them as a warning, not reject it: `gateCount` = `nandBurn` + `latchBurn`; `area` = `gateCount` + λ·`stateCount` and `bstar` = `nandBurn` + λ_burn·`latchBurn` (these can legitimately differ if a parameter changed after registration); `bonus` = 0 when `optimal` is false; `verifWeight` = (`bstar` + `bonus`)·`multiplier` when verified; `multiplier` = `params.processorMultiplier`; `minerKey` = keccak256(`processor` (20 bytes) ‖ `circuitId` (32 bytes, big-endian)); `tap.netlist.nand` = `nandBurn` and `tap.netlist.latch` = `latchBurn`.

#### 3.8 Naming

Implementations MUST use the member and trait names of this TAP (`nandBurn`, `latchBurn`, `cost`, …) in machine-readable output. User interfaces SHOULD use the explicit labels "NAND burn", "LATCH burn" and "Design cost". The community shorthand "C/N/L" names the three TapeOut primitives: N and L correspond to `nandBurn` and `latchBurn`; C refers to the TapeOut container (电容), which this TAP does not describe — the source circuit's container is recorded by TAP-721 (`tap.source.container`). The letter C in the PoD formula of this TAP (C = A·max(d,1)^β) denotes the design cost `cost` and is unrelated to the C of "C/N/L"; interfaces MUST NOT label `cost` as the "C" of "C/N/L", and interfaces that use the shorthand SHOULD also show the explicit labels.

#### 3.9 Functional check (`functionCheck`)

1. `standing.verified` reports only the mining contract's sampling status. A tool MUST NOT present `verified` (or `verifWeight` > 0) as evidence that the netlist computes its task's function.
2. A collection or tool that presents a netlist as correct for its task (for example with a label such as "correct" or "proven", a trait, or by using correctness as a condition for eligibility or rarity) MUST check the netlist independently against the task's reference circuit: the circuit `refCircuitId` of processor contract `refCircuits` returned by `getTask(taskId)` at `B`. The check MUST be exhaustive over all 2^nIn input patterns when both circuits are combinational (no LATCH records) and nIn ≤ 16; otherwise it MUST follow a declared sampling procedure. The procedure `tap-pod-fc/1` below is one such procedure; a collection that uses another MUST publish it (§4.4).
3. The result SHOULD be recorded as `tap.pod.functionCheck`, an object kept separate from `standing.verified`:

   | Member | Required | Type | Content |
   |---|---|---|---|
   | `method` | yes | string | `"exhaustive"`, `"sampled"` or `"unconfirmed"` (the check could not be run, for example because the reference contains REF records that the checker cannot resolve) |
   | `vectors` | yes | number | Number of input patterns (combinational) or beats (sequential) compared; for a mismatch, up to and including the first differing one |
   | `result` | unless `unconfirmed` | string | `"match"` or `"mismatch"`; absent when `method` is `"unconfirmed"` |
   | `procedure` | yes | string | `"tap-pod-fc/1"`, or the identifier of the procedure the collection published |
   | `seed` | when `sampled` | hash | The 32-byte seed of the sampling procedure |
   | `reference` | unless `unconfirmed` | object | `processor` (address) and `circuitId` (decimal string) of the reference circuit |

   `method` `"exhaustive"` is allowed only when `design.stateCount` is 0; an exhaustive match has `vectors` = 2^nIn. A tool MUST NOT present a netlist as correct unless `result` is `"match"`, and SHOULD show the method and, for `sampled`, the number of vectors.
4. Procedure `tap-pod-fc/1`. Evaluation follows TAP-02 §4; input `j` is signal `2 + j`. The candidate and the reference must have equal `nIn` and `nOut`, otherwise the result is `"mismatch"` with `vectors` 0. `stream(seed, i_1, …, i_k)` is the bit string SHA-256(seed ‖ u32be(i_1) ‖ … ‖ u32be(i_k) ‖ u32be(0)) ‖ SHA-256(… ‖ u32be(1)) ‖ …, read byte by byte, least significant bit first.
   - Both combinational and nIn ≤ 16 (`exhaustive`): pattern `i` for `i` = 0 … 2^nIn − 1, input `j` = bit `j` of `i`.
   - Both combinational and nIn > 16 (`sampled`): 16,384 patterns; pattern `k` takes its inputs from `stream(seed, k)`.
   - Otherwise (`sampled`): 64 runs (1 run when nIn = 0); each run starts both circuits from the all-zero state and applies max(`cycles`, 32) beats, `cycles` from `getTask`; the inputs of beat `t` of run `r` come from `stream(seed, r, t)`; outputs are compared at every beat.
   - The default seed is SHA-256 of the ASCII string `TAP-pod functionCheck v1`, `0x2a8ae4d777d75596dacbaefb75c5ca2304bb0f292ce47b5a438665217d1b3a99`. A collection that uses the check for eligibility or labels MUST fix the seed it uses in its manifest (§4.4).

### 4. Producing, verifying and refreshing

#### 4.1 Producing

To produce a snapshot of circuit `(processor, circuitId)` at block `B`, a producer reads at `B`: `minerKey(processor, circuitId)`; `getMiner` of that key, and stops if the circuit has no miner record; `getTask(taskId)`; `lambda()`, `beta()`, `lambdaBurn()`, `processorMultiplier(processor)`; optionally the block header and the implementation slot. It builds the object of §3 and computes `cost`. It SHOULD also confirm the source under TAP-draft-netlist-bound-nft §3.2, preferably at the same block.

#### 4.2 Verifying

A verifier that checks a snapshot MUST:

1. check that the snapshot is well-formed (§3.7) and that `processor` and `circuitId` equal `tap.source`;
2. if `blockHash` is present, check it against block `block` of chain 56;
3. read, at `block`, every getter named in §3.3–§3.5 and compare each member with the value read (for `cost`, with the value recomputed from the values read).

The outcome is `confirmed` if every comparison holds, `mismatch` if any does not, and `unavailable` if the verifier cannot obtain state at `block` (for example because every reachable node has pruned it). A verifier MUST NOT report `confirmed` from reads at another block. It SHOULD warn when the mining proxy's implementation at `block` differs from the one listed in Deployments, since the getters' meaning may then differ. It SHOULD use two independent node operators and SHOULD report a read served by one operator only as single-source. It MAY also show live values (§3.1 item 4).

#### 4.3 Refreshing

A producer MAY replace a token's snapshot with a newer one. The new `block` MUST be greater than the previous one. Whether a collection is frozen is read from the chain, not from metadata (TAP-draft-netlist-bound-nft §7.2): at L1, `frozen()` returns true; at L0, the probe named in the manifest's `freeze` member returns its `expect` value (§5.1, §8 of that draft). Once the collection is frozen in this sense, its snapshots are not replaced. A refresh MUST NOT change a trait, label or rarity that the collection's committed rule derives from PoD facts (§4.4); those stay computed from the committed block. A collection SHOULD NOT refresh selectively (for example only for tokens whose standing improved); if it refreshes, it SHOULD refresh every token of the collection that carries a snapshot at the same block. When metadata changes, a collection that implements ERC-4906 emits `MetadataUpdate` or `BatchMetadataUpdate` as TAP-draft-netlist-bound-nft §8.2 requires.

#### 4.4 Commitment in the manifest

A collection whose tokens receive content through a reveal (TAP-draft-netlist-bound-nft §6) and that carries `tap.pod`, or that derives traits, labels, tiers, rarity or eligibility from PoD facts, MUST fix the following in its manifest before the master seed can be known, as required by TAP-draft-netlist-bound-nft §6.1:

1. the snapshot block, as `pod.block` (number) of the manifest;
2. every rule that derives traits, labels, tiers, rarity or eligibility from PoD facts, as `pod.rule`: an object with `sha256` (SHA-256 of the rule document) and `uris`. The rule document MUST be published by the same time;
3. if the rule or a label uses §3.9, the check procedure and its seed, as `pod.functionCheck`: an object with `procedure` and `seed` (hash).

At reveal, the snapshot of every token MUST be taken at `pod.block`; a later refresh (§4.3) may only increase `tap.pod.block`. A snapshot block or rule chosen after the seed is known MUST NOT be used. A tool that has the manifest SHOULD check these commitments and SHOULD report a collection that breaks them.

### 5. On-chain traits (ERC-7496)

#### 5.1 Interface

This TAP uses ERC-7496 "NFT Dynamic Traits" as of commit `b7520ddde9f659fa40cda2e0849d987a4ff88bf5` of the ethereum/ERCs repository (file `ERCS/erc-7496.md`, SHA-256 `a751a977c0b2db8904a2f976bf9f5afcafbecd06124754ebc94a7f3b2369a9d5`; Standards Track, category ERC, created 2023-07-28, requires EIP-165, EIP-721 and EIP-1155; status **Draft**, last checked 2026-10-17 UTC). The names, interface identifier and schema below are those of that text. A collection SHOULD state the commit of ERC-7496 it implements.

A collection MAY publish its snapshots on chain through ERC-7496. ERC-7496 traits are read from the token contract itself; a companion (TAP-draft-netlist-bound-nft §8.3) cannot carry them, so a collection whose token contract cannot be changed publishes `tap.pod` in metadata only. If a collection publishes traits, it MUST implement ERC-7496 in full, including `supportsInterface(0xaf332f3e)` returning true, and MUST define every trait of §5.2 (not a subset). The functions and events used are those of ERC-7496:

```solidity
function getTraitValue(uint256 tokenId, bytes32 traitKey) external view returns (bytes32 traitValue);     // 0xa28eec87
function getTraitValues(uint256 tokenId, bytes32[] calldata traitKeys) external view returns (bytes32[] memory traitValues); // 0xf80ecba3
function getTraitMetadataURI() external view returns (string memory uri);                                 // 0xde475bf9
function setTrait(uint256 tokenId, bytes32 traitKey, bytes32 newValue) external;                         // 0x2bf453e3
event TraitUpdated(bytes32 indexed traitKey, uint256 tokenId, bytes32 traitValue);
event TraitUpdatedRange(bytes32 indexed traitKey, uint256 fromTokenId, uint256 toTokenId);
event TraitUpdatedRangeUniformValue(bytes32 indexed traitKey, uint256 fromTokenId, uint256 toTokenId, bytes32 traitValue);
event TraitUpdatedList(bytes32 indexed traitKey, uint256[] tokenIds);
event TraitUpdatedListUniformValue(bytes32 indexed traitKey, uint256[] tokenIds, bytes32 traitValue);
event TraitMetadataURIUpdated();
```

#### 5.2 Trait names and keys

Each trait key is `keccak256` of the UTF-8 trait name, as ERC-7496 recommends. The names carry the prefix `tap.pod.` so that they cannot collide with a collection's other traits.

| Trait name | Trait key | dataType | Value |
|---|---|---|---|
| `tap.pod.snapshotBlock` | `0x0c83b866c7f4ae4bc14376df103564c65d79f5d851284a0c11a210f1728bca19` | decimal | `block` |
| `tap.pod.taskId` | `0xfd64ebeaade5a108f78bfc94ee0edfe916c75d828e7c70129827ea0caa1a4723` | decimal | `design.taskId` |
| `tap.pod.nandBurn` | `0xe6812d63110001a7da779d278372a1b4831d829f2b26af45f40826e40274f42b` | decimal | `design.nandBurn` |
| `tap.pod.latchBurn` | `0x91b9d0cc668255fa778685c7338fe63d92e536385c87f08c6e17a26d42c0ef85` | decimal | `design.latchBurn` |
| `tap.pod.area` | `0xef44719e0caef64b0ad22f820f1708667b608e0c4c59a80c8deebf8688627337` | decimal | `design.area` |
| `tap.pod.depth` | `0x691e154bb3637b1685d381f103f429ac2d4cdc57f92fd1f1194b47f0bd316e3e` | decimal | `design.depth` |
| `tap.pod.cost` | `0x1553b0cf7ee3f2ca0aa45a80f70c798570abcdf04acf5aec1a612b21ecc5d29b` | decimal | `design.cost` |
| `tap.pod.bstar` | `0x13d8a1dcf1cef697a18c42ef48929ae6e6124242f366c4ea7440825c3883cd36` | decimal | `design.bstar` |
| `tap.pod.status` | `0x5c1f2b4070b54fc2f5561f38390399cf8d4c29b81499370517a16c2717151d39` | decimal | `standing.status` |
| `tap.pod.optimal` | `0x8cc64f68d1b65bf6912ce63a85a0f5816e9b5a3ee7bdbd8bef65d7f44ca4abdb` | boolean | `standing.optimal` |
| `tap.pod.bonus` | `0xeb0e1e58cd5de11d87fbfa80b7b0c7db07fe2927be7ec0031c9c85d8b62ddb4a` | decimal | `standing.bonus` |
| `tap.pod.multiplier` | `0x8e86769259637e5965f73f19f92dd8221947eee18e3eb2566926f6e2184725ea` | decimal | `standing.multiplier` |
| `tap.pod.verified` | `0xa5dba9952bac764a13016b30c24d35b2efb5d9d9b33f600d4dcbfc44500659c5` | boolean | `standing.verified` |
| `tap.pod.verifWeight` | `0x0314874f9605c7d0456f0d16f4f551a20fbd2861f171aed22417d41a6f5da2d3` | decimal | `standing.verifWeight` |
| `tap.pod.unverWeight` | `0x0717ebcfb36876929ba6257ed6a85a3c22cc4ed0348df2bb927e4dbf3dcc811a` | decimal | `standing.unverWeight` |

#### 5.3 Value encoding

- `decimal` traits: the unsigned integer, big-endian, left-padded to 32 bytes (`bytes32(uint256(x))`); trait metadata `"signed": false`, `"decimals": 0`. If a value does not fit in 256 bits (possible only for `cost` with a large β), the collection MUST NOT publish traits for that token. `tap.pod.status` carries the raw code; it MUST NOT use `valueMappings`, because not every code is known.
- `boolean` traits: `bytes32(0)` for false and `bytes32(uint256(1))` for true, with no `valueMappings`; this 0/1 encoding is ERC-7496's default for booleans.
- Task names, `params`, `since`, `stopBlock` and `minerKey` have no trait; they are in the metadata only.

#### 5.4 Presence, writes and events

1. `tap.pod.snapshotBlock` is the presence marker: a token has PoD traits if and only if its value is non-zero. A token without a snapshot MUST return `bytes32(0)` for every trait of §5.2 (ERC-7496 already requires `bytes32(0)` for a defined trait without a value). A tool MUST NOT read a zero value of another trait as a fact unless `tap.pod.snapshotBlock` is non-zero; `latchBurn` 0 and `bonus` 0 are legitimate values.
2. Trait values MUST change only by an explicit transaction that writes the values of one snapshot. The contract MUST NOT compute them by calling the mining contract (or any other contract) at read time; ERC-7496 forbids trait values that change without an explicit on-chain action and an event.
3. A write MUST set all fifteen traits of a token from one snapshot in one transaction and MUST emit, for every trait key, `TraitUpdated` or one of the range or list events of ERC-7496. `tap.pod.snapshotBlock` MUST NOT decrease.
4. Whenever a token carries both `tap.pod` in its metadata and traits of §5.2, they MUST describe the same snapshot; where they disagree, tools MUST treat the token as `mismatch` until the collection corrects it. (ERC-7496 gives on-chain values precedence over metadata; this TAP adds that a disagreement is an error.)
5. `tokenOwnerCanUpdateValue` MUST be false for every trait of §5.2. `setTrait` and any other function that writes these keys MUST be restricted to an account the collection designates; the collection SHOULD expose that account as `owner()` (ERC-173) or name it in the trait metadata.
6. Once the collection is frozen in the sense of §4.3 (`frozen()` returns true at L1, or the manifest's `freeze` probe returns its `expect` value at L0), the traits of §5.2 MUST NOT be written again.
7. A collection MAY set `validateOnSale` to `requireEq` for `tap.pod.snapshotBlock`, so that an offer made against one snapshot cannot be filled after a refresh. For other traits of §5.2 it SHOULD be `none`.

#### 5.5 Trait metadata

The document returned by `getTraitMetadataURI()` MUST list each trait of §5.2 under its trait name with the `dataType` given in §5.3. `displayName` values MUST be unique (ERC-7496); the values in `assets/tap-pod-attributes/trait-metadata.json` are RECOMMENDED, and a collection that localises them SHOULD keep the words "at snapshot" for the volatile traits.

### 6. Rig reference (`tap.rig`)

`tap.rig` is an unverified reference. It MAY be present to point to a rig voucher on X Layer that the collection considers related to the source circuit's miner:

| Member | Type | Content |
|---|---|---|
| `chainId` | number | `196` |
| `contract` | address | `0x9cfc959cd42b2e1d39a0d850c528210e818ae520` (the official "TapeOut Rig" voucher, Deployments) |
| `id` | decimal string | The voucher token id |

1. This TAP defines no way to verify that the voucher belongs to the source circuit's miner, and a tool MUST NOT present it as verified.
2. A tool that displays it MUST label it as a reference, for example "related rig voucher (informative)", MAY read and show the voucher's current holder as a live value, and MUST NOT imply that the NFT holder holds, controls or benefits from the rig or the voucher.
3. `tap.rig` MUST NOT be used as an input to rarity or ranking (§8), and its absence MUST NOT be treated as a defect.

### 7. Claims

1. A snapshot is a record of facts about a circuit at a block. Holding a TAP-721 token that carries `tap.pod` or `tap.rig` confers no right to BEM, to mining rewards, to any share of a rig's output, to a rig or its voucher, to the source circuit or its container, and no yield of any kind.
2. A collection that follows this TAP MUST NOT describe a token, in its metadata, trait metadata or listing text, as entitling its holder to any of the above, and MUST NOT describe `verifWeight`, `unverWeight` or `bonus` as income of the NFT. It MUST NOT describe a token as an investment or financial instrument.
3. A tool that displays `standing` values SHOULD show, near them, a notice such as "Mining facts of the source circuit at block B. The NFT does not mine and earns nothing."
4. Adding `tap.pod` or `tap.rig` to a token's metadata does not back the token by a rig. For example, a collection whose tokens are not backed by rigs does not become backed by adding `tap.rig`, and MUST NOT suggest otherwise.

### 8. Deriving rarity (informative)

This section is informative; it adds no requirement. A collection that ranks tokens by PoD attributes can make rankings reproducible by publishing the rule and computing it from snapshot values only, for example:

- **Design efficiency** from recorded design facts: `q = cRef / cost` per task (higher is better; the mining formula clamps q to [1/4, 4], a ranking need not), or `cost` within one task;
- **Element mix**: designs with `latchBurn` > 0 (sequential) versus combinational designs; `nandBurn` buckets;
- **Task**: rarer tasks, by the number of tokens per `taskId` in the collection;
- **Optimal first at snapshot**: a badge, displayed with its snapshot block as §3.1 item 4 requires, because the slot moves.

A ranking rule is part of the commitment of §4.4 and is fixed before the seed. Rankings that reward low cost should require `functionCheck.result` `"match"`, because a design that computes the wrong function can be cheaper than every correct one. Rankings based on recorded design facts stay correct over time; rankings based on `standing` are only as current as the snapshot. Weights describe the mining contract's accounting, not the NFT, and are a poor basis for rarity. `tap.rig` is excluded (§6).

## Rationale

- **Relationship to TAP-721.** This TAP is a separate Application TAP rather than part of TAP-721 because it is tied to one deployment: the BEM PoD mining contract on BNB Smart Chain, its getters, its parameters and its proxy. TAP-721 is a Standards TAP whose rules apply to any TAP-721 collection on any TapeOut chain; PoD attributes apply only to tokens whose source circuit has a miner record, and they have to follow the mining contract if it is upgraded or replaced, which should not reopen TAP-721. A TAP-721 collection that does not draw on mined circuits ignores this TAP, and tools ignore `tap.pod` when they do not know it, as TAP-721 requires for members defined by other TAPs.
- **A snapshot, not a pointer.** The NFT may live on X Layer while the miner lives on BNB Smart Chain, and no contract on one chain can read the other. A labelled snapshot is honest about what the producer saw and when, and anyone can check it against an archive node. A pointer ("look up circuit #17851") would show whatever the chain says today and invite reading today's standing as a property of the NFT.
- **Two groups with different promises.** Design facts are stored once at registration; standing changes with every new design submitted for the task. Grouping them in the object, rather than flagging each field, lets tools apply one display rule (§3.1 item 4) and lets rarity rules choose stable inputs.
- **Getter-level definitions.** Every member names the getter and tuple position it comes from, so two producers get identical objects for the same block, and a verifier needs nothing but `eth_call`. `cost` is the only derived design value; it is defined from stored values so that it can be checked even where `bestSlot` does not return it (only the slot holder's cost is returned).
- **Explicit names.** In "C/N/L", N and L are the NAND and LATCH primitives, which the mining contract counts as `nandBurn` and `latchBurn`; C is the TapeOut container (电容), a different object that TAP-721 records as `tap.source.container`. The PoD formula also uses the letter C, for design cost. Machine-readable names are therefore the contract's own (`nandBurn`, `latchBurn`, `cost`), so that neither letter is ambiguous.
- **ERC-7496 rather than a new interface.** It is the existing ERC for on-chain traits of ERC-721 tokens, with a schema marketplaces can read. Its rule that traits change only by explicit, event-emitting writes matches the snapshot model exactly; a contract that read the mining contract live would violate it. The presence marker solves ERC-7496's zero default, which would otherwise make "no snapshot" indistinguishable from "LATCH burn 0".
- **All fifteen traits or none, written together.** Partial or mixed-block traits would let a token show a cost from one block and an optimal flag from another.
- **`verified` is not correctness.** The mining contract accepts a design after sampled vectors, so a verified netlist can compute a different function from its task's reference circuit, and such a design can be cheaper than every correct one (Test Cases). Naming the sampling status `verified` and the independent check `functionCheck`, in separate members, keeps the contract's word and the collection's claim apart. Exhaustive checking up to nIn = 16 is cheap (65,536 patterns); above that, and for sequential designs, a declared sampling procedure with a seed fixed before the reveal is the practical limit.
- **Commitment before the seed.** Standing facts change from block to block. If the snapshot block or the rarity rule could be chosen after the seed, the collection could pick the block or rule that favours tokens it already knows the owners of. Fixing both in the manifest, as TAP-draft-netlist-bound-nft §6.1 requires for every assignment and labelling input, removes that choice.
- **Status as a raw code.** Only code 1 is confirmed. Mapping unknown codes to words would invent semantics; the raw code with the label `unknown` is safe to extend later.
- **The rig reference is unverified.** The rig bridge exists, but nothing on chain ties a voucher id to a circuit in a way this TAP could check, and a verified-looking link between an NFT and a rig is exactly the misleading claim §7 forbids.
- **Alternatives considered.** Putting PoD facts only into ERC-721 `attributes`: kept as an allowed duplicate (TAP-draft-netlist-bound-nft §7.3 item 4) but not sufficient, because `attributes` has no block, no types and no verification rule. A cross-chain oracle that pushes live values: rejected for this version; it adds a trusted relayer and still cannot make standing a property of the NFT.

## Backwards Compatibility

This TAP only adds the members `tap.pod` and `tap.rig` and a set of ERC-7496 trait keys. Tools that implement TAP-draft-netlist-bound-nft but not this TAP ignore the new members (§7.1 of that draft). Collections that already show PoD facts in `attributes` can keep them and add `tap.pod`; where they disagree, `tap` prevails.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

## Test Cases

`assets/tap-pod-attributes/vectors.json` is generated by `make_vectors.py` from recorded reads, without network access, and is reproduced byte for byte by the test suite (SHA-256 `ade615b1a2e461d26bbf88b67eb93767eb88d26a189b824cf0c484108a4dbebb`; `trait-metadata.json` `336be474884b5cf2ce32ed77bdb05a75a02c8b96db1073e229fe287c6cdda0ac`). The reads were made read-only at BNB Smart Chain block 128200681 (hash `0xf4733a8a55285297dedf89f2ecf23911ecb2a5e3922cb3ab86690f5a278830c5`, timestamp 1792253755, 2026-10-17 16:15:55 UTC): `assets/chain-snapshot.json` (four circuits; the reads for TapeOut #17851 and #17852 agreed between two operators, while the reads for #3151 and #38 and the contract parameters `lambda()`, `beta()`, `lambdaBurn()`, `taskCount()` and both `processorMultiplier` values came from the archive node `https://tapeout.net/rpc` only) and `assets/tap-pod-attributes/raw/` (`pod_snapshot.py`, archive node, block header cross-checked with a second operator). For the three circuits in both sources, every field read agrees. Parameters at that block: λ = 6, β = 3, λ_burn = 1; `processorMultiplier` 1 for TapeOut (`0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`, processor 30) and 6 for Blonskr_No1 (`0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c`, processor 1); implementation `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898`.

| Circuit | Task (K_task, C_ref) | g, s | n, m | d | A | b* | C | Standing at block 128200681 |
|---|---|---|---|---|---|---|---|---|
| TapeOut #17851 | 3 XOR (4, 108) | 4, 0 | 4, 0 | 3 | 4 | 4 | 108 | status 1, not optimal (slot: #906, C 108), bonus 0, P 1, verifWeight 4 |
| TapeOut #17852 | 220 8-bit Johnson counter (25, 584) | 10, 9 | 1, 9 | 1 | 64 | 10 | 64 | status 1, not optimal (slot: #2033, C 64), bonus 0, P 1, verifWeight 10 |
| TapeOut #3151 | 48 8-bit population count (71, 290816) | 55, 0 | 55, 0 | 16 | 55 | 55 | 225280 | status 1, not optimal (slot: #14947, C 45056), bonus 0, P 1, verifWeight 55 |
| Blonskr_No1 #38 | — | — | — | — | — | — | — | no miner record (its netlist contains REF records, which the mining contract rejects): no `tap.pod`; every trait `bytes32(0)` |
| TapeOut #906 (slot holder) | 3 | 4, 0 | 4, 0 | 3 | 4 | 4 | 108 | optimal, bonus 4, verifWeight 8; `bestSlot` cost 108 |
| TapeOut #2033 (slot holder) | 220 | 10, 9 | 1, 9 | 1 | 64 | 10 | 64 | optimal, bonus 100, verifWeight 110; `bestSlot` cost 64 |
| TapeOut #14947 (slot holder) | 48 | 88, 0 | 88, 0 | 8 | 88 | 88 | 45056 | optimal, bonus 284, verifWeight 372; `bestSlot` cost 45056 |

What the vectors show: for each slot holder, `bestSlot(taskId, processor).cost` equals C = A·max(d,1)^β computed from the stored area and depth, and `bonusOf(taskId, C)` equals the stored bonus, which equals ⌊K_task·clamp(C_ref/C, 1/4, 4)⌋ (for #14947, C_ref/C ≈ 6.45 is clamped to 4: 71·4 = 284). #17851 and #17852 have the same cost as the slot holder and are not optimal, consistent with "strictly smaller". The member `verifiedButWrong` is a synthetic example, marked `"synthetic": true` and built from `synthetic/verified-but-wrong.json`: a three-NAND OR netlist recorded as a verified miner of the public XOR task 3 under a fictional processor and circuit id, in the context of the public reads of #906. It computes a different function from the task's reference circuit (an exhaustive `functionCheck` mismatch, differing on one of four patterns) and is cheaper than its slot holder (C 24 against 108) without holding the slot. Such miners exist on chain; a real instance is withheld from these vectors until it has been disclosed to the TapeOut team, and the synthetic example exercises the same check. Every stored `area` and `bstar` matches A = g + λ·s and b* = n + λ_burn·m; `nandBurn` and `latchBurn` equal the NAND and LATCH record counts of `netlist(id)` and `circuitBurn`; verifWeight = (b* + bonus)·P. `cachedDepth` returns the stored depth as its second value; its third value (`live`: 4, 10, 51) equals, for these three circuits, the number of live elements under §3 of the structural hash draft (TAP-draft-netlist-structural-hash); this is an observation, not a published rule, and this TAP does not use the value. Every snapshot carries `functionCheck` under `tap-pod-fc/1` against the reference circuits recorded in `raw/ref-task<id>.json` (processor `0xF4412C52ec3DDf7CAf5f518B6662F77B02Bde28E`, circuits 3, 48, 220): the XOR and population-count designs match exhaustively (4 and 256 patterns), the two Johnson counters match over 32 beats (sampled, default seed), and the synthetic `verifiedButWrong` example is an exhaustive mismatch although `verified` is true. The file also contains the trait values of every snapshot, the trait metadata, twelve snapshots that must be rejected (one rule each), five manifest commitment cases (§4.4), and a complete token metadata example with `tap.source`, `tap.netlist`, `tap.pod` and `tap.rig` that passes both this TAP's validator and the reference check of TAP-draft-netlist-bound-nft.

## Reference Implementation

Python 3.9, in `assets/tap-pod-attributes/` (MIT); ABI work uses Foundry's `cast`, keccak-256 uses pycryptodome:

| File | Covers |
|---|---|
| `pod_snapshot.py` | §4.1 reads at a pinned block (read-only JSON-RPC, cross-check across nodes, single-source reporting), §3 object, §5.3 trait values, §5.5 trait metadata, cross-checks of Test Cases |
| `pod_validate.py` | §3.7 well-formedness and warnings, §3.9 `functionCheck` format, §2 binding to `tap.source`, §4.4 manifest commitments, §6 `tap.rig` format |
| `function_check.py` | §3.9 procedure `tap-pod-fc/1` (uses the TAP-02 reference evaluator); `pod_snapshot.py --check` reads the reference circuit and adds `functionCheck` |
| `make_vectors.py` | `vectors.json`, `trait-metadata.json` |
| `test_pod.py` | Tests; regenerates the vectors and compares bytes |

Uses `assets/tap-netlist-bound-nft/tapnft.py`, `tap02_reference.py` and `assets/chain-snapshot.json`; these paths are updated when the folders are renamed `assets/tap-<nn>/` on number assignment.

Links at a fixed commit will be added before Review (TAP-01 §7.2 item 8).

## Deployments

This TAP deploys no contract. It reads:

| Chain (chainId) | Contract | Address | State read for this draft | Sealed? |
|---|---|---|---|---|
| BNB Smart Chain (56) | PoD mining contract (ERC-1967 proxy, UUPS) | `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46` | Implementation `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898` at every block sampled from 119600000 to 128200681; `isSealed()` true and `owner()` zero at block 128200681 | Yes, by its own report: `seal()` was executed at block 121815032 (transaction `0xb42998938688380c395a904e055ffc98e7d4e67cae274228b793aeec715a300d`), emitting `OwnershipTransferred` to the zero address and `Sealed()`. The previous owner was `0xbc951f39eA94818f54A6AbBF0FAC1Fe6AEce4876`, a timelock (`getMinDelay()` 172800 s), executed by `0x571d447f4f24688eC35Ccf07f1D6993655F6aF15` |
| BNB Smart Chain (56) | Processor contracts named as sources | e.g. TapeOut `0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`, Blonskr_No1 `0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c` | `circuitInfo`, `netlist` (source check, TAP-draft-netlist-bound-nft §3.2) | Beacon proxies behind an unsealed factory (TAP-02) |
| X Layer (196) | TapeOut Rig voucher ("TapeOut Rig"/RIG, proxy) | `0x9cfc959cd42B2e1d39a0d850c528210E818AE520` | Not read by this TAP; named in `tap.rig` only | No (owner `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138`) |

Anyone can repeat the mining-contract checks with `eth_call` (`isSealed()` `0x631f9852`, `owner()` `0x8da5cb5b`) and `eth_getStorageAt` on the slot in §3.2.

**What this means for snapshots.** While the mining contract could be upgraded, an upgrade could have changed the meaning of any getter, so a snapshot was only a statement about the implementation in force at its block; recording `implementation` makes that explicit. The chain shows that ownership was renounced and the contract reports itself sealed since block 121815032, so, if `seal()` removes every upgrade path, the getters' meaning can no longer change by upgrade. This cannot be fully confirmed without the implementation's source, which was not found verified on a public explorer (Open questions). For this reason §3.2 recommends recording `implementation`, and §4.2 asks verifiers to warn when it differs from the implementation listed here. Because this TAP depends on the mining contract's behaviour, it can become Final only if that contract is sealed (TAP-01 §5.1); if the seal is confirmed from source, that condition is met.

## Security Considerations

- **Stale snapshots.** A snapshot is true at its block and may be false a block later. The main risk is display: a marketplace that shows "optimal first" without the block suggests a property that has already passed to another design. §3.1 item 4 and the presence of `block` in every object and trait set are the defence; tools that show live values next to the snapshot make staleness visible.
- **Cherry-picked blocks.** A producer chooses the block. It can choose one at which the circuit was optimal or had a high weight, and refresh only tokens that improved. Verification (§4.2) proves the values were true at that block, not that the block is representative. Tools should show the snapshot's date and, where possible, live values; §4.3 asks collections to refresh uniformly.
- **Contract behaviour.** The facts mean what the mining contract computes. Before block 121815032 its owner could upgrade it through a 48-hour timelock; since then it reports itself sealed. If the seal does not cover every upgrade or parameter path, later snapshots may follow different rules than earlier ones. Recording `implementation` and the `params` of each snapshot keeps snapshots comparable or shows that they are not.
- **Trusted writer for on-chain traits.** An NFT contract on X Layer cannot read BNB Smart Chain. Its ERC-7496 values are whatever its writer submits. They are checkable (§4.2), not self-verifying; marketplaces that rely on them should verify against BNB Smart Chain or mark them as reported by the collection.
- **Misleading marketing.** PoD weights look like earnings, and a rig reference looks like backing. §7 forbids both claims; tools should display the notice of §7 item 3 and must not show `tap.rig` as verified. A collection that breaks §7 does not follow this TAP, whatever else it implements.
- **Unverified sources.** A snapshot can be attached to any NFT. Without a confirmed source (TAP-draft-netlist-bound-nft §3.2), the PoD facts belong to some circuit, not necessarily to the NFT's netlist; §2 item 4 limits how they may be shown.
- **Node answers.** A lying node can forge any read. Two independent operators defeat one liar; old blocks are often served by one archive operator only, and verifiers should say so. `blockHash` detects a wrong chain or a reorganised block.
- **Draft dependency.** ERC-7496 is itself a Draft. If its interface or schema changes, on-chain traits written under this TAP may no longer match what marketplaces expect; collections state the revision they implement (§5.1), and the metadata snapshot does not depend on ERC-7496.
- **Wrong designs presented as correct.** A collection that shows "verified" as "correct", or ranks by cost without a functional check, can give its rarest label to a design that computes the wrong function (Test Cases). §3.9 forbids the first and requires the check for the second.
- **Grinding after the seed.** Without §4.4 a collection could choose the snapshot block or the rarity rule after seeing which tokens get which netlists.
- **Untrusted strings.** Task names are set on chain by task creators and copied into `tap.pod.design.task.name`. Tools must treat them as untrusted text (escape for HTML, no rich rendering) and must not use them as identifiers; `taskId` is the identifier.

### Open questions

1. **Status codes.** Only `status` 1 ("mining") is confirmed: the official front end tests `status === 1`. The front end has been observed to offer a restart for code 3, which suggests "restartable", but this could not be confirmed in its published bundle, so this TAP labels 3 `"unknown"` like codes 0, 2 and 4–255. Can the PoD authors publish the full table?
2. **Mining contract source.** The implementation `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898` was not found verified on a public explorer. Without it, the field semantics (in particular `stateCount`, `depth`, `unverWeight`, the third value of `cachedDepth` (observed to equal the live-element count, Test Cases), and whether `seal()` removes every upgrade and parameter path) are inferred from observation and the front end.
3. **`refArea` as K_task.** The ABI member `refArea` behaves as K_task (it matches `bonusOf` for three tasks, and for task 220 it is not the reference's area, since 584 is not a multiple of 25). Should `tap.pod` keep the name `kTask`?
4. **Stable task id.** Can a stopped and restarted miner change `taskId`? If so, `taskId` belongs in `standing`.
5. **Sequential check semantics.** `tap-pod-fc/1` compares sequential designs beat by beat from the all-zero state. Tasks whose vectors allow a warm-up or a phase offset may need another procedure; the task vector format is not published. Should the PoD authors' vector semantics replace it once available?
6. **Rig mapping.** Is there an on-chain mapping from a rig voucher id to a (processor, circuit id) miner that a later version could verify?
7. **Second operator.** The reads for #3151, #38, the reference circuits and the contract parameters come from one archive operator only (Test Cases). Before Review they should be repeated with a second operator that serves block 128200681.

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
