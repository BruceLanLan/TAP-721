#!/usr/bin/env python3
"""For one id per contiguous run of excluded ids, binary-search the first block at which
ownerOf(id) == black hole, then pull Transfer logs (to = black hole) in that block.
Writes transfers_sample.json. Archive eth_call on xlayerrpc.okx.com; getLogs window <= 100 blocks.
"""
import json, os, sys, time
from scan_owners import COLLECTION, rpc_batch, owner_calls, decode, HERE
from scan_transfers import TRANSFER, DEPLOY_BLOCK

URL = "https://xlayerrpc.okx.com"
DEAD = "0x000000000000000000000000000000000000dead"


def owner_at(i, b):
    return decode(rpc_batch(URL, owner_calls([i], hex(b)))[0])


def main():
    t = json.load(open(os.path.join(HERE, "tokens.json")))
    ex, B = t["excludedTokenIds"], t["block"]
    runs, s, p = [], ex[0], ex[0]
    for x in ex[1:]:
        if x != p + 1:
            runs.append((s, p)); s = x
        p = x
    runs.append((s, p))
    out = []
    for (lo_id, hi_id) in runs:
        i = (lo_id + hi_id) // 2
        lo, hi = DEPLOY_BLOCK, B  # invariant: owner(hi)==DEAD, owner(lo)!=DEAD
        while hi - lo > 1:
            m = (lo + hi) // 2
            if owner_at(i, m) == DEAD:
                hi = m
            else:
                lo = m
            time.sleep(0.05)
        logs = rpc_batch(URL, [("eth_getLogs", [{"address": COLLECTION, "fromBlock": hex(hi), "toBlock": hex(hi),
                                                 "topics": [TRANSFER, None, "0x" + "0" * 24 + DEAD[2:]]}])])[0]["result"]
        blk = rpc_batch(URL, [("eth_getBlockByNumber", [hex(hi), False])])[0]["result"]
        ids = sorted(int(l["topics"][3], 16) for l in logs)
        rec = {"run": [lo_id, hi_id], "probeId": i, "arrivalBlock": hi,
               "arrivalTimeUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(blk["timestamp"], 16))),
               "txs": sorted({l["transactionHash"] for l in logs}),
               "senders": sorted({"0x" + l["topics"][1][-40:] for l in logs}),
               "idsToDeadInBlock": len(ids), "probeIdInLogs": i in ids,
               "idRangeInBlock": [ids[0], ids[-1]] if ids else None}
        print(json.dumps(rec), file=sys.stderr)
        out.append(rec)
    json.dump(out, open(os.path.join(HERE, "transfers_sample.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
