"""Generate vectors2.json for structural hash version 2 (tapnet/2: ROM, ROM read ports, RAM ports). MIT licence.

Deterministic: fixed seeds, sorted keys, no timestamps.  python3 make_vectors2.py [--check]
Also provides the netlist-graph helpers and invariant transformations used by test_canon2.py.
"""
from __future__ import annotations

import json
import os
import random
import sys

import canon2
from canon2 import tapnet2 as t2

HERE = os.path.dirname(os.path.abspath(__file__))
import examples  # noqa: E402  (tapnet/2 reference examples, ../tap-draft-large-netlists, unchanged)

SEED = 20261020

# ------------------------------------------------------------------ graphs
# g = (n_in, n_out, nodes, outs, banks).  banks: bank number -> (a, w).
# nodes: id -> one of
#   ("N", [r, r])                  NAND
#   ("L", [r])                     LATCH
#   ("R", [pins], w, entries)      ROM
#   ("P", target, [pins])          ROM read port reading the table of ROM node `target`
#   ("M", bank, [pins])            RAM read port (w of the bank)
#   ("W", bank, we, [pins], [wdata], seq)   RAM write port; writes of one bank are applied in `seq` order
# A reference r is ("c", v), ("i", k) or ("e", id, j) (j = column; 0 for NAND/LATCH).
# outs: ids of NAND nodes forming the last n_out records, in output order. Nothing else refers to an output.


def width(g, k):
    n = g[2][k]
    return {"N": 1, "L": 1, "R": n[2] if n[0] == "R" else 0, "P": g[2][n[1]][2] if n[0] == "P" else 0,
            "M": g[4][n[1]][1] if n[0] == "M" else 0, "W": 0}[n[0]]


def refs(n):
    if n[0] in ("N", "L"):
        return n[1]
    if n[0] == "R":
        return n[1]
    if n[0] in ("P", "M"):
        return n[2]
    return [n[2]] + n[3] + n[4]


def deps(n):
    d = [r[1] for r in refs(n) if r[0] == "e"] if n[0] != "L" else []
    if n[0] == "P":
        d.append(n[1])
    return d


def file_from_graph(g, order=None) -> bytes:
    n_in, n_out, nodes, outs, banks = g
    outset = set(outs)
    if order is None:
        order = canonical_order(g)
    seq = list(order) + list(outs)
    pos, nxt = {}, 2 + n_in
    for k in seq:
        for j in range(width(g, k)):
            pos[(k, j)] = nxt + j
        nxt += width(g, k)

    def sig(r):
        return r[1] if r[0] == "c" else 2 + r[1] if r[0] == "i" else pos[(r[1], r[2])]
    body, rom_off, mem = bytearray(), {}, False
    for k in seq:
        n = nodes[k]
        if n[0] == "N":
            body += t2.enc_nand(sig(n[1][0]), sig(n[1][1]))
        elif n[0] == "L":
            body += t2.enc_latch(sig(n[1][0]))
        elif n[0] == "R":
            rom_off[k] = t2.HEADER_LEN + len(body)
            body += t2.enc_rom([sig(p) for p in n[1]], n[2], t2.pack_rom_data(n[3], len(n[1]), n[2]))
        elif n[0] == "P":
            body += t2.enc_romp(rom_off[n[1]], [sig(p) for p in n[2]], nodes[n[1]][2])
        elif n[0] == "M":
            body += t2.enc_ramr(n[1], [sig(p) for p in n[2]], banks[n[1]][1])
            mem = True
        else:
            body += t2.enc_ramw(n[1], [sig(p) for p in n[3]], [sig(x) for x in n[4]], sig(n[2]))
            mem = True
    assert not outset & set(order)
    data = t2.make_file(bytes(body), n_in, n_out, flags=t2.FLAG_MEM if mem else 0)
    t2.check_file(data)
    return data


def _write_key(g, k):
    n = g[2][k]
    return n[5]


def _order_deps(g):
    """Dependencies for any valid order: references, ROM port targets, and the write order within a bank."""
    nodes, outset = g[2], set(g[3])
    rest = sorted(k for k in nodes if k not in outset)
    dd = {k: set(deps(nodes[k])) for k in rest}
    by_bank = {}
    for k in rest:
        if nodes[k][0] == "W":
            by_bank.setdefault(nodes[k][1], []).append(k)
    for ws in by_bank.values():
        ws.sort(key=lambda k: _write_key(g, k))
        for a, b in zip(ws, ws[1:]):
            dd[b].add(a)
    return rest, dd


def canonical_order(g):
    rest, dd = _order_deps(g)
    placed, order = set(), []
    while len(order) < len(rest):
        k = min(k for k in rest if k not in placed and dd[k] <= placed)
        placed.add(k)
        order.append(k)
    return order


def random_order(rng, g):
    rest, dd = _order_deps(g)
    placed, order = set(), []
    while len(order) < len(rest):
        ready = [k for k in rest if k not in placed and dd[k] <= placed]
        k = rng.choice(ready)
        placed.add(k)
        order.append(k)
    return order


def _ref(rng, n_in, avail, p_const=0.1):
    x = rng.random()
    if x < p_const:
        return ("c", rng.randrange(2))
    if not avail or (n_in and x < 0.3):
        return ("i", rng.randrange(n_in)) if n_in else ("c", rng.randrange(2))
    return rng.choice(avail[-8:] if rng.random() < 0.7 else avail)


