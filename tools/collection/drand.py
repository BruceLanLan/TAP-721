#!/usr/bin/env python3
"""drand quicknet: chain info, round timing and verified beacons (stdlib only, read-only HTTP GET).

  drand.py info                              # fetch /<chainhash>/info from every relay, check the chain hash
  drand.py round-at 2026-10-31T12:00:00Z     # first round produced at or after that UTC time
  drand.py fetch <round> [--out beacon.json] # fetch, verify and save one beacon

What is verified
  * chain info: every relay must return the same info, and SHA-256(u32be(period) || i64be(genesis_time) ||
    public_key || groupHash || beaconID) must equal the requested chain hash, so period, genesis and the
    group public key are bound to the hash written in the manifest (layout reproduced against the live
    quicknet info on 2026-10-18; it is drand's Info.Hash());
  * beacon: round number as requested; randomness == SHA-256(signature) (drand's rule for all schemes);
    randomness is 32 bytes, signature 48 bytes (a compressed G1 point for bls-unchained-g1-rfc9380);
    at least `min_agree` relays (default 2) return the identical signature, and none disagrees;
  * the round's production time genesis + (round - 1) * period is not in the future.

What is NOT verified: the BLS signature itself (pairing check of the signature against the group public
key over the round's message SHA-256(u64be(round)), with hash-to-G1 per RFC 9380). Without it a set of
relays that colluded could serve a made-up (signature, SHA-256(signature)) pair. The residual trust is
that the agreeing relays (by default api.drand.sh, api2.drand.sh, api3.drand.sh - one operator - and
drand.cloudflare.com - another) are honest. Anyone can close the gap with drand's own clients, e.g.
`drand-client` (Go) or `drand-client` (JS), which verify the signature against the public key printed by
`drand.py info`.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import struct
import sys
import time
import urllib.request

from _paths import QUICKNET, compact, write_bytes

RELAYS = ["https://api.drand.sh", "https://api2.drand.sh", "https://api3.drand.sh", "https://drand.cloudflare.com"]


class DrandError(Exception):
    pass


def _get(url: str, timeout: float = 20):
    req = urllib.request.Request(url, headers={"user-agent": "tct1-collection", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chain_hash_of(info: dict) -> str:
    """drand Info.Hash(): SHA-256(u32be(period) || i64be(genesis) || pk || groupHash || beaconID if not 'default')."""
    beacon_id = (info.get("metadata") or {}).get("beaconID", "")
    data = (struct.pack(">I", int(info["period"])) + struct.pack(">q", int(info["genesis_time"]))
            + bytes.fromhex(info["public_key"]) + bytes.fromhex(info["groupHash"]))
    if beacon_id and beacon_id != "default":
        data += beacon_id.encode()
    return hashlib.sha256(data).hexdigest()


def fetch_info(chain_hash: str = QUICKNET, relays: list = None, min_agree: int = 2) -> dict:
    relays = relays or RELAYS
    got, errs = [], []
    for r in relays:
        try:
            got.append((r, _get(f"{r}/{chain_hash}/info")))
        except Exception as e:
            errs.append(f"{r}: {e}")
    if len(got) < min_agree:
        raise DrandError(f"chain info: only {len(got)} relays answered (need {min_agree}): {errs}")
    keys = ("public_key", "period", "genesis_time", "hash", "groupHash", "schemeID")
    ref = {k: got[0][1].get(k) for k in keys}
    for r, i in got[1:]:
        if {k: i.get(k) for k in keys} != ref:
            raise DrandError(f"chain info: {r} disagrees with {got[0][0]}")
    info = got[0][1]
    if info.get("hash") != chain_hash:
        raise DrandError(f"chain info: hash member {info.get('hash')} != {chain_hash}")
    if chain_hash_of(info) != chain_hash:
        raise DrandError("chain info: SHA-256 of (period, genesis, public key, group hash, beacon id) "
                         f"is {chain_hash_of(info)}, not {chain_hash}")
    info = dict(info)
    info["_relays"] = [r for r, _ in got]
    return info


def round_time(info: dict, rnd: int) -> int:
    """Unix time at which round `rnd` is produced."""
    if rnd < 1:
        raise DrandError("rounds start at 1")
    return int(info["genesis_time"]) + (rnd - 1) * int(info["period"])


def round_at(info: dict, t: int) -> int:
    """First round produced at or after unix time t. Equals floor((t - genesis)/period) + 1 when t is on a
    period boundary (the formula of the TapeCode-Test1 profile); otherwise it is one more."""
    g, p = int(info["genesis_time"]), int(info["period"])
    if t <= g:
        return 1
    return -(-(t - g) // p) + 1


def parse_utc(s: str) -> int:
    s = s.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return calendar.timegm(time.strptime(s, fmt))
        except ValueError:
            pass
    raise DrandError(f"cannot parse UTC time {s!r} (use 2026-10-31T12:00:00Z)")


def utc(t: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def check_beacon(b: dict, rnd: int) -> None:
    """Offline checks of one beacon object (round, sizes, randomness == SHA-256(signature))."""
    if int(b.get("round", -1)) != rnd:
        raise DrandError(f"beacon round {b.get('round')} != {rnd}")
    sig = bytes.fromhex(b["signature"])
    rand = bytes.fromhex(b["randomness"])
    if len(rand) != 32:
        raise DrandError("randomness is not 32 bytes")
    if len(sig) != 48:
        raise DrandError(f"signature is {len(sig)} bytes; quicknet (bls-unchained-g1-rfc9380) uses 48")
    if hashlib.sha256(sig).digest() != rand:
        raise DrandError("randomness != SHA-256(signature)")


def fetch_beacon(rnd: int, chain_hash: str = QUICKNET, relays: list = None, min_agree: int = 2,
                 info: dict = None, now: float = None) -> dict:
    """Fetch round `rnd` from the relays and verify it. Returns a beacon record (see save format)."""
    info = info or fetch_info(chain_hash, relays, min_agree)
    t = round_time(info, rnd)
    now = time.time() if now is None else now
    if t > now:
        raise DrandError(f"round {rnd} is produced at {utc(t)}, which is in the future")
    relays = relays or RELAYS
    got, errs = [], []
    for r in relays:
        try:
            b = _get(f"{r}/{chain_hash}/public/{rnd}")
            check_beacon(b, rnd)
            got.append((r, b))
        except Exception as e:
            errs.append(f"{r}: {e}")
    if len(got) < min_agree:
        raise DrandError(f"round {rnd}: only {len(got)} relays returned a valid beacon (need {min_agree}): {errs}")
    sig = got[0][1]["signature"]
    for r, b in got[1:]:
        if b["signature"] != sig:
            raise DrandError(f"round {rnd}: {r} returned a different signature than {got[0][0]}")
    b = got[0][1]
    return {"chainHash": chain_hash, "round": rnd, "randomness": b["randomness"], "signature": sig,
            "producedAt": utc(t), "schemeID": info.get("schemeID"), "publicKey": info["public_key"],
            "verified": {"randomnessIsSha256OfSignature": True, "chainHashMatchesInfo": True,
                         "relaysAgreeing": [r for r, _ in got], "relayErrors": errs, "blsSignature": False}}


def load_beacon(path: str, chain_hash: str, rnd: int) -> dict:
    """Load a saved beacon and re-run the offline checks against the manifest's chain hash and round."""
    with open(path, "rb") as f:
        b = json.loads(f.read())
    if b.get("chainHash") != chain_hash:
        raise DrandError(f"{path}: chainHash {b.get('chainHash')} != manifest {chain_hash}")
    check_beacon(b, rnd)
    return b


