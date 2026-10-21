"""Tests for structural hash version 2 (canon2.py). MIT licence.  python3 test_canon2.py"""
from __future__ import annotations

import json
import os
import random
import unittest
import zlib

import canon
import canon2
import make_vectors as mv1
import make_vectors2 as mv2
from canon2 import C0, C1, input_label, rom_reduce, tapnet2 as t2

HERE = os.path.dirname(os.path.abspath(__file__))
N_RANDOM = 300
SEED = 4242


def run(data, seqs):
    """Outputs for each input sequence from the all-zero state and all-zero memory."""
    nl = t2.decode(data, (1, 2))
    res = []
    for seq in seqs:
        st, mem, outs = [0] * nl.n_latch, None, []
        for x in seq:
            _, o, st, mem, _ = t2.evaluate_full(nl, st, mem, x)
            outs.append(tuple(o))
        res.append(outs)
    return res


def reheader(data, version):
    return data[:6] + bytes([version]) + data[7:]


def has_ram(g):
    return any(n[0] in ("M", "W") for n in g[2].values())


class Reduce(unittest.TestCase):
    def test_permutation(self):
        x, y = input_label(0), input_label(1)
        tf = sum(b << m for m, b in enumerate([0, 1, 0, 0]))
        tg = sum(b << m for m, b in enumerate([0, 0, 1, 0]))
        self.assertEqual(rom_reduce([x, y], tf), rom_reduce([y, x], tg))
        self.assertNotEqual(rom_reduce([x, y], tf), rom_reduce([y, x], tf))

    def test_constant_slice(self):
        x = input_label(0)
        self.assertEqual(rom_reduce([x, C1], 0b1000), ([x], 0b10))
        self.assertEqual(rom_reduce([C0, x], 0b0100), ([x], 0b10))
        self.assertEqual(rom_reduce([C1, C0], 0b0010), ([], 1))

    def test_dedup_last(self):
        a, b, c = ("a",), ("b",), ("c",)
        self.assertEqual(canon2.dedup_last([a, b, a, c, c]), [b, a, c])


class Compatibility(unittest.TestCase):
    """/2 equals /1 on every tapnet/1 file and on the same records re-headed as tapnet/2."""

    def test_v1_vectors(self):
        with open(os.path.join(HERE, "vectors.json")) as f:
            v = json.load(f)
        n = 0
        for c in v["cases"] + v["chainSnapshot"]:
            data = bytes.fromhex(c["file"][2:])
            for ver in (1, 2):
                r = canon2.canonicalize(reheader(data, ver))
                self.assertEqual("0x" + r.canonical.hex(), c["canonical"], c.get("name"))
                self.assertEqual("0x" + r.structural_hash.hex(), c["structuralHash"], c.get("name"))
                self.assertEqual((r.version, r.planes, r.rom_nodes, r.ram_nodes), (1, 0, 0, 0))
                n += 1
        self.assertEqual(n, 80)
        for c in v["invalid"]:
            with self.assertRaises(Exception):
                canon2.canonicalize(bytes.fromhex(c["file"][2:]))

    def test_v1_random(self):
        rng = random.Random(SEED)
        for _ in range(N_RANDOM):
            g = mv1.random_graph(rng)
            for data in (mv1.file_from_graph(g), mv1.transform(rng, g)):
                r1 = canon.canonicalize(data)
                for ver in (1, 2):
                    r2 = canon2.canonicalize(reheader(data, ver))
                    self.assertEqual(r2.canonical, r1.canonical)
                    self.assertEqual(r2.structural_hash, r1.structural_hash)
                    self.assertEqual((r2.rounds, r2.cyclic, r2.copies), (r1.rounds, r1.cyclic, r1.copies))

    def test_dead_memory_is_v1(self):
        """A tapnet/2 file whose ROMs and RAM ports are all dead hashes as version 1, byte for byte."""
        rng = random.Random(SEED + 9)
        for i in range(200):
            g = mv1.random_graph(rng)
            r1 = canon.canonicalize(mv1.file_from_graph(g))
            n_in, n_out, nodes1, outs = g
            nodes = {k: ("N" if op == canon.NAND else "L",
                         [r if r[0] != "e" else ("e", r[1], 0) for r in ins]) for k, (op, ins) in nodes1.items()}
            nk = max(nodes) + 1
            x = ("i", 0) if n_in else ("c", 1)
            nodes[nk] = ("R", [x, ("c", 1)], 2, [1, 2, 3, 0])                     # unread ROM
            nodes[nk + 1] = ("P", nk, [("c", 0), x])                               # unread ROM port
            nodes[nk + 2] = ("W", 17, x, [x, ("c", 0)], [("e", nk, 1), x], 0.0)    # bank nobody reads
            nodes[nk + 3] = ("M", 17, [("c", 0), x])                               # unread read port
            data = mv2.file_from_graph((n_in, n_out, nodes, list(outs), {17: (2, 2)}))
            self.assertEqual(data[7], t2.FLAG_MEM)
            r = canon2.canonicalize(data)
            self.assertEqual((r.canonical, r.structural_hash, r.version), (r1.canonical, r1.structural_hash, 1))


