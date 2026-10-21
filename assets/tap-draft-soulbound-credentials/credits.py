"""Reference implementation for the TAP draft "Design Credits and Lineage for TapeOut Netlists".

MIT licence. Pure Python 3.9+, standard library only. It contains its own keccak-256
and secp256k1 (RFC 6979 signing, public-key recovery) because neither is in the
standard library; test_credits.py cross-checks both against pycryptodome, eth_keys and
eth_account when they are installed. The structural hash comes from canon.py (copied
unchanged from the TAP-721 family, together with tapnft.py and tap02_reference.py).

What is here:
  * keccak256, secp256k1 sign / recover, Ethereum addresses;
  * EIP-712 encoding of the Credit, Lineage and Revocation statements (§4);
  * statement validation (including the Unicode 15.1.0 character table of §4.4) and
    verification: ecrecover, or ERC-1271 through an injected reader at the verification
    block, with an injected TapeOut-container resolver for the label of §4.6;
  * revocations, judged at one verification block for contract signers (§4.7);
  * publication-fact verification from recorded chain reads, with receipt normalisation
    and the chain's finality tag (§3.2);
  * design hashes of an on-chain circuit and the `applies` relation (§3.3, §4.4);
  * earliest-known-occurrence statements: order, judging, standing sets (§3.4);
  * anchors (§5.2) and the display model of §6 (groups, order, the §6.5 mark, labels).
Network access is not implemented here: callers pass recorded reads (fetch_reads.py).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata

import canon
import tapnft

# ---------------------------------------------------------------------------
# keccak-256 (the pre-standard Keccak padding used by Ethereum, not SHA3-256)
# ---------------------------------------------------------------------------

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M64 = (1 << 64) - 1


def _rol(v: int, n: int) -> int:
    return ((v << n) | (v >> (64 - n))) & _M64 if n else v


def _keccak_f(a: list) -> list:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        a = [a[i] ^ d[i % 5] for i in range(25)]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(a[x + 5 * y], _ROT[x][y])
        a = [b[i] ^ ((~b[(i % 5 + 1) % 5 + 5 * (i // 5)]) & b[(i % 5 + 2) % 5 + 5 * (i // 5)]) for i in range(25)]
        a[0] ^= rc
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data)
    msg.append(0x01)
    while len(msg) % rate:
        msg.append(0)
    msg[-1] |= 0x80
    st = [0] * 25
    for off in range(0, len(msg), rate):
        for i in range(rate // 8):
            st[i] ^= int.from_bytes(msg[off + 8 * i: off + 8 * i + 8], "little")
        st = _keccak_f(st)
    return b"".join(st[i].to_bytes(8, "little") for i in range(4))


# ---------------------------------------------------------------------------
# secp256k1
# ---------------------------------------------------------------------------

P = 2 ** 256 - 2 ** 32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    if p1[0] == p2[0]:
        if (p1[1] + p2[1]) % P == 0:
            return None
        lam = 3 * p1[0] * p1[0] * pow(2 * p1[1], -1, P) % P
    else:
        lam = (p2[1] - p1[1]) * pow(p2[0] - p1[0], -1, P) % P
    x = (lam * lam - p1[0] - p2[0]) % P
    return (x, (lam * (p1[0] - x) - p1[1]) % P)


def _mul(k: int, pt):
    acc = None
    while k:
        if k & 1:
            acc = _add(acc, pt)
        pt = _add(pt, pt)
        k >>= 1
    return acc


def address_of_pub(pub) -> str:
    return "0x" + keccak256(pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big"))[12:].hex()


def address_of_key(priv: int) -> str:
    return address_of_pub(_mul(priv, G))


def _rfc6979_k(priv: int, h: bytes) -> int:
    xb = priv.to_bytes(32, "big")
    hb = (int.from_bytes(h, "big") % N).to_bytes(32, "big")
    v, k = b"\x01" * 32, b"\x00" * 32
    k = hmac.new(k, v + b"\x00" + xb + hb, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    k = hmac.new(k, v + b"\x01" + xb + hb, hashlib.sha256).digest()
    v = hmac.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N:
            return cand
        k = hmac.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac.new(k, v, hashlib.sha256).digest()


def sign(priv: int, h: bytes) -> bytes:
    """Deterministic (RFC 6979, SHA-256) low-s signature r ‖ s ‖ v with v in {27, 28}."""
    z = int.from_bytes(h, "big")
    k = _rfc6979_k(priv, h)
    rp = _mul(k, G)
    r = rp[0] % N
    s = pow(k, -1, N) * (z + r * priv) % N
    rec = (rp[1] & 1) | (2 if rp[0] >= N else 0)
    if s > N // 2:
        s, rec = N - s, rec ^ 1
    assert r and s and rec < 2
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([27 + rec])


class SigError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def recover(h: bytes, sig: bytes) -> str:
    """Recover the signer address under the rules of §4.6 item 1, or raise SigError."""
    if len(sig) != 65:
        raise SigError("bad-signature-length")
    r = int.from_bytes(sig[0:32], "big")
    s = int.from_bytes(sig[32:64], "big")
    v = sig[64]
    if v not in (0, 1, 27, 28):
        raise SigError("bad-v")
    if not (1 <= r < N) or not (1 <= s < N):
        raise SigError("bad-r-s")
    if s > N // 2:
        raise SigError("high-s")
    rec = v - 27 if v >= 27 else v
    x = r
    y2 = (pow(x, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if y * y % P != y2:
        raise SigError("bad-r-s")
    if (y & 1) != rec:
        y = P - y
    rinv = pow(r, -1, N)
    z = int.from_bytes(h, "big")
    q = _add(_mul(s * rinv % N, (x, y)), _mul((-z * rinv) % N, G))
    if q is None:
        raise SigError("bad-r-s")
    return address_of_pub(q)


# ---------------------------------------------------------------------------
# EIP-712 (§4.2, §4.3)
# ---------------------------------------------------------------------------

DOMAIN_NAME = "TAP Design Credits"
DOMAIN_VERSION = "1"

TYPES = {
    "EIP712Domain": [("name", "string"), ("version", "string")],
    "DesignRef": [("netlistHash", "bytes32"), ("structuralHash", "bytes32")],
    "Circuit": [("chainId", "uint256"), ("processor", "address"), ("circuitId", "uint256")],
    "Credit": [
        ("signer", "address"), ("signerChainId", "uint256"), ("subject", "DesignRef"), ("source", "Circuit"),
        ("role", "string"), ("displayName", "string"), ("noteURI", "string"), ("noteSha256", "bytes32"),
        ("license", "string"), ("issuedAt", "uint64"), ("nonce", "bytes32"),
    ],
    "Lineage": [
        ("signer", "address"), ("signerChainId", "uint256"), ("subject", "DesignRef"), ("relation", "string"),
        ("object", "DesignRef"), ("reason", "string"), ("issuedAt", "uint64"), ("nonce", "bytes32"),
    ],
    "Revocation": [
        ("signer", "address"), ("signerChainId", "uint256"), ("statement", "bytes32"), ("reason", "string"),
        ("issuedAt", "uint64"),
    ],
}
PRIMARY = ("Credit", "Lineage", "Revocation")


def _deps(t: str, acc: set) -> set:
    for _, ft in TYPES[t]:
        if ft in TYPES and ft not in acc:
            acc.add(ft)
            _deps(ft, acc)
    return acc


def encode_type(t: str) -> str:
    def one(n):
        return n + "(" + ",".join(f"{ft} {fn}" for fn, ft in TYPES[n]) + ")"
    deps = sorted(_deps(t, set()) - {t})
    return one(t) + "".join(one(d) for d in deps)


def type_hash(t: str) -> bytes:
    return keccak256(encode_type(t).encode())


def _hex(v: str, n: int) -> bytes:
    if not isinstance(v, str) or not re.fullmatch(r"0x[0-9a-f]{%d}" % (2 * n), v):
        raise ValueError(f"expected 0x + {2 * n} lowercase hex digits")
    return bytes.fromhex(v[2:])


def _uint(v, bits: int) -> int:
    if isinstance(v, bool):
        raise ValueError("not an integer")
    if isinstance(v, str):
        if not re.fullmatch(r"0|[1-9][0-9]*", v):
            raise ValueError("bad decimal string")
        v = int(v)
    if not isinstance(v, int) or v < 0 or v >= 1 << bits:
        raise ValueError("integer out of range")
    return v


def _enc_value(ft: str, v) -> bytes:
    if ft == "string":
        if not isinstance(v, str):
            raise ValueError("expected string")
        return keccak256(v.encode("utf-8"))
    if ft == "bytes32":
        return _hex(v, 32)
    if ft == "address":
        return b"\x00" * 12 + _hex(v, 20)
    if ft.startswith("uint"):
        return _uint(v, int(ft[4:])).to_bytes(32, "big")
    if ft in TYPES:
        return hash_struct(ft, v)
    raise ValueError("unknown type " + ft)


def hash_struct(t: str, obj: dict) -> bytes:
    if not isinstance(obj, dict) or set(obj) != {fn for fn, _ in TYPES[t]}:
        raise ValueError(f"{t}: members must be exactly {[fn for fn, _ in TYPES[t]]}")
    return keccak256(type_hash(t) + b"".join(_enc_value(ft, obj[fn]) for fn, ft in TYPES[t]))


def domain_separator() -> bytes:
    return hash_struct("EIP712Domain", {"name": DOMAIN_NAME, "version": DOMAIN_VERSION})


def digest(t: str, message: dict) -> bytes:
    if t not in PRIMARY:
        raise ValueError("unknown statement type")
    return keccak256(b"\x19\x01" + domain_separator() + hash_struct(t, message))


# ---------------------------------------------------------------------------
# Statement rules (§4.4, §4.5)
# ---------------------------------------------------------------------------

ROLES = ("designer", "co-designer", "optimizer", "reviewer", "tester")
RELATIONS = ("derivedFrom", "supersedes", "optimizes")
ZERO32 = "0x" + "00" * 32
ZERO20 = "0x" + "00" * 20
MAX_ENVELOPE = 8192
MAX_SIGNATURE = 2048


class Invalid(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# §4.4: characters forbidden in displayName and reason. Control characters (general
# category Cc), plus every code point with the Unicode property Default_Ignorable_Code_Point
# or Bidi_Control, Unicode 15.1.0, copied from
#   https://www.unicode.org/Public/15.1.0/ucd/DerivedCoreProperties.txt (Default_Ignorable_Code_Point)
#   https://www.unicode.org/Public/15.1.0/ucd/PropList.txt (Bidi_Control)
# Bidi_Control is a subset of Default_Ignorable_Code_Point in 15.1.0; both are listed so that
# the table can be diffed against the source files. This excludes ZERO WIDTH JOINER and the
# variation selectors, so emoji ZWJ sequences and emoji presentation selectors are rejected.
UNICODE_VERSION = "15.1.0"
CONTROL_RANGES = [(0x0000, 0x001F), (0x007F, 0x009F)]
DEFAULT_IGNORABLE_RANGES = [
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C), (0x115F, 0x1160), (0x17B4, 0x17B5),
    (0x180B, 0x180D), (0x180E, 0x180E), (0x180F, 0x180F), (0x200B, 0x200F), (0x202A, 0x202E),
    (0x2060, 0x2064), (0x2065, 0x2065), (0x2066, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A),
    (0xE0000, 0xE0000), (0xE0001, 0xE0001), (0xE0002, 0xE001F), (0xE0020, 0xE007F), (0xE0080, 0xE00FF),
    (0xE0100, 0xE01EF), (0xE01F0, 0xE0FFF),
]
BIDI_CONTROL_RANGES = [(0x061C, 0x061C), (0x200E, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069)]
_FORBIDDEN_RANGES = CONTROL_RANGES + DEFAULT_IGNORABLE_RANGES + BIDI_CONTROL_RANGES


def forbidden_char(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _FORBIDDEN_RANGES)


def _text(v, max_bytes: int, where: str) -> None:
    if not isinstance(v, str):
        raise Invalid("bad-text", where)
    if len(v.encode("utf-8")) > max_bytes:
        raise Invalid("bad-text", f"{where} longer than {max_bytes} bytes")
    if unicodedata.normalize("NFC", v) != v:
        raise Invalid("bad-text", f"{where} not NFC")
    if any(forbidden_char(ord(ch)) for ch in v):
        raise Invalid("bad-text", f"{where} has a control, default-ignorable or bidirectional-control character")


def _ascii(v, max_bytes: int, where: str) -> None:
    if not isinstance(v, str) or len(v) > max_bytes or any(not (0x20 <= ord(c) <= 0x7E) for c in v):
        raise Invalid("bad-text", where)


def _design_ref(d, where: str) -> None:
    try:
        nh, sh = _hex(d["netlistHash"], 32), _hex(d["structuralHash"], 32)
    except (KeyError, TypeError, ValueError) as e:
        raise Invalid("bad-field", f"{where}: {e}")
    if set(d) != {"netlistHash", "structuralHash"}:
        raise Invalid("bad-field", where)
    if nh == bytes(32) and sh == bytes(32):
        raise Invalid("empty-subject", where)


def _signer_fields(m: dict) -> None:
    try:
        _hex(m["signer"], 20)
        if not isinstance(m["signerChainId"], int) or isinstance(m["signerChainId"], bool):
            raise ValueError("signerChainId must be a JSON integer")
        _uint(m["signerChainId"], 53)
        if not isinstance(m["issuedAt"], int) or isinstance(m["issuedAt"], bool):
            raise ValueError("issuedAt must be a JSON integer")
        _uint(m["issuedAt"], 53)
    except (KeyError, TypeError, ValueError) as e:
        raise Invalid("bad-field", str(e))
    if m["signer"] == ZERO20:
        raise Invalid("bad-field", "signer is zero")


def check_message(t: str, m: dict) -> None:
    """Field rules of §4.4; raises Invalid."""
    if t not in PRIMARY:
        raise Invalid("unknown-type", str(t))
    if not isinstance(m, dict) or set(m) != {fn for fn, _ in TYPES[t]}:
        raise Invalid("bad-field", f"{t}: wrong member set")
    _signer_fields(m)
    if t == "Credit":
        _design_ref(m["subject"], "subject")
        src = m["source"]
        if not isinstance(src, dict) or set(src) != {"chainId", "processor", "circuitId"}:
            raise Invalid("bad-source", "members")
        try:
            cid = _uint(src["circuitId"], 256)
            proc = _hex(src["processor"], 20)
            if not isinstance(src["chainId"], int) or isinstance(src["chainId"], bool):
                raise ValueError("chainId must be a JSON integer")
            ch = _uint(src["chainId"], 53)
            if not isinstance(src["circuitId"], str):
                raise ValueError("circuitId must be a decimal string")
        except ValueError as e:
            raise Invalid("bad-source", str(e))
        absent = ch == 0 and proc == bytes(20) and cid == 0
        if not absent and (ch == 0 or proc == bytes(20) or cid == 0):
            raise Invalid("bad-source", "partly zero")
        if m["role"] not in ROLES:
            raise Invalid("bad-role", repr(m["role"]))
        _text(m["displayName"], 64, "displayName")
        _ascii(m["noteURI"], 512, "noteURI")
        try:
            _hex(m["noteSha256"], 32)
            _hex(m["nonce"], 32)
        except ValueError as e:
            raise Invalid("bad-field", str(e))
        if (m["noteURI"] == "") != (m["noteSha256"] == ZERO32):
            raise Invalid("note-mismatch")
        _ascii(m["license"], 256, "license")
    elif t == "Lineage":
        _design_ref(m["subject"], "subject")
        _design_ref(m["object"], "object")
        if m["relation"] not in RELATIONS:
            raise Invalid("bad-relation", repr(m["relation"]))
        if _overlaps(m["subject"], m["object"]):
            raise Invalid("self-edge")
        _text(m["reason"], 280, "reason")
        try:
            _hex(m["nonce"], 32)
        except ValueError as e:
            raise Invalid("bad-field", str(e))
    else:
        try:
            _hex(m["statement"], 32)
        except ValueError as e:
            raise Invalid("bad-field", str(e))
        if m["statement"] == ZERO32:
            raise Invalid("bad-field", "statement is zero")
        _text(m["reason"], 280, "reason")


def _overlaps(a: dict, b: dict) -> bool:
    return any(a[k] != ZERO32 and a[k] == b[k] for k in ("netlistHash", "structuralHash"))


def parse_envelope(env) -> tuple:
    """Envelope rules of §4.1. Returns (type, message, signature bytes)."""
    if isinstance(env, (bytes, str)):
        raw = env.encode() if isinstance(env, str) else env
        if len(raw) > MAX_ENVELOPE:
            raise Invalid("bad-envelope", "too large")
        env = json.loads(raw)
    if not isinstance(env, dict) or set(env) != {"tapCredit", "type", "message", "signature"}:
        raise Invalid("bad-envelope", "members")
    if env["tapCredit"] != 1 or isinstance(env["tapCredit"], bool):
        raise Invalid("bad-envelope", "tapCredit")
    sig = env["signature"]
    if not isinstance(sig, str) or not re.fullmatch(r"0x([0-9a-f]{2})+", sig) or len(sig) > 2 + 2 * MAX_SIGNATURE:
        raise Invalid("bad-envelope", "signature")
    check_message(env["type"], env["message"])
    return env["type"], env["message"], bytes.fromhex(sig[2:])


# TAP-10 §2.1: chains and their finality tags. ERC-1271 checks (§4.6 item 4) and
# publication facts (§3.2) are made only on these chains.
FINALITY_TAG = {56: "finalized", 8453: "safe", 196: "safe"}


def container_label(name: str) -> str:
    """§4.6: the label a tool shows for a holder-following signer (a TapeOut container)."""
    return f"container of {name}; validity follows its holder"


def verify_statement(env, erc1271=None, container_of=None) -> dict:
    """§4.6. Result status: valid | invalid | unverified.

    `erc1271(chainId, signer, digest, signature, block=None)` returns None when the verifier
    cannot make the call, else (valid: bool, block: int). With block=None the reader calls
    isValidSignature at the verification block of §4.6 item 4 (the block of the chain's
    finality tag, agreed by two operators) and returns that block; with a block it calls
    at that block (used for anchors and for the §6.5 mark).
    `container_of(chainId, address, block)` returns the on-chain name N of the circuit whose
    TapeOut container `address` is (TAP-10 §4.3), or None."""
    try:
        t, m, sig = parse_envelope(env)
    except Invalid as e:
        return {"status": "invalid", "error": e.code}
    except (ValueError, TypeError) as e:
        return {"status": "invalid", "error": "bad-envelope", "detail": str(e)}
    d = digest(t, m)
    res = {"type": t, "digest": "0x" + d.hex(), "signer": m["signer"], "signerChainId": m["signerChainId"]}
    if m["signerChainId"] == 0:
        try:
            who = recover(d, sig)
        except SigError as e:
            return {**res, "status": "invalid", "error": e.code}
        if who != m["signer"]:
            return {**res, "status": "invalid", "error": "signer-mismatch", "recovered": who}
        return {**res, "status": "valid", "method": "ecrecover"}
    if m["signerChainId"] not in FINALITY_TAG:
        return {**res, "status": "unverified", "error": "erc1271-chain-unsupported"}
    got = erc1271(m["signerChainId"], m["signer"], d, sig) if erc1271 else None
    if got is None:
        return {**res, "status": "unverified", "error": "erc1271-unverified"}
    ok, block = got
    if container_of is not None:
        name = container_of(m["signerChainId"], m["signer"], block)
        if name is not None:
            res["container"] = name
            res["label"] = container_label(name)
    if not ok:
        return {**res, "status": "invalid", "error": "erc1271-invalid", "block": block}
    return {**res, "status": "valid", "method": "erc1271", "validAt": {"chainId": m["signerChainId"], "block": block}}


def recorded_erc1271(calls: list, verification_blocks: dict):
    """An erc1271 reader over recorded isValidSignature calls (test vectors).
    calls: [{"chainId", "account", "digest", "block", "result"}]; verification_blocks: {chainId: block}."""
    def reader(chain, account, d, sig, block=None):
        b = verification_blocks.get(str(chain)) if block is None else block
        if b is None:
            return None
        for c in calls:
            if (c["chainId"], c["account"], c["digest"], c["block"]) == (chain, account, "0x" + d.hex(), b):
                return c["result"][:10] == "0x1626ba7e", b
        return None
    return reader


def recorded_containers(table: dict):
    """A container_of resolver over a recorded table {"<chainId>:<address>": name}."""
    def resolve(chain, account, block):
        return table.get(f"{chain}:{account}")
    return resolve


def make_envelope(t: str, message: dict, priv: int) -> dict:
    """Test helper: sign a message with a (test) private key."""
    check_message(t, message)
    return {"tapCredit": 1, "type": t, "message": message, "signature": "0x" + sign(priv, digest(t, message)).hex()}


def apply_revocations(results: list, envelopes: list) -> list:
    """§4.7. `results[i]` is verify_statement(envelopes[i]). Returns one entry per statement
    with `state`: active | revoked | invalid | unverified | revocation | void-revocation |
    revocation-unjudged.

    For a contract signer (signerChainId != 0), the validity of a statement and of the
    Revocations that name it are judged at one verification block: a Revocation verified at
    another block, or one that could not be verified, leaves the target `unverified`
    (never `active`) and is itself `revocation-unjudged`."""
    out = []
    by_digest = {}
    for r, e in zip(results, envelopes):
        entry = {"digest": r.get("digest"), "type": r.get("type"), "state": r["status"] if r["status"] != "valid" else "active",
                 "result": r, "envelope": e}
        out.append(entry)
        if r["status"] == "valid":
            by_digest[r["digest"]] = entry
    for entry in out:
        r = entry["result"]
        if r.get("type") != "Revocation" or r["status"] == "invalid":
            continue
        target = by_digest.get(entry["envelope"]["message"]["statement"])
        if r["status"] == "unverified":
            # a contract-signed revocation that could not be judged
            if target is not None and target["result"]["type"] != "Revocation" and \
                    (target["result"]["signer"], target["result"]["signerChainId"]) == (r["signer"], r["signerChainId"]):
                entry["state"] = "revocation-unjudged"
                if target["state"] == "active":
                    target["state"] = "unverified"
                    target["reason"] = "revocation-not-judged"
            continue
        entry["state"] = "revocation"
        if target is None:
            continue  # pending: applies if the statement appears later
        tr = target["result"]
        if tr["type"] == "Revocation" or (tr["signer"], tr["signerChainId"]) != (r["signer"], r["signerChainId"]):
            entry["state"] = "void-revocation"
            continue
        if tr["signerChainId"] != 0 and tr.get("validAt") != r.get("validAt"):
            entry["state"] = "revocation-unjudged"
            if target["state"] == "active":
                target["state"] = "unverified"
                target["reason"] = "revocation-not-judged-at-same-block"
            continue
        target["state"] = "revoked"
        target["revokedBy"] = r["digest"]
    return out


# ---------------------------------------------------------------------------
# Facts (§3)
# ---------------------------------------------------------------------------

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TAPED_OUT_TOPIC = "0xc11215e417669c143c8a07aeb778034c0a0a85ebdf305d64a629b19a7a9ce031"
CREDIT_POSTED_TOPIC = "0x46f7d925bbc35e7f8caf9e4c0b850b7405b337d421079c498a73570c2758dfcb"  # CreditPosted(address,bytes32,bytes32,bytes)


def _word_addr(a: str) -> str:
    return "0x" + "00" * 12 + a[2:]


def _word_uint(n: int) -> str:
    return "0x" + n.to_bytes(32, "big").hex()


def check_publication_fact(f: dict) -> None:
    need = {"chainId", "processor", "circuitId", "publisher", "block", "blockHash", "txHash", "logIndex"}
    if not isinstance(f, dict) or not need <= set(f):
        raise Invalid("bad-fact", "members")
    allowed = need | {"name", "timestamp", "txFrom"}
    if set(f) - allowed:
        raise Invalid("bad-fact", "unknown member")
    try:
        _hex(f["processor"], 20)
        _hex(f["publisher"], 20)
        _hex(f["blockHash"], 32)
        _hex(f["txHash"], 32)
        _uint(f["circuitId"], 256)
        if not isinstance(f["circuitId"], str):
            raise ValueError("circuitId must be a decimal string")
        for k in ("chainId", "block", "logIndex") + (("timestamp",) if "timestamp" in f else ()):
            if not isinstance(f[k], int) or isinstance(f[k], bool) or f[k] < 0:
                raise ValueError(k)
        if "txFrom" in f:
            _hex(f["txFrom"], 20)
    except ValueError as e:
        raise Invalid("bad-fact", str(e))


def normalize_receipt(r: dict) -> str:
    """TAP-10 §5.2 normalisation of a receipt for comparison between nodes: only the fields
    §3.2 uses, as canonical JSON with keys sorted and strings lowercased."""
    keep = {"status": r["status"], "blockNumber": r["blockNumber"], "blockHash": r["blockHash"],
            "transactionHash": r["transactionHash"], "from": r["from"],
            "logs": [{"address": l["address"], "topics": l["topics"], "data": l["data"], "logIndex": l["logIndex"]}
                     for l in r["logs"]]}
    return json.dumps(_lower(keep), sort_keys=True, separators=(",", ":"))


def normalize_header(h: dict) -> str:
    return json.dumps(_lower({"number": h["number"], "hash": h["hash"], "timestamp": h["timestamp"]}),
                      sort_keys=True, separators=(",", ":"))


def _lower(x):
    if isinstance(x, str):
        return x.lower()
    if isinstance(x, list):
        return [_lower(v) for v in x]
    if isinstance(x, dict):
        return {k: _lower(v) for k, v in x.items()}
    return x


def verify_publication(f: dict, reads: dict, min_nodes: int = 2) -> dict:
    """§3.2 from recorded reads.

    reads = {"isCPU": {node: bool}, "receipt": {node: receipt}, "block": {node: header},
             "circuitInfo": {node: hex}, "stateBlock": int (the block of the isCPU, cpuAt and
             circuitInfo reads), "finalityTag": str, "finalityBlock": {node: int},
             optional "cpuAt": {node: addr}, "processorNumber": int, "areaCode": int|None}
    Nodes are keyed by URL; nodes of different operators are expected.
    Returns {"status": "verified"|"failed"|"unfinalized", "checks": [...], "error"?}."""
    checks = []

    def fail(code, detail=""):
        return {"status": "failed", "error": code, "detail": detail, "checks": checks}

    try:
        check_publication_fact(f)
    except Invalid as e:
        return fail(e.code, str(e))
    if f["chainId"] not in FINALITY_TAG:
        return fail("unsupported-chain")
    if reads.get("finalityTag") != FINALITY_TAG[f["chainId"]]:
        return fail("wrong-finality-tag", str(reads.get("finalityTag")))
    sb = reads.get("stateBlock")
    if not isinstance(sb, int) or sb < f["block"]:
        return fail("bad-state-block", "isCPU, cpuAt and circuitInfo must be read at or after block")
    fin = reads.get("finalityBlock", {})
    if len(fin) < min_nodes:
        return fail("too-few-nodes", "finality")
    # step 1: processor registered with the factory (read at stateBlock)
    vals = reads.get("isCPU", {})
    if len(vals) < min_nodes or not all(vals.values()):
        return fail("not-a-processor")
    checks.append("isCPU")
    # step 2: receipt agreement and block identity
    recs = reads.get("receipt", {})
    if len(recs) < min_nodes:
        return fail("too-few-nodes", "receipt")
    norm = {normalize_receipt(r) for r in recs.values()}
    if len(norm) != 1:
        return fail("nodes-disagree", "receipt")
    first = json.loads(norm.pop())
    if first["status"] != "0x1" or first["transactionHash"] != f["txHash"]:
        return fail("bad-receipt")
    if int(first["blockNumber"], 16) != f["block"] or first["blockHash"] != f["blockHash"]:
        return fail("block-mismatch")
    heads = reads.get("block", {})
    if len(heads) < min_nodes or len({normalize_header(h) for h in heads.values()}) != 1:
        return fail("block-mismatch", "header")
    head = json.loads(normalize_header(next(iter(heads.values()))))
    if head["hash"] != f["blockHash"] or int(head["number"], 16) != f["block"]:
        return fail("block-mismatch", "header")
    checks.append("receipt")
    # step 3: the mint log
    mint = [l for l in first["logs"] if l["address"] == f["processor"] and len(l["topics"]) == 4
            and l["topics"][0] == TRANSFER_TOPIC and l["topics"][1] == ZERO32
            and l["topics"][3] == _word_uint(int(f["circuitId"]))]
    if len(mint) != 1:
        return fail("no-mint-log")
    if int(mint[0]["logIndex"], 16) != f["logIndex"] or mint[0]["topics"][2] != _word_addr(f["publisher"]):
        return fail("publisher-mismatch")
    checks.append("mintLog")
    # corroboration (not required): TapedOut(id, publisher, ., .)
    tap = [l for l in first["logs"] if l["address"] == f["processor"] and len(l["topics"]) >= 3
           and l["topics"][0] == TAPED_OUT_TOPIC and l["topics"][1] == _word_uint(int(f["circuitId"]))]
    if tap and tap[0]["topics"][2] == _word_addr(f["publisher"]):
        checks.append("tapedOutLog")
    # step 4: circuit exists (read at stateBlock >= block)
    infos = reads.get("circuitInfo", {})
    if len(infos) < min_nodes or len(set(infos.values())) != 1:
        return fail("circuit-missing")
    checks.append("circuitInfo")
    # step 5: timestamp and txFrom
    if "timestamp" in f:
        if int(head["timestamp"], 16) != f["timestamp"]:
            return fail("timestamp-mismatch")
        checks.append("timestamp")
    if "txFrom" in f:
        if first["from"] != f["txFrom"]:
            return fail("txfrom-mismatch")
        checks.append("txFrom")
    # step 6: name
    if "name" in f:
        cpu = reads.get("cpuAt", {})
        num = reads.get("processorNumber")
        if len(cpu) < min_nodes or any(a != f["processor"] for a in cpu.values()) or num is None:
            return fail("name-mismatch", "processor number")
        if f["name"] != tapnft.tape_name(int(f["circuitId"]), num, reads.get("areaCode")):
            return fail("name-mismatch")
        checks.append("name")
    # step 7: at or below the block of the chain's finality tag on every node used
    if min(fin.values()) < f["block"]:
        return {"status": "unfinalized", "checks": checks}
    checks.append("finalityTag")
    return {"status": "verified", "checks": checks}


def design_of(netlist: bytes, n_in: int, n_out: int) -> dict:
    """§3.3: the netlist hash and (for a REF-free circuit) the structural hash of a circuit."""
    try:
        f = tapnft.file_from_chain(netlist, n_in, n_out)  # raises Invalid for REF records
    except tapnft.Invalid:
        return {"netlistHash": None, "structuralHash": None}
    return {"netlistHash": tapnft.hex32(tapnft.netlist_hash(f)),
            "structuralHash": tapnft.hex32(canon.structural_hash(f))}


def applies(ref: dict, design: dict) -> bool:
    """§3.3: a DesignRef applies to a circuit (or file) iff every non-zero hash in it equals the
    corresponding hash of the circuit's design. A circuit without a design matches nothing.
    Used for publication facts "of design D" (§3.3), `source` (§4.4) and the mark of §6.5."""
    if design.get("netlistHash") is None:
        return False
    return all(ref[k] == ZERO32 or ref[k] == design.get(k) for k in ("netlistHash", "structuralHash"))


check_subject = applies  # name used by earlier drafts


def consistent_with_file(ref: dict, file_design: dict):
    """§4.4: if a DesignRef gives both hashes and the tool has the netlist file whose SHA-256 is
    the netlist hash (file_design = design_of(that file)), the structural hash MUST be that file's.
    Returns True or False, or None when the rule does not apply (one hash only, or another file)."""
    if ref["netlistHash"] == ZERO32 or ref["structuralHash"] == ZERO32:
        return None
    if file_design.get("netlistHash") != ref["netlistHash"]:
        return None
    return file_design.get("structuralHash") == ref["structuralHash"]


class Incomparable(ValueError):
    """Two facts on different chains, one of whose block-header timestamps is not known."""


def header_timestamp(fact: dict, header_ts=None):
    """The timestamp of the header of fact's block (§3.4). `header_ts` maps (chainId, block)
    to a header timestamp read under §3.2 step 2. A verified fact's `timestamp` member equals
    that header's (§3.2 step 5), so it is used when no header read is supplied."""
    if header_ts is not None and (fact["chainId"], fact["block"]) in header_ts:
        return header_ts[(fact["chainId"], fact["block"])]
    if "timestamp" in fact:
        return fact["timestamp"]
    raise Incomparable(f"no header timestamp for chain {fact['chainId']} block {fact['block']}")


