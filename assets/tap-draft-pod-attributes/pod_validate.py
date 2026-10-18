#!/usr/bin/env python3
"""Validator for the `tap.pod` object and the optional `tap.rig` reference (TAP draft "PoD attributes").

  pod_validate.py metadata.json      # a whole token metadata document with a `tap` object
  pod_validate.py --pod pod.json     # a bare `tap.pod` object

Prints errors (the object does not conform) and warnings (it conforms, but a cross-check that the
Specification asks tools to report did not hold). Exit status 1 if there is any error. No network.
"""
import json
import re
import sys

from pod_snapshot import CHAIN_ID, KNOWN_IMPLEMENTATIONS, MINING, RIG_VOUCHER, STATUS_LABELS, cost, keccak256

DEC = re.compile(r"^(0|[1-9][0-9]*)$")
ADDR = re.compile(r"^0x[0-9a-f]{40}$")
HEX32 = re.compile(r"^0x[0-9a-f]{64}$")
U256 = 2 ** 256


class Result:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, m):
        self.errors.append(m)

    def warn(self, m):
        self.warnings.append(m)

    @property
    def ok(self):
        return not self.errors


def _is_int(x, lo=0, hi=2 ** 32 - 1):
    return isinstance(x, int) and not isinstance(x, bool) and lo <= x <= hi


def _is_dec(x, hi=U256):
    return isinstance(x, str) and bool(DEC.match(x)) and int(x) < hi


def _need(obj, key, check, what, r, path):
    if not isinstance(obj, dict) or key not in obj:
        r.err(f"{path}.{key}: missing")
        return False
    if not check(obj[key]):
        r.err(f"{path}.{key}: must be {what}, got {obj[key]!r}")
        return False
    return True