class RandomV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(SEED + 1)
        cls.graphs = [mv2.random_graph(rng) for _ in range(N_RANDOM)]

    def each(self, step, need_ram=False):
        rng = random.Random(zlib.crc32(step.__name__.encode()))
        changed = 0
        for g in self.graphs:
            if need_ram and not has_ram(g):
                continue
            f0 = mv2.file_from_graph(g)
            base = canon2.structural_hash(f0)
            g2 = step(rng, g)
            f2 = mv2.file_from_graph(g2, mv2.random_order(rng, g2))
            changed += f2 != f0
            self.assertEqual(canon2.structural_hash(f2), base, step.__name__)
        self.assertGreater(changed, 50, step.__name__)

    def test_ram_present(self):
        n = sum(1 for g in self.graphs if has_ram(g))
        self.assertGreater(n, 150)

    def test_renumbering(self):
        rng = random.Random(1)
        for g in self.graphs:
            base = canon2.structural_hash(mv2.file_from_graph(g))
            self.assertEqual(canon2.structural_hash(mv2.file_from_graph(g, mv2.random_order(rng, g))), base)

    def test_nand_swap(self):
        self.each(mv2.t_swap)

    def test_rom_pin_permutation(self):
        self.each(mv2.t_pin_perm)

    def test_rom_column_permutation(self):
        self.each(mv2.t_col_perm)

    def test_rom_dead_columns(self):
        self.each(mv2.t_dead_cols)

    def test_rom_split(self):
        self.each(mv2.t_split)

    def test_rom_port_to_rom(self):
        self.each(mv2.t_port_to_rom)

    def test_duplication(self):
        self.each(mv2.t_dup)

    def test_dead_elements(self):
        self.each(mv2.t_dead)

    def test_rom_constant_pin(self):
        self.each(mv2.t_const_pin)

    def test_rom_duplicated_pin(self):
        self.each(mv2.t_dup_pin)

    def test_bank_renumbering(self):
        self.each(mv2.t_bank_renumber, True)

    def test_ram_column_permutation(self):
        self.each(mv2.t_ram_col_perm, True)

    def test_ram_dead_columns(self):
        self.each(mv2.t_ram_dead_cols, True)

    def test_ram_constant_address_bit(self):
        self.each(mv2.t_ram_const_bit, True)

    def test_ram_split(self):
        self.each(mv2.t_ram_split, True)

    def test_combined(self):
        rng = random.Random(2)
        for g in self.graphs:
            base = canon2.structural_hash(mv2.file_from_graph(g))
            for _ in range(2):
                self.assertEqual(canon2.structural_hash(mv2.transform(rng, g)), base)

    def test_canonical_valid_equivalent_idempotent(self):
        rng = random.Random(3)
        ram_cyclic = rom_cyclic = with_ram = 0
        for g in self.graphs:
            data = mv2.transform(rng, g)
            r = canon2.canonicalize(data)
            nl = t2.decode(r.canonical, (1, 2))
            self.assertEqual(r.canonical[6], r.version)
            self.assertEqual(r.version == 2, r.rom_nodes + r.ram_nodes > 0)
            self.assertEqual(nl.has_mem, r.planes > 0)
            self.assertEqual(len(nl.banks), r.planes)
            self.assertTrue(all(w == 1 for _, w in nl.banks.values()))
            r2 = canon2.canonicalize(r.canonical)
            self.assertEqual(r2.canonical, r.canonical)
            self.assertEqual((r2.copies, r2.planes, r2.nodes), (r.copies, r.planes, r.nodes))
            n_in = g[0]
            seqs = [[[rng.randrange(2) for _ in range(n_in)] for _ in range(10)] for _ in range(4)]
            self.assertEqual(run(data, seqs), run(r.canonical, seqs))
            with_ram += r.planes > 0
            if r.cyclic:
                ram_cyclic += r.planes > 0
                rom_cyclic += r.rom_nodes > 0
        self.assertGreater(with_ram, 100)
        self.assertGreater(ram_cyclic, 30)
        self.assertGreater(rom_cyclic, 30)

    def test_equal_hash_equal_behaviour(self):
        """Different random netlists that happen to share a hash behave identically."""
        rng = random.Random(5)
        by = {}
        for g in self.graphs:
            by.setdefault((g[0], canon2.structural_hash(mv2.file_from_graph(g))), []).append(g)
        for (n_in, _), gs in by.items():
            if len(gs) > 1:
                seqs = [[[rng.randrange(2) for _ in range(n_in)] for _ in range(8)] for _ in range(4)]
                outs = {tuple(map(tuple, run(mv2.file_from_graph(x), seqs))) for x in gs}
                self.assertEqual(len(outs), 1)