def random_graph(rng, max_in=4, max_el=26, ram=True):
    n_in = rng.randint(0, max_in)
    n_el = rng.randint(4, max_el)
    n_out = rng.randint(1, 3)
    banks = {}
    if ram:
        for b in rng.sample(range(256), rng.randint(0, 3)):
            banks[b] = (rng.randint(1, 3), rng.randint(1, 3))
    nodes, avail, latches, roms, seq = {}, [], [], [], 0
    for k in range(n_el - n_out):
        x = rng.random()
        if x < 0.15:
            nodes[k] = ("L", [None])
            latches.append(k)
            avail.append(("e", k, 0))
        elif x < 0.30:
            a, w = rng.randint(1, 3), rng.randint(1, 3)
            nodes[k] = ("R", [_ref(rng, n_in, avail) for _ in range(a)], w,
                        [rng.randrange(1 << w) for _ in range(1 << a)])
            roms.append(k)
            avail += [("e", k, j) for j in range(w)]
        elif x < 0.37 and roms:
            t = rng.choice(roms)
            nodes[k] = ("P", t, [_ref(rng, n_in, avail) for _ in range(len(nodes[t][1]))])
            avail += [("e", k, j) for j in range(nodes[t][2])]
        elif x < 0.52 and banks:
            b = rng.choice(sorted(banks))
            nodes[k] = ("M", b, [_ref(rng, n_in, avail, 0.15) for _ in range(banks[b][0])])
            avail += [("e", k, j) for j in range(banks[b][1])]
        elif x < 0.64 and banks:
            b = rng.choice(sorted(banks))
            a, w = banks[b]
            we = ("c", 1) if rng.random() < 0.2 else _ref(rng, n_in, avail, 0)
            nodes[k] = ("W", b, we, [_ref(rng, n_in, avail, 0.15) for _ in range(a)],
                        [_ref(rng, n_in, avail) for _ in range(w)], float(seq))
            seq += 1
        else:
            nodes[k] = ("N", [_ref(rng, n_in, avail), _ref(rng, n_in, avail)])
            avail.append(("e", k, 0))
    outs = []
    for k in range(n_el - n_out, n_el):
        nodes[k] = ("N", [_ref(rng, n_in, avail, 0), _ref(rng, n_in, avail, 0)])
        outs.append(k)
    every = avail + [("e", k, 0) for k in outs]
    for k in latches:
        nodes[k] = ("L", [rng.choice(every) if every and rng.random() < 0.9 else ("c", rng.randrange(2))])
    return n_in, n_out, nodes, outs, banks


def _copy(g):
    n_in, n_out, nodes, outs, banks = g
    new = {}
    for k, n in nodes.items():
        new[k] = tuple(list(x) if isinstance(x, list) else x for x in n)
    return n_in, n_out, new, list(outs), dict(banks)


def _rewire(g, fn):
    """Apply fn to every reference of every element."""
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] in ("N", "L", "R"):
            n[1][:] = [fn(r, k) for r in n[1]]
        elif n[0] in ("P", "M"):
            n[2][:] = [fn(r, k) for r in n[2]]
        else:
            nodes[k] = ("W", n[1], fn(n[2], k), [fn(r, k) for r in n[3]], [fn(r, k) for r in n[4]], n[5])


def _ports_of(g, t):
    return [k for k in sorted(g[2]) if g[2][k][0] == "P" and g[2][k][1] == t]


def _avail(g):
    nodes, outset = g[2], set(g[3])
    return [("e", k, j) for k in sorted(nodes) if k not in outset for j in range(width(g, k))]


# ---- transformations that keep the structural hash

def t_swap(rng, g):
    g = _copy(g)
    for k in sorted(g[2]):
        n = g[2][k]
        if n[0] == "N" and rng.random() < 0.5:
            n[1].reverse()
    return g


def permute_pins(pins, entries, perm):
    """New pin perm[i] = old pin i; the table follows."""
    a = len(pins)
    new_pins = [None] * a
    for i in range(a):
        new_pins[perm[i]] = pins[i]
    new_entries = [0] * (1 << a)
    for old in range(1 << a):
        new = 0
        for i in range(a):
            new |= ((old >> i) & 1) << perm[i]
        new_entries[new] = entries[old]
    return new_pins, new_entries


def t_pin_perm(rng, g):
    """Permute the address pins of every ROM with its table; ROM ports reading it permute their pins alike."""
    g = _copy(g)
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R":
            perm = list(range(len(n[1])))
            rng.shuffle(perm)
            pins, entries = permute_pins(n[1], n[3], perm)
            nodes[k] = ("R", pins, n[2], entries)
            for p in _ports_of(g, k):
                pp, _ = permute_pins(nodes[p][2], [0] * (1 << len(pins)), perm)
                nodes[p] = ("P", k, pp)
    return g


def t_col_perm(rng, g):
    """Permute the columns of every ROM (its ports follow) and rewire the readers."""
    g = _copy(g)
    nodes = g[2]
    perms = {}
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R":
            w = n[2]
            p = list(range(w))
            rng.shuffle(p)
            perms[k] = p
            ent = []
            for e in n[3]:
                ne = 0
                for j in range(w):
                    ne |= ((e >> j) & 1) << p[j]
                ent.append(ne)
            nodes[k] = ("R", n[1], w, ent)
            for q in _ports_of(g, k):
                perms[q] = p
    _rewire(g, lambda r, _k: ("e", r[1], perms[r[1]][r[2]]) if r[0] == "e" and r[1] in perms else r)
    return g


def t_dead_cols(rng, g):
    """Append unread columns to some ROMs (their ports widen alike)."""
    g = _copy(g)
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R" and rng.random() < 0.6:
            extra = rng.randint(1, 2)
            nodes[k] = ("R", n[1], n[2] + extra, [e | (rng.randrange(1 << extra) << n[2]) for e in n[3]])
    return g


