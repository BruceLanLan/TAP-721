#!/usr/bin/env python3
"""tapfam: reference implementation of the tool-side display rules of the TAP-721 family (MIT, stdlib only).

  tapfam.py token --rpc URL [--source-rpc URL]... --contract 0x… --id N [--metadata FILE|URL] [--netlist FILE]
                  [--manifest FILE|URL] [--token-set FILE] [--collection-dir DIR] [--master-seed 0x…] [--json]
  tapfam.py metadata FILE [--netlist FILE] [--manifest FILE] [--collection-dir DIR] [--json]     (offline checks only)
  tapfam.py bundle FILE [--rpc URL]... [--json]                                                    (credit bundle)
  tapfam.py credential --rpc URL --contract 0x… --id N [--metadata FILE|URL] [--artifact FILE] [--json]
  … --offline [--fixture FILE]   answers every chain read from the recorded fixture (fixtures/recorded-rpc.json)

Every line of the report is tagged with the section of the draft it implements (README). The checker reads the
chain only (eth_call, eth_getCode, eth_getLogs, receipts and headers) and never sends a transaction. Every rule
is a call into the reference modules of the family (see _paths.py); nothing is reimplemented here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _paths as P  # noqa: E402
import chain as C  # noqa: E402
from report import T721, TBR, TDC, TPOD, TSB, TSH, Report  # noqa: E402

tapnft, canon, canon2, tapnet2, credits, soulbound = P.tapnft, P.canon, P.canon2, P.tapnet2, P.credits, P.soulbound
keccak256 = P.keccak256
ZERO32, ONES32 = C.ZERO32, C.ONES32
ZERO_ADDR = "0x" + "00" * 20

# ERC-165 identifiers (TAP-721 Test Cases; soulbound §8.5; bridging vectors `interfaces`; ERC-7496 §5.1 of PoD).
IID = {
    "ERC165": "0x01ffc9a7", "ERC721": "0x80ac58cd", "ERC4906": "0x49064906",
    "ITapNetlistNFT": "0x282b67f6", "ITapCompanion": "0x12b40a6c", "ITapNetlistEval": "0xec7d7e20",
    "ITapNetlistTokenSet": "0x3f7177c7", "ITapBridgeMirror": "0xdba6a55e",
    "ITapCredential": "0x5558759c", "ITapCredentialProven": "0x07aaf2dc", "ITapCredentialAttested": "0x7587c9da",
    "ITapCredentialClaimed": "0x11e35684", "ERC5192": "0xb45a3c0e", "ERC7496": "0xaf332f3e",
}
# TAP-10 facts the checker needs (docs/FACTS.md; TAP-10 Deployments): processor factories, container openers,
# area codes. A chain that is not listed gets "not known to this tool" lines, never a guess.
FACTORY = {56: "0x68224f668083c29e9800be2a646d42d18cedf7e2"}
OPENER = {56: "0x021745de2f42a7839d96f2d3634d0294487d81f1", 196: "0x536add8f30f03b69f6fbf29d425a816a0dc50106"}
AREA_CODE = {56: None, 196: 2, 8453: 3}
MINING = "0x7e2e0dc66a3bd9103e69b766afa62d9f7b697b46"           # PoD mining contract (BNB Smart Chain)
RIG_VOUCHER = "0x9cfc959cd42b2e1d39a0d850c528210e818ae520"      # PoD §6
MAX_FETCH = 8 * 1024 * 1024
MAX_GATES = 1 << 20   # bound on records before a structural hash is computed (TAP-SH §9 item 4)
POD_TRAITS = ["snapshotBlock", "taskId", "nandBurn", "latchBurn", "area", "depth", "cost", "bstar", "status",
              "optimal", "bonus", "multiplier", "verified", "verifWeight", "unverWeight"]
MINER_TYPES = ("address,uint64,uint32,uint32,uint32,uint32,uint64,uint32,uint64,uint8,address,uint32,uint32,"
               "uint64,uint64,bool,uint64,uint64,uint64,uint128,uint128,uint256")
MINER_FIELDS = ["circuits", "circuitId", "taskId", "gateCount", "stateCount", "depth", "area", "mult", "since",
                "status", "registrant", "nandBurn", "latchBurn", "bstar", "bonus", "optimal", "commitBlock",
                "firstUnusedId", "stopBlock", "verifWeight", "unverWeight", "debt"]
# getTask returns twelve values (not a struct): the return data is the tuple body itself, without a leading offset.
TASK_TYPES = ["uint8", "uint32", "uint32", "uint32", "uint32", "bool", "bytes32", "string", "uint64", "uint256", "address", "uint64"]
CRED_TYPES = "(uint8,uint8,address,bytes32,bytes32,bytes32,uint64,uint64,uint256)"
SPEC_TYPES = "(address,uint32,uint32,bytes32,uint32,bool,bytes32,uint64,uint64,uint64,address,bytes32)"


class Stop(Exception):
    """The report cannot continue (no metadata, no contract)."""


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def hx(b: bytes) -> str:
    return "0x" + b.hex()


def short(h: str) -> str:
    return h if len(h) <= 14 else h[:10] + "…" + h[-4:]


def fetch_bytes(uri: str, offline: bool) -> bytes:
    """Read a file path, a data: URI, or an http(s) URL (online only). Other schemes are not resolved."""
    if uri.startswith("data:"):
        head, _, body = uri.partition(",")
        import base64
        return base64.b64decode(body) if ";base64" in head else urllib.request.unquote_to_bytes(body)
    if re.match(r"^https?://", uri):
        if offline:
            raise IOError(f"offline: {uri} not fetched")
        req = urllib.request.Request(uri, headers={"user-agent": "tap-family-checker"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read(MAX_FETCH + 1)
        if len(data) > MAX_FETCH:
            raise IOError("file larger than the fetch limit")
        return data
    if re.match(r"^[a-z][a-z0-9+.-]*://", uri):
        raise IOError(f"scheme of {uri} is not resolved by this tool")
    with open(uri, "rb") as f:
        return f.read()


def parse_token_id(tid: str):
    m = tapnft.TOKEN_ID.match(tid or "")
    return (int(m.group(1)), m.group(2), int(m.group(3))) if m else None


# ---------------------------------------------------------------- RPC set-up

def build_rpc(args) -> C.Rpc:
    if getattr(args, "offline", False):
        path = getattr(args, "fixture", None) or P.FIXTURE_FILE
        return C.Rpc(fixture=C.load_fixture(path))
    nodes = {}
    for url in (getattr(args, "rpc", None) or []) + (getattr(args, "source_rpc", None) or []):
        rpc = C.Rpc()
        rpc.nodes[0] = [url]
        cid = int(rpc.request(0, "eth_chainId", []), 16)
        nodes.setdefault(cid, []).append(url)
    return C.Rpc(nodes=nodes)


def chain_label(rpc: C.Rpc, chain_id: int) -> str:
    try:
        return f"chain {chain_id} at block {rpc.pinned_block(chain_id)}" + (" (recorded fixture)" if rpc.offline else "")
    except (C.RpcError, C.NotRecorded) as e:
        return f"chain {chain_id} (block unknown: {e})"


# ---------------------------------------------------------------- metadata (§7, offline)

def load_metadata(args, rpc: C.Rpc, chain_id, contract, token_id, rep: Report) -> dict:
    src = getattr(args, "metadata", None)
    if src:
        raw = fetch_bytes(src, rpc.offline)
        rep.info(f"{T721} §7.1", "metadata.source", f"{src} ({len(raw)} bytes)")
    else:
        if chain_id is None or not contract:
            raise Stop("no metadata file and no contract to read tokenURI from")
        uri = rpc.call_decode(chain_id, contract, "tokenURI(uint256)", (token_id,), "string")
        rep.info(f"{T721} §7.1", "metadata.source", f"tokenURI({token_id}) = {uri[:120]}")
        raw = fetch_bytes(uri, rpc.offline)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        rep.fail(f"{T721} §7.1", "metadata.json", f"metadata is not UTF-8 JSON: {e}")
        raise Stop("metadata unreadable")


def check_metadata_doc(doc: dict, rep: Report) -> dict | None:
    """§7.1–§7.3 rules that need no network, through tapnft.check_metadata. Returns `tap` or None."""
    try:
        tap = tapnft.check_metadata(doc)
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §7.1", "metadata", f"invalid: {e}")
        return None
    rep.ok(f"{T721} §7.1", "metadata", "the tap member follows §7.1–§7.3 (offline rules)")
    rep.info(f"{T721} §4.1", "token.id", tap["id"])
    rep.info(f"{T721} §7.2", "state.declared", f"tap.state = {tap['state']}")
    if "manifest" in tap:
        rep.info(f"{T721} §5.1", "manifest.declared", f"tap.manifest.sha256 = {tap['manifest']['sha256']} (content committed by a manifest)")
    else:
        rep.info(f"{T721} §8.1", "manifest.declared", "no tap.manifest: a collection without a manifest (content assigned at mint, §7.2; no editions, §6.4)")
        if "freeze" in tap:
            fr = tap["freeze"]
            rep.info(f"{T721} §5.1", "freeze.probe", f"tap.freeze names the probe {fr['call']} on {fr['contract']} (chain {fr['chainId']}); "
                     "it names a check, not a state (§5.1): the frozen state is read from the chain (§7.2)")
    st = tapnft.netlist_status(tap)
    if st == "none":
        rep.info(f"{T721} §7.2", "netlist.declared", "no tap.netlist (unrevealed)")
    elif st == "unverifiable":
        rep.unverifiable(f"{T721} §2.5", "netlist.declared", f"tap.netlist.format = {tap['netlist']['format']!r}: a format this tool does not support; "
                         "shown as unverifiable, not as invalid, and never as verified")
    else:
        n = tap["netlist"]
        rep.info(f"{T721} §7.1", "netlist.declared", f"tapnet/1 {n['sha256']} ({n['bytes']} bytes, nIn {n['nIn']}, nOut {n['nOut']}, nand {n['nand']}, latch {n['latch']})")
    if "edition" in tap:
        rep.info(f"{T721} §6.4", "edition.declared", f"edition {tap['edition']['index']}/{tap['edition']['of']} (declared)")
    if "source" in tap:
        s = tap["source"]
        rep.info(f"{T721} §3.1", "source.declared", f"{s.get('name') or s['processor'] + '#' + s['circuitId']} on chain {s['chainId']} at block {s['block']} "
                 "(provenance only: no right over the source circuit, §3.2)")
    if "companion" in tap:
        rep.info(f"{T721} §8.3", "companion.declared", f"tap.companion = {tap['companion']['address']} on chain {tap['companion']['chainId']}")
    if "content" in tap:
        c = tap["content"]
        rep.info(f"{T721} §7.5", "content.declared", f"files in container {c['container']} ({c['name']}) on chain {c['chainId']}; "
                 "the hashes of §7.1 stay authoritative; a lock is not shown as locked on the strength of `lock` alone (§7.5 item 3)")
    if "bridge" in tap:
        b = tap["bridge"]
        rep.info(f"{TBR} §5.2", "bridge.declared", f"gateway {b.get('gateway')} on home chain {b.get('chainId')} (declared; a client checks homeChainId() and collectionKey() before use)")
    if "rig" in tap:
        r = tap["rig"]
        rep.info(f"{TPOD} §6", "rig", f"related rig voucher (informative): #{r.get('id')} of {r.get('contract')} on chain {r.get('chainId')}; not verified, "
                 "implies no holding, control or benefit; not an input to rarity")
    return tap


def check_collection_dir(path: str, tap: dict, manifest_sha: str | None, rep: Report):
    """Collection-level rules over every token's metadata (§7.1 manifest consistency, §5.1 freeze probes,
    §6.4/§7.3 item 3 editions)."""
    docs = []
    for name in sorted(os.listdir(path)):
        fp = os.path.join(path, name)
        if os.path.isfile(fp) and not name.startswith("."):
            try:
                with open(fp, "rb") as f:
                    d = json.loads(f.read())
                tapnft.check_metadata(d)
                docs.append(d)
            except (ValueError, tapnft.Invalid) as e:
                rep.fail(f"{T721} §7.1", "collection.metadata", f"{name}: {e}")
                return
    rep.info(f"{T721} §7.3", "collection.size", f"{len(docs)} token metadata files from {path}")
    try:
        found = tapnft.check_manifest_consistency(docs, manifest_sha)
        rep.ok(f"{T721} §7.1", "collection.manifest", "every token carries the same tap.manifest.sha256" if found else "no token carries tap.manifest")
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §7.1", "collection.manifest", f"collection is invalid: {e}")
        return
    try:
        probe = tapnft.check_freeze_probes(docs)
        if found is None:
            rep.ok(f"{T721} §5.1", "collection.freeze", f"tap.freeze is {'the same on every token' if probe else 'absent from every token'}")
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §5.1", "collection.freeze", f"{e}; no freeze is reported for this collection")
    try:
        res = tapnft.check_editions(docs, manifest_sha)
        if found is None:
            rep.ok(f"{T721} §6.4", "edition.check", "no editions: a collection without a manifest forms none, even where tokens share a netlist hash")
        elif res == "valid":
            rep.ok(f"{T721} §6.4", "edition.check", "editions of every netlist hash are consistent across the collection (§7.3 item 3)")
        else:
            rep.unverifiable(f"{T721} §2.5", "edition.check", "edition check unverifiable: some tokens carry a netlist format this tool does not support")
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §6.4", "edition.check", f"{e}")


# ---------------------------------------------------------------- netlist file, structural hash (§2, §7.4, TAP-SH)

def check_netlist_file(tap: dict, data: bytes | None, rep: Report) -> dict:
    """§7.4 / §2.5: the fetched file against tap.netlist. Returns {"status": verified|invalid|unverifiable|none,
    "design": {netlistHash, structuralHash} or None}."""
    out = {"status": "none", "design": None, "metrics": None}
    if "netlist" not in tap:
        return out
    st = tapnft.netlist_status(tap)
    if data is None and st == "tapnet/1":
        rep.skip(f"{T721} §7.4", "netlist.file", "netlist file not available (pass --netlist or run online): the token is not shown as a checked netlist-bound NFT")
        return out
    try:
        mt = tapnft.check_netlist_against_metadata(tap, data)
    except tapnft.Unverifiable as e:
        out["status"] = "unverifiable"
        rep.unverifiable(f"{T721} §2.5", "netlist.file", f"{e}; the edition check of this token is unverifiable too")
        if data is not None:
            _structural_of_other_format(data, tap, rep)
        return out
    except tapnft.Invalid as e:
        out["status"] = "invalid"
        rep.fail(f"{T721} §7.4", "netlist.file", f"invalid: {e}")
        return out
    out["status"] = "verified"
    out["metrics"] = mt
    rep.ok(f"{T721} §7.4", "netlist.file", f"file hashes to tap.netlist.sha256, is a valid tapnet/1 file (§2.2) and its metrics match "
           f"(nIn {mt.n_in}, nOut {mt.n_out}, nand {mt.nand}, latch {mt.latch}, gates {mt.gates})")
    if (len(data) - tapnft.HEADER_LEN) // 4 > MAX_GATES:
        rep.skip(f"{TSH} §9", "structural.hash", f"structural hash not computed: more than {MAX_GATES} records (bound of this tool)")
        return out
    sh1 = hx(canon.structural_hash(data))
    sh2 = hx(canon2.structural_hash(data))
    out["design"] = {"netlistHash": tap["netlist"]["sha256"], "structuralHash": sh1}
    same = " (version 2 equals version 1 for a tapnet/1 file, §10.1)" if sh1 == sh2 else f"; version 2 {sh2}"
    rep.info(f"{TSH} §7", "structural.hash", f"structural hash {sh1}{same}; identifies structure only: it says nothing about function or metrics (§9 item 3)")
    decl = tap["netlist"].get("structuralHash")
    if decl is not None:
        if decl == sh1:
            rep.ok(f"{TSH} §9", "structural.declared", "tap.netlist.structuralHash equals the recomputed structural hash")
        else:
            rep.fail(f"{TSH} §9", "structural.declared", f"tap.netlist.structuralHash {decl} differs from the recomputed {sh1}")
    return out


def _structural_of_other_format(data: bytes, tap: dict, rep: Report) -> None:
    """A tapnet/2 file: version 2 of the structural hash is defined for it (TAP-SH §10); the binding of the
    file to tap.netlist stays unverifiable here (§2.5), so the hash is shown for the fetched bytes only."""
    if len(data) < 7 or data[6] != 2:
        return
    try:
        tapnet2.check_file(data)
        sh2 = hx(canon2.structural_hash(data))
    except Exception as e:  # tapnet2.Invalid, canon2.TooLarge, ValueError
        rep.skip(f"{TSH} §10", "structural.hash", f"version 2 structural hash not computed for the fetched tapnet/2 file: {e}")
        return
    rep.info(f"{TSH} §10", "structural.hash", f"version 2 structural hash of the fetched tapnet/2 file: {sh2} (the file's binding to tap.netlist is unverifiable by this tool)")
    decl = tap["netlist"].get("structuralHash")
    if decl is not None:
        (rep.ok if decl == sh2 else rep.fail)(f"{TSH} §9", "structural.declared",
                                              "tap.netlist.structuralHash equals the version 2 hash of the fetched file" if decl == sh2
                                              else f"tap.netlist.structuralHash {decl} differs from the version 2 hash {sh2} of the fetched file")


# ---------------------------------------------------------------- source circuits (§3.2)

def check_source(tap: dict, rpc: C.Rpc, rep: Report) -> dict:
    """§3.2 for a declared source. Returns {"confirmed": bool|None, "design": …, "block": …}."""
    out = {"confirmed": None, "design": None, "block": None}
    src = tap.get("source")
    if src is None:
        return out
    if tapnft.netlist_status(tap) != "tapnet/1":
        rep.unverifiable(f"{T721} §2.5", "source.check", "source verification applies to tapnet/1 netlists only")
        return out
    cid, proc, circ = src["chainId"], src["processor"], int(src["circuitId"])
    if not rpc.has_chain(cid):
        rep.unverified(f"{T721} §3.2", "source.check", f"not verified: no RPC for chain {cid} (pass --source-rpc)" + (" / not in the fixture" if rpc.offline else ""))
        return out
    try:
        pinned = rpc.pinned_block(cid)
        fac = FACTORY.get(cid)
        if fac is None:
            rep.unverified(f"{T721} §3.2", "source.check", f"not verified: the processor factory of chain {cid} is not known to this tool (step 1)")
            return out
        if not rpc.call_decode(cid, fac, "isCPU(address)", (proc,), "bool", pinned):
            rep.fail(f"{T721} §3.2", "source.check", f"{proc} is not registered with the processor factory {fac} (step 1, read at block {pinned})")
            return out
        block, how = src["block"], "the declared block"
        try:
            info = rpc.call_decode(cid, proc, "circuitInfo(uint256)", (circ,), ["uint256", "uint256", "uint256", "uint256"], block)
            nl = rpc.call_decode(cid, proc, "netlist(uint256)", (circ,), "bytes", block)
        except (C.RpcError, C.NotRecorded):
            block, how = pinned, "the pinned block (declared block not readable; a stored netlist has no setter, so any later block confirms it)"
            info = rpc.call_decode(cid, proc, "circuitInfo(uint256)", (circ,), ["uint256", "uint256", "uint256", "uint256"], block)
            nl = rpc.call_decode(cid, proc, "netlist(uint256)", (circ,), "bytes", block)
    except (C.RpcError, C.NotRecorded) as e:
        rep.unverified(f"{T721} §3.2", "source.check", f"not verified: chain read failed ({e})")
        return out
    out["block"] = block
    try:
        f = tapnft.file_from_chain(nl, info[0], info[1])
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §3.2", "source.check", f"the source circuit's file is not a valid tapnet/1 file ({e}): it cannot be a source under this version")
        return out
    got = hx(tapnft.netlist_hash(f))
    out["design"] = {"netlistHash": got, "structuralHash": hx(canon.structural_hash(f))}
    if got != tap["netlist"]["sha256"]:
        out["confirmed"] = False
        rep.fail(f"{T721} §3.2", "source.check", f"source NOT confirmed: the file built from circuitInfo/netlist hashes to {got}, not to tap.netlist.sha256 (read at {how}, block {block})")
        return out
    out["confirmed"] = True
    rep.ok(f"{T721} §3.2", "source.check", f"source confirmed: isCPU at block {pinned}; circuitInfo/netlist read at {how}, block {block}, rebuild to {got}")
    if "name" in src:
        num = None
        m = re.match(r"^(\d+)(?:\.(\d+))?\.(\d+)\.tape$", src["name"])
        if m:
            num = int(m.group(3))
        if num is not None and fac:
            try:
                at = rpc.call_decode(cid, fac, "cpuAt(uint256)", (num,), "address", pinned)
                want = tapnft.tape_name(circ, num, AREA_CODE.get(cid))
                if at == proc and src["name"] == want:
                    rep.ok(f"{T721} §3.1", "source.name", f"on-chain name {src['name']} matches cpuAt({num})")
                else:
                    rep.fail(f"{T721} §3.1", "source.name", f"tap.source.name {src['name']} does not match (cpuAt({num}) = {at}, expected name {want})")
            except (C.RpcError, C.NotRecorded) as e:
                rep.skip(f"{T721} §3.1", "source.name", f"name not checked ({e})")
    if "container" in src:
        op = OPENER.get(cid)
        if op is None:
            rep.unverified(f"{T721} §3.2", "source.container", f"declared container not checked: the container opener of chain {cid} is not known to this tool; a reported address is not accepted (item 5)")
        else:
            try:
                acct = rpc.call_decode(cid, op, "accountOf(address,uint256)", (proc, circ), "address", pinned)
                (rep.ok if acct == src["container"] else rep.fail)(f"{T721} §3.2", "source.container",
                                                                  f"container {src['container']} {'equals' if acct == src['container'] else 'differs from'} accountOf(processor, id) = {acct} (item 5)")
            except (C.RpcError, C.NotRecorded) as e:
                rep.unverified(f"{T721} §3.2", "source.container", f"declared container not checked ({e})")
    return out


# ---------------------------------------------------------------- conformance level (§8)

def probe_interfaces(rpc: C.Rpc, cid: int, addr: str, names: list) -> dict:
    return {n: rpc.supports_interface(cid, addr, IID[n]) for n in names}


def detect_level(rpc: C.Rpc, cid: int, contract: str, tap: dict | None, rep: Report) -> dict:
    """§8: the level a tool displays, decided by ERC-165 (never by the presence of selectors, TAP-SB §10.1 item 5)."""
    out = {"level": "L0", "iface": None, "via": None, "ifaces": {}, "credential": False, "mirror": False}
    if cid is None or not contract or not rpc.has_chain(cid):
        rep.skip(f"{T721} §8", "level", "conformance level not detected: no RPC for the collection's chain" + (" / not in the fixture" if rpc.offline else ""))
        return out
    try:
        code = rpc.get_code(cid, contract)
    except (C.RpcError, C.NotRecorded):
        code = None
    if code is not None and code in ("0x", ""):
        rep.fail(f"{T721} §8", "level", f"no contract code at {contract} on {chain_label(rpc, cid)}")
        return out
    names = ["ERC165", "ERC721", "ERC4906", "ITapNetlistNFT", "ITapCompanion", "ITapNetlistEval", "ITapNetlistTokenSet",
             "ITapBridgeMirror", "ITapCredential", "ERC5192", "ERC7496"]
    try:
        f = probe_interfaces(rpc, cid, contract, names)
    except (C.NotRecorded) as e:
        rep.skip(f"{T721} §8", "level", f"ERC-165 not probed: {e}")
        return out
    out["ifaces"] = f
    rep.info(f"{T721} §8", "erc165", "reported: " + (", ".join(n for n in names if f[n]) or "none") + f" ({chain_label(rpc, cid)})")
    out["credential"] = f["ITapCredential"]
    out["mirror"] = f["ITapBridgeMirror"]
    l1 = f["ITapNetlistNFT"] and f["ERC165"] and f["ERC4906"]
    if f["ITapNetlistNFT"] and not l1:
        rep.fail(f"{T721} §8.2", "level", "ITapNetlistNFT reported without ERC-165 and ERC-4906: not L1")
    if l1:
        out.update(level="L1", iface=contract, via="contract")
        rep.ok(f"{T721} §8.2", "level", "L1 (on-chain interface): ITapNetlistNFT, ERC-165 and ERC-4906 reported")
        return out
    # §8.3: L1 through a companion named in the metadata
    comp = (tap or {}).get("companion")
    if comp and comp["chainId"] == cid and rpc.has_chain(cid):
        g = probe_interfaces(rpc, cid, comp["address"], ["ITapNetlistNFT", "ITapCompanion", "ERC165", "ERC4906"])
        try:
            col = rpc.call_decode(cid, comp["address"], "collection()", (), "address")
        except (C.RpcError, C.NotRecorded):
            col = None
        if g["ITapNetlistNFT"] and g["ITapCompanion"] and g["ERC165"] and g["ERC4906"] and col == contract:
            out.update(level="L1", iface=comp["address"], via="companion")
            rep.ok(f"{T721} §8.3", "level", f"L1 via companion {comp['address']} (ITapNetlistNFT + ITapCompanion reported, collection() = {contract})")
            try:
                by = rpc.call_decode(cid, comp["address"], "endorsedBy()", (), "address")
                rep.info(f"{T721} §8.3", "companion.endorsed", f"endorsedBy() = {by}" if by != ZERO_ADDR else "not endorsed on chain; the binding rests on tap.companion (way 1)")
            except (C.RpcError, C.NotRecorded):
                pass
            return out
        rep.fail(f"{T721} §8.3", "companion", f"tap.companion {comp['address']} is not a two-way bound companion "
                 f"(ITapNetlistNFT {g['ITapNetlistNFT']}, ITapCompanion {g['ITapCompanion']}, collection() = {col})")
    if f["ITapCredential"]:
        rep.ok(f"{TSB} §10.1", "level", "L0 (metadata only); metadata can change (credential contract: tokenURI fixed at mint is established only by a code check, §10.1 item 4)")
        return out
    label = "L0 (metadata only)"
    if tap is not None and "manifest" not in tap:
        label += ", no manifest: content not committed"
    rep.ok(f"{T721} §8.1", "level", label)
    return out


# ---------------------------------------------------------------- L1 reads and states (§7.2, §8.2)

def read_l1(rpc: C.Rpc, cid: int, iface: str, token_id: int) -> dict:
    d = {}
    d["collection"] = rpc.call_decode(cid, iface, "collection()", (), "address")
    d["tokenRange"] = tuple(rpc.call_decode(cid, iface, "tokenRange()", (), ["uint256", "uint256"]))
    d["manifestHash"] = rpc.call_decode(cid, iface, "manifestHash()", (), "bytes32")
    d["masterSeed"] = rpc.call_decode(cid, iface, "masterSeed()", (), "bytes32")
    d["pools"] = rpc.call_decode(cid, iface, "pools()", (), "(string,uint8,bytes32)[]")
    d["frozen"] = rpc.call_decode(cid, iface, "frozen()", (), "bool")
    d["netlistHashOf"] = rpc.call_decode(cid, iface, "netlistHashOf(uint256)", (token_id,), "bytes32")
    d["imageHashOf"] = rpc.call_decode(cid, iface, "imageHashOf(uint256)", (token_id,), "bytes32")
    d["entryIndexOf"] = {}
    for p in range(len(d["pools"])):
        try:
            d["entryIndexOf"][p] = rpc.call_decode(cid, iface, "entryIndexOf(uint256,uint256)", (token_id, p), "uint256")
        except (C.RpcError, C.NotRecorded):
            d["entryIndexOf"][p] = None
    return d


def check_l1(rpc: C.Rpc, cid: int, lvl: dict, tap: dict, token_id: int, rep: Report) -> dict:
    """Profile (manifest / mint-bound / bridged copy), reveal and frozen state from the chain."""
    iface = lvl["iface"]
    try:
        d = read_l1(rpc, cid, iface, token_id)
    except (C.RpcError, C.NotRecorded, ValueError) as e:
        rep.fail(f"{T721} §8.2", "l1.reads", f"ITapNetlistNFT reads failed: {e}")
        return {}
    has_manifest = "manifest" in tap
    pools_empty = len(d["pools"]) == 0
    if lvl["mirror"]:
        profile = "bridged"
        rep.info(f"{TBR} §5.3", "profile", "bridged copy (ITapBridgeMirror reported): the reveal and the manifest file are on the home chain; "
                 "tap.id is the home token's identifier; netlistHashOf/imageHashOf are the hashes that arrived with the token; frozen() may stay false (TAP-721 §8.2)")
    elif d["manifestHash"] == ZERO32 and d["masterSeed"] == ZERO32 and pools_empty and not has_manifest:
        profile = "mint-bound"
        rep.info(f"{T721} §8.2", "profile", "mint-bound collection: manifestHash() and masterSeed() are zero and pools() is empty; the netlist hash was recorded at mint; "
                 "tokenRange() is informative and coverage is not derived from it")
    elif d["manifestHash"] == ZERO32 and d["masterSeed"] == ZERO32 and pools_empty and has_manifest:
        profile = "uncommitted"
        rep.warn(f"{T721} §8.2", "profile", "manifest not yet committed on chain (manifestHash() is zero) although the metadata names one")
    elif d["manifestHash"] != ZERO32 and pools_empty and d["masterSeed"] == ZERO32:
        profile = "bridged?"
        rep.warn(f"{T721} §8.2", "profile", "looks like a bridged copy (manifest hash without pools or seed) but reports no ITapBridgeMirror")
    else:
        profile = "manifest"
        rep.info(f"{T721} §8.2", "profile", f"collection with a manifest: manifestHash() = {d['manifestHash']}, {len(d['pools'])} pool(s) committed")
    if d["manifestHash"] != ZERO32:
        if not has_manifest:
            rep.fail(f"{T721} §7.1", "manifest.onchain", f"manifestHash() = {d['manifestHash']} but the metadata carries no tap.manifest")
        elif tap["manifest"]["sha256"] != d["manifestHash"]:
            rep.fail(f"{T721} §7.1", "manifest.onchain", f"tap.manifest.sha256 differs from manifestHash() = {d['manifestHash']}")
        else:
            rep.ok(f"{T721} §7.1", "manifest.onchain", "tap.manifest.sha256 equals manifestHash()")
    # reveal state (§7.2, §8.2 item 2)
    seed = d["masterSeed"]
    if profile == "mint-bound":
        rep.info(f"{T721} §7.2", "state.chain", "no reveal: a mint-bound token is bound at mint and never uses the state unrevealed")
        if tap["state"] != "revealed":
            rep.fail(f"{T721} §8.2", "state.consistency", "mint-bound metadata MUST NOT use the state unrevealed")
    elif profile == "bridged":
        rep.info(f"{T721} §7.2", "state.chain", "reveal state is read on the home chain; the copy carries the arrived hashes")
    elif seed == ZERO32:
        rep.info(f"{T721} §7.2", "state.chain", "not revealed on chain: masterSeed() is zero")
        if tap["state"] == "revealed" and profile == "manifest":
            rep.fail(f"{T721} §7.2", "state.consistency", "metadata says revealed but masterSeed() is zero")
    elif seed == ONES32:
        rep.info(f"{T721} §7.2", "state.chain", "revealed without a reveal: reveal.source none, masterSeed() is the all-ones value and counts as set (§8.2 item 2)")
    else:
        rep.info(f"{T721} §7.2", "state.chain", f"revealed on chain: masterSeed() = {seed}")
    if profile == "manifest" and seed != ZERO32 and tap["state"] == "unrevealed":
        rep.warn(f"{T721} §7.2", "state.consistency", "the seed is set but the metadata is still unrevealed: not yet updated, or the token is outside the token set (§5.4)")
    # frozen (§7.2 / §8.2 item 5)
    if d["frozen"]:
        rep.ok(f"{T721} §7.2", "frozen", "frozen: frozen() returns true (manifest committed, seed set, nothing can change; latched)" if profile == "manifest"
               else "frozen: frozen() returns true")
    else:
        rep.info(f"{T721} §7.2", "frozen", "not frozen: frozen() returns false (content can still change)" + (" — a bridged copy may stay false" if profile == "bridged" else ""))
    # hashes (§8.2: metadata values MUST equal the interface, except a field no pool carries)
    st = tapnft.netlist_status(tap)
    if "netlist" in tap:
        if st != "tapnet/1":
            rep.unverifiable(f"{T721} §2.5", "netlist.onchain", f"netlistHashOf() = {d['netlistHashOf']} not compared: the format's netlist hash rule is not supported")
        elif d["netlistHashOf"] == ZERO32:
            rep.warn(f"{T721} §8.2", "netlist.onchain", "netlistHashOf() is zero: no netlist hash known on chain yet (not bound, §8.2 item 4), or the netlist field is carried by no pool")
        elif d["netlistHashOf"] == tap["netlist"]["sha256"]:
            rep.ok(f"{T721} §8.2", "netlist.onchain", "netlistHashOf() equals tap.netlist.sha256")
        else:
            rep.fail(f"{T721} §8.2", "netlist.onchain", f"netlistHashOf() = {d['netlistHashOf']} differs from tap.netlist.sha256")
    if "image" in tap:
        if d["imageHashOf"] == ZERO32:
            rep.info(f"{T721} §8.2", "image.onchain", "imageHashOf() is zero: not bound yet, or the image is fixed in the metadata (no pool / mint-bound without image hashes)")
        elif d["imageHashOf"] == tap["image"]["sha256"]:
            rep.ok(f"{T721} §8.2", "image.onchain", "imageHashOf() equals tap.image.sha256")
        else:
            rep.fail(f"{T721} §8.2", "image.onchain", f"imageHashOf() = {d['imageHashOf']} differs from tap.image.sha256")
    # coverage (§5.4, §8.5)
    first, supply = d["tokenRange"]
    set_mode = False
    if lvl["ifaces"].get("ITapNetlistTokenSet"):
        try:
            tsh = rpc.call_decode(cid, iface, "tokenSetHash()", (), "bytes32")
            set_mode = tsh != ZERO32
        except (C.RpcError, C.NotRecorded):
            tsh = None
        if set_mode:
            try:
                idx = rpc.call_decode(cid, iface, "indexOf(uint256)", (token_id,), "uint256")
                rep.info(f"{T721} §8.5", "coverage", f"set mode (tokenSetHash {tsh}): token covered, index {idx}")
            except (C.RpcError, C.NotRecorded):
                rep.info(f"{T721} §8.5", "coverage", f"set mode (tokenSetHash {tsh}): indexOf reverts, the token is not covered or the set is not recorded yet")
    if not set_mode and profile == "manifest":
        if supply == 0:
            rep.info(f"{T721} §8.2", "coverage", "tokenRange() supply 0: unbounded range (bridged copy or mint-bound)")
        elif first <= token_id < first + supply:
            rep.ok(f"{T721} §8.2", "coverage", f"token in tokenRange() {first}…{first + supply - 1}, index {token_id - first}")
        else:
            rep.fail(f"{T721} §8.2", "coverage", f"token outside tokenRange() {first}…{first + supply - 1}")
    d["profile"], d["setMode"] = profile, set_mode
    return d


# ---------------------------------------------------------------- L0 freeze probe (§5.1, §7.2)

def freeze_probe(rpc: C.Rpc, probe: dict, where: str, rep: Report) -> None:
    cid = probe["chainId"]
    if not rpc.has_chain(cid):
        rep.skip(f"{T721} §7.2", "frozen", f"freeze probe {probe['call']} ({where}) not read: no RPC for chain {cid}")
        return
    try:
        val = rpc.call_decode(cid, probe["contract"], probe["call"], (), "bool")
    except (C.RpcError, C.NotRecorded, ValueError) as e:
        rep.skip(f"{T721} §7.2", "frozen", f"freeze probe {probe['call']} ({where}) failed: {e}")
        return
    if val == probe["expect"]:
        rep.ok(f"{T721} §7.2", "frozen", f"frozen: {probe['call']} on {probe['contract']} returns {str(val).lower()} = expect ({where}); L0: the guarantee rests on the collection having given up the power to change tokenURI (§8.1)")
    else:
        rep.info(f"{T721} §7.2", "frozen", f"not frozen: {probe['call']} on {probe['contract']} returns {str(val).lower()} ({where}); the owner can still change tokenURI")


# ---------------------------------------------------------------- manifest and assignment (§5, §6)

def check_manifest_file(args, tap: dict, l1: dict, rpc: C.Rpc, token_id: int, rep: Report) -> dict | None:
    """§5.1–§5.4 and the recomputed assignment of §6. Returns the parsed manifest or None."""
    if "manifest" not in tap:
        return None
    src = getattr(args, "manifest", None)
    raw = None
    if src:
        raw = fetch_bytes(src, rpc.offline)
    elif not rpc.offline:
        for u in tap["manifest"]["uris"]:
            try:
                raw = fetch_bytes(u, False)
                src = u
                break
            except (IOError, OSError):
                continue
    if raw is None:
        rep.skip(f"{T721} §5.1", "manifest.file", "manifest not fetched (pass --manifest): assignment not recomputed")
        return None
    got = hx(sha256(raw))
    if got != tap["manifest"]["sha256"]:
        rep.fail(f"{T721} §5.1", "manifest.file", f"{src} hashes to {got}, not to tap.manifest.sha256")
        return None
    try:
        man = tapnft.check_manifest(raw)
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §5.1", "manifest.file", f"manifest invalid: {e}")
        return None
    col = man["collection"]
    tid = parse_token_id(tap["id"])
    if tid and (col["chainId"], col["address"]) != (tid[0], tid[1]):
        rep.fail(f"{T721} §5.1", "manifest.file", f"manifest.collection {col['chainId']}/{col['address']} is not the collection of tap.id")
        return None
    size = f"token set of {col['tokenSet']['count']}" if "tokenSet" in col else f"range {col['firstTokenId']}…{col['firstTokenId'] + col['supply'] - 1}"
    rep.ok(f"{T721} §5.1", "manifest.file", f"manifest {got} valid (§5.1–§5.2 and §6.1 parameters): {size}, reveal {man['reveal']['source']}, pools {[p['label'] for p in man['pools']]}")
    if l1 and l1.get("pools") is not None and l1.get("profile") == "manifest":
        want = [(p["label"], tapnft.fields_mask(p["fields"]), p["root"]) for p in man["pools"]]
        have = [(p[0], p[1], p[2]) for p in l1["pools"]]
        (rep.ok if want == have else rep.fail)(f"{T721} §8.2", "pools.onchain",
                                               "pools() equals the manifest's pools (label, field mask, root; item 1)" if want == have
                                               else f"pools() {have} differs from the manifest's pools {want}")
    ids = None
    if "tokenSet" in col:
        ts = getattr(args, "token_set", None)
        if not ts:
            rep.skip(f"{T721} §5.4", "tokenset.file", "set mode: token set file not given (--token-set): coverage and assignment not recomputed")
            return man
        try:
            ids = tapnft.check_token_set(man, fetch_bytes(ts, rpc.offline))
            rep.ok(f"{T721} §5.4", "tokenset.file", f"token set file checked: {len(ids)} ids, hash {col['tokenSet']['sha256']}")
        except (tapnft.Invalid, IOError) as e:
            rep.fail(f"{T721} §5.4", "tokenset.file", f"token set file rejected: {e}")
            return man
    # master seed
    seed = None
    if man["reveal"]["source"] != "none":
        s = (l1 or {}).get("masterSeed")
        if s and s not in (ZERO32, ONES32):
            seed = bytes.fromhex(s[2:])
        elif getattr(args, "master_seed", None):
            seed = bytes.fromhex(args.master_seed[2:])
        if seed is None:
            rep.skip(f"{T721} §6", "assignment", "master seed unknown (not revealed on chain; pass --master-seed for an L0 collection): assignment not recomputed")
            return man
    try:
        asg = tapnft.assignment(man, seed, token_id, ids)
    except tapnft.Invalid as e:
        rep.fail(f"{T721} §6", "assignment", f"{e}")
        return man
    if asg is None:
        rep.info(f"{T721} §5.4", "assignment", "token not covered by the manifest (outside the range or the token set): it receives no pool entry, now or later; not awaiting a reveal")
        if tap["state"] != "unrevealed" or "image" in tap or "netlist" in tap:
            rep.fail(f"{T721} §5.4", "assignment", "a token outside the token set MUST be unrevealed without tap.image and tap.netlist")
        return man
    for k, pool in enumerate(man["pools"]):
        x = asg[pool["label"]]
        entry = pool["entries"][x]
        line = f"pool {pool['label']!r}: entry {x}"
        oc = (l1 or {}).get("entryIndexOf", {}).get(k)
        if oc is not None:
            line += f"; entryIndexOf({token_id}, {k}) = {oc}" + ("" if oc == x else " MISMATCH")
            if oc != x:
                rep.fail(f"{T721} §8.2", "assignment", line + " (item 2)")
                continue
        rep.ok(f"{T721} §6.3", "assignment", line)
        if tap["state"] == "revealed":
            for f in pool["fields"]:
                decl = tap.get(f, {}).get("sha256")
                if decl is None:
                    rep.fail(f"{T721} §7.3", f"{f}.entry", f"tap.{f} missing although the pool carries the field")
                elif decl == entry[f]:
                    rep.ok(f"{T721} §7.3", f"{f}.entry", f"tap.{f}.sha256 equals the pool entry's {f} value (item 3)")
                else:
                    rep.fail(f"{T721} §7.3", f"{f}.entry", f"tap.{f}.sha256 {decl} differs from the pool entry's value {entry[f]} (item 3)")
    return man


# ---------------------------------------------------------------- PoD attributes

def check_pod(tap: dict, manifest: dict | None, source: dict, rpc: C.Rpc, lvl: dict, cid, contract, token_id, rep: Report) -> None:
    if "pod" not in tap:
        return
    pv = P.pod_validate()
    if pv is None:
        rep.skip(f"{TPOD} §3.7", "pod.format", "tap.pod not checked: pod_validate.py needs pycryptodome")
        return
    r = pv.validate_tap(tap, manifest)
    for e in r.errors:
        rep.fail(f"{TPOD} §3.7", "pod.format", e)
    for w in r.warnings:
        rep.warn(f"{TPOD} §3.7", "pod.format", w)
    if not r.ok:
        rep.fail(f"{TPOD} §4.2", "pod.verify", "snapshot rejected (not well-formed): no PoD fact is displayed")
        return
    pod = tap["pod"]
    rep.ok(f"{TPOD} §3.7", "pod.format", f"tap.pod well-formed: snapshot of {pod['processor']}#{pod['circuitId']} at block {pod['block']}" + (" (manifest commitments checked, §4.4)" if manifest else ""))
    basis = "facts about the NFT's netlist (source confirmed)" if source.get("confirmed") else "declared by the collection, not verified (source not confirmed, §2 item 4)"
    d, s = pod["design"], pod["standing"]
    rep.info(f"{TPOD} §3.4", "pod.design", f"recorded design facts — task {d['taskId']}{(' ' + d['task']['name']) if d.get('task') else ''}: NAND burn {d['nandBurn']}, LATCH burn {d['latchBurn']}, "
             f"depth {d['depth']}, area {d['area']}, b* {d['bstar']}, design cost {d['cost']}; {basis}")
    rep.info(f"{TPOD} §3.1", "pod.standing", f"standing at block {pod['block']} (not current): status {s['status']} ({s['statusLabel']}), optimal first {str(s['optimal']).lower()}, "
             f"bonus {s['bonus']}, multiplier {s['multiplier']}, verifWeight {s['verifWeight']}, unverWeight {s['unverWeight']}; {basis}")
    rep.info(f"{TPOD} §3.9", "pod.verified", f"PoD sampling status at block {pod['block']}: verified = {str(s['verified']).lower()} (the mining contract's sampled vectors); "
             "not evidence that the netlist computes the task's function")
    fc = pod.get("functionCheck")
    if fc:
        if fc.get("method") == "unconfirmed":
            rep.info(f"{TPOD} §3.9", "pod.functionCheck", "functional check unconfirmed (could not be run): the netlist is not shown as correct")
        elif fc.get("result") == "match":
            rep.ok(f"{TPOD} §3.9", "pod.functionCheck", f"function matches the task's reference circuit {fc['reference']['processor']}#{fc['reference']['circuitId']}: {fc['method']}, {fc['vectors']} vectors ({fc['procedure']})")
        else:
            rep.fail(f"{TPOD} §3.9", "pod.functionCheck", f"function MISMATCH against the reference circuit ({fc['method']}, {fc['vectors']} vectors): not correct for its task even though verified = {str(s['verified']).lower()}")
    else:
        rep.info(f"{TPOD} §3.9", "pod.functionCheck", "no functional check recorded: the netlist is not shown as correct for its task")
    rep.info(f"{TPOD} §7", "pod.notice", f"Mining facts of the source circuit at block {pod['block']}. The NFT does not mine and earns nothing.")
    _verify_pod_snapshot(pod, rpc, rep)
    if lvl.get("ifaces", {}).get("ERC7496") and cid is not None:
        _check_pod_traits(pod, rpc, cid, contract, token_id, rep)


def _verify_pod_snapshot(pod: dict, rpc: C.Rpc, rep: Report) -> None:
    """§4.2 item 3: re-read every getter at the snapshot block and compare."""
    cid, B = pod["chainId"], pod["block"]
    if not rpc.has_chain(cid):
        rep.unverified(f"{TPOD} §4.2", "pod.verify", f"unavailable: no RPC for chain {cid}")
        return
    try:
        key = rpc.call_decode(cid, pod["mining"], "minerKey(address,uint256)", (pod["processor"], int(pod["circuitId"])), "bytes32", B)
        miner = dict(zip(MINER_FIELDS, rpc.call_decode(cid, pod["mining"], "getMiner(bytes32)", (key,), "(" + MINER_TYPES + ")", B)))
        lam = rpc.call_decode(cid, pod["mining"], "lambda()", (), "uint256", B)
        beta = rpc.call_decode(cid, pod["mining"], "beta()", (), "uint256", B)
        lb = rpc.call_decode(cid, pod["mining"], "lambdaBurn()", (), "uint256", B)
        pm = rpc.call_decode(cid, pod["mining"], "processorMultiplier(address)", (pod["processor"],), "uint256", B)
    except (C.RpcError, C.NotRecorded) as e:
        rep.unverified(f"{TPOD} §4.2", "pod.verify", f"unavailable: state at block {B} could not be read ({e}); not reported as confirmed from another block")
        return
    d, s, p = pod["design"], pod["standing"], pod["params"]
    diffs = []

    def cmp(name, want, got):
        if str(want) != str(got):
            diffs.append(f"{name}: snapshot {want}, chain {got}")
    cmp("minerKey", pod["minerKey"], key)
    cmp("params.lambda", p["lambda"], lam); cmp("params.beta", p["beta"], beta); cmp("params.lambdaBurn", p["lambdaBurn"], lb)
    cmp("params.processorMultiplier", p["processorMultiplier"], pm)
    for k in ("taskId", "gateCount", "stateCount", "depth", "nandBurn", "latchBurn", "area", "bstar"):
        cmp(f"design.{k}", d[k], miner[k])
    cost = int(miner["area"]) * max(int(miner["depth"]), 1) ** int(beta)
    cmp("design.cost", d["cost"], cost)
    cmp("standing.status", s["status"], miner["status"]); cmp("standing.optimal", s["optimal"], miner["optimal"])
    cmp("standing.bonus", s["bonus"], miner["bonus"]); cmp("standing.multiplier", s["multiplier"], miner["mult"])
    cmp("standing.verifWeight", s["verifWeight"], miner["verifWeight"]); cmp("standing.unverWeight", s["unverWeight"], miner["unverWeight"])
    cmp("standing.since", s["since"], miner["since"]); cmp("standing.stopBlock", s["stopBlock"], miner["stopBlock"])
    cmp("standing.verified", s["verified"], int(miner["verifWeight"]) > 0)
    if d.get("task"):
        try:
            t = rpc.call_decode(cid, pod["mining"], "getTask(uint32)", (d["taskId"],), TASK_TYPES, B)
            cmp("design.task.name", d["task"]["name"], t[7]); cmp("design.task.kTask", d["task"]["kTask"], t[8]); cmp("design.task.cRef", d["task"]["cRef"], t[9])
        except (C.RpcError, C.NotRecorded):
            pass
    if diffs:
        rep.fail(f"{TPOD} §4.2", "pod.verify", "mismatch: " + "; ".join(diffs))
    else:
        rep.ok(f"{TPOD} §4.2", "pod.verify", f"confirmed: every getter re-read at block {B} equals the snapshot" + (" (recorded reads)" if rpc.offline else ""))


def _check_pod_traits(pod: dict, rpc: C.Rpc, cid: int, contract: str, token_id: int, rep: Report) -> None:
    """§5.4 item 4: ERC-7496 traits must describe the same snapshot as tap.pod."""
    keys = [hx(keccak256(f"tap.pod.{n}".encode())) for n in POD_TRAITS]
    try:
        vals = []
        for k in keys:
            vals.append(rpc.call_decode(cid, contract, "getTraitValue(uint256,bytes32)", (token_id, k), "bytes32"))
    except (C.RpcError, C.NotRecorded) as e:
        rep.skip(f"{TPOD} §5.4", "pod.traits", f"ERC-7496 traits not read: {e}")
        return
    if int(vals[0], 16) == 0:
        rep.info(f"{TPOD} §5.4", "pod.traits", "no on-chain PoD traits (tap.pod.snapshotBlock is zero); other zero traits are not read as facts")
        return
    d, s = pod["design"], pod["standing"]
    want = [pod["block"], d["taskId"], d["nandBurn"], d["latchBurn"], d["area"], d["depth"], d["cost"], d["bstar"], s["status"],
            1 if s["optimal"] else 0, s["bonus"], s["multiplier"], 1 if s["verified"] else 0, s["verifWeight"], s["unverWeight"]]
    bad = [n for n, w, v in zip(POD_TRAITS, want, vals) if int(w) != int(v, 16)]
    if bad:
        rep.fail(f"{TPOD} §5.4", "pod.traits", f"on-chain traits disagree with tap.pod ({', '.join(bad)}): the token is treated as mismatch until corrected")
    else:
        rep.ok(f"{TPOD} §5.4", "pod.traits", f"ERC-7496 traits describe the same snapshot as tap.pod (block {pod['block']})")


# ---------------------------------------------------------------- bridge discovery (TAP-BR §5.2)

def collection_key(home_chain_id: int, home_contract: str) -> str:
    """TAP-BR §3: keccak256(abi.encode("TAP-NFT collection v1", uint64 homeChainId, address homeContract))."""
    tag = b"TAP-NFT collection v1"
    enc = ((96).to_bytes(32, "big") + home_chain_id.to_bytes(32, "big") + bytes(12) + bytes.fromhex(home_contract[2:])
           + len(tag).to_bytes(32, "big") + tag.ljust(32, b"\0"))
    return hx(keccak256(enc))


def check_bridge(tap: dict, rpc: C.Rpc, rep: Report) -> None:
    b = tap.get("bridge")
    if not b:
        return
    tid = parse_token_id(tap["id"])
    cid = b.get("chainId")
    if not (tid and isinstance(cid, int) and isinstance(b.get("gateway"), str) and rpc.has_chain(cid)):
        rep.unverified(f"{TBR} §5.2", "bridge.gateway", "gateway not checked (no RPC for the home chain or malformed tap.bridge); a client MUST NOT use it unchecked")
        return
    try:
        home = rpc.call_decode(cid, b["gateway"], "homeChainId()", (), "uint64")
        key = rpc.call_decode(cid, b["gateway"], "collectionKey()", (), "bytes32")
    except (C.RpcError, C.NotRecorded, ValueError) as e:
        rep.unverified(f"{TBR} §5.2", "bridge.gateway", f"gateway not checked ({e})")
        return
    want = collection_key(tid[0], tid[1])
    if home == tid[0] and key == want and cid == tid[0]:
        rep.ok(f"{TBR} §5.2", "bridge.gateway", f"gateway {b['gateway']}: homeChainId() = {home} and collectionKey() = {key} match the collection (§3)")
    else:
        rep.fail(f"{TBR} §5.2", "bridge.gateway", f"gateway {b['gateway']} does not belong to this collection (homeChainId {home}, collectionKey {key}, expected {want})")


# ---------------------------------------------------------------- design credits (TAP-DC)

def _publication_reads(fact: dict, rpc: C.Rpc) -> dict | None:
    """The `reads` dict of credits.verify_publication, from ≥ 2 nodes online, or from the fixture."""
    cid = fact["chainId"]
    if rpc.offline:
        rec = rpc.fixture.get("publicationReads", {}).get(f"{cid}:{fact['processor']}:{fact['circuitId']}")
        return rec
    urls = rpc.urls(cid)
    if len(urls) < 2 or cid not in C.FINALITY_TAG or cid not in FACTORY:
        return None
    reads = {"finalityTag": C.FINALITY_TAG[cid], "isCPU": {}, "receipt": {}, "block": {}, "circuitInfo": {}, "cpuAt": {}, "finalityBlock": {}, "netlist": {}}
    fin = {}
    for u in urls:
        fin[u] = int(rpc.get_block(cid, C.FINALITY_TAG[cid], u)["number"], 16)
    sb = min(fin.values())
    reads["stateBlock"] = sb
    num = None
    m = re.match(r"^(\d+)(?:\.(\d+))?\.(\d+)\.tape$", fact.get("name", ""))
    if m:
        num = int(m.group(3))
    reads["processorNumber"], reads["areaCode"] = num, AREA_CODE.get(cid)
    for u in urls:
        reads["finalityBlock"][u] = fin[u]
        reads["receipt"][u] = rpc.get_receipt(cid, fact["txHash"], u)
        reads["block"][u] = rpc.get_block(cid, fact["block"], u)
        reads["isCPU"][u] = rpc.call_decode(cid, FACTORY[cid], "isCPU(address)", (fact["processor"],), "bool", sb, u)
        reads["circuitInfo"][u] = rpc.call(cid, fact["processor"], C.encode_call("circuitInfo(uint256)", int(fact["circuitId"])), sb, u)
        reads["netlist"][u] = hx(rpc.call_decode(cid, fact["processor"], "netlist(uint256)", (int(fact["circuitId"]),), "bytes", sb, u))
        if num is not None:
            reads["cpuAt"][u] = rpc.call_decode(cid, FACTORY[cid], "cpuAt(uint256)", (num,), "address", sb, u)
        reads.setdefault("publisherCode", {})[u] = rpc.get_code(cid, fact["publisher"], sb, u)
    return reads


def _design_from_reads(reads: dict) -> dict:
    infos, nls = set(reads.get("circuitInfo", {}).values()), set(reads.get("netlist", {}).values())
    if len(infos) != 1 or len(nls) != 1:
        return {"netlistHash": None, "structuralHash": None}
    info = C.decode(["uint256", "uint256", "uint256", "uint256"], infos.pop())
    return credits.design_of(bytes.fromhex(nls.pop()[2:]), info[0], info[1])


def _erc1271_reader(rpc: C.Rpc):
    if rpc.offline:
        rec = rpc.fixture.get("erc1271", {})
        return credits.recorded_erc1271(rec.get("calls", []), rec.get("verificationBlocks", {}))

    def reader(chain, account, d, sig, block=None):
        urls = rpc.urls(chain)
        if len(urls) < 2 or chain not in C.FINALITY_TAG:
            return None
        if block is None:
            block = min(int(rpc.get_block(chain, C.FINALITY_TAG[chain], u)["number"], 16) for u in urls)
        data = "0x1626ba7e" + d.hex() + (64).to_bytes(32, "big").hex() + len(sig).to_bytes(32, "big").hex() + sig.hex() + "00" * ((-len(sig)) % 32)
        answers = set()
        for u in urls:
            try:
                answers.add(rpc.call(chain, account, data, block, u)[:10])
            except C.RpcError:
                answers.add("revert")
        if len(answers) != 1:
            return None
        return answers.pop() == "0x1626ba7e", block
    return reader


def _container_resolver(rpc: C.Rpc):
    if rpc.offline:
        return credits.recorded_containers(rpc.fixture.get("containers", {}))
    return None  # TAP-10 §4.3 container resolution is not implemented online (README)


def check_credits(bundle: dict, standalone: bool, rpc: C.Rpc, rep: Report, file_design: dict | None = None) -> None:
    """TAP-DC §3–§6: facts verified vs claims, with the display rules of §6."""
    try:
        credits.check_bundle(bundle, standalone)
    except credits.Invalid as e:
        rep.fail(f"{TDC} §5.1", "credits.bundle", f"not a credit bundle: {e}")
        return
    rep.ok(f"{TDC} §5.1", "credits.bundle", f"credit bundle: {len(bundle.get('publications', []))} publication fact(s), {len(bundle.get('statements', []))} statement(s), "
           f"{len(bundle.get('earliest', []))} earliest-occurrence statement(s), {len(bundle.get('anchors', []))} anchor(s); everything is input to verification, not a result")
    # §3.2 publication facts
    pubs = []
    for f in bundle.get("publications", []):
        try:
            credits.check_publication_fact(f)
        except credits.Invalid as e:
            rep.fail(f"{TDC} §3.1", "credits.fact", f"malformed publication fact: {e}")
            continue
        try:
            reads = _publication_reads(f, rpc)
        except (C.RpcError, C.NotRecorded, ValueError, KeyError) as e:
            reads = None
            why = str(e)
        else:
            why = "needs two nodes of the fact's chain (--source-rpc twice) and a known factory" if reads is None else ""
        if reads is None:
            rep.unverified(f"{TDC} §6.1", "credits.fact", credits.render_publication(f, "unverified") + f" — not verified: {why}")
            continue
        r = credits.verify_publication(f, reads)
        num = reads.get("processorNumber")
        design = _design_from_reads(reads) if r["status"] == "verified" else {"netlistHash": None, "structuralHash": None}
        pubs.append({"fact": f, "design": design, "verified": r["status"] == "verified", "number": num})
        if r["status"] == "verified":
            line = credits.render_publication(f, "verified") + f" (state block {reads['stateBlock']}, {len(reads['receipt'])} nodes)"
            if design["structuralHash"]:
                line += f"; design: netlist {short(design['netlistHash'])}, structural {short(design['structuralHash'])}"
            codes = set(reads.get("publisherCode", {}).values())
            if codes and codes != {"0x"}:
                line += "; the first publisher had contract code at the block read (relayer or wallet contract?)"
            rep.ok(f"{TDC} §6.1", "credits.fact", line)
        else:
            rep.unverified(f"{TDC} §6.1", "credits.fact", credits.render_publication(f, r["status"]) + f" ({r.get('error', '')} {r.get('detail', '')})".rstrip())
    # §4 statements
    envs = bundle.get("statements", [])
    results = [credits.verify_statement(e, _erc1271_reader(rpc), _container_resolver(rpc)) for e in envs]
    for e, r in zip(envs, results):
        if r["status"] != "valid":
            continue
        m = e["message"]
        if file_design and "subject" in m and credits.consistent_with_file(m["subject"], file_design) is False:
            r.update(status="invalid", error="subject-structural-hash-mismatch")
        if e["type"] == "Credit" and m["source"]["chainId"] != 0:
            match = [p for p in pubs if p["verified"] and (p["fact"]["chainId"], p["fact"]["processor"], p["fact"]["circuitId"]) ==
                     (m["source"]["chainId"], m["source"]["processor"], m["source"]["circuitId"])]
            if match and not credits.applies(m["subject"], match[0]["design"]):
                r.update(status="invalid", error="subject-does-not-apply-to-source")
            elif not match:
                r["sourceUnread"] = True
    entries = credits.apply_revocations(results, envs)
    anchors = {}
    for a in bundle.get("anchors", []):
        rep.unverified(f"{TDC} §5.2", "credits.anchor", f"anchor on chain {a.get('chainId')} tx {a.get('txHash')} log {a.get('logIndex')}: not read by this tool; anchored claims are ordered as unanchored")
    verified_pubs = [{"fact": p["fact"], "design": p["design"]} for p in pubs if p["verified"]]
    active_credits = [e for e in entries if e["state"] == "active" and e["type"] == "Credit"]
    order = credits.credit_order(active_credits, verified_pubs, anchors, _erc1271_reader(rpc))
    by_role = {}
    for o in order:
        by_role[o["role"]] = by_role.get(o["role"], 0) + 1
    if order:
        rep.info(f"{TDC} §6.4", "credits.claims", "active Credit claims per role: " + ", ".join(f"{r} {n}" for r, n in by_role.items()) +
                 "; no claim is selected as the designer; the order among unanchored claims is not precedence")
    by_digest = {e["digest"]: e for e in entries}
    for o in order:
        e = by_digest[o["digest"]]
        m = e["envelope"]["message"]
        kind = "exact file (netlistHash)" if m["subject"]["netlistHash"] != ZERO32 else "every file with this structure (structuralHash)"
        line = credits.render_credit(o, m.get("displayName", "")) + f"; names {kind}"
        if e["result"].get("sourceUnread"):
            line += "; declared source not read (not checked against the subject)"
        rep.info(f"{TDC} §6.2", "credits.claim", line)
    for e in entries:
        m = e["envelope"]["message"]
        if e["type"] == "Lineage" and e["state"] == "active":
            rep.info(f"{TDC} §6.2", "credits.claim", f"[claim] {m['relation']}: subject {short(m['subject']['netlistHash'])}/{short(m['subject']['structuralHash'])} → "
                     f"object {short(m['object']['netlistHash'])}/{short(m['object']['structuralHash'])}, claimed by {m['signer']}" +
                     (f" (contract on chain {m['signerChainId']})" if m["signerChainId"] else "") + ("; same function remains a claim" if m["relation"] == "optimizes" else ""))
        elif e["state"] == "revoked":
            rep.info(f"{TDC} §4.7", "credits.revoked", f"[revoked] {e['type']} {short(e['digest'])} by {m['signer']}: not active; display name and note withheld (§6.7)")
        elif e["state"] in ("invalid",):
            rep.fail(f"{TDC} §4.6", "credits.invalid", f"invalid {e['type'] or 'statement'} ({e['result'].get('error')}): not displayed")
        elif e["state"] == "unverified":
            rep.unverified(f"{TDC} §4.6", "credits.unverified", f"{e['type']} {short(e['digest'] or '')} by {m.get('signer')} unverified ({e['result'].get('error') or e.get('reason')}): not shown as valid")
    # §3.4 earliest-occurrence statements
    for s in bundle.get("earliest", []):
        occ = s.get("occurrence", {}) if isinstance(s, dict) else {}
        mine = [p for p in pubs if (p["fact"]["chainId"], p["fact"]["processor"], p["fact"]["circuitId"]) == (occ.get("chainId"), occ.get("processor"), occ.get("circuitId"))]
        ok = bool(mine and mine[0]["verified"])
        design = mine[0]["design"] if mine else {"netlistHash": None, "structuralHash": None}
        others = [(p["fact"], p["verified"], p["design"], p["number"]) for p in pubs if not mine or p is not mine[0]]
        j = credits.judge_earliest(s, ok, design, others, mine[0]["number"] if mine else None)
        text = credits.render_earliest(s, j)
        if j["status"] == "standing":
            tied = j.get("tiedWith") or []
            rep.info(f"{TDC} §6.3", "credits.earliest", text + (f"; tied with {len(tied)} other(s)" if tied else "") +
                     (f"; indexer: {s['indexer']}" if s.get("indexer") else "") + " — the earliest KNOWN occurrence, not the origin of the design")
        elif j["status"] == "invalid":
            rep.fail(f"{TDC} §3.4", "credits.earliest", f"{text} ({j.get('error')})")
        else:
            rep.warn(f"{TDC} §3.4", "credits.earliest", text + " — the earlier occurrence is displayed instead")


# ---------------------------------------------------------------- soulbound credentials (TAP-SB)

def check_credential(rpc: C.Rpc, cid: int, contract: str, token_id: int, doc: dict | None, lvl: dict, args, rep: Report) -> None:
    f = lvl.get("ifaces") or {}
    if not f.get("ITapCredential"):
        rep.fail(f"{TSB} §3.1", "credential.contract", "the contract does not report ITapCredential through ERC-165")
        return
    missing = [n for n in ("ERC721", "ERC5192", "ERC165") if not f.get(n)]
    if missing:
        rep.fail(f"{TSB} §3.1", "credential.contract", f"a credential contract MUST report {', '.join(missing)}")
    if f.get("ERC4906"):
        rep.fail(f"{TSB} §3.2", "credential.contract", "a credential contract MUST NOT report ERC-4906")
    if f.get("ITapNetlistNFT"):
        rep.warn(f"{TSB} §3.2", "credential.contract", "ITapNetlistNFT reported: allowed only if the mint-bound profile is implemented in full; a credential is never shown as L1")
    kinds = probe_interfaces(rpc, cid, contract, ["ITapCredentialProven", "ITapCredentialAttested", "ITapCredentialClaimed"])
    rep.info(f"{TSB} §8.5", "credential.contract", f"credential contract {contract} on chain {cid}; kind interfaces: " + (", ".join(k[14:].lower() for k, v in kinds.items() if v) or "none"))
    code_ok = False
    known = getattr(args, "known_code_hash", None)
    if known:
        try:
            got = hx(keccak256(bytes.fromhex(rpc.get_code(cid, contract)[2:])))
            code_ok = got == known.lower()
            (rep.ok if code_ok else rep.fail)(f"{TSB} §10.1", "credential.code", f"runtime code keccak {got} {'equals' if code_ok else 'differs from'} the known build {known}")
        except (C.RpcError, C.NotRecorded) as e:
            rep.skip(f"{TSB} §10.1", "credential.code", f"code not read: {e}")
    try:
        rec = rpc.call_decode(cid, contract, "credentialOf(uint256)", (token_id,), CRED_TYPES)
        status = rpc.call_decode(cid, contract, "statusOf(uint256)", (token_id,), "uint8")
    except (C.RpcError, C.NotRecorded) as e:
        try:
            status = rpc.call_decode(cid, contract, "statusOf(uint256)", (token_id,), "uint8")
        except (C.RpcError, C.NotRecorded):
            status = None
        if status == 0:
            rep.info(f"{TSB} §3.5", "credential.status", "status none: the token does not exist (never minted, or renounced); credentialOf reverts")
        else:
            rep.fail(f"{TSB} §8.1", "credential.record", f"credentialOf({token_id}) failed: {e}")
        return
    onchain = {"kind": rec[0], "subject": rec[1], "issuer": rec[2], "scope": rec[3], "artifact": rec[4], "evidence": rec[5],
               "issuedAt": rec[6], "expiresAt": rec[7], "replaces": rec[8]}
    kind = soulbound.KINDS.get(rec[0], f"unknown({rec[0]})")
    subject = soulbound.SUBJECTS.get(rec[1], f"unknown({rec[1]})")
    st_name = soulbound.STATUSES[status] if status is not None and 0 <= status < len(soulbound.STATUSES) else f"reserved({status})"
    try:
        nh = rpc.call_decode(cid, contract, "netlistHashOf(uint256)", (token_id,), "bytes32")
    except (C.RpcError, C.NotRecorded):
        nh = None
    try:
        locked = rpc.call_decode(cid, contract, "locked(uint256)", (token_id,), "bool")
        (rep.ok if locked else rep.fail)(f"{TSB} §3.1", "credential.locked", "locked(tokenId) is true (ERC-5192)" if locked else "locked(tokenId) is false: not soulbound")
    except (C.RpcError, C.NotRecorded):
        rep.skip(f"{TSB} §3.1", "credential.locked", "locked(tokenId) not read")
    # metadata against the record (§9)
    if doc is not None:
        try:
            c = soulbound.check_credential_metadata(doc, onchain)
            rep.ok(f"{TSB} §9", "credential.metadata", "tap.credential follows §9 and equals the on-chain record (no status, no entitlement names)")
        except soulbound.Reject as e:
            rep.fail(f"{TSB} §9", "credential.metadata", f"credential metadata rejected: {e}")
            c = (doc.get("tap") or {}).get("credential") if isinstance(doc.get("tap"), dict) else None
            c = c if isinstance(c, dict) else None
    else:
        c = None
    # §10.1: kind label, status, non-entitlement, level
    rechecked = False
    spec = None
    if kind == "proven":
        try:
            sp = rpc.call_decode(cid, contract, "specOf(bytes32)", (rec[3],), [SPEC_TYPES, "uint256", "uint256"])
            spec = dict(zip(soulbound.SPEC_FIELDS, sp[0]))
        except (C.RpcError, C.NotRecorded, ValueError):
            spec = None
        art = getattr(args, "artifact", None)
        if spec and art:
            try:
                data = fetch_bytes(art, rpc.offline)
                if hx(sha256(data)) != rec[4]:
                    rep.fail(f"{TSB} §10.2", "credential.recheck", "the artifact file does not hash to the record's artifact")
                else:
                    soulbound.check_submission(spec, data)
                    rechecked = True
                    rep.ok(f"{TSB} §10.2", "credential.recheck", "artifact re-checked against specOf(scope): pins, gate bound and truth table pass (§4.6 items 4–6)")
            except soulbound.Reject as e:
                rep.fail(f"{TSB} §10.2", "credential.recheck", f"artifact does NOT pass its specification: {e}")
            except (IOError, OSError) as e:
                rep.skip(f"{TSB} §10.2", "credential.recheck", f"artifact not read: {e}")
    label = soulbound.display_label(kind, rechecked, st_name) if kind in soulbound.KINDS.values() else f"unknown kind {rec[0]}"
    if kind == "attested":
        label = f"Attested by {rec[2]} (issuer identity not verified)" + ("" if st_name == "active" else f" [{st_name}]")
    if not code_ok:
        label += " — unverified contract"
    rep.info(f"{TSB} §10.1", "credential.kind", f"{label}; subject {subject}; contract {contract} on chain {cid}")
    if st_name == "active":
        rep.ok(f"{TSB} §10.1", "credential.status", "status active (read from the contract at the pinned block)")
    else:
        rep.warn(f"{TSB} §10.1", "credential.status", f"status {st_name}: not shown as active")
        if st_name == "superseded":
            _rebound_link(rpc, cid, contract, token_id, rep)
    if rec[8]:
        rep.info(f"{TSB} §3.8", "credential.replaces", f"replaces token {rec[8]} (rebind or re-issue); that token is superseded")
    if rec[7]:
        rep.info(f"{TSB} §10.3", "credential.expires", f"expiresAt {rec[7]} (Unix seconds)")
    rep.info(f"{TSB} §10.1", "credential.notice", "a credential is not an entitlement to any payment or allocation (§2); credentials of different kinds are never added up or ranked (item 3)")
    if kind == "proven":
        if spec:
            rep.info(f"{TSB} §10.2", "credential.spec", f"specification {rec[3]} defined by registrant {spec['registrant']}: nIn {spec['nIn']}, nOut {spec['nOut']}, maxGates {spec['maxGates']}, "
                     f"unique {str(spec['unique']).lower()}; infoHash {spec['infoHash']}")
        rep.info(f"{TSB} §10.2", "credential.notice", "a proven credential does not prove who designed the netlist (the recipient revealed a file that passed); "
                 "a unique specification does not prove an original design")
    elif kind == "attested":
        if c and c.get("issuerName"):
            rep.info(f"{TSB} §10.3", "credential.issuerName", f"issuer name \"{c['issuerName']}\" (self-declared by the producer, shown next to {rec[2]}, not verified)")
        if c and c.get("scopeLabel"):
            rep.info(f"{TSB} §10.3", "credential.scopeLabel", f"scope label \"{c['scopeLabel']}\" (self-declared; hashes to the scope)")
    elif kind == "claimed":
        _claimed_statement(rpc, cid, contract, token_id, rec, c, args, rep)
    if subject == "agent":
        rep.info(f"{TSB} §10.5", "credential.agent", "subject agent: the holder is the operating account of a software agent" +
                 (f"; registry {c['agent']['registry']} id {c['agent']['agentId']} (link not verified)" if c and c.get("agent") else ""))
    # §10.1 item 5: level line for a credential
    lvl_line = "L0 (metadata only)" + ("" if code_ok else "; metadata can change")
    if nh is not None and doc is not None and isinstance(doc.get("tap", {}).get("netlist"), dict):
        if nh == doc["tap"]["netlist"].get("sha256"):
            lvl_line += "; artifact recorded by the credential contract (netlistHashOf equals tap.netlist.sha256)"
        else:
            rep.fail(f"{TSB} §10.1", "credential.artifact", f"netlistHashOf() = {nh} differs from tap.netlist.sha256")
    rep.info(f"{TSB} §10.1", "credential.level", lvl_line + "; never L1, never \"verified on chain\" in the sense of TAP-721 §7.4")


def _rebound_link(rpc: C.Rpc, cid: int, contract: str, token_id: int, rep: Report) -> None:
    topic = hx(keccak256(b"CredentialRebound(uint256,uint256)"))
    try:
        logs = rpc.get_logs(cid, contract, [topic, hx(token_id.to_bytes(32, "big"))], 0, rpc.pinned_block(cid))
    except (C.RpcError, C.NotRecorded):
        rep.skip(f"{TSB} §10.1", "credential.replacement", "replacement not looked up (eth_getLogs failed or not recorded)")
        return
    if logs:
        rep.info(f"{TSB} §10.1", "credential.replacement", f"superseded by token {int(logs[-1]['topics'][2], 16)} (CredentialRebound)")
    else:
        rep.skip(f"{TSB} §10.1", "credential.replacement", "no CredentialRebound log found in the range read")


def _claimed_statement(rpc: C.Rpc, cid: int, contract: str, token_id: int, rec, c, args, rep: Report) -> None:
    st = (c or {}).get("statement")
    if not st:
        rep.info(f"{TSB} §10.4", "credential.statement", "Self-claimed without a Design Credits statement (scope zero)" if rec[3] == ZERO32 else "Self-claimed; the statement behind the claim scope is not named in the metadata")
        return
    src = getattr(args, "statement", None)
    env = None
    if src:
        env = json.loads(fetch_bytes(src, rpc.offline))
    elif not rpc.offline:
        for u in st.get("uris", []):
            try:
                env = json.loads(fetch_bytes(u, False))
                break
            except (IOError, OSError, ValueError):
                continue
    if env is None:
        rep.unverified(f"{TSB} §10.4", "credential.statement", f"Self-claimed; statement {short(st['id'])} not fetched (pass --statement): shown as a claim only")
        return
    r = credits.verify_statement(env, _erc1271_reader(rpc), _container_resolver(rpc))
    if r["status"] != "valid":
        rep.unverified(f"{TSB} §10.4", "credential.statement", f"statement {r['status']} ({r.get('error')}): not displayed as valid")
        return
    if r["digest"] != st["id"]:
        rep.fail(f"{TSB} §10.4", "credential.statement", "the fetched envelope is not the statement named in the metadata")
        return
    try:
        holder = rpc.call_decode(cid, contract, "ownerOf(uint256)", (token_id,), "address")
    except (C.RpcError, C.NotRecorded):
        holder = None
    art = {"netlistHash": rec[4], "structuralHash": None}
    nf = getattr(args, "artifact", None)
    if nf:
        try:
            data = fetch_bytes(nf, rpc.offline)
            if hx(sha256(data)) == rec[4]:
                art["structuralHash"] = hx(canon.structural_hash(data))
        except (IOError, OSError, tapnft.Invalid):
            pass
    disp = soulbound.statement_display(env["message"], holder, cid, art, revoked=False)
    m = env["message"]
    rep.info(f"{TSB} §10.4", "credential.statement", f"Self-claimed; carried statement {short(r['digest'])}: {disp} — [claim] {m.get('role') or m.get('relation')}, claimed by {m['signer']}" +
             (f", self-declared name \"{m['displayName']}\"" if m.get("displayName") else ""))


# ---------------------------------------------------------------- commands

def cmd_token(args) -> Report:
    rep = Report("token")
    rpc = build_rpc(args)
    contract = args.contract.lower() if args.contract else None
    token_id = args.id
    cid = args.chain_id
    try:
        if cid is None and not rpc.offline and contract and rpc.nodes:
            cid = sorted(rpc.nodes)[0] if len(rpc.nodes) == 1 or not args.source_rpc else int(C.Rpc(nodes={0: [args.rpc[0]]}).request(0, "eth_chainId", []), 16)
        doc = load_metadata(args, rpc, cid, contract, token_id, rep)
    except Stop as e:
        rep.fail(f"{T721} §7.4", "metadata", str(e))
        return rep
    except (C.RpcError, C.NotRecorded, IOError, OSError) as e:
        rep.fail(f"{T721} §7.4", "metadata", f"metadata not loaded: {e}")
        return rep
    tap = check_metadata_doc(doc, rep)
    tid = parse_token_id((tap or doc.get("tap", {}) or {}).get("id")) if isinstance(doc.get("tap"), dict) else None
    if tid:
        if cid is None:
            cid = tid[0]
        if contract is None:
            contract = tid[1]
        if token_id is None:
            token_id = tid[2]
    lvl = detect_level(rpc, cid, contract, tap, rep)
    if tap is None:
        return rep
    if tid and (tid[0], tid[1], tid[2]) != (cid, contract, token_id):
        if lvl["mirror"]:
            rep.info(f"{TBR} §5.3", "token.id", f"tap.id names the home token {tid[1]}/{tid[2]} on chain {tid[0]}; this contract is a bridged copy")
        else:
            rep.fail(f"{T721} §4.1", "token.id", f"tap.id {tap['id']} is not the token asked for (chain {cid}, {contract}, id {token_id})")
    rep.result.update(chainId=cid, contract=contract, tokenId=token_id, level=lvl["level"], manifest="manifest" in tap, state=tap["state"])
    # netlist file
    data = None
    if args.netlist:
        data = fetch_bytes(args.netlist, rpc.offline)
    elif "netlist" in tap and not rpc.offline:
        for u in tap["netlist"]["uris"]:
            try:
                data = fetch_bytes(u, False)
                break
            except (IOError, OSError):
                continue
    nres = check_netlist_file(tap, data, rep)
    rep.result["netlist"] = nres["status"]
    source = check_source(tap, rpc, rep)
    l1 = {}
    if lvl["level"] == "L1":
        l1 = check_l1(rpc, cid, lvl, tap, token_id, rep)
    if lvl["credential"]:
        check_credential(rpc, cid, contract, token_id, doc, lvl, args, rep)
    man = check_manifest_file(args, tap, l1, rpc, token_id, rep)
    # collection-level rules first (§7.1 manifest consistency, §5.1 freeze probes, §6.4 editions), so that a
    # collection whose tokens name different probes gets no freeze reported below
    if args.collection_dir:
        if "manifest" in tap:
            sha = (l1 or {}).get("manifestHash") if (l1 or {}).get("manifestHash", ZERO32) != ZERO32 else tap["manifest"]["sha256"]
        else:
            sha = None
        check_collection_dir(args.collection_dir, tap, sha, rep)
    if lvl["level"] != "L1" and not lvl["credential"]:
        if "manifest" in tap:
            if man and man.get("freeze"):
                freeze_probe(rpc, man["freeze"], "manifest.freeze", rep)
            elif man:
                rep.info(f"{T721} §7.2", "frozen", "the manifest names no freeze probe: the frozen state cannot be derived (tap.freeze is ignored next to a manifest)")
            else:
                rep.skip(f"{T721} §7.2", "frozen", "frozen state not derived: the manifest (and its freeze probe) was not fetched")
        elif "freeze" in tap:
            if rep.has("collection.freeze", "fail"):
                rep.skip(f"{T721} §5.1", "frozen", "no freeze reported: the collection's tokens name different tap.freeze probes, or only some name one")
            else:
                freeze_probe(rpc, tap["freeze"], "tap.freeze", rep)
        else:
            rep.info(f"{T721} §7.2", "frozen", "no freeze probe named: the frozen state cannot be derived; content not committed")
    # editions
    if "manifest" not in tap:
        if not args.collection_dir:
            rep.info(f"{T721} §6.4", "edition.check", "no editions: a collection without a manifest forms none (tap.edition absent)")
    elif nres["status"] == "unverifiable":
        rep.unverifiable(f"{T721} §2.5", "edition.check", "edition check unverifiable for this token's format")
    elif not args.collection_dir:
        rep.skip(f"{T721} §7.3", "edition.check", "collection-level edition check not run (needs every token's metadata: --collection-dir)")
    check_pod(tap, man, source, rpc, lvl, cid, contract, token_id, rep)
    check_bridge(tap, rpc, rep)
    if "credits" in tap:
        check_credits(tap["credits"], False, rpc, rep, nres.get("design"))
    if nres["status"] == "verified" and not rep.failed:
        rep.ok(f"{T721} §7.4", "verdict", f"checked netlist-bound NFT at {lvl['level']}" + ("; not shown as verified on chain (L0)" if lvl["level"] == "L0" else ""))
    elif nres["status"] == "unverifiable":
        rep.unverifiable(f"{T721} §2.5", "verdict", "not shown as a checked netlist-bound NFT: the netlist is unverifiable by this tool")
    elif nres["status"] == "none" and tap["state"] == "unrevealed" and not rep.failed:
        rep.info(f"{T721} §7.2", "verdict", "unrevealed token: nothing to check yet beyond the metadata and the manifest")
    elif not rep.failed:
        rep.skip(f"{T721} §7.4", "verdict", "not shown as a checked netlist-bound NFT: the netlist file was not checked")
    return rep


def cmd_metadata(args) -> Report:
    rep = Report("metadata")
    with open(args.file, "rb") as f:
        raw = f.read()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        rep.fail(f"{T721} §7.1", "metadata", f"not UTF-8 JSON: {e}")
        return rep
    rep.info(f"{T721} §7.1", "metadata.source", f"{args.file} ({len(raw)} bytes); offline checks only: no conformance level is detected and no state is read")
    tap = check_metadata_doc(doc, rep)
    if tap is None:
        return rep
    rep.result.update(manifest="manifest" in tap, state=tap["state"])
    rpc = C.Rpc(fixture={"chains": {}})  # nothing is read
    data = fetch_bytes(args.netlist, True) if args.netlist else None
    nres = check_netlist_file(tap, data, rep)
    man = None
    if "manifest" in tap and args.manifest:
        man = check_manifest_file(args, tap, {}, rpc, parse_token_id(tap["id"])[2], rep)
    if "manifest" not in tap:
        rep.info(f"{T721} §8.1", "level", "L0 (metadata only), no manifest: content not committed — the level shown without a chain read is the metadata-only level")
        rep.info(f"{T721} §6.4", "edition.check", "no editions: a collection without a manifest forms none")
    else:
        rep.info(f"{T721} §8", "level", "level not detected offline (ERC-165 needs the chain); an L0 token is never shown as verified on chain")
    if args.collection_dir and "manifest" in tap:
        check_collection_dir(args.collection_dir, tap, tap["manifest"]["sha256"], rep)
    elif args.collection_dir:
        check_collection_dir(args.collection_dir, tap, None, rep)
    check_pod(tap, man, {"confirmed": None}, rpc, {"ifaces": {}}, None, None, None, rep)
    if "credits" in tap:
        check_credits(tap["credits"], False, rpc, rep, nres.get("design"))
    if "credential" in tap:
        try:
            c = soulbound.check_credential_metadata(doc)
            rep.ok(f"{TSB} §9", "credential.metadata", f"tap.credential follows §9 (kind {c['kind']}, subject {c['subject']}); the record and the status are read from the contract (not here)")
            rep.info(f"{TSB} §10.1", "credential.kind", soulbound.display_label(c["kind"]) + " — unverified contract (offline: kind as declared by the metadata, status unknown)")
        except soulbound.Reject as e:
            rep.fail(f"{TSB} §9", "credential.metadata", f"credential metadata rejected: {e}")
    return rep


def cmd_bundle(args) -> Report:
    rep = Report("bundle")
    rpc = build_rpc(args)
    with open(args.file, "rb") as f:
        raw = f.read()
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        rep.fail(f"{TDC} §5.1", "credits.bundle", f"not UTF-8 JSON: {e}")
        return rep
    check_credits(bundle, True, rpc, rep, None)
    return rep


def cmd_credential(args) -> Report:
    rep = Report("credential")
    rpc = build_rpc(args)
    contract = args.contract.lower()
    cid = args.chain_id
    if cid is None:
        if rpc.offline:
            rep.fail(f"{TSB} §10.1", "credential.contract", "--chain-id is required offline")
            return rep
        cid = sorted(rpc.nodes)[0]
    doc = None
    if args.metadata:
        try:
            doc = load_metadata(args, rpc, cid, contract, args.id, rep)
            check_metadata_doc(doc, rep)
        except (Stop, IOError, OSError) as e:
            rep.fail(f"{T721} §7.1", "metadata", f"metadata not loaded: {e}")
            doc = None
    lvl = detect_level(rpc, cid, contract, doc.get("tap") if doc else None, rep)
    check_credential(rpc, cid, contract, args.id, doc, lvl, args, rep)
    return rep


def run_argv(argv) -> Report:
    """Parse a command line and return its Report (used by the tests)."""
    args = parser().parse_args(argv)
    return args.fn(args)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tapfam", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, chain=True):
        p.add_argument("--json", action="store_true", help="JSON report instead of text")
        if chain:
            p.add_argument("--rpc", action="append", help="JSON-RPC URL of the collection's chain (repeatable)")
            p.add_argument("--source-rpc", action="append", help="JSON-RPC URL of a source chain, twice for two nodes (repeatable)")
            p.add_argument("--offline", action="store_true", help="answer every chain read from the recorded fixture")
            p.add_argument("--fixture", help="fixture file for --offline (default fixtures/recorded-rpc.json)")
            p.add_argument("--chain-id", type=int, help="chain id of the collection (default: eth_chainId of --rpc, or tap.id)")

    t = sub.add_parser("token", help="full report of one token")
    common(t)
    t.add_argument("--contract", help="collection address")
    t.add_argument("--id", type=int, help="token id")
    t.add_argument("--metadata", help="metadata file or URL (default: tokenURI)")
    t.add_argument("--netlist", help="netlist file (default: fetched from tap.netlist.uris online)")
    t.add_argument("--manifest", help="manifest file or URL (default: fetched from tap.manifest.uris online)")
    t.add_argument("--token-set", help="token set file (set mode)")
    t.add_argument("--collection-dir", help="directory with every token's metadata, for the collection-level checks")
    t.add_argument("--master-seed", help="master seed of an L0 collection (0x + 64 hex), for the assignment")
    t.add_argument("--artifact", help="(credential contracts) the artifact file, to re-check a proven credential")
    t.add_argument("--statement", help="(credential contracts) the envelope of a claimed credential's statement")
    t.add_argument("--known-code-hash", help="(credential contracts) keccak-256 of a known runtime code build")
    t.set_defaults(fn=cmd_token)

    m = sub.add_parser("metadata", help="offline checks of one metadata file")
    common(m, chain=False)
    m.add_argument("file")
    m.add_argument("--netlist")
    m.add_argument("--manifest")
    m.add_argument("--token-set")
    m.add_argument("--master-seed")
    m.add_argument("--collection-dir")
    m.set_defaults(fn=cmd_metadata)

    b = sub.add_parser("bundle", help="a standalone credit bundle file")
    common(b)
    b.add_argument("file")
    b.set_defaults(fn=cmd_bundle)

    c = sub.add_parser("credential", help="a soulbound credential")
    common(c)
    c.add_argument("--contract", required=True)
    c.add_argument("--id", type=int, required=True)
    c.add_argument("--metadata")
    c.add_argument("--artifact")
    c.add_argument("--statement")
    c.add_argument("--known-code-hash")
    c.set_defaults(fn=cmd_credential)
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    rep = args.fn(args)
    print(rep.dumps(args.json))
    return 1 if rep.failed else 0


if __name__ == "__main__":
    sys.exit(main())
