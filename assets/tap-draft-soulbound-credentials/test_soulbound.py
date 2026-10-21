"""Tests for the TAP draft "Soulbound Netlist Credentials". MIT licence.

python3 test_soulbound.py   (standard library; eth_account / cast cross-checks run when installed)
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys

import canon
import credits
import make_vectors as mv
import soulbound as sb
import tap02_reference as tap02
import tapnft

HERE = os.path.dirname(os.path.abspath(__file__))
V = json.load(open(os.path.join(HERE, "vectors.json"), encoding="utf-8"))
FAILS = []


def check(cond: bool, what: str) -> None:
    if not cond:
        FAILS.append(what)
        print("FAIL", what)


def random_comb(rng: random.Random, n_in: int, n_gates: int, n_out: int) -> bytes:
    recs = []
    for k in range(n_gates):
        hi = 2 + n_in + k
        recs.append((rng.randrange(hi), rng.randrange(hi)))
    data = b"".join(b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big") for a, b in recs)
    return tapnft.encode_file(data, n_in, n_out)


def renumber(rng: random.Random, f: bytes) -> bytes:
    """Random topological renumbering that keeps the output gates last and in order, plus input swaps."""
    n_in, n_out, recs = tapnft.decode_file(f)
    els = [tuple(e.ins) for e in tap02.decode(recs, n_in)]
    E = len(els)
    base = 2 + n_in
    outs = list(range(E - n_out, E))
    body = list(range(E - n_out))
    # random topological order of the body
    order, placed = [], set()
    pending = body[:]
    while pending:
        ready = [k for k in pending if all((s < base) or (s - base) in placed for s in els[k])]
        k = rng.choice(ready)
        order.append(k)
        placed.add(k)
        pending.remove(k)
    order += outs
    pos = {k: i for i, k in enumerate(order)}
    m = lambda s: s if s < base else base + pos[s - base]  # noqa: E731
    out = b""
    for k in order:
        a, b = (m(els[k][0]), m(els[k][1]))
        if rng.random() < 0.5:
            a, b = b, a
        out += b"\x00" + a.to_bytes(3, "big") + b.to_bytes(3, "big")
    return tapnft.encode_file(out, n_in, n_out)


def test_vectors_reproduce() -> None:
    data = json.dumps(mv.build(), indent=1, ensure_ascii=False) + "\n"
    check(open(os.path.join(HERE, "vectors.json"), encoding="utf-8").read() == data, "vectors.json reproduces")


def test_files() -> None:
    for name, e in V["files"].items():
        f = bytes.fromhex(e["file"][2:])
        check(sb.hx(sb.design_key(f)) == e["designKey"], f"design key {name}")
        check(sb.hx(canon.structural_hash(f)) == e["structuralHash"], f"structural hash {name}")
        if "truthTableHash" in e:
            check(sb.hx(sb.truth_table_hash(f)) == e["truthTableHash"], f"truth table {name}")


def test_eval_consistency() -> None:
    rng = random.Random(7)
    for _ in range(40):
        n_in = rng.randrange(0, 7)
        f = random_comb(rng, n_in, rng.randrange(1, 20), rng.randrange(1, 4))
        f = tapnft.encode_file(tapnft.decode_file(f)[2], n_in, min(tapnft.decode_file(f)[1], 1))
        m = tapnft.check_file(f)
        cols = sb.eval_all(f)
        c = tap02.load(tapnft.decode_file(f)[2], m.n_in, m.n_out)
        for x in range(1 << n_in):
            bits = [(x >> i) & 1 for i in range(n_in)]
            _, outs = tap02.beat(c, [], bits)
            check(outs == [(col >> x) & 1 for col in cols], "bit-sliced eval equals TAP-02 beat")


def test_design_key_equivalence() -> None:
    """For LATCH-free files: equal design keys <=> equal structural hashes."""
    rng = random.Random(11)
    pool = []
    for _ in range(60):
        n_in = rng.randrange(1, 4)
        f = random_comb(rng, n_in, rng.randrange(2, 9), 1)
        pool.append(f)
        g = renumber(rng, f)
        check(sb.design_key(f) == sb.design_key(g), "renumbering keeps design key")
        check(canon.structural_hash(f) == canon.structural_hash(g), "renumbering keeps structural hash")
        pool.append(g)
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]
            if tapnft.decode_file(a)[:2] != tapnft.decode_file(b)[:2]:
                continue
            check((sb.design_key(a) == sb.design_key(b)) == (canon.structural_hash(a) == canon.structural_hash(b)),
                  "design key equality matches structural hash equality")
    for p in V["designKeyPairs"]:
        check(p["sameDesignKey"] == p["sameStructuralHash"], "vector pair " + p["a"] + "/" + p["b"])


def test_truth_table_layout() -> None:
    t = {x["name"]: x for x in V["truthTables"]}
    check(t["xorBytes"]["bytes"] == "0x00000002000000016" + "0", "xor truth table bytes: 0x60 (0110 then padding)")
    check(t["id3Bytes"]["bytes"] == "0x0000000300000001" + "55", "x0 over 3 inputs: 0101 0101 MSB first")
    check(t["constOne0"]["bytes"] == "0x0000000000000001" + "80", "nIn 0: one byte, MSB")


def test_rejections() -> None:
    xor = mv.XOR
    try:
        sb.check_combinational(tapnft.encode_file(bytes.fromhex("0100000300000002000003"), 1, 1))
        check(False, "latch file rejected")
    except sb.Reject as e:
        check(e.code in ("has-latch", "invalid-file"), "latch file rejected")
    try:
        sb.check_submission(mv.spec(target=sb.hx(sb.truth_table_hash(xor))), xor + b"\x00" * 7 * 7100)
        check(False, "oversized file rejected")
    except sb.Reject as e:
        check(e.code in ("invalid-file", "file-too-large", "too-many-gates"), "oversized file rejected")


def test_attestations() -> None:
    a = V["attestations"]
    for k in ("valid", "agent", "rebind", "wrongSigner"):
        e = a[k]
        h = sb.digest("Attestation", e["message"], V["chainId"], V["contract"])
        check(sb.hx(h) == e["digest"], f"attestation digest {k}")
        signer = sb.recover_eoa(h, bytes.fromhex(e["signature"][2:]))
        check(signer == V["keys"][e["signer"] - 1]["address"], f"attestation signer {k}")
    check(a["highS"]["ok"] is False and a["highS"]["error"] == "high-s", "high-s rejected")
    check(sb.hx(sb.scope_of_label(a["scopeLabel"])) == a["scope"], "scope label hash")


def test_commitments_per_committer() -> None:
    """B1: a copied commitment is recorded for the copier and cannot occupy the recipient's commitment."""
    iss = sb.Issuer(V["chainId"], V["contract"])
    s = mv.spec(target=V["files"]["xor"]["truthTableHash"])
    sid = iss.register_spec(s)
    c = sb.commitment(sid, mv.ADDR[2], 0, sb.sha256(mv.XOR), mv.salt(1))
    iss.commit(mv.ADDR[1], sid, c, 1000)           # front-runner first
    iss.commit(mv.ADDR[2], sid, c, 1001)           # the recipient still commits
    r = iss.reveal(sid, mv.ADDR[2], 0, mv.XOR, mv.salt(1), 2000)
    check(r["token"] == 1 and iss.owner[1] == mv.ADDR[2], "recipient mints despite a copied commitment")
    try:
        iss.reveal(sid, mv.ADDR[1], 0, mv.XOR, mv.salt(1), 2001)
        check(False, "copier cannot reveal the copied commitment")
    except sb.Reject as e:
        check(e.code == "no-commitment", "copier cannot reveal the copied commitment")


