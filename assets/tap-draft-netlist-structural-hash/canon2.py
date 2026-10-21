"""Reference implementation of structural hash version 2 (tap-structural-hash/2) of the TAP draft
"Structural Hash of Flat Netlists": tapnet/1 and tapnet/2 files, including ROM records (0x10), ROM read
ports (0x13) and RAM read and write ports (0x11, 0x12).

MIT licence. Pure Python 3.9+, no dependencies besides canon.py (version 1, imported unchanged), the
reference code of "Netlist-Bound NFTs" (tapnft.py, tap02_reference.py, via canon.py) and tapnet2.py of
"Large Netlists and Verifiable Execution" (../tap-draft-large-netlists), all unchanged.

Section numbers refer to §10 of the draft:
  10.2  elements: NAND, LATCH, one ROM column per output bit of a ROM or ROM read port, one RAM read
        column per output bit of a RAM read port; RAM write ports are sinks; bank bit planes (b, j) are
        state without a signal
  10.3  liveness per signal and per plane; write ports whose enable is signal 0 are never live
  10.4  ROM column labels after the label-driven pin reduction (rom_reduce)
  10.5  RAM planes: fixed address positions (every port on the same constant), write lists in file order
        with every tuple that equals a later one removed (dedup_last)
  10.6  labels (planes like LATCH, ROM and RAM read columns like NAND in the feedback rounds)
  10.7  merging; 10.8 canonical order and bank numbers; 10.9 records (one w = 1 bank per plane node, write
        records last, each distinct ROM table stored once); 10.10 canonical file and hash domains

No set or dict iteration order influences any output: every ordering below is by an explicit key.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
_T2 = os.path.normpath(os.path.join(HERE, "..", "tap-draft-large-netlists"))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if _T2 not in sys.path:
    sys.path.append(_T2)

import canon  # noqa: E402  (tap-structural-hash/1 reference, unchanged)
import tapnet2  # noqa: E402  (tapnet/2 reference, unchanged)
from canon import CYC0, H, const_label, cyc_label, input_label, latch_label, nand_label, tap02, tapnft  # noqa: E402

TAG_ROM, TAG_PLANE, TAG_PLANE0, TAG_PLANE_R, TAG_RAMR = 0x06, 0x07, 0x08, 0x09, 0x0A
HASH_DOMAIN1 = canon.HASH_DOMAIN                      # b"tap-structural-hash/1\x00"
HASH_DOMAIN2 = b"tap-structural-hash/2\x00"
NAND, LATCH, ROM, RAMR = "N", "L", "R", "M"
C0, C1 = const_label(0), const_label(1)
MAX_BANKS = 256


class TooLarge(ValueError):
    """The input exceeds the caller's bound, or the canonical file cannot be written (10.8, 10.10)."""


# ---------------------------------------------------------------- ROM column: pin reduction and label (10.4)

def column_table(data: bytes, ds: int, a: int, w: int, j: int) -> int:
    """Column j of the ROM data at ds as an int whose bit m is entry m's bit j."""
    t = 0
    for m in range(1 << a):
        bit = m * w + j
        if (data[ds + (bit >> 3)] >> (bit & 7)) & 1:
            t |= 1 << m
    return t


def rom_reduce(pin_labels, table: int):
    """pin_labels[i]: label of address pin i (addr[0] = LSB); table bit m: column value at address m.
    Returns (q, t): the distinct non-constant pin labels ascending, and the reduced 2^len(q)-bit table."""
    q = sorted({l for l in pin_labels if l != C0 and l != C1})
    pos = {l: i for i, l in enumerate(q)}
    fixed = 0
    var = []
    for i, l in enumerate(pin_labels):
        if l == C1:
            fixed |= 1 << i
        elif l != C0:
            var.append((i, pos[l]))
    t = 0
    for m in range(1 << len(q)):
        addr = fixed
        for i, p in var:
            addr |= ((m >> p) & 1) << i
        if (table >> addr) & 1:
            t |= 1 << m
    return q, t


