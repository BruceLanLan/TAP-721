#!/usr/bin/env python3
"""Generate vectors.json for the draft "Design Credits and Lineage for TapeOut Netlists".

MIT licence. Standard library only (plus credits.py and the copied TAP-721 files).
Deterministic: running it twice gives the same bytes. Inputs: chain-reads.json
(fetch_reads.py) and occurrences.json (scan_occurrences.py), both recorded read-only.

ALL PRIVATE KEYS BELOW ARE TEST-ONLY: keccak256("tap-design-credits test key <n>").
They are public and must never hold funds or sign anything real.

    python3 make_vectors.py            # writes vectors.json, prints its SHA-256
    python3 make_vectors.py --check    # fails if vectors.json differs
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys

import credits as c

HERE = os.path.dirname(os.path.abspath(__file__))
Z = c.ZERO32
XOR_NETLIST = "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e"
XOR_STRUCT = "0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b"
XOR5_STRUCT = "0x5b14f1ebd0f77af7735c51748ed0be067df673d628ead9928157e71374516f7e"  # xor_5nand
ANDNOT_STRUCT = "0xff38f0eecca6e6272de2fc4f23f9acaa251ce3c6b6996a3765c51a3c4bf09d53"
NOSRC = {"chainId": 0, "processor": c.ZERO20, "circuitId": "0"}


def key(n: int) -> int:
    return int.from_bytes(c.keccak256(f"tap-design-credits test key {n}".encode()), "big")


KEYS = {lab: key(n) for n, lab in enumerate("ABCDE", start=1)}
ADDR = {lab: c.address_of_key(k) for lab, k in KEYS.items()}


def nonce(label: str) -> str:
    return "0x" + c.keccak256(b"nonce:" + label.encode()).hex()


def credit(who: str, role: str = "designer", subject=None, source=None, display="", note=("", Z), lic="",
           issued=1792000000, n="1", chain=0, signer=None) -> dict:
    return {"signer": signer or ADDR[who], "signerChainId": chain,
            "subject": subject or {"netlistHash": Z, "structuralHash": XOR_STRUCT},
            "source": source or dict(NOSRC), "role": role, "displayName": display, "noteURI": note[0],
            "noteSha256": note[1], "license": lic, "issuedAt": issued, "nonce": nonce(who + n)}


def lineage(who: str, rel: str, subj: str, obj: str, reason: str = "", n="1") -> dict:
    return {"signer": ADDR[who], "signerChainId": 0, "subject": {"netlistHash": Z, "structuralHash": subj},
            "relation": rel, "object": {"netlistHash": Z, "structuralHash": obj}, "reason": reason,
            "issuedAt": 1792000100, "nonce": nonce(who + rel + n)}


def revocation(who: str, target: str, reason: str = "") -> dict:
    return {"signer": ADDR[who], "signerChainId": 0, "statement": target, "reason": reason, "issuedAt": 1792000200}


def env(t: str, m: dict, who: str) -> dict:
    return c.make_envelope(t, m, KEYS[who])


def raw_env(t: str, m: dict, sig: bytes) -> dict:
    return {"tapCredit": 1, "type": t, "message": m, "signature": "0x" + sig.hex()}


def dig(t: str, m: dict) -> str:
    return "0x" + c.digest(t, m).hex()


# ---------------------------------------------------------------------------

def typed_data(t: str, m: dict) -> dict:
    """The eth_signTypedData_v4 payload of a statement (Appendix A of the draft)."""
    used = [t] + sorted(c._deps(t, set()))
    return {"types": {n: [{"name": a, "type": b} for a, b in c.TYPES[n]] for n in ["EIP712Domain"] + used},
            "primaryType": t, "domain": {"name": c.DOMAIN_NAME, "version": c.DOMAIN_VERSION}, "message": m}


def typed_data_json(td: dict) -> str:
    """The exact text of Appendix A (two-space indent, UTF-8, keys in the order above, one
    line per type member)."""
    return re.sub(r'\{\n\s+"name": ("[^"]*"),\n\s+"type": ("[^"]*")\n\s+\}', r'{ "name": \1, "type": \2 }',
                  json.dumps(td, indent=2, ensure_ascii=False))


def sec_eip712() -> dict:
    m = credit_full_message()
    td = typed_data("Credit", m)
    return {"domain": {"name": c.DOMAIN_NAME, "version": c.DOMAIN_VERSION},
            "domainSeparator": "0x" + c.domain_separator().hex(),
            "types": {t: {"encodeType": c.encode_type(t), "typeHash": "0x" + c.type_hash(t).hex()}
                      for t in ("EIP712Domain", "DesignRef", "Circuit", "Credit", "Lineage", "Revocation")},
            "typedDataExample": {"note": "eth_signTypedData_v4 payload of valid/credit_full; Appendix A of the draft quotes typedDataJson verbatim",
                                 "typedData": td, "typedDataJson": typed_data_json(td), "digest": dig("Credit", m),
                                 "signature": env("Credit", m, "A")["signature"], "signer": ADDR["A"]}}


def sec_keys() -> list:
    return [{"label": lab, "testOnly": True, "derivation": f'keccak256("tap-design-credits test key {n}")',
             "privateKey": "0x" + KEYS[lab].to_bytes(32, "big").hex(), "address": ADDR[lab]}
            for n, lab in enumerate("ABCDE", start=1)]


NOTE = b"# XOR in four NAND\nA note for test vectors only.\n"
NOTE_HASH = "0x" + hashlib.sha256(NOTE).hexdigest()


def credit_full_message() -> dict:
    src = {"chainId": 56, "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", "circuitId": "17851"}
    return credit("A", subject={"netlistHash": XOR_NETLIST, "structuralHash": XOR_STRUCT}, source=src,
                  display="Ada (test) — 测试", note=("ipfs://bafy-test-note", NOTE_HASH), lic="CC0-1.0", n="2")


def valid_cases() -> list:
    cases = [
        ("credit_minimal", "Credit", credit("A"), "A"),
        ("credit_full", "Credit", credit_full_message(), "A"),
        ("credit_netlist_only", "Credit", credit("B", role="co-designer",
                                                 subject={"netlistHash": XOR_NETLIST, "structuralHash": Z}), "B"),
        ("credit_reviewer", "Credit", credit("D", role="reviewer", lic="https://example.invalid/licence"), "D"),
        ("lineage_derivedFrom", "Lineage", lineage("B", "derivedFrom", XOR5_STRUCT, XOR_STRUCT, "started from the 4-NAND XOR"), "B"),
        ("lineage_supersedes", "Lineage", lineage("A", "supersedes", XOR_STRUCT, XOR5_STRUCT), "A"),
        ("lineage_optimizes", "Lineage", lineage("C", "optimizes", XOR_STRUCT, XOR5_STRUCT, "4 NAND instead of 5"), "C"),
    ]
    out = []
    for name, t, m, who in cases:
        e = env(t, m, who)
        out.append({"name": name, "envelope": e, "digest": dig(t, m), "expect": {"status": "valid", "signer": ADDR[who]}})
    # revocation of credit_minimal by its signer
    m = revocation("A", out[0]["digest"], "test revocation")
    out.append({"name": "revocation", "envelope": env("Revocation", m, "A"), "digest": dig("Revocation", m),
                "expect": {"status": "valid", "signer": ADDR["A"]}})
    # same statement with v in {0, 1}
    e = copy.deepcopy(out[0]["envelope"])
    sig = bytes.fromhex(e["signature"][2:])
    e["signature"] = "0x" + (sig[:64] + bytes([sig[64] - 27])).hex()
    out.append({"name": "credit_minimal_v01", "envelope": e, "digest": out[0]["digest"],
                "expect": {"status": "valid", "signer": ADDR["A"]}})
    return out


def invalid_cases() -> list:
    base_m = credit("A", n="inv")
    base = env("Credit", base_m, "A")
    sig = bytes.fromhex(base["signature"][2:])
    r, s, v = sig[:32], int.from_bytes(sig[32:64], "big"), sig[64]
    out = []

    def add(name, e, err):
        out.append({"name": name, "envelope": e, "expect": {"status": "invalid", "error": err}})

    m = dict(base_m, signer=ADDR["B"])
    add("signer_mismatch", raw_env("Credit", m, c.sign(KEYS["A"], c.digest("Credit", m))), "signer-mismatch")
    add("high_s", raw_env("Credit", base_m, r + (c.N - s).to_bytes(32, "big") + bytes([55 - v])), "high-s")
    add("bad_v", raw_env("Credit", base_m, sig[:64] + bytes([29])), "bad-v")
    add("r_zero", raw_env("Credit", base_m, bytes(32) + sig[32:]), "bad-r-s")
    add("short_signature", raw_env("Credit", base_m, sig[:64]), "bad-signature-length")
    t = copy.deepcopy(base)
    t["message"]["displayName"] = "Mallory"
    add("tampered_after_signing", t, "signer-mismatch")

    def signed(name, m, err, typ="Credit"):
        # signed with A's key without the field checks of make_envelope
        add(name, raw_env(typ, m, c.sign(KEYS["A"], c.digest(typ, m)) if _encodable(typ, m) else sig), err)

    signed("empty_subject", dict(base_m, subject={"netlistHash": Z, "structuralHash": Z}), "empty-subject")
    signed("role_author", dict(base_m, role="author"), "bad-role")
    signed("role_uppercase", dict(base_m, role="Designer"), "bad-role")
    signed("source_partial", dict(base_m, source={"chainId": 56, "processor": c.ZERO20, "circuitId": "17851"}), "bad-source")
    signed("source_circuit_number", dict(base_m, source={"chainId": 56, "processor": ADDR["C"], "circuitId": 17851}), "bad-source")
    signed("note_uri_without_hash", dict(base_m, noteURI="ipfs://x"), "note-mismatch")
    signed("note_hash_without_uri", dict(base_m, noteSha256=NOTE_HASH), "note-mismatch")
    signed("display_rlo", dict(base_m, displayName="evil‮gnp.exe"), "bad-text")
    signed("display_control", dict(base_m, displayName="a\nb"), "bad-text")
    signed("display_65_bytes", dict(base_m, displayName="x" * 65), "bad-text")
    signed("display_not_nfc", dict(base_m, displayName="é"), "bad-text")
    signed("license_non_ascii", dict(base_m, license="CC0–1.0"), "bad-text")
    signed("uppercase_hex", dict(base_m, nonce=base_m["nonce"].upper().replace("0X", "0x")), "bad-field")
    signed("signer_zero", dict(base_m, signer=c.ZERO20), "bad-field")
    signed("issuedAt_string", dict(base_m, issuedAt="1792000000"), "bad-field")
    extra = dict(base_m)
    extra["extra"] = 1
    add("extra_member", raw_env("Credit", extra, sig), "bad-field")
    signed("lineage_self_edge", lineage("A", "derivedFrom", XOR_STRUCT, XOR_STRUCT), "self-edge", "Lineage")
    signed("lineage_bad_relation", dict(lineage("A", "inspiredBy", XOR_STRUCT, XOR5_STRUCT)), "bad-relation", "Lineage")
    signed("revocation_zero", revocation("A", Z), "bad-field", "Revocation")
    e = copy.deepcopy(base)
    e["tapCredit"] = 2
    add("envelope_version", e, "bad-envelope")
    e = copy.deepcopy(base)
    e["type"] = "Attestation"
    add("unknown_type", e, "unknown-type")
    e = copy.deepcopy(base)
    e["note"] = "unsigned extra member"
    add("envelope_extra_member", e, "bad-envelope")
    return out


def _encodable(t, m) -> bool:
    try:
        c.digest(t, m)
        return True
    except (ValueError, KeyError, TypeError):
        return False


CONTAINER_A = "0x" + "a1" * 20  # synthetic contract accounts on X Layer (196)
CONTAINER_B = "0x" + "b2" * 20
MAGIC = "0x1626ba7e" + "00" * 28
REJECT = "0xffffffff" + "00" * 28


def call_rec(account: str, d: str, block: int, ok: bool, chain: int = 196) -> dict:
    return {"chainId": chain, "account": account, "digest": d, "block": block, "result": MAGIC if ok else REJECT}


def contract_env(m: dict, who: str = "A") -> dict:
    """A contract-signer envelope: the signature is what the holder's key (test key `who`) signs."""
    t = "Credit" if "role" in m else ("Lineage" if "relation" in m else "Revocation")
    return raw_env(t, m, c.sign(KEYS[who], c.digest(t, m)))


