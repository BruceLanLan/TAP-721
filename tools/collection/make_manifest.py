#!/usr/bin/env python3
"""Write the TapeCode-Test1 manifest (draft A §5) from pools.json (stdlib only, MIT).

  make_manifest.py --pools work/pools.json --at 2026-10-31T12:00:00Z --out work/manifest.json
  make_manifest.py --pools work/pools.json --round 33548212 --out work/manifest.json \
      [--token-set tools/tokenset/tokens.json --token-set-uri tape://…/tct1/tokenset.bin --token-set-uri ipfs://…]

Set mode (default when a token set is given or tools/tokenset/tokens.json exists): collection.tokenSet =
{sha256, count, uris} over the valid ids (draft A §5.4); the token-set file (u32be ids, ascending) is written
next to the manifest as tokenset.bin and must be published with it. Rarity-mode pools add a `rules` member
(rarity rule, snapshot, parameters, SHA-256 of rarity-7000.json and of RARITY.md, max file size) so every
input of the assignment is committed before the seed (§6.1 item 3). The written bytes are re-checked with
tapnft.check_manifest and tapnft.check_token_set.

The reveal round is either given or computed from a UTC time with the LIVE quicknet info (drand.py; the
chain hash is checked against the info). The round must be produced at least --min-lead-hours (default 72,
profile §4 step 3) after now, because the manifest hash has to be public before the seed is known (§6.1).

Output bytes: json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True), no trailing newline.
These bytes are what is published and hashed; never re-serialise the file. Entries carry the hash, the
tier and (netlists) the source circuit; URIs and attributes go into the token metadata (profile §2.2).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time

import drand
import os

from _paths import (CHAIN_ID, CONTRACT, FIRST_TOKEN_ID, FREEZE, IMAGE_LABEL, MAX_CONTAINER_FILE, MAX_NETLIST_BYTES,
                    NETLIST_LABEL, QUICKNET, RARITY_DOC, TOKENS_FILE, ZERO32, compact, load_token_ids, read_json,
                    tapnft, write_bytes)


def pool_root(entries: list, field: str) -> str:
    leaves = [tapnft.leaf_hash(i, [bytes.fromhex(e[field][2:])]) for i, e in enumerate(entries)]
    return tapnft.hex32(tapnft.merkle_root(leaves))


def build_manifest(pools: dict, chain_hash: str, rnd: int, token_ids: list = None, token_set_uris: list = None,
                   rules_uris: dict = None) -> dict:
    supply = pools["supply"]
    rarity = pools.get("mode") == "rarity"
    img = [{"image": e["image"], "tier": e["tier"]} for e in pools["images"]]
    # rarity mode: sources are committed through the design table hash in `rules`; legacy: per entry
    net = [{"netlist": e["netlist"], "tier": e["tier"], **({} if rarity else {"source": e["source"]})}
           for e in pools["netlists"]]
    for entries in (img, net):
        if len(entries) != supply:
            raise SystemExit(f"pool has {len(entries)} entries, supply is {supply}")
        for e in entries:
            v = e.get("image") or e.get("netlist")
            if not isinstance(v, str) or not tapnft.HEX32.match(v) or v == ZERO32:
                raise SystemExit(f"bad entry value {v!r}")
    if token_ids is not None:
        if len(token_ids) != supply:
            raise SystemExit(f"token set has {len(token_ids)} ids, pools have {supply} entries")
        if not token_set_uris:
            raise SystemExit("set mode needs at least one --token-set-uri")
        col = {"chainId": CHAIN_ID, "address": CONTRACT,
               "tokenSet": {"sha256": tapnft.hex32(tapnft.token_set_hash(token_ids)), "count": len(token_ids),
                            "uris": token_set_uris}}
    else:
        col = {"chainId": CHAIN_ID, "address": CONTRACT, "firstTokenId": FIRST_TOKEN_ID, "supply": supply}
    m = {
        "tapManifest": 1,
        "collection": col,
        "reveal": {"source": "drand", "chainHash": chain_hash, "round": rnd},
        "pools": [
            {"label": IMAGE_LABEL, "fields": ["image"], "root": pool_root(img, "image"), "entries": img},
            {"label": NETLIST_LABEL, "fields": ["netlist"], "root": pool_root(net, "netlist"), "entries": net},
        ],
        "freeze": FREEZE,
    }
    if rarity:
        r = pools["rarity"]
        ru = rules_uris or {}
        with open(RARITY_DOC, "rb") as f:
            doc_sha = "0x" + hashlib.sha256(f.read()).hexdigest()
        m["rules"] = {
            "rarity": {"rule": r["rule"], "params": r["params"],
                       "doc": {"sha256": doc_sha, "uris": ru.get("doc", ["tools/collection/RARITY.md"])}},
            "snapshot": {"chainId": r["chainId"], "block": r["block"], "mining": r["mining"].lower()},
            "designTable": {"sha256": r["tableSha256"], "uris": ru.get("table", ["tools/collection/rarity-7000.json"])},
            "eligibility": {"maxFileBytes": MAX_NETLIST_BYTES},
            "pool": "tiers Mythic..Common, then SHA-256 ascending, copies consecutive",
        }
    return m


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pools", required=True)
    ap.add_argument("--out", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--round", type=int)
    g.add_argument("--at", help="target UTC time; the first round produced at or after it is used")
    ap.add_argument("--chain", default=QUICKNET)
    ap.add_argument("--token-set", help=f"valid token ids (default: {TOKENS_FILE} if it exists)")
    ap.add_argument("--token-set-uri", action="append", help="where tokenset.bin is published (repeatable)")
    ap.add_argument("--range-mode", action="store_true", help="ignore token sets; firstTokenId/supply")
    ap.add_argument("--rules-doc-uri", action="append", help="URIs of RARITY.md")
    ap.add_argument("--design-table-uri", action="append", help="URIs of rarity-7000.json")
    ap.add_argument("--min-lead-hours", type=float, default=72.0)
    ap.add_argument("--allow-past-round", action="store_true",
                    help="TESTS ONLY: accept a round that is already produced (the seed is then known)")
    a = ap.parse_args(argv)

    info = drand.fetch_info(a.chain)
    rnd = a.round if a.round is not None else drand.round_at(info, drand.parse_utc(a.at))
    t = drand.round_time(info, rnd)
    lead = (t - time.time()) / 3600
    if lead < a.min_lead_hours:
        msg = f"round {rnd} is produced at {drand.utc(t)}, {lead:.1f} h from now (< {a.min_lead_hours} h)"
        if not a.allow_past_round:
            print("error:", msg, file=sys.stderr)
            return 1
        print("WARNING (test mode):", msg, "- this manifest must never be used for a real reveal")

    pools = read_json(a.pools)
    ts_path = a.token_set or (TOKENS_FILE if os.path.exists(TOKENS_FILE) else None)
    ids = None if a.range_mode or not ts_path else load_token_ids(ts_path)
    rules_uris = {k: v for k, v in (("doc", a.rules_doc_uri), ("table", a.design_table_uri)) if v}
    data = compact(build_manifest(pools, a.chain, rnd, ids, a.token_set_uri, rules_uris))
    if len(data) >= MAX_CONTAINER_FILE:
        print(f"error: manifest is {len(data)} bytes, container limit is {MAX_CONTAINER_FILE}", file=sys.stderr)
        return 1
    m = tapnft.check_manifest(data)
    write_bytes(a.out, data)
    if ids is not None:
        ts_file = os.path.join(os.path.dirname(os.path.abspath(a.out)), "tokenset.bin")
        write_bytes(ts_file, tapnft.token_set_file(ids))
        with open(ts_file, "rb") as f:
            tapnft.check_token_set(m, f.read())
        print(f"token set: {len(ids)} ids from {ts_path}, sha256 {m['collection']['tokenSet']['sha256']} -> {ts_file}")
    print(f"manifestHash 0x{hashlib.sha256(data).hexdigest()}")
    print(f"size {len(data)} bytes ({len(data) / 1e6:.3f} MB; container limit {MAX_CONTAINER_FILE})")
    print(f"reveal: drand {a.chain} round {rnd}, produced at {drand.utc(t)}")
    for p in m["pools"]:
        print(f"pool {p['label']}: {len(p['entries'])} entries, root {p['root']}")
    print("tapnft.check_manifest: ok")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
