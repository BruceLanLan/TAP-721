"""Generate vectors.json for the TAP draft "Structural Hash of Flat Netlists".

MIT licence. Deterministic: fixed RNG seed, sorted keys, fixed indentation, no timestamps.
Run from any directory:  python3 make_vectors.py
Also provides the netlist graph helpers and transformations used by test_canon.py.
"""
from __future__ import annotations

import json
import os
import random

import canon
from canon import tap02, tapnft

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261018

# ------------------------------------------------------------------ netlist graphs
# A graph is (n_in, n_out, nodes, outputs): nodes maps an element id (int) to (op, refs),
# refs are ("c", 0|1), ("i", k) or ("e", id); outputs is the list of n_out distinct ids that
# form the last n_out records, in output order. Invariant kept by every transformation:
# no element outside `outputs` refers to an output through a NAND input.


def graph_from_file(data: bytes):
    n_in, n_out, rec = tapnft.decode_file(data)
    els = tap02.decode(rec, n_in)
    base = 2 + n_in

    def ref(s):
        return ("c", s) if s < 2 else ("i", s - 2) if s < base else ("e", s - base)
    nodes = {k: (e.op, [ref(s) for s in e.ins]) for k, e in enumerate(els)}
    return n_in, n_out, nodes, [len(els) - n_out + j for j in range(n_out)]


def file_from_graph(g, order=None) -> bytes:
    """Serialize; `order` lists the non-output ids (default: ascending ids)."""
    n_in, n_out, nodes, outs = g
    if order is None:
        order = sorted(k for k in nodes if k not in set(outs))
    seq = list(order) + list(outs)
    pos = {k: 2 + n_in + p for p, k in enumerate(seq)}

    def sig(r):
        return r[1] if r[0] == "c" else 2 + r[1] if r[0] == "i" else pos[r[1]]
    body = bytearray()
    for k in seq:
        op, refs = nodes[k]
        body.append(op)
        for r in refs:
            body += sig(r).to_bytes(3, "big")
    data = tapnft.encode_file(bytes(body), n_in, n_out)
    tapnft.check_file(data)
    return data


def random_graph(rng: random.Random, max_in=4, max_el=28, p_latch=0.25):
    n_in = rng.randint(0, max_in)
    n_el = rng.randint(1, max_el)
    n_out = rng.randint(1, min(3, n_el))
    nodes = {}
    for k in range(n_el):
        def back():
            s = rng.randrange(2 + n_in + k)
            return ("c", s) if s < 2 else ("i", s - 2) if s < 2 + n_in else ("e", s - 2 - n_in)
        if rng.random() < p_latch:
            s = rng.randrange(2 + n_in + n_el)
            nodes[k] = (tap02.LATCH, [("c", s) if s < 2 else ("i", s - 2) if s < 2 + n_in
                                      else ("e", s - 2 - n_in)])
        else:
            nodes[k] = (tap02.NAND, [back(), back()])
    return n_in, n_out, nodes, [n_el - n_out + j for j in range(n_out)]


def random_order(rng, g):
    """A random record order of the non-output elements that respects NAND references."""
    _, _, nodes, outs = g
    outset = set(outs)
    rest = sorted(k for k in nodes if k not in outset)
    deps = {k: {r[1] for r in nodes[k][1] if r[0] == "e"} if nodes[k][0] == tap02.NAND else set()
            for k in rest}
    placed, order = set(), []
    while len(order) < len(rest):
        ready = [k for k in rest if k not in placed and deps[k] <= placed]
        k = rng.choice(ready)
        placed.add(k)
        order.append(k)
    return order


def t_swap(rng, g):
    n_in, n_out, nodes, outs = g
    new = {k: (op, list(reversed(refs)) if op == tap02.NAND and rng.random() < 0.5 else list(refs))
           for k, (op, refs) in nodes.items()}
    return n_in, n_out, new, outs


def t_dead(rng, g, count=4):
    n_in, n_out, nodes, outs = g
    nodes = dict(nodes)
    outset = set(outs)
    nxt = max(nodes) + 1
    for _ in range(count):
        pool = [("c", 0), ("c", 1)] + [("i", i) for i in range(n_in)]
        inner = pool + [("e", k) for k in sorted(nodes) if k not in outset]
        if rng.random() < 0.35:   # a dead LATCH may refer to anything, itself included
            target = rng.choice(pool + [("e", k) for k in sorted(nodes)] + [("e", nxt)])
            nodes[nxt] = (tap02.LATCH, [target])
        else:
            nodes[nxt] = (tap02.NAND, [rng.choice(inner), rng.choice(inner)])
        nxt += 1
    return n_in, n_out, nodes, outs


