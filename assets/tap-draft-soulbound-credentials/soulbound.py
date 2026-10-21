"""Reference implementation for the TAP draft "Soulbound Netlist Credentials".

MIT licence. Pure Python 3.9+, standard library only. keccak-256 and secp256k1 come from
credits.py, the netlist file check from tapnft.py and the structural labels from canon.py
(all copied unchanged from the Design Credits draft and the TAP-721 family).

Contents, in the order of the Specification:
  §3  credential kinds, subjects and statuses (constants)
  §4  proven credentials: truth tables (§4.2), design keys (§4.3), specifications, their
      ids and work bounds (§4.4), commitments (§4.5), the issuance checks (§4.6)
  §5  attested credentials and rebinding: EIP-712 types, digests, signature checks
  §6  claimed credentials: claim scopes, Design Credits statements carried by a claim
  §8  the on-chain interfaces: selectors, ERC-165 ids, event topics
  §9  token metadata: the `tap.credential` member
  §10 display labels
  An executable model of the reference contract (Issuer) produces the scenario vectors.
"""
from __future__ import annotations

import hashlib
import re

import canon
import credits
import tap02_reference as tap02
import tapnft

keccak256 = credits.keccak256


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def u8(x: int) -> bytes:
    return x.to_bytes(1, "big")


def u32be(x: int) -> bytes:
    return x.to_bytes(4, "big")


def u64be(x: int) -> bytes:
    return x.to_bytes(8, "big")


def addr(a: str) -> bytes:
    if not re.fullmatch(r"0x[0-9a-f]{40}", a):
        raise ValueError("address must be 0x + 40 lowercase hex digits")
    return bytes.fromhex(a[2:])


def b32(h: str) -> bytes:
    if not re.fullmatch(r"0x[0-9a-f]{64}", h):
        raise ValueError("bytes32 must be 0x + 64 lowercase hex digits")
    return bytes.fromhex(h[2:])


def hx(b: bytes) -> str:
    return "0x" + b.hex()


ZERO32 = "0x" + "00" * 32
ZERO_ADDR = "0x" + "00" * 20

# ---------------------------------------------------------------- §3 kinds, subjects, statuses

KIND_PROVEN, KIND_ATTESTED, KIND_CLAIMED = 1, 2, 3
KINDS = {KIND_PROVEN: "proven", KIND_ATTESTED: "attested", KIND_CLAIMED: "claimed"}
SUBJECT_ACCOUNT, SUBJECT_AGENT = 0, 1
SUBJECTS = {SUBJECT_ACCOUNT: "account", SUBJECT_AGENT: "agent"}
STATUS_NONE, STATUS_ACTIVE, STATUS_EXPIRED, STATUS_REVOKED, STATUS_SUPERSEDED = range(5)
STATUSES = ["none", "active", "expired", "revoked", "superseded"]
MAX_EXHAUSTIVE_INPUTS = 16
# Work bounds of the reference contract (§4.4 item 2), measured against a 16,777,216-gas transaction (EIP-7825)
MAX_GATE_WORK = 1 << 16
GATE_OVERHEAD = 20
MAX_TABLE_BYTES = 1 << 17
MAX_FILE_BYTES = 49152
REBIND_DELAY = 7 * 24 * 3600

TAG_TRUTH_TABLE = b"tap-credential-truth-table/1\x00"
TAG_DESIGN_KEY = b"tap-credential-design-key/1\x00"
TAG_SPEC = b"tap-credential-spec/1\x00"
TAG_SERIES = b"tap-credential-series/1\x00"
TAG_COMMIT = b"tap-credential-commit/1\x00"
TAG_SCOPE = b"tap-credential-scope/1\x00"
TAG_CLAIM = b"tap-credential-claim/1\x00"


