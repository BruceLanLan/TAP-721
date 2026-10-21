---
tap: TBD
title: Structural Hash of Flat Netlists
description: A canonical form and a hash for REF-free TapeOut netlists that stay the same when gates are renumbered or reordered, NAND inputs are swapped, dead gates are added or identical gates are duplicated.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-02, TAP-draft-netlist-bound-nft, TAP-draft-large-netlists
license: CC0-1.0
---

# TAP-TBD: Structural Hash of Flat Netlists

## Summary

This TAP extends TAP-721 (Netlist-Bound NFTs) with a fingerprint for every flat TapeOut netlist that stays the same when the same design is merely renumbered, reordered, padded with unused gates or duplicated, so that such copies cannot be passed off as different designs.

## Abstract

This TAP is an extension of TAP-721 (Netlist-Bound NFTs, `TAP-draft-netlist-bound-nft`): it adds a design-level identifier for the netlists of TAP-721 tokens and changes nothing in TAP-721 itself. A netlist file (`tapnet/1`, defined by `TAP-draft-netlist-bound-nft`) is identified byte for byte by its SHA-256 hash. The same design can be written as many different files: gates can be numbered in another order, the two inputs of a NAND can be swapped, unused gates can be added and a gate can be duplicated. This TAP specifies a deterministic canonicalization of a `tapnet/1` file: it removes elements that cannot influence an output, gives every remaining element a structural label (by hashing for elements without feedback, by iterative refinement for elements that depend on LATCH feedback), merges elements with equal labels, and writes the result as a canonical `tapnet/1` file in a fixed element order. The `structuralHash` is the SHA-256 of that canonical file under a domain tag. Two netlists have the same structural hash exactly when their merged structures are isomorphic with the same ordered inputs and outputs. The structural hash is not a test of logical equivalence: two different implementations of the same function have different structural hashes. The TAP comes with test vectors, including BNB Smart Chain mainnet circuits, and a reference implementation. Version 2 (§10) extends the structural hash, as a conservative extension, to `tapnet/2` files (`TAP-draft-large-netlists`) with ROM records, ROM read ports and RAM ports.

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
2. Metadata that carries a structural hash SHOULD place it as `"structuralHash"` in the `netlist` member of the `tap` object of `TAP-draft-netlist-bound-nft`, next to `sha256` (for a netlist in a format defined under §2.5 of that draft, next to the member that replaces it), as `0x` + 64 lowercase hex digits. That draft defines this member (§7.1) for formats and files for which this TAP defines a structural hash: valid `tapnet/1` files (§2), and, in version 2, also valid `tapnet/2` files without a record that §10 does not define (§10.1).
3. Tools MUST NOT describe two netlists with different structural hashes as having different functions, and MUST NOT describe two netlists with equal structural hashes as having the same metrics (gate count, `nState`): the hash identifies structure only.
4. Tools that compute structural hashes of untrusted files MUST bound the number of records before computing (TAP-02 §7, requirement 1); Security Considerations give the cost.
5. Implementations MUST complete the file check of §2 before allocating per-record structures (TAP-02 §7, requirement 2).
6. A future version that changes any step MUST use a different domain tag than `tap-structural-hash/1` and a different label prefix than `TAPSH1`, unless it is a conservative extension: it leaves the canonical file and the structural hash of every input that has a version-1 structural hash unchanged, adds only new label tags for new record kinds, leaves every file with records it does not define without a structural hash, and uses a new domain tag for canonical files that contain the new record kinds. Version 2 (`tap-structural-hash/2`, §10) is such an extension.

### 10. Version 2: `tapnet/2` files

This section defines `tap-structural-hash/2` for the `tapnet/2` format of `TAP-draft-large-netlists` §1 (ROM records `0x10`, RAM read ports `0x11`, RAM write ports `0x12`, ROM read ports `0x13`, flags byte). Steps of §2–§8 that are not mentioned here apply unchanged. `u16be(x)` is `x` as a 2-byte unsigned big-endian integer, as in `TAP-draft-large-netlists` §0.

**10.1 Scope.** Version 2 is defined for every valid `tapnet/1` file (§2) and every valid `tapnet/2` file (`TAP-draft-large-netlists` §1.2). It is a conservative extension of version 1: for every input whose merged structure (10.7) contains no ROM node and no RAM node, including every `tapnet/1` file, the canonical file and the structural hash are exactly those of §2–§7, byte for byte. A file with a record that this section does not define (for example a record kind added by a later format) has no structural hash in version 2; an implementation MUST reject it and MUST NOT reinterpret the record as another kind.