def precedes(a: dict, b: dict, header_ts=None):
    """§3.4 order of two publication facts: True, False, or None (tied across chains).
    Raises Incomparable when a cross-chain comparison lacks a header timestamp."""
    if a["chainId"] == b["chainId"]:
        return (a["block"], a["logIndex"]) < (b["block"], b["logIndex"])
    ta, tb = header_timestamp(a, header_ts), header_timestamp(b, header_ts)
    if ta == tb:
        return None
    return ta < tb


def _nonneg_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 1 << 53


def check_earliest(s: dict) -> None:
    """Form of an earliest-occurrence statement (§3.4), including that the occurrence lies
    within some scope entry by chain and block (its processor number is checked by
    judge_earliest)."""
    if not isinstance(s, dict) or set(s) - {"tapEarliest", "key", "occurrence", "scope", "indexer", "asOf"} \
            or not {"tapEarliest", "key", "occurrence", "scope"} <= set(s) or s["tapEarliest"] != 1 \
            or isinstance(s["tapEarliest"], bool):
        raise Invalid("bad-earliest", "members")
    k = s["key"]
    if not isinstance(k, dict) or set(k) != {"kind", "hash"} or k["kind"] not in ("netlist", "structural"):
        raise Invalid("bad-earliest", "key")
    try:
        _hex(k["hash"], 32)
    except ValueError:
        raise Invalid("bad-earliest", "key hash")
    if "indexer" in s:
        _ascii(s["indexer"], 256, "indexer")
    if "asOf" in s and not isinstance(s["asOf"], str):
        raise Invalid("bad-earliest", "asOf")
    check_publication_fact(s["occurrence"])
    if "timestamp" not in s["occurrence"]:
        raise Invalid("bad-earliest", "occurrence needs timestamp")
    if not isinstance(s["scope"], list) or not s["scope"]:
        raise Invalid("bad-earliest", "scope")
    for e in s["scope"]:
        if not isinstance(e, dict) or set(e) != {"chainId", "processors", "toBlock"} \
                or not _nonneg_int(e["chainId"]) or not _nonneg_int(e["toBlock"]):
            raise Invalid("bad-earliest", "scope entry")
        p = e["processors"]
        if p != "all" and (not isinstance(p, list) or not p or any(not _nonneg_int(x) for x in p)
                           or len(set(p)) != len(p)):
            raise Invalid("bad-earliest", "scope processors")
    occ = s["occurrence"]
    if not any(e["chainId"] == occ["chainId"] and e["toBlock"] >= occ["block"] for e in s["scope"]):
        raise Invalid("bad-earliest", "occurrence outside scope")