def test_bounds() -> None:
    b = V["bounds"]
    check(b["maxGateWork"] == 1 << 16 and b["maxTableBytes"] == 1 << 17 and b["gateOverhead"] == 20, "bounds")
    for e in b["examples"]:
        check(e["gateWork"] == sb.gate_work(e["nIn"], e["maxGates"]) <= b["maxGateWork"], "gate work example")
        check(e["tableBytes"] == sb.table_bytes(e["nIn"], e["nOut"]) <= b["maxTableBytes"], "table example")
    check(sb.gate_work(16, 238) > b["maxGateWork"] and sb.table_bytes(16, 17) > b["maxTableBytes"], "bounds are tight")


def test_claim_statements() -> None:
    st = V["claimStatements"]
    check(sb.hx(sb.claim_scope(bytes.fromhex(st["statementId"][2:]))) == st["claimScope"], "claim scope")
    check(st["claimScope"] != st["statementId"] and st["zeroScope"] == sb.ZERO32, "claim scope is domain-separated")
    for c in st["cases"]:
        got = sb.statement_display(c["message"], st["holder"], V["chainId"], st["artifact"], c["revoked"])
        check(got == c["display"], "statement display " + c["name"])


def test_scenario_replays() -> None:
    check(mv.scenario({k: e["spec"] for k, e in V["specs"].items()}, V) == V["scenario"], "scenario replays")


