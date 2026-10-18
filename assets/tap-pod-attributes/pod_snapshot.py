#!/usr/bin/env python3
"""Proof-of-Design snapshot for a Netlist-Bound NFT (TAP draft "PoD attributes").

Reads, read-only (eth_call / eth_getStorageAt / eth_getBlockByNumber only, never a transaction),
the BEM mining contract on BNB Smart Chain at one pinned block and builds

  * the `tap.pod` metadata object (Specification §3), and
  * the ERC-7496 trait values (Specification §5).

Usage:
  pod_snapshot.py <processor> <circuitId> <block> [--rpc URL]... [--raw out.json] [--rig id] [--check]

--check also reads the task's reference circuit and adds `functionCheck` (§3.9, function_check.py).

The first --rpc is the primary node (default: the archive node https://tapeout.net/rpc). Every
further node is a cross-check; a node that has pruned the state ("missing trie node") is skipped and
the read is reported as single-source. Public bsc-dataseed nodes keep state for about a minute only.

The pure functions (build_pod, trait_values, cost, ...) need no network and are used by
make_vectors.py and test_pod.py. ABI encoding/decoding uses Foundry's `cast`.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

from Crypto.Hash import keccak as _keccak

CHAIN_ID = 56
MINING = "0x7e2e0dc66a3bd9103e69b766afa62d9f7b697b46"
# Mining implementation(s) listed in the draft's Deployments section.
KNOWN_IMPLEMENTATIONS = {"0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898"}
ERC1967_IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
DEFAULT_NODES = ["https://tapeout.net/rpc", "https://bsc-dataseed.bnbchain.org"]
RIG_VOUCHER = {"chainId": 196, "contract": "0x9cfc959cd42b2e1d39a0d850c528210e818ae520"}

MINER_SIG = ("(address,uint64,uint32,uint32,uint32,uint32,uint64,uint32,uint64,uint8,address,uint32,uint32,"
             "uint64,uint64,bool,uint64,uint64,uint64,uint128,uint128,uint256)")
MINER_FIELDS = ["circuits", "circuitId", "taskId", "gateCount", "stateCount", "depth", "area", "mult", "since",
                "status", "registrant", "nandBurn", "latchBurn", "bstar", "bonus", "optimal", "commitBlock",
                "firstUnusedId", "stopBlock", "verifWeight", "unverWeight", "debt"]
TASK_SIG = "(uint8,uint32,uint32,uint32,uint32,bool,bytes32,string,uint64,uint256,address,uint64)"
TASK_FIELDS = ["kind", "cycles", "nIn", "nOut", "vectorCount", "active", "vectorsRoot", "name", "refArea",
               "refCost", "refCircuits", "refCircuitId"]

# Confirmed status codes (Specification §3.5). Every other code, including 3, is "unknown".
STATUS_LABELS = {1: "mining"}

# ERC-7496 traits defined by this TAP: (trait name, dataType, where the value comes from).
TRAITS = [
    ("tap.pod.snapshotBlock", "decimal", "block"),
    ("tap.pod.taskId", "decimal", "design.taskId"),
    ("tap.pod.nandBurn", "decimal", "design.nandBurn"),
    ("tap.pod.latchBurn", "decimal", "design.latchBurn"),
    ("tap.pod.area", "decimal", "design.area"),
    ("tap.pod.depth", "decimal", "design.depth"),
    ("tap.pod.cost", "decimal", "design.cost"),
    ("tap.pod.bstar", "decimal", "design.bstar"),
    ("tap.pod.status", "decimal", "standing.status"),
    ("tap.pod.optimal", "boolean", "standing.optimal"),
    ("tap.pod.bonus", "decimal", "standing.bonus"),
    ("tap.pod.multiplier", "decimal", "standing.multiplier"),
    ("tap.pod.verified", "boolean", "standing.verified"),
    ("tap.pod.verifWeight", "decimal", "standing.verifWeight"),
    ("tap.pod.unverWeight", "decimal", "standing.unverWeight"),
]
DISPLAY_NAMES = {
    "tap.pod.snapshotBlock": "PoD snapshot block (BSC)", "tap.pod.taskId": "PoD task",
    "tap.pod.nandBurn": "NAND burn", "tap.pod.latchBurn": "LATCH burn", "tap.pod.area": "Area",
    "tap.pod.depth": "Depth", "tap.pod.cost": "Design cost", "tap.pod.bstar": "Burn basis b*",
    "tap.pod.status": "Miner status (at snapshot)", "tap.pod.optimal": "Optimal first (at snapshot)",
    "tap.pod.bonus": "Design bonus (at snapshot)", "tap.pod.multiplier": "Processor multiplier (at snapshot)",
    "tap.pod.verified": "Verified (at snapshot)", "tap.pod.verifWeight": "Verified weight (at snapshot)",
    "tap.pod.unverWeight": "Unverified weight (at snapshot)",
}


# ---------------------------------------------------------------- pure functions

def keccak256(data: bytes) -> str:
    h = _keccak.new(digest_bits=256)
    h.update(data)
    return "0x" + h.hexdigest()


def trait_key(name: str) -> str:
    return keccak256(name.encode("utf-8"))


def cost(area: int, depth: int, beta: int) -> int:
    """Design cost C = A * max(d, 1) ** beta (exact integer)."""
    return area * max(depth, 1) ** beta


def status_label(code: int) -> str:
    return STATUS_LABELS.get(code, "unknown")


def _int(x):
    return int(str(x).split(" ")[0])


def _bool(x):
    if isinstance(x, bool):
        return x
    return str(x).lower() == "true"


def build_pod(entry: dict, mining: dict, block: int, header: dict = None, implementation: str = None) -> dict:
    """Build the `tap.pod` object from raw reads.

    `entry` has the shape of one item of chain-snapshot.json "circuits" (processor, circuitId, minerKey,
    miner{...}, task{...}); `mining` has lambda, beta, lambdaBurn and processorMultiplier{processor: P}.
    """
    m = entry["miner"]
    t = entry.get("task") or {}
    proc = entry["processor"].lower()
    pm = {k.lower(): v for k, v in mining["processorMultiplier"].items()}
    beta = _int(mining["beta"])
    area, depth = _int(m["area"]), _int(m["depth"])
    vw = _int(m["verifWeight"])
    pod = {
        "v": 1,
        "chainId": CHAIN_ID,
        "block": int(block),
    }
    if header:
        pod["blockHash"] = header["hash"].lower()
        pod["timestamp"] = int(header["timestamp"])
    pod["mining"] = MINING
    if implementation:
        pod["implementation"] = implementation.lower()
    pod.update({
        "processor": proc,
        "circuitId": str(_int(entry["circuitId"])),
        "minerKey": entry["minerKey"].lower(),
        "params": {
            "lambda": _int(mining["lambda"]),
            "beta": beta,
            "lambdaBurn": _int(mining["lambdaBurn"]),
            "processorMultiplier": str(_int(pm[proc])),
        },
        "design": {
            "taskId": _int(m["taskId"]),
            "gateCount": _int(m["gateCount"]),
            "stateCount": _int(m["stateCount"]),
            "nandBurn": _int(m["nandBurn"]),
            "latchBurn": _int(m["latchBurn"]),
            "depth": depth,
            "area": str(area),
            "bstar": str(_int(m["bstar"])),
            "cost": str(cost(area, depth, beta)),
        },
        "standing": {
            "status": _int(m["status"]),
            "statusLabel": status_label(_int(m["status"])),
            "optimal": _bool(m["optimal"]),
            "bonus": str(_int(m["bonus"])),
            "multiplier": _int(m["mult"]),
            "verified": vw > 0,
            "verifWeight": str(vw),
            "unverWeight": str(_int(m["unverWeight"])),
            "since": str(_int(m["since"])),
            "stopBlock": str(_int(m["stopBlock"])),
        },
    })
    if t:
        pod["design"]["task"] = {"name": t["name"], "kTask": str(_int(t["refArea"])), "cRef": str(_int(t["refCost"]))}
    return pod


def _get(pod, path):
    if path == "block":
        return pod["block"]
    a, b = path.split(".")
    return pod[a][b]


def trait_values(pod: dict) -> list:
    """ERC-7496 (name, key, dataType, bytes32 value) for one pod object (Specification §5.3)."""
    out = []
    for name, dtype, path in TRAITS:
        v = _get(pod, path)
        n = (1 if v else 0) if dtype == "boolean" else int(v)
        if n < 0 or n >= 2 ** 256:
            raise ValueError(f"{name} out of range")
        out.append({"name": name, "key": trait_key(name), "dataType": dtype, "value": "0x" + n.to_bytes(32, "big").hex()})
    return out


def trait_schema() -> dict:
    """The ERC-7496 trait metadata (getTraitMetadataURI document) for the traits of this TAP."""
    traits = {}
    for name, dtype, _ in TRAITS:
        dt = {"type": "boolean"} if dtype == "boolean" else {"type": "decimal", "signed": False, "decimals": 0}
        traits[name] = {"displayName": DISPLAY_NAMES[name], "dataType": dt, "validateOnSale": "none",
                        "tokenOwnerCanUpdateValue": False}
    return {"traits": traits}


def cross_checks(pod: dict, entry: dict, extra: dict = None) -> list:
    """Consistency checks between the snapshot and what the contract implies (results, not assertions)."""
    d, s, p = pod["design"], pod["standing"], pod["params"]
    res = []

    def chk(name, ok, detail):
        res.append({"check": name, "ok": bool(ok), "detail": detail})

    area, bstar, c = int(d["area"]), int(d["bstar"]), int(d["cost"])
    chk("gateCount == nandBurn + latchBurn", d["gateCount"] == d["nandBurn"] + d["latchBurn"],
        f'{d["gateCount"]} vs {d["nandBurn"]}+{d["latchBurn"]}')
    chk("area == gateCount + lambda*stateCount", area == d["gateCount"] + p["lambda"] * d["stateCount"],
        f'{area} vs {d["gateCount"]}+{p["lambda"]}*{d["stateCount"]}')
    chk("bstar == nandBurn + lambdaBurn*latchBurn", bstar == d["nandBurn"] + p["lambdaBurn"] * d["latchBurn"],
        f'{bstar} vs {d["nandBurn"]}+{p["lambdaBurn"]}*{d["latchBurn"]}')
    if "circuitBurn" in entry:
        cb = entry["circuitBurn"]
        chk("circuitBurn == (nandBurn, latchBurn)", (int(cb["nandBurn"]), int(cb["latchBurn"])) == (d["nandBurn"], d["latchBurn"]),
            f'{cb["nandBurn"]},{cb["latchBurn"]}')
    if "cachedDepth" in entry:
        cd = entry["cachedDepth"]
        chk("cachedDepth.depth == depth", int(cd["depth"]) == d["depth"], f'cached={cd["cached"]} depth={cd["depth"]} live={cd["live"]}')
    if "netlist" in entry and entry["netlist"]:
        nand, latch = count_records(entry["netlist"])
        chk("netlist NAND/LATCH records == nandBurn/latchBurn", (nand, latch) == (d["nandBurn"], d["latchBurn"]), f"{nand},{latch}")
    if "gateCount" in entry and "nState" in entry:
        chk("circuitInfo gateCount/nState == miner gateCount/stateCount",
            (int(entry["gateCount"]), int(entry["nState"])) == (d["gateCount"], d["stateCount"]),
            f'{entry["gateCount"]},{entry["nState"]}')
    chk("multiplier == processorMultiplier(processor)", str(s["multiplier"]) == p["processorMultiplier"],
        f'{s["multiplier"]} vs {p["processorMultiplier"]}')
    if s["verified"]:
        h = (bstar + int(s["bonus"])) * s["multiplier"]
        chk("verifWeight == (bstar + bonus) * multiplier", int(s["verifWeight"]) == h, f'{s["verifWeight"]} vs {h}')
    if not s["optimal"]:
        chk("bonus == 0 when not optimal", int(s["bonus"]) == 0, s["bonus"])
    if extra:
        bs = extra.get("bestSlot")
        if bs is not None:
            holder = int(bs["holderPlus1"]) - 1
            is_holder = holder == int(pod["circuitId"])
            chk("optimal == (bestSlot holder is this circuit)", is_holder == s["optimal"], f"holder #{holder}")
            if is_holder:
                chk("bestSlot.cost == cost", int(bs["cost"]) == c, f'{bs["cost"]} vs {c}')
            else:
                res.append({"check": "cost vs bestSlot.cost (informative: a cheaper design can lose or never hold the "
                                     "slot after a counterexample kick)", "ok": c >= int(bs["cost"]), "informative": True,
                            "detail": f'{c} vs {bs["cost"]}'})
        if extra.get("bonusOfCost") is not None and s["optimal"]:
            chk("bonusOf(taskId, cost) == bonus", int(extra["bonusOfCost"]) == int(s["bonus"]),
                f'{extra["bonusOfCost"]} vs {s["bonus"]}')
        if "task" in d and extra.get("bonusOfCost") is not None:
            k, cref, q = int(d["task"]["kTask"]), int(d["task"]["cRef"]), 4
            qf = min(max(cref / c, 1 / q), q)
            chk("bonusOf(taskId, cost) ~= kTask * clamp(cRef/cost, 1/4, 4) (float, informative)",
                abs(int(extra["bonusOfCost"]) - k * qf) < 1, f'{extra["bonusOfCost"]} vs {k * qf:.3f}')
    return res


def count_records(netlist_hex: str):
    """Count TAP-02 NAND (0x00, 7 bytes) and LATCH (0x01, 4 bytes) records; REF raises."""
    b = bytes.fromhex(netlist_hex[2:] if netlist_hex.startswith("0x") else netlist_hex)
    i = nand = latch = 0
    while i < len(b):
        if b[i] == 0:
            nand += 1; i += 7
        elif b[i] == 1:
            latch += 1; i += 4
        else:
            raise ValueError(f"record type {b[i]} at {i}: not a NAND/LATCH-only netlist")
    if i != len(b):
        raise ValueError("truncated record")
    return nand, latch


# ---------------------------------------------------------------- chain reads

def _rpc(node, method, params):
    req = urllib.request.Request(node, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                                 {"content-type": "application/json", "user-agent": "tap-pod/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _cast(*args):
    return subprocess.check_output(["cast", *map(str, args)], text=True).strip()


def _decode(out_types, data):
    j = json.loads(_cast("abi-decode", "--json", "f()(" + out_types + ")", data))
    return j["data"] if isinstance(j, dict) and "data" in j else j


class Reader:
    def __init__(self, nodes, block):
        self.nodes, self.block, self.single, self.log = nodes, block, [], []

    def _raw(self, method, params, label, norm=lambda x: x):
        seen = {}
        for node in self.nodes:
            res = None
            t0 = time.time()
            for attempt in range(3):
                try:
                    res = _rpc(node, method, params)
                except urllib.error.HTTPError as e:  # 429 is transient; other HTTP errors are final
                    res = {"error": f"HTTP {e.code}", "_net": e.code == 429 or e.code >= 500}
                except Exception as e:  # network error, timeout
                    res = {"error": str(e), "_net": True}
                err = str(res.get("error", ""))
                transient = res.get("_net") or "429" in err or "rate" in err.lower() or "timeout" in err.lower()
                if "result" in res or not transient:
                    break
                time.sleep(2 + 3 * attempt)
            self.log.append(f"{node}: {label}: {time.time() - t0:.1f}s")
            if "result" in res:
                seen[node] = norm(res["result"])
            else:
                self.log.append(f"{node}: {label}: {str(res.get('error'))[:100]}")
        vals = list(seen.values())
        if not vals:
            raise RuntimeError(f"no node answered {label}")
        if any(v != vals[0] for v in vals):
            raise RuntimeError(f"nodes disagree on {label}: {seen}")
        if len(vals) == 1:
            self.single.append(label)
        return vals[0]

    def call(self, to, sig, *args):
        name, out = sig.split(")(", 1)
        data = _cast("calldata", name + ")", *args)
        res = self._raw("eth_call", [{"to": to, "data": data}, hex(self.block)], f"{sig.split('(')[0]}{args}")
        return _decode(out[:-1], res)

    def storage(self, to, slot):
        return self._raw("eth_getStorageAt", [to, slot, hex(self.block)], f"storage {slot[:10]}")

    def header(self):
        return self._raw("eth_getBlockByNumber", [hex(self.block), False], "header",
                         lambda h: {"number": int(h["number"], 16), "hash": h["hash"], "timestamp": int(h["timestamp"], 16)})


def _items(x):
    return x if isinstance(x, list) else [x]


def read_raw(processor, circuit_id, block, nodes):
    r = Reader(nodes, block)
    key = r.call(MINING, "minerKey(address,uint256)(bytes32)", processor, circuit_id)[0]
    miner = dict(zip(MINER_FIELDS, [str(v).lower() if isinstance(v, bool) else str(v)
                                    for v in r.call(MINING, f"getMiner(bytes32)({MINER_SIG})", key)[0]]))
    if int(miner["taskId"]) == 0 or miner["circuits"].lower() != processor.lower():
        raise SystemExit(f"{processor} #{circuit_id} has no miner record at block {block}")
    task = dict(zip(TASK_FIELDS, [str(v) for v in r.call(MINING, f"getTask(uint32)({TASK_SIG})", miner["taskId"])[0]]))
    burn = r.call(MINING, "circuitBurn(address,uint256)(uint32,uint32)", processor, circuit_id)
    dep = r.call(MINING, "cachedDepth(address,uint256)(bool,uint32,uint32)", processor, circuit_id)
    info = r.call(processor, "circuitInfo(uint256)(uint32,uint32,uint32,uint32)", circuit_id)
    net = r.call(processor, "netlist(uint256)(bytes)", circuit_id)[0]
    mining = {fn: int(r.call(MINING, f"{fn}()({typ})")[0]) for fn, typ in
              [("lambda", "uint16"), ("beta", "uint8"), ("lambdaBurn", "uint16")]}
    mining["processorMultiplier"] = {processor.lower(): int(r.call(MINING, "processorMultiplier(address)(uint256)", processor)[0])}
    bs = r.call(MINING, "bestSlot(uint32,address)(uint64,uint256)", miner["taskId"], processor)
    c = cost(int(miner["area"]), int(miner["depth"]), mining["beta"])
    bonus_of = int(r.call(MINING, "bonusOf(uint32,uint256)(uint64)", miner["taskId"], c)[0])
    impl = "0x" + r.storage(MINING, ERC1967_IMPL_SLOT)[-40:]
    entry = {"processor": processor, "circuitId": int(circuit_id), "minerKey": key, "miner": miner, "task": task,
             "circuitBurn": {"nandBurn": int(burn[0]), "latchBurn": int(burn[1])},
             "cachedDepth": {"cached": bool(_bool(dep[0])), "depth": int(dep[1]), "live": int(dep[2])},
             "nIn": int(info[0]), "nOut": int(info[1]), "nState": int(info[2]), "gateCount": int(info[3]), "netlist": net}
    extra = {"bestSlot": {"holderPlus1": str(bs[0]).split(" ")[0], "cost": str(bs[1]).split(" ")[0]},
             "bonusOfCost": str(bonus_of)}
    return {"block": block, "header": r.header(), "implementation": impl, "entry": entry, "mining": mining,
            "extra": extra, "nodes": nodes, "singleSourceReads": r.single, "nodeLog": r.log, "transactionsSent": 0}


def read_reference(ref_processor, ref_id, block, nodes):
    """Read a task's reference circuit (getTask refCircuits / refCircuitId) at `block`."""
    r = Reader(nodes, block)
    info = r.call(ref_processor, "circuitInfo(uint256)(uint32,uint32,uint32,uint32)", ref_id)
    net = r.call(ref_processor, "netlist(uint256)(bytes)", ref_id)[0]
    return {"processor": ref_processor.lower(), "circuitId": int(ref_id), "block": block, "nIn": int(info[0]),
            "nOut": int(info[1]), "nState": int(info[2]), "gateCount": int(info[3]), "netlist": net,
            "singleSourceReads": r.single, "transactionsSent": 0}


