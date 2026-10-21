# Assets for the TAP draft "Netlist-Bound NFTs"

| File | What it is |
|---|---|
| `tapnft.py` | Reference implementation: `.tapnet` files, the manifest Merkle tree (`merkle_levels` plus `merkle_proof_from_levels` give many proofs from one tree), `check_manifest` (range mode and set mode), token sets (`token_set_hash`, `token_set_file`, `check_token_set`, `token_index`), `assignment`, the reveal permutation, `check_metadata`, `netlist_status` (a netlist in a format other than `tapnet/1` is reported as `unverifiable`, never as invalid, §2.5) the collection-level `check_editions` (which first checks that tokens carry `tap.manifest` all with one hash or not at all, optionally against a known manifest hash, §7.1, and returns `unverifiable` when it had to skip tokens in an unsupported format, §2.5), and `check_freeze_probes` (one `tap.freeze` for the whole collection or none, §5.1). For a format other than `tapnet/1`, `check_netlist_against_metadata` still checks bytes 0–6 of the fetched file (§2.5). The command line `python3 tapnft.py FILE…` checks `.tapnet` files, manifests and token metadata. |
| `tap02_reference.py` | TAP-02 reference implementation, copied from `assets/tap-02/reference.py` (TAPs repository) with only the header comment changed. |
| `chain-circuits.json` | Pinned on-chain input: `circuitInfo` and `netlist` of four BNB Smart Chain circuits at block 128200681. The data comes from read-only `eth_call` reads (subset of `chain-snapshot.json`); no transaction was sent. |
| `make_vectors.py` | Generates `vectors.json` and `example/` using only `tapnft.py` functions. It is deterministic. |
| `vectors.json` | Test vectors (sections below). |
| `example/` | Worked collection: `manifest.json`, `token/1.json` … `token/8.json`, and the three `.tapnet` files under `netlists/<sha256>.tapnet`. |
| `test_tapnft.py` | `unittest` suite. It regenerates everything and compares it byte for byte with the files on disk. It re-verifies every vector, re-derives the example from the files alone, and runs property tests (bijection, Merkle round trips) with a fixed RNG seed. |

## Regenerate and test

```
python3 make_vectors.py && python3 test_tapnft.py
```

Needs Python 3.9 or later and the standard library only. To re-pin the chain input from a fresh snapshot, run
`python3 make_vectors.py --import chain-snapshot.json`. This changes `chain.block`, `source.block` and therefore the hash below.

SHA-256 of `vectors.json`:

```
9808f32ae21d911e377de09aa9f5df862715e9d1286041033f225a54c70031e8
```

## Sections of `vectors.json`

