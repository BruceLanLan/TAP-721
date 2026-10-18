#!/usr/bin/env python3
"""tapup — safe, resumable batch uploader for a TapeOut container's site store (TAP-10 SiteRegistry).

Subcommands: plan, operator {show,set,clear}, upload, verify, lock-checklist.  Python 3.9+ stdlib only.

Keys: a hot-wallet key is read from an environment variable (default TAPUP_PRIVATE_KEY) and removed from the
environment immediately, or decrypted once from a Foundry keystore with `cast wallet decrypt-keystore` (you type
the password at cast's prompt). The key is never a CLI argument and never written to disk. `--unlocked ADDR`
(eth_sendTransaction without a key) is refused unless the RPC node is anvil.
"""
import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ethcrypto  # noqa: E402

CHUNK = 24_000
MAX_CHUNKS = 350
MAX_SIZE = CHUNK * MAX_CHUNKS
READ_ONE = 98_304            # TAP-10 §7.1: read() up to 96 KiB, readRange segments above
MAX_TTL = 2_592_000          # measured on X Layer fork: setOperator reverts TooLarge above 30 days
ZERO = "0x" + "00" * 20

CHAINS = {
    196: {
        "name": "X Layer",
        "store": "0xd6EFb7adCc9c83dC4924Ad56f6a8E4e969b9ADB6",
        "binding": "0x68809Fd2fb343aA57D0aeB7f33Defe477c9666f9",
        "opener": "0x536adD8F30f03b69f6fbF29d425A816A0dC50106",
        # ERC-1967 implementation of the store accepted by this tool (read 2026-10-18, block ~73,488,700)
        "store_impl": "0xa85c4143d1d4a77f54b8e4ecc9e6d1418afea45f",
        "rpc": "https://rpc.xlayer.tech",
    },
}
IMPL_SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
GAS_ORACLE = "0x420000000000000000000000000000000000000F"  # OP-stack GasPriceOracle (L1 data fee)

# Gas model (measured on an anvil fork of X Layer, see README): gasUsed ≈ base + per_byte × chunk bytes.
GAS = {"put_new": 296_000, "put_replace": 160_000, "append": 175_000, "per_byte": 217}
GAS_LIMIT_MARGIN = 1.25

CONTENT_TYPES = {
    ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif", ".svg": "image/svg+xml",
    ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".css": "text/css",
    ".js": "text/javascript", ".mjs": "text/javascript", ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8", ".xml": "application/xml", ".wasm": "application/wasm",
    ".ico": "image/x-icon", ".mp4": "video/mp4", ".webm": "video/webm", ".mp3": "audio/mpeg",
    ".woff2": "font/woff2", ".woff": "font/woff", ".pdf": "application/pdf",
    ".tapnet": "application/octet-stream", ".bin": "application/octet-stream",
}


def die(msg, code=1):
    print("error: " + msg, file=sys.stderr)
    sys.exit(code)


# ================================================================ ABI


def sel(sig):
    return ethcrypto.keccak256(sig.encode())[:4]


def topic(sig):
    return "0x" + ethcrypto.keccak256(sig.encode()).hex()


def _word(n):
    return n.to_bytes(32, "big")


def _pad(b):
    return b + b"\x00" * (-len(b) % 32)


def enc(types, vals):
    head, tail = [], []
    hlen = 32 * len(types)
    for t, v in zip(types, vals):
        if t in ("string", "bytes"):
            b = v.encode() if isinstance(v, str) and t == "string" else (bytes.fromhex(v[2:]) if isinstance(v, str) else v)
            head.append(_word(hlen + sum(len(x) for x in tail)))
            tail.append(_word(len(b)) + _pad(b))
        elif t == "address":
            head.append(_word(int(v, 16)))
        elif t == "bytes32":
            head.append(bytes.fromhex(v[2:]) if isinstance(v, str) else v)
        elif t in ("uint256", "uint40", "uint32", "bool"):
            head.append(_word(int(v)))
        else:
            raise ValueError(t)
    return b"".join(head) + b"".join(tail)


def calldata(sig, types, vals):
    return "0x" + (sel(sig) + enc(types, vals)).hex()


def dec(types, data):
    if isinstance(data, str):
        data = bytes.fromhex(data[2:])
    out = []
    for i, t in enumerate(types):
        w = data[32 * i:32 * i + 32]
        if t in ("string", "bytes"):
            off = int.from_bytes(w, "big")
            n = int.from_bytes(data[off:off + 32], "big")
            b = data[off + 32:off + 32 + n]
            out.append(b.decode("utf-8", "replace") if t == "string" else b)
        elif t == "address":
            out.append("0x" + w[12:].hex())
        elif t == "bytes32":
            out.append("0x" + w.hex())
        elif t == "bool":
            out.append(int.from_bytes(w, "big") != 0)
        else:
            out.append(int.from_bytes(w, "big"))
    return out


# ================================================================ RPC


class RpcError(Exception):
    def __init__(self, err):
        self.err = err
        super().__init__(json.dumps(err)[:500])

    @property
    def message(self):
        return str(self.err.get("message", "")) if isinstance(self.err, dict) else str(self.err)


