"""Tiny read-only JSON-RPC client, ABI helpers and the recorded-fixture mode of the family checker.

Standard library only (urllib). The client issues `eth_call`, `eth_getCode`, `eth_blockNumber`,
`eth_getBlockByNumber`, `eth_getTransactionReceipt` and `eth_getLogs` and nothing else: it never sends a
transaction and never signs anything.

Selectors are keccak-256 of the signature (credits.keccak256, pure Python), so any `tap.freeze.call` can be
probed. Every read is pinned to one block per chain (TAP-10 §5): the first read of a chain fetches
`eth_blockNumber` (or the chain's finality tag) and later reads of that chain use that block.

Offline mode (`--offline`): the same code answers from a recorded fixture (fixtures/recorded-rpc.json),
keyed by chain id, method and the exact request, and raises NotRecorded for anything else.
"""
from __future__ import annotations

import json
import re
import urllib.request

from _paths import keccak256

ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
ZERO32 = "0x" + "00" * 32
ONES32 = "0x" + "ff" * 32

# TAP-10 §2.1 finality tags of the chains the family uses (credits.FINALITY_TAG lists the same).
FINALITY_TAG = {56: "finalized", 8453: "safe", 196: "safe"}


class RpcError(Exception):
    """The node answered with a JSON-RPC error (a revert, an unknown method, a pruned block)."""

    def __init__(self, message, code=None, data=None):
        super().__init__(message)
        self.code, self.data = code, data


class NotRecorded(Exception):
    """Offline mode: the fixture holds no answer for this request."""


# ---------------------------------------------------------------- ABI

