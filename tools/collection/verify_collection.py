#!/usr/bin/env python3
"""Independent checker for a Netlist-Bound NFT collection revealed with drand (stdlib only, MIT).

Anyone can run it. It trusts nothing produced by the operator except the files it is given, and recomputes
everything with tapnft.py (draft A reference implementation) and drand.py:

  verify_collection.py --manifest manifest.json --meta meta/ [--token-set-file tokenset.bin] [--ids 1-10000]
  verify_collection.py --manifest https://.../manifest.json --base-url https://gateway/.../meta/ \
      [--expect-manifest-sha256 0x...] [--round N] [--beacon beacon.json] [--netlists net/ | --fetch-netlists]
      [--design-table rarity-7000.json] [--reveal reveal.json] [--published-at 2026-10-28T10:00:00Z]
      [--freeze-rpc https://rpc.xlayer.tech]

Checks
  manifest  SHA-256 of the bytes as fetched (optionally against an announced value); tapnft.check_manifest
            (structure of draft A §5.1-§5.2, roots recomputed); reveal.source == drand.
  token set set mode: the token-set file (--token-set-file, else tokenset.bin next to a local manifest, else
            the first fetchable http(s) URI of tokenSet.uris) passes tapnft.check_token_set.
  seed      drand chain info checked against the manifest's chainHash; the round's beacon from several
            relays (or a saved beacon) with randomness == SHA-256(signature) (BLS NOT checked, see
            drand.py); --round must equal the manifest's round; --published-at must precede the round.
  tokens    for every id of --ids (default: the covered ids): metadata (<dir>/<id> or <base-url><id>)
            passes tapnft.check_metadata; tap.id is right; tap.manifest.sha256 == manifestHash. A covered id
            is revealed and its tap.image / tap.netlist hashes equal the entries of tapnft.assignment; its
            tap.edition equals the recomputed edition; tap.source equals the manifest entry's source, or
            (with --design-table, whose SHA-256 must equal rules.designTable.sha256) the table's processor
            and circuitId for that netlist hash. An id outside the token set must be a placeholder: state
            unrevealed, no tap.image, no tap.netlist. tap.content, if present, has a valid shape and its
            image/netlist paths name the token's hashes. The set passes tapnft.check_editions. tap.pod, if
            present, passes pod_validate.validate_tap when the draft-C validator is importable.
  netlists  with --netlists DIR (<sha256-hex>.tapnet) or --fetch-netlists (https:// URIs only): each distinct
            file passes tapnft.check_netlist_against_metadata.
  reveal    with --reveal: seeds, entry indices, values, every Merkle proof (tapnft.merkle_verify), the
            excluded list and the SHA-256 of every metadata file listed there.
  freeze    with --freeze-rpc: eth_call of the manifest's freeze probe (read-only), printed as the L0 status.

Exit status 0 if no mismatch was found, 1 otherwise.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import drand
from _paths import POD_DIR, tapnft


def fetch(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"user-agent": "tct1-verify"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def read_source(path_or_url: str) -> bytes:
    if re.match(r"^https?://", path_or_url):
        return fetch(path_or_url)
    with open(path_or_url, "rb") as f:
        return f.read()


def parse_ids(spec: str) -> list:
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return sorted(set(out))


class Report:
    def __init__(self, limit: int):
        self.items, self.limit = [], limit

    def bad(self, msg: str) -> None:
        self.items.append(msg)
        if len(self.items) <= self.limit:
            print("MISMATCH:", msg)

    def need(self, cond: bool, msg: str) -> bool:
        if not cond:
            self.bad(msg)
        return cond


def content_problems(c, tap) -> list:
    out = []
    if not isinstance(c, dict):
        return ["tap.content must be an object"]
    if not (isinstance(c.get("chainId"), int) and c["chainId"] > 0):
        out.append("tap.content.chainId")
    if not (isinstance(c.get("container"), str) and tapnft.ADDR.match(c["container"])):
        out.append("tap.content.container must be a lowercase address")
    if not (isinstance(c.get("name"), str) and tapnft.TAPE_NAME.match(c["name"])):
        out.append("tap.content.name must be a TAP-10 on-chain name")
    p = c.get("paths")
    if not (isinstance(p, dict) and p and all(isinstance(v, str) and v and not v.startswith("/") and ".." not in v
                                              for v in p.values())):
        return out + ["tap.content.paths must map names to relative paths"]
    for f in ("image", "netlist"):
        if f in p and f in tap and tap[f]["sha256"][2:] not in p[f]:
            out.append(f"tap.content.paths.{f} does not name tap.{f}.sha256")
    if "lock" in c and not (isinstance(c["lock"], str) and tapnft.ADDR.match(c["lock"])):
        out.append("tap.content.lock must be a lowercase address")
    return out


def freeze_probe(rpc: str, fr: dict) -> str:
    sig = fr["call"]
    sel = {"uriFrozen()": "0x274e4a1d"}.get(sig)
    if sel is None:
        return f"freeze probe {sig}: selector unknown to this tool (needs keccak-256); check it with cast"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": fr["contract"], "data": sel}, "latest"]}).encode()
    req = urllib.request.Request(rpc, body, {"content-type": "application/json", "user-agent": "tct1-verify"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if "error" in res:
        return f"freeze probe failed: {res['error']}"
    val = int(res["result"], 16) == 1
    return f"L0 (metadata only); {sig} on chain {fr['chainId']} = {str(val).lower()}" + \
        ("" if val == fr["expect"] else " -> NOT frozen: the owner can still change tokenURI")


def load_token_set(m: dict, a) -> list:
    tries = []
    if a.token_set_file:
        tries.append(a.token_set_file)
    elif not re.match(r"^https?://", a.manifest):
        tries.append(os.path.join(os.path.dirname(os.path.abspath(a.manifest)), "tokenset.bin"))
    tries += [u for u in m["collection"]["tokenSet"]["uris"] if re.match(r"^https?://", u)]
    errs = []
    for src in tries:
        try:
            data = read_source(src)
        except Exception as e:
            errs.append(f"{src}: {e}")
            continue
        ids = tapnft.check_token_set(m, data)  # raises on a wrong file
        print(f"token set: {len(ids)} ids from {src}, check_token_set ok")
        return ids
    raise tapnft.Invalid(f"token-set file not available: {errs}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="path or https URL")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--meta", help="directory with one file per token id")
    src.add_argument("--base-url", help="tokenURI = base-url + decimal id")
    ap.add_argument("--token-set-file", help="set mode: the token-set file (u32be ids)")
    ap.add_argument("--ids", help="every token id of the contract, e.g. 1-10000 (ids outside the set must be placeholders)")
    ap.add_argument("--expect-manifest-sha256")
    ap.add_argument("--round", type=int, help="the announced drand round (must equal the manifest's)")
    ap.add_argument("--beacon", help="saved beacon; default: fetch and verify live")
    ap.add_argument("--netlists", help="directory of <sha256-hex>.tapnet files")
    ap.add_argument("--fetch-netlists", action="store_true", help="fetch https:// netlist URIs")
    ap.add_argument("--design-table", help="rarity design table committed by rules.designTable.sha256")
    ap.add_argument("--reveal", help="reveal.json to cross-check (proofs, indices, metadata hashes)")
    ap.add_argument("--published-at", help="UTC time the manifest hash became public (e.g. its container block)")
    ap.add_argument("--freeze-rpc", help="JSON-RPC URL of the collection's chain, for the freeze probe")
    ap.add_argument("--allow-unrevealed", action="store_true",
                    help="accept unrevealed covered tokens (blind-box phase; works before the round is produced)")
    ap.add_argument("--jobs", type=int, default=16, help="parallel HTTP fetches in --base-url mode")
    ap.add_argument("--show", type=int, default=25, help="print at most this many mismatches")
    a = ap.parse_args(argv)
    rep = Report(a.show)
    t0 = time.time()

    raw = read_source(a.manifest)
    mh = "0x" + hashlib.sha256(raw).hexdigest()
    print(f"manifest sha256 {mh} ({len(raw)} bytes)")
    if a.expect_manifest_sha256:
        rep.need(mh == a.expect_manifest_sha256.lower(), f"manifest hash {mh} != announced {a.expect_manifest_sha256}")
    try:
        m = tapnft.check_manifest(raw)
    except tapnft.Invalid as e:
        print(f"FAILED: manifest invalid: {e}")
        return 1
    if m["reveal"]["source"] != "drand":
        print("FAILED: this checker handles reveal.source == drand only")
        return 1
    c, rv = m["collection"], m["reveal"]
    set_mode = "tokenSet" in c
    try:
        ids = load_token_set(m, a) if set_mode else list(range(c["firstTokenId"], c["firstTokenId"] + c["supply"]))
    except tapnft.Invalid as e:
        print(f"FAILED: {e}")
        return 1
    n = len(ids)
    covered = set(ids)
    check_ids = parse_ids(a.ids) if a.ids else ids
    rep.need(covered <= set(check_ids), "--ids does not contain every covered id")
    print(f"manifest ok (tapnft.check_manifest); {'set' if set_mode else 'range'} mode, {n} covered ids; "
          f"checking {len(check_ids)} ids")

    table = None
    if a.design_table:
        traw = read_source(a.design_table)
        want = ((m.get("rules") or {}).get("designTable") or {}).get("sha256")
        rep.need("0x" + hashlib.sha256(traw).hexdigest() == want,
                 f"design table SHA-256 differs from rules.designTable.sha256 ({want})")
        table = {d["netlistSha256"].lower(): d for d in json.loads(traw)["designs"]}

    # seed
    if a.round is not None:
        rep.need(a.round == rv["round"], f"announced round {a.round} != manifest round {rv['round']}")
    info = drand.fetch_info(rv["chainHash"])
    produced = drand.round_time(info, rv["round"])
    print(f"drand chain {rv['chainHash']} info verified; round {rv['round']} produced at {drand.utc(produced)}")
    if a.published_at:
        pub = drand.parse_utc(a.published_at)
        rep.need(pub < produced, f"manifest published {drand.utc(pub)} is not before the round ({drand.utc(produced)})")
    blind = a.allow_unrevealed and not a.beacon and produced > time.time()
    labels = [p["label"] for p in m["pools"]]
    assign = {}
    if blind:
        print("round not produced yet: checking the blind-box set only (no seed, no assignment)")
        beacon, master = None, None
    else:
        beacon = drand.get_beacon(rv["chainHash"], rv["round"], a.beacon)
        master = bytes.fromhex(beacon["randomness"])
        print(f"masterSeed 0x{beacon['randomness']} (randomness == SHA-256(signature); BLS signature not checked)")
        for t in check_ids:
            r = tapnft.assignment(m, master, t, ids if set_mode else None)
            if r is not None:
                assign[t] = [r[lab] for lab in labels]
    expected = {}
    for t, ks in assign.items():
        for k, p in enumerate(m["pools"]):
            for f in p["fields"]:
                expected.setdefault(f, {})[t] = p["entries"][ks[k]][f]
    exp_edition = {}
    if "netlist" in expected:
        groups = {}
        for t in sorted(expected["netlist"]):
            groups.setdefault(expected["netlist"][t], []).append(t)
        for ts in groups.values():
            for rank, t in enumerate(ts, 1):
                exp_edition[t] = {"index": rank, "of": len(ts)} if len(ts) > 1 else None
    net_pool = next((k for k, p in enumerate(m["pools"]) if "netlist" in p["fields"]), None)

    # tokens
    def load(t):
        try:
            if a.meta:
                with open(os.path.join(a.meta, str(t)), "rb") as f:
                    return t, f.read(), None
            return t, fetch(a.base_url + str(t)), None
        except Exception as e:
            return t, None, str(e)

    if a.base_url:
        with ThreadPoolExecutor(a.jobs) as ex:
            loaded = list(ex.map(load, check_ids))
    else:
        loaded = [load(t) for t in check_ids]

    pv = None
    docs, file_hash, by_netlist = [], {}, {}
    n_rev = n_place = 0
    for t, data, err in loaded:
        if data is None:
            rep.bad(f"token {t}: cannot read metadata: {err}")
            continue
        file_hash[t] = "0x" + hashlib.sha256(data).hexdigest()
        try:
            d = json.loads(data)
            tap = tapnft.check_metadata(d)
        except (ValueError, tapnft.Invalid) as e:
            rep.bad(f"token {t}: {e}")
            continue
        want_id = f"eip155:{c['chainId']}/erc721:{c['address']}/{t}"
        rep.need(tap["id"] == want_id, f"token {t}: tap.id {tap['id']} != {want_id}")
        rep.need((tap.get("manifest") or {}).get("sha256") == mh, f"token {t}: tap.manifest.sha256 != manifestHash")
        if "content" in tap:
            for msg in content_problems(tap["content"], tap):
                rep.bad(f"token {t}: {msg}")
        docs.append(d)
        if t not in covered:
            rep.need(tap["state"] == "unrevealed" and "image" not in tap and "netlist" not in tap,
                     f"token {t}: outside the token set but not a placeholder (state {tap['state']})")
            n_place += 1
            continue
        if tap["state"] != "revealed":
            if not a.allow_unrevealed:
                rep.bad(f"token {t}: state {tap['state']}")
            continue
        if blind:
            rep.bad(f"token {t}: revealed before its drand round was produced")
            continue
        n_rev += 1
        for f in ("image", "netlist"):
            if f in expected:
                got = tap[f]["sha256"]
                rep.need(got == expected[f][t], f"token {t}: tap.{f}.sha256 {got} != assigned entry {expected[f][t]}")
        if net_pool is not None:
            es = m["pools"][net_pool]["entries"][assign[t][net_pool]].get("source")
            if es is not None:
                rep.need(tap.get("source") == es, f"token {t}: tap.source differs from the manifest entry's source")
        if table is not None:
            row = table.get(tap["netlist"]["sha256"])
            s = tap.get("source") or {}
            rep.need(row is not None and (s.get("processor"), s.get("circuitId")) == (row["processor"].lower(), str(row["circuitId"])),
                     f"token {t}: tap.source differs from the design table")
        e = exp_edition.get(t)
        rep.need(tap.get("edition") in ((e,) if e else (None, {"index": 1, "of": 1})),
                 f"token {t}: tap.edition {tap.get('edition')} != expected {e}")
        if "pod" in tap or "rig" in tap:
            if pv is None:
                try:
                    sys.path.insert(0, POD_DIR)
                    import pod_validate as pv  # noqa: WPS433
                except ImportError as ex:
                    print(f"note: tap.pod present but the draft-C validator cannot be imported ({ex}); not checked")
                    pv = False
            if pv:
                r = pv.validate_tap(tap)
                rep.need(r.ok, f"token {t}: tap.pod/rig invalid: {r.errors}")
        by_netlist.setdefault(tap["netlist"]["sha256"], tap)
    try:
        tapnft.check_editions(docs)
    except tapnft.Invalid as e:
        rep.bad(f"check_editions: {e}")
    print(f"tokens: {n_rev} revealed, {n_place} excluded placeholders, "
          f"{len(docs) - n_rev - n_place} unrevealed covered documents checked")

    # netlists
    if a.netlists or a.fetch_netlists:
        checked = 0
        for h, tap in sorted(by_netlist.items()):
            data, why = None, ""
            if a.netlists:
                p = os.path.join(a.netlists, h[2:] + ".tapnet")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        data = f.read()
                else:
                    why = f"{p} missing"
            else:
                for u in tap["netlist"]["uris"]:
                    if u.startswith("https://"):
                        try:
                            data = fetch(u)
                            break
                        except Exception as e:
                            why = f"{u}: {e}"
                else:
                    why = why or "no https:// URI"
            if data is None:
                rep.bad(f"netlist {h}: not available ({why})")
                continue
            try:
                tapnft.check_netlist_against_metadata(tap, data)
                checked += 1
            except tapnft.Invalid as e:
                rep.bad(f"netlist {h}: {e}")
        print(f"netlists: {checked}/{len(by_netlist)} distinct files pass check_netlist_against_metadata")

    # reveal.json
    if a.reveal and beacon is not None:
        r = json.loads(read_source(a.reveal))
        rep.need(r.get("manifestSha256") == mh, "reveal.json: manifestSha256 differs")
        rep.need(r.get("masterSeed") == "0x" + beacon["randomness"], "reveal.json: masterSeed differs from drand")
        for k, p in enumerate(m["pools"]):
            s = tapnft.pool_seed(master, c["chainId"], c["address"], p["label"])
            rep.need(r["pools"][k]["seed"] == tapnft.hex32(s), f"reveal.json: seed of {p['label']} differs")
        if a.ids:
            rep.need(r.get("excluded", []) == [t for t in check_ids if t not in covered], "reveal.json: excluded list differs")
        nproof = 0
        for e in r["tokens"]:
            t = e["id"]
            if not rep.need(t in assign, f"reveal.json: token {t} is not covered"):
                continue
            for k, p in enumerate(m["pools"]):
                pe = e["pools"][k]
                rep.need(pe["entry"] == assign[t][k], f"reveal.json: token {t} {p['label']} entry differs")
                vals = [p["entries"][assign[t][k]][f] for f in p["fields"]]
                rep.need(pe["values"] == vals, f"reveal.json: token {t} {p['label']} values differ")
                if "proof" in pe:
                    leaf = tapnft.leaf_hash(pe["entry"], [bytes.fromhex(v[2:]) for v in pe["values"]])
                    ok = tapnft.merkle_verify(bytes.fromhex(p["root"][2:]), n, pe["entry"], leaf,
                                              [bytes.fromhex(h[2:]) for h in pe["proof"]])
                    rep.need(ok, f"reveal.json: token {t} {p['label']} proof does not verify")
                    nproof += 1
            if t in file_hash:
                rep.need(e.get("meta") == file_hash[t], f"reveal.json: token {t} metadata file hash differs")
        rep.need(len(r["tokens"]) == len(assign), "reveal.json: token count differs from the covered ids checked")
        print(f"reveal.json: {len(r['tokens'])} tokens, {nproof} proofs verified")

    if a.freeze_rpc and m.get("freeze"):
        try:
            print(freeze_probe(a.freeze_rpc, m["freeze"]))
        except Exception as e:
            print("freeze probe failed:", e)
    else:
        print("conformance: L0 (metadata only); frozen state not probed (use --freeze-rpc)")

    dt = time.time() - t0
    if rep.items:
        print(f"FAILED: {len(rep.items)} mismatches ({dt:.1f} s)")
        return 1
    print(f"OK: no mismatch ({dt:.1f} s)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except drand.DrandError as e:
        print("error:", e, file=sys.stderr)
        sys.exit(1)
