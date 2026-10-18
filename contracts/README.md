# Reference contracts for the netlist-NFT TAP drafts

Foundry project. Solidity 0.8.28, optimizer 10,000 runs, EVM `shanghai` (one build for BNB Smart Chain, Base and X Layer).

| Path | Content |
|---|---|
| `src/interfaces/` | `ITapNetlistNFT`, `ITapNetlistEval` (Netlist-Bound NFTs draft), `ITapBridge*` (bridging draft). CC0 |
| `src/core/` | `TapNetlistNFT` (L1 collection), `TapCompanion` (L1 for an existing ERC-721), libraries `TapPermutation`, `TapMerkle`, `TapNetlistCheck`, `TapNetlistVM`, storage `TapNetlistStore` |
| `src/bridge/` | `TapGateway`, `TapMirror`, `TapBridgeEndpoint`, `LayerZeroV2Adapter`, `HubRelayAdapter` |
| `src/tools/` | `TapContainerLock`: holds a TapeOut container's circuit so its files can no longer change, while anyone can renew its activation |
| `src/vendor/` | Minimal ERC-721, ERC-4906 events, `Owned` (MIT) |
| `test/` | Unit, vector and gas tests; `test/fixtures/` holds values generated from the Python reference implementations |

```bash
forge build
forge test
```

`test/fixtures/make_core_fixtures.py` regenerates `core-vectors.json` (Python 3.11).

## Fork tests (TapeOut containers on X Layer)

`test/fork/ContainerLock.t.sol` runs against X Layer mainnet state without broadcasting anything. It needs an RPC URL and Cancun execution rules (the X Layer site store uses Cancun opcodes, while this project compiles for Shanghai):

```bash
XLAYER_RPC=https://rpc.xlayer.tech forge test --evm-version cancun --match-path test/fork/ContainerLock.t.sol
```

Without `XLAYER_RPC` the fork tests return early and count as passed.

Nothing here is deployed or audited.