class Reject(ValueError):
    """An input the Specification says MUST be rejected. `code` names the rule."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------- §4.1 combinational files


def check_combinational(file: bytes) -> tapnft.Metrics:
    """A valid tapnet/1 file (TAP-721 §2.2) without LATCH records."""
    try:
        m = tapnft.check_file(file)
    except tapnft.Invalid:
        raise Reject("invalid-file") from None
    if m.latch != 0:
        raise Reject("has-latch")
    return m


def _nand_pairs(file: bytes) -> list:
    n_in, _, records = tapnft.decode_file(file)
    els = tap02.decode(records, n_in)
    return [tuple(e.ins) for e in els]


def input_pattern(i: int, n_in: int) -> int:
    """Integer whose bit x is input i of input vector x, for x in [0, 2^nIn)."""
    width = 1 << n_in
    period = 1 << (i + 1)
    block = ((1 << (1 << i)) - 1) << (1 << i)  # 2^i zeros then 2^i ones (bits 0.. are LSB)
    v = 0
    for start in range(0, width, period):
        v |= block << start
    return v


def eval_all(file: bytes) -> list:
    """Bit-sliced evaluation over every input vector: per output j an integer whose bit x
    is output j for input vector x (input i = bit i of x, TAP-02 §5 packing order)."""
    m = check_combinational(file)
    if m.n_in > MAX_EXHAUSTIVE_INPUTS:
        raise Reject("too-many-inputs")
    mask = (1 << (1 << m.n_in)) - 1
    sig = [0, mask] + [input_pattern(i, m.n_in) for i in range(m.n_in)]
    for a, b in _nand_pairs(file):
        sig.append(~(sig[a] & sig[b]) & mask)
    return sig[len(sig) - m.n_out:]


# ---------------------------------------------------------------- §4.2 truth tables


def column_bytes(col: int, n_in: int) -> bytes:
    """2^nIn bits, input vector 0 first, most significant bit of each byte first."""
    n = 1 << n_in
    bits = format(col, "0%db" % n)[::-1]          # character x is the output for input vector x
    bits = bits + "0" * (max(8, n) - n)
    return int(bits, 2).to_bytes(max(1, n // 8), "big")


def truth_table(n_in: int, n_out: int, columns: list) -> bytes:
    if not (0 <= n_in <= MAX_EXHAUSTIVE_INPUTS) or not (1 <= n_out <= 1 << 16) or len(columns) != n_out:
        raise Reject("bad-truth-table")
    return u32be(n_in) + u32be(n_out) + b"".join(column_bytes(c, n_in) for c in columns)


def truth_table_hash_of_columns(n_in: int, n_out: int, columns: list) -> bytes:
    return sha256(TAG_TRUTH_TABLE + truth_table(n_in, n_out, columns))


def truth_table_hash(file: bytes) -> bytes:
    m = check_combinational(file)
    return truth_table_hash_of_columns(m.n_in, m.n_out, eval_all(file))


def truth_table_hash_of_function(n_in: int, n_out: int, f) -> bytes:
    """f(x) -> integer whose bit j is output j for input vector x."""
    cols = [0] * n_out
    for x in range(1 << n_in):
        y = f(x)
        for j in range(n_out):
            if (y >> j) & 1:
                cols[j] |= 1 << x
    return truth_table_hash_of_columns(n_in, n_out, cols)


# ---------------------------------------------------------------- §4.3 design keys


def output_labels(file: bytes) -> list:
    """Structural labels (TAP structural hash §4.1-§4.2) of the output elements."""
    m = check_combinational(file)
    lab = [canon.const_label(0), canon.const_label(1)] + [canon.input_label(i) for i in range(m.n_in)]
    for a, b in _nand_pairs(file):
        lab.append(canon.nand_label(lab[a], lab[b]))
    return lab[len(lab) - m.n_out:]


def design_key(file: bytes) -> bytes:
    m = check_combinational(file)
    return sha256(TAG_DESIGN_KEY + u32be(m.n_in) + u32be(m.n_out) + b"".join(output_labels(file)))


# ---------------------------------------------------------------- §4.4 specifications

SPEC_FIELDS = ("registrant", "nIn", "nOut", "target", "maxGates", "unique", "series",
               "commitStart", "commitEnd", "revealEnd", "recoveryAuthority", "infoHash")


def spec_bytes(s: dict) -> bytes:
    if set(s) != set(SPEC_FIELDS):
        raise Reject("spec-members")
    return (addr(s["registrant"]) + u32be(s["nIn"]) + u32be(s["nOut"]) + b32(s["target"])
            + u32be(s["maxGates"]) + u8(1 if s["unique"] else 0) + b32(s["series"]) + u64be(s["commitStart"])
            + u64be(s["commitEnd"]) + u64be(s["revealEnd"]) + addr(s["recoveryAuthority"]) + b32(s["infoHash"]))


def spec_id(s: dict) -> bytes:
    return sha256(TAG_SPEC + spec_bytes(s))


def series_key(registrant: str, series: str) -> bytes:
    return sha256(TAG_SERIES + addr(registrant) + b32(series))


def check_spec(s: dict, max_gate_work: int = MAX_GATE_WORK, max_table_bytes: int = MAX_TABLE_BYTES) -> None:
    """The registration rules of §4.4 (the series ordering rule needs state: Issuer)."""
    spec_bytes(s)
    if not (1 <= s["nOut"] <= 1 << 16) or not (0 <= s["nIn"] <= MAX_EXHAUSTIVE_INPUTS):
        raise Reject("bad-pins")
    if s["target"] == ZERO32:
        raise Reject("zero-target")
    if s["maxGates"] < s["nOut"]:
        raise Reject("bad-max-gates")
    if not (s["commitStart"] < s["commitEnd"] < s["revealEnd"]):
        raise Reject("bad-windows")
    if s["unique"] and s["series"] == ZERO32:
        raise Reject("unique-without-series")
    if gate_work(s["nIn"], s["maxGates"]) > max_gate_work:
        raise Reject("too-much-gate-work")
    if table_bytes(s["nIn"], s["nOut"]) > max_table_bytes:
        raise Reject("table-too-large")


def gate_work(n_in: int, max_gates: int) -> int:
    """(256-lane words + per-gate overhead) times gates: the first bound of the reference contract (§4.4)."""
    return (max(1, (1 << n_in) // 256) + GATE_OVERHEAD) * max_gates


def table_bytes(n_in: int, n_out: int) -> int:
    """Bytes of the truth-table buffer (§4.2): the second bound of the reference contract (§4.4)."""
    return n_out * max(1, (1 << n_in) // 8)


# ---------------------------------------------------------------- §4.5 commitments


def commitment(spec: bytes, recipient: str, subject: int, netlist_hash: bytes, salt: bytes) -> bytes:
    if len(spec) != 32 or len(netlist_hash) != 32 or len(salt) != 32 or subject not in SUBJECTS:
        raise Reject("bad-commitment-input")
    return sha256(TAG_COMMIT + spec + addr(recipient) + u8(subject) + netlist_hash + salt)


# ---------------------------------------------------------------- §4.6 the check of a submission


def check_submission(s: dict, file: bytes) -> dict:
    """Content checks of §4.6 items 4-7 (window, commitment and duplicate rules: Issuer)."""
    m = check_combinational(file)
    if (m.n_in, m.n_out) != (s["nIn"], s["nOut"]):
        raise Reject("pin-mismatch")
    if m.nand > s["maxGates"]:
        raise Reject("too-many-gates")
    if len(file) > MAX_FILE_BYTES:
        raise Reject("file-too-large")
    out = {"netlistHash": hx(sha256(file)), "designKey": hx(design_key(file)), "gates": m.nand}
    if truth_table_hash(file) != b32(s["target"]):
        raise Reject("wrong-function")
    return out


# ---------------------------------------------------------------- §5 EIP-712

DOMAIN_NAME = "TAP Soulbound Credentials"
DOMAIN_VERSION = "1"

TYPES = {
    "EIP712Domain": [("name", "string"), ("version", "string"), ("chainId", "uint256"),
                     ("verifyingContract", "address")],
    "Attestation": [("issuer", "address"), ("recipient", "address"), ("subject", "uint8"), ("scope", "bytes32"),
                    ("artifact", "bytes32"), ("evidence", "bytes32"), ("issuedAt", "uint64"),
                    ("expiresAt", "uint64"), ("deadline", "uint64"), ("replaces", "uint256"), ("nonce", "bytes32")],
    "Rebind": [("authority", "address"), ("oldTokenId", "uint256"), ("newHolder", "address"),
               ("deadline", "uint64"), ("nonce", "bytes32")],
}


def encode_type(t: str) -> str:
    return t + "(" + ",".join(f"{ft} {fn}" for fn, ft in TYPES[t]) + ")"


def type_hash(t: str) -> bytes:
    return keccak256(encode_type(t).encode())


def _enc(ft: str, v) -> bytes:
    if ft == "string":
        return keccak256(v.encode("utf-8"))
    if ft == "bytes32":
        return b32(v)
    if ft == "address":
        return b"\x00" * 12 + addr(v)
    if ft.startswith("uint"):
        bits = int(ft[4:])
        if isinstance(v, bool) or not isinstance(v, int) or not (0 <= v < 1 << bits):
            raise Reject("uint-range")
        return v.to_bytes(32, "big")
    raise ValueError(ft)


def hash_struct(t: str, obj: dict) -> bytes:
    if set(obj) != {fn for fn, _ in TYPES[t]}:
        raise Reject("members")
    return keccak256(type_hash(t) + b"".join(_enc(ft, obj[fn]) for fn, ft in TYPES[t]))


def domain_separator(chain_id: int, contract: str) -> bytes:
    return hash_struct("EIP712Domain", {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": chain_id,
                                        "verifyingContract": contract})


def digest(t: str, msg: dict, chain_id: int, contract: str) -> bytes:
    return keccak256(b"\x19\x01" + domain_separator(chain_id, contract) + hash_struct(t, msg))


def check_attestation_fields(a: dict) -> None:
    hash_struct("Attestation", a)
    if a["issuer"] == ZERO_ADDR or a["recipient"] == ZERO_ADDR:
        raise Reject("zero-address")
    if a["subject"] not in SUBJECTS:
        raise Reject("bad-subject")
    if a["artifact"] == ZERO32 or a["scope"] == ZERO32:
        raise Reject("zero-artifact-or-scope")
    if a["expiresAt"] != 0 and a["expiresAt"] <= a["issuedAt"]:
        raise Reject("bad-expiry")


def recover_eoa(h: bytes, sig: bytes) -> str:
    """§5.3: 65 bytes r ‖ s ‖ v, v in {0, 1, 27, 28}, r and s in range, low s (as in Design Credits §4.6)."""
    try:
        return credits.recover(h, sig)
    except credits.SigError as e:
        raise Reject(e.code) from None


def scope_of_label(label: str) -> bytes:
    return sha256(TAG_SCOPE + label.encode("utf-8"))


# ---------------------------------------------------------------- §6 claimed credentials


def claim_scope(statement_id: bytes) -> bytes:
    """§6: the scope of a claimed credential: zero, or a domain-separated hash of the statement id."""
    if len(statement_id) != 32:
        raise Reject("bad-statement-id")
    if statement_id == b"\x00" * 32:
        return statement_id
    return sha256(TAG_CLAIM + statement_id)


def statement_display(message: dict, holder: str, chain_id: int, artifact: dict, revoked: bool = False) -> str:
    """§6, §10.4: how a tool shows a verified Design Credits statement carried by a claimed credential.
    message: the statement's message (TAP-draft-design-credits §4.3); artifact: {"netlistHash", "structuralHash"}
    of the credential's artifact. Returns "revoked", "mismatch" or "consistent"."""
    if revoked:
        return "revoked"
    signer_ok = message["signer"] == holder and message["signerChainId"] in (0, chain_id)
    subject_ok = credits.applies(message["subject"], artifact)
    return "consistent" if signer_ok and subject_ok else "mismatch"


