# Assets for the TAP draft "Structural Hash of Flat Netlists"

| File | What it is |
|---|---|
| `canon.py` | Reference implementation (MIT): `canonicalize(file)` returns the canonical `tapnet/1` file, the structural hash and the counts `live`, `nodes`, `cyclic`, `rounds`, `copies`. It uses `tapnft.py` and `tap02_reference.py` of the "Netlist-Bound NFTs" draft unchanged; copies are included in this folder (see "Included copies" below). |
| `make_vectors.py` | Generates `vectors.json` (deterministic: fixed seed, sorted keys, no timestamps). Also holds the netlist-graph helpers and the transformations (renumbering, NAND input swaps, dead elements, duplication) used by the tests. |
| `vectors.json` | Test vectors, format `tap-structural-hash-vectors/1` (sections below). |
| `chain-circuits.json` | Pinned on-chain input: `netlist` and `circuitInfo` of four BNB Smart Chain circuits at block 128200681, from read-only `eth_call` reads (subset of `../tap-draft-netlist-bound-nft/chain-snapshot.json`); no transaction was sent. |
| `test_canon.py` | `unittest` suite (below). |

## Regenerate and test

```
python3 make_vectors.py && python3 test_canon.py
```

Python 3.9 or later, standard library only. To re-pin the chain input from a fresh snapshot:
`python3 make_vectors.py --import ../tap-draft-netlist-bound-nft/chain-snapshot.json` (this changes the hash below if the snapshot changed).

SHA-256 of `vectors.json`:

```
35aaf41cbcff011290ba51ee9cc9f5ca7820345658069161bba74062914062aa
```

Command line: `python3 canon.py file.tapnet`, or `python3 canon.py 0x<netlist> --n-in N --n-out M`
(add `--write out.tapnet` to save the canonical file).

## Sections of `vectors.json`

- `labelDomain`, `hashDomain`: the label prefix `TAPSH1` and the structural-hash domain tag
  `tap-structural-hash/1 ‖ 0x00`.
- `cases`: input file, netlist hash, canonical file, structural hash and counts. Hand-made fixtures (XOR family
  from circuit #17851, 5-NAND XOR, input order, double negation, toggles, LATCH duplication with feedback,
  output tail cases, constant rings, `nIn = 0`, shift register, LFSR) and four seeded random netlists with
  three transformed variants each.
- `equalGroups`: cases that must share a structural hash. `distinct`: pairs that must not.
- `invalid`: files that must be rejected (REF record, bad header, no records, NAND forward reference).
- `chainSnapshot`: the REF-free mainnet circuits of `chain-circuits.json` with their canonical files and hashes
  (#38 uses REF and is skipped).

## Structural hashes of mainnet circuits (BNB Smart Chain, block 128200681, processor `0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`)

| Circuit | Structural hash | Remark |
|---|---|---|
| #17851 XOR | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` | canonical file = on-chain netlist with its two middle NAND records exchanged |
| #17852 Johnson counter | `0x7d37fb8366db82442b4c6e8213c972a8ac2d6c7b37d114d6019a0ea76d0f74c3` | two LATCHes with the same `d` merge; canonical file = input file |
| #3151 popcount8 | `0xbe6e9ecc052462ba51ab577539f17ec6b7119ff041c1703712eff3fc68484075` | 4 of 55 NAND are dead |

## What `test_canon.py` checks

For 300 netlists generated with fixed seeds (half uniformly random, half biased so most elements are live):

- invariance of the structural hash under random renumbering, NAND input swaps, dead elements (including dead
  LATCH loops), duplication (including LATCHes whose feedback references move to the copy), and their combination;
- the canonical file passes `tapnft.check_file`, has the same `nIn`/`nOut`, and gives the same outputs as the
  input under `tap02_reference.beat` for random input sequences from the all-zero state;
- idempotence: `canon(canon(x)) == canon(x)`;
- netlists with equal hashes behave identically on random inputs;
- every vector, group, invalid file and mainnet circuit; `vectors.json` is regenerated and compared byte for byte;
- cost: a 3,000-stage shift register takes no refinement rounds; a 200-LATCH ring takes about 200.

## Version 2 (`tap-structural-hash/2`, draft §10): `tapnet/2` with ROM, ROM read ports and RAM ports

| File | What it is |
|---|---|
| `canon2.py` | Reference implementation of version 2 (MIT). `canonicalize(file)` accepts `tapnet/1` and `tapnet/2` files and returns the canonical file, its version (1 when no ROM or RAM node remains), the structural hash and the counts `live`, `nodes`, `romNodes`, `ramNodes`, `planes`, `cyclic`, `rounds`, `copies`. Imports `canon.py` unchanged and `tapnet2.py` of the "Large Netlists and Verifiable Execution" draft unchanged (a copy is included in this folder, see "Included copies" below). Rejects records it does not define. |
| `make_vectors2.py` | Generates `vectors2.json` (deterministic). Also holds the `tapnet/2` graph helpers and the ROM and RAM transformations used by the tests. |
| `vectors2.json` | Test vectors, format `tap-structural-hash-vectors/2`: `cases`, `equalGroups`, `distinct`, `invalid`. |
| `test_canon2.py` | `unittest` suite for version 2 (35 tests, about 6 s): compatibility with every case of `vectors.json` and with `canon.py` on 300 random netlists, ROM/ROM-port/RAM invariances on 300 random `tapnet/2` netlists, validity, idempotence and behaviour of canonical files (with memory), distinctness, rejection of unknown records, the 256-bank limit. |

```
python3 make_vectors2.py && python3 test_canon2.py
```

SHA-256 of `vectors2.json`:

```
06bd3c06961bb4d87b60d3837591696f762b78ddd931cb5eb3a31a8c4564dbe8
```

Command line: `python3 canon2.py file.tapnet [--write out.tapnet]`.

## Included copies

So that this folder runs on its own, it contains unchanged copies of four modules of other drafts in the TAP-721 family.
Python finds them in this folder first (the script's own directory precedes the fallback paths to the sibling asset
folders that `canon.py` and `canon2.py` append to `sys.path`).

| File | Origin | SHA-256 |
|---|---|---|
| `tapnft.py` | `assets/tap-draft-netlist-bound-nft/tapnft.py` of `TAP-draft-netlist-bound-nft` as first submitted (PR #67, commit `9b238c7`) | `d8873914d0b57ca6ae89d69743eec5f99486b1b2f9805c628ad3c0199e6f3f3a` |
| `tap02_reference.py` | `assets/tap-draft-netlist-bound-nft/tap02_reference.py` of the same draft (itself a copy of `assets/tap-02/reference.py` with only the header comment changed) | `88c777b6b773ccb89a058f3b2d0bb52f255eb753578ea5fd4ee9bae14b1b7808` |
| `tapnet2.py` | `assets/tap-draft-large-netlists/tapnet2.py` of `TAP-draft-large-netlists` | `208e2fb49f1d84e6d518ce461e51a1092f065cdc931ac17cd3a25c946be0ba1b` |
| `examples.py` | `assets/tap-draft-large-netlists/examples.py` of the same draft (used by `make_vectors2.py`) | `b8682091c4fa4333928cc17987c48932dac1c7bc462c914ce32a76c73e6995ba` |

When those drafts are numbered, the copies can be replaced by imports from their `assets/tap-<nn>/` folders; no
vector depends on where the modules are loaded from.