def check_bundle(b: dict, standalone: bool) -> None:
    """Form of a credit bundle (§5.1): a standalone file must carry tapCreditBundle = 1;
    in tap.credits it is optional but must be 1 when present. Members it does not know are
    ignored; the facts and statements inside are verified separately."""
    if not isinstance(b, dict):
        raise Invalid("bad-bundle", "not an object")
    if "tapCreditBundle" in b:
        m = b["tapCreditBundle"]
        if m != 1 or isinstance(m, bool) or not isinstance(m, int):
            raise Invalid("bad-bundle", "tapCreditBundle must be 1")
    elif standalone:
        raise Invalid("bad-bundle", "standalone file needs tapCreditBundle")
    if b.get("v") != 1 or isinstance(b.get("v"), bool) or not isinstance(b.get("v"), int):
        raise Invalid("bad-bundle", "v must be 1")
    for k in ("publications", "earliest", "statements", "anchors"):
        if k in b and not isinstance(b[k], list):
            raise Invalid("bad-bundle", k)

def in_scope(s: dict, fact: dict, processor_number):
    """§3.4: True, False, or None when the processor number is unknown and only a scope entry
    that lists processors could contain the fact."""
    unknown = False
    for e in s["scope"]:
        if e["chainId"] != fact["chainId"] or fact["block"] > e["toBlock"]:
            continue
        if e["processors"] == "all":
            return True
        if processor_number is None:
            unknown = True
        elif processor_number in e["processors"]:
            return True
    return None if unknown else False


