"""Reference implementation for the TAP draft "Structural Hash of Flat Netlists".

MIT licence. Pure Python 3.9+, no dependencies besides the reference code of the
"Netlist-Bound NFTs" draft (tapnft.py, tap02_reference.py), imported unchanged from
../tap-draft-netlist-bound-nft.

Specification steps (section numbers of the draft):
  §3  liveness
  §4  structural labels: one-pass labels for nodes with a finite unfolding,
      round-based refinement for nodes that depend on LATCH feedback
  §5  merging: one node per label
  §6  canonical order and the output tail
  §7  canonical file and structuralHash

No set or dict iteration order influences any output: every ordering below is by an
explicit key.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tap-draft-netlist-bound-nft"))

import tap02_reference as tap02  # noqa: E402
import tapnft  # noqa: E402

LABEL_DOMAIN = b"TAPSH1"
TAG_CONST, TAG_INPUT, TAG_NAND, TAG_LATCH, TAG_CYC0, TAG_CYC = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05
HASH_DOMAIN = b"tap-structural-hash/1\x00"
NAND, LATCH = tap02.NAND, tap02.LATCH


def H(*parts: bytes) -> bytes:
    return hashlib.sha256(LABEL_DOMAIN + b"".join(parts)).digest()


def const_label(v: int) -> bytes:
    return H(bytes([TAG_CONST, v]))


def input_label(i: int) -> bytes:
    return H(bytes([TAG_INPUT]), i.to_bytes(4, "big"))


def nand_label(la: bytes, lb: bytes) -> bytes:
    lo, hi = (la, lb) if la <= lb else (lb, la)
    return H(bytes([TAG_NAND]), lo, hi)


def latch_label(ld: bytes) -> bytes:
    return H(bytes([TAG_LATCH]), ld)


CYC0 = H(bytes([TAG_CYC0]))


def cyc_label(ld: bytes) -> bytes:
    return H(bytes([TAG_CYC]), ld)


class TooLarge(ValueError):
    """The netlist exceeds the caller's size bound (TAP-02 §7, requirement 1)."""


@dataclass
class Result:
    canonical: bytes          # the canonical tapnet/1 file
    structural_hash: bytes    # SHA-256(HASH_DOMAIN || canonical)
    live: int                 # live elements of the input file
    nodes: int                # merged nodes (classes)
    cyclic: int               # live elements whose unfolding is infinite
    rounds: int               # refinement rounds computed for the cyclic region (0 if none)
    copies: int               # copy records in the output tail


