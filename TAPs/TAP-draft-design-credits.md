---
tap: TBD
title: Design Credits and Lineage for TapeOut Netlists
description: How tools show what the chain records about the first publication of a TapeOut circuit as checked facts, and how designers sign credit, lineage and revocation statements about netlists as claims, without mixing the two.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/72
status: Draft
type: Application
created: 2026-10-19
requires: TAP-02, TAP-10, TAP-draft-netlist-bound-nft, TAP-draft-netlist-structural-hash, EIP-712, ERC-721, ERC-1271
license: CC0-1.0
---

# TAP-TBD: Design Credits and Lineage for TapeOut Netlists

## Summary

This TAP lets wallets, explorers and circuit tools show who first put a circuit on chain as a checked fact and who says they designed it as a signed claim, and never present the second as the first.

## Abstract

Authorship of a netlist cannot be proven on chain: netlists are public, anyone can tape out a netlist they did not design, two designers can arrive at the same netlist independently, and the account that tapes out a circuit may be a relayer, a wallet contract or a miner who did not design it. This TAP separates two layers. The **facts layer** holds what anyone can check against the chain: the *publication fact* of a circuit (the account its circuit token was minted to, the chain, processor, circuit id, block, transaction and log), with an exact verification procedure, and the *earliest known occurrence* of a design, an indexer statement over a declared scope that anyone can refute by showing an earlier verified occurrence with the same netlist hash or structural hash. The **claims layer** holds EIP-712 statements signed by an externally owned account or an ERC-1271 contract account with a chain-agnostic domain: *Credit* (a role such as designer or optimizer for a design, with an optional self-declared display name, a design note fixed by its SHA-256 and a licence), *Lineage* (derivedFrom, supersedes and optimizes edges between designs) and *Revocation*. Facts and statements travel in a *credit bundle*, either as a standalone JSON file or as the `tap.credits` member of TAP-721 token metadata, and can be anchored in time by logs of an informative events-only contract pattern. Display rules oblige tools to show facts as verified only after verification, to show every claim as a claim with its signer, to keep claims out of the facts layer, and to show conflicting claims side by side. The TAP grants no royalty, yield, exclusivity or identity verification.

## Motivation

TapeOut circuits are ERC-721 tokens, and TAP-721 binds collectible tokens to their netlists. Wallets, explorers, collection pages and circuit editors increasingly show a line such as "designed by" next to a circuit. Today that line is filled from whatever address is at hand: the current holder of the circuit token, the account that sent the tape-out transaction, or the `registrant` of a Proof-of-Design miner record. None of them says who designed the netlist; the PoD attributes draft likewise keeps the registrant out of its attributes (`TAP-draft-pod-attributes` §3.5, informative).

The gap is real on mainnet. BNB Smart Chain circuit `17851.30.tape`, a Proof-of-Design miner and the worked example of the TAP-721 drafts, has the same netlist hash as circuit `3.635.tape`, the reference circuit of the XOR task in processor "RefBench", taped out by a different account 57 days earlier (Test Cases). A scan of two processors finds 130 further circuits with that netlist hash; the earliest, `906.30.tape`, was taped out by a third account about 20 hours before the reference circuit. All of these circuits are legitimate. The netlist is the textbook four-NAND XOR, which many people derive on their own, and an identical netlist can be an independent derivation as well as a copy. The chain cannot tell the two apart: it records who taped out which netlist and when, not who designed it or where it came from. That is why this TAP exists. A tool that labels any of these accounts as the designer, the earliest included, is guessing.

Designers still want credit, and collectors and players want to know the history of a design: which design an optimization improved, which version supersedes which, who reviewed it. That information exists only as claims. Claims are useful when they are signed, portable across tools and chains, revocable by their signer, and displayed so that nobody mistakes them for facts. No TapeOut standard defines such statements, and general attestation schemes do not say which TapeOut facts can be checked, how, or what a tool may conclude from them.

This TAP therefore defines a small set of checkable facts with exact procedures, a small set of signed claims with exact encodings, and display rules that keep them apart.

ERC-5375 lets the authors of an NFT give EIP-712 signed consent to being named as its authors, and states that such consent is not proof of authorship. This TAP applies the same idea to TapeOut netlists and keeps signed claims apart from the facts the chain records. The authors therefore request the number 5375 (proposal name TAP-5375, mirroring ERC-5375); because TAP-01 §6.1 otherwise assigns the lowest free number above 10, this needs the editors' agreement. Until a number is assigned, the draft keeps the file name `TAP-draft-design-credits.md` and `tap: TBD`; the editors assign the final number, and if it differs, the draft takes that number.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

### 1. Terms and notation

| Term | Meaning |
|---|---|
| Circuit | A circuit stored by a processor contract (TAP-02), identified by (chain id, processor contract, circuit id) |
| Netlist file, netlist hash | As in `TAP-draft-netlist-bound-nft` §2 for `tapnet/1`: the `tapnet/1` file and its SHA-256 (§2.3). Netlist formats defined under its §2.5 are not covered by this TAP |
| Structural hash | As in `TAP-draft-netlist-structural-hash` §7 |
| Design | A netlist hash, a structural hash, or both. A design reference with only a structural hash names every netlist file with that structural hash |
| Design of a circuit | The netlist hash and structural hash of the file built from the circuit (§3.3) |
| Applies | A design reference applies to a circuit when every non-zero hash in it equals the circuit's (§3.3) |
| Publication fact | The record of a circuit's first mint (§3.1) |
| First publisher | The account the circuit token was first minted to (§3.1) |
| Finality-tag block | The block a chain's finality tag of TAP-10 §2.1 names: `finalized` on BNB Smart Chain, `safe` on Base and X Layer |
| Earliest-occurrence statement | An indexer's statement that a publication fact is the earliest occurrence of a design within a scope (§3.4) |
| Statement | A signed Credit, Lineage or Revocation message (§4) |
| Claim | A Credit or Lineage statement |
| Signer account | The pair (`signer`, `signerChainId`) of a statement (§4.4) |
| Verification block | The block at which a contract signer's statement is checked (§4.6 item 4) |
| Credit bundle | The JSON object of §5.1 that carries facts and statements |
| Producer | Anyone who writes a credit bundle |
| Tool | Software that displays facts or claims under this TAP |

Byte strings in JSON are `0x` followed by lowercase hexadecimal digits: 64 for a 32-byte value, 40 for an address. `‖` is concatenation. `keccak256` is the hash function of EIP-712; SHA-256 is the hash function of FIPS 180-4. Chain reads follow TAP-10 §5: "two nodes" below means two nodes of different operators (TAP-10 §5.1), and answers are compared after the normalisation of TAP-10 §5.2.

Information under this TAP falls into three classes: **verified facts** (§3.1–§3.3 after verification), **earliest-occurrence statements** (§3.4: the occurrence is checkable, the earliness is only refutable) and **claims** (§4). §6 says how tools display each class.

### 2. Scope and non-claims

This TAP defines facts, statements and display rules. A fact, an earliest-occurrence statement or a statement under this TAP does not confer, and producers and tools MUST NOT present it as conferring: a royalty, revenue share or any payment; yield, mining income or any Proof-of-Design reward; exclusivity or any right to stop others from taping out, copying or using a netlist; enforcement of a licence; ownership of a circuit token, a container or a TAP-721 token; or verification of anyone's identity.

### 3. Facts

#### 3.1 Publication fact