def judge_earliest(s: dict, occurrence_ok: bool, occurrence_design: dict, others: list,
                   occurrence_number=None, header_ts=None) -> dict:
    """§3.4. `occurrence_ok`: §3.2 verified for s.occurrence; `occurrence_design`: design_of
    the occurrence's circuit; `occurrence_number`: its processor number (None if unknown).
    `others`: list of (fact, verified: bool, design, processorNumber or None) known to the tool.
    Returns {"status": standing|refuted|superseded|invalid, ...}. A standing result lists in
    `tiedWith` the known facts of the design that are tied with the occurrence and have no
    known predecessor; `incomparable` lists facts that could not be ordered (no header
    timestamp); `scopeUnknown` lists earlier facts whose processor number was unknown (they
    are counted as outside the scope, so they supersede rather than refute)."""
    try:
        check_earliest(s)
    except Invalid as e:
        return {"status": "invalid", "error": e.code}
    key = "structuralHash" if s["key"]["kind"] == "structural" else "netlistHash"
    if not occurrence_ok:
        return {"status": "invalid", "error": "occurrence-not-verified"}
    if occurrence_design.get(key) != s["key"]["hash"]:
        return {"status": "invalid", "error": "occurrence-other-design"}
    inside = in_scope(s, s["occurrence"], occurrence_number)
    if inside is None:
        return {"status": "invalid", "error": "occurrence-processor-unknown"}
    if not inside:
        return {"status": "invalid", "error": "occurrence-outside-scope"}
    occ = s["occurrence"]
    same = [(f, n) for f, ok, d, n in others
            if ok and d.get(key) == s["key"]["hash"] and f is not occ and not _same_fact(f, occ)]
    earlier_in, earlier_out, tied, incomparable, unknown = [], [], [], [], []
    for fact, num in same:
        try:
            p = precedes(fact, occ, header_ts)
        except Incomparable:
            incomparable.append(fact)
            continue
        if p is None:
            tied.append(fact)
        elif p:
            where = in_scope(s, fact, num)
            if where is None:
                unknown.append(fact)
            (earlier_in if where else earlier_out).append(fact)

    def earliest(fs):
        best = fs[0]
        for f in fs[1:]:
            try:
                if precedes(f, best, header_ts):
                    best = f
            except Incomparable:
                pass
        return best

    extra = {}
    if incomparable:
        extra["incomparable"] = incomparable
    if unknown:
        extra["scopeUnknown"] = unknown
    if earlier_in:
        return {"status": "refuted", "by": earliest(earlier_in), **extra}
    if earlier_out:
        return {"status": "superseded", "by": earliest(earlier_out), **extra}

    def has_predecessor(t):
        for f, _ in same + [(occ, occurrence_number)]:
            if f is t:
                continue
            try:
                if precedes(f, t, header_ts):
                    return True
            except Incomparable:
                pass
        return False
    return {"status": "standing", "tiedWith": [t for t in tied if not has_predecessor(t)], **extra}