**10.2 Elements and planes.** In a `tapnet/2` file:

- each NAND and LATCH record is one element;
- a ROM record with `w` output bits is `w` elements, one per output bit: the **ROM column** `j` (`0 ≤ j < w`) produces signal `first + j`, where `first` is the first signal the record creates; its inputs are the `a` address references of the record (`addr[0]` least significant) and its table is the `2^a` bits `T[m]` = stream bit `m·w + j` of the record's data;
- a ROM read port is `w` ROM columns in the same way, with its own address references and the data of the ROM record at `romOffset` (it is a ROM column like any other; the indirection is not part of the structure);
- a RAM read port of bank `b` with `w` output bits is `w` elements: the **RAM read column** `j` produces signal `first + j` and reads bit `j` of the bank;
- a RAM write port creates no signal and is not an element.

For each bank `b` of width `w` and each `j < w`, the **plane** `(b, j)` is bit `j` of all entries of bank `b`: a memory of `2^a` one-bit entries that only the read columns `j` of `b` read and that every write port of `b` writes with its `we`, its address and its `wdata[j]`. (Informative: bit `j` of an entry evolves independently of the other bits, so a `w`-bit bank is `w` one-bit memories sharing their address and enable wiring, as a `w`-bit ROM is `w` columns.) Planes are not signals; they are the state elements of memory, as LATCHes are of single bits.

**10.3 Liveness.** §3 applies with these rules: a live ROM column makes the elements among its address references live; a live RAM read column makes the elements among its address references live and makes its plane live; a live plane `(b, j)` makes live, for every write port of bank `b` whose `we` is not signal 0, the elements among its `we`, its address references and its `wdata[j]`. Other columns of the same record, other planes of the same bank and write ports whose `we` is signal 0 are not made live. A plane that no live read column reads is not live, and neither are its writes.

**10.4 ROM columns.** Given labels `λ` of its inputs, the **reduced form** of a ROM column with inputs `p_0 … p_{a−1}` and table `T` is:

1. Let `q_0 < q_1 < … < q_{k−1}` be the distinct labels among `λ(p_i)` that are not `L(0x00 ‖ u8(0))` or `L(0x00 ‖ u8(1))`, in ascending order (`0 ≤ k ≤ a`).
2. For `0 ≤ m < 2^k`, let `addr(m) = Σ_i b_i · 2^i`, where `b_i = 0` if `λ(p_i) = L(0x00 ‖ u8(0))`, `b_i = 1` if `λ(p_i) = L(0x00 ‖ u8(1))`, and otherwise `b_i` is bit `r` of `m` for the `r` with `q_r = λ(p_i)`. The reduced table is `t[m] = T[addr(m)]`.
3. `tbytes` is `t` packed LSB first (bit `m` is bit `m mod 8` of byte `⌊m/8⌋`) into `⌈2^k / 8⌉` bytes, unused high bits zero (one byte when `k = 0`).

The label of the ROM column is `L(0x06 ‖ u8(k) ‖ q_0 ‖ … ‖ q_{k−1} ‖ tbytes)`. (Informative: address references on signal 0 or 1 are folded into the table, references with equal labels are merged to the diagonal of the table, and the remaining pins are sorted by label with the table permuted accordingly. The reduction never looks at the table to decide which pins to keep.)

**10.5 RAM planes.** For a live plane `P = (b, j)` of a bank with `a` address bits, the **ports** of `P` are its live read columns and the write ports of `b` whose `we` is not signal 0. Address position `i` is **fixed** in `P` if every port of `P` has the same constant signal (0, or 1) as `addr[i]`; the other positions, in ascending order, are the **kept** positions `i_0 < … < i_{k−1}` of `P` (`0 ≤ k ≤ a`). Kept positions are determined by signal indices and liveness only, before any label is computed.

Given labels `λ`, the **write list** of `P` is obtained from the write ports of `b` whose `we` is not signal 0, in file order: each contributes the tuple `λ(we) ‖ λ(addr[i_0]) ‖ … ‖ λ(addr[i_{k−1}]) ‖ λ(wdata[j])` (`k + 2` labels); then every tuple that is equal to a later tuple of the list is removed, keeping the order of the rest. A RAM read column with plane `P` has the **inputs** `addr[i_0] … addr[i_{k−1}]` (its references at the kept positions of `P`).