def canonicalize(data: bytes, max_gates: int | None = None) -> Result:
    if max_gates is not None and (len(data) - tapnft.HEADER_LEN) // 4 > max_gates:
        raise TooLarge(f"more than {max_gates} records possible")   # bound before decoding (records >= 4 bytes)
    m = tapnft.check_file(data)                       # rejects anything tapnet/1 rejects
    n_in, n_out, records = tapnft.decode_file(data)
    if max_gates is not None and m.gates > max_gates:
        raise TooLarge(f"{m.gates} gates > bound {max_gates}")
    els = tap02.decode(records, n_in)
    base = 2 + n_in
    n_el = len(els)
    ins = [e.ins for e in els]                        # signal indices
    ops = [e.op for e in els]

    # §3 liveness: backward reachability from the output elements through every input.
    live = [False] * n_el
    stack = [n_el - n_out + j for j in range(n_out)]
    while stack:
        k = stack.pop()
        if live[k]:
            continue
        live[k] = True
        for s in ins[k]:
            if s >= base and not live[s - base]:
                stack.append(s - base)
    order = [k for k in range(n_el) if live[k]]      # original order: topological for NAND

    # §4.1 finite unfoldings: a node is acyclic iff all its element inputs are acyclic (least fixpoint).
    label: dict[int, bytes] = {}                      # element index -> final label

    def sig_label(s: int) -> bytes:
        if s < 2:
            return const_label(s)
        if s < base:
            return input_label(s - 2)
        return label[s - base]

    pending = {k: sum(1 for s in ins[k] if s >= base) for k in order}
    consumers: dict[int, list[int]] = {k: [] for k in order}
    for k in order:
        for s in ins[k]:
            if s >= base:
                consumers[s - base].append(k)        # once per occurrence
    queue = [k for k in order if pending[k] == 0]
    qi = 0
    while qi < len(queue):
        k = queue[qi]
        qi += 1
        if ops[k] == NAND:
            label[k] = nand_label(sig_label(ins[k][0]), sig_label(ins[k][1]))
        else:
            label[k] = latch_label(sig_label(ins[k][0]))
        for c in consumers[k]:
            pending[c] -= 1
            if pending[c] == 0:
                queue.append(c)
    cyc = [k for k in order if k not in label]       # infinite unfoldings, original order

    # §4.2 refinement of the cyclic region; acyclic labels are fixed leaves.
    rounds = 0
    if cyc:
        cur: dict[int, bytes] = {}

        def eval_round(latch_labels: dict[int, bytes]) -> dict[int, bytes]:
            lab = dict(latch_labels)

            def get(s: int) -> bytes:
                if s >= base and (s - base) in lab:
                    return lab[s - base]
                return sig_label(s)
            for k in cyc:                             # original order: NAND inputs come first
                if ops[k] == NAND:
                    lab[k] = nand_label(get(ins[k][0]), get(ins[k][1]))
            return lab

        cur = eval_round({k: CYC0 for k in cyc if ops[k] == LATCH})
        count = len(set(cur.values()))
        while True:
            rounds += 1

            def prev(s: int, cur=cur) -> bytes:
                if s >= base and (s - base) in cur:
                    return cur[s - base]
                return sig_label(s)
            nxt = eval_round({k: cyc_label(prev(ins[k][0])) for k in cyc if ops[k] == LATCH})
            ncount = len(set(nxt.values()))
            cur = nxt
            if ncount == count:
                break
            count = ncount
        label.update(cur)

    # §5 merging: one node per label; all members of a class have the same structure.
    node: dict[bytes, tuple[int, tuple[bytes, ...]]] = {}
    depth_of: dict[bytes, int] = {}
    depth = {}
    for k in order:
        if ops[k] == NAND:
            la, lb = sig_label(ins[k][0]), sig_label(ins[k][1])
            struct = (NAND, (min(la, lb), max(la, lb)))
            d = 1 + max((depth[s - base] if s >= base and ops[s - base] == NAND else 0) for s in ins[k])
        else:
            struct = (LATCH, (sig_label(ins[k][0]),))
            d = 0
        depth[k] = d
        lk = label[k]
        if lk in node:
            if node[lk] != struct or depth_of[lk] != d:
                raise AssertionError("label collision or unstable partition")  # SHA-256 collision
        else:
            node[lk] = struct
            depth_of[lk] = d

    # §6 output tail.
    outs = [label[n_el - n_out + j] for j in range(n_out)]
    first = {}
    for j, v in enumerate(outs):
        first.setdefault(v, j)
    nand_consumers: dict[bytes, list[bytes]] = {v: [] for v in node}
    for v in sorted(node):
        op, il = node[v]
        if op == NAND:
            for x in il:
                if x in node:
                    nand_consumers[x].append(v)
    slot: dict[bytes, int] = {}
    for j in range(n_out - 1, -1, -1):
        v = outs[j]
        if first[v] == j and all(c in slot and slot[c] > j for c in nand_consumers[v]):
            slot[v] = j
    core = sorted((v for v in node if v not in slot), key=lambda v: (depth_of[v], v))

    sig: dict[bytes, int] = {const_label(0): 0, const_label(1): 1}
    for i in range(n_in):
        sig[input_label(i)] = 2 + i
    for p, v in enumerate(core):
        sig[v] = base + p
    for v, j in slot.items():
        sig[v] = base + len(core) + j

    def record(v: bytes) -> bytes:
        op, il = node[v]
        if op == NAND:
            a, b = sorted(sig[x] for x in il)
            return bytes([NAND]) + a.to_bytes(3, "big") + b.to_bytes(3, "big")
        return bytes([LATCH]) + sig[il[0]].to_bytes(3, "big")

    body = b"".join(record(v) for v in core) + b"".join(record(v) for v in outs)
    canonical = tapnft.encode_file(body, n_in, n_out)
    tapnft.check_file(canonical)
    return Result(canonical, hashlib.sha256(HASH_DOMAIN + canonical).digest(), len(order), len(node),
                  len(cyc), rounds, n_out - len(slot))


def canonical_file(data: bytes) -> bytes:
    return canonicalize(data).canonical


def structural_hash(data: bytes) -> bytes:
    return canonicalize(data).structural_hash


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Structural hash of a tapnet/1 file")
    ap.add_argument("file", help="path to a .tapnet file, or 0x-hex netlist bytes with --n-in/--n-out")
    ap.add_argument("--n-in", type=int)
    ap.add_argument("--n-out", type=int)
    ap.add_argument("--write", help="write the canonical file here")
    a = ap.parse_args()
    if a.file.startswith("0x"):
        raw = tapnft.file_from_chain(bytes.fromhex(a.file[2:]), a.n_in, a.n_out)
    else:
        with open(a.file, "rb") as f:
            raw = f.read()
    r = canonicalize(raw)
    print("netlistHash    ", tapnft.hex32(tapnft.netlist_hash(raw)))
    print("structuralHash ", tapnft.hex32(r.structural_hash))
    print(f"live {r.live}  nodes {r.nodes}  cyclic {r.cyclic}  rounds {r.rounds}  copies {r.copies}")
    print("canonical      ", "0x" + r.canonical.hex())
    if a.write:
        with open(a.write, "wb") as f:
            f.write(r.canonical)
