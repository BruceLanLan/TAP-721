"""Reference implementation of the draft TAP "Large Netlists and Verifiable Execution" (tapnet/2).

MIT License. Pure Python 3.9+, standard library only. Follows TAPs/TAP-draft-large-netlists.md (section
numbers below refer to it).

Contents:
  1  tapnet/2 files: encode, decode, check (ROM 0x10, RAM ports 0x11 / 0x12, ROM port 0x13,
     flags byte), metrics                                                       (spec section 1)
  2  one-beat evaluation (with ROM and memory), canonical ROM expansion to tapnet/1  (1.3)
  3  Merkle trees and proofs (0), multiproofs, chunking, netlistHash2            (0, 2.1)
  3b the optional on-chain store ITapLargeNetlistStore, which is also the chunk oracle (3, 6)
  4  prefix commitments (signal words 0x04, state words 0x05, latch d-table words 0x09),
     right-frontier append proofs, output chain 0x08, input leaves 0x0A         (4)
  4b the memory tree (word leaves 0x0B) and the state root of MEM files (0x0C)  (4.6)
  5  budgets and canonical greedy segmentation                                   (5)
  6  segment witnesses and verify_segment (reads the file only through the chunk oracle)  (6.1)
  7  beat-end segments (outputs, new state) and their verifier                  (6.2)
  8  checkpoints (0x06), tuple leaves (0x07)                                      (4.5, 7)
  9  witness encoding and parsing (with the memory extension), and witness size bounds (6.3)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple

# ---------------------------------------------------------------- 1 tapnet/2 files

MAGIC = b"TAPNET"
HEADER_LEN = 16
VERSION1, VERSION2 = 0x01, 0x02
OP_NAND, OP_LATCH, OP_REF, OP_ROM = 0x00, 0x01, 0x02, 0x10
OP_RAMR, OP_RAMW, OP_ROMP = 0x11, 0x12, 0x13     # RAM read port, RAM write port, ROM read port (1.1)
FLAG_MEM = 0x01                                  # flags byte (header byte 7), bit 0: the file has RAM ports
RAM_MAX_BANK_BITS = 1 << 24                      # 2^a * stride(w) <= 2^24 bits per bank (2^16 words)
MEM_BANK_BITS, MEM_WORD_BITS = 8, 16             # memory tree position = bank << 16 | word
MEM_HEIGHT = MEM_BANK_BITS + MEM_WORD_BITS       # 24
MEM_WEIGHT = 4                                   # extWords charged per memory access (read or write proof)
MAX_FILE = 64 << 20            # 64 MiB
MAX_SIGNALS = 1 << 24          # TAP-02
MAX_PINS = 1 << 16             # TAP-02
ROM_MIN_A, ROM_MAX_A = 1, 20
ROM_MIN_W, ROM_MAX_W = 1, 256

CHUNK = 16384                  # C

DOM_NODE = 0x01
DOM_CHUNK = 0x02
DOM_NH2 = 0x03
DOM_SIGNAL = 0x04              # signal-value words, also output words
DOM_STATE = 0x05
DOM_CHECKPOINT = 0x06
DOM_TUPLE = 0x07
DOM_IO = 0x08                  # output hash chain
DOM_LATCHD = 0x09              # latch d-reference table words
DOM_INPUT = 0x0A               # per-beat input leaves
DOM_MEMWORD = 0x0B             # memory word leaf: SHA-256(0x0B || word), no index (4.6)
DOM_STATE2 = 0x0C              # state root of a MEM file: SHA-256(0x0C || latchRoot || memRoot)

EMPTY = b"\x00" * 32           # commitment of an empty prefix; as a stateRoot: the all-zero state


class Invalid(ValueError):
    """A file or value this extension says MUST be rejected."""


class Missing(Exception):
    """A verifier needed a byte, word or proof the witness does not contain."""


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def u8(x: int) -> bytes:
    return x.to_bytes(1, "big")


def u16(x: int) -> bytes:
    return x.to_bytes(2, "big")


def u24(x: int) -> bytes:
    return x.to_bytes(3, "big")


def u32(x: int) -> bytes:
    return x.to_bytes(4, "big")


def u64(x: int) -> bytes:
    return x.to_bytes(8, "big")


def hx(b: bytes) -> str:
    return "0x" + b.hex()


def rom_data_len(a: int, w: int) -> int:
    return ((1 << a) * w + 7) // 8


def ram_stride(w: int) -> int:
    """Bits per RAM entry in the bank's bit vector: w rounded up to a power of two (so an entry never straddles
    a 256-bit word)."""
    s = 1
    while s < w:
        s <<= 1
    return s


def enc_ramr(bank: int, addr: Sequence[int], w: int) -> bytes:
    return bytes([OP_RAMR, bank, len(addr)]) + u16(w) + b"".join(u24(x) for x in addr)


def enc_ramw(bank: int, addr: Sequence[int], wdata: Sequence[int], we: int) -> bytes:
    return (bytes([OP_RAMW, bank, len(addr)]) + u16(len(wdata)) + u24(we) + b"".join(u24(x) for x in addr)
            + b"".join(u24(x) for x in wdata))


def enc_romp(target: int, addr: Sequence[int], w: int) -> bytes:
    return bytes([OP_ROMP]) + u32(target) + bytes([len(addr)]) + u16(w) + b"".join(u24(x) for x in addr)


def enc_nand(x: int, y: int) -> bytes:
    return bytes([OP_NAND]) + u24(x) + u24(y)


def enc_latch(d: int) -> bytes:
    return bytes([OP_LATCH]) + u24(d)


def pack_rom_data(entries: Sequence[int], a: int, w: int) -> bytes:
    """Entry k occupies bits [k*w, (k+1)*w) of an LSB-first bit stream (TAP-02 section 5)."""
    if len(entries) != 1 << a:
        raise Invalid("ROM needs exactly 2^a entries")
    out = bytearray(rom_data_len(a, w))
    for k, e in enumerate(entries):
        if e < 0 or e >> w:
            raise Invalid("ROM entry wider than w")
        base = k * w
        for j in range(w):
            if (e >> j) & 1:
                bit = base + j
                out[bit >> 3] |= 1 << (bit & 7)
    return bytes(out)


def enc_rom(addr: Sequence[int], w: int, data: bytes) -> bytes:
    a = len(addr)
    if not (ROM_MIN_A <= a <= ROM_MAX_A and ROM_MIN_W <= w <= ROM_MAX_W):
        raise Invalid("ROM dimensions out of range")
    if len(data) != rom_data_len(a, w):
        raise Invalid("ROM data length")
    return bytes([OP_ROM, a]) + u16(w) + b"".join(u24(s) for s in addr) + data


def make_file(records: bytes, n_in: int, n_out: int, version: int = VERSION2, flags: int = 0) -> bytes:
    """Wrap record bytes in a header without checking (use check_file to validate). flags = FLAG_MEM for a
    file with RAM ports (spec 1.1)."""
    return MAGIC + bytes([version, flags]) + u32(n_in) + u32(n_out) + records


class RawRecord(NamedTuple):
    op: int
    off: int        # byte offset of the opcode
    refs: tuple     # NAND (x, y); LATCH (d,); ROM address references, addr[0] = least significant bit
    a: int
    w: int
    ds: int         # ROM data start (absolute offset); NAND/LATCH: end of record
    dl: int         # ROM data length; else 0
    end: int        # offset of the next record
    n_out: int
    bank: int = 0   # RAM ports: bank number
    target: int = 0 # ROM port: offset of the ROM record it reads

    @property
    def struct_end(self) -> int:
        """End of the bytes a verifier must read: the whole record, or a ROM's header and references.
        (A ROM port's ds points at its target ROM's data; its structural bytes are the whole port record.)"""
        return self.ds if self.op in (OP_NAND, OP_LATCH, OP_ROM) else self.end


def parse_record(read: Callable[[int, int], bytes], off: int, file_len: int) -> RawRecord:
    """Parse one record. Lengths are checked against file_len before anything is read or allocated.

    read(offset, n) returns n bytes (or raises Missing in a verifier)."""
    if off >= file_len:
        raise Invalid("record offset beyond end of file")
    op = read(off, 1)[0]
    if op == OP_NAND:
        end = off + 7
        if end > file_len:
            raise Invalid(f"truncated NAND at byte {off}")
        b = read(off + 1, 6)
        return RawRecord(op, off, (int.from_bytes(b[0:3], "big"), int.from_bytes(b[3:6], "big")), 0, 0, end, 0, end, 1)
    if op == OP_LATCH:
        end = off + 4
        if end > file_len:
            raise Invalid(f"truncated LATCH at byte {off}")
        b = read(off + 1, 3)
        return RawRecord(op, off, (int.from_bytes(b, "big"),), 0, 0, end, 0, end, 1)
    if op == OP_ROM:
        if off + 4 > file_len:
            raise Invalid(f"truncated ROM header at byte {off}")
        h = read(off + 1, 3)
        a, w = h[0], int.from_bytes(h[1:3], "big")
        if not ROM_MIN_A <= a <= ROM_MAX_A:
            raise Invalid(f"ROM address width a={a} out of range")
        if not ROM_MIN_W <= w <= ROM_MAX_W:
            raise Invalid(f"ROM word width w={w} out of range")
        ds = off + 4 + 3 * a
        dl = rom_data_len(a, w)
        end = ds + dl
        if end > file_len:  # checked before reading references or touching data
            raise Invalid(f"truncated ROM at byte {off}")
        b = read(off + 4, 3 * a)
        refs = tuple(int.from_bytes(b[3 * i:3 * i + 3], "big") for i in range(a))
        return RawRecord(op, off, refs, a, w, ds, dl, end, w)
    if op in (OP_RAMR, OP_RAMW, OP_ROMP):
        hl = {OP_RAMR: 5, OP_RAMW: 5, OP_ROMP: 8}[op]
        if off + hl > file_len:
            raise Invalid(f"truncated port header at byte {off}")
        h = read(off + 1, hl - 1)
        if op == OP_ROMP:
            tgt, a, w = int.from_bytes(h[0:4], "big"), h[4], int.from_bytes(h[5:7], "big")
            bank = 0
        else:
            bank, a, w, tgt = h[0], h[1], int.from_bytes(h[2:4], "big"), 0
        if not ROM_MIN_A <= a <= ROM_MAX_A or not ROM_MIN_W <= w <= ROM_MAX_W:
            raise Invalid(f"port dimensions out of range at byte {off}")
        if op != OP_ROMP and (1 << a) * ram_stride(w) > RAM_MAX_BANK_BITS:
            raise Invalid(f"RAM bank larger than 2^24 bits at byte {off}")
        nrefs = a if op != OP_RAMW else 1 + a + w
        end = off + hl + 3 * nrefs
        if end > file_len:
            raise Invalid(f"truncated port record at byte {off}")
        b = read(off + hl, 3 * nrefs)
        refs = tuple(int.from_bytes(b[3 * i:3 * i + 3], "big") for i in range(nrefs))
        if op == OP_ROMP:
            ds = tgt + 4 + 3 * a          # data of the target ROM (validity: an earlier ROM with the same a, w)
            return RawRecord(op, off, refs, a, w, ds, rom_data_len(a, w), end, w, 0, tgt)
        return RawRecord(op, off, refs, a, w, end, 0, end, w if op == OP_RAMR else 0, bank, 0)
    if op == OP_REF:
        raise Invalid(f"REF record (opcode 0x02) at byte {off} is not allowed in tapnet/2")
    raise Invalid(f"unknown opcode 0x{op:02x} at byte {off}")


@dataclass
class Record:
    raw: RawRecord
    first_out: int
    latch_ord: int  # LATCH: its ordinal; otherwise the number of latches before it


@dataclass
class Netlist:
    data: bytes
    version: int
    n_in: int
    n_out: int
    records: List[Record]
    n_signals: int
    latch_d: List[int]                 # d reference of each latch, in file order
    nand: int = 0
    rom_records: int = 0
    rom_bits: int = 0
    flags: int = 0
    banks: Dict[int, Tuple[int, int]] = field(default_factory=dict)   # bank -> (a, w)
    ram_reads: int = 0
    ram_writes: int = 0
    rom_ports: int = 0

    @property
    def n_latch(self) -> int:
        return len(self.latch_d)

    @property
    def has_mem(self) -> bool:
        return bool(self.flags & FLAG_MEM)

    def metrics(self) -> dict:
        m = {"nIn": self.n_in, "nOut": self.n_out, "nand": self.nand, "latch": self.n_latch,
             "romBits": self.rom_bits, "romRecords": self.rom_records, "signals": self.n_signals,
             "bytes": len(self.data)}
        if self.has_mem or self.rom_ports:
            m.update({"ramBanks": len(self.banks), "ramBits": sum((1 << a) * w for a, w in self.banks.values()),
                      "ramReadPorts": self.ram_reads, "ramWritePorts": self.ram_writes, "romPorts": self.rom_ports})
        return m


def decode(data: bytes, versions: Tuple[int, ...] = (VERSION2,)) -> Netlist:
    """Decode and fully check a file. tapnet/2 only by default; versions=(1,) or (1, 2) for tapnet/1 too
    (tapnet/1 never allows ROM)."""
    if not isinstance(data, (bytes, bytearray)):
        raise Invalid("file must be bytes")
    data = bytes(data)
    if len(data) > MAX_FILE:
        raise Invalid("file larger than 64 MiB")
    if len(data) < HEADER_LEN:
        raise Invalid("file shorter than the 16-byte header")
    if data[:6] != MAGIC:
        raise Invalid("bad magic")
    version = data[6]
    if version not in versions:
        raise Invalid(f"unsupported version {version}")
    flags = data[7]
    if flags & ~FLAG_MEM or (flags and version != VERSION2):
        raise Invalid("flags byte: unknown flag bits")
    n_in = int.from_bytes(data[8:12], "big")
    n_out = int.from_bytes(data[12:16], "big")
    if n_in > MAX_PINS:
        raise Invalid("nIn out of range")
    if not 1 <= n_out <= MAX_PINS:
        raise Invalid("nOut out of range")
    if len(data) == HEADER_LEN:
        raise Invalid("no records")

    def read(o: int, n: int) -> bytes:
        return data[o:o + n]

    flen = len(data)
    off, nxt, records, latch_d = HEADER_LEN, 2 + n_in, [], []
    nand = rom_records = rom_bits = 0
    banks: Dict[int, Tuple[int, int]] = {}
    roms: Dict[int, Tuple[int, int]] = {}
    nr = nw = npo = 0
    while off < flen:
        raw = parse_record(read, off, flen)
        if raw.op in (OP_ROM, OP_RAMR, OP_RAMW, OP_ROMP) and version == VERSION1:
            raise Invalid("ROM and port records are not allowed in tapnet/1")
        if raw.op in (OP_RAMR, OP_RAMW):
            if banks.setdefault(raw.bank, (raw.a, raw.w)) != (raw.a, raw.w):
                raise Invalid(f"RAM port at byte {off} disagrees with the dimensions of bank {raw.bank}")
            nr += raw.op == OP_RAMR
            nw += raw.op == OP_RAMW
        if raw.op == OP_ROMP:
            if roms.get(raw.target) != (raw.a, raw.w):
                raise Invalid(f"ROM port at byte {off} does not name an earlier ROM with the same a, w")
            npo += 1
        if raw.op == OP_ROM:
            roms[off] = (raw.a, raw.w)
        if nxt + raw.n_out > MAX_SIGNALS:
            raise Invalid("more than 2^24 signals")
        if raw.op != OP_LATCH:
            for r in raw.refs:
                if r >= nxt:
                    raise Invalid(f"signal {r} referenced by the record at byte {off} is not available")
        if raw.op == OP_ROM:
            bits = (1 << raw.a) * raw.w
            if bits % 8 and data[raw.end - 1] >> (bits % 8):
                raise Invalid(f"nonzero padding bits in the ROM at byte {off}")
            rom_records += 1
            rom_bits += bits
        elif raw.op == OP_NAND:
            nand += 1
        records.append(Record(raw, nxt, len(latch_d)))
        if raw.op == OP_LATCH:
            latch_d.append(raw.refs[0])
        nxt += raw.n_out
        off = raw.end
    for d in latch_d:
        if d >= nxt:
            raise Invalid(f"LATCH references signal {d}, beyond the last signal")
    if nxt - 2 - n_in < n_out:
        raise Invalid("too few signals for outputs")
    if flags and not banks:
        raise Invalid("flags byte: MEM flag set, but the file has no RAM ports")
    if banks and not flags:
        raise Invalid("flags byte: a file with RAM ports must set the MEM flag")
    return Netlist(data, version, n_in, n_out, records, nxt, latch_d, nand, rom_records, rom_bits,
                   flags, banks, nr, nw, npo)


def check_file(data: bytes) -> dict:
    """Full check of a tapnet/2 file. Returns its metrics or raises Invalid."""
    return decode(data).metrics()


def _as_netlist(f) -> Netlist:
    return f if isinstance(f, Netlist) else decode(f, (VERSION1, VERSION2))


# ---------------------------------------------------------------- 2 evaluation and ROM expansion

def evaluate(f, state: Sequence[int], inputs: Sequence[int],
             flip_signals=frozenset(), flip_state=frozenset()) -> Tuple[List[int], List[int], List[int]]:
    """One beat. Returns (V, outputs, new_state), V = all signal values of the beat.

    `f` is a decoded Netlist or the file bytes (decoded on every call; see step()).

    flip_signals / flip_state inject faults (used only by the dispute simulation's cheaters).
    For a file with RAM ports use evaluate_full (this assumes all-zero memory and drops the new memory)."""
    nl = _as_netlist(f)
    if nl.has_mem or nl.rom_ports:
        V, outs, ns, _, _ = evaluate_full(nl, state, None, inputs, flip_signals, flip_state)
        return V, outs, ns
    if len(state) != nl.n_latch or len(inputs) != nl.n_in:
        raise ValueError("state or input length does not match the netlist")
    if any(b not in (0, 1) for b in state) or any(b not in (0, 1) for b in inputs):
        raise ValueError("bits must be 0 or 1")
    V = [0, 1] + list(inputs)
    data = nl.data
    for rec in nl.records:
        raw = rec.raw
        if raw.op == OP_NAND:
            v = 1 - (V[raw.refs[0]] & V[raw.refs[1]])
            if flip_signals and len(V) in flip_signals:
                v ^= 1
            V.append(v)
        elif raw.op == OP_LATCH:
            v = state[rec.latch_ord]
            if flip_signals and len(V) in flip_signals:
                v ^= 1
            V.append(v)
        else:
            addr = 0
            for i, r in enumerate(raw.refs):
                addr |= V[r] << i
            base = addr * raw.w
            for j in range(raw.w):
                bit = base + j
                v = (data[raw.ds + (bit >> 3)] >> (bit & 7)) & 1
                if flip_signals and len(V) in flip_signals:
                    v ^= 1
                V.append(v)
    new_state = [V[d] for d in nl.latch_d]
    for l in flip_state:
        new_state[l] ^= 1
    return V, V[len(V) - nl.n_out:], new_state


Mem = Dict[int, List[int]]          # bank -> its 2^a entries (ints of w bits); a missing bank is all zero


def mem_copy(mem: Optional[Mem]) -> Mem:
    return {b: list(v) for b, v in (mem or {}).items()}


def mem_get(nl: Netlist, mem: Optional[Mem], bank: int, addr: int) -> int:
    v = (mem or {}).get(bank)
    return v[addr] if v is not None else 0


def evaluate_full(f, state: Sequence[int], mem: Optional[Mem], inputs: Sequence[int],
                  flip_signals=frozenset(), flip_state=frozenset(), flip_mem=frozenset()):
    """One beat of a file that may have RAM ports (spec 1.3). Returns
    (V, outputs, new_state, new_mem, events): RAM read ports see `mem` (the memory at the start of the beat);
    write ports are applied in file order to a copy, which becomes new_mem. events lists every applied
    memory change as (record offset, bank, addr, new entry), in file order (used to build the per-segment
    memory roots M). flip_mem = {(bank, addr, bit)}: a cheater flips that bit of the entry right after the
    first write port of `bank` in this beat (whether or not it wrote), and records it as an event there."""
    nl = _as_netlist(f)
    if len(state) != nl.n_latch or len(inputs) != nl.n_in:
        raise ValueError("state or input length does not match the netlist")
    V = [0, 1] + list(inputs)
    data = nl.data
    new_mem = mem_copy(mem)
    events = []
    flipped = set()

    def push(v):
        if flip_signals and len(V) in flip_signals:
            v ^= 1
        V.append(v)

    for rec in nl.records:
        raw = rec.raw
        if raw.op == OP_NAND:
            push(1 - (V[raw.refs[0]] & V[raw.refs[1]]))
        elif raw.op == OP_LATCH:
            push(state[rec.latch_ord])
        elif raw.op in (OP_ROM, OP_ROMP):
            addr = 0
            for i, r in enumerate(raw.refs):
                addr |= V[r] << i
            base = addr * raw.w
            for j in range(raw.w):
                bit = base + j
                push((data[raw.ds + (bit >> 3)] >> (bit & 7)) & 1)
        elif raw.op == OP_RAMR:
            addr = sum(V[r] << i for i, r in enumerate(raw.refs))
            e = mem_get(nl, mem, raw.bank, addr)
            for j in range(raw.w):
                push((e >> j) & 1)
        else:  # OP_RAMW
            we = V[raw.refs[0]]
            addr = sum(V[r] << i for i, r in enumerate(raw.refs[1:1 + raw.a]))
            wd = sum(V[r] << j for j, r in enumerate(raw.refs[1 + raw.a:]))
            bank = new_mem.setdefault(raw.bank, [0] * (1 << raw.a))
            if we:
                bank[addr] = wd
                events.append((raw.off, raw.bank, addr, wd))
            if raw.bank not in flipped:
                flipped.add(raw.bank)
                for (b, k, i) in flip_mem:
                    if b == raw.bank:
                        bank[k] ^= 1 << i
                        events.append((raw.off, b, k, bank[k]))
    new_state = [V[d] for d in nl.latch_d]
    for l in flip_state:
        new_state[l] ^= 1
    return V, V[len(V) - nl.n_out:], new_state, new_mem, events


def step(f, state_bits: Sequence[int], input_bits: Sequence[int]) -> Tuple[List[int], List[int]]:
    """One beat including ROM. Returns (outputs, new_state).

    `f` is a decoded Netlist or the file bytes. Bytes are decoded (and checked for validity) on every call,
    so a caller that runs many beats should decode once with decode() and pass the Netlist; evaluate()
    accepts both forms in the same way."""
    _, outs, ns = evaluate(f, state_bits, input_bits)
    return outs, ns


def pack_bits(bits: Sequence[int]) -> bytes:
    out = bytearray((len(bits) + 7) // 8)
    for i, v in enumerate(bits):
        if v:
            out[i >> 3] |= 1 << (i & 7)
    return bytes(out)


def unpack_bits(data: bytes, n: int) -> List[int]:
    return [(data[i >> 3] >> (i & 7)) & 1 if (i >> 3) < len(data) else 0 for i in range(n)]


def expand_rom_to_tapnet1(f) -> bytes:
    """An equivalent tapnet/1 file: every ROM becomes a NAND multiplexer tree over its address bits
    (informative canonical expansion; constants folded, sub-trees shared within one ROM).
    NAND and LATCH records are copied in order; LATCH d references are remapped."""
    nl = _as_netlist(f)
    out = bytearray()
    nxt = 2 + nl.n_in
    mapping = list(range(2 + nl.n_in))
    patches = []

    def emit(x: int, y: int) -> int:
        nonlocal nxt
        out.extend(enc_nand(x, y))
        nxt += 1
        return nxt - 1

    if nl.has_mem:
        raise Invalid("a file with RAM ports has no tapnet/1 expansion")
    for rec in nl.records:
        raw = rec.raw
        if raw.op == OP_NAND:
            mapping.append(emit(mapping[raw.refs[0]], mapping[raw.refs[1]]))
        elif raw.op == OP_LATCH:
            patches.append((len(out), raw.refs[0]))
            out.extend(enc_latch(0))
            mapping.append(nxt)
            nxt += 1
        else:
            addr = [mapping[r] for r in raw.refs]
            memo: Dict[Tuple[int, int], int] = {}
            notmap: Dict[int, int] = {}

            def not_(x: int) -> int:
                if x < 2:
                    return 1 - x
                if x not in notmap:
                    s = emit(x, x)
                    notmap[x], notmap[s] = s, x
                return notmap[x]

            def nand(x: int, y: int) -> int:
                if x > y:
                    x, y = y, x
                if x == 0:
                    return 1
                if x == 1 or x == y:
                    return not_(y)
                if (x, y) not in memo:
                    memo[(x, y)] = emit(x, y)
                return memo[(x, y)]

            def mux(sel: int, x0: int, x1: int) -> int:
                return x0 if x0 == x1 else nand(nand(x0, not_(sel)), nand(x1, sel))

            vals_out = []
            for j in range(raw.w):
                vals = []
                for k in range(1 << raw.a):
                    bit = k * raw.w + j
                    vals.append((nl.data[raw.ds + (bit >> 3)] >> (bit & 7)) & 1)  # constants 0/1 are signals 0/1
                for i in range(raw.a):
                    vals = [mux(addr[i], vals[2 * m], vals[2 * m + 1]) for m in range(len(vals) // 2)]
                vals_out.append(vals[0])
            invs = [not_(v) for v in vals_out]
            mapping.extend(emit(i, i) for i in invs)   # fresh output signals, contiguous
        if nxt > MAX_SIGNALS:
            raise Invalid("expansion exceeds 2^24 signals")
    for pos, d in patches:
        out[pos + 1:pos + 4] = u24(mapping[d])
    want = [mapping[x] for x in range(nl.n_signals - nl.n_out, nl.n_signals)]
    if want != list(range(nxt - nl.n_out, nxt)):
        invs = [emit(s, s) for s in want]
        for i in invs:
            emit(i, i)
    if nxt > MAX_SIGNALS:
        raise Invalid("expansion exceeds 2^24 signals")
    return make_file(bytes(out), nl.n_in, nl.n_out, VERSION1)


# ---------------------------------------------------------------- 3 Merkle trees, chunks, netlistHash2

def node_hash(left: bytes, right: bytes) -> bytes:
    return sha256(b"\x01" + left + right)


def merkle_levels(leaves: Sequence[bytes]) -> List[List[bytes]]:
    """Core TAP section 5.3: node = SHA-256(0x01 || L || R), an odd last node moves up unchanged."""
    if not leaves:
        raise Invalid("empty tree")
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        lv = levels[-1]
        nxt = [node_hash(lv[i], lv[i + 1]) for i in range(0, len(lv) - 1, 2)]
        if len(lv) % 2:
            nxt.append(lv[-1])
        levels.append(nxt)
    return levels


def merkle_root(leaves: Sequence[bytes]) -> bytes:
    return merkle_levels(leaves)[-1][0]


def merkle_proof(levels: List[List[bytes]], index: int) -> List[bytes]:
    return multiproof(levels, [index])


def merkle_verify(root: bytes, size: int, index: int, leaf: bytes, proof: Sequence[bytes]) -> bool:
    return multiverify(root, size, {index: leaf}, proof)


def multiproof(levels: List[List[bytes]], indices: Sequence[int]) -> List[bytes]:
    """Deduplicated proof for several leaves: at each level, in increasing index order, the sibling of every
    known node that is neither known nor absent (odd last node)."""
    known = sorted(set(indices))
    if not known or known[0] < 0 or known[-1] >= len(levels[0]):
        raise Invalid("multiproof index out of range")
    proof = []
    for lv in levels[:-1]:
        ks = set(known)
        for i in known:
            sib = i ^ 1
            if sib < len(lv) and sib not in ks:
                proof.append(lv[sib])
        known = sorted({i >> 1 for i in known})
    return proof


def multiverify(root: bytes, size: int, leaves: Dict[int, bytes], proof: Sequence[bytes]) -> bool:
    if not leaves or size < 1 or any(not 0 <= i < size for i in leaves):
        return False
    known, width, p = dict(leaves), size, 0
    while width > 1:
        nxt: Dict[int, bytes] = {}
        for i in sorted(known):
            if (i >> 1) in nxt:
                continue
            if i % 2 == 0:
                if i + 1 >= width:
                    h = known[i]
                elif i + 1 in known:
                    h = node_hash(known[i], known[i + 1])
                else:
                    if p >= len(proof):
                        return False
                    h = node_hash(known[i], proof[p])
                    p += 1
            else:
                if p >= len(proof):
                    return False
                h = node_hash(proof[p], known[i])
                p += 1
            nxt[i >> 1] = h
        known, width = nxt, (width + 1) // 2
    return p == len(proof) and known.get(0) == root


def split_chunks(data: bytes) -> List[bytes]:
    return [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]


def n_chunks(file_len: int) -> int:
    return (file_len + CHUNK - 1) // CHUNK


def chunk_leaf(i: int, chunk: bytes) -> bytes:
    return sha256(bytes([DOM_CHUNK]) + u32(i) + chunk)


def chunk_levels(data: bytes) -> List[List[bytes]]:
    return merkle_levels([chunk_leaf(i, c) for i, c in enumerate(split_chunks(data))])


def chunk_root(data: bytes) -> bytes:
    return chunk_levels(data)[-1][0]


def nh2_from(file_len: int, root: bytes) -> bytes:
    return sha256(bytes([DOM_NH2]) + u64(file_len) + root)


def netlist_hash2(data: bytes) -> bytes:
    """netlistHash2 = SHA-256(0x03 || u64be(fileLength) || chunkMerkleRoot)."""
    return nh2_from(len(data), chunk_root(data))


def chunk_proof(data: bytes, index: int, levels=None) -> List[bytes]:
    return merkle_proof(levels or chunk_levels(data), index)


def verify_chunk(netlist_hash2_: bytes, file_len: int, root: bytes, index: int, chunk: bytes,
                 proof: Sequence[bytes]) -> bool:
    """What putChunk checks: the chunk, its index and proof against the committed netlistHash2."""
    if nh2_from(file_len, root) != netlist_hash2_:
        return False
    n = n_chunks(file_len)
    if not 0 <= index < n:
        return False
    want = CHUNK if index < n - 1 else file_len - CHUNK * (n - 1)
    return len(chunk) == want and merkle_verify(root, n, index, chunk_leaf(index, chunk), proof)


# ---------------------------------------------------------------- 3b the store and the chunk oracle

class StoreError(Exception):
    """A revert of ITapLargeNetlistStore: name is the Solidity error, arg its argument."""

    def __init__(self, name: str, arg):
        super().__init__(f"{name}({arg})")
        self.name, self.arg = name, arg


class LargeStore:
    """Reference model of ITapLargeNetlistStore (spec section 3). `known` is the set of known netlist hashes
    (spec section 3: which hashes are known is defined by the contract). Events are appended to self.events as (name, args).

    The store is also the chunk oracle of the verifiers (spec section 6): for a netlistHash2 with largeStored true,
    largeInfo gives the file length and largeChunk(h, i) chunk i, each chunk having been checked against
    netlistHash2 by putChunk."""

    def __init__(self, known: Sequence[bytes] = ()):
        self.known = set(known)
        self.begun: Dict[bytes, Tuple[int, bytes]] = {}
        self.chunks: Dict[bytes, Dict[int, bytes]] = {}
        self.header: Dict[bytes, Tuple[int, int]] = {}
        self.events: List[Tuple[str, tuple]] = []
        self.reads = 0                       # largeChunk calls (instrumentation for measurements)

    def beginLarge(self, h: bytes, length: int, root: bytes) -> None:
        if h not in self.known:
            raise StoreError("UnknownNetlist", hx(h))
        if not HEADER_LEN < length <= MAX_FILE:
            raise StoreError("BadLength", length)
        if nh2_from(length, root) != h:
            raise StoreError("HashMismatch", hx(h))
        if h in self.begun:
            return
        self.begun[h] = (length, root)
        self.chunks[h] = {}
        self.events.append(("LargeBegun", (hx(h), length, hx(root))))

    def putChunk(self, h: bytes, index: int, chunk: bytes, proof: Sequence[bytes]) -> None:
        if h not in self.begun:
            raise StoreError("NotBegun", hx(h))
        length, root = self.begun[h]
        if not verify_chunk(h, length, root, index, chunk, proof):
            raise StoreError("BadChunk", index)
        if index in self.chunks[h]:
            return
        self.chunks[h][index] = bytes(chunk)
        if index == 0:
            self.header[h] = (int.from_bytes(chunk[8:12], "big"), int.from_bytes(chunk[12:16], "big"))
        self.events.append(("ChunkStored", (hx(h), index)))
        if len(self.chunks[h]) == n_chunks(length):
            self.events.append(("LargeStored", (hx(h),)))

    def largeStored(self, h: bytes) -> bool:
        return h in self.begun and len(self.chunks[h]) == n_chunks(self.begun[h][0])

    def largeChunk(self, h: bytes, index: int) -> bytes:
        self.reads += 1
        c = self.chunks.get(h, {}).get(index)
        if c is None:
            raise StoreError("ChunkNotStored", index)
        return c

    def largeInfo(self, h: bytes) -> Tuple[int, int, int, int, bool]:
        """(length, nIn, nOut, chunks stored, stored); zeros for a hash never begun, nIn = nOut = 0 until
        chunk 0 is stored."""
        if h not in self.begun:
            return 0, 0, 0, 0, False
        n_in, n_out = self.header.get(h, (0, 0))
        return self.begun[h][0], n_in, n_out, len(self.chunks[h]), self.largeStored(h)


def store_file(store: LargeStore, data: bytes, order: Optional[Sequence[int]] = None) -> bytes:
    """Upload a whole file (anyone may do this): beginLarge, then putChunk for every chunk. Returns its hash."""
    lv = chunk_levels(data)
    h = nh2_from(len(data), lv[-1][0])
    store.beginLarge(h, len(data), lv[-1][0])
    chunks = split_chunks(data)
    for i in (order if order is not None else range(len(chunks))):
        store.putChunk(h, i, chunks[i], merkle_proof(lv, i))
    return h


def oracle_for(data: bytes) -> Tuple[LargeStore, bytes]:
    """A store holding exactly this file (a convenience for tests and vectors)."""
    lv = chunk_levels(data)
    h = nh2_from(len(data), lv[-1][0])
    store = LargeStore([h])
    store_file(store, data)
    return store, h


# ---------------------------------------------------------------- 4 prefix commitments

KIND_BITS, KIND_U32 = "bits", "u32"
PER_WORD = {KIND_BITS: 256, KIND_U32: 8}


def word_leaf(dom: int, k: int, word: bytes) -> bytes:
    return sha256(bytes([dom]) + u32(k) + word)


def make_word(values: Sequence[int], start: int, end: int, kind: str) -> bytes:
    w = bytearray(32)
    if kind == KIND_BITS:
        for i in range(start, end):
            if values[i]:
                o = i - start
                w[o >> 3] |= 1 << (o & 7)
    else:
        for i in range(start, end):
            o = 4 * (i - start)
            w[o:o + 4] = u32(values[i])
    return bytes(w)


def prefix_words(values: Sequence[int], n: int, kind: str) -> List[bytes]:
    per = PER_WORD[kind]
    return [make_word(values, s, min(s + per, n), kind) for s in range(0, n, per)]


def prefix_leaves(dom: int, values: Sequence[int], n: int, kind: str) -> List[bytes]:
    return [word_leaf(dom, k, w) for k, w in enumerate(prefix_words(values, n, kind))]


def prefix_root(dom: int, values: Sequence[int], n: int, kind: str = KIND_BITS) -> bytes:
    """Merkle root over ceil(n / perWord) words holding values[0:n]; unused slots of the last word are zero.
    The tree grows with n (it is not padded to the full signal count); n = 0 gives EMPTY (spec 4.2)."""
    if n == 0:
        return EMPTY
    return merkle_root(prefix_leaves(dom, values, n, kind))


def word_get(word: bytes, slot: int, kind: str) -> int:
    if kind == KIND_BITS:
        return (word[slot >> 3] >> (slot & 7)) & 1
    return int.from_bytes(word[4 * slot:4 * slot + 4], "big")


def _peak_heights(full: int) -> List[int]:
    return [b for b in range(full.bit_length() - 1, -1, -1) if (full >> b) & 1]


def fold_peaks(hashes: Sequence[bytes]) -> bytes:
    """Root of a tree (spec section 0) from its peaks (largest first): H(p1, H(p2, ... H(pk-1, pk)))."""
    acc = hashes[-1]
    for h in reversed(hashes[:-1]):
        acc = node_hash(h, acc)
    return acc


class Acc:
    """Append-only prefix accumulator. root() equals prefix_root(dom, values, count, kind)."""

    def __init__(self, dom: int, kind: str):
        self.dom, self.kind, self.per = dom, kind, PER_WORD[kind]
        self.full = 0
        self.stack: List[Tuple[int, bytes]] = []
        self.partial = bytearray(32)
        self.pcount = 0

    @property
    def count(self) -> int:
        return self.full * self.per + self.pcount

    def append(self, v: int) -> None:
        if self.kind == KIND_BITS:
            if v:
                self.partial[self.pcount >> 3] |= 1 << (self.pcount & 7)
        else:
            self.partial[4 * self.pcount:4 * self.pcount + 4] = u32(v)
        self.pcount += 1
        if self.pcount == self.per:
            self._push(word_leaf(self.dom, self.full, bytes(self.partial)))
            self.full += 1
            self.partial = bytearray(32)
            self.pcount = 0

    def _push(self, h: bytes) -> None:
        self.stack.append((0, h))
        while len(self.stack) >= 2 and self.stack[-1][0] == self.stack[-2][0]:
            lv, r = self.stack.pop()
            _, l = self.stack.pop()
            self.stack.append((lv + 1, node_hash(l, r)))

    def get(self, i: int) -> int:
        """Value at index i, only for i inside the partial word."""
        if not self.full * self.per <= i < self.count:
            raise Missing("value not in the partial word")
        return word_get(bytes(self.partial), i - self.full * self.per, self.kind)

    def root(self) -> bytes:
        hs = [h for _, h in self.stack]
        if self.pcount:
            hs.append(word_leaf(self.dom, self.full, bytes(self.partial)))
        return fold_peaks(hs) if hs else EMPTY

    def frontier(self) -> Tuple[List[bytes], Optional[bytes]]:
        """Append (right-frontier) proof: the peaks of the full words and the partial word."""
        return [h for _, h in self.stack], (bytes(self.partial) if self.pcount else None)

    @classmethod
    def from_values(cls, dom: int, kind: str, values: Sequence[int], n: int) -> "Acc":
        acc = cls(dom, kind)
        per = acc.per
        full = n // per
        for k in range(full):
            acc._push(word_leaf(dom, k, make_word(values, k * per, k * per + per, kind)))
        acc.full = full
        for i in range(full * per, n):
            acc.append(values[i])
        return acc

    @classmethod
    def from_frontier(cls, dom: int, kind: str, count: int, peaks: Sequence[bytes],
                      partial: Optional[bytes], expect_root: bytes) -> Optional["Acc"]:
        """Rebuild an accumulator for prefix length `count` from an append proof; None unless it matches."""
        acc = cls(dom, kind)
        full, pc = divmod(count, acc.per)
        heights = _peak_heights(full)
        if len(peaks) != len(heights) or any(len(p) != 32 for p in peaks):
            return None
        if (partial is None) != (pc == 0):
            return None
        if partial is not None:
            if len(partial) != 32:
                return None
            for s in range(pc, acc.per):  # unused slots must be zero
                if word_get(partial, s, kind):
                    return None
        acc.full, acc.pcount = full, pc
        acc.stack = list(zip(heights, peaks))
        if partial is not None:
            acc.partial = bytearray(partial)
        return acc if acc.root() == expect_root else None


def state_root(state: Sequence[int]) -> bytes:
    """stateRoot: prefix root of the latch state vector (file order), word leaves 0x05."""
    return prefix_root(DOM_STATE, state, len(state))


def out_root(outputs: Sequence[int]) -> bytes:
    """Root of the beat's output vector (word leaves 0x04, spec 4.3)."""
    return prefix_root(DOM_SIGNAL, outputs, len(outputs))


def io_next(io: bytes, out_root_: bytes) -> bytes:
    """ioHash_{t+1} = SHA-256(0x08 || ioHash_t || outRoot_t); ioHash_0 = EMPTY (spec 4.4)."""
    return sha256(bytes([DOM_IO]) + io + out_root_)


def input_leaf(t: int, input_bits: Sequence[int]) -> bytes:
    """inputLeaf(t) = SHA-256(0x0A || u64be(t) || SHA-256(packed input bits)), spec 4.4."""
    return sha256(bytes([DOM_INPUT]) + u64(t) + sha256(pack_bits(input_bits)))


def input_levels(inputs: Sequence[Sequence[int]]) -> List[List[bytes]]:
    return merkle_levels([input_leaf(t, x) for t, x in enumerate(inputs)])


def input_root(inputs: Sequence[Sequence[int]]) -> bytes:
    """inputRoot = tree(inputLeaf(0), ..., inputLeaf(T - 1))."""
    return input_levels(inputs)[-1][0]


def unpack_inputs(n_in: int, packed: bytes) -> List[int]:
    """The input bits of a revealed packed input vector; Invalid unless it has ceil(nIn/8) bytes and zero
    padding bits."""
    if len(packed) != (n_in + 7) // 8:
        raise Invalid("packed inputs have the wrong length")
    if n_in % 8 and packed[-1] >> (n_in % 8):
        raise Invalid("nonzero padding bits in packed inputs")
    return unpack_bits(packed, n_in)


# ---------------------------------------------------------------- 4b memory tree (spec 4.6)
#
# All RAM banks live in one perfect binary tree of height 24 (MEM_HEIGHT). Bank b, entry k (w bits, stride
# s = ram_stride(w)) occupies bits slot .. slot + w - 1 of word j, where bit = k * s, j = bit >> 8 and
# slot = bit & 255 (bit o of a word is bit o mod 8 of byte o / 8, as for bit words). Word j of bank b is leaf
# (b << 16) | j. A leaf is SHA-256(0x0B || word) (no index: its position is fixed by the path), nodes are
# SHA-256(0x01 || l || r). An all-zero subtree of height h has the constant hash ZERO_H[h]; the all-zero
# memory has root ZERO_MEM = ZERO_H[24], whatever the file.

ZERO_WORD = bytes(32)


def mem_leaf(word: bytes) -> bytes:
    return sha256(bytes([DOM_MEMWORD]) + word)


ZERO_H = [mem_leaf(ZERO_WORD)]
for _h in range(MEM_HEIGHT):
    ZERO_H.append(node_hash(ZERO_H[-1], ZERO_H[-1]))
ZERO_MEM = ZERO_H[MEM_HEIGHT]


def mem_pos(bank: int, a: int, w: int, addr: int) -> Tuple[int, int]:
    """(leaf position, slot) of entry addr of a bank with dimensions (a, w)."""
    bit = addr * ram_stride(w)
    return (bank << MEM_WORD_BITS) | (bit >> 8), bit & 255


def word_entry(word: bytes, slot: int, w: int) -> int:
    return sum(((word[(slot + j) >> 3] >> ((slot + j) & 7)) & 1) << j for j in range(w))


def word_patch(word: bytes, slot: int, w: int, value: int) -> bytes:
    b = bytearray(word)
    for j in range(w):
        o = slot + j
        if (value >> j) & 1:
            b[o >> 3] |= 1 << (o & 7)
        else:
            b[o >> 3] &= ~(1 << (o & 7)) & 0xFF
    return bytes(b)


def mem_path_root(word: bytes, pos: int, sibs: Sequence[bytes]) -> bytes:
    """Root of the memory tree from a leaf word at pos and its 24 siblings (leaf level first)."""
    if len(sibs) != MEM_HEIGHT or not 0 <= pos < 1 << MEM_HEIGHT:
        raise Missing("malformed memory proof")
    h = mem_leaf(word)
    for l in range(MEM_HEIGHT):
        h = node_hash(h, sibs[l]) if (pos >> l) & 1 == 0 else node_hash(sibs[l], h)
    return h


class MemTree:
    """Sparse model of the memory tree: only nodes that differ from the all-zero tree are stored."""

    def __init__(self):
        self.nodes: List[Dict[int, bytes]] = [dict() for _ in range(MEM_HEIGHT + 1)]
        self.words: Dict[int, bytes] = {}

    def node(self, lvl: int, i: int) -> bytes:
        return self.nodes[lvl].get(i, ZERO_H[lvl])

    def root(self) -> bytes:
        return self.node(MEM_HEIGHT, 0)

    def word(self, pos: int) -> bytes:
        return self.words.get(pos, ZERO_WORD)

    def proof(self, pos: int) -> List[bytes]:
        return [self.node(l, (pos >> l) ^ 1) for l in range(MEM_HEIGHT)]

    def set_word(self, pos: int, word: bytes) -> None:
        self.words[pos] = word
        h, i = mem_leaf(word), pos
        self.nodes[0][i] = h
        for l in range(MEM_HEIGHT):
            sib = self.node(l, i ^ 1)
            h = node_hash(h, sib) if i % 2 == 0 else node_hash(sib, h)
            i >>= 1
            self.nodes[l + 1][i] = h

    def set_entry(self, bank: int, a: int, w: int, addr: int, value: int) -> None:
        pos, slot = mem_pos(bank, a, w, addr)
        self.set_word(pos, word_patch(self.word(pos), slot, w, value))

    def copy(self) -> "MemTree":
        t = MemTree()
        t.nodes = [dict(d) for d in self.nodes]
        t.words = dict(self.words)
        return t

    @classmethod
    def from_mem(cls, nl: Netlist, mem: Optional[Mem]) -> "MemTree":
        t = cls()
        for bank, entries in sorted((mem or {}).items()):
            a, w = nl.banks[bank]
            for k, v in enumerate(entries):
                if v:
                    t.set_entry(bank, a, w, k, v)
        return t


def mem_root(nl: Netlist, mem: Optional[Mem]) -> bytes:
    return MemTree.from_mem(nl, mem).root()


def combine_state(latch_root: bytes, memory_root: bytes) -> bytes:
    """stateRoot of a file with the MEM flag after beat 0: SHA-256(0x0C || latchRoot || memRoot)."""
    return sha256(bytes([DOM_STATE2]) + latch_root + memory_root)


def full_state_root(nl: Netlist, state: Sequence[int], mem: Optional[Mem]) -> bytes:
    """stateRoot of a beat t >= 1 (beat 0 is always EMPTY): the latch prefix root, combined with the memory
    root for a file with the MEM flag."""
    lr = state_root(state)
    return combine_state(lr, mem_root(nl, mem)) if nl.has_mem else lr


def full_state_roots(nl: Netlist, states: Sequence[Sequence[int]], mems: Sequence[Optional[Mem]]) -> List[bytes]:
    return [EMPTY] + [full_state_root(nl, s, m) for s, m in zip(states[1:], mems[1:])]


# ---------------------------------------------------------------- 5 budgets and canonical segmentation

class Budget(NamedTuple):
    """Defaults: the RECOMMENDED budget of spec 5.1, chosen from the gas measured with the Solidity verifier
    (contracts/, test/GasVerify.t.sol)."""
    gates: int = 6000       # gate-equivalents: NAND 1, LATCH 1, ROM w + a
    ext_words: int = 256    # distinct externally read words (P_j words and stateRoot words)
    chunks: int = 16        # chunk cap: bounds the chunks the verifier reads (static count, see seg_cost_add)


DEFAULT_BUDGET = Budget()
TINY_BUDGET = Budget(16, 4, 2)


class SegTuple(NamedTuple):
    """seg_j = (byteOffset, firstSignal, latchOrdinal, P, D, M), spec 4.5: M is the memory root after the write
    ports before this boundary (ZERO_MEM in every tuple of a file without MEM, and then not hashed)."""
    byte_offset: int
    first_signal: int
    latch_ordinal: int
    p: bytes
    d: bytes
    m: bytes = ZERO_MEM

    def as_json(self, has_mem: bool = False) -> list:
        """5 elements for a file without MEM, 6 (with M) for a file with MEM, whatever the value of M."""
        base = [self.byte_offset, self.first_signal, self.latch_ordinal, hx(self.p), hx(self.d)]
        return base + [hx(self.m)] if has_mem else base


def chunk_set(start: int, end: int) -> set:
    return set(range(start // CHUNK, (end - 1) // CHUNK + 1)) if end > start else set()


@dataclass
class SegCost:
    gates: int = 0
    ext: set = field(default_factory=set)
    struct_chunks: set = field(default_factory=set)
    rom_chunks: int = 0

    @property
    def chunks(self) -> int:
        return len(self.struct_chunks) + self.rom_chunks

    def within(self, b: Budget) -> bool:
        return self.gates <= b.gates and len(self.ext) <= b.ext_words and self.chunks <= b.chunks

    def as_json(self) -> dict:
        return {"gates": self.gates, "extWords": len(self.ext), "chunks": self.chunks}


def record_ext_words(raw: RawRecord, first_signal: int, latch_ord: int) -> set:
    """External reads of a record in a segment starting at first_signal. Constants 0/1 are not reads
    (spec 5.2); signals >= first_signal are internal; a LATCH reads its state word. A RAM read or
    write port adds MEM_WEIGHT units ("M", offset, i), never shared with other records."""
    if raw.op == OP_LATCH:
        return {("S", latch_ord >> 8)}
    ext = {("P", r >> 8) for r in raw.refs if 2 <= r < first_signal}
    if raw.op in (OP_RAMR, OP_RAMW):
        ext |= {("M", raw.off, i) for i in range(MEM_WEIGHT)}
    return ext


def record_gates(raw: RawRecord) -> int:
    """Gate-equivalents: NAND, LATCH 1; ROM and ROM port w + a; RAM read port w + a; RAM write port 1 + a + w."""
    if raw.op in (OP_NAND, OP_LATCH):
        return 1
    return raw.w + raw.a + (raw.op == OP_RAMW)


def seg_cost_add(cost: SegCost, raw: RawRecord, first_signal: int, latch_ord: int) -> SegCost:
    """Static (value-independent) cost. Chunks: distinct chunks of all structural bytes, plus, per ROM,
    min(chunks its data region touches, 2) (spec 5.2: not deduplicated; an upper bound on the chunks read)."""
    g = record_gates(raw)
    rom = min(len(chunk_set(raw.ds, raw.ds + raw.dl)), 2) if raw.op in (OP_ROM, OP_ROMP) else 0
    return SegCost(cost.gates + g, cost.ext | record_ext_words(raw, first_signal, latch_ord),
                   cost.struct_chunks | chunk_set(raw.off, raw.struct_end), cost.rom_chunks + rom)


class Segment(NamedTuple):
    records: list           # [(RawRecord, first_out, latch_ord)]
    end_off: int
    end_signal: int
    end_latch: int
    stop: str               # "eof" or "budget"
    cost: SegCost
    next_record: Optional[RawRecord]


def canonical_segment(read: Callable[[int, int], bytes], file_len: int, off: int, first_signal: int,
                      latch_ord: int, budget: Budget) -> Segment:
    """Greedy: the first record is always included; then records are added while the cost stays within
    the budget. The segment is maximal: the next record would exceed the budget, or the file ends."""
    if off >= file_len:
        raise Invalid("no segment starts at the end of the file")
    cost, recs, s, l, o = SegCost(), [], first_signal, latch_ord, off
    nxt_rec, stop = None, "eof"
    while o < file_len:
        raw = parse_record(read, o, file_len)
        new = seg_cost_add(cost, raw, first_signal, l)
        if recs and not new.within(budget):
            nxt_rec, stop = raw, "budget"
            break
        recs.append((raw, s, l))
        cost, s, o = new, s + raw.n_out, raw.end
        l += raw.op == OP_LATCH
    return Segment(recs, o, s, l, stop, cost, nxt_rec)


def _file_reader(data: bytes) -> Callable[[int, int], bytes]:
    return lambda o, n: data[o:o + n]


def greedy_boundaries(nl: Netlist, start: Tuple[int, int, int], budget: Budget) -> List[Tuple[int, int, int]]:
    read, flen = _file_reader(nl.data), len(nl.data)
    b = [start]
    while b[-1][0] < flen:
        seg = canonical_segment(read, flen, *b[-1], budget)
        b.append((seg.end_off, seg.end_signal, seg.end_latch))
    return b


def segment_boundaries(f, budget: Budget = DEFAULT_BUDGET) -> List[Tuple[int, int, int]]:
    """(byteOffset, firstSignal, latchOrdinal) of seg_0 .. seg_m. Static: the same in every beat."""
    nl = _as_netlist(f)
    return greedy_boundaries(nl, (HEADER_LEN, 2 + nl.n_in, 0), budget)


def initial_tuple(n_in: int, inputs: Sequence[int], m: bytes = ZERO_MEM) -> SegTuple:
    """seg_0 = (16, 2 + nIn, 0, P(2 + nIn), D = EMPTY, M = memRoot_t of the beat; ZERO_MEM without MEM)."""
    return SegTuple(HEADER_LEN, 2 + n_in, 0, prefix_root(DOM_SIGNAL, [0, 1] + list(inputs), 2 + n_in), EMPTY, m)


def tuples_for_boundaries(nl: Netlist, V: Sequence[int], bounds, mem_t: Optional[Mem] = None,
                          events: Sequence[tuple] = ()) -> List[SegTuple]:
    """Segment tuples at the given boundaries. For a MEM file, M at each boundary is the root of mem_t with the
    events (from evaluate_full, possibly a cheater's) of the records before that boundary applied."""
    accp, accd, out = Acc(DOM_SIGNAL, KIND_BITS), Acc(DOM_LATCHD, KIND_U32), []
    tree = MemTree.from_mem(nl, mem_t) if nl.has_mem else None
    ev = sorted(events, key=lambda e: e[0])   # stable: keeps file order within one record
    ei = 0
    for off, sig, lat in bounds:
        while accp.count < sig:
            accp.append(V[accp.count])
        while accd.count < lat:
            accd.append(nl.latch_d[accd.count])
        m = ZERO_MEM
        if tree is not None:
            while ei < len(ev) and ev[ei][0] < off:
                _, bank, addr, val = ev[ei]
                a, w = nl.banks[bank]
                tree.set_entry(bank, a, w, addr, val)
                ei += 1
            m = tree.root()
        out.append(SegTuple(off, sig, lat, accp.root(), accd.root(), m))
    return out


def segment_tuples(f, V: Sequence[int], budget: Budget = DEFAULT_BUDGET, mem_t: Optional[Mem] = None,
                   events: Sequence[tuple] = ()) -> List[SegTuple]:
    nl = _as_netlist(f)
    return tuples_for_boundaries(nl, V, segment_boundaries(nl, budget), mem_t, events)


# ---------------------------------------------------------------- 6 segment witnesses and verify_segment

@dataclass
class SegWitness:
    """Witness of one segment step (spec 6.1). It carries no file bytes: the verifier reads the file only
    through the chunk oracle bound to netlistHash2 (spec section 6), so a witness holds tree proofs only."""
    p_peaks: List[bytes]
    p_partial: Optional[bytes]
    p_words: Dict[int, bytes]
    p_proof: List[bytes]
    d_peaks: List[bytes]
    d_partial: Optional[bytes]
    s_size: int                 # number of state words; bound by no tuple (spec Rationale); 0 if stateRoot = EMPTY
    s_words: Dict[int, bytes]
    s_proof: List[bytes]
    # memory proofs (spec 6.1; both empty for a segment without RAM accesses: then there is no extension)
    mem_reads: List[Tuple[bytes, List[bytes]]] = field(default_factory=list)    # (word, 24 siblings) per read
    mem_writes: List[Tuple[bytes, List[bytes]]] = field(default_factory=list)   # (old word, 24 siblings) per write


LAST_READ = {"chunks": 0}       # distinct chunks the last verifier call read from the oracle (measurements)


def oracle_file_len(oracle, nh2: bytes) -> Optional[int]:
    """fileLen of netlistHash2 from the chunk oracle, or None unless the file is completely stored."""
    length, _, _, _, stored = oracle.largeInfo(nh2)
    return length if stored else None


class OracleReader:
    """read(offset, n) over the chunks of netlistHash2 in a chunk oracle (a store with largeStored true).
    Records the distinct chunks read."""

    def __init__(self, oracle, nh2: bytes, file_len: int):
        self.oracle, self.nh2, self.file_len = oracle, nh2, file_len
        self.cache: Dict[int, bytes] = {}

    def chunk(self, i: int) -> bytes:
        if i not in self.cache:
            n = n_chunks(self.file_len)
            c = self.oracle.largeChunk(self.nh2, i)
            if not 0 <= i < n or len(c) != (CHUNK if i < n - 1 else self.file_len - CHUNK * (n - 1)):
                raise Missing(f"oracle returned a chunk {i} of the wrong length")
            self.cache[i] = c
        return self.cache[i]

    def __call__(self, o: int, n: int) -> bytes:
        if o < 0 or o + n > self.file_len:
            raise Missing("read beyond the end of the file")
        out = bytearray()
        while n > 0:
            ci, co = divmod(o, CHUNK)
            part = self.chunk(ci)[co:co + n]
            out += part
            o += len(part)
            n -= len(part)
        return bytes(out)


def _rom_addressed_range(raw: RawRecord, addr: int) -> Tuple[int, int]:
    base = addr * raw.w
    return raw.ds + (base >> 3), raw.ds + ((base + raw.w - 1) >> 3) + 1


def segment_chunks(f, V: Sequence[int], a: SegTuple, end_off: int) -> set:
    """The chunks a verifier reads for the step from a to end_off (structural bytes of the segment and of the
    next record, and the addressed ROM bytes); informative, for measurements."""
    nl = _as_netlist(f)
    data, flen = nl.data, len(nl.data)
    read = _file_reader(data)
    need: set = set()
    o = a.byte_offset
    while o < end_off:
        raw = parse_record(read, o, flen)
        need |= chunk_set(raw.off, raw.struct_end)
        if raw.op in (OP_ROM, OP_ROMP):
            need |= chunk_set(*_rom_addressed_range(raw, sum(V[r] << i for i, r in enumerate(raw.refs))))
        o = raw.end
    if o < flen:
        raw = parse_record(read, o, flen)
        need |= chunk_set(raw.off, raw.struct_end)
    return need


def build_seg_witness(f, V: Sequence[int], state: Sequence[int], a: SegTuple, end_off: int,
                      sroot: Optional[bytes] = None, mem_t: Optional[Mem] = None,
                      events: Sequence[tuple] = ()) -> SegWitness:
    """Witness for the segment from tuple a to the record boundary end_off, built from the prover's own
    signal values V (a cheater's V gives a witness that fails). sroot is the beat's agreed latch root, the
    latchRoot argument of verify_segment (default: state_root(state)); for sroot = EMPTY (the initial all-zero
    state, spec 4.3) the witness has no state words. For a file with MEM, mem_t is the memory at the start of
    the beat and events the memory changes of the beat (from evaluate_full); the witness then carries one
    memory proof per RAM read (none if memRoot_t = ZERO_MEM) and one per applied write."""
    nl = _as_netlist(f)
    data, flen = nl.data, len(nl.data)
    read = _file_reader(data)
    p_idx: set = set()
    s_idx: set = set()
    o, l = a.byte_offset, a.latch_ordinal
    while o < end_off:
        raw = parse_record(read, o, flen)
        if raw.op == OP_LATCH:
            s_idx.add(l >> 8)
        else:
            p_idx |= {r >> 8 for r in raw.refs if 2 <= r < a.first_signal}
        l += raw.op == OP_LATCH
        o = raw.end
    accp = Acc.from_values(DOM_SIGNAL, KIND_BITS, V, a.first_signal)
    p_peaks, p_partial = accp.frontier()
    if p_partial is not None:
        p_idx.discard(a.first_signal >> 8)
    p_words, p_proof = {}, []
    if p_idx:
        words = prefix_words(V, a.first_signal, KIND_BITS)
        lv = merkle_levels([word_leaf(DOM_SIGNAL, k, w) for k, w in enumerate(words)])
        p_words = {k: words[k] for k in sorted(p_idx)}
        p_proof = multiproof(lv, sorted(p_idx))
    accd = Acc.from_values(DOM_LATCHD, KIND_U32, nl.latch_d, a.latch_ordinal)
    d_peaks, d_partial = accd.frontier()
    if sroot is None:
        sroot = state_root(state)
    s_words, s_proof, s_size = {}, [], 0
    if nl.n_latch and sroot != EMPTY:
        swords = prefix_words(state, nl.n_latch, KIND_BITS)
        s_size = len(swords)
        if s_idx:
            lv = merkle_levels([word_leaf(DOM_STATE, k, w) for k, w in enumerate(swords)])
            s_words = {k: swords[k] for k in sorted(s_idx)}
            s_proof = multiproof(lv, sorted(s_idx))
    w = SegWitness(p_peaks, p_partial, p_words, p_proof, d_peaks, d_partial, s_size, s_words, s_proof)
    if nl.has_mem:
        _add_mem_witness(nl, w, V, state, a, end_off, sroot, mem_t, events)
    return w


def _add_mem_witness(nl: Netlist, w: SegWitness, V, state, a: SegTuple, end_off: int, sroot: bytes,
                     mem_t: Optional[Mem], events: Sequence[tuple]) -> None:
    """Memory proofs (spec 6.1): one per RAM read against memRoot_t, unless memRoot_t = ZERO_MEM, and one per
    applied write against the running root, which starts at a.M."""
    read = _file_reader(nl.data)
    tree_t = MemTree.from_mem(nl, mem_t)
    zero_mem = tree_t.root() == ZERO_MEM
    ev = sorted(events, key=lambda e: e[0])
    running = tree_t.copy()

    def apply(pred):
        for off, bank, addr, val in ev:
            if pred(off):
                an, wn = nl.banks[bank]
                running.set_entry(bank, an, wn, addr, val)

    apply(lambda off: off < a.byte_offset)
    o = a.byte_offset
    while o < end_off:
        raw = parse_record(read, o, len(nl.data))
        if raw.op == OP_RAMR and not zero_mem:
            addr = sum(V[r] << i for i, r in enumerate(raw.refs))
            pos, _ = mem_pos(raw.bank, raw.a, raw.w, addr)
            w.mem_reads.append((tree_t.word(pos), tree_t.proof(pos)))
        elif raw.op == OP_RAMW:
            if V[raw.refs[0]]:
                addr = sum(V[r] << i for i, r in enumerate(raw.refs[1:1 + raw.a]))
                pos, _ = mem_pos(raw.bank, raw.a, raw.w, addr)
                w.mem_writes.append((running.word(pos), running.proof(pos)))
            apply(lambda off, ro=raw.off: off == ro)
        o = raw.end


def _check_words(dom: int, root: bytes, size: int, words: Dict[int, bytes], proof) -> bool:
    if not words:
        return not proof
    if any(len(x) != 32 for x in words.values()):
        return False
    return multiverify(root, size, {k: word_leaf(dom, k, x) for k, x in words.items()}, proof)


VERIFY_CALLS = {"segment": 0, "beat_end": 0}   # call counter (tests assert one call per dispute)


def verify_segment(oracle, netlist_hash2_: bytes, state_root_: bytes, a: SegTuple, b: SegTuple, w,
                   budget: Budget = DEFAULT_BUDGET, mem_root: bytes = None) -> bool:
    """verify_segment(netlistHash2, latchRoot, memRoot, a, b, witness, budget) of spec 6.1: check that b is the
    canonical successor of the agreed tuple a in a beat whose agreed latch root is state_root_ (the stateRoot
    for a file without MEM, the latchRoot of the opening of stateRoot_t for a file with MEM) and whose memory
    root is mem_root (default ZERO_MEM: files without MEM, and beat 0). Reads the file only through the chunk
    oracle bound to netlist_hash2_ (largeInfo / largeChunk of a store); w is a SegWitness or its encoding
    (spec 6.3). Returns False on any failure."""
    VERIFY_CALLS["segment"] += 1
    LAST_READ["chunks"] = 0
    try:
        if isinstance(w, (bytes, bytearray)):
            w = parse_seg_witness(bytes(w))
        return _verify_segment(oracle, netlist_hash2_, state_root_, ZERO_MEM if mem_root is None else mem_root,
                               a, b, w, budget)
    except (Missing, Invalid, StoreError, KeyError, IndexError, ValueError, TypeError):
        return False


def _verify_segment(oracle, nh2: bytes, sroot: bytes, mem_t: bytes, a: SegTuple, b: SegTuple, w: SegWitness,
                    budget: Budget) -> bool:
    file_len = oracle_file_len(oracle, nh2)
    if file_len is None or file_len > MAX_FILE:
        return False
    if not HEADER_LEN <= a.byte_offset < file_len:
        return False
    fs = a.first_signal
    accp = Acc.from_frontier(DOM_SIGNAL, KIND_BITS, fs, w.p_peaks, w.p_partial, a.p)
    accd = Acc.from_frontier(DOM_LATCHD, KIND_U32, a.latch_ordinal, w.d_peaks, w.d_partial, a.d)
    if accp is None or accd is None:
        return False
    n_pw = (fs + 255) // 256
    if w.p_partial is not None and (fs >> 8) in w.p_words:
        return False
    if not _check_words(DOM_SIGNAL, a.p, n_pw, w.p_words, w.p_proof):
        return False
    zero_state = sroot == EMPTY        # the all-zero state of any length (spec 4.3): no state words
    # The memory root is an argument, like the latch root: the game takes both from the opening of the agreed
    # stateRoot_t (spec 7.4), so the verifier never infers the form of a state root from the witness.
    zero_mem = mem_t == ZERO_MEM       # the all-zero memory: RAM reads give 0 and consume no proof
    if len(mem_t) != 32:
        return False
    if zero_state:
        if w.s_size or w.s_words or w.s_proof:
            return False
    elif not _check_words(DOM_STATE, sroot, w.s_size, w.s_words, w.s_proof):
        return False
    read = OracleReader(oracle, nh2, file_len)
    try:
        seg = canonical_segment(read, file_len, a.byte_offset, fs, a.latch_ordinal, budget)
        # canonical_segment has parsed the next record's structural bytes too (maximality)
        partial_k = fs >> 8 if w.p_partial is not None else -1
        local: List[int] = []
        mroot = a.m                    # running memory root: after the writes of the records before this one
        ri = wi = 0

        def val(x: int) -> int:
            if x < 2:
                return x
            if x >= fs:
                return local[x - fs]          # IndexError (forward reference) -> False
            k = x >> 8
            word = w.p_partial if k == partial_k else w.p_words[k]
            return word_get(word, x & 255, KIND_BITS)

        for raw, s, l in seg.records:
            if raw.op == OP_NAND:
                vs = [1 - (val(raw.refs[0]) & val(raw.refs[1]))]
            elif raw.op == OP_LATCH:
                vs = [0 if zero_state else word_get(w.s_words[l >> 8], l & 255, KIND_BITS)]
                accd.append(raw.refs[0])
            elif raw.op in (OP_ROM, OP_ROMP):
                addr = 0
                for i, r in enumerate(raw.refs):
                    addr |= val(r) << i
                lo, hi = _rom_addressed_range(raw, addr)
                got = read(lo, hi - lo)
                base = (addr * raw.w) & 7
                vs = [(got[(base + j) >> 3] >> ((base + j) & 7)) & 1 for j in range(raw.w)]
            elif raw.op == OP_RAMR:
                addr = sum(val(r) << i for i, r in enumerate(raw.refs))
                if zero_mem:
                    vs = [0] * raw.w
                else:
                    word, sibs = w.mem_reads[ri]
                    ri += 1
                    pos, slot = mem_pos(raw.bank, raw.a, raw.w, addr)
                    if len(word) != 32 or mem_path_root(word, pos, sibs) != mem_t:
                        return False
                    e = word_entry(word, slot, raw.w)
                    vs = [(e >> j) & 1 for j in range(raw.w)]
            else:  # OP_RAMW: creates no signals; applies the write to the running memory root
                vs = []
                if val(raw.refs[0]):
                    addr = sum(val(r) << i for i, r in enumerate(raw.refs[1:1 + raw.a]))
                    wd = sum(val(r) << j for j, r in enumerate(raw.refs[1 + raw.a:]))
                    old, sibs = w.mem_writes[wi]
                    wi += 1
                    pos, slot = mem_pos(raw.bank, raw.a, raw.w, addr)
                    if len(old) != 32 or mem_path_root(old, pos, sibs) != mroot:
                        return False
                    mroot = mem_path_root(word_patch(old, slot, raw.w, wd), pos, sibs)
            for v in vs:
                local.append(v)
                accp.append(v)
    finally:
        LAST_READ["chunks"] = len(read.cache)
    if ri != len(w.mem_reads) or wi != len(w.mem_writes):
        return False
    return (b.byte_offset == seg.end_off and b.first_signal == seg.end_signal
            and b.latch_ordinal == seg.end_latch and b.p == accp.root() and b.d == accd.root()
            and b.m == mroot)


# ---------------------------------------------------------------- 7 beat-end segments

OUT_PER_SEG = 256
LATCH_PER_SEG = 256


class EndTuple(NamedTuple):
    """Beat-end tuple: (outOrdinal, R) for outputs, (latchOrdinal, R) for the new state."""
    ordinal: int
    root: bytes

    def as_json(self) -> list:
        return [self.ordinal, hx(self.root)]


def out_tuples(outputs: Sequence[int]) -> List[EndTuple]:
    n = len(outputs)
    acc, res = Acc(DOM_SIGNAL, KIND_BITS), [EndTuple(0, EMPTY)]
    for k in range(0, n, OUT_PER_SEG):
        for i in range(k, min(k + OUT_PER_SEG, n)):
            acc.append(outputs[i])
        res.append(EndTuple(acc.count, acc.root()))
    return res


def state_tuples(new_state: Sequence[int]) -> List[EndTuple]:
    n = len(new_state)
    acc, res = Acc(DOM_STATE, KIND_BITS), [EndTuple(0, EMPTY)]
    for k in range(0, n, LATCH_PER_SEG):
        for i in range(k, min(k + LATCH_PER_SEG, n)):
            acc.append(new_state[i])
        res.append(EndTuple(acc.count, acc.root()))
    return res


@dataclass
class EndWitness:
    """Witness of one beat-end step (spec 6.2): tree proofs only."""
    kind: str                    # "out" or "state"
    p_words: Dict[int, bytes]
    p_proof: List[bytes]
    d_words: Dict[int, bytes]
    d_proof: List[bytes]
    r_peaks: List[bytes]         # frontier of the output / new-state prefix tree (segments are word aligned)


def build_out_witness(f, V: Sequence[int], outputs: Sequence[int], k: int) -> EndWitness:
    nl = _as_netlist(f)
    S, n_out = nl.n_signals, nl.n_out
    lo, hi = k * OUT_PER_SEG, min(k * OUT_PER_SEG + OUT_PER_SEG, n_out)
    idx = sorted({(S - n_out + i) >> 8 for i in range(lo, hi)})
    words = prefix_words(V, S, KIND_BITS)
    lv = merkle_levels([word_leaf(DOM_SIGNAL, j, x) for j, x in enumerate(words)])
    acc = Acc.from_values(DOM_SIGNAL, KIND_BITS, outputs, lo)
    return EndWitness("out", {j: words[j] for j in idx}, multiproof(lv, idx), {}, [], acc.frontier()[0])


def build_state_witness(f, V: Sequence[int], new_state: Sequence[int], k: int) -> EndWitness:
    nl = _as_netlist(f)
    S, L = nl.n_signals, nl.n_latch
    lo, hi = k * LATCH_PER_SEG, min(k * LATCH_PER_SEG + LATCH_PER_SEG, L)
    didx = sorted({l >> 3 for l in range(lo, hi)})
    dwords = prefix_words(nl.latch_d, L, KIND_U32)
    dlv = merkle_levels([word_leaf(DOM_LATCHD, j, x) for j, x in enumerate(dwords)])
    pidx = sorted({nl.latch_d[l] >> 8 for l in range(lo, hi) if nl.latch_d[l] >= 2})
    words = prefix_words(V, S, KIND_BITS)
    plv = merkle_levels([word_leaf(DOM_SIGNAL, j, x) for j, x in enumerate(words)])
    acc = Acc.from_values(DOM_STATE, KIND_BITS, new_state, lo)
    return EndWitness("state", {j: words[j] for j in pidx}, multiproof(plv, pidx) if pidx else [],
                      {j: dwords[j] for j in didx}, multiproof(dlv, didx), acc.frontier()[0])


def verify_beat_end(oracle, netlist_hash2_: bytes, n_out: int, seg_m: SegTuple, a: EndTuple, b: EndTuple,
                    w) -> bool:
    """Check one beat-end segment: b is the successor of the agreed tuple a, given the agreed final segment
    tuple seg_m (whose P is P(S) and whose D is the full latch d-table root) and the file's nOut (a public
    parameter of the claim, largeInfo of the store). The oracle supplies only fileLen."""
    VERIFY_CALLS["beat_end"] += 1
    try:
        if isinstance(w, (bytes, bytearray)):
            w = parse_end_witness(bytes(w))
        return _verify_beat_end(oracle, netlist_hash2_, n_out, seg_m, a, b, w)
    except (Missing, Invalid, StoreError, KeyError, IndexError, ValueError, TypeError):
        return False


def _verify_beat_end(oracle, nh2: bytes, n_out: int, seg_m: SegTuple, a: EndTuple, b: EndTuple,
                     w: EndWitness) -> bool:
    file_len = oracle_file_len(oracle, nh2)
    if file_len is None or seg_m.byte_offset != file_len:
        return False
    S = seg_m.first_signal
    if not _check_words(DOM_SIGNAL, seg_m.p, (S + 255) // 256, w.p_words, w.p_proof):
        return False

    def val(x: int) -> int:
        if x < 2:
            return x
        if x >= S:
            raise Missing("signal beyond P_m")
        return word_get(w.p_words[x >> 8], x & 255, KIND_BITS)

    if w.kind == "out":
        if w.d_words or w.d_proof:
            return False
        if not 1 <= n_out <= S - 2:
            return False
        total, dom = n_out, DOM_SIGNAL
    elif w.kind == "state":
        total, dom = seg_m.latch_ordinal, DOM_STATE
        if not _check_words(DOM_LATCHD, seg_m.d, (total + 7) // 8, w.d_words, w.d_proof):
            return False
    else:
        return False
    if a.ordinal % 256 or not 0 <= a.ordinal < total:
        return False
    acc = Acc.from_frontier(dom, KIND_BITS, a.ordinal, w.r_peaks, None, a.root)
    if acc is None:
        return False
    hi = min(a.ordinal + 256, total)
    for i in range(a.ordinal, hi):
        if w.kind == "out":
            acc.append(val(S - n_out + i))
        else:
            acc.append(val(word_get(w.d_words[i >> 3], i & 7, KIND_U32)))
    return b.ordinal == hi and b.root == acc.root()


# ---------------------------------------------------------------- 8 checkpoints, tuple leaves

def checkpoint_leaf(t: int, state_root_: bytes, io: bytes) -> bytes:
    """SHA-256(0x06 || u64be(t) || stateRoot_t || ioHash_t)."""
    return sha256(bytes([DOM_CHECKPOINT]) + u64(t) + state_root_ + io)


INITIAL_LEAF = checkpoint_leaf(0, EMPTY, EMPTY)   # stateRoot_0 = EMPTY (all-zero state), io_0 = EMPTY


def checkpoint_times(T: int, K: int) -> List[int]:
    """Checkpoints at t = 0, K, 2K, ... and always at T (spec 7.1)."""
    return sorted(set(range(0, T, K)) | {T})


def seg_tuple_leaf(j: int, s: SegTuple, has_mem: bool = False) -> bytes:
    """segLeaf (spec 4.5); for a file with the MEM flag, M is appended to the preimage."""
    return sha256(bytes([DOM_TUPLE, 0]) + u32(j) + u64(s.byte_offset) + u32(s.first_signal)
                  + u32(s.latch_ordinal) + s.p + s.d + (s.m if has_mem else b""))


def end_tuple_leaf(kind: str, k: int, e: EndTuple) -> bytes:
    return sha256(bytes([DOM_TUPLE, 1 if kind == "out" else 2]) + u32(k) + u32(e.ordinal) + e.root)


def beat_state_roots(states: Sequence[Sequence[int]]) -> List[bytes]:
    """stateRoot_t of a run from the all-zero state: EMPTY at t = 0, prefix roots afterwards (spec 4.3)."""
    return [EMPTY] + [state_root(s) for s in states[1:]]


# ---------------------------------------------------------------- 9 witness encoding (spec 6.3) and bounds

def _ser_hashes(hs) -> bytes:
    return u16(len(hs)) + b"".join(hs)


def _ser_words(ws: Dict[int, bytes]) -> bytes:
    return u16(len(ws)) + b"".join(u32(k) + ws[k] for k in sorted(ws))


def _ser_frontier(peaks, partial) -> bytes:
    return u8(len(peaks)) + b"".join(peaks) + (b"\x01" + partial if partial is not None else b"\x00")


def serialize_seg_witness(w: SegWitness) -> bytes:
    out = _ser_frontier(w.p_peaks, w.p_partial) + _ser_words(w.p_words) + _ser_hashes(w.p_proof)
    out += _ser_frontier(w.d_peaks, w.d_partial)
    out += u32(w.s_size) + _ser_words(w.s_words) + _ser_hashes(w.s_proof)
    if w.mem_reads or w.mem_writes:      # memory extension (spec 6.3), absent when both lists are empty
        for lst in (w.mem_reads, w.mem_writes):
            out += u16(len(lst))
            for word, sibs in lst:
                mask = sum(1 << l for l in range(MEM_HEIGHT) if sibs[l] == ZERO_H[l])
                out += word + u32(mask) + b"".join(sibs[l] for l in range(MEM_HEIGHT) if not (mask >> l) & 1)
    return out


def serialize_end_witness(w: EndWitness) -> bytes:
    out = b"\x01" if w.kind == "out" else b"\x02"
    out += _ser_words(w.p_words) + _ser_hashes(w.p_proof) + _ser_words(w.d_words) + _ser_hashes(w.d_proof)
    out += u8(len(w.r_peaks)) + b"".join(w.r_peaks)
    return out


class _Parser:
    def __init__(self, data: bytes):
        self.d, self.p = data, 0

    def take(self, n: int) -> bytes:
        if self.p + n > len(self.d):
            raise Invalid("witness truncated")
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

    def uint(self, n: int) -> int:
        return int.from_bytes(self.take(n), "big")

    def hashes(self, count_bytes: int) -> List[bytes]:
        return [self.take(32) for _ in range(self.uint(count_bytes))]

    def words(self) -> Dict[int, bytes]:
        out: Dict[int, bytes] = {}
        last = -1
        for _ in range(self.uint(2)):
            k = self.uint(4)
            if k <= last:
                raise Invalid("word indices not strictly increasing")
            out[k] = self.take(32)
            last = k
        return out

    def frontier(self) -> Tuple[List[bytes], Optional[bytes]]:
        peaks = self.hashes(1)
        flag = self.uint(1)
        if flag not in (0, 1):
            raise Invalid("bad partial-word flag")
        return peaks, (self.take(32) if flag else None)

    def end(self) -> None:
        if self.p != len(self.d):
            raise Invalid("trailing bytes in witness")


def parse_seg_witness(data: bytes) -> SegWitness:
    """Segment witness encoding of spec 6.3; raises Invalid on any malformation (the verifier then fails)."""
    ps = _Parser(data)
    p_peaks, p_partial = ps.frontier()
    p_words, p_proof = ps.words(), ps.hashes(2)
    d_peaks, d_partial = ps.frontier()
    s_size = ps.uint(4)
    s_words, s_proof = ps.words(), ps.hashes(2)
    w = SegWitness(p_peaks, p_partial, p_words, p_proof, d_peaks, d_partial, s_size, s_words, s_proof)
    if ps.p < len(ps.d):                     # memory extension (spec 6.3)
        for lst in (w.mem_reads, w.mem_writes):
            for _ in range(ps.uint(2)):
                word, mask = ps.take(32), ps.uint(4)
                if mask >> MEM_HEIGHT:
                    raise Invalid("bad zero-sibling mask")
                sibs = [ZERO_H[l] if (mask >> l) & 1 else ps.take(32) for l in range(MEM_HEIGHT)]
                if any(not (mask >> l) & 1 and sibs[l] == ZERO_H[l] for l in range(MEM_HEIGHT)):
                    raise Invalid("a zero sibling must be omitted (non-canonical)")
                lst.append((word, sibs))
        if not w.mem_reads and not w.mem_writes:
            raise Invalid("empty memory extension (non-canonical)")
    ps.end()
    return w


def parse_end_witness(data: bytes) -> EndWitness:
    """Beat-end witness encoding of spec 6.3; raises Invalid on any malformation."""
    ps = _Parser(data)
    kind = {1: "out", 2: "state"}.get(ps.uint(1))
    if kind is None:
        raise Invalid("bad beat-end witness kind")
    p_words, p_proof = ps.words(), ps.hashes(2)
    d_words, d_proof = ps.words(), ps.hashes(2)
    peaks = ps.hashes(1)
    ps.end()
    return EndWitness(kind, p_words, p_proof, d_words, d_proof, peaks)


def multiproof_bound(k: int, depth: int) -> int:
    """Most sibling hashes a multiproof (reference format) for k leaves of a tree of depth `depth` can have.
    At level l with c_l known nodes it adds 2*c_{l+1} - c_l hashes; summing gives
    sum_{l=1}^{depth-1} c_l + 2 - k with c_l <= min(k, 2^(depth-l))."""
    if k <= 0 or depth <= 0:
        return 0
    return sum(min(k, 1 << (depth - l)) for l in range(1, depth)) + 2 - k


SIGNAL_WORD_DEPTH = 16          # ceil(2^24 / 256) = 2^16 signal or state words
DTABLE_DEPTH = 21               # ceil(2^24 / 8) = 2^21 d-table words


def seg_witness_bound(budget: Budget = DEFAULT_BUDGET) -> int:
    """Upper bound, in bytes of the spec 6.3 encoding, of any segment witness an honest prover needs under `budget`:
    P append proof (at most 16 peaks and a partial word), D append proof (at most 21 peaks and a partial word),
    and kP + kS <= max(extWords, 20) proven P and state words in trees of at most 2^16 words. The 20: the first
    record of a segment is always included (spec 5.3), whatever the budget, and reads at most 20 words (a ROM
    with a = 20); every later record keeps the segment within extWords."""
    fixed = (1 + 16 * 32 + 1 + 32) + (1 + 21 * 32 + 1 + 32) + 2 + 2 + 4 + 2 + 2
    best = 0
    e = max(budget.ext_words, ROM_MAX_A)
    for kp in range(e + 1):
        for ks in (e - kp,):
            v = 36 * (kp + ks) + 32 * (multiproof_bound(kp, SIGNAL_WORD_DEPTH)
                                       + multiproof_bound(ks, SIGNAL_WORD_DEPTH))
            best = max(best, v)
    return fixed + best


def end_witness_bound() -> int:
    """Upper bound, in bytes of the spec 6.3 encoding, of a beat-end witness: output steps read at most 2 P words and
    have at most 8 peaks; state steps read at most 256 P words and 32 D words and have at most 16 peaks."""
    out = 1 + 2 + 2 * 36 + 2 + 32 * multiproof_bound(2, SIGNAL_WORD_DEPTH) + 2 + 2 + 1 + 8 * 32
    st = (1 + 2 + 256 * 36 + 2 + 32 * multiproof_bound(256, SIGNAL_WORD_DEPTH)
          + 2 + 32 * 36 + 2 + 32 * multiproof_bound(32, DTABLE_DEPTH) + 1 + 16 * 32)
    return max(out, st)


WITNESS_CAP = 98304             # 96 KiB: the cap a game MUST accept (spec 6.3), above both bounds


def witness_breakdown(w: SegWitness) -> dict:
    """Counts and bytes of a segment witness by part (for the size measurements)."""
    return {
        "pWords": len(w.p_words), "pProofHashes": len(w.p_proof),
        "sWords": len(w.s_words), "sProofHashes": len(w.s_proof),
        "frontierHashes": len(w.p_peaks) + len(w.d_peaks), "total": len(serialize_seg_witness(w)),
    }


# ---------------------------------------------------------------- witness bound of files with RAM ports

MEM_ACCESS_MAX_BYTES = 32 + 4 + 32 * MEM_HEIGHT          # word, zero-sibling mask, 24 siblings (no zero sibling)
MEM_EXT_HEADER = 2 + 2                                   # the two counts of the memory extension
RAMW_MAX_REFS = 1 + ROM_MAX_A + ROM_MAX_W                # 277: a lone write port's distinct P words


def seg_witness_bound_ram(budget: Budget = DEFAULT_BUDGET) -> int:
    """Upper bound of a segment witness of a file with RAM ports (spec 6.3). Within the budget,
    kP + kS + MEM_WEIGHT * kM <= extWords. A segment whose first record alone exceeds the budget is that record
    and nothing else: a write port reads at most 277 P words and makes 1 memory access (a ROM, ROM port or RAM
    read port at most 20 words and at most 1 access). The memory part, with its two counts (MEM_EXT_HEADER), is
    present only when kM >= 1; with kM = 0 the bound is that of a file without RAM ports. Under the default budget
    every kM >= 1 gives less, so the bound is the same 84,208 bytes."""
    fixed = (1 + 16 * 32 + 1 + 32) + (1 + 21 * 32 + 1 + 32) + 2 + 2 + 4 + 2 + 2

    def words(k: int) -> int:
        return 36 * k + 32 * multiproof_bound(k, SIGNAL_WORD_DEPTH)

    best = 0
    e = budget.ext_words
    for km in range(e // MEM_WEIGHT + 1):
        rest = e - MEM_WEIGHT * km
        mem = km * MEM_ACCESS_MAX_BYTES + (MEM_EXT_HEADER if km else 0)
        for kp in range(rest + 1):
            best = max(best, mem + words(kp) + words(rest - kp))
    lone = words(RAMW_MAX_REFS) + MEM_ACCESS_MAX_BYTES + MEM_EXT_HEADER
    return fixed + max(best, lone, words(ROM_MAX_A) + MEM_ACCESS_MAX_BYTES + MEM_EXT_HEADER)
