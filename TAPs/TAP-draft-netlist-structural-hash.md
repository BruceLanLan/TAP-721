---
tap: TBD
title: Structural Hash of Flat Netlists
description: A canonical form and a hash for REF-free TapeOut netlists that stay the same when gates are renumbered or reordered, NAND inputs are swapped, dead gates are added or identical gates are duplicated.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-02, TAP-draft-netlist-bound-nft
license: CC0-1.0
---

# TAP-TBD: Structural Hash of Flat Netlists

## Summary

This TAP extends TAP-721 (Netlist-Bound NFTs) with a fingerprint for every flat TapeOut netlist that stays the same when the same design is merely renumbered, reordered, padded with unused gates or duplicated, so that such copies cannot be passed off as different designs.

## Abstract

This TAP is an extension of TAP-721 (Netlist-Bound NFTs, `TAP-draft-netlist-bound-nft`): it adds a design-level identifier for the netlists of TAP-721 tokens and changes nothing in TAP-721 itself. A netlist file (`tapnet/1`, defined by `TAP-draft-netlist-bound-nft`) is identified byte for byte by its SHA-256 hash. The same design can be written as many different files: gates can be numbered in another order, the two inputs of a NAND can be swapped, unused gates can be added and a gate can be duplicated. This TAP specifies a deterministic canonicalization of a `tapnet/1` file: it removes elements that cannot influence an output, gives every remaining element a structural label (by hashing for elements without feedback, by iterative refinement for elements that depend on LATCH feedback), merges elements with equal labels, and writes the result as a canonical `tapnet/1` file in a fixed element order. The `structuralHash` is the SHA-256 of that canonical file under a domain tag. Two netlists have the same structural hash exactly when their merged structures are isomorphic with the same ordered inputs and outputs. The structural hash is not a test of logical equivalence: two different implementations of the same function have different structural hashes. The TAP comes with test vectors, including BNB Smart Chain mainnet circuits, and a reference implementation.

## Motivation

`TAP-draft-netlist-bound-nft` binds each token to a netlist file and counts editions by the netlist hash. The netlist hash changes with every byte, so it says nothing about designs. A collection that advertises "10,000 unique circuits" can produce them from one design by renumbering gates, swapping NAND inputs, sprinkling in gates that drive nothing, or duplicating a gate and splitting its fan-out. Each of these changes the file and the netlist hash, and none of them changes the design. Holders, marketplaces and rarity tools need an identifier that ignores exactly these rewritings, so that "unique design" can be checked instead of trusted.

The identifier has to be defined precisely enough that independent implementations agree byte for byte, has to be cheap enough to compute for every token of a large collection, and has to state honestly what it does not detect. Full logical equivalence is not an option (Rationale), and an informal "same up to renaming" invites each tool to use its own heuristic.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.

### 1. Notation

| Notation | Meaning |
|---|---|
| `‖` | byte string concatenation |
| `u8(x)`, `u24(x)`, `u32be(x)` | `x` as a 1-, 3- or 4-byte unsigned big-endian integer |
| `SHA-256` | FIPS 180-4 |
| `L(x)` | `SHA-256(ASCII("TAPSH1") ‖ x)`, a 32-byte **label** |
| `min`, `max`, "ascending" on labels | byte-wise lexicographic order of the 32-byte strings (equivalently, as 256-bit big-endian unsigned integers) |
| element | one record of the file; element `k` (from 0) produces signal `2 + nIn + k` (TAP-02 §2) |
| `S` | `2 + nIn + E`, where `E` is the number of elements |

Labels are compared and hashed only as byte strings. Implementations MUST treat two equal labels as denoting the same structure; Security Considerations discuss collisions.

### 2. Input

The input is a `tapnet/1` file: header `"TAPNET" ‖ 0x01 ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut)` followed by TAP-02 records, NAND and LATCH only, valid as defined by `TAP-draft-netlist-bound-nft` (§2.2). An implementation MUST reject a file that is not valid there, and MUST NOT compute a structural hash for it. In particular, a file containing a REF record has no structural hash in this version.

Element `k` is either `NAND(a, b)` or `LATCH(d)` with signal indices as in TAP-02. The outputs are the signals `S − nOut … S − 1`; output `j` is signal `S − nOut + j`. Output signals are always element signals (TAP-02 §3, condition 3).

