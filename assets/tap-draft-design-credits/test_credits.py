#!/usr/bin/env python3
"""Tests for the draft "Design Credits and Lineage for TapeOut Netlists".

MIT licence. Runs with the standard library; optional cross-checks run when
pycryptodome, eth_keys, eth_account or Foundry `cast` are installed, and are reported
as skipped otherwise.

    python3 make_vectors.py && python3 test_credits.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

import credits as c
import make_vectors as mv

HERE = os.path.dirname(os.path.abspath(__file__))
PASSED, SKIPPED = [], []


def check(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"{name}: {detail}")
    PASSED.append(name)


def skip(name, why):
    SKIPPED.append(f"{name} ({why})")


def load():
    with open(os.path.join(HERE, "vectors.json"), "rb") as f:
        raw = f.read()
    return raw, json.loads(raw)


# The English text is required; the translation is checked when it is present (it is added as TAP-<nn>.zh.md
# after a number is assigned).
_TAPS = os.path.join(HERE, "..", "..", "TAPs")
DRAFTS = [os.path.join(_TAPS, "TAP-draft-design-credits.md")] + [
    p for p in [os.path.join(_TAPS, "TAP-draft-design-credits.zh.md")] if os.path.exists(p)]


def appendix_json(path):
    """The fenced JSON block of Appendix A of a draft file."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head = text.index("## Appendix A") if "## Appendix A" in text else text.index("## 附录 A")
    start = text.index("```json\n", head) + len("```json\n")
    end = text.index("\n```", start)
    return text[start:end]


def test_reproducible(raw):
    data = (json.dumps(mv.build(), indent=1, ensure_ascii=False) + "\n").encode()
    check("vectors reproducible", data == raw)


