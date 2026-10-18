#!/usr/bin/env python3
"""Build vectors.json for the PoD-attributes draft from recorded mainnet reads (no network).

Inputs:
  ../tap-draft-netlist-bound-nft/chain-snapshot.json   read by tools/fetch_chain.py at one pinned BNB Smart Chain block
  raw/raw<id>.json          read by pod_snapshot.py --raw at the same block (adds bestSlot, bonusOf,
                            the block header and the proxy implementation; also optimal-slot holders)
  synthetic/*.json          hand-built SYNTHETIC examples in the raw-read shape (verifiedButWrong); not chain data
Output: vectors.json (deterministic).
"""
import copy
import glob
import json
import os
import sys

import function_check
from pod_snapshot import function_check_for
from pod_snapshot import MINING, RIG_VOUCHER, TRAITS, build_pod, cross_checks, trait_key, trait_schema, trait_values
from pod_validate import validate_pod, validate_tap

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tap-draft-netlist-bound-nft"))

COMPARE = ["miner", "task", "circuitBurn", "cachedDepth", "netlist", "nIn", "nOut", "nState", "gateCount"]


def _norm(x):
    return json.loads(json.dumps(x).lower())


def load_raw():
    raws = {}
    for p in sorted(glob.glob(os.path.join(HERE, "raw", "raw*.json"))):
        r = json.load(open(p, encoding="utf-8"))
        raws[(r["entry"]["processor"].lower(), int(r["entry"]["circuitId"]))] = (os.path.relpath(p, HERE), r)
    return raws


def with_fc(pod, entry):
    """Add §3.9 functionCheck from the recorded reference circuit raw/ref-task<id>.json, if present."""
    p = os.path.join(HERE, "raw", f"ref-task{pod['design']['taskId']}.json")
    if os.path.exists(p) and entry.get("task"):
        with open(p, encoding="utf-8") as f:
            pod["functionCheck"] = function_check_for(entry, entry["task"], json.load(f))
    return pod


def manifest_cases(meta_tap):
    """§4.4: the manifest fixes the snapshot block (and rule, check procedure) before the seed."""
    base = {"tapManifest": 1,
            "collection": {"chainId": 196, "address": "0x0000000000000000000000000000000000000001", "firstTokenId": 1,
                           "supply": 1},
            "reveal": {"source": "drand", "...": "parameters of draft A §6.1"},
            "pools": ["... draft A §5.2 ..."],
            "pod": {"block": meta_tap["pod"]["block"],
                    "rule": {"sha256": "0x" + "22" * 32, "uris": ["ipfs://example-rarity-rule"]},
                    "functionCheck": {"procedure": function_check.PROCEDURE, "seed": function_check.DEFAULT_SEED}}}
    out = []

    def case(label, f, valid, expect=None):
        m = copy.deepcopy(base)
        f(m)
        r = validate_tap(meta_tap, m)
        assert r.ok == valid, (label, r.errors)
        out.append({"label": label, "manifestPod": m.get("pod"), "revealSource": m["reveal"]["source"], "valid": r.ok,
                    "errors": r.errors, "warnings": r.warnings, "expect": expect})

    case("snapshot block committed in the manifest", lambda m: None, True)
    case("manifest without pod for a revealed collection", lambda m: m.pop("pod"), False, "manifest.pod")
    case("snapshot earlier than the committed block", lambda m: m["pod"].__setitem__("block", m["pod"]["block"] + 1),
         False, "earlier than the block committed")
    case("refreshed snapshot after the committed block (warning only)",
         lambda m: m["pod"].__setitem__("block", m["pod"]["block"] - 1000), True, "refreshed snapshot")
    case("collection without a reveal (source none) need not commit", lambda m: (m.pop("pod"), m["reveal"].update(source="none")),
         True)
    return out