def t_split(rng, g):
    """Split some ROMs without ports into two ROMs over the same address, rewiring readers."""
    g = _copy(g)
    nodes = g[2]
    nxt = max(nodes) + 1
    moves = {}
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R" and n[2] >= 2 and not _ports_of(g, k) and rng.random() < 0.6:
            w = n[2]
            cut = rng.randint(1, w - 1)
            nodes[k] = ("R", list(n[1]), cut, [e & ((1 << cut) - 1) for e in n[3]])
            nodes[nxt] = ("R", list(n[1]), w - cut, [e >> cut for e in n[3]])
            moves[k] = (cut, nxt)
            nxt += 1

    def fn(r, _k):
        if r[0] == "e" and r[1] in moves and r[2] >= moves[r[1]][0]:
            return ("e", moves[r[1]][1], r[2] - moves[r[1]][0])
        return r
    _rewire(g, fn)
    return g


def t_port_to_rom(rng, g):
    """Replace ROM read ports by ROM records with a copy of the table (and the reverse direction is the
    original graph): a ROM port is a ROM column node like any other."""
    g = _copy(g)
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "P" and rng.random() < 0.7:
            t = nodes[n[1]]
            nodes[k] = ("R", list(n[2]), t[2], list(t[3]))
    return g


def t_dup(rng, g, count=3):
    """Duplicate elements and move some references to the copy. A duplicated write port is placed right
    after the original in its bank's write order."""
    g = _copy(g)
    nodes, outset = g[2], set(g[3])
    for _ in range(count):
        cand = [k for k in sorted(nodes) if k not in outset]
        if not cand:
            break
        k = rng.choice(cand)
        nk = max(nodes) + 1
        n = nodes[k]
        if n[0] == "W":
            later = [nodes[x][5] for x in nodes if nodes[x][0] == "W" and nodes[x][5] > n[5]]
            s = (n[5] + min(later)) / 2 if later else n[5] + 1
            nodes[nk] = ("W", n[1], n[2], list(n[3]), list(n[4]), s)
            continue
        nodes[nk] = tuple(list(x) if isinstance(x, list) else x for x in n)
        _rewire(g, lambda r, _j: ("e", nk, r[2]) if r[0] == "e" and r[1] == k and rng.random() < 0.5 else r)
    return g


def t_dead(rng, g, count=3):
    """Add unread elements: NAND, LATCH, ROM, ROM port, RAM read port, a write port with enable on signal 0,
    and a whole bank that nothing reads (with read and write ports)."""
    g = _copy(g)
    n_in, _, nodes, outs, banks = g
    for _ in range(count):
        nk = max(nodes) + 1
        avail = _avail(g)
        x = rng.random()
        roms = [k for k in sorted(nodes) if nodes[k][0] == "R"]
        if x < 0.15:
            nodes[nk] = ("L", [rng.choice(avail + [("e", k, 0) for k in outs] + [("e", nk, 0)])])
        elif x < 0.3:
            a, w = rng.randint(1, 3), rng.randint(1, 3)
            nodes[nk] = ("R", [_ref(rng, n_in, avail) for _ in range(a)], w,
                         [rng.randrange(1 << w) for _ in range(1 << a)])
        elif x < 0.4 and roms:
            t = rng.choice(roms)
            nodes[nk] = ("P", t, [_ref(rng, n_in, avail) for _ in range(len(nodes[t][1]))])
        elif x < 0.55 and banks:
            b = rng.choice(sorted(banks))
            nodes[nk] = ("M", b, [_ref(rng, n_in, avail) for _ in range(banks[b][0])])
        elif x < 0.7 and banks:
            b = rng.choice(sorted(banks))
            a, w = banks[b]
            nodes[nk] = ("W", b, ("c", 0), [_ref(rng, n_in, avail) for _ in range(a)],
                         [_ref(rng, n_in, avail) for _ in range(w)], rng.random() * 40 - 1)
        elif x < 0.8 and len(banks) < 200:
            b = rng.choice([v for v in range(256) if v not in banks])
            a, w = rng.randint(1, 2), rng.randint(1, 2)
            banks[b] = (a, w)
            nodes[nk] = ("W", b, _ref(rng, n_in, avail), [_ref(rng, n_in, avail) for _ in range(a)],
                         [_ref(rng, n_in, avail) for _ in range(w)], 0.5)
            nodes[nk + 1] = ("M", b, [_ref(rng, n_in, avail) for _ in range(a)])
        else:
            nodes[nk] = ("N", [_ref(rng, n_in, avail), _ref(rng, n_in, avail)])
    return g


def t_const_pin(rng, g):
    """Insert an address pin on signal 0 or 1 into some ROMs without ports; the other half is junk."""
    g = _copy(g)
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R" and len(n[1]) < 5 and not _ports_of(g, k) and rng.random() < 0.6:
            c = rng.randrange(2)
            a, w = len(n[1]), n[2]
            ent = [n[3][m & ((1 << a) - 1)] if (m >> a) & 1 == c else rng.randrange(1 << w)
                   for m in range(1 << (a + 1))]
            pins, ent = permute_pins(list(n[1]) + [("c", c)], ent, rng.sample(range(a + 1), a + 1))
            nodes[k] = ("R", pins, w, ent)
    return g


def t_dup_pin(rng, g):
    """Wire an address signal of some ROMs without ports to a second pin; off-diagonal entries are junk."""
    g = _copy(g)
    nodes = g[2]
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "R" and len(n[1]) < 5 and not _ports_of(g, k) and rng.random() < 0.6:
            a, w = len(n[1]), n[2]
            i = rng.randrange(a)
            ent = [n[3][m & ((1 << a) - 1)] if ((m >> a) & 1) == ((m >> i) & 1) else rng.randrange(1 << w)
                   for m in range(1 << (a + 1))]
            pins, ent = permute_pins(list(n[1]) + [n[1][i]], ent, rng.sample(range(a + 1), a + 1))
            nodes[k] = ("R", pins, w, ent)
    return g


# ---- RAM transformations

