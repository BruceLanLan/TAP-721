"""Generate vectors.json and example/ from tapnft.py. Deterministic; rerun to reproduce byte for byte.

    python3 make_vectors.py                          # regenerate vectors.json and example/
    python3 make_vectors.py --import chain-snapshot.json
                                                     # first refresh chain-circuits.json from a snapshot

The on-chain input is the pinned file chain-circuits.json (a subset of chain-snapshot.json, read
from BNB Smart Chain with read-only calls). Everything else is constructed here. Every value in
vectors.json is computed with tapnft.py; nothing is hard-coded except inputs and the expected error
texts, which are asserted against what tapnft.py raises.

Python 3.9+, no dependencies besides tapnft.py and tap02_reference.py.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path

import tapnft as T

HERE = Path(__file__).resolve().parent
CHAIN_FILE = HERE / "chain-circuits.json"
EXAMPLE_DIR = "example"


def dumps(obj) -> str:
    """The one serializer for vectors.json, the example manifest and token metadata."""
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def h(b: bytes) -> str:
    return T.hex32(b)


def u32s(xs) -> bytes:
    return b"".join(x.to_bytes(4, "big") for x in xs)


def text_sha(s: str) -> bytes:
    return T.sha256(s.encode())


# ---------------------------------------------------------------- chain input

def import_snapshot(path: Path) -> None:
    snap = json.loads(path.read_text(encoding="utf-8"))
    keep = ("processor", "processorNumber", "processorName", "circuitId", "nIn", "nOut", "nState", "gateCount", "netlist")
    out = {"note": "Pinned subset of chain-snapshot.json: read-only eth_call results on BNB Smart Chain at `block`; "
                   "no transaction was sent.",
           "chainId": snap["chainId"], "block": snap["block"], "nodes": snap.get("nodes", []),
           "circuits": [{k: c[k] for k in keep} for c in snap["circuits"]]}
    CHAIN_FILE.write_text(dumps(out))
    print("wrote", CHAIN_FILE.name, "from", path, "block", snap["block"])


def load_chain() -> dict:
    return json.loads(CHAIN_FILE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- a. tapnet files from mainnet circuits

def section_tapnet(chain: dict) -> list:
    out = []
    for c in chain["circuits"]:
        raw = bytes.fromhex(c["netlist"][2:])
        data = T._encode_unchecked(raw, c["nIn"], c["nOut"])
        area = None  # BNB Smart Chain has no area code (TAP-10 §2.1)
        v = {
            "source": {"chainId": chain["chainId"], "processor": c["processor"].lower(),
                       "processorNumber": c["processorNumber"], "processorName": c["processorName"],
                       "circuitId": str(c["circuitId"]), "name": T.tape_name(c["circuitId"], c["processorNumber"], area),
                       "block": chain["block"]},
            "circuitInfo": {"nIn": c["nIn"], "nOut": c["nOut"], "nState": c["nState"], "gateCount": c["gateCount"]},
            "file": "0x" + data.hex(),
            "netlistHash": h(T.netlist_hash(data)),
        }
        try:
            mt = T.check_file(data)
        except T.Invalid as e:
            v.update(valid=False, reason=str(e), metrics=None)
        else:
            assert T.file_from_chain(raw, c["nIn"], c["nOut"]) == data
            assert len(data) == T.HEADER_LEN + 7 * mt.nand + 4 * mt.latch
            # cross-check against circuitInfo (REF-free circuit: gateCount = NAND + LATCH, nState = LATCH)
            assert mt.gates == c["gateCount"] and mt.latch == c["nState"], c["circuitId"]
            v.update(valid=True, reason=None,
                     metrics=dict(mt.as_json(), gates=mt.gates, bytes=len(data)))
        out.append(v)
    return out


# ---------------------------------------------------------------- b. invalid files

def nand(a, b):
    return b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big")


def latch(d):
    return b"\x01" + d.to_bytes(3, "big")


REF_CPU = bytes.fromhex("00000000000000000000000000000000000000aa")


def ref(cid, ins, n_out):
    return b"\x02" + REF_CPU + cid.to_bytes(8, "big") + bytes([len(ins), n_out]) + b"".join(s.to_bytes(3, "big") for s in ins)


def hdr(n_in, n_out, magic=T.MAGIC, version=1, reserved=0):
    return magic + bytes([version, reserved]) + n_in.to_bytes(4, "big") + n_out.to_bytes(4, "big")


INVALID_FILES = [
    # (name, rule, file bytes, expected exception text)
    ("short_header", "file shorter than the 16-byte header", hdr(2, 1)[:10],
     "file shorter than the 16-byte header"),
    ("bad_magic", "bytes 0..5 must be ASCII TAPNET", hdr(2, 1, magic=b"TAPNEX") + nand(2, 3), "bad magic"),
    ("version_2", "version byte must be 0x01", hdr(2, 1, version=2) + nand(2, 3), "unsupported version 2"),
    ("reserved_byte_1", "reserved byte must be 0x00", hdr(2, 1, reserved=1) + nand(2, 3), "reserved byte is not zero"),
    ("no_records", "at least one record", hdr(2, 1), "no records"),
    ("unknown_opcode", "opcode must be 0x00 (NAND) or 0x01 (LATCH)", hdr(2, 1) + b"\x03" + (2).to_bytes(3, "big") + (3).to_bytes(3, "big"),
     "TAP-02: unknown opcode 0x03 at byte 0"),
    ("truncated_record", "every record complete", hdr(2, 1) + nand(2, 3)[:5], "TAP-02: truncated record at byte 4"),
    ("ref_record", "REF (0x02) must be rejected even when well-formed", hdr(1, 1) + ref(1, [2], 1),
     "REF record (opcode 0x02) is not allowed in tapnet/1"),
    ("nand_future_signal", "NAND inputs must be produced earlier", hdr(2, 1) + nand(2, 5) + nand(2, 3),
     "TAP-02: signal 5 referenced by element at 4 is not available"),
    ("latch_d_out_of_range", "LATCH d must be < number of signals", hdr(1, 1) + latch(9),
     "TAP-02: signal 9 referenced by element at 3 is not available"),
    ("too_few_signals_for_outputs", "nOut <= number of element outputs", hdr(2, 2) + nand(2, 3),
     "TAP-02: too few signals for outputs"),
    ("nOut_zero", "1 <= nOut <= 65536", hdr(2, 0) + nand(2, 3), "TAP-02: nIn/nOut out of range"),
    ("nIn_too_large", "nIn <= 65536", hdr(65537, 1) + nand(2, 3), "TAP-02: nIn/nOut out of range"),
]


def section_invalid_files() -> list:
    out = []
    for name, rule, data, expect in INVALID_FILES:
        try:
            T.check_file(data)
        except T.Invalid as e:
            assert str(e) == expect, (name, str(e))
        else:
            raise SystemExit(f"{name} was accepted")
        out.append({"name": name, "rule": rule, "file": "0x" + data.hex(), "error": expect})
    return out


# ---------------------------------------------------------------- c. Merkle

MERKLE_SIZES = [1, 2, 3, 5, 8]


def pool_values(size: int, fields: list) -> list:
    return [[text_sha(f"{f} {i}") for f in fields] for i in range(size)]


def merkle_pool(size: int, fields: list) -> dict:
    vals = pool_values(size, fields)
    leaves = [T.leaf_hash(i, v) for i, v in enumerate(vals)]
    root = T.merkle_root(leaves)
    proofs = []
    for i in range(size):
        p = T.merkle_proof(leaves, i)
        assert T.merkle_verify(root, size, i, leaves[i], p)
        proofs.append([h(x) for x in p])
    return {"size": size, "fields": fields, "fieldsMask": T.fields_mask(fields),
            "values": [[h(x) for x in v] for v in vals], "leaves": [h(x) for x in leaves],
            "root": h(root), "proofs": proofs}


def section_merkle() -> dict:
    pools = []
    for fields in (["image"], ["image", "netlist"]):
        for n in MERKLE_SIZES:
            pools.append(merkle_pool(n, fields))
    # negatives on the size-5 single-field pool
    vals = pool_values(5, ["image"])
    leaves = [T.leaf_hash(i, v) for i, v in enumerate(vals)]
    root = T.merkle_root(leaves)
    p1, p4 = T.merkle_proof(leaves, 1), T.merkle_proof(leaves, 4)
    tampered = T.leaf_hash(2, [text_sha("image 2 (tampered)")])
    neg = [
        ("wrong_index", "proof and leaf of index 1 presented as index 2", 2, leaves[1], p1),
        ("extra_sibling", "index 4 has a one-element proof; an extra trailing sibling must fail", 4, leaves[4], p4 + [leaves[0]]),
        ("tampered_leaf", "leaf of index 2 built from a different value", 2, tampered, T.merkle_proof(leaves, 2)),
        ("index_out_of_range", "index = size", 5, leaves[4], p4),
    ]
    negatives = []
    for name, note, idx, leaf, proof in neg:
        assert not T.merkle_verify(root, 5, idx, leaf, proof), name
        negatives.append({"name": name, "note": note, "root": h(root), "size": 5, "index": idx, "leaf": h(leaf),
                          "proof": [h(x) for x in proof], "valid": False})
    errors = []
    for name, fn, expect in [
        ("proof_index_equals_size", lambda: T.merkle_proof(leaves, 5), "index out of range"),
        ("proof_index_negative", lambda: T.merkle_proof(leaves, -1), "index out of range"),
        ("root_of_empty_pool", lambda: T.merkle_root([]), "empty pool"),
        ("leaf_value_31_bytes", lambda: T.leaf_hash(0, [bytes(31)]), "leaf values must be 32 bytes each"),
    ]:
        errors.append({"name": name, "error": expect_error(fn, expect, name)})
    return {"valueDerivation": "value of field f at index i = SHA-256(UTF-8(f + ' ' + decimal(i)))",
            "pools": pools, "negatives": negatives, "errors": errors}


def expect_error(fn, expect: str, name: str) -> str:
    try:
        fn()
    except T.Invalid as e:
        assert str(e) == expect, (name, str(e))
        return expect
    raise SystemExit(f"{name} was accepted")


# ---------------------------------------------------------------- d. permutation

COLLECTION = "0x00000000000000000000000000000000000000aa"
MASTER_SEED = bytes(range(32))  # fixed example value 0x000102…1f, NOT a real randomness beacon output
PERM_SIZES = [1, 2, 3, 7, 10, 255, 256, 257, 1000]
BIG_N = 10000


def is_bijection(seed: bytes, n: int) -> tuple:
    ys = [T.permute(seed, n, x) for x in range(n)]
    return ys, sorted(ys) == list(range(n))


def walk(seed: bytes, n: int, x: int) -> list:
    """The cycle-walking path: E(x), E(E(x)), … until a value < n (for Solidity debugging)."""
    half = T._half_bits(n)
    path = [T._feistel(seed, x, half)]
    while path[-1] >= n:
        path.append(T._feistel(seed, path[-1], half))
    assert path[-1] == T.permute(seed, n, x)
    return path


def section_permutation() -> dict:
    seeds = []
    for ms_name, ms in [("zero", bytes(32)), ("bytes 0x00..0x1f", MASTER_SEED), ("all 0xff", b"\xff" * 32)]:
        for chain_id, label in [(196, "IMAGE_V1"), (196, "NETLIST_V1"), (8453, "NETLIST_V1"), (196, "网表_V1")]:
            seeds.append({"masterSeed": h(ms), "masterSeedName": ms_name, "chainId": chain_id, "collection": COLLECTION,
                          "label": label, "labelUtf8": "0x" + label.encode().hex(),
                          "poolSeed": h(T.pool_seed(ms, chain_id, COLLECTION, label))})
    seed = T.pool_seed(MASTER_SEED, 196, COLLECTION, "NETLIST_V1")
    perms = []
    for n in PERM_SIZES:
        ys, ok = is_bijection(seed, n)
        assert ok, n
        b = max(1, (n - 1).bit_length())
        perms.append({"n": n, "bits": b, "half": T._half_bits(n), "output": ys, "bijective": ok})
    ys, ok = is_bijection(seed, BIG_N)
    assert ok
    big = {"n": BIG_N, "bits": max(1, (BIG_N - 1).bit_length()), "half": T._half_bits(BIG_N), "first64": ys[:64],
           "sha256OfU32be": h(T.sha256(u32s(ys))), "bijective": ok}
    walks = [{"n": n, "index": x, "path": walk(seed, n, x)} for n in (10, 257) for x in range(8)]
    rounds = [{"r": r, "R": rv, "half": 5, "F": T._round(seed, r, rv, 5)} for r in range(4) for rv in (0, 1, 31)]
    seed_errors = []
    for name, args, expect in [
        ("collection_mixed_case", (MASTER_SEED, 196, "0x00000000000000000000000000000000000000AA", "IMAGE_V1"),
         "collection must be a lowercase 0x address"),
        ("collection_without_0x", (MASTER_SEED, 196, "00000000000000000000000000000000000000aa", "IMAGE_V1"),
         "collection must be a lowercase 0x address"),
        ("master_seed_31_bytes", (MASTER_SEED[:31], 196, COLLECTION, "IMAGE_V1"), "master seed must be 32 bytes"),
    ]:
        seed_errors.append({"name": name, "masterSeed": "0x" + args[0].hex(), "chainId": args[1], "collection": args[2],
                            "label": args[3], "error": expect_error(lambda a=args: T.pool_seed(*a), expect, name)})
    permute_errors = [{"name": nm, "n": n, "index": x, "error": expect_error(lambda n=n, x=x: T.permute(seed, n, x), "index out of range", nm)}
                      for nm, n, x in [("index_equals_n", 10, 10), ("index_negative", 10, -1)]]
    return {"seeds": seeds, "seedErrors": seed_errors, "permuteErrors": permute_errors,
            "permuteSeed": {"masterSeed": h(MASTER_SEED), "chainId": 196, "collection": COLLECTION, "label": "NETLIST_V1",
                            "poolSeed": h(seed)},
            "roundFunction": rounds, "walks": walks, "permutations": perms, "large": big}


# ---------------------------------------------------------------- e. metadata

def H(s: str) -> str:
    return h(text_sha(s))


BASE_ID = f"eip155:196/erc721:{COLLECTION}/1"


def base_unrevealed() -> dict:
    return {"name": "Example #1", "image": "https://example.invalid/unrevealed.png",
            "tap": {"v": 1, "id": BASE_ID, "state": "unrevealed",
                    "manifest": {"sha256": H("manifest"), "uris": ["https://example.invalid/manifest.json"]}}}


def base_revealed() -> dict:
    return {"name": "Example #1", "image": "https://example.invalid/images/1.png",
            "tap": {"v": 1, "id": BASE_ID, "state": "revealed",
                    "image": {"sha256": H("image"), "uris": ["https://example.invalid/images/1.png"]},
                    "netlist": {"format": "tapnet/1", "sha256": H("netlist"), "bytes": 16 + 7 * 3 + 4 * 1,
                                "nIn": 2, "nOut": 1, "nand": 3, "latch": 1,
                                "uris": ["https://example.invalid/netlists/1.tapnet"]}}}


def base_edition_source() -> dict:
    d = base_revealed()
    t = d["tap"]
    t["manifest"] = {"sha256": H("manifest"), "uris": ["https://example.invalid/manifest.json", "ipfs://bafyexample"]}
    t["edition"] = {"index": 2, "of": 3}
    t["source"] = {"chainId": 56, "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", "circuitId": "3151",
                   "name": "3151.30.tape", "block": 1}
    t["license"] = {"image": "CC-BY-4.0", "netlist": "MIT"}
    t["companion"] = {"chainId": 56, "address": "0x00000000000000000000000000000000000000bb"}
    t["x-unknown-member"] = {"ignored": True}
    return d


def mutate(base_fn, path: list, value=None, delete=False):
    d = base_fn()
    o = d
    for k in path[:-1]:
        o = o[k]
    if delete:
        del o[path[-1]]
    else:
        o[path[-1]] = value
    return d


R, U, F = base_revealed, base_unrevealed, base_edition_source
INVALID_METADATA = [
    # (name, document, expected error)
    ("not_an_object", lambda: [], "metadata must be a JSON object"),
    ("missing_name", lambda: mutate(R, ["name"], delete=True), "`name` is required"),
    ("missing_image", lambda: mutate(R, ["image"], delete=True), "`image` is required"),
    ("missing_tap", lambda: mutate(R, ["tap"], delete=True), "`tap` object is required"),
    ("v_2", lambda: mutate(R, ["tap", "v"], 2), "tap.v must be 1"),
    ("id_uppercase_address", lambda: mutate(R, ["tap", "id"], BASE_ID.replace("aa/1", "AA/1")),
     "tap.id must be eip155:<chainId>/erc721:<lowercase address>/<tokenId>"),
    ("id_leading_zero_token", lambda: mutate(R, ["tap", "id"], BASE_ID[:-1] + "01"),
     "tap.id must be eip155:<chainId>/erc721:<lowercase address>/<tokenId>"),
    ("state_unknown", lambda: mutate(R, ["tap", "state"], "minted"), "tap.state must be unrevealed or revealed"),
    ("state_frozen", lambda: mutate(F, ["tap", "state"], "frozen"), "tap.state must be unrevealed or revealed"),
    ("manifest_sha_uppercase", lambda: mutate(U, ["tap", "manifest", "sha256"], H("manifest").upper().replace("0X", "0x")),
     "tap.manifest.sha256 must be 0x + 64 lowercase hex digits"),
    ("manifest_uris_empty", lambda: mutate(U, ["tap", "manifest", "uris"], []), "tap.manifest.uris must be a non-empty list"),
    ("unrevealed_without_manifest", lambda: mutate(U, ["tap", "manifest"], delete=True),
     "an unrevealed token MUST carry tap.manifest"),
    ("unrevealed_with_netlist", lambda: mutate(U, ["tap", "netlist"], base_revealed()["tap"]["netlist"]),
     "an unrevealed token MUST NOT carry tap.netlist"),
    ("revealed_without_image", lambda: mutate(R, ["tap", "image"], delete=True), "tap.image.sha256 is required"),
    ("image_uri_without_scheme", lambda: mutate(R, ["tap", "image", "uris"], ["images/1.png"]),
     "tap.image.uris: bad URI 'images/1.png'"),
    ("revealed_without_netlist", lambda: mutate(R, ["tap", "netlist"], delete=True), "tap.netlist is required once revealed"),
    ("netlist_format", lambda: mutate(R, ["tap", "netlist", "format"], "tapnet/2"), "tap.netlist.format must be 'tapnet/1'"),
    ("netlist_sha_short", lambda: mutate(R, ["tap", "netlist", "sha256"], H("netlist")[:-2]), "tap.netlist.sha256 is required"),
    ("netlist_bytes_string", lambda: mutate(R, ["tap", "netlist", "bytes"], "41"), "tap.netlist.bytes must be an integer 0..2^53-1"),
    ("netlist_nand_negative", lambda: mutate(R, ["tap", "netlist", "nand"], -1), "tap.netlist.nand must be an integer 0..2^53-1"),
    ("netlist_latch_bool", lambda: mutate(R, ["tap", "netlist", "latch"], True), "tap.netlist.latch must be an integer 0..2^53-1"),
    ("netlist_bytes_mismatch", lambda: mutate(R, ["tap", "netlist", "bytes"], 42), "tap.netlist.bytes does not match nand/latch"),
    ("netlist_uris_missing", lambda: mutate(R, ["tap", "netlist", "uris"], delete=True), "tap.netlist.uris must be a non-empty list"),
    ("edition_index_zero", lambda: mutate(F, ["tap", "edition", "index"], 0), "tap.edition.index must be in 1..of"),
    ("edition_index_above_of", lambda: mutate(F, ["tap", "edition", "index"], 4), "tap.edition.index must be in 1..of"),
    ("edition_not_object", lambda: mutate(F, ["tap", "edition"], [2, 3]), "tap.edition must be an object"),
    ("source_chain_zero", lambda: mutate(F, ["tap", "source", "chainId"], 0), "tap.source.chainId must be non-zero"),
    ("source_processor_short", lambda: mutate(F, ["tap", "source", "processor"], "0xb1024b89"), "tap.source.processor must be a lowercase address"),
    ("source_processor_mixed_case", lambda: mutate(F, ["tap", "source", "processor"], "0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C"),
     "tap.source.processor must be a lowercase address"),
    ("unrevealed_bad_image", lambda: mutate(U, ["tap", "image"], "garbage"), "tap.image.sha256 is required"),
    ("unrevealed_bad_source", lambda: mutate(U, ["tap", "source"], 5), "tap.source must be an object"),
    ("unrevealed_bad_edition", lambda: mutate(U, ["tap", "edition"], {"index": 2, "of": 1}), "tap.edition.index must be in 1..of"),
    ("source_circuit_id_number", lambda: mutate(F, ["tap", "source", "circuitId"], 3151), "tap.source.circuitId must be a decimal string"),
    ("source_block_missing", lambda: mutate(F, ["tap", "source", "block"], delete=True), "tap.source.block must be an integer 0..2^53-1"),
    ("companion_not_object", lambda: mutate(F, ["tap", "companion"], "0x00000000000000000000000000000000000000bb"),
     "tap.companion must be an object"),
    ("companion_chain_zero", lambda: mutate(F, ["tap", "companion", "chainId"], 0), "tap.companion.chainId must be non-zero"),
    ("companion_address_mixed_case", lambda: mutate(F, ["tap", "companion", "address"], "0x00000000000000000000000000000000000000BB"),
     "tap.companion.address must be a lowercase address"),
    ("license_not_object", lambda: mutate(F, ["tap", "license"], "MIT"), "tap.license must be an object"),
    ("license_netlist_number", lambda: mutate(F, ["tap", "license", "netlist"], 1),
     "tap.license.netlist must be an SPDX identifier or URI string"),
    ("source_name_not_tap10", lambda: mutate(F, ["tap", "source", "name"], "3151.tape"), "tap.source.name must be a TAP-10 on-chain name"),
]


def section_metadata() -> dict:
    valid = []
    def unrevealed_with_image():
        d = U()
        d["tap"]["image"] = {"sha256": H("placeholder"), "uris": ["https://example.invalid/unrevealed.png"]}
        return d

    for name, fn in [("unrevealed", U), ("unrevealed_with_placeholder_image", unrevealed_with_image),
                     ("revealed_minimal", R), ("revealed_edition_source", F)]:
        d = fn()
        assert T.check_metadata(d)["state"] == d["tap"]["state"]
        valid.append({"name": name, "document": d})
    invalid = []
    for name, fn, expect in INVALID_METADATA:
        d = fn()
        try:
            T.check_metadata(d)
        except T.Invalid as e:
            assert str(e) == expect, (name, str(e))
        else:
            raise SystemExit(f"metadata {name} was accepted")
        invalid.append({"name": name, "document": d, "error": expect})
    return {"valid": valid, "invalid": invalid}


def section_netlist_checks(tapnet: list) -> list:
    """check_netlist_against_metadata on a real file: one match and two rejects."""
    v = next(x for x in tapnet if x["valid"])
    data = bytes.fromhex(v["file"][2:])
    m = v["metrics"]
    good = {"format": "tapnet/1", "sha256": v["netlistHash"], "bytes": m["bytes"], "nIn": m["nIn"], "nOut": m["nOut"],
            "nand": m["nand"], "latch": m["latch"], "uris": ["https://example.invalid/n.tapnet"]}
    cases = [("match", good, None),
             ("hash_mismatch", dict(good, sha256=H("other")), "netlist file does not hash to tap.netlist.sha256"),
             ("metrics_mismatch", dict(good, nOut=m["nOut"] + 1), "netlist metrics differ from tap.netlist")]
    out = []
    for name, net, expect in cases:
        try:
            T.check_netlist_against_metadata({"netlist": net}, data)
            got = None
        except T.Invalid as e:
            got = str(e)
        assert got == expect, (name, got)
        out.append({"name": name, "file": v["source"]["name"], "netlist": net, "error": expect})
    return out


# ---------------------------------------------------------------- f. worked example collection

EX_SUPPLY = 8
EX_CHAIN = 196
EX_BASE = "https://example.invalid/tap-example"
DRAND_QUICKNET = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"


def section_example(tapnet: list) -> tuple:
    files = {}
    good = [x for x in tapnet if x["valid"]]
    assert good, "no valid tapnet file to build the example from"
    for x in good:
        files[f"{EXAMPLE_DIR}/netlists/{x['netlistHash'][2:]}.tapnet"] = bytes.fromhex(x["file"][2:])
    net_src = [good[i % len(good)] for i in range(EX_SUPPLY)]

    img_entries, net_entries = [], []
    for i in range(EX_SUPPLY):
        img_entries.append({"image": H(f"example image {i}"),
                            "uris": [f"{EX_BASE}/images/{i}.png"],
                            "attributes": [{"trait_type": "Background", "value": ["Copper", "Silicon", "Gold", "Glass"][i % 4]}]})
        s = net_src[i]
        net_entries.append({"netlist": s["netlistHash"],
                            "uris": [f"{EX_BASE}/netlists/{s['netlistHash'][2:]}.tapnet"],
                            "source": {k: s["source"][k] for k in ("chainId", "processor", "circuitId", "name", "block")},
                            "attributes": [{"trait_type": "NAND", "value": s["metrics"]["nand"]},
                                           {"trait_type": "LATCH", "value": s["metrics"]["latch"]}]})

    def leaves(entries, field):
        return [T.leaf_hash(i, [bytes.fromhex(e[field][2:])]) for i, e in enumerate(entries)]

    img_leaves, net_leaves = leaves(img_entries, "image"), leaves(net_entries, "netlist")
    manifest = {
        "tapManifest": 1,
        "collection": {"chainId": EX_CHAIN, "address": COLLECTION, "firstTokenId": 1, "supply": EX_SUPPLY},
        "reveal": {"source": "drand", "chainHash": DRAND_QUICKNET, "round": 1000000,
                   "note": "example only: the masterSeed used below is a fixed value, not this round's randomness"},
        "freeze": {"chainId": EX_CHAIN, "contract": COLLECTION, "call": "uriFrozen()", "expect": True},
        "pools": [
            {"label": "IMAGE_V1", "fields": ["image"], "root": h(T.merkle_root(img_leaves)), "entries": img_entries},
            {"label": "NETLIST_V1", "fields": ["netlist"], "root": h(T.merkle_root(net_leaves)), "entries": net_entries},
        ],
    }
    man_text = dumps(manifest)
    man_bytes = man_text.encode()
    man_hash = h(T.sha256(man_bytes))
    files[f"{EXAMPLE_DIR}/manifest.json"] = man_bytes

    seeds = {p["label"]: T.pool_seed(MASTER_SEED, EX_CHAIN, COLLECTION, p["label"]) for p in manifest["pools"]}
    assign = []
    for x in range(EX_SUPPLY):
        ie, ne = T.permute(seeds["IMAGE_V1"], EX_SUPPLY, x), T.permute(seeds["NETLIST_V1"], EX_SUPPLY, x)
        assign.append((x + 1, ie, ne, net_entries[ne]["netlist"]))
    # edition index = rank of the token id among token ids sharing the netlist hash, ascending, from 1
    by_hash = {}
    for tid, _, _, nh in sorted(assign):
        by_hash.setdefault(nh, []).append(tid)

    tokens = []
    by_file = {x["netlistHash"]: x for x in good}
    for tid, ie, ne, nh in assign:
        s = by_file[nh]
        m = s["metrics"]
        group = by_hash[nh]
        tap = {"v": 1, "id": f"eip155:{EX_CHAIN}/erc721:{COLLECTION}/{tid}", "state": "revealed",
               "manifest": {"sha256": man_hash, "uris": [f"{EX_BASE}/manifest.json"]},
               "image": {"sha256": img_entries[ie]["image"], "uris": img_entries[ie]["uris"]},
               "netlist": {"format": T.FORMAT_ID, "sha256": nh, "bytes": m["bytes"], "nIn": m["nIn"], "nOut": m["nOut"],
                           "nand": m["nand"], "latch": m["latch"], "uris": net_entries[ne]["uris"]},
               "source": net_entries[ne]["source"]}
        if len(group) > 1:
            tap["edition"] = {"index": group.index(tid) + 1, "of": len(group)}
        doc = {"name": f"TAP Example #{tid}", "description": f"Worked example token {tid} of the Netlist-Bound NFT draft.",
               "image": img_entries[ie]["uris"][0],
               "attributes": img_entries[ie]["attributes"] + net_entries[ne]["attributes"],
               "tap": tap}
        T.check_metadata(doc)
        T.check_netlist_against_metadata(tap, bytes.fromhex(s["file"][2:]))
        text = dumps(doc).encode()
        files[f"{EXAMPLE_DIR}/token/{tid}.json"] = text
        tokens.append({"tokenId": tid, "index": tid - 1, "imageEntry": ie, "netlistEntry": ne,
                       "imageHash": img_entries[ie]["image"], "netlistHash": nh, "netlistSource": s["source"]["name"],
                       "imageLeaf": h(img_leaves[ie]), "imageProof": [h(p) for p in T.merkle_proof(img_leaves, ie)],
                       "netlistLeaf": h(net_leaves[ne]), "netlistProof": [h(p) for p in T.merkle_proof(net_leaves, ne)],
                       "edition": tap.get("edition"), "metadataPath": f"{EXAMPLE_DIR}/token/{tid}.json",
                       "metadataSha256": h(T.sha256(text)), "metadata": doc})
    T.check_editions([t["metadata"] for t in tokens])
    for perm in ("imageEntry", "netlistEntry"):
        assert sorted(t[perm] for t in tokens) == list(range(EX_SUPPLY))
    ex = {"collection": manifest["collection"],
          "masterSeed": h(MASTER_SEED),
          "masterSeedNote": "fixed example value (bytes 0x00..0x1f); a real collection takes it from the declared reveal source",
          "poolSeeds": {k: h(v) for k, v in sorted(seeds.items())},
          "manifestPath": f"{EXAMPLE_DIR}/manifest.json", "manifestText": man_text, "manifestSha256": man_hash,
          "netlistFiles": sorted(k for k in files if k.endswith(".tapnet")),
          "tokens": tokens}
    return ex, files


# ---------------------------------------------------------------- manifests (check_manifest)

def one_pool_manifest() -> dict:
    """Supply 3, one pool holding both fields, object-form uris, reveal source none."""
    entries, leaves = [], []
    for i in range(3):
        img, net = text_sha(f"paired image {i}"), text_sha(f"paired netlist {i}")
        entries.append({"image": h(img), "netlist": h(net),
                        "uris": {"image": [f"https://example.invalid/p/{i}.png"], "netlist": [f"https://example.invalid/p/{i}.tapnet"]}})
        leaves.append(T.leaf_hash(i, [img, net]))
    return {"tapManifest": 1,
            "collection": {"chainId": 8453, "address": "0x00000000000000000000000000000000000000cc", "firstTokenId": 0, "supply": 3},
            "reveal": {"source": "none"},
            "pools": [{"label": "PAIRED_V1", "fields": ["image", "netlist"], "root": h(T.merkle_root(leaves)), "entries": entries}]}


def example_manifest(man_text: str):
    return lambda: json.loads(man_text)


def mut(base, path, value=None, delete=False):
    def fn():
        d = base()
        o = d
        for k in path[:-1]:
            o = o[k]
        if delete:
            del o[path[-1]]
        else:
            o[path[-1]] = value
        return d
    return fn


def section_manifests(man_text: str) -> dict:
    ONE, TWO = one_pool_manifest, example_manifest(man_text)
    assert T.check_manifest(man_text.encode())
    valid = []
    for name, fn in [("one_pool_two_fields_object_uris", ONE), ("two_pools_example", TWO)]:
        text = man_text if fn is TWO else dumps(fn())
        T.check_manifest(text.encode())
        valid.append({"name": name, "manifest": text, "sha256": h(T.sha256(text.encode()))})

    def blockhash():
        d = ONE()
        d["reveal"] = {"source": "blockhash", "chainId": 8453, "blockNumber": 30000000}
        return d

    def overlap():
        d = TWO()
        p0 = d["pools"][0]
        d["pools"][1] = dict(p0, label="IMAGE_V2")
        return d

    def three_pools():
        d = TWO()
        d["pools"].append(dict(d["pools"][0], label="EXTRA"))
        return d

    def one_entry_less():
        d = ONE()
        d["pools"][0]["entries"].pop()
        return d

    T.check_manifest(dumps(blockhash()).encode())
    valid.append({"name": "one_pool_blockhash_reveal", "manifest": dumps(blockhash()),
                  "sha256": h(T.sha256(dumps(blockhash()).encode()))})
    ex_img0 = json.loads(man_text)["pools"][0]["entries"][0]["image"]
    cases = [
        ("not_utf8", None, bytes([0xff, 0xfe]) + b"{}", "manifest is not UTF-8 JSON"),
        ("not_object", lambda: [1], None, "manifest must be a JSON object"),
        ("tapManifest_2", mut(ONE, ["tapManifest"], 2), None, "tapManifest must be 1"),
        ("tapManifest_true", mut(ONE, ["tapManifest"], True), None, "tapManifest must be 1"),
        ("address_mixed_case", mut(ONE, ["collection", "address"], "0x00000000000000000000000000000000000000CC"), None,
         "collection.address must be a lowercase address"),
        ("chain_id_zero", mut(ONE, ["collection", "chainId"], 0), None, "collection.chainId must be non-zero"),
        ("supply_zero", mut(ONE, ["collection", "supply"], 0), None, "collection.supply must be in 1..2^32"),
        ("supply_above_2_32", mut(ONE, ["collection", "supply"], 2**32 + 1), None, "collection.supply must be in 1..2^32"),
        ("first_token_id_too_large", mut(ONE, ["collection", "firstTokenId"], 2**53 - 3), None,
         "collection.firstTokenId must be at most 2^53 - 1 - supply"),
        ("reveal_vrf", mut(ONE, ["reveal"], {"source": "vrf"}), None, 'reveal.source "vrf" is reserved and not defined in version 1'),
        ("reveal_unknown", mut(ONE, ["reveal"], {"source": "coinflip"}), None, "reveal.source must be drand, blockhash or none"),
        ("drand_chain_hash_with_0x", mut(TWO, ["reveal", "chainHash"], "0x" + DRAND_QUICKNET), None,
         "reveal.chainHash must be 64 lowercase hex digits without 0x"),
        ("drand_round_missing", mut(TWO, ["reveal", "round"], delete=True), None, "reveal.round must be an integer 0..2^53-1"),
        ("blockhash_without_block", mut(blockhash, ["reveal", "blockNumber"], delete=True), None,
         "reveal.blockNumber must be an integer 0..2^53-1"),
        ("no_pools", mut(ONE, ["pools"], []), None, "pools must hold one or two pools"),
        ("three_pools", three_pools, None, "pools must hold one or two pools"),
        ("label_empty", mut(ONE, ["pools", 0, "label"], ""), None, "pools[0].label must be 1-64 bytes of printable ASCII"),
        ("label_65_bytes", mut(ONE, ["pools", 0, "label"], "L" * 65), None, "pools[0].label must be 1-64 bytes of printable ASCII"),
        ("label_non_ascii", mut(ONE, ["pools", 0, "label"], "网表"), None, "pools[0].label must be 1-64 bytes of printable ASCII"),
        ("label_duplicate", mut(TWO, ["pools", 1, "label"], "IMAGE_V1"), None, "pools[1].label is not unique"),
        ("fields_reversed", mut(ONE, ["pools", 0, "fields"], ["netlist", "image"]), None,
         'pools[0].fields must be ["image"], ["netlist"] or ["image", "netlist"]'),
        ("fields_overlap", overlap, None, "pools[1].fields: a field appears in more than one pool"),
        ("root_zero", mut(ONE, ["pools", 0, "root"], "0x" + "00" * 32), None, "pools[0].root must not be zero"),
        ("root_wrong", mut(ONE, ["pools", 0, "root"], H("wrong root")), None, "pools[0].root does not match its entries"),
        ("entry_count_wrong", one_entry_less, None, "pools[0].entries must hold exactly supply entries"),
        ("entry_value_zero", mut(ONE, ["pools", 0, "entries", 1, "netlist"], "0x" + "00" * 32), None,
         "pools[0].entries[1].netlist must not be zero"),
        ("entry_value_uppercase", mut(TWO, ["pools", 0, "entries", 0, "image"], ex_img0.upper().replace("0X", "0x")), None,
         "pools[0].entries[0].image must be 0x + 64 lowercase hex digits"),
        ("uris_list_in_two_field_pool", mut(ONE, ["pools", 0, "entries", 0, "uris"], ["https://example.invalid/p/0.png"]), None,
         "pools[0].entries[0].uris must be an object with image and netlist lists in a two-field pool"),
        ("uris_object_in_one_field_pool", mut(TWO, ["pools", 0, "entries", 0, "uris"], {"image": ["https://example.invalid/0.png"]}),
         None, "pools[0].entries[0].uris must be a non-empty list of URIs"),
        ("uris_object_missing_netlist", mut(ONE, ["pools", 0, "entries", 2, "uris"], {"image": ["https://example.invalid/p/2.png"]}),
         None, "pools[0].entries[2].uris.netlist must be a non-empty list of URIs"),
        ("freeze_expect_false", mut(TWO, ["freeze", "expect"], False), None, "freeze.expect must be true"),
        ("freeze_call_with_argument", mut(TWO, ["freeze", "call"], "uriFrozen(uint256)"), None,
         "freeze.call must be a function signature without arguments, e.g. uriFrozen()"),
    ]
    invalid = []
    for name, fn, raw, expect in cases:
        data = raw if raw is not None else dumps(fn()).encode()
        expect_error(lambda d=data: T.check_manifest(d), expect, name)
        entry = {"name": name, "error": expect}
        try:
            entry["manifest"] = data.decode("utf-8")
        except UnicodeDecodeError:
            entry["manifestHex"] = "0x" + data.hex()
        invalid.append(entry)
    return {"valid": valid, "invalid": invalid}


# ---------------------------------------------------------------- token sets (set mode)

TS_RNG_SEED = 196
TS_BASE = "https://example.invalid/tap-set"


def set_mode_manifest(ids: list) -> dict:
    """10 ids out of 1..20, one two-field pool, drand reveal (masterSeed = MASTER_SEED, fixed)."""
    n = len(ids)
    entries, leaves = [], []
    for i in range(n):
        img, net = text_sha(f"set image {i}"), text_sha(f"set netlist {i}")
        entries.append({"image": h(img), "netlist": h(net)})
        leaves.append(T.leaf_hash(i, [img, net]))
    return {"tapManifest": 1,
            "collection": {"chainId": 196, "address": COLLECTION,
                           "tokenSet": {"sha256": h(T.token_set_hash(ids)), "count": n, "uris": [f"{TS_BASE}/ids.bin"]}},
            "reveal": {"source": "drand", "chainHash": DRAND_QUICKNET, "round": 1000000},
            "pools": [{"label": "PAIRED_V1", "fields": ["image", "netlist"], "root": h(T.merkle_root(leaves)), "entries": entries}]}


def section_token_sets() -> tuple:
    rng = random.Random(TS_RNG_SEED)
    small_ids = sorted(rng.sample(range(1, 21), 10))
    man = set_mode_manifest(small_ids)
    man_text = dumps(man)
    T.check_manifest(man_text.encode())
    ids_file = T.token_set_file(small_ids)
    assert T.check_token_set(man, ids_file) == small_ids
    small = []
    for t in range(1, 21):
        a = T.assignment(man, MASTER_SEED, t, small_ids)
        small.append({"tokenId": t, "index": T.token_index(small_ids, t) if a else None, "entries": a})
    assert sorted(x["entries"]["PAIRED_V1"] for x in small if x["entries"]) == list(range(10))

    big_ids = sorted(rng.sample(range(1, 10001), 7000))
    big_man = {"collection": {"chainId": 196, "address": COLLECTION,
                              "tokenSet": {"sha256": h(T.token_set_hash(big_ids)), "count": len(big_ids)}},
               "reveal": {"source": "drand"}, "pools": [{"label": "NETLIST_V1"}]}
    ys = [T.assignment(big_man, MASTER_SEED, t, big_ids)["NETLIST_V1"] for t in big_ids]
    assert sorted(ys) == list(range(len(big_ids)))
    assert T.assignment(big_man, MASTER_SEED, next(t for t in range(1, 10001) if t not in set(big_ids)), big_ids) is None
    large = {"idsDerivation": f"random.Random({TS_RNG_SEED}): sample(range(1, 21), 10) first, then sample(range(1, 10001), 7000), each sorted",
             "count": len(big_ids), "sha256": big_man["collection"]["tokenSet"]["sha256"],
             "chainId": 196, "collection": COLLECTION, "label": "NETLIST_V1", "masterSeed": h(MASTER_SEED),
             "poolSeed": h(T.pool_seed(MASTER_SEED, 196, COLLECTION, "NETLIST_V1")),
             "first32": [{"tokenId": t, "index": i, "entry": ys[i]} for i, t in enumerate(big_ids[:32])],
             "sha256OfEntriesU32be": h(T.sha256(u32s(ys))),
             "note": "entries listed in ascending token id order; tokens outside the set receive nothing"}

    file_errors = []
    for name, data, expect in [
        ("length_not_multiple_of_4", ids_file[:-1], "token-set file length is not a multiple of 4"),
        ("not_ascending", ids_file[4:8] + ids_file[:4] + ids_file[8:], "token ids must be strictly ascending"),
        ("duplicate_id", ids_file[:4] + ids_file[:-4], "token ids must be strictly ascending"),
        ("one_id_missing", ids_file[:-4], "token-set file does not hold tokenSet.count ids"),
        ("other_ids", T.token_set_file(small_ids[:-1] + [small_ids[-1] + 1]), "token-set file does not hash to tokenSet.sha256"),
    ]:
        file_errors.append({"name": name, "file": "0x" + data.hex(),
                            "error": expect_error(lambda d=data: T.check_token_set(man, d), expect, name)})
    hash_errors = []
    for name, ids, expect in [("not_ascending", [2, 1], "token ids must be strictly ascending"),
                              ("id_above_u32", [1, 2**32], "token ids must be integers 0..2^32-1")]:
        hash_errors.append({"name": name, "ids": ids, "error": expect_error(lambda i=ids: T.token_set_hash(i), expect, name)})
    sec = {"small": {"ids": small_ids, "file": "0x" + ids_file.hex(), "sha256": h(T.token_set_hash(small_ids)),
                     "manifest": man_text, "manifestSha256": h(T.sha256(man_text.encode())), "masterSeed": h(MASTER_SEED),
                     "poolSeed": h(T.pool_seed(MASTER_SEED, 196, COLLECTION, "PAIRED_V1")), "tokens": small},
           "large": large, "fileErrors": file_errors, "hashErrors": hash_errors}

    S = lambda: json.loads(man_text)  # noqa: E731
    mvalid = [{"name": "set_mode_one_pool", "manifest": man_text, "sha256": h(T.sha256(man_text.encode()))}]

    def both():
        d = S()
        d["collection"].update(firstTokenId=1, supply=10)
        return d

    def short_pool():
        d = S()
        p = d["pools"][0]
        p["entries"].pop()
        return d

    cases = [
        ("set_mode_with_supply", both, "collection must use either firstTokenId and supply or tokenSet, not both"),
        ("set_mode_not_object", mut(S, ["collection", "tokenSet"], "0x" + "11" * 32), "collection.tokenSet must be an object"),
        ("set_mode_sha_uppercase", mut(S, ["collection", "tokenSet", "sha256"], "0x" + "AB" * 32),
         "collection.tokenSet.sha256 must be 0x + 64 lowercase hex digits"),
        ("set_mode_count_zero", mut(S, ["collection", "tokenSet", "count"], 0), "collection.tokenSet.count must be in 1..2^32"),
        ("set_mode_count_above_2_32", mut(S, ["collection", "tokenSet", "count"], 2**32 + 1), "collection.tokenSet.count must be in 1..2^32"),
        ("set_mode_uris_missing", mut(S, ["collection", "tokenSet", "uris"], delete=True),
         "collection.tokenSet.uris must be a non-empty list of URIs"),
        ("set_mode_entry_count_wrong", short_pool, "pools[0].entries must hold exactly count entries"),
    ]
    minvalid = []
    for name, fn, expect in cases:
        data = dumps(fn()).encode()
        minvalid.append({"name": name, "manifest": data.decode(), "error": expect_error(lambda d=data: T.check_manifest(d), expect, name)})
    return sec, mvalid, minvalid


# ---------------------------------------------------------------- tap.content (§7.5) and outside-the-set placeholders (§5.4, §7.2)

def base_content() -> dict:
    d = base_revealed()
    d["tap"]["content"] = {"chainId": 196, "container": "0x00000000000000000000000000000000000000dd", "name": "1.2.282.tape",
                           "paths": {"image": "images/1.png", "netlist": "netlists/1.tapnet", "metadata": "token/1.json"},
                           "lock": "0x00000000000000000000000000000000000000ee"}
    return d


def section_content() -> dict:
    C = base_content
    valid = []
    for name, fn in [("full", C), ("minimal_no_lock_empty_paths",
                                   lambda: mutate(lambda: mutate(C, ["tap", "content", "lock"], delete=True), ["tap", "content", "paths"], {}))]:
        d = fn()
        T.check_metadata(d)
        valid.append({"name": name, "document": d})
    cases = [
        ("not_object", mut(C, ["tap", "content"], "1.2.282.tape"), "tap.content must be an object"),
        ("chain_zero", mut(C, ["tap", "content", "chainId"], 0), "tap.content.chainId must be non-zero"),
        ("chain_missing", mut(C, ["tap", "content", "chainId"], delete=True), "tap.content.chainId must be an integer 0..2^53-1"),
        ("container_mixed_case", mut(C, ["tap", "content", "container"], "0x00000000000000000000000000000000000000DD"),
         "tap.content.container must be a lowercase address"),
        ("name_not_tap10", mut(C, ["tap", "content", "name"], "testBlonskr"), "tap.content.name must be a TAP-10 on-chain name"),
        ("paths_missing", mut(C, ["tap", "content", "paths"], delete=True), "tap.content.paths must be an object"),
        ("paths_image_number", mut(C, ["tap", "content", "paths", "image"], 1), "tap.content.paths.image must be a non-empty string"),
        ("paths_metadata_empty", mut(C, ["tap", "content", "paths", "metadata"], ""), "tap.content.paths.metadata must be a non-empty string"),
        ("lock_mixed_case", mut(C, ["tap", "content", "lock"], "0x00000000000000000000000000000000000000EE"),
         "tap.content.lock must be a lowercase address"),
    ]
    invalid = []
    for name, fn, expect in cases:
        d = fn()
        invalid.append({"name": name, "document": d, "error": expect_error(lambda d=d: T.check_metadata(d), expect, name)})
    return {"valid": valid, "invalid": invalid}


def section_placeholders(ts: dict) -> dict:
    """Metadata for a token outside the small token set: check_metadata(doc, outside_token_set=True)."""
    sm = ts["small"]
    t = next(i for i in range(1, 21) if i not in sm["ids"])
    man_uri = f"{TS_BASE}/manifest.json"

    def P():
        return {"name": f"Set example #{t}", "image": f"{TS_BASE}/not-covered.png",
                "tap": {"v": 1, "id": f"eip155:196/erc721:{COLLECTION}/{t}", "state": "unrevealed",
                        "manifest": {"sha256": sm["manifestSha256"], "uris": [man_uri]}}}

    def with_tap_image():
        d = P()
        d["tap"]["image"] = {"sha256": H("placeholder"), "uris": [f"{TS_BASE}/not-covered.png"]}
        return d

    assert T.check_metadata(P(), outside_token_set=True)
    assert T.check_metadata(with_tap_image())  # fine for a token awaiting a reveal
    cases = [
        ("carries_tap_image", with_tap_image, "a token outside the token set MUST NOT carry tap.image"),
        ("revealed", mut(P, ["tap", "state"], "revealed"), "a token outside the token set MUST be unrevealed"),
        ("carries_tap_netlist", mut(P, ["tap", "netlist"], base_revealed()["tap"]["netlist"]), "an unrevealed token MUST NOT carry tap.netlist"),
        ("no_manifest", mut(P, ["tap", "manifest"], delete=True), "an unrevealed token MUST carry tap.manifest"),
    ]
    invalid = []
    for name, fn, expect in cases:
        d = fn()
        invalid.append({"name": name, "document": d,
                        "error": expect_error(lambda d=d: T.check_metadata(d, outside_token_set=True), expect, name)})
    return {"tokenId": t, "tokenSet": "tokenSets.small", "check": "check_metadata(document, outside_token_set=True)",
            "valid": [{"name": "placeholder_with_erc721_image", "document": P()}],
            "validAwaitingReveal": [{"name": "same_with_tap_image_awaiting_reveal", "document": with_tap_image(),
                                     "note": "valid for a token inside the set (outside_token_set=False), invalid outside it"}],
            "invalid": invalid}


# ---------------------------------------------------------------- editions (collection level)

def section_editions(example: dict) -> dict:
    """check_editions over the example's 8 documents, then one mutation per failure mode."""
    import copy
    docs = [t["metadata"] for t in example["tokens"]]
    T.check_editions(docs)
    # pick the first token (by id) whose netlist hash is shared, and mutate only that document
    victim = next(t for t in example["tokens"] if t["edition"])
    tid, ed = victim["tokenId"], victim["edition"]
    want = f"token {tid}: edition must be {ed['index']}/{ed['of']}"
    wrong_index = ed["index"] % ed["of"] + 1
    cases = [("missing_edition", None), ("wrong_index", {"index": wrong_index, "of": ed["of"]}),
             ("wrong_of", {"index": ed["index"], "of": ed["of"] + 1})]
    invalid = []
    for name, new in cases:
        ds = copy.deepcopy(docs)
        t = ds[tid - 1]["tap"]
        if new is None:
            del t["edition"]
        else:
            t["edition"] = new
        T.check_metadata(ds[tid - 1])  # each mutated document is still valid on its own
        invalid.append({"name": name, "tokenId": tid, "edition": new, "error": expect_error(lambda d=ds: T.check_editions(d), want, name)})
    return {"collection": "example (documents in example.tokens[*].metadata)", "valid": True, "invalid": invalid}


