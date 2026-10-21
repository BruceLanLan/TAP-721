#!/usr/bin/env python3
"""Record the read-only chain reads behind the worked example of the draft
"Design Credits and Lineage for TapeOut Netlists" into chain-reads.json.

MIT licence. Standard library only (plus credits.py for keccak-256 and one test-key
signature). Read-only: eth_call, eth_getLogs, eth_getTransactionByHash,
eth_getTransactionReceipt, eth_getBlockByNumber, eth_getCode. No transaction is ever sent.

    python3 fetch_reads.py            # writes chain-reads.json next to this file

Pinning. Every state read (eth_call, eth_getCode) on BNB Smart Chain is made at ONE block:
the lower of the `finalized` blocks (the chain's finality tag, TAP-10 §2.1) reported by the
two public nodes below at the start of the run. Public BSC nodes keep state for only about
a hundred blocks, so the pinned state reads are made first, immediately after pinning, on
both public nodes (two operators); the archive node (tapeout.net/rpc, a third operator) is
asked the same calls at the same block. Receipts, transactions and block headers are
immutable and are read afterwards from three public nodes and compared. The archive node
alone is used for eth_getLogs and for the historical nextId() observations.
scan_occurrences.py later reads every circuit at the same pinned block (archive node only,
because the public nodes no longer serve that block's state by then).

X Layer reads (the container example of the Rationale) are pinned to the lower of the
`safe` blocks reported by two operators (drpc and OKX) and made on both.
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import credits

ARCHIVE = "https://tapeout.net/rpc"
NODES = [
    "https://bsc-dataseed.bnbchain.org",
    "https://bsc-dataseed1.defibit.io",
    "https://bsc-dataseed1.ninicoin.io",
]
FACTORY = "0x68224f668083c29e9800be2a646d42d18cedf7e2"
CIRCUIT_BEACON = "0xf8d6d8eb894d6971c8976ad8b4971cbefe028156"
MINING = "0x7e2e0dc66a3bd9103e69b766afa62d9f7b697b46"

XL_NODES = ["https://xlayer.drpc.org", "https://rpc.xlayer.tech"]  # drpc, OKX: two operators
XL_FACTORY = "0x1f09daefa827f02cbb40967cc91b259763760761"
XL_CIRCUIT_BEACON = "0xf70d1ed4f62cf3780157b0b421b7e2f45bd0991c"
XL_OPENER = "0x536add8f30f03b69f6fbf29d425a816a0dc50106"
XL_CONTAINER_IMPL = "0xac4f791353ee9f06e2c50ae4c34680d28ea52a57"  # TAP-10 Deployments
XL_EXAMPLE = (282, 1)  # processor 282 "testBlonskr", circuit #1: 1.2.282.tape

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
TAPED_OUT = "0xc11215e417669c143c8a07aeb778034c0a0a85ebdf305d64a629b19a7a9ce031"

CIRCUITS = [
    # (label, processor, processor number, circuit id, creation tx found by the search in README)
    ("17851.30", "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", 30, 17851,
     "0x0d2638af463201264353140faa4b9740bfb92dae626ca1d4dedcf2b7010b3c18"),
    ("3.635", "0xf4412c52ec3ddf7caf5f518b6662f77b02bde28e", 635, 3,
     "0xeeaba590bdd88a8da2ed6aa28dd2bf260f7f431479e69addd4ba6265c881a72c"),
    # earliest known circuit with this netlist hash in processors {30, 635} (scan_occurrences.py)
    ("906.30", "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", 30, 906,
     "0x7ac6baada39c8a5d45dc269c02b1c998a4c9098a880e38d9c56f8c99b35c0cef"),
    # a renumbered variant: different netlist hash, same structural hash
    ("1045.30", "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", 30, 1045,
     "0x7e1169b907a5137267ed03f438646b6f447b361d13aeaa8392616581be66c9d1"),
]
SCANNED = [(30, "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c"), (635, "0xf4412c52ec3ddf7caf5f518b6662f77b02bde28e")]

# Candidate signatures used to name selectors found in the circuit implementations' bytecode.
# A selector is named only when keccak256 of one of these signatures reproduces it.
CANDIDATES = [
    # ERC-721 / ERC-165 / metadata / enumerable
    "balanceOf(address)", "ownerOf(uint256)", "safeTransferFrom(address,address,uint256)",
    "safeTransferFrom(address,address,uint256,bytes)", "transferFrom(address,address,uint256)",
    "approve(address,uint256)", "setApprovalForAll(address,bool)", "getApproved(uint256)",
    "isApprovedForAll(address,address)", "supportsInterface(bytes4)", "name()", "symbol()",
    "tokenURI(uint256)", "totalSupply()", "tokenByIndex(uint256)", "tokenOfOwnerByIndex(address,uint256)",
    # TAP-02 §6
    "nextId()", "circuitInfo(uint256)", "netlist(uint256)", "eval(uint256,bytes)", "step(uint256,bytes,bytes)",
    "beat(address,uint256,bytes)", "tapeout(bytes,uint32,uint32)", "TAPEOUT_FEE()",
    # common administration / initialisation / minting names
    "initialize()", "initialize(string,string)", "initialize(address)", "initialize(string,string,address)",
    "owner()", "transferOwnership(address)", "renounceOwnership()", "mint(address,uint256)", "mint(address)",
    "safeMint(address,uint256)", "safeMint(address)", "mintTo(address)", "burn(uint256)", "factory()",
    "transistor()", "nand()", "latch()", "setBaseURI(string)", "baseURI()", "contractURI()",
    # names found for the remaining selectors in public signature databases (4byte.directory,
    # openchain.xyz) on 2026-10-19; listed here so that the preimage is recomputed locally
    "TREASURY()", "transistorsContract()", "transistors()", "initialize(string,string,address,address)", "sweepFees()",
]


def rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if "error" in out:
        raise RuntimeError(f"{url} {method}: {out['error']}")
    return out["result"]


def try_call(url: str, to: str, data: str, block: int) -> dict:
    """eth_call that records a revert instead of raising."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                       "params": [{"to": to, "data": data}, hex(block)]}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if "error" in out:
        msg = json.dumps(out["error"])
        if "revert" not in msg.lower():
            raise RuntimeError(f"{url} eth_call: {msg}")
        return {"reverted": True, "error": out["error"]}
    return {"reverted": False, "result": out["result"]}