- `chain`: chain id, pinned block, and the nodes the snapshot script queried (not all of them answered).
- `tapnet`: the four mainnet circuits. Each entry has its source (`17851.30.tape`, `17852.30.tape` and `3151.30.tape` on processor 30 "TapeOut", and `38.1.tape` on processor 1 "Blonskr_No1"), the file built as `"TAPNET" 01 00 ‖ u32(nIn) ‖ u32(nOut) ‖ netlist(id)`, `netlistHash`, metrics, and validity. `38.1.tape` contains REF records, so it is listed as rejected with the reason. For the three valid circuits, the generator asserts NAND + LATCH = `gateCount` and LATCH = `nState`.
- `invalidFiles`: one hand-made reject per rule, with the exact `tapnft.Invalid` text.
- `merkle`: pools of size 1, 2, 3, 5 and 8, with one field (image) and with two fields (image, netlist). Each pool has values, leaves, root and every proof. There are also 4 negative verify cases and `errors` (proof index out of range, empty pool, a 31-byte leaf value).
- `permutation`: `poolSeed` examples, `permute` outputs for n = 1, 2, 3, 7, 10, 255, 256, 257 and 1000 (all indices), and for n = 10000 the first 64 indices plus the SHA-256 of the whole permutation as u32be. It also includes `seedErrors` (mixed-case or un-prefixed collection, short master seed), `permuteErrors`, and round-function values `F(r, R)` and cycle-walking paths for debugging a Solidity port. These two debug lists use the private helpers `_round`, `_feistel` and `_half_bits`, because no public function exposes the intermediate steps.
- `metadata`: valid documents (unrevealed, unrevealed with a placeholder image, revealed, and revealed with edition, source, license and companion) and invalid documents (including `state: "frozen"`, which the standard no longer allows) that each break one rule of `check_metadata`, with the error text. A `tap.netlist.format` other than `tapnet/1` is not an error (§2.5, see `otherFormats`); the invalid case `netlist_format_not_string` uses a non-string format.
- `manifests`: `check_manifest` vectors. Valid manifests: one pool with both fields and object-form `uris`, the same pool with a `blockhash` reveal, and the two-pool example manifest. Invalid manifests each break one rule of §5.1, §5.2 or §6.1: `vrf`, a drand `chainHash` with `0x`, overlapping fields, a wrong root, a wrong entry count, the wrong `uris` form, bad labels, a zero value, supply bounds, `freeze` members and so on. Each comes with the exact error.
- `tokenSets`: set mode. `small` has 10 ids out of 1..20, with the `.bin` file bytes, its hash, a set-mode manifest, and the assignment of every token 1..20 (`null` for tokens outside the set). `large` has 7,000 ids out of 1..10,000, drawn with a fixed RNG; it gives the set hash, the first 32 assignments, and the SHA-256 of all entries as u32be in ascending id order. There are also token-set file and hash errors. Set-mode manifest cases are appended at the end of `manifests.valid` and `manifests.invalid`.
- `content`: valid and invalid `tap.content` members (§7.5).
- `placeholders`: metadata for a token outside `tokenSets.small`, checked with `check_metadata(doc, outside_token_set=True)` (§5.4, §7.2). The placeholder ERC-721 `image` is allowed, but `tap.image` and `tap.netlist` are rejected. The same document with a `tap.image` is valid for a token that is waiting for a reveal.
- `editions`: `check_editions` over the 8 example documents (passes). It also has three collection-level failures, each made by mutating one token: a missing edition, a wrong index and a wrong `of`. Each failure comes with the exact message, and each mutated document still passes `check_metadata` on its own. `collectionErrors` holds three collections that break §7.1: `tap.manifest` (and `tap.edition`) dropped from the tokens of one edition (rejected without further input), dropped from every token (rejected when `check_editions` is given the manifest hash, `manifestSha256`, as a tool knows it from `manifestHash()` or the manifest file; without it the collection is indistinguishable from one without a manifest), and two different manifest hashes.
- `netlistChecks`: `check_netlist_against_metadata` on a real file (one match, two rejects).
- `example`: supply 8 on chain 196 at `0x…00aa`, with pools `IMAGE_V1` (fake image hashes, `example.invalid` URIs) and `NETLIST_V1`. The netlist pool holds the three valid mainnet files repeated as A B C A B C A B, so editions occur. Each token has its entry indices, hashes, Merkle proofs, edition, and metadata document with its SHA-256. The **masterSeed is the fixed value 0x000102…1f**. The `drand` parameters in the manifest are illustrative: the seed is not the randomness of that round. The manifest also carries the optional `freeze` member `{"chainId": 196, "contract": "0x…00aa", "call": "uriFrozen()", "expect": true}`. It tells tools which on-chain read shows that the URIs are frozen. Metadata never says "frozen" itself.
- `noManifest`: metadata of collections without a manifest, such as mint-bound collections (§8.2): valid documents (no manifest; with a `tap.freeze` probe, §7.1; a document with a manifest whose `tap.freeze` is ignored, §7.2), invalid documents (a `tap.edition` without a manifest, §6.4; bad `tap.freeze` members, including a probe of another chain or contract than `tap.id`, §5.1), a collection-level check of two mint-bound tokens with the same netlist hash and no edition (passes), and `freezeProbe`: `check_freeze_probes` over those two tokens and two failing collections (different probes; a probe on only one token).
- `otherFormats`: a token whose netlist is a `tapnet/2` file (the `message` example of `TAP-draft-large-netlists`), checked by this tool, which supports `tapnet/1` only: `check_metadata` accepts it, `netlist_status` returns `unverifiable` and `check_netlist_against_metadata` raises `Unverifiable` (not `Invalid`), as §2.5 requires. `fetchedFiles` checks fetched bytes for that token: another version's header and a missing file are unverifiable; a `tapnet/1` file, a file without `TAPNET` and a truncated header are invalid. `editionsSkipped` has two such tokens under one manifest with the same netlist hash and no edition: `check_editions` returns `unverifiable`, because a tool that supports `tapnet/2` would require editions 1/2 and 2/2. Five invalid documents break the members every format keeps (`format`, `uris`) or write `tapnet/1` with a trailing space or in upper case.

All JSON is written with `json.dumps(obj, indent=1, sort_keys=True) + "\n"`. The manifest hash is
the SHA-256 of `example/manifest.json` exactly as written.
