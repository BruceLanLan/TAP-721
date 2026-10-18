"""Keccak-256, secp256k1 ECDSA (RFC 6979), RLP and EIP-1559 transaction signing. Python 3.9 stdlib only.

The private key lives only in process memory (an int); nothing here reads or writes files.
"""
import hashlib
import hmac

# ---------------------------------------------------------------- Keccak-256 (original padding 0x01, not SHA3)

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B,
    0x0000000080000001, 0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088,
    0x0000000080008009, 0x000000008000000A, 0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
    0x8000000000008003, 0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25, 39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14]
_M = 0xFFFFFFFFFFFFFFFF
# pi step: B[y, 2x+3y] = rot(A[x, y]); index = x + 5y
_PI = [0] * 25
for _x in range(5):
    for _y in range(5):
        _PI[_x + 5 * _y] = _y + 5 * ((2 * _x + 3 * _y) % 5)


def _f(A):
    M, ROT, PI = _M, _ROT, _PI
    for rc in _RC:
        C = [A[x] ^ A[x + 5] ^ A[x + 10] ^ A[x + 15] ^ A[x + 20] for x in range(5)]
        D = [C[(x - 1) % 5] ^ (((C[(x + 1) % 5] << 1) | (C[(x + 1) % 5] >> 63)) & M) for x in range(5)]
        B = [0] * 25
        for i in range(25):
            a = A[i] ^ D[i % 5]
            r = ROT[i]
            B[PI[i]] = ((a << r) | (a >> (64 - r))) & M if r else a
        for y in range(0, 25, 5):
            b0, b1, b2, b3, b4 = B[y], B[y + 1], B[y + 2], B[y + 3], B[y + 4]
            A[y] = b0 ^ ((~b1) & b2)
            A[y + 1] = b1 ^ ((~b2) & b3)
            A[y + 2] = b2 ^ ((~b3) & b4)
            A[y + 3] = b3 ^ ((~b4) & b0)
            A[y + 4] = b4 ^ ((~b0) & b1)
        A[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136
    data = bytes(data)
    pad = rate - (len(data) % rate)
    data += b"\x01" + b"\x00" * (pad - 2) + b"\x80" if pad > 1 else b"\x81"
    A = [0] * 25
    fb = int.from_bytes
    for off in range(0, len(data), rate):
        blk = data[off:off + rate]
        for i in range(17):
            A[i] ^= fb(blk[8 * i:8 * i + 8], "little")
        _f(A)
    return b"".join(A[i].to_bytes(8, "little") for i in range(4))


# ---------------------------------------------------------------- secp256k1

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _jdouble(p):
    X, Y, Z = p
    if Y == 0:
        return (0, 0, 0)
    S = 4 * X * Y * Y % P
    M = 3 * X * X % P
    X2 = (M * M - 2 * S) % P
    return (X2, (M * (S - X2) - 8 * Y ** 4) % P, 2 * Y * Z % P)


def _jadd(p, q):
    if p[2] == 0:
        return q
    if q[2] == 0:
        return p
    X1, Y1, Z1 = p
    X2, Y2, Z2 = q
    Z1s, Z2s = Z1 * Z1 % P, Z2 * Z2 % P
    U1, U2 = X1 * Z2s % P, X2 * Z1s % P
    S1, S2 = Y1 * Z2s * Z2 % P, Y2 * Z1s * Z1 % P
    if U1 == U2:
        return _jdouble(p) if S1 == S2 else (0, 0, 0)
    H, R = (U2 - U1) % P, (S2 - S1) % P
    H2 = H * H % P
    H3 = H * H2 % P
    U1H2 = U1 * H2 % P
    X3 = (R * R - H3 - 2 * U1H2) % P
    return (X3, (R * (U1H2 - X3) - S1 * H3) % P, H * Z1 * Z2 % P)


def _mul(k, pt=G):
    acc, add = (0, 0, 0), (pt[0], pt[1], 1)
    while k:
        if k & 1:
            acc = _jadd(acc, add)
        add = _jdouble(add)
        k >>= 1
    if acc[2] == 0:
        raise ValueError("point at infinity")
    zi = pow(acc[2], -1, P)
    return (acc[0] * zi * zi % P, acc[1] * zi * zi * zi % P)


def _rfc6979_k(priv: int, h: bytes):
    x = priv.to_bytes(32, "big")
    hh = (int.from_bytes(h, "big") % N).to_bytes(32, "big")
    V, K = b"\x01" * 32, b"\x00" * 32
    K = hmac.new(K, V + b"\x00" + x + hh, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    K = hmac.new(K, V + b"\x01" + x + hh, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    while True:
        V = hmac.new(K, V, hashlib.sha256).digest()
        k = int.from_bytes(V, "big")
        if 1 <= k < N:
            yield k
        K = hmac.new(K, V + b"\x00", hashlib.sha256).digest()
        V = hmac.new(K, V, hashlib.sha256).digest()


def sign_hash(priv: int, h: bytes):
    """Return (yParity, r, s) with low s."""
    z = int.from_bytes(h, "big")
    for k in _rfc6979_k(priv, h):
        Rx, Ry = _mul(k)
        r = Rx % N
        if r == 0:
            continue
        s = pow(k, -1, N) * (z + r * priv) % N
        if s == 0:
            continue
        v = (Ry & 1) ^ (1 if Rx >= N else 0) << 1
        if s > N // 2:
            s = N - s
            v ^= 1
        return v, r, s


def address_of(priv: int) -> str:
    if not 1 <= priv < N:
        raise ValueError("invalid private key")
    x, y = _mul(priv)
    raw = keccak256(x.to_bytes(32, "big") + y.to_bytes(32, "big"))[12:]
    return to_checksum(raw.hex())


def to_checksum(addr_hex: str) -> str:
    a = addr_hex.lower().replace("0x", "")
    h = keccak256(a.encode()).hex()
    return "0x" + "".join(c.upper() if int(h[i], 16) >= 8 else c for i, c in enumerate(a))


# ---------------------------------------------------------------- RLP and EIP-1559


def _rlp_len(n, off):
    if n < 56:
        return bytes([off + n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([off + 55 + len(b)]) + b


def rlp(x) -> bytes:
    if isinstance(x, int):
        x = b"" if x == 0 else x.to_bytes((x.bit_length() + 7) // 8, "big")
    if isinstance(x, (bytes, bytearray)):
        x = bytes(x)
        if len(x) == 1 and x[0] < 0x80:
            return x
        return _rlp_len(len(x), 0x80) + x
    if isinstance(x, list):
        body = b"".join(rlp(i) for i in x)
        return _rlp_len(len(body), 0xC0) + body
    raise TypeError(type(x))


def sign_1559(priv: int, chain_id: int, nonce: int, max_priority: int, max_fee: int, gas: int, to: str,
              value: int, data: bytes):
    """Return (raw_tx_bytes, tx_hash_hex)."""
    fields = [chain_id, nonce, max_priority, max_fee, gas, bytes.fromhex(to[2:]), value, data, []]
    v, r, s = sign_hash(priv, keccak256(b"\x02" + rlp(fields)))
    raw = b"\x02" + rlp(fields + [v, r, s])
    return raw, "0x" + keccak256(raw).hex()
