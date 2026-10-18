"""Generate test/fixtures/core-vectors.json from the Python reference (tapnft.py).

MIT licence. Run from anywhere:  python3 contracts/test/fixtures/make_core_fixtures.py
The Solidity tests in test/core/CoreVectors.t.sol assert bit-identical results.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "assets", "tap-netlist-bound-nft"))

import tap02_reference as tap02  # noqa: E402
import tapnft as T  # noqa: E402

h = T.hex32
sha = T.sha256


def nand(a, b):
    return b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big")


def latch(d):
    return b"\x01" + d.to_bytes(3, "big")


def chain_file(n_nand, n_latch, n_in=2, n_out=1):
    """n_nand NANDs, each fed by the two previous signals, then n_latch LATCHes on the last signal."""
    recs = bytearray()
    nxt = 2 + n_in
    for _ in range(n_nand):
        recs += nand(nxt - 1, nxt - 2)
        nxt += 1
    total = nxt + n_latch
    for _ in range(n_latch):
        recs += latch(total - 1)
    return T.encode_file(bytes(recs), n_in, n_out)


def file_entry(name, data):
    m = T.check_file(data)
    return {"name": name, "file": "0x" + data.hex(), "sha256": h(T.netlist_hash(data)), "bytes": len(data),
            "nIn": m.n_in, "nOut": m.n_out, "nand": m.nand, "latch": m.latch}


def main():
    out = {}

    # ---- permute
    seeds = [sha(b"tap-core-vectors"), sha(b"tap-core-vectors-2")]
    perm = []
    for s in seeds:
        for n in [1, 2, 3, 7, 10, 255, 256, 257, 1000, 10000]:
            idx = sorted({i for i in [0, 1, 2, 3, n // 2, (n * 7) // 13, n - 2, n - 1] if 0 <= i < n})
            perm.append({"seed": h(s), "n": n, "indices": idx, "outputs": [T.permute(s, n, i) for i in idx]})
    out["permute"] = perm

    # ---- pool seed
    ms = sha(b"tap-core-master")
    ps = []
    for chain, coll, label in [
        (196, "0x0e91460d6823c711643e650a9a4c0cc21de41614", "IMAGE_V1"),
        (196, "0x0e91460d6823c711643e650a9a4c0cc21de41614", "NETLIST_V1"),
        (56, "0x48d43345656f0f9510dc3c06cba99dff597617c2", "网表"),
        (8453, "0x0000000000000000000000000000000000000001", ""),
    ]:
        ps.append({"masterSeed": h(ms), "chainId": chain, "collection": coll, "label": label,
                   "seed": h(T.pool_seed(ms, chain, coll, label))})
    out["poolSeed"] = ps

    # ---- leaf hash
    lh = []
    for i, vals in [(0, [sha(b"a")]), (9999, [sha(b"img"), sha(b"net")]), (2**32 - 1, [b"\x00" * 32])]:
        lh.append({"index": i, "values": [h(v) for v in vals], "leaf": h(T.leaf_hash(i, vals))})
    out["leafHash"] = lh

    # ---- Merkle
    mk = []
    for size in [1, 2, 3, 5, 7, 8, 13, 100]:
        leaves = [T.leaf_hash(i, [sha(b"v" + i.to_bytes(4, "big"))]) for i in range(size)]
        root = T.merkle_root(leaves)
        idx = list(range(size)) if size <= 13 else [0, 1, 50, 96, 97, 98, 99]
        proofs = [T.merkle_proof(leaves, i) for i in idx]
        for i, p in zip(idx, proofs):
            assert T.merkle_verify(root, size, i, leaves[i], p)
        mk.append({"size": size, "root": h(root), "leaves": [h(x) for x in leaves], "indices": idx,
                   "proofs": [[h(x) for x in p] for p in proofs]})
    out["merkle"] = mk

    # ---- tapnet files
    xor_records = bytes.fromhex("00000002000003000000020000040000000300000400000005000006")  # BSC circuit #17851
    xor_file = T.file_from_chain(xor_records, 2, 1)
    # T flip-flop: q' = t xor q; output = t xor q
    tff = T.encode_file(latch(7) + nand(2, 3) + nand(2, 4) + nand(3, 4) + nand(5, 6), 1, 1)
    files = [
        file_entry("xor-17851", xor_file),
        file_entry("tff-latch", tff),
        file_entry("gas-1204", chain_file(1204, 0)),
        file_entry("gas-24000", chain_file(3424, 4)),
        file_entry("chunked-60000", chain_file(8568, 2)),
    ]
    assert files[2]["bytes"] == 8444 and files[3]["bytes"] == 24000 and files[4]["bytes"] == 60000
    out["files"] = files

    invalid = {
        "short-header": b"TAPNET\x01\x00\x00\x00",
        "bad-magic": b"TAPNEX\x01\x00" + xor_file[8:],
        "bad-version": b"TAPNET\x02\x00" + xor_file[8:],
        "reserved-nonzero": b"TAPNET\x01\x01" + xor_file[8:],
        "no-records": xor_file[:16],
        "nout-zero": T._encode_unchecked(xor_records, 2, 0),
        "nout-too-large": T._encode_unchecked(xor_records, 2, 5),
        "nin-too-large": T._encode_unchecked(xor_records, 65537, 1),
        "nout-over-pins": T._encode_unchecked(xor_records, 2, 65537),
        "truncated-nand": xor_file[:-1],
        "truncated-latch": T._encode_unchecked(nand(2, 3) + b"\x01\x00\x00", 2, 1),
        "ref-record": T._encode_unchecked(nand(2, 3) + b"\x02" + b"\x11" * 20 + (5).to_bytes(8, "big") + b"\x01\x01"
                                    + (4).to_bytes(3, "big"), 2, 1),
        "unknown-opcode": T._encode_unchecked(nand(2, 3) + b"\x03\x00\x00\x00", 2, 1),
        "nand-self-reference": T._encode_unchecked(nand(2, 4), 2, 1),
        "nand-forward-reference": T._encode_unchecked(nand(2, 3) + nand(6, 2) + nand(4, 5), 2, 1),
        "latch-out-of-range": T._encode_unchecked(latch(5) + nand(2, 3), 1, 1),
    }
    inv = []
    for name, data in invalid.items():
        try:
            T.check_file(data)
        except T.Invalid:
            inv.append({"name": name, "file": "0x" + data.hex()})
            continue
        raise AssertionError(f"{name} unexpectedly valid")
    # boundary cases that ARE valid
    edge_valid = [file_entry("latch-max-signal", T.encode_file(latch(4) + nand(2, 3), 1, 1)),
                  file_entry("nin-65536", T.encode_file(nand(0, 1), 65536, 1)),
                  file_entry("const-only", T.encode_file(nand(1, 1), 0, 1))]
    out["invalidFiles"] = inv
    out["edgeFiles"] = edge_valid

    # ---- end-to-end collection (two pools: image, netlist)
    chain_id, coll, first, supply = 31337, "0x7a90000000000000000000000000000000000001", 1, 10
    net_values = [T.netlist_hash(xor_file), T.netlist_hash(tff), T.netlist_hash(xor_file),
                  sha(b"n3"), T.netlist_hash(xor_file), T.netlist_hash(tff),
                  sha(b"n6"), sha(b"n7"), sha(b"n8"), sha(b"n9")]
    img_values = [sha(b"image" + bytes([i])) for i in range(supply)]
    pools = [("IMAGE_V1", 1, [[v] for v in img_values]), ("NETLIST_V1", 2, [[v] for v in net_values])]
    master = sha(b"tap-core-e2e")
    manifest = {
        "tapManifest": 1,
        "collection": {"chainId": chain_id, "address": coll, "firstTokenId": first, "supply": supply},
        "reveal": {"source": "none"},
        "pools": [],
    }
    e2e_pools, tokens = [], []
    trees = []
    for label, mask, entries in pools:
        leaves = [T.leaf_hash(i, vals) for i, vals in enumerate(entries)]
        root = T.merkle_root(leaves)
        trees.append((label, leaves, root, entries))
        e2e_pools.append({"label": label, "fields": mask, "root": h(root)})
        field = "image" if mask == 1 else "netlist"
        manifest["pools"].append({"label": label, "fields": [field], "root": h(root),
                                  "entries": [{field: h(v[0])} for v in entries]})
    manifest_bytes = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    for t in range(first, first + supply):
        x = t - first
        per = []
        for label, leaves, root, entries in trees:
            k = T.permute(T.pool_seed(master, chain_id, coll, label), supply, x)
            p = T.merkle_proof(leaves, k)
            assert T.merkle_verify(root, supply, k, leaves[k], p)
            per.append({"entryIndex": k, "values": [h(v) for v in entries[k]], "proof": [h(v) for v in p]})
        tokens.append({"tokenId": t, "pools": per})
    out["e2e"] = {"chainId": chain_id, "collection": coll, "firstTokenId": first, "supply": supply,
                  "masterSeed": h(master), "manifestHash": h(sha(manifest_bytes)), "pools": e2e_pools,
                  "poolSeeds": [h(T.pool_seed(master, chain_id, coll, lab)) for lab, *_ in trees],
                  "tokens": tokens}

    # ---- evaluation (TAP-02 §4 beat, §5 packing) of the real files in vectors.json "tapnet"
    with open(os.path.join(HERE, "..", "..", "..", "assets", "tap-netlist-bound-nft", "vectors.json")) as f:
        real = {e["source"]["circuitId"]: bytes.fromhex(e["file"][2:]) for e in json.load(f)["tapnet"] if e["valid"]}

    def beat(data, state_bytes, in_bytes):
        n_in, n_out, recs = T.decode_file(data)
        c = tap02.load(recs, n_in, n_out)
        ns, outs = tap02.beat(c, tap02.unpack(state_bytes, c.n_state), tap02.unpack(in_bytes, n_in))
        return tap02.pack(ns), tap02.pack(outs)

    ev = []
    for cid, n_inputs in [("17851", 4), ("3151", 256)]:
        data = real[cid]
        ins = [bytes([i]) for i in range(n_inputs)]
        ev.append({"circuitId": cid, "file": "0x" + data.hex(), "sha256": h(sha(data)),
                   "inputs": ["0x" + i.hex() for i in ins],
                   "outputs": ["0x" + beat(data, b"", i)[1].hex() for i in ins]})
    data = real["17852"]
    st, states, outs = b"", [], []
    for _ in range(20):
        st, o = beat(data, st, b"")
        states.append("0x" + st.hex())
        outs.append("0x" + o.hex())
    out["eval"] = ev
    out["johnson"] = {"circuitId": "17852", "file": "0x" + data.hex(), "sha256": h(sha(data)),
                      "states": states, "outputs": outs}

    # ---- explicit token set: ids 1..10000 minus 3,000 fixed-RNG exclusions (TapeCode-Test1 shape)
    rng = random.Random(20261018)
    excluded = set(rng.sample(range(1, 10001), 3000))
    ids = [t for t in range(1, 10001) if t not in excluded]
    assert len(ids) == 7000
    set_file = b"".join(t.to_bytes(4, "big") for t in ids)  # token set file (draft A §5.4)
    set_hash = sha(set_file)
    ts_master = sha(b"tap-core-tokenset")
    ts_coll = "0x7a90000000000000000000000000000000000002"
    ts_seed = T.pool_seed(ts_master, 31337, ts_coll, "NETLIST_V1")
    pick = sorted(set([0, 1, 2, 3, 3499, 3500, 6998, 6999] + rng.sample(range(7000), 92)))
    token_set = {
        "chainId": 31337, "collection": ts_coll, "label": "NETLIST_V1", "masterSeed": h(ts_master),
        "poolSeed": h(ts_seed), "ids": ids, "tokenSetFile": "0x" + set_file.hex(), "tokenSetHash": h(set_hash),
        "sampleTokenIds": [ids[r] for r in pick], "sampleRanks": pick,
        "sampleEntries": [T.permute(ts_seed, 7000, r) for r in pick],
        "excludedSample": sorted(rng.sample(sorted(excluded), 20)) + [0, 10001],
    }
    with open(os.path.join(HERE, "core-tokenset.json"), "w") as f:
        json.dump({"tokenSet": token_set}, f, indent=1)
        f.write("\n")

    path = os.path.join(HERE, "core-vectors.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