def get_beacon(chain_hash: str, rnd: int, beacon_file: str = None, relays: list = None, min_agree: int = 2) -> dict:
    return load_beacon(beacon_file, chain_hash, rnd) if beacon_file else fetch_beacon(rnd, chain_hash, relays, min_agree)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chain", default=QUICKNET, help="chain hash (default: quicknet)")
    ap.add_argument("--relay", action="append", help="relay base URL (repeatable; default: drand + cloudflare)")
    ap.add_argument("--min-agree", type=int, default=2)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    s = sub.add_parser("round-at")
    s.add_argument("time", help="UTC, e.g. 2026-10-31T12:00:00Z")
    s = sub.add_parser("fetch")
    s.add_argument("round", type=int)
    s.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        info = fetch_info(a.chain, a.relay, a.min_agree)
        if a.cmd == "info":
            print(json.dumps({k: v for k, v in info.items()}, indent=1))
            print(f"chain hash verified; genesis {utc(int(info['genesis_time']))}, period {info['period']} s, "
                  f"latest round now {round_at(info, int(time.time())) - 1}")
        elif a.cmd == "round-at":
            t = parse_utc(a.time)
            r = round_at(info, t)
            print(json.dumps({"chainHash": a.chain, "round": r, "producedAt": utc(round_time(info, r)),
                              "target": utc(t), "genesis_time": info["genesis_time"], "period": info["period"]}))
        else:
            b = fetch_beacon(a.round, a.chain, a.relay, a.min_agree, info=info)
            print(json.dumps(b, indent=1))
            if a.out:
                write_bytes(a.out, compact(b))
                print("wrote", a.out)
    except DrandError as e:
        print("error:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