def t_bank_renumber(rng, g):
    g = _copy(g)
    nodes, banks = g[2], g[4]
    new = rng.sample(range(256), len(banks))
    mp = dict(zip(sorted(banks), new))
    g = g[:4] + ({mp[b]: v for b, v in banks.items()},)
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] in ("M", "W"):
            nodes[k] = (n[0], mp[n[1]]) + n[2:]
    return g


def t_ram_col_perm(rng, g):
    """Permute the word bits of every bank: the wdata of its writes and the columns of its read ports."""
    g = _copy(g)
    nodes, banks = g[2], g[4]
    perm = {}
    for b in sorted(banks):
        p = list(range(banks[b][1]))
        rng.shuffle(p)
        perm[b] = p                                    # old bit j -> new bit p[j]
    moved = {}
    for k in sorted(nodes):
        n = nodes[k]
        if n[0] == "W":
            p = perm[n[1]]
            wd = [None] * len(p)
            for j in range(len(p)):
                wd[p[j]] = n[4][j]
            nodes[k] = ("W", n[1], n[2], n[3], wd, n[5])
        elif n[0] == "M":
            moved[k] = perm[n[1]]
    _rewire(g, lambda r, _k: ("e", r[1], moved[r[1]][r[2]]) if r[0] == "e" and r[1] in moved else r)
    return g


def t_ram_dead_cols(rng, g):
    """Widen some banks by bits that no read port column is read from (arbitrary write data)."""
    g = _copy(g)
    nodes, banks = g[2], g[4]
    avail = _avail(g)
    for b in sorted(banks):
        a, w = banks[b]
        if w < 4 and rng.random() < 0.6:
            extra = rng.randint(1, 4 - w)
            banks[b] = (a, w + extra)
            for k in sorted(nodes):
                n = nodes[k]
                if n[0] == "W" and n[1] == b:
                    extra_refs = [rng.choice([("c", 1), ("c", 0)] + avail) for _ in range(extra)]
                    nodes[k] = ("W", b, n[2], n[3], n[4] + extra_refs, n[5])
    return g


def t_ram_const_bit(rng, g):
    """Add an address bit tied to the same constant (0 or 1) to every port of some banks."""
    g = _copy(g)
    nodes, banks = g[2], g[4]
    for b in sorted(banks):
        a, w = banks[b]
        if a < 4 and rng.random() < 0.6:
            c, i = rng.randrange(2), rng.randrange(a + 1)
            banks[b] = (a + 1, w)
            for k in sorted(nodes):
                n = nodes[k]
                if n[0] == "M" and n[1] == b:
                    nodes[k] = ("M", b, n[2][:i] + [("c", c)] + n[2][i:])
                elif n[0] == "W" and n[1] == b:
                    nodes[k] = ("W", b, n[2], n[3][:i] + [("c", c)] + n[3][i:], n[4], n[5])
    return g


def t_ram_split(rng, g):
    """Split some banks by word bits into two banks; every port is duplicated, readers rewired."""
    g = _copy(g)
    nodes, banks = g[2], g[4]
    moves = {}
    for b in sorted(banks):
        a, w = banks[b]
        if w >= 2 and rng.random() < 0.6:
            cut = rng.randint(1, w - 1)
            nb = rng.choice([v for v in range(256) if v not in banks])
            banks[b], banks[nb] = (a, cut), (a, w - cut)
            for k in sorted(nodes):
                n = nodes[k]
                if n[1:2] == (b,) and n[0] in ("M", "W"):
                    nk = max(nodes) + 1
                    if n[0] == "W":
                        nodes[k] = ("W", b, n[2], n[3], n[4][:cut], n[5])
                        nodes[nk] = ("W", nb, n[2], list(n[3]), n[4][cut:], n[5])
                    else:
                        nodes[nk] = ("M", nb, list(n[2]))
                        moves[k] = (cut, nk)

    def fn(r, _k):
        if r[0] == "e" and r[1] in moves and r[2] >= moves[r[1]][0]:
            return ("e", moves[r[1]][1], r[2] - moves[r[1]][0])
        return r
    _rewire(g, fn)
    return g


ROM_TRANSFORMS = [t_swap, t_pin_perm, t_col_perm, t_dead_cols, t_split, t_dup, t_dead, t_const_pin, t_dup_pin,
                  t_port_to_rom]
RAM_TRANSFORMS = [t_bank_renumber, t_ram_col_perm, t_ram_dead_cols, t_ram_const_bit, t_ram_split]
TRANSFORMS = ROM_TRANSFORMS + RAM_TRANSFORMS


def transform(rng, g):
    for step in rng.sample(TRANSFORMS, len(TRANSFORMS)):
        if rng.random() < 0.6:
            g = step(rng, g)
    return file_from_graph(g, random_order(rng, g))


# ------------------------------------------------------------------ fixtures

class B:
    """Tiny tapnet/2 builder with raw signal indices."""

    def __init__(self, n_in):
        self.n_in, self.nxt, self.buf, self.mem = n_in, 2 + n_in, bytearray(), False

    def nand(self, x, y):
        self.buf += t2.enc_nand(x, y)
        self.nxt += 1
        return self.nxt - 1

    def latch(self, d=0):
        self.buf += t2.enc_latch(d)
        self.nxt += 1
        return self.nxt - 1, len(self.buf) - 4

    def set_d(self, pos, d):
        self.buf[pos + 1:pos + 4] = d.to_bytes(3, "big")

    def rom(self, pins, w, entries):
        off = t2.HEADER_LEN + len(self.buf)
        self.buf += t2.enc_rom(pins, w, t2.pack_rom_data(entries, len(pins), w))
        first = self.nxt
        self.nxt += w
        return list(range(first, first + w)), off

    def romp(self, off, pins, w):
        self.buf += t2.enc_romp(off, pins, w)
        first = self.nxt
        self.nxt += w
        return list(range(first, first + w))

    def read(self, bank, pins, w):
        self.buf += t2.enc_ramr(bank, pins, w)
        self.mem = True
        first = self.nxt
        self.nxt += w
        return list(range(first, first + w))

    def write(self, bank, pins, wdata, we):
        self.buf += t2.enc_ramw(bank, pins, wdata, we)
        self.mem = True

    def file(self, n_out, version=2):
        d = t2.make_file(bytes(self.buf), self.n_in, n_out, version, t2.FLAG_MEM if self.mem else 0)
        if version == 2:
            t2.check_file(d)
        return d