def selector(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()[:8]


def _types_of(sig: str) -> list:
    inner = sig[sig.index("(") + 1:sig.rindex(")")]
    return [t.strip() for t in inner.split(",") if t.strip()]


def _word_of(t: str, v) -> bytes:
    if t == "address":
        if not ADDR.match(v):
            raise ValueError(f"bad address {v!r}")
        return bytes(12) + bytes.fromhex(v[2:])
    if t == "bool":
        return (1 if v else 0).to_bytes(32, "big")
    if t.startswith("uint"):
        return int(v).to_bytes(32, "big")
    if t == "bytes32":
        b = bytes.fromhex(v[2:]) if isinstance(v, str) else bytes(v)
        if len(b) != 32:
            raise ValueError("bytes32 needs 32 bytes")
        return b
    if t == "bytes4":
        b = bytes.fromhex(v[2:]) if isinstance(v, str) else bytes(v)
        return b.ljust(32, b"\0")
    raise ValueError(f"unsupported argument type {t}")


def encode_call(sig: str, *args) -> str:
    """Calldata for a function with static arguments only (every call the checker makes)."""
    types = _types_of(sig)
    if len(types) != len(args):
        raise ValueError(f"{sig}: {len(args)} arguments for {len(types)} parameters")
    return selector(sig) + b"".join(_word_of(t, a) for t, a in zip(types, args)).hex()


def _is_dynamic(t: str) -> bool:
    if t in ("bytes", "string") or t.endswith("[]"):
        return True
    if t.startswith("("):
        return any(_is_dynamic(x) for x in split_tuple(t))
    return False


def split_tuple(t: str) -> list:
    """Components of a tuple type "(a,b,(c,d)[])"."""
    inner, out, depth, cur = t[1:-1], [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        cur += ch
    if cur:
        out.append(cur)
    return out


def _decode_at(t: str, data: bytes, off: int):
    """Decode one value of type t whose head starts at `off` (its tail is addressed relative to `off`
    for tuples/arrays, which is the ABI's rule: offsets are relative to the start of the enclosing
    tuple or array body)."""
    word = data[off:off + 32]
    if len(word) < 32:
        raise ValueError("return data too short")
    if t == "address":
        return "0x" + word[12:].hex()
    if t == "bool":
        return int.from_bytes(word, "big") != 0
    if t.startswith("uint"):
        return int.from_bytes(word, "big")
    if t.startswith("int"):
        v = int.from_bytes(word, "big")
        return v - (1 << 256) if v >> 255 else v
    if t == "bytes32":
        return "0x" + word.hex()
    if re.match(r"^bytes\d+$", t):
        n = int(t[5:])
        return "0x" + word[:n].hex()
    raise ValueError(f"unsupported static type {t}")


def _decode_body(types: list, data: bytes, base: int) -> list:
    out, head = [], base
    for t in types:
        if _is_dynamic(t):
            rel = int.from_bytes(data[head:head + 32], "big")
            out.append(_decode_dynamic(t, data, base + rel))
            head += 32
        elif t.startswith("("):
            comps = split_tuple(t)
            out.append(tuple(_decode_body(comps, data, head)))
            head += 32 * _static_words(t)
        else:
            out.append(_decode_at(t, data, head))
            head += 32
    return out


def _static_words(t: str) -> int:
    if t.startswith("("):
        return sum(_static_words(x) for x in split_tuple(t))
    return 1


def _decode_dynamic(t: str, data: bytes, at: int):
    if t in ("bytes", "string"):
        n = int.from_bytes(data[at:at + 32], "big")
        raw = data[at + 32:at + 32 + n]
        if len(raw) != n:
            raise ValueError("return data too short")
        return raw.decode("utf-8", "replace") if t == "string" else raw
    if t.endswith("[]"):
        elem = t[:-2]
        n = int.from_bytes(data[at:at + 32], "big")
        if n > 1_000_000:
            raise ValueError("array too long")
        body = at + 32
        if _is_dynamic(elem):
            return [_decode_dynamic(elem, data, body + int.from_bytes(data[body + 32 * i:body + 32 * i + 32], "big"))
                    for i in range(n)]
        if elem.startswith("("):
            w = 32 * _static_words(elem)
            return [tuple(_decode_body(split_tuple(elem), data, body + i * w)) for i in range(n)]
        return [_decode_at(elem, data, body + 32 * i) for i in range(n)]
    if t.startswith("("):
        return tuple(_decode_body(split_tuple(t), data, at))
    raise ValueError(f"unsupported dynamic type {t}")


def decode(types, hexdata: str):
    """Decode return data. `types` is a list of ABI types or a single type string."""
    single = isinstance(types, str)
    tl = [types] if single else list(types)
    data = bytes.fromhex(hexdata[2:]) if hexdata.startswith("0x") else bytes.fromhex(hexdata)
    vals = _decode_body(tl, data, 0)
    return vals[0] if single else vals


def encode_words(*vals) -> str:
    """Static words only: used by make_fixture.py to build recorded answers."""
    out = b""
    for t, v in vals:
        out += _word_of(t, v)
    return "0x" + out.hex()


def encode_bytes_return(raw: bytes) -> str:
    """ABI encoding of a single `bytes` (or `string`) return value."""
    n = len(raw)
    pad = (-n) % 32
    return "0x" + (32).to_bytes(32, "big").hex() + n.to_bytes(32, "big").hex() + raw.hex() + "00" * pad


# ---------------------------------------------------------------- client

class Rpc:
    """Read-only JSON-RPC over one or more node URLs per chain, or over a recorded fixture.

    nodes: {chainId: [url, ...]}. In offline mode `fixture` is the parsed fixture document and nodes are
    ignored. `pin` caches one block number per chain (TAP-10 §5: every read of a chain at one block)."""

    def __init__(self, nodes: dict = None, fixture: dict = None, timeout: float = 30.0, user_agent: str = "tap-family-checker"):
        self.nodes = {int(k): list(v) for k, v in (nodes or {}).items()}
        self.fixture = fixture
        self.timeout = timeout
        self.user_agent = user_agent
        self.pin = {}
        self.calls = 0

    @property
    def offline(self) -> bool:
        return self.fixture is not None

    def has_chain(self, chain_id: int) -> bool:
        if self.offline:
            return str(chain_id) in self.fixture.get("chains", {})
        return bool(self.nodes.get(chain_id))

    def urls(self, chain_id: int) -> list:
        if self.offline:
            return [f"fixture:{chain_id}"]
        return self.nodes.get(chain_id, [])

    # -- raw transport
    def _post(self, url: str, method: str, params: list):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(url, body, {"content-type": "application/json", "user-agent": self.user_agent})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            res = json.load(r)
        self.calls += 1
        if "error" in res:
            e = res["error"] if isinstance(res["error"], dict) else {"message": str(res["error"])}
            raise RpcError(e.get("message", "rpc error"), e.get("code"), e.get("data"))
        return res.get("result")

    def _fixture_chain(self, chain_id: int) -> dict:
        ch = self.fixture.get("chains", {}).get(str(chain_id))
        if ch is None:
            raise NotRecorded(f"chain {chain_id} is not in the fixture")
        return ch

    def request(self, chain_id: int, method: str, params: list, url: str = None):
        """One request to one node (the first of the chain unless `url` is given)."""
        if self.offline:
            ch = self._fixture_chain(chain_id)
            key = method + ":" + json.dumps(params, sort_keys=True, separators=(",", ":"))
            if key not in ch.get("requests", {}):
                raise NotRecorded(f"chain {chain_id}: {key} is not recorded")
            ans = ch["requests"][key]
            self.calls += 1
            if isinstance(ans, dict) and "error" in ans:
                raise RpcError(ans["error"].get("message", "recorded error"), ans["error"].get("code"), ans["error"].get("data"))
            return ans
        urls = self.nodes.get(chain_id) or []
        if not urls:
            raise RpcError(f"no RPC URL for chain {chain_id}")
        return self._post(url or urls[0], method, params)

    # -- pinned block
    def pinned_block(self, chain_id: int) -> int:
        """The block every read of this chain is pinned to: the chain's finality tag when the node knows
        it, else the latest block, fetched once."""
        if chain_id in self.pin:
            return self.pin[chain_id]
        tag = FINALITY_TAG.get(chain_id, "latest")
        try:
            head = self.request(chain_id, "eth_getBlockByNumber", [tag, False])
            n = int(head["number"], 16)
        except (RpcError, NotRecorded, TypeError, KeyError):
            n = int(self.request(chain_id, "eth_blockNumber", []), 16)
        self.pin[chain_id] = n
        return n

    def set_pin(self, chain_id: int, block: int) -> None:
        self.pin[chain_id] = block

    # -- reads
    def call(self, chain_id: int, to: str, data: str, block=None, url: str = None) -> str:
        if block is None:
            block = self.pinned_block(chain_id)
        tag = hex(block) if isinstance(block, int) else block
        return self.request(chain_id, "eth_call", [{"to": to.lower(), "data": data}, tag], url)

    def call_decode(self, chain_id: int, to: str, sig: str, args: tuple, ret, block=None, url: str = None):
        """eth_call of `sig(args)` and decoding of the result as `ret` (a type or list of types)."""
        out = self.call(chain_id, to, encode_call(sig, *args), block, url)
        if out in (None, "0x"):
            raise RpcError("empty return data (no code at the address, or the function does not exist)")
        return decode(ret, out)

    def supports_interface(self, chain_id: int, to: str, iid: str, block=None) -> bool:
        """ERC-165. A revert or empty return counts as false."""
        try:
            return bool(self.call_decode(chain_id, to, "supportsInterface(bytes4)", (iid,), "bool", block))
        except (RpcError, ValueError):
            return False

    def get_code(self, chain_id: int, addr: str, block=None, url: str = None) -> str:
        if block is None:
            block = self.pinned_block(chain_id)
        tag = hex(block) if isinstance(block, int) else block
        return self.request(chain_id, "eth_getCode", [addr.lower(), tag], url) or "0x"

    def get_block(self, chain_id: int, number, url: str = None) -> dict:
        tag = hex(number) if isinstance(number, int) else number
        return self.request(chain_id, "eth_getBlockByNumber", [tag, False], url)

    def get_receipt(self, chain_id: int, tx_hash: str, url: str = None) -> dict:
        return self.request(chain_id, "eth_getTransactionReceipt", [tx_hash.lower()], url)

    def get_logs(self, chain_id: int, address: str, topics: list, from_block, to_block, url: str = None) -> list:
        f = {"address": address.lower(), "topics": topics,
             "fromBlock": hex(from_block) if isinstance(from_block, int) else from_block,
             "toBlock": hex(to_block) if isinstance(to_block, int) else to_block}
        return self.request(chain_id, "eth_getLogs", [f], url) or []


def load_fixture(path: str) -> dict:
    with open(path, "rb") as f:
        return json.loads(f.read())
