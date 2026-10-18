"""Shared constants and import paths for the TapeCode-Test1 collection tools (stdlib only, MIT).

Puts the reference implementation of the Netlist-Bound NFTs draft (`tapnft.py`, which itself imports
`tap02_reference`) and the profile's quota module (`tct1_quota.py`) on sys.path. The PoD validator
(`pod_validate.py`, which needs pycryptodome through `pod_snapshot.py`) is imported lazily, only when a
PoD snapshot is used.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DRAFTS = os.path.normpath(os.path.join(HERE, "..", ".."))
TAPNFT_DIR = os.path.join(DRAFTS, "assets", "tap-netlist-bound-nft")
PROFILES_DIR = os.path.join(DRAFTS, "profiles")
POD_DIR = os.path.join(DRAFTS, "assets", "tap-pod-attributes")

for _d in (TAPNFT_DIR, PROFILES_DIR):
    if _d not in sys.path:
        sys.path.insert(0, _d)

import tapnft  # noqa: E402  (reference functions; never reimplemented here)
import tct1_quota  # noqa: E402  (tiers, percentages, quotas, edition plan)

# ---------------------------------------------------------------- TapeCode-Test1 facts (DESIGN.md §0)
CHAIN_ID = 196
CONTRACT = "0x0e91460d6823c711643e650a9a4c0cc21de41614"
FIRST_TOKEN_ID = 1
SUPPLY = 10000
FREEZE = {"chainId": CHAIN_ID, "contract": CONTRACT, "call": "uriFrozen()", "expect": True}
IMAGE_LABEL = "IMAGE_V1"
NETLIST_LABEL = "NETLIST_V1"
MAX_NETLIST_BYTES = 49152          # draft A §8.2 item 4 (storeNetlist limit)
MAX_CONTAINER_FILE = 8 * 1024 * 1024  # TapeCode single-file limit (profile §3.6)

# drand quicknet. Only the chain hash is a constant: genesis, period and the public key are always
# fetched from /<chainhash>/info and checked against this hash (drand.py).
QUICKNET = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"

ZERO32 = "0x" + "00" * 32
DEAD = "0x000000000000000000000000000000000000dead"
ID_RANGE = range(1, 10001)          # every TCT1 token id (valid and excluded)
RARITY_FILE = os.path.join(HERE, "rarity-7000.json")
RARITY_DOC = os.path.join(HERE, "RARITY.md")
TOKENS_FILE = os.path.join(DRAFTS, "tools", "tokenset", "tokens.json")

# Source chain (BNB Smart Chain) facts for tap.source: processor numbers (TAP-10 names) and the container
# opener whose accountOf(processor, circuitId) gives tap.source.container (draft A §3.2 item 5).
BSC_PROCESSOR_NUMBER = {"0xb1024b89886b9a34aa4ff5f31c411d708b20a14c": 30,   # TapeOut
                        "0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c": 1}    # Blonskr_No1
BSC_OPENER = "0x021745de2f42a7839d96f2d3634d0294487d81f1"
BSC_ARCHIVE_RPC = "https://tapeout.net/rpc"


def load_token_ids(path: str) -> list:
    """Valid token ids, ascending, from: a .bin token-set file (u32be ids); a JSON list of ids; a JSON object
    with ids/valid/tokens/tokenIds; or an owners map {"owners": {id: address}} (ids owned by 0x…dead or
    by nobody are excluded)."""
    with open(path, "rb") as f:
        raw = f.read()
    if path.endswith(".bin"):
        if len(raw) % 4:
            raise SystemExit(f"{path}: length is not a multiple of 4")
        ids = [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw), 4)]
    else:
        d = json.loads(raw)
        if isinstance(d, dict):
            for k in ("validTokenIds", "ids", "valid", "validIds", "tokens", "tokenIds"):
                if isinstance(d.get(k), list):
                    d = d[k]
                    break
            else:
                if isinstance(d.get("owners"), dict):
                    d = [int(k) for k, v in d["owners"].items() if v and str(v).lower() != DEAD]
                else:
                    raise SystemExit(f"{path}: no id list found")
        ids = [int(x["id"] if isinstance(x, dict) else x) for x in d]
    ids = sorted(set(ids))
    if not path.endswith(".bin") and isinstance(json.loads(raw), dict):
        declared = json.loads(raw).get("tokenSetHash")
        if declared and tapnft.hex32(tapnft.token_set_hash(ids)) != declared.lower():
            raise SystemExit(f"{path}: tokenSetHash {declared} does not match its ids")
    return ids


def pod_validate():
    """Lazy import of the draft-C validator (needs pycryptodome)."""
    if POD_DIR not in sys.path:
        sys.path.insert(0, POD_DIR)
    try:
        import pod_validate as pv  # noqa: WPS433
    except ImportError as e:  # pragma: no cover
        raise SystemExit(f"tap.pod needs {POD_DIR}/pod_validate.py and pycryptodome: {e}")
    return pv


def compact(obj) -> bytes:
    """Deterministic compact JSON bytes: sorted keys, no whitespace, ASCII only, no trailing newline."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def write_bytes(path: str, data: bytes) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def read_json(path: str):
    with open(path, "rb") as f:
        return json.loads(f.read())


def is_hex32(s) -> bool:
    return isinstance(s, str) and tapnft.HEX32.match(s) is not None