# ---------------------------------------------------------------- §8 interfaces


def selector(sig: str) -> bytes:
    return keccak256(sig.encode())[:4]


def interface_id(sigs: list) -> str:
    v = 0
    for s in sigs:
        v ^= int.from_bytes(selector(s), "big")
    return "0x%08x" % v


I_CREDENTIAL = [
    "credentialOf(uint256)",
    "statusOf(uint256)",
    "credentialsOf(address,uint8,address,bytes32,bool,uint256,uint256)",
    "netlistHashOf(uint256)",
    "netlistFile(bytes32)",
    "storeNetlist(bytes)",
    "renounce(uint256)",
]
I_PROVEN = [
    "registerSpec((address,uint32,uint32,bytes32,uint32,bool,bytes32,uint64,uint64,uint64,address,bytes32))",
    "specOf(bytes32)",
    "checkBounds()",
    "commit(bytes32,bytes32)",
    "reveal(bytes32,address,uint8,bytes,bytes32)",
    "requestRebind((address,uint256,address,uint64,bytes32),bytes)",
    "vetoRebind(uint256)",
    "completeRebind(uint256)",
]
I_ATTESTED = [
    "redeem((address,address,uint8,bytes32,bytes32,bytes32,uint64,uint64,uint64,uint256,bytes32),bytes)",
    "revokeAttestation((address,address,uint8,bytes32,bytes32,bytes32,uint64,uint64,uint64,uint256,bytes32))",
    "attestationStatus(bytes32)",
]
I_CLAIMED = ["claim(bytes,bytes32,bytes32,uint8)"]
ERC5192 = ["locked(uint256)"]

