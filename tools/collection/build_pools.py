#!/usr/bin/env python3
"""Build the IMAGE_V1 and NETLIST_V1 pools of TapeCode-Test1 (stdlib only, MIT).

  build_pools.py --images images.csv --out work/ [--rarity rarity-7000.json] [--netcache DIR]   # default
  build_pools.py --images images.csv --netlists netlists.csv --out work/ --supply 10000          # legacy

Default (rarity) mode: the netlist pool follows tools/collection/RARITY.md and its design table
rarity-7000.json (size rule; tiers Mythic 70x1, Legendary 140x2, Epic 350x3, Rare 350x6, Common 500x7 =
7,000 slots). Each design's file is built from chain (BNB Smart Chain archive node, read-only eth_call
circuitInfo/netlist at the table's block, wrapped by tapnft.file_from_chain) or taken from --netcache
(<sha256-hex>.tapnet, filled on first run); its SHA-256 must equal the table's netlistSha256 and its
NAND/LATCH counts the table's N/L. tap.source = {chainId 56, processor, circuitId, block, name
"<id>.<processor number>.tape", container = opener.accountOf(processor, circuitId)} (draft A §3.2 item 5).
Image quotas per tier = the rarity table's token counts.

Inputs (CSV with a header row, or a JSON array of objects; relative paths resolve against the input
file's directory):

  images:   tier, and either path (the image file, hashed here) or sha256 (0x + 64 hex, precomputed);
            optional ext (default: the path's suffix, else "png").
  netlists (legacy mode): tier, processor, circuitId, block, optional chainId (default 56) and name, and
            either file (a .tapnet file) or rpc (JSON-RPC URLs separated by spaces or ';'); quotas and the
            edition plan from tct1_quota.

Checks: every netlist passes tapnft.check_file and is <= 49,152 bytes; no value is zero; image hashes are
distinct; each tier's image count equals its quota; the netlist pool has one entry per token.

Pool order (committed by the Merkle roots): tiers Mythic..Common; inside a tier, images by SHA-256
ascending, netlists by SHA-256 ascending with the copies of one hash consecutive.

Writes <out>/pools.json and <out>/net/<sha256-hex>.tapnet (the distinct netlist files, for upload).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import urllib.request

from _paths import (BSC_ARCHIVE_RPC, BSC_OPENER, BSC_PROCESSOR_NUMBER, MAX_NETLIST_BYTES, RARITY_FILE, SUPPLY,
                    ZERO32, compact, is_hex32, read_json, tapnft, tct1_quota, write_bytes)

SEL_CIRCUIT_INFO = "0x084d60f1"  # circuitInfo(uint256) -> (uint32 nIn, uint32 nOut, uint32 nState, uint32 gateCount)
SEL_NETLIST = "0x3fc4be56"       # netlist(uint256) -> bytes
SEL_ACCOUNT_OF = "0x0c1905e5"    # accountOf(address,uint256) -> address (TAP-10 container opener)


class BuildError(Exception):
    pass


def load_rows(path: str) -> list:
    with open(path, "rb") as f:
        raw = f.read()
    if path.lower().endswith(".json"):
        rows = json.loads(raw)
        if isinstance(rows, dict):
            rows = rows.get("rows") or rows.get("entries")
        if not isinstance(rows, list):
            raise BuildError(f"{path}: expected a JSON array of objects")
        return rows
    text = raw.decode("utf-8-sig")
    return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(text.splitlines())]


def _resolve(base: str, p: str) -> str:
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


# ---------------------------------------------------------------- chain reads (read-only eth_call)

def _rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, body, {"content-type": "application/json", "user-agent": "tct1-collection"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if "error" in res:
        raise BuildError(f"{url}: {res['error']}")
    return res["result"]


def _words(hexdata: str) -> bytes:
    b = bytes.fromhex(hexdata[2:] if hexdata.startswith("0x") else hexdata)
    if len(b) % 32:
        raise BuildError("ABI return data is not a multiple of 32 bytes")
    return b


def read_circuit(url: str, processor: str, circuit_id: int, block: int) -> tuple:
    arg = circuit_id.to_bytes(32, "big").hex()
    tag = hex(block)
    info = _words(_rpc(url, "eth_call", [{"to": processor, "data": SEL_CIRCUIT_INFO + arg}, tag]))
    if len(info) < 128:
        raise BuildError(f"{url}: circuitInfo returned {len(info)} bytes")
    n_in, n_out, n_state, gates = (int.from_bytes(info[32 * i:32 * i + 32], "big") for i in range(4))
    net = _words(_rpc(url, "eth_call", [{"to": processor, "data": SEL_NETLIST + arg}, tag]))
    off = int.from_bytes(net[:32], "big")
    ln = int.from_bytes(net[off:off + 32], "big")
    if off + 32 + ln > len(net):
        raise BuildError(f"{url}: netlist() return data truncated")
    return n_in, n_out, n_state, gates, net[off + 32:off + 32 + ln]


def file_from_rpcs(urls: list, processor: str, circuit_id: int, block: int, warnings: list) -> bytes:
    results, errors = [], []
    for u in urls:
        try:
            results.append((u, read_circuit(u, processor, circuit_id, block)))
        except Exception as e:  # a pruned node answers "missing trie node"; keep going
            errors.append(f"{u}: {e}")
    if not results:
        raise BuildError(f"{processor}#{circuit_id} at {block}: no node answered: {errors}")
    first = results[0][1]
    for u, r in results[1:]:
        if r != first:
            raise BuildError(f"{processor}#{circuit_id} at {block}: {u} disagrees with {results[0][0]}")
    if len(results) == 1:
        warnings.append(f"{processor}#{circuit_id} at block {block}: single-source read ({results[0][0]})")
    n_in, n_out, n_state, gates, netlist = first
    data = tapnft.file_from_chain(netlist, n_in, n_out)  # raises Invalid (e.g. REF records)
    mt = tapnft.check_file(data)
    if mt.latch != n_state or mt.gates != gates:
        raise BuildError(f"{processor}#{circuit_id}: file metrics {mt.as_json()} differ from circuitInfo "
                         f"(nState {n_state}, gateCount {gates})")
    return data


# ---------------------------------------------------------------- pools

def _source(row: dict) -> dict:
    proc = str(row.get("processor", "")).lower()
    cid = str(row.get("circuitId", "")).strip()
    try:
        block = int(row.get("block"))
        chain = int(row.get("chainId") or 56)
    except (TypeError, ValueError):
        raise BuildError(f"netlist row {row}: block and chainId must be integers") from None
    if not tapnft.ADDR.match(proc):
        raise BuildError(f"netlist row {row}: processor must be a 0x address")
    if not tapnft.DEC.match(cid):
        raise BuildError(f"netlist row {row}: circuitId must be a decimal string")
    src = {"chainId": chain, "processor": proc, "circuitId": cid, "block": block}
    name = str(row.get("name") or "").strip()
    if name:
        if not tapnft.TAPE_NAME.match(name):
            raise BuildError(f"netlist row {row}: name {name!r} is not a TAP-10 on-chain name")
        src["name"] = name
    return src


def load_images(images_path: str, slots: dict, errors: list) -> list:
    tiers = list(slots)
    base = os.path.dirname(os.path.abspath(images_path))
    imgs, seen = [], {}
    for n, row in enumerate(load_rows(images_path), 1):
        tier = row.get("tier")
        if tier not in tiers:
            errors.append(f"image row {n}: tier {tier!r} not in {tiers}")
            continue
        if row.get("path"):
            p = _resolve(base, row["path"])
            with open(p, "rb") as f:
                h = "0x" + hashlib.sha256(f.read()).hexdigest()
            ext = row.get("ext") or (os.path.splitext(p)[1][1:].lower() or "png")
        elif row.get("sha256"):
            h = str(row["sha256"]).lower()
            ext = row.get("ext") or "png"
        else:
            errors.append(f"image row {n}: needs path or sha256")
            continue
        if not is_hex32(h) or h == ZERO32:
            errors.append(f"image row {n}: hash {h!r} must be non-zero 0x + 64 hex digits")
            continue
        if not re.match(r"^[a-z0-9]{1,8}$", ext):
            errors.append(f"image row {n}: bad ext {ext!r}")
            continue
        if h in seen:
            errors.append(f"image row {n}: duplicate image hash {h} (also row {seen[h]})")
            continue
        seen[h] = n
        imgs.append({"image": h, "tier": tier, "ext": ext})
    for t in tiers:
        c = sum(1 for e in imgs if e["tier"] == t)
        if c != slots[t]:
            errors.append(f"images: tier {t} has {c} images, quota is {slots[t]}")
    imgs.sort(key=lambda e: (tiers.index(e["tier"]), e["image"]))

    return imgs


def build(images_path: str, netlists_path: str, supply: int = SUPPLY, allow_cross_tier: bool = False,
          drop_oversize: bool = False) -> tuple:
    """Return (pools document, {hash-hex: file bytes})."""
    tiers = tct1_quota.TIERS
    quotas = tct1_quota.quotas(supply, tct1_quota.PCT)
    slots = dict(zip(tiers, quotas))
    warnings, errors = [], []

    imgs = load_images(images_path, slots, errors)
    # netlists
    base = os.path.dirname(os.path.abspath(netlists_path))
    files, designs = {}, {}
    for n, row in enumerate(load_rows(netlists_path), 1):
        tier = row.get("tier")
        try:
            if tier not in tiers:
                raise BuildError(f"tier {tier!r} not in {tiers}")
            src = _source(row)
            if row.get("file"):
                with open(_resolve(base, row["file"]), "rb") as f:
                    data = f.read()
            elif row.get("rpc"):
                urls = [u for u in re.split(r"[;\s]+", row["rpc"]) if u] if isinstance(row["rpc"], str) else list(row["rpc"])
                data = file_from_rpcs(urls, src["processor"], int(src["circuitId"]), src["block"], warnings)
            else:
                raise BuildError("needs file or rpc")
            mt = tapnft.check_file(data)
        except (BuildError, tapnft.Invalid, OSError) as e:
            errors.append(f"netlist row {n}: {e}")
            continue
        h = tapnft.hex32(tapnft.netlist_hash(data))
        if len(data) > MAX_NETLIST_BYTES:
            msg = f"netlist row {n}: {h} is {len(data)} bytes > {MAX_NETLIST_BYTES} (cannot be stored on chain)"
            (warnings if drop_oversize else errors).append(msg + (" - dropped" if drop_oversize else ""))
            continue
        if h == ZERO32:
            errors.append(f"netlist row {n}: zero hash")
            continue
        d = designs.get(h)
        if d is None:
            files[h] = data
            designs[h] = {"tiers": [tier], "bytes": len(data), **mt.as_json(), "source": src,
                          "file": f"net/{h[2:]}.tapnet", "rows": [n]}
            continue
        d["rows"].append(n)
        if tier not in d["tiers"]:
            if not allow_cross_tier:
                errors.append(f"netlist {h} listed in tiers {d['tiers'] + [tier]} (rows {d['rows']}); "
                              "a design must belong to one tier")
                continue
            d["tiers"].append(tier)
        if src != d["source"]:
            # Same bytes from two circuits: keep the lowest (chainId, processor, circuitId) as the source.
            a, b = d["source"], src
            ka = (a["chainId"], a["processor"], int(a["circuitId"]))
            kb = (b["chainId"], b["processor"], int(b["circuitId"]))
            if kb < ka:
                d["source"] = src
            warnings.append(f"netlist {h}: identical file from several circuits; source = "
                            f"{d['source']['processor']}#{d['source']['circuitId']}")

    for h, d in sorted(designs.items()):
        if len(d["tiers"]) > 1:
            warnings.append(f"netlist {h} is in tiers {d['tiers']} - allowed by --allow-cross-tier; "
                            "its edition counts across tiers")
    plan, nets = [], []
    for t in tiers:
        hs = sorted(h for h, d in designs.items() if t in d["tiers"])
        if not hs:
            errors.append(f"netlists: tier {t} has no eligible designs")
            continue
        q, hi, lo = tct1_quota.editions(slots[t], len(hs))
        plan.append({"tier": t, "slots": slots[t], "designs": len(hs), "q": q, "withQPlus1": hi, "withQ": lo})
        if q == 0:
            warnings.append(f"netlists: tier {t} has {len(hs)} designs for {slots[t]} slots; "
                            f"{len(hs) - hi} designs get no copy")
        for k, h in enumerate(hs):
            for _ in range(q + 1 if k < hi else q):
                nets.append({"netlist": h, "tier": t, "source": designs[h]["source"]})
    if len(nets) != supply and not errors:
        errors.append(f"netlists: {len(nets)} slots filled, supply is {supply}")
    copies = {}
    for e in nets:
        copies[e["netlist"]] = copies.get(e["netlist"], 0) + 1
    for h, d in designs.items():
        d["copies"] = copies.get(h, 0)

    if errors:
        raise BuildError("\n".join(errors))
    doc = {"supply": supply, "tiers": tiers, "pct": tct1_quota.PCT, "quotas": quotas, "plan": plan,
           "images": imgs, "netlists": nets, "designs": dict(sorted(designs.items())), "warnings": warnings}
    return doc, files


def _batch(url: str, calls: list, tries: int = 6) -> list:
    """One JSON-RPC batch of eth_call [(to, data, blocktag)]; returns the raw results (raises on any error)."""
    import time as _t
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": "eth_call", "params": [{"to": to, "data": d}, tag]}
                       for i, (to, d, tag) in enumerate(calls)]).encode()
    delay = 1.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, body, {"content-type": "application/json", "user-agent": "tct1-collection"})
            with urllib.request.urlopen(req, timeout=120) as r:
                res = json.load(r)
            if isinstance(res, dict):
                raise BuildError(f"{url}: {res}")
            res.sort(key=lambda x: x["id"])
            if len(res) != len(calls) or any("error" in x for x in res):
                raise BuildError(f"{url}: {[x.get('error') for x in res if 'error' in x][:2] or 'short batch'}")
            return [x["result"] for x in res]
        except Exception:
            if attempt == tries - 1:
                raise
            _t.sleep(delay)
            delay *= 2


def fetch_designs(designs: list, block: int, rpc: str, opener: str, cache: str, warnings: list,
                  batch_designs: int = 8) -> dict:
    """{netlistSha256: (file bytes, container)} for every design, from the cache or read-only eth_call."""
    out, todo = {}, []
    cont_path = os.path.join(cache, "containers.json") if cache else None
    containers = read_json(cont_path) if cont_path and os.path.exists(cont_path) else {}
    for d in designs:
        h = d["netlistSha256"].lower()
        key = f"{d['processor'].lower()}/{d['circuitId']}"
        p = os.path.join(cache, h[2:] + ".tapnet") if cache else None
        if p and os.path.exists(p) and key in containers:
            with open(p, "rb") as f:
                out[h] = (f.read(), containers[key])
        else:
            todo.append(d)
    tag = hex(block)
    for k in range(0, len(todo), batch_designs):
        part = todo[k:k + batch_designs]
        calls = []
        for d in part:
            proc, arg = d["processor"].lower(), int(d["circuitId"]).to_bytes(32, "big").hex()
            calls += [(proc, SEL_CIRCUIT_INFO + arg, tag), (proc, SEL_NETLIST + arg, tag),
                      (opener, SEL_ACCOUNT_OF + bytes.fromhex(proc[2:]).rjust(32, b"\0").hex() + arg, tag)]
        try:
            res = _batch(rpc, calls)
        except BuildError:
            raise
        except Exception as e:
            raise BuildError(f"chain read from {rpc} failed: {e}") from None
        for j, d in enumerate(part):
            info, net, acct = (_words(x) for x in res[3 * j:3 * j + 3])
            n_in, n_out, n_state, gates = (int.from_bytes(info[32 * i:32 * i + 32], "big") for i in range(4))
            off = int.from_bytes(net[:32], "big")
            ln = int.from_bytes(net[off:off + 32], "big")
            data = tapnft.file_from_chain(net[off + 32:off + 32 + ln], n_in, n_out)
            mt = tapnft.check_file(data)
            if mt.latch != n_state or mt.gates != gates:
                raise BuildError(f"{d['processor']}#{d['circuitId']}: metrics differ from circuitInfo")
            container = "0x" + acct[12:32].hex()
            h = d["netlistSha256"].lower()
            out[h] = (data, container)
            if cache:
                write_bytes(os.path.join(cache, h[2:] + ".tapnet"), data)
                containers[f"{d['processor'].lower()}/{d['circuitId']}"] = container
        if cache:
            write_bytes(cont_path, compact(containers))
        print(f"  read {min(k + batch_designs, len(todo))}/{len(todo)} designs from {rpc}", file=sys.stderr)
    if todo:
        warnings.append(f"{len(todo)} designs read from a single node ({rpc}) at block {block}")
    return out


def build_rarity(images_path: str, rarity_path: str = RARITY_FILE, cache: str = None, rpc: str = BSC_ARCHIVE_RPC,
                 opener: str = BSC_OPENER, proc_numbers: dict = None) -> tuple:
    """Rarity mode (RARITY.md). Return (pools document, {hash-hex: file bytes})."""
    proc_numbers = proc_numbers or BSC_PROCESSOR_NUMBER
    with open(rarity_path, "rb") as f:
        rraw = f.read()
    r = json.loads(rraw)
    tiers = [t["tier"] for t in r["tiers"]]
    if tiers != tct1_quota.TIERS:
        raise BuildError(f"rarity tiers {tiers} differ from {tct1_quota.TIERS}")
    slots = {t["tier"]: t["tokens"] for t in r["tiers"]}
    supply = sum(slots.values())
    if supply != r["supply"]:
        raise BuildError(f"rarity tiers sum to {supply}, table says supply {r['supply']}")
    warnings, errors = [], []
    imgs = load_images(images_path, slots, errors)
    if errors:
        raise BuildError("\n".join(errors))

    by_tier = {t: [] for t in tiers}
    seen = set()
    for d in r["designs"]:
        h = d["netlistSha256"].lower()
        if h in seen:
            raise BuildError(f"design table lists {h} twice")
        seen.add(h)
        by_tier[d["tier"]].append(d)
    plan = []
    for t in r["tiers"]:
        ds = by_tier[t["tier"]]
        if len(ds) != t["designs"] or any(d["copies"] != t["copies"] for d in ds):
            raise BuildError(f"tier {t['tier']}: {len(ds)} designs / copies differ from {t['designs']} x {t['copies']}")
        plan.append({"tier": t["tier"], "slots": t["tokens"], "designs": t["designs"], "q": t["copies"],
                     "withQPlus1": 0, "withQ": t["designs"]})

    fetched = fetch_designs(r["designs"], r["block"], rpc, opener, cache, warnings)
    files, designs, nets = {}, {}, []
    for t in tiers:
        for d in sorted(by_tier[t], key=lambda d: d["netlistSha256"].lower()):
            h = d["netlistSha256"].lower()
            data, container = fetched[h]
            if tapnft.hex32(tapnft.netlist_hash(data)) != h:
                raise BuildError(f"{d['processor']}#{d['circuitId']}: file hash differs from the table's {h}")
            mt = tapnft.check_file(data)
            if (mt.nand, mt.latch) != (d["N"], d["L"]):
                raise BuildError(f"{h}: NAND/LATCH {mt.nand}/{mt.latch} differ from the table's N/L {d['N']}/{d['L']}")
            if len(data) > MAX_NETLIST_BYTES:
                raise BuildError(f"{h}: {len(data)} bytes > {MAX_NETLIST_BYTES}")
            proc = d["processor"].lower()
            if proc not in proc_numbers:
                raise BuildError(f"processor {proc} has no known processor number (TAP-10 name)")
            src = {"chainId": r["chainId"], "processor": proc, "circuitId": str(d["circuitId"]), "block": r["block"],
                   "name": tapnft.tape_name(int(d["circuitId"]), proc_numbers[proc], None), "container": container}
            files[h] = data
            designs[h] = {"tiers": [t], "bytes": len(data), **mt.as_json(), "source": src, "copies": d["copies"],
                          "file": f"net/{h[2:]}.tapnet", "S": d["S"], "taskId": d["taskId"]}
            nets += [{"netlist": h, "tier": t, "source": src}] * d["copies"]
    if len(nets) != supply:
        raise BuildError(f"netlist pool has {len(nets)} entries, supply is {supply}")
    doc = {"mode": "rarity", "supply": supply, "tiers": tiers, "quotas": [slots[t] for t in tiers], "plan": plan,
           "rarity": {"rule": r["rule"], "block": r["block"], "chainId": r["chainId"], "mining": r["mining"],
                      "params": r["params"], "tableSha256": "0x" + hashlib.sha256(rraw).hexdigest()},
           "images": imgs, "netlists": nets, "designs": dict(sorted(designs.items())), "warnings": warnings}
    return doc, files


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", required=True)
    ap.add_argument("--out", required=True, help="output directory (pools.json, net/)")
    ap.add_argument("--rarity", default=RARITY_FILE, help="design table (default: rarity-7000.json)")
    ap.add_argument("--netcache", help="cache directory for netlist files read from chain")
    ap.add_argument("--rpc", default=BSC_ARCHIVE_RPC, help="BNB Smart Chain archive node (read-only eth_call)")
    ap.add_argument("--netlists", help="legacy mode: netlist CSV/JSON (quotas from tct1_quota)")
    ap.add_argument("--supply", type=int, default=SUPPLY, help="legacy mode supply")
    ap.add_argument("--allow-cross-tier", action="store_true",
                    help="legacy mode: allow one netlist hash in several tiers (synthetic tests only)")
    ap.add_argument("--drop-oversize", action="store_true",
                    help="legacy mode: drop netlists above 49,152 bytes with a warning instead of failing")
    a = ap.parse_args(argv)
    try:
        if a.netlists:
            doc, files = build(a.images, a.netlists, a.supply, a.allow_cross_tier, a.drop_oversize)
        else:
            doc, files = build_rarity(a.images, a.rarity, a.netcache, a.rpc)
    except (BuildError, tapnft.Invalid) as e:
        print("error:", str(e).replace("\n", "\nerror: "), file=sys.stderr)
        return 1
    for h, data in files.items():
        if doc["designs"][h]["copies"]:
            write_bytes(os.path.join(a.out, "net", h[2:] + ".tapnet"), data)
    write_bytes(os.path.join(a.out, "pools.json"), compact(doc))
    print(f"{'tier':10} {'slots':>6} {'designs':>8}  edition plan")
    for p in doc["plan"]:
        q = p["q"]
        plan = (f"{p['withQPlus1']} x {q + 1} + " if p["withQPlus1"] else "") + f"{p['withQ']} x {q}"
        print(f"{p['tier']:10} {p['slots']:>6} {p['designs']:>8}  {plan}")
    used = sum(1 for d in doc["designs"].values() if d["copies"])
    print(f"images {len(doc['images'])}, netlist slots {len(doc['netlists'])}, distinct netlists {used}, "
          f"netlist bytes {sum(d['bytes'] for d in doc['designs'].values() if d['copies'])}")
    for w in doc["warnings"]:
        print("warning:", w)
    print("wrote", os.path.join(a.out, "pools.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
