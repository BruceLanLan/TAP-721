#!/usr/bin/env python3
"""Offline tests of the family checker against the vectors of every asset folder and the recorded-RPC fixture.

  python3 test_family_checker.py        (Python 3.9+; pycryptodome for the PoD cases, skipped without it)

No network: every chain read comes from fixtures/recorded-rpc.json.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import _paths as P  # noqa: E402
import chain as C  # noqa: E402
import make_fixture as MF  # noqa: E402
import tapfam  # noqa: E402

A721 = P.TAPNFT_DIR
V721 = json.load(open(os.path.join(A721, "vectors.json"), encoding="utf-8"))
VSH = json.load(open(os.path.join(P.CANON_DIR, "vectors.json"), encoding="utf-8"))
VCR = json.load(open(os.path.join(P.CREDITS_DIR, "vectors.json"), encoding="utf-8"))
VSB = json.load(open(os.path.join(P.SOULBOUND_DIR, "vectors.json"), encoding="utf-8"))
VPOD = json.load(open(os.path.join(P.POD_DIR, "vectors.json"), encoding="utf-8"))
EXAMPLE_MANIFEST = os.path.join(A721, "example", "manifest.json")
EXAMPLE_TOKENS = os.path.join(A721, "example", "token")
TMP = tempfile.mkdtemp(prefix="tapfam-test-")


def write_json(name: str, doc) -> str:
    path = os.path.join(TMP, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f)
    return path


def write_bytes(name: str, data: bytes) -> str:
    path = os.path.join(TMP, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def netlist_path(h: str) -> str:
    return os.path.join(A721, "example", "netlists", h[2:] + ".tapnet")


def run(*argv):
    return tapfam.run_argv(list(argv))


def line(rep, key, status=None):
    for ln in rep.lines:
        if ln.key == key and (status is None or ln.status == status):
            return ln
    return None


def statuses(rep, key):
    return [ln.status for ln in rep.lines if ln.key == key]


class Fixture(unittest.TestCase):
    def test_fixture_up_to_date(self):
        data = (json.dumps(MF.build(), indent=1, sort_keys=False, ensure_ascii=False) + "\n").encode("utf-8")
        with open(P.FIXTURE_FILE, "rb") as f:
            self.assertEqual(f.read(), data, "run make_fixture.py")

    def test_fixture_sources_hash(self):
        fx = C.load_fixture(P.FIXTURE_FILE)
        import hashlib
        self.assertEqual(fx["sources"]["chain-reads.json"], hashlib.sha256(open(os.path.join(P.CREDITS_DIR, "chain-reads.json"), "rb").read()).hexdigest())
        self.assertEqual(fx["sources"]["chain-snapshot.json"], hashlib.sha256(open(os.path.join(A721, "chain-snapshot.json"), "rb").read()).hexdigest())

    def test_recorded_source_reads_are_the_repository_reads(self):
        """The recorded eth_call answers decode to the values chain-snapshot.json / chain-reads.json hold."""
        rpc = C.Rpc(fixture=C.load_fixture(P.FIXTURE_FILE))
        snap = json.load(open(os.path.join(A721, "chain-snapshot.json"), encoding="utf-8"))
        for c in snap["circuits"]:
            info = rpc.call_decode(56, c["processor"], "circuitInfo(uint256)", (c["circuitId"],), ["uint256"] * 4, snap["block"])
            self.assertEqual(info, [c["nIn"], c["nOut"], c["nState"], c["gateCount"]])
            nl = rpc.call_decode(56, c["processor"], "netlist(uint256)", (c["circuitId"],), "bytes", snap["block"])
            self.assertEqual("0x" + nl.hex(), c["netlist"])
        reads = json.load(open(os.path.join(P.CREDITS_DIR, "chain-reads.json"), encoding="utf-8"))
        self.assertEqual(rpc.pinned_block(56), reads["pinnedBlock"]["number"])
        self.assertTrue(rpc.call_decode(56, reads["factory"]["address"], "isCPU(address)", (reads["circuits"][0]["processor"],), "bool"))


class Abi(unittest.TestCase):
    def test_selectors_match_the_tap_tables(self):
        self.assertEqual(C.selector("supportsInterface(bytes4)"), "0x01ffc9a7")
        self.assertEqual(C.selector("netlistHashOf(uint256)"), "0x32d9b670")
        self.assertEqual(C.selector("entryIndexOf(uint256,uint256)"), "0x6b3b2d25")
        self.assertEqual(C.selector("isCPU(address)"), "0x5f5a364f")
        for sig, sel in VSB["interfaces"]["selectors"].items():
            self.assertEqual(C.selector(sig), sel, sig)

    def test_pools_round_trip(self):
        pools = [("IMAGE_V1", 1, "0x" + "11" * 32), ("NETLIST_V1", 2, "0x" + "22" * 32)]
        self.assertEqual([tuple(p) for p in C.decode("(string,uint8,bytes32)[]", MF.enc_pools(pools))], pools)
        self.assertEqual(C.decode("(string,uint8,bytes32)[]", MF.enc_pools([])), [])

    def test_multi_return_with_string(self):
        vals = [0, 1, 2, 1, 256, True, "0x" + "ab" * 32, "异或门 XOR", 4, 108, "0x" + "cd" * 20, 3]
        self.assertEqual(C.decode(tapfam.TASK_TYPES, MF.enc_multi(tapfam.TASK_TYPES, vals)), vals)

    def test_bytes_return(self):
        self.assertEqual(C.decode("bytes", C.encode_bytes_return(b"TAPNET\x01")), b"TAPNET\x01")


class ExampleCollection(unittest.TestCase):
    """The eight-token worked example as an L1 collection (synthetic contract 0x…aa in the fixture)."""

    def report(self, t, **extra):
        argv = ["token", "--offline", "--contract", MF.EXAMPLE, "--id", str(t["tokenId"]), "--metadata", os.path.join(A721, t["metadataPath"]),
                "--netlist", netlist_path(t["netlistHash"]), "--manifest", EXAMPLE_MANIFEST]
        for k, v in extra.items():
            argv += ["--" + k.replace("_", "-"), v]
        return run(*argv)

    def test_every_token(self):
        by_hash = {c["netlistHash"]: c["structuralHash"] for c in VSH["chainSnapshot"]}
        for t in V721["example"]["tokens"]:
            with self.subTest(token=t["tokenId"]):
                rep = self.report(t, collection_dir=EXAMPLE_TOKENS)
                self.assertFalse(rep.failed, rep.render())
                self.assertEqual(rep.result["level"], "L1")
                self.assertEqual(rep.result["netlist"], "verified")
                self.assertIn("L1 (on-chain interface)", line(rep, "level").text)
                self.assertEqual(line(rep, "profile").text.split(":")[0], "collection with a manifest")
                self.assertEqual(line(rep, "frozen").status, "ok")
                self.assertEqual(line(rep, "manifest.onchain").status, "ok")
                self.assertEqual(line(rep, "netlist.onchain").status, "ok")
                self.assertEqual(line(rep, "image.onchain").status, "ok")
                self.assertEqual(line(rep, "pools.onchain").status, "ok")
                self.assertEqual(statuses(rep, "assignment"), ["ok", "ok"])
                self.assertIn(f"entry {t['imageEntry']}; entryIndexOf({t['tokenId']}, 0) = {t['imageEntry']}", rep.lines[[l.key for l in rep.lines].index("assignment")].text)
                self.assertEqual(line(rep, "netlist.entry").status, "ok")
                self.assertEqual(line(rep, "image.entry").status, "ok")
                self.assertEqual(line(rep, "source.check").status, "ok")
                self.assertIn("declared block, block 128200681", line(rep, "source.check").text)
                self.assertEqual(line(rep, "source.name").status, "ok")
                self.assertIn(by_hash[t["netlistHash"]], line(rep, "structural.hash").text)
                self.assertEqual(line(rep, "edition.check").status, "ok")
                self.assertEqual(line(rep, "collection.manifest").status, "ok")
                ed = t["metadata"]["tap"].get("edition")
                if ed:
                    self.assertIn(f"edition {ed['index']}/{ed['of']}", line(rep, "edition.declared").text)
                self.assertEqual(line(rep, "verdict").status, "ok")

    def test_json_output(self):
        t = V721["example"]["tokens"][3]
        rep = self.report(t)
        doc = json.loads(rep.dumps(True))
        self.assertEqual(doc["format"], "tap-family-checker-report/1")
        self.assertEqual(doc["command"], "token")
        self.assertEqual(doc["result"]["tokenId"], 4)
        self.assertTrue(all(set(l) >= {"ref", "key", "status", "text"} for l in doc["lines"]))
        self.assertTrue(all(l["ref"].startswith("TAP-") for l in doc["lines"]))

    def test_wrong_netlist_file(self):
        t = V721["example"]["tokens"][3]  # token 4, XOR
        other = next(x for x in V721["example"]["tokens"] if x["netlistHash"] != t["netlistHash"])
        rep = run("token", "--offline", "--contract", MF.EXAMPLE, "--id", "4", "--metadata", os.path.join(A721, t["metadataPath"]),
                  "--netlist", netlist_path(other["netlistHash"]))
        self.assertEqual(line(rep, "netlist.file").status, "fail")
        self.assertIn("does not hash to tap.netlist.sha256", line(rep, "netlist.file").text)
        self.assertTrue(rep.failed)
        self.assertIsNone(line(rep, "structural.hash"))

    def test_netlist_checks_vectors(self):
        """netlistChecks: a fetched file against metadata (§7.4), one match and two rejects."""
        files = {t["source"].get("name") or f"{t['source']['circuitId']}.{t['source']['processorNumber']}.tape": t["file"] for t in V721["tapnet"]}
        for v in V721["netlistChecks"]:
            with self.subTest(name=v["name"]):
                doc = json.loads(json.dumps(V721["example"]["tokens"][3]["metadata"]))
                doc["tap"]["netlist"] = v["netlist"]
                rep = run("metadata", write_json(f"nc-{v['name']}.json", doc), "--netlist", write_bytes(f"nc-{v['name']}.tapnet", bytes.fromhex(files[v["file"]][2:])))
                ln = line(rep, "netlist.file")
                if v["error"] is None:
                    self.assertEqual(ln.status, "ok")
                else:
                    self.assertEqual(ln.status, "fail")
                    self.assertIn(v["error"], ln.text)

    def test_tampered_editions_and_manifest_consistency(self):
        """editions.invalid and editions.collectionErrors through --collection-dir."""
        tokens = V721["example"]["tokens"]
        for v in V721["editions"]["invalid"]:
            with self.subTest(name=v["name"]):
                d = os.path.join(TMP, "ed-" + v["name"])
                shutil.rmtree(d, ignore_errors=True)
                os.makedirs(d)
                for t in tokens:
                    doc = json.loads(json.dumps(t["metadata"]))
                    if t["tokenId"] == v["tokenId"]:
                        if v["edition"] is None:
                            doc["tap"].pop("edition", None)
                        else:
                            doc["tap"]["edition"] = v["edition"]
                    write_json(os.path.join("ed-" + v["name"], f"{t['tokenId']}.json"), doc)
                t = tokens[3]
                rep = run("token", "--offline", "--contract", MF.EXAMPLE, "--id", "4", "--metadata", os.path.join(A721, t["metadataPath"]),
                          "--netlist", netlist_path(t["netlistHash"]), "--collection-dir", d)
                self.assertEqual(line(rep, "edition.check").status, "fail")
                self.assertIn(v["error"], line(rep, "edition.check").text)
        # one token without tap.manifest: the collection is invalid (§7.1)
        d = os.path.join(TMP, "ed-mixed")
        os.makedirs(d, exist_ok=True)
        for t in tokens:
            doc = json.loads(json.dumps(t["metadata"]))
            if t["tokenId"] == 2:
                doc["tap"].pop("manifest")
                doc["tap"].pop("edition", None)
            write_json(os.path.join("ed-mixed", f"{t['tokenId']}.json"), doc)
        rep = run("metadata", os.path.join(A721, tokens[3]["metadataPath"]), "--collection-dir", d)
        self.assertEqual(line(rep, "collection.manifest").status, "fail")
        self.assertIn("mixes tokens with and without tap.manifest", line(rep, "collection.manifest").text)

    def test_unrevealed_and_placeholder_metadata(self):
        for v in V721["metadata"]["valid"]:
            with self.subTest(name=v["name"]):
                rep = run("metadata", write_json(f"md-{v['name']}.json", v["document"]))
                self.assertFalse(rep.failed, rep.render())
        for v in V721["metadata"]["invalid"]:
            with self.subTest(name=v["name"]):
                rep = run("metadata", write_json(f"mdi-{v['name']}.json", v["document"]))
                self.assertEqual(line(rep, "metadata").status, "fail")
                self.assertIn(v["error"], line(rep, "metadata").text)


class NoManifest(unittest.TestCase):
    def test_valid_documents_are_labelled_no_manifest(self):
        for v in V721["noManifest"]["valid"]:
            with self.subTest(name=v["name"]):
                rep = run("metadata", write_json(f"nm-{v['name']}.json", v["document"]))
                self.assertFalse(rep.failed, rep.render())
                tap = v["document"]["tap"]
                if "manifest" in tap:
                    self.assertIn("content committed by a manifest", line(rep, "manifest.declared").text)
                    self.assertIsNone(line(rep, "freeze.probe"), "tap.freeze is ignored next to a manifest (§7.2)")
                else:
                    self.assertIn("no manifest: content not committed", line(rep, "level").text)
                    self.assertIn("no editions", line(rep, "edition.check").text)
                    if "freeze" in tap:
                        self.assertIn("names a check, not a state", line(rep, "freeze.probe").text)

    def test_invalid_documents(self):
        for v in V721["noManifest"]["invalid"]:
            with self.subTest(name=v["name"]):
                rep = run("metadata", write_json(f"nmi-{v['name']}.json", v["document"]))
                self.assertEqual(line(rep, "metadata").status, "fail")
                self.assertIn(v["error"], line(rep, "metadata").text)

    def test_freeze_probes_across_a_collection(self):
        fp = V721["noManifest"]["freezeProbe"]
        d = os.path.join(TMP, "fp-ok")
        os.makedirs(d, exist_ok=True)
        for i, doc in enumerate(fp["documents"]):
            write_json(os.path.join("fp-ok", f"{i}.json"), doc)
        rep = run("metadata", write_json("fp-ok-0.json", fp["documents"][0]), "--collection-dir", d)
        self.assertEqual(line(rep, "collection.freeze").status, "ok")
        for v in fp["invalid"]:
            with self.subTest(name=v["name"]):
                d = os.path.join(TMP, "fp-" + v["name"])
                os.makedirs(d, exist_ok=True)
                for i, doc in enumerate(v["documents"]):
                    write_json(os.path.join("fp-" + v["name"], f"{i}.json"), doc)
                rep = run("metadata", write_json(f"fp-{v['name']}-0.json", v["documents"][0]), "--collection-dir", d)
                self.assertEqual(line(rep, "collection.freeze").status, "fail")
                self.assertIn(v["error"], line(rep, "collection.freeze").text)

    def test_same_hash_without_manifest_forms_no_edition(self):
        ed = V721["noManifest"]["editions"]
        d = os.path.join(TMP, "nm-ed")
        os.makedirs(d, exist_ok=True)
        for i, doc in enumerate(ed["documents"]):
            write_json(os.path.join("nm-ed", f"{i}.json"), doc)
        rep = run("metadata", write_json("nm-ed-0.json", ed["documents"][0]), "--collection-dir", d)
        self.assertFalse(rep.failed, rep.render())
        self.assertNotIn("fail", statuses(rep, "edition.check"))
        self.assertIn("no editions", line(rep, "edition.check").text)

    def test_mint_bound_contract(self):
        doc = json.loads(json.dumps(V721["noManifest"]["valid"][0]["document"]).replace(MF.EXAMPLE, MF.MINT_BOUND))
        rep = run("token", "--offline", "--contract", MF.MINT_BOUND, "--id", "1", "--metadata", write_json("mb.json", doc))
        self.assertFalse(rep.failed, rep.render())
        self.assertEqual(rep.result["level"], "L1")
        self.assertTrue(line(rep, "profile").text.startswith("mint-bound collection"))
        self.assertEqual(line(rep, "netlist.onchain").status, "ok")
        self.assertEqual(line(rep, "image.onchain").status, "ok")
        self.assertIn("never uses the state unrevealed", line(rep, "state.chain").text)
        self.assertIn("not frozen", line(rep, "frozen").text)
        self.assertIn("no editions", line(rep, "edition.check").text)
        self.assertEqual(line(rep, "verdict").status, "skip")  # no netlist file given

    def test_l0_freeze_probe(self):
        doc = json.loads(json.dumps(V721["noManifest"]["valid"][1]["document"]).replace(MF.EXAMPLE, MF.L0_FREEZE))
        rep = run("token", "--offline", "--contract", MF.L0_FREEZE, "--id", "1", "--metadata", write_json("l0.json", doc))
        self.assertFalse(rep.failed, rep.render())
        self.assertEqual(line(rep, "level").text, "L0 (metadata only), no manifest: content not committed")
        self.assertEqual(line(rep, "frozen").status, "ok")
        self.assertIn("uriFrozen() on " + MF.L0_FREEZE + " returns true = expect (tap.freeze)", line(rep, "frozen").text)
        self.assertIsNone(line(rep, "profile"))

    def test_token_reports_no_freeze_when_probes_differ(self):
        """§5.1 through the token subcommand: the single token's probe is not read when the collection's tokens name different probes."""
        fp = V721["noManifest"]["freezeProbe"]
        for v in fp["invalid"]:
            with self.subTest(name=v["name"]):
                d = os.path.join(TMP, "tfp-" + v["name"])
                os.makedirs(d, exist_ok=True)
                docs = [json.loads(json.dumps(doc).replace(MF.EXAMPLE, MF.L0_FREEZE)) for doc in v["documents"]]
                for i, doc in enumerate(docs):
                    write_json(os.path.join("tfp-" + v["name"], f"{i}.json"), doc)
                rep = run("token", "--offline", "--contract", MF.L0_FREEZE, "--id", "1", "--metadata", write_json(f"tfp-{v['name']}-0.json", docs[0]),
                          "--collection-dir", d)
                self.assertEqual(line(rep, "collection.freeze").status, "fail")
                self.assertEqual(statuses(rep, "frozen"), ["skip"], rep.render())
        d = os.path.join(TMP, "tfp-ok")
        os.makedirs(d, exist_ok=True)
        docs = [json.loads(json.dumps(doc).replace(MF.EXAMPLE, MF.L0_FREEZE)) for doc in fp["documents"]]
        for i, doc in enumerate(docs):
            write_json(os.path.join("tfp-ok", f"{i}.json"), doc)
        rep = run("token", "--offline", "--contract", MF.L0_FREEZE, "--id", "1", "--metadata", write_json("tfp-ok-0.json", docs[0]), "--collection-dir", d)
        self.assertEqual(line(rep, "collection.freeze").status, "ok")
        self.assertEqual(statuses(rep, "frozen"), ["ok"])
        self.assertIn("no editions", line(rep, "edition.check").text)

    def test_l1_ignores_tap_freeze(self):
        """At L1 the tool reads frozen() and ignores tap.freeze (§7.2): the probe line comes from frozen()."""
        doc = json.loads(json.dumps(V721["noManifest"]["valid"][1]["document"]).replace(MF.EXAMPLE, MF.MINT_BOUND))
        rep = run("token", "--offline", "--contract", MF.MINT_BOUND, "--id", "1", "--metadata", write_json("l1f.json", doc))
        self.assertIn("frozen() returns false", line(rep, "frozen").text)


class OtherFormats(unittest.TestCase):
    def test_tapnet2_token_is_unverifiable(self):
        v = V721["otherFormats"]["tokens"][0]
        rep = run("metadata", write_json("of.json", v["document"]))
        self.assertFalse(rep.failed, rep.render())
        self.assertEqual(line(rep, "netlist.declared").status, "unverifiable")
        self.assertEqual(line(rep, "netlist.file").status, "unverifiable")
        self.assertNotIn("verified", rep.render().replace("unverifiable", "").replace("never as verified", ""))

    def test_fetched_files(self):
        v = V721["otherFormats"]["tokens"][0]
        for f in V721["otherFormats"]["fetchedFiles"]:
            with self.subTest(name=f["name"]):
                argv = ["metadata", write_json("of.json", v["document"])]
                if f["file"] is not None:
                    argv += ["--netlist", write_bytes(f"of-{f['name']}.bin", bytes.fromhex(f["file"][2:]))]
                rep = run(*argv)
                ln = line(rep, "netlist.file")
                if f["result"] == "unverifiable":
                    self.assertEqual(ln.status, "unverifiable")
                else:
                    self.assertEqual(ln.status, "fail")
                    self.assertIn(f["error"], ln.text)

    def test_invalid_format_strings(self):
        for v in V721["otherFormats"]["invalid"]:
            with self.subTest(name=v["name"]):
                rep = run("metadata", write_json(f"ofi-{v['name']}.json", v["document"]))
                self.assertEqual(line(rep, "metadata").status, "fail")
                self.assertIn(v["error"], line(rep, "metadata").text)

    def test_edition_check_unverifiable(self):
        es = V721["otherFormats"]["editionsSkipped"]
        d = os.path.join(TMP, "of-ed")
        os.makedirs(d, exist_ok=True)
        for i, doc in enumerate(es["documents"]):
            write_json(os.path.join("of-ed", f"{i}.json"), doc)
        rep = run("metadata", write_json("of-ed-0.json", es["documents"][0]), "--collection-dir", d)
        self.assertEqual(line(rep, "edition.check").status, "unverifiable")

    def test_token_command_verdict(self):
        v = V721["otherFormats"]["tokens"][0]
        rep = run("token", "--offline", "--contract", MF.EXAMPLE, "--id", "1", "--metadata", write_json("of.json", v["document"]))
        self.assertEqual(line(rep, "verdict").status, "unverifiable")
        self.assertEqual(line(rep, "netlist.onchain").status, "unverifiable")


class BridgedCopy(unittest.TestCase):
    def test_mirror(self):
        t = V721["example"]["tokens"][3]
        rep = run("token", "--offline", "--contract", MF.MIRROR, "--id", "4", "--metadata", os.path.join(A721, t["metadataPath"]),
                  "--netlist", netlist_path(t["netlistHash"]))
        self.assertFalse(rep.failed, rep.render())
        self.assertTrue(line(rep, "profile").text.startswith("bridged copy"))
        self.assertEqual(line(rep, "profile").ref, "TAP-BR §5.3")
        home = [l for l in rep.lines if l.key == "token.id"][-1]
        self.assertEqual((home.ref, home.status), ("TAP-BR §5.3", "info"))
        self.assertIn("home token", home.text)
        self.assertIn("a bridged copy may stay false", line(rep, "frozen").text)
        self.assertEqual(line(rep, "netlist.onchain").status, "ok")

    def test_collection_key_and_mirror_id(self):
        vb = json.load(open(os.path.join(P.BRIDGING_DIR, "vectors.json"), encoding="utf-8"))
        for k in vb["collectionKeys"]:
            self.assertEqual(tapfam.collection_key(k["homeChainId"], k["homeContract"]), k["collectionKey"])
        self.assertEqual(tapfam.IID["ITapBridgeMirror"], vb["interfaces"]["interfaceIds"]["ITapBridgeMirror"])
        for name in ("ITapCredential", "ITapCredentialProven", "ITapCredentialAttested", "ITapCredentialClaimed"):
            self.assertEqual(tapfam.IID[name], VSB["interfaces"][name])
        self.assertEqual(tapfam.IID["ERC5192"], VSB["interfaces"]["IERC5192"])

    def test_wrong_token_id_is_a_failure_elsewhere(self):
        t = V721["example"]["tokens"][3]
        rep = run("token", "--offline", "--contract", MF.EXAMPLE, "--id", "5", "--metadata", os.path.join(A721, t["metadataPath"]))
        self.assertEqual(line(rep, "token.id", "fail").ref, "TAP-721 §4.1")


class Credentials(unittest.TestCase):
    FINAL = next(s for s in VSB["scenario"] if s["step"] == "final token states")["result"]

    def cred(self, tid, *extra):
        return run("credential", "--offline", "--chain-id", str(VSB["chainId"]), "--contract", VSB["contract"], "--id", str(tid), *extra)

    def test_kind_labels_and_statuses(self):
        for tid_s, st in self.FINAL.items():
            with self.subTest(token=tid_s):
                rep = self.cred(int(tid_s))
                self.assertFalse(rep.failed, rep.render())
                status = st["status"]["1900000000"]
                if st["holder"] is None:
                    self.assertIn("status none", line(rep, "credential.status").text)
                    self.assertIsNone(line(rep, "credential.kind"))
                    continue
                kind = P.soulbound.KINDS[st["credential"]["kind"]]
                k = line(rep, "credential.kind").text
                self.assertIn({"proven": "Proven per contract (not re-checked)", "attested": "Attested by " + st["credential"]["issuer"] + " (issuer identity not verified)",
                               "claimed": "Self-claimed"}[kind], k)
                self.assertIn("unverified contract", k)
                self.assertIn("subject " + P.soulbound.SUBJECTS[st["credential"]["subject"]], k)
                if status == "active":
                    self.assertEqual(line(rep, "credential.status").status, "ok")
                    self.assertNotIn("[", k.split(" — ")[0])
                else:
                    self.assertEqual(line(rep, "credential.status").status, "warn")
                    self.assertIn(f"[{status}]", k)
                lvl = line(rep, "credential.level").text
                self.assertTrue(lvl.startswith("L0 (metadata only); metadata can change"))
                self.assertIn("never L1", lvl)
                self.assertIn("not an entitlement", line(rep, "credential.notice").text)
                self.assertIn("L0 (metadata only)", line(rep, "level").text)
                if kind == "proven":
                    self.assertIn("registrant", line(rep, "credential.spec").text)
                    self.assertIn("maxGates 4", line(rep, "credential.spec").text)
                    self.assertIn("does not prove who designed", [l for l in rep.lines if l.key == "credential.notice"][-1].text)
                if st["credential"]["expiresAt"]:
                    self.assertIn(str(st["credential"]["expiresAt"]), line(rep, "credential.expires").text)
                if st["credential"]["replaces"]:
                    self.assertIn(f"replaces token {st['credential']['replaces']}", line(rep, "credential.replaces").text)

    def test_superseded_links_to_replacement(self):
        rep = self.cred(1)
        self.assertIn("superseded by token 3", line(rep, "credential.replacement").text)
        rep = self.cred(5)
        self.assertIn("superseded by token 7", line(rep, "credential.replacement").text)

    def test_metadata_against_record_and_recheck(self):
        m = VSB["metadata"][0]  # proven ok: token 1
        art = write_bytes("xor.tapnet", bytes.fromhex(VSB["files"]["xor"]["file"][2:]))
        rep = self.cred(1, "--metadata", write_json("cred1.json", m["doc"]), "--artifact", art)
        self.assertFalse(rep.failed, rep.render())
        self.assertEqual(line(rep, "credential.metadata").status, "ok")
        self.assertEqual(line(rep, "credential.recheck").status, "ok")
        self.assertIn("Proven: passes its specification (re-checked) [superseded]", line(rep, "credential.kind").text)
        self.assertIn("artifact recorded by the credential contract", line(rep, "credential.level").text)
        self.assertEqual(line(rep, "level").ref, "TAP-SB §10.1")
        # the record prevails: token 3's record (issuedAt 609800, replaces 1) differs from token 1's document (§9 item 1)
        rep = self.cred(3, "--metadata", write_json("cred1bad.json", m["doc"]))
        self.assertEqual(line(rep, "credential.metadata").status, "fail")
        self.assertIn("credential-onchain-mismatch", line(rep, "credential.metadata").text)

    def test_wrong_artifact_file(self):
        m = VSB["metadata"][0]
        art = write_bytes("and2.tapnet", bytes.fromhex(VSB["files"]["and2"]["file"][2:]))
        rep = self.cred(1, "--metadata", write_json("cred1.json", m["doc"]), "--artifact", art)
        self.assertEqual(line(rep, "credential.recheck").status, "fail")
        self.assertIn("Proven per contract (not re-checked)", line(rep, "credential.kind").text)

    def test_metadata_vectors_offline(self):
        for m in VSB["metadata"]:
            err = m.get("error") if not m["ok"] else None
            if err == "credential-onchain-mismatch":
                continue  # needs the record: covered above
            with self.subTest(name=m["name"]):
                rep = run("metadata", write_json("sbm.json", m["doc"]))
                ln = line(rep, "credential.metadata") or line(rep, "metadata")
                if err is None:
                    # (the "tap.pod with mining names" document carries a tap.pod that is not a snapshot: the PoD
                    # validator rejects that member, which is a separate finding from the credential rules)
                    self.assertEqual(line(rep, "metadata").status, "ok", rep.render())
                    self.assertEqual(line(rep, "credential.metadata").status, "ok", rep.render())
                    kind = m["doc"]["tap"]["credential"]["kind"]
                    self.assertIn({"proven": "Proven per contract (not re-checked)", "attested": "Attested by issuer", "claimed": "Self-claimed"}[kind],
                                  line(rep, "credential.kind").text)
                else:
                    self.assertEqual(ln.status, "fail", rep.render())
                    if ln.key == "metadata":
                        # rejected first by the TAP-721 rules the credential rules restate (§3.2: tap.image, no tap.manifest, no tap.edition)
                        self.assertIn(err, ("credential-image", "credential-edition", "credential-state"), rep.render())
                    else:
                        self.assertIn(err, ln.text)

    def test_claim_statement_display(self):
        """§6/§10.4 through soulbound.statement_display on the claimStatements vectors."""
        st = VSB["claimStatements"]
        for c in st["cases"]:
            got = P.soulbound.statement_display(c["message"], st["holder"], VSB["chainId"], st["artifact"], c["revoked"])
            self.assertEqual(got, c["display"], c["name"])


class Credits(unittest.TestCase):
    def test_standalone_bundle(self):
        rep = run("bundle", "--offline", write_json("bundle.json", VCR["bundle"]["standalone"]))
        self.assertFalse(rep.failed, rep.render())
        facts = [l for l in rep.lines if l.key == "credits.fact"]
        self.assertEqual([l.status for l in facts], ["ok"] * 4)
        for l in facts:
            self.assertTrue(l.text.startswith("[verified fact]"))
            self.assertIn("first taped out by", l.text)
            self.assertIn("state block 128542889", l.text)
            low = l.text.lower()
            for word in ("designer", "author", "creator", "made by"):
                self.assertNotIn(word, low)
        claims = [l for l in rep.lines if l.key == "credits.claim"]
        self.assertEqual(len(claims), 2)
        self.assertTrue(claims[0].text.startswith("[claim] designer, claimed by 0x541378bc90ff35563c25197869b436889f6caf4c"))
        self.assertIn('self-declared name "Ada (test)"', claims[0].text)
        self.assertIn("names exact file (netlistHash)", claims[0].text)
        self.assertIn("[claim] derivedFrom", claims[1].text)
        self.assertIn("designer 1", line(rep, "credits.claims").text)
        e = line(rep, "credits.earliest")
        self.assertTrue(e.text.startswith("[earliest known, refutable] 906.30.tape"))
        self.assertIn("not the origin", e.text)

    def test_tap_credits_member_in_token_metadata(self):
        doc = json.loads(json.dumps(V721["example"]["tokens"][3]["metadata"]))
        doc["tap"]["credits"] = VCR["bundle"]["tapCredits"]
        t = V721["example"]["tokens"][3]
        rep = run("token", "--offline", "--contract", MF.EXAMPLE, "--id", "4", "--metadata", write_json("t4credits.json", doc), "--netlist", netlist_path(t["netlistHash"]))
        self.assertFalse(rep.failed, rep.render())
        self.assertEqual(line(rep, "credits.bundle").status, "ok")
        self.assertEqual(statuses(rep, "credits.fact"), ["ok"] * 4)

    def test_standalone_invalid(self):
        for v in VCR["bundle"]["standaloneInvalid"]:
            with self.subTest(name=v["name"]):
                rep = run("bundle", "--offline", write_json(f"bi-{v['name']}.json", v["bundle"]))
                self.assertEqual(line(rep, "credits.bundle").status, "fail")
                self.assertIn(v["error"], line(rep, "credits.bundle").text)

    def test_display_scenario(self):
        """display: states, groups per role, container label, revoked claim absent (§6.4, §4.7)."""
        d = VCR["display"]
        bundle = {"v": 1, "statements": d["statements"]}
        rep = run("bundle", "--offline", write_json("display.json", dict(bundle, tapCreditBundle=1)))
        claims = [l for l in rep.lines if l.key == "credits.claim"]
        expect = d["expect"]
        n_active = sum(len(g["anchored"]) + len(g["unanchored"]) + len(g["container"]) for g in expect["groups"].values())
        self.assertEqual(len(claims), n_active)
        roles = [l.text.split("] ")[1].split(",")[0] for l in claims]
        self.assertEqual(roles, sorted(roles, key=P.credits.ROLES.index))
        counts = line(rep, "credits.claims").text
        for role, g in expect["groups"].items():
            self.assertIn(f"{role} {len(g['anchored']) + len(g['unanchored']) + len(g['container'])}", counts)
        container = [l for l in claims if "container of 1.2.282.tape; validity follows its holder" in l.text]
        self.assertEqual(len(container), 1)
        self.assertEqual(claims.index(container[0]), len(expect["groups"]["designer"]["anchored"]) + len(expect["groups"]["designer"]["unanchored"]))
        self.assertEqual(len([l for l in rep.lines if l.key == "credits.revoked"]), expect["states"].count("revoked"))
        self.assertFalse(any("Revocation" in l.text for l in claims))

    def test_unverified_facts_without_reads(self):
        """A fact whose chain reads are not available is displayed as not verified, never as verified."""
        pub = dict(VCR["display"]["publications"][0]["fact"])
        rep = run("bundle", "--offline", write_json("unv.json", {"tapCreditBundle": 1, "v": 1, "publications": [pub]}))
        self.assertEqual(line(rep, "credits.fact").status, "unverified")
        self.assertIn("not verified", line(rep, "credits.fact").text)


@unittest.skipIf(P.pod_validate() is None, "pod_validate.py needs pycryptodome")
class Pod(unittest.TestCase):
    def doc_for(self, pod: dict, source_block=None) -> dict:
        snap = {c["circuitId"]: c for c in json.load(open(os.path.join(A721, "chain-snapshot.json"), encoding="utf-8"))["circuits"]}
        c = snap.get(int(pod["circuitId"]) if str(pod["circuitId"]).isdigit() else -1)
        if c:
            f = P.tapnft.file_from_chain(bytes.fromhex(c["netlist"][2:]), c["nIn"], c["nOut"])
            m = P.tapnft.check_file(f)
            net = {"format": "tapnet/1", "sha256": P.tapnft.hex32(P.tapnft.netlist_hash(f)), "bytes": len(f), "nIn": m.n_in, "nOut": m.n_out,
                   "nand": m.nand, "latch": m.latch, "uris": ["https://example.invalid/n.tapnet"]}
            name = f"{pod['circuitId']}.{c['processorNumber']}.tape"
        else:
            net = {"format": "tapnet/1", "sha256": "0x" + "ab" * 32, "bytes": 37, "nIn": 2, "nOut": 1, "nand": 3, "latch": 0, "uris": ["https://example.invalid/n.tapnet"]}
            name = None
        src = {"chainId": 56, "processor": pod.get("processor", "0x" + "00" * 20), "circuitId": str(pod.get("circuitId", "0")), "block": pod.get("block", 0)}
        if name:
            src["name"] = name
        return {"name": "pod test", "image": "https://example.invalid/i.png",
                "tap": {"v": 1, "id": "eip155:196/erc721:0x0000000000000000000000000000000000000001/1", "state": "revealed",
                        "image": {"sha256": "0x" + "11" * 32, "uris": ["https://example.invalid/i.png"]}, "netlist": net, "source": src, "pod": pod}}

    def test_real_snapshots_confirmed(self):
        for case in VPOD["cases"]:
            if not case.get("hasMinerRecord"):
                continue
            with self.subTest(label=case["label"]):
                rep = run("token", "--offline", "--metadata", write_json("pod.json", self.doc_for(case["pod"])))
                self.assertFalse(rep.failed, rep.render())
                self.assertEqual(line(rep, "pod.format").status, "ok")
                self.assertEqual(line(rep, "pod.verify").status, "ok", line(rep, "pod.verify").text)
                self.assertEqual(line(rep, "source.check").status, "ok")
                self.assertIn("facts about the NFT's netlist (source confirmed)", line(rep, "pod.design").text)
                self.assertIn(f"standing at block {case['pod']['block']} (not current)", line(rep, "pod.standing").text)
                self.assertIn("not evidence that the netlist computes", line(rep, "pod.verified").text)
                self.assertEqual(line(rep, "pod.functionCheck").status, "ok")
                self.assertIn("The NFT does not mine and earns nothing", line(rep, "pod.notice").text)

    def test_source_not_confirmed_means_declared_only(self):
        case = VPOD["cases"][0]
        doc = self.doc_for(case["pod"])
        doc["tap"]["netlist"]["sha256"] = "0x" + "ab" * 32  # the NFT's netlist is not the source circuit's
        rep = run("token", "--offline", "--metadata", write_json("pod-nosrc.json", doc))
        self.assertEqual(line(rep, "source.check").status, "fail")
        self.assertIn("declared by the collection, not verified", line(rep, "pod.design").text)

    def test_verified_but_wrong(self):
        case = VPOD["verifiedButWrong"][0]
        rep = run("token", "--offline", "--metadata", write_json("pod-vbw.json", self.doc_for(case["pod"])))
        self.assertEqual(line(rep, "pod.format").status, "ok")
        self.assertIn("verified = true", line(rep, "pod.verified").text)
        self.assertEqual(line(rep, "pod.functionCheck").status, "fail")
        self.assertIn("MISMATCH", line(rep, "pod.functionCheck").text)
        self.assertEqual(line(rep, "pod.verify").status, "unverified")  # fictional processor: no recorded state

    def test_invalid_snapshots_rejected(self):
        for case in VPOD["invalid"]:
            with self.subTest(label=case["label"]):
                rep = run("metadata", write_json("pod-inv.json", self.doc_for(case["pod"])))
                self.assertTrue(rep.failed, rep.render())
                # rejected by the PoD validator, or earlier by the TAP-721 metadata rules its tap.source copies (processor case, circuitId type)
                self.assertTrue(any(l.key in ("pod.format", "metadata") and l.status == "fail" for l in rep.lines), rep.render())
                self.assertIsNone(line(rep, "pod.design"), "no PoD fact is displayed for a rejected snapshot")

    def test_metadata_example_and_rig(self):
        doc = json.loads(json.dumps(VPOD["metadataExample"]["document"]))
        doc["image"] = "https://example.invalid/i.png"
        doc["tap"]["image"] = {"sha256": "0x" + "11" * 32, "uris": [doc["image"]]}
        rep = run("metadata", write_json("pod-ex.json", doc))
        self.assertFalse(rep.failed, rep.render())
        self.assertIn("related rig voucher (informative)", line(rep, "rig").text)
        self.assertIn("not verified", line(rep, "rig").text)
        self.assertEqual(line(rep, "pod.verify").status, "unverified")  # metadata command reads nothing


class StructuralHash(unittest.TestCase):
    def test_declared_structural_hash(self):
        t = V721["example"]["tokens"][3]
        doc = json.loads(json.dumps(t["metadata"]))
        doc["tap"]["netlist"]["structuralHash"] = VSH["cases"][0]["structuralHash"]  # xor_17851
        rep = run("metadata", write_json("sh-ok.json", doc), "--netlist", netlist_path(t["netlistHash"]))
        self.assertEqual(line(rep, "structural.declared").status, "ok")
        doc["tap"]["netlist"]["structuralHash"] = "0x" + "00" * 31 + "01"
        rep = run("metadata", write_json("sh-bad.json", doc), "--netlist", netlist_path(t["netlistHash"]))
        self.assertEqual(line(rep, "structural.declared").status, "fail")

    def test_vectors_agree(self):
        """Every chain circuit of the structural-hash vectors through check_netlist_file."""
        import report as R
        for c in VSH["chainSnapshot"]:
            data = bytes.fromhex(c["file"][2:])
            m = P.tapnft.check_file(data)
            tap = {"netlist": {"format": "tapnet/1", "sha256": c["netlistHash"], "bytes": len(data), "nIn": m.n_in, "nOut": m.n_out,
                               "nand": m.nand, "latch": m.latch, "uris": ["x:"]}}
            rep = R.Report("t")
            out = tapfam.check_netlist_file(tap, data, rep)
            self.assertEqual(out["design"]["structuralHash"], c["structuralHash"])


if __name__ == "__main__":
    try:
        unittest.main(verbosity=1)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