def word(n: int) -> str:
    return hex(n)[2:].rjust(64, "0")


def addr_word(a: str) -> str:
    return a.lower()[2:].rjust(64, "0")


def call(url: str, to: str, data: str, block):
    return rpc(url, "eth_call", [{"to": to, "data": data}, block if isinstance(block, str) else hex(block)])


def abi_bytes(ret: str) -> str:
    raw = bytes.fromhex(ret[2:])
    off = int.from_bytes(raw[0:32], "big")
    ln = int.from_bytes(raw[off:off + 32], "big")
    return "0x" + raw[off + 32:off + 32 + ln].hex()


def slim_receipt(r: dict) -> dict:
    return {
        "status": r["status"], "blockHash": r["blockHash"], "blockNumber": r["blockNumber"],
        "transactionHash": r["transactionHash"], "transactionIndex": r["transactionIndex"],
        "from": r["from"].lower(), "to": (r["to"] or "").lower(),
        "logs": [{"address": l["address"].lower(), "topics": l["topics"], "data": l["data"],
                  "logIndex": l["logIndex"]} for l in r["logs"]],
    }


def dispatcher_selectors(code_hex: str) -> list:
    """PUSH4 x followed (directly) by EQ: the comparisons of a Solidity function dispatcher.
    Heuristic; may include a few constants compared with EQ elsewhere in the code."""
    code = bytes.fromhex(code_hex[2:])
    out, i = [], 0
    while i < len(code):
        op = code[i]
        if op == 0x63 and i + 5 < len(code) and code[i + 5] == 0x14:
            out.append("0x" + code[i + 1:i + 5].hex())
        if 0x60 <= op <= 0x7F:
            i += op - 0x5F
        i += 1
    return sorted(set(out))


def name_selectors(sels: list) -> dict:
    known = {"0x" + credits.keccak256(s.encode())[:4].hex(): s for s in CANDIDATES}
    named = {s: known[s] for s in sels if s in known}
    return {"selectors": sels, "named": named, "unnamed": [s for s in sels if s not in known],
            "method": "PUSH4 followed by EQ in the runtime bytecode; a selector is named only when keccak256 of a "
                      "candidate signature (CANDIDATES in fetch_reads.py) reproduces it"}


