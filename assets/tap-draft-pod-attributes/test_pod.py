#!/usr/bin/env python3
"""Tests for the PoD-attributes draft tooling. Run: python3 test_pod.py  (no network; uses `cast` if installed)."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tap-draft-netlist-bound-nft"))

import pod_snapshot as ps  # noqa: E402
from pod_validate import validate_pod, validate_tap  # noqa: E402



def _json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


V = _json(os.path.join(HERE, "vectors.json"))
SNAP = _json(os.path.join(HERE, "..", "tap-draft-netlist-bound-nft", "chain-snapshot.json"))


def pods():
    return [c for c in V["cases"] if c.get("pod")] + V["optimalHolders"] + V["verifiedButWrong"]


class Reproducible(unittest.TestCase):
    def test_vectors_regenerate_byte_for_byte(self):
        files = ["vectors.json", "trait-metadata.json"]
        before = {f: _sha(os.path.join(HERE, f)) for f in files}
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_vectors.py")], cwd=HERE, stdout=subprocess.DEVNULL)
        after = {f: _sha(os.path.join(HERE, f)) for f in files}
        self.assertEqual(before, after)


class Formula(unittest.TestCase):
    def test_cost_examples(self):
        self.assertEqual(ps.cost(4, 3, 3), 108)
        self.assertEqual(ps.cost(64, 1, 3), 64)
        self.assertEqual(ps.cost(55, 16, 3), 225280)
        self.assertEqual(ps.cost(7, 0, 3), 7)  # max(d, 1)

    def test_pods_against_raw_getter_values(self):
        """Every pod field equals the getter value it is defined from (Specification §3.3), recomputed here."""
        by_id = {(e["processor"].lower(), str(e["circuitId"])): e for e in SNAP["circuits"]}
        raws = {}
        for f in sorted(os.listdir(os.path.join(HERE, "raw"))):
            if not f.startswith("raw"):
                continue
            r = _json(os.path.join(HERE, "raw", f))
            raws[(r["entry"]["processor"].lower(), str(r["entry"]["circuitId"]))] = r["entry"]
        lam, beta, lb = SNAP["mining"]["lambda"], SNAP["mining"]["beta"], SNAP["mining"]["lambdaBurn"]
        for c in pods():
            p = c["pod"]
            e = by_id.get((p["processor"], p["circuitId"])) or raws.get((p["processor"], p["circuitId"])) \
                or _json(os.path.join(HERE, c["source"]))["entry"]  # synthetic/ examples
            m = e["miner"]
            g, s, n, l = (int(m[k]) for k in ("gateCount", "stateCount", "nandBurn", "latchBurn"))
            d, a, b = int(m["depth"]), int(m["area"]), int(m["bstar"])
            with self.subTest(circuit=p["circuitId"]):
                self.assertEqual(p["block"], SNAP["block"])
                self.assertEqual(p["design"]["taskId"], int(m["taskId"]))
                self.assertEqual((p["design"]["nandBurn"], p["design"]["latchBurn"]), (n, l))
                self.assertEqual(p["design"]["area"], str(a))
                self.assertEqual(a, g + lam * s)          # A = g + λ·s
                self.assertEqual(b, n + lb * l)           # b* = n + λ_burn·m
                self.assertEqual(p["design"]["cost"], str(a * max(d, 1) ** beta))
                self.assertEqual(p["standing"]["optimal"], m["optimal"] == "true")
                self.assertEqual(p["standing"]["verifWeight"], m["verifWeight"])
                self.assertEqual(int(m["verifWeight"]), (b + int(m["bonus"])) * int(m["mult"]))  # H = (b* + K·q)·P
                self.assertEqual(p["design"]["task"]["kTask"], e["task"]["refArea"])
                self.assertEqual(p["design"]["task"]["cRef"], e["task"]["refCost"])

    def test_all_cross_checks_hold(self):
        for c in pods():
            for x in c["crossChecks"]:
                if x.get("informative"):
                    continue
                with self.subTest(circuit=c["pod"]["circuitId"], check=x["check"]):
                    self.assertTrue(x["ok"], x["detail"])

    def test_optimal_holders_confirm_cost(self):
        """For the optimal-slot holder, bestSlot().cost is the contract's own C and must equal ours."""
        for c in V["optimalHolders"]:
            self.assertTrue(c["pod"]["standing"]["optimal"])
            self.assertEqual(c["extraReads"]["bestSlot"]["cost"], c["pod"]["design"]["cost"])
            self.assertEqual(c["extraReads"]["bonusOfCost"], c["pod"]["standing"]["bonus"])

    def test_reader_agreement(self):
        self.assertEqual(len(V["readerAgreement"]), 3)
        for a in V["readerAgreement"]:
            self.assertEqual(a["differences"], [], a["circuit"])

    def test_no_record_case(self):
        c = next(c for c in V["cases"] if not c["hasMinerRecord"])
        self.assertIsNone(c["pod"])
        self.assertTrue(all(t["value"] == "0x" + "00" * 32 for t in c["traits"]))


