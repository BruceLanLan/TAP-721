# Assets: Design Credits and Lineage

Reference implementation and vectors for `TAPs/TAP-draft-design-credits.md`. Python 3.9+, standard library only;
optional cross-checks use pycryptodome, eth_keys, eth_account and Foundry `cast` when installed.

| File | Content |
|---|---|
| `credits.py` | keccak-256, secp256k1, EIP-712 statements, verification (ERC-1271 at a verification block, container labels), revocation, publication facts, earliest occurrences, anchors, display order |
| `make_vectors.py` | writes `vectors.json` (deterministic; `--check` compares) |
| `test_credits.py` | runs every vector and the cross-checks; checks Appendix A of `../../TAPs/TAP-draft-design-credits.md` (and of its translation, when present) against the vectors |
| `fetch_reads.py` | records the read-only reads in `chain-reads.json`: the worked example (BSC, state reads pinned to one `finalized` block on three operators), the selector enumeration of the circuit implementations, and the X Layer container delegation path (pinned to one `safe` block on two operators) |
| `scan_occurrences.py` | minimal occurrence indexer over processors 30 and 635, at the pinned block of `chain-reads.json` (archive node only), writes `occurrences.json` |
| `canon.py`, `tapnft.py`, `tap02_reference.py` | copied unchanged from the TAP-721 family reference implementations, so that this folder runs on its own (origin and SHA-256 below) |

```bash
python3 make_vectors.py && python3 test_credits.py
# re-record chain reads (network, read-only); scan_occurrences.py reads the block pinned by fetch_reads.py:
python3 fetch_reads.py && python3 scan_occurrences.py 30 635 && python3 make_vectors.py
```

Re-running `fetch_reads.py` pins a new block, so `chain-reads.json`, `occurrences.json` and therefore `vectors.json`
change; update the block numbers, counts and the SHA-256 pinned in the Test Cases of the TAP (and its translation) at the same time.
Public BSC nodes keep state for only about a hundred blocks: `fetch_reads.py` makes its pinned state reads first and
in parallel, and the scan uses the archive node `https://tapeout.net/rpc` alone (one operator; the scan's bounds,
`nextId()` and `circuitInfo(nextId() + 1)`, were checked on three operators by `fetch_reads.py`).

All private keys in `vectors.json` are test-only: `keccak256("tap-design-credits test key <n>")`.

How the creation transactions were found: `eth_getLogs` on the processor for
`Transfer(0, *, id)` over a block range (archive node `https://tapeout.net/rpc`); the range was narrowed by a
binary search on `nextId()` at historical blocks, which on the deployed processors returns the latest id.

Selector names: the dispatcher selectors of the circuit implementations were extracted from their runtime bytecode
(`PUSH4` followed by `EQ`); a selector is named only when `keccak256` of a candidate signature reproduces it. Five
candidate names came from public signature databases (4byte.directory, openchain.xyz).

## Included copies

| File | Origin | SHA-256 |
|---|---|---|
| `canon.py` | `assets/tap-draft-netlist-structural-hash/canon.py` of `TAP-draft-netlist-structural-hash` (PR #70) | `c3571dd13a772320abe90842d917c599d65b5e528b73e0044e6cc78f8832fe68` |
| `tapnft.py` | `assets/tap-draft-netlist-bound-nft/tapnft.py` of `TAP-draft-netlist-bound-nft` as first submitted (PR #67, commit `9b238c7`) | `d8873914d0b57ca6ae89d69743eec5f99486b1b2f9805c628ad3c0199e6f3f3a` |
| `tap02_reference.py` | `assets/tap-draft-netlist-bound-nft/tap02_reference.py` of the same draft (a copy of `assets/tap-02/reference.py` with only the header comment changed) | `88c777b6b773ccb89a058f3b2d0bb52f255eb753578ea5fd4ee9bae14b1b7808` |

`canon.py` appends `../tap-draft-netlist-bound-nft` to `sys.path` as a fallback; the copies in this folder are found first.