def sec_erc1271() -> list:
    """Synthetic isValidSignature results. `recorded` lists calls (chain, account, digest, block,
    result); `verificationBlocks` is the finality-tag block the verifier pinned per chain (§4.6
    item 4); `containers` maps "<chainId>:<address>" to the circuit name of a TapeOut container."""
    m = credit("A", signer=CONTAINER_A, chain=196, n="1271")
    d = dig("Credit", m)
    e = contract_env(m)
    m_b = dict(m, signer=CONTAINER_B)
    e_b = {"tapCredit": 1, "type": "Credit", "message": m_b, "signature": e["signature"]}
    m_eth = dict(m, signerChainId=1)
    e_eth = contract_env(m_eth)

    def case(name, envl, recorded, vb, expect, containers=None, note=None):
        x = {"name": name, "envelope": envl, "digest": dig("Credit", envl["message"]), "synthetic": True,
             "recorded": recorded, "verificationBlocks": vb, "containers": containers or {}, "expect": expect}
        if note:
            x["note"] = note
        return x

    return [
        case("contract_valid", e, [call_rec(CONTAINER_A, d, 73500000, True)], {"196": 73500000},
             {"status": "valid", "validAt": {"chainId": 196, "block": 73500000}}),
        case("contract_rejects", e, [call_rec(CONTAINER_A, d, 73600000, False)], {"196": 73600000},
             {"status": "invalid", "error": "erc1271-invalid"}),
        case("contract_unreadable", e, [], {}, {"status": "unverified", "error": "erc1271-unverified"}),
        case("replay_to_other_account", e_b, [call_rec(CONTAINER_B, dig("Credit", m_b), 73500000, False)], {"196": 73500000},
             {"status": "invalid", "error": "erc1271-invalid"},
             note="Same signature presented for a second account with the same owner: the digest differs because signer is signed, so the owner never signed it."),
        case("contract_signature_never_recovered", e, [], {}, {"status": "unverified", "error": "erc1271-unverified"},
             note="signerChainId != 0: public-key recovery is never used, even though the signature recovers to a real key."),
        case("chain_not_in_tap10", e_eth, [call_rec(CONTAINER_A, dig("Credit", m_eth), 23000000, True, chain=1)], {"1": 23000000},
             {"status": "unverified", "error": "erc1271-chain-unsupported"},
             note="Chain 1 is not in the chain table of TAP-10 §2.1: the statement is unverified, whatever a node of that chain answers."),
        case("container_labelled", e, [call_rec(CONTAINER_A, d, 73500000, True)], {"196": 73500000},
             {"status": "valid", "validAt": {"chainId": 196, "block": 73500000}, "container": "1.2.282.tape",
              "label": c.container_label("1.2.282.tape")},
             containers={"196:" + CONTAINER_A: "1.2.282.tape"},
             note="The signer resolves (TAP-10 §4.3) to the container of 1.2.282.tape: its validity follows the circuit's holder."),
    ]