class FunctionCheck(unittest.TestCase):
    def test_every_pod_has_a_check(self):
        for c in pods():
            self.assertIn("functionCheck", c["pod"], c["label"])

    def test_checks_reproduce_from_recorded_reads(self):
        import function_check as fc
        for c in pods():
            p = c["pod"]
            src = c.get("source")
            if src == "chain-snapshot.json":
                e = next(x for x in SNAP["circuits"] if str(x["circuitId"]) == p["circuitId"])
            else:
                e = _json(os.path.join(HERE, src))["entry"]
            ref = _json(os.path.join(HERE, "raw", f"ref-task{p['design']['taskId']}.json"))
            self.assertEqual((ref["processor"], str(ref["circuitId"])),
                             (e["task"]["refCircuits"].lower(), str(e["task"]["refCircuitId"])))
            self.assertEqual(ps.function_check_for(e, e["task"], ref), p["functionCheck"], c["label"])

    def test_exhaustive_counts(self):
        for c in pods():
            f = c["pod"]["functionCheck"]
            if f["method"] == "exhaustive" and f["result"] == "match":
                self.assertEqual(f["vectors"], 2 ** int(c["pod"]["circuitId"] and _nin(c)))

    def test_verified_is_not_correct(self):
        w = V["verifiedButWrong"]
        self.assertEqual(len(w), 1)
        self.assertIs(w[0]["synthetic"], True)
        self.assertTrue(w[0]["source"].startswith("synthetic/"))
        p = w[0]["pod"]
        self.assertTrue(p["standing"]["verified"])
        self.assertFalse(p["standing"]["optimal"])
        # cheaper than the slot holder recorded in bestSlot, yet not holding the slot
        self.assertLess(int(p["design"]["cost"]), int(w[0]["extraReads"]["bestSlot"]["cost"]))
        self.assertEqual((p["functionCheck"]["method"], p["functionCheck"]["result"]), ("exhaustive", "mismatch"))
        for c in V["cases"][:3] + V["optimalHolders"]:
            self.assertEqual(c["pod"]["functionCheck"]["result"], "match", c["label"])

    def test_manifest_commitment(self):
        for c in V["manifestCommitment"]:
            with self.subTest(label=c["label"]):
                self.assertEqual(bool(c["valid"]), not c["errors"])
                if c["expect"]:
                    self.assertTrue(any(c["expect"] in x for x in c["errors"] + c["warnings"]), c)


def _nin(c):
    src = c.get("source")
    if src == "chain-snapshot.json":
        return next(x for x in SNAP["circuits"] if str(x["circuitId"]) == c["pod"]["circuitId"])["nIn"]
    return _json(os.path.join(HERE, src))["entry"]["nIn"]