def table_bytes(k: int, t: int) -> bytes:
    return t.to_bytes(((1 << k) + 7) // 8, "little")  # LSB first; k = 0 gives one byte


def rom_label(pin_labels, table: int) -> bytes:
    q, t = rom_reduce(pin_labels, table)
    return H(bytes([TAG_ROM, len(q)]), *q, table_bytes(len(q), t))


# ---------------------------------------------------------------- RAM planes (10.5)

def dedup_last(writes):
    """Remove every write whose label tuple occurs again later; keep the order of the rest."""
    seen, out = set(), []
    for wt in reversed(writes):
        if wt not in seen:
            seen.add(wt)
            out.append(wt)
    out.reverse()
    return out


def plane_body(k: int, writes) -> bytes:
    return bytes([k]) + b"".join(b"".join(wt) for wt in writes)


# ---------------------------------------------------------------- decoding (10.2)

def _elements(data: bytes):
    """Return (version, n_in, n_out, n_sig, kind, ins, tab, rplane, writes).
    kind/ins by signal; tab[s] = (ds, a, w, j) for ROM columns; rplane[s] = (bank, j) for RAM read columns;
    writes[bank] = [(we, addr tuple, wdata tuple), ...] in file order."""
    if len(data) < 7:
        raise tapnet2.Invalid("file shorter than the header")
    version = data[6]
    kind, ins, tab, rplane, writes = {}, {}, {}, {}, {}
    if version == tapnet2.VERSION1:
        tapnft.check_file(data)                        # exactly the /1 input check
        n_in, n_out, rec = tapnft.decode_file(data)
        s = 2 + n_in
        for e in tap02.decode(rec, n_in):
            kind[s] = NAND if e.op == tap02.NAND else LATCH
            ins[s] = tuple(e.ins)
            s += 1
        return version, n_in, n_out, s, kind, ins, tab, rplane, writes
    if version != tapnet2.VERSION2:
        raise tapnet2.Invalid(f"unsupported version {version}")
    nl = tapnet2.decode(data)                         # full tapnet/2 check
    for r in nl.records:
        raw, f = r.raw, r.first_out
        if raw.op == tapnet2.OP_NAND:
            kind[f], ins[f] = NAND, tuple(raw.refs)
        elif raw.op == tapnet2.OP_LATCH:
            kind[f], ins[f] = LATCH, tuple(raw.refs)
        elif raw.op in (tapnet2.OP_ROM, tapnet2.OP_ROMP):   # a ROM port's ds is its target ROM's data
            for j in range(raw.w):
                kind[f + j], ins[f + j], tab[f + j] = ROM, tuple(raw.refs), (raw.ds, raw.a, raw.w, j)
        elif raw.op == tapnet2.OP_RAMR:
            for j in range(raw.w):
                kind[f + j], ins[f + j], rplane[f + j] = RAMR, tuple(raw.refs), (raw.bank, j)
        elif raw.op == tapnet2.OP_RAMW:
            refs = raw.refs
            writes.setdefault(raw.bank, []).append((refs[0], tuple(refs[1:1 + raw.a]), tuple(refs[1 + raw.a:])))
        else:
            raise tapnet2.Invalid(f"unexpected opcode {raw.op}")
    return version, nl.n_in, nl.n_out, nl.n_signals, kind, ins, tab, rplane, writes


@dataclass
class Result:
    canonical: bytes
    structural_hash: bytes
    version: int              # version byte of the canonical file (1: no ROM or RAM node, 2: otherwise)
    live: int                 # live element signals (one per live ROM column / RAM read column)
    nodes: int                # merged signal nodes (NAND, LATCH, ROM, RAM read)
    rom_nodes: int
    ram_nodes: int            # merged RAM read-column nodes
    planes: int               # merged plane nodes (= banks of the canonical file)
    cyclic: int               # live signals and planes whose unfolding is infinite
    rounds: int
    copies: int


def canonicalize(data: bytes, max_signals: int | None = None) -> Result:
    version, n_in, n_out, n_sig, kind, ins, tab, rplane, writes = _elements(data)
    if max_signals is not None and n_sig > max_signals:
        raise TooLarge(f"{n_sig} signals > bound {max_signals}")
    base = 2 + n_in

    # 10.3 liveness, per signal and per plane (bank, bit)
    live, live_planes = set(), set()
    stack = [n_sig - n_out + j for j in range(n_out)]
    while stack:
        s = stack.pop()
        if s in live:
            continue
        live.add(s)
        for x in ins[s]:
            if x >= base and x not in live:
                stack.append(x)
        if kind[s] == RAMR and rplane[s] not in live_planes:
            b, j = rplane[s]
            live_planes.add((b, j))
            for we, addr, wd in writes.get(b, ()):
                if we != 0:
                    for x in (we,) + addr + (wd[j],):
                        if x >= base and x not in live:
                            stack.append(x)
    order = sorted(live)
    planes = sorted(live_planes)

    table = {}
    for s in order:
        if kind[s] == ROM:
            ds, a, w, j = tab[s]
            table[s] = column_table(data, ds, a, w, j)

    # 10.5 per plane: enabled writes (signal refs), kept address positions
    pw: dict[tuple, list] = {}
    keep: dict[tuple, list] = {}
    preads: dict[tuple, list] = {p: [] for p in planes}
    for s in order:
        if kind[s] == RAMR:
            preads[rplane[s]].append(s)
    for p in planes:
        b, j = p
        pw[p] = [(we, addr, wd[j]) for we, addr, wd in writes.get(b, ()) if we != 0]
        addrs = [ins[s] for s in preads[p]] + [addr for _, addr, _ in pw[p]]
        a = len(addrs[0])
        keep[p] = [i for i in range(a)
                   if not (addrs[0][i] in (0, 1) and all(ad[i] == addrs[0][i] for ad in addrs))]

    def ram_ins(s):
        return tuple(ins[s][i] for i in keep[rplane[s]])

    def plane_deps(p):
        ks = keep[p]
        out = []
        for we, addr, wd in pw[p]:
            out += [we] + [addr[i] for i in ks] + [wd]
        return out

    # §4.2 acyclic labels: dependency graph over live signals and live planes
    label: dict[int, bytes] = {}
    plabel: dict[tuple, bytes] = {}

    def sig_label(x: int) -> bytes:
        if x < 2:
            return const_label(x)
        if x < base:
            return input_label(x - 2)
        return label[x]

    def write_tuples(p, get):
        ks = keep[p]
        return dedup_last([(get(we),) + tuple(get(addr[i]) for i in ks) + (get(wd),) for we, addr, wd in pw[p]])

    def elem_label(s: int, get, getp) -> bytes:
        k = kind[s]
        if k == NAND:
            return nand_label(get(ins[s][0]), get(ins[s][1]))
        if k == ROM:
            return rom_label([get(x) for x in ins[s]], table[s])
        if k == RAMR:
            return H(bytes([TAG_RAMR]), getp(rplane[s]), *[get(x) for x in ram_ins(s)])
        return latch_label(get(ins[s][0]))

    items = [("s", s) for s in order] + [("p", p) for p in planes]

    def deps(it):
        if it[0] == "p":
            return [("s", x) for x in plane_deps(it[1]) if x >= base]
        s = it[1]
        d = [("s", x) for x in ins[s] if x >= base]
        if kind[s] == RAMR:
            d = [("s", x) for x in ram_ins(s) if x >= base] + [("p", rplane[s])]
        return d

    pending, consumers = {}, {it: [] for it in items}
    for it in items:
        ds_ = deps(it)
        pending[it] = len(ds_)
        for d in ds_:
            consumers[d].append(it)
    queue = [it for it in items if pending[it] == 0]
    qi = 0
    while qi < len(queue):
        it = queue[qi]
        qi += 1
        if it[0] == "s":
            label[it[1]] = elem_label(it[1], sig_label, plabel.__getitem__)
        else:
            p = it[1]
            plabel[p] = H(bytes([TAG_PLANE]), plane_body(len(keep[p]), write_tuples(p, sig_label)))
        for c in consumers[it]:
            pending[c] -= 1
            if pending[c] == 0:
                queue.append(c)
    cyc = [s for s in order if s not in label]
    cyc_planes = [p for p in planes if p not in plabel]

    # §4.3 rounds: LATCHes and planes are state, NAND / ROM / RAM read columns are combinational
    rounds = 0
    if cyc or cyc_planes:
        def eval_round(latch_labels, plane_labels):
            lab = dict(latch_labels)

            def get(x: int) -> bytes:
                return lab[x] if x in lab else sig_label(x)

            def getp(p):
                return plane_labels[p] if p in plane_labels else plabel[p]
            for s in cyc:
                if kind[s] != LATCH:
                    lab[s] = elem_label(s, get, getp)
            return lab, dict(plane_labels)

        cur, curp = eval_round({s: CYC0 for s in cyc if kind[s] == LATCH},
                               {p: H(bytes([TAG_PLANE0, len(keep[p])])) for p in cyc_planes})
        count = len(set(cur.values()) | set(curp.values()))
        while True:
            rounds += 1

            def prev(x: int, cur=cur) -> bytes:
                return cur[x] if x in cur else sig_label(x)
            nl_ = {s: cyc_label(prev(ins[s][0])) for s in cyc if kind[s] == LATCH}
            np_ = {p: H(bytes([TAG_PLANE_R]), plane_body(len(keep[p]), write_tuples(p, prev))) for p in cyc_planes}
            cur, curp = eval_round(nl_, np_)
            ncount = len(set(cur.values()) | set(curp.values()))
            if ncount == count:
                break
            count = ncount
        label.update(cur)
        plabel.update(curp)

    # §5 / 10.7 merging
    node: dict[bytes, tuple] = {}
    depth_of: dict[bytes, int] = {}
    depth: dict[int, int] = {}
    for s in order:
        k = kind[s]
        if k == NAND:
            la, lb = sig_label(ins[s][0]), sig_label(ins[s][1])
            struct = (NAND, (min(la, lb), max(la, lb)))
            dins = ins[s]
        elif k == ROM:
            q, t = rom_reduce([sig_label(x) for x in ins[s]], table[s])
            struct = (ROM, tuple(q), t)
            dins = ins[s]
        elif k == RAMR:
            dins = ram_ins(s)
            struct = (RAMR, tuple(sig_label(x) for x in dins), plabel[rplane[s]])
        else:
            struct = (LATCH, (sig_label(ins[s][0]),))
            dins = ()
        d = 0 if k == LATCH else 1 + max([(depth[x] if x >= base and kind[x] != LATCH else 0) for x in dins],
                                         default=0)
        depth[s] = d
        lk = label[s]
        if lk in node:
            if node[lk] != struct or depth_of[lk] != d:
                raise AssertionError("label collision or unstable partition")
        else:
            node[lk] = struct
            depth_of[lk] = d
    pnode: dict[bytes, tuple] = {}
    for p in planes:
        st = (len(keep[p]), tuple(write_tuples(p, sig_label)))
        if pnode.setdefault(plabel[p], st) != st:
            raise AssertionError("label collision (plane)")

    # §6 / 10.8 output tail; readers are NAND, ROM and RAM read nodes
    outs = [label[n_sig - n_out + j] for j in range(n_out)]
    first = {}
    for j, v in enumerate(outs):
        first.setdefault(v, j)
    comb_readers: dict[bytes, list[bytes]] = {v: [] for v in node}
    for v in sorted(node):
        st = node[v]
        if st[0] != LATCH:
            for x in st[1]:
                if x in node:
                    comb_readers[x].append(v)
    slot: dict[bytes, int] = {}
    for j in range(n_out - 1, -1, -1):
        v = outs[j]
        if first[v] == j and all(c in slot and slot[c] > j for c in comb_readers[v]):
            slot[v] = j
    core = sorted((v for v in node if v not in slot), key=lambda v: (depth_of[v], v))

    sig: dict[bytes, int] = {C0: 0, C1: 1}
    for i in range(n_in):
        sig[input_label(i)] = 2 + i
    for p, v in enumerate(core):
        sig[v] = base + p
    for v, j in slot.items():
        sig[v] = base + len(core) + j
    banks = sorted(pnode)
    if len(banks) > MAX_BANKS:
        raise TooLarge(f"{len(banks)} plane nodes > {MAX_BANKS} banks")
    bank_of = {v: i for i, v in enumerate(banks)}

    # 10.9 records
    body = bytearray()
    rom_at: dict[tuple, int] = {}

    def u24(x: int) -> bytes:
        return x.to_bytes(3, "big")

    def addr_refs(xs) -> bytes:
        return b"".join(u24(sig[x]) for x in xs) if xs else u24(0)

    def record(v: bytes) -> bytes:
        st = node[v]
        if st[0] == NAND:
            a, b = sorted(sig[x] for x in st[1])
            return bytes([0x00]) + u24(a) + u24(b)
        if st[0] == LATCH:
            return bytes([0x01]) + u24(sig[st[1][0]])
        if st[0] == RAMR:
            return bytes([0x11, bank_of[st[2]], max(1, len(st[1])), 0, 1]) + addr_refs(st[1])
        q, t = st[1], st[2]
        if q:
            a, tb, refs = len(q), table_bytes(len(q), t), addr_refs(q)
        else:                                          # constant column: a = 1, address signal 0, [v, v]
            a, tb, refs = 1, bytes([3 if t & 1 else 0]), u24(0)
        off = rom_at.get((a, tb))
        if off is not None:                            # table already stored: ROM read port
            return bytes([0x13]) + off.to_bytes(4, "big") + bytes([a, 0, 1]) + refs
        rom_at[(a, tb)] = tapnet2.HEADER_LEN + len(body)
        return bytes([0x10, a, 0, 1]) + refs + tb

    for v in core + outs:
        body += record(v)
    for v in banks:
        k, wts = pnode[v]
        for wt in wts:
            body += (bytes([0x12, bank_of[v], max(1, k), 0, 1]) + u24(sig[wt[0]]) + addr_refs(wt[1:1 + k])
                     + u24(sig[wt[-1]]))
    body = bytes(body)

    rom_nodes = sum(1 for v in node if node[v][0] == ROM)
    ram_nodes = sum(1 for v in node if node[v][0] == RAMR)
    if rom_nodes == 0 and ram_nodes == 0:
        canonical = tapnft.encode_file(body, n_in, n_out)      # checks as tapnet/1
        h = hashlib.sha256(HASH_DOMAIN1 + canonical).digest()
        cver = 1
    else:
        canonical = tapnet2.make_file(body, n_in, n_out, flags=tapnet2.FLAG_MEM if banks else 0)
        try:
            tapnet2.check_file(canonical)                      # 64 MiB, 2^24 signals
        except tapnet2.Invalid as e:
            raise TooLarge(f"canonical file is not a valid tapnet/2 file: {e}") from e
        h = hashlib.sha256(HASH_DOMAIN2 + canonical).digest()
        cver = 2
    return Result(canonical, h, cver, len(order), len(node), rom_nodes, ram_nodes, len(banks),
                  len(cyc) + len(cyc_planes), rounds, n_out - len(slot))


def structural_hash(data: bytes) -> bytes:
    return canonicalize(data).structural_hash


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="tap-structural-hash/2 of a tapnet/1 or tapnet/2 file")
    ap.add_argument("file")
    ap.add_argument("--write", help="write the canonical file here")
    args = ap.parse_args()
    with open(args.file, "rb") as f:
        raw = f.read()
    r = canonicalize(raw)
    print("structuralHash ", "0x" + r.structural_hash.hex())
    print(f"canonical v{r.version}  live {r.live}  nodes {r.nodes}  rom {r.rom_nodes}  ram {r.ram_nodes}"
          f"  planes {r.planes}  cyclic {r.cyclic}  rounds {r.rounds}  copies {r.copies}")
    if args.write:
        with open(args.write, "wb") as f:
            f.write(r.canonical)