def invalid_cases(pod):
    """Mutations of a valid pod object and the error each must produce."""
    out = []

    def case(label, f, expect):
        p = copy.deepcopy(pod)
        f(p)
        r = validate_pod(p)
        out.append({"label": label, "pod": p, "valid": r.ok, "errors": r.errors, "expectError": expect})

    case("cost not equal to area*max(depth,1)^beta", lambda p: p["design"].__setitem__("cost", "109"), "design.cost")
    case("verified true but verifWeight 0", lambda p: p["standing"].__setitem__("verifWeight", "0"), "verified")
    case("statusLabel for unknown code", lambda p: p["standing"].update(status=2, statusLabel="mining"), "statusLabel")
    case("wrong chainId", lambda p: p.__setitem__("chainId", 196), "chainId")
    case("mixed-case processor address", lambda p: p.__setitem__("processor", p["processor"].upper().replace("0X", "0x")), "processor")
    case("circuitId as JSON number", lambda p: p.__setitem__("circuitId", int(p["circuitId"])), "circuitId")
    case("block missing", lambda p: p.pop("block"), "block")
    case("cost as JSON number", lambda p: p["design"].__setitem__("cost", int(p["design"]["cost"])), "design.cost")
    case("unknown version", lambda p: p.__setitem__("v", 2), ".v")
    case("functionCheck exhaustive on a sequential design",
         lambda p: (p["design"].__setitem__("stateCount", 1), p["design"].__setitem__("area", str(int(p["design"]["area"]) + 6)),
                    p["design"].__setitem__("cost", str((int(p["design"]["area"])) * max(p["design"]["depth"], 1) ** 3))),
         "exhaustive applies only")
    case("functionCheck sampled without seed",
         lambda p: p["functionCheck"].update(method="sampled"), "functionCheck.seed")
    case("functionCheck unconfirmed with a result",
         lambda p: p["functionCheck"].update(method="unconfirmed"), "must be absent")
    return out


def metadata_example(entry, pod, processor_number, rig_id):
    import tapnft  # draft A reference implementation
    net = bytes.fromhex(entry["netlist"][2:])
    f = tapnft.file_from_chain(net, entry["nIn"], entry["nOut"])
    m = tapnft.check_file(f)
    tap = {
        "v": 1,
        "id": "eip155:196/erc721:0x0000000000000000000000000000000000000001/1",
        "state": "revealed",
        "netlist": {"format": "tapnet/1", "sha256": tapnft.hex32(tapnft.netlist_hash(f)), "bytes": len(f),
                    **m.as_json(), "uris": ["ipfs://example"]},
        "source": {"chainId": 56, "processor": pod["processor"], "circuitId": pod["circuitId"],
                   "name": tapnft.tape_name(int(pod["circuitId"]), processor_number, None), "block": pod["block"]},
        "pod": pod,
        "rig": dict(RIG_VOUCHER, id=str(rig_id)),
    }
    return {"name": "Example token (illustrative collection address)", "tap": tap}