EVENTS = [
    "CredentialIssued(uint256,address,uint8,uint8,address,bytes32,bytes32)",
    "CredentialStatusChanged(uint256,uint8)",
    "CredentialRebound(uint256,uint256)",
    "SpecRegistered(bytes32,address)",
    "Committed(bytes32,address,bytes32)",
    "Accepted(uint256,bytes32,address,bytes32,bytes32)",
    "RebindRequested(uint256,address,uint64)",
    "RebindVetoed(uint256)",
    "AttestationRevoked(bytes32,address)",
    "Locked(uint256)",
]


def interface_table() -> dict:
    return {
        "ITapCredential": interface_id(I_CREDENTIAL),
        "ITapCredentialProven": interface_id(I_PROVEN),
        "ITapCredentialAttested": interface_id(I_ATTESTED),
        "ITapCredentialClaimed": interface_id(I_CLAIMED),
        "IERC5192": interface_id(ERC5192),
        "selectors": {s: hx(selector(s)) for s in I_CREDENTIAL + I_PROVEN + I_ATTESTED + I_CLAIMED + ERC5192},
        "topics": {e: hx(keccak256(e.encode())) for e in EVENTS},
    }


# ---------------------------------------------------------------- §9 metadata

HEX32 = re.compile(r"0x[0-9a-f]{64}")
HEXADDR = re.compile(r"0x[0-9a-f]{40}")
DEC = re.compile(r"0|[1-9][0-9]*")


def _req(c: bool, code: str) -> None:
    if not c:
        raise Reject(code)


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= (1 << 53) - 1


def _hashed(v, code: str) -> None:
    _req(isinstance(v, dict) and isinstance(v.get("sha256"), str) and HEX32.fullmatch(v["sha256"]) is not None
         and isinstance(v.get("uris"), list) and len(v["uris"]) > 0 and all(isinstance(u, str) for u in v["uris"]),
         code)