def t_dup(rng, g, count=3):
    """Copy elements and move a random subset of their references (LATCH feedback included) to the copy."""
    n_in, n_out, nodes, outs = g
    nodes = {k: (op, list(refs)) for k, (op, refs) in nodes.items()}
    outset = set(outs)
    for _ in range(count):
        cand = [k for k in sorted(nodes)
                if nodes[k][0] == tap02.LATCH or all(r[0] != "e" or r[1] not in outset for r in nodes[k][1])]
        if not cand:
            break
        k = rng.choice(cand)
        nk = max(nodes) + 1
        nodes[nk] = (nodes[k][0], list(nodes[k][1]))
        for j in sorted(nodes):
            op, refs = nodes[j]
            for p, r in enumerate(refs):
                if r == ("e", k) and rng.random() < 0.5:
                    if op == tap02.NAND and j not in outset and k in outset:
                        continue
                    refs[p] = ("e", nk)
    return n_in, n_out, nodes, outs


def transform(rng, g):
    """Apply a random mix of the invariant transformations and serialize in a random order."""
    for step in rng.sample([t_swap, t_dead, t_dup], 3):
        if rng.random() < 0.8:
            g = step(rng, g)
    return file_from_graph(g, random_order(rng, g))


# ------------------------------------------------------------------ fixtures

def F(n_in, n_out, recs):
    """recs: list of ("N", a, b) or ("L", d) with raw signal indices."""
    body = bytearray()
    for r in recs:
        if r[0] == "N":
            body += bytes([0]) + r[1].to_bytes(3, "big") + r[2].to_bytes(3, "big")
        else:
            body += bytes([1]) + r[1].to_bytes(3, "big")
    data = tapnft.encode_file(bytes(body), n_in, n_out)
    tapnft.check_file(data)
    return data


XOR_17851 = bytes.fromhex("00000002000003000000020000040000000300000400000005000006")