def sec_revocations() -> list:
    a1 = env("Credit", credit("A", n="r1"), "A")
    b1 = env("Credit", credit("B", n="r1"), "B")
    da1, db1 = a1and_digest(a1), a1and_digest(b1)
    rev_a = env("Revocation", revocation("A", da1, "mine"), "A")
    rev_by_b = env("Revocation", revocation("B", da1, "not mine"), "B")
    rev_rev = env("Revocation", revocation("A", a1and_digest(rev_a)), "A")
    pending = env("Revocation", revocation("B", "0x" + "77" * 32), "B")
    out = [
        {"name": "own_revocation", "envelopes": [a1, rev_a], "expect": ["revoked", "revocation"]},
        {"name": "foreign_revocation_void", "envelopes": [b1, rev_by_b, a1], "expect": ["active", "void-revocation", "active"]},
        {"name": "revoking_a_revocation_is_void", "envelopes": [a1, rev_a, rev_rev], "expect": ["revoked", "revocation", "void-revocation"]},
        {"name": "pending_revocation", "envelopes": [pending, b1], "expect": ["revocation", "active"]},
        {"name": "order_independent", "envelopes": [rev_a, a1], "expect": ["revocation", "revoked"]},
    ]
    # Contract signer (synthetic container on X Layer): validity of the claim and of its
    # revocation are judged at one verification block.
    cm = credit("A", signer=CONTAINER_A, chain=196, n="rc")
    ce = contract_env(cm)
    rm = dict(revocation("A", dig("Credit", cm), "withdrawn"), signer=CONTAINER_A, signerChainId=196)
    re_ = contract_env(rm)
    dc, dr = dig("Credit", cm), dig("Revocation", rm)
    calls = [call_rec(CONTAINER_A, dc, 73500000, True), call_rec(CONTAINER_A, dr, 73500000, True),
             call_rec(CONTAINER_A, dc, 73600000, True), call_rec(CONTAINER_A, dr, 73600000, True)]
    out += [
        {"name": "contract_revocation_same_block", "synthetic": True, "envelopes": [ce, re_], "recorded": calls,
         "verificationBlocks": [{"196": 73500000}, {"196": 73500000}], "expect": ["revoked", "revocation"]},
        {"name": "contract_revocation_other_block", "synthetic": True, "envelopes": [ce, re_], "recorded": calls,
         "verificationBlocks": [{"196": 73500000}, {"196": 73600000}], "expect": ["unverified", "revocation-unjudged"],
         "note": "Verified at different blocks: the tool must judge both at one block before it shows the claim as active or revoked."},
        {"name": "contract_revocation_unverified", "synthetic": True, "envelopes": [ce, re_], "recorded": calls[:1],
         "verificationBlocks": [{"196": 73500000}, {"196": 73500000}], "expect": ["unverified", "revocation-unjudged"],
         "note": "The revocation could not be checked at the claim's verification block, so the claim is not shown as active."},
    ]
    return out


