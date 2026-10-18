#!/usr/bin/env python3
"""End-to-end test of the TapeCode-Test1 collection tools at full size (stdlib + network, MIT).

  python3 test_pipeline.py      # outputs under $TCT1_TEST_OUT or a new temporary directory
                                # netlist cache under $TCT1_NETCACHE (default: <out>/netcache)

Final plan: 7,000 valid tokens (token set = tools/tokenset/tokens.json, or, until it exists, the ids of
tools/tokenset/owners.json not held by 0x…dEaD), 3,000 excluded ids with placeholder metadata, the rarity
design table rarity-7000.json (1,410 real mainnet designs; files read from the BNB Smart Chain archive
node on the first run and cached), fake image hashes, a REAL past drand quicknet round fetched live.
Then verify_collection.py on the directory, over HTTP (local server) and against tampered copies.
Network: drand relays (GET), https://tapeout.net/rpc (eth_call only).
"""
from __future__ import annotations

import csv
import functools
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import drand  # noqa: E402
from _paths import (DRAFTS, MAX_NETLIST_BYTES, RARITY_FILE, TOKENS_FILE, load_token_ids, read_json,  # noqa: E402
                    tapnft)

OUT = os.environ.get("TCT1_TEST_OUT") or tempfile.mkdtemp(prefix="tct1-collection-")
NETCACHE = os.environ.get("TCT1_NETCACHE") or os.path.join(OUT, "netcache")
TOKENS = TOKENS_FILE if os.path.exists(TOKENS_FILE) else os.path.join(DRAFTS, "tools", "tokenset", "owners.json")
TARGET_TIME = "2026-10-17T12:00:00Z"   # a past instant; its round is fetched live
TIMES, SIZES = {}, {}
REAL_CID = "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi"


def slurp(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def spit(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def run(script, *args, ok=True):
    t = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, script), *args], capture_output=True, text=True)
    dt = time.time() - t
    if ok and p.returncode != 0:
        raise AssertionError(f"{script} {' '.join(args)} failed ({p.returncode}):\n{p.stdout}\n{p.stderr}")
    if not ok and p.returncode == 0:
        raise AssertionError(f"{script} {' '.join(args)} unexpectedly succeeded:\n{p.stdout}")
    return p, dt


def dir_size(path):
    total = files = 0
    for root, _, fs in os.walk(path):
        for f in fs:
            total += os.path.getsize(os.path.join(root, f))
            files += 1
    return total, files