When a processor contract tapes out a circuit, it mints the circuit token with ERC-721 `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)` from the zero address (TAP-02 §6). The **publication fact** of the circuit is the following JSON object:

| Member | Required | Type | Content |
|---|---|---|---|
| `chainId` | yes | number | The chain id (TAP-10 §2.1) |
| `processor` | yes | string | The processor contract address |
| `circuitId` | yes | string | The circuit id, decimal |
| `publisher` | yes | string | The `to` address of the mint log: the first publisher |
| `block` | yes | number | The number of the block containing the mint log |
| `blockHash` | yes | string | The hash of that block |
| `txHash` | yes | string | The hash of the transaction containing the mint log |
| `logIndex` | yes | number | The `logIndex` of the mint log as returned by `eth_getTransactionReceipt` |
| `timestamp` | no | number | The block's timestamp; required inside an earliest-occurrence statement (§3.4) |
| `name` | no | string | The circuit's on-chain name (TAP-10 §3.1) |
| `txFrom` | no | string | The sender of the transaction (informative, §3.5) |

Numbers are JSON integers between 0 and 2^53 − 1. A publication fact with other members is malformed.

#### 3.2 Verifying a publication fact

A tool MUST verify a publication fact as follows before it treats the fact as verified. `chainId` MUST be a chain of TAP-10 §2.1. Every read in steps 1–4 and 6 MUST be made on at least two nodes, and every value compared MUST be identical on all of them after normalisation; receipts are compared on `status`, `blockNumber`, `blockHash`, `transactionHash`, `from` and, for each log, `address`, `topics`, `data` and `logIndex`, and block headers on `number`, `hash` and `timestamp`. Steps 1, 4 and 6 read contract state at one block at or after `block`, the **state block**, which the tool records; a tool SHOULD use the finality-tag block of step 7 (processor numbers are append-only and never reused, TAP-10 §1 and §4.3, and circuits are not removed, so every such block gives the same answer).

1. Confirm that `processor` is registered with the chain's processor factory (`isCPU(address)`, selector `0x5f5a364f`), using only the factory addresses that TAP-10 lists under Deployments.
2. Read the receipt of `txHash` (`eth_getTransactionReceipt`). It MUST have `status` 1, `blockNumber` equal to `block` and `blockHash` equal to `blockHash`. Read the header of block `block` (`eth_getBlockByNumber`); its hash MUST equal `blockHash`.
3. The receipt MUST contain exactly one log that is emitted by `processor`, has four topics, has `topics[0]` = `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` (`Transfer`), `topics[1]` = zero and `topics[3]` = `circuitId` as a 32-byte big-endian integer. Its `logIndex` MUST equal `logIndex` and its `topics[2]` MUST equal `publisher`, left-padded to 32 bytes.
4. `circuitInfo(circuitId)` (TAP-02 §6) MUST NOT revert at the state block.
5. If `timestamp` is present, it MUST equal the timestamp of the header read in step 2. If `txFrom` is present, it MUST equal the receipt's `from`.
6. If `name` is present, it MUST equal the on-chain name of TAP-10 §3.1 computed from `circuitId`, the chain's area code and the processor number `k` for which `cpuAt(k)` returns `processor`.
7. `block` MUST NOT be above the finality-tag block (TAP-10 §2.1) reported by any node used. A fact that passes steps 1–6 but not step 7 is **unfinalized**; a tool MUST NOT display it as verified.

A fact that passes every step is **verified**. The tool records the time of verification, the state block and the nodes used. A tool that knows of more than one mint log for the same processor and circuit id (for example from a log index) MUST treat every publication fact of that circuit as failed and SHOULD report the conflict.

A tool MAY also check that the receipt contains a log from `processor` with `topics[0]` = `0xc11215e417669c143c8a07aeb778034c0a0a85ebdf305d64a629b19a7a9ce031` (the deployed `TapedOut(uint256,address,uint32,uint32)` event), `topics[1]` = `circuitId` and `topics[2]` = `publisher`. This log is corroboration only; this TAP does not interpret its data words, and its absence does not fail the fact.

Finding the transaction is not part of verification. A producer can locate it with `eth_getLogs` on the processor for `Transfer` with `topics[3]` = `circuitId`, or for the `TapedOut` event with `topics[1]` = `circuitId`, over a block range in which the circuit was created.

#### 3.3 Design of a circuit

The design of a circuit is computed by building the `tapnet/1` file from `circuitInfo(circuitId)` and `netlist(circuitId)` exactly as in `TAP-draft-netlist-bound-nft` §3.2 steps 2–3, and then:

- `netlistHash` = SHA-256 of that file, if the file is valid (`TAP-draft-netlist-bound-nft` §2.2);
- `structuralHash` = the structural hash of that file (`TAP-draft-netlist-structural-hash` §7).

A circuit whose netlist contains a REF record has no design under this version. A design reference D (a pair of a netlist hash and a structural hash, zero meaning "not given") **applies** to a circuit C if and only if C has a design and every non-zero hash in D equals the corresponding hash of the design of C. A statement applies to C when its `subject` applies to C. A verified publication fact is a publication fact **of design D** when D applies to its circuit.

#### 3.4 Earliest-occurrence statements

An **earliest-occurrence statement** is a JSON object:

| Member | Required | Type | Content |
|---|---|---|---|
| `tapEarliest` | yes | number | `1` |
| `key` | yes | object | `kind`: `"netlist"` or `"structural"`; `hash`: a netlist hash or structural hash |
| `occurrence` | yes | object | A publication fact (§3.1) that includes `timestamp` |
| `scope` | yes | array | One or more objects with `chainId` (number), `processors` (`"all"` or a non-empty array of distinct processor numbers, TAP-10 §1) and `toBlock` (number) |
| `indexer` | no | string | Who made the statement: free text or a URI, at most 256 bytes of printable ASCII; unverified |
| `asOf` | no | string | ISO 8601 date and time of the scan |

The **processor number** of a publication fact is the `k` for which `cpuAt(k)` returns its `processor` (TAP-10 §4.3 step 3). A publication fact lies **inside the scope** when some entry of `scope` has its `chainId`, has `processors` equal to `"all"` or containing its processor number, and has `toBlock` at or above its `block`. The occurrence MUST lie inside the scope.

A producer MUST list in `scope` only processors it scanned completely: every circuit id from 1 to the latest id of each listed processor at `toBlock`, or every processor of the factory at `toBlock` for `"all"`. This rule binds producers. Tools cannot check it and do not use it in judging; an incomplete scan shows up only when someone publishes an earlier occurrence.

**Order.** For two publication facts `a` and `b`: if they are on the same chain, `a` precedes `b` when `(a.block, a.logIndex)` is lexicographically smaller than `(b.block, b.logIndex)`; if they are on different chains, `a` precedes `b` when the timestamp of `a`'s block is smaller than that of `b`'s block (the header timestamps read in §3.2 step 2, whether or not the facts carry `timestamp`), and two facts with equal timestamps on different chains are **tied**. A fact whose header timestamp the tool does not have cannot be ordered against facts on other chains; the tool leaves it out of those comparisons and SHOULD say so.

**Judging.** A tool judges an earliest-occurrence statement S as follows:

