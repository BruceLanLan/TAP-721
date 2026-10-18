#!/usr/bin/env python3
"""Read ownerOf(id) for every token of the collection at one pinned block.

Usage:
  python3 scan_owners.py                  # pin to latest finalized-ish block (latest - 64)
  python3 scan_owners.py --block 12345    # re-check at a given block
Writes owners.json: {block, blockHash, timestamp, owners: {id: address|null}}.
Stdlib only.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error

COLLECTION = "0x0e91460d6823c711643e650a9a4c0cc21de41614"
RPCS = ["https://rpc.xlayer.tech", "https://xlayerrpc.okx.com", "https://xlayer.drpc.org"]
OWNER_OF = "0x6352211e"
HERE = os.path.dirname(os.path.abspath(__file__))


def rpc_batch(url, calls, tries=8):
    body = [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]
    data = json.dumps(body).encode()
    delay = 1.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data, {"content-type": "application/json", "user-agent": "tap-tokenset"})
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r)
            if isinstance(res, dict):
                raise RuntimeError(res)
            res.sort(key=lambda x: x["id"])
            if len(res) != len(calls):
                raise RuntimeError("short batch")
            # Treat transport-level errors (rate limits) as retryable; keep execution reverts.
            for x in res:
                e = x.get("error")
                if e and "revert" not in str(e.get("message", "")).lower() and e.get("code") not in (3,):
                    raise RuntimeError(e)
            return res
        except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, TimeoutError, ConnectionError) as ex:
            if attempt == tries - 1:
                raise
            print(f"  retry {attempt+1} on {url}: {str(ex)[:120]}", file=sys.stderr)
            time.sleep(delay)
            delay = min(delay * 2, 30)


def call1(url, method, params):
    return rpc_batch(url, [(method, params)])[0]["result"]


def owner_calls(ids, block_hex):
    return [("eth_call", [{"to": COLLECTION, "data": OWNER_OF + i.to_bytes(32, "big").hex()}, block_hex]) for i in ids]


def decode(x):
    if "error" in x:
        return None  # nonexistent / burned token (ownerOf reverts)
    r = x["result"]
    if not r or r == "0x" or len(r) < 66:
        return None
    return "0x" + r[-40:]


def read_owners(url, ids, block_hex, size=10, pause=0.15):
    out = {}
    for k in range(0, len(ids), size):
        chunk = ids[k:k + size]
        res = rpc_batch(url, owner_calls(chunk, block_hex))
        for i, x in zip(chunk, res):
            out[i] = decode(x)
        if k % 1000 == 0:
            print(f"  {url}: {k}/{len(ids)}", file=sys.stderr)
        time.sleep(pause)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", type=int)
    ap.add_argument("--rpc", default=RPCS[0])
    ap.add_argument("--max-id", type=int, default=10000)
    ap.add_argument("--out", default=os.path.join(HERE, "owners.json"))
    a = ap.parse_args()

    if a.block is None:
        latest = int(call1(a.rpc, "eth_blockNumber", []), 16)
        a.block = latest - 64
    bh = hex(a.block)
    blk = call1(a.rpc, "eth_getBlockByNumber", [bh, False])
    ts = int(blk["timestamp"], 16)
    ts_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    print(f"block {a.block} {blk['hash']} {ts_utc}", file=sys.stderr)

    supply = call1(a.rpc, "eth_call", [{"to": COLLECTION, "data": "0x18160ddd"}, bh])
    ids = list(range(1, a.max_id + 1))
    owners = read_owners(a.rpc, ids, bh)
    json.dump({"collection": COLLECTION, "chainId": 196, "rpc": a.rpc, "block": a.block, "blockHash": blk["hash"],
               "timestamp": ts, "timestampUtc": ts_utc, "totalSupply": int(supply, 16),
               "owners": {str(i): owners[i] for i in ids}}, open(a.out, "w"), indent=0)
    print(f"wrote {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