### 3. Liveness

The **live** elements are the smallest set that contains the `nOut` output elements and, with each live element, every element whose signal is one of its inputs (`a` and `b` of a NAND, `d` of a LATCH). Because LATCH `d` is followed like any other input, elements that act only through LATCH feedback are live, and a loop that no output reads is not.

All later steps use the live elements only. Constants and inputs are not elements; every input index keeps its meaning whether or not it is read.

### 4. Structural labels

**4.1 Fixed labels.** Signal 0 has label `L(0x00 ‖ u8(0))`; signal 1 has label `L(0x00 ‖ u8(1))`; input `i` (signal `2 + i`) has label `L(0x01 ‖ u32be(i))`.

**4.2 Elements without feedback.** The set `A` of **acyclic** elements is the smallest set of live elements such that a live element belongs to `A` whenever each of its inputs that is an element signal belongs to `A`. (Equivalently: an element is in `A` if and only if following inputs backwards from it never runs into a cycle.) Every element of `A` gets its final label, computed so that inputs are labelled first:

- `NAND(a, b)`: `L(0x02 ‖ min(λa, λb) ‖ max(λa, λb))`;
- `LATCH(d)`: `L(0x03 ‖ λd)`;

where `λs` is the label of signal `s`.

**4.3 Elements with feedback.** Let `C` be the live elements not in `A` (possibly empty). Each element of `C` depends on a cycle, and every cycle passes through a LATCH (TAP-02 §3, conditions 4 and 5). Labels of `C` are computed in rounds `r = 0, 1, 2, …`. In round `r`, every signal `s` has a label `λ_r(s)`: the fixed or final label for constants, inputs and elements of `A`, and for elements of `C`:

- a LATCH `e = LATCH(d)` in `C`: `λ_0(e) = L(0x04)`, and `λ_{r+1}(e) = L(0x05 ‖ λ_r(d))`;
- a NAND `e = NAND(a, b)` in `C`: `λ_r(e) = L(0x02 ‖ min(λ_r(a), λ_r(b)) ‖ max(λ_r(a), λ_r(b)))`. This is well defined because `a` and `b` are smaller signal indices than `e`.

Let `n_r` be the number of distinct values among `λ_r(e)` for `e` in `C`. Let `R` be the smallest `r ≥ 1` with `n_r = n_{r−1}`. The final label of each element `e` of `C` is `λ_R(e)`. (`R` exists and is at most one more than the number of LATCHes in `C`; see Rationale.) Implementations MAY compute the same labels by any method.

**4.4 Final labels.** Every live element now has a final label `λ(e)`. NAND labels use tag `0x02` in both 4.2 and 4.3; the tags `0x03`, `0x04` and `0x05` occur only for LATCHes.

### 5. Merging

The **nodes** are the distinct final labels of the live elements. Each node `v` has a kind and input labels, taken from any live element `e` with `λ(e) = v`:

- if `e = NAND(a, b)`: kind NAND, inputs `(min(λa, λb), max(λa, λb))`;
- if `e = LATCH(d)`: kind LATCH, input `λd`.

All elements with the same final label have the same kind and the same input labels. If an implementation finds two elements with equal final labels and different kinds or input labels, it MUST stop with an error instead of producing a structural hash (this can happen only through a SHA-256 collision).

The input labels of a node are labels of constants, inputs or nodes. A NAND node MAY have two equal inputs (for example after two duplicated gates were merged).

### 6. Canonical order

**6.1 Depth.** The depth of a LATCH node is 0. The depth of a NAND node is `1 + max(depth(x), depth(y))` over its two inputs, where a constant, an input or a LATCH node counts as depth 0.

**6.2 Output tail.** Let `o_j = λ(output element j)` for `j = 0 … nOut − 1`; several outputs MAY have the same node. Let `first(v)` be the smallest `j` with `o_j = v`. A NAND node `w` **reads** node `v` if `v` is one of `w`'s input labels. Process `j = nOut − 1, nOut − 2, …, 0` in this order: node `o_j` is **placed in slot `j`** if and only if `first(o_j) = j` and every NAND node that reads `o_j` has already been placed in a slot greater than `j`. Let `T` be the set of placed nodes.

**6.3 Core.** The core is the list of all nodes not in `T`, in ascending order of the pair `(depth(v), v)`.