def pin(nodes: list, tag: str) -> dict:
    rep = {u: rpc(u, "eth_getBlockByNumber", [tag, False]) for u in nodes}
    n = min(int(b["number"], 16) for b in rep.values())
    heads = {u: rpc(u, "eth_getBlockByNumber", [hex(n), False]) for u in nodes}
    assert len({(h["hash"], h["timestamp"]) for h in heads.values()}) == 1, heads
    h = next(iter(heads.values()))
    return {"number": n, "hash": h["hash"], "timestamp": int(h["timestamp"], 16), "tag": tag,
            "reportedBy": {u: int(b["number"], 16) for u, b in rep.items()}}


def xlayer_container() -> dict:
    p = pin(XL_NODES, "safe")
    B = p["number"]
    num, cid = XL_EXAMPLE
    out = {"chainId": 196, "pinnedBlock": p, "nodes": XL_NODES, "example": "1.2.282.tape (processor 282, circuit #1)"}

    def both(to, data):
        r = {u: call(u, to, data, B) for u in XL_NODES}
        assert len(set(r.values())) == 1, (to, data, r)
        return next(iter(r.values()))

    proc = "0x" + both(XL_FACTORY, "0x4bc7cbbd" + word(num))[-40:]
    out["processor"] = proc
    cont = "0x" + both(XL_OPENER, "0x0c1905e5" + addr_word(proc) + word(cid))[-40:]  # accountOf(address,uint256)
    out["container"] = cont
    codes = {u: rpc(u, "eth_getCode", [cont, hex(B)]) for u in XL_NODES}
    assert len(set(codes.values())) == 1
    code = next(iter(codes.values()))
    out["containerCode"] = code
    # EIP-1167 minimal proxy: 363d3d373d3d3d363d73 <impl> 5af43d82803e903d91602b57fd5bf3, then ERC-6551 footer
    pre, post = "0x363d3d373d3d3d363d73", "5af43d82803e903d91602b57fd5bf3"
    assert code.startswith(pre) and code[len(pre) + 40:len(pre) + 40 + len(post)] == post
    out["containerDelegatesTo"] = "0x" + code[len(pre):len(pre) + 40]
    out["containerDelegatesToEqualsTap10Implementation"] = out["containerDelegatesTo"] == XL_CONTAINER_IMPL
    out["token()"] = both(cont, "0xfc0c546a")
    out["owner()"] = "0x" + both(cont, "0x8da5cb5b")[-40:]
    out["ownerOf(1)"] = "0x" + both(proc, "0x6352211e" + word(cid))[-40:]
    impl_code = rpc(XL_NODES[0], "eth_getCode", [XL_CONTAINER_IMPL, hex(B)])
    out["implementationCodeKeccak"] = "0x" + credits.keccak256(bytes.fromhex(impl_code[2:])).hex()
    # The implementation is a beacon proxy: the beacon address is an immutable in its bytecode,
    # loaded by PUSH32 right after `implementation()` (0x5c60da1b) is prepared.
    k = impl_code.find("7f" + "00" * 12)
    beacon = "0x" + impl_code[k + 2 + 24:k + 2 + 64]
    out["implementationIsBeaconProxy"] = {"beacon": beacon, "how": "PUSH32 immutable in the bytecode of the TAP-10 container implementation, called with implementation() = 0x5c60da1b"}
    out["beacon.implementation()"] = "0x" + both(beacon, "0x5c60da1b")[-40:]
    out["beacon.owner()"] = "0x" + both(beacon, "0x8da5cb5b")[-40:]
    # One isValidSignature call: a digest and a signature by public test key 1 (not the holder).
    d = credits.keccak256(b"tap-design-credits isValidSignature probe")
    sig = credits.sign(int.from_bytes(credits.keccak256(b"tap-design-credits test key 1"), "big"), d)
    data = "0x1626ba7e" + d.hex() + word(64) + word(65) + sig.hex() + "00" * 31
    res = {u: try_call(u, cont, data, B) for u in XL_NODES}
    assert len({json.dumps(v, sort_keys=True) for v in res.values()}) == 1, res
    out["isValidSignature"] = {"digest": "0x" + d.hex(), "signature": "0x" + sig.hex(),
                               "signedBy": credits.address_of_key(int.from_bytes(credits.keccak256(b"tap-design-credits test key 1"), "big")),
                               "calldata": data, "answer": next(iter(res.values())),
                               "note": "test key 1 is not the holder, so the container is expected to reject the signature"}
    # Circuit implementation behind the X Layer circuit beacon, and its dispatcher selectors.
    cimpl = "0x" + both(XL_CIRCUIT_BEACON, "0x5c60da1b")[-40:]
    ccode = rpc(XL_NODES[0], "eth_getCode", [cimpl, hex(B)])
    out["circuitImplementation"] = {"beacon": XL_CIRCUIT_BEACON, "implementation": cimpl,
                                    "codeKeccak": "0x" + credits.keccak256(bytes.fromhex(ccode[2:])).hex(),
                                    **name_selectors(dispatcher_selectors(ccode))}
    return out