def tbl(f, a):
    return [f(*[(m >> i) & 1 for i in range(a)]) for m in range(1 << a)]


# -- ROM fixtures (from the ROM proposal)

def fx_andnot(swap_pins=False, swap_table=None):
    b = B(2)
    if swap_table is None:
        swap_table = swap_pins
    pins = [3, 2] if swap_pins else [2, 3]
    f = (lambda u, v: v & (1 - u)) if swap_table else (lambda u, v: u & (1 - v))
    b.rom(pins, 1, tbl(f, 2))
    return b.file(1)


def fx_andnot_nand():
    b = B(2)
    ny = b.nand(3, 3)
    n = b.nand(2, ny)
    b.nand(n, n)
    return b.file(1)


def fx_wide(variant):
    b = B(3)
    f1 = lambda x, y, z: (x & y) | (y & z) | (x & z)  # noqa: E731
    f3 = lambda x, y, z: x & (1 - y)                  # noqa: E731
    f0 = lambda x, y, z: x ^ y ^ z                    # noqa: E731
    f2 = lambda x, y, z: x | z                        # noqa: E731
    if variant == "base":
        cols, _ = b.rom([2, 3, 4], 4, [f0(*v) | f1(*v) << 1 | f2(*v) << 2 | f3(*v) << 3
                                       for v in [(m & 1, (m >> 1) & 1, (m >> 2) & 1) for m in range(8)]])
        p, q = cols[1], cols[3]
    elif variant == "narrow":
        ent = []
        for m in range(8):
            z, x, y = m & 1, (m >> 1) & 1, (m >> 2) & 1
            ent.append(f3(x, y, z) | f1(x, y, z) << 1)
        cols, _ = b.rom([4, 2, 3], 2, ent)
        p, q = cols[1], cols[0]
    else:
        p = b.rom([2, 3, 4], 1, tbl(f1, 3))[0][0]
        q = b.rom([3, 2, 4], 1, tbl(lambda y, x, z: f3(x, y, z), 3))[0][0]
    b.nand(p, q)
    b.nand(q, p)
    return b.file(2)


def fx_const_pin(kind):
    b = B(2)
    x = lambda u, v: u ^ v                  # noqa: E731
    if kind == "plain":
        c = b.rom([2, 3], 1, tbl(x, 2))[0][0]
    elif kind == "tied1":
        c = b.rom([2, 1, 3], 1, tbl(lambda u, k, v: x(u, v) if k else 1, 3))[0][0]
    else:
        c = b.rom([0, 3, 2], 1, tbl(lambda k, v, u: 0 if k else x(u, v), 3))[0][0]
    b.nand(c, c)
    return b.file(1)


def fx_const_column(kind):
    b = B(1)
    if kind == "two_pins":
        c = b.rom([1, 0], 1, [0, 1, 0, 0])[0][0]
    elif kind == "one_pin":
        c = b.rom([1], 1, [0, 1])[0][0]
    else:
        c = b.rom([0], 1, [1, 1])[0][0]
    b.nand(c, 2)
    return b.file(1)


def fx_const_signal_nand():
    b = B(1)
    b.nand(1, 2)
    return b.file(1)


def fx_counter_rom(kind):
    b = B(0)
    (q0, p0), (q1, p1) = b.latch(), b.latch()
    inc = [(m + 1) & 3 for m in range(4)]
    if kind == "base":
        (n0, n1), _ = b.rom([q0, q1], 2, inc)
    elif kind == "permuted":
        ent = [0] * 4
        for m in range(4):
            mm = ((m & 1) << 1) | (m >> 1)
            ent[mm] = ((inc[m] >> 1) & 1) | ((inc[m] & 1) << 1)
        (n1, n0), _ = b.rom([q1, q0], 2, ent)
    else:
        (n0, n1), _ = b.rom([q0, q1], 2, [(m - 1) & 3 for m in range(4)])
    b.set_d(p0, n0)
    b.set_d(p1, n1)
    b.nand(q0, q0)
    b.nand(q1, q1)
    return b.file(2)


def fx_xor(version, extra=None):
    b = B(2)
    n0 = b.nand(2, 3)
    if extra == "dead_rom":
        b.rom([n0, 2], 3, [1, 5, 7, 2])
    elif extra == "dead_ram":                          # a bank nobody reads, and an unread read port
        b.write(9, [2, n0], [n0, 3], 2)
        b.read(9, [3, 2], 2)
    n1 = b.nand(2, n0)
    n2 = b.nand(3, n0)
    b.nand(n1, n2)
    return b.file(1, version=version)


# -- ROM read port fixtures

def fx_rom_port(kind):
    """XOR table read at (x0, x1) and at (x2, x3); outputs NAND of both readings."""
    b = B(4)
    t = tbl(lambda u, v: u ^ v, 2)
    (c,), off = b.rom([2, 3], 1, t)
    if kind == "port":
        (d,) = b.romp(off, [4, 5], 1)
    elif kind == "two_roms":
        (d,), _ = b.rom([5, 4], 1, t)                  # pins permuted, same symmetric table
    elif kind == "port_same_pins":                     # a port on the same address as the ROM: one node
        (d,) = b.romp(off, [3, 2], 1)
    elif kind == "single":
        d = c
    b.nand(c, d)
    return b.file(1)


