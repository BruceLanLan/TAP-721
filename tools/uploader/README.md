# tapup — batch uploader for a TapeOut container's site store

`tapup.py` writes many files into a container's TAP-10 `SiteRegistry` (`putFile` + `appendChunk`), resumes after
any interruption without re-sending what is already on chain, verifies every byte afterwards, and prepares the
locking step (`TapContainerLock`, see `DESIGN.md` §0). Python 3.9+ standard library only; `cast` (Foundry) is
used only to decrypt a keystore if you choose that signer, `anvil`/`forge` only for the tests.

| File | What |
|---|---|
| `tapup.py` | CLI: `plan`, `operator {show,set,clear}`, `upload`, `verify`, `lock-checklist` |
| `ethcrypto.py` | Keccak-256, secp256k1 (RFC 6979), RLP, EIP-1559 signing (checked against `cast keccak` / `cast decode-transaction`) |
| `test_e2e.py` | End-to-end test on an anvil fork of X Layer (36 checks) |

## Usage

```sh
export TAPUP_RPC=https://rpc.xlayer.tech       # or a private X Layer endpoint (public one: batch ≤ 10, getLogs ≤ 100 blocks)
C=0xa8edd3b032d33aa0657a3e151a7f8c3e5f71f6b9   # container of circuit #1 of processor 0x8E0b…60cF (1.2.282.tape)

# 1. plan (read-only): hashes every file, reads fileInfo for every path, marks new / replace / partial / skip
python3 tapup.py plan ./out --container $C --prefix "" --out plan.json [-v] [--type .tapnet=application/octet-stream]

# 2. operator: the holder lets a hot wallet upload for at most 30 days
python3 tapup.py operator show --container $C
python3 tapup.py operator set  --container $C --op 0xHOT… --ttl 86400 --keystore-account holder --live
# 3. upload from the hot wallet (resumable; same journal every time)
export TAPUP_PRIVATE_KEY=…    # hot wallet only; read once and removed from the environment
python3 tapup.py upload --plan plan.json --journal upload.jsonl --concurrency 8 --live
# 4. verify every file (fileInfo + bytes read back, all at one pinned block); exit 1 on any mismatch
python3 tapup.py verify --plan plan.json --report verify.json
# 5. clear the operator, then the read-only lock checklist (prints, never runs, the bind/transfer commands)
python3 tapup.py operator clear --container $C --keystore-account holder --live
python3 tapup.py lock-checklist --container $C --name 1.2.282.tape --lock 0xLOCK…
```

Paths are the files' paths relative to the directory, optionally under `--prefix`. Content type comes from the
extension; a file with no extension (e.g. `meta/1`) is `application/json` when it parses as JSON, else
`application/octet-stream`. Hidden files are skipped; paths that TAP-10 §7.2 readers would mangle (`?`, `#`, `%`,
`.`/`..` segments, non-NFC) and files over 8,400,000 bytes are rejected by `plan`.

### How `upload` stays safe and resumable

- **The chain decides what to send.** Each run re-reads `fileInfo` for every path: matching sha256 + size +
  content type → skip; same declared sha256, size = k × 24,000 and the on-chain prefix hashes equal to the local
  prefix → resume with `appendChunk(k)`; anything else → `putFile` (replace). The plan's status is only a preview.
- **Journal (JSONL, fsync per line).** A header pins chain id, store, container, sender and anvil-vs-live; a
  different plan/container/chain/sender is refused. Every tx is journaled as `sent` (hash computed locally)
  *before* it is broadcast, then `mined` / `dropped` / `failed`. On restart, unresolved hashes are reconciled
  first (receipt → mined; still in the pool → wait; absent → dropped) before any new nonce is used.
- **Nonces** are allocated locally from `latest` (a run refuses to start if the sender has pending tx that the
  journal does not know). At most `--concurrency` tx are unconfirmed; chunks of one file go out in nonce order so
  `appendChunk`'s `expectIndex` always holds.
- **Gas limits** come from the measured model below × 1.25 (no `estimateGas`: chunk k+1 cannot be estimated
  before chunk k is mined). Fees are `2 × baseFee + tip`, refreshed every 60 s; a tx missing from the pool is
  rebroadcast (3×), and `--bump` replaces a stuck one with +25 % fee up to `--fee-cap-wei`. If a nonce is
  consumed without a receipt we know of, rebroadcasts fail, the fee cap is hit, or one tx stays pending longer
  than `--give-up` (1,800 s), the run ends with exit 4 and leaves the hashes unresolved; the next run reconciles them.
- Keep `--concurrency` ≤ 16 on X Layer (OP-stack txpool per-account slots); the default 8 is safe.
- **Stops on any revert** (exit 2) after collecting receipts for what is already in flight, and names each
  reverted tx. A re-run refuses until you pass `--ack-reverts`. RPC failures retry with exponential backoff.
- Refuses to send to a non-anvil node without `--live`, asks for `yes` unless `--yes`, checks
  `canEdit(container, sender)` and the balance against the worst case first, and refuses if the site store's
  ERC-1967 implementation differs from the one tested here (`0xa85c…a45f`; `--accept-impl` after re-testing).

## Safety notes

1. **Test on a fork first**, with the real files: `anvil --fork-url https://rpc.xlayer.tech --hardfork cancun
   --gas-limit 210000000`, impersonate the holder, run plan → operator → upload → verify. A plan made on anvil is
   refused on a live node and vice versa (both report chain id 196).