def a1and_digest(e: dict) -> str:
    return dig(e["type"], e["message"])


# ---------------------------------------------------------------------------
# Publication facts from recorded reads

def load_reads() -> dict:
    with open(os.path.join(HERE, "chain-reads.json")) as f:
        return json.load(f)


def reads_for(cr: dict, circ: dict) -> dict:
    pb = cr["pinnedBlock"]
    return {"isCPU": circ["isCPU"], "receipt": circ["receipt"], "block": circ["block"],
            "circuitInfo": circ["circuitInfo"], "stateBlock": pb["number"], "finalityTag": pb["tag"],
            "finalityBlock": pb["reportedBy"], "cpuAt": circ["cpuAt"],
            "processorNumber": circ["processorNumber"], "areaCode": None}


def fact_for(circ: dict) -> dict:
    rec = next(iter(circ["receipt"].values()))
    mint = [l for l in rec["logs"] if l["address"] == circ["processor"] and l["topics"][0] == c.TRANSFER_TOPIC][0]
    blk = next(iter(circ["block"].values()))
    import tapnft
    return {"chainId": 56, "processor": circ["processor"], "circuitId": str(circ["circuitId"]),
            "name": tapnft.tape_name(circ["circuitId"], circ["processorNumber"], None),
            "publisher": "0x" + mint["topics"][2][-40:], "block": int(rec["blockNumber"], 16),
            "blockHash": rec["blockHash"], "txHash": rec["transactionHash"], "logIndex": int(mint["logIndex"], 16),
            "timestamp": int(blk["timestamp"], 16), "txFrom": rec["from"]}


def design_for(circ: dict) -> dict:
    info = next(iter(circ["circuitInfo"].values()))
    nl = bytes.fromhex(next(iter(circ["netlist"].values()))[2:])
    return c.design_of(nl, int(info[2:66], 16), int(info[66:130], 16))