1. S is **invalid** unless it follows the form above and its `occurrence` is a verified publication fact (§3.2) whose design (§3.3) has `key.hash` as its netlist hash (`kind` `"netlist"`) or structural hash (`kind` `"structural"`) and which lies inside the scope. A tool that does not know the occurrence's processor number treats it as inside the scope only through an entry with `processors` = `"all"`.
2. Consider every verified publication fact O′ known to the tool whose design has the same hash of the same kind and which precedes S's occurrence. If any such O′ lies inside the scope, S is **refuted** by the earliest of them; otherwise, if any exists, S is **superseded** by the earliest of them. An O′ whose processor number the tool does not know counts as outside the scope.
3. Otherwise S is **standing**. Its **standing set** is its occurrence together with every known verified fact of that design that is tied with the occurrence and that no known verified fact of that design precedes.

A tool that knows a refuting or superseding occurrence MUST NOT display S's occurrence as the earliest known one and MUST display the earliest occurrence it knows instead. Anyone can refute or supersede a statement by publishing a publication fact of an earlier occurrence; no other evidence is needed. Cross-chain ties are common: BNB Smart Chain produces a block about every 0.45 seconds while header timestamps count whole seconds, so several of its blocks share each timestamp.

#### 3.5 What facts do not establish

- The first publisher is the account that called the tape-out function. It can be an externally owned account, a wallet contract, a relayer, a TapeOut container acting through ERC-6551 `execute`, or an account that took the netlist from someone else or derived it independently. Tools MUST NOT describe the first publisher as the designer, author or creator of the netlist.
- `txFrom` is the account that signed the outer transaction. When it differs from `publisher`, the tape-out was made through a contract. It MUST NOT replace `publisher` in any rule of this TAP.
- A relayer or contract that tapes out for a user may then transfer the circuit token to that user, which emits a later `Transfer` log. A tool MAY show that transfer, as a transfer at its block; it does not change the publication fact or the first publisher.
- The current holder of a circuit token (`ownerOf`) and the `registrant` of a Proof-of-Design miner record (position 10, counted from 0, of the tuple returned by `getMiner(bytes32)` of the Proof-of-Design mining contract) are not facts under this TAP: neither is a publication fact, and neither is a designer. Tools MUST NOT present either as the first publisher or as a designer. (Informative: `TAP-draft-pod-attributes` §3.4 lists that tuple, and its §3.5 keeps `registrant` out of its attributes; this rule does not depend on that draft.)
- An earliest-occurrence statement says nothing about designs that were never taped out, that were taped out outside its scope, that contain REF records, or that differ only in ways the structural hash does not ignore (`TAP-draft-netlist-structural-hash` §8). Tools MUST NOT present the earliest known occurrence as the origin of a design.

### 4. Claims: signed statements

#### 4.1 Envelope

A statement is carried in an **envelope**, a JSON object with exactly these members:

| Member | Type | Content |
|---|---|---|
| `tapCredit` | number | `1` |
| `type` | string | `"Credit"`, `"Lineage"` or `"Revocation"` |
| `message` | object | The message, with exactly the members of the type in §4.3 |
| `signature` | string | `0x` followed by an even number of lowercase hexadecimal digits, at most 2,048 bytes |

The UTF-8 serialisation of an envelope MUST NOT exceed 8,192 bytes. In `message`, `address` values are lowercase addresses, `bytes32` values are 32-byte strings, `string` values are JSON strings, `uint64` values and the `uint256` members `signerChainId` and `chainId` are JSON integers between 0 and 2^53 − 1, and the `uint256` member `circuitId` is a decimal string without leading zeros. A tool MUST reject an envelope that breaks any rule of §4.1–§4.4.

#### 4.2 Domain

Statements are EIP-712 typed data with the domain

```
EIP712Domain(string name,string version)
name    = "TAP Design Credits"
version = "1"
```

The domain has no `chainId`, `verifyingContract` or `salt`, so a statement is valid on no particular chain and the same statement can be shown on every chain. The domain separator is listed in Test Cases, and Appendix A gives a complete `eth_signTypedData_v4` payload.

#### 4.3 Types

```
DesignRef(bytes32 netlistHash,bytes32 structuralHash)

Circuit(uint256 chainId,address processor,uint256 circuitId)

Credit(address signer,uint256 signerChainId,DesignRef subject,Circuit source,string role,string displayName,string noteURI,bytes32 noteSha256,string license,uint64 issuedAt,bytes32 nonce)

Lineage(address signer,uint256 signerChainId,DesignRef subject,string relation,DesignRef object,string reason,uint64 issuedAt,bytes32 nonce)

Revocation(address signer,uint256 signerChainId,bytes32 statement,string reason,uint64 issuedAt)
```

`hashStruct`, `encodeType` (referenced types appended in alphabetical order: `Circuit`, then `DesignRef`) and the digest follow EIP-712:

```
digest = keccak256(0x19 ‖ 0x01 ‖ domainSeparator ‖ hashStruct(message))
```

The digest is the **statement id**. Two envelopes with the same type and message are the same statement, even if their signatures differ.

#### 4.4 Field rules

| Field | Rule |
|---|---|
| `signer` | Not the zero address. The account that makes the statement |
| `signerChainId` | `0`: `signer` is verified by public-key recovery (§4.6 item 3). Otherwise the chain id of the chain on which `signer` is a contract verified by ERC-1271 (§4.6 item 4) |
| `subject`, `object` | A `DesignRef` in which at least one hash is non-zero. Zero means "not given" |
| `source` | All three members zero (no source), or all non-zero. A non-zero source names a circuit whose design the signer says is the subject |
| `role` | One of `designer`, `co-designer`, `optimizer`, `reviewer`, `tester` (§4.5) |
| `displayName` | At most 64 bytes of UTF-8 in Unicode Normalization Form C, without control characters (U+0000–U+001F, U+007F–U+009F) and without any code point that has the property `Default_Ignorable_Code_Point` or `Bidi_Control` in Unicode 15.1.0 (the ranges are listed in Test Cases); empty for none |
| `noteURI`, `noteSha256` | `noteURI` is at most 512 bytes of printable ASCII (`0x20`–`0x7e`); `noteSha256` is the SHA-256 of the note's bytes. Both are empty and zero, or both are given |
| `license` | Empty, or an SPDX license expression or a URI, at most 256 bytes of printable ASCII |
| `relation` | One of `derivedFrom`, `supersedes`, `optimizes` (§4.5) |
| `reason` | Same character rules as `displayName`, at most 280 bytes; may be empty |
| `statement` | The non-zero statement id of the statement being revoked |
| `issuedAt` | Unix time in seconds, as declared by the signer |
| `nonce` | Any 32 bytes; it distinguishes otherwise identical statements |

The character rule of `displayName` and `reason` excludes, among others, ZERO WIDTH JOINER, the variation selectors and the tag characters, so emoji sequences built with them are rejected.

A `Lineage` whose `subject` and `object` share a non-zero `netlistHash`, or share a non-zero `structuralHash`, MUST be rejected.

If a `DesignRef` gives both hashes and the tool has the netlist file whose SHA-256 is its netlist hash, the structural hash MUST be that file's structural hash; otherwise the tool MUST reject the statement. When a tool reads a non-zero `source`, it MUST reject the Credit unless the subject applies to that circuit (§3.3).

#### 4.5 Meaning of roles and relations

A Credit says: the signer claims to have had `role` in creating or checking the design `subject`.

| Role | Claimed meaning |
|---|---|
| `designer` | Created the design |
| `co-designer` | Created the design together with others |
| `optimizer` | Produced the design by improving another design |
| `reviewer` | Examined the design without creating it |
| `tester` | Wrote or ran tests of the design |