def write_inputs(work):
    os.makedirs(work, exist_ok=True)
    tiers = read_json(RARITY_FILE)["tiers"]
    with open(os.path.join(work, "images.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sha256", "tier", "ext"])
        i = 0
        for t in tiers:
            for _ in range(t["tokens"]):
                w.writerow(["0x" + hashlib.sha256(f"tct1-synthetic-image-{i}".encode()).hexdigest(), t["tier"], "png"])
                i += 1
    shutil.copy(os.path.join(HERE, "template.example.json"), os.path.join(work, "template.json"))
    real = slurp(os.path.join(HERE, "template.example.json"), "r")
    for k in ("IMAGE_DIR_CID", "NETLIST_DIR_CID", "MANIFEST_CID", "BLINDBOX_CID", "TOKENSET_CID"):
        real = real.replace(k, REAL_CID)
    real = real.replace("CONTENT_CIRCUIT_NAME", "2.2.282.tape").replace("gateway.example.invalid", "ipfs-gateway.example.com")
    spit(os.path.join(work, "template-real.json"), real)


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = os.path.join(OUT, "work")
        write_inputs(cls.work)
        print("\noutputs in", OUT, "| token set from", TOKENS)

    def p(self, name):
        return os.path.join(self.work, name)

    def test_1_full_pipeline(self):
        w = self.work
        t_all = time.time()
        # 1 pools (rarity mode; real files from chain or cache)
        out, TIMES["build_pools"] = run("build_pools.py", "--images", self.p("images.csv"), "--out", w,
                                        "--netcache", NETCACHE)
        print(out.stdout)
        pools = read_json(self.p("pools.json"))
        self.assertEqual(len(pools["images"]), 7000)
        self.assertEqual(len(pools["netlists"]), 7000)
        self.assertEqual(len(pools["designs"]), 1410)
        self.assertEqual(pools["quotas"], [70, 280, 1050, 2100, 3500])
        self.assertTrue(all(d["bytes"] <= MAX_NETLIST_BYTES for d in pools["designs"].values()))

        # 2 drand round for a past time, live info
        info = drand.fetch_info()
        rnd = drand.round_at(info, drand.parse_utc(TARGET_TIME))
        ts = ["--token-set", TOKENS, "--token-set-uri", f"ipfs://{REAL_CID}/tokenset.bin"]
        # 3 manifest: refused without the test flag, then written in set mode
        run("make_manifest.py", "--pools", self.p("pools.json"), "--round", str(rnd), "--out", self.p("x.json"), *ts, ok=False)
        out, TIMES["make_manifest"] = run("make_manifest.py", "--pools", self.p("pools.json"), "--round", str(rnd),
                                          "--out", self.p("manifest.json"), "--allow-past-round", *ts)
        print(out.stdout)
        SIZES["manifest"] = os.path.getsize(self.p("manifest.json"))
        self.assertLess(SIZES["manifest"], 8 * 1024 * 1024)
        m = tapnft.check_manifest(slurp(self.p("manifest.json")))
        ids = tapnft.check_token_set(m, slurp(self.p("tokenset.bin")))
        self.assertEqual(len(ids), 7000)
        self.assertEqual(m["rules"]["designTable"]["sha256"], "0x" + hashlib.sha256(slurp(RARITY_FILE)).hexdigest())
        # 4 beacon
        out, TIMES["drand_fetch"] = run("drand.py", "fetch", str(rnd), "--out", self.p("beacon.json"))
        b = read_json(self.p("beacon.json"))
        self.assertEqual(hashlib.sha256(bytes.fromhex(b["signature"])).hexdigest(), b["randomness"])
        self.assertGreaterEqual(len(b["verified"]["relaysAgreeing"]), 2)
        run("drand.py", "fetch", str(drand.round_at(info, int(time.time())) + 1000), ok=False)  # future round
        # 5 reveal (live beacon fetch)
        args = ["--manifest", self.p("manifest.json"), "--pools", self.p("pools.json"), "--template",
                self.p("template.json"), "--out", w]
        out, TIMES["reveal_unrevealed_only"] = run("reveal.py", *args, "--unrevealed-only")
        out, TIMES["reveal"] = run("reveal.py", *args)
        print(out.stdout)
        for d in ("meta", "meta-unrevealed"):
            SIZES[d] = dir_size(self.p(d))
            self.assertEqual(SIZES[d][1], 10000)
        SIZES["reveal.json"] = os.path.getsize(self.p("reveal.json"))
        SIZES["net"] = dir_size(self.p("net"))
        # spot checks against tapnft directly
        t = ids[0]
        a = tapnft.assignment(m, bytes.fromhex(b["randomness"]), t, ids)
        d = read_json(self.p(f"meta/{t}"))
        self.assertEqual(d["tap"]["netlist"]["sha256"], m["pools"][1]["entries"][a["NETLIST_V1"]]["netlist"])
        self.assertEqual(set(d["tap"]["source"]), {"chainId", "processor", "circuitId", "block", "name", "container"})
        self.assertEqual(d["tap"]["content"]["paths"]["netlist"], f"tct1/net/{d['tap']['netlist']['sha256'][2:]}.tapnet")
        excl = next(x for x in range(1, 10001) if x not in set(ids))
        de = read_json(self.p(f"meta/{excl}"))
        self.assertEqual(de["tap"]["state"], "unrevealed")
        self.assertNotIn("netlist", de["tap"])
        self.assertNotIn("image", de["tap"])
        self.assertIsNone(tapnft.assignment(m, bytes.fromhex(b["randomness"]), excl, ids))
        # 6 independent verification (directory, live drand)
        out, TIMES["verify_dir"] = run("verify_collection.py", "--manifest", self.p("manifest.json"), "--meta", self.p("meta"),
                                       "--ids", "1-10000", "--round", str(rnd), "--netlists", self.p("net"),
                                       "--reveal", self.p("reveal.json"), "--design-table", RARITY_FILE,
                                       "--expect-manifest-sha256", "0x" + hashlib.sha256(slurp(self.p("manifest.json"))).hexdigest())
        print(out.stdout)
        self.assertIn("OK: no mismatch", out.stdout)
        self.assertIn("7000 revealed, 3000 excluded placeholders", out.stdout)
        TIMES["pipeline_total"] = time.time() - t_all
        # blind-box set
        out, _ = run("verify_collection.py", "--manifest", self.p("manifest.json"), "--meta", self.p("meta-unrevealed"),
                     "--ids", "1-10000", "--beacon", self.p("beacon.json"), "--allow-unrevealed")
        self.assertIn("OK: no mismatch", out.stdout)
        # blind-box window: a manifest naming a FUTURE round verifies before the round, cannot be revealed
        fut = os.path.join(OUT, "future")
        run("make_manifest.py", "--pools", self.p("pools.json"), "--round", str(drand.round_at(info, int(time.time()) + 4 * 86400)),
            "--out", os.path.join(fut, "manifest.json"), *ts)
        fargs = ["--manifest", os.path.join(fut, "manifest.json"), "--pools", self.p("pools.json"),
                 "--template", self.p("template.json"), "--out", fut]
        run("reveal.py", *fargs, "--unrevealed-only")
        out, _ = run("verify_collection.py", "--manifest", os.path.join(fut, "manifest.json"), "--meta",
                     os.path.join(fut, "meta-unrevealed"), "--ids", "1-10000", "--allow-unrevealed")
        self.assertIn("round not produced yet", out.stdout)
        run("reveal.py", *fargs, ok=False)
        # realistic URIs (59-char CIDs): meta/ size for the folder-limit question
        real = os.path.join(OUT, "real-uris")
        run("reveal.py", "--manifest", self.p("manifest.json"), "--pools", self.p("pools.json"), "--template",
            self.p("template-real.json"), "--out", real, "--beacon", self.p("beacon.json"), "--no-proofs")
        SIZES["meta_realistic_uris"] = dir_size(os.path.join(real, "meta"))

    def test_2_http_and_tamper(self):
        if not os.path.exists(self.p("reveal.json")):
            self.skipTest("pipeline did not run")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a, **k):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=self.work))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}/"
        try:
            out, TIMES["verify_http"] = run("verify_collection.py", "--manifest", base + "manifest.json",
                                            "--base-url", base + "meta/", "--ids", "1-10000",
                                            "--token-set-file", self.p("tokenset.bin"), "--beacon", self.p("beacon.json"))
            self.assertIn("OK: no mismatch", out.stdout)
        finally:
            srv.shutdown()
            srv.server_close()
        m = tapnft.check_manifest(slurp(self.p("manifest.json")))
        ids = tapnft.check_token_set(m, slurp(self.p("tokenset.bin")))
        excl = next(x for x in range(1, 10001) if x not in set(ids))
        # tampering: swap the netlists of two covered tokens; give an excluded id a netlist
        tam = os.path.join(OUT, "tampered")
        shutil.rmtree(tam, ignore_errors=True)
        shutil.copytree(self.p("meta"), tam)
        docs = {t: read_json(os.path.join(tam, str(t))) for t in ids[:50]}
        a = ids[0]
        bb = next(t for t in docs if docs[t]["tap"]["netlist"]["sha256"] != docs[a]["tap"]["netlist"]["sha256"])
        docs[a]["tap"]["netlist"], docs[bb]["tap"]["netlist"] = docs[bb]["tap"]["netlist"], docs[a]["tap"]["netlist"]
        fake = json.loads(json.dumps(docs[a]))
        fake["tap"]["id"] = fake["tap"]["id"].rsplit("/", 1)[0] + f"/{excl}"
        docs[excl] = fake
        for t in (a, bb, excl):
            spit(os.path.join(tam, str(t)), json.dumps(docs[t]))
        out, _ = run("verify_collection.py", "--manifest", self.p("manifest.json"), "--meta", tam, "--ids", "1-10000",
                     "--beacon", self.p("beacon.json"), ok=False)
        self.assertIn(f"token {a}: tap.netlist.sha256", out.stdout)
        self.assertIn(f"token {excl}: outside the token set but not a placeholder", out.stdout)
        # a manifest byte change is caught by the announced hash; a wrong token-set file is rejected
        raw = slurp(self.p("manifest.json"))
        spit(os.path.join(OUT, "manifest-ws.json"), raw + b"\n")
        shutil.copy(self.p("tokenset.bin"), os.path.join(OUT, "tokenset.bin"))
        out, _ = run("verify_collection.py", "--manifest", os.path.join(OUT, "manifest-ws.json"), "--meta", self.p("meta"),
                     "--beacon", self.p("beacon.json"), "--expect-manifest-sha256",
                     "0x" + hashlib.sha256(raw).hexdigest(), ok=False)
        self.assertIn("!= announced", out.stdout)
        bad_ts = os.path.join(OUT, "tokenset-bad.bin")
        spit(bad_ts, slurp(self.p("tokenset.bin"))[:-4] + (10000).to_bytes(4, "big") if ids[-1] != 10000
             else slurp(self.p("tokenset.bin"))[4:] + (10001).to_bytes(4, "big"))
        out, _ = run("verify_collection.py", "--manifest", self.p("manifest.json"), "--meta", self.p("meta"),
                     "--token-set-file", bad_ts, "--beacon", self.p("beacon.json"), ok=False)
        self.assertIn("token-set file does not hash", out.stdout)