# -- RAM fixtures

def fx_ram_reg(kind):
    """One RAM bit per address: write (we = x0, addr = x1, data = x2), read (addr = x1); output NOT(read).
    Variants keep or change the structure."""
    b = B(4)
    bank = 7 if kind == "renumbered" else 0
    if kind == "const_bit":                            # a = 2, the extra bit tied to 1 in every port
        b.write(bank, [1, 3], [4], 2)
        r = b.read(bank, [1, 3], 1)[0]
    elif kind == "wider_a":                            # a = 2, the extra bit on input 3: a different bank
        b.write(bank, [3, 5], [4], 2)
        r = b.read(bank, [3, 5], 1)[0]
    else:
        if kind == "disabled_write":
            b.write(bank, [5], [5], 0)                 # enable on signal 0: never live
        b.write(bank, [3], [4], 2)
        if kind == "dup_write":
            b.write(bank, [3], [4], 2)
        if kind == "extra_write":
            b.write(bank, [5], [5], 3)
        if kind == "dead_bank":
            b.write(200, [2], [3], 4)
            b.read(200, [5], 1)
        r = b.read(bank, [3], 1)[0]
        if kind == "dup_read":
            r2 = b.read(bank, [3], 1)[0]
            b.nand(r, r2)
            return b.file(1)
    b.nand(r, r)
    return b.file(1)


def fx_ram_two_writes(swapped):
    b = B(4)
    w1 = ([3], [4], 2)
    w2 = ([5], [2], 5)
    for pins, wd, we in ([w2, w1] if swapped else [w1, w2]):
        b.write(0, pins, wd, we)
    r = b.read(0, [3], 1)[0]
    b.nand(r, r)
    return b.file(1)


def fx_ram_wide(kind):
    """A 4 x 3-bit bank written from inputs, two of its bits read (one read port)."""
    b = B(6)
    addr, wd, we = [2, 3], [4, 5, 6], 7
    if kind == "base":
        b.write(5, addr, wd, we)
        r = b.read(5, addr[::-1], 3)
        x, y = r[0], r[2]
    elif kind == "col_perm":                           # bits (2, 0, 1)
        b.write(5, addr, [wd[2], wd[0], wd[1]], we)
        r = b.read(5, addr[::-1], 3)
        x, y = r[1], r[0]
    elif kind == "split":                              # two banks of 1 and 2 bits
        b.write(11, addr, [wd[0], wd[1]], we)
        b.write(12, addr, [wd[2]], we)
        x = b.read(11, addr[::-1], 2)[0]
        y = b.read(12, addr[::-1], 1)[0]
    elif kind == "narrow":                             # only the two read bits
        b.write(5, addr, [wd[2], wd[0]], we)
        r = b.read(5, addr[::-1], 2)
        x, y = r[1], r[0]
    b.nand(x, y)
    b.nand(y, x)
    return b.file(2)


def fx_ram_counter(kind):
    """2-bit counter kept in RAM (one entry, address bit tied to 0) and incremented through a ROM."""
    b = B(0)
    if kind in ("base", "decrement"):
        q = b.read(1, [0], 2)
        f = (lambda m: (m + 1) & 3) if kind == "base" else (lambda m: (m - 1) & 3)
        n, _ = b.rom(q, 2, [f(m) for m in range(4)])
        b.write(1, [0], n, 1)
    elif kind == "split":                              # one bank per bit
        q0 = b.read(1, [0], 1)[0]
        q1 = b.read(2, [0], 1)[0]
        q = [q0, q1]
        n, _ = b.rom(q, 2, [(m + 1) & 3 for m in range(4)])
        b.write(1, [0], [n[0]], 1)
        b.write(2, [0], [n[1]], 1)
    elif kind == "latch":                              # the same counter with LATCHes: a different design
        (q0, p0), (q1, p1) = b.latch(), b.latch()
        q = [q0, q1]
        n, _ = b.rom(q, 2, [(m + 1) & 3 for m in range(4)])
        b.set_d(p0, n[0])
        b.set_d(p1, n[1])
    b.nand(q[0], q[0])
    b.nand(q[1], q[1])
    return b.file(2)


def fx_ram_unwritten(kind):
    b = B(1)
    if kind == "ram":
        r = b.read(0, [2], 1)[0]                       # never written: always 0, but not signal 0
        b.nand(r, 2)
    else:
        b.nand(0, 2)
    return b.file(1)


def fx_ram_outputs():
    """RAM read columns as outputs: a w = 2 read port whose two bits always hold the same data (one node and
    one copy record)."""
    b = B(3)
    b.write(0, [2], [3, 3], 4)
    b.read(0, [2], 2)
    return b.file(2)


def fx_ram_out_dup():
    b = B(3)
    b.write(0, [2], [3], 4)
    b.read(0, [2], 1)
    b.read(0, [2], 1)
    return b.file(2)


