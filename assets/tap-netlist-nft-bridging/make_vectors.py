#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test vectors for the TAP draft "Moving Netlist-Bound NFTs between TapeOut chains".

Dependency-free (includes a Keccak-256). Writes vectors.json next to this file; the output is
byte-for-byte reproducible. Usage: python3 make_vectors.py [--check]
"""
import hashlib
import json
import os
import sys

# ---------------------------------------------------------------- Keccak-256 (original padding 0x01)

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1


def _rol(v, n):
    return ((v << n) | (v >> (64 - n))) & _M if n else v


def _f(a):
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        a = [[a[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rol(a[x][y], _ROT[x][y])
        a = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        a[0][0] ^= rc
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += b"\x00" * ((-len(msg)) % rate)
    msg[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            x, y = i % 5, i // 5
            a[x][y] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        a = _f(a)
    out = b""
    for i in range(4):
        out += a[i % 5][i // 5].to_bytes(8, "little")
    return out


assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"

# ---------------------------------------------------------------- ABI helpers


def u(n: int, bits: int = 256) -> bytes:
    assert 0 <= n < (1 << bits)
    return n.to_bytes(32, "big")


def addr(a: str) -> bytes:
    b = bytes.fromhex(a[2:])
    assert len(b) == 20
    return b


def word_addr(a: str) -> bytes:
    return b"\x00" * 12 + addr(a)


def h(b: bytes) -> str:
    return "0x" + b.hex()


def collection_key(home_chain_id: int, home_contract: str) -> bytes:
    # abi.encode("TAP-NFT collection v1", uint64 homeChainId, address homeContract)
    label = b"TAP-NFT collection v1"
    enc = u(0x60) + u(home_chain_id, 64) + word_addr(home_contract) + u(len(label)) + label.ljust(32, b"\x00")
    return keccak256(enc)


def payload(p: dict) -> bytes:
    return b"".join([
        u(1, 8),
        bytes.fromhex(p["collectionKey"][2:]),
        u(p["tokenId"]),
        word_addr(p["to"]),
        bytes.fromhex(p["netlistHash"][2:]),
        bytes.fromhex(p["imageHash"][2:]),
        bytes.fromhex(p["manifestHash"][2:]),
        u(p["srcChainId"], 64),
        u(p["dstChainId"], 64),
        u(p["nonce"], 64),
    ])


def endpoint_id(chain_id: int, a: str) -> bytes:
    return b"\x00" * 4 + chain_id.to_bytes(8, "big") + addr(a)


# ---------------------------------------------------------------- inputs (examples, not deployments)

TCT1 = "0x0e91460d6823c711643e650a9a4c0cc21de41614"  # TapeCode-Test1, X Layer (196)
GATEWAY = "0x00000000000000000000000000000000000a0196"  # example addresses
MIRROR_BSC = "0x00000000000000000000000000000000000b0056"
MIRROR_BASE = "0x00000000000000000000000000000000000c8453"
HUB = "0xe61A9C7213a6Aa616C246a2B569e555B417b25ee"  # TAP-10 DeWEB hub, every chain
HUB_ADAPTER_BSC = "0x00000000000000000000000000000000000d0056"
SRC_CONTAINER = "0x00000000000000000000000000000000000e0196"
DST_CONTAINER = "0x00000000000000000000000000000000000e0056"
TAPNET = bytes.fromhex("5441504e45540100000000020000000100000002000003")  # nIn 2, nOut 1, NAND(2,3)

key_xl = collection_key(196, TCT1)
netlist = hashlib.sha256(TAPNET).digest()
image = hashlib.sha256(b"example image").digest()
manifest = hashlib.sha256(b"example manifest").digest()
Z = "0x" + "00" * 32

cases = [
    {"name": "home-to-remote", "description": "TapeCode-Test1 #7 leaves X Layer for BNB Smart Chain",
     "srcEndpoint": GATEWAY,
     "payload": {"collectionKey": h(key_xl), "tokenId": 7, "to": "0x00000000000000000000000000000000000000b0",
                 "netlistHash": h(netlist), "imageHash": h(image), "manifestHash": h(manifest),
                 "srcChainId": 196, "dstChainId": 56, "nonce": 0}},
    {"name": "remote-to-home", "description": "the same token returns from BNB Smart Chain to X Layer",
     "srcEndpoint": MIRROR_BSC,
     "payload": {"collectionKey": h(key_xl), "tokenId": 7, "to": "0x00000000000000000000000000000000000000c0",
                 "netlistHash": h(netlist), "imageHash": h(image), "manifestHash": h(manifest),
                 "srcChainId": 56, "dstChainId": 196, "nonce": 3}},
    {"name": "remote-to-home-unbound", "description": "token #8 (no hashes bound) returns from Base to X Layer",
     "srcEndpoint": MIRROR_BASE,
     "payload": {"collectionKey": h(key_xl), "tokenId": 8, "to": "0x00000000000000000000000000000000000000d0",
                 "netlistHash": Z, "imageHash": Z, "manifestHash": Z,
                 "srcChainId": 8453, "dstChainId": 196, "nonce": 0}},
    {"name": "extremes", "description": "largest token id, nonce and chain ids the encoding allows",
     "srcEndpoint": MIRROR_BSC,
     "payload": {"collectionKey": h(key_xl), "tokenId": (1 << 256) - 1,
                 "to": "0xffffffffffffffffffffffffffffffffffffffff",
                 "netlistHash": "0x" + "ff" * 32, "imageHash": "0x" + "ff" * 32, "manifestHash": "0x" + "ff" * 32,
                 "srcChainId": (1 << 64) - 1, "dstChainId": (1 << 64) - 2, "nonce": (1 << 64) - 1}},
]

valid = []
for c in cases:
    pl = payload(c["payload"])
    assert len(pl) == 320
    mid = keccak256(addr(c["srcEndpoint"]) + pl)  # messageId = keccak256(srcEndpoint ‖ payload)
    p = dict(c["payload"])
    p["tokenId"] = str(p["tokenId"])  # decimal string: JSON numbers lose precision above 2^53
    for k in ("srcChainId", "dstChainId", "nonce"):
        p[k] = str(p[k])
    valid.append({
        "name": c["name"], "description": c["description"], "fields": p,
        "payload": h(pl), "payloadHash": h(keccak256(pl)),
        "srcEndpoint": c["srcEndpoint"], "messageId": h(mid),
        "hubRef": h(mid),
        "hubDigest": h(keccak256(mid + keccak256(pl))),
    })

base = bytes.fromhex(valid[0]["payload"][2:])


def mutate(off: int, val: bytes) -> bytes:
    b = bytearray(base)
    b[off:off + len(val)] = val
    return bytes(b)


invalid = [
    {"name": "short", "payload": h(base[:-1]), "reason": "length 319, not 320"},
    {"name": "long", "payload": h(base + b"\x00"), "reason": "length 321, not 320"},
    {"name": "version-2", "payload": h(mutate(31, b"\x02")), "reason": "version word is not 1"},
    {"name": "version-high-bits", "payload": h(mutate(0, b"\x01")), "reason": "version word not canonical"},
    {"name": "to-zero", "payload": h(mutate(0x60, b"\x00" * 32)), "reason": "`to` is zero"},
    {"name": "address-high-bits", "payload": h(mutate(0x60, b"\x01")), "reason": "`to` word has non-zero upper 96 bits"},
    {"name": "srcChainId-overflow", "payload": h(mutate(0xe0 + 23, b"\x01")), "reason": "srcChainId word exceeds uint64"},
    {"name": "dstChainId-overflow", "payload": h(mutate(0x100, b"\x80")), "reason": "dstChainId word exceeds uint64"},
    {"name": "nonce-overflow", "payload": h(mutate(0x120 + 23, b"\x01")), "reason": "nonce word exceeds uint64"},
]

# LayerZero V2 executor option: TYPE_3 (0x0003) ‖ worker 1 ‖ uint16 length 17 ‖ option 1 (lzReceive) ‖ uint128 gas
def lz_option(gas: int) -> bytes:
    return (3).to_bytes(2, "big") + b"\x01" + (17).to_bytes(2, "big") + b"\x01" + gas.to_bytes(16, "big")


# EIP-712 for the hub relay verifier
DOMAIN_T = keccak256(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
HUB_T = keccak256(b"HubMessage(uint64 srcChainId,address hub,address fromContainer,uint256 outboxIndex,bytes32 digest)")
domain = keccak256(DOMAIN_T + keccak256(b"TAP-NFT Hub Relay") + keccak256(b"1") + u(56) + word_addr(HUB_ADAPTER_BSC))
digest0 = bytes.fromhex(valid[0]["hubDigest"][2:])
struct = keccak256(HUB_T + u(196, 64) + word_addr(HUB) + word_addr(SRC_CONTAINER) + u(5) + digest0)
signing = keccak256(b"\x19\x01" + domain + struct)


# Selectors, ERC-165 interface ids (XOR of the interface's own selectors) and event topics
def sel(sig: str) -> bytes:
    return keccak256(sig.encode())[:4]


def iface(sigs):
    x = 0
    for g in sigs:
        x ^= int.from_bytes(sel(g), "big")
    return "0x" + x.to_bytes(4, "big").hex()


IFACES = {
    "ITapBridgeAdapter": ["layerId()", "quote(uint64,bytes,bytes)", "send(uint64,bytes,bytes,address)"],
    "ITapBridgeEndpoint": ["receivePayload(uint64,address,bytes)", "collectionKey()", "homeChainId()", "route(uint64)",
                           "routesSealed()"],
    "ITapBridgeTransfer": ["quoteBridge(uint256,uint64,address,bytes[])", "bridge(uint256,uint64,address,bool,bytes[])",
                           "resend(bytes,uint256,bytes)", "departed(bytes32)", "executed(bytes32)",
                           "confirmedBy(bytes32,address)", "nextNonce()", "setRoute(uint64,uint8,address[],address)",
                           "sealRoutes()"],
    "ITapBridgeMirror": ["knownNetlist(bytes32)", "manifestHash()", "materialize(bytes)"],
    "ITapBridgeAdapterSealed": ["adapterSealed()"],
}
EXTRA = [
    "lzReceive((uint32,bytes32,uint64),bytes32,bytes,address,bytes)",
    "allowInitializePath((uint32,bytes32,uint64))",
    "nextNonce(uint32,bytes32)",
    "send((uint32,bytes32,bytes,bytes,bool),address)",
    "quote((uint32,bytes32,bytes,bytes,bool),address)",
    "setDelegate(address)",
    "setPeer(uint64,uint32,bytes32,address)",
    "setCircuit(address,uint256)",
    "setRemote(uint64,address,address,address)",
    "deliver(uint64,uint256,bytes32,bytes,bytes)",
    "hubMessageHash(uint64,address,uint256,bytes32)",
    "send(address,uint256,bytes32,bytes32,bytes)",
    "outboxCount(address)",
    "seal()",
    "remoteEndpoint(uint64)",
    "locationOf(uint256)",
    "isDefaultSendLibrary(address,uint32)",
    "getReceiveLibrary(address,uint32)",
    "getAppUlnConfig(address,uint32)",
    "receiveLibraryTimeout(address,uint32)",
]
ERRORS = [
    # endpoints (TapBridgeEndpoint, TapGateway, TapMirror) and payload decoding
    "BadPayload()", "RouteClosed(uint64)", "NotAdapter(address)", "WrongPeer(address)", "WrongSource()",
    "WrongDestination()", "WrongCollection()", "Replay(bytes32)", "AlreadyConfirmed(bytes32,address)",
    "NotDeparted(bytes32)", "ZeroRecipient()", "ContractRecipient(address)", "EndpointRecipient(address)",
    "BadOptions()", "InsufficientFee(uint256,uint256)", "RefundFailed()", "BadRoute()", "Sealed()", "NotOwner()",
    "AdapterNotSealed(address)", "Reentrancy()",
    "NotAuthorized()", "AlreadyEscrowed(uint256)", "NotEscrowed(uint256)", "NotOnRoute(uint256,uint64)", "EscrowFailed(uint256)", "NotBound(uint256)",
    "WrongDataSource()",
    "AlreadyLive(uint256)", "OutOfRange(uint256)", "ManifestConflict(bytes32,bytes32)", "NotHomeCollection()",
    "SameChain()", "ERC721NotAuthorized(address,uint256)",
    # adapters
    "NotEndpoint()", "WrongPeer()", "AlreadySet()", "ZeroOwner()", "NotLzEndpoint()", "NotPinned(uint32)", "UnknownChain(uint64)", "ValueNotAccepted()",
    "BadAttesters()", "BadSignatures()", "AlreadyDelivered()", "BadRef()", "NotCircuitHolder()",
]
EVENTS = [
    "Departed(bytes32,uint256,uint64,address)",
    "Confirmed(bytes32,address)",
    "Arrived(bytes32,uint256,uint64,address)",
    "RouteSet(uint64,uint8,address[],address)",
    "RoutesSealed()",
    "AdapterSealed()",
    "MetadataUpdate(uint256)",
]
interfaces = {
    "interfaceIds": {k: iface(v) for k, v in IFACES.items()},
    "selectors": {g: h(sel(g)) for v in IFACES.values() for g in v} | {g: h(sel(g)) for g in EXTRA},
    "eventTopics": {e: h(keccak256(e.encode())) for e in EVENTS},
    "errors": {e: h(sel(e)) for e in ERRORS},
}

out = {
    "format": "tap-netlist-nft-bridging-vectors/2",
    "generator": "make_vectors.py",
    "notes": "Addresses other than TapeCode-Test1 and the DeWEB hub are examples, not deployments. "
             "Integers above 2^53 are decimal strings.",
    "collectionKeys": [
        {"homeChainId": 196, "homeContract": TCT1, "collectionKey": h(key_xl)},
        {"homeChainId": 56, "homeContract": "0x0000000000000000000000000000000000000001",
         "collectionKey": h(collection_key(56, "0x0000000000000000000000000000000000000001"))},
    ],
    "validPayloads": valid,
    "invalidPayloads": invalid,
    "layerZero": {
        "eids": {"56": 30102, "8453": 30184, "196": 30274},
        "endpointV2": "0x1a44076050125825900e736c501f859c50fE728c",
        "defaultOptions": [{"gas": 400000, "options": h(lz_option(400000))},
                           {"gas": 300000, "options": h(lz_option(300000))}],
        "layerId": h(keccak256(b"TAP-NFT adapter LayerZeroV2 v1")),
    },
    "interfaces": interfaces,
    "hubRelay": {
        "layerId": h(keccak256(b"TAP-NFT adapter TAP-10 hub relay v1")),
        "toEndpointId": {"chainId": 56, "container": DST_CONTAINER, "endpointId": h(endpoint_id(56, DST_CONTAINER))},
        "eip712": {
            "domainTypehash": h(DOMAIN_T), "hubMessageTypehash": h(HUB_T),
            "domain": {"name": "TAP-NFT Hub Relay", "version": "1", "chainId": 56, "verifyingContract": HUB_ADAPTER_BSC},
            "domainSeparator": h(domain),
            "message": {"srcChainId": 196, "hub": HUB, "fromContainer": SRC_CONTAINER, "outboxIndex": 5,
                        "digest": valid[0]["hubDigest"], "payloadOf": "home-to-remote"},
            "structHash": h(struct), "signingHash": h(signing),
        },
    },
}

if __name__ == "__main__":
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")
    text = json.dumps(out, indent=2) + "\n"
    try:  # optional cross-check against an independent Keccak
        from Crypto.Hash import keccak as _k
        for v in valid:
            data = bytes.fromhex(v["srcEndpoint"][2:]) + bytes.fromhex(v["payload"][2:])
            assert "0x" + _k.new(digest_bits=256, data=data).hexdigest() == v["messageId"]
    except ImportError:
        pass
    if "--check" in sys.argv:
        with open(path) as f:
            ok = f.read() == text
        print("vectors.json up to date" if ok else "vectors.json differs")
        sys.exit(0 if ok else 1)
    with open(path, "w") as f:
        f.write(text)
    print(path, hashlib.sha256(text.encode()).hexdigest())