2. **Keys.** The holder key never needs to be hot: use it (keystore or hardware wallet via your own `cast send`)
   only for `operator set/clear`, `bind` and the final transfer. The uploader key comes from `TAPUP_PRIVATE_KEY`
   (or `--key-env NAME`) and is deleted from the environment at start-up, or from a Foundry keystore decrypted
   once by `cast wallet decrypt-keystore` (you type the password). Never on the command line, never on disk.
   Fund the hot wallet with just the plan's estimate plus margin.
3. **Operator TTL.** `setOperator` rejects TTLs above 30 days (2,592,000 s, `TooLarge`). Use the shortest TTL
   that covers the upload; renew with another `operator set` if needed. Only the holder can set it.
4. **Clear the operator before locking** (`operator clear` → `operatorOf == 0`, `operatorUntil == 0`).
   `lock-checklist` fails while an operator is live. Then `bind` the maximum months and `safeTransferFrom` the
   circuit to a `TapContainerLock` — the checklist prints the exact commands; it never runs them.
5. Partially uploaded files are visible on chain as `incomplete` (size short of the declared hash) until their
   last chunk lands; run `verify` before announcing anything.

## Measured on the anvil fork (X Layer block ~73,489,000, `--hardfork cancun`)

gasUsed from receipts of the e2e run (61 `putFile`, 35 `appendChunk`):

| Call | Model | Examples |
|---|---|---|
| `putFile`, new path | ≈ 296,000 + 217 × bytes | 0 B 300k · 1,297 B 581k · 24,000 B 5.50 M |
| `putFile`, existing path (replace) | ≈ 160,000 + 217 × bytes | 250 B 214k |
| `appendChunk` | ≈ 174,000 + 217 × bytes | 1 B 175k · 4,000 B 1.04 M · 24,000 B 5.38 M |
| `setOperator` | ≈ 97k–119k | |

A file of n bytes costs about 296k + 174k × (chunks − 1) + 217 × n gas (DESIGN.md's mainnet 24 KB figure,
5.58 M, matches within 2 %). At X Layer's 0.02 gwei (2026-10-18): a 1 KB JSON ≈ 0.51 M gas ≈ 0.00001 OKB;
10,000 × 1 KB ≈ 0.10 OKB; 10,000 × 50 KB images ≈ 1.15 × 10¹¹ gas ≈ 2.3 OKB. `plan` prints the estimate with the
live gas price and the OP-stack L1 data fee (GasPriceOracle; currently 0 on X Layer). The anvil fork reports
~1 gwei gas price, so fork cost figures are 50× too high — only gas is meaningful there.

Throughput: one block holds ~38 full-chunk tx (210 M gas). Pure-Python signing takes ~0.17 s for a 24 KB
chunk (≈ 0.01 s for small files); in-flight tx are capped by `--concurrency`, so expect roughly
concurrency ÷ block time tx/s. The public RPC accepts at most 10 calls per batch (the tool adapts), so `plan`
and `verify` of 20,000 files take a few thousand requests; a private endpoint is faster.

## Site store behaviour observed on the fork

- `fileInfo.size` is the number of bytes uploaded so far, while `sha256Hash` is the full-file hash declared by
  `putFile`; `FileSet` is emitted on every chunk with the running size (indexers see one event per chunk).
- `putFile` on an existing path resets it to one chunk (old chunks are orphaned) and costs ~136k less than a new path.
- `appendChunk` needs `expectIndex == chunkCount` (`BadIndex`), rejects > 24,000 bytes (`TooLarge`), but does not
  require earlier chunks to be full and never records a declared total: completeness is only "size and SHA-256 match".
- Empty files are allowed (`chunkCount` 1, size 0).
- `operatorOf` returns 0 once the TTL passes, but `operatorUntil` keeps the old timestamp (mainnet today:
  operator 0, until 1,791,718,710). An operator cannot set operators, and is no longer valid after the circuit
  NFT changes hands.
- The container's ERC-6551 `state()` counts `execute` calls; it is 0 on mainnet, so the container has never
  granted any ERC-721 approval. `lock-checklist` uses this and scans `ApprovalForAll` logs (100-block windows)
  only when `state() > 0` or `--scan-logs`.
- `bind` from the holder currently accepts up to 108 more months (paid until 2027-10-01, ten-year cap).

## Tests

```sh
python3 test_e2e.py [--work DIR] [--keep-anvil]
```
Starts its own anvil fork on a free port and kills it at the end. Generates 49 files (20 extensionless JSON,
one extensionless non-JSON, 15 PNG-like files from 10 B to 150,000 B incl. 24,000/24,001/100,000 B, 12 `.tapnet`,
one empty file, a skipped `.DS_Store`), then: plan → operator set from the impersonated holder → refusals
(no key, non-holder, TTL > 30 d) → a deliberately partial file resumed with `appendChunk` → upload under 1 s
interval mining killed with SIGKILL while a tx is unresolved → resume (journal reconciled, no chunk mined twice,
successful tx = total chunks) → third run sends nothing → verify → on-chain tamper detected, re-planned as
replace and fixed → journal/plan mismatch refusals → keystore signer → revert mid-upload (holder clears the
operator with tx in flight: exit 2, re-run needs `--ack-reverts`) → operator clear → `TapContainerLock` deployed
on the fork → `lock-checklist` PASS → the printed `bind` and `safeTransferFrom` executed on the fork →
`locked() == true` and the old holder can no longer set an operator.