def _same_fact(a: dict, b: dict) -> bool:
    return (a["chainId"], a["processor"], a["circuitId"]) == (b["chainId"], b["processor"], b["circuitId"])


def subject_key(t: str, message: dict, revoked: tuple = None) -> str:
    """Informative §5.2: the `subjectKey` topic for discovery: the subject's netlist hash if
    non-zero, else its structural hash. A Revocation has no subject: its key is that of the
    statement it revokes, given as revoked = (type, message), or zero."""
    if t == "Revocation":
        return subject_key(*revoked) if revoked else ZERO32
    subj = message["subject"]
    return subj["netlistHash"] if subj["netlistHash"] != ZERO32 else subj["structuralHash"]


def check_anchor(log: dict, envelope_bytes: bytes) -> dict:
    """§5.2: a CreditPosted(address,bytes32,bytes32,bytes) log anchors a statement if its digest
    topic equals the digest recomputed from the posted bytes and the statement verifies
    (checked by the caller). The subjectKey topic is a discovery hint and is not checked."""
    if len(log["topics"]) != 4 or log["topics"][0] != CREDIT_POSTED_TOPIC:
        return {"status": "no-anchor", "error": "not-credit-posted"}
    try:
        t, m, _ = parse_envelope(envelope_bytes)
    except (Invalid, ValueError) as e:
        return {"status": "no-anchor", "error": getattr(e, "code", "bad-envelope")}
    d = "0x" + digest(t, m).hex()
    if d != log["topics"][2]:
        return {"status": "no-anchor", "error": "digest-mismatch"}
    return {"status": "anchor", "digest": d}