def function_check_for(entry, task, reference, seed=None):
    """§3.9 functionCheck object for a miner entry, its task tuple and the reference circuit read."""
    import function_check as fc
    return fc.check(bytes.fromhex(entry["netlist"][2:]), int(entry["nIn"]), int(entry["nOut"]),
                    bytes.fromhex(reference["netlist"][2:]), reference["nIn"], reference["nOut"],
                    cycles=int(task["cycles"]), seed_hex=seed or fc.DEFAULT_SEED,
                    ref_id={"processor": reference["processor"], "circuitId": str(reference["circuitId"])})


def main(argv):
    args, nodes, raw_out, rig, check = [], [], None, None, False
    i = 0
    while i < len(argv):
        if argv[i] == "--rpc":
            nodes.append(argv[i + 1]); i += 2
        elif argv[i] == "--raw":
            raw_out = argv[i + 1]; i += 2
        elif argv[i] == "--check":
            check = True; i += 1
        elif argv[i] == "--rig":
            rig = argv[i + 1]; i += 2
        else:
            args.append(argv[i]); i += 1
    if len(args) != 3:
        raise SystemExit(__doc__)
    processor, cid, block = args[0], int(args[1]), int(args[2])
    raw = read_raw(processor, cid, block, nodes or DEFAULT_NODES)
    if raw_out:
        with open(raw_out, "w") as f:
            json.dump(raw, f, indent=1)
            f.write("\n")
    pod = build_pod(raw["entry"], raw["mining"], block, raw["header"], raw["implementation"])
    if check:
        t = raw["entry"]["task"]
        ref = read_reference(t["refCircuits"], int(t["refCircuitId"]), block, nodes or DEFAULT_NODES)
        pod["functionCheck"] = function_check_for(raw["entry"], t, ref)
    out = {"pod": pod, "traits": trait_values(pod), "crossChecks": cross_checks(pod, raw["entry"], raw["extra"]),
           "singleSourceReads": raw["singleSourceReads"]}
    if rig is not None:
        out["rig"] = dict(RIG_VOUCHER, id=str(int(rig)))
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main(sys.argv[1:])
