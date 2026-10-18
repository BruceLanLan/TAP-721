#!/usr/bin/env python3
"""Fetch every Transfer(address,address,uint256) log of the collection from its deploy
block up to --to-block (default: the block pinned in owners.json).
Writes transfers.json: [{block, tx, logIndex, from, to, tokenId}].
Uses drpc (allows 10k-block getLogs ranges); rpc.xlayer.tech / okx cap ranges at 100 blocks.
"""
import argparse, json, os, sys
from scan_owners import COLLECTION, rpc_batch, HERE

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
DEPLOY_BLOCK = 72863247


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default="https://xlayer.drpc.org")
    ap.add_argument("--to-block", type=int)
    ap.add_argument("--step", type=int, default=9999)
    ap.add_argument("--out", default=os.path.join(HERE, "transfers.json"))
    a = ap.parse_args()
    if a.to_block is None:
        a.to_block = json.load(open(os.path.join(HERE, "owners.json")))["block"]
    out = []
    b = DEPLOY_BLOCK
    step = a.step
    while b <= a.to_block:
        e = min(b + step - 1, a.to_block)
        try:
            res = rpc_batch(a.rpc, [("eth_getLogs", [{"address": COLLECTION, "topics": [TRANSFER],
                                                      "fromBlock": hex(b), "toBlock": hex(e)}])], tries=3)[0]
            if "error" in res:
                raise RuntimeError(res["error"])
        except Exception as ex:  # provider rejects big ranges / big responses: shrink and retry
            if step == 1:
                raise
            step = max(1, step // 4)
            print(f"  shrink to {step}: {str(ex)[:80]}", file=sys.stderr)
            continue
        for lg in res["result"]:
            t = lg["topics"]
            if len(t) != 4:
                continue
            out.append({"block": int(lg["blockNumber"], 16), "tx": lg["transactionHash"],
                        "logIndex": int(lg["logIndex"], 16), "from": "0x" + t[1][-40:],
                        "to": "0x" + t[2][-40:], "tokenId": int(t[3], 16)})
        print(f"  {b}-{e}: total {len(out)}", file=sys.stderr)
        b = e + 1
        step = min(a.step, step * 2)
    out.sort(key=lambda x: (x["block"], x["logIndex"]))
    json.dump(out, open(a.out, "w"))
    print(f"wrote {len(out)} transfers to {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
