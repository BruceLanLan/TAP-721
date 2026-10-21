#!/usr/bin/env python3
"""A minimal occurrence indexer (informative) for the draft "Design Credits and Lineage
for TapeOut Netlists": reads every circuit of the given processors, computes the netlist
hash and the structural hash of every REF-free circuit, and lists the circuits whose
hashes equal a target. Writes occurrences.json.

MIT licence. Standard library only, plus canon.py / tapnft.py / tap02_reference.py
(copied unchanged from the TAP-721 family). Read-only eth_call; no transaction is sent.

    python3 scan_occurrences.py 30 635

Every read is made at ONE block: the pinned block recorded by fetch_reads.py in
chain-reads.json (`pinnedBlock`, the BSC `finalized` block at the time of that run), so the
scan is a snapshot of the processors at that block, and that block is the `toBlock` of the
earliest-occurrence statements of the worked example. Public BSC nodes keep state for only
about a hundred blocks, so the bulk reads go to the archive node alone (one operator);
fetch_reads.py checked nextId() and circuitInfo(nextId + 1) of both processors on two
further operators at the same block, and the scan repeats those two reads on the archive.

Circuit ids run from 1 to nextId() inclusive: on the deployed processors nextId() was
observed to return the id of the latest circuit, not the next one (circuitInfo(nextId())
succeeds and circuitInfo(nextId() + 1) reverts at the pinned block; see chain-reads.json).
Within one processor, ids are assigned in mint order, so the lowest matching id is that
processor's earliest matching circuit; comparing processors needs the mint blocks
(fetch_reads.py records them for the circuits of the worked example).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import canon
import tapnft

HERE = os.path.dirname(os.path.abspath(__file__))
NODES = os.environ.get("BSC_RPC", "https://tapeout.net/rpc").split(",")
NODE = NODES[0]
with open(os.path.join(HERE, "chain-reads.json")) as _f:
    BLOCK = json.load(_f)["pinnedBlock"]["number"]
FACTORY = "0x68224f668083c29e9800be2a646d42d18cedf7e2"
TARGET_NETLIST = "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e"
TARGET_STRUCTURAL = "0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b"


def _post(body, node=None):
    req = urllib.request.Request(node or NODE, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def batch(calls: list[tuple[str, str]]) -> list:
    """Batched eth_call; entries missing or rate-limited in the batch answer are retried."""
    results: dict = {}
    pending = list(range(len(calls)))
    last = ""
    for attempt in range(8):
        if not pending:
            break
        body = [{"jsonrpc": "2.0", "id": i, "method": "eth_call",
                 "params": [{"to": calls[i][0], "data": calls[i][1]}, hex(BLOCK)]} for i in pending]
        try:
            res = _post(body, NODES[attempt % len(NODES)])
        except Exception as e:  # noqa: BLE001 - network hiccup, retry
            last = repr(e)
            time.sleep(1 + attempt)
            continue
        if isinstance(res, dict):
            res = [res]
        for x in res:
            if not isinstance(x, dict) or "id" not in x:
                continue
            if "result" in x:
                results[x["id"]] = x["result"]
            elif "execution reverted" in json.dumps(x.get("error", "")):
                results[x["id"]] = None
            else:
                last = json.dumps(x.get("error"))[:200]
        pending = [i for i in pending if i not in results]
        if pending:
            time.sleep(1 + attempt)
    if pending:
        raise RuntimeError(f"{len(pending)} calls unanswered: {last}")
    return [results[i] for i in range(len(calls))]


def w(n: int) -> str:
    return hex(n)[2:].rjust(64, "0")


def abi_bytes(ret: str) -> bytes:
    raw = bytes.fromhex(ret[2:])
    off = int.from_bytes(raw[0:32], "big")
    ln = int.from_bytes(raw[off:off + 32], "big")
    return raw[off + 32:off + 32 + ln]


def _chunks(lo: int, hi: int, step: int):
    return [list(range(s, min(hi, s + step - 1) + 1)) for s in range(lo, hi + 1, step)]


def scan(number: int) -> dict:
    """A structural hash covers nIn and nOut, so only circuits with the target's
    nIn = 2 and nOut = 1 can match; their netlists are read, the rest only counted."""
    proc = "0x" + batch([(FACTORY, "0x4bc7cbbd" + w(number))])[0][-40:]
    last = int(batch([(proc, "0x61b8ce8c")])[0], 16)
    after = batch([(proc, "0x084d60f1" + w(last + 1))])[0]
    out = {"processorNumber": number, "processor": proc, "block": BLOCK, "nextIdAtBlock": last,
           "lastId": last, "circuitInfoAfterLastReverted": after is None, "circuitsRead": 0, "unreadable": 0,
           "candidates": 0, "candidatesRefFree": 0, "candidatesWithRef": 0,
           "exactMatches": [], "structuralMatches": []}
    infos = {}
    with ThreadPoolExecutor(6) as ex:
        for ids, res in zip(_chunks(1, last, 100), ex.map(lambda ids: batch([(proc, "0x084d60f1" + w(i)) for i in ids]),
                                                         _chunks(1, last, 100))):
            for i, r in zip(ids, res):
                infos[i] = r
    cand = []
    for i in range(1, last + 1):
        r = infos.get(i)
        if not r:
            out["unreadable"] += 1
            continue
        out["circuitsRead"] += 1
        if int(r[2:66], 16) == 2 and int(r[66:130], 16) == 1:
            cand.append(i)
    out["candidates"] = len(cand)
    print(f"  processor {number}: {last} circuits, {len(cand)} with nIn 2 / nOut 1", file=sys.stderr)
    groups = [cand[k:k + 25] for k in range(0, len(cand), 25)]
    with ThreadPoolExecutor(6) as ex:
        for ids, res in zip(groups, ex.map(lambda ids: batch([(proc, "0x3fc4be56" + w(i)) for i in ids]), groups)):
            for i, nl in zip(ids, res):
                try:
                    f = tapnft.file_from_chain(abi_bytes(nl), 2, 1)
                except tapnft.Invalid:
                    out["candidatesWithRef"] += 1  # REF records: no structural hash
                    continue
                out["candidatesRefFree"] += 1
                nh = tapnft.hex32(tapnft.netlist_hash(f))
                if nh == TARGET_NETLIST:
                    out["exactMatches"].append(i)
                if nh == TARGET_NETLIST or tapnft.hex32(canon.structural_hash(f)) == TARGET_STRUCTURAL:
                    out["structuralMatches"].append(i)
    out["exactMatches"].sort()
    out["structuralMatches"].sort()
    return out


def main() -> None:
    nums = [int(a) for a in sys.argv[1:]] or [30, 635]
    result = {"format": "tap-design-credits-occurrences/2", "chainId": 56, "nodes": NODES, "block": BLOCK,
              "targetNetlistHash": TARGET_NETLIST, "targetStructuralHash": TARGET_STRUCTURAL,
              "processors": [scan(n) for n in nums]}
    path = os.path.join(HERE, "occurrences.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=1)
        f.write("\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
