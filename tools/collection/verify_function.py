#!/usr/bin/env python3
"""Check that BEM miner circuits compute their task's function (stdlib + Foundry `cast`, MIT).

  verify_function.py --snapshot ../../assets/tap-draft-netlist-bound-nft/chain-snapshot.json
  verify_function.py --csv miners.csv [--block 128200681] [--rpc URL] [--random 16384] [--seq every-beat]
                     [--confirm] [--out result.json]

Why: PoD mining verifies a miner against `getTask(taskId).vectorCount` sampled vectors only, so
`verifWeight > 0` does not prove the circuit is correct. This tool compares each circuit with its task's
reference circuit (`getTask(taskId).refCircuits`, `refCircuitId`), both read at one pinned block.

Input rows: `processor, circuitId[, taskId]` (CSV with a header row), or the `circuits` list of
`assets/tap-draft-netlist-bound-nft/chain-snapshot.json` (taskId from `miner.taskId`). A missing taskId is read with
`getMiner(minerKey(processor, circuitId))` on the mining contract.

Method (TAP-02 semantics: signal 0 = 0, 1 = 1, 2.. = inputs, then element outputs; outputs = last nOut
signals; I/O bits packed LSB first as in tap02_reference.pack). Every signal is evaluated bit-parallel as
one Python integer, one bit per input pattern:
  combinational (no LATCH in either circuit): all 2^nIn inputs when nIn <= --exhaustive-max (16), else
    --random patterns drawn from --seed;
  sequential: the task's beat semantics (reset, warm-up, which beat is compared) are not published, so the
    default result is "unconfirmed". With --seq every-beat both circuits start from the all-zero state and
    must give equal outputs at every beat over max(cycles, 32) beats of random inputs; a difference is
    reported as "differs-every-beat", not as wrong.
  a reference that contains REF records is "unconfirmed".

Results: equivalent | NOT-EQUIVALENT (with the first counterexample, both outputs and the `cast call`
commands that reproduce it with the processors' own `eval(uint256,bytes)`) | match-every-beat |
differs-every-beat | unconfirmed | error. --confirm runs those two `cast call`s and checks the outputs.
Network access is read-only (eth_call). Nothing is ever sent.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import urllib.request

MINING = "0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46"
DEFAULT_RPC = "https://tapeout.net/rpc"
DEFAULT_BLOCK = 128200681
SEL_NETLIST = "0x3fc4be56"      # netlist(uint256)
SEL_INFO = "0x084d60f1"         # circuitInfo(uint256) -> (nIn, nOut, nState, gateCount)
SEL_GETMINER = "0x0527edc2"     # getMiner(bytes32); taskId is tuple member 2
TASK_SIG = ("getTask(uint32)((uint8,uint32,uint32,uint32,uint32,bool,bytes32,string,uint64,uint256,"
            "address,uint64))")
TASK_FIELDS = ["kind", "cycles", "nIn", "nOut", "vectorCount", "active", "vectorsRoot", "name",
               "refArea", "refCost", "refCircuits", "refCircuitId"]


class Chain:
    def __init__(self, rpc: str, block: int):
        self.rpc, self.block = rpc, block
        self._tasks: dict = {}
        self._circ: dict = {}

    def call(self, to: str, data: str) -> str:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                           "params": [{"to": to, "data": data}, hex(self.block)]}).encode()
        last = None
        for _ in range(6):
            try:
                req = urllib.request.Request(self.rpc, body, {"content-type": "application/json",
                                                              "user-agent": "tap-verify-function"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    res = json.load(r)
                if "error" in res:
                    raise RuntimeError(res["error"])
                return res["result"]
            except Exception as e:  # transient resets on the archive node
                last = e
        raise RuntimeError(f"eth_call {to} {data[:10]} failed: {last}")

    def cast(self, *args: str) -> str:
        out = subprocess.run(["cast", *args, "-r", self.rpc, "-b", str(self.block)],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"cast {' '.join(args[:3])}: {out.stderr.strip()}")
        return out.stdout.strip()

    def circuit(self, proc: str, cid: int) -> dict:
        key = (proc.lower(), cid)
        if key not in self._circ:
            w = "%064x" % cid
            a = self.call(proc, SEL_NETLIST + w)
            n = int(a[2 + 64:2 + 128], 16)
            net = bytes.fromhex(a[2 + 128:2 + 128 + 2 * n])
            b = self.call(proc, SEL_INFO + w)
            info = [int(b[2 + 64 * k:2 + 64 * (k + 1)], 16) for k in range(4)]
            self._circ[key] = {"net": net, "nIn": info[0], "nOut": info[1], "nState": info[2], "gates": info[3]}
        return self._circ[key]

    def task(self, tid: int) -> dict:
        if tid not in self._tasks:
            v = json.loads(self.cast("call", MINING, TASK_SIG, str(tid), "--json"))[0]
            self._tasks[tid] = dict(zip(TASK_FIELDS, v))
        return self._tasks[tid]

    def task_of(self, proc: str, cid: int) -> int:
        key = self.cast("call", MINING, "minerKey(address,uint256)(bytes32)", proc, str(cid))
        r = self.call(MINING, SEL_GETMINER + key[2:])
        return int(r[2 + 64 * 2:2 + 64 * 3], 16)


def parse(net: bytes):
    """Elements as (0, a, b) for NAND and (1, d) for LATCH; None if a REF (or unknown) record occurs."""
    i, els = 0, []
    while i < len(net):
        op = net[i]
        if op == 0 and i + 7 <= len(net):
            els.append((0, int.from_bytes(net[i + 1:i + 4], "big"), int.from_bytes(net[i + 4:i + 7], "big")))
            i += 7
        elif op == 1 and i + 4 <= len(net):
            els.append((1, int.from_bytes(net[i + 1:i + 4], "big")))
            i += 4
        else:
            return None
    return els


def run(els, inputs, state, n_out, mask):
    """One beat, bit-parallel. Returns (new_state, outputs)."""
    a = [0, mask] + list(inputs)
    si = 0
    for e in els:
        if e[0] == 0:
            a.append(~(a[e[1]] & a[e[2]]) & mask)
        else:
            a.append(state[si])
            si += 1
    new_state = [a[e[1]] for e in els if e[0] == 1]
    return new_state, a[len(a) - n_out:]


def exhaustive_inputs(n_in: int):
    width = 1 << n_in
    mask = (1 << width) - 1
    ins = []
    for i in range(n_in):
        rep, length = ((1 << (1 << i)) - 1) << (1 << i), 1 << (i + 1)   # bits j with (j >> i) & 1 == 1
        while length < width:
            rep |= rep << length
            length *= 2
        ins.append(rep & mask)
    return ins, mask


def pack(bits) -> str:
    out = bytearray(max(1, (len(bits) + 7) // 8))
    for i, v in enumerate(bits):
        if v:
            out[i >> 3] |= 1 << (i & 7)
    return "0x" + out.hex()


def lane(values, j):
    return [(v >> j) & 1 for v in values]


def check(chain: Chain, proc: str, cid: int, tid, args, rng) -> dict:
    res = {"processor": proc, "circuitId": cid, "block": chain.block}
    if tid is None:
        tid = chain.task_of(proc, cid)
    res["taskId"] = tid
    if tid == 0:
        return {**res, "result": "error", "detail": "no miner record (taskId 0)"}
    t = chain.task(tid)
    res.update(task=t["name"], kind=t["kind"], cycles=t["cycles"], vectorCount=t["vectorCount"],
               reference={"processor": t["refCircuits"], "circuitId": int(t["refCircuitId"])})
    d = chain.circuit(proc, cid)
    r = chain.circuit(t["refCircuits"], int(t["refCircuitId"]))
    if (d["nIn"], d["nOut"]) != (r["nIn"], r["nOut"]):
        return {**res, "result": "NOT-EQUIVALENT", "detail": f"arity {d['nIn']}/{d['nOut']} vs reference {r['nIn']}/{r['nOut']}"}
    n_in, n_out = d["nIn"], d["nOut"]
    res.update(nIn=n_in, nOut=n_out, gates=d["gates"])
    de, re_ = parse(d["net"]), parse(r["net"])
    if de is None:
        return {**res, "result": "error", "detail": "circuit has a REF or malformed record"}
    if re_ is None:
        return {**res, "result": "unconfirmed", "detail": "reference circuit uses REF"}
    seq = any(e[0] == 1 for e in de) or any(e[0] == 1 for e in re_) or int(t["kind"]) != 0
    if not seq:
        if n_in <= args.exhaustive_max:
            ins, mask = exhaustive_inputs(n_in)
            mode = f"exhaustive {1 << n_in}"
        else:
            width = args.random
            mask = (1 << width) - 1
            ins = [rng.getrandbits(width) for _ in range(n_in)]
            mode = f"random {width} (seed {args.seed})"
        _, o1 = run(de, ins, [], n_out, mask)
        _, o2 = run(re_, ins, [], n_out, mask)
        res["mode"] = mode
        diff = 0
        for x, y in zip(o1, o2):
            diff |= x ^ y
        if not diff:
            return {**res, "result": "equivalent"}
        j = (diff & -diff).bit_length() - 1
        inp = pack(lane(ins, j))
        ce = {"inputs": inp, "outputs": pack(lane(o1, j)), "referenceOutputs": pack(lane(o2, j)),
              "cast": [f"cast call -r {chain.rpc} -b {chain.block} {proc} 'eval(uint256,bytes)(bytes)' {cid} {inp}",
                       f"cast call -r {chain.rpc} -b {chain.block} {t['refCircuits']} 'eval(uint256,bytes)(bytes)' {int(t['refCircuitId'])} {inp}"]}
        if args.confirm:
            got = chain.cast("call", proc, "eval(uint256,bytes)(bytes)", str(cid), inp)
            want = chain.cast("call", t["refCircuits"], "eval(uint256,bytes)(bytes)", str(t["refCircuitId"]), inp)
            ce["onchain"] = {"outputs": got, "referenceOutputs": want, "differs": got != want}
        return {**res, "result": "NOT-EQUIVALENT", "counterexample": ce}
    if args.seq != "every-beat":
        return {**res, "result": "unconfirmed", "detail": "sequential; task beat semantics not published (use --seq every-beat)"}
    width = 256
    mask = (1 << width) - 1
    s1 = [0] * sum(1 for e in de if e[0] == 1)
    s2 = [0] * sum(1 for e in re_ if e[0] == 1)
    beats = max(int(t["cycles"]), 32)
    for k in range(beats):
        ins = [rng.getrandbits(width) for _ in range(n_in)]
        s1, o1 = run(de, ins, s1, n_out, mask)
        s2, o2 = run(re_, ins, s2, n_out, mask)
        if o1 != o2:
            return {**res, "result": "differs-every-beat", "detail": f"first difference at beat {k} from the zero state; "
                    "may be a semantics difference (warm-up, phase), not an error"}
    return {**res, "result": "match-every-beat", "mode": f"{width} random streams x {beats} beats"}


def rows_from(args):
    if args.snapshot:
        with open(args.snapshot) as f:
            snap = json.load(f)
        if args.block is None:
            args.block = snap.get("block")
        for c in snap["circuits"]:
            tid = c.get("miner", {}).get("taskId")
            yield c["processor"], int(c["circuitId"]), (int(tid) if tid is not None else None)
    else:
        with open(args.csv, newline="") as f:
            for row in csv.DictReader(f):
                tid = (row.get("taskId") or "").strip()
                yield row["processor"].strip(), int(row["circuitId"]), (int(tid) if tid else None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--snapshot", help="chain-snapshot.json (uses its circuits and block)")
    src.add_argument("--csv", help="CSV with processor, circuitId[, taskId]")
    ap.add_argument("--rpc", default=DEFAULT_RPC, help="archive JSON-RPC (BNB Smart Chain)")
    ap.add_argument("--block", type=int, default=None, help=f"pinned block (default: snapshot block or {DEFAULT_BLOCK})")
    ap.add_argument("--exhaustive-max", type=int, default=16)
    ap.add_argument("--random", type=int, default=16384, help="random patterns when nIn > --exhaustive-max")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--seq", choices=["off", "every-beat"], default="off")
    ap.add_argument("--confirm", action="store_true", help="reproduce each counterexample with cast eval")
    ap.add_argument("--out", help="write all results as JSON")
    args = ap.parse_args(argv)
    rows = list(rows_from(args))
    if args.block is None:
        args.block = DEFAULT_BLOCK
    chain = Chain(args.rpc, args.block)
    rng = random.Random(args.seed)
    results, bad = [], 0
    for proc, cid, tid in rows:
        try:
            r = check(chain, proc, cid, tid, args, rng)
        except Exception as e:
            r = {"processor": proc, "circuitId": cid, "taskId": tid, "result": "error", "detail": str(e)}
        results.append(r)
        line = f"{r['result']:16} {proc} #{cid} task {r.get('taskId')} {r.get('task', '')} {r.get('mode', r.get('detail', ''))}"
        if "counterexample" in r:
            ce = r["counterexample"]
            line += f"\n    in {ce['inputs']}: circuit {ce['outputs']} reference {ce['referenceOutputs']}"
            if "onchain" in ce:
                line += f" | on chain: {ce['onchain']['outputs']} vs {ce['onchain']['referenceOutputs']}"
            line += "".join(f"\n    {c}" for c in ce["cast"])
        print(line)
        bad += r["result"] == "NOT-EQUIVALENT"
    if args.out:
        with open(args.out, "w") as f:
            json.dump({"block": args.block, "rpc": args.rpc, "results": results}, f, indent=1, ensure_ascii=False)
    counts: dict = {}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print("summary:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