# ---------------------------------------------------------------------------
# Display model (§6)
# ---------------------------------------------------------------------------

def first_publisher_mark(entry: dict, publication: dict, design: dict, erc1271=None) -> bool:
    """§6.5: may a claim be marked "signed by the first publisher of N" for this verified
    publication fact (with `design` = design of its circuit)? Only if the claim's subject
    applies to the circuit, the signer equals the publisher, and either the signer is an
    EOA (signerChainId 0) or it is a contract on the fact's chain whose isValidSignature
    accepted the statement at the publication block."""
    m = entry["envelope"]["message"]
    if not applies(m["subject"], design) or m["signer"] != publication["publisher"]:
        return False
    if m["signerChainId"] == 0:
        return True
    if m["signerChainId"] != publication["chainId"] or erc1271 is None:
        return False
    sig = bytes.fromhex(entry["envelope"]["signature"][2:])
    got = erc1271(m["signerChainId"], m["signer"], bytes.fromhex(entry["digest"][2:]), sig, publication["block"])
    return bool(got) and got[0] is True and got[1] == publication["block"]


def credit_order(entries: list, publications: list, anchors: dict, erc1271=None) -> list:
    """§6.4: order active Credit entries for one design.
    entries: apply_revocations() items of type Credit with state active.
    publications: [{"fact": verified publication fact, "design": its circuit's design}] shown.
    anchors: digest -> anchor timestamp (verified CreditPosted).

    Within each role (order of §4.5): anchored claims, earliest anchor first; then unanchored
    claims; then claims whose signer is a TapeOut container, unranked. The order inside the
    unanchored and container groups is unspecified by the TAP; this reference implementation
    uses the statement id so that its output is reproducible. The §6.5 mark does not affect
    the order."""
    def marks(e):
        return [p["fact"] for p in publications if first_publisher_mark(e, p["fact"], p["design"], erc1271)]

    def group(e):
        if e["result"].get("container"):
            return 2
        return 0 if e["digest"] in anchors else 1

    def key(e):
        m = e["envelope"]["message"]
        g = group(e)
        return (ROLES.index(m["role"]), g, anchors.get(e["digest"], 0) if g == 0 else 0, e["digest"])

    out = []
    for e in sorted(entries, key=key):
        m = e["envelope"]["message"]
        out.append({"digest": e["digest"], "role": m["role"], "signer": m["signer"],
                    "signerChainId": m["signerChainId"],
                    "group": ("anchored", "unanchored", "container")[group(e)],
                    "label": e["result"].get("label"),
                    "badge": [p.get("name") or f"{p['processor']}#{p['circuitId']}" for p in marks(e)],
                    "anchored": anchors.get(e["digest"])})
    return out


