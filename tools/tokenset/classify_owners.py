#!/usr/bin/env python3
"""Classify every distinct owner in owners.json at the pinned block:
 - eth_getCode size (EOA vs contract), for every owner
 - burn-like address patterns
 - for contracts: probe ERC-6551 token(), owner(), and EIP-7702 delegation prefix
Also cross-checks a random sample of ownerOf on second (and third) operators.
Writes owner_classes.json and crosscheck.json.
"""
import json, os, random, sys, time
from scan_owners import COLLECTION, rpc_batch, owner_calls, decode, HERE

SECOND = ["https://xlayerrpc.okx.com", "https://xlayer.drpc.org"]


def burn_like(a):
    h = a[2:].lower()
    return (int(h, 16) < 2 ** 32 or h.endswith("dead") or h.startswith("dead") or len(set(h)) <= 2
            or h.strip("0") in ("", "1"))


def main():
    d = json.load(open(os.path.join(HERE, "owners.json")))
    bh = hex(d["block"])
    owners = sorted({v for v in d["owners"].values() if v})
    counts = {}
    for v in d["owners"].values():
        counts[v] = counts.get(v, 0) + 1
    url = SECOND[0]
    codes = {}
    for k in range(0, len(owners), 10):
        chunk = owners[k:k + 10]
        res = rpc_batch(url, [("eth_getCode", [a, bh]) for a in chunk])
        for a, x in zip(chunk, res):
            codes[a] = x["result"]
        time.sleep(0.1)
    contracts = [a for a in owners if codes[a] not in ("0x", None)]
    print(f"{len(owners)} owners, {len(contracts)} with code", file=sys.stderr)
    info = {}
    for a in owners:
        c = codes[a]
        e = {"count": counts[a], "codeSize": (len(c) - 2) // 2, "burnLike": burn_like(a)}
        if c.startswith("0xef0100"):
            e["eip7702Delegate"] = "0x" + c[8:48]
        info[a] = e
    # probe contracts
    for a in contracts:
        calls = [("eth_call", [{"to": a, "data": sig}, bh]) for sig in ("0xfc0c546a", "0x8da5cb5b")]  # token(), owner()
        res = rpc_batch(url, calls)
        info[a]["token()"] = res[0].get("result") if "error" not in res[0] else None
        info[a]["owner()"] = res[1].get("result") if "error" not in res[1] else None
    json.dump({"block": d["block"], "owners": info}, open(os.path.join(HERE, "owner_classes.json"), "w"), indent=1)

    # cross-check sample
    random.seed(d["blockHash"])
    sample = sorted(random.sample(range(1, 10001), 250))
    # make sure some black-hole tokens are in sample too
    report = {"block": d["block"], "sampleSize": len(sample), "results": {}}
    for u in SECOND:
        mism = []
        try:
            for k in range(0, len(sample), 10):
                chunk = sample[k:k + 10]
                res = rpc_batch(u, owner_calls(chunk, bh))
                for i, x in zip(chunk, res):
                    if decode(x) != d["owners"][str(i)]:
                        mism.append(i)
                time.sleep(0.2)
            blk = rpc_batch(u, [("eth_getBlockByNumber", [bh, False])])[0]["result"]
            report["results"][u] = {"mismatches": mism, "blockHashMatches": blk["hash"] == d["blockHash"]}
        except Exception as ex:
            report["results"][u] = {"error": str(ex)[:200]}
        print(u, report["results"][u], file=sys.stderr)
    report["sample"] = sample
    json.dump(report, open(os.path.join(HERE, "crosscheck.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