class Distinctness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(SEED + 2)
        cls.graphs = [g for g in (mv2.random_graph(rng) for _ in range(N_RANDOM)) if has_ram(g)]

    def test_rom_table_bit_matters(self):
        rng = random.Random(4)
        checked = 0
        for g in self.graphs:
            r = canon2.canonicalize(mv2.transform(rng, g))
            nl = t2.decode(r.canonical, (1, 2))
            for rec in nl.records:
                if rec.raw.op == t2.OP_ROM:
                    d = bytearray(r.canonical)
                    d[rec.raw.ds] ^= 1
                    self.assertNotEqual(canon2.structural_hash(bytes(d)), r.structural_hash)
                    checked += 1
        self.assertGreater(checked, 100)

    def test_write_order_matters(self):
        """Exchanging two different write ports of one plane in a canonical file changes the hash."""
        rng = random.Random(6)
        checked = 0
        for g in self.graphs:
            r = canon2.canonicalize(mv2.transform(rng, g))
            nl = t2.decode(r.canonical, (1, 2))
            ws = [rec.raw for rec in nl.records if rec.raw.op == t2.OP_RAMW]
            for x, y in zip(ws, ws[1:]):
                if x.bank == y.bank:
                    d = r.canonical
                    a, b = d[x.off:x.end], d[y.off:y.end]
                    d2 = d[:x.off] + b + a + d[y.end:]
                    self.assertNotEqual(canon2.structural_hash(d2), r.structural_hash)
                    checked += 1
                    break
        self.assertGreater(checked, 20)

    def test_bank_identity_matters(self):
        """Redirecting a read port of a canonical file to another bank with the same a changes the hash."""
        rng = random.Random(7)
        checked = 0
        for g in self.graphs:
            r = canon2.canonicalize(mv2.transform(rng, g))
            nl = t2.decode(r.canonical, (1, 2))
            for rec in nl.records:
                raw = rec.raw
                if raw.op == t2.OP_RAMR:
                    other = [b for b, (a, _) in sorted(nl.banks.items()) if a == raw.a and b != raw.bank]
                    if other:
                        d = bytearray(r.canonical)
                        d[raw.off + 1] = other[0]
                        self.assertNotEqual(canon2.structural_hash(bytes(d)), r.structural_hash)
                        checked += 1
                        break
        self.assertGreater(checked, 20)

    def test_unknown_records_rejected(self):
        """Opcodes that tapnet/2 does not define are rejected, never reinterpreted."""
        good = mv2.fx_ram_reg("base")
        for op in (0x02, 0x03, 0x14, 0xff):
            bad = good[:16] + bytes([op]) + good[17:]
            with self.assertRaises(Exception):
                canon2.canonicalize(bad)

    def test_bank_limit(self):
        """More than 256 plane nodes: no canonical file, an error instead of a hash."""
        b = mv2.B(9)
        gates = [b.nand(2 + i, 2 + k) for i in range(9) for k in range(i + 1, 9)]     # 36 distinct signals
        reads = []
        for bank in range(17):                          # 17 banks x 16 bits = 272 distinct planes
            b.write(bank, [2 + bank % 9], [gates[(bank * 16 + j) % 36] for j in range(16)], 2 + bank // 9)
            reads += b.read(bank, [2 + bank % 9], 16)
        acc = reads[0]
        for x in reads[1:]:
            acc = b.nand(acc, x)
        data = b.file(1)
        with self.assertRaises(canon2.TooLarge):
            canon2.canonicalize(data)


class Vectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "vectors2.json")) as f:
            cls.v = json.load(f)

    def test_reproducible(self):
        with open(os.path.join(HERE, "vectors2.json"), encoding="utf-8") as f:
            self.assertEqual(json.dumps(mv2.build(), indent=1, sort_keys=True) + "\n", f.read())

    def test_cases(self):
        for c in self.v["cases"]:
            data = bytes.fromhex(c["file"][2:])
            r = canon2.canonicalize(data)
            self.assertEqual("0x" + r.canonical.hex(), c["canonical"])
            self.assertEqual("0x" + r.structural_hash.hex(), c["structuralHash"])
            dom = canon2.HASH_DOMAIN1 if r.version == 1 else canon2.HASH_DOMAIN2
            self.assertEqual(r.structural_hash, canon2.hashlib.sha256(dom + r.canonical).digest())
            self.assertEqual(canon2.canonicalize(r.canonical).canonical, r.canonical)
            n_in = c["nIn"]
            rng = random.Random(c["name"])
            seqs = [[[rng.randrange(2) for _ in range(n_in)] for _ in range(6)] for _ in range(3)]
            self.assertEqual(run(data, seqs), run(r.canonical, seqs), c["name"])

    def test_groups_distinct_invalid(self):
        by = {c["name"]: c["structuralHash"] for c in self.v["cases"]}
        for g in self.v["equalGroups"]:
            self.assertEqual({by[m] for m in g["members"]}, {g["structuralHash"]})
        for d in self.v["distinct"]:
            a, b = d["members"]
            self.assertNotEqual(by[a], by[b])
        for c in self.v["invalid"]:
            with self.assertRaises(Exception):
                canon2.canonicalize(bytes.fromhex(c["file"][2:]))

    def test_ram_examples(self):
        by = {c["name"]: c for c in self.v["cases"]}
        self.assertEqual((by["ram16"]["planes"], by["ram16"]["ramNodes"]), (4, 8))
        self.assertEqual(by["rammix"]["planes"], 13)
        c = by["ram_out_equal_bits"]
        self.assertEqual((c["ramNodes"], c["planes"], c["copies"]), (1, 1, 1))
        self.assertEqual(by["xor_v2_dead_ram"]["canonicalVersion"], 1)
        # each distinct reduced table is stored once; the other columns become ROM read ports
        canon_bytes = bytes.fromhex(by["romports"]["canonical"][2:])
        nl = t2.decode(canon_bytes)
        self.assertEqual(nl.rom_records + nl.rom_ports, 15)
        self.assertLess(nl.rom_records, 15)


if __name__ == "__main__":
    unittest.main(verbosity=1)