class RPC:
    def __init__(self, url, retries=6):
        self.url, self.retries, self._id, self.max_batch = url, retries, 0, 100

    def _post(self, body):
        delay = 0.5
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(self.url, json.dumps(body).encode(),
                                             {"content-type": "application/json", "user-agent": "tapup"})
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.load(r)
            except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
                code = getattr(e, "code", None)
                if code is not None and code < 500 and code not in (403, 429):  # 403: CDN rate block on rpc.xlayer.tech
                    raise
                if attempt == self.retries:
                    raise
                time.sleep(delay + random.random() * delay)
                delay = min(delay * 2, 30)

    def call(self, method, *params):
        self._id += 1
        res = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": list(params)})
        if "error" in res:
            raise RpcError(res["error"])
        return res["result"]

    def batch(self, calls, size=20):
        """calls: [(method, params)] -> [result or RpcError]. Shrinks the batch if the node limits it."""
        out = []
        i = 0
        while i < len(calls):
            n = min(size, self.max_batch)
            part = calls[i:i + n]
            body = [{"jsonrpc": "2.0", "id": j, "method": m, "params": p} for j, (m, p) in enumerate(part)]
            res = self._post(body)
            if isinstance(res, dict):
                err = res.get("error", res)
                msg = str(err.get("message", "")).lower() if isinstance(err, dict) else ""
                if n > 1 and "batch" in msg:
                    self.max_batch = max(1, n // 2)
                    continue
                raise RpcError(err)
            res.sort(key=lambda x: x["id"])
            out += [RpcError(x["error"]) if "error" in x else x["result"] for x in res]
            i += n
        return out

    def eth_call(self, to, data, frm=None, value=0, block="latest"):
        tx = {"to": to, "data": data}
        if frm:
            tx["from"] = frm
        if value:
            tx["value"] = hex(value)
        return self.call("eth_call", tx, block)


def is_anvil(rpc):
    try:
        return str(rpc.call("web3_clientVersion")).lower().startswith("anvil")
    except RpcError:
        return False


# ================================================================ chain views


class Site:
    def __init__(self, rpc, store, container, block="latest"):
        self.rpc, self.store, self.container, self.block = rpc, store, container, block

    def file_info_many(self, paths):
        calls = [("eth_call", [{"to": self.store, "data": calldata("fileInfo(address,string)", ["address", "string"],
                                                                  [self.container, p])}, self.block]) for p in paths]
        out = []
        for p, r in zip(paths, self.rpc.batch(calls)):
            if isinstance(r, RpcError):
                raise r
            size, ctype, sha, upd, cc = dec(["uint32", "string", "bytes32", "uint40", "uint256"], r)
            out.append({"size": size, "contentType": ctype, "sha256": sha, "updatedAt": upd, "chunkCount": cc})
        return out

    def read_bytes(self, path, size):
        if size <= READ_ONE:
            r = self.rpc.eth_call(self.store, calldata("read(address,string)", ["address", "string"], [self.container, path]),
                                  block=self.block)
            return dec(["bytes"], r)[0]
        calls = [("eth_call", [{"to": self.store, "data": calldata(
            "readRange(address,string,uint256,uint256)", ["address", "string", "uint256", "uint256"],
            [self.container, path, off, READ_ONE])}, self.block]) for off in range(0, size, READ_ONE)]
        parts = []
        for r in self.rpc.batch(calls, size=4):
            if isinstance(r, RpcError):
                raise r
            parts.append(dec(["bytes"], r)[0])
        return b"".join(parts)

    def read_small_many(self, paths):
        calls = [("eth_call", [{"to": self.store, "data": calldata("read(address,string)", ["address", "string"],
                                                                  [self.container, p])}, self.block]) for p in paths]
        return [r if isinstance(r, RpcError) else dec(["bytes"], r)[0] for r in self.rpc.batch(calls, size=10)]

    def view(self, sig, types, vals, out):
        return dec(out, self.rpc.eth_call(self.store, calldata(sig, types, vals)))

    def can_edit(self, who):
        return self.view("canEdit(address,address)", ["address", "address"], [self.container, who], ["bool"])[0]

    def operator(self):
        op = self.view("operatorOf(address)", ["address"], [self.container], ["address"])[0]
        until = self.view("operatorUntil(address)", ["address"], [self.container], ["uint256"])[0]
        return op, until


def container_token(rpc, container):
    chain_id, proc, token_id = dec(["uint256", "address", "uint256"], rpc.eth_call(container, "0x" + sel("token()").hex()))
    holder = dec(["address"], rpc.eth_call(proc, calldata("ownerOf(uint256)", ["uint256"], [token_id])))[0]
    return chain_id, proc, token_id, holder


def store_impl(rpc, store):
    return "0x" + rpc.call("eth_getStorageAt", store, IMPL_SLOT, "latest")[-40:]


def check_store_impl(rpc, chain_id, store, accept):
    impl = store_impl(rpc, store)
    want = CHAINS.get(chain_id, {}).get("store_impl")
    if want and impl.lower() != want.lower():
        msg = "site store implementation is %s, this tool was checked against %s" % (impl, want)
        if not accept:
            die(msg + " (TAP-10 §6.1 store-changed). Re-test on a fork, then pass --accept-impl " + impl)
        if accept.lower() != impl.lower():
            die(msg + "; --accept-impl does not match")
        print("warning: " + msg + " (accepted by --accept-impl)")
    return impl


# ================================================================ files


def content_type(path, data, overrides):
    ext = os.path.splitext(path.rsplit("/", 1)[-1])[1].lower()
    if ext in overrides:
        return overrides[ext]
    if ext in CONTENT_TYPES:
        return CONTENT_TYPES[ext]
    if not ext:
        try:
            json.loads(data.decode("utf-8"))
            return "application/json"
        except (UnicodeDecodeError, ValueError):
            pass
    return "application/octet-stream"


def check_path(p):
    if unicodedata.normalize("NFC", p) != p:
        return "not NFC-normalized"
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in p):
        return "control character"
    segs = p.split("/")
    if p.startswith("/") or p.endswith("/") or "" in segs:
        return "empty segment or leading/trailing /"
    if "." in segs or ".." in segs:
        return ". or .. segment"
    if "?" in p or "#" in p or "%" in p:
        return "contains ? # or % (TAP-10 §7.2 readers strip/decode these)"
    return None


def chunks_of(size):
    return max(1, math.ceil(size / CHUNK))


def gas_for_chunk(kind, n):
    base = {"put_new": GAS["put_new"], "put_replace": GAS["put_replace"], "append": GAS["append"]}[kind]
    return base + GAS["per_byte"] * n


def classify(local, onchain, verify_prefix=None):
    """Return (status, resumeAt). status: skip | new | replace | partial."""
    if onchain["chunkCount"] == 0:
        return "new", 0
    same = onchain["sha256"].lower() == local["sha256"].lower() and onchain["contentType"] == local["contentType"]
    if same and onchain["size"] == local["size"]:
        return "skip", None
    k = onchain["chunkCount"]
    if same and onchain["size"] < local["size"] and onchain["size"] == k * CHUNK and k < local["chunks"]:
        if verify_prefix is None or verify_prefix(local, onchain["size"]):
            return "partial", k
    return "replace", 0


def walk(root, prefix, overrides, exclude_hidden=True):
    files, errors = [], []
    root = os.path.abspath(root)
    for d, dirs, names in os.walk(root):
        dirs.sort()
        if exclude_hidden:
            dirs[:] = [x for x in dirs if not x.startswith(".")]
        for n in sorted(names):
            if exclude_hidden and n.startswith("."):
                continue
            full = os.path.join(d, n)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            path = (prefix.strip("/") + "/" + rel) if prefix.strip("/") else rel
            with open(full, "rb") as f:
                data = f.read()
            err = check_path(path)
            if len(data) > MAX_SIZE:
                err = "larger than %d bytes (350 chunks)" % MAX_SIZE
            if err:
                errors.append((path, err))
                continue
            files.append({"path": path, "local": rel, "size": len(data), "sha256": "0x" + hashlib.sha256(data).hexdigest(),
                          "contentType": content_type(path, data, overrides), "chunks": chunks_of(len(data))})
    return files, errors


def tx_gas_list(f, status, start):
    out = []
    for k in range(start, f["chunks"]):
        n = min(CHUNK, f["size"] - k * CHUNK)
        out.append(gas_for_chunk(("put_replace" if status == "replace" else "put_new") if k == 0 else "append", n))
    return out