FIXTURES = [
    # ROM (from the ROM proposal)
    ("andnot_rom", fx_andnot(), "x AND NOT y as one ROM (a = 2, w = 1)"),
    ("andnot_rom_pins_swapped", fx_andnot(True), "address pins exchanged, table permuted accordingly"),
    ("andnot_rom_pins_swapped_only", fx_andnot(True, False), "address pins exchanged, table not permuted"),
    ("andnot_nand", fx_andnot_nand(), "the same function with 3 NAND (tapnet/2, no ROM)"),
    ("wide_rom", fx_wide("base"), "4-column ROM, 2 columns read"),
    ("wide_rom_narrow", fx_wide("narrow"), "only the 2 read columns, columns and pins permuted"),
    ("wide_rom_split", fx_wide("split"), "one ROM per read column"),
    ("const_pin_plain", fx_const_pin("plain"), "2-pin XOR ROM"),
    ("const_pin_tied1", fx_const_pin("tied1"), "extra pin on signal 1, other half junk"),
    ("const_pin_tied0", fx_const_pin("tied0"), "extra pin on signal 0, pins permuted, other half junk"),
    ("const_column_two_pins", fx_const_column("two_pins"), "both pins constant: constant column 1"),
    ("const_column_one_pin", fx_const_column("one_pin"), "one constant pin: constant column 1"),
    ("const_column_canonical", fx_const_column("canonical"), "the canonical writing of the constant column"),
    ("const_signal_nand", fx_const_signal_nand(), "NAND(1, x) without ROM"),
    ("counter_rom", fx_counter_rom("base"), "2-bit LATCH counter, next state from a ROM"),
    ("counter_rom_permuted", fx_counter_rom("permuted"), "pins and columns permuted"),
    ("counter_rom_decrement", fx_counter_rom("decrement"), "down counter: different table"),
    ("xor_v1", fx_xor(1), "xor_17851 as tapnet/1"),
    ("xor_v2", fx_xor(2), "the same records as tapnet/2"),
    ("xor_v2_dead_rom", fx_xor(2, "dead_rom"), "tapnet/2 with an unread ROM"),
    ("xor_v2_dead_ram", fx_xor(2, "dead_ram"), "tapnet/2 with a bank nobody reads (MEM flag set)"),
    ("sbox", examples.sbox_file(), "AES S-box ROM (a = 8, w = 8)"),
    ("sbox_expanded", None, "canonical NAND expansion of the S-box (as tapnet/2)"),
    # ROM read ports
    ("rom_port", fx_rom_port("port"), "XOR table read by its ROM and by a ROM read port (0x13)"),
    ("rom_port_two_roms", fx_rom_port("two_roms"), "the same with a second ROM holding a copy of the table"),
    ("rom_port_same_pins", fx_rom_port("port_same_pins"), "a ROM port on the ROM's own address (pins permuted)"),
    ("rom_port_single", fx_rom_port("single"), "the ROM column read twice"),
    ("romports", examples.romports_file(), "large-netlists example: one ROM, two ROM ports"),
    ("romdup", examples.romdup_file(), "large-netlists example: three ROM copies instead of ports"),
    # RAM
    ("ram_reg", fx_ram_reg("base"), "RAM bit: write (we x0, addr x1, data x2), read addr x1"),
    ("ram_reg_renumbered", fx_ram_reg("renumbered"), "bank 7 instead of bank 0"),
    ("ram_reg_dup_read", fx_ram_reg("dup_read"), "two read ports on the same address"),
    ("ram_reg_dup_write", fx_ram_reg("dup_write"), "the write port duplicated"),
    ("ram_reg_disabled_write", fx_ram_reg("disabled_write"), "an extra write port with enable on signal 0"),
    ("ram_reg_const_bit", fx_ram_reg("const_bit"), "a = 2, the extra address bit on signal 1 in every port"),
    ("ram_reg_dead_bank", fx_ram_reg("dead_bank"), "an extra bank whose read port nobody reads"),
    ("ram_reg_wider_a", fx_ram_reg("wider_a"), "a = 2, the extra address bit on an input"),
    ("ram_reg_extra_write", fx_ram_reg("extra_write"), "an extra enabled write port"),
    ("ram_two_writes", fx_ram_two_writes(False), "two write ports into one bank"),
    ("ram_two_writes_swapped", fx_ram_two_writes(True), "the same two write ports in the other order"),
    ("ram_wide", fx_ram_wide("base"), "4 x 3-bit bank, two bits read"),
    ("ram_wide_col_perm", fx_ram_wide("col_perm"), "word bits permuted in every port"),
    ("ram_wide_split", fx_ram_wide("split"), "split into a 2-bit and a 1-bit bank"),
    ("ram_wide_narrow", fx_ram_wide("narrow"), "only the two read bits"),
    ("ram_counter", fx_ram_counter("base"), "2-bit counter in RAM (feedback through memory)"),
    ("ram_counter_split", fx_ram_counter("split"), "one bank per bit"),
    ("ram_counter_decrement", fx_ram_counter("decrement"), "down counter: different table"),
    ("ram_counter_latch", fx_ram_counter("latch"), "the same counter with LATCHes"),
    ("ram_unwritten", fx_ram_unwritten("ram"), "NAND(read of a never-written bank, x)"),
    ("ram_unwritten_const", fx_ram_unwritten("const"), "NAND(0, x)"),
    ("ram_out_equal_bits", fx_ram_outputs(), "w = 2 read port with equal bits as both outputs"),
    ("ram_out_two_ports", fx_ram_out_dup(), "two w = 1 read ports on the same address as outputs"),
    ("ram16", examples.ram16_file(), "large-netlists example: 16 x 4-bit RAM"),
    ("ram16_latch", examples.ram16_file("latch"), "the same memory built from LATCHes"),
    ("rammix", examples.rammix_file(), "large-netlists example: two banks, ROM port on memory data"),
]

EQUAL_GROUPS = [
    ["andnot_rom", "andnot_rom_pins_swapped"],
    ["wide_rom", "wide_rom_narrow", "wide_rom_split"],
    ["const_pin_plain", "const_pin_tied1", "const_pin_tied0"],
    ["const_column_two_pins", "const_column_one_pin", "const_column_canonical"],
    ["counter_rom", "counter_rom_permuted"],
    ["xor_v1", "xor_v2", "xor_v2_dead_rom", "xor_v2_dead_ram"],
    ["rom_port", "rom_port_two_roms"],
    ["rom_port_same_pins", "rom_port_single"],
    ["romports", "romdup"],
    ["ram_reg", "ram_reg_renumbered", "ram_reg_dup_read", "ram_reg_dup_write", "ram_reg_disabled_write",
     "ram_reg_const_bit", "ram_reg_dead_bank"],
    ["ram_wide", "ram_wide_col_perm", "ram_wide_split", "ram_wide_narrow"],
    ["ram_counter", "ram_counter_split"],
    ["ram_out_equal_bits", "ram_out_two_ports"],
]