def _text(v, n: int) -> bool:
    if not isinstance(v, str) or len(v.encode("utf-8")) > n:
        return False
    return not any(credits.forbidden_char(ord(ch)) for ch in v)


STATUS_MEMBERS = ("status", "revoked", "expired", "superseded")
# §2 item 3: names that state or suggest an economic value. The list is illustrative: tools reject by meaning,
# in any language; this model only matches these words.
ECONOMIC_WORDS = frozenset((
    "value", "price", "worth", "yield", "apy", "apr", "interest", "dividend", "dividends", "revenue", "profit",
    "income", "payout", "payment", "share", "shares", "allocation", "allotment", "airdrop", "reward", "rewards",
    "points", "point", "weight", "weighting", "tier", "multiplier", "bonus", "boost", "score", "rank", "eligible",
    "eligibility", "entitlement", "claimable", "vesting", "stake", "staking"))


def _words(name: str) -> list:
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", name)]


def _economic_names(doc) -> bool:
    """True if a member name anywhere in the document, or an ERC-721 attribute's trait_type, uses a word of
    ECONOMIC_WORDS. The member `value` of an ERC-721 attribute entry is part of that format and is exempt, and so
    is the member `tap.pod` (TAP-draft-pod-attributes), which carries its own non-entitlement rules (its §7).
    Only names are checked: text such as `description` is left to the judgement of tools (§9 item 4)."""
    def walk(v, in_attr=False) -> bool:
        if isinstance(v, dict):
            for k, x in v.items():
                if not (in_attr and k == "value") and any(w in ECONOMIC_WORDS for w in _words(k)):
                    return True
                if walk(x):
                    return True
            return False
        if isinstance(v, list):
            return any(walk(x) for x in v)
        return False
    attrs = doc.get("attributes", [])
    if isinstance(attrs, list):
        for a in attrs:
            if isinstance(a, dict):
                t = a.get("trait_type")
                if isinstance(t, str) and any(w in ECONOMIC_WORDS for w in _words(t)):
                    return True
                if walk(a, in_attr=True):
                    return True
    rest = {k: v for k, v in doc.items() if k != "attributes"}
    if isinstance(rest.get("tap"), dict):
        rest["tap"] = {k: v for k, v in rest["tap"].items() if k != "pod"}
    return walk(rest)


def check_credential_metadata(doc: dict, onchain: dict = None) -> dict:
    """Check the token metadata of a credential (§9). `onchain` is credentialOf() as JSON, optional."""
    _req(isinstance(doc, dict) and isinstance(doc.get("tap"), dict), "no-tap")
    tap = doc["tap"]
    _req(tap.get("state") == "revealed" and "manifest" not in tap, "credential-state")
    _req(isinstance(tap.get("image"), dict), "credential-image")
    _req("edition" not in tap, "credential-edition")   # §3.2: credential collections form no TAP-721 editions
    tapnft.check_metadata(doc)
    c = tap.get("credential")
    _req(isinstance(c, dict), "no-credential")
    _req(c.get("v") == 1, "credential-v")
    _req(c.get("kind") in KINDS.values(), "credential-kind")
    _req(c.get("subject") in SUBJECTS.values(), "credential-subject")
    k = c["contract"] if isinstance(c.get("contract"), dict) else None
    _req(k is not None and _int(k.get("chainId")) and isinstance(k.get("address"), str)
         and HEXADDR.fullmatch(k["address"]) is not None, "credential-contract")
    m = re.fullmatch(r"eip155:([0-9]+)/erc721:(0x[0-9a-f]{40})/(0|[1-9][0-9]*)", tap["id"])
    _req(m is not None and int(m.group(1)) == k["chainId"] and m.group(2) == k["address"], "credential-contract-id")
    _req(isinstance(c.get("issuer"), str) and HEXADDR.fullmatch(c["issuer"]) is not None, "credential-issuer")
    _req(isinstance(c.get("scope"), str) and HEX32.fullmatch(c["scope"]) is not None, "credential-scope")
    _req(_int(c.get("issuedAt")) and _int(c.get("expiresAt")), "credential-times")
    _req(c["expiresAt"] == 0 or c["expiresAt"] > c["issuedAt"], "credential-times")
    if "replaces" in c:
        _req(isinstance(c["replaces"], str) and DEC.fullmatch(c["replaces"]) is not None
             and c["replaces"] != "0", "credential-replaces")
    if "evidence" in c:
        _hashed(c["evidence"], "credential-evidence")
    if "cohort" in c:
        _req(_text(c["cohort"], 64), "credential-cohort")
    if "issuerName" in c:
        _req(c["kind"] == "attested" and _text(c["issuerName"], 64), "credential-issuer-name")
    if "scopeLabel" in c:
        _req(_text(c["scopeLabel"], 256) and c["kind"] == "attested"
             and hx(scope_of_label(c["scopeLabel"])) == c["scope"], "credential-scope-label")
    if c["kind"] == "proven":
        sp = c.get("spec")
        _req(isinstance(sp, dict) and set(sp) >= {"id", "maxGates", "target"} and "mode" not in sp, "credential-spec")
        _req(sp["id"] == c["scope"], "credential-spec")
        _req(tap["netlist"]["latch"] == 0 and tap["netlist"]["nand"] <= sp["maxGates"], "credential-spec")
        if "info" in sp:
            _hashed(sp["info"], "credential-spec")
    else:
        _req("spec" not in c, "credential-spec")
    if "statement" in c:
        st = c["statement"]
        _req(c["kind"] == "claimed" and isinstance(st, dict) and HEX32.fullmatch(st.get("id", "")) is not None
             and hx(claim_scope(b32(st["id"]))) == c["scope"] and isinstance(st.get("uris"), list)
             and len(st["uris"]) > 0 and all(isinstance(u, str) for u in st["uris"]), "credential-statement")
    if "agent" in c:
        a = c["agent"]
        _req(c["subject"] == "agent" and isinstance(a, dict)
             and re.fullmatch(r"eip155:[0-9]+:0x[0-9a-f]{40}", a.get("registry", "")) is not None
             and isinstance(a.get("agentId"), str) and DEC.fullmatch(a["agentId"]) is not None, "credential-agent")
    for bad in STATUS_MEMBERS:
        _req(bad not in c, "credential-forbidden-member")
    _req(not _economic_names(doc), "credential-forbidden-member")
    if onchain is not None:
        _req(KINDS[onchain["kind"]] == c["kind"] and SUBJECTS[onchain["subject"]] == c["subject"]
             and onchain["issuer"] == c["issuer"] and onchain["scope"] == c["scope"]
             and onchain["artifact"] == tap["netlist"]["sha256"] and onchain["issuedAt"] == c["issuedAt"]
             and onchain["expiresAt"] == c["expiresAt"]
             and (onchain["evidence"] == ZERO32) == ("evidence" not in c)
             and (onchain["evidence"] == ZERO32 or onchain["evidence"] == c["evidence"]["sha256"])
             and str(onchain["replaces"]) == c.get("replaces", "0"), "credential-onchain-mismatch")
    return c