def test_keccak():
    check("keccak empty", c.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
    check("keccak abc", c.keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")
    check("selector postCredit", c.keccak256(b"postCredit(bytes32,bytes32,bytes)")[:4].hex() == "b03622c3")
    check("topic CreditPosted", "0x" + c.keccak256(b"CreditPosted(address,bytes32,bytes32,bytes)").hex() == c.CREDIT_POSTED_TOPIC)
    check("topic TapedOut", "0x" + c.keccak256(b"TapedOut(uint256,address,uint32,uint32)").hex() == c.TAPED_OUT_TOPIC)
    check("selector isValidSignature", c.keccak256(b"isValidSignature(bytes32,bytes)")[:4].hex() == "1626ba7e")
    try:
        from Crypto.Hash import keccak
    except ImportError:
        return skip("keccak vs pycryptodome", "not installed")
    for n in (0, 1, 135, 136, 137, 271, 272, 1000):
        data = hashlib.sha256(str(n).encode()).digest() * (n // 32 + 1)
        data = data[:n]
        k = keccak.new(digest_bits=256)
        k.update(data)
        check(f"keccak vs pycryptodome len {n}", k.digest() == c.keccak256(data))


def test_secp256k1(v):
    for k in v["keys"]:
        check(f"key {k['label']} test-only", k["testOnly"] is True)
        check(f"key {k['label']} address", c.address_of_key(int(k["privateKey"], 16)) == k["address"])
    try:
        from eth_keys import keys
    except ImportError:
        return skip("signatures vs eth_keys", "not installed")
    for k in v["keys"]:
        pk = keys.PrivateKey(bytes.fromhex(k["privateKey"][2:]))
        check(f"eth_keys address {k['label']}", pk.public_key.to_checksum_address().lower() == k["address"])
        for i in range(3):
            h = c.keccak256(f"{k['label']}{i}".encode())
            ours = c.sign(int(k["privateKey"], 16), h)
            theirs = pk.sign_msg_hash(h)
            check(f"eth_keys signature {k['label']}/{i}", ours[:64] == theirs.to_bytes()[:64] and ours[64] - 27 == theirs.v)


def test_eip712(v):
    e = v["eip712"]
    check("domain separator", e["domainSeparator"] == "0x" + c.domain_separator().hex())
    check("domain separator value", e["domainSeparator"] == "0x609a43feee15b09b02f48f2488d2a7657b828fb16b36dee7b3526a2ff4029450")
    for t, x in e["types"].items():
        check(f"encodeType {t}", x["encodeType"] == c.encode_type(t))
        check(f"typeHash {t}", x["typeHash"] == "0x" + c.keccak256(x["encodeType"].encode()).hex())
    check("Credit encodeType order", e["types"]["Credit"]["encodeType"].endswith(
        "Circuit(uint256 chainId,address processor,uint256 circuitId)DesignRef(bytes32 netlistHash,bytes32 structuralHash)"))
    ex = e["typedDataExample"]
    check("typed data example is credit_full", ex["typedData"]["message"] == v["valid"][1]["envelope"]["message"]
          and ex["signature"] == v["valid"][1]["envelope"]["signature"] and ex["digest"] == v["valid"][1]["digest"])
    check("typed data JSON text", json.loads(ex["typedDataJson"]) == ex["typedData"])
    for path in DRAFTS:
        check(f"appendix A of {os.path.basename(path)} equals the vector", appendix_json(path) == ex["typedDataJson"])
    td = ex["typedData"]
    check("typed data primaryType", td["primaryType"] == "Credit" and list(td["types"]) == ["EIP712Domain", "Credit", "Circuit", "DesignRef"])
    try:
        from eth_account.messages import encode_typed_data
        from eth_utils import keccak
    except ImportError:
        return skip("EIP-712 vs eth_account", "not installed")
    for case in v["valid"]:
        env = case["envelope"]
        t = env["type"]
        used = {t} | c._deps(t, set())
        full = {"types": {n: [{"name": a, "type": b} for a, b in c.TYPES[n]] for n in used | {"EIP712Domain"}},
                "primaryType": t, "domain": e["domain"], "message": _for_eth_account(t, env["message"])}
        sm = encode_typed_data(full_message=full)
        d = keccak(b"\x19" + sm.version + sm.header + sm.body)
        check(f"eth_account digest {case['name']}", "0x" + d.hex() == case["digest"])
    # the appendix JSON as a wallet receives it (hex strings, decimal string circuitId)
    from eth_account import Account
    td = json.loads(appendix_json(DRAFTS[0]))
    sm = encode_typed_data(full_message=td)
    check("eth_account digest of appendix A", "0x" + keccak(b"\x19" + sm.version + sm.header + sm.body).hex() == ex["digest"])
    key = next(k for k in v["keys"] if k["address"] == ex["signer"])
    signed = Account.sign_message(sm, key["privateKey"])
    check("eth_account signature of appendix A", "0x" + bytes(signed.signature).hex() == ex["signature"])


def _for_eth_account(t, m):
    out = {}
    for fn, ft in c.TYPES[t]:
        x = m[fn]
        if ft in c.TYPES:
            out[fn] = _for_eth_account(ft, x)
        elif ft == "bytes32":
            out[fn] = bytes.fromhex(x[2:])
        elif ft.startswith("uint"):
            out[fn] = int(x)
        else:
            out[fn] = x
    return out


def test_cast(v):
    cast = shutil.which("cast")
    if not cast:
        return skip("cast wallet sign --data", "cast not installed")
    ex = v["eip712"]["typedDataExample"]
    key = next(k for k in v["keys"] if k["address"] == ex["signer"])
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(appendix_json(DRAFTS[0]))
        path = f.name
    try:
        out = subprocess.run([cast, "wallet", "sign", "--data", "--from-file", path, "--private-key", key["privateKey"]],
                             capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(path)
    if out.returncode != 0:
        return skip("cast wallet sign --data", out.stderr.strip()[:120])
    check("cast signature of appendix A equals reference signature", out.stdout.strip() == ex["signature"], out.stdout)


def test_valid(v):
    for case in v["valid"]:
        r = c.verify_statement(case["envelope"])
        check(f"valid {case['name']}", r["status"] == "valid" and r["signer"] == case["expect"]["signer"]
              and r["digest"] == case["digest"], r)
        # the envelope survives a JSON round trip and the size limit
        raw = json.dumps(case["envelope"], ensure_ascii=False).encode()
        check(f"valid {case['name']} size", len(raw) <= c.MAX_ENVELOPE)
        check(f"valid {case['name']} from bytes", c.verify_statement(raw)["status"] == "valid")


def test_invalid(v):
    seen = set()
    for case in v["invalid"]:
        r = c.verify_statement(case["envelope"])
        check(f"invalid {case['name']}", r["status"] == "invalid" and r["error"] == case["expect"]["error"], r)
        seen.add(case["expect"]["error"])
    for code in ("signer-mismatch", "high-s", "bad-v", "bad-r-s", "bad-signature-length", "empty-subject", "bad-role",
                 "bad-source", "note-mismatch", "bad-text", "bad-field", "self-edge", "bad-relation", "bad-envelope",
                 "unknown-type"):
        check(f"invalid covers {code}", code in seen)


def test_erc1271(v):
    for case in v["erc1271"]:
        reader = c.recorded_erc1271(case["recorded"], case["verificationBlocks"])
        r = c.verify_statement(case["envelope"], reader, c.recorded_containers(case["containers"]))
        exp = case["expect"]
        check(f"erc1271 {case['name']}", r["status"] == exp["status"] and r.get("error") == exp.get("error")
              and r.get("validAt") == exp.get("validAt") and r.get("label") == exp.get("label"), r)
    by = {x["name"]: x for x in v["erc1271"]}
    check("erc1271 replay digests differ", by["contract_valid"]["digest"] != by["replay_to_other_account"]["digest"])
    check("erc1271 container label", by["container_labelled"]["expect"]["label"] == "container of 1.2.282.tape; validity follows its holder")


def test_revocations(v):
    for case in v["revocations"]:
        if "verificationBlocks" in case:
            res = [c.verify_statement(e, c.recorded_erc1271(case["recorded"], vb))
                   for e, vb in zip(case["envelopes"], case["verificationBlocks"])]
        else:
            res = [c.verify_statement(e) for e in case["envelopes"]]
        states = [x["state"] for x in c.apply_revocations(res, case["envelopes"])]
        check(f"revocation {case['name']}", states == case["expect"], states)


def test_publication(v):
    for x in v["publication"]["facts"]:
        r = c.verify_publication(x["fact"], x["reads"])
        check(f"publication {x['label']} verified", r["status"] == "verified", r)
        check(f"publication {x['label']} expect", r == x["expect"])
        check(f"publication {x['label']} TapedOut corroborates", "tapedOutLog" in r["checks"])
        check(f"publication {x['label']} structural design", x["design"]["structuralHash"] == mv.XOR_STRUCT)
        check(f"publication {x['label']} exact design", (x["design"]["netlistHash"] == mv.XOR_NETLIST) == (x["label"] != "1045.30"))
    base = {x["label"]: x["reads"] for x in v["publication"]["facts"]}
    for x in v["publication"]["failures"]:
        rd = dict(base[x["readsFrom"]])
        rd.update(x["readsOverride"])
        r = c.verify_publication(x["fact"], rd)
        check(f"publication failure {x['name']}", r["status"] == x["expect"]["status"]
              and r.get("error") == x["expect"]["error"], r)
    for x in v["publication"]["normalised"]:
        rd = dict(base[x["readsFrom"]])
        rd.update(x["readsOverride"])
        check(f"publication normalised {x['name']}", c.verify_publication(x["fact"], rd) == x["expect"])
    for x in v["publication"]["facts"]:
        check(f"publication {x['label']} finality tag", x["reads"]["finalityTag"] == c.FINALITY_TAG[x["fact"]["chainId"]])


def test_chain_reads():
    with open(os.path.join(HERE, "chain-reads.json")) as f:
        cr = json.load(f)
    check("chain reads sent no transaction", cr["transactionsSent"] == 0)
    pb = cr["pinnedBlock"]
    check("pinned at the BSC finality tag", pb["tag"] == "finalized" and pb["number"] == min(pb["reportedBy"].values()))
    for circ in cr["circuits"]:
        hashes = {r["blockHash"] for r in circ["receipt"].values()}
        check(f"{circ['label']} receipts agree on 3 nodes", len(circ["receipt"]) >= 3 and len(hashes) == 1
              and len({c.normalize_receipt(r) for r in circ["receipt"].values()}) == 1)
        for k in ("netlist", "circuitInfo", "isCPU", "cpuAt", "publisherCodeAtPinnedBlock"):
            check(f"{circ['label']} {k} agrees on 3 operators", len(circ[k]) == 3 and len({json.dumps(x) for x in circ[k].values()}) == 1)
        rec = next(iter(circ["receipt"].values()))
        logs = {json.dumps(l, sort_keys=True) for l in circ["archiveLogs"] if l["transactionHash"] == rec["transactionHash"]}
        proc_logs = {json.dumps({**l, "transactionHash": rec["transactionHash"]}, sort_keys=True)
                     for l in rec["logs"] if l["address"] == circ["processor"]}
        check(f"{circ['label']} archive logs match receipt", logs == proc_logs)
        check(f"{circ['label']} publisher has no code at the pinned block", all(v == "0x" for v in circ["publisherCodeAtPinnedBlock"].values()))
    for num, sp in cr["scannedProcessors"].items():
        check(f"processor {num} nextId is the latest id", len(set(sp["nextIdAtPinnedBlock"].values())) == 1
              and all(sp["circuitInfo(nextId)Exists"].values()) and all(sp["circuitInfo(nextId+1)Reverted"].values()))
    reg = cr["podMiner17851"]["registrant"]
    pub = mv.fact_for(cr["circuits"][0])["publisher"]
    check("17851 registrant equals publisher (but is not a designer)", reg == pub)
    # selector enumeration of the circuit implementations
    impls = [cr["circuitBeacon"]["implementationCode"], cr["xlayerContainer"]["circuitImplementation"]]
    check("BSC circuit implementation is the TAP-10 one", impls[0]["address"] == "0x8e1d125def6d3826c278299273a0760d47626068")
    check("X Layer circuit implementation is the TAP-10 one", impls[1]["implementation"] == "0x977f217887e085d298cb3819cdad5a0ee35f29b2")
    for im in impls:
        check("all dispatcher selectors named", im["unnamed"] == [] and len(im["selectors"]) == len(im["named"]))
        for sel, sig in im["named"].items():
            check(f"selector {sig}", "0x" + c.keccak256(sig.encode())[:4].hex() == sel)
        check("tapeout among selectors", im["named"].get("0x7bd3ac1d") == "tapeout(bytes,uint32,uint32)")
    # X Layer container delegation (M5)
    x = cr["xlayerContainer"]
    check("X Layer pinned at safe", x["pinnedBlock"]["tag"] == "safe" and len(x["nodes"]) == 2)
    check("container is an EIP-1167 clone of the TAP-10 implementation",
          x["containerDelegatesTo"] == "0xac4f791353ee9f06e2c50ae4c34680d28ea52a57" and x["containerDelegatesToEqualsTap10Implementation"])
    check("container implementation is a beacon proxy", x["implementationIsBeaconProxy"]["beacon"] == "0x9b135f586f7850a3fa92210c298f732b20bc8f44")
    check("beacon implementation", x["beacon.implementation()"] == "0x6b6fda1483367e939314070a4f233c1dfd35996b")
    check("container owner follows holder", x["owner()"] == x["ownerOf(1)"])
    ans = x["isValidSignature"]["answer"]
    check("isValidSignature rejects a non-holder signature", ans["reverted"] or ans["result"][:10] != "0x1626ba7e")


def test_earliest(v):
    for x in v["earliest"]:
        others = [(k["fact"], k["verified"], k["design"], k["processorNumber"]) for k in x["known"]]
        j = c.judge_earliest(x["statement"], x["occurrenceVerified"], x["occurrenceDesign"], others,
                             x["occurrenceProcessorNumber"])
        got = {"status": j["status"]}
        if "error" in j:
            got["error"] = j["error"]
        if "by" in j:
            got["by"] = j["by"].get("name")
        for k in ("tiedWith", "incomparable", "scopeUnknown"):
            if k in j:
                got[k] = [t.get("name") for t in j[k]]
        check(f"earliest {x['name']}", got == x["expect"], got)
    by = {x["name"]: x for x in v["earliest"]}
    check("earliest 17851 refuted by 906.30", by["17851_scope_30_635_refuted"]["expect"].get("by") == "906.30.tape")
    check("earliest reference circuit refuted by 906.30", by["3_635_scope_30_635_refuted"]["expect"].get("by") == "906.30.tape")
    check("earliest occurrence outside its own scope", by["17851_outside_own_scope_invalid"]["expect"]["status"] == "invalid")
    check("earliest superseded from outside scope", by["3_635_scope_635_superseded"]["expect"].get("by") == "906.30.tape")
    check("earliest wording", by["906_scope_30_635_standing"]["display"].startswith("[earliest known, refutable]"))
    scan = v["occurrenceScan"]
    check("earliest toBlock is the scan block", all(e["toBlock"] == scan["block"] for e in by["906_scope_30_635_standing"]["statement"]["scope"]))
    occ = scan["processors"]
    p30 = [p for p in occ if p["processorNumber"] == 30][0]
    p635 = [p for p in occ if p["processorNumber"] == 635][0]
    check("scan: 906 lowest id with the netlist hash in 30", p30["exactMatches"][0] == 906 and p635["exactMatches"] == [3])
    check("scan: 1045 structural only", 1045 in p30["structuralMatches"] and 1045 not in p30["exactMatches"])
    check("scan complete at one block", p30["unreadable"] == 0 and p635["unreadable"] == 0
          and p30["block"] == p635["block"] == scan["block"] and p30["circuitInfoAfterLastReverted"])
    check("earliest tie set excludes facts with a predecessor", by["cross_chain_tie_standing_synthetic"]["expect"].get("tiedWith") == ["2.2.999.tape"])
    a = {"chainId": 1, "block": 5, "logIndex": 2, "timestamp": 9}
    check("order same chain block", c.precedes(dict(a, block=4), a) is True)
    check("order same chain logIndex", c.precedes(dict(a, logIndex=1), a) is True)
    check("order same chain ignores timestamp", c.precedes(dict(a, block=6, timestamp=1), a) is False)
    check("order cross chain", c.precedes(dict(a, chainId=2, block=99, timestamp=8), a) is True)
    check("order cross chain tie", c.precedes(dict(a, chainId=2, timestamp=9), a) is None)
    check("order uses header timestamps", c.precedes(dict(a, chainId=2, block=7, timestamp=1), a, {(2, 7): 10}) is False)
    nots = {k: w for k, w in a.items() if k != "timestamp"}
    try:
        c.precedes(dict(nots, chainId=2), a)
        check("order cross chain without timestamp raises", False)
    except c.Incomparable:
        check("order cross chain without timestamp raises", True)
    check("order same chain without timestamp", c.precedes(dict(nots, block=4), a) is True)


def test_anchors(v):
    for x in v["anchors"]:
        r = c.check_anchor(x["log"], x["statementUtf8"].encode())
        check(f"anchor {x['name']}", r == x["expect"], r)
    check("anchor positive", v["anchors"][0]["expect"]["status"] == "anchor")


def test_display(v):
    d = v["display"]
    reader = c.recorded_erc1271(d["recorded"], d["verificationBlocks"])
    res = [c.verify_statement(e, reader, c.recorded_containers(d["containers"])) for e in d["statements"]]
    entries = c.apply_revocations(res, d["statements"])
    check("display states", [x["state"] for x in entries] == d["expect"]["states"])
    active = [x for x in entries if x["type"] == "Credit" and x["state"] == "active"]
    order = c.credit_order(active, d["publications"], d["anchors"], reader)
    check("display unanchored order unspecified", d["expect"]["unanchoredOrderUnspecified"] is True)
    groups = {}
    for o in order:
        groups.setdefault(o["role"], {"anchored": [], "unanchored": [], "container": []})[o["group"]].append(o["digest"])
    for role, g in d["expect"]["groups"].items():
        check(f"display {role} anchored order", groups[role]["anchored"] == g["anchored"])
        check(f"display {role} unanchored set", sorted(groups[role]["unanchored"]) == sorted(g["unanchored"]))
        check(f"display {role} container tail set", sorted(groups[role]["container"]) == sorted(g["container"]))
    check("display role order", [o["role"] for o in order] == sorted([o["role"] for o in order], key=c.ROLES.index))
    keys = {k["label"]: k["address"] for k in v["keys"]}
    byd = {o["digest"]: o for o in order}
    st = d["statements"]
    dg = [mv.a1and_digest(e) for e in st]
    check("display anchored first", order[0]["signer"] == keys["A"] and order[0]["group"] == "anchored")
    check("display mark does not move a claim ahead of an anchored one", byd[dg[2]]["badge"] == ["42.7.tape"]
          and byd[dg[2]]["group"] == "unanchored")
    check("display contract mark at publication block", byd[dg[6]]["badge"] == ["5.2.77.tape"])
    check("display no mark when ERC-1271 rejected at publication block", byd[dg[7]]["badge"] == [])
    check("display container in tail with label", byd[dg[8]]["group"] == "container"
          and byd[dg[8]]["label"] == "container of 1.2.282.tape; validity follows its holder")
    check("display revoked claim absent", dg[5] not in byd)
    for line in d["expect"]["lines"][3:]:
        check("display claim label", line.startswith("[claim] "))
        low = line.lower()
        check("display no authorship words", "author " not in low.replace("not proof of authorship", "")
              and "designed by" not in low and "creator" not in low)
    for line in d["expect"]["lines"][:3]:
        check("display fact label", line.startswith("[verified fact]") and "first taped out by" in line)
    pub = d["publications"][0]
    e_c = [x for x in entries if x["digest"] == dg[2]][0]
    check("mark needs the subject to apply", c.first_publisher_mark(e_c, pub["fact"], pub["design"])
          and not c.first_publisher_mark(e_c, pub["fact"], {"netlistHash": mv.XOR_NETLIST, "structuralHash": mv.XOR5_STRUCT}))
    e_k1 = [x for x in entries if x["digest"] == dg[6]][0]
    check("contract mark refused on another chain", not c.first_publisher_mark(e_k1, dict(d["publications"][1]["fact"], chainId=56),
                                                                              pub["design"], reader))


def test_bundle(v):
    b = v["bundle"]["tapCredits"]
    check("bundle v", b["v"] == 1)
    for f in b["publications"]:
        check(f"bundle fact {f['name']} well-formed", c.check_publication_fact(f) is None)
    for e in b["statements"]:
        check("bundle statement valid", c.verify_statement(e)["status"] == "valid")
    for s in b["earliest"]:
        check("bundle earliest well-formed", c.check_earliest(s) is None)
    check("bundle tap.credits form (marker optional)", c.check_bundle(b, standalone=False) is None)
    sa = v["bundle"]["standalone"]
    check("standalone bundle marker", sa["tapCreditBundle"] == 1 and c.check_bundle(sa, standalone=True) is None)
    check("standalone bundle content equals tap.credits", {k: x for k, x in sa.items() if k != "tapCreditBundle"} == b)
    for case in v["bundle"]["standaloneInvalid"]:
        try:
            c.check_bundle(case["bundle"], standalone=True)
            check(f"standalone bundle {case['name']} rejected", False)
        except c.Invalid as e:
            check(f"standalone bundle {case['name']} rejected", e.code == case["error"])


def test_rules():
    m = mv.credit("A", n="rules")
    e = c.make_envelope("Credit", m, mv.KEYS["A"])
    big = dict(e)
    big["signature"] = "0x" + "00" * (c.MAX_SIGNATURE + 1)
    check("oversized signature rejected", c.verify_statement(big)["error"] == "bad-envelope")
    blob = json.dumps(dict(e, message=dict(m, displayName="x" * 64))).encode() + b" " * 9000
    check("oversized envelope rejected", c.verify_statement(blob)["status"] == "invalid")
    check("64-byte display name ok", c.verify_statement(c.make_envelope("Credit", dict(m, displayName="é" * 32), mv.KEYS["A"]))["status"] == "valid")
    d17851 = {"netlistHash": mv.XOR_NETLIST, "structuralHash": mv.XOR_STRUCT}
    d1045 = {"netlistHash": "0x6b90490a18ea09ab2ad0d126773444705dd23c9a9b8d619e5f7d1571b1872ab4", "structuralHash": mv.XOR_STRUCT}
    full = {"netlistHash": mv.XOR_NETLIST, "structuralHash": mv.XOR_STRUCT}
    struct_only = {"netlistHash": c.ZERO32, "structuralHash": mv.XOR_STRUCT}
    check("applies: full ref to 17851", c.applies(full, d17851))
    check("applies: full ref not to 1045", not c.applies(full, d1045))
    check("applies: structural ref to 1045", c.applies(struct_only, d1045))
    check("applies: other structure", not c.applies({"netlistHash": c.ZERO32, "structuralHash": mv.XOR5_STRUCT}, d17851))
    check("applies: no design", not c.applies(struct_only, {"netlistHash": None, "structuralHash": None}))
    wrong = {"netlistHash": mv.XOR_NETLIST, "structuralHash": mv.XOR5_STRUCT}
    check("both hashes consistent with the file", c.consistent_with_file(full, d17851) is True)
    check("both hashes inconsistent with the file", c.consistent_with_file(wrong, d17851) is False)
    check("consistency rule n/a for another file", c.consistent_with_file(full, d1045) is None)
    check("consistency rule n/a for one hash", c.consistent_with_file(struct_only, d17851) is None)
    u = load()[1]["unicode"]
    check("unicode table in vectors", u["version"] == c.UNICODE_VERSION and len(u["defaultIgnorable"]) == len(c.DEFAULT_IGNORABLE_RANGES))
    for cp in (0x00AD, 0x200B, 0x200D, 0xFE0F, 0x2066, 0xE0041, 0x0007):
        check(f"forbidden U+{cp:04X}", c.forbidden_char(cp))
    for cp in (0x0041, 0x00E9, 0x6D4B, 0x2014, 0x1F469):
        check(f"allowed U+{cp:04X}", not c.forbidden_char(cp))
    check("design of REF circuit is none", c.design_of(bytes([2]) + bytes(30), 0, 1) == {"netlistHash": None, "structuralHash": None})


def main():
    raw, v = load()
    test_reproducible(raw)
    test_keccak()
    test_secp256k1(v)
    test_eip712(v)
    test_cast(v)
    test_valid(v)
    test_invalid(v)
    test_erc1271(v)
    test_revocations(v)
    test_publication(v)
    test_chain_reads()
    test_earliest(v)
    test_anchors(v)
    test_display(v)
    test_bundle(v)
    test_rules()
    print(f"{len(PASSED)} checks passed; vectors.json sha256 {hashlib.sha256(raw).hexdigest()}")
    for s in SKIPPED:
        print("skipped:", s)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("FAIL", e)
        sys.exit(1)