def test_eth_account() -> None:
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data
    except ImportError:
        print("skip eth_account cross-check (not installed)")
        return
    types = {t: [{"name": n, "type": ty} for n, ty in sb.TYPES[t]] for t in sb.TYPES}
    for k, primary in (("valid", "Attestation"), ("agent", "Attestation")):
        e = V["attestations"][k]
        msg = dict(e["message"])
        full = {"types": {"EIP712Domain": types["EIP712Domain"], primary: types[primary]}, "primaryType": primary, "domain": V["eip712"]["domain"], "message": msg}
        sm = encode_typed_data(full_message=full)
        key = V["keys"][e["signer"] - 1]["private"]
        signed = Account.sign_message(sm, private_key=key)
        check("0x" + signed.signature.hex().removeprefix("0x") == e["signature"], f"eth_account signature {k}")
    r = V["rebind"]
    full = {"types": {"EIP712Domain": types["EIP712Domain"], "Rebind": types["Rebind"]}, "primaryType": "Rebind", "domain": V["eip712"]["domain"], "message": r["message"]}
    signed = Account.sign_message(encode_typed_data(full_message=full), private_key=V["keys"][4]["private"])
    check("0x" + signed.signature.hex().removeprefix("0x") == r["signature"], "eth_account rebind signature")


def test_interface_ids_cast() -> None:
    if shutil.which("cast") is None:
        print("skip cast cross-check")
        return
    for s, sel in list(V["interfaces"]["selectors"].items())[:6]:
        out = subprocess.run(["cast", "sig", s], capture_output=True, text=True).stdout.strip()
        check(out == sel, f"cast sig {s}")


def test_metadata() -> None:
    for m in V["metadata"]:
        r = mv.outcome(lambda: sb.check_credential_metadata(m["doc"], m["onchain"]) and "ok")
        check(r["ok"] == m["ok"] and r.get("error") == m.get("error"), "metadata " + m["name"])


def test_pinned_hash_in_spec() -> None:
    import hashlib
    h = hashlib.sha256(open(os.path.join(HERE, "vectors.json"), "rb").read()).hexdigest()
    # The English text is required; the translation is checked when it is present (it is added as
    # TAP-<nn>.zh.md after a number is assigned).
    for name in ("TAP-draft-soulbound-credentials.md", "TAP-draft-soulbound-credentials.zh.md"):
        path = os.path.join(HERE, "..", "..", "TAPs", name)
        if not os.path.exists(path):
            if name.endswith(".zh.md"):
                continue
            check(False, f"{name} exists")
            continue
        text = open(path, encoding="utf-8").read()
        check(h in text, f"{name} pins the SHA-256 of vectors.json")
        for k in ("ITapCredential", "ITapCredentialProven", "ITapCredentialAttested", "ITapCredentialClaimed"):
            check(V["interfaces"][k] in text, f"{name} lists the ERC-165 id of {k}")
        check(V["eip712"]["types"]["Attestation"]["typeHash"] in text, f"{name} lists the Attestation type hash")


def test_differential() -> None:
    for i, c in enumerate(V["differential"]):
        f = bytes.fromhex(c["file"][2:])
        check(sb.hx(sb.design_key(f)) == c["designKey"] and sb.hx(sb.truth_table_hash(f)) == c["truthTableHash"],
              f"differential case {i}")


def _expect(fn, code: str, what: str) -> None:
    try:
        fn()
        check(False, what)
    except sb.Reject as e:
        check(e.code == code, f"{what} ({e.code})")


def _proven(iss, s, who, f, salt_n, t):
    sid = sb.spec_id(s)
    iss.commit(who, sid, sb.commitment(sid, who, 0, sb.sha256(f), mv.salt(salt_n)), s["commitStart"])
    return iss.reveal(sid, who, 0, f, mv.salt(salt_n), t)["token"]


def test_series_records_every_round() -> None:
    """M2: a unique round rejects a design revealed in an earlier non-unique round of the same series."""
    iss = sb.Issuer(V["chainId"], V["contract"])
    tt, series = V["files"]["xor"]["truthTableHash"], sb.hx(sb.sha256(b"m2 series"))
    r1 = mv.spec(target=tt, series=series)
    r2 = mv.spec(target=tt, series=series, unique=True, commitStart=3000, commitEnd=4000, revealEnd=5000)
    iss.register_spec(r1)
    iss.register_spec(r2)
    _proven(iss, r1, mv.ADDR[1], mv.XOR, 1, 2000)
    _expect(lambda: _proven(iss, r2, mv.ADDR[2], mv.XOR_SWAPPED_INPUTS, 2, 4000), "duplicate-design",
            "unique round sees a non-unique earlier round")


