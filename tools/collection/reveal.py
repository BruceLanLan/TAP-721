#!/usr/bin/env python3
"""Reveal TapeCode-Test1: assignments, editions, proofs and the per-token metadata files (stdlib only, MIT).

  # blind-box phase, right after the manifest is published (no seed needed):
  reveal.py --manifest work/manifest.json --pools work/pools.json --template template.json --out work --unrevealed-only
  # after the drand round named in the manifest is produced:
  reveal.py --manifest work/manifest.json --pools work/pools.json --template template.json --out work \
            [--beacon work/beacon.json] [--token-set-file work/tokenset.bin] [--pod-snapshot pods.json] [--no-proofs]

Steps (draft A §5-§7, every primitive from tapnft.py):
  1. manifestHash = SHA-256(manifest bytes as published); tapnft.check_manifest (structure, roots); in set
     mode the token-set file (default: tokenset.bin next to the manifest) passes tapnft.check_token_set;
     pools.json (operator file: image extensions, netlist metrics, sources) must match the manifest.
  2. masterSeed = randomness of the manifest's drand round (drand.py: fetched and verified, or a saved
     beacon re-checked offline).
  3. For every token id of the contract (--ids, default 1-10000): tapnft.assignment(manifest, seed, t, ids)
     gives the entry of each pool, or None for an id outside the token set (excluded, e.g. held by 0x…dEaD).
     Editions = rank among tokens with the same netlist hash (§6.4). Proofs = tapnft.merkle_proof_from_levels
     over tapnft.merkle_levels, each re-checked with tapnft.merkle_verify.
  4. meta/<id>: revealed documents for covered ids, placeholders for excluded ids (state "unrevealed",
     tap.manifest, no tap.image / tap.netlist); meta-unrevealed/<id>: blind box for covered ids, the same
     placeholder for excluded ids. Compact JSON, no extension. Every document passes tapnft.check_metadata
     and the tap.content check below; the set passes tapnft.check_editions; tap.pod (optional) passes
     pod_validate.validate_tap.
  5. reveal.json: seed, pool seeds and, per covered token, entry index, values and proof (bind() arguments),
     edition and SHA-256 of its metadata file; the excluded ids.

Template (JSON): name, description, image, image_uris, netlist_uris, manifest_uris, optional external_url,
license, companion, content {chainId, container, name, paths {image, netlist, manifest, metadata}, lock?},
unrevealed {name, description, image}, excluded {name, description, image}. Placeholders: {id},
{sha256} (64 hex digits, no 0x), {ext} (image extension from pools.json).

tap.content (collection member, not defined by draft A; tools ignore unknown members) says which TapeOut
container serves this token's files: chainId, container (lowercase address), name (TAP-10 on-chain name),
paths (container-relative paths of this token's image, netlist, manifest and metadata), lock (optional,
the TapContainerLock holding the content circuit).
"""
from __future__ import annotations

import argparse
import hashlib

import os

import sys
import time

import drand
from _paths import (CHAIN_ID, CONTRACT, ID_RANGE, IMAGE_LABEL, NETLIST_LABEL, compact, pod_validate, read_json,
                    tapnft, write_bytes)


class RevealError(Exception):
    pass


def fill(pattern: str, **kw) -> str:
    out = pattern
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    if any("{" + k + "}" in out for k in ("id", "sha256", "ext")):
        raise RevealError(f"unfilled placeholder in {pattern!r}")
    return out


def token_ref(t: int) -> str:
    return f"eip155:{CHAIN_ID}/erc721:{CONTRACT}/{t}"


def parse_ids(spec: str) -> list:
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return sorted(set(out))


def check_content(c) -> None:
    """Shape of tap.content (collection-defined member)."""
    def req(cond, msg):
        if not cond:
            raise tapnft.Invalid(msg)
    req(isinstance(c, dict), "tap.content must be an object")
    req(isinstance(c.get("chainId"), int) and c["chainId"] > 0, "tap.content.chainId")
    req(isinstance(c.get("container"), str) and tapnft.ADDR.match(c["container"]) is not None,
        "tap.content.container must be a lowercase address")
    req(isinstance(c.get("name"), str) and tapnft.TAPE_NAME.match(c["name"]) is not None,
        "tap.content.name must be a TAP-10 on-chain name")
    p = c.get("paths")
    req(isinstance(p, dict) and p and all(isinstance(v, str) and v and not v.startswith("/") and ".." not in v
                                          for v in p.values()), "tap.content.paths must map names to relative paths")
    if "lock" in c:
        req(isinstance(c["lock"], str) and tapnft.ADDR.match(c["lock"]) is not None, "tap.content.lock")