class Traits(unittest.TestCase):
    def test_keys_are_keccak_of_names(self):
        self.assertEqual(ps.keccak256(b""), "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        have_cast = shutil.which("cast") is not None
        for t in V["traitKeys"]:
            with self.subTest(name=t["name"]):
                self.assertEqual(t["key"], ps.trait_key(t["name"]))
                if have_cast:
                    self.assertEqual(t["key"], subprocess.check_output(["cast", "keccak", t["name"]], text=True).strip())

    def test_names_unique_and_prefixed(self):
        names = [t["name"] for t in V["traitKeys"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(n.startswith("tap.pod.") for n in names))
        disp = [t["displayName"] for t in V["traitSchema"]["traits"].values()]
        self.assertEqual(len(disp), len(set(disp)))

    def test_schema_shape(self):
        for name, t in V["traitSchema"]["traits"].items():
            self.assertFalse(name.startswith("0x"))
            self.assertIn(t["dataType"]["type"], ("decimal", "boolean"))
            if t["dataType"]["type"] == "decimal":
                self.assertEqual((t["dataType"]["signed"], t["dataType"]["decimals"]), (False, 0))
            self.assertFalse(t["tokenOwnerCanUpdateValue"])

    def test_values_decode_back(self):
        for c in pods():
            p = c["pod"]
            for t in c["traits"]:
                n = int(t["value"], 16)
                self.assertEqual(len(t["value"]), 66)
                src = dict((a, b) for a, _, b in ps.TRAITS)[t["name"]]
                v = ps._get(p, src)
                self.assertEqual(n, int(v) if not isinstance(v, bool) else int(v), t["name"])
            self.assertNotEqual(int(c["traits"][0]["value"], 16), 0)  # snapshotBlock is the presence marker


class Validator(unittest.TestCase):
    def test_valid_pods(self):
        for c in pods():
            r = validate_pod(c["pod"])
            self.assertTrue(r.ok, r.errors)
            self.assertEqual(r.warnings, [])

    def test_invalid_vectors(self):
        for c in V["invalid"]:
            with self.subTest(label=c["label"]):
                r = validate_pod(c["pod"])
                self.assertFalse(r.ok)
                self.assertTrue(any(c["expectError"] in e for e in r.errors), r.errors)

    def test_unknown_status_is_labelled_unknown(self):
        p = copy.deepcopy(pods()[0]["pod"])
        p["standing"].update(status=2, statusLabel="unknown")
        r = validate_pod(p)
        self.assertTrue(r.ok, r.errors)
        self.assertTrue(any("no known meaning" in w for w in r.warnings))

    def test_status_3_is_unknown(self):
        self.assertEqual(ps.status_label(1), "mining")
        self.assertEqual(ps.status_label(3), "unknown")
        p = copy.deepcopy(pods()[0]["pod"])
        p["standing"].update(status=3, statusLabel="restartable")
        self.assertFalse(validate_pod(p).ok)

    def test_ref_circuit_has_no_record(self):
        e = next(c for c in SNAP["circuits"] if str(c["circuitId"]) == "38")
        with self.assertRaises(ValueError):
            ps.count_records(e["netlist"])

    def test_unknown_implementation_warns(self):
        p = copy.deepcopy(pods()[0]["pod"])
        p["implementation"] = "0x" + "ab" * 20
        r = validate_pod(p)
        self.assertTrue(r.ok)
        self.assertTrue(any("implementation" in w for w in r.warnings))

    def test_metadata_example(self):
        doc = V["metadataExample"]["document"]
        r = validate_tap(doc["tap"])
        self.assertTrue(r.ok, r.errors)
        self.assertEqual(r.warnings, [])
        try:
            import tapnft
        except ImportError:
            self.skipTest("draft A reference implementation not found")
        meta = dict(doc, image="ipfs://example")
        tap = dict(meta["tap"], image={"sha256": "0x" + "11" * 32, "uris": ["ipfs://example"]})
        tapnft.check_metadata(dict(meta, tap=tap))  # draft A accepts the extra members

    def test_source_mismatch_and_rig(self):
        tap = copy.deepcopy(V["metadataExample"]["document"]["tap"])
        tap["source"]["circuitId"] = "1"
        self.assertTrue(any("circuitId" in e for e in validate_tap(tap).errors))
        tap = copy.deepcopy(V["metadataExample"]["document"]["tap"])
        del tap["source"]
        self.assertTrue(any("tap.source" in e for e in validate_tap(tap).errors))
        tap = copy.deepcopy(V["metadataExample"]["document"]["tap"])
        tap["rig"]["contract"] = "0x" + "00" * 20
        self.assertTrue(any("tap.rig.contract" in e for e in validate_tap(tap).errors))
        tap["rig"] = {"chainId": 196, "contract": ps.RIG_VOUCHER["contract"], "id": 5}
        self.assertTrue(any("tap.rig.id" in e for e in validate_tap(tap).errors))

    def test_netlist_count_mismatch_warns(self):
        tap = copy.deepcopy(V["metadataExample"]["document"]["tap"])
        tap["netlist"]["nand"] += 1
        r = validate_tap(tap)
        self.assertTrue(r.ok)
        self.assertTrue(any("nandBurn" in w for w in r.warnings))


class Records(unittest.TestCase):
    def test_count_records(self):
        self.assertEqual(ps.count_records("0x" + "00000002000003" + "01000004"), (1, 1))
        with self.assertRaises(ValueError):
            ps.count_records("0x02000000")
        with self.assertRaises(ValueError):
            ps.count_records("0x000000")


if __name__ == "__main__":
    unittest.main(verbosity=1)