def sec_publication(cr: dict) -> dict:
    out = {"facts": [], "failures": []}
    for circ in cr["circuits"]:
        f = fact_for(circ)
        rd = reads_for(cr, circ)
        res = c.verify_publication(f, rd)
        out["facts"].append({"label": circ["label"], "fact": f, "reads": rd, "design": design_for(circ),
                             "expect": res})
    circ = cr["circuits"][0]
    f0, rd0 = fact_for(circ), reads_for(cr, circ)

    def fail(name, f=None, rd=None, expect=None):
        f = f or f0
        rd = rd or rd0
        res = c.verify_publication(f, rd)
        assert res["status"] == expect[0] and res.get("error") == expect[1], (name, res)
        out["failures"].append({"name": name, "fact": f, "readsFrom": circ["label"],
                                "readsOverride": {k: v for k, v in rd.items() if rd0.get(k) != v},
                                "expect": {"status": expect[0], "error": expect[1]}})

    fail("wrong_publisher", dict(f0, publisher=ADDR["A"]), expect=("failed", "publisher-mismatch"))
    fail("wrong_log_index", dict(f0, logIndex=f0["logIndex"] + 1), expect=("failed", "publisher-mismatch"))
    fail("wrong_circuit", dict(f0, circuitId="17852"), expect=("failed", "no-mint-log"))
    fail("wrong_block_hash", dict(f0, blockHash="0x" + "11" * 32), expect=("failed", "block-mismatch"))
    fail("wrong_timestamp", dict(f0, timestamp=f0["timestamp"] + 1), expect=("failed", "timestamp-mismatch"))
    fail("wrong_txfrom", dict(f0, txFrom=ADDR["A"]), expect=("failed", "txfrom-mismatch"))
    fail("wrong_name", dict(f0, name="17851.31.tape"), expect=("failed", "name-mismatch"))
    one = {k: v for k, v in rd0.items()}
    one["receipt"] = {k: v for k, v in list(rd0["receipt"].items())[:1]}
    fail("one_node_only", rd=one, expect=("failed", "too-few-nodes"))
    dis = copy.deepcopy(rd0)
    k1 = list(dis["receipt"])[1]
    dis["receipt"][k1]["logs"] = dis["receipt"][k1]["logs"][:-1]
    fail("nodes_disagree", rd=dis, expect=("failed", "nodes-disagree"))
    nocirc = dict(rd0, circuitInfo={k: v for k, v in list(rd0["circuitInfo"].items())[:1]})
    fail("circuit_missing", rd=nocirc, expect=("failed", "circuit-missing"))
    nc = dict(rd0, isCPU={k: False for k in rd0["isCPU"]})
    fail("not_registered", rd=nc, expect=("failed", "not-a-processor"))
    unf = dict(rd0, finalityBlock={k: f0["block"] - 1 for k in rd0["finalityBlock"]}, stateBlock=f0["block"])
    fail("unfinalized", rd=unf, expect=("unfinalized", None))
    fail("wrong_finality_tag", rd=dict(rd0, finalityTag="latest"), expect=("failed", "wrong-finality-tag"))
    fail("chain_not_in_tap10", dict(f0, chainId=1), expect=("failed", "unsupported-chain"))
    fail("state_read_before_mint", rd=dict(rd0, stateBlock=f0["block"] - 1), expect=("failed", "bad-state-block"))
    bad = dict(f0)
    bad["designer"] = ADDR["A"]
    fail("unknown_member", bad, expect=("failed", "bad-fact"))
    # Normalisation (TAP-10 §5.2): fields that §3.2 does not use, and the case of hex strings,
    # do not make nodes disagree.
    nrm = copy.deepcopy(rd0)
    k1 = list(nrm["receipt"])[1]
    nrm["receipt"][k1]["gasUsed"] = "0x1"
    nrm["receipt"][k1]["blockHash"] = nrm["receipt"][k1]["blockHash"].upper().replace("0X", "0x")
    res = c.verify_publication(f0, nrm)
    assert res["status"] == "verified", res
    out["normalised"] = [{"name": "unused_field_and_hex_case", "fact": f0, "readsFrom": circ["label"],
                          "readsOverride": {"receipt": nrm["receipt"]}, "expect": res}]
    return out


