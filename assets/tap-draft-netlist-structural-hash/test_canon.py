"""Tests for the reference implementation of "Structural Hash of Flat Netlists". MIT licence.

python3 test_canon.py
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import unittest

import canon
import make_vectors as mv
from canon import tap02, tapnft

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 7051
N_RANDOM = 300


def run(data: bytes, seqs):
    n_in, n_out, rec = tapnft.decode_file(data)
    c = tap02.load(rec, n_in, n_out)
    res = []
    for seq in seqs:
        st, outs = [0] * c.n_state, []
        for x in seq:
            st, o = tap02.beat(c, st, x)
            outs.append(tuple(o))
        res.append(outs)
    return res


def random_graph_biased(rng):
    """Random netlists whose outputs read recent elements, so that most of the netlist is live."""
    n_in = rng.randint(0, 4)
    n_el = rng.randint(2, 40)
    n_out = rng.randint(1, min(3, n_el))
    nodes = {}

    def ref(limit):
        if limit > 2 + n_in and rng.random() < 0.75:
            s = rng.randrange(max(2 + n_in, limit - 6), limit)
        else:
            s = rng.randrange(limit)
        return ("c", s) if s < 2 else ("i", s - 2) if s < 2 + n_in else ("e", s - 2 - n_in)
    for k in range(n_el):
        if rng.random() < 0.25:
            nodes[k] = (tap02.LATCH, [ref(2 + n_in + n_el)])
        else:
            nodes[k] = (tap02.NAND, [ref(2 + n_in + k), ref(2 + n_in + k)])
    return n_in, n_out, nodes, [n_el - n_out + j for j in range(n_out)]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = random.Random(SEED)
        cls.graphs = [random_graph_biased(rng) if i % 2 else mv.random_graph(rng) for i in range(N_RANDOM)]


class Invariance(Base):
    def test_renumbering(self):
        rng = random.Random(SEED + 1)
        for g in self.graphs:
            h = canon.structural_hash(mv.file_from_graph(g))
            for _ in range(3):
                self.assertEqual(h, canon.structural_hash(mv.file_from_graph(g, mv.random_order(rng, g))))

    def test_input_swaps(self):
        rng = random.Random(SEED + 2)
        for g in self.graphs:
            self.assertEqual(canon.structural_hash(mv.file_from_graph(g)),
                             canon.structural_hash(mv.file_from_graph(mv.t_swap(rng, g))))

    def test_dead_elements(self):
        rng = random.Random(SEED + 3)
        for g in self.graphs:
            g2 = mv.t_dead(rng, g, count=rng.randint(1, 8))
            self.assertEqual(canon.structural_hash(mv.file_from_graph(g)),
                             canon.structural_hash(mv.file_from_graph(g2, mv.random_order(rng, g2))))

    def test_duplication(self):
        rng = random.Random(SEED + 4)
        for g in self.graphs:
            g2 = mv.t_dup(rng, g, count=rng.randint(1, 6))
            self.assertEqual(canon.structural_hash(mv.file_from_graph(g)),
                             canon.structural_hash(mv.file_from_graph(g2, mv.random_order(rng, g2))))

    def test_latch_duplication_with_feedback(self):
        rng = random.Random(SEED + 5)
        hit = 0
        for g in self.graphs:
            latches = [k for k in sorted(g[2]) if g[2][k][0] == tap02.LATCH]
            if not latches:
                continue
            n_in, n_out, nodes, outs = g
            nodes = {k: (op, list(r)) for k, (op, r) in nodes.items()}
            k = rng.choice(latches)
            nk = max(nodes) + 1
            nodes[nk] = (tap02.LATCH, list(nodes[k][1]))
            if nodes[k][1] == [("e", k)]:
                nodes[nk] = (tap02.LATCH, [("e", nk)])     # a self-holding copy holds itself
                hit += 1
            for j in sorted(nodes):
                for p, r in enumerate(nodes[j][1]):
                    if r == ("e", k) and j != k and rng.random() < 0.5:
                        nodes[j][1][p] = ("e", nk)
                        hit += 1
            g2 = (n_in, n_out, nodes, outs)
            self.assertEqual(canon.structural_hash(mv.file_from_graph(g)),
                             canon.structural_hash(mv.file_from_graph(g2, mv.random_order(rng, g2))))
        self.assertGreater(hit, 20)

    def test_combined(self):
        rng = random.Random(SEED + 6)
        for g in self.graphs:
            h = canon.structural_hash(mv.file_from_graph(g))
            for _ in range(2):
                self.assertEqual(h, canon.structural_hash(mv.transform(rng, g)))


class Properties(Base):
    def test_canonical_is_valid_equivalent_idempotent(self):
        rng = random.Random(SEED + 7)
        for g in self.graphs:
            data = mv.file_from_graph(g)
            r = canon.canonicalize(data)
            m = tapnft.check_file(r.canonical)
            n_in, n_out, _ = tapnft.decode_file(data)
            self.assertEqual((m.n_in, m.n_out), (n_in, n_out))
            self.assertEqual(canon.canonical_file(r.canonical), r.canonical)          # idempotence
            seqs = [[[rng.randint(0, 1) for _ in range(n_in)] for _ in range(10)] for _ in range(6)]
            self.assertEqual(run(data, seqs), run(r.canonical, seqs))               # same outputs
            self.assertLessEqual(m.gates, r.live + n_out)

    def test_hash_definition(self):
        data = mv.file_from_graph(self.graphs[0])
        r = canon.canonicalize(data)
        self.assertEqual(r.structural_hash, hashlib.sha256(b"tap-structural-hash/1\x00" + r.canonical).digest())

    def test_distinct_designs(self):
        """Different random netlists with different behaviour must not collide."""
        rng = random.Random(SEED + 8)
        seen = {}
        for g in self.graphs:
            data = mv.file_from_graph(g)
            n_in = g[0]
            seqs = [[[rng.randint(0, 1) for _ in range(n_in)] for _ in range(8)] for _ in range(4)]
            h = canon.structural_hash(data)
            if h in seen:
                other, oseqs = seen[h]
                self.assertEqual(run(other, oseqs), run(data, oseqs))
            else:
                seen[h] = (data, seqs)

    def test_size_bound(self):
        data = mv.file_from_graph(self.graphs[0])
        with self.assertRaises(canon.TooLarge):
            canon.canonicalize(data, max_gates=0)

    def test_long_shift_register_is_linear(self):
        """A 3,000-stage shift register: no refinement rounds (acyclic), so it is fast."""
        n = 3000
        recs = [("L", 2 + 1 + k + 1) for k in range(n - 1)] + [("L", 2)] + [("N", 3, 3)]
        r = canon.canonicalize(mv.F(1, 1, recs))
        self.assertEqual((r.cyclic, r.rounds, r.nodes), (0, 0, n + 1))


class LongRing(unittest.TestCase):
    def test_ring_cost(self):
        """A 200-LATCH ring with one tap needs about 200 rounds: the quadratic worst case is bounded by size."""
        n = 200
        recs = [("L", 2 + k + 1) for k in range(n - 1)] + [("L", 2 + n + 1)] + [("N", 2, 2), ("N", 2 + n, 2 + n)]
        r = canon.canonicalize(mv.F(0, 1, recs))
        self.assertEqual(r.cyclic, n + 2)
        self.assertGreaterEqual(r.rounds, n - 2)
        self.assertEqual(canon.canonical_file(r.canonical), r.canonical)


class Vectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(HERE, "vectors.json")) as f:
            cls.doc = json.load(f)
        cls.by = {c["name"]: c for c in cls.doc["cases"]}

    def test_cases(self):
        for c in self.doc["cases"]:
            data = bytes.fromhex(c["file"][2:])
            r = canon.canonicalize(data)
            self.assertEqual("0x" + r.canonical.hex(), c["canonical"], c["name"])
            self.assertEqual(tapnft.hex32(r.structural_hash), c["structuralHash"], c["name"])
            self.assertEqual((r.live, r.nodes, r.cyclic, r.rounds, r.copies),
                             (c["live"], c["nodes"], c["cyclic"], c["rounds"], c["copies"]), c["name"])

    def test_groups(self):
        for g in self.doc["equalGroups"]:
            self.assertEqual({self.by[m]["structuralHash"] for m in g["members"]}, {g["structuralHash"]})
        for d in self.doc["distinct"]:
            a, b = d["members"]
            self.assertNotEqual(self.by[a]["structuralHash"], self.by[b]["structuralHash"])

    def test_invalid(self):
        for c in self.doc["invalid"]:
            with self.assertRaises(tapnft.Invalid, msg=c["name"]):
                canon.canonicalize(bytes.fromhex(c["file"][2:]))

    def test_mainnet_xor(self):
        c = self.by["xor_17851"]
        self.assertEqual(c["file"], "0x" + tapnft.file_from_chain(mv.XOR_17851, 2, 1).hex())
        data = bytes.fromhex(c["file"][2:])
        table = run(data, [[[a, b]] for a in (0, 1) for b in (0, 1)])
        self.assertEqual([t[0][0] for t in table], [0, 1, 1, 0])

    def test_chain_snapshot(self):
        rng = random.Random(SEED + 9)
        for c in self.doc["chainSnapshot"]:
            data = bytes.fromhex(c["file"][2:])
            r = canon.canonicalize(data)
            self.assertEqual(tapnft.hex32(r.structural_hash), c["structuralHash"])
            self.assertEqual("0x" + r.canonical.hex(), c["canonical"])
            seqs = [[[rng.randint(0, 1) for _ in range(c["nIn"])] for _ in range(20)] for _ in range(4)]
            self.assertEqual(run(data, seqs), run(r.canonical, seqs))

    def test_reproducible(self):
        text = json.dumps(mv.build(), indent=1, sort_keys=True) + "\n"
        with open(os.path.join(HERE, "vectors.json")) as f:
            self.assertEqual(text, f.read())


if __name__ == "__main__":
    unittest.main(verbosity=1)
