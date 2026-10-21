**Problem.** A contract that has to identify a TapeOut netlist, store it or check what it computes is limited by one transaction. On BNB Smart Chain (16,777,216 gas per transaction) that means files of some tens of kilobytes: the netlist-bound NFT draft (#67), for example, stores and evaluates netlists only up to 49,152 bytes, about 7,000 NAND records. The designs for which an on-chain identity and an on-chain check matter most are far larger:

- **verifiable inference**: the INT-C16 language-model chip published by its author (https://jogjohgoeg.github.io/nand-llama-research/) budgets about 1,012,501 NAND and 94,800 LATCH bits with weights in mask ROM, about 7.5 MB as NAND and LATCH records alone, and about 98 million beats per generated token;
- **checkable game results**: a game written as a circuit, where a player claims a score after a run with given buttons and anyone can contest it;
- **large designs for TapeOut processors**: processors, accelerators and lookup tables built from TAP-02 records outgrow one transaction as soon as they include memories and tables;
- **netlist-bound NFTs** that carry such designs.

Three things are missing: a compact way to write ROM data and memories (expanding a ROM into NAND gates multiplies its size, and RAM built from LATCHes dominates small processor designs), a netlist hash and an upload that fit transactions, and a way for a contract to decide a disagreement about a run that no chain can execute.

**Proposal.** A standalone Standards TAP, "Large Netlists and Verifiable Execution" (`tapnet/2`, chunked netlist hash, one-step verifiers, dispute rules):

- `tapnet/2`: the NAND and LATCH records of TAP-02 plus a mask-ROM record (opcode `0x10`), a ROM read port (`0x13`) and a writable memory (RAM read and write ports `0x11` / `0x12`, committed by a fixed-depth memory tree and gated by a header flag), files up to 64 MiB, no REF;
- `netlistHash2 = SHA-256(0x03 ‖ u64be(length) ‖ chunkRoot)` over 16,384-byte chunks, and an optional on-chain store `ITapLargeNetlistStore` (ERC-165 `0x8230af7f`) that accepts a file chunk by chunk and serves as the chunk oracle of the verifiers;
- commitments (prefix roots of signal values, state and the LATCH `d` table; an output hash chain; input leaves), a canonical, value-independent segmentation under a budget `(gates, extWords, chunks)`, default `(6000, 256, 16)`, and the one-step verifiers `verify_segment` and `verify_beat_end`, with a fixed witness encoding (witnesses at most 84,208 bytes without RAM ports, 92,810 bytes with them);
- the data and rules a dispute game MUST use: claims `(netlistHash2, T, K, inputRoot, checkpointRoot)` with a published checkpoint list, data availability, two ways to commit inputs (computed on chain, or by an input provider that may not claim), bounds on `T` and `K`, several challengers with acceptance kept apart from individual disputes, a three-level bisection that ends in exactly one verifier call, and the treatment of failed moves and timeouts. Bonds and timeout lengths are left to applications.

Measured with the Solidity reference: the costliest verifier call takes about 9.3 million gas of execution (about 10.6 million as the final move of the reference game); storing a 16 KiB chunk about 3.7 million gas per transaction. The TAP makes no claim about monetary costs.

**Type.** Standards.

**Builds on.** TAP-02 (records, bounds, bit packing, initial state) and ERC-165. It relates to the TAP-721 family (#66, #67) but does not require it: an informative section describes how a netlist-bound NFT pool references a `tapnet/2` netlist by `netlistHash2` and what its `tap.netlist` metadata contains (`format: "tapnet/2"`, `netlistHash2`, metrics, URIs). That section relies on §2.5 "Other netlist formats" of the netlist-bound NFT draft, proposed in the 2026-10-21 update of #67; version 2 of the structural hash (#70) is defined for `tapnet/2` files.

**Existing material.**

- Draft text (English, normative), test vectors and a dependency-free Python reference (68 tests), submitted as `TAPs/TAP-draft-large-netlists.md` with `assets/tap-draft-large-netlists/`; a Chinese translation is kept in the reference repository.
- Reference repository https://github.com/BruceLanLan/tap-large-netlists at commit `4fa0c0baf2c1d226b38814aed0d0f58c244cad24`: Solidity store, verifiers and an informative dispute game (Foundry, 89 tests including 118 end-to-end dispute scenarios and every vector replayed), a game-cartridge demo (an 8-bit CPU with its program in ROM and 256 bytes of RAM, 5,781 bytes, with score disputes), and an L1 data fee snapshot for Base and X Layer. Not deployed; reviewed internally; not externally audited.

**Questions for editors and readers.**

1. **ROM opcode and TAP-02.** `tapnet/2` uses opcode `0x10` for its ROM record so that low opcodes stay free for TAP-02. Should the opcode be coordinated with TAP-02 now, so that a future TAP-02 version can adopt the same record, and is a separate format version (`0x02`) the right way to keep `tapnet/1` and TAP-02 circuits unchanged?
2. **Relation to the netlist-bound NFT draft.** The proposal is standalone so that inference, games and processor designs can use it without NFTs. Its use with netlist-bound NFTs relies only on the §2.5 hook proposed in #67; the TAP cites that section, shows how `tapnet/2` meets each of its conditions, and changes nothing in that draft. Is that split acceptable?
3. **Scope.** Should the dispute economics (bonds, timeouts, eligibility) later become a separate Application TAP built on §7, as the draft suggests?
4. **Number.** We ask the editors to consider number **7007**, as #66 did for 721: ERC-7007 standardises verifiable AI-generated content settled by zkML or opML proofs, the latter with a challenge period, and this TAP provides the same kind of settlement for runs of TapeOut netlists (challenge, bisection, one-step verifier). Until a number is assigned the draft is `TAP-draft-large-netlists` with `tap: TBD`; the editors decide the final number.