**6.4 Signal indices.** Constant 0 and 1 are signals 0 and 1; input `i` is signal `2 + i`; the core node at position `p` (from 0) is signal `2 + nIn + p`; the node placed in slot `j` is signal `2 + nIn + |core| + j`. Write `σ(x)` for the signal index of the constant, input or node with label `x`.

**6.5 Records.** The record of a node `v` is

- NAND with inputs `(x, y)`: `0x00 ‖ u24(min(σ(x), σ(y))) ‖ u24(max(σ(x), σ(y)))`;
- LATCH with input `x`: `0x01 ‖ u24(σ(x))`.

The canonical records are the records of the core nodes in core order, followed by, for `j = 0 … nOut − 1`, the record of `o_j`. For a slot whose node was placed there, that record is the node itself; for any other slot it is a **copy record**: a second element with the same kind and inputs as the node, which nothing refers to.

### 7. Canonical file and structural hash

The **canonical file** is

```
"TAPNET" ‖ 0x01 ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut) ‖ canonical records
```

with the `nIn` and `nOut` of the input file. The **structural hash** is

```
structuralHash = SHA-256(ASCII("tap-structural-hash/1") ‖ 0x00 ‖ canonical file)
```

written in JSON as `0x` followed by 64 lowercase hexadecimal digits.

The canonical file is a valid `tapnet/1` file (Rationale). An implementation MUST check it as an input file (§2) before returning a hash, and MUST report an error instead of a hash if the check fails (possible only when the copy records push it over the TAP-02 size limits).

### 8. What the structural hash guarantees

Assuming SHA-256 has no collisions on the inputs involved:

1. **Characterization.** Two valid files have the same structural hash if and only if they have the same `nIn` and `nOut` and their merged structures (the nodes of §5 with their kinds, input relations, fixed constant and input labels, and the ordered list `o_0 … o_{nOut−1}`) are isomorphic.
2. **Invariance.** The structural hash does not change under any combination of: reordering or renumbering elements in any way that keeps the file valid, as long as the output elements keep their output order; swapping the two inputs of any NAND; adding, removing or changing elements that are not live; replacing an element by several elements with the same kind and inputs (duplication) and distributing its readers, LATCH feedback included, among the copies; and merging such duplicates back.
3. **Behaviour.** The canonical file computes, from the all-zero state, the same output sequence as the input file for every input sequence (TAP-02 §4). Its state layout, `nState` and gate count generally differ from the input file's.
4. **Idempotence.** The canonical file of a canonical file is itself, so both have the same structural hash.

The structural hash changes under: a permutation of the inputs or of the outputs (unless it maps the structure onto itself, as exchanging the two inputs of a symmetric XOR does); a change of `nIn` or `nOut`, including an added unused input; inserting or removing logic such as `NAND(NAND(x, x), NAND(x, x))` for `x`; constant simplification such as `NAND(x, 1)` for `NAND(x, x)`; De Morgan rewriting, retiming of LATCHes and any other change that keeps the function but changes the structure.

### 9. Use by collections and tools

1. A collection, marketplace or rarity tool that states how many distinct designs a set of netlists contains MUST count distinct structural hashes, and SHOULD state the netlist-hash count next to it.
2. Metadata that carries a structural hash SHOULD place it as `"structuralHash"` in the `netlist` member of the `tap` object of `TAP-draft-netlist-bound-nft`, next to `sha256`, as `0x` + 64 lowercase hex digits. That draft defines this member (§7.1).
3. Tools MUST NOT describe two netlists with different structural hashes as having different functions, and MUST NOT describe two netlists with equal structural hashes as having the same metrics (gate count, `nState`): the hash identifies structure only.
4. Tools that compute structural hashes of untrusted files MUST bound the number of records before computing (TAP-02 §7, requirement 1); Security Considerations give the cost.
5. Implementations MUST complete the file check of §2 before allocating per-record structures (TAP-02 §7, requirement 2).
6. A future version that changes any step MUST use a different domain tag than `tap-structural-hash/1` and a different label prefix than `TAPSH1`.

## Rationale

