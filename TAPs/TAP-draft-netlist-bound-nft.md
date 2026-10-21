---
tap: TBD
title: Netlist-Bound NFTs
description: An ERC-721 extension that binds each token to a verifiable, REF-free TapeOut netlist and an image, with one identifier, one file format and one reveal procedure on every TapeOut chain.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-02, TAP-10, ERC-165, ERC-173, ERC-721, ERC-4906, CAIP-19 (ChainAgnostic/CAIPs commit 1a897eede982d3d4eb68982f3798ebb0878c6ef5)
license: CC0-1.0
---

# TAP-TBD: Netlist-Bound NFTs

## Summary

This TAP lets an NFT carry, next to its picture, a real TapeOut circuit that anyone can download, check against the chain, simulate and tape out again on any TapeOut chain.

## Abstract

A netlist-bound NFT is an ERC-721 token whose metadata, and optionally whose contract, bind it to an image and to a netlist in the `tapnet/1` format defined here (a TAP-02 netlist without REF records, with its input and output counts). The TAP specifies that format and its hash, a hook through which other Standards TAPs define further netlist formats, how a netlist is traced back to the TapeOut circuit it was copied from, a global token identifier for the chains of TAP-10, a collection manifest that commits pools of images and netlists by Merkle roots before the reveal (over a token range or an explicit token set), a keyed permutation that assigns pool entries to tokens from one random seed, and the `tap` member of the token metadata. Like ERC-721, it has a mandatory core with two conformance levels, L0 (metadata only, reachable by an existing contract that can only change its base URI) and L1 (the on-chain interface `ITapNetlistNFT`, implemented by the collection or a companion contract), plus extensions: TokenSet (required of an L1 contract in set mode), Companion (required of every companion), the optional Eval extension that lets contracts run a token's netlist, and rules for hosting content in TapeOut containers. Bridging, Proof-of-Design attributes and a structural netlist hash are separate TAP-721 extension proposals.

## Motivation

TapeOut circuits are already ERC-721 tokens (TAP-10 §1): each processor contract stores netlists and mints one token per circuit. Those tokens are working tools — miners, components, CPUs — and are used as such. Communities have started to ask for a second kind of object: a collectible whose identity is a real circuit, which wallets, explorers and games on any TapeOut chain can read, check and use.

The motivating case is TapeCode-Test1, an existing 10,000-token ERC-721 collection on X Layer whose contract can only change its base URI. Its founders want every token to show an avatar and to carry the netlist of a Proof-of-Design miner, so that the collection becomes the base of circuit games on X Layer rather than a picture-only collection. Some of its tokens are held by an address that can never move them, so the tokens to be served are not one contiguous range. Two community write-ups ("TapeCode-Test1 NFT 图片及网表上传方案" and "NFT 头像图片与网表合并及跨链读取可行性方案", both October 2026; background only) proposed how to do this. They agree on the idea but not on field names, hash definitions, how a netlist is checked, or the reveal algorithm.

Without one text, a wallet, an explorer or a game cannot read two such collections the same way, and holders cannot check that a reveal was fair. Existing standards cover the pieces around the binding but not the binding itself: ERC-721 gives ownership and a metadata URI; ERC-4906 signals metadata changes; TAP-02 defines netlists and how they evaluate; TAP-10 defines chains, on-chain names and verified reads of files stored in TapeOut containers. This TAP reuses all four and adds only what is missing.

ERC-721 became the common base for NFTs because it is one short document that every wallet implements and that later ERCs extend. This TAP aims to play the same role for netlist-bound NFTs on TapeOut chains. The authors therefore request the number 721 (proposal name TAP-721, mirroring ERC-721); because TAP-01 §6.1 otherwise assigns the lowest free number above 10, this needs the editors' agreement. This text and its extension drafts say "TAP-721" for readability; if the editors assign another number, the drafts take that number.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

**Every L1 contract MUST implement the `ITapNetlistNFT` and ERC-165 interfaces** (and ERC-4906), subject to the rules of §8.2. An existing ERC-721 contract that cannot be changed reaches L1 through a companion contract (§8.3), or conforms at L0 (§8.1), the metadata-only conformance path for existing contracts: an L0 collection implements no TAP-721 interface and conforms by publishing token metadata that follows §7, with, when it reveals, a manifest and reveal that follow §5 and §6. At both levels, the token metadata of every TAP-721 token MUST follow §7.

The core (§1–§8.2) is followed by extensions in the same document:

- **TAP-721 Companion extension** (§8.3, `ITapCompanion`): every companion contract MUST implement it;
- **TAP-721 Eval extension** (§8.4, `ITapNetlistEval`): an L1 contract MAY implement it;
- **TAP-721 TokenSet extension** (§8.5, `ITapNetlistTokenSet`): an L1 contract whose manifest uses set mode (§5.4) MUST implement it, and one in range mode MAY;
- **TAP-721 container hosting and locking** (§8.6): SHOULD-level rules for collections that serve content from TapeOut containers.

### Conformance summary

This table is a guide to the sections below; where it and a section differ, the section prevails.

| Part | Status | Sections | Interface (ERC-165 id) |
|---|---|---|---|
| `tapnet/1` files, netlist hash, other formats | Core: every implementation and tool | §2 (other formats: §2.5) | — |
| Source circuits | Optional to declare; verification rules apply when declared | §3 | — |
| Token identifier, content locations | Core | §4 | — |
| Manifest, pools, Merkle tree | Core for a collection that reveals or implements L1 (except bridged copies and mint-bound contracts, §8.2) | §5.1–§5.3 | — |
| Token sets (set mode) | Conditional: a collection whose tokens are not one contiguous range | §5.4 | — |
| Reveal (master seed, pool seeds, permutation, editions) | Core for a collection with a manifest | §6 | — |
| Token metadata (`tap` member) | Core: L0 and L1 | §7 | — |
| L0 | Conformance level | §8.1 | — |
| L1 | Conformance level | §8.2 | `ITapNetlistNFT` (`0x282b67f6`), ERC-165 (`0x01ffc9a7`), ERC-4906 (`0x49064906`) |
| TAP-721 Companion extension | Conditional: L1 for an existing ERC-721 | §8.3 | `ITapCompanion` (`0x12b40a6c`) |
| TAP-721 Eval extension | Optional | §8.4 | `ITapNetlistEval` (`0xec7d7e20`) |
| TAP-721 TokenSet extension | Conditional: an L1 contract in set mode | §8.5 | `ITapNetlistTokenSet` (`0x3f7177c7`) |
| TAP-721 container hosting and locking | Recommended for content in TapeOut containers | §8.6, §7.5 | — |

### 1. Terms

| Term | Meaning |
|---|---|
| Collection | The ERC-721 contract whose tokens are bound |
| Netlist-bound NFT | A token of a collection that follows this TAP |
| Netlist file | A byte string in the `tapnet/1` format (§2), or in a format defined under §2.5 |
| Netlist hash | The identifier of a netlist file under its format: `SHA-256` of the file for `tapnet/1` (§2.3), or the hash a format defined under §2.5 specifies |
| Source circuit | A TapeOut circuit (chain, processor contract, circuit id) whose netlist a netlist file reproduces (§3) |
| Container | The TapeOut container of a circuit (TAP-10), whose site store can hold files |
| Manifest | The collection's JSON file listing every image and netlist the collection can assign (§5) |
| Pool | An ordered list in the manifest with one entry per covered token, holding image hashes, netlist hashes or both |
| Range mode, set mode | The two ways a manifest names the tokens it covers: a contiguous range of token ids, or an explicit token set (§5.4) |
| Index | The position of a covered token: its offset from the first token id in range mode, its rank in the token set in set mode |
| Master seed | The 32-byte random value that fixes the assignment of pool entries to tokens (§6) |
| Edition | The tokens that receive the same netlist hash (§6.4) |
| Companion | A separate contract that implements L1 for an existing ERC-721 contract (§8.3) |
| Chain table | TAP-10 §2.1. This TAP does not define chains of its own |

Byte strings are written in hexadecimal with a `0x` prefix. `‖` is concatenation. `u8(x)`, `u32be(x)` and `u64be(x)` are big-endian unsigned integers of 1, 4 and 8 bytes. `SHA-256` is FIPS 180-4. Hashes in JSON are `0x` followed by 64 lowercase hexadecimal digits, and addresses are `0x` followed by 40 lowercase hexadecimal digits.

### 2. Netlist files (`tapnet/1`)

#### 2.1 Layout

| Offset | Length | Content |
|---|---|---|
| 0 | 6 | ASCII `TAPNET` (`0x5441504e4554`) |
| 6 | 1 | Format version, `0x01` |
| 7 | 1 | Reserved, `0x00` |
| 8 | 4 | `nIn`, `u32be` |
| 12 | 4 | `nOut`, `u32be` |
| 16 | rest | TAP-02 records (TAP-02 §2) |

#### 2.2 Validity

A byte string is a valid `tapnet/1` file if and only if all of the following hold:

1. It is at least 16 bytes long, bytes 0–5 are `TAPNET`, byte 6 is `0x01` and byte 7 is `0x00`;
2. The records are not empty;
3. Every record is a NAND (`0x00`) or a LATCH (`0x01`) record. A REF record (`0x02`) makes the file invalid;
4. The records, with the `nIn` and `nOut` of the header, are a well-formed netlist under TAP-02 §3, including its bounds on `nIn` and `nOut`. (Condition 6 of TAP-02 §3 cannot arise without REF records.)

Tools MUST reject files that are not valid and MUST NOT produce them. Tools MUST check record lengths before reading and MUST bound the number of records before allocating memory for them (TAP-02 §7).

A valid file is exactly `16 + 7·nand + 4·latch` bytes long, where `nand` and `latch` are its numbers of NAND and LATCH records.

#### 2.3 Netlist hash

```
netlistHash = SHA-256(netlist file)
```

The netlist hash identifies a netlist file byte for byte. Two files that compute the same function but differ in any byte have different hashes. A structural identifier that ignores gate numbering is defined in `TAP-draft-netlist-structural-hash`.

#### 2.4 Metrics

The metrics of a valid file are `nIn`, `nOut`, `nand`, `latch` and `gates = nand + latch`. Because the file has no REF records, `latch` equals the circuit's state size `nState` and `gates` equals TAP-02's `gateCount`.

#### 2.5 Other netlist formats

A Standards TAP MAY define another netlist format. Such a format MUST be identified by bytes 0–5 `TAPNET` and a byte 6 that differs from `0x01` and from byte 6 of every format previously defined under this section, and by a `tap.netlist.format` string other than `"tapnet/1"` and other than that of every such format; it MUST define its validity, its metrics, its netlist hash rule and the members of `tap.netlist` that replace `sha256` and `bytes`. Its netlist hash rule MUST be such that, without a SHA-256 collision, no hash it produces equals `SHA-256(f)` for a valid `tapnet/1` file `f` or the netlist hash of a valid file in a format previously defined under this section (for example `TAP-draft-large-netlists` hashes a 41-byte preimage starting with `0x03`, while every `tapnet/1` file starts with `0x54`). Rationale lists the values already taken.

For a token whose netlist is in such a format: the netlist value in pool entries (§5.2), the value of `netlistHashOf` and the known netlist hashes (§8.2 item 4) are that format's netlist hash; and the requirements of §2.2, §2.4, §5.2, §7.1, §7.3 items 2 and 3, §7.4 and §7.5 item 2 that refer to `tapnet/1`, to `SHA-256(file)`, to `sha256` or to the `bytes` formula apply with that format's validity, metrics, hash and members in their place. A `tap.netlist.format` string that differs from `"tapnet/1"` only in letter case or whitespace is invalid.

A tool that does not support the format MUST still fetch the netlist file when it can, and MUST treat the token as invalid if bytes 0–5 of that file are not `TAPNET` or its byte 6 is `0x01`. Otherwise it MUST display the token's netlist as unverifiable, not as invalid, and MUST report the edition check (§6.4, §7.3 item 3) of such tokens as unverifiable. It MUST NOT display an unverifiable netlist as verified; because it cannot perform the checks of §7.4, it does not show such a token as a checked netlist-bound NFT.

`storeNetlist`, `netlistFile`, `netlistOf`, source verification (§3.2, and with it `tap.source`), the TAP-721 Eval extension (§8.4) and TAPs written for `tapnet/1` apply to `tapnet/1` files only, unless a TAP states otherwise.

### 3. Source circuits

#### 3.1 Declaring a source

A netlist MAY declare a source circuit: `(chainId, processor contract, circuit id)` on a chain of the chain table, together with the block number at which it was read. It SHOULD also give the circuit's on-chain name (TAP-10 §3.1): `<#ID>.<processor number>.tape` on BNB Smart Chain and `<#ID>.<area code>.<processor number>.tape` elsewhere.

#### 3.2 Verifying a source

A verifier MUST confirm a declared source as follows, reading the source chain under the rules of TAP-10 §5 (independent nodes, one pinned block). It reads at a block pinned under TAP-10 §5.3, or at the declared `block` if it has archive access, and reports which; because a stored netlist has no setter (TAP-02 §3), a confirmation at any block at or after the declared one confirms the source:

1. Confirm that the processor contract is registered with that chain's processor factory (`isCPU(address)`, selector `0x5f5a364f`), using only the factory addresses that TAP-10 lists under Deployments;
2. Read `circuitInfo(id)` and `netlist(id)` (TAP-02 §6);
3. Build `TAPNET ‖ 0x01 ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut) ‖ netlist(id)`;
4. The source is confirmed if and only if that file is valid (§2.2) and its SHA-256 equals the declared netlist hash;
5. If the metadata declares the source's `container`, it MUST equal the chain's container opener `accountOf(processor contract, circuit id)` (TAP-10 Appendix A); a tool MUST NOT accept a container address that is merely reported.

A circuit whose netlist contains a REF record cannot be a source under this version. (Every Proof-of-Design miner circuit qualifies, because the mining contract rejects circuits with REF records.)

The source chain does not have to be the collection's chain. Verifying a source is a read of the source chain; it does not need a bridge, and this TAP does not ask any contract to perform it.

A source is provenance only. A later transfer of the source circuit's token, or a change of its name or container, does not change the netlist bound to an NFT. Holding a netlist-bound NFT gives no right over the source circuit, its container or anything that circuit earns.

### 4. Identifiers and content locations

#### 4.1 Token identifier

The global identifier of a netlist-bound NFT is its CAIP-19 asset ID (CAIP-19, ChainAgnostic/CAIPs commit `1a897eede982d3d4eb68982f3798ebb0878c6ef5`):

```
eip155:<chainId>/erc721:<collection address>/<tokenId>
```

with the decimal chain id from the chain table, the collection address in lowercase hexadecimal and the decimal token id (no leading zeros). Tools that index, display or reference tokens of more than one chain MUST use this identifier and MUST NOT identify a token by its token id alone.

#### 4.2 Content locations

Images, netlist files, token-set files and manifests are located by URIs. A list of URIs for one piece of content SHOULD contain at least one `tape://` URL (TAP-10 §3.2), whose bytes TAP-10 clients verify against the chain, and at least one content-addressed URI (`ipfs://` or `ar://`). `https://` URIs MAY be listed, in particular so that marketplaces that do not resolve other schemes can show the image.

A tool MUST check the SHA-256 of any bytes it fetches against the hash given for that content and MUST treat any URI, gateway or server as untrusted.

Content served from a TapeOut container is also subject to the TAP-721 container hosting and locking rules (§8.6).

A container proves that a file with a given hash exists at a path; it does not prove which token receives that file. That binding is established by the metadata (L0) or by the on-chain interface (L1, §8).

Marketplaces usually fetch `tokenURI` and `image` from their servers, where a browser Service Worker gateway (TAP-10 §8.8) does not run. A collection that relies on such marketplaces needs an HTTPS URI that a server can fetch, and SHOULD list a content-addressed copy as well.

### 5. Manifests and pools

#### 5.1 Manifest file

A collection that assigns content to tokens through a reveal, or that implements L1 other than as a bridged copy or a mint-bound contract (§8.2), MUST publish a manifest: a UTF-8 JSON file. Its hash is

```
manifestHash = SHA-256(manifest file bytes, exactly as published)
```

No canonical JSON form is defined; the published bytes are what is hashed. The manifest has these members:

| Member | Type | Content |
|---|---|---|
| `tapManifest` | number | `1` |
| `collection` | object | `chainId` (number), `address` (string, lowercase), and either a token range — `firstTokenId` (number, at most 2^53 − 1 − `supply`) and `supply` (number) — or a token set — `tokenSet`: {`sha256`, `count` (number), `uris`} (§5.4) — but not both |
| `reveal` | object | `source` (string): `drand`, `vrf`, `blockhash` or `none`, and the parameters of §6.1 |
| `pools` | array | One or two pools (§5.2), in a fixed order |
| `freeze` | object, optional | For L0: how a tool checks that `tokenURI` can no longer change. `chainId`, `contract`, `call` (a function signature without arguments returning `bool`, for example `"uriFrozen()"`) and `expect` (`true`) |

In range mode the tokens covered are `firstTokenId … firstTokenId + supply − 1`; in set mode they are the ids of the token set (§5.4). `supply` (range mode) and `count` (set mode), written `n` below, MUST satisfy 1 ≤ `n` ≤ 2^32. Other TAPs MAY define further members of the manifest (for example `pod` in `TAP-draft-pod-attributes`); tools MUST ignore members they do not know.

A collection without a manifest that conforms at L0 MAY name the probe of `freeze` in the member `tap.freeze` of its token metadata (§7.1), with the same members. The member names a check, not a state: tools derive the frozen state from the chain (§7.2) and MUST NOT treat its presence as evidence of a freeze. `tap.freeze.chainId` and `tap.freeze.contract` MUST equal the chain id and collection address of `tap.id`. `tap.freeze` MUST either be present, with the same members, in the metadata of every token of the collection, or absent from all of them; tools MUST NOT report a freeze for a collection whose tokens name different probes.

