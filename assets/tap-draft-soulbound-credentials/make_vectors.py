"""Write vectors.json for the TAP draft "Soulbound Netlist Credentials" (deterministic).

MIT licence. `python3 make_vectors.py` writes vectors.json; `--check` compares instead.
All private keys are public test keys: keccak256("tap-soulbound test key <n>"). Never use them.
"""
from __future__ import annotations

import json
import os
import random
import sys

import canon
import credits
import soulbound as sb
import tapnft

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "vectors.json")

CHAIN_ID = 31337
CONTRACT = "0x00000000000000000000000000000000000000c1"


def key(n: int) -> int:
    return int.from_bytes(credits.keccak256(f"tap-soulbound test key {n}".encode()), "big")


KEYS = {n: key(n) for n in (1, 2, 3, 4, 5)}
ADDR = {n: credits.address_of_key(k) for n, k in KEYS.items()}


class B:
    """Tiny combinational netlist builder: signals 0, 1, inputs 2.., then NAND gates."""

    def __init__(self, n_in: int):
        self.n_in, self.recs = n_in, []

    def inp(self, i: int) -> int:
        return 2 + i

    def nand(self, a: int, b: int) -> int:
        self.recs.append((a, b))
        return 2 + self.n_in + len(self.recs) - 1

    def xor(self, a: int, b: int) -> int:
        g = self.nand(a, b)
        return self.nand(self.nand(a, g), self.nand(b, g))

    def file(self, outputs: list) -> bytes:
        """Outputs must be the last len(outputs) gates, in order (TAP-02 §3)."""
        last = 2 + self.n_in + len(self.recs)
        assert outputs == list(range(last - len(outputs), last)), "outputs must be the trailing gates"
        recs = b"".join(b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big") for a, b in self.recs)
        return tapnft.encode_file(recs, self.n_in, len(outputs))


def raw(records_hex: str, n_in: int, n_out: int) -> bytes:
    return tapnft.encode_file(bytes.fromhex(records_hex), n_in, n_out)


# ---- the files

XOR = raw("00000002000003" "00000002000004" "00000003000004" "00000005000006", 2, 1)
XOR_RENUMBERED = raw("00000002000003" "00000003000004" "00000002000004" "00000005000006", 2, 1)   # middle gates swapped
XOR_SWAPPED_INPUTS = raw("00000003000002" "00000004000002" "00000004000003" "00000006000005", 2, 1)  # NAND inputs swapped
XOR_DEAD_GATE = raw("00000002000003" "00000000000001" "00000002000004" "00000003000004" "00000006000007", 2, 1)


def _xor_double_neg() -> bytes:
    b = B(2)
    g = b.nand(2, 3)
    x = b.nand(b.nand(2, g), b.nand(3, g))
    n1 = b.nand(x, x)
    return b.file([b.nand(n1, n1)])


XOR_DOUBLE_NEG = _xor_double_neg()
AND2 = raw("00000002000003" "00000004000004", 2, 1)


def _half_adder() -> bytes:
    b = B(2)
    g = b.nand(2, 3)
    s = b.nand(b.nand(2, g), b.nand(3, g))
    c = b.nand(g, g)
    return b.file([s, c])


HALF_ADDER = _half_adder()


def _parity(n: int, balanced: bool) -> bytes:
    b = B(n)
    sig = [b.inp(i) for i in range(n)]
    if balanced:
        while len(sig) > 1:
            nxt = [b.xor(sig[i], sig[i + 1]) for i in range(0, len(sig) - 1, 2)]
            if len(sig) % 2:
                nxt.append(sig[-1])
            sig = nxt
        out = sig[0]
    else:
        acc = sig[0]
        for s in sig[1:]:
            acc = b.xor(acc, s)
        out = acc
    return b.file([out])


def _adder8() -> bytes:
    """8-bit ripple-carry adder: inputs a0..a7 (0-7), b0..b7 (8-15); outputs s0..s7, carry (bit 8)."""
    b = B(16)
    sums, carry = [], None
    for i in range(8):
        x, y = b.inp(i), b.inp(8 + i)
        g1 = b.nand(x, y)
        p = b.nand(b.nand(x, g1), b.nand(y, g1))           # x xor y
        if carry is None:
            sums.append(p)
            carry = b.nand(g1, g1)                         # x and y
        else:
            g2 = b.nand(p, carry)
            sums.append(b.nand(b.nand(p, g2), b.nand(carry, g2)))
            carry = b.nand(g1, g2)                         # (x and y) or (p and c)
    buf = [b.nand(s, s) for s in sums + [carry]]          # outputs must be the trailing gates
    return b.file([b.nand(n, n) for n in buf])


PARITY16 = _parity(16, balanced=True)
ADDER8 = _adder8()
PARITY24 = _parity(24, balanced=False)

FILES = {
    "xor": XOR, "xorRenumbered": XOR_RENUMBERED, "xorSwappedInputs": XOR_SWAPPED_INPUTS, "xorDeadGate": XOR_DEAD_GATE,
    "xorDoubleNegation": XOR_DOUBLE_NEG, "and2": AND2, "halfAdder": HALF_ADDER, "parity16": PARITY16,
    "adder8": ADDER8, "parity24": PARITY24,
}


def file_entry(f: bytes) -> dict:
    m = sb.check_combinational(f)
    e = {"file": sb.hx(f), "netlistHash": sb.hx(sb.sha256(f)), **m.as_json(),
         "designKey": sb.hx(sb.design_key(f)), "structuralHash": sb.hx(canon.structural_hash(f))}
    if m.n_in <= sb.MAX_EXHAUSTIVE_INPUTS:
        e["truthTableHash"] = sb.hx(sb.truth_table_hash(f))
    return e


def adder_fn(x: int) -> int:
    return ((x & 0xFF) + (x >> 8)) & 0x1FF


def spec(**kw) -> dict:
    s = {"registrant": ADDR[1], "nIn": 2, "nOut": 1, "target": sb.ZERO32, "maxGates": 4, "unique": False,
         "series": sb.ZERO32, "commitStart": 1000, "commitEnd": 2000, "revealEnd": 3000,
         "recoveryAuthority": sb.ZERO_ADDR, "infoHash": sb.hx(sb.sha256(b"XOR in at most 4 NAND gates (test)"))}
    s.update(kw)
    return s


def salt(n: int) -> bytes:
    return sb.sha256(b"tap-soulbound test salt %d" % n)


def outcome(fn):
    try:
        return {"ok": True, "result": fn()}
    except sb.Reject as e:
        return {"ok": False, "error": e.code}


def build() -> dict:
    v = {"format": "tap-soulbound-credentials-vectors/1",
         "note": "Synthetic test data. Private keys are public test keys; never use them for anything else.",
         "chainId": CHAIN_ID, "contract": CONTRACT}
    v["keys"] = [{"n": n, "private": "0x%064x" % KEYS[n], "address": ADDR[n], "testOnly": True} for n in KEYS]
    v["interfaces"] = sb.interface_table()
    v["eip712"] = {
        "domain": {"name": sb.DOMAIN_NAME, "version": sb.DOMAIN_VERSION, "chainId": CHAIN_ID,
                   "verifyingContract": CONTRACT},
        "domainSeparator": sb.hx(sb.domain_separator(CHAIN_ID, CONTRACT)),
        "types": {t: {"encodeType": sb.encode_type(t), "typeHash": sb.hx(sb.type_hash(t))} for t in sb.TYPES},
    }
    v["files"] = {k: file_entry(f) for k, f in FILES.items()}

    # -- truth tables from functions
    v["truthTables"] = [
        {"name": "xor", "nIn": 2, "nOut": 1, "hash": sb.hx(sb.truth_table_hash_of_function(2, 1, lambda x: (x & 1) ^ (x >> 1)))},
        {"name": "halfAdder", "nIn": 2, "nOut": 2,
         "hash": sb.hx(sb.truth_table_hash_of_function(2, 2, lambda x: ((x & 1) ^ (x >> 1)) | ((x & 1) & (x >> 1)) << 1))},
        {"name": "parity16", "nIn": 16, "nOut": 1,
         "hash": sb.hx(sb.truth_table_hash_of_function(16, 1, lambda x: bin(x).count("1") & 1))},
        {"name": "adder8", "nIn": 16, "nOut": 9, "hash": sb.hx(sb.truth_table_hash_of_function(16, 9, adder_fn))},
        {"name": "and2", "nIn": 2, "nOut": 1, "hash": sb.hx(sb.truth_table_hash_of_function(2, 1, lambda x: (x & 1) & (x >> 1)))},
        {"name": "constOne0", "nIn": 0, "nOut": 1, "bytes": sb.hx(sb.truth_table(0, 1, [1])),
         "hash": sb.hx(sb.truth_table_hash_of_columns(0, 1, [1]))},
        {"name": "xorBytes", "nIn": 2, "nOut": 1, "bytes": sb.hx(sb.truth_table(2, 1, [0b0110]))},
        {"name": "id3Bytes", "nIn": 3, "nOut": 1, "bytes": sb.hx(sb.truth_table(3, 1, [0b10101010]))},
    ]
    for t in v["truthTables"]:
        if t["name"] in v["files"]:
            assert v["files"][t["name"]]["truthTableHash"] == t["hash"], t["name"]

    # -- design keys vs structural hashes
    pairs = []
    names = list(FILES)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            fa, fb = v["files"][a], v["files"][b]
            if (fa["nIn"], fa["nOut"]) != (fb["nIn"], fb["nOut"]):
                continue
            same_dk = fa["designKey"] == fb["designKey"]
            same_sh = fa["structuralHash"] == fb["structuralHash"]
            assert same_dk == same_sh
            pairs.append({"a": a, "b": b, "sameDesignKey": same_dk, "sameStructuralHash": same_sh})
    v["designKeyPairs"] = pairs

    # -- specifications
    tt_xor = v["files"]["xor"]["truthTableHash"]
    specs = {
        "xor4": spec(target=tt_xor),
        "xor4Unique": spec(target=tt_xor, unique=True, series=sb.hx(sb.sha256(b"xor-series")),
                           recoveryAuthority=ADDR[5]),
        "xor4UniqueRound2": spec(target=tt_xor, unique=True, series=sb.hx(sb.sha256(b"xor-series")),
                                 commitStart=3000, commitEnd=4000, revealEnd=5000),
        "parity16": spec(nIn=16, target=v["files"]["parity16"]["truthTableHash"], maxGates=60),
        "adder8": spec(nIn=16, nOut=9, target=v["truthTables"][3]["hash"], maxGates=200),
    }
    v["specs"] = {k: {"spec": s, "specBytes": sb.hx(sb.spec_bytes(s)), "specId": sb.hx(sb.spec_id(s))}
                  for k, s in specs.items()}
    v["bounds"] = {"maxGateWork": sb.MAX_GATE_WORK, "gateOverhead": sb.GATE_OVERHEAD,
                   "maxTableBytes": sb.MAX_TABLE_BYTES, "maxFileBytes": sb.MAX_FILE_BYTES,
                   "rebindDelay": sb.REBIND_DELAY,
                   "examples": [{"nIn": n, "nOut": o, "maxGates": g, "gateWork": sb.gate_work(n, g),
                                 "tableBytes": sb.table_bytes(n, o)}
                                for n, o, g in ((16, 16, 237), (13, 128, 1260), (8, 3120, 3120), (2, 1, 4))]}
    v["specChecks"] = [
        {"name": n, "spec": s, **outcome(lambda s=s: sb.check_spec(s) or "ok")} for n, s in [
            ("ok", specs["xor4"]),
            ("badWindows", spec(target=tt_xor, commitEnd=1000)),
            ("tooManyInputs", spec(nIn=17, target=tt_xor)),
            ("uniqueWithoutSeries", spec(target=tt_xor, unique=True)),
            ("zeroTarget", spec()),
            ("tooMuchGateWork", spec(nIn=16, target=tt_xor, maxGates=238)),
            ("largestGateWork16", spec(nIn=16, target=tt_xor, maxGates=237)),
            ("tableTooLarge", spec(nIn=16, nOut=17, target=tt_xor, maxGates=17)),
            ("reviewerManyOutputs", spec(nIn=13, nOut=4096, target=tt_xor, maxGates=4096)),
            ("maxGatesBelowOutputs", spec(nOut=2, target=tt_xor, maxGates=1)),
        ]]

    # -- commitments
    xor_sid = sb.spec_id(specs["xor4"])
    v["commitments"] = [
        {"spec": sb.hx(xor_sid), "recipient": ADDR[2], "subject": 0, "netlistHash": v["files"]["xor"]["netlistHash"],
         "salt": sb.hx(salt(1)), "commitment": sb.hx(sb.commitment(xor_sid, ADDR[2], 0, sb.sha256(XOR), salt(1)))},
        {"spec": sb.hx(xor_sid), "recipient": ADDR[4], "subject": 1, "netlistHash": v["files"]["xor"]["netlistHash"],
         "salt": sb.hx(salt(2)), "commitment": sb.hx(sb.commitment(xor_sid, ADDR[4], 1, sb.sha256(XOR), salt(2)))},
    ]

    # -- submission checks (content only)
    v["submissions"] = [
        {"spec": sn, "file": fn, **outcome(lambda sn=sn, fn=fn: sb.check_submission(specs[sn], FILES[fn]))}
        for sn, fn in [("xor4", "xor"), ("xor4", "xorRenumbered"), ("xor4", "xorDoubleNegation"), ("xor4", "and2"),
                       ("xor4", "halfAdder"), ("parity16", "parity16"), ("adder8", "adder8")]]

    # -- attestations
    scope = sb.hx(sb.scope_of_label("TapeOut Foundation / contributor / 2026-S1 (test)"))
    badge = v["files"]["halfAdder"]["netlistHash"]
    att = {"issuer": ADDR[3], "recipient": ADDR[2], "subject": 0, "scope": scope, "artifact": badge,
           "evidence": sb.hx(sb.sha256(b"evidence document (test)")), "issuedAt": 1800000000, "expiresAt": 1900000000,
           "deadline": 0, "replaces": 0, "nonce": sb.hx(sb.sha256(b"nonce 1"))}
    att_agent = dict(att, recipient=ADDR[4], subject=1, expiresAt=0, nonce=sb.hx(sb.sha256(b"nonce 2")))
    att_rebind = dict(att, recipient=ADDR[4], replaces=5, nonce=sb.hx(sb.sha256(b"nonce 3")))

    def signed(a, signer):
        h = sb.digest("Attestation", a, CHAIN_ID, CONTRACT)
        sig = credits.sign(KEYS[signer], h)
        return {"message": a, "structHash": sb.hx(sb.hash_struct("Attestation", a)), "digest": sb.hx(h),
                "signer": signer, "signature": sb.hx(sig)}

    v["attestations"] = {"scopeLabel": "TapeOut Foundation / contributor / 2026-S1 (test)", "scope": scope,
                         "valid": signed(att, 3), "agent": signed(att_agent, 3), "rebind": signed(att_rebind, 3),
                         "wrongSigner": signed(att, 2)}
    sig = bytes.fromhex(v["attestations"]["valid"]["signature"][2:])
    r, s, vv = sig[:32], int.from_bytes(sig[32:64], "big"), sig[64]
    high = r + (credits.N - s).to_bytes(32, "big") + bytes([55 - vv])
    v["attestations"]["highS"] = {"signature": sb.hx(high), **outcome(
        lambda: sb.recover_eoa(bytes.fromhex(v["attestations"]["valid"]["digest"][2:]), high))}
    ag = bytes.fromhex(v["attestations"]["agent"]["signature"][2:])
    low_v = ag[:64] + bytes([ag[64] - 27])
    v["attestations"]["agentLowV"] = {"signature": sb.hx(low_v), "note": "the agent signature with v in {0, 1}",
                                      **outcome(lambda: sb.recover_eoa(
                                          bytes.fromhex(v["attestations"]["agent"]["digest"][2:]), low_v))}

    def rebind_msg(old, holder, n):
        rb = {"authority": ADDR[5], "oldTokenId": old, "newHolder": holder, "deadline": 0,
              "nonce": sb.hx(sb.sha256(b"rebind nonce %d" % n))}
        h = sb.digest("Rebind", rb, CHAIN_ID, CONTRACT)
        return {"message": rb, "digest": sb.hx(h), "signature": sb.hx(credits.sign(KEYS[5], h))}

    v["rebind"] = rebind_msg(1, ADDR[3], 1)
    v["rebindToHolder"] = rebind_msg(1, ADDR[4], 2)
    v["rebindVetoed"] = rebind_msg(2, ADDR[1], 3)
    v["rebindLapsed"] = rebind_msg(2, ADDR[1], 4)
    v["rebindReplacement"] = rebind_msg(2, ADDR[5], 5)
    v["rebindReplacement2"] = rebind_msg(2, ADDR[1], 6)

    # -- Design Credits statements carried by a claimed credential (§6, §10.4)
    st_id = sb.sha256(b"design credits statement id (test)")
    xor_design = {"netlistHash": v["files"]["xor"]["netlistHash"], "structuralHash": v["files"]["xor"]["structuralHash"]}
    credit = {"signer": ADDR[2], "signerChainId": 0,
              "subject": {"netlistHash": sb.ZERO32, "structuralHash": xor_design["structuralHash"]}}
    v["claimStatements"] = {
        "statementId": sb.hx(st_id), "claimScope": sb.hx(sb.claim_scope(st_id)),
        "zeroScope": sb.hx(sb.claim_scope(b"\x00" * 32)), "artifact": xor_design, "holder": ADDR[2],
        "cases": [
            {"name": n, "message": m, "revoked": rv, "display": sb.statement_display(m, ADDR[2], CHAIN_ID, xor_design, rv)}
            for n, m, rv in (
                ("holder signed, structural hash matches", credit, False),
                ("contract signer on this chain", dict(credit, signerChainId=CHAIN_ID), False),
                ("signed by another account", dict(credit, signer=ADDR[3]), False),
                ("contract signer on another chain", dict(credit, signerChainId=1), False),
                ("subject is another design",
                 dict(credit, subject={"netlistHash": v["files"]["and2"]["netlistHash"], "structuralHash": sb.ZERO32}),
                 False),
                ("revoked by its signer", credit, True),
            )]}

    # -- scenario on the executable model
    v["scenario"] = scenario(specs, v)
    # -- metadata
    v["metadata"] = metadata_vectors(v, specs)
    # -- differential cases for the Solidity truth table and design key (reviewer's generator, seed 2026)
    v["differential"] = differential()
    return v


def differential() -> list:
    """Random combinational files stressing nIn 0..9 with many outputs (overlapping 32-byte writes for nIn < 8),
    chunk boundaries and nOut = nand. The Solidity `inspect` must return the same design key and truth-table hash."""
    rng = random.Random(2026)

    def comb(n_in, n_gates, n_out):
        recs = []
        for k in range(n_gates):
            hi = 2 + n_in + k
            recs.append((rng.randrange(hi), rng.randrange(hi)))
        data = b"".join(b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big") for a, b in recs)
        return tapnft.encode_file(data, n_in, n_out)

    def case(f):
        m = sb.check_combinational(f)
        return {"nIn": m.n_in, "nOut": m.n_out, "file": sb.hx(f), "designKey": sb.hx(sb.design_key(f)),
                "truthTableHash": sb.hx(sb.truth_table_hash(f))}

    cases = []
    for n_in in list(range(0, 10)) + [16, 15, 12]:
        for _ in range(6 if n_in < 10 else 2):
            n_out = rng.randrange(1, 40) if n_in < 10 else rng.randrange(1, 4)
            cases.append(case(comb(n_in, n_out + rng.randrange(0, 60), n_out)))
    for n_in, n_out in [(0, 37), (1, 33), (2, 65), (3, 9), (7, 3), (8, 5), (0, 1), (16, 2)]:
        cases.append(case(comb(n_in, n_out, n_out)))
    return cases


def scenario(specs: dict, v: dict) -> list:
    iss = sb.Issuer(CHAIN_ID, CONTRACT)
    log = []

    def step(name, fn):
        r = outcome(fn)
        log.append({"step": name, **r})
        return r

    sid = lambda n: sb.spec_id(specs[n])  # noqa: E731
    step("register xor4Unique", lambda: sb.hx(iss.register_spec(specs["xor4Unique"])))
    step("register xor4UniqueRound2", lambda: sb.hx(iss.register_spec(specs["xor4UniqueRound2"])))
    step("register overlapping round (rejected)",
         lambda: sb.hx(iss.register_spec(spec(target=specs["xor4"]["target"], unique=True,
                                              series=specs["xor4Unique"]["series"], commitStart=4500,
                                              commitEnd=4600, revealEnd=4700))))
    step("register a specification beyond the gate-work bound (rejected)",
         lambda: sb.hx(iss.register_spec(spec(nIn=16, target=specs["xor4"]["target"], maxGates=238))))
    c2 = sb.commitment(sid("xor4Unique"), ADDR[2], 0, sb.sha256(XOR), salt(1))
    c4 = sb.commitment(sid("xor4Unique"), ADDR[4], 1, sb.sha256(XOR_RENUMBERED), salt(2))
    step("commit before window (rejected)", lambda: iss.commit(ADDR[2], sid("xor4Unique"), c2, 999))
    step("account 1 copies account 2's pending commitment first (recorded for account 1 only)",
         lambda: iss.commit(ADDR[1], sid("xor4Unique"), c2, 1400))
    step("account 2 commits xor", lambda: iss.commit(ADDR[2], sid("xor4Unique"), c2, 1500))
    step("account 2 commits the same commitment twice (rejected)",
         lambda: iss.commit(ADDR[2], sid("xor4Unique"), c2, 1501))
    step("agent 4 commits renumbered xor", lambda: iss.commit(ADDR[4], sid("xor4Unique"), c4, 1600))
    step("reveal during commit window (rejected)",
         lambda: iss.reveal(sid("xor4Unique"), ADDR[2], 0, XOR, salt(1), 1999))
    step("reveal with wrong salt (rejected)", lambda: iss.reveal(sid("xor4Unique"), ADDR[2], 0, XOR, salt(9), 2000))
    step("reveal account 2 xor (token 1)", lambda: iss.reveal(sid("xor4Unique"), ADDR[2], 0, XOR, salt(1), 2000))
    step("same-round renamed copy accepted (token 2)",
         lambda: iss.reveal(sid("xor4Unique"), ADDR[4], 1, XOR_RENUMBERED, salt(2), 2100))
    c3 = sb.commitment(sid("xor4UniqueRound2"), ADDR[3], 0, sb.sha256(XOR_SWAPPED_INPUTS), salt(3))
    step("round 2: account 3 commits input-swapped xor", lambda: iss.commit(ADDR[3], sid("xor4UniqueRound2"), c3, 3500))
    cw = sb.commitment(sid("xor4UniqueRound2"), ADDR[3], 0, sb.sha256(AND2), salt(4))
    step("round 2: account 3 commits and2", lambda: iss.commit(ADDR[3], sid("xor4UniqueRound2"), cw, 3600))
    step("round 2: renamed copy of round-1 answer rejected",
         lambda: iss.reveal(sid("xor4UniqueRound2"), ADDR[3], 0, XOR_SWAPPED_INPUTS, salt(3), 4000))
    step("round 2: wrong function rejected",
         lambda: iss.reveal(sid("xor4UniqueRound2"), ADDR[3], 0, AND2, salt(4), 4001))
    # proven rebind by the recovery authority, with a delay and the old holder's veto (token 3)
    sig = lambda k: bytes.fromhex(v[k]["signature"][2:])  # noqa: E731
    rb, rh, rv = v["rebind"]["message"], v["rebindToHolder"]["message"], v["rebindVetoed"]["message"]
    step("proven: rebind requested by someone else (rejected)",
         lambda: iss.request_rebind(ADDR[2], rb, sig("rebind"), 5000))
    step("proven: rebind to an account that already holds the specification (rejected)",
         lambda: iss.request_rebind(ADDR[4], rh, sig("rebindToHolder"), 5000))
    step("proven: account 1 requests a rebind of token 2", lambda: iss.request_rebind(ADDR[1], rv, sig("rebindVetoed"), 5000))
    step("proven: veto by a non-holder (rejected)", lambda: iss.veto_rebind(ADDR[1], 2, 5000))
    step("proven: agent 4 vetoes the rebind of its token 2", lambda: iss.veto_rebind(ADDR[4], 2, 5000))
    step("proven: completing a vetoed rebind (rejected)", lambda: iss.complete_rebind(ADDR[1], 2, 5000 + sb.REBIND_DELAY))
    step("proven: account 3 requests a rebind of token 1 (ready at 5000 + delay)",
         lambda: iss.request_rebind(ADDR[3], rb, sig("rebind"), 5000))
    step("proven: the same Rebind sent again while it is pending (rejected: digest used)",
         lambda: iss.request_rebind(ADDR[3], rb, sig("rebind"), 5001))
    step("proven: completion before the delay (rejected)",
         lambda: iss.complete_rebind(ADDR[3], 1, 5000 + sb.REBIND_DELAY - 1))
    step("proven: completion after the delay (token 3)",
         lambda: iss.complete_rebind(ADDR[3], 1, 5000 + sb.REBIND_DELAY))
    step("proven: rebind request replayed (rejected)",
         lambda: iss.request_rebind(ADDR[3], rb, sig("rebind"), 5000 + sb.REBIND_DELAY + 1))
    # claimed (token 4)
    st = sb.sha256(b"design credits statement id (test)")
    step("claimed: account 2 claims xor with a statement id (token 4)",
         lambda: iss.claim(ADDR[2], XOR, st, b"\x00" * 32, 0, 700000))
    step("renounce by non-holder (rejected)", lambda: iss.renounce(ADDR[3], 4))
    step("holder renounces token 4", lambda: iss.renounce(ADDR[2], 4))
    # a request that is not completed lapses; a new authority-signed Rebind replaces a pending or lapsed one
    D, T = sb.REBIND_DELAY, 800000
    rl, r1, r2 = v["rebindLapsed"]["message"], v["rebindReplacement"]["message"], v["rebindReplacement2"]["message"]
    step("proven: account 1 requests a rebind of token 2 (ready at 800000 + delay)",
         lambda: iss.request_rebind(ADDR[1], rl, sig("rebindLapsed"), T))
    step("proven: completion one delay after it became ready (rejected: lapsed)",
         lambda: iss.complete_rebind(ADDR[1], 2, T + 2 * D))
    step("proven: veto of a lapsed request (rejected: nothing pending)", lambda: iss.veto_rebind(ADDR[4], 2, T + 2 * D))
    step("proven: account 5 requests a rebind of token 2, replacing the lapsed request",
         lambda: iss.request_rebind(ADDR[5], r1, sig("rebindReplacement"), T + 2 * D))
    step("proven: account 1 requests again with a new Rebind, replacing the pending request (delay restarts)",
         lambda: iss.request_rebind(ADDR[1], r2, sig("rebindReplacement2"), T + 2 * D + 100))
    step("proven: the replaced new holder tries to complete (rejected)",
         lambda: iss.complete_rebind(ADDR[5], 2, T + 3 * D))
    step("proven: completion before the restarted delay (rejected)",
         lambda: iss.complete_rebind(ADDR[1], 2, T + 3 * D))
    step("proven: agent 4 vetoes the replacement request", lambda: iss.veto_rebind(ADDR[4], 2, T + 3 * D + 50))
    # attested (tokens 5, 6, 7)
    a = v["attestations"]
    sig_of = lambda k: bytes.fromhex(a[k]["signature"][2:])  # noqa: E731
    step("store badge netlist", lambda: sb.hx(iss.store(HALF_ADDER)))
    step("attested: redeem before its issuedAt (rejected)",
         lambda: iss.redeem(ADDR[2], a["valid"]["message"], sig_of("valid"), 1799999999))
    step("attested: redeem after its expiry (rejected)",
         lambda: iss.redeem(ADDR[2], a["valid"]["message"], sig_of("valid"), 1900000000))
    step("attested: redeem by non-recipient (rejected)",
         lambda: iss.redeem(ADDR[1], a["valid"]["message"], sig_of("valid"), 1800000100))
    step("attested: wrong signer (rejected)",
         lambda: iss.redeem(ADDR[2], a["wrongSigner"]["message"], sig_of("wrongSigner"), 1800000100))
    step("attested: redeem (token 5)", lambda: iss.redeem(ADDR[2], a["valid"]["message"], sig_of("valid"), 1800000100))
    step("attested: redeem twice (rejected)",
         lambda: iss.redeem(ADDR[2], a["valid"]["message"], sig_of("valid"), 1800000200))
    step("attested: agent redeem with a v in {0, 1} signature (token 6)",
         lambda: iss.redeem(ADDR[4], a["agent"]["message"], sig_of("agentLowV"), 1800000300))
    step("attested: revoke by non-issuer (rejected)", lambda: iss.revoke_attestation(ADDR[2], a["agent"]["message"]))
    step("attested: issuer revokes agent attestation", lambda: iss.revoke_attestation(ADDR[3], a["agent"]["message"]))
    step("attested: issuer re-issues token 5 to account 4 (token 7)",
         lambda: iss.redeem(ADDR[4], a["rebind"]["message"], sig_of("rebind"), 1800000400))
    now_end = 1800005000
    states = {}
    for t in range(1, iss.next_token):
        states[str(t)] = {"holder": iss.owner.get(t), "credential": iss.tokens[t],
                          "status": {str(now): sb.STATUSES[iss.status(t, now)] for now in (now_end, 1900000000)}}
    log.append({"step": "final token states", "ok": True, "result": states})
    q = lambda *args: outcome(lambda: iss.credentials_of(*args)[0])  # noqa: E731
    log.append({"step": "credentialsOf(account 4, proven, any, any, activeOnly) at 1800005000",
                **q(ADDR[4], 1, sb.ZERO_ADDR, sb.ZERO32, True, now_end)})
    log.append({"step": "credentialsOf(account 4, attested, issuer 3, scope, all)",
                **q(ADDR[4], 2, ADDR[3], a["scope"], False, now_end)})
    log.append({"step": "credentialsOf(account 4, attested, any, any, activeOnly)",
                **q(ADDR[4], 2, sb.ZERO_ADDR, sb.ZERO32, True, now_end)})
    log.append({"step": "credentialsOf(account 4, kind 0) (rejected: one kind per query)",
                **q(ADDR[4], 0, sb.ZERO_ADDR, sb.ZERO32, False, now_end)})
    log.append({"step": "credentialsOf(account 4, proven, limit 0) (rejected)",
                **q(ADDR[4], 1, sb.ZERO_ADDR, sb.ZERO32, False, now_end, 0, 0)})
    # cursors after a renounce: the cursor counts every token minted to the holder, renounced ones included
    step("claimed: account 2 claims and2 (token 8)", lambda: iss.claim(ADDR[2], AND2, b"\x00" * 32, b"\x00" * 32, 0,
                                                                    now_end + 1000))
    step("claimed: account 2 claims the half adder (token 9)",
         lambda: iss.claim(ADDR[2], HALF_ADDER, b"\x00" * 32, b"\x00" * 32, 0, now_end + 1001))
    page = lambda cursor: outcome(lambda: dict(zip(("tokenIds", "nextCursor"), iss.credentials_of(  # noqa: E731
        ADDR[2], 3, sb.ZERO_ADDR, sb.ZERO32, False, now_end + 2000, cursor, 1))))
    log.append({"step": "credentialsOf(account 2, claimed, cursor 0, limit 1) after renouncing token 4", **page(0)})
    log.append({"step": "credentialsOf(account 2, claimed, cursor 4, limit 1)", **page(4)})
    return log


def metadata_vectors(v: dict, specs: dict) -> list:
    f = v["files"]["xor"]
    sp = v["specs"]["xor4Unique"]
    base = {
        "name": "XOR in 4 NAND gates — proven credential (test)",
        "image": "https://example.invalid/sbt/badge-xor.png",
        "tap": {
            "v": 1, "id": f"eip155:{CHAIN_ID}/erc721:{CONTRACT}/1", "state": "revealed",
            "image": {"sha256": sb.hx(sb.sha256(b"badge image (test)")), "uris": ["https://example.invalid/sbt/badge-xor.png"]},
            "netlist": {"format": "tapnet/1", "sha256": f["netlistHash"], "bytes": len(XOR), "nIn": 2, "nOut": 1,
                        "nand": 4, "latch": 0, "uris": ["https://example.invalid/sbt/xor.tapnet"],
                        "structuralHash": f["structuralHash"]},
            "credential": {
                "v": 1, "kind": "proven", "subject": "account",
                "contract": {"chainId": CHAIN_ID, "address": CONTRACT},
                "issuer": ADDR[1], "scope": sp["specId"], "issuedAt": 2000, "expiresAt": 0,
                "spec": {"id": sp["specId"], "nIn": 2, "nOut": 1, "target": sp["spec"]["target"],
                         "maxGates": 4, "unique": True, "series": sp["spec"]["series"],
                         "info": {"sha256": sp["spec"]["infoHash"], "uris": ["https://example.invalid/sbt/xor-spec.md"]}},
            },
        },
    }
    onchain = {"kind": 1, "subject": 0, "issuer": ADDR[1], "scope": sp["specId"], "artifact": f["netlistHash"],
               "evidence": sb.ZERO32, "issuedAt": 2000, "expiresAt": 0, "replaces": 0}

    def variant(name, mutate, oc=None, note=None):
        d = json.loads(json.dumps(base))
        mutate(d["tap"]["credential"], d)
        r = outcome(lambda: sb.check_credential_metadata(d, oc) and "ok")
        e = {"name": name, "doc": d, "onchain": oc, **r}
        if note:
            e["note"] = note
        return e

    a = v["attestations"]

    def attested(c, d):
        c.update(kind="attested", issuer=ADDR[3], scope=a["scope"], scopeLabel=a["scopeLabel"],
                 issuerName="TapeOut Foundation (self-declared, test)", issuedAt=1800000100, expiresAt=1900000000,
                 evidence={"sha256": a["valid"]["message"]["evidence"], "uris": ["https://example.invalid/sbt/ev.json"]})
        del c["spec"]

    def agent(c, d):
        attested(c, d)
        c.update(subject="agent", agent={"registry": "eip155:8453:0x" + "8004" * 10, "agentId": "42"})

    st = v["claimStatements"]

    def claimed(c, d):
        c.update(kind="claimed", issuer=ADDR[2], scope=st["claimScope"], issuedAt=700000,
                 statement={"id": st["statementId"], "uris": ["https://example.invalid/sbt/credit.json"]})
        del c["spec"]

    return [
        variant("proven ok", lambda c, d: None, onchain),
        variant("claimed with statement ok", claimed),
        variant("claimed, statement id not hashed into scope",
                lambda c, d: (claimed(c, d), c.update(scope=st["statementId"]))),
        variant("statement on attested", lambda c, d: (attested(c, d), c.update(
            statement={"id": st["statementId"], "uris": ["https://example.invalid/sbt/credit.json"]}))),
        variant("spec mode member (removed in version 1)", lambda c, d: c["spec"].update(mode="optimistic")),
        variant("tap.image missing", lambda c, d: d["tap"].pop("image")),
        variant("reward member", lambda c, d: c.update(rewardPoints=10)),
        variant("tier member outside the credential", lambda c, d: d.update(tier="gold")),
        variant("weight in ERC-721 attributes",
                lambda c, d: d.update(attributes=[{"trait_type": "Weight", "value": 3}])),
        variant("neutral ERC-721 attributes ok",
                lambda c, d: d.update(attributes=[{"trait_type": "Kind", "value": "proven"},
                                                  {"trait_type": "Cohort", "value": "2026-S1 (test)"}])),
        variant("cohort ok", lambda c, d: c.update(cohort="2026 spring cohort (test)")),
        variant("edition present (credentials form no TAP-721 editions)",
                lambda c, d: d["tap"].update(edition={"index": 1, "of": 2})),
        variant("tap.pod with mining names ok (exempt, its own non-entitlement rules)",
                lambda c, d: d["tap"].update(pod={"standing": {"bonus": "0", "multiplier": 1, "verifWeight": "0"}})),
        variant("bonus member outside tap.pod", lambda c, d: c.update(bonus="1")),
        variant("tap.pod fact repeated in ERC-721 attributes (not exempt)",
                lambda c, d: d.update(attributes=[{"trait_type": "tap.pod.bonus", "value": "0"}])),
        variant("reward wording in description (tool judgement)",
                lambda c, d: d.update(description="Holders will share in future rewards (test)"),
                note="tool judgement: §2 item 3 forbids this text and a tool MUST reject it (§9 item 4); "
                     "the machine check covers member names only, so the result here is ok"),
        variant("proven, on-chain mismatch", lambda c, d: None, dict(onchain, issuedAt=2001)),
        variant("attested ok", attested),
        variant("attested agent ok", agent),
        variant("scopeLabel does not hash to scope", lambda c, d: (attested(c, d), c.update(scopeLabel="other"))),
        variant("issuerName on proven", lambda c, d: c.update(issuerName="Foundation")),
        variant("status in metadata", lambda c, d: c.update(status="active")),
        variant("payout member", lambda c, d: c.update(allocation="100")),
        variant("agent member on account subject", lambda c, d: c.update(agent={"registry": "eip155:1:0x" + "11" * 20,
                                                                               "agentId": "1"})),
        variant("expiry before issuance", lambda c, d: c.update(expiresAt=1000)),
        variant("netlist over maxGates", lambda c, d: c["spec"].update(maxGates=3)),
        variant("manifest present", lambda c, d: d["tap"].update(manifest={"sha256": "0x" + "11" * 32, "uris": ["x"]})),
        variant("bidi control in issuerName",
                lambda c, d: (attested(c, d), c.update(issuerName="Found‮ation"))),
    ]


def main() -> None:
    data = json.dumps(build(), indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    if "--check" in sys.argv:
        with open(OUT, encoding="utf-8") as fh:
            ok = fh.read() == data
        print("vectors.json up to date" if ok else "vectors.json differs")
        sys.exit(0 if ok else 1)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(data)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
