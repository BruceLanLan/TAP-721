#!/usr/bin/env python3
"""Build tokens.json + tokens.bin from owners.json (+ owner_classes.json, transfers.json if present).

tokenSetHash = SHA-256( u32be(id_1) || u32be(id_2) || ... ) over validTokenIds ascending.
tokens.bin holds exactly those bytes, so `shasum -a 256 tokens.bin` == tokenSetHash.
"""
import hashlib, json, os, struct
from scan_owners import HERE

DEAD = "0x000000000000000000000000000000000000dead"
# Black-hole set: decided from the evidence documented in README.md / blackHoleAddresses below.
BLACK_HOLES = {
    "0x000000000000000000000000000000000000dead": {
        "label": "0x...dEaD conventional burn address",
        "evidence": [
            "eth_getCode == 0x at the pinned block (no contract code, no EIP-7702 delegation)",
            "nonce 0: has never sent a transaction; no one is known to hold its private key "
            "(vanity-pattern address, would require a 2^160 preimage search)",
            "collection contract is not a proxy (EIP-1967 impl slot empty), has no DELEGATECALL/SELFDESTRUCT; "
            "its only state-changing entry points are approve/setApprovalForAll/transferFrom/safeTransferFrom/"
            "claim/setBaseURI/freezeBaseURI -- no admin transfer or burn, so tokens can leave 0xdead only "
            "via a signature from 0xdead itself",
            "eth_call simulation at the pinned block of transferFrom(0xdEaD, 0x1111..1112, 4800): reverts "
            "'NotAuthorized' from collection owner() 0xa8Edd3B032D33aA0657a3E151a7F8c3e5F71F6B9 and from a random EOA; "
            "succeeds only with from=0xdEaD",
            "getApproved(id) == 0x0 for sampled excluded ids 4692, 4800, 6000, 7785",
            "balanceOf(0xdEaD) == 3000 at the pinned block, matching the ownerOf scan",
        ],
    },
}


def main():
    d = json.load(open(os.path.join(HERE, "owners.json")))
    owners = {int(k): v for k, v in d["owners"].items()}
    holes = set(BLACK_HOLES)
    excluded = sorted(i for i, o in owners.items() if o is None or o.lower() in holes)
    valid = sorted(i for i in owners if i not in set(excluded))
    blob = b"".join(struct.pack(">I", i) for i in valid)
    h = hashlib.sha256(blob).hexdigest()
    open(os.path.join(HERE, "tokens.bin"), "wb").write(blob)

    bh = []
    tr_path = os.path.join(HERE, "transfers.json")
    transfers = json.load(open(tr_path)) if os.path.exists(tr_path) else None
    sample_path = os.path.join(HERE, "transfers_sample.json")
    sample = json.load(open(sample_path)) if os.path.exists(sample_path) else None
    for a, meta in BLACK_HOLES.items():
        e = dict(address=a, **meta, tokenCount=sum(1 for o in owners.values() if o == a))
        if transfers is not None:
            ins = [t for t in transfers if t["to"] == a]
            outs = [t for t in transfers if t["from"] == a]
            blocks = sorted({t["block"] for t in ins})
            e["transfersIn"] = len(ins)
            e["transfersOut"] = len(outs)
            e["arrivalBlocks"] = {"first": blocks[0], "last": blocks[-1], "distinctBlocks": len(blocks)} if blocks else None
            e["arrivalTxs"] = sorted({t["tx"] for t in ins})[:50]
            e["senders"] = sorted({t["from"] for t in ins})
        if transfers is None and sample is not None and a == DEAD:
            e["arrivals"] = {
                "method": "binary search of ownerOf over blocks for one id per contiguous run, then eth_getLogs "
                          "(Transfer, to=0xdEaD) over blocks 72890740..72890839 (100-block window)",
                "windowResult": "3000 Transfer logs, 3000 distinct ids, 7 txs, all from "
                                "0x70d23972688d5e079b9a2fa877142a05cac00d3d",
                "firstBlock": min(r["arrivalBlock"] for r in sample),
                "lastBlock": max(r["arrivalBlock"] for r in sample),
                "firstTimeUtc": min(r["arrivalTimeUtc"] for r in sample),
                "lastTimeUtc": max(r["arrivalTimeUtc"] for r in sample),
                "txs": sorted({x for r in sample for x in r["txs"]}),
                "senders": sorted({x for r in sample for x in r["senders"]}),
                "sample": sample,
            }
        bh.append(e)

    out = {
        "collection": d["collection"], "chainId": 196,
        "block": d["block"], "blockHash": d["blockHash"],
        "timestamp": d["timestamp"], "timestampUtc": d["timestampUtc"],
        "totalSupply": d["totalSupply"],
        "blackHoleAddresses": bh,
        "counts": {"total": len(owners), "valid": len(valid), "excluded": len(excluded)},
        "tokenSetHash": "0x" + h,
        "tokenSetHashSpec": "sha256(concat(u32be(id) for id in validTokenIds ascending)); bytes in tokens.bin",
        "validTokenIds": valid,
        "excludedTokenIds": excluded,
    }
    json.dump(out, open(os.path.join(HERE, "tokens.json"), "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("block", "blockHash", "timestampUtc", "counts", "tokenSetHash")}, indent=1))


if __name__ == "__main__":
    main()