An L0 collection SHOULD make the time of publication provable, by uploading the manifest to a TapeOut container or by committing its hash in a companion (§8.3). For a container upload, the publication block is the block of the earliest site-store event `FileSet(address indexed container, string path, uint32 size, bytes32 sha256Hash, string contentType)` (topic `0x13b9b0f05b22c496a9d9a29e7041c56c04670dc98ab327448870f18eb07b6773`, TAP-10 Appendix A) for that container and path whose `sha256Hash` equals the manifest hash; for a companion, it is the block of `ManifestCommitted`. A tool checks that this block precedes the moment the master seed became known; a tool that cannot find the block treats the publication time as unproven and says so.

#### 5.2 Pools

A pool is an object with:

| Member | Type | Content |
|---|---|---|
| `label` | string | 1–64 bytes of printable ASCII (`0x20`–`0x7e`), unique within the manifest. Used in §6.2 |
| `fields` | array | `["image"]`, `["netlist"]` or `["image", "netlist"]` |
| `root` | string | Merkle root of the pool (§5.3), `0x` + 64 lowercase hex digits |
| `entries` | array | Exactly `n` entries (`supply` or `count`) |

Each entry is an object with one member per field, named `image` or `netlist`, whose value is the SHA-256 of the image file or the netlist hash, as `0x` + 64 lowercase hex digits. An entry MAY carry `uris`: in a one-field pool, a non-empty array of URI strings for that field's content; in a two-field pool, an object with the members `image` and `netlist`, each a non-empty array of URI strings. An entry MAY also carry `attributes` (ERC-721 metadata attributes contributed by this entry), `source` (§3.1, for netlist fields) and other members; tools MUST ignore members they do not know.

Every pool entry MUST carry a non-zero value for each of its pool's fields, and every netlist hash in a netlist field MUST belong to a valid `tapnet/1` file. A collection that pairs each image with a fixed netlist uses one pool with both fields; a collection whose images and netlists are assigned independently uses two pools.

The field bit mask used on chain is `image = 1`, `netlist = 2`. Inside a leaf, values appear in the order image, then netlist. Each field appears in at most one pool, so a manifest has one pool or two. A collection MAY use a single pool with one field (an image-only or netlist-only reveal). A field that no pool carries is not assigned by the reveal: the collection fixes it in each token's metadata, §7.3 item 3 does not apply to it, and at L1 the matching getter (`imageHashOf` or `netlistHashOf`) returns zero for it permanently, except in a bridged copy or a mint-bound contract, which return the hashes recorded for the token (§8.2). Roots and entry values MUST NOT be zero; on chain, zero means "not bound".

#### 5.3 Merkle tree

For a pool with entries `0 … n−1`:

```
leaf(i)  = SHA-256(0x00 ‖ u32be(i) ‖ value_1 ‖ … ‖ value_k)     values in field order, 32 bytes each
node     = SHA-256(0x01 ‖ left ‖ right)
```

The tree is built level by level from the leaves: nodes `2j` and `2j+1` of a level are combined into node `j` of the next level; if a level has an odd number of nodes, its last node moves up to the next level unchanged. The root is the single node of the last level. A pool of one entry has `root = leaf(0)`.

A proof for entry `i` is the list of sibling nodes from the leaf level upwards, omitting the levels at which the node moved up unchanged. Verifying a proof requires the root, the pool size, the index, the leaf and the proof:

```
verify(root, size, index, leaf, proof):
    if index ≥ size: fail
    h = leaf ; i = index ; n = size ; k = 0
    while n > 1:
        if i is odd:          h = SHA-256(0x01 ‖ proof[k] ‖ h) ; k = k + 1
        else if i + 1 < n:    h = SHA-256(0x01 ‖ h ‖ proof[k]) ; k = k + 1
        i = i >> 1 ; n = (n + 1) >> 1
    succeed if and only if k = len(proof) and h = root
```

The index inside the leaf binds each value to its position, so a proof for one position cannot be used for another.

#### 5.4 Token sets

A collection whose covered tokens are not one contiguous range — for example because some tokens are held by an address that can never move them — uses set mode. The token set file is the concatenation of `u32be(tokenId)` for every covered token id in strictly ascending order (so every id MUST be below 2^32), and `tokenSet.sha256` is its SHA-256. The file MUST be published with the manifest, at the URIs in `tokenSet.uris`. The token set is an input to the assignment, so it MUST be fixed before the master seed can be known (§6.1, item 3). A tool MUST reject a token set file that is not strictly ascending, whose length is not `4 × count`, or whose SHA-256 differs.

The index of a covered token `t` is its rank in the token set: the number of covered ids smaller than `t`.

Tokens outside the token set receive no pool entry, now or later. Their metadata MUST NOT carry `tap.image` or `tap.netlist`. A collection SHOULD still serve a metadata file for each of them, so that marketplaces do not receive an error; such a file carries `tap.v`, `tap.id`, `tap.state` = `unrevealed` and `tap.manifest`; its ERC-721 `image` (required by §7.1) is a placeholder. A tool that has the token set MUST NOT display such a token as awaiting a reveal, and SHOULD display it as not covered by the manifest. At L1, `netlistHashOf` and `imageHashOf` return zero for such a token permanently, and `entryIndexOf` reverts (§8.2).

### 6. Reveal

#### 6.1 Master seed

The manifest's `reveal` object fixes, before the seed can be known, where the master seed will come from:

| `source` | Parameters | Master seed |
|---|---|---|
| `drand` | `chainHash` (64 lowercase hexadecimal digits without `0x`, as drand publishes it), `round` (number) | The 32-byte `randomness` of that round of that drand chain |
| `vrf` | — | Reserved. Version 1 does not define a VRF source; tools MUST reject a manifest that uses it |
| `blockhash` | `chainId` (number), `blockNumber` (number) | The hash of that block |
| `none` | — | No reveal: pool entry `x` goes to the token whose index is `x` (§6.3) |

Requirements:

1. The manifest hash MUST be published, and for L1 committed on chain (§8), before the master seed can be known: before the drand round is produced, or before the block is produced;
2. The master seed MUST be used exactly once. A collection MUST NOT request or choose a second seed, and MUST NOT commit a second manifest for the same tokens after the first manifest's seed is known;
3. Every input that affects how tokens are assigned or labelled — pool order, the token set, tiers and rarity rules, eligibility rules, and the snapshot blocks of attribute sources such as `TAP-draft-pod-attributes` — MUST be fixed by the manifest (in its bytes, or in a file whose SHA-256 the manifest contains) before the master seed can be known;
4. A collection whose `reveal.source` is not `none` SHOULD finish minting before the master seed can be known, because once it is known anyone can compute which unminted token id receives which entry;
5. A collection SHOULD publish the revealed metadata promptly after the seed becomes known, and SHOULD warn holders in advance that from that moment anyone can compute every token's assignment;
6. `blockhash` SHOULD NOT be used on a chain whose blocks are produced by a single sequencer, because that sequencer can choose among block contents; X Layer and Base are such chains (as of 2026-10-17 UTC). A block hash can be read on chain only during the 256 blocks after its block; a reveal not recorded in that window cannot happen under this manifest;
7. A tool that checks a `drand` seed MUST confirm that the `randomness` equals SHA-256 of the round's `signature`, MUST obtain the same signature from at least two independent drand relays whose chain information hashes to `chainHash`, and SHOULD verify the BLS signature against the chain's public key;
8. How the master seed is written on chain is implementation-defined; an L1 contract MUST set it to the value this section defines for the manifest's source, and its `Revealed(masterSeed)` event lets anyone compare.

#### 6.2 Pool seeds

```
poolSeed = SHA-256(masterSeed ‖ u64be(chainId) ‖ collection address (20 bytes) ‖ UTF-8(label))
```

`chainId` and the address are the manifest's `collection.chainId` and `collection.address`, wherever the permutation is computed (a companion, or a copy of the collection on another chain, uses the home values). Each pool has its own seed, so pools are assigned independently from one master seed. A collection that wants image and netlist rarities to be independent puts them in two pools.

#### 6.3 Keyed permutation

Token `t`, with index `x` — `t − firstTokenId` in range mode, its rank in the token set in set mode (§5.4) — receives entry `permute(poolSeed, n, x)` of each pool, where `n` is `supply` or `count`:

```
permute(seed, n, x):
    if n = 1: return 0
    b    = max(1, bitlength(n − 1))
    h    = ceil(b / 2)
    mask = 2^h − 1
    E(v):
        L = v >> h ; R = v & mask
        for r in 0, 1, 2, 3:
            (L, R) = (R, L xor F(r, R))
        return (L << h) | R
    F(r, R) = uint256(SHA-256(seed ‖ u8(r) ‖ u32be(R))) & mask
    y = E(x)
    while y ≥ n: y = E(y)
    return y
```

`E` is a four-round Feistel permutation of `[0, 4^h)`, and `4^h < 4n`, so cycle walking terminates and `permute(seed, n, ·)` is a permutation of `[0, n)`. Any party can compute the entry of any single token without computing the others, on chain or off chain.

#### 6.4 Editions

When the same netlist hash appears more than once in the netlist fields of a collection, the tokens that receive it form an edition. The edition of such a token is `(index, of)`, where `of` is the number of tokens that receive that netlist hash and `index` is the token's rank among them by ascending token id, starting at 1. Editions are determined by the reveal; a collection MUST NOT make one netlist appear as several by changing gate numbering or encoding (Security Considerations).