def main():
    snap = json.load(open(os.path.join(HERE, "..", "tap-draft-netlist-bound-nft", "chain-snapshot.json"), encoding="utf-8"))
    raws = load_raw()
    block = snap["block"]
    any_raw = next(iter(raws.values()))[1]
    assert all(r["block"] == block for _, r in raws.values()), "raw reads must be at the snapshot block"
    header, impl = any_raw["header"], any_raw["implementation"]
    snap_impl = "0x" + snap["mining"]["implementationSlot"][-40:]
    assert snap_impl.lower() == impl.lower(), (snap_impl, impl)
    mining = {k: snap["mining"][k] for k in ("lambda", "beta", "lambdaBurn", "processorMultiplier")}

    cases, agreement = [], []
    for e in snap["circuits"]:
        key = (e["processor"].lower(), int(e["circuitId"]))
        has = int(e["miner"]["taskId"]) != 0 and e["miner"]["circuits"].lower() == key[0]
        c = {"label": f'{e["processorName"]} #{e["circuitId"]}', "processor": key[0], "processorNumber": e["processorNumber"],
             "circuitId": str(e["circuitId"]), "source": "chain-snapshot.json", "hasMinerRecord": has}
        if not has:
            c["pod"] = None
            c["note"] = ("getMiner(minerKey) returns the zero record (the netlist contains REF records, which the mining "
                         "contract rejects): no PoD attributes; tap.pod.snapshotBlock trait stays 0")
            c["traits"] = [{"name": n, "key": trait_key(n), "value": "0x" + "00" * 32} for n, _, _ in TRAITS]
            cases.append(c)
            continue
        extra = raws[key][1]["extra"] if key in raws else None
        pod = with_fc(build_pod(e, mining, block, header, impl), e)
        r = validate_pod(pod)
        c.update(pod=pod, valid=r.ok, warnings=r.warnings, traits=trait_values(pod), crossChecks=cross_checks(pod, e, extra))
        if key in raws:
            other = raws[key][1]["entry"]
            diff = [k for k in COMPARE if _norm(e.get(k)) != _norm(other.get(k))]
            agreement.append({"circuit": c["label"], "file": raws[key][0], "fieldsCompared": COMPARE, "differences": diff})
            c["extraReads"] = extra
        cases.append(c)

    snap_keys = {(e["processor"].lower(), int(e["circuitId"])) for e in snap["circuits"]}
    holders, wrong = [], []
    for key, (path, r) in sorted(raws.items(), key=lambda kv: kv[0][1]):
        if key in snap_keys:
            continue
        pod = with_fc(build_pod(r["entry"], r["mining"], r["block"], r["header"], r["implementation"]), r["entry"])
        v = validate_pod(pod)
        item = {"source": path, "pod": pod, "valid": v.ok, "warnings": v.warnings, "traits": trait_values(pod),
                "extraReads": r["extra"], "crossChecks": cross_checks(pod, r["entry"], r["extra"])}
        assert pod["standing"]["optimal"], path
        holders.append(dict(label=f"TapeOut #{key[1]} (optimal-slot holder)", **item))
    for path in sorted(glob.glob(os.path.join(HERE, "synthetic", "*.json"))):
        r = json.load(open(path, encoding="utf-8"))
        assert r.get("synthetic") is True, path
        assert r["block"] == block, path
        pod = with_fc(build_pod(r["entry"], r["mining"], r["block"], r["header"], r["implementation"]), r["entry"])
        v = validate_pod(pod)
        wrong.append({"label": "SYNTHETIC example (not a TapeOut circuit): verified, but computes another function "
                               "than the reference",
                      "synthetic": True, "note": r["note"], "source": os.path.relpath(path, HERE), "pod": pod,
                      "valid": v.ok, "warnings": v.warnings, "traits": trait_values(pod), "extraReads": r["extra"],
                      "crossChecks": cross_checks(pod, r["entry"], r["extra"])})

    first = next(c for c in cases if c.get("pod"))
    meta = metadata_example(next(e for e in snap["circuits"] if str(e["circuitId"]) == first["circuitId"]),
                            first["pod"], first["processorNumber"], 1)
    mv = validate_tap(meta["tap"])
    mcases = manifest_cases(meta["tap"])

    out = {
        "description": "Vectors for TAP draft 'Proof-of-Design Attributes for Netlist-Bound NFTs'. Values read "
                       "read-only from BNB Smart Chain; no transaction was sent.",
        "chainId": 56,
        "block": block,
        "blockHash": header["hash"],
        "timestamp": header["timestamp"],
        "mining": MINING,
        "implementation": impl.lower(),
        "params": {"lambda": mining["lambda"], "beta": mining["beta"], "lambdaBurn": mining["lambdaBurn"],
                   "processorMultiplier": {k.lower(): v for k, v in mining["processorMultiplier"].items()}},
        "nodes": {"chain-snapshot.json": snap["nodes"], "singleSourceReads": snap["singleSourceReads"],
                  "raw": any_raw["nodes"]},
        "limitations": "Only TapeOut #17851 and #17852 in chain-snapshot.json were confirmed by two operators. The reads "
                       "listed in nodes.singleSourceReads (circuits #3151 and #38 and the contract parameters) and every "
                       "eth_call in raw/ come from the archive node https://tapeout.net/rpc alone, because other public "
                       "nodes no longer serve state at this block; only block headers were cross-checked. Repeat with a "
                       "second archive operator before Review.",
        "traitKeys": [{"name": n, "key": trait_key(n), "dataType": t} for n, t, _ in TRAITS],
        "traitSchema": trait_schema(),
        "cases": cases,
        "optimalHolders": holders,
        "verifiedButWrong": wrong,
        "manifestCommitment": mcases,
        "readerAgreement": agreement,
        "functionCheck": {"procedure": function_check.PROCEDURE, "defaultSeed": function_check.DEFAULT_SEED,
                          "defaultSeedPreimage": "TAP-pod functionCheck v1",
                          "exhaustiveMaxNIn": function_check.EXHAUSTIVE_MAX_NIN,
                          "sampledCombinational": function_check.SAMPLED_COMBINATIONAL,
                          "sequentialRuns": function_check.SEQ_RUNS, "sequentialMinBeats": function_check.SEQ_MIN_BEATS},
        "invalid": invalid_cases(first["pod"]),
        "metadataExample": {"document": meta, "valid": mv.ok, "errors": mv.errors, "warnings": mv.warnings},
    }
    with open(os.path.join(HERE, "vectors.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
        f.write("\n")
    with open(os.path.join(HERE, "trait-metadata.json"), "w", encoding="utf-8") as f:
        json.dump(trait_schema(), f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("wrote vectors.json:", len(cases), "cases,", len(holders), "holders,", len(wrong), "wrong,",
          len(out["invalid"]), "invalid,", len(mcases), "manifest cases")


if __name__ == "__main__":
    main()