# ================================================================ plan


def l1_fee_fn(rpc):
    """Linear model of the OP-stack L1 data fee from GasPriceOracle.getL1FeeUpperBound(txSize); 0 if absent."""
    try:
        if rpc.call("eth_getCode", GAS_ORACLE, "latest") in ("0x", "0x0"):
            return lambda n: 0
        a = dec(["uint256"], rpc.eth_call(GAS_ORACLE, calldata("getL1FeeUpperBound(uint256)", ["uint256"], [1000])))[0]
        b = dec(["uint256"], rpc.eth_call(GAS_ORACLE, calldata("getL1FeeUpperBound(uint256)", ["uint256"], [25000])))[0]
        return lambda n: a + (b - a) * (n - 1000) // 24000
    except RpcError:
        return lambda n: 0


def cmd_plan(a):
    rpc = RPC(a.rpc)
    chain_id = int(rpc.call("eth_chainId"), 16)
    cfg = CHAINS.get(chain_id, {})
    store = a.store or cfg.get("store") or die("no site store known for chain %d; pass --store" % chain_id)
    impl = check_store_impl(rpc, chain_id, store, a.accept_impl)
    overrides = dict(x.split("=", 1) for x in a.type)
    files, errors = walk(a.dir, a.prefix, overrides)
    for p, e in errors:
        print("  BAD  %s: %s" % (p, e))
    if errors:
        die("%d path(s) cannot be uploaded" % len(errors))
    if not files:
        die("no files")
    site = Site(rpc, store, a.container)
    infos = site.file_info_many([f["path"] for f in files])
    gas_price = int(rpc.call("eth_gasPrice"), 16)
    l1 = l1_fee_fn(rpc)
    tot = {"skip": 0, "new": 0, "replace": 0, "partial": 0}
    gas = txs = byts = l1fee = 0
    for f, oc in zip(files, infos):
        st, start = classify(f, oc)  # prefix verified again by upload before resuming
        f["status"], f["resumeAt"], f["onchain"] = st, start, oc
        tot[st] += 1
        if st != "skip":
            g = tx_gas_list(f, st, start)
            gas += sum(g)
            txs += len(g)
            byts += f["size"] - start * CHUNK
            l1fee += sum(l1(min(CHUNK, f["size"] - k * CHUNK) + 300) for k in range(start, f["chunks"]))
    block = int(rpc.call("eth_blockNumber"), 16)
    plan = {"tapupPlan": 1, "chainId": chain_id, "store": store, "storeImpl": impl, "container": a.container,
            "root": os.path.abspath(a.dir), "prefix": a.prefix, "block": block, "anvil": is_anvil(rpc),
            "gasPrice": gas_price, "files": files}
    with open(a.out, "w") as fh:
        json.dump(plan, fh, indent=1)
    if a.verbose:
        for f in files:
            print("  %-8s %-48s %9d B  %3d chunk(s)  %s" % (f["status"], f["path"], f["size"], f["chunks"], f["contentType"]))
    cost = gas * gas_price + l1fee
    print("chain %d (%s)%s  store %s  container %s  block %d" % (chain_id, cfg.get("name", "?"),
          "  [anvil fork]" if plan["anvil"] else "", store, a.container, block))
    print("files %d: new %d, replace %d, partial %d, skip %d" % (len(files), tot["new"], tot["replace"], tot["partial"], tot["skip"]))
    print("to send: %d tx, %d bytes; est. gas %d (%.1f M)" % (txs, byts, gas, gas / 1e6))
    print("gas price %.6f gwei -> est. cost %.6f native (L1 data fee part %.6f), x%.2f gas limits reserve %.6f" % (
        gas_price / 1e9, cost / 1e18, l1fee / 1e18, GAS_LIMIT_MARGIN, gas * GAS_LIMIT_MARGIN * gas_price * 2 / 1e18))
    print("plan written to " + a.out)


# ================================================================ signers


class KeySigner:
    def __init__(self, priv):
        self._priv = priv
        self.address = ethcrypto.address_of(priv)

    def sign(self, chain_id, nonce, tip, max_fee, gas, to, data):
        return ethcrypto.sign_1559(self._priv, chain_id, nonce, tip, max_fee, gas, to, 0, data)


class UnlockedSigner:
    def __init__(self, addr):
        self.address = ethcrypto.to_checksum(addr)


def load_signer(a, rpc):
    if getattr(a, "unlocked", None):
        if not is_anvil(rpc):
            die("--unlocked is only allowed against an anvil node")
        return UnlockedSigner(a.unlocked)
    if getattr(a, "keystore_account", None):
        cmd = ["cast", "wallet", "decrypt-keystore", a.keystore_account]
        if a.keystore_dir:
            cmd += ["--keystore-dir", a.keystore_dir]
        env = {k: v for k, v in os.environ.items() if k != "CAST_UNSAFE_PASSWORD"} if not a.allow_env_password else None
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stdin=None, stderr=None, text=True, env=env)
        m = re.search(r"0x[0-9a-fA-F]{64}", r.stdout or "")
        if r.returncode != 0 or not m:
            die("could not decrypt keystore %s" % a.keystore_account)
        priv = int(m.group(0), 16)
        del r, m
        return KeySigner(priv)
    name = a.key_env
    v = os.environ.pop(name, None)
    if not v:
        die("no signer: set %s (hex private key) in the environment, or use --keystore-account" % name)
    v = v.strip()
    if not re.fullmatch(r"(0x)?[0-9a-fA-F]{64}", v):
        die("%s is not a 32-byte hex private key" % name)
    return KeySigner(int(v, 16))


def fees(rpc, a):
    blk = rpc.call("eth_getBlockByNumber", "latest", False)
    base = int(blk.get("baseFeePerGas") or "0x0", 16)
    try:
        tip = int(rpc.call("eth_maxPriorityFeePerGas"), 16)
    except RpcError:
        tip = 1
    if a.tip_wei is not None:
        tip = a.tip_wei
    max_fee = a.max_fee_wei if a.max_fee_wei is not None else 2 * base + tip
    return tip, max_fee


def confirm(a, rpc, lines):
    anvil = is_anvil(rpc)
    print("\n".join(lines))
    if not anvil and not a.live:
        die("this RPC is not anvil; sending to a live chain needs --live (test on a fork first)")
    if a.yes:
        return
    if not sys.stdin.isatty():
        die("refusing to send without --yes on a non-interactive terminal")
    if input("type 'yes' to send: ").strip() != "yes":
        die("aborted")