def test_rebind_lapse_replace_renounce() -> None:
    """M1: a pending request lapses, can be replaced by a new Rebind, and ends when the old token is renounced."""
    keys = {mv.ADDR[5]: mv.KEYS[5]}
    iss = sb.Issuer(V["chainId"], V["contract"])
    s = mv.spec(target=V["files"]["xor"]["truthTableHash"], recoveryAuthority=mv.ADDR[5])
    iss.register_spec(s)
    t = _proven(iss, s, mv.ADDR[2], mv.XOR, 1, 2000)
    D = sb.REBIND_DELAY

    def req(holder, n, now):
        rb = {"authority": mv.ADDR[5], "oldTokenId": t, "newHolder": holder, "deadline": 0,
              "nonce": sb.hx(sb.sha256(b"unit rebind %d" % n))}
        h = sb.digest("Rebind", rb, V["chainId"], V["contract"])
        return iss.request_rebind(holder, rb, credits.sign(keys[mv.ADDR[5]], h), now)

    req(mv.ADDR[3], 1, 10000)
    _expect(lambda: iss.complete_rebind(mv.ADDR[3], t, 10000 + 2 * D), "rebind-lapsed", "lapsed request")
    check(iss.pending_rebind(t, 10000 + 2 * D) is None, "lapsed request is not pending")
    req(mv.ADDR[4], 2, 10000 + 2 * D)
    req(mv.ADDR[3], 3, 10000 + 2 * D + 5)
    check(iss.pending_rebind(t, 10000 + 2 * D + 5) == (mv.ADDR[3], 10000 + 3 * D + 5), "replacement restarts delay")
    iss.renounce(mv.ADDR[2], t)
    check(t not in iss.pending, "renounce ends the pending request")
    _expect(lambda: iss.complete_rebind(mv.ADDR[3], t, 10000 + 3 * D + 5), "no-pending-rebind", "after renounce")


def test_cursor_after_renounce() -> None:
    """MINOR-2: the cursor indexes every token minted to the holder, renounced ones included (as in Solidity)."""
    iss = sb.Issuer(V["chainId"], V["contract"])
    u = mv.ADDR[2]
    a = iss.claim(u, mv.XOR, b"\x00" * 32, b"\x00" * 32, 0, 1)
    iss.claim(u, mv.AND2, b"\x00" * 32, b"\x00" * 32, 0, 1)
    c = iss.claim(u, mv.HALF_ADDER, b"\x00" * 32, b"\x00" * 32, 0, 1)
    iss.renounce(u, a)
    ids, nxt = iss.credentials_of(u, 3, sb.ZERO_ADDR, sb.ZERO32, False, 1, 0, 1)
    check(ids == [a + 1] and nxt == 2, "first page skips the renounced token, cursor 2")
    ids, nxt = iss.credentials_of(u, 3, sb.ZERO_ADDR, sb.ZERO32, False, 1, nxt, 1)
    check(ids == [c] and nxt == 0, "second page")


def test_attested_accumulate_and_reissue_expired() -> None:
    """MINOR-3: attested credentials of one issuer and scope accumulate; an expired one can be re-issued."""
    iss = sb.Issuer(V["chainId"], V["contract"])
    iss.store(mv.HALF_ADDER)
    base = dict(V["attestations"]["valid"]["message"])

    def redeem(a, now):
        h = sb.digest("Attestation", a, V["chainId"], V["contract"])
        return iss.redeem(a["recipient"], a, credits.sign(mv.KEYS[3], h), now)

    t1 = redeem(base, 1800000100)
    check(iss.status(t1, 1900000000) == sb.STATUS_EXPIRED, "expired")
    t2 = redeem(dict(base, recipient=mv.ADDR[4], issuedAt=1900000000, expiresAt=0, replaces=t1,
                     nonce=sb.hx(sb.sha256(b"u1"))), 1900000001)
    check(iss.status(t1, 1900000001) == sb.STATUS_SUPERSEDED and iss.status(t2, 1900000001) == sb.STATUS_ACTIVE,
          "expired credential re-issued")
    redeem(dict(base, recipient=mv.ADDR[4], issuedAt=1900000000, expiresAt=0, nonce=sb.hx(sb.sha256(b"u2"))),
           1900000002)
    ids, _ = iss.credentials_of(mv.ADDR[4], 2, mv.ADDR[3], base["scope"], True, 1900000003)
    check(len(ids) == 2, "two active attested credentials of one issuer and scope")


def test_python_version_safe() -> None:
    check(sys.version_info >= (3, 9), "python >= 3.9")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK" if not FAILS else f"{len(FAILS)} failures")
    sys.exit(1 if FAILS else 0)
