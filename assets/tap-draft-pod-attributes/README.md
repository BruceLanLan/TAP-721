# tap-draft-pod-attributes

Tools and vectors for the TAP draft "Proof-of-Design Attributes for Netlist-Bound NFTs"
(`TAPs/TAP-draft-pod-attributes.md`). Code is MIT; data files are CC0.

Requirements: Python 3.9+, pycryptodome (keccak-256), Foundry `cast` (ABI encoding/decoding).
Nothing here sends a transaction: only `eth_call`, `eth_getStorageAt` and `eth_getBlockByNumber`.

| File | Purpose |
|---|---|
| `pod_snapshot.py` | Read a miner at a pinned BNB Smart Chain block and print the `tap.pod` object, its ERC-7496 trait values and cross-checks |
| `pod_validate.py` | Validate a `tap.pod` object (`--pod file`) or the PoD members of a token metadata document (with `functionCheck` and, in code, the manifest commitments of §4.4) |
| `function_check.py` | §3.9 functional check `tap-pod-fc/1` against the task's reference circuit (TAP-02 reference evaluator) |
| `make_vectors.py` | Build `vectors.json`, `trait-metadata.json` and `example-image.png` from `../tap-draft-netlist-bound-nft/chain-snapshot.json`, `raw/` and `synthetic/` (no network) |
| `test_pod.py` | Tests (no network); regenerates the vectors and checks they are byte-identical; runs the reference check of TAP-draft-netlist-bound-nft (`tapnft.check_metadata`) on the metadata example as stored |
| `raw/raw<id>.json` | Raw reads by `pod_snapshot.py --raw` at block 128200681 (TapeOut processor) |
| `raw/ref-task<id>.json` | Reference circuits of tasks 3, 48, 220 at the same block (`read_reference`) |
| `synthetic/verified-but-wrong.json` | SYNTHETIC `verifiedButWrong` example (hand-built, fictional processor and id; not chain data). A real instance is withheld until disclosed to the TapeOut team |
| `vectors.json` | Test vectors (see the draft's Test Cases) |
| `example-image.png` | The 1×1 PNG behind `metadataExample` (`image` and `tap.image.sha256`); a stored deflate block, rebuilt byte for byte by `make_vectors.py` |
| `trait-metadata.json` | Recommended ERC-7496 trait metadata (`getTraitMetadataURI` document) |

## Usage

```sh
# snapshot one circuit (archive node first; further --rpc nodes are cross-checks)
python3 pod_snapshot.py 0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C 17851 128200681 \
    --rpc https://tapeout.net/rpc --rpc https://bsc-dataseed.bnbchain.org --raw raw/raw17851.json [--rig <voucherId>] [--check]

python3 pod_validate.py --pod pod.json
python3 pod_validate.py token-metadata.json
python3 make_vectors.py && python3 test_pod.py
```

Public BNB Smart Chain nodes prune state after about a minute (publicnode.com refuses archive reads
without a token), so a pinned block usually has one source only, the archive node
`https://tapeout.net/rpc`; the tool lists such reads under `singleSourceReads`. Block headers are
not pruned and are cross-checked.

## Checksums

```
651b660886847443e0bbdd9b4cd542c1f99491f566a680fe094a3f7c9017a102  vectors.json
336be474884b5cf2ce32ed77bdb05a75a02c8b96db1073e229fe287c6cdda0ac  trait-metadata.json
47dfc2f9468420af2b30a09346890994276dbb21828fe21b743ac911a2b3aa0c  example-image.png
```