def validate_pod(pod, r=None):
    r = r or Result()
    P = "tap.pod"
    if not isinstance(pod, dict):
        r.err(f"{P}: must be an object")
        return r
    _need(pod, "v", lambda x: x == 1, "1", r, P)
    _need(pod, "chainId", lambda x: x == CHAIN_ID, str(CHAIN_ID), r, P)
    _need(pod, "block", lambda x: _is_int(x, 1, 2 ** 64 - 1), "a block number >= 1", r, P)
    _need(pod, "mining", lambda x: x == MINING, f"{MINING} (lowercase)", r, P)
    proc_ok = _need(pod, "processor", lambda x: isinstance(x, str) and bool(ADDR.match(x)), "a lowercase address", r, P)
    cid_ok = _need(pod, "circuitId", lambda x: _is_dec(x), "a decimal string", r, P)
    key_ok = _need(pod, "minerKey", lambda x: isinstance(x, str) and bool(HEX32.match(x)), "0x + 64 lowercase hex", r, P)
    for k, check, what in [("blockHash", lambda x: isinstance(x, str) and bool(HEX32.match(x)), "0x + 64 lowercase hex"),
                           ("timestamp", lambda x: _is_int(x, 0, 2 ** 64 - 1), "an integer"),
                           ("implementation", lambda x: isinstance(x, str) and bool(ADDR.match(x)), "a lowercase address")]:
        if k in pod:
            _need(pod, k, check, what, r, P)
    if isinstance(pod.get("implementation"), str) and ADDR.match(pod["implementation"]) \
            and pod["implementation"] not in KNOWN_IMPLEMENTATIONS:
        r.warn(f"{P}.implementation {pod['implementation']} is not the implementation listed in Deployments")
    if proc_ok and cid_ok and key_ok:
        packed = bytes.fromhex(pod["processor"][2:]) + int(pod["circuitId"]).to_bytes(32, "big")
        if keccak256(packed) != pod["minerKey"]:
            r.warn(f"{P}.minerKey differs from keccak256(abi.encodePacked(processor, circuitId)) (the observed derivation)")

    pa = pod.get("params")
    if not isinstance(pa, dict):
        r.err(f"{P}.params: missing")
        pa = None
    else:
        for k, hi in [("lambda", 2 ** 16 - 1), ("beta", 255), ("lambdaBurn", 2 ** 16 - 1)]:
            _need(pa, k, lambda x, hi=hi: _is_int(x, 0, hi), "an integer", r, P + ".params")
        _need(pa, "processorMultiplier", _is_dec, "a decimal string", r, P + ".params")

    d = pod.get("design")
    d_ok = isinstance(d, dict)
    if not d_ok:
        r.err(f"{P}.design: missing")
    else:
        for k in ["gateCount", "stateCount", "nandBurn", "latchBurn", "depth"]:
            d_ok &= _need(d, k, _is_int, "a uint32 integer", r, P + ".design")
        d_ok &= _need(d, "taskId", lambda x: _is_int(x, 1), "a task id >= 1", r, P + ".design")
        d_ok &= _need(d, "area", lambda x: _is_dec(x, 2 ** 64), "a uint64 decimal string", r, P + ".design")
        d_ok &= _need(d, "bstar", lambda x: _is_dec(x, 2 ** 64), "a uint64 decimal string", r, P + ".design")
        d_ok &= _need(d, "cost", _is_dec, "a decimal string", r, P + ".design")
        if "task" in d:
            t = d["task"]
            if not isinstance(t, dict):
                r.err(f"{P}.design.task: must be an object")
            else:
                _need(t, "name", lambda x: isinstance(x, str), "a string", r, P + ".design.task")
                _need(t, "kTask", lambda x: _is_dec(x, 2 ** 64), "a uint64 decimal string", r, P + ".design.task")
                _need(t, "cRef", _is_dec, "a decimal string", r, P + ".design.task")

    s = pod.get("standing")
    s_ok = isinstance(s, dict)
    if not s_ok:
        r.err(f"{P}.standing: missing")
    else:
        s_ok &= _need(s, "status", lambda x: _is_int(x, 0, 255), "a uint8 integer", r, P + ".standing")
        s_ok &= _need(s, "statusLabel", lambda x: isinstance(x, str), "a string", r, P + ".standing")
        for k in ["optimal", "verified"]:
            s_ok &= _need(s, k, lambda x: isinstance(x, bool), "true or false", r, P + ".standing")
        s_ok &= _need(s, "multiplier", _is_int, "a uint32 integer", r, P + ".standing")
        for k, hi in [("bonus", 2 ** 64), ("verifWeight", 2 ** 128), ("unverWeight", 2 ** 128), ("since", 2 ** 64),
                      ("stopBlock", 2 ** 64)]:
            s_ok &= _need(s, k, lambda x, hi=hi: _is_dec(x, hi), "a decimal string", r, P + ".standing")

    if "functionCheck" in pod:
        validate_function_check(pod["functionCheck"], r, d if d_ok else None)

    if not r.ok:
        return r

    # Derived values (errors).
    want = cost(int(d["area"]), d["depth"], pa["beta"])
    if int(d["cost"]) != want:
        r.err(f"{P}.design.cost: {d['cost']} != area * max(depth,1)^beta = {want}")
    if s["verified"] != (int(s["verifWeight"]) > 0):
        r.err(f"{P}.standing.verified must equal verifWeight > 0")
    label = STATUS_LABELS.get(s["status"], "unknown")
    if s["statusLabel"] != label:
        r.err(f"{P}.standing.statusLabel must be {label!r} for status {s['status']}")

    # Cross-checks (warnings): relations observed on chain that the mining contract does not publish as rules.
    if d["gateCount"] != d["nandBurn"] + d["latchBurn"]:
        r.warn("design.gateCount != nandBurn + latchBurn")
    if int(d["area"]) != d["gateCount"] + pa["lambda"] * d["stateCount"]:
        r.warn("design.area != gateCount + lambda * stateCount (parameters may have changed since registration)")
    if int(d["bstar"]) != d["nandBurn"] + pa["lambdaBurn"] * d["latchBurn"]:
        r.warn("design.bstar != nandBurn + lambdaBurn * latchBurn (parameters may have changed since registration)")
    if not s["optimal"] and int(s["bonus"]) != 0:
        r.warn("standing.bonus is nonzero although optimal is false")
    if s["verified"] and int(s["verifWeight"]) != (int(d["bstar"]) + int(s["bonus"])) * s["multiplier"]:
        r.warn("standing.verifWeight != (bstar + bonus) * multiplier")
    if str(s["multiplier"]) != pa["processorMultiplier"]:
        r.warn("standing.multiplier != params.processorMultiplier")
    if label == "unknown":
        r.warn(f"standing.status {s['status']} has no known meaning")
    return r