A Lineage says: the signer claims that `subject` stands in `relation` to `object`.

| Relation | Claimed meaning |
|---|---|
| `derivedFrom` | `subject` was made starting from `object` |
| `supersedes` | `subject` replaces `object`, for example as a corrected version |
| `optimizes` | `subject` computes the same function as `object` at lower cost |

`displayName` is a name the signer gives itself. `noteURI` points to a design note whose bytes are fixed by `noteSha256`; a tool that fetches the note MUST check its SHA-256 and MUST NOT show a note that does not match. `license` is the licence under which the signer offers whatever rights it holds in the design and the note; it is not verified. `issuedAt` is not a fact.

#### 4.6 Verifying a statement

A tool verifies an envelope as follows:

1. Check §4.1–§4.4.
2. Compute the digest of §4.3.
3. If `signerChainId` is 0: the signature MUST be exactly 65 bytes `r ‖ s ‖ v` with `v` ∈ {0, 1, 27, 28}; `r` and `s` MUST be in [1, n − 1] and `s` MUST NOT exceed n/2, where n is the order of secp256k1; the address recovered from the digest and the signature MUST equal `signer`.
4. If `signerChainId` is not 0: the chain MUST be a chain of TAP-10 §2.1; for any other chain the statement is **unverified**. The **verification block** is the lower of the finality-tag block numbers reported by two nodes. The tool calls `isValidSignature(bytes32 digest, bytes signature)` (selector `0x1626ba7e`) on `signer` at the verification block on both nodes; the two answers MUST be identical, otherwise the statement is unverified. The statement is valid **at that block** if and only if the call returns a 32-byte value whose first four bytes are `0x1626ba7e`. The tool records the chain and the verification block. It MUST NOT fall back to public-key recovery. A tool MAY in addition call `isValidSignature` for an anchored statement (§5.2) at the block of its anchor on the same chain; that result says only that the contract accepted the signature at that block.

A statement that passes is **valid**; one that fails is **invalid**. A tool that cannot perform item 4 MUST treat the statement as **unverified** and MUST NOT display it as valid. Because the validity of a contract signature can change, a tool SHOULD re-verify such a statement when it displays it and MUST show its verification block.