# ---------------------------------------------------------------- build

def build(chain: dict | None = None) -> tuple:
    """Returns (vectors document, {relative path: bytes}) — the latter includes vectors.json itself."""
    chain = chain or load_chain()
    tapnet = section_tapnet(chain)
    example, files = section_example(tapnet)
    doc = {"format": "tap-netlist-bound-nft-vectors/1",
           "generator": "make_vectors.py (functions of tapnft.py only)",
           "chain": {"chainId": chain["chainId"], "block": chain["block"], "nodes": chain.get("nodes", []),
                     "note": "read-only eth_call results; no transaction sent"},
           "tapnet": tapnet,
           "invalidFiles": section_invalid_files(),
           "merkle": section_merkle(),
           "permutation": section_permutation(),
           "metadata": section_metadata(),
           "netlistChecks": section_netlist_checks(tapnet),
           "manifests": section_manifests(example["manifestText"]),
           "editions": section_editions(example),
           "example": example}
    ts, mvalid, minvalid = section_token_sets()
    doc["tokenSets"] = ts
    doc["content"] = section_content()
    doc["placeholders"] = section_placeholders(ts)
    doc["manifests"]["valid"] += mvalid      # appended so earlier vectors keep their positions
    doc["manifests"]["invalid"] += minvalid
    files["vectors.json"] = dumps(doc).encode()
    return doc, files


def main(argv: list) -> None:
    if len(argv) >= 2 and argv[0] == "--import":
        import_snapshot(Path(argv[1]))
    _, files = build()
    for rel, data in sorted(files.items()):
        p = HERE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    print(len(files), "files written; vectors.json sha256", hashlib.sha256(files["vectors.json"]).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1:])