def send_simple(rpc, signer, chain_id, to, data, gas, a):
    """One transaction, wait for receipt. Used by `operator`."""
    tip, max_fee = fees(rpc, a)
    if isinstance(signer, UnlockedSigner):
        nonce = int(rpc.call("eth_getTransactionCount", signer.address, "pending"), 16)
        h = rpc.call("eth_sendTransaction", {"from": signer.address, "to": to, "data": data, "gas": hex(gas),
                                             "nonce": hex(nonce), "maxFeePerGas": hex(max_fee),
                                             "maxPriorityFeePerGas": hex(tip)})
    else:
        nonce = int(rpc.call("eth_getTransactionCount", signer.address, "pending"), 16)
        raw, h = signer.sign(chain_id, nonce, tip, max_fee, gas, to, bytes.fromhex(data[2:]))
        rpc.call("eth_sendRawTransaction", "0x" + raw.hex())
    print("sent " + h)
    for _ in range(600):
        r = rpc.call("eth_getTransactionReceipt", h)
        if r:
            ok = r["status"] == "0x1"
            print("%s in block %d, gas %d" % ("ok" if ok else "REVERTED", int(r["blockNumber"], 16), int(r["gasUsed"], 16)))
            if not ok:
                sys.exit(2)
            return r
        time.sleep(1)
    die("no receipt after 600 s for " + h, 3)


# ================================================================ operator


def cmd_operator(a):
    rpc = RPC(a.rpc)
    chain_id = int(rpc.call("eth_chainId"), 16)
    store = a.store or CHAINS.get(chain_id, {}).get("store") or die("pass --store")
    site = Site(rpc, store, a.container)
    _, proc, tid, holder = container_token(rpc, a.container)
    op, until = site.operator()
    now = int(rpc.call("eth_getBlockByNumber", "latest", False)["timestamp"], 16)
    print("container %s  circuit %s #%d  holder %s" % (a.container, proc, tid, holder))
    print("operatorOf = %s  operatorUntil = %d (%s)" % (op, until, "expired/none" if until <= now else "%d s left" % (until - now)))
    if a.action == "show":
        return
    if not is_anvil(rpc) and not a.live:
        die("this RPC is not anvil; sending to a live chain needs --live (test on a fork first)")
    check_store_impl(rpc, chain_id, store, a.accept_impl)
    signer = load_signer(a, rpc)
    if signer.address.lower() != holder.lower():
        die("signer %s is not the circuit holder %s (only the holder can set the operator)" % (signer.address, holder))
    if a.action == "set":
        if not 0 < a.ttl <= MAX_TTL:
            die("--ttl must be 1..%d seconds (the store rejects longer TTLs)" % MAX_TTL)
        target, ttl = ethcrypto.to_checksum(a.op), a.ttl
    else:
        target, ttl = ZERO, 0
    data = calldata("setOperator(address,address,uint256)", ["address", "address", "uint256"], [a.container, target, ttl])
    confirm(a, rpc, ["chain %d via %s  from %s" % (chain_id, a.rpc, signer.address),
                     "setOperator(%s, %s, %d)" % (a.container, target, ttl)])
    send_simple(rpc, signer, chain_id, store, data, 200_000, a)
    op, until = site.operator()
    print("now operatorOf = %s  operatorUntil = %d" % (op, until))


# ================================================================ journal


class Journal:
    def __init__(self, path):
        self.path = path
        self.entries = []
        if os.path.exists(path):
            with open(path) as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.entries.append(json.loads(line))
                    except ValueError:
                        # a torn last line from a crash is tolerated; anything else is not
                        rest = f.read().strip()
                        if rest:
                            die("journal %s line %d is corrupt" % (path, i + 1))
        self.fh = open(path, "a")

    def header(self):
        return self.entries[0] if self.entries and self.entries[0].get("t") == "header" else None

    def write(self, **e):
        e["ts"] = int(time.time())
        self.entries.append(e)
        self.fh.write(json.dumps(e, separators=(",", ":")) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())

    def unresolved(self):
        """Sent transactions grouped by nonce that have no mined/dropped/failed record."""
        done = {e["hash"] for e in self.entries if e["t"] in ("mined", "dropped", "failed")}
        mined_nonces = {e["nonce"] for e in self.entries if e["t"] == "mined"}
        by_nonce = OrderedDict()
        for e in self.entries:
            if e["t"] == "sent" and e["hash"] not in done and e["nonce"] not in mined_nonces:
                by_nonce.setdefault(e["nonce"], []).append(e)
        return by_nonce

    def open_reverts(self):
        acked = {e["hash"] for e in self.entries if e["t"] == "ack"}
        return [e for e in self.entries if e["t"] == "mined" and e["status"] != 1 and e["hash"] not in acked]


def reconcile(rpc, journal, sender, wait_s):
    """Resolve every journaled tx whose outcome is unknown, before deciding what to send."""
    pend = journal.unresolved()
    if not pend:
        return
    print("reconciling %d unresolved nonce(s) from the journal" % len(pend))
    deadline = time.time() + wait_s
    delay = 2
    while pend:
        try:
            _reconcile_pass(rpc, journal, sender, pend)
            delay = 2
        except (RpcError, OSError) as e:  # transient RPC trouble: nothing is decided, try again
            print("  reconcile: RPC error (%s); retrying in %d s" % (str(e)[:100], delay))
            time.sleep(delay)
            delay = min(delay * 2, 60)
        if pend:
            if time.time() > deadline:
                die("%d journaled tx still unresolved after %d s; re-run upload later" % (len(pend), wait_s), 3)
            time.sleep(2)


def _reconcile_pass(rpc, journal, sender, pend):
    latest = int(rpc.call("eth_getTransactionCount", sender, "latest"), 16)
    for nonce in list(pend):
        entries = pend[nonce]
        got = None
        for e in entries:
            r = rpc.call("eth_getTransactionReceipt", e["hash"])
            if r:
                got = (e, r)
                break
        if got:
            e, r = got
            journal.write(t="mined", hash=e["hash"], nonce=nonce, path=e["path"], chunk=e["chunk"],
                          status=int(r["status"], 16), gasUsed=int(r["gasUsed"], 16), block=int(r["blockNumber"], 16))
            for o in entries:
                if o is not e:
                    journal.write(t="dropped", hash=o["hash"], nonce=nonce, why="replaced")
            del pend[nonce]
            continue
        in_pool = any(rpc.call("eth_getTransactionByHash", e["hash"]) for e in entries)
        if in_pool and nonce >= latest:
            continue  # still pending: wait
        why = "nonce used by another tx" if nonce < latest else "not in pool (never broadcast or dropped)"
        for e in entries:
            journal.write(t="dropped", hash=e["hash"], nonce=nonce, why=why)
        del pend[nonce]


# ================================================================ upload


def load_plan(path):
    with open(path) as f:
        plan = json.load(f)
    if plan.get("tapupPlan") != 1:
        die("not a tapup plan: " + path)
    return plan


def local_bytes(plan, f):
    with open(os.path.join(plan["root"], f["local"]), "rb") as fh:
        data = fh.read()
    if "0x" + hashlib.sha256(data).hexdigest() != f["sha256"] or len(data) != f["size"]:
        die("local file %s changed since the plan was made; re-run plan" % f["local"])
    return data


