# TapeCode-Test1 valid token set

Read-only snapshot of which TapeCode-Test1 tokens (X Layer, chainId 196) sit at a black-hole address
and which are valid, plus a canonical commitment to the valid set.

- Collection: `0x0e91460d6823c711643e650a9a4c0cc21de41614` (ERC-721, ids 1..10000, `MAX_SUPPLY` = `totalSupply` = 10000, deployed at block 72,863,247)
- Pinned block: **73,520,053**, hash `0x567a1b212d8ff2cb2e2131ce83434e05871bcb7d927d172deb40157b1a2e7f64`, 2026-10-18T02:04:49Z
- Result: **3,000** tokens owned by `0x000000000000000000000000000000000000dEaD`, **7,000** valid. No other black hole found.
- `tokenSetHash` = `0x01cca77378b49feefc5db9218230922d61193a70780dcb04f232ba4da6000222`

## Files

| file | content |
|---|---|
| `owners.json` | `ownerOf(id)` for all 10,000 ids at the pinned block (from rpc.xlayer.tech) |
| `owner_classes.json` | every distinct owner (5,321): code size, burn-like pattern flag, EIP-7702 delegate, `token()`/`owner()` probes for contracts |
| `crosscheck.json` | 250 random ids (seeded by block hash) re-read on a second operator |
| `transfers_sample.json` | arrival of the black-hole tokens: for one id in each contiguous run, the first block where it is owned by 0xdEaD, plus that block's Transfer logs |
| `tokens.json` | the result: block info, `blackHoleAddresses` with evidence, `validTokenIds`, `excludedTokenIds`, `tokenSetHash` |
| `tokens.bin` | 28,000 bytes = `u32be(id)` for each valid id, ascending |

In the public repository `owners.json`, `owner_classes.json` and `transfers_sample.json` (per-token holder
addresses) are not included; regenerate them with the commands below. SHA-256 of the files used to build
`tokens.json`:

| file | sha256 |
|---|---|
| `owners.json` | `1dd39688e2eaafe99c26d6ff25f44bf297acb514f43f7537303ef2b1d0ee0f51` |
| `owner_classes.json` | `dd9cb0b9dae4997f2c6867c74283ed77e07e9eba055a90f056f21b8047603c2d` |
| `transfers_sample.json` | `8fbc5e8b69c0ea8008ce0ac7a404d13fd108e0fb2cd9a366d91360da2c88a24d` |

## Method

1. `scan_owners.py` pins block B = latest - 64, then calls `ownerOf(id)` for ids 1..10000 at B
   (batches of 10, throttled, exponential backoff on 403/429). No call reverted: all 10,000 tokens exist.
2. `classify_owners.py` gets `eth_getCode` at B for each distinct owner, flags burn-like addresses
   (value < 2^32, `dead` prefix/suffix, `0x0…01`, ≤2 distinct hex digits), probes contracts for
   ERC-6551 `token()` and `owner()`, and re-reads 250 random ids on xlayerrpc.okx.com
   (0 mismatches, same block hash). xlayer.drpc.org returned HTTP 500 for historical `eth_call` at B.
3. `sample_arrivals.py` binary-searches `ownerOf` (archive `eth_call` on okx) to find when one id in each
   contiguous excluded run first became owned by 0xdEaD. It then reads `Transfer(to=0xdEaD)` logs. A single
   100-block `eth_getLogs` over 72,890,740..72,890,839 returns **3,000 logs for 3,000 distinct ids in 7 txs**.
   All 7 come from `0x70d23972688d5e079b9a2fa877142a05cac00d3d` in blocks 72,890,789..72,890,800
   (2026-10-10 19:17:05..19:17:16 UTC). The tx hashes are in `tokens.json` under `blackHoleAddresses[0].arrivals`.
   (`scan_transfers.py` is an optional full-history log scan via drpc. rpc.xlayer.tech and okx cap `getLogs` at
   100 blocks, and drpc rejects large responses, so the full scan is slow. It was not needed for the result.)
4. `build_tokenset.py` writes `tokens.json` / `tokens.bin`.

### Black-hole candidates examined

- `0x…dEaD` holds 3,000 tokens (`balanceOf` = 3000 agrees). No code, nonce 0. It is the standard burn address and
  nobody is known to hold its key. The collection is not a proxy (EIP-1967 slot empty). Its bytecode has no
  DELEGATECALL or SELFDESTRUCT. The only functions that change state are the ERC-721 approve/transfer set,
  `claim()`, `setBaseURI` and `freezeBaseURI`. No admin path can move a token, so nothing can leave 0xdEaD.
  This was also simulated with read-only `eth_call` at B: `transferFrom(0xdEaD, …, 4800)` reverts `NotAuthorized`
  when sent from the collection `owner()` (`0xa8Ed…F6B9`) and from a random address. It succeeds only with
  `from = 0xdEaD`. `getApproved` is zero on the sampled excluded ids.
  **Black hole.**
- The zero address, `0x…0001`-style addresses and other burn-like patterns own no tokens.
- 80 owners have code. All 80 are 23-byte EIP-7702 delegation designators (`0xef0100…`) pointing to
  `0xe40ccb2d94975c51bff0c004efdfd9b3a5796fa4`. These are normal EOAs with a smart-wallet delegate, and the
  EOA key can always sign, so they can transfer. Together they hold 93 tokens, all valid. None is an ERC-6551
  account (`token()` reverts) and none is a container contract.
- The other 5,240 owners are plain EOAs: valid.

The 3,000 excluded ids fall in 10 contiguous runs from 4692 to 7785 (see `excludedTokenIds`).

## Re-check

```sh
cd tools/tokenset
python3 scan_owners.py --block 73520053          # writes owners.json (~10 min, rate-limited RPC)
python3 classify_owners.py                       # owner_classes.json, crosscheck.json
python3 sample_arrivals.py                       # transfers_sample.json (needs tokens.json from a first build)
python3 build_tokenset.py                        # tokens.json, tokens.bin, prints tokenSetHash
shasum -a 256 tokens.bin                         # must equal tokenSetHash (shasum prints it without the 0x prefix)
# spot check one id by hand:
cast call 0x0e91460d6823c711643e650a9a4c0cc21de41614 'ownerOf(uint256)(address)' 4800 \
  --rpc-url https://xlayerrpc.okx.com --block 73520053
```

You can recompute the hash on its own, with no RPC:
`python3 -c 'import json,hashlib,struct;v=json.load(open("tokens.json"))["validTokenIds"];print(hashlib.sha256(b"".join(struct.pack(">I",i) for i in v)).hexdigest())'`

Python 3 stdlib only. `cast` (Foundry) is optional and only needed for manual spot checks.