def sec_earliest(cr: dict, pub: dict, occ: dict) -> list:
    """Earliest-occurrence statements over the recorded facts. Every case lists the facts the
    tool knows (`known`: fact, verified, design, processor number or null), so it can be
    re-judged without other data. toBlock is the block of the occurrence scan."""
    facts = {x["label"]: x for x in pub["facts"]}
    scan_block = occ["block"]

    def kn(label, num=True):
        x = facts[label]
        return {"fact": x["fact"], "verified": x["expect"]["status"] == "verified", "design": x["design"],
                "processorNumber": x["reads"]["processorNumber"] if num else None}

    def stmt(fact, procs, kind="structural", h=XOR_STRUCT, to=scan_block, extra_scope=()):
        return {"tapEarliest": 1, "key": {"kind": kind, "hash": h}, "occurrence": fact,
                "scope": [{"chainId": 56, "processors": procs, "toBlock": to}] + list(extra_scope),
                "indexer": "scan_occurrences.py (test vectors)", "asOf": "2026-10-19T11:03:12Z"}

    out = []

    def add(name, s, occ_label, known, expect_status, occ_ok=True, occ_num=True, synthetic=False, note=None):
        o = facts[occ_label]
        num = o["reads"]["processorNumber"] if occ_num else None
        others = [(k["fact"], k["verified"], k["design"], k["processorNumber"]) for k in known]
        j = c.judge_earliest(s, occ_ok, o["design"], others, num)
        assert j["status"] == expect_status, (name, j)
        exp = {"status": j["status"]}
        if "error" in j:
            exp["error"] = j["error"]
        if "by" in j:
            exp["by"] = j["by"].get("name")
        for k in ("tiedWith", "incomparable", "scopeUnknown"):
            if k in j:
                exp[k] = [t.get("name") for t in j[k]]
        x = {"name": name, "statement": s, "occurrenceVerified": occ_ok, "occurrenceDesign": o["design"],
             "occurrenceProcessorNumber": num, "known": known, "expect": exp, "display": c.render_earliest(s, j)}
        if synthetic:
            x["synthetic"] = True
        if note:
            x["note"] = note
        out.append(x)

    labels = ["17851.30", "3.635", "906.30", "1045.30"]

    def known(*exclude):
        return [kn(l) for l in labels if l not in exclude]

    f17851, f3, f906, f1045 = (facts[l]["fact"] for l in labels)
    # The tool knows the four recorded occurrences. scan_occurrences.py read every circuit of
    # processors 30 and 635 at scan_block; #906 is the lowest id with this netlist hash in 30.
    add("17851_scope_30_635_refuted", stmt(f17851, [30, 635]), "17851.30", known("17851.30"), "refuted")
    add("17851_outside_own_scope_invalid", stmt(f17851, [635]), "17851.30", known("17851.30"), "invalid")
    add("3_635_scope_635_superseded", stmt(f3, [635]), "3.635", known("3.635"), "superseded")
    add("3_635_scope_30_635_refuted", stmt(f3, [30, 635]), "3.635", known("3.635"), "refuted")
    add("906_scope_30_635_standing", stmt(f906, [30, 635]), "906.30", known("906.30"), "standing")
    add("906_netlist_key_scope_30_635_standing", stmt(f906, [30, 635], "netlist", XOR_NETLIST), "906.30", known("906.30"), "standing")
    add("1045_structural_refuted", stmt(f1045, [30]), "1045.30", known("1045.30"), "refuted")
    add("1045_netlist_key_invalid", stmt(f1045, [30], "netlist", XOR_NETLIST), "1045.30", known("1045.30"), "invalid")
    add("wrong_key_invalid", stmt(f906, [30, 635], h=XOR5_STRUCT), "906.30", known("906.30"), "invalid")
    add("unverified_occurrence_invalid", stmt(f906, [30, 635]), "906.30", known("906.30"), "invalid", occ_ok=False)
    add("toBlock_before_occurrence_invalid", stmt(f17851, [30, 635], to=f17851["block"] - 1), "17851.30", known("17851.30"), "invalid")
    add("processor_number_unknown_list_scope_invalid", stmt(f906, [30, 635]), "906.30", known("906.30"), "invalid", occ_num=False,
        note="The tool does not know the occurrence's processor number, and the scope lists processors.")
    add("processor_number_unknown_all_scope_standing", stmt(f906, "all"), "906.30", known("906.30"), "standing", occ_num=False)
    add("earlier_fact_processor_unknown_superseded", stmt(f3, [30, 635]), "3.635",
        [kn("17851.30"), kn("906.30", num=False), kn("1045.30")], "superseded",
        note="906.30 precedes the occurrence but its processor number is unknown to the tool: counted as outside the scope.")
    # Synthetic cross-chain cases on X Layer (196), with the same timestamp as 906.30.
    def xl(block, li, cid):
        return dict(f906, chainId=196, processor="0x" + "c3" * 20, circuitId=str(cid), name=f"{cid}.2.999.tape",
                    block=block, logIndex=li, blockHash="0x" + f"{block:064x}", txHash="0x" + f"{cid:064x}")
    d906 = facts["906.30"]["design"]
    t9, t10 = xl(9, 0, 2), xl(10, 0, 1)
    s = stmt(f906, [30, 635], extra_scope=[{"chainId": 196, "processors": "all", "toBlock": 80000000}])
    add("cross_chain_tie_standing_synthetic", s, "906.30",
        known("906.30") + [{"fact": t10, "verified": True, "design": d906, "processorNumber": 999},
                           {"fact": t9, "verified": True, "design": d906, "processorNumber": 999}], "standing", synthetic=True,
        note="Two X Layer facts share 906.30's timestamp; 2.2.999.tape (block 9) precedes 1.2.999.tape (block 10) on its chain, so only 2.2.999.tape is in the standing set.")
    nots = {k: v for k, v in xl(11, 0, 3).items() if k != "timestamp"}
    add("cross_chain_incomparable_synthetic", s, "906.30",
        known("906.30") + [{"fact": nots, "verified": True, "design": d906, "processorNumber": 999}], "standing", synthetic=True,
        note="A fact on another chain without a known header timestamp cannot be ordered and is reported as incomparable.")
    return out