def cmd_upload(a):
    plan = load_plan(a.plan)
    rpc = RPC(a.rpc)
    chain_id = int(rpc.call("eth_chainId"), 16)
    anvil = is_anvil(rpc)
    if not anvil and not a.live:
        die("this RPC is not anvil; sending to a live chain needs --live (test on a fork first)")
    if chain_id != plan["chainId"]:
        die("RPC chain %d differs from the plan's chain %d" % (chain_id, plan["chainId"]))
    if anvil != plan["anvil"]:
        die("the plan was made on %s but this RPC is %s; re-run plan here" % (
            "an anvil fork" if plan["anvil"] else "a live node", "anvil" if anvil else "a live node"))
    store, container = plan["store"], plan["container"]
    check_store_impl(rpc, chain_id, store, a.accept_impl)
    signer = load_signer(a, rpc)
    if isinstance(signer, UnlockedSigner):
        die("upload needs a signing key (the journal records tx hashes before broadcast)")
    sender = signer.address

    journal = Journal(a.journal)
    hdr = journal.header()
    want = {"chainId": chain_id, "store": store.lower(), "container": container.lower(), "sender": sender.lower(),
            "anvil": anvil}
    if hdr is None:
        if journal.entries:
            die("journal %s has no header" % a.journal)
        journal.write(t="header", plan=os.path.abspath(a.plan), **want)
    else:
        for k, v in want.items():
            if hdr.get(k) != v:
                die("journal %s was made for %s=%s, this run has %s=%s; refusing (use a new journal)" % (
                    a.journal, k, hdr.get(k), k, v))

    reconcile(rpc, journal, sender, a.pending_wait)
    reverts = journal.open_reverts()
    if reverts:
        for e in reverts:
            print("  REVERTED nonce %d %s chunk %d tx %s" % (e["nonce"], e["path"], e["chunk"], e["hash"]))
        if not a.ack_reverts:
            die("the journal has %d reverted tx; inspect them, then re-run with --ack-reverts" % len(reverts), 2)
        for e in reverts:
            journal.write(t="ack", hash=e["hash"])

    site = Site(rpc, store, container)
    if not site.can_edit(sender):
        die("%s cannot edit container %s (not the holder, and not a live operator)" % (sender, container))
    op, until = site.operator()
    now = int(rpc.call("eth_getBlockByNumber", "latest", False)["timestamp"], 16)
    if op.lower() == sender.lower() and until - now < 600:
        print("warning: operator TTL ends in %d s" % (until - now))

    # fresh state from the chain decides what to send (never the plan's stale status)
    files = [f for f in plan["files"] if not a.only or re.search(a.only, f["path"])]
    infos = site.file_info_many([f["path"] for f in files])

    def prefix_ok(f, n):
        onchain = site.read_bytes(f["path"], n)
        return hashlib.sha256(onchain).digest() == hashlib.sha256(local_bytes(plan, f)[:n]).digest()

    work = []
    for f, oc in zip(files, infos):
        st, start = classify(f, oc, prefix_ok)
        if st != "skip":
            work.append((f, st, start))
    if not work:
        print("nothing to upload: all %d file(s) already match" % len(files))
        return
    ntx = sum(f["chunks"] - s for f, _, s in work)
    est = sum(sum(tx_gas_list(f, st, s)) for f, st, s in work)
    tip, max_fee = fees(rpc, a)
    bal = int(rpc.call("eth_getBalance", sender, "latest"), 16)
    need = int(est * GAS_LIMIT_MARGIN) * max_fee
    if bal < need and not a.ignore_balance:
        die("balance %.6f < worst-case %.6f native for %d tx (fund %s or pass --ignore-balance)" % (
            bal / 1e18, need / 1e18, ntx, sender))
    confirm(a, rpc, ["chain %d%s via %s" % (chain_id, " [anvil]" if anvil else "", a.rpc),
                     "store %s container %s" % (store, container),
                     "sender %s balance %.6f" % (sender, bal / 1e18),
                     "%d file(s) to write (%d new/replace, %d resume), %d tx, est. gas %.1f M, max fee %.4f gwei" % (
                         len(work), sum(1 for w in work if w[1] != "partial"), sum(1 for w in work if w[1] == "partial"),
                         ntx, est / 1e6, max_fee / 1e9),
                     "journal " + a.journal])

    def txs():
        for f, st, start in work:
            data = local_bytes(plan, f)
            for k in range(start, f["chunks"]):
                piece = data[k * CHUNK:(k + 1) * CHUNK]
                if k == 0:
                    cd = calldata("putFile(address,string,string,bytes32,bytes)",
                                  ["address", "string", "string", "bytes32", "bytes"],
                                  [container, f["path"], f["contentType"], f["sha256"], piece])
                    kind = "put_replace" if st == "replace" else "put_new"
                else:
                    cd = calldata("appendChunk(address,string,uint256,bytes)", ["address", "string", "uint256", "bytes"],
                                  [container, f["path"], k, piece])
                    kind = "append"
                gas = int((gas_for_chunk(kind, len(piece)) + 16 * len(f["path"]) + 30_000) * GAS_LIMIT_MARGIN)
                yield {"path": f["path"], "chunk": k, "of": f["chunks"], "bytes": len(piece), "data": bytes.fromhex(cd[2:]),
                       "gas": gas}

    latest = int(rpc.call("eth_getTransactionCount", sender, "latest"), 16)
    pending = int(rpc.call("eth_getTransactionCount", sender, "pending"), 16)
    if pending != latest:
        die("sender has %d pending tx not in this journal; wait for them or use another key" % (pending - latest), 3)
    nonce = latest
    inflight = OrderedDict()
    gen = txs()
    nxt = next(gen, None)
    stop = abandon = None
    rpc_fail = 0
    sent = mined = gas_used = 0
    t0 = fee_at = time.time()

    def broadcast(raw):
        delay = 1
        for attempt in range(a.retries + 1):
            try:
                rpc.call("eth_sendRawTransaction", "0x" + raw.hex())
                return None
            except RpcError as e:
                m = e.message.lower()
                if "already known" in m or "known transaction" in m:
                    return None
                transient = any(s in m for s in ("rate", "limit", "timeout", "busy", "try again", "too many"))
                if not transient or attempt == a.retries:
                    return e.message
            except Exception as e:  # network failure after retries inside RPC
                if attempt == a.retries:
                    return str(e)
            time.sleep(delay + random.random())
            delay = min(delay * 2, 30)

    while (nxt is not None and stop is None) or inflight:
        while nxt is not None and stop is None and len(inflight) < a.concurrency:
            if a.max_tx and sent >= a.max_tx:
                stop = "stopped after --max-tx %d (test hook)" % a.max_tx
                break
            tx = nxt
            if time.time() - fee_at > 60:
                tip, max_fee = fees(rpc, a)
                fee_at = time.time()
            raw, h = signer.sign(chain_id, nonce, tip, max_fee, tx["gas"], store, tx["data"])
            journal.write(t="sent", nonce=nonce, hash=h, path=tx["path"], chunk=tx["chunk"], of=tx["of"],
                          bytes=tx["bytes"], gas=tx["gas"], maxFee=max_fee)
            err = broadcast(raw)
            if err:
                journal.write(t="failed", nonce=nonce, hash=h, error=err[:300])
                stop = "broadcast of nonce %d (%s chunk %d) failed: %s" % (nonce, tx["path"], tx["chunk"], err)
                break
            inflight[nonce] = {"tx": tx, "hashes": [h], "raw": raw, "at": time.time(), "fee": (tip, max_fee),
                               "rebroadcast": 0}
            nonce += 1
            sent += 1
            nxt = next(gen, None)
        if not inflight:
            break
        time.sleep(a.poll)
        allh = [(n, h) for n, it in inflight.items() for h in it["hashes"]]
        try:
            rs = rpc.batch([("eth_getTransactionReceipt", [h]) for _, h in allh])
        except Exception as e:  # RPC trouble while polling is not fatal: the tx are already journaled
            rpc_fail += 1
            print("  receipt poll failed (%d): %s" % (rpc_fail, str(e)[:120]))
            if rpc_fail >= 20:
                abandon = "RPC failing while polling receipts"
                break
            time.sleep(min(30, 2 ** min(rpc_fail, 5)))
            continue
        rpc_fail = 0
        got = {}
        for (n, h), r in zip(allh, rs):
            if r and not isinstance(r, RpcError):
                got[n] = (h, r)
        for n in list(inflight):
            if n not in got:
                continue
            h, r = got[n]
            it = inflight.pop(n)
            st = int(r["status"], 16)
            gu = int(r["gasUsed"], 16)
            journal.write(t="mined", hash=h, nonce=n, path=it["tx"]["path"], chunk=it["tx"]["chunk"], status=st,
                          gasUsed=gu, block=int(r["blockNumber"], 16), bytes=it["tx"]["bytes"])
            for o in it["hashes"]:
                if o != h:
                    journal.write(t="dropped", hash=o, nonce=n, why="replaced")
            mined += 1
            gas_used += gu
            if st != 1 and stop is None:
                stop = "tx %s (nonce %d, %s chunk %d) REVERTED" % (h, n, it["tx"]["path"], it["tx"]["chunk"])
            if a.progress and mined % a.progress == 0:
                print("  mined %d/%d tx, gas %d, %.1f tx/s" % (mined, ntx, gas_used, mined / (time.time() - t0)))
        # stuck handling for the oldest in-flight nonce; anything unclear ends the run (exit 4) and leaves the
        # unresolved hashes in the journal, so the next run's reconcile (chain state) decides
        if inflight:
            n0, it = next(iter(inflight.items()))
            age = time.time() - it["at"]
            if age > a.stuck_timeout:
                latest_n = int(rpc.call("eth_getTransactionCount", sender, "latest"), 16)
                in_pool = any(rpc.call("eth_getTransactionByHash", h) for h in it["hashes"])
                if latest_n > n0:
                    if age > 2 * a.stuck_timeout:
                        abandon = "nonce %d was consumed but none of its %d hash(es) has a receipt" % (n0, len(it["hashes"]))
                elif not in_pool:
                    if it["rebroadcast"] < 3:
                        err = broadcast(it["raw"])
                        print("  nonce %d not in pool after %d s: rebroadcast%s" % (n0, age, (" failed: " + err) if err else ""))
                        it["rebroadcast"] += 1
                        it["at"] = time.time()
                    else:
                        abandon = "nonce %d dropped from the pool and 3 rebroadcasts did not stick" % n0
                elif a.bump and age > 2 * a.stuck_timeout:
                    tp, mf = it["fee"]
                    tp, mf = max(tp * 5 // 4 + 1, tp + 1), mf * 5 // 4 + 1
                    if mf > a.fee_cap_wei:
                        abandon = "nonce %d stuck and the fee cap is reached" % n0
                    else:
                        raw, h = signer.sign(chain_id, n0, tp, mf, it["tx"]["gas"], store, it["tx"]["data"])
                        journal.write(t="sent", nonce=n0, hash=h, path=it["tx"]["path"], chunk=it["tx"]["chunk"],
                                      of=it["tx"]["of"], bytes=it["tx"]["bytes"], gas=it["tx"]["gas"], maxFee=mf,
                                      replaces=it["hashes"][-1])
                        if not broadcast(raw):
                            it["hashes"].append(h)
                            it["raw"], it["fee"], it["at"] = raw, (tp, mf), time.time()
                            print("  nonce %d fee bumped to %d wei" % (n0, mf))
                if age > a.give_up and not abandon:
                    abandon = "nonce %d pending for %d s (pass --bump to raise the fee)" % (n0, age)
        if abandon:
            break
    dt = time.time() - t0
    print("sent %d tx, mined %d, gas used %d, %.0f s" % (sent, mined, gas_used, dt))
    if abandon:
        print("STOPPED: %s; %d tx left unresolved in the journal. Re-run upload: it reconciles them first." % (
            abandon, len(inflight)))
        sys.exit(4)
    if stop:
        print("STOPPED: " + stop)
        sys.exit(2 if "REVERTED" in stop or "failed" in stop else 4)
    print("upload complete; run verify")


# ================================================================ verify


def cmd_verify(a):
    plan = load_plan(a.plan)
    rpc = RPC(a.rpc)
    chain_id = int(rpc.call("eth_chainId"), 16)
    if chain_id != plan["chainId"]:
        die("RPC chain %d differs from the plan's chain %d" % (chain_id, plan["chainId"]))
    block = int(rpc.call("eth_blockNumber"), 16)
    site = Site(rpc, plan["store"], plan["container"], hex(block))  # every read pinned to one block (TAP-10 §7.1)
    files = [f for f in plan["files"] if not a.only or re.search(a.only, f["path"])]
    infos = site.file_info_many([f["path"] for f in files])
    report, bad = [], 0
    cache = {}
    for i, (f, oc) in enumerate(zip(files, infos)):
        if i % 200 == 0 and not a.no_bytes:  # batch-read the next 200 small files (bounded memory)
            small = [g["path"] for g, o in zip(files[i:i + 200], infos[i:i + 200]) if o["chunkCount"] and o["size"] <= READ_ONE]
            cache = dict(zip(small, site.read_small_many(small)))
        probs = []
        data = None
        try:
            data = local_bytes(plan, f) if not a.no_local_check else None
        except SystemExit:
            probs.append("local file changed")
        if oc["chunkCount"] == 0:
            probs.append("missing")
        else:
            if oc["size"] != f["size"]:
                probs.append("size %d != %d" % (oc["size"], f["size"]))
            if oc["sha256"].lower() != f["sha256"].lower():
                probs.append("declared sha256 differs")
            if oc["contentType"] != f["contentType"]:
                probs.append("contentType %r != %r" % (oc["contentType"], f["contentType"]))
            if not a.no_bytes and oc["size"] <= MAX_SIZE:
                got = cache.get(f["path"])
                if got is None:
                    got = site.read_bytes(f["path"], oc["size"])
                if isinstance(got, RpcError):
                    probs.append("read failed: " + got.message[:80])
                    got = b""
                if len(got) != oc["size"]:
                    probs.append("read %d bytes, declared %d" % (len(got), oc["size"]))
                if "0x" + hashlib.sha256(got).hexdigest() != f["sha256"].lower():
                    probs.append("bytes sha256 mismatch")
        if probs:
            bad += 1
            print("  FAIL %s: %s" % (f["path"], "; ".join(probs)))
        report.append({"path": f["path"], "ok": not probs, "problems": probs, "size": f["size"], "sha256": f["sha256"],
                       "onchain": oc})
    out = {"chainId": chain_id, "container": plan["container"], "store": plan["store"], "block": block,
           "checked": len(files), "failed": bad, "bytesRead": not a.no_bytes, "files": report}
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(out, fh, indent=1)
    print("verify at block %d: %d file(s), %d ok, %d failed%s" % (block, len(files), len(files) - bad, bad,
                                                                  "" if not a.report else "  report " + a.report))
    sys.exit(1 if bad else 0)


# ================================================================ lock-checklist


def find_creation_block(rpc, addr, hi):
    lo = 0
    if rpc.call("eth_getCode", addr, hex(hi)) in ("0x", "0x0"):
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if rpc.call("eth_getCode", addr, hex(mid)) in ("0x", "0x0"):
            lo = mid + 1
        else:
            hi = mid
    return lo


def get_logs(rpc, addr, topics, frm, to, step, batch=20):
    """eth_getLogs in windows of `step` blocks, `batch` windows per HTTP request (rpc.xlayer.tech allows 100)."""
    wins = [(x, min(to, x + step - 1)) for x in range(frm, to + 1, step)]
    out = []
    for i in range(0, len(wins), batch):
        part = wins[i:i + batch]
        res = rpc.batch([("eth_getLogs", [{"address": addr, "topics": topics, "fromBlock": hex(x), "toBlock": hex(y)}])
                         for x, y in part], size=batch)
        for r in res:
            if isinstance(r, RpcError):
                raise r
            out += r
    return out


def cmd_lock(a):
    rpc = RPC(a.rpc)
    chain_id = int(rpc.call("eth_chainId"), 16)
    cfg = CHAINS.get(chain_id, {})
    store = a.store or cfg.get("store") or die("pass --store")
    binding = a.binding or cfg.get("binding") or die("pass --binding")
    C = ethcrypto.to_checksum(a.container)
    ok = True

    def check(cond, text):
        nonlocal ok
        print("  [%s] %s" % ("ok" if cond else "!!", text))
        ok = ok and bool(cond)

    head = int(rpc.call("eth_blockNumber"), 16)
    now = int(rpc.call("eth_getBlockByNumber", hex(head), False)["timestamp"], 16)
    tchain, proc, tid, holder = container_token(rpc, C)
    print("lock checklist  chain %d  block %d  container %s" % (chain_id, head, C))
    print("  circuit %s #%d  chainId in token() %d  holder %s" % (proc, tid, tchain, holder))
    if cfg.get("opener"):
        acct = dec(["address"], rpc.eth_call(cfg["opener"], calldata("accountOf(address,uint256)", ["address", "uint256"],
                                                                       [proc, tid])))[0]
        check(acct.lower() == C.lower() and tchain == chain_id, "opener.accountOf(processor, #%d) == container (TAP-10 §4.3)" % tid)
    impl = store_impl(rpc, store)
    check(impl.lower() == cfg.get("store_impl", impl).lower(), "site store implementation %s is the one this tool was tested against" % impl)
    site = Site(rpc, store, C)
    op, until = site.operator()
    check(op.lower() == ZERO, "operatorOf(container) == 0 (now %s; operatorUntil %d, %s)" % (
        op, until, "in the past" if until <= now else "IN THE FUTURE"))
    # last OperatorSet events, to name any operator address (informational)
    state = dec(["uint256"], rpc.eth_call(C, "0x" + sel("state()").hex()))[0]
    if state == 0 and not a.scan_logs:
        check(True, "container state() == 0: it has never executed a call, so it cannot have granted ApprovalForAll")
    else:
        start = find_creation_block(rpc, C, head) or 0
        print("  container state() = %d; scanning ApprovalForAll logs from block %d (%d blocks) ..." % (state, start, head - start))
        t_afa = topic("ApprovalForAll(address,address,bool)")
        owner_topic = "0x" + "00" * 12 + C[2:].lower()
        logs = get_logs(rpc, proc, [t_afa, owner_topic], start, head, a.log_step)
        ops = {"0x" + lg["topics"][2][-40:] for lg in logs}
        live = [o for o in ops if dec(["bool"], rpc.eth_call(proc, calldata(
            "isApprovedForAll(address,address)", ["address", "address"], [C, o])))[0]]
        check(not live, "no ApprovalForAll from the container on the processor (%d event(s); live: %s)" % (
            len(logs), ", ".join(live) or "none"))
    appr = dec(["address"], rpc.eth_call(proc, calldata("getApproved(uint256)", ["uint256"], [tid])))[0]
    check(appr.lower() == ZERO, "getApproved(#%d) == 0 (%s); cleared on transfer anyway" % (tid, appr))
    paid = dec(["uint256"], rpc.eth_call(binding, calldata("containerPaidUntil(address)", ["address"], [C])))[0]
    fee = dec(["uint256"], rpc.eth_call(binding, "0x" + sel("monthlyFee()").hex()))[0]
    print("  containerPaidUntil %d (%s UTC), monthlyFee %d wei" % (paid, time.strftime("%Y-%m-%d", time.gmtime(paid)), fee))
    months = 0
    if a.name:
        def can_bind(m):
            try:
                rpc.eth_call(binding, calldata("bind(string,address,uint256)", ["string", "address", "uint256"], [a.name, C, m]),
                             frm=holder, value=m * fee)
                return True
            except RpcError:
                return False
        lo, hi = 0, 121
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if can_bind(mid):
                lo = mid
            else:
                hi = mid
        months = lo
        check(months > 0 or paid - now > 3000 * 86400, "bind(%s) from the holder accepts up to %d more month(s) now (eth_call)" % (a.name, months))
    else:
        print("  (pass --name <on-chain name> to compute how many months can still be bound)")
    # files sanity
    try:
        n = site.view("pathCount(address)", ["address"], [C], ["uint256"])[0]
        fb = site.view("fallbackPath(address)", ["address"], [C], ["string"])[0]
        print("  site has %d path(s); fallbackPath %r" % (n, fb))
    except RpcError:
        pass
    if a.lock:
        L = ethcrypto.to_checksum(a.lock)
        code = rpc.call("eth_getCode", L, "latest")
        if code in ("0x", "0x0"):
            check(False, "lock %s has code" % L)
        else:
            def lv(sig, t):
                return dec([t], rpc.eth_call(L, "0x" + sel(sig).hex()))[0]
            check(lv("processor()", "address").lower() == proc.lower(), "lock.processor() == %s" % proc)
            check(lv("circuitId()", "uint256") == tid, "lock.circuitId() == %d" % tid)
            check(lv("container()", "address").lower() == C.lower(), "lock.container() == container")
            check(lv("binding()", "address").lower() == binding.lower(), "lock.binding() == %s" % binding)
            if a.name:
                check(lv("onChainName()", "string") == a.name, "lock.onChainName() == %s" % a.name)
    else:
        L = "<TapContainerLock address>"
        print("  (pass --lock <address> to check a deployed TapContainerLock)")
    rpc_hint = a.rpc if not is_anvil(rpc) else cfg.get("rpc", "$RPC")
    print("\nCommands to run yourself as the holder %s (NOT executed; test each on a fork first):" % holder)
    if op.lower() != ZERO or until > now:
        print("  cast send %s 'setOperator(address,address,uint256)' %s %s 0 --rpc-url %s --account <holder>" % (store, C, ZERO, rpc_hint))
    m = months or 120
    print("  cast send %s 'bind(string,address,uint256)' %s %s %d --value %d --rpc-url %s --account <holder>" % (
        binding, a.name or "<on-chain name>", C, m, m * fee, rpc_hint))
    print("  cast send %s 'safeTransferFrom(address,address,uint256)' %s %s %d --rpc-url %s --account <holder>" % (
        proc, holder, L, tid, rpc_hint))
    print("  # afterwards: cast call %s 'locked()(bool)' --rpc-url %s   -> true" % (L, rpc_hint))
    print("\nchecklist: %s" % ("PASS" if ok else "FAIL"))
    sys.exit(0 if ok else 1)


# ================================================================ CLI


def main(argv=None):
    p = argparse.ArgumentParser(prog="tapup", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rpc", default=os.environ.get("TAPUP_RPC"), help="JSON-RPC URL (env TAPUP_RPC)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def sender_opts(s):
        s.add_argument("--key-env", default="TAPUP_PRIVATE_KEY", help="env var holding the hex private key")
        s.add_argument("--keystore-account", help="Foundry keystore name; decrypted once by cast (password prompt)")
        s.add_argument("--keystore-dir")
        s.add_argument("--allow-env-password", action="store_true", help="let cast read CAST_UNSAFE_PASSWORD")
        s.add_argument("--yes", action="store_true", help="do not ask for confirmation")
        s.add_argument("--live", action="store_true", help="required to send to a non-anvil node")
        s.add_argument("--tip-wei", type=int)
        s.add_argument("--max-fee-wei", type=int)
        s.add_argument("--accept-impl", help="accept this (changed) site store implementation address")

    s = sub.add_parser("plan", help="walk a directory and compare with the chain")
    s.add_argument("dir")
    s.add_argument("--container", required=True)
    s.add_argument("--store")
    s.add_argument("--prefix", default="", help="path prefix inside the site, e.g. meta")
    s.add_argument("--type", action="append", default=[], help="override content type: .ext=type/subtype")
    s.add_argument("--out", default="tapup-plan.json")
    s.add_argument("--accept-impl")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("operator", help="show, set or clear the site operator (holder only)")
    s.add_argument("action", choices=["show", "set", "clear"])
    s.add_argument("--container", required=True)
    s.add_argument("--store")
    s.add_argument("--op", help="operator address (set)")
    s.add_argument("--ttl", type=int, default=86400, help="seconds, max %d" % MAX_TTL)
    s.add_argument("--unlocked", help="anvil only: send from this unlocked/impersonated address")
    sender_opts(s)
    s.set_defaults(fn=cmd_operator)

    s = sub.add_parser("upload", help="send putFile/appendChunk for every file that differs")
    s.add_argument("--plan", required=True)
    s.add_argument("--journal", required=True)
    s.add_argument("--concurrency", type=int, default=8, help="max unconfirmed tx in flight")
    s.add_argument("--poll", type=float, default=1.0)
    s.add_argument("--retries", type=int, default=5)
    s.add_argument("--stuck-timeout", type=float, default=90)
    s.add_argument("--give-up", type=float, default=1800, help="end the run if one tx stays pending this long (s)")
    s.add_argument("--bump", action="store_true", help="replace a stuck tx with a 25%% higher fee")
    s.add_argument("--fee-cap-wei", type=int, default=10 ** 9, help="never bump maxFeePerGas above this")
    s.add_argument("--pending-wait", type=int, default=300, help="seconds to wait for journaled pending tx")
    s.add_argument("--ack-reverts", action="store_true")
    s.add_argument("--ignore-balance", action="store_true")
    s.add_argument("--only", help="regex: only paths matching")
    s.add_argument("--progress", type=int, default=50)
    s.add_argument("--max-tx", type=int, default=0, help=argparse.SUPPRESS)  # test hook: stop after N sends
    sender_opts(s)
    s.set_defaults(fn=cmd_upload)

    s = sub.add_parser("verify", help="read every file back and compare size and SHA-256")
    s.add_argument("--plan", required=True)
    s.add_argument("--report")
    s.add_argument("--only")
    s.add_argument("--no-bytes", action="store_true", help="check fileInfo only, do not download")
    s.add_argument("--no-local-check", action="store_true")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("lock-checklist", help="read-only checks before locking; prints the commands")
    s.add_argument("--container", required=True)
    s.add_argument("--store")
    s.add_argument("--binding")
    s.add_argument("--name", help="on-chain name, e.g. 1.2.282.tape")
    s.add_argument("--lock", help="deployed TapContainerLock address")
    s.add_argument("--log-step", type=int, default=100, help="blocks per eth_getLogs window")
    s.add_argument("--scan-logs", action="store_true", help="scan logs even when container state() == 0")
    s.set_defaults(fn=cmd_lock)

    a = p.parse_args(argv)
    if not a.rpc:
        die("pass --rpc or set TAPUP_RPC")
    if getattr(a, "action", None) == "set" and not a.op:
        die("operator set needs --op")
    a.fn(a)


if __name__ == "__main__":
    main()