def render_credit(item: dict, display_name: str) -> str:
    """One display line for a credit claim under §6.2 (informative wording)."""
    who = item["signer"] + (f" (contract on chain {item['signerChainId']})" if item["signerChainId"] else "")
    line = f"[claim] {item['role']}, claimed by {who}"
    if item.get("label"):
        line += f" [{item['label']}]"
    if display_name:
        line += f", self-declared name \"{display_name}\""
    for b in item["badge"]:
        line += f" — signed by the first publisher of {b} (not proof of authorship)"
    return line


def render_publication(f: dict, status: str) -> str:
    """One display line for a publication fact under §6.1 (informative wording)."""
    label = "[verified fact]" if status == "verified" else f"[{status}, not verified]"
    name = f.get("name") or f"{f['processor']}#{f['circuitId']}"
    return f"{label} {name} first taped out by {f['publisher']} on chain {f['chainId']} at block {f['block']}"


def render_earliest(s: dict, judged: dict) -> str:
    occ = s["occurrence"]
    name = occ.get("name") or f"{occ['processor']}#{occ['circuitId']}"
    scope = "; ".join(f"chain {e['chainId']} processors {e['processors']} to block {e['toBlock']}" for e in s["scope"])
    if judged["status"] == "standing":
        return f"[earliest known, refutable] {name} at block {occ['block']} (scope: {scope})"
    if judged["status"] in ("refuted", "superseded"):
        by = judged["by"]
        return f"[{judged['status']}] earlier occurrence {by.get('name') or by['circuitId']} at block {by['block']} precedes {name}"
    return "[invalid earliest-occurrence statement]"
