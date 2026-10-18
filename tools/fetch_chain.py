"""Read-only snapshot of the mainnet data the vectors are built from.

Uses `cast` (Foundry) for ABI work. Every value is read from two independent BNB Smart Chain
nodes at one pinned block and must agree; the result is written to
../assets/chain-snapshot.json. No transaction is sent.
"""
import json
import urllib.request
import time
import subprocess
import sys

NODES = ["https://tapeout.net/rpc", "https://bsc-rpc.publicnode.com", "https://bsc-dataseed.bnbchain.org", "https://bsc-dataseed1.ninicoin.io"]
MINING = "0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46"
FACTORY = "0x68224F668083c29e9800Be2a646d42d18cedF7e2"
TAPEOUT = "0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C"   # processor 30, "TapeOut"
BEHEMOTH = "0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c"  # processor 1, "Blonskr_No1"
CIRCUITS = [
    (TAPEOUT, 30, 17851),
    (TAPEOUT, 30, 17852),
    (TAPEOUT, 30, 3151),
    (BEHEMOTH, 1, 38),
]
MINER = ("(address,uint64,uint32,uint32,uint32,uint32,uint64,uint32,uint64,uint8,address,uint32,uint32,"
         "uint64,uint64,bool,uint64,uint64,uint64,uint128,uint128,uint256)")
MINER_FIELDS = ["circuits", "circuitId", "taskId", "gateCount", "stateCount", "depth", "area", "mult", "since",
                "status", "registrant", "nandBurn", "latchBurn", "bstar", "bonus", "optimal", "commitBlock",
                "firstUnusedId", "stopBlock", "verifWeight", "unverWeight", "debt"]
TASK = "(uint8,uint32,uint32,uint32,uint32,bool,bytes32,string,uint64,uint256,address,uint64)"
TASK_FIELDS = ["kind", "cycles", "nIn", "nOut", "vectorCount", "active", "vectorsRoot", "name", "refArea",
               "refCost", "refCircuits", "refCircuitId"]


SINGLE = []


def _rpc(node, payload):
    req = urllib.request.Request(node, json.dumps(payload).encode(),
                                 {"content-type": "application/json", "user-agent": "tap-tools/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _one(node, block, to, sig, args):
    data = subprocess.check_output(["cast", "calldata", sig.split(")(")[0] + ")", *map(str, args)], text=True).strip()
    out_types = "f()(" + sig.split(")(", 1)[1] if ")(" in sig else None
    for attempt in range(3):
        try:
            res = _rpc(node, {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                              "params": [{"to": to, "data": data}, hex(block)]})
        except Exception as e:  # network error or HTTP 429
            res = {"error": str(e)}
        if "result" in res:
            time.sleep(0.3)
            dec = subprocess.run(["cast", "abi-decode", "--json", out_types, res["result"]],
                                 capture_output=True, text=True)
            if dec.returncode:
                raise SystemExit(f"cannot decode {sig}: {dec.stderr}")
            j = json.loads(dec.stdout)
            return j["data"] if isinstance(j, dict) and "data" in j else j
        if "missing trie node" in str(res.get("error")):
            return None
        print("  retry", node.split("//")[1], sig.split("(")[0], str(res.get("error"))[:120], file=sys.stderr)
        time.sleep(3 + 4 * attempt)
    return None


def call(block, to, sig, *args):
    """Read from the nodes in turn until two of them return the same value."""
    seen = []
    for node in NODES:
        v = _one(node, block, to, sig, args)
        if v is None:
            continue
        if v in seen:
            return v
        seen.append(v)
    if len(seen) == 1:
        SINGLE.append(f"{sig} {args}")
        return seen[0]
    raise SystemExit(f"nodes disagree on {sig} {args}: {seen}")


def tuple_items(s):
    """cast --json renders a tuple as a JSON list (newer cast) or one string '(a, b, ...)'."""
    if isinstance(s, list):
        return [str(x).lower() if isinstance(x, bool) else str(x) for x in s]
    s = s.strip()[1:-1]
    out, depth, cur, q = [], 0, "", False
    for ch in s:
        if ch == '"':
            q = not q
        if ch == "," and depth == 0 and not q:
            out.append(cur.strip()); cur = ""; continue
        depth += ch in "([" and not q
        depth -= ch in ")]" and not q
        cur += ch
    out.append(cur.strip())
    return [x.split(" [")[0].strip('"') for x in out]


def main():
    block = int(sys.argv[1]) if len(sys.argv) > 1 else int(subprocess.check_output(
        ["cast", "block-number", "-r", NODES[0]], text=True)) - 20
    snap = {"chainId": 56, "block": block, "nodes": NODES, "transactionsSent": 0, "circuits": [], "mining": {}}
    for cpu, number, cid in CIRCUITS:
        info = call(block, cpu, "circuitInfo(uint256)(uint32,uint32,uint32,uint32)", cid)
        net = call(block, cpu, "netlist(uint256)(bytes)", cid)[0]
        entry = {"processor": cpu, "processorNumber": number, "processorName": call(block, cpu, "name()(string)")[0],
                 "circuitId": cid, "nIn": int(info[0]), "nOut": int(info[1]), "nState": int(info[2]),
                 "gateCount": int(info[3]), "netlist": net}
        key = call(block, MINING, "minerKey(address,uint256)(bytes32)", cpu, cid)[0]
        miner = dict(zip(MINER_FIELDS, tuple_items(call(block, MINING, f"getMiner(bytes32)({MINER})", key)[0])))
        entry["minerKey"] = key
        entry["miner"] = miner
        burn = call(block, MINING, "circuitBurn(address,uint256)(uint32,uint32)", cpu, cid)
        entry["circuitBurn"] = {"nandBurn": int(burn[0]), "latchBurn": int(burn[1])}
        dep = call(block, MINING, "cachedDepth(address,uint256)(bool,uint32,uint32)", cpu, cid)
        entry["cachedDepth"] = {"cached": dep[0], "depth": int(dep[1]), "live": int(dep[2])}
        if int(miner["taskId"]) and miner["circuits"].lower() == cpu.lower():
            entry["task"] = dict(zip(TASK_FIELDS, tuple_items(call(block, MINING, f"getTask(uint32)({TASK})", miner["taskId"])[0])))
        snap["circuits"].append(entry)
        print("read", entry["processorName"], cid, file=sys.stderr)
    m = snap["mining"]
    m["address"] = MINING
    for fn, typ in [("lambda()", "uint16"), ("beta()", "uint8"), ("lambdaBurn()", "uint16"), ("taskCount()", "uint32")]:
        m[fn[:-2]] = int(call(block, MINING, f"{fn}({typ})")[0])
    m["processorMultiplier"] = {cpu: int(call(block, MINING, "processorMultiplier(address)(uint256)", cpu)[0])
                                for cpu in (TAPEOUT, BEHEMOTH)}
    m["implementationSlot"] = subprocess.check_output(
        ["cast", "storage", "-r", NODES[0], "-b", str(block), MINING,
         "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"], text=True).strip()
    snap["singleSourceReads"] = SINGLE
    with open(sys.argv[2] if len(sys.argv) > 2 else "../assets/chain-snapshot.json", "w") as f:
        json.dump(snap, f, indent=1)
        f.write("\n")


if __name__ == "__main__":
    main()