**10.6 Labels.** In §4.2 the dependency relation is extended: a ROM column depends on its inputs, a RAM read column on its inputs and its plane, and a plane on the `we`, the references at its kept positions and the `wdata[j]` of every write port of its bank whose `we` is not signal 0. A plane or element belongs to `A` if following these dependencies backwards from it never runs into a cycle. Labels of `A`:

- ROM column: the label of 10.4 from the final labels of its inputs;
- plane `P` with `k` kept positions: `L(0x07 ‖ u8(k) ‖ write list)`, where the write list (10.5) is written as the concatenation of its tuples;
- RAM read column with plane `P` and inputs `x_0 … x_{k−1}`: `L(0x0A ‖ λ(P) ‖ λ(x_0) ‖ … ‖ λ(x_{k−1}))`.

In §4.3 the planes not in `A` are refined like LATCHes and the ROM and RAM read columns not in `A` like NANDs: a plane `P` in `C` with `k` kept positions has `λ_0(P) = L(0x08 ‖ u8(k))` and `λ_{r+1}(P) = L(0x09 ‖ u8(k) ‖ write list computed from the round-`r` labels)`; a ROM column or RAM read column in `C` has as `λ_r` the label above computed from round-`r` labels (of its inputs and, for a read column, of its plane), which is well defined because its address references are smaller signal indices than itself. `n_r` counts the distinct values among `λ_r(e)` for the elements `e` of `C` together with `λ_r(P)` for the planes `P` of `C`; the definition of `R` is unchanged.

**10.7 Merging.** In §5, a node whose elements are ROM columns has kind ROM, input labels `q_0 … q_{k−1}` (in this order) and reduced table `t`; a node whose elements are RAM read columns has kind RAM, the label of its plane and its input labels `λ(x_0) … λ(x_{k−1})` (in this order). Planes with the same final label form one **plane node**, with its number `k` of kept positions and its write list. All elements (or planes) with the same final label have the same kind and the same input labels, reduced table, plane label or write list; otherwise the implementation MUST stop with an error. A ROM node with `k = 0` is a **constant column**; it is a node, distinct from the constants (signals 0 and 1). A RAM node is never merged with a constant, even when its plane has an empty write list.

**10.8 Canonical order.** In §6.1 the depth of a ROM or RAM node is `1 + max` of the depths of its input labels (`1` when it has none), where constants, inputs and LATCH nodes count as depth 0; plane nodes have no depth and are not part of the core. In §6.2, "a NAND node `w` reads node `v`" is replaced by "a NAND, ROM or RAM node `w` reads node `v`", where a ROM or RAM node reads its input labels. Plane nodes are numbered `0, 1, …` in ascending order of their labels; this number is their **bank** in the canonical file. If there are more than 256 plane nodes, the implementation MUST report an error instead of a hash.

**10.9 Records.** In §6.5:

- the record of a RAM node with plane bank `β` and inputs `(x_0 … x_{k−1})` is `0x11 ‖ u8(β) ‖ u8(max(k, 1)) ‖ u16be(1) ‖ u24(σ(x_0)) ‖ … ‖ u24(σ(x_{k−1}))`, with the single reference `u24(0)` when `k = 0`;
- the record of a ROM node with inputs `q_0 … q_{k−1}` and reduced table `t` is `0x10 ‖ u8(k) ‖ u16be(1) ‖ u24(σ(q_0)) ‖ … ‖ u24(σ(q_{k−1})) ‖ tbytes` if `k ≥ 1`, and `0x10 ‖ u8(1) ‖ u16be(1) ‖ u24(0) ‖ u8(3·t[0])` if `k = 0` (one address bit on signal 0 and the table `[t[0], t[0]]`). If an earlier record of the canonical records is a ROM record (`0x10`) with the same address width and the same data bytes, the record is instead the ROM read port `0x13 ‖ u32be(o) ‖ u8(a) ‖ u16be(1) ‖ (the same address references)`, where `o` is the byte offset in the canonical file of the first such ROM record and `a` its address width.

