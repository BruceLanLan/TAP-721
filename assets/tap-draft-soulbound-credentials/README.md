# Assets: Soulbound Netlist Credentials

Reference implementation and vectors for `../../TAPs/TAP-draft-soulbound-credentials.md`. Python 3.9+, standard library only;
optional cross-checks use `eth_account` and Foundry `cast` when installed.

| File | Content |
|---|---|
| `soulbound.py` | truth tables (bit-sliced), design keys, specification ids and work bounds, commitments (per committer), submission checks, claim scopes and Design Credits statement display, EIP-712 attestations and rebinds (delay and veto), signature rules, `tap.credential` metadata check (names only; `tap.pod` exempt, `tap.edition` rejected), display labels, ERC-165 ids, and `Issuer`, an executable model of the reference contract (lapsing and replaceable rebind requests, series record of design keys, Solidity cursor semantics) |
| `make_vectors.py` | writes `vectors.json` (deterministic; `--check` compares), including the `differential` section for the Solidity differential test |
| `test_soulbound.py` | checks the vectors; design key == structural hash equality on random combinational files and renumberings; bit-sliced evaluation against the TAP-02 evaluator; `eth_account` signatures; `cast sig` selectors; regressions of the second review (series record, rebind lapse and replacement, cursor after renounce, accumulating attested credentials) |
| `canon.py`, `tapnft.py`, `tap02_reference.py`, `credits.py` | copied unchanged from the TAP-721 family and the Design Credits draft, so that this folder runs on its own (origin and SHA-256 below) |

```bash
python3 make_vectors.py && python3 test_soulbound.py
```

## Solidity reference (`contracts/`)

`contracts/` holds `src/`, `test/`, `foundry.toml` and `.gitignore`. Its dependency forge-std is not included; install
version 1.17.0 into `contracts/lib/forge-std` first, without adding a git submodule to this repository, for example:

```bash
cd contracts
git clone --depth 1 --branch v1.17.0 https://github.com/foundry-rs/forge-std lib/forge-std
# or: forge install --no-git foundry-rs/forge-std@v1.17.0
forge test -vv    # Solidity 0.8.28 (via_ir); differential test, gas corners, attack regressions
```

The Foundry tests read `../vectors.json` (`fs_permissions` in `foundry.toml` grants read access to the parent
folder), so run `make_vectors.py` first if you change the generator. `lib/`, `out/` and `cache/` are not part of the
assets.

All private keys in `vectors.json` are public test keys, `keccak256("tap-soulbound test key <n>")`. Never use them.
The data in `vectors.json` is synthetic; no chain was read and no transaction was sent.

## Included copies

| File | Origin | SHA-256 |
|---|---|---|
| `canon.py` | `assets/tap-draft-netlist-structural-hash/canon.py` of `TAP-draft-netlist-structural-hash` (PR #70) | `c3571dd13a772320abe90842d917c599d65b5e528b73e0044e6cc78f8832fe68` |
| `tapnft.py` | `assets/tap-draft-netlist-bound-nft/tapnft.py` of `TAP-draft-netlist-bound-nft` as first submitted (PR #67, commit `9b238c7`) | `d8873914d0b57ca6ae89d69743eec5f99486b1b2f9805c628ad3c0199e6f3f3a` |
| `tap02_reference.py` | `assets/tap-draft-netlist-bound-nft/tap02_reference.py` of the same draft (a copy of `assets/tap-02/reference.py` with only the header comment changed) | `88c777b6b773ccb89a058f3b2d0bb52f255eb753578ea5fd4ee9bae14b1b7808` |
| `credits.py` | `assets/tap-draft-design-credits/credits.py` of `TAP-draft-design-credits` | `7204a16d0610695267f8c925f67935c67368d14feca98d5d55ec651e69122dab` |

`canon.py` appends `../tap-draft-netlist-bound-nft` to `sys.path` as a fallback; the copies in this folder are found first.
