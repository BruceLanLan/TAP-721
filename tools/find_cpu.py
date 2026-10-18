import sys
from rpc import batch, batch_chunked, eth_call
url, factory, target = sys.argv[1], sys.argv[2], sys.argv[3].lower()
n = int(batch(url, [eth_call(factory, "0xa94da8a7")])[0], 16)
for start in range(0, n, 100):
    idx = range(start, min(n, start + 100))
    res = batch_chunked(url, [eth_call(factory, "0x4bc7cbbd" + i.to_bytes(32, "big").hex()) for i in idx])
    for i, r in zip(idx, res):
        if r is None: print("null at", i)
        if r and "0x" + r[-40:] == target:
            print("processor number", i, "of", n); sys.exit()
print("not found among", n)
