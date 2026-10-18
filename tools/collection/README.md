# TapeCode-Test1 collection generator

Tools that turn the avatar pool and the netlist pool into the manifest, the reveal and the 10,000 per-token
metadata files of TapeCode-Test1 (X Layer 196, `0x0e91460d6823c711643e650a9a4c0cc21de41614`, ids 1..10000,
`tokenURI = baseURI + id`) under the final plan: **7,000 valid tokens** (token set, draft A §5.4; the 3,000
ids held by `0x…dEaD` are excluded and get placeholder metadata), netlist rarity by `RARITY.md` /
`rarity-7000.json` (size rule; 70×1 / 140×2 / 350×3 / 350×6 / 500×7), netlist files ≤ 49,152 bytes.

Python 3.9+, standard library only. Every TAP primitive comes from
`assets/tap-netlist-bound-nft/tapnft.py` (imported, never reimplemented): `check_file`, `file_from_chain`,
`tape_name`, `leaf_hash`, `merkle_root`, `merkle_levels`, `merkle_proof_from_levels`, `merkle_verify`,
`pool_seed`, `permute`, `assignment`, `token_set_file`, `token_set_hash`, `check_token_set`, `token_index`,
`check_manifest`, `check_metadata`, `check_editions`, `check_netlist_against_metadata`. The optional
`tap.pod` (`--pod-snapshot`) is checked with `assets/tap-pod-attributes/pod_validate.py`, which needs
pycryptodome; the final plan's metadata carries no mining state, so it is off by default.

Network access is read-only: HTTP GET to drand relays, `eth_call` for chain reads and the freeze probe.

| File | Role |
|---|---|
| `build_pools.py` | Avatars + design table → `pools.json` + `net/<sha256>.tapnet`; reads the 1,410 files from BSC (cached), checks hashes, N/L, size, quotas; builds minimal `tap.source` incl. `container` |
| `make_manifest.py` | `pools.json` + token set → `manifest.json` (exact bytes, `collection.tokenSet`, `rules`) + `tokenset.bin` |
| `drand.py` | quicknet info (chain hash recomputed), round ↔ time, fetch and verify a beacon |
| `reveal.py` | seed → `tapnft.assignment` → `meta/<id>`, `meta-unrevealed/<id>`, `reveal.json` |
| `verify_collection.py` | Independent checker (directory or base URL) |
| `template.example.json` | Metadata template (replace every `*_CID`, `CONTENT_CIRCUIT_NAME`, gateway host, `content.container`/`name`, `companion.address`) |
| `test_pipeline.py` | Full-size end-to-end test with a real past drand round |
| `RARITY.md`, `rarity-7000.json` | Rarity rule and design table (inputs, committed by hash in `rules`) |
| `verify_function.py` | Functional check of designs against their task reference (rarity eligibility) |

## Inputs

- `images.csv` (or JSON array): `tier` plus `path` (hashed) or `sha256`; optional `ext`. Per-tier counts
  must equal the rarity table's token counts (70 / 280 / 1,050 / 2,100 / 3,500).
- Design table `rarity-7000.json` (default). Each design's file is read at the table's block from the BSC
  archive node (`circuitInfo`, `netlist`, wrapped by `tapnft.file_from_chain`) or from `--netcache`; its
  SHA-256 must equal `netlistSha256` and its NAND/LATCH counts `N`/`L`. `tap.source` = `{chainId 56,
  processor, circuitId, block, name "<id>.<processor number>.tape", container}` with `container =
  opener.accountOf(processor, circuitId)` (BSC opener `0x0217…81f1`, draft A §3.2 item 5). No registrant,
  no mining state.
- Token set: `tools/tokenset/tokens.json` (`validTokenIds`, its `tokenSetHash` re-checked) by default, or
  `--token-set FILE` (`.bin`, id list, or an owners map minus `0x…dEaD`).
- Legacy mode (`--netlists CSV`, quotas from `tct1_quota.py`, range manifest) is kept for other collections.

Pool order, committed by the roots: tiers Mythic→Common, then SHA-256 ascending, copies consecutive.

## Metadata

- Revealed (`meta/<id>` for a valid id): `name`, `description`, `image` (HTTPS gateway), `external_url`,
  `attributes` (Avatar Rarity, Netlist Rarity, NAND, LATCH, Inputs, Outputs, Size), `tap` = `v`, `id`,
  `state:"revealed"`, `manifest`, `image`, `netlist`, minimal `source`, `edition` when shared, `license`,
  `companion`, `content`.
- `tap.content` (collection member; draft A tools ignore it): `{chainId, container, name, paths {image,
  netlist, manifest, metadata}, lock?}` — the content container and this token's paths in it; add `lock`
  (the `TapContainerLock`) once the content circuit is locked.
- Excluded id (in `meta/` and `meta-unrevealed/`): `state:"unrevealed"`, `tap.manifest`, no `tap.image`,
  no `tap.netlist`, attribute `Status: Excluded`.