**Relationship to TAP-721.** This TAP is a separate Standards TAP rather than a section of TAP-721 because it specifies an algorithm that may evolve: a later version may, for example, add constant propagation under a new domain tag (§9 item 6), and such a change must neither reopen TAP-721 nor touch the netlist hash, which stays the byte-level identity of a TAP-721 token. Kept apart, TAP-721 can advance while the structural hash gathers independent implementations, and tools that only verify TAP-721 tokens need not implement it. It stays Standards because independent implementations must agree byte for byte (below).

**Structural, not functional.** The question a collection must answer is "are these two tokens the same design?", not "do these two circuits compute the same thing?". Two different implementations of XOR (4 NAND and 5 NAND) are different designs, with different costs and different authors; the vectors `xor_17851` and `xor_5nand` have different hashes on purpose. Proof-of-Design mining makes the same choice: it scores each registered design separately and ranks designs of one task by their design cost, so a functional identifier would merge exactly what PoD keeps apart.

**Why not SAT or BDD equivalence.** Combinational equivalence checking is coNP-complete and sequential equivalence (with LATCH state) is PSPACE-complete; BDDs blow up on multipliers. A hash must be computable in near-linear time by anyone, with no timeouts, no solver versions and no "undecided" result; otherwise two tools disagree on the same pair. Equivalence also does not give a canonical name: knowing that A equals B does not give a value that a third netlist C can be compared with.

**Relation to PoD's optimal-first rule.** PoD compares the design cost `C = A·max(d,1)^β` of different submissions for one task and favours the cheapest; it never asks whether two submissions are the same design. The structural hash answers that second question. The two are complementary: a collection can show both "how good" (PoD attributes) and "how many distinct" (structural hashes).

**Merging instead of tie-breaking.** Graph canonicalization is hard in general because some nodes cannot be told apart by local refinement; such nodes then need an arbitrary tie-break, and the result is no longer invariant. This TAP avoids the problem by merging every pair of elements that refinement cannot separate. The final labels of §4 are equal exactly for elements that are *bisimilar*: same kind, and inputs that are pairwise bisimilar (as an unordered pair for NAND), with constants and inputs equal only to themselves. Bisimilar elements carry equal values in every beat from the all-zero state (by induction over beats: LATCHes start at 0, and equal inputs give equal outputs), so merging them preserves behaviour. After merging, no two nodes are bisimilar; an automorphism of the merged structure would itself be a bisimulation, so the merged structure has no non-trivial automorphism, every node has a distinct label, and the canonical order of §6 is total. No fallback tie-break exists because none is needed. This gives the characterization of §8: the canonical file is a function of the isomorphism class of the merged structure, and the merged structure can be read back from the canonical file.

**What merging covers beyond duplicates.** Bisimulation also merges elements that are not literal copies but behave identically for structural reasons: two independent toggles driven by the same input (`two_toggles`), or a LATCH holding itself and a ring of two LATCHes holding each other (both always 0; `const_ring_1` and `const_ring_2` share a hash). These merges are sound and follow from structure alone, without looking at constants.

**Why labels by depth of unfolding, and why the split into `A` and `C`.** A label of 4.2 is a hash of the element's complete backward cone; it is computed once. Elements with feedback have infinite backward unfoldings, so their labels are hashes of the unfolding cut after `r` LATCH steps; the round labels refine monotonically (equal `λ_{r+1}` implies equal `λ_r`), so the partition into classes can only split, and once one round splits nothing the partition is stable forever, because round `r + 1` depends only on round `r`. Each round that does not stop splits at least one LATCH class, which bounds `R`. An element with a finite unfolding is never bisimilar to one with an infinite unfolding, so treating `A` separately gives the same merging as running rounds over everything, and keeps long shift registers and other feedback-free structures linear. A LATCH round label does not include its own previous label; monotonicity holds without it.

**Why `(depth, label)` order.** LATCH nodes have depth 0 and come first; a NAND node's inputs have smaller depth; so every NAND in the core refers backwards, and LATCH records may refer anywhere (TAP-02 §3, condition 5). Depth first keeps the canonical file readable (layers) and the label breaks ties.

