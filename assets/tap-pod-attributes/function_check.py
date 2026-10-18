#!/usr/bin/env python3
"""Functional check of a netlist against its task's reference circuit (procedure `tap-pod-fc/1`).

Specification §3.9 of the PoD-attributes draft. `verified` in a PoD snapshot only says the mining
contract's sampled vectors passed; this module checks the function independently.

  * Both circuits combinational (no LATCH) and nIn <= 16: every one of the 2^nIn input patterns
    (method "exhaustive"). Input j of pattern i is bit j of i.
  * Otherwise (method "sampled"):
      - combinational: 16,384 patterns; bit j of pattern k is bit (j mod 8) of byte (j div 8) of the
        stream SHA-256(seed || u32be(k) || u32be(0)) || SHA-256(seed || u32be(k) || u32be(1)) || ...
      - sequential: 64 runs (1 run when nIn = 0); each run starts both circuits from the all-zero state and applies
        max(cycles, 32) beats; the inputs of beat t of run r come from the stream
        SHA-256(seed || u32be(r) || u32be(t) || u32be(0)) || ...; outputs are compared at every beat.
    `vectors` is the number of patterns (combinational) or beats (sequential) compared.
  * A reference that cannot be evaluated (for example it contains REF records and no resolver is
    available) gives method "unconfirmed" with no result.

Evaluation follows TAP-02 §4 via the TAP-02 reference implementation. No network.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tap-netlist-bound-nft"))
import tap02_reference as tap02  # noqa: E402

PROCEDURE = "tap-pod-fc/1"
DEFAULT_SEED = "0x" + hashlib.sha256(b"TAP-pod functionCheck v1").hexdigest()
EXHAUSTIVE_MAX_NIN = 16
SAMPLED_COMBINATIONAL = 16384
SEQ_RUNS = 64
SEQ_MIN_BEATS = 32


def _bits(seed: bytes, idx: tuple, n: int) -> list:
    out, chunk = [], 0
    while len(out) < n:
        h = hashlib.sha256(seed + b"".join(i.to_bytes(4, "big") for i in idx) + chunk.to_bytes(4, "big")).digest()
        for byte in h:
            for b in range(8):
                out.append((byte >> b) & 1)
        chunk += 1
    return out[:n]


def _load(netlist: bytes, n_in: int, n_out: int):
    return tap02.load(netlist, n_in, n_out)


def check(candidate: bytes, c_in: int, c_out: int, reference: bytes, r_in: int, r_out: int,
          cycles: int = 1, seed_hex: str = DEFAULT_SEED, ref_id: dict = None) -> dict:
    res = {"procedure": PROCEDURE}
    if ref_id:
        res["reference"] = ref_id
    try:
        ref = _load(reference, r_in, r_out)
    except tap02.IllFormed:
        res.update(method="unconfirmed", vectors=0)
        return res
    cand = _load(candidate, c_in, c_out)
    if (c_in, c_out) != (r_in, r_out):
        res.update(method="exhaustive" if cand.n_state == 0 and ref.n_state == 0 and c_in <= EXHAUSTIVE_MAX_NIN
                   else "sampled", vectors=0, result="mismatch")
        if res["method"] == "sampled":
            res["seed"] = seed_hex
        return res
    if cand.n_state == 0 and ref.n_state == 0 and c_in <= EXHAUSTIVE_MAX_NIN:
        n = 1 << c_in
        for i in range(n):
            x = [(i >> j) & 1 for j in range(c_in)]
            if tap02.beat(cand, [], x)[1] != tap02.beat(ref, [], x)[1]:
                res.update(method="exhaustive", vectors=i + 1, result="mismatch")
                return res
        res.update(method="exhaustive", vectors=n, result="match")
        return res
    seed = bytes.fromhex(seed_hex[2:])
    res.update(method="sampled", seed=seed_hex)
    count = 0
    if cand.n_state == 0 and ref.n_state == 0:
        for k in range(SAMPLED_COMBINATIONAL):
            x = _bits(seed, (k,), c_in)
            count += 1
            if tap02.beat(cand, [], x)[1] != tap02.beat(ref, [], x)[1]:
                res.update(vectors=count, result="mismatch")
                return res
        res.update(vectors=count, result="match")
        return res
    beats = max(cycles, SEQ_MIN_BEATS)
    for r in range(SEQ_RUNS if c_in else 1):
        sc, sr = [0] * cand.n_state, [0] * ref.n_state
        for t in range(beats):
            x = _bits(seed, (r, t), c_in)
            sc, oc = tap02.beat(cand, sc, x)
            sr, orf = tap02.beat(ref, sr, x)
            count += 1
            if oc != orf:
                res.update(vectors=count, result="mismatch")
                return res
    res.update(vectors=count, result="match")
    return res