# ---------------------------------------------------------------- manifest

def load_manifest(path: str, token_set_file: str = None) -> tuple:
    with open(path, "rb") as f:
        raw = f.read()
    m = tapnft.check_manifest(raw)
    mh = "0x" + hashlib.sha256(raw).hexdigest()
    c = m["collection"]
    if (c["chainId"], c["address"]) != (CHAIN_ID, CONTRACT):
        raise RevealError("manifest is not the TapeCode-Test1 manifest (collection mismatch)")
    if [p["label"] for p in m["pools"]] != [IMAGE_LABEL, NETLIST_LABEL]:
        raise RevealError(f"expected pools {IMAGE_LABEL}, {NETLIST_LABEL}")
    if m["reveal"]["source"] != "drand":
        raise RevealError("reveal.source must be drand")
    if "tokenSet" in c:
        tsf = token_set_file or os.path.join(os.path.dirname(os.path.abspath(path)), "tokenset.bin")
        with open(tsf, "rb") as f:
            ids = tapnft.check_token_set(m, f.read())
    else:
        ids = list(range(c["firstTokenId"], c["firstTokenId"] + c["supply"]))
    return m, mh, ids


def check_pools_json(m: dict, pools: dict) -> None:
    img, net = m["pools"][0]["entries"], m["pools"][1]["entries"]
    if [(e["image"], e["tier"]) for e in img] != [(e["image"], e["tier"]) for e in pools["images"]]:
        raise RevealError("pools.json images differ from the manifest IMAGE_V1 entries")
    if [(e["netlist"], e["tier"]) for e in net] != [(e["netlist"], e["tier"]) for e in pools["netlists"]]:
        raise RevealError("pools.json netlists differ from the manifest NETLIST_V1 entries")


# ---------------------------------------------------------------- documents

def content(tpl: dict, t: int, **paths) -> dict:
    c = dict(tpl["content"])
    pats = c.pop("paths")
    c["paths"] = {k: fill(pats[k], id=t, **v) for k, v in paths.items() if k in pats}
    check_content(c)
    return c


def placeholder_doc(t: int, tpl: dict, mh: str, kind: str) -> dict:
    """Blind box (kind 'unrevealed') or excluded id (kind 'excluded'): state unrevealed, no image/netlist."""
    u = tpl[kind]
    tap = {"v": 1, "id": token_ref(t), "state": "unrevealed",
           "manifest": {"sha256": mh, "uris": [fill(x, id=t) for x in tpl["manifest_uris"]]}}
    if tpl.get("content"):
        tap["content"] = content(tpl, t, manifest={}, metadata={})
    if tpl.get("companion"):
        tap["companion"] = tpl["companion"]
    doc = {"name": fill(u["name"], id=t), "description": fill(u.get("description", ""), id=t),
           "image": fill(u["image"], id=t), "tap": tap}
    if kind == "excluded":
        doc["attributes"] = [{"trait_type": "Status", "value": "Excluded"}]
    return doc


def revealed_doc(t: int, tpl: dict, mh: str, img: dict, net: dict, design: dict, edition, pod) -> dict:
    ih, nh = img["image"][2:], net["netlist"][2:]
    image_url = fill(tpl["image"], id=t, sha256=ih, ext=img["ext"])
    image_uris = [fill(x, id=t, sha256=ih, ext=img["ext"]) for x in tpl["image_uris"]]
    if image_url not in image_uris:
        image_uris.append(image_url)
    attrs = [{"trait_type": "Avatar Rarity", "value": img["tier"]},
             {"trait_type": "Netlist Rarity", "value": net["tier"]},
             {"trait_type": "NAND", "display_type": "number", "value": design["nand"]},
             {"trait_type": "LATCH", "display_type": "number", "value": design["latch"]},
             {"trait_type": "Inputs", "display_type": "number", "value": design["nIn"]},
             {"trait_type": "Outputs", "display_type": "number", "value": design["nOut"]}]
    if "S" in design:
        attrs.append({"trait_type": "Size", "display_type": "number", "value": design["S"]})
    src = {k: net["source"][k] for k in ("chainId", "processor", "circuitId", "block", "name", "container")
           if k in net["source"]}   # minimal source: no registrant, no mining state
    tap = {"v": 1, "id": token_ref(t), "state": "revealed",
           "manifest": {"sha256": mh, "uris": [fill(x, id=t) for x in tpl["manifest_uris"]]},
           "image": {"sha256": img["image"], "uris": image_uris},
           "netlist": {"format": tapnft.FORMAT_ID, "sha256": net["netlist"], "bytes": design["bytes"],
                       "nIn": design["nIn"], "nOut": design["nOut"], "nand": design["nand"], "latch": design["latch"],
                       "uris": [fill(x, id=t, sha256=nh) for x in tpl["netlist_uris"]]},
           "source": src}
    if tpl.get("content"):
        tap["content"] = content(tpl, t, image={"sha256": ih, "ext": img["ext"]}, netlist={"sha256": nh},
                                 manifest={}, metadata={})
    if edition is not None:
        tap["edition"] = {"index": edition[0], "of": edition[1]}
    if tpl.get("license"):
        tap["license"] = tpl["license"]
    if tpl.get("companion"):
        tap["companion"] = tpl["companion"]
    if pod is not None:
        tap["pod"] = pod
    doc = {"name": fill(tpl["name"], id=t), "description": fill(tpl.get("description", ""), id=t),
           "image": image_url, "attributes": attrs, "tap": tap}
    if tpl.get("external_url"):
        doc["external_url"] = fill(tpl["external_url"], id=t)
    return doc