**Why the output tail and copy records.** `tapnet/1` fixes the outputs as the last `nOut` records in order. After merging, two outputs can be one node, and an output node can be read by a NAND that must come later. The rule of 6.2 keeps a node in its output slot whenever that is valid and otherwise leaves it in the core and writes a copy record into the slot. Validity: a NAND placed in the tail reads only core nodes or nodes placed in earlier slots (a node placed in slot `s` is read only by NANDs placed in later slots); a copy record of a node in the core reads only core nodes; a copy in slot `j` of a node placed in slot `first(v) < j` reads nodes placed before `first(v)`. Copy records are read by nothing, so canonicalizing the canonical file merges each back into its node and reproduces the same placement (idempotence). As a result the canonical file can have up to `nOut` more records than the merged structure, and can even be larger than the input file; metrics in metadata always come from the input file.

**Why constant propagation is not in version 1.** Replacing `NAND(x, 1)` by `NOT x` or `NAND(x, 0)` by 1 is the first step of logic optimization; once it is in, there is no principled place to stop (double negation, absorption, De Morgan, retiming), and each extra rule changes every hash. An output can also become constant, which `tapnet/1` cannot express because outputs must be elements. Constants also matter for PoD cost, which counts gates as written. Version 1 therefore treats constants as two fixed leaves. Likewise `NAND(NAND(x, x), NAND(x, x))` is not reduced to `x` (`not_twice` and `not_four_times` differ).

**Why inputs and outputs keep their order.** The ordered pins are the interface of a design; a component that swaps two inputs is a different component when wired into a larger circuit. Exchanging inputs gives the same hash only when the structure is symmetric (`xor_inputs_exchanged`), and a different hash otherwise (`andnot`, `andnot_inputs_exchanged`).

**Why a canonical file and not just a hash.** The canonical file is itself a valid, runnable netlist; anyone can inspect it, run it, and recompute the hash from it. Hashing it with a domain tag keeps the structural hash distinct from the netlist hash of the same bytes.

**Why Standards rather than Application.** Two tools that count designs differently disagree on the same collection, which is an interoperability failure, not a convention; the canonical file and hash therefore have to be reproduced byte for byte by independent implementations, with vectors.

**Why REF is excluded.** A REF's structure lives in another circuit and depends on the processor at a block (TAP-02, Security Considerations). Defining a flattening rule is left to a later version (Open questions).

## Backwards Compatibility

This TAP adds an identifier and changes nothing that exists. Netlist hashes, editions and metrics of `TAP-draft-netlist-bound-nft` are unaffected.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

## Test Cases

`assets/tap-draft-netlist-structural-hash/vectors.json` (format `tap-structural-hash-vectors/1`) is generated by `make_vectors.py` from the reference implementation and is reproducible byte for byte (SHA-256 `35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa`). Each case gives the input file, its netlist hash, the canonical file, the structural hash and the counts `live`, `nodes`, `cyclic` (`|C|`), `rounds` (`R`, 0 when `C` is empty) and `copies`. Every implementation has to reproduce the canonical file and the structural hash of every case and has to reject every file in `invalid`.