FC_METHODS = ("exhaustive", "sampled", "unconfirmed")
FC_RESULTS = ("match", "mismatch")


def validate_function_check(fc, r, design=None):
    """§3.9 `tap.pod.functionCheck`: a check against the task's reference circuit, separate from `verified`."""
    P = "tap.pod.functionCheck"
    if not isinstance(fc, dict):
        r.err(f"{P}: must be an object")
        return
    ok = _need(fc, "method", lambda x: x in FC_METHODS, " | ".join(FC_METHODS), r, P)
    _need(fc, "vectors", lambda x: _is_int(x, 0, 2 ** 53 - 1), "an integer", r, P)
    _need(fc, "procedure", lambda x: isinstance(x, str) and 0 < len(x) <= 256, "a non-empty string", r, P)
    if not ok:
        return
    m = fc["method"]
    if m == "unconfirmed":
        if "result" in fc:
            r.err(f"{P}.result: must be absent when method is unconfirmed")
    else:
        _need(fc, "result", lambda x: x in FC_RESULTS, " | ".join(FC_RESULTS), r, P)
        _need(fc, "reference", lambda x: isinstance(x, dict) and isinstance(x.get("processor"), str)
              and bool(ADDR.match(x["processor"])) and _is_dec(x.get("circuitId")),
              "{processor: lowercase address, circuitId: decimal string}", r, P)
    if m == "sampled":
        _need(fc, "seed", lambda x: isinstance(x, str) and bool(HEX32.match(x)), "0x + 64 lowercase hex", r, P)
    if m == "exhaustive" and design is not None and design.get("stateCount") != 0:
        r.err(f"{P}.method: exhaustive applies only to combinational circuits (design.stateCount 0)")


def validate_manifest_pod(mp, r):
    """§4.4 `pod` member of the collection manifest."""
    P = "manifest.pod"
    if not isinstance(mp, dict):
        r.err(f"{P}: must be an object")
        return False
    ok = _need(mp, "block", lambda x: _is_int(x, 1, 2 ** 53 - 1), "a block number >= 1", r, P)
    for k in ("rule",):
        if k in mp:
            _need(mp, k, lambda x: isinstance(x, dict) and isinstance(x.get("sha256"), str) and bool(HEX32.match(x["sha256"]))
                  and isinstance(x.get("uris"), list) and len(x["uris"]) > 0, "{sha256, uris}", r, P)
    if "functionCheck" in mp:
        _need(mp, "functionCheck", lambda x: isinstance(x, dict) and isinstance(x.get("procedure"), str)
              and isinstance(x.get("seed"), str) and bool(HEX32.match(x["seed"])), "{procedure, seed}", r, P)
    return ok


def validate_rig(rig, r):
    P = "tap.rig"
    if not isinstance(rig, dict):
        r.err(f"{P}: must be an object")
        return
    _need(rig, "chainId", lambda x: x == RIG_VOUCHER["chainId"], str(RIG_VOUCHER["chainId"]), r, P)
    _need(rig, "contract", lambda x: x == RIG_VOUCHER["contract"], RIG_VOUCHER["contract"] + " (lowercase)", r, P)
    _need(rig, "id", _is_dec, "a decimal string", r, P)