FIXTURES = [
    # name, file, note
    ("xor_17851", tapnft.file_from_chain(XOR_17851, 2, 1),
     "BNB Smart Chain circuit #17851 (nIn 2, nOut 1): XOR from 4 NAND"),
    ("xor_17851_reordered", F(2, 1, [("N", 2, 3), ("N", 3, 4), ("N", 2, 4), ("N", 5, 6)]),
     "the two independent middle NAND records exchanged"),
    ("xor_17851_swapped", F(2, 1, [("N", 3, 2), ("N", 4, 2), ("N", 4, 3), ("N", 6, 5)]),
     "every NAND's inputs exchanged"),
    ("xor_17851_dead", F(2, 1, [("L", 5), ("N", 2, 3), ("N", 2, 3), ("N", 2, 5), ("N", 3, 5),
                                ("N", 4, 6), ("N", 7, 8)]),
     "a dead LATCH loop through a dead duplicate NAND, plus a dead NAND"),
    ("xor_17851_duplicated", F(2, 1, [("N", 2, 3), ("N", 3, 2), ("N", 2, 4), ("N", 3, 5), ("N", 6, 7)]),
     "the first NAND duplicated; its two consumers use different copies"),
    ("xor_inputs_exchanged", F(2, 1, [("N", 3, 2), ("N", 3, 4), ("N", 2, 4), ("N", 5, 6)]),
     "inputs 0 and 1 exchanged; XOR is symmetric, so the structure is the same"),
    ("xor_5nand", F(2, 1, [("N", 2, 2), ("N", 3, 3), ("N", 2, 5), ("N", 4, 3), ("N", 6, 7)]),
     "XOR from 5 NAND: same function, different design"),
    ("andnot", F(2, 1, [("N", 3, 3), ("N", 2, 4), ("N", 5, 5)]),
     "a AND NOT b"),
    ("andnot_inputs_exchanged", F(2, 1, [("N", 2, 2), ("N", 3, 4), ("N", 5, 5)]),
     "b AND NOT a: input order is part of the interface"),
    ("not_twice", F(1, 1, [("N", 2, 2), ("N", 3, 3)]),
     "NOT NOT a: double negation is not simplified"),
    ("not_four_times", F(1, 1, [("N", 2, 2), ("N", 3, 3), ("N", 4, 4), ("N", 5, 5)]),
     "NOT NOT NOT NOT a: same function as not_twice, different hash"),
    ("toggle", F(1, 1, [("L", 7), ("N", 2, 3), ("N", 2, 4), ("N", 3, 4), ("N", 5, 6)]),
     "q' = q XOR en; the LATCH refers forward to the output"),
    ("toggle_latch_duplicated", F(1, 1, [("L", 8), ("L", 8), ("N", 2, 3), ("N", 2, 5), ("N", 4, 5),
                                         ("N", 6, 7)]),
     "the LATCH duplicated; the XOR reads one copy on each side"),
    ("two_toggles", F(1, 2, [("L", 11), ("L", 12), ("N", 2, 3), ("N", 2, 5), ("N", 3, 5), ("N", 2, 4),
                             ("N", 2, 8), ("N", 4, 8), ("N", 6, 7), ("N", 9, 10)]),
     "two identical toggles on the same input as two outputs: they merge, and the tail gets a copy record"),
    ("output_feeds_output", F(2, 2, [("N", 2, 3), ("N", 4, 2)]),
     "output 1 reads output 0; both stay in the tail"),
    ("output_feeds_earlier_output", F(2, 2, [("N", 2, 3), ("L", 4), ("N", 4, 3)]),
     "output 0 is a LATCH of the element output 1 also reads: no copy needed"),
    ("const_ring_1", F(1, 1, [("L", 3), ("N", 3, 2)]),
     "a LATCH holding itself (always 0) feeding a NAND"),
    ("const_ring_2", F(1, 1, [("L", 4), ("L", 3), ("N", 3, 2)]),
     "a two-LATCH ring (always 0) feeding a NAND: bisimilar to const_ring_1, same hash"),
    ("oscillator_nin0", F(0, 1, [("L", 3), ("N", 2, 2)]),
     "nIn = 0: q' = NOT q"),
    ("shift4", F(1, 1, [("L", 4), ("L", 5), ("L", 6), ("L", 2), ("N", 3, 3), ("N", 7, 7)]),
     "4-stage shift register (records in reverse), buffered by two NOTs"),
    ("lfsr4", F(0, 1, [("L", 3), ("L", 4), ("L", 5), ("L", 12),
                       ("N", 2, 3), ("N", 2, 6), ("N", 3, 6), ("N", 7, 8),
                       ("N", 9, 9), ("N", 10, 10), ("N", 11, 11), ("N", 5, 5)]),
     "4-bit ring with an XOR tap: every LATCH is in the cyclic region"),
]

EQUAL_GROUPS = [
    ["xor_17851", "xor_17851_reordered", "xor_17851_swapped", "xor_17851_dead", "xor_17851_duplicated",
     "xor_inputs_exchanged"],
    ["toggle", "toggle_latch_duplicated"],
    ["const_ring_1", "const_ring_2"],
]
DISTINCT = [
    ["xor_17851", "xor_5nand"],
    ["andnot", "andnot_inputs_exchanged"],
    ["not_twice", "not_four_times"],
]