| Case | nIn / nOut | live / nodes | cyclic / rounds / copies | structuralHash |
|---|---|---|---|---|
| `xor_17851` | 2 / 1 | 4 / 4 | 0 / 0 / 0 | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` |
| `xor_17851_reordered` | 2 / 1 | 4 / 4 | 0 / 0 / 0 | same |
| `xor_17851_swapped` | 2 / 1 | 4 / 4 | 0 / 0 / 0 | same |
| `xor_17851_dead` | 2 / 1 | 4 / 4 | 0 / 0 / 0 | same |
| `xor_17851_duplicated` | 2 / 1 | 5 / 4 | 0 / 0 / 0 | same |
| `xor_inputs_exchanged` | 2 / 1 | 4 / 4 | 0 / 0 / 0 | same |
| `xor_5nand` | 2 / 1 | 5 / 5 | 0 / 0 / 0 | `0x5b14f1ebd0f77af7735c51748ed0be067df673d628ead9928157e71374516f7e` |
| `andnot` | 2 / 1 | 3 / 3 | 0 / 0 / 0 | `0xff38f0eecca6e6272de2fc4f23f9acaa251ce3c6b6996a3765c51a3c4bf09d53` |
| `andnot_inputs_exchanged` | 2 / 1 | 3 / 3 | 0 / 0 / 0 | `0xda6a9bd1d790a1b01b22b7a6c0a6fb4dbca940e44a873d3561c77dc9ee6ff01c` |
| `not_twice` | 1 / 1 | 2 / 2 | 0 / 0 / 0 | `0x096157a90361130942d925b3b68f9671514d84480d1b7535403ebcb3a394ac3e` |
| `not_four_times` | 1 / 1 | 4 / 4 | 0 / 0 / 0 | `0x760266f78addafe3d2ece0d69c4b90338bd367f03590d5039e08b515a0a584ac` |
| `toggle` | 1 / 1 | 5 / 5 | 5 / 1 / 0 | `0x3bbb5fc0917a103aba62e9dcc6e6dc974c2e88796360620afd285387761b6129` |
| `toggle_latch_duplicated` | 1 / 1 | 6 / 5 | 6 / 1 / 0 | same as `toggle` |
| `two_toggles` | 1 / 2 | 10 / 5 | 10 / 1 / 1 | `0x5ccbe61cdbdcbe2bab41dc9279388c2d8d9613c3b5cec92cf070f54f9b388f09` |
| `output_feeds_output` | 2 / 2 | 2 / 2 | 0 / 0 / 0 | `0x491d421994de2a4af40f45f2e54715ceb97068a2f718a10d74532d4606379b4b` |
| `output_feeds_earlier_output` | 2 / 2 | 3 / 3 | 0 / 0 / 0 | `0x1dc622edb48b77392015b0223e783b26e230f88b72d6020d746ee80d16803a9a` |
| `const_ring_1` | 1 / 1 | 2 / 2 | 2 / 1 / 0 | `0xaa4dc675a525bf95cd4ec7d6a5986ace9db0adec59f8742a62c2e9f0fac5ccaf` |
| `const_ring_2` | 1 / 1 | 3 / 2 | 3 / 1 / 0 | same as `const_ring_1` |
| `oscillator_nin0` | 0 / 1 | 2 / 2 | 2 / 1 / 0 | `0x9bb7669e0f9489aed5e3433f8e79564d010f1e9f0aa5c3a620375e178bdb1e24` |
| `shift4` | 1 / 1 | 6 / 6 | 0 / 0 / 0 | `0x8aca90286fc15446ac229fbbc4f19b7d107d9e41e711dc8bc5139aa43669466e` |
| `lfsr4` | 0 / 1 | 12 / 12 | 12 / 4 / 0 | `0xd8202933cb79383f65fe34bd9f7cb9798543a5e8a60911e4f627fdb790a85e64` |

The file also contains `equalGroups` (cases that must share a hash: the XOR family, the toggle pair, the two constant rings, and four seeded random netlists each with three variants after renumbering, NAND input swaps, dead elements and duplication), `distinct` (pairs that must differ: 4- vs 5-NAND XOR, `andnot` vs its input-exchanged version, double vs quadruple negation), and `invalid` (a REF record, a bad header, no records, a NAND forward reference).

**Mainnet circuits.** `chainSnapshot` holds the REF-free circuits of `assets/tap-draft-netlist-structural-hash/chain-circuits.json` (pinned from `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`; the fourth circuit there, #38, uses REF and has no structural hash), read-only (`eth_call`, no transaction) on BNB Smart Chain at block 128,200,681 from processor `0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`:

| Circuit | nIn / nOut | NAND / LATCH | live / nodes / copies | structuralHash |
|---|---|---|---|---|
| #17851 (XOR, PoD miner) | 2 / 1 | 4 / 0 | 4 / 4 / 0 | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` |
| #17852 (8-bit Johnson counter task, PoD miner) | 0 / 8 | 1 / 9 | 10 / 9 / 1 | `0x7d37fb8366db82442b4c6e8213c972a8ac2d6c7b37d114d6019a0ea76d0f74c3` |
| #3151 (8-bit population count, PoD miner) | 8 / 4 | 55 / 0 | 51 / 51 / 0 | `0xbe6e9ecc052462ba51ab577539f17ec6b7119ff041c1703712eff3fc68484075` |

Two of them show the steps at work on real data. #3151 has 4 NAND that no output reads; they are dropped, and the 51 live elements agree with the third value of `cachedDepth` (`live`) that the PoD mining contract stores for this circuit, which appears to be the same count (observed for three circuits, 4, 10 and 51; not documented, and the contract source is not published). #17852 has two LATCHes with the same `d` (the first and the last record); they merge, the last output slot gets a copy record, and the canonical file equals the input file byte for byte. The canonical file of #17851 differs from the on-chain netlist only in the order of its two middle NAND records.