def sec_anchors() -> list:
    """Logs of the informative CreditPosted(address,bytes32,bytes32,bytes) event (§5.2)."""
    m = credit("C", n="anchor")
    e = env("Credit", m, "C")
    raw = json.dumps(e, separators=(",", ":"), ensure_ascii=False).encode()
    d = dig("Credit", m)
    sk = c.subject_key("Credit", m)
    log = {"address": "0x" + "cd" * 20, "topics": [c.CREDIT_POSTED_TOPIC, "0x" + "00" * 12 + ADDR["E"][2:], d, sk],
           "data": "(ABI-encoded statement bytes)", "blockNumber": 128500000, "timestamp": 1792500000}
    bad = dict(log, topics=[c.CREDIT_POSTED_TOPIC, log["topics"][1], "0x" + "99" * 32, sk])
    other = dict(log, topics=["0x" + "ab" * 32] + log["topics"][1:])
    old_event = dict(log, topics=log["topics"][:3])
    wrong_key = dict(log, topics=log["topics"][:3] + ["0x" + "42" * 32])
    return [
        {"name": "anchor", "log": log, "statementUtf8": raw.decode(), "expect": c.check_anchor(log, raw)},
        {"name": "digest_mismatch", "log": bad, "statementUtf8": raw.decode(), "expect": c.check_anchor(bad, raw)},
        {"name": "not_credit_posted", "log": other, "statementUtf8": raw.decode(), "expect": c.check_anchor(other, raw)},
        {"name": "three_topics", "log": old_event, "statementUtf8": raw.decode(), "expect": c.check_anchor(old_event, raw)},
        {"name": "subject_key_not_checked", "log": wrong_key, "statementUtf8": raw.decode(),
         "expect": c.check_anchor(wrong_key, raw), "note": "subjectKey is a discovery hint only"},
        {"name": "garbage_statement", "log": log, "statementUtf8": "{\"hello\":1}",
         "expect": c.check_anchor(log, b"{\"hello\":1}")},
    ]


def sec_display() -> dict:
    """§6.4 / §6.5 with synthetic data. Publications: 42.7.tape on BSC first taped out by test
    key C; two X Layer circuits first taped out by contract accounts K1 and K2. The design of
    all three circuits is the XOR of the worked example."""
    design = {"netlistHash": XOR_NETLIST, "structuralHash": XOR_STRUCT}
    k1, k2 = "0x" + "d1" * 20, "0x" + "d2" * 20

    def pubfact(chain, proc, cid, name, publisher, block):
        return {"chainId": chain, "processor": proc, "circuitId": cid, "name": name, "publisher": publisher,
                "block": block, "blockHash": "0x" + f"{block:064x}", "txHash": "0x" + f"{block + 1:064x}",
                "logIndex": 3, "timestamp": 1792000000}
    pubs = [{"fact": pubfact(56, "0x" + "5e" * 20, "42", "42.7.tape", ADDR["C"], 128000000), "design": design},
            {"fact": pubfact(196, "0x" + "6e" * 20, "5", "5.2.77.tape", k1, 73000000), "design": design},
            {"fact": pubfact(196, "0x" + "6e" * 20, "6", "6.2.77.tape", k2, 73000001), "design": design}]
    stm = [
        env("Credit", credit("A", display="Ada (test)", n="d"), "A"),            # 0 anchored
        env("Credit", credit("B", display="Satoshi", n="d"), "B"),               # 1 unanchored, famous name
        env("Credit", credit("C", n="d"), "C"),                                  # 2 first publisher of 42.7.tape (EOA)
        env("Credit", credit("D", role="reviewer", n="d"), "D"),                 # 3
        env("Credit", credit("E", role="co-designer", n="d"), "E"),              # 4
        env("Credit", credit("A", display="older claim", n="d0", issued=1700000000), "A"),  # 5 revoked below
        contract_env(credit("B", signer=k1, chain=196, n="k1")),                 # 6 K1: accepted at its publication block
        contract_env(credit("B", signer=k2, chain=196, n="k2")),                 # 7 K2: rejected at its publication block
        contract_env(credit("D", signer=CONTAINER_A, chain=196, n="ct"), "D"),   # 8 a TapeOut container
    ]
    stm.append(env("Revocation", revocation("A", a1and_digest(stm[5])), "A"))
    vb = 73600000
    calls = [call_rec(k1, a1and_digest(stm[6]), vb, True), call_rec(k1, a1and_digest(stm[6]), 73000000, True),
             call_rec(k2, a1and_digest(stm[7]), vb, True), call_rec(k2, a1and_digest(stm[7]), 73000001, False),
             call_rec(CONTAINER_A, a1and_digest(stm[8]), vb, True)]
    containers = {"196:" + CONTAINER_A: "1.2.282.tape"}
    reader = c.recorded_erc1271(calls, {"196": vb})
    results = [c.verify_statement(e, reader, c.recorded_containers(containers)) for e in stm]
    entries = c.apply_revocations(results, stm)
    active = [x for x in entries if x["type"] == "Credit" and x["state"] == "active"]
    anchors = {a1and_digest(stm[0]): 1792100000}
    order = c.credit_order(active, pubs, anchors, reader)
    names = {a1and_digest(e): e["message"]["displayName"] for e in stm if e["type"] == "Credit"}
    groups = {}
    for o in order:
        groups.setdefault(o["role"], {"anchored": [], "unanchored": [], "container": []})[o["group"]].append(o["digest"])
    return {"synthetic": True, "publications": pubs, "statements": stm, "anchors": anchors,
            "recorded": calls, "verificationBlocks": {"196": vb}, "containers": containers,
            "expect": {"states": [x["state"] for x in entries],
                       "unanchoredOrderUnspecified": True,
                       "groups": groups,
                       "order": [{"digest": o["digest"], "signer": o["signer"], "role": o["role"], "group": o["group"],
                                  "badge": o["badge"], "label": o["label"]} for o in order],
                       "roleCounts": {r: sum(1 for o in order if o["role"] == r) for r in c.ROLES},
                       "lines": [c.render_publication(p["fact"], "verified") for p in pubs]
                                + [c.render_credit(o, names[o["digest"]]) for o in order]}}