def main() -> None:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    publishers = {}
    for label, proc, num, cid, txh in CIRCUITS:  # receipts are immutable: read before pinning
        r0 = rpc(NODES[0], "eth_getTransactionReceipt", [txh])
        mint = [l for l in r0["logs"] if l["address"].lower() == proc and l["topics"][0] == TRANSFER][0]
        publishers[label] = "0x" + mint["topics"][2][-40:]
    p = pin(NODES[:2], "finalized")
    B = p["number"]
    state_nodes = NODES[:2] + [ARCHIVE]
    out = {
        "format": "tap-design-credits-chain-reads/2",
        "chainId": 56,
        "readAt": now,
        "pinnedBlock": p,
        "stateNodes": state_nodes,
        "archiveNode": ARCHIVE,
        "nodes": NODES,
        "transactionsSent": 0,
        "factory": {"address": FACTORY},
        "circuits": [],
    }

    def par(jobs: dict) -> dict:
        """Run the pinned reads concurrently, so that they finish while the public nodes still serve block B."""
        with ThreadPoolExecutor(24) as ex:
            futs = {k: ex.submit(f) for k, f in jobs.items()}
            return {k: f.result() for k, f in futs.items()}

    jobs = {}
    for label, proc, num, cid, txh in CIRCUITS:
        for u in state_nodes:
            jobs[(label, "publisherCodeAtPinnedBlock", u)] = (lambda u=u, a=publishers[label]: rpc(u, "eth_getCode", [a, hex(B)]))
            jobs[(label, "cpuAt", u)] = (lambda u=u, n=num: "0x" + call(u, FACTORY, "0x4bc7cbbd" + word(n), B)[-40:])
            jobs[(label, "isCPU", u)] = (lambda u=u, pr=proc: int(call(u, FACTORY, "0x5f5a364f" + addr_word(pr), B), 16) == 1)
            jobs[(label, "circuitInfo", u)] = (lambda u=u, pr=proc, i=cid: call(u, pr, "0x084d60f1" + word(i), B))
            jobs[(label, "netlist", u)] = (lambda u=u, pr=proc, i=cid: abi_bytes(call(u, pr, "0x3fc4be56" + word(i), B)))
    for num, proc in SCANNED:
        for u in state_nodes:
            jobs[("scan", str(num), u)] = (lambda u=u, pr=proc: int(call(u, pr, "0x61b8ce8c", B), 16))
    for u in state_nodes:
        jobs[("cpuCount", u)] = (lambda u=u: int(call(u, FACTORY, "0xa94da8a7", B), 16))
        jobs[("beacon", u)] = (lambda u=u: "0x" + call(u, CIRCUIT_BEACON, "0x5c60da1b", B)[-40:])
    # 1. pinned state reads first (public nodes keep state for about a hundred blocks)
    res = par(jobs)
    nid = {num: {u: res[("scan", str(num), u)] for u in state_nodes} for num, _ in SCANNED}
    jobs2 = {}
    for num, proc in SCANNED:
        n = nid[num][state_nodes[0]]
        assert len(set(nid[num].values())) == 1, nid
        for u in state_nodes:
            jobs2[(num, "at", u)] = (lambda u=u, pr=proc, n=n: not try_call(u, pr, "0x084d60f1" + word(n), B)["reverted"])
            jobs2[(num, "next", u)] = (lambda u=u, pr=proc, n=n: try_call(u, pr, "0x084d60f1" + word(n + 1), B)["reverted"])
    res2 = par(jobs2)
    pinned = {label: {k: {u: res[(label, k, u)] for u in state_nodes}
                      for k in ("publisherCodeAtPinnedBlock", "cpuAt", "isCPU", "circuitInfo", "netlist")}
              for label, *_ in CIRCUITS}
    out["scannedProcessors"] = {str(num): {"processor": proc, "nextIdAtPinnedBlock": nid[num],
                                           "circuitInfo(nextId)Exists": {u: res2[(num, "at", u)] for u in state_nodes},
                                           "circuitInfo(nextId+1)Reverted": {u: res2[(num, "next", u)] for u in state_nodes}}
                                for num, proc in SCANNED}
    out["factory"]["cpuCount"] = {u: res[("cpuCount", u)] for u in state_nodes}
    impl = {u: res[("beacon", u)] for u in state_nodes}
    out["circuitBeacon"] = {"address": CIRCUIT_BEACON, "implementation()": impl}

    # 2. immutable reads and archive-only reads
    for label, proc, num, cid, txh in CIRCUITS:
        c = {"label": label, "processor": proc, "processorNumber": num, "circuitId": cid, "txHash": txh, **pinned[label]}
        receipts = {u: slim_receipt(rpc(u, "eth_getTransactionReceipt", [txh])) for u in NODES}
        c["receipt"] = receipts
        tx = rpc(NODES[0], "eth_getTransactionByHash", [txh])
        c["transaction"] = {"from": tx["from"].lower(), "to": tx["to"].lower(), "nonce": tx["nonce"],
                            "value": tx["value"], "selector": tx["input"][:10], "blockNumber": tx["blockNumber"]}
        bn = receipts[NODES[0]]["blockNumber"]
        c["block"] = {}
        for u in NODES:
            b = rpc(u, "eth_getBlockByNumber", [bn, False])
            c["block"][u] = {"number": b["number"], "hash": b["hash"], "timestamp": b["timestamp"]}
        b = int(bn, 16)
        c["archiveLogs"] = [
            {"address": l["address"].lower(), "topics": l["topics"], "data": l["data"],
             "logIndex": l["logIndex"], "transactionHash": l["transactionHash"]}
            for l in rpc(ARCHIVE, "eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(b), "address": proc,
                                                    "topics": [[TRANSFER, TAPED_OUT]]}])
        ]
        # Informative observation only: nextId() before and at the creation block (archive).
        c["nextIdObserved"] = {str(b - 1): int(call(ARCHIVE, proc, "0x61b8ce8c", b - 1), 16),
                               str(b): int(call(ARCHIVE, proc, "0x61b8ce8c", b), 16)}
        out["circuits"].append(c)

    # Selectors of the BSC circuit implementation at the pinned block (archive node).
    bimpl = next(iter(impl.values()))
    code = rpc(ARCHIVE, "eth_getCode", [bimpl, hex(B)])
    out["circuitBeacon"]["implementationCode"] = {
        "address": bimpl, "codeKeccak": "0x" + credits.keccak256(bytes.fromhex(code[2:])).hex(),
        **name_selectors(dispatcher_selectors(code))}

    # PoD miner record of 17851 (registrant only, TAP-draft-pod-attributes §3.4 position 10), at the pinned block.
    key = call(ARCHIVE, MINING, "0x10eafa00" + addr_word(CIRCUITS[0][1]) + word(CIRCUITS[0][3]), B)
    miner = call(ARCHIVE, MINING, "0x0527edc2" + key[2:], B)
    words = [miner[2 + 64 * i: 2 + 64 * (i + 1)] for i in range(22)]
    out["podMiner17851"] = {"minerKey": key, "registrant": "0x" + words[10][-40:], "taskId": int(words[2], 16),
                            "block": B}

    out["xlayerContainer"] = xlayer_container()

    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chain-reads.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("wrote", path, "pinned block", B)


if __name__ == "__main__":
    main()