Collections without a manifest do not form editions, even when several of their tokens carry the same netlist hash, and their metadata MUST NOT contain `tap.edition`.

### 7. Token metadata

#### 7.1 The `tap` member

The JSON document returned by `tokenURI` MUST contain the ERC-721 metadata members `name` and `image`, and MUST contain a member `tap`:

| Member | Required | Type | Content |
|---|---|---|---|
| `v` | yes | number | `1` |
| `id` | yes | string | The token identifier of §4.1 |
| `state` | yes | string | `unrevealed` or `revealed` |
| `manifest` | when the collection has a manifest | object | `sha256` (manifest hash), `uris` |
| `image` | when `revealed` | object | `sha256`, `uris` |
| `netlist` | when `revealed` | object | `format` (`"tapnet/1"`), `sha256` (netlist hash), `bytes`, `nIn`, `nOut`, `nand`, `latch` (numbers), `uris`; optionally `structuralHash`: the structural hash of the file under `TAP-draft-netlist-structural-hash`, for formats and files for which that TAP defines one (`0x` + 64 lowercase hex digits) |
| `edition` | when `of > 1`; never without `manifest` (§6.4) | object | `index`, `of` (§6.4) |
| `source` | no | object | `chainId` (number), `processor` (lowercase address), `circuitId` (decimal string) and `block` (number), all required; `name` (on-chain name) and `container` (the source circuit's container address, lowercase) optional |
| `content` | no | object | Where the collection's files are stored in a TapeOut container (§7.5) |
| `license` | no | object | `image`, `netlist`: an SPDX identifier or a URI each |
| `companion` | when the collection names its companion through metadata (§8.3, way 1) | object | `chainId`, `address` (§8.3) |
| `freeze` | no; used only without `manifest` (§7.2) | object | The freeze probe of a collection without a manifest: `chainId`, `contract`, `call` and `expect`, as in the manifest's `freeze` (§5.1) |

In `manifest`, `image` and `netlist`, every listed member is required except `structuralHash`; `uris` is a non-empty array of URI strings. A collection that gives `structuralHash` for one netlist SHOULD give it for every netlist that has one. For a netlist in a format defined under §2.5, `format` is that format's identifier and the members that replace `sha256` and `bytes` are those the format defines. Numbers are JSON integers between 0 and 2^53 − 1. Members not listed here MAY appear; tools MUST ignore members they do not know. Other TAPs MAY define further members of `tap`.

Within one collection, `tap.manifest` MUST either be present, with the same `sha256`, in the metadata of every token (including tokens outside the token set, §5.4), or absent from the metadata of every token. At L1, when `manifestHash()` is non-zero, every token's `tap.manifest.sha256` MUST equal it. An indexer that finds tokens of one collection both with and without `tap.manifest`, or with different `tap.manifest.sha256`, MUST treat the collection as invalid.

Example (informative; the `tap` member of token 4 of the worked example in `vectors.json`, URIs shortened):

```json
{
  "v": 1,
  "id": "eip155:196/erc721:0x00000000000000000000000000000000000000aa/4",
  "state": "revealed",
  "manifest": {"sha256": "0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983", "uris": ["https://example.invalid/tap-example/manifest.json"]},
  "image": {"sha256": "0x2da1fc59339f21ea2cd41bffc0136e4a399f64ce690e0ca06e0bb90f6e589b9e", "uris": ["https://example.invalid/tap-example/images/0.png"]},
  "netlist": {"format": "tapnet/1", "sha256": "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e", "bytes": 44, "nIn": 2, "nOut": 1, "nand": 4, "latch": 0, "uris": ["https://example.invalid/tap-example/netlists/ecb6….tapnet"]},
  "edition": {"index": 1, "of": 3},
  "source": {"chainId": 56, "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", "circuitId": "17851", "block": 128200681, "name": "17851.30.tape"}
}
```

#### 7.2 States

- `unrevealed`: the token has no content yet, or it is outside the token set (§5.4). `netlist` MUST be absent and `manifest` MUST be present (a collection without a manifest assigns content at mint and never uses this state). A placeholder `tap.image` member MAY be present for a token awaiting a reveal and MUST be absent for a token outside the token set (§5.4); the ERC-721 `image` remains required (§7.1) and MAY be a placeholder; any other member that is present MUST still follow §7.1;
- `revealed`: the content is assigned.

Whether content can still change is not a metadata state: a file written before a freeze cannot truthfully announce it. Tools derive it from the chain (§8): `frozen()` at L1, or for L0 the probe the manifest names in `freeze` (§5.1) or, for a collection without a manifest, the probe named in `tap.freeze` (§7.1). Tools MUST NOT use `tap.freeze` for a token whose metadata carries `tap.manifest`, nor at L1, where they read `frozen()` and ignore `tap.freeze`.

#### 7.3 Consistency

1. `image` (the ERC-721 member) and every URI in `tap.image.uris` MUST serve the bytes whose SHA-256 is `tap.image.sha256`;
2. `tap.netlist.bytes` MUST equal `16 + 7·nand + 4·latch`;
3. Once revealed, `tap.image.sha256` and `tap.netlist.sha256` MUST equal the values of the pool entries the token receives under §6 for every field that a pool carries (§5.2), and `tap.edition` MUST follow §6.4 (absent or `1/1` for a netlist hash received by one token). Editions can only be checked across the whole collection; an indexer that has every token's metadata MUST check them;
4. `attributes` (the ERC-721 member) MAY repeat facts from `tap` for marketplaces; where they disagree, `tap` prevails.

#### 7.4 Checking a token

A tool that shows a token as netlist-bound MUST at least: parse the metadata and check the rules of §7.1–§7.3 that need no network access; fetch the netlist file from one of `tap.netlist.uris`; check that its SHA-256 equals `tap.netlist.sha256`, that it is valid (§2.2) and that its metrics equal the declared ones. It SHOULD fetch the manifest (and, in set mode, the token set file), check their hashes and recompute the token's assignment (§6), and SHOULD verify a declared source (§3.2). It MUST display the conformance level (§8) and MUST NOT display an L0 token as verified on chain.

#### 7.5 Content in a TapeOut container

A collection that stores its files in a TapeOut container MAY describe them in `tap.content`:

| Member | Required | Type | Content |
|---|---|---|---|
| `chainId` | yes | number | The chain of the container, from the chain table |
| `container` | yes | string | The container address, lowercase |
| `name` | yes | string | The on-chain name of the container's circuit (TAP-10 §3.1) |
| `paths` | yes | object | Paths inside the container's site (TAP-10 §7.2), each a string, each optional: `image`, `netlist`, `metadata` |
| `lock` | no | string | Address of the lock contract that holds the container's circuit (§8.6), lowercase |

A tool that uses `tap.content`:

1. MUST derive the container from `name` by TAP-10 §4.2 on the chain `chainId` and MUST NOT use `container` unless it equals the derived address;
2. MUST read files under TAP-10 §7.1 and MUST check the image and netlist files against `tap.image.sha256` and `tap.netlist.sha256`, not only against the hash the site store declares;
3. SHOULD show whether the container's circuit is held by `lock` (the processor contract's `ownerOf` for that circuit, read at the pinned block), and MUST NOT describe the files as locked on the strength of `lock` alone.

`tap.content` adds locations; it does not replace `uris`, and the hashes of §7.1 remain authoritative.

### 8. Conformance and extensions

§8.1 and §8.2 define the two conformance levels of the core. §8.3–§8.6 define the TAP-721 extensions; a contract reports through ERC-165 exactly the extension interfaces it implements.

#### 8.1 L0: metadata

A collection conforms at L0 if its token metadata follows §7 and, when it reveals, its manifest and reveal follow §5 and §6. L0 requires no contract change: a collection that can only set a base URI conforms by publishing the metadata files. At L0 the guarantee that content will not change rests on the collection giving up the power to change `tokenURI` (for example an irreversible `freezeBaseURI()`); tools MUST label such collections as "L0 (metadata only)"; for a collection without a manifest they MUST also show that no manifest commits its content (for example "L0 (metadata only), no manifest: content not committed").

#### 8.2 L1: on-chain interface

A contract conforms at L1 if it implements `ITapNetlistNFT` below, ERC-165 (reporting the interface identifiers of `ITapNetlistNFT` `0x282b67f6`, ERC-165 `0x01ffc9a7` and ERC-4906 `0x49064906`) and ERC-4906, and if:

1. `manifestHash()` and `masterSeed()` once non-zero, and `pools()` and `tokenRange()` once set (non-empty, `supply` ≥ 1), never change; `pools()[i]` equals the label, field mask and root of the manifest's `pools[i]`;
2. `entryIndexOf(t, p)` returns `permute(poolSeed_p, n, x)` with the index `x` of §6.3 once `masterSeed()` is non-zero, and reverts before, for a token that is not covered (outside the range, or outside the token set, §5.4), and for a pool index that does not exist. If the manifest's `reveal.source` is `none`, the contract sets `masterSeed()` to `0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff` when the manifest is committed, `entryIndexOf(t, p)` returns the index `x`, and the seed counts as set for item 5. For any other source the contract MUST NOT record zero or that value as the master seed;
3. `bind` records, for any caller, the entry a token receives, after verifying a Merkle proof (§5.3) against the pool root at index `entryIndexOf(t, p)`; it is idempotent. An implementation MAY also record every entry of a pool in one call or over several calls, after rebuilding the pool's root from the full list of values and checking it against the committed root; once the seed is set, `netlistHashOf` and `imageHashOf` then answer for every covered token without `bind`;
4. A netlist hash is known when `bind` has recorded it; when, after `masterSeed()` is set, a permissionless function has recorded it by deriving it from a pool recorded under item 3 for a token that receives it (in the reference implementation, `markKnown(uint256 tokenId)`); when it arrived with a token under a bridging TAP; or, in a mint-bound contract (below), when a token minted with it exists. `storeNetlist` accepts only `tapnet/1` files whose SHA-256 is a known netlist hash and whose length is at most 49,152 bytes, and makes them readable through `netlistFile` and `netlistOf`. It SHOULD check validity (§2.2) on chain, and MUST do so if the contract implements the TAP-721 Eval extension (§8.4). The layout behind `NetlistStored.pointer` is informative; clients read files through `netlistFile`. Revert data is not part of this interface;
5. `frozen()` returns true only when the manifest is committed, the seed is set and no account can change `tokenURI`, the manifest, the pools or the seed; once true it never returns false. A contract behind an upgradeable proxy is not frozen while its upgrade path exists;
6. It emits ERC-4906 `MetadataUpdate` or `BatchMetadataUpdate` whenever the metadata of a token may have changed (commit, reveal, bind, recording a pool or a token set, freeze), so that marketplaces refresh. In set mode a `BatchMetadataUpdate` over `0 … 2^256 − 1` satisfies this.

How the manifest is committed, the seed written, pools and token sets recorded and the contract frozen is implementation-defined; the events of `ITapNetlistNFT` let anyone check the result.

`tokenURI` of an L1 collection MUST still follow §7, and the values in its metadata MUST equal what the interface returns, except for a field that no pool carries (§5.2), for which the interface returns zero.

An L1 contract whose manifest uses set mode (§5.4) MUST also implement the TAP-721 TokenSet extension (§8.5).

**Bridged copies.** A copy of the collection on another chain, created by a bridging TAP that builds on this one, MAY implement `ITapNetlistNFT` without the manifest: there `entryIndexOf` and `bind` MAY revert with an error that the bridging TAP defines, and `netlistHashOf` and `imageHashOf` return the hashes that arrived with the token. In such a copy, `collection()` returns the copy itself, `tokenRange()` MAY return `supply` = 0 for an unbounded range, `frozen()` MAY stay false, and the metadata's `tap.id` is the identifier of the home token (§4.1). In every implementation `netlistHashOf` and `imageHashOf` return zero only while no hash is known for the token, or permanently for a field that no pool carries (§5.2).