**Holder-following signers.** For a contract signer, a tool MUST check with TAP-10 §4.3, on chain `signerChainId` at the verification block, whether `signer` is the TapeOut container of a circuit N. If it is, whoever holds N decides which signatures the container accepts, and the tool MUST label each of its statements "container of N; validity follows its holder" (or the same words in the tool's language) and SHOULD NOT rank its claims (§6.4).

#### 4.7 Revocation

A valid Revocation R **revokes** a statement S if and only if S is valid, R's `statement` equals S's statement id, S is not a Revocation, R and S have the same signer account (`signer` and `signerChainId`), and, when `signerChainId` is not 0, R and S are valid at the same verification block. A tool MUST judge a contract signer's statement and every Revocation it knows that names that statement at one verification block; while it cannot (for example because a Revocation is unverified or was verified at another block), it MUST NOT display S as active. Any other valid Revocation is void. A Revocation whose target the tool does not know is kept and applies when the target appears.

No statement restores a revoked statement; a signer that wants to restore a claim signs a new statement with a new `nonce`. For an externally owned signer a revocation is therefore permanent. For a contract signer, a revocation holds at every verification block at which the contract accepts R; at a block at which the contract accepts S but no longer accepts R (for example after the circuit holding a container changes hands), S is active again. A tool MUST NOT display a revoked statement as active; it MAY display it as revoked.

### 5. Carrying facts and statements

#### 5.1 Credit bundle and `tap.credits`

A **credit bundle** is a JSON object:

| Member | Required | Type | Content |
|---|---|---|---|
| `tapCreditBundle` | in a standalone file | number | `1`. Marks a standalone file as a credit bundle, as `tapManifest` and `tapEarliest` mark their objects. In `tap.credits` it MAY be present; if present it MUST be `1` |
| `v` | yes | number | `1` |
| `publications` | no | array | Publication facts (§3.1) |
| `earliest` | no | array | Earliest-occurrence statements (§3.4) |
| `statements` | no | array | Envelopes (§4.1) |
| `anchors` | no | array | Objects with `chainId` (number), `contract` (string), `txHash` (string) and `logIndex` (number), each naming a log that may be an anchor (§5.2) |

A credit bundle MAY be published as a standalone file, by any producer, for any circuit or design; a standalone file MUST contain `tapCreditBundle`, and a tool MUST NOT treat a standalone JSON file without it as a credit bundle. A TAP-721 token MAY carry a credit bundle as the member `credits` of its `tap` object (`TAP-draft-netlist-bound-nft` §7.1 lets other TAPs define further members of `tap`); `tap.credits` does not change the meaning of any other `tap` member. A producer that includes `tap.credits` MUST NOT fill metadata members that name an author or maker of the token (for example `created_by`, `artist`, `creator` or `author`) from publication facts, earliest-occurrence statements or claims.

Everything in a credit bundle is input to verification, not a result. A tool MUST verify each fact and statement it uses under §3 and §4 and MUST ignore members it does not know. A producer SHOULD include only facts and statements that verify, and MUST NOT include a statement it has altered.

#### 5.2 Anchors and a credit log pattern

An **anchor** of a statement S is a log, on a chain of TAP-10 §2.1, that has four topics, `topics[0]` = `0x46f7d925bbc35e7f8caf9e4c0b850b7405b337d421079c498a73570c2758dfcb` (`CreditPosted(address,bytes32,bytes32,bytes)`) and `topics[2]` equal to S's statement id, whose data ABI-decodes to one `bytes` value that is the UTF-8 serialisation of an envelope of S, where S is valid (§4.6). `topics[1]` and `topics[3]` have no meaning under this TAP and are not checked. An anchor establishes only that S existed no later than the timestamp of the log's block on that chain. A tool MUST read an anchor log under the rules of §3.2 steps 2 and 7 (receipt, block identity, finality-tag block) before it uses it.

*Credit log (informative).* The following events-only contract pattern produces anchors. This TAP does not require any contract to implement it, and no ERC-165 identifier is defined.

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapCreditLog {
    event CreditPosted(address indexed poster, bytes32 indexed digest, bytes32 indexed subjectKey, bytes statement);
    function postCredit(bytes32 digest, bytes32 subjectKey, bytes calldata statement) external;
}
```

A credit log in this pattern emits `CreditPosted(msg.sender, digest, subjectKey, statement)` with its arguments unchanged, stores and verifies nothing, takes no payment, never reverts, and has no owner and no upgrade path, so that it cannot censor or reinterpret statements. `subjectKey` is a discovery hint: the netlist hash of the statement's subject if it is non-zero, otherwise its structural hash; for a Revocation, the subject key of the statement it revokes. A tool can then find the anchored statements about a design with one `eth_getLogs` filter on `topics[3]`, and checks each log under the rules above.

### 6. Display rules

These rules apply to every tool that displays any fact, earliest-occurrence statement or claim of this TAP.

#### 6.1 Facts

1. A tool MUST display a publication fact as verified only after it passed §3.2, and MUST state the chain and block. A fact that is not verified MUST either not be displayed or be displayed as not verified. (Informative: "verified" here means a publication fact that passed §3.2; it is unrelated to `standing.verified` of `TAP-draft-pod-attributes`, which reports the mining contract's sampled check.)
2. A tool MUST describe the first publisher with words such as "first taped out by" or "first publisher", and MUST NOT use "designer", "author", "creator", "made by" or an equivalent for it.
3. A tool SHOULD indicate when the first publisher had contract code at the block read, because it may then be a relayer or a wallet contract.

#### 6.2 Claims

1. A tool MUST display every claim with: a label that identifies it as a claim; its role or relation; and its signer address, in full or one action away, together with `signerChainId` when it is not 0 and, for a container, the label of §4.6.
2. A tool MUST display `displayName` only next to the signer address and marked as self-declared, and MUST NOT display it in place of the address or with any mark of verification.
3. A tool MUST NOT display a claim in the style it uses for verified facts, MUST NOT use a claim to fill in or change a fact, and MUST NOT derive a fact from a claim.
4. A tool MUST state which kind of design a claim names: an exact file (`netlistHash`) or every file with a structure (`structuralHash`).
5. A tool MUST NOT attach names, handles or profiles from other sources to a signer as if the signer had signed them.

#### 6.3 Earliest-occurrence statements

A tool MUST display a standing earliest-occurrence statement as the earliest **known** occurrence, together with its scope and its `indexer` if present, and MUST NOT describe it as the original, the first ever, or the invention of the design. If the standing set has more than one member, the tool MUST display all of them as tied. Refuted and superseded statements follow §3.4.

#### 6.4 Several claims

1. A tool MUST display all active claims about a design that it shows any claim about, subject to §6.6, including claims that contradict each other. It MUST NOT select one claim as the designer of the design, and MUST show how many active claims each role has.
2. Active Credit claims about one design are grouped by role, in the order of §4.5. Within a role, anchored claims (§5.2) come first, earlier anchor timestamps first; claims whose signer is a TapeOut container (§4.6) come last and are not ranked. The order among the other, unanchored claims, and among container claims, is unspecified: a tool SHOULD NOT present it as precedence and MAY shuffle it on each view. The mark of §6.5, `issuedAt` and `displayName` MUST NOT affect the order.
3. For a `supersedes` claim, a tool SHOULD show whether the same signer account has an active Credit about `object`. For an `optimizes` claim, a tool MAY show facts it computed from the two netlist files (for example gate counts); "same function" remains a claim unless the tool checked it, and a tool that checked it MUST say how.

#### 6.5 Signed by the first publisher

A tool MAY mark a claim as "signed by the first publisher of N", where N is the on-chain name (or processor and circuit id) of a circuit, if and only if it displays a verified publication fact for N, the claim applies to N (§3.3), the claim's `signer` equals that fact's `publisher`, and either `signerChainId` is 0 or `signerChainId` equals the fact's `chainId` and `isValidSignature` on `signer` accepted the claim at the fact's `block` (called as in §4.6 item 4, at that block instead of the verification block). The mark MUST name N, MUST NOT be worded or styled as proof of authorship, and does not change the order of §6.4.

For a contract signer this needs the contract state at the publication block; a tool without archive access cannot evaluate it and then MUST NOT show the mark.

#### 6.6 Unwanted claims

A tool MAY collapse claims behind a count, for example claims that are neither anchored nor marked under §6.5. Collapsed claims MUST remain reachable. A tool MUST NOT collapse a claim because of its `displayName`, and MUST NOT collapse a claim marked under §6.5. A tool that hides claims by a local list MUST say that claims are hidden.

#### 6.7 Personal data

`displayName`, `noteURI` and the note may contain personal data that the signer chose to publish. A tool SHOULD stop displaying the display name and note of a revoked statement, and SHOULD remove them from caches it controls when a revocation becomes known.

## Rationale

**Facts and claims in separate layers.** The chain proves who received a mint, in which block; it cannot prove who had an idea. Every "designed by" line built from chain data alone silently turns the first into the second. Two layers with different labels, and a rule that nothing flows from claims into facts, make the distinction visible. A third class, the earliest-occurrence statement, is needed because "earliest" is a negative statement (no earlier occurrence exists): its occurrence can be checked, but its earliness can only be refuted.

**Identical netlists are not evidence of copying.** Small circuits have few good netlists, and textbook constructions such as the four-NAND XOR of the worked example are derived again and again. The worked example is therefore described in terms of identical netlists and equal hashes, and the TAP draws no conclusion from them about who designed what or who took a netlist from whom.

**The mint recipient as first publisher.** Three candidate addresses exist for a tape-out: the transaction sender, the mint recipient and the `msg.sender` of `tapeout`. TAP-02 §6, from the verified source of the BNB Smart Chain implementation, states that `tapeout(bytes,uint32,uint32)` mints to the caller, so the mint recipient is the caller. To check that no other entry point is offered, the runtime bytecode of the circuit implementations behind the circuit beacons was read at BNB Smart Chain block 128,542,889 (`0x8E1D125Def6d3826C278299273a0760D47626068`) and X Layer block 73,638,715 (`0x977f217887E085D298Cb3819cDAD5A0ee35F29B2`), the implementations TAP-10 lists. Each dispatches 26 selectors (every `PUSH4` compared with `EQ`), and all 26 were named by recomputing `keccak256` of candidate signatures, five of them found in public signature databases: the ERC-721 functions, the TAP-02 §6 functions other than `beat` (its selector `0x1fc0021d` is in neither dispatcher), `TAPEOUT_FEE()`, `TREASURY()`, `factory()`, `transistors()`, `transistorsContract()`, `sweepFees()` and `initialize(string,string,address,address)` (recorded in `assets/tap-draft-design-credits/chain-reads.json`). Among them only `tapeout` is a minting function by its name and by TAP-02 §6. Names are not behaviour: the enumeration rules out further entry points, not a mint inside a named function. The `Transfer` log is part of ERC-721, so it carries this meaning on any processor that follows TAP-02 and does not depend on the undocumented `TapedOut` event. The transaction sender is a weaker identifier: when a wallet contract, a relayer or a container tapes out, the sender is whoever paid gas.

**Why the `TapedOut` event is only corroboration.** Its signature `TapedOut(uint256,address,uint32,uint32)` was matched by its topic hash, but the source of the circuit implementation was not read for this draft. On mainnet its data words were (4, 0) for circuit 17851 and (10, 9) for circuit 17852, which matches (gate count, state count) and not (NAND, LATCH) count (1, 9) for 17852; the meaning is observed, not confirmed.

**Finality-tag blocks and two operators.** A publication fact orders occurrences, so a reorganised block could change which occurrence comes first. Requiring blocks at or below the chain's finality tag (TAP-10 §2.1) and identical reads from two operators follows TAP-10 §5 and the source check of TAP-721.

**Earliest occurrence as a refutable indexer statement.** A complete index of every circuit on every TapeOut chain is possible but large (1,341 processors on BNB Smart Chain alone at block 128,542,889), changes with every block, and cannot be checked by a wallet. A statement with an explicit scope can be produced by any indexer, and one verified counter-example refutes it. Comparing across chains by timestamp is coarse, and on chains with a single sequencer the sequencer sets timestamps; ties are therefore shown as ties rather than broken. A tied fact that has a known predecessor is not in the standing set, because that predecessor is then also tied with or earlier than the occurrence.

**Both hashes.** A netlist hash identifies a file; a structural hash identifies a design up to renumbering, input swaps, dead gates and duplicates. Credit can attach to either: a designer can claim the structure, while a statement about one encoding attaches to the file. A netlist taken from someone else and changed so that the structural hash changes (for example by a double negation) escapes both; that is a limit of `TAP-draft-netlist-structural-hash`, stated in Security Considerations.

**EIP-712 with a chain-agnostic domain.** Typed data is shown field by field by common wallets, unlike a raw hash, which TAP-10 §8.4 forbids shells to sign. Netlists and claims are chain-independent, so the domain has no chain id or verifying contract. Contract accounts, however, exist per chain, so `signerChainId` is part of the signed message: it names the chain whose code decides the signature's validity.

**`signer` inside the message.** Without it, a signature accepted by one ERC-1271 account could be presented for another account with the same owner. Two TapeOut containers whose circuits have one holder are such a pair. On X Layer, read at block 73,638,715 on two operators, the container of `1.2.282.tape` (found with the opener's `accountOf`) is an EIP-1167 clone of `0xAC4F791353eE9F06e2C50Ae4C34680D28Ea52a57`, the container implementation TAP-10 lists; that contract is a beacon proxy whose beacon `0x9b135f586f7850a3fa92210c298f732b20bc8f44` returned the implementation `0x6B6fDa1483367e939314070a4f233c1DFD35996B`. The container's `owner()` equalled the circuit's holder, and its `isValidSignature` returned zero for a signature by a public test key that does not hold the circuit (`assets/tap-draft-design-credits/chain-reads.json`). Binding the account into the digest prevents the replay.

**Contract signers at one block.** The answer of `isValidSignature` depends on the contract's state, which for a container changes when its circuit is sold. Judging a statement and the Revocations that name it at the same block keeps the two answers consistent: a claim cannot appear active because its revocation was checked under an earlier holder and the claim under a later one. Using the finality-tag block, with two operators agreeing, gives every tool the same answer for the same block. The mark of §6.5 is about who received the mint, so for a contract it asks the contract at the block of the mint.

**Low-s and the statement id.** The statement id is the digest, not the signature, so malleable signatures cannot create a second statement. The accepted `v` values and the range checks on `r` and `s` follow TAP-10 §14.2; low-s is required in addition, as Ethereum does for transactions, so that an externally owned account has one accepted encoding of each signature.

**Five roles and three relations, no free text.** Free-text roles invite "verified author" and similar labels. A closed list keeps displays comparable; a later version can add values.

**Display-name characters.** Default-ignorable and bidirectional-control characters render as nothing or reorder text, which makes two names that look the same compare different, or makes a name look like another. Citing the Unicode properties, at a fixed Unicode version, gives every implementation the same table.

**Anchors as an informative pattern.** Statements are self-verifying, so on-chain storage would add cost without adding truth. The only thing a chain can add is time: a log proves that bytes existed by a block. The TAP defines what makes a log an anchor and leaves the contract informative, so that no particular deployment is needed. An owner-less, non-upgradeable, non-verifying contract cannot censor or reinterpret statements, and tools ignore anything that does not verify. The `subjectKey` topic lets a tool find the anchors about a design without reading every log.

**Order without precedence.** Only anchors give claims an order that a signer cannot choose after the fact, and even that order can be raced (Security Considerations). Among unanchored claims any order would favour someone, for example the lowest statement id, which a signer can grind; leaving it unspecified and allowing shuffling keeps tools from implying precedence.

**Requires.** `TAP-draft-netlist-bound-nft` is required because the netlist file and netlist hash are defined there, and `TAP-draft-netlist-structural-hash` (which itself requires it) for the structural hash. `TAP-draft-pod-attributes` is only an informative reference: §3.5 names the `registrant` by its position in the `getMiner` tuple itself, and no requirement of this TAP depends on that draft. TAP-10 supplies chains, finality tags, processor numbers, names, factories, container resolution and read rules; TAP-02 supplies the processor interface, and ERC-721 the `Transfer` mint event that a publication fact rests on. EIP-712 defines the statement encoding and ERC-1271 contract signatures. `tap.credits` is optional: a tool that never displays TAP-721 tokens can implement this TAP from credit bundles alone.

**Application type.** The TAP is a convention for how applications label information; it changes no contract, file format or hash, and it adds a member to TAP-721 metadata without changing any existing one, so it does not weaken any Standards TAP (TAP-01 §3).

**Not in this TAP.** Identity verification, reputation scores, dispute resolution and payments all need trusted parties or economics this TAP does not want to define. Signed claims plus checkable facts are the part that needs no trust.

## Backwards Compatibility

This TAP adds a JSON member and new files; it changes nothing that exists. Tools and marketplaces that ignore `tap.credits` are unaffected. Existing circuits need no change: their publication facts can be read today.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

## Test Cases

`assets/tap-draft-design-credits/vectors.json` (format `tap-design-credits-vectors/1`) is generated by `assets/tap-draft-design-credits/make_vectors.py` and is reproducible byte for byte; its SHA-256 is `de1eda4fa7f1ca31449bb73af72a55e1f4416c00d20fd63512873858b11aae8c`. All private keys in it are derived as `keccak256("tap-design-credits test key <n>")`, are marked `testOnly`, and are public test keys, never to be used for anything else. Sections:

- `eip712`: the domain separator `0x609a43feee15b09b02f48f2488d2a7657b828fb16b36dee7b3526a2ff4029450`, and `encodeType` strings and type hashes: `DesignRef` `0xe0d77062a697623ec32ae3015da3f13817cf501f710e8d996629e77a6d550baf`, `Circuit` `0xd386bc95eeb878ae451ff972a49c90176c5ffbb790c94c9b2c539724163e02c0`, `Credit` `0xa3bd8c54c1373e9324d0fa362dc5f6a5d661d6de82130ec9307a8363c04f8cdf`, `Lineage` `0x83b976bf8511fef7567e8d66114d0a392d99e6acbaf0dfd878b4c40b9107f1ae`, `Revocation` `0xcca803a0f1cf651afe8aaa284da73db5bd30450c60f69823b9e19427c55a3370`; and `typedDataExample`, the payload of Appendix A with its digest and signature;
- `keys`: the test keys and their addresses;
- `unicode`: the Unicode version and the code point ranges excluded by §4.4;
- `valid`: envelopes that verify, with their statement ids and recovered signers (Credit with and without source, note and licence; Lineage of each relation; Revocation; `v` in both encodings);
- `invalid`: envelopes that each break one rule, with the expected error (including zero-width, soft-hyphen, ZWJ, variation-selector and tag characters);
- `erc1271`: contract-signer statements with recorded `isValidSignature` calls and verification blocks (synthetic), including the account-replay case of Rationale, a chain outside TAP-10 §2.1 and a container-labelled signer;
- `revocations`: scenarios with the resulting state of every statement, including a contract signer's revocation judged at the same block, at another block, and unverified;
- `publication`: the worked example below, with recorded reads, variants that fail each step of §3.2 (including a wrong finality tag, a chain outside TAP-10 and a state block before the mint), and a variant that differs only in fields §3.2 does not compare;
- `earliest`: earliest-occurrence statements judged standing, refuted, superseded, tied and invalid, each with the facts the tool knows, including unknown processor numbers and a fact without a header timestamp;
- `anchors`: logs that are and are not anchors;
- `display`: an ordering scenario (§6.4, §6.5) with the expected groups, marks (including contract signers accepted and rejected at the publication block) and container label; the order inside the unanchored and container groups is marked unspecified;
- `bundle`: a complete `tap.credits` member for the worked example, the same bundle as a standalone file with `tapCreditBundle`, and standalone files rejected for a missing or wrong `tapCreditBundle`.

**Worked example (BNB Smart Chain, read-only, 2026-10-19).** `assets/tap-draft-design-credits/fetch_reads.py` recorded the reads in `assets/tap-draft-design-credits/chain-reads.json`; no transaction was sent. Every contract-state read (`isCPU`, `cpuAt`, `circuitInfo`, `netlist`, `nextId`, `eth_getCode`) was made at one block, 128,542,889 (hash `0x7cc64dc1ec1e0e7eb8e20b104bb80a99c838a537b4776cd07d75b8171e5e6ecd`, 2026-10-19 11:03:12 UTC), the lower of the `finalized` blocks reported by `bsc-dataseed.bnbchain.org` and `bsc-dataseed1.defibit.io`, and returned identical values on those two nodes and on the archive node `tapeout.net/rpc`, three operators. Receipts and block headers were identical on `bsc-dataseed.bnbchain.org`, `bsc-dataseed1.defibit.io` and `bsc-dataseed1.ninicoin.io`; logs and the historical `nextId()` observations came from the archive node. Below, the first publishers are called accounts A, B, C and D. These labels belong to this example only and are unrelated to the test keys of `vectors.json`; the addresses are in `assets/tap-draft-design-credits/chain-reads.json`.

| | `17851.30.tape` | `3.635.tape` |
|---|---|---|
| Processor | `0xb1024b89886b9a34aa4ff5f31c411d708b20a14c` ("TapeOut", number 30) | `0xf4412c52ec3ddf7caf5f518b6662f77b02bde28e` ("RefBench", number 635) |
| Mint log | `Transfer(0 → account A, 17851)`, log index 604 | `Transfer(0 → account B, 3)`, log index 1166 |
| Block | 128,194,577, hash `0x2dadb1cb05354bc0759be63a7c2b354c8bd45ff7d2742c8532c62b06ac024867`, 2026-10-17 15:30:08 UTC | 117,235,964, hash `0xf222237677fab4031938cb50bd8242f20fdaadea629ae205b2fe8c48402023ef`, 2026-08-21 12:57:05 UTC |
| Transaction | `0x0d2638af463201264353140faa4b9740bfb92dae626ca1d4dedcf2b7010b3c18`, `tapeout` (`0x7bd3ac1d`), sender = publisher | `0xeeaba590bdd88a8da2ed6aa28dd2bf260f7f431479e69addd4ba6265c881a72c`, `tapeout`, sender = publisher |
| `TapedOut` log | `topics[1]` = 17851, `topics[2]` = publisher, data (4, 0) | `topics[1]` = 3, `topics[2]` = publisher, data (4, 0) |
| Netlist | `0x00000002000003000000020000040000000300000400000005000006`, `nIn` 2, `nOut` 1 | identical |
| Netlist hash | `0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e` | identical |
| Structural hash | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` | identical |

Both publication facts verify. For 17851 the first publisher, the transaction sender and the Proof-of-Design `registrant` of its miner record are the same account, A; under §3.5 none of this makes A the designer. `3.635.tape` is the reference circuit of the XOR task (`getTask(3)` names it), and its publication precedes 17851's. The two circuits have the same netlist hash, which says nothing about whether one was derived from the other.

`assets/tap-draft-design-credits/scan_occurrences.py` read every circuit of processors 30 and 635 at the same block 128,542,889, from the archive node alone (public nodes keep state for only about a hundred blocks, too short for a full scan); `assets/tap-draft-design-credits/fetch_reads.py` had checked on the two public nodes, at that block, the two reads that bound the scan. `nextId()` returned 17,975 for processor 30 and 267 for processor 635; at that block `circuitInfo(nextId())` succeeded and `circuitInfo(nextId() + 1)` reverted on all three operators, so ids 1 to `nextId()` are every circuit (Open questions). The scan computed the designs of the 4,248 circuits with `nIn` 2 and `nOut` 1 (a structural hash covers `nIn` and `nOut`, so no other circuit can match); the results are in `assets/tap-draft-design-credits/occurrences.json`. It found 132 circuits with this netlist hash (131 in processor 30, from #906 to #17975, and #3 in processor 635) and 134 with its structural hash; the two others, #1045 and #15368 of processor 30, are renumbered variants (in #1045 the two middle NAND records are swapped). Within one processor, ids are assigned in mint order, so #906 is processor 30's earliest; between processors the mint blocks decide, and #906's block precedes #3's. The scope's `toBlock` below is the scan block. The earliest is not the reference circuit:

| | `906.30.tape` | `1045.30.tape` |
|---|---|---|
| Mint log | `Transfer(0 → account C, 906)`, log index 569 | `Transfer(0 → account D, 1045)`, log index 72 |
| Block | 117,079,378, 2026-08-20 17:22:18 UTC | 117,249,114, 2026-08-21 14:35:46 UTC |
| Transaction | `0x7ac6baada39c8a5d45dc269c02b1c998a4c9098a880e38d9c56f8c99b35c0cef` | `0x7e1169b907a5137267ed03f438646b6f447b361d13aeaa8392616581be66c9d1` |
| Netlist hash | same as 17851 | `0x6b90490a18ea09ab2ad0d126773444705dd23c9a9b8d619e5f7d1571b1872ab4` |
| Structural hash | same as 17851 | same as 17851 |

For a tool that knows these four occurrences, the statement "earliest known occurrence of structural hash `0x74db…559b`: `906.30.tape`; scope chain 56, processors [30, 635], to block 128,542,889" is standing. The same statement naming 17851, `3.635.tape` or 1045 is refuted by `906.30.tape`; one naming `3.635.tape` with scope [635] is superseded by it; one naming 17851 with scope [635] is invalid, because its occurrence lies outside its scope; and one naming 1045 with key kind `"netlist"` and the netlist hash of 17851 is invalid. `906.30.tape` was taped out about 20 hours before the task's reference circuit, by account C: the earliest known occurrence need not be the reference design, and none of these facts identifies a designer.

## Reference Implementation

Under `assets/tap-draft-design-credits/` (MIT; Python 3.9+, standard library only):

- `credits.py`: keccak-256 and secp256k1 (RFC 6979 signing, recovery) in pure Python; EIP-712 encoding of the three statement types; envelope and field checks, including the Unicode 15.1.0 character table; statement verification with an injected ERC-1271 reader (verification block, or a given block) and an injected container resolver; revocations judged at one verification block; publication-fact verification from recorded reads, with the receipt normalisation of §3.2; designs of circuits and the `applies` relation; earliest-occurrence judging with standing sets; anchors; credit ordering, the §6.5 mark and informative display lines.
- `make_vectors.py` writes `vectors.json`; `test_credits.py` checks the vectors, checks that Appendix A of this text (and of its translation, when present) equals the vector, and cross-checks keccak-256 against pycryptodome, signatures against `eth_keys`, EIP-712 digests and the Appendix A signature against `eth_account`, and the Appendix A payload against Foundry `cast wallet sign --data`, each when installed.
- `fetch_reads.py` records the chain reads of the worked example and of the Rationale (selector enumeration, X Layer container); `scan_occurrences.py` is a minimal occurrence indexer for the earliest-occurrence example.
- `canon.py`, `tapnft.py` and `tap02_reference.py` are copied unchanged from the reference implementations of `TAP-draft-netlist-structural-hash` and `TAP-draft-netlist-bound-nft` (origin and SHA-256 in the folder's README), so that the folder runs on its own.

No credit log contract is provided; the pattern of §5.2 is informative. The reference implementation does not perform network reads in `credits.py` (§3.2 and §4.6 item 4 take recorded reads and injected readers), does not fetch anchor logs from a chain (§5.2), and leaves the subject and source checks of §4.4 to the caller (`applies`, `consistent_with_file`), because they need the netlist file.

## Deployments

This TAP depends on no deployed contract of its own, and no credit log is deployed. Publication facts are verified against the processor factories that TAP-10 lists under Deployments; on BNB Smart Chain that factory is an upgradeable proxy that is not sealed (TAP-02, Deployments), so a verifier records the state block it read.

## Security Considerations

- **Impersonation through display names.** Anyone can sign a Credit with any `displayName`, including a famous designer's name or handle. §6.2 keeps the name next to the signer address and marked as self-declared; the character rules of §4.4 remove control, default-ignorable and bidirectional-control characters, but not look-alike characters, so tools should not rely on the name to identify anyone.
- **False first-publisher reasoning.** The first publisher can be a copier, a relayer or a contract. §3.5 and §6.1 forbid presenting it as the designer, and §6.5 limits the mark to a statement about who signed.
- **Relayers and contract publishers.** A relayer or a contract that tapes out on behalf of users becomes the first publisher of every circuit it submits. A mark for such an address says nothing about the users behind it.
- **Copies and structural-hash evasion.** Copying a public netlist is free, and a copier can change the structural hash with function-preserving edits (`TAP-draft-netlist-structural-hash`, Security Considerations). An earliest-occurrence statement then treats the copy as a new design. Lineage claims and reviewers can point this out; this TAP cannot detect it. Conversely, an identical netlist is not evidence of copying.
- **Racing to tape out.** Anyone who sees a netlist before it is taped out (in a mempool, a shared file or a design note) can tape it out first and become the earliest known occurrence. Earliness is not origin (§3.5, §6.3).
- **Racing and squatting anchors.** Anchors order claims, and anyone can post. Someone who sees a design before its designer anchors a claim can sign a Credit of their own and anchor it first; someone who sees a pending `postCredit` can post the same statement earlier. An anchor's order is the order of posting, not of authorship, and tools display it as such.
- **Key compromise.** A stolen key can sign claims and revoke the owner's claims. Revocations by an externally owned account are permanent, and this TAP has no key rotation. Designers should sign with keys they keep for this purpose, or with a contract account whose owners can change; such an account's statements are valid only at blocks at which the account accepts them (§4.6).
- **Changing contract signatures.** An ERC-1271 account can accept a signature at one block and reject it later, or the reverse; a container follows its circuit's holder, so its claims change hands with the circuit. Tools show the verification block, re-verify, judge revocations at the same block (§4.7), and label containers (§4.6).
- **Spam claims.** Claims cost nothing to sign, and posting to a credit log costs only gas. §6.6 lets tools collapse unanchored, unmarked claims without hiding them, and §6.4 gives unanchored claims no precedence.
- **Reorganisations and lying nodes.** Publication facts and anchors are read on two operators and only at or below the finality-tag block (§3.2, §5.2); contract signatures are checked at the finality-tag block on two operators (§4.6).
- **Cross-chain ordering.** Timestamps on chains with a single sequencer are chosen by that sequencer; cross-chain ties are shown as ties (§3.4).
- **Upgradeable processors.** Processor contracts are beacon proxies behind an unsealed factory (TAP-02); an upgrade could add other minting paths. A publication fact records the block, and TAP-02 §7 item 3 asks verifiers to record the implementation at that block.
- **Note substitution.** A note is accepted only if its SHA-256 matches `noteSha256` (§4.5).
- **Personal data.** Display names, handles and notes are published by the signer, are public and cannot be erased from copies. Revocation stops compliant tools from displaying them (§6.7) but cannot remove them from archives or from a credit log.

### Open questions

1. Should circuits with REF records get a design (and therefore claims) once a flattening rule exists?
2. Should a credit log be deployed at one address on every TapeOut chain, and by whom?
3. Should earliest-occurrence statements be signed by their indexers (an EIP-712 type), so that tools can weigh indexers?
4. Should ERC-6492 signatures of contract accounts that are not yet deployed be accepted?
5. On the deployed processors `nextId()` returns the id of the latest circuit: 17851 at block 128,194,577, which minted 17851, and 17,975 for processor 30 at block 128,542,889, where `circuitInfo(17975)` succeeded and `circuitInfo(17976)` reverted on three operators. TAP-02 §6 describes it as the id the next circuit will get. Should TAP-02 be corrected?
6. Should a later version add roles (for example `compiler-author`) or a relation for pin-permuted variants?

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).

## Appendix A. `eth_signTypedData_v4` payload (informative)

The payload below is the Credit `credit_full` of `assets/tap-draft-design-credits/vectors.json` (section `valid`; also `eip712.typedDataExample`), as a wallet receives it through `eth_signTypedData_v4`. It uses the public test key 1 (address `0x541378bc90ff35563c25197869b436889f6caf4c`) and must not be used for anything real. Its digest is `0x453a0e24cda12aaf737632a3d3926de9d0cae46ca83c72ae8632b3a433165233` and its signature is `0xc07119a0cad762a825412457012608626f597908f513a80668858443711c892a2d5ac1d66827c1d598213784e0074b93fc5e2514d36fb17ba747ba431cb993101b`; `test_credits.py` checks both with `eth_account` and Foundry `cast wallet sign --data`. `circuitId` is a decimal string as in §4.1.

```json
{
  "types": {
    "EIP712Domain": [
      { "name": "name", "type": "string" },
      { "name": "version", "type": "string" }
    ],
    "Credit": [
      { "name": "signer", "type": "address" },
      { "name": "signerChainId", "type": "uint256" },
      { "name": "subject", "type": "DesignRef" },
      { "name": "source", "type": "Circuit" },
      { "name": "role", "type": "string" },
      { "name": "displayName", "type": "string" },
      { "name": "noteURI", "type": "string" },
      { "name": "noteSha256", "type": "bytes32" },
      { "name": "license", "type": "string" },
      { "name": "issuedAt", "type": "uint64" },
      { "name": "nonce", "type": "bytes32" }
    ],
    "Circuit": [
      { "name": "chainId", "type": "uint256" },
      { "name": "processor", "type": "address" },
      { "name": "circuitId", "type": "uint256" }
    ],
    "DesignRef": [
      { "name": "netlistHash", "type": "bytes32" },
      { "name": "structuralHash", "type": "bytes32" }
    ]
  },
  "primaryType": "Credit",
  "domain": {
    "name": "TAP Design Credits",
    "version": "1"
  },
  "message": {
    "signer": "0x541378bc90ff35563c25197869b436889f6caf4c",
    "signerChainId": 0,
    "subject": {
      "netlistHash": "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e",
      "structuralHash": "0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b"
    },
    "source": {
      "chainId": 56,
      "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c",
      "circuitId": "17851"
    },
    "role": "designer",
    "displayName": "Ada (test) — 测试",
    "noteURI": "ipfs://bafy-test-note",
    "noteSha256": "0x478290f500973e722f5bf60c0a8e0ae51b9774e7b1582c44bacaf2445250b731",
    "license": "CC0-1.0",
    "issuedAt": 1792000000,
    "nonce": "0xc9d4ad756c3d2ec3f4f350c4e8013414968064454ea7b9040b16e4c5cfe1d690"
  }
}
```