DISTINCT = [
    ("andnot_rom", "andnot_rom_pins_swapped_only"),
    ("andnot_rom", "andnot_nand"),
    ("const_column_two_pins", "const_signal_nand"),
    ("counter_rom", "counter_rom_decrement"),
    ("sbox", "sbox_expanded"),
    ("rom_port", "rom_port_single"),
    ("ram_reg", "ram_reg_wider_a"),
    ("ram_reg", "ram_reg_extra_write"),
    ("ram_two_writes", "ram_two_writes_swapped"),
    ("ram_counter", "ram_counter_decrement"),
    ("ram_counter", "ram_counter_latch"),
    ("ram_unwritten", "ram_unwritten_const"),
    ("ram16", "ram16_latch"),
]


def _fixture_files():
    out = []
    for n, d, note in FIXTURES:
        if n == "sbox_expanded":
            e = t2.expand_rom_to_tapnet1(examples.sbox_file())
            d = e[:6] + b"\x02" + e[7:]
        out.append((n, d, note))
    return out


def case(name, data, note):
    r = canon2.canonicalize(data)
    return {"name": name, "note": note, "version": data[6], "flags": data[7],
            "nIn": int.from_bytes(data[8:12], "big"), "nOut": int.from_bytes(data[12:16], "big"),
            "file": "0x" + data.hex(), "canonical": "0x" + r.canonical.hex(), "canonicalVersion": r.version,
            "structuralHash": "0x" + r.structural_hash.hex(), "live": r.live, "nodes": r.nodes,
            "romNodes": r.rom_nodes, "ramNodes": r.ram_nodes, "planes": r.planes, "cyclic": r.cyclic,
            "rounds": r.rounds, "copies": r.copies}


def invalid_cases():
    """Files that /2 must reject (not valid tapnet/2 or tapnet/1)."""
    good = fx_ram_reg("base")
    no_flag = good[:7] + b"\x00" + good[8:]
    rom_flag = fx_andnot()[:7] + b"\x01" + fx_andnot()[8:]
    b = B(1)
    b.read(0, [2], 1)
    b.read(0, [2, 2], 1)
    mismatch = t2.make_file(bytes(b.buf), 1, 1, flags=t2.FLAG_MEM)
    ref = t2.make_file(bytes([0x02]) + bytes(8), 1, 1)
    rp = fx_rom_port("port")
    return [("ram_without_mem_flag", no_flag), ("mem_flag_without_ram", rom_flag),
            ("bank_dimension_mismatch", mismatch), ("ref_record", ref),
            ("rom_port_bad_offset", rp[:-21] + t2.enc_romp(17, [4, 5], 1) + rp[-7:])]


def build():
    rng = random.Random(SEED)
    cases = [case(n, d, note) for n, d, note in _fixture_files()]
    groups = [list(g) for g in EQUAL_GROUPS]
    i = 0
    made = 0
    while made < 4:
        g = random_graph(rng)
        i += 1
        if canon2.canonicalize(file_from_graph(g)).planes == 0:     # keep draws with live RAM
            continue
        names = [f"random{made}"]
        cases.append(case(names[0], file_from_graph(g), f"random tapnet/2 netlist with live RAM"
                          f" (seed {SEED}, draw {i})"))
        for v in range(3):
            names.append(f"random{made}_variant{v}")
            cases.append(case(names[-1], transform(rng, g), f"random{made} after renumbering and the ROM and RAM"
                              " transformations of test_canon2.py"))
        groups.append(names)
        made += 1
    by = {c["name"]: c for c in cases}
    out_groups = []
    for gr in groups:
        hs = {by[m]["structuralHash"] for m in gr}
        assert len(hs) == 1, gr
        out_groups.append({"members": gr, "structuralHash": hs.pop()})
    for a, b in DISTINCT:
        assert by[a]["structuralHash"] != by[b]["structuralHash"], (a, b)
    invalid = []
    for n, d in invalid_cases():
        try:
            canon2.canonicalize(d)
        except Exception:                               # noqa: BLE001
            invalid.append({"name": n, "file": "0x" + d.hex()})
        else:
            raise AssertionError(f"invalid case {n} accepted")
    return {
        "format": "tap-structural-hash-vectors/2",
        "labelDomain": "TAPSH1",
        "labelTags": {"rom": "0x06", "plane": "0x07", "planeRound0": "0x08", "planeRound": "0x09",
                      "ramRead": "0x0a"},
        "hashDomain1": "0x" + canon2.HASH_DOMAIN1.hex(),
        "hashDomain2": "0x" + canon2.HASH_DOMAIN2.hex(),
        "cases": cases,
        "equalGroups": out_groups,
        "distinct": [{"members": list(d)} for d in DISTINCT],
        "invalid": invalid,
        "compatibility": "every case of vectors.json (version 1), as tapnet/1 and re-headed as tapnet/2, has the "
                         "same canonical file and structural hash under version 2 (checked by test_canon2.py)",
    }


def main():
    text = json.dumps(build(), indent=1, sort_keys=True) + "\n"
    path = os.path.join(HERE, "vectors2.json")
    if "--check" in sys.argv:
        with open(path, encoding="utf-8") as f:
            assert f.read() == text, "vectors2.json differs from the generator"
        print("vectors2.json up to date")
        return
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(text)
    print(path, canon2.hashlib.sha256(text.encode()).hexdigest())


if __name__ == "__main__":
    main()
