#!/usr/bin/env python3
"""Record historical drand quicknet rounds into test/fixtures/drand-quicknet-rounds.json.

MIT licence. Standard library only. Read-only: HTTP GET of public drand data, nothing else.

    python3 contracts/test/fixtures/fetch_drand_rounds.py        # writes drand-quicknet-rounds.json next to this file
    python3 contracts/test/fixtures/fetch_drand_rounds.py --check  # re-fetches and compares with the committed file

The Foundry tests of the drand reveal kit (test/tools/drand) check real BLS signatures on chain. A drand round is
public, immutable data, so the tests use recorded rounds and need no network. Every round is taken from TWO relays run
by different operators (api.drand.sh from the drand team, drand.cloudflare.com from Cloudflare); the script refuses
to write anything if

  * a relay's /info does not hash to the quicknet chain hash (SHA-256(u32be(period) || i64be(genesis_time) ||
    public_key || groupHash || beaconID), TAP-721 core section 6.1 item 7) or carries another public key than the
    one pinned in src/tools/drand/DrandBeacon.sol,
  * the two relays answer with different signatures for a round,
  * randomness is not SHA-256(signature) (drand's definition for the unchained schemes),
  * a round is not yet produced (only rounds well in the past are listed).

It does not check the BLS signatures: the tests do that, on chain, with the EIP-2537 precompiles.

The rounds are a fixed list, not "the latest", and the file has no timestamp: regenerating gives the same bytes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "drand-quicknet-rounds.json")

CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
PUBLIC_KEY = (
    "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c"
    "8c4b450b6a0a6c3ac6a5776a2d106451"
    "0d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5"
    "a6e9c76a4bc09e76eae8991ef5ece45a"
)  # quicknet's group public key (compressed G2); DrandBeacon.sol hard-codes the same point, checked below
GENESIS = 1692803367
PERIOD = 3
RELAYS = ["https://api.drand.sh", "https://drand.cloudflare.com"]

# The base of the kit tests: round BASE is "now" in most tests, its time is 2026-10-12 UTC.
BASE = 33_000_000
ROUNDS = sorted(
    set(
        [1, 2, 3, 4, 5, 10, 100, 1000, 1_000_000, 33_145_012]  # early rounds; 33,145,012 is used by tools/collection tests
        + [BASE + i for i in range(0, 8)]  # contiguous: self-test round and rounds posted to the beacon
        + [BASE + 15_604 + i for i in range(0, 6)]  # around the smallest fixed-mode R for a commit at time(BASE) + 10 s
        + [BASE + 16_000, BASE + 16_001]
        + [BASE + 20_000 + i for i in range(0, 4)]  # deferred-mode R candidates
        + [BASE + 40_000 + i for i in range(0, 3)]  # a second pair for lag and clock tests
        + [100_000 + i * 1_000_003 for i in range(0, 16)]  # spread over the chain's history: both sort flags, many x values
    )
)


def get_json(url: str, tries: int = 5):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tap721-fixture/1"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001 - report the last error after the retries
            last = e
            time.sleep(1.0 + attempt)
    raise SystemExit(f"{url}: {last}")


def chain_hash(info: dict) -> str:
    data = (
        PERIOD.to_bytes(4, "big")
        + int(info["genesis_time"]).to_bytes(8, "big")
        + bytes.fromhex(info["public_key"])
        + bytes.fromhex(info["groupHash"])
        + info["metadata"]["beaconID"].encode()
    )
    return hashlib.sha256(data).hexdigest()


def pinned_in_beacon() -> str:
    """The x coordinate of the PK constant of DrandBeacon.sol (x.c0, x.c1, y.c0, y.c1 as 64-byte words), re-encoded as
    the compressed key drand publishes: c1 || c0 with the top three bits of the first byte being flags."""
    src = open(os.path.join(HERE, "..", "..", "src", "tools", "drand", "DrandBeacon.sol"), encoding="utf-8").read()
    block = src[src.index("bytes private constant PK ="):]
    blob = b"".join(bytes.fromhex(w) for w in re.findall(r'hex"([0-9a-f]+)"', block[: block.index(";")]))
    if len(blob) != 256:
        raise SystemExit("cannot read the PK constant of DrandBeacon.sol")
    words = [blob[i * 64 : (i + 1) * 64] for i in range(4)]
    return (words[1][16:] + words[0][16:]).hex()


def check_info(relay: str, info: dict) -> None:
    if int(info["period"]) != PERIOD or int(info["genesis_time"]) != GENESIS:
        raise SystemExit(f"{relay}: period/genesis differ from quicknet")
    pinned = pinned_in_beacon()
    # the compressed key has flag bits (0x80 = compressed) in the top three bits of its first byte
    if PUBLIC_KEY[2:] != pinned[2:] or (int(PUBLIC_KEY[:2], 16) & 0x1F) != int(pinned[:2], 16):
        raise SystemExit("PUBLIC_KEY differs from the PK constant of DrandBeacon.sol")
    if info["public_key"] != PUBLIC_KEY:
        raise SystemExit(f"{relay}: public key is not the one pinned in DrandBeacon.sol")
    if chain_hash(info) != CHAIN_HASH:
        raise SystemExit(f"{relay}: /info does not hash to the quicknet chain hash")


def record() -> dict:
    for relay in RELAYS:
        check_info(relay, get_json(f"{relay}/{CHAIN_HASH}/info"))
    now = time.time()
    rounds = []
    for r in ROUNDS:
        if GENESIS + PERIOD * (r - 1) + 86400 > now:
            raise SystemExit(f"round {r} is not at least a day old")
        answers = [get_json(f"{relay}/{CHAIN_HASH}/public/{r}") for relay in RELAYS]
        for relay, a in zip(RELAYS, answers):
            if int(a["round"]) != r:
                raise SystemExit(f"{relay}: asked for round {r}, got {a['round']}")
            sig = bytes.fromhex(a["signature"])
            if len(sig) != 48:
                raise SystemExit(f"{relay}: round {r}: signature is {len(sig)} bytes, not 48")
            if hashlib.sha256(sig).hexdigest() != a["randomness"]:
                raise SystemExit(f"{relay}: round {r}: randomness is not SHA-256(signature)")
        if answers[0]["signature"] != answers[1]["signature"]:
            raise SystemExit(f"round {r}: the relays disagree: {answers[0]['signature']} / {answers[1]['signature']}")
        rounds.append(
            {
                "round": r,
                "signature": "0x" + answers[0]["signature"],
                "randomness": "0x" + answers[0]["randomness"],
                "flag": "0x%02x" % (bytes.fromhex(answers[0]["signature"])[0] & 0xE0),
            }
        )
        print(f"round {r}: {len(RELAYS)} relays agree", file=sys.stderr)
    return {
        "chainHash": CHAIN_HASH,
        "publicKey": PUBLIC_KEY,
        "genesis": GENESIS,
        "period": PERIOD,
        "scheme": "bls-unchained-g1-rfc9380",
        "relays": RELAYS,
        "count": len(rounds),
        "rounds": rounds,
    }


def main() -> None:
    doc = record()
    if "--check" in sys.argv:
        with open(OUT, "r", encoding="utf-8") as f:
            old = json.load(f)
        if old != doc:
            raise SystemExit("drand-quicknet-rounds.json differs from what the relays serve")
        print("drand-quicknet-rounds.json up to date", file=sys.stderr)
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(f"wrote {OUT} ({doc['count']} rounds)", file=sys.stderr)


if __name__ == "__main__":
    main()
