# Reference contracts for the netlist-NFT TAP drafts

Foundry project. Solidity 0.8.28, optimizer 10,000 runs, EVM `shanghai` (one build for BNB Smart Chain, Base and X Layer).

| Path | Content |
|---|---|
| `src/interfaces/` | `ITapNetlistNFT`, `ITapNetlistEval` (Netlist-Bound NFTs draft), `ITapBridge*` (bridging draft). CC0 |
| `src/core/` | `TapNetlistNFT` (L1 collection), `TapCompanion` (L1 for an existing ERC-721), `TapMintBoundNFT` (L1 without a manifest: the mint-bound profile of §8.2), libraries `TapPermutation`, `TapMerkle`, `TapNetlistCheck`, `TapNetlistVM`, storage `TapNetlistStore` |
| `src/bridge/` | `TapGateway`, `TapMirror`, `TapBridgeEndpoint`, `LayerZeroV2Adapter`, `HubRelayAdapter` |
| `src/tools/` | `TapContainerLock`: holds a TapeOut container's circuit so its files can no longer change, while anyone can renew its activation |
| `src/vendor/` | Minimal ERC-721, ERC-4906 events, `Owned` (MIT) |
| `test/` | Unit, vector and gas tests; `test/fixtures/` holds values generated from the Python reference implementations |

```bash
forge build
forge test
```

`test/fixtures/make_core_fixtures.py` regenerates `core-vectors.json` (Python 3.11).

## Mint-bound profile (`TapMintBoundNFT`)

`src/core/TapMintBoundNFT.sol` is the reference for the mint-bound collections profile of the core draft (§8.2):
an L1 collection that commits to no manifest and records the netlist hash of each token id at its mint. It
inherits `ERC721Min`, `TapNetlistStore` and `Owned` (not `TapNetlistCore`, which carries the manifest, the
pools and the Eval and TokenSet extensions) and reports ERC-165, ERC-721, ERC-721 Metadata, ERC-4906,
`ITapNetlistNFT` and ERC-173; it does not report the Eval, TokenSet or Companion extension ids.

| Rule of the profile | Implementation |
|---|---|
| Netlist hash recorded once per id, never changed | `mint(to, tokenId, netlistHash, imageHash)` (owner or minters) records both hashes at the id's first mint and emits `NetlistRecorded`; no function writes them again |
| A burned id is never minted again with another hash | `burn` keeps the recorded hashes; a re-mint must repeat the identical netlist hash and image hash (`HashMismatch` otherwise), so `netlistHashOf` answers for burned ids too |
| `manifestHash()`, `masterSeed()` zero, `pools()` empty, permanently | Constant functions |
| `entryIndexOf`, `bind` revert | `NoManifest()` for every token and pool index |
| `tokenRange()` | Fixed at construction: `(firstTokenId, supply)` bounds the ids that can ever be minted; `supply` = 0 means unbounded and returns `(0, 0)` |
| `imageHashOf` | `recordsImageHash` (constructor) decides for the whole collection: every mint records a non-zero image hash, or none does and the getter is zero permanently (the field no pool carries, §5.2) |
| `storeNetlist` | `TapNetlistStore` with the on-chain validity check (`TapNetlistCheck`): a valid `tapnet/1` file of at most 49,152 bytes whose SHA-256 was recorded at a mint; the hash stays known after a burn |
| `frozen()` | True once `freeze()` locks the base URI (the only mutable input of `tokenURI`); emits `Frozen` and `BatchMetadataUpdate(0, 2^256 − 1)`; never returns to false. A freeze does not end minting or burning; `endMinting()` does, irreversibly |
| Ownership (ERC-173) | Kept after the freeze (minter set, `endMinting`); renouncing is allowed only once frozen, so the contract is never left unfrozen without an owner. After `freeze()`, `endMinting()` and a renounce nothing can change or mint again |
| ERC-4906 | `MetadataUpdate(tokenId)` at every mint, `BatchMetadataUpdate(0, 2^256 − 1)` on `setBaseURI` and `freeze` |

`tokenURI` = `baseURI` ‖ decimal token id, as in `TapNetlistNFT`. Tests: `test/core/TapMintBoundNFT.t.sol`
(unit tests, gas, and a differential check that reads `assets/tap-draft-netlist-bound-nft/vectors.json`:
the `tapnet` and `invalidFiles` files are stored or rejected exactly as the Python reference accepts or rejects
them, and the `noManifest` metadata matches the getters at the chain id and address the Python side used).

## Fork tests (TapeOut containers on X Layer)

`test/fork/ContainerLock.t.sol` runs against X Layer mainnet state without broadcasting anything. It needs an RPC URL and Cancun execution rules (the X Layer site store uses Cancun opcodes, while this project compiles for Shanghai):

```bash
XLAYER_RPC=https://rpc.xlayer.tech forge test --evm-version cancun --match-path test/fork/ContainerLock.t.sol
```

Without `XLAYER_RPC` the fork tests return early and count as passed.

Nothing here is deployed or audited.
