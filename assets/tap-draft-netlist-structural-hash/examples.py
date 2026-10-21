"""Deterministic example circuits and invalid samples for tapnet/2 (generated in code)."""
from __future__ import annotations

from typing import List, Sequence, Tuple

import tapnet2 as t2


class Builder:
    def __init__(self, n_in: int):
        self.n_in = n_in
        self.next = 2 + n_in
        self.buf = bytearray()

    def inp(self, i: int) -> int:
        return 2 + i

    def nand(self, x: int, y: int) -> int:
        self.buf += t2.enc_nand(x, y)
        self.next += 1
        return self.next - 1

    def not_(self, x: int) -> int:
        return self.nand(x, x)

    def and_(self, x: int, y: int) -> int:
        return self.not_(self.nand(x, y))

    def xor(self, x: int, y: int) -> Tuple[int, int]:
        """Returns (x XOR y, NAND(x, y))."""
        n1 = self.nand(x, y)
        return self.nand(self.nand(x, n1), self.nand(y, n1)), n1

    def latch(self) -> Tuple[int, int]:
        """Returns (signal, position) — set the d reference later with set_d."""
        pos = len(self.buf)
        self.buf += t2.enc_latch(0)
        self.next += 1
        return self.next - 1, pos

    def set_d(self, pos: int, d: int) -> None:
        self.buf[pos + 1:pos + 4] = t2.u24(d)

    def rom(self, addr: Sequence[int], w: int, entries: Sequence[int]) -> List[int]:
        a = len(addr)
        self.last_rom = t2.HEADER_LEN + len(self.buf)       # offset of this ROM record (for rom_port)
        self.buf += t2.enc_rom(addr, w, t2.pack_rom_data(entries, a, w))
        outs = list(range(self.next, self.next + w))
        self.next += w
        return outs

    def rom_port(self, rom_offset: int, addr: Sequence[int], w: int) -> List[int]:
        """ROM read port (0x13) of the ROM record at rom_offset (same a and w)."""
        self.buf += t2.enc_romp(rom_offset, addr, w)
        outs = list(range(self.next, self.next + w))
        self.next += w
        return outs

    def ram_read(self, bank: int, addr: Sequence[int], w: int) -> List[int]:
        """RAM read port (0x11): w signals = entry addr of the bank at the start of the beat."""
        self.has_ram = True
        self.buf += t2.enc_ramr(bank, addr, w)
        outs = list(range(self.next, self.next + w))
        self.next += w
        return outs

    def ram_write(self, bank: int, addr: Sequence[int], wdata: Sequence[int], we: int) -> None:
        """RAM write port (0x12): if we, entry addr of the bank := wdata for the next beat. It creates no signal;
        all its references must point backwards."""
        self.has_ram = True
        self.buf += t2.enc_ramw(bank, addr, wdata, we)

    # ---- small helpers for the memory examples
    def outputs(self, sigs: Sequence[int]) -> List[int]:
        """Copies sigs to the last len(sigs) signals (two inverters each; the outputs are contiguous)."""
        inv = [self.not_(x) for x in sigs]
        return [self.not_(x) for x in inv]

    def mux(self, s: int, x0: int, x1: int) -> int:
        """s ? x1 : x0."""
        return self.nand(self.nand(x0, self.not_(s)), self.nand(x1, s))

    def mux_bus(self, s: int, x0: Sequence[int], x1: Sequence[int]) -> List[int]:
        return [self.mux(s, a, b) for a, b in zip(x0, x1)]

    def mux_tree(self, addr: Sequence[int], words: Sequence[Sequence[int]]) -> List[int]:
        """words[addr] (addr LSB first), as a tree of 2:1 multiplexers."""
        level = [list(w) for w in words]
        for s in addr:
            level = [self.mux_bus(s, level[2 * i], level[2 * i + 1]) for i in range(len(level) // 2)]
        return level[0]

    def decoder(self, addr: Sequence[int], enable: int) -> List[int]:
        """One-hot lines: line k = enable AND (addr == k)."""
        lines = [enable]
        for s in addr:
            ns = self.not_(s)
            lines = [self.and_(l, x) for x in (ns, s) for l in lines]
        return lines

    def add(self, x: Sequence[int], y: Sequence[int]) -> List[int]:
        """x + y modulo 2^len(x) (ripple carry)."""
        out, carry = [], 0
        for a, b in zip(x, y):
            s1, n1 = self.xor(a, b)
            s2, n2 = self.xor(s1, carry)
            out.append(s2)
            carry = self.nand(n1, n2)
        return out

    def register(self, n: int) -> List[Tuple[int, int]]:
        return [self.latch() for _ in range(n)]

    def file(self, n_out: int) -> bytes:
        flags = t2.FLAG_MEM if getattr(self, "has_ram", False) else 0
        data = t2.make_file(bytes(self.buf), self.n_in, n_out, flags=flags)
        t2.check_file(data)
        return data


class XorShift:
    """xorshift64*: a fixed PRNG so examples do not depend on Python's random module."""

    def __init__(self, seed: int):
        self.s = seed or 1

    def next(self) -> int:
        s = self.s
        s ^= (s >> 12) & 0xFFFFFFFFFFFFFFFF
        s ^= (s << 25) & 0xFFFFFFFFFFFFFFFF
        s ^= (s >> 27) & 0xFFFFFFFFFFFFFFFF
        self.s = s & 0xFFFFFFFFFFFFFFFF
        return (self.s * 0x2545F4914F6CDD1D) & 0xFFFFFFFFFFFFFFFF

    def below(self, n: int) -> int:
        return (self.next() >> 11) % n

    def bits(self, n: int) -> List[int]:
        return [self.below(2) for _ in range(n)]


def aes_sbox() -> List[int]:
    def gmul(a: int, b: int) -> int:
        p = 0
        while b:
            if b & 1:
                p ^= a
            a = ((a << 1) ^ 0x11B) if a & 0x80 else (a << 1)
            b >>= 1
        return p

    inv = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if gmul(a, b) == 1:
                inv[a] = b
                break
    rotl = lambda x, k: ((x << k) | (x >> (8 - k))) & 0xFF  # noqa: E731
    return [inv[x] ^ rotl(inv[x], 1) ^ rotl(inv[x], 2) ^ rotl(inv[x], 3) ^ rotl(inv[x], 4) ^ 0x63 for x in range(256)]


def sbox_file() -> bytes:
    """8-bit AES S-box as one ROM (a = 8, w = 8). Inputs x[0..7] LSB first, outputs S(x) LSB first."""
    b = Builder(8)
    b.rom([b.inp(i) for i in range(8)], 8, aes_sbox())
    return b.file(8)


def mul4_file() -> bytes:
    """4x4-bit multiplication table ROM: inputs x (bits 0..3) and y (bits 4..7), output x*y (8 bits)."""
    b = Builder(8)
    b.rom([b.inp(i) for i in range(8)], 8, [(k & 15) * (k >> 4) for k in range(256)])
    return b.file(8)


MESSAGE = b"Hello from tapnet/2 ROM!\n"
MESSAGE_DELAY = 8   # beats of silence before the message


def message_file() -> bytes:
    """Sequential: a 6-bit counter (LATCHes, enable input) addresses a ROM (a = 6, w = 8) holding zeros
    for MESSAGE_DELAY beats and then MESSAGE. Output = the character for the current beat."""
    b = Builder(1)
    qs = [b.latch() for _ in range(6)]
    carry = b.inp(0)
    for q, pos in qs:
        x, n1 = b.xor(q, carry)
        b.set_d(pos, x)
        carry = b.not_(n1)                 # q AND carry
    entries = [0] * 64
    for i, ch in enumerate(MESSAGE):
        entries[MESSAGE_DELAY + i] = ch
    b.rom([q for q, _ in qs], 8, entries)
    return b.file(8)


def large_file() -> bytes:
    """Synthetic file larger than 49,152 bytes (6 chunks): 64 LATCHes, ROM A (S-box), 4,000 NANDs, ROM B
    (a = 15, w = 8, 32 KiB of data spanning 3 chunks), 4,000 NANDs, ROM C (a = 4, w = 4), 16 output NANDs."""
    rng = XorShift(0x7A9E7A9E)
    b = Builder(16)
    latches = [b.latch() for _ in range(64)]
    rom_a = b.rom([b.inp(i) for i in range(8)], 8, aes_sbox())

    def nand_block(n: int) -> None:
        for _ in range(n):
            hi = b.next
            def pick() -> int:
                if rng.below(4):
                    return hi - 1 - rng.below(min(32, hi - 2))
                return 2 + rng.below(hi - 2)
            b.nand(pick(), pick())

    nand_block(4000)
    rom_b = b.rom([2 + rng.below(b.next - 2) for _ in range(15)], 8, [rng.below(256) for _ in range(1 << 15)])
    nand_block(4000)
    rom_c = b.rom([b.next - 1 - i for i in range(4)], 4, [rng.below(16) for _ in range(16)])
    for i, (_, pos) in enumerate(latches):
        src = (rom_a, rom_b)[i % 2]
        b.set_d(pos, src[i % 8] if i < 16 else 2 + rng.below(b.next - 2))
    for i in range(16):
        b.nand(rom_c[i % 4], rom_b[i % 8])
    return b.file(16)


def nand_only_file(n: int = 21000) -> bytes:
    """Measurement only: n NANDs with mostly local wiring, 16 inputs, 16 outputs."""
    rng = XorShift(0x5EED)
    b = Builder(16)
    for _ in range(n):
        hi = b.next
        b.nand(hi - 1 - rng.below(min(64, hi - 2)), hi - 1 - rng.below(min(64, hi - 2)))
    return b.file(16)


def random_rom_file(rng: XorShift) -> bytes:
    """Small random netlist with ROMs and LATCHes (for the expansion equivalence test)."""
    n_in = 1 + rng.below(6)
    b = Builder(n_in)
    latches = [b.latch() for _ in range(rng.below(5))]
    for _ in range(2 + rng.below(4)):
        for _ in range(rng.below(6)):
            b.nand(2 + rng.below(b.next - 2), rng.below(b.next))
        a = 1 + rng.below(5)
        w = 1 + rng.below(10)
        b.rom([rng.below(b.next) for _ in range(a)], w, [rng.below(1 << w) for _ in range(1 << a)])
    for _ in range(1 + rng.below(6)):
        b.nand(rng.below(b.next), rng.below(b.next))
    for _, pos in latches:
        b.set_d(pos, rng.below(b.next))
    n_out = 1 + rng.below(min(8, b.next - 2 - n_in))
    return b.file(n_out)


# ---------------------------------------------------------------- memory examples (RAM ports, ROM ports)

RAM16_A, RAM16_W, RAM16_BANK = 4, 4, 3
RAM16_N_IN = 2 * RAM16_A + RAM16_W + 2


def ram16_file(kind: str = "ram") -> bytes:
    """A 16 x 4-bit memory with two read ports and a read-modify-write port, built from RAM ports (kind "ram",
    bank 3) or from LATCHes, multiplexers and a write decoder (kind "latch", what LATCHes alone need).

    Inputs (14): RADDR[0..3], WADDR[0..3], WDATA[0..3], WE, MODE.
    Per beat:    R1 = mem[RADDR], R2 = mem[WADDR]   (memory at the start of the beat)
                 if WE: mem[WADDR] := (MODE ? R2 + WDATA : WDATA) mod 16
                 ACC (4 LATCHes) := ACC xor R1
    Outputs (12): R1, R2, ACC."""
    A, W = RAM16_A, RAM16_W
    b = Builder(RAM16_N_IN)
    i = [b.inp(k) for k in range(RAM16_N_IN)]
    raddr, waddr, wdata, we, mode = i[0:4], i[4:8], i[8:12], i[12], i[13]
    acc = b.register(W)
    if kind == "latch":
        mem = [b.register(W) for _ in range(1 << A)]
        r1 = b.mux_tree(raddr, [[q for q, _ in m] for m in mem])
        r2 = b.mux_tree(waddr, [[q for q, _ in m] for m in mem])
    else:
        r1 = b.ram_read(RAM16_BANK, raddr, W)
        r2 = b.ram_read(RAM16_BANK, waddr, W)
    new = b.mux_bus(mode, wdata, b.add(r2, wdata))
    if kind == "latch":
        lines = b.decoder(waddr, we)
        for k in range(1 << A):
            for (q, pos), x in zip(mem[k], b.mux_bus(lines[k], [q for q, _ in mem[k]], new)):
                b.set_d(pos, x)
    else:
        b.ram_write(RAM16_BANK, waddr, new, we)        # after the adder: all references point backwards
    for (q, pos), r in zip(acc, r1):
        b.set_d(pos, b.xor(q, r)[0])
    b.outputs(r1 + r2 + [q for q, _ in acc])
    return b.file(12)


def ram16_inputs(n: int, seed: int) -> List[List[int]]:
    rng = XorShift(seed)
    return [rng.bits(RAM16_N_IN) for _ in range(n)]


def ram16_memory(kind: str, state: Sequence[int], mem) -> List[int]:
    """The 16 entries, from the LATCH state (LATCHes 4.. in order) or from bank 3."""
    if kind == "latch":
        return [sum(state[RAM16_W + RAM16_W * k + j] << j for j in range(RAM16_W)) for k in range(1 << RAM16_A)]
    return list((mem or {}).get(RAM16_BANK, [0] * (1 << RAM16_A)))


RAMMIX_N_IN = 12


def rammix_rom() -> List[int]:
    rng = XorShift(0x3A11)
    return [rng.below(1 << 12) for _ in range(64)]


def rammix_file() -> bytes:
    """Two banks, two write ports into one bank in the same beat, an entry width that is not a power of two,
    and a ROM read port addressed by memory contents.

    Inputs (12): A[0..5], D[0..3], WE, SEL.
    Bank 0: a = 6, w = 12 (stride 16: 1,024 bits in 4 memory words); bank 7: a = 2, w = 1.
    Per beat:  r = ROM[A] (a = 6, w = 12);  q = bank0[A];  p = ROM[q[0..5]] (ROM port 0x13);
               x = bank7[D0, D1]
               if WE:  bank0[A] := q xor r                      (write port 1)
               if SEL: bank0[D0..D3, 0, 0] := p                 (write port 2; wins over port 1 on the same entry)
               if WE:  bank7[D0, D1] := not x                   (write port 3)
               ACC (4 LATCHes) := ACC xor q[0..3]
    Outputs (29): q, p, x, ACC."""
    b = Builder(RAMMIX_N_IN)
    i = [b.inp(k) for k in range(RAMMIX_N_IN)]
    A, D, we, sel = i[0:6], i[6:10], i[10], i[11]
    acc = b.register(4)
    r = b.rom(A, 12, rammix_rom())
    rom_off = b.last_rom
    q = b.ram_read(0, A, 12)
    p = b.rom_port(rom_off, q[0:6], 12)
    x = b.ram_read(7, D[0:2], 1)[0]
    b.ram_write(0, A, [b.xor(u, v)[0] for u, v in zip(q, r)], we)
    b.ram_write(0, D + [0, 0], p, sel)
    b.ram_write(7, D[0:2], [b.not_(x)], we)
    for (l, pos), y in zip(acc, q[0:4]):
        b.set_d(pos, b.xor(l, y)[0])
    b.outputs(q + p + [x] + [l for l, _ in acc])
    return b.file(29)


def rammix_inputs(n: int, seed: int) -> List[List[int]]:
    rng = XorShift(seed)
    return [rng.bits(RAMMIX_N_IN) for _ in range(n)]


ROMPORT_ENTRIES = [3, 17, 8, 31, 0, 22, 9, 14]


def romports_file() -> bytes:
    """A ROM (a = 3, w = 5) read through the ROM record itself and through two ROM ports (0x13); no RAM, so
    no MEM flag. Inputs x[0..5]; outputs ROM[x0..x2], ROM[x3..x5], ROM[x2, x1, x0]."""
    b = Builder(6)
    b.rom([2, 3, 4], 5, ROMPORT_ENTRIES)
    b.rom_port(t2.HEADER_LEN, [5, 6, 7], 5)
    b.rom_port(t2.HEADER_LEN, [4, 3, 2], 5)
    return b.file(15)


def romdup_file() -> bytes:
    """romports_file with three copies of the ROM instead of ROM ports."""
    b = Builder(6)
    for addr in ([2, 3, 4], [5, 6, 7], [4, 3, 2]):
        b.rom(addr, 5, ROMPORT_ENTRIES)
    return b.file(15)


RAM_EXAMPLES = {
    "ram16": ram16_file,
    "rammix": rammix_file,
    "romports": romports_file,
}


EXAMPLES = {
    "sbox": sbox_file,
    "mul4": mul4_file,
    "message": message_file,
    "large": large_file,
}


def invalid_files() -> List[Tuple[str, bytes, str]]:
    """(name, file, reason fragment). Each must be rejected by check_file."""
    H = lambda n_in, n_out, v=2, r=0: t2.MAGIC + bytes([v, r]) + t2.u32(n_in) + t2.u32(n_out)  # noqa: E731
    nand = t2.enc_nand
    rom_hdr = lambda a, w: bytes([t2.OP_ROM, a]) + t2.u16(w)  # noqa: E731
    ok_rom = t2.enc_rom([2], 1, bytes([0b10]))                # a=1, w=1: 2 bits, 6 padding bits
    rr = t2.enc_ramr(0, [2], 1)                                # RAM read port, bank 0, a = 1, w = 1
    rw = t2.enc_ramw(0, [2], [2], 2)                           # RAM write port, bank 0, a = 1, w = 1
    return [
        ("short_header", t2.MAGIC + b"\x02\x00\x00", "shorter than the 16-byte header"),
        ("bad_magic", b"TAPNEX" + H(1, 1)[6:] + nand(2, 2), "bad magic"),
        ("version_1", H(1, 1, v=1) + nand(2, 2), "unsupported version"),
        ("version_3", H(1, 1, v=3) + nand(2, 2), "unsupported version"),
        ("flags_unknown_bit", H(1, 1, r=2) + nand(2, 2), "unknown flag bits"),
        ("flags_unknown_bit_with_mem", H(1, 1, r=3) + rw + rr, "unknown flag bits"),
        ("mem_flag_without_ram", H(1, 1, r=1) + nand(2, 2), "no RAM ports"),
        ("ram_without_mem_flag", H(1, 1) + rr, "must set the MEM flag"),
        ("no_records", H(1, 1), "no records"),
        ("n_out_zero", H(1, 0) + nand(2, 2), "nOut out of range"),
        ("n_in_too_large", H(65537, 1) + nand(2, 2), "nIn out of range"),
        ("ref_record", H(1, 1) + nand(2, 2) + bytes([2]) + b"\x00" * 30 + b"\x00\x01", "REF record"),
        ("unknown_opcode_03", H(1, 1) + bytes([3]) + b"\x00" * 6, "unknown opcode"),
        ("unknown_opcode_14", H(1, 1) + bytes([0x14, 1]) + t2.u16(1) + t2.u24(2) + b"\x00", "unknown opcode"),
        ("truncated_nand", H(1, 1) + nand(2, 2)[:5], "truncated NAND"),
        ("truncated_latch", H(1, 1) + nand(2, 2) + t2.enc_latch(3)[:2], "truncated LATCH"),
        ("nand_forward_ref", H(1, 1) + nand(2, 3), "not available"),
        ("latch_ref_beyond_end", H(1, 1) + t2.enc_latch(4), "beyond the last signal"),
        ("too_few_signals_for_outputs", H(1, 2) + nand(2, 2), "too few signals"),
        ("rom_a_zero", H(1, 1) + rom_hdr(0, 1) + b"\x00", "address width"),
        ("rom_a_21", H(1, 1) + rom_hdr(21, 1) + t2.u24(2) * 21, "address width"),
        ("rom_w_zero", H(1, 1) + rom_hdr(1, 0) + t2.u24(2), "word width"),
        ("rom_w_257", H(1, 1) + rom_hdr(1, 257) + t2.u24(2) + b"\x00" * 65, "word width"),
        ("rom_truncated_header", H(1, 1) + rom_hdr(2, 1)[:3], "truncated ROM header"),
        ("rom_truncated_refs", H(1, 1) + rom_hdr(2, 1) + t2.u24(2), "truncated ROM"),
        ("rom_truncated_data", H(1, 1) + rom_hdr(3, 8) + t2.u24(2) * 3 + b"\x00" * 7, "truncated ROM"),
        ("rom_huge_declared_data", H(1, 1) + rom_hdr(20, 256) + t2.u24(2) * 20, "truncated ROM"),
        ("rom_forward_ref", H(1, 1) + t2.enc_rom([3], 1, b"\x00"), "not available"),
        ("rom_ref_own_output", H(1, 1) + t2.enc_rom([2, 3], 1, b"\x00"), "not available"),
        ("rom_nonzero_padding", H(1, 1) + ok_rom[:-1] + bytes([0b110]), "padding"),
        ("rom_nonzero_padding_w3", H(1, 3) + t2.enc_rom([2], 3, b"\x00")[:-1] + bytes([0x40]), "padding"),
        ("ram_bank_dimensions_disagree", H(1, 1, r=1) + rr + t2.enc_ramr(0, [2], 2), "dimensions of bank"),
        ("ram_read_forward_ref", H(1, 1, r=1) + t2.enc_ramr(0, [3], 1), "not available"),
        ("ram_write_forward_we", H(1, 1, r=1) + nand(2, 2) + t2.enc_ramw(0, [2], [2], 4) + rr,
         "not available"),
        ("ram_write_forward_addr", H(1, 1, r=1) + nand(2, 2) + t2.enc_ramw(0, [4], [2], 2) + rr,
         "not available"),
        ("ram_write_forward_data", H(1, 1, r=1) + nand(2, 2) + t2.enc_ramw(0, [2], [4], 2) + rr,
         "not available"),
        ("ram_bank_too_large", H(1, 1, r=1) + t2.enc_ramr(0, [2] * 20, 17), "2^24"),
        ("ram_a_zero", H(1, 1, r=1) + bytes([0x11, 0, 0]) + t2.u16(1), "port dimensions"),
        ("ram_w_zero", H(1, 1, r=1) + bytes([0x11, 0, 1]) + t2.u16(0) + t2.u24(2), "port dimensions"),
        ("ram_w_257", H(1, 1, r=1) + bytes([0x11, 0, 1]) + t2.u16(257) + t2.u24(2), "port dimensions"),
        ("ram_truncated_header", H(1, 1, r=1) + rr[:4], "truncated port header"),
        ("ram_truncated_write", H(1, 1, r=1) + rw[:-1], "truncated port record"),
        ("rom_port_truncated_header", H(1, 1) + ok_rom + t2.enc_romp(16, [2], 1)[:7], "truncated port header"),
        ("rom_port_without_rom", H(1, 1) + t2.enc_romp(16, [2], 1), "earlier ROM"),
        ("rom_port_other_w", H(1, 2) + ok_rom + t2.enc_romp(16, [2], 2), "earlier ROM"),
        ("rom_port_later_rom", H(1, 2) + t2.enc_romp(23, [2], 1) + ok_rom, "earlier ROM"),
        ("rom_port_bad_offset", H(1, 2) + ok_rom + t2.enc_romp(17, [2], 1), "earlier ROM"),
        ("rom_port_forward_ref", H(1, 2) + ok_rom + t2.enc_romp(16, [4], 1), "not available"),
    ]
