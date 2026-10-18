"""Tests for tapnft.py and the published vectors. Run: python3 test_tapnft.py (Python 3.9+, stdlib only)."""
from __future__ import annotations

import json
import random
import unittest
from pathlib import Path

import make_vectors as MV
import tapnft as T

HERE = Path(__file__).resolve().parent
RNG_SEED = 20261018


def unhex(s: str) -> bytes:
    return bytes.fromhex(s[2:])


class Regeneration(unittest.TestCase):
    """make_vectors.build() must reproduce vectors.json and example/ byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.doc, cls.files = MV.build()
        cls.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))

    def test_vectors_bytes(self):
        self.assertEqual((HERE / "vectors.json").read_bytes(), self.files["vectors.json"])

    def test_vectors_structure(self):
        self.assertEqual(self.vec, json.loads(json.dumps(self.doc)))

    def test_example_files(self):
        for rel, data in self.files.items():
            with self.subTest(rel=rel):
                self.assertEqual((HERE / rel).read_bytes(), data)

    def test_pinned_chain_matches_snapshot(self):
        snap_path = HERE / "chain-snapshot.json"
        if not snap_path.exists():
            self.skipTest("chain-snapshot.json not present")
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        if snap["block"] != MV.load_chain()["block"]:
            self.skipTest("snapshot was re-taken at another block")
        pinned = {(c["processor"].lower(), c["circuitId"]): c for c in MV.load_chain()["circuits"]}
        for c in snap["circuits"]:
            p = pinned[(c["processor"].lower(), c["circuitId"])]
            for k in ("nIn", "nOut", "nState", "gateCount", "netlist"):
                self.assertEqual(p[k], c[k], (c["circuitId"], k))


class TapnetVectors(unittest.TestCase):
    def setUp(self):
        self.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))

    def test_chain_circuits(self):
        for v in self.vec["tapnet"]:
            data = unhex(v["file"])
            with self.subTest(name=v["source"]["name"]):
                self.assertEqual(T.hex32(T.netlist_hash(data)), v["netlistHash"])
                ci = v["circuitInfo"]
                self.assertEqual(data[:16], T.MAGIC + b"\x01\x00" + ci["nIn"].to_bytes(4, "big") + ci["nOut"].to_bytes(4, "big"))
                if v["valid"]:
                    mt = T.check_file(data)
                    self.assertEqual(dict(mt.as_json(), gates=mt.gates, bytes=len(data)), v["metrics"])
                    self.assertEqual(mt.gates, ci["gateCount"])
                    self.assertEqual(mt.latch, ci["nState"])
                else:
                    with self.assertRaises(T.Invalid) as cm:
                        T.check_file(data)
                    self.assertEqual(str(cm.exception), v["reason"])

    def test_some_circuit_rejected_for_ref(self):
        self.assertTrue(any(not v["valid"] and "REF" in v["reason"] for v in self.vec["tapnet"]))

    def test_invalid_files(self):
        for v in self.vec["invalidFiles"]:
            with self.subTest(name=v["name"]):
                with self.assertRaises(T.Invalid) as cm:
                    T.check_file(unhex(v["file"]))
                self.assertEqual(str(cm.exception), v["error"])


class Merkle(unittest.TestCase):
    def test_vectors(self):
        vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["merkle"]
        for p in vec["pools"]:
            leaves = [unhex(x) for x in p["leaves"]]
            for i, vals in enumerate(p["values"]):
                self.assertEqual(T.leaf_hash(i, [unhex(x) for x in vals]), leaves[i])
            root = unhex(p["root"])
            self.assertEqual(T.merkle_root(leaves), root)
            for i, proof in enumerate(p["proofs"]):
                self.assertTrue(T.merkle_verify(root, p["size"], i, leaves[i], [unhex(x) for x in proof]))
        for n in vec["negatives"]:
            self.assertFalse(T.merkle_verify(unhex(n["root"]), n["size"], n["index"], unhex(n["leaf"]),
                                             [unhex(x) for x in n["proof"]]), n["name"])

    def test_round_trips(self):
        rng = random.Random(RNG_SEED)
        for size in list(range(1, 70)) + [rng.randrange(70, 600) for _ in range(5)]:
            leaves = [T.leaf_hash(i, [rng.randbytes(32) if hasattr(rng, "randbytes") else bytes(rng.getrandbits(8) for _ in range(32))])
                      for i in range(size)]
            root = T.merkle_root(leaves)
            for i in range(size):
                proof = T.merkle_proof(leaves, i)
                self.assertTrue(T.merkle_verify(root, size, i, leaves[i], proof))
                # proof length = number of levels where the node had a sibling
                self.assertLessEqual(len(proof), max(0, (size - 1).bit_length()))
                if size > 1:
                    j = (i + 1) % size
                    self.assertFalse(T.merkle_verify(root, size, j, leaves[i], proof))
                    self.assertFalse(T.merkle_verify(root, size, i, leaves[i], proof + [leaves[0]]))
                    if proof:
                        self.assertFalse(T.merkle_verify(root, size, i, leaves[i], proof[:-1]))
                self.assertFalse(T.merkle_verify(root, size, i, T.sha256(leaves[i]), proof))
                self.assertFalse(T.merkle_verify(root, size, size, leaves[i], proof))

    def test_levels_fast_path(self):
        rng = random.Random(RNG_SEED)
        for size in list(range(1, 80)) + [rng.randrange(80, 400) for _ in range(3)]:
            leaves = [T.sha256(b"%d %d" % (size, i)) for i in range(size)]
            levels = T.merkle_levels(leaves)
            self.assertEqual(levels[0], leaves)
            self.assertEqual(levels[-1], [T.merkle_root(leaves)])
            for i in range(size):
                self.assertEqual(T.merkle_proof_from_levels(levels, i), T.merkle_proof(leaves, i))
            for bad in (size, -1):
                with self.assertRaises(T.Invalid):
                    T.merkle_proof_from_levels(levels, bad)

    def test_errors(self):
        leaves = [T.leaf_hash(i, [bytes(32)]) for i in range(4)]
        for bad in (4, 5, -1):
            with self.assertRaises(T.Invalid):
                T.merkle_proof(leaves, bad)
        with self.assertRaises(T.Invalid):
            T.leaf_hash(0, [bytes(33)])
        self.assertEqual([e["name"] for e in json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["merkle"]["errors"]],
                         ["proof_index_equals_size", "proof_index_negative", "root_of_empty_pool", "leaf_value_31_bytes"])

    def test_single_leaf(self):
        leaf = T.leaf_hash(0, [b"\x11" * 32])
        self.assertEqual(T.merkle_root([leaf]), leaf)
        self.assertEqual(T.merkle_proof([leaf], 0), [])


class Permutation(unittest.TestCase):
    def test_vectors(self):
        vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["permutation"]
        for s in vec["seeds"]:
            self.assertEqual(T.hex32(T.pool_seed(unhex(s["masterSeed"]), s["chainId"], s["collection"], s["label"])), s["poolSeed"])
        seed = unhex(vec["permuteSeed"]["poolSeed"])
        for p in vec["permutations"]:
            ys = [T.permute(seed, p["n"], x) for x in range(p["n"])]
            self.assertEqual(ys, p["output"])
            self.assertEqual(sorted(ys), list(range(p["n"])))
        big = vec["large"]
        ys = [T.permute(seed, big["n"], x) for x in range(big["n"])]
        self.assertEqual(ys[:64], big["first64"])
        self.assertEqual(T.hex32(T.sha256(MV.u32s(ys))), big["sha256OfU32be"])
        self.assertEqual(sorted(ys), list(range(big["n"])))

    def test_seed_errors(self):
        vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["permutation"]
        for e in vec["seedErrors"]:
            with self.assertRaises(T.Invalid) as cm:
                T.pool_seed(unhex(e["masterSeed"]), e["chainId"], e["collection"], e["label"])
            self.assertEqual(str(cm.exception), e["error"])
        seed = unhex(vec["permuteSeed"]["poolSeed"])
        for e in vec["permuteErrors"]:
            with self.assertRaises(T.Invalid) as cm:
                T.permute(seed, e["n"], e["index"])
            self.assertEqual(str(cm.exception), e["error"])

    def test_bijection_random_sizes(self):
        rng = random.Random(RNG_SEED)
        sizes = list(range(1, 65)) + [rng.randrange(65, 3000) for _ in range(40)] + [4096, 4097]
        for n in sizes:
            seed = T.sha256(b"seed %d" % rng.getrandbits(64))
            ys = [T.permute(seed, n, x) for x in range(n)]
            self.assertEqual(sorted(ys), list(range(n)), n)

    def test_domain(self):
        # 4^h >= n and the Feistel network alone is a bijection of the 4^h domain
        rng = random.Random(RNG_SEED)
        for n in [2, 3, 5, 17, 100, 1 << 12, (1 << 12) + 1]:
            half = T._half_bits(n)
            self.assertGreaterEqual(1 << (2 * half), n)
            seed = T.sha256(bytes([n & 0xff]))
            dom = 1 << (2 * half)
            if dom <= 1 << 14:
                self.assertEqual(sorted(T._feistel(seed, v, half) for v in range(dom)), list(range(dom)))
        with self.assertRaises(T.Invalid):
            T.permute(b"\x00" * 32, 5, 5)
        with self.assertRaises(T.Invalid):
            T.permute(b"\x00" * 32, 5, -1)


class Metadata(unittest.TestCase):
    def setUp(self):
        self.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))

    def test_valid(self):
        for v in self.vec["metadata"]["valid"]:
            self.assertEqual(T.check_metadata(v["document"])["state"], v["document"]["tap"]["state"])

    def test_invalid(self):
        for v in self.vec["metadata"]["invalid"]:
            with self.subTest(name=v["name"]):
                with self.assertRaises(T.Invalid) as cm:
                    T.check_metadata(v["document"])
                self.assertEqual(str(cm.exception), v["error"])

    def test_editions(self):
        import copy
        ed = self.vec["editions"]
        docs = [t["metadata"] for t in self.vec["example"]["tokens"]]
        T.check_editions(docs)
        self.assertEqual(len(ed["invalid"]), 3)
        for c in ed["invalid"]:
            with self.subTest(name=c["name"]):
                ds = copy.deepcopy(docs)
                tap = ds[c["tokenId"] - 1]["tap"]
                if c["edition"] is None:
                    del tap["edition"]
                else:
                    tap["edition"] = c["edition"]
                T.check_metadata(ds[c["tokenId"] - 1])
                with self.assertRaises(T.Invalid) as cm:
                    T.check_editions(ds)
                self.assertEqual(str(cm.exception), c["error"])

    def test_netlist_checks(self):
        files = {v["source"]["name"]: unhex(v["file"]) for v in self.vec["tapnet"]}
        for c in self.vec["netlistChecks"]:
            if c["error"] is None:
                T.check_netlist_against_metadata({"netlist": c["netlist"]}, files[c["file"]])
            else:
                with self.assertRaises(T.Invalid) as cm:
                    T.check_netlist_against_metadata({"netlist": c["netlist"]}, files[c["file"]])
                self.assertEqual(str(cm.exception), c["error"])


class Manifests(unittest.TestCase):
    def setUp(self):
        self.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["manifests"]

    def test_valid(self):
        for v in self.vec["valid"]:
            data = v["manifest"].encode("utf-8")
            self.assertEqual(T.hex32(T.sha256(data)), v["sha256"])
            T.check_manifest(data)

    def test_invalid(self):
        for v in self.vec["invalid"]:
            with self.subTest(name=v["name"]):
                data = v["manifest"].encode("utf-8") if "manifest" in v else unhex(v["manifestHex"])
                with self.assertRaises(T.Invalid) as cm:
                    T.check_manifest(data)
                self.assertEqual(str(cm.exception), v["error"])

    def test_example_manifest_file(self):
        man = T.check_manifest((HERE / MV.EXAMPLE_DIR / "manifest.json").read_bytes())
        self.assertNotIn("0x", man["reveal"]["chainHash"])


class TokenSets(unittest.TestCase):
    def setUp(self):
        self.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["tokenSets"]

    def test_small(self):
        sm = self.vec["small"]
        man = T.check_manifest(sm["manifest"].encode("utf-8"))
        ids = T.check_token_set(man, unhex(sm["file"]))
        self.assertEqual(ids, sm["ids"])
        self.assertEqual(T.hex32(T.token_set_hash(ids)), sm["sha256"])
        for tok in sm["tokens"]:
            self.assertEqual(T.assignment(man, unhex(sm["masterSeed"]), tok["tokenId"], ids), tok["entries"])
            if tok["entries"] is None:
                with self.assertRaises(T.Invalid):
                    T.token_index(ids, tok["tokenId"])
            else:
                self.assertEqual(T.token_index(ids, tok["tokenId"]), tok["index"])

    def test_large(self):
        lg = self.vec["large"]
        rng = random.Random(MV.TS_RNG_SEED)
        rng.sample(range(1, 21), 10)
        ids = sorted(rng.sample(range(1, 10001), lg["count"]))
        self.assertEqual(T.hex32(T.token_set_hash(ids)), lg["sha256"])
        seed = T.pool_seed(unhex(lg["masterSeed"]), lg["chainId"], lg["collection"], lg["label"])
        self.assertEqual(T.hex32(seed), lg["poolSeed"])
        ys = [T.permute(seed, len(ids), T.token_index(ids, t)) for t in ids]
        self.assertEqual(sorted(ys), list(range(len(ids))))
        self.assertEqual([{"tokenId": t, "index": i, "entry": ys[i]} for i, t in enumerate(ids[:32])], lg["first32"])
        self.assertEqual(T.hex32(T.sha256(MV.u32s(ys))), lg["sha256OfEntriesU32be"])

    def test_errors(self):
        man = json.loads(self.vec["small"]["manifest"])
        for e in self.vec["fileErrors"]:
            with self.assertRaises(T.Invalid) as cm:
                T.check_token_set(man, unhex(e["file"]))
            self.assertEqual(str(cm.exception), e["error"])
        for e in self.vec["hashErrors"]:
            with self.assertRaises(T.Invalid) as cm:
                T.token_set_hash(e["ids"])
            self.assertEqual(str(cm.exception), e["error"])

    def test_range_mode_assignment_matches_example(self):
        ex = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["example"]
        man = json.loads(ex["manifestText"])
        for tok in ex["tokens"]:
            self.assertEqual(T.assignment(man, unhex(ex["masterSeed"]), tok["tokenId"]),
                             {"IMAGE_V1": tok["imageEntry"], "NETLIST_V1": tok["netlistEntry"]})
        self.assertIsNone(T.assignment(man, unhex(ex["masterSeed"]), 0))
        self.assertIsNone(T.assignment(man, unhex(ex["masterSeed"]), 9))


class ContentAndPlaceholders(unittest.TestCase):
    def setUp(self):
        self.vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))

    def test_content(self):
        for v in self.vec["content"]["valid"]:
            T.check_metadata(v["document"])
        for v in self.vec["content"]["invalid"]:
            with self.subTest(name=v["name"]):
                with self.assertRaises(T.Invalid) as cm:
                    T.check_metadata(v["document"])
                self.assertEqual(str(cm.exception), v["error"])

    def test_placeholders(self):
        ph = self.vec["placeholders"]
        self.assertNotIn(ph["tokenId"], self.vec["tokenSets"]["small"]["ids"])
        for v in ph["valid"]:
            self.assertEqual(T.check_metadata(v["document"], outside_token_set=True)["state"], "unrevealed")
        for v in ph["validAwaitingReveal"]:
            T.check_metadata(v["document"])
            with self.assertRaises(T.Invalid):
                T.check_metadata(v["document"], outside_token_set=True)
        for v in ph["invalid"]:
            with self.subTest(name=v["name"]):
                with self.assertRaises(T.Invalid) as cm:
                    T.check_metadata(v["document"], outside_token_set=True)
                self.assertEqual(str(cm.exception), v["error"])

    def test_cli_set_mode_manifest(self):
        import subprocess, sys, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "set-manifest.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.vec["tokenSets"]["small"]["manifest"])
            out = subprocess.run([sys.executable, str(HERE / "tapnft.py"), path], capture_output=True, text=True, cwd=str(HERE))
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("token set of 10", out.stdout)


class Example(unittest.TestCase):
    """Re-derive the worked example from the files on disk, as an independent verifier would."""

    def test_collection(self):
        vec = json.loads((HERE / "vectors.json").read_text(encoding="utf-8"))["example"]
        man_bytes = (HERE / vec["manifestPath"]).read_bytes()
        self.assertEqual(T.hex32(T.sha256(man_bytes)), vec["manifestSha256"])
        man = json.loads(man_bytes)
        col = man["collection"]
        supply = col["supply"]
        master = unhex(vec["masterSeed"])
        pools = {}
        for p in man["pools"]:
            self.assertEqual(len(p["entries"]), supply)
            leaves = [T.leaf_hash(i, [unhex(e[f]) for f, _ in T.FIELD_ORDER if f in p["fields"]])
                      for i, e in enumerate(p["entries"])]
            self.assertEqual(T.hex32(T.merkle_root(leaves)), p["root"])
            pools[p["label"]] = (p, leaves, T.pool_seed(master, col["chainId"], col["address"], p["label"]))
        netfiles = {}
        for rel in vec["netlistFiles"]:
            data = (HERE / rel).read_bytes()
            T.check_file(data)
            netfiles[T.hex32(T.netlist_hash(data))] = data
        seen = {}
        for tid in range(col["firstTokenId"], col["firstTokenId"] + supply):
            doc = json.loads((HERE / MV.EXAMPLE_DIR / "token" / f"{tid}.json").read_bytes())
            tap = T.check_metadata(doc)
            self.assertEqual(tap["id"], f"eip155:{col['chainId']}/erc721:{col['address']}/{tid}")
            self.assertEqual(tap["manifest"]["sha256"], vec["manifestSha256"])
            x = tid - col["firstTokenId"]
            ip, il, iseed = pools["IMAGE_V1"]
            np_, nl, nseed = pools["NETLIST_V1"]
            ie, ne = T.permute(iseed, supply, x), T.permute(nseed, supply, x)
            self.assertEqual(tap["image"]["sha256"], ip["entries"][ie]["image"])
            self.assertEqual(tap["netlist"]["sha256"], np_["entries"][ne]["netlist"])
            T.check_netlist_against_metadata(tap, netfiles[tap["netlist"]["sha256"]])
            t = vec["tokens"][x]
            self.assertEqual((t["imageEntry"], t["netlistEntry"]), (ie, ne))
            self.assertTrue(T.merkle_verify(unhex(ip["root"]), supply, ie, il[ie], [unhex(p) for p in t["imageProof"]]))
            self.assertTrue(T.merkle_verify(unhex(np_["root"]), supply, ne, nl[ne], [unhex(p) for p in t["netlistProof"]]))
            seen.setdefault(tap["netlist"]["sha256"], []).append((tid, tap.get("edition")))
        for nh, toks in seen.items():
            for rank, (tid, ed) in enumerate(sorted(toks), 1):
                if len(toks) > 1:
                    self.assertEqual(ed, {"index": rank, "of": len(toks)}, tid)
                else:
                    self.assertIsNone(ed)
        self.assertTrue(any(len(v) > 1 for v in seen.values()), "example should contain editions")
        T.check_editions([json.loads(p.read_bytes()) for p in sorted((HERE / MV.EXAMPLE_DIR / "token").glob("*.json"))])


if __name__ == "__main__":
    unittest.main(verbosity=1)