INVALID = [
    ("ref_record", tapnft._encode_unchecked(bytes([2]) + bytes(20) + (1).to_bytes(8, "big") + bytes([0, 1]), 0, 1),
     "REF is not allowed in tapnet/1"),
    ("bad_magic", b"TAPNEX\x01\x00" + (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes(7),
     "header"),
    ("no_records", tapnft._encode_unchecked(b"", 1, 1), "at least one record"),
    ("nand_forward", tapnft._encode_unchecked(bytes([0, 0, 0, 3, 0, 0, 3]), 1, 1), "NAND forward reference"),
]


def case(name, data, note):
    r = canon.canonicalize(data)
    n_in, n_out, _ = tapnft.decode_file(data)
    return {"name": name, "note": note, "nIn": n_in, "nOut": n_out, "file": "0x" + data.hex(),
            "netlistHash": tapnft.hex32(tapnft.netlist_hash(data)),
            "canonical": "0x" + r.canonical.hex(), "structuralHash": tapnft.hex32(r.structural_hash),
            "live": r.live, "nodes": r.nodes, "cyclic": r.cyclic, "rounds": r.rounds, "copies": r.copies}


def build():
    rng = random.Random(SEED)
    cases = [case(n, d, note) for n, d, note in FIXTURES]
    groups = [{"members": g} for g in EQUAL_GROUPS]
    for i in range(4):
        g = random_graph(rng)
        base = file_from_graph(g)
        names = [f"random{i}"]
        cases.append(case(names[0], base, f"random netlist (seed {SEED}, #{i})"))
        for v in range(3):
            names.append(f"random{i}_variant{v}")
            cases.append(case(names[-1], transform(rng, g), f"random{i} after renumbering, input swaps,"
                              " dead elements and duplication"))
        groups.append({"members": names})
    by = {c["name"]: c for c in cases}
    for gr in groups:
        hs = {by[m]["structuralHash"] for m in gr["members"]}
        assert len(hs) == 1, gr
        gr["structuralHash"] = hs.pop()
    for a, b in DISTINCT:
        assert by[a]["structuralHash"] != by[b]["structuralHash"], (a, b)
    pinned = os.path.join(HERE, "chain-circuits.json")
    chain = chain_cases(pinned) if os.path.exists(pinned) else []
    return {
        "format": "tap-structural-hash-vectors/1",
        "labelDomain": canon.LABEL_DOMAIN.decode(),
        "hashDomain": "0x" + canon.HASH_DOMAIN.hex(),
        "cases": cases,
        "equalGroups": groups,
        "distinct": [{"members": d} for d in DISTINCT],
        "invalid": [{"name": n, "file": "0x" + d.hex(), "note": note} for n, d, note in INVALID],
        "chainSnapshot": chain,
    }


def chain_cases(path):
    """Structural hashes of the REF-free circuits pinned in chain-circuits.json (REF circuits are skipped)."""
    with open(path) as f:
        snap = json.load(f)
    out = []
    items = snap if isinstance(snap, list) else snap.get("circuits", [])
    for it in items:
        try:
            nl, n_in, n_out = it["netlist"], int(it["nIn"]), int(it["nOut"])
            data = tapnft.file_from_chain(bytes.fromhex(nl[2:] if nl.startswith("0x") else nl), n_in, n_out)
        except (KeyError, TypeError, ValueError, tapnft.Invalid):
            continue
        r = canon.canonicalize(data)
        src = {k: snap[k] for k in ("chainId", "block") if isinstance(snap, dict) and k in snap}
        src.update({k: it[k] for k in ("chainId", "block", "processor", "circuitId") if k in it})
        m = tapnft.check_file(data)
        out.append({"source": src, "nIn": n_in, "nOut": n_out, "nand": m.nand, "latch": m.latch,
                    "file": "0x" + data.hex(), "netlistHash": tapnft.hex32(tapnft.netlist_hash(data)),
                    "canonical": "0x" + r.canonical.hex(), "structuralHash": tapnft.hex32(r.structural_hash),
                    "live": r.live, "nodes": r.nodes, "cyclic": r.cyclic, "rounds": r.rounds,
                    "copies": r.copies})
    out.sort(key=lambda c: (c["netlistHash"], json.dumps(c["source"], sort_keys=True)))
    return out


def import_snapshot(path):
    """Pin the circuits of a chain snapshot (read-only eth_call results) into chain-circuits.json."""
    with open(path) as f:
        snap = json.load(f)
    keep = ("processor", "circuitId", "nIn", "nOut", "nState", "gateCount", "netlist")
    doc = {"chainId": snap["chainId"], "block": snap["block"],
           "note": "Pinned subset of ../tap-draft-netlist-bound-nft/chain-snapshot.json: read-only eth_call results; no transaction was sent.",
           "circuits": [{k: c[k] for k in keep if k in c} for c in snap["circuits"]]}
    with open(os.path.join(HERE, "chain-circuits.json"), "w", newline="\n") as f:
        f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main():
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--import":
        import_snapshot(sys.argv[2])
    doc = build()
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    path = os.path.join(HERE, "vectors.json")
    with open(path, "w", newline="\n") as f:
        f.write(text)
    print(path, tapnft.hex32(tapnft.sha256(text.encode())))


if __name__ == "__main__":
    main()