Copy records of ROM and RAM nodes are records of this form. The canonical records are the core records and the output-slot records of §6.5, followed by the **write records**: for each plane node in bank order, for each tuple `(we, y_0 … y_{k−1}, d)` of its write list in order, `0x12 ‖ u8(β) ‖ u8(max(k, 1)) ‖ u16be(1) ‖ u24(σ(we)) ‖ u24(σ(y_0)) ‖ … ‖ u24(σ(y_{k−1})) ‖ u24(σ(d))`, with the single address reference `u24(0)` when `k = 0`. (Write records create no signals, so the outputs remain the last `nOut` signals.)

**10.10 Canonical file and hash.** If there is no ROM node and no RAM node, the canonical file and the structural hash are those of §7 (a `tapnet/1` file and the domain `tap-structural-hash/1`). Otherwise the canonical file is

```
"TAPNET" ‖ 0x02 ‖ u8(flags) ‖ u32be(nIn) ‖ u32be(nOut) ‖ canonical records
```

with `flags = 0x01` if there is at least one plane node and `0x00` otherwise, and

```
structuralHash = SHA-256(ASCII("tap-structural-hash/2") ‖ 0x00 ‖ canonical file)
```

An implementation MUST check this canonical file as a `tapnet/2` file (`TAP-draft-large-netlists` §1.2) and MUST report an error instead of a hash if the check fails (possible only when per-column records, write records or copy records push it over the 64 MiB or 2^24-signal limits). The structural hash is computed over the file bytes with SHA-256, not with `netlistHash2`.

**10.11 Guarantees.** §8 holds with the merged structure of 10.7, where two ROM nodes correspond when they have the same reduced table and corresponding input labels, two RAM nodes when their planes and inputs correspond, and two plane nodes when they have the same `k` and corresponding write lists; behaviour (§8 item 3) is from the all-zero state and the all-zero memory (`TAP-draft-large-netlists` §1.3). In addition to the invariances of §8 item 2, the structural hash does not change under:

- ROM: permuting the address references of a ROM together with its table; permuting, adding or removing unread output bits; splitting a ROM into several ROMs with the same address references, or joining such ROMs; duplicating a ROM or some of its columns and distributing its readers; adding an address reference on signal 0 or 1 with arbitrary table entries on the other value; adding a second address reference to a signal that is already one, with arbitrary entries off the diagonal;
- ROM read ports: replacing a ROM read port by a ROM record holding a copy of the table, or the reverse;
- RAM: renumbering banks; permuting the bits of a bank consistently in all its ports (the `wdata` of every write port and the columns of every read port, readers rewired); widening a bank by bits that no live read column reads; splitting a bank by bits into several banks with copies of every port, or joining such banks; duplicating a read port and distributing its readers; duplicating a write port immediately after itself (more generally, adding a write port equal to a later write port of the same bank); adding a write port whose `we` is signal 0; adding a bank, read ports or write ports that no live read column depends on; adding an address bit that every live port of the bank ties to the same constant; reordering records in any valid way that keeps the relative order of the write ports of each bank;
- format: converting between `tapnet/1` and `tapnet/2` when no ROM or RAM node remains (for example a `tapnet/2` file whose ROMs and RAM ports are all unread).

The structural hash changes under: replacing a ROM by NAND logic (including the expansion of `TAP-draft-large-netlists` §1.3) or the reverse; using a ROM column as a buffer, an inverter or a NAND; adding an address reference that the table does not depend on; splitting a ROM by address into smaller ROMs and a multiplexer; any change of a table entry, including entries that no reachable state addresses; replacing RAM by LATCHes and multiplexers or the reverse; exchanging two different write ports of one bank; adding a write port that can be enabled, even one that a later write always overrides; permuting the address bits of a bank; changing the address width of a bank other than by an address bit tied to the same constant in every live port; and placing two banks into one bank at different address regions. A RAM read column of a bank that is never written reads 0 in every beat but is not the constant 0: a NAND that reads it has a different label from a NAND that reads signal 0.

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

**Version 2: ROM and RAM as nodes (§10).**