**Mint-bound collections.** A contract that records the netlist hash of each token id at the token's mint, at most once over the contract's lifetime, MAY implement `ITapNetlistNFT` without a manifest. In such a contract: no function changes a recorded hash, and a token id that was burned MUST NOT be minted again with another netlist hash; `manifestHash()` and `masterSeed()` return zero and `pools()` is empty, permanently, so item 1 holds without a manifest; `entryIndexOf` and `bind` revert for every token, in place of items 2 and 3; `tokenRange()` MAY return `supply` = 0; `netlistHashOf` returns the hash recorded at mint; `imageHashOf` returns the image hash recorded at mint, or zero if the contract records none, and in the latter case the exception for a field that no pool carries (above) applies to the image; `storeNetlist` MAY, in addition to the files item 4 allows, accept any valid `tapnet/1` file of at most 49,152 bytes; and `frozen()` returns true only when no account can change `tokenURI` or a recorded hash, in place of the conditions of item 5 on the manifest and the seed, and once true never returns false. `frozen()` does not imply that minting has ended. A mint-bound contract reports `ITapNetlistNFT` only if it implements this profile in full. The metadata of its tokens has no `tap.manifest` and never uses the state `unrevealed` (§7.2).

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapNetlistNFT {
    struct Pool { string label; uint8 fields; bytes32 root; }

    function collection() external view returns (address);
    function tokenRange() external view returns (uint256 firstTokenId, uint256 supply);
    function manifestHash() external view returns (bytes32);
    function pools() external view returns (Pool[] memory);
    function masterSeed() external view returns (bytes32);
    function entryIndexOf(uint256 tokenId, uint256 poolIndex) external view returns (uint256);
    function bind(uint256 tokenId, uint256 poolIndex, bytes32[] calldata values, bytes32[] calldata proof) external;
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);
    function imageHashOf(uint256 tokenId) external view returns (bytes32);
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);
    function netlistOf(uint256 tokenId) external view returns (bytes memory);
    function frozen() external view returns (bool);

    event ManifestCommitted(bytes32 indexed manifestHash);
    event Revealed(bytes32 masterSeed);
    event Bound(uint256 indexed tokenId, uint256 indexed poolIndex, uint256 entryIndex);
    event NetlistStored(bytes32 indexed netlistHash, address pointer);
    event Frozen();
}
```

`values` in `bind` holds the entry's 32-byte field values in field order (image, then netlist). The function selectors, ERC-165 interface identifiers and event topics are listed in Test Cases.

#### 8.3 TAP-721 Companion extension

An existing ERC-721 contract that cannot be changed MAY reach L1 through a companion: a separate contract on the same chain that implements `ITapNetlistNFT` with `collection()` returning the existing contract. The binding is two-way:

1. The companion names the collection (`collection()`);
2. The collection side names the companion in one of two ways: its metadata carries `tap.companion`, or the collection's owner has endorsed the companion on chain. The second way works even after the collection's URI is frozen.

Every companion MUST implement `ITapCompanion` and report its ERC-165 identifier `0x12b40a6c`. `endorse()` reverts unless `msg.sender` equals the collection's `owner()` (ERC-173) at the time of the call; the first successful call records the caller permanently and emits `Endorsed(address by)`, and later calls have no effect. An implementation MAY refuse an endorsement before the manifest is committed. `endorsedBy()` returns the recorded address or zero. A later change of the collection's owner does not undo an endorsement.

```solidity
interface ITapCompanion {
    function endorse() external;
    function endorsedBy() external view returns (address);
    event Endorsed(address by);
}
```

A companion's `frozen()` returns true only when no account can change the companion's manifest, pools or seed, the companion is endorsed or named by the collection, and the existing contract can no longer change `tokenURI`. A companion MAY read the existing contract's freeze flag live, but MUST latch the first `true` it observes and SHOULD offer a permissionless function that latches it, so that `frozen()` never returns to false. ERC-4906 events of a companion come from the companion's address; marketplaces that watch only the collection may not see them.

#### 8.4 TAP-721 Eval extension (optional)

An L1 contract MAY also let any contract on its chain run a token's netlist. It then implements `ITapNetlistEval` and reports its ERC-165 identifier `0xec7d7e20`.

```solidity
interface ITapNetlistEval {
    function evalOf(uint256 tokenId, bytes calldata inputs) external view returns (bytes memory outputs);
    function stepOf(uint256 tokenId, bytes calldata state, bytes calldata inputs)
        external view returns (bytes memory newState, bytes memory outputs);
    function evalFile(bytes32 netlistHash, bytes calldata inputs) external view returns (bytes memory outputs);
    function stepFile(bytes32 netlistHash, bytes calldata state, bytes calldata inputs)
        external view returns (bytes memory newState, bytes memory outputs);
}
```

1. One call is one beat of TAP-02 §4 over the stored netlist file, with inputs, state and outputs packed as in TAP-02 §5 (inputs and state read leniently; outputs and new state exactly `ceil(n/8)` bytes with zero padding). The result MUST equal TAP-02's for every input and state;
2. `evalOf` and `evalFile` MUST revert when the netlist has a LATCH record, as TAP-02's `eval` does;
3. All four functions MUST revert when the netlist file is not stored on this chain, and `evalOf` and `stepOf` MUST revert when no netlist hash is known for the token.

Because files have no REF records, the cost of a beat is proportional to the file size, and a caller can read the metrics before calling.

#### 8.5 TAP-721 TokenSet extension

An L1 contract whose manifest uses set mode (§5.4) MUST also implement `ITapNetlistTokenSet` and report its ERC-165 identifier `0x3f7177c7`. In set mode `tokenRange()` returns `(0, count)`, `tokenSetHash()` returns `tokenSet.sha256`, and `entryIndexOf` reverts until the token set file has been recorded on chain and checked against `tokenSet.sha256`. Until then, `tokenAt` and `indexOf` MUST revert. An L1 contract in range mode MAY implement the interface; it then returns zero from `tokenSetHash()`, `firstTokenId + i` from `tokenAt(i)` and `t − firstTokenId` from `indexOf(t)`. Tools tell the modes apart by `tokenSetHash()` being non-zero, not by `tokenRange()`.

How the token set is recorded is implementation-defined. The reference implementation loads the packed token set file bytes themselves (`loadTokenSet(bytes)`, or `loadTokenSetChunk(uint256,bytes)` over several transactions), checks them against `tokenSet.sha256`, and keeps one transaction at or below 128 KiB of calldata, about 32,000 ids.

```solidity
interface ITapNetlistTokenSet {
    function tokenSetHash() external view returns (bytes32);            // tokenSet.sha256; zero in range mode
    function tokenCount() external view returns (uint256);              // n (count or supply)
    function tokenAt(uint256 index) external view returns (uint256);    // token id of that index
    function indexOf(uint256 tokenId) external view returns (uint256);  // index; reverts if not covered or not recorded
}
```

#### 8.6 TAP-721 container hosting and locking

This section applies to collections that serve content (§4.2) or metadata from a TapeOut container, and to the tools that display them; `tap.content` (§7.5) describes such content in the metadata. It defines no interface.

Files in a TapeOut container can be replaced or removed by the holder of the container's circuit, or by a site operator the holder set. A collection that serves its content from a container SHOULD, once the content is uploaded and checked, clear any operator and move that circuit to a contract that can never write to the site store (a lock contract). Moving the circuit into its own container also stops all writes, but then nobody can renew the container's activation (TAP-10 §6.3), so compliant shells stop displaying it when the paid period ends; a lock contract that can only renew avoids this.

A lock removes the holder's power to change files; it does not remove the power of whoever can upgrade the site store. The hashes of §5 and §7, not the lock, are what make a substitution detectable.

Tools SHOULD show whether the container that serves a collection's content is locked. A container serving token metadata SHOULD NOT set a fallback path (TAP-10 §7.2), so that a missing file is reported as missing rather than answered with another page.

## Rationale

**Netlist bytes, not a pointer to a circuit.** Binding an NFT to "circuit N of processor P" would make the NFT depend on another token that can be transferred, and on a chain the NFT may not live on. A self-contained file whose hash is bound makes the netlist travel with the NFT, verifiable and re-taped on any chain; the source stays as provenance (§3).

**No REF in version 1.** A REF record names a processor contract address and circuit id on one chain, so a netlist with REF records is neither chain-independent nor self-contained. Flattening REF records into gates is possible but needs a precise renumbering rule that the first use does not need: Proof-of-Design miners already forbid REF. A later version can add flattening without changing `tapnet/1`.

**Byte hash plus a separate structural hash.** The netlist hash must be cheap and unambiguous for contracts and wallets; SHA-256 of the file is both. Recognising that two netlists are the same design despite renumbered gates is a different problem with known limits; it is specified in its own TAP so that its algorithm can evolve without touching this one.

**SHA-256.** TAP-10 verifies container files with SHA-256, and drand, IPFS and most tooling use it, so one hash serves files, manifests, token sets, Merkle trees and the permutation. It is available on all three chains as the precompile at address `0x02` (checked on 2026-10-17 UTC by `eth_call` with input `abc` on BNB Smart Chain, Base and X Layer, each returning `0xba7816bf…f20015ad`).

**A keyed permutation instead of a shuffle.** A Fisher–Yates shuffle of 10,000 entries cannot be run in one transaction and must be computed off chain in full before anyone can check one token. The Feistel permutation with cycle walking gives every token its entry independently in a few hashes, on chain or off chain, and is a bijection by construction.

**Merkle roots instead of storing every entry.** Storing 10,000 pairs of hashes in contract storage costs hundreds of millions of gas; a root costs one slot. `bind` lets anyone, typically the holder or an indexer, record a token's entry when it is needed. Recording a whole pool at once (§8.2, item 3) is allowed as a cheaper path for collections that want every token readable on chain from the reveal on; it is checked against the same root, so it adds no trust.

**One master seed, several pools.** Image rarity and netlist rarity often need to be independent. Domain-separated pool seeds give that from one randomness request, and also allow collections that pair images and netlists in a single pool.

**No domain tag in pool seeds and the round function.** The Merkle tree prefixes leaves and nodes with `0x00` and `0x01` (§5.3) because both are compared with a committed root, and §2.5 keeps other formats' netlist hashes apart from each other and from `SHA-256` of `tapnet/1` files because both land in the same places: pool entries, `netlistHashOf` and the known netlist hashes. The outputs of `poolSeed` (§6.2) and `F` (§6.3) land in none of those places: they are used only as a permutation key and as round values masked to at most 16 bits, and are never stored, committed or compared with another hash. A collision between them and a hash of another kind would therefore let nobody substitute one value for another, so they carry no domain tag; their inputs are also fixed by the manifest and a public seed, and `F` has a fixed 37-byte input.

**A hook for other formats.** `tapnet/1` is kept small so that contracts can check and evaluate it; netlists with memories or of many megabytes need other encodings and other hashes. §2.5 lets a Standards TAP add such a format without changing `tapnet/1` or its hash. Requiring a version byte and a hash space that differ from those of `tapnet/1` and of every format defined before means that, without a SHA-256 collision, a value in a pool entry or in `netlistHashOf` names one file in one format. Requiring tools to show an unsupported format as unverifiable, while still rejecting a fetched file that is not a `TAPNET` file of another version, keeps a valid token from being reported as broken by an older tool without letting an invalid one pass as unverifiable. A format string that differs from `tapnet/1` only in case or whitespace is invalid, so that it cannot turn a broken `tapnet/1` token into an unverifiable one.

**Mint-bound collections and the freeze probe.** Collections that bind a netlist at mint have no reveal to commit to. The mint-bound profile (§8.2) lets them offer the same reads as other L1 contracts without a manifest. They form no editions (§6.4): with no manifest, the number of tokens that share a netlist hash is not fixed in advance and can change with every mint, so an edition count would be misleading until minting ends. `tap.freeze` (§7.1) gives an L0 collection without a manifest the same way to point tools at its freeze check as a manifest gives, while the frozen state itself is still read from the chain.

**Token sets by rank.** A collection whose usable tokens have gaps would otherwise either assign content to tokens nobody can use, which wastes scarce netlists and misstates scarcity, or redeploy. Set mode keeps the permutation unchanged and only changes the index: the rank of a token in an ascending list. A packed `u32be` list is trivial to hash on chain and off chain, and a rank needs no extra data beyond the list. A bounding range with holes was rejected because the pool size would no longer equal the number of tokens served. Fixing the set before the seed (§6.1, item 3) prevents the producer from including or excluding tokens after seeing the assignment. Separate files for excluded tokens (§5.4) keep marketplaces working without implying that content will come.

**Containers, names and locks.** Community shorthand for the three TapeOut primitives is C/N/L: container (电容), NAND and LATCH. This TAP uses the last two in `tapnet/1` and the first for storage. A container is an attractive home for content because TAP-10 clients verify its files against the chain, but its holder can change files, and its site store is upgradeable. The design therefore relies on hashes for integrity and on a lock contract only to stop casual changes; `tap.content` names the container by its on-chain name, from which a tool derives the address, so a wrong or malicious address in metadata cannot redirect a tool.

**Two levels.** Without L0, a collection whose contract cannot be changed and can only set its base URI — the motivating case — could not conform. With only L0, other contracts on chain could not read netlists, which circuit games need. L1 through a companion closes that gap without replacing the collection.

**A core and extensions in one document.** As in ERC-721, the core interface is mandatory and the extensions are optional or conditional parts of the same document. The TokenSet, Companion and Eval extensions have interfaces separate from `ITapNetlistNFT`, so that its ERC-165 identifier `0x282b67f6` stays the same for every L1 contract and a contract reports exactly the parts it implements.

**A reserved seed for collections without a reveal.** With `reveal.source` `none` there is no random value, but L1 needs a non-zero `masterSeed()` to signal that assignments are final. The all-ones value cannot be confused with "not revealed" (zero), and a random source producing it is negligible; contracts refuse it as a random seed.

**A size limit for stored netlists.** 49,152 bytes is the largest file that the reference implementation stores and checks for validity within a 16,777,216-gas transaction, the cap of BNB Smart Chain. Larger netlists are the subject of `TAP-draft-large-netlists`, which defines the `tapnet/2` format under §2.5 and its chunk-by-chunk on-chain storage (its §3).

**Manifest bytes are hashed as published.** A canonical JSON form would add a dependency for no gain: the manifest is published once and never re-serialised.

**The Eval extension.** Proof-of-Design mining runs on BNB Smart Chain only. On the other chains, the point of carrying a real netlist is that contracts can use it: games, puzzles and competitions that call the circuit of a token. The extension makes the netlist a callable function on the collection's own chain, with the same semantics as a TapeOut processor, without taping it out again.

**One topic.** The file format, source check, identifier, manifest, reveal and metadata are what a wallet needs to check one token end to end; L1 adds on-chain reads of the same values and nothing else. If editors prefer a narrower text, the TAP-721 Eval extension (§8.4) is the first part that can stand alone, and `tapnet/1` (§2) could become its own format TAP; `TAP-draft-netlist-structural-hash` already depends only on it.

**Existing specifications.** The token identifier is CAIP-19, because wallets and indexers already parse it. The hashes are served by dedicated functions rather than ERC-7496 traits because they are fixed by the manifest and proven by Merkle proofs, while ERC-7496 traits are values an owner may set; `TAP-draft-pod-attributes` uses ERC-7496 for facts that are snapshots of another contract. No existing ERC defines a committed, publicly recomputable reveal, so §5–§6 define one with the smallest primitives available on all chains.

**Relationship to other TAPs.** Three proposals extend TAP-721 and require it, as ERC-4906 and ERC-7496 extend ERC-721: `TAP-draft-netlist-nft-bridging` (moving TAP-721 tokens between chains), `TAP-draft-pod-attributes` (Proof-of-Design attributes for TAP-721 tokens) and `TAP-draft-netlist-structural-hash` (a structural hash of `tapnet/1` files). They are separate TAPs for four reasons. One topic per TAP: each can be reviewed, accepted or rejected without reopening this one. Upgradeable dependencies: bridging depends on a message layer and its own security analysis, and the PoD attributes read contracts that can be upgraded; neither should hold this core back or tie it to their changes. Application type: PoD facts (task, burns, cost, optimal-first status) change over time and belong to one application, so they are an Application TAP, while this one is a Standards TAP. Algorithm evolution: recognising one design under renumbered gates has known limits, and its algorithm can change without changing the netlist hash of §2.3.

**Names used by other drafts (informative).** §7.1 lets other TAPs define further members of `tap`, and §5.1 further members of the manifest. The following names are used by drafts that build on this one (some not yet submitted); a new member should not reuse them.

| Name | Where | Draft | Content |
|---|---|---|---|
| `tap.bridge` | token metadata | `TAP-draft-netlist-nft-bridging` | The home collection's bridge gateway: `chainId`, `gateway` |
| `tap.pod` | token metadata | `TAP-draft-pod-attributes` | A snapshot of the source circuit's Proof-of-Design facts at one block |
| `tap.rig` | token metadata | `TAP-draft-pod-attributes` | An unverified reference to a rig voucher on X Layer |
| `pod` | manifest | `TAP-draft-pod-attributes` | Snapshot parameters fixed before the seed |
| `tap.credits` | token metadata | `TAP-draft-design-credits` | A credit bundle: publication facts and signed credit, lineage and revocation statements |
| `tap.credential` | token metadata | `TAP-draft-soulbound-credentials` | The credential record of a soulbound credential, in a collection without a manifest, at L0 (§6.4, §8.1) |

**Netlist formats defined under §2.5 (informative).** Each new format takes a byte 6 and a netlist hash space that no earlier format uses. The values taken so far:

| `tap.netlist.format` | Byte 6 | Netlist hash | First byte of the hashed preimage | Defined in |
|---|---|---|---|---|
| `tapnet/1` | `0x01` | `SHA-256(file)` | `0x54` (`T` of `TAPNET`) | this TAP, §2 |
| `tapnet/2` | `0x02` | `netlistHash2 = SHA-256(0x03 ‖ u64be(len) ‖ chunkRoot)`, a 41-byte preimage | `0x03` | `TAP-draft-large-netlists` §1, §2.1 |

**What is left out.** PNG files that embed a netlist are allowed as additional content but are not a source of truth, because marketplaces and messengers re-encode images and drop ancillary chunks.

## Backwards Compatibility

Netlist-bound NFTs are ERC-721 tokens; wallets and marketplaces that ignore `tap` show the name, image and attributes as before. TapeOut circuit tokens are unaffected; they can be sources (§3). Existing collections reach L0 by changing their metadata and L1 through a companion, without redeployment.

An existing collection without a manifest cannot reach L1 through a companion, because a companion implements `ITapNetlistNFT` with a manifest (§5.1, §8.3), and the mint-bound profile (§8.2) is open only to the contract that mints the tokens; such a collection stays at L0 unless it publishes a manifest for its tokens while it can still change their metadata.

## Test Cases

`assets/tap-draft-netlist-bound-nft/vectors.json` is generated by `assets/tap-draft-netlist-bound-nft/make_vectors.py`, reproducible byte for byte, with SHA-256 `9808f32ae21d911e377de09aa9f5df862715e9d1286041033f225a54c70031e8`. Its members `format` and `generator` identify the file; its sections are:

- `chain`: the chain id and pinned block of the on-chain input (BNB Smart Chain block 128,200,681, `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`);
- `tapnet`: netlist files built from four BNB Smart Chain mainnet circuits read at that block, with netlist hashes, metrics, on-chain names and validity (one circuit contains REF records and is listed as rejected);
- `invalidFiles`: one rejected file per rule of §2.2, with the expected error;
- `merkle`: pools of 1, 2, 3, 5 and 8 entries with one and two fields, roots, every proof, failing proofs and error cases;
- `permutation`: pool seeds and `permute` outputs for pool sizes 1, 2, 3, 7, 10, 255, 256, 257 and 1,000 in full, and for 10,000 the first 64 outputs and a hash of the whole permutation, with error cases and intermediate values for debugging ports;
- `metadata`: valid and invalid `tap` members, each invalid one breaking one rule of §7 (a `tap.netlist.format` other than `tapnet/1` is not one of them, §2.5);
- `manifests`: valid manifests (range mode and set mode, one and two pools, object-form `uris`) and invalid manifests, each breaking one rule of §5.1, §5.2, §5.4 or §6.1;
- `tokenSets`: set mode (§5.4): a 10-of-20 set with its file, hash, manifest and the assignment of every token (none for tokens outside the set); a 7,000-of-10,000 set with its hash, the first 32 assignments and a hash of all of them; token set file and hash errors;
- `content`: valid and invalid `tap.content` members (§7.5);
- `placeholders`: metadata of tokens outside the token set and awaiting reveal (§5.4, §7.2);
- `editions`: the collection-level edition check (§6.4, §7.3 item 3) over the example, three failures, and three collections that drop `tap.manifest` from some or all tokens or carry two manifest hashes (§7.1);
- `netlistChecks`: a fetched file checked against metadata (§7.4), one match and two rejects;
- `noManifest`: metadata of collections without a manifest, such as a mint-bound token (§8.2), with and without `tap.freeze` (§5.1, §7.1), a `tap.freeze` ignored next to a manifest (§7.2), invalid `tap.freeze` members, including a probe of another chain or contract (§5.1), a `tap.edition` without a manifest (§6.4), two tokens with the same netlist hash and no edition, which pass the edition check, and two collections whose tokens name different probes or where only some tokens name one (§5.1);
- `otherFormats`: a token whose netlist is a `tapnet/2` file (`TAP-draft-large-netlists`), which the reference implementation, supporting `tapnet/1` only, accepts and reports as unverifiable, not invalid (§2.5); five fetched files for that token, two unverifiable (another version's header, no file) and three invalid (a `tapnet/1` file, a file without `TAPNET`, a truncated header); two such tokens under one manifest with the same netlist hash and no edition, whose edition check is reported as unverifiable, since a tool that supports `tapnet/2` would require editions (§2.5, §6.4); and five documents that break the members every format keeps or write `tapnet/1` with other case or whitespace (§2.5);
- `example`: a complete eight-token collection with two pools, its manifest file and hash, a fixed master seed, the assignment and the metadata of every token (also under `example/`).

The Solidity reference implementation's tests reproduce these values from a fixture generated from `vectors.json`, including evaluation (§8.4) of the mainnet circuits #17851 (XOR, all 4 inputs), #3151 (popcount8, all 256 inputs) and #17852 (Johnson counter, 20 beats from the zero state) against the TAP-02 reference implementation.

Interfaces (each ERC-165 identifier is the XOR of its selectors; recomputed with `cast sig`):

| Interface | Status | ERC-165 id | Functions (selector) |
|---|---|---|---|
| `ITapNetlistNFT` | TAP-721 core (L1) | `0x282b67f6` | `bind(uint256,uint256,bytes32[],bytes32[])` `0x25944f76`, `collection()` `0x7de1e536`, `entryIndexOf(uint256,uint256)` `0x6b3b2d25`, `frozen()` `0x054f7d9c`, `imageHashOf(uint256)` `0xa7257a04`, `manifestHash()` `0x337f3f32`, `masterSeed()` `0x3982d13f`, `netlistFile(bytes32)` `0x5267c429`, `netlistHashOf(uint256)` `0x32d9b670`, `netlistOf(uint256)` `0xae502e0b`, `pools()` `0xc5c51dca`, `storeNetlist(bytes)` `0xf8b0cc86`, `tokenRange()` `0x40698418` |
| `ITapNetlistTokenSet` | TAP-721 TokenSet extension (set mode) | `0x3f7177c7` | `tokenSetHash()` `0xa36c08c6`, `tokenCount()` `0x9f181b5e`, `tokenAt(uint256)` `0x92a91a3a`, `indexOf(uint256)` `0x91ac7e65` |
| `ITapCompanion` | TAP-721 Companion extension | `0x12b40a6c` | `endorse()` `0xf4fbaf58`, `endorsedBy()` `0xe64fa534` |
| `ITapNetlistEval` | TAP-721 Eval extension (optional) | `0xec7d7e20` | `evalOf(uint256,bytes)` `0x3097c028`, `stepOf(uint256,bytes,bytes)` `0x6ff2b6b8`, `evalFile(bytes32,bytes)` `0xf822bb64`, `stepFile(bytes32,bytes,bytes)` `0x4b3ab3d4` |

Other identifiers used in this TAP: ERC-165 `0x01ffc9a7`, ERC-4906 `0x49064906`, `isCPU(address)` `0x5f5a364f`, ERC-173 `owner()` `0x8da5cb5b`.

Event topics (`cast keccak` of the signature): `ManifestCommitted(bytes32)` `0x283da7c24290f991388adb4188dab383e865d9edad5d228e8b95805b85bba620`, `Revealed(bytes32)` `0xd5e62fe0c4e6bd40a7736fb2ab572a9a0f5e742f27741505011b9bc89c7ead19`, `Bound(uint256,uint256,uint256)` `0x2893e106f460291bc3157184f05db4c33b0b5f3f34eccce325296bfaaa71436a`, `NetlistStored(bytes32,address)` `0x4095b27949435770a1b733b92eb73b92fb8d0c052ef06cf5db328010d57a64ed`, `Frozen()` `0xa8cab3d1893ed53071b052fafa843143492f25d1d6b0170d460789f7ab1954be`, `Endorsed(address)` `0x403ec5d7987cb23abdef39abe83a6e7f084b84f0809eeda3c3a5b64df6679c56`, and the site-store event `FileSet(address,string,uint32,bytes32,string)` `0x13b9b0f05b22c496a9d9a29e7041c56c04670dc98ab327448870f18eb07b6773`.

Measured costs of the reference implementation for a pool of 10,000 (informative; transaction gas, execution gas in parentheses): `entryIndexOf` 25,700 on average and at most 35,300 (7,200 and 16,800); `bind` with a depth-14 proof about 128,000 (76,000); `storeNetlist` with the validity check 2.28 million for an 8,444-byte file of 1,204 gates (2.17 million) and 13.0 million for the 49,152-byte maximum (12.45 million); recording a one-field pool of 10,000 entries 84 million in one transaction, or seven transactions of at most 13.1 million each. The evaluator costs about 290 gas per gate for a 1,204-gate file.

## Reference Implementation

- Python, standard library only: `assets/tap-draft-netlist-bound-nft/tapnft.py` (file check, hashes, source file construction, Merkle tree, pool seeds, permutation, manifest and token-set checks, assignment, metadata and edition checks, and the unverifiable status of other formats), with the TAP-02 reference implementation `tap02_reference.py`, copied from `assets/tap-02/reference.py` (TAPs repository) with only the header comment changed, the generator `make_vectors.py` and the test suite `test_tapnft.py`.
- Solidity: https://github.com/BruceLanLan/TAP-721, to be linked at a fixed commit before Review (TAP-01 §7.2 item 8). It contains the interfaces of §8; `TapNetlistNFT` (an L1 collection), `TapCompanion` (L1 for an existing ERC-721), the libraries `TapPermutation`, `TapMerkle`, `TapNetlistCheck`, `TapNetlistStore` and `TapNetlistVM`, and their tests.
- Implementation-defined entry points of the reference L1 contract, which clients will meet: `commitManifest`, `commitManifestTokenSet` and `commitManifestNoReveal` (§5.1, §6.1); `scheduleBlockhashReveal` and `revealFromBlockhash`, with a delay of at most 1,000,000 blocks; `loadTokenSet` and `loadTokenSetChunk` (§8.5); `loadPool` and `loadPoolChunk` (§8.2 item 3); `markKnown(uint256 tokenId)` (§8.2 item 4); `poolSeed(uint256)` (§6.2). The reference contract accepts at most 100,000 covered tokens, a limit of the implementation, not of this TAP.
- The reference library does not implement the network checks of §3.2 (steps 1, 2 and 5), the publication block of §5.1, §6.1 item 7 or §7.5. Paths under `assets/` are updated when a number is assigned.

## Deployments

This TAP depends on no deployed contract of its own. Verifying a source (§3.2) uses the processor factories and processor contracts that TAP-02 and TAP-10 list under their Deployments; on BNB Smart Chain the processor factory is an upgradeable proxy that is not sealed (TAP-02, Deployments), so a verifier reads at a pinned block and relies on the netlist hash fixed in the NFT, not on the factory's future behaviour.

## Security Considerations

- **Content replaced before freezing.** At L0, and at L1 before `frozen()`, the collection owner can change `tokenURI`. The manifest hash, published before the seed, makes any substitution detectable: a token whose content does not match its pool entry under §6 fails §7.3. Tools must show the conformance level and the frozen state. Collections without a manifest have no such commitment: until `tokenURI` is frozen, their content can change without failing any check of §7.3, and tools label them accordingly (§8.1).
- **Mint-bound contracts.** A mint-bound contract (§8.2) commits to no manifest or Merkle root. Which netlist a later token receives, and how many tokens end up sharing a netlist hash, depend only on the contract's code, and `frozen()` does not mean that minting has ended; before a freeze, even the recorded hashes are protected only by that code. Tools and holders have to read the contract to know what it can still mint.
- **Seed grinding.** If the party that publishes the manifest could see the seed first, it could choose a manifest that favours chosen tokens. §6.1 requires the manifest first and one seed only; `blockhash` on single-sequencer chains is not recommended because the sequencer can grind.
- **Lost block-hash reveals.** A block hash is available on chain for 256 blocks only. A collection that schedules a `blockhash` reveal and misses that window cannot be revealed under its manifest, and choosing another block would be a second seed (§6.1, items 2 and 6).
- **Choices made after the seed.** A token set, label or rule computed from a block or formula chosen after the seed lets the producer favour chosen tokens; §6.1 items 2 and 3 forbid it.
- **Minting after the seed.** Once the seed is known, anyone can compute which unminted token id receives which entry; a collection that keeps minting lets minters pick the tokens they prefer (§6.1, item 4).
- **Public knowledge after the seed.** Once the seed is known anyone can compute every assignment, so listings made before the reveal no longer reflect public knowledge until metadata is updated (§6.1, item 5).
- **Excluded tokens.** In set mode, tokens outside the set never receive content, and no remedy is defined if such a token later turns out to be movable. A collection unsure whether an address can move its tokens should keep those tokens in the set.
- **Fake scarcity.** A collection can present one design as many by renumbering gates. Editions (§6.4) count identical files; `TAP-draft-netlist-structural-hash` counts identical designs. Collections that advertise netlist rarity should declare both; §7.1 asks a collection that declares `structuralHash` to declare it for every netlist, so that indexers can count tokens per design and not only per file.
- **Malicious files.** Netlists come from untrusted sources. Without REF records, evaluation cost is bounded by the file size (TAP-02 §7, requirement 1, still applies to tools that also handle TAP-02 netlists with REF). Parsers must check lengths first and must never execute embedded content.
- **Mutable container files.** Until a container's circuit is held by a contract that cannot write, its holder can replace every file (§8.6), and the site store's upgrader can change its behaviour at any time. A `tap.content` member could name a container the collection does not control; §7.5 requires tools to derive the container from its name and to check every file against the hashes of §7.1.
- **Gateway and marketplace substitution.** HTTPS gateways and marketplaces cache and may alter content. Every fetch is checked against its hash; a `tape://` URL is verified byte by byte by TAP-10 clients. A container fallback page can answer for a missing file; §8.6 asks collections not to set one.
- **Provenance is not ownership.** A source circuit proves where a netlist came from at a block; it gives the NFT holder no claim on that circuit, its container, its mining output or any BEM. Collections must not imply otherwise.
- **Verification by the source.** Mining verification by sampled vectors does not imply functional correctness; `TAP-draft-pod-attributes` asks collections that label netlists by quality to check them against the task's reference circuit.
- **More than one companion.** A collection's owner can endorse several companions, and a companion cannot prevent it. Tools should treat the earliest endorsed companion as canonical and flag a collection whose owner has endorsed more than one.
- **Netlists are public data.** Every on-chain netlist can be read and taped out by anyone. A netlist-bound NFT gives no exclusivity over a design: what it carries is the binding, the fair assignment and the provenance. Licensing statements (`tap.license`) describe the rights the collection grants, not rights it could enforce against copies.
- **Evaluation of committed but malformed files.** A manifest can commit the hash of an invalid file. Contracts that evaluate netlists check validity before storing (§8.2, item 4), and evaluators must revert on any byte string they cannot decode.
- **Upgradeable source contracts.** Processor contracts are beacon proxies behind an unsealed factory (TAP-02 §3 and Deployments). A later upgrade could change what `netlist(id)` returns; verifiers record the block they read, and the NFT's netlist hash, not the live chain, is authoritative.
- **Hash choice.** SHA-256 collisions are out of reach; the format version byte and `tapManifest` allow a future change.

### Open questions

1. Should a later netlist format (§2.5) allow REF records flattened under a defined rule?
2. Should the manifest require a licence for each pool rather than per token?
3. Should a minimal lock-contract interface (for example `locked()`) be standardized, so that tools can show a container as locked without knowing the lock's code?
4. Should a `vrf` seed source be defined, and against which fixed version of which VRF service?

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
