# Anvil dry run of the deployment scripts (TAP-721 family)

Run on 2026-10-21 with Foundry 1.8.3 (`forge`, `anvil`, `cast`), `contracts/script/anvil-dry-run.sh` and
`assets/tap-draft-soulbound-credentials/contracts/script/anvil-dry-run.sh`: a fresh local `anvil` (chain id 31337,
30,000,000 block gas limit), anvil's public default account 0 as deployer, every script with `--broadcast --slow`.
Gas is the `gasUsed` of the receipts. No public chain was touched. The CI job `forge` repeats this run.

`--slow` matters: without it forge sends the whole batch at once, anvil packs 28.4 million gas into one block and
the transaction that does not fit stays pending until another one arrives, so `forge script` waits forever. Public
RPCs have the same failure mode in other forms (nonce gaps, rate limits), which is why `deploy-testnet.sh` always
passes `--slow`.

## DeployCore.s.sol:DeployCore — 32 transactions, 8,650,578 gas

| Gas | Transaction |
|---|---|
| 602,803 | CREATE2 `TapNetlistVM` (library, through forge's CREATE2 factory `0x4e59b448…956C`) |
| 5,313,521 | CREATE `TapNetlistNFT("TAP-721 Example Collection", "TAP721X", "https://example.invalid/tap-example/token/", deployer)` |
| 263,384 | `commitManifest(0x23157012…5983, 1, 8, [IMAGE_V1/1/0x74db282d…, NETLIST_V1/2/0x376e16d7…])` |
| 553,140 | 8 × `mint(deployer, t)` (about 69,000 each) |
| 136,776 | `reveal(0x000102…1f)` |
| 1,352,978 | 16 × `bind(t, pool, values, proof)` (about 84,600 each) |
| 369,529 | 3 × `storeNetlist(file)` (44, 59 and 401 bytes; SSTORE2 pointers) |
| 58,447 | `freeze()` |

Result: `manifestHash 0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983`, `masterSeed
0x000102…1f`, `tokenRange (1, 8)`, `frozen true`.

## DeployCompanion.s.sol:DeployCompanion — 34 transactions, 8,849,372 gas

| Gas | Transaction |
|---|---|
| 1,515,427 | CREATE `ExampleLegacy721("TAP-721 Example Legacy", "TAP721L", "https://example.invalid/tap-example/legacy/", deployer)` |
| 447,244 | 8 × `ExampleLegacy721.mint` |
| 45,523 | `ExampleLegacy721.freezeURI()` |
| 4,620,012 | CREATE `TapCompanion(legacy, 0x274e4a1d, deployer)` (the library already exists at its CREATE2 address and is not redeployed) |
| 263,322 | `commitManifest` |
| 136,765 | `reveal` |
| 1,351,165 | 16 × `bind` |
| 369,319 | 3 × `storeNetlist` |
| 52,969 | `endorse()` |
| 47,626 | `seal()` |

Result: `endorsed true`, `isSealed true`, `frozen true`.

## DeployContainerLock.s.sol:DeployContainerLock — 5 transactions, 1,167,475 gas (anvil mocks)

| Gas | Transaction |
|---|---|
| 140,723 | CREATE `MockProcessor` (anvil only) |
| 44,053 | `MockProcessor.set(1, deployer)` |
| 107,930 | CREATE `MockOpener` |
| 184,223 | CREATE `MockBinding` |
| 690,546 | CREATE `TapContainerLock(processor, 1, container, opener, binding, "1.2.282.tape")` |

On a real chain only the last line applies (about 0.7 million gas), with the TapeOut addresses of TAP-10.

## DeploySoulbound.s.sol:DeploySoulbound — 2 transactions, 5,191,911 gas

| Gas | Transaction |
|---|---|
| 5,101,950 | CREATE `SoulboundNetlistCredential("TAP-5192 Example Credential", "TAP5192X", "https://example.invalid/tap-5192/")` |
| 89,961 | `storeNetlist(xor file)` → `0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e` |

## Totals

| | Transactions | Gas |
|---|---|---|
| Testnet run (`deploy-testnet.sh`: core + companion + soulbound) | 68 | 22,691,861 |
| plus the container lock, on a mainnet with TapeOut contracts | 1 | 690,546 |

`forge script` estimates about 1.3 × these figures before sending ("Estimated total gas used for script:
11,639,491" for DeployCore); the balance should cover the estimate.

## deployments/31337.json written by the run

```json
{
  "chain": "anvil",
  "chainId": 31337,
  "core": {
    "ITapNetlistEval": "0xec7d7e20",
    "ITapNetlistNFT": "0x282b67f6",
    "ITapNetlistTokenSet": "0x3f7177c7",
    "TapNetlistNFT": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
    "TapNetlistVM": "0x82aF8337aa103e35b4A9C6cF11195E36E77Fa036",
    "baseURI": "https://example.invalid/tap-example/token/",
    "block": 0,
    "deployer": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "firstTokenId": 1,
    "frozen": true,
    "manifestFile": "../assets/tap-draft-netlist-bound-nft/example/manifest.json",
    "manifestHash": "0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983",
    "masterSeed": "0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    "name": "TAP-721 Example Collection",
    "pool0Root": "0x74db282d145acb6d347e7d2bce76abf6b6f84e6ec46a8ef9973abefde313e27a",
    "pool1Root": "0x376e16d74681f43023dedadee1612c20f7ecd2a7cd6231a8c959e772251608de",
    "supply": 8,
    "symbol": "TAP721X",
    "timestamp": 1792590752
  },
  "companion": {
    "ITapCompanion": "0x12b40a6c",
    "ITapNetlistNFT": "0x282b67f6",
    "TapCompanion": "0x99bbA657f2BbC93c02D617f8bA121cB8Fc104Acf",
    "block": 1,
    "collection": "0x84eA74d481Ee0A5332c457a4d796187F6Ba67fEB",
    "deployer": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "endorsed": true,
    "exampleLegacy": true,
    "frozen": true,
    "manifestHash": "0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983",
    "masterSeed": "0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    "sealed": true,
    "timestamp": 1792590760,
    "uriFrozenSelector": "0x274e4a1d"
  },
  "containerLock": {
    "TapContainerLock": "0x21dF544947ba3E8b3c32561399E88B52Dc8b2823",
    "binding": "0x4C4a2f8c81640e47606d3fd77B353E87Ba015584",
    "block": 2,
    "circuitId": 1,
    "container": "0x796237F35c895766996564925A52b2DD32e35642",
    "deployer": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
    "locked": false,
    "mocked": true,
    "onChainName": "1.2.282.tape",
    "opener": "0x04C89607413713Ec9775E14b954286519d836FEf",
    "processor": "0x1fA02b2d6A771842690194Cf62D91bdd92BfE28d",
    "timestamp": 1792590764
  }
}
```

The soulbound project writes its own `deployments/31337.json` with section `soulbound` (address, `REBIND_DELAY
604800`, `MAX_GATE_WORK 65536`, `MAX_TABLE_BYTES 131072`, `MAX_FILE_BYTES 49152`, `domainSeparator`, the stored
hash and the five interface ids `0xb45a3c0e`, `0x5558759c`, `0x07aaf2dc`, `0x7587c9da`, `0x11e35684`).

Addresses on anvil are those of a fresh node (deployer nonce 0, 1, …) and mean nothing elsewhere.