- Blind box (`meta-unrevealed/<id>` for a valid id): `state:"unrevealed"`, `tap.manifest`, placeholder image.
- States are only `unrevealed` / `revealed`; frozenness is read from chain (`freeze` probe).

## Runbook (dates = profile §5)

| When | Command / action | Publish |
|---|---|---|
| before K2 | `python3 build_pools.py --images images.csv --out work/ --netcache cache/` | nothing yet |
| K1.5 | Deploy the Companion and open the content circuit; put their addresses in `template.json` | — |
| K2, ≥ 72 h before the round | `python3 drand.py round-at 2026-10-31T12:00:00Z`; `python3 make_manifest.py --pools work/pools.json --at 2026-10-31T12:00:00Z --out work/manifest.json --token-set-uri tape://…/tct1/tokenset.bin --token-set-uri ipfs://… --design-table-uri … --rules-doc-uri …` (refuses a round < 72 h away) | **`manifest.json` byte for byte**, `tokenset.bin`, `rarity-7000.json`, `RARITY.md` (container + IPFS); `commitManifest`; the manifestHash. All on chain before the round is produced (§5.1, §6.1) |
| K2 | `python3 reveal.py --manifest work/manifest.json --pools work/pools.json --template template.json --out work --unrevealed-only` | `meta-unrevealed/` → `setBaseURI` (blind box v1). Anyone can check it before the round: `verify_collection.py … --ids 1-10000 --allow-unrevealed` |
| K3 (after the round) | `python3 drand.py fetch <round> --out work/beacon.json`; Companion `reveal(0x<randomness>)`; `python3 reveal.py … --out work --beacon work/beacon.json` | `beacon.json`, `reveal.json` |
| K3 | `python3 verify_collection.py --manifest work/manifest.json --meta work/meta --ids 1-10000 --netlists work/net --reveal work/reveal.json --design-table rarity-7000.json --expect-manifest-sha256 0x…` | — |
| before K4 | Upload `meta/1…10000` (no extension, `application/json`), avatars and `net/` | content container + IPFS |
| K4 | `setBaseURI(<meta dir>/)`; `verify_collection.py --manifest <URL> --base-url <baseURI> --ids 1-10000 --freeze-rpc https://rpc.xlayer.tech` | the verifier command |
| K5 | `freezeBaseURI()`; rerun the verifier with `--freeze-rpc` | — |

The seed is used once; if a script is wrong after the round, fix it and regenerate (the result is unique
for one manifest and round). A different manifest needs a later round announced before the old one.

## drand verification level

Checked: every relay serves the same chain info, and SHA-256(u32be(period) ‖ i64be(genesis) ‖ public key ‖
groupHash ‖ beaconID) equals the manifest's `chainHash`; round number; randomness = SHA-256(signature);
32-byte randomness, 48-byte signature; ≥ 2 relays (api, api2, api3.drand.sh, drand.cloudflare.com) return
the identical signature; the round is not in the future. A saved `beacon.json` is re-checked offline.
**Not checked: the BLS signature.** Residual trust: the agreeing relays did not collude on an invented
(signature, SHA-256(signature)) pair (drand.sh hosts share one operator; Cloudflare is a second). drand's
own client closes the gap. `round-at T` = first round produced at or after T.

## Test results (`python3 test_pipeline.py`, 2026-10-18)

7,000 valid ids from `tools/tokenset/tokens.json` (tokenSetHash `0x01cc…0222`), 3,000 excluded; 1,410 real
designs (files read from `https://tapeout.net/rpc` at block 128,200,681 on the first run, 2 min 37 s, then
cached; every hash and N/L matched the table; largest file 8,444 bytes); fake avatar hashes; drand quicknet
round 33,145,012 (2026-10-17 12:00 UTC) agreed by four relays. 8/8 tests pass, including: past-round refusal,
future-round refusal, blind-box verification before a future round, verification over HTTP, detection of
swapped netlists, of an excluded id given content, of a changed manifest byte and of a wrong token-set file.

| Step | Time |
|---|---|
| build_pools (cached files) | 0.9 s |
| make_manifest (incl. live `/info`) | 3.1 s |
| drand fetch | 6.1 s |
| reveal (10,000 files, 14,000 proofs in 0.2 s) | 9.4 s |
| verify_collection (directory) | 11–14 s; over HTTP 6.9 s |
| whole pipeline | ≈ 45 s |

| Output | Size |
|---|---|
| manifest.json (7,000 + 7,000 entries, hash + tier, `rules`, `tokenSet`) | 1,334,960 bytes |
| meta/ (10,000 files; test template) | 22,358,432 bytes (21.3 MiB) |
| meta/ with realistic 59-char CIDs | 24,383,432 bytes (23.3 MiB), under the 32 MB folder limit |
| meta-unrevealed/ | 7,929,682 bytes |
| reveal.json | 14,792,929 bytes |
| net/ (1,410 distinct files) | 1,077,342 bytes |

## Known limits

- Container addresses come from one archive node; the factory `isCPU` check (draft A §3.2 step 1) is not
  done here.
- `verify_collection.py` knows the `uriFrozen()` selector only (no keccak in the standard library).
