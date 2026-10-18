"""Minimal JSON-RPC helpers (stdlib only)."""
import json, urllib.request

def batch(url, calls):
    body = [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)]
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", "user-agent": "tap-tools"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    if isinstance(res, dict):
        raise RuntimeError(res)
    res.sort(key=lambda x: x["id"])
    return [x.get("result") for x in res]

def batch_chunked(url, calls, size=int(__import__("os").environ.get("BATCH","20"))):
    out = []
    for i in range(0, len(calls), size):
        out += batch(url, calls[i:i + size])
    return out

def eth_call(to, data, block="latest"):
    return ("eth_call", [{"to": to, "data": data}, block])