class Units(unittest.TestCase):
    def test_round_timing(self):
        info = {"genesis_time": 1692803367, "period": 3}
        self.assertEqual(drand.round_at(info, 1793448000), 33548212)   # profile example, on a boundary
        self.assertEqual(drand.round_time(info, 33548212), 1793448000)
        self.assertEqual(drand.round_at(info, 1793448001), 33548213)   # first round at or after t

    def test_chain_hash_live(self):
        info = drand.fetch_info()
        self.assertEqual(drand.chain_hash_of(info), drand.QUICKNET)
        self.assertEqual(info["schemeID"], "bls-unchained-g1-rfc9380")

    def test_bad_beacon_rejected(self):
        with self.assertRaises(drand.DrandError):
            drand.check_beacon({"round": 5, "randomness": "00" * 32, "signature": "11" * 48}, 5)

    def test_token_set_loader(self):
        ids = load_token_ids(TOKENS)
        self.assertEqual(len(ids), 7000)
        owners = os.path.join(DRAFTS, "tools", "tokenset", "owners.json")
        if os.path.exists(owners):
            o = read_json(owners)["owners"]
            self.assertTrue(all(o[str(t)] != "0x000000000000000000000000000000000000dead" for t in ids))
        self.assertEqual(MAX_NETLIST_BYTES, 49152)

    def test_build_rejects(self):
        import build_pools
        work = tempfile.mkdtemp(prefix="tct1-neg-", dir=OUT)
        write_inputs(work)
        rows = slurp(os.path.join(work, "images.csv"), "r").splitlines()
        spit(os.path.join(work, "img-short.csv"), "\n".join(rows[:-1]) + "\n")
        with self.assertRaises(build_pools.BuildError) as cm:
            build_pools.build_rarity(os.path.join(work, "img-short.csv"), cache=NETCACHE)
        self.assertIn("quota is 3500", str(cm.exception))
        # a design table whose hash does not match the chain file
        r = read_json(RARITY_FILE)
        r["designs"][0]["netlistSha256"] = "0x" + "ab" * 32
        spit(os.path.join(work, "rarity-bad.json"), json.dumps(r))
        with self.assertRaises((build_pools.BuildError, KeyError)):
            build_pools.build_rarity(os.path.join(work, "images.csv"), os.path.join(work, "rarity-bad.json"),
                                     cache=os.path.join(work, "emptycache"), rpc="http://127.0.0.1:9")
        # invalid netlist file (legacy mode)
        bad = os.path.join(work, "bad.tapnet")
        spit(bad, b"TAPNET\x01\x00" + b"\x00" * 8)
        spit(os.path.join(work, "net-bad.csv"), "tier,processor,circuitId,block,file\nMythic,0x" + "11" * 20 + ",1,1," + bad + "\n")
        with self.assertRaises(build_pools.BuildError) as cm:
            build_pools.build(os.path.join(work, "images.csv"), os.path.join(work, "net-bad.csv"))
        self.assertIn("no records", str(cm.exception))

    def test_chain_read(self):
        """Read circuit 17851 of processor 30 at the pinned block and compare with the example file."""
        import build_pools
        try:
            data = build_pools.file_from_rpcs(["https://tapeout.net/rpc"], "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c",
                                              17851, 128200681, [])
        except build_pools.BuildError as e:
            self.skipTest(f"archive node unavailable: {e}")
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         "ecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e")


def tearDownModule():
    if TIMES:
        res = {"times_s": {k: round(v, 2) for k, v in TIMES.items()}, "sizes": SIZES, "out": OUT, "tokens": TOKENS}
        print("\n" + json.dumps(res, indent=1))
        with open(os.path.join(OUT, "test-results.json"), "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