`test_canon.py` additionally checks, for 300 generated netlists with fixed seeds: invariance under random renumbering, NAND input swaps, dead elements (including dead LATCH loops), duplication (including LATCHes with redirected feedback) and their combination; equal outputs of input and canonical file under the TAP-02 reference evaluator for random input sequences from the all-zero state; idempotence; and validity of every canonical file.

## Reference Implementation

- `assets/tap-draft-netlist-structural-hash/canon.py` (MIT): about 250 lines of dependency-free Python (including a command line); `canonicalize(file)` returns the canonical file, the structural hash and the counts above. It uses the file check of `assets/tap-draft-netlist-bound-nft/tapnft.py` and the TAP-02 decoder `tap02_reference.py`, unchanged. These paths (`assets/tap-draft-netlist-bound-nft/tapnft.py`, `tap02_reference.py`, and `assets/tap-draft-netlist-bound-nft/chain-snapshot.json` in Test Cases) cross asset folders; they are updated when the folders are renamed `assets/tap-<nn>/` on number assignment. Command line: `python3 canon.py <file.tapnet>` or `python3 canon.py 0x<netlist> --n-in N --n-out M`.
- `make_vectors.py` regenerates `vectors.json`; `test_canon.py` runs the tests above (`python3 make_vectors.py && python3 test_canon.py`).

## Deployments

This TAP depends on no deployed contract.

## Security Considerations

- **Not a function identifier.** Different structural hashes do not mean different behaviour, and the hash cannot prove that a collection's designs are functionally distinct. Equal structural hashes do mean identical behaviour from the all-zero state (§8).
- **Deliberate variants are cheap.** Anyone can change the structural hash without changing the function, for example by inserting a double negation, re-expressing a gate with De Morgan, or adding an unused input. The hash removes the free rewritings (renumbering, swaps, dead gates, duplicates) and nothing more. A collection that claims design scarcity still has to say how its designs were made; readers should read a structural-hash count as an upper bound on the number of designs, not as a measure of originality.
- **Collisions.** Labels and the structural hash rely on SHA-256 collision resistance. A collision between labels is detected (§5) where it would produce an inconsistent merge; a crafted collision between two whole canonical files would require a SHA-256 collision.
- **Cost on adversarial input.** Liveness, the labels of `A`, merging and the tail are linear in the number of records; sorting the core is `O(n log n)`. Refinement of `C` costs one pass over `C` per round, and `R` is at most the number of LATCHes in `C` plus one, so the worst case is quadratic in the size of the feedback region. The worst case is reached by a long ring whose LATCHes can be told apart only by their distance from a single tap. *Measured* with the reference implementation (CPython 3.9, one core): a ring of 2,000 LATCHes needed 2,000 rounds and 3.2 s, and a 50,000-stage shift register (no feedback) 0 rounds and 0.95 s. Netlists that fit in one BNB Smart Chain transaction are far smaller than the sizes at which the quadratic term matters for native code, but tools have to bound the number of records of untrusted files before computing (§9, item 4), and services can cache structural hashes by netlist hash, since the structural hash is a function of the file.
- **Memory.** Decoding happens only after the file check of §2 (§9, item 5), so a malformed file cannot make a tool allocate in proportion to a length it claims.
- **Interface games.** Because input and output order are part of the hash, a collection could present one design with permuted pins as several. Tools that care can also compare structural hashes of the netlists under the pin permutations they consider equivalent; this TAP does not define a pin-order-free hash (Open questions).

### Open questions

1. Whether a quasi-linear canonical labelling of the feedback region (for example partition refinement in the style of Hopcroft or Paige and Tarjan, which finds the same classes in `O(n log n)`, combined with a canonical naming of the classes) should replace the rounds of §4.3 in a later version.
2. A flattening rule for REF circuits, so that netlists with sub-circuits get a structural hash, and whether it belongs here or in a `tapnet/2` format.
3. Whether a second, pin-order-free hash (canonical under input and output permutations) is wanted for rarity tools, given that it needs a tie-break among symmetric pins.
4. Whether a small, fixed set of sound simplifications (for example constant inputs of NAND) should be offered as a separate, explicitly named hash rather than changing this one.

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