# ---------------------------------------------------------------- §10 display labels


def display_label(kind: str, rechecked: bool = False, status: str = "active") -> str:
    if kind == "proven":
        base = "Proven: passes its specification (re-checked)" if rechecked else \
            "Proven per contract (not re-checked)"
    elif kind == "attested":
        base = "Attested by issuer (identity not verified)"
    else:
        base = "Self-claimed"
    return base if status == "active" else f"{base} [{status}]"


# ---------------------------------------------------------------- executable model of the reference contract


class Issuer:
    """A model of SoulboundNetlistCredential: the same rules, in memory. Used for scenario vectors."""

    def __init__(self, chain_id: int, address: str, max_gate_work: int = MAX_GATE_WORK,
                 max_table_bytes: int = MAX_TABLE_BYTES, erc1271=None):
        self.chain_id, self.address = chain_id, address
        self.max_gate_work, self.max_table_bytes = max_gate_work, max_table_bytes
        self.erc1271 = erc1271 or {}       # contract address -> function(digest, sig) -> bool
        self.specs, self.files = {}, {}
        self.commits = set()                # (specId, committer, commitment): kept per committer (§4.5)
        self.series_end, self.series_designs = {}, {}
        self.tokens, self.owner, self.status_flag = {}, {}, {}
        self.held = {}                      # (specId, account) -> True: holds or held a credential of the spec
        self.pending = {}                   # old token -> (new holder, readyAt); lapses at readyAt + REBIND_DELAY
        self.minted_to = {}                 # holder -> token ids minted to it, in mint order, never pruned (§8.1)
        self.att_used, self.att_revoked, self.att_token, self.rebind_used = set(), set(), {}, set()
        self.next_token = 1

    # -- helpers
    def _store(self, file: bytes) -> bytes:
        h = sha256(file)
        self.files[h] = file
        return h

    def _mint(self, holder: str, cred: dict) -> int:
        t = self.next_token
        self.next_token += 1
        self.tokens[t], self.owner[t], self.status_flag[t] = cred, holder, STATUS_ACTIVE
        self.minted_to.setdefault(holder, []).append(t)
        return t

    def pending_rebind(self, old: int, now: int):
        """§4.7: the pending request for `old`, or None (never made, completed, vetoed, renounced or lapsed)."""
        p = self.pending.get(old)
        if p is None or now >= p[1] + REBIND_DELAY:
            return None
        return p

    def status(self, t: int, now: int) -> int:
        if t not in self.owner:
            return STATUS_NONE
        f = self.status_flag[t]
        if f != STATUS_ACTIVE:
            return f
        e = self.tokens[t]["expiresAt"]
        return STATUS_EXPIRED if e != 0 and now >= e else STATUS_ACTIVE

    def _sig_ok(self, signer: str, h: bytes, sig: bytes) -> bool:
        """§5.3: public-key recovery first (EIP-7702 accounts keep their key), then ERC-1271 for code."""
        try:
            if recover_eoa(h, sig) == signer:
                return True
        except Reject:
            pass
        if signer in self.erc1271:
            return bool(self.erc1271[signer](h, sig))
        return False

    # -- proven
    def register_spec(self, s: dict, now: int = 0) -> bytes:
        check_spec(s, self.max_gate_work, self.max_table_bytes)
        sid = spec_id(s)
        if sid in self.specs:
            raise Reject("spec-exists")
        if s["series"] != ZERO32:
            sk = series_key(s["registrant"], s["series"])
            if s["commitStart"] < self.series_end.get(sk, 0):
                raise Reject("series-overlap")
            self.series_end[sk] = s["revealEnd"]
        self.specs[sid] = dict(s)
        return sid

    def commit(self, sender: str, sid: bytes, c: bytes, now: int) -> None:
        s = self.specs.get(sid)
        if s is None:
            raise Reject("no-spec")
        if not (s["commitStart"] <= now < s["commitEnd"]):
            raise Reject("not-commit-window")
        if (sid, sender, c) in self.commits:
            raise Reject("commit-exists")
        self.commits.add((sid, sender, c))

    def reveal(self, sid: bytes, recipient: str, subject: int, file: bytes, salt: bytes, now: int) -> dict:
        s = self.specs.get(sid)
        if s is None:
            raise Reject("no-spec")
        if not (s["commitEnd"] <= now < s["revealEnd"]):
            raise Reject("not-reveal-window")
        c = commitment(sid, recipient, subject, sha256(file), salt)
        if (sid, recipient, c) not in self.commits:
            raise Reject("no-commitment")
        if self.held.get((sid, recipient)):
            raise Reject("already-holds")
        r = check_submission(s, file)
        sk = series_key(s["registrant"], s["series"])
        if s["unique"]:
            prior = self.series_designs.get((sk, r["designKey"]))
            if prior is not None and prior != sid:
                raise Reject("duplicate-design")
        self.commits.discard((sid, recipient, c))
        if s["series"] != ZERO32:
            # §4.6: every reveal of a series records its design key, whether or not its round is unique
            self.series_designs.setdefault((sk, r["designKey"]), sid)
        self._store(file)
        self.held[(sid, recipient)] = True
        t = self._mint(recipient, {
            "kind": KIND_PROVEN, "subject": subject, "issuer": s["registrant"], "scope": hx(sid),
            "artifact": r["netlistHash"], "evidence": ZERO32, "issuedAt": now, "expiresAt": 0, "replaces": 0})
        return {"token": t, **r}

    def request_rebind(self, sender: str, r: dict, sig: bytes, now: int) -> int:
        old = r["oldTokenId"]
        if sender != r["newHolder"]:
            raise Reject("not-new-holder")
        if old not in self.owner or self.tokens[old]["kind"] != KIND_PROVEN:
            raise Reject("not-proven")
        if self.status_flag[old] == STATUS_SUPERSEDED:
            raise Reject("not-rebindable")
        sid = b32(self.tokens[old]["scope"])
        s = self.specs[sid]
        if s["recoveryAuthority"] == ZERO_ADDR or r["authority"] != s["recoveryAuthority"]:
            raise Reject("not-authority")
        if r["deadline"] != 0 and now > r["deadline"]:
            raise Reject("expired-offer")
        if self.held.get((sid, r["newHolder"])):
            raise Reject("already-holds")
        h = digest("Rebind", r, self.chain_id, self.address)
        if h in self.rebind_used or not self._sig_ok(r["authority"], h, sig):
            raise Reject("bad-signature")
        self.rebind_used.add(h)
        self.pending[old] = (r["newHolder"], now + REBIND_DELAY)   # replaces a pending or lapsed request
        return now + REBIND_DELAY

    def veto_rebind(self, sender: str, old: int, now: int) -> None:
        if self.owner.get(old) != sender:
            raise Reject("not-holder")
        if self.pending_rebind(old, now) is None:
            raise Reject("no-pending-rebind")
        del self.pending[old]

    def complete_rebind(self, sender: str, old: int, now: int) -> int:
        if old not in self.pending:
            raise Reject("no-pending-rebind")
        new_holder, ready = self.pending[old]
        if sender != new_holder:
            raise Reject("not-new-holder")
        if now < ready:
            raise Reject("rebind-not-ready")
        if now >= ready + REBIND_DELAY:
            raise Reject("rebind-lapsed")
        if old not in self.owner or self.status_flag[old] == STATUS_SUPERSEDED:
            raise Reject("not-rebindable")
        sid = b32(self.tokens[old]["scope"])
        if self.held.get((sid, new_holder)):
            raise Reject("already-holds")
        del self.pending[old]
        self.held[(sid, new_holder)] = True
        cred = dict(self.tokens[old], issuedAt=now, replaces=old)
        self.status_flag[old] = STATUS_SUPERSEDED
        return self._mint(new_holder, cred)

    # -- attested
    def redeem(self, sender: str, a: dict, sig: bytes, now: int) -> int:
        check_attestation_fields(a)
        if a["issuedAt"] > now:
            raise Reject("issued-in-future")
        if a["expiresAt"] != 0 and a["expiresAt"] <= now:
            raise Reject("already-expired")
        if sender != a["recipient"]:
            raise Reject("not-recipient")
        h = digest("Attestation", a, self.chain_id, self.address)
        if h in self.att_used:
            raise Reject("already-redeemed")
        if h in self.att_revoked:
            raise Reject("revoked")
        if a["deadline"] != 0 and now > a["deadline"]:
            raise Reject("expired-offer")
        if not self._sig_ok(a["issuer"], h, sig):
            raise Reject("bad-signature")
        if b32(a["artifact"]) not in self.files:
            raise Reject("artifact-not-stored")
        if a["replaces"] != 0:
            old = a["replaces"]
            if old not in self.owner or self.tokens[old]["kind"] != KIND_ATTESTED \
                    or self.tokens[old]["issuer"] != a["issuer"]:
                raise Reject("bad-replaces")
            if self.status_flag[old] in (STATUS_SUPERSEDED, STATUS_REVOKED):
                raise Reject("not-rebindable")
        self.att_used.add(h)
        t = self._mint(a["recipient"], {
            "kind": KIND_ATTESTED, "subject": a["subject"], "issuer": a["issuer"], "scope": a["scope"],
            "artifact": a["artifact"], "evidence": a["evidence"], "issuedAt": a["issuedAt"],
            "expiresAt": a["expiresAt"], "replaces": a["replaces"]})
        self.att_token[h] = t
        if a["replaces"] != 0:
            self.status_flag[a["replaces"]] = STATUS_SUPERSEDED
        return t

    def revoke_attestation(self, sender: str, a: dict) -> None:
        h = digest("Attestation", a, self.chain_id, self.address)
        if sender != a["issuer"]:
            raise Reject("not-issuer")
        self.att_revoked.add(h)
        t = self.att_token.get(h)
        if t is not None and t in self.owner and self.status_flag[t] == STATUS_ACTIVE:
            self.status_flag[t] = STATUS_REVOKED

    # -- claimed
    def claim(self, sender: str, file: bytes, statement: bytes, evidence: bytes, subject: int, now: int) -> int:
        try:
            tapnft.check_file(file)
        except tapnft.Invalid:
            raise Reject("invalid-file") from None
        if len(file) > MAX_FILE_BYTES:
            raise Reject("file-too-large")
        if subject not in SUBJECTS:
            raise Reject("bad-subject")
        h = self._store(file)
        return self._mint(sender, {"kind": KIND_CLAIMED, "subject": subject, "issuer": sender,
                                   "scope": hx(claim_scope(statement)), "artifact": hx(h), "evidence": hx(evidence),
                                   "issuedAt": now, "expiresAt": 0, "replaces": 0})

    # -- holder
    def renounce(self, sender: str, t: int) -> None:
        if self.owner.get(t) != sender:
            raise Reject("not-holder")
        self.pending.pop(t, None)          # §4.7: renouncing ends a pending rebind of the token
        del self.owner[t]

    def store(self, file: bytes) -> bytes:
        try:
            tapnft.check_file(file)
        except tapnft.Invalid:
            raise Reject("invalid-file") from None
        if len(file) > MAX_FILE_BYTES:
            raise Reject("file-too-large")
        return self._store(file)

    def credentials_of(self, holder: str, kind: int, issuer: str, scope: str, active_only: bool, now: int,
                       cursor: int = 0, limit: int = 100) -> tuple:
        """§8.1 item 2: one kind per query (kind 0 is rejected) and limit >= 1. The cursor is an index into the
        list of tokens ever minted to `holder` (renounced ones included), as in the reference contract."""
        if kind not in KINDS or limit < 1:
            raise Reject("bad-query")
        ids = self.minted_to.get(holder, [])
        out, i = [], cursor
        while i < len(ids) and len(out) < limit:
            t = ids[i]
            c = self.tokens[t]
            i += 1
            if self.owner.get(t) != holder:
                continue
            if c["kind"] != kind:
                continue
            if issuer != ZERO_ADDR and c["issuer"] != issuer:
                continue
            if scope != ZERO32 and c["scope"] != scope:
                continue
            if active_only and self.status(t, now) != STATUS_ACTIVE:
                continue
            out.append(t)
        return out, (i if i < len(ids) else 0)
