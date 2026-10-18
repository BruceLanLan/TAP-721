# Assets for the TAP draft "Structural Hash of Flat Netlists"

| File | What it is |
|---|---|
| `canon.py` | Reference implementation (MIT): `canonicalize(file)` returns the canonical `tapnet/1` file, the structural hash and the counts `live`, `nodes`, `cyclic`, `rounds`, `copies`. It imports `tapnft.py` and `tap02_reference.py` unchanged from `../tap-draft-netlist-bound-nft`. |
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