- *ROM as a node.* Expanding ROMs to NAND would make the hash depend on an informative expansion that nests multiplexers by address bit order (so it is not invariant under address permutation), folds constants, which version 1 refuses for NAND, and exceeds 2^24 signals for large ROMs. A mask ROM and a NAND multiplexer are different designs, as two NAND implementations of XOR are.
- *One node per ROM column and per RAM bit.* Each ROM column and each RAM read column produces one signal, so §5 and §6 apply unchanged; dead bits, column order, splitting and duplicated ROMs or ports are handled by liveness and merging without further rules. A node for a whole bank or a whole read port was rejected: a read port creates `w` consecutive signals, and an output that is one of its bits cannot be placed in a one-signal output slot or copied by a copy record, while §8 item 4 rules out inserting buffers. The canonical file writes every plane as a bank of width 1 and every live read bit as its own read port; it pays a header per column and per write tuple.
- *Planes are state, read columns are combinational.* A read port returns the memory at the start of the beat, as a LATCH returns its state, but its address acts in the same beat. Planes are therefore refined like LATCHes (round-0 label from `k` only) and read columns like NANDs. Two planes with the same final label hold the same contents in every beat from the all-zero memory, by induction over beats as for LATCHes, so merging them preserves behaviour.
- *Write order is structure.* When several write ports write one entry in one beat the last one wins (`TAP-draft-large-netlists` §1.3), so the write list keeps file order, and exchanging two different write ports changes the hash. Removing a tuple that equals a later tuple is sound: the later port writes the same entry with the same value under the same enable after it, and reads see only the memory at the start of the beat. It also stays label-driven and monotone: if two planes have equal round-`(r+1)` labels their reduced round-`r` write lists are equal; round-`(r−1)` labels are a coarsening, and removing tuples that become equal under a coarsening commutes with the removal already done, so the round-`r` labels are equal and the argument for `R` of version 1 holds, with planes counted like LATCHes. A write port that a later port always overrides but with different data is not removed: that is optimization, and its data cone, live by §10.3, could contain feedback that changes `R` and with it every label of `C` (the same obstacle as for don't-care ROM pins below).
- *Static rules for memory.* Write ports with `we` on signal 0, and address bits that every live port of a plane ties to the same constant, are recognised from signal indices and liveness alone, before labels exist, so they cannot interact with refinement. Folding such a bit is safe because no port can address the other half of the plane. Two things are not done: permuting the address bits of a bank (a canonical bit order would have to be chosen jointly for all ports of a plane, which needs a tie-break among symmetric bits), and splitting a plane into regions at bits that are constant in every port but not equal (it would need a liveness rule that knows which writes can reach which reads); both are Open questions.
- *ROM read ports.* A ROM read port is a second reader of a table. Treating its columns as ROM columns makes a file that shares a table through ports and a file that holds copies of the table have the same hash (`romports` and `romdup`). The canonical file stores each distinct reduced table once and reads the others through ROM read ports, so that a design that needs ports to fit into 64 MiB keeps a canonical file that fits too.
- *Label-driven ROM pin reduction only.* Folding constant pins and merging equal-label pins depends only on input labels, never on table contents; merging is required anyway because sorting by label has no canonical tie-break. Removing pins on which the table does not depend, or replacing an all-equal column by a constant signal, would be logic optimization with no principled stopping point; it would also make raw-live elements effectively dead, so that dead feedback loops behind such pins could change `R` and with it every label of `C`, and constant outputs cannot be written in either format.
- *Monotonicity of ROM columns.* If two ROM columns have equal round-`(r+1)` labels, their reduced forms are equal; their corresponding inputs then have equal round-`r` labels, and the round-`r` reduced forms follow from the round-`(r+1)` forms by the same further merging and re-sorting, so the round-`r` labels are equal. A ROM or RAM read column in `C` keeps at least one input or plane in `C`, so its label never equals a label of `A`, a constant or an input; plane labels in `C` use tags of their own.
- *Idempotence.* The canonical file has the merged structure: plane nodes become banks of width 1 whose write records list exactly the write list, with no write port enabled by signal 0 and no fixed address bit except the single padding bit of `k = 0`, which every port of that bank ties to signal 0 and which is folded again; ROM tables shared through ROM read ports are read back as the same columns; copy records merge back as in version 1.
- *Bank limit.* `tapnet/2` numbers banks with one byte, so a canonical file can hold at most 256 plane nodes. A design with more distinct RAM bits gets an error instead of a hash. Packing several planes into one bank by address regions would lift the limit but needs the region splitting above; it is an Open question.
- *Cost.* Labelling a ROM column costs `O(k · 2^k)`; in `C` it is repeated in every round because the label order of the inputs changes. Planes cost one pass over their write tuples per round and never touch `2^a`. This has the shape of the `O(R·|C|)` cost of version 1. Services can cache structural hashes by `netlistHash2`.
- *Conservative extension.* A format version is a representation detail; a design moved from `tapnet/1` to `tapnet/2` keeps its structural hash as long as it has no ROM or RAM node. Labels keep the prefix `TAPSH1`; the tags `0x06`–`0x0A` are new, so no existing label changes. Files with record kinds that version 2 does not define get no hash rather than a guessed one.

## Backwards Compatibility

This TAP adds an identifier and changes nothing that exists. Netlist hashes, editions and metrics of `TAP-draft-netlist-bound-nft` are unaffected.

This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`) and is submitted after it. TAP-721 is the requested number of the core draft; if editors assign another, this draft takes that number: every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, is replaced by it.

Version 2 (§10) depends on the `tapnet/2` format of `TAP-draft-large-netlists`. It adds a second domain tag and new label tags and changes no version-1 canonical file or hash: every version-1 test vector is reproduced by the version-2 implementation, both as `tapnet/1` and re-headed as `tapnet/2`. If `TAP-draft-large-netlists` is assigned a number, every reference to it here, including the `requires` field, is replaced by that number.

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

**Version 2.** `assets/tap-draft-netlist-structural-hash/vectors2.json` (format `tap-structural-hash-vectors/2`) is generated by `make_vectors2.py` and is reproducible byte for byte (SHA-256 `06bd3c06961bb4d87b60d3837591696f762b78ddd931cb5eb3a31a8c4564dbe8`). Each case gives the input file (`tapnet/1` or `tapnet/2`), the canonical file, its version, the structural hash and the counts `live`, `nodes`, `romNodes`, `ramNodes`, `planes`, `cyclic` (elements and planes in `C`), `rounds` and `copies`. Every implementation of version 2 has to reproduce the canonical file and the structural hash of every case, has to reject every file in `invalid` (RAM ports without the MEM flag, the MEM flag without RAM ports, a bank used with two different dimensions, a REF record, a ROM read port with a bad `romOffset`), and has to reproduce every case of `vectors.json` as above, both as given and re-headed as `tapnet/2`. Selected cases:

| Case | nIn / nOut | canonical | live / nodes | ROM / RAM / planes | cyclic / rounds / copies | structuralHash |
|---|---|---|---|---|---|---|
| `xor_v2_dead_ram` (= `xor_v1`, `xor_v2`, `xor_v2_dead_rom`) | 2 / 1 | v1 | 4 / 4 | 0 / 0 / 0 | 0 / 0 / 0 | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` |
| `andnot_rom` (= `andnot_rom_pins_swapped`) | 2 / 1 | v2 | 1 / 1 | 1 / 0 / 0 | 0 / 0 / 0 | `0xf4779d46f1b063f3e863b3f11e8049092ec047d7c85c5587c1ffb808ac3c18e7` |
| `andnot_nand` | 2 / 1 | v1 | 3 / 3 | 0 / 0 / 0 | 0 / 0 / 0 | `0xff38f0eecca6e6272de2fc4f23f9acaa251ce3c6b6996a3765c51a3c4bf09d53` |
| `wide_rom` (= `wide_rom_narrow`, `wide_rom_split`) | 3 / 2 | v2 | 4 / 3 | 2 / 0 / 0 | 0 / 0 / 1 | `0x70b221b7824d66d9a75b7c24d023fbdf274886828592042a855eb8c4d0197720` |
| `const_pin_plain` (= `const_pin_tied1`, `const_pin_tied0`) | 2 / 1 | v2 | 2 / 2 | 1 / 0 / 0 | 0 / 0 / 0 | `0x1b4b0592ac92f641b2befb3c40f1eacb8cc2ca9117662e6c190abd2787f869de` |
| `const_column_two_pins` (= `const_column_one_pin`, `const_column_canonical`) | 1 / 1 | v2 | 2 / 2 | 1 / 0 / 0 | 0 / 0 / 0 | `0x1cc365f21aaeef54dd53d33e419e55fdc5f1d8674c6f18375b1c0996e4c158ac` |
| `counter_rom` (= `counter_rom_permuted`) | 0 / 2 | v2 | 6 / 6 | 2 / 0 / 0 | 6 / 2 / 0 | `0x81c01c5aa1ff25e46009416db80f1ace46862f9ec367b7ed723450c262d5ccf0` |
| `sbox` | 8 / 8 | v2 | 8 / 8 | 8 / 0 / 0 | 0 / 0 / 0 | `0x651982893d76d7c9fc86b3551fadf3d4aa22224c4030829e24978f5d63172bd7` |
| `sbox_expanded` | 8 / 8 | v1 | 896 / 896 | 0 / 0 / 0 | 0 / 0 / 0 | `0x615132d97d974d6a950e2c90f533166958ba316d5055d183de06d64ed5af50e4` |
| `rom_port` (= `rom_port_two_roms`) | 4 / 1 | v2 | 3 / 3 | 2 / 0 / 0 | 0 / 0 / 0 | `0x9e0e1922a93b0e1ddb8871b81e4552156063cb5b022eca3282a7a60d55e1263c` |
| `romports` (= `romdup`) | 6 / 15 | v2 | 15 / 14 | 14 / 0 / 0 | 0 / 0 / 1 | `0xb44b176b4ca6308b3736a27fead61edd7c57d48e51c6da1b33848ffb437453b6` |
| `ram_reg` (= `ram_reg_renumbered`, `ram_reg_dup_read`, `ram_reg_dup_write`, `ram_reg_disabled_write`, `ram_reg_const_bit`, `ram_reg_dead_bank`) | 4 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x7eef710a08c5864df681c438aaa27bd9ab5886638dc961408bfd07fc49a8c0b3` |
| `ram_reg_wider_a` | 4 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x20cacc3bb19c9001221ce5d59f36913ca3128b4b6ecc3bb7f3b3e8e9e802eb18` |
| `ram_reg_extra_write` | 4 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x1cfd8e3bec733c97e37585cd1155600cc474e04214477d21d6e114892d4fe309` |
| `ram_two_writes` | 4 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x92ce5d40cc23bb3eb58f9d5726467b40dd6c4b718ebe36a326ac683b3e53c903` |
| `ram_two_writes_swapped` | 4 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x63aa26f256e7c467dbbaf44bc8edea6dd4c883f880870e6e904523f93c53e1d0` |
| `ram_wide` (= `ram_wide_col_perm`, `ram_wide_split`, `ram_wide_narrow`) | 6 / 2 | v2 | 4 / 3 | 0 / 2 / 2 | 0 / 0 / 1 | `0x14f8125b3baab914e4753d4860710e0500112c9ed375fc3ecb6ac94e318d1534` |
| `ram_counter` (= `ram_counter_split`) | 0 / 2 | v2 | 6 / 6 | 2 / 2 / 2 | 8 / 2 / 0 | `0x60edbc3bf7d26b2f04ad7e31d7306e0571753223e2285526c71cc6fe24ede97f` |
| `ram_counter_decrement` | 0 / 2 | v2 | 6 / 6 | 2 / 2 / 2 | 8 / 2 / 0 | `0x4d05e962cbe91a524fda2d62a6ab535bda3267c0d06d6f3dd764e47f923e9e3f` |
| `ram_unwritten` | 1 / 1 | v2 | 2 / 2 | 0 / 1 / 1 | 0 / 0 / 0 | `0x4c977f3658342087502f94ac15eb7a1717718a8710a2cee5deeaa180cae9937c` |
| `ram_out_equal_bits` (= `ram_out_two_ports`) | 3 / 2 | v2 | 2 / 1 | 0 / 1 / 1 | 0 / 0 / 1 | `0x76df1fdf8e37c02b9953d57123c57a6ecdda8e67b7c6179779b08177b4f24863` |
| `ram16` | 14 / 12 | v2 | 103 / 100 | 0 / 8 / 4 | 99 / 3 / 0 | `0xcd4895c3e989d7aa17b994bfa1db537819b5b9dc3cb037093963f05b259038a5` |
| `ram16_latch` | 14 / 12 | v1 | 959 / 792 | 0 / 0 / 0 | 703 / 3 / 0 | `0x6297e6c9259e7c91b9d3c78f0c90f0fcf6c8a025dce3feab3a44cb840ada621a` |
| `rammix` | 12 / 29 | v2 | 164 / 163 | 24 / 13 / 13 | 165 / 3 / 0 | `0x2505378f810f6d7a1b08babffa34ee6e5401f8db108e1b953712d175a90684f0` |

The file also contains `equalGroups` (13 hand-made groups and four seeded random netlists with live RAM, each with three variants) and `distinct` (13 pairs that must differ: table not permuted with its pins, ROM versus NAND, constant column versus signal 1, up versus down counter, S-box versus its NAND expansion, a ROM port on another address, a RAM bank with a wider address, an extra enabled write port, two write ports exchanged, RAM versus LATCH counters, a never-written bank versus signal 0, and the 16 × 4-bit memory of `TAP-draft-large-netlists` built from RAM ports versus built from LATCHes). The LATCH version of the RAM counter (`ram_counter_latch`) has the hash of `counter_rom`, which is the same design.

`test_canon2.py` checks, besides the vectors: every case of `vectors.json` and 300 random version-1 netlists with their transformed variants give the same canonical file, hash, rounds and copies under both implementations; a `tapnet/2` file whose ROMs and RAM ports are all unread hashes as version 1; for 300 random `tapnet/2` netlists with ROMs, ROM read ports, RAM banks and LATCH feedback through memory, invariance under renumbering, NAND input swaps, ROM pin and column permutations, dead ROM columns, ROM splits, replacing ROM read ports by ROM copies, duplication (including adjacent write ports), dead elements (including disabled write ports and unread banks), constant and duplicated ROM pins, bank renumbering, RAM bit permutations, dead RAM bits, constant RAM address bits, bank splits and their combination; validity, idempotence and equal outputs (from the all-zero state and memory) of every canonical file, including more than 30 with planes in `C`; that exchanging two write ports, redirecting a read port to another bank or flipping a ROM table bit in a canonical file changes the hash; that unknown opcodes are rejected; and that more than 256 plane nodes give an error.

## Reference Implementation

- `assets/tap-draft-netlist-structural-hash/canon.py` (MIT): about 250 lines of dependency-free Python (including a command line); `canonicalize(file)` returns the canonical file, the structural hash and the counts above. It uses the file check `tapnft.py` and the TAP-02 decoder `tap02_reference.py` of `TAP-draft-netlist-bound-nft`, unchanged; copies of both are included in `assets/tap-draft-netlist-structural-hash/` so that the folder runs on its own (their origin and SHA-256 are listed in its README). The path `assets/tap-draft-netlist-bound-nft/chain-snapshot.json` in Test Cases refers to that draft's asset folder and is updated when the folders are renamed `assets/tap-<nn>/` on number assignment. Command line: `python3 canon.py <file.tapnet>` or `python3 canon.py 0x<netlist> --n-in N --n-out M`.
- `make_vectors.py` regenerates `vectors.json`; `test_canon.py` runs the tests above (`python3 make_vectors.py && python3 test_canon.py`).
- `canon2.py` (MIT): version 2 (§10), about 450 lines of dependency-free Python; `canonicalize(file)` accepts `tapnet/1` and `tapnet/2` files and returns the canonical file, its version, the structural hash and the counts above. It imports `canon.py` unchanged and uses the `tapnet/2` decoder `tapnet2.py` of `TAP-draft-large-netlists` unchanged; a copy of it, and of that draft's `examples.py` used by `make_vectors2.py`, is included in the same folder. `make_vectors2.py` regenerates `vectors2.json`; `test_canon2.py` runs the version-2 tests (`python3 make_vectors2.py && python3 test_canon2.py`).

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
2. A flattening rule for REF circuits, so that netlists with sub-circuits get a structural hash, and whether it belongs here or in a later format.
3. Whether a second, pin-order-free hash (canonical under input and output permutations) is wanted for rarity tools, given that it needs a tie-break among symmetric pins.
4. Whether a small, fixed set of sound simplifications (for example constant inputs of NAND) should be offered as a separate, explicitly named hash rather than changing this one.
5. An ordering of ROM inputs in `C` by the lexicographic history `(λ_0, …, λ_r)`, which never changes once two inputs are told apart and reduces the per-round cost of a ROM column from `O(k·2^k)` to `O(k)`, at the price of ranks kept across rounds.
6. Packing planes into fewer banks of the canonical file (by address regions, with a rule that splits a plane at address bits that every port ties to constants), which would lift the limit of 256 plane nodes, and regrouping ROM columns with the same inputs into wider ROM records.
7. Whether a bank-wide permutation of address bits should be an invariance, given that it needs a joint canonical order of the address bits of all ports of a plane.

## Copyright

Copyright and related rights waived via [CC0](../LICENSE).