def check_doc(d: dict) -> None:
    tap = tapnft.check_metadata(d)
    if "content" in tap:
        check_content(tap["content"])


def load_pods(path: str) -> dict:
    pv = pod_validate()
    d = read_json(path)
    if isinstance(d, dict) and "cases" in d:
        items = [c["pod"] for c in d["cases"] if c.get("pod")]
    elif isinstance(d, dict) and "pods" in d:
        items = d["pods"]
    elif isinstance(d, list):
        items = d
    else:
        raise RevealError(f"{path}: expected a list of tap.pod objects, {{'pods': [...]}} or {{'cases': [...]}}")
    out = {}
    for p in items:
        r = pv.validate_pod(p)
        if not r.ok:
            raise RevealError(f"{path}: pod {p.get('processor')}#{p.get('circuitId')}: {r.errors}")
        out[(p["processor"], p["circuitId"])] = p
    return out


# ---------------------------------------------------------------- main

def run(a) -> int:
    t0 = time.time()
    m, mh, ids = load_manifest(a.manifest, a.token_set_file)
    pools = read_json(a.pools)
    tpl = read_json(a.template)
    check_pools_json(m, pools)
    all_ids = parse_ids(a.ids)
    covered = set(ids)
    if not covered <= set(all_ids):
        raise RevealError("token set holds ids outside --ids")
    n = len(ids)
    mode = "set" if "tokenSet" in m["collection"] else "range"
    print(f"manifest {mh} ok ({os.path.getsize(a.manifest)} bytes, tapnft.check_manifest), {mode} mode, "
          f"{n} covered ids, {len(all_ids) - n} excluded")

    for t in all_ids:
        d = placeholder_doc(t, tpl, mh, "unrevealed" if t in covered else "excluded")
        check_doc(d)
        write_bytes(os.path.join(a.out, "meta-unrevealed", str(t)), compact(d))
    print(f"meta-unrevealed/: {len(all_ids)} documents, all pass check_metadata")
    if a.unrevealed_only:
        return 0

    rv = m["reveal"]
    beacon = drand.get_beacon(rv["chainHash"], rv["round"], a.beacon)
    master = bytes.fromhex(beacon["randomness"])
    print(f"drand round {rv['round']}: randomness {beacon['randomness']} "
          f"({'saved beacon re-checked' if a.beacon else 'fetched from ' + ', '.join(beacon['verified']['relaysAgreeing'])})")
    labels = [p["label"] for p in m["pools"]]
    assign = {}
    for t in all_ids:
        r = tapnft.assignment(m, master, t, ids if mode == "set" else None)
        if (r is not None) != (t in covered):
            raise RevealError(f"token {t}: assignment/coverage mismatch")
        if r is not None:
            assign[t] = [r[lab] for lab in labels]
    for k in range(2):
        if sorted(v[k] for v in assign.values()) != list(range(n)):
            raise RevealError("permutation is not a bijection")  # cannot happen; cheap guard

    by_hash = {}
    for t in sorted(assign):
        by_hash.setdefault(pools["netlists"][assign[t][1]]["netlist"], []).append(t)
    edition = {}
    for h, ts in by_hash.items():
        for rank, t in enumerate(ts, 1):
            edition[t] = (rank, len(ts)) if len(ts) > 1 else None

    pods = load_pods(a.pod_snapshot) if a.pod_snapshot else {}
    pv = pod_validate() if pods else None
    docs, pod_warn, with_pod = {}, set(), 0
    for t in all_ids:
        if t not in assign:
            d = placeholder_doc(t, tpl, mh, "excluded")
        else:
            img = pools["images"][assign[t][0]]
            net = pools["netlists"][assign[t][1]]
            design = pools["designs"][net["netlist"]]
            src = net["source"]
            pod = pods.get((src["processor"], src["circuitId"])) if src["chainId"] == 56 else None
            d = revealed_doc(t, tpl, mh, img, net, design, edition[t], pod)
            if pod is not None:
                r = pv.validate_tap(d["tap"])
                if not r.ok:
                    raise RevealError(f"token {t}: tap.pod invalid: {r.errors}")
                pod_warn.update(r.warnings)
                with_pod += 1
        check_doc(d)
        docs[t] = d
    tapnft.check_editions(list(docs.values()))
    print(f"meta/: {len(all_ids)} documents ({n} revealed, {len(all_ids) - n} excluded placeholders) pass "
          f"check_metadata; check_editions passes ({sum(1 for e in edition.values() if e)} tokens in editions, "
          f"{len(by_hash)} distinct netlists)")
    if pods:
        print(f"tap.pod on {with_pod} tokens, validated with pod_validate.validate_tap"
              + (f"; warnings: {sorted(pod_warn)}" if pod_warn else ""))

    proofs = [{}, {}]
    if not a.no_proofs:
        t1 = time.time()
        for k, p in enumerate(m["pools"]):
            field = p["fields"][0]
            leaves = [tapnft.leaf_hash(i, [bytes.fromhex(e[field][2:])]) for i, e in enumerate(p["entries"])]
            levels = tapnft.merkle_levels(leaves)
            root = bytes.fromhex(p["root"][2:])
            for i in range(n):
                pr = tapnft.merkle_proof_from_levels(levels, i)
                if not tapnft.merkle_verify(root, n, i, leaves[i], pr):
                    raise RevealError(f"proof {p['label']}[{i}] does not verify")
                proofs[k][i] = pr
        print(f"proofs: {2 * n} computed (tapnft.merkle_levels / merkle_proof_from_levels) and verified "
              f"({time.time() - t1:.1f} s)")

    tokens = []
    for t in all_ids:
        data = compact(docs[t])
        write_bytes(os.path.join(a.out, "meta", str(t)), data)
        if t not in assign:
            continue
        entry = {"id": t, "index": tapnft.token_index(ids, t), "pools": [], "meta": "0x" + hashlib.sha256(data).hexdigest()}
        for k, p in enumerate(m["pools"]):
            i = assign[t][k]
            e = {"entry": i, "values": [p["entries"][i][p["fields"][0]]]}
            if not a.no_proofs:
                e["proof"] = [tapnft.hex32(x) for x in proofs[k][i]]
            entry["pools"].append(e)
        if edition[t]:
            entry["edition"] = list(edition[t])
        tokens.append(entry)
    rev = {"manifestSha256": mh, "collection": m["collection"], "reveal": rv,
           "beacon": {k: beacon[k] for k in ("round", "randomness", "signature")},
           "masterSeed": "0x" + beacon["randomness"],
           "pools": [{"label": p["label"], "root": p["root"],
                      "seed": tapnft.hex32(tapnft.pool_seed(master, CHAIN_ID, CONTRACT, p["label"]))} for p in m["pools"]],
           "excluded": [t for t in all_ids if t not in assign],
           "tokens": tokens}
    write_bytes(os.path.join(a.out, "reveal.json"), compact(rev))
    print(f"wrote {a.out}/reveal.json ({os.path.getsize(os.path.join(a.out, 'reveal.json'))} bytes) and "
          f"{len(all_ids)} files in {a.out}/meta/ in {time.time() - t0:.1f} s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--pools", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--token-set-file", help="token-set file (default: tokenset.bin next to the manifest)")
    ap.add_argument("--ids", default=f"{ID_RANGE.start}-{ID_RANGE.stop - 1}", help="all token ids of the contract")
    ap.add_argument("--beacon", help="saved beacon (drand.py fetch --out); default: fetch live")
    ap.add_argument("--pod-snapshot", help="tap.pod objects keyed by (processor, circuitId); needs pycryptodome")
    ap.add_argument("--unrevealed-only", action="store_true")
    ap.add_argument("--no-proofs", action="store_true")
    a = ap.parse_args(argv)
    try:
        return run(a)
    except (RevealError, tapnft.Invalid, drand.DrandError, OSError) as e:
        print("error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