def validate_tap(tap, manifest=None):
    """Validate the PoD-related members of a `tap` metadata object (other members are draft A's business).

    With `manifest` (the collection manifest, a dict), also check the commitments of §4.4."""
    r = Result()
    if not isinstance(tap, dict):
        r.err("tap: must be an object")
        return r
    if "pod" in tap:
        validate_pod(tap["pod"], r)
        pod, src = tap["pod"], tap.get("source")
        if r.ok and src is None:
            r.err("tap.source: REQUIRED when tap.pod is present")
        elif r.ok:
            if src.get("chainId") != CHAIN_ID:
                r.err("tap.source.chainId must be 56 when tap.pod is present")
            if str(src.get("processor", "")).lower() != pod["processor"]:
                r.err("tap.source.processor differs from tap.pod.processor")
            if str(src.get("circuitId")) != pod["circuitId"]:
                r.err("tap.source.circuitId differs from tap.pod.circuitId")
            if isinstance(src.get("block"), int) and src["block"] > pod["block"]:
                r.warn("tap.pod.block is earlier than tap.source.block")
        nl = tap.get("netlist")
        if r.ok and isinstance(nl, dict) and "nand" in nl:
            if (nl.get("nand"), nl.get("latch")) != (pod["design"]["nandBurn"], pod["design"]["latchBurn"]):
                r.warn("tap.netlist nand/latch differ from tap.pod.design nandBurn/latchBurn")
        fc = pod.get("functionCheck") if isinstance(pod, dict) else None
        if r.ok and isinstance(fc, dict) and fc.get("method") == "exhaustive" and isinstance(nl, dict) \
                and isinstance(nl.get("nIn"), int) and fc.get("result") == "match" and fc["vectors"] != 2 ** nl["nIn"]:
            r.err("tap.pod.functionCheck.vectors must be 2^nIn for an exhaustive match")
        if r.ok and manifest is not None:
            _check_manifest(pod, manifest, r)
    if "rig" in tap:
        validate_rig(tap["rig"], r)
    return r


def _check_manifest(pod, manifest, r):
    reveal = manifest.get("reveal") if isinstance(manifest, dict) else None
    seeded = isinstance(reveal, dict) and reveal.get("source") not in (None, "none")
    mp = manifest.get("pod") if isinstance(manifest, dict) else None
    if mp is None:
        if seeded:
            r.err("manifest.pod: REQUIRED when a revealed collection carries tap.pod (snapshot block fixed before the seed)")
        return
    if not validate_manifest_pod(mp, r):
        return
    if pod["block"] < mp["block"]:
        r.err("tap.pod.block is earlier than the block committed in manifest.pod.block")
    elif pod["block"] > mp["block"]:
        r.warn("tap.pod is a refreshed snapshot; traits and rarity derived by the manifest's rule stay those of "
               "manifest.pod.block")
    fc, mfc = pod.get("functionCheck"), mp.get("functionCheck")
    if isinstance(fc, dict) and fc.get("method") == "sampled" and isinstance(mfc, dict):
        if (fc.get("procedure"), fc.get("seed")) != (mfc["procedure"], mfc["seed"]):
            r.err("tap.pod.functionCheck procedure/seed differ from manifest.pod.functionCheck")


def main(argv):
    if argv[:1] == ["--pod"]:
        r = validate_pod(json.load(open(argv[1], encoding="utf-8")))
    elif len(argv) == 1:
        doc = json.load(open(argv[0], encoding="utf-8"))
        r = validate_tap(doc.get("tap") if isinstance(doc, dict) else None)
    else:
        raise SystemExit(__doc__)
    for e in r.errors:
        print("error:", e)
    for w in r.warnings:
        print("warning:", w)
    print("ok" if r.ok else "invalid")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