def sec_bundle(pub: dict, earliest: list) -> dict:
    facts = [x["fact"] for x in pub["facts"]]
    st = [env("Credit", credit("A", subject={"netlistHash": XOR_NETLIST, "structuralHash": XOR_STRUCT},
                                display="Ada (test)", n="bundle"), "A"),
          env("Lineage", lineage("B", "derivedFrom", XOR5_STRUCT, XOR_STRUCT, "test lineage", n="bundle"), "B")]
    ear = [x["statement"] for x in earliest if x["name"] == "906_scope_30_635_standing"]
    return {"note": "tapCredits: tap.credits member (tapCreditBundle optional) for a TAP-721 token whose netlist is the XOR of 17851.30.tape; statements use test keys. publications lists the four recorded occurrences (one of them, 1045.30, has the same structural hash only). standalone: the same bundle as a standalone file, which must carry tapCreditBundle = 1 (§5.1); standaloneInvalid: standalone files a tool must reject.",
            "tapCredits": {"v": 1, "publications": facts, "earliest": ear, "statements": st},
            "standalone": {"tapCreditBundle": 1, "v": 1, "publications": facts, "earliest": ear, "statements": st},
            "standaloneInvalid": [
                {"name": "missing_marker", "error": "bad-bundle",
                 "bundle": {"v": 1, "publications": facts, "earliest": ear, "statements": st}},
                {"name": "marker_true", "error": "bad-bundle",
                 "bundle": {"tapCreditBundle": True, "v": 1, "statements": st}},
                {"name": "marker_string", "error": "bad-bundle",
                 "bundle": {"tapCreditBundle": "1", "v": 1, "statements": st}},
                {"name": "marker_2", "error": "bad-bundle",
                 "bundle": {"tapCreditBundle": 2, "v": 1, "statements": st}}]}


def build() -> dict:
    cr = load_reads()
    with open(os.path.join(HERE, "occurrences.json")) as f:
        occ = json.load(f)
    pub = sec_publication(cr)
    earliest = sec_earliest(cr, pub, occ)
    return {
        "format": "tap-design-credits-vectors/1",
        "generator": "make_vectors.py",
        "warning": "All private keys in this file are TEST-ONLY and public. Never use them for anything else.",
        "eip712": sec_eip712(),
        "keys": sec_keys(),
        "note": {"bytesUtf8": NOTE.decode(), "sha256": NOTE_HASH},
        "unicode": {"version": c.UNICODE_VERSION,
                    "sources": ["https://www.unicode.org/Public/15.1.0/ucd/DerivedCoreProperties.txt",
                                "https://www.unicode.org/Public/15.1.0/ucd/PropList.txt"],
                    "control": [[f"{a:04X}", f"{b:04X}"] for a, b in c.CONTROL_RANGES],
                    "defaultIgnorable": [[f"{a:04X}", f"{b:04X}"] for a, b in c.DEFAULT_IGNORABLE_RANGES],
                    "bidiControl": [[f"{a:04X}", f"{b:04X}"] for a, b in c.BIDI_CONTROL_RANGES]},
        "valid": valid_cases(),
        "invalid": invalid_cases(),
        "erc1271": sec_erc1271(),
        "revocations": sec_revocations(),
        "publication": pub,
        "occurrenceScan": {k: occ[k] for k in occ if k != "nodes"},
        "earliest": earliest,
        "anchors": sec_anchors(),
        "display": sec_display(),
        "bundle": sec_bundle(pub, earliest),
    }


def main() -> None:
    data = (json.dumps(build(), indent=1, ensure_ascii=False) + "\n").encode()
    path = os.path.join(HERE, "vectors.json")
    if "--check" in sys.argv:
        with open(path, "rb") as f:
            if f.read() != data:
                sys.exit("vectors.json differs from the generator output")
        print("vectors.json up to date")
    else:
        with open(path, "wb") as f:
            f.write(data)
    print("sha256", hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
