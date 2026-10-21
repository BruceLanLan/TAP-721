# Read-only verification of a TAP-721 family deployment

For editors. Everything here is `eth_call`, `eth_getCode` or local computation: no key, no transaction. Set the
chain and the addresses from the author's `deployments/<chainId>.json` (DEPLOY.md §7) and run the commands with
Foundry's `cast` (v1.8.3 or later). Expected values are those of the worked example that every script deploys
(`assets/tap-draft-netlist-bound-nft/example`); where a value depends on the chain or the address (token
assignment), the section says how to recompute it.

```bash
export RPC_URL=…                 # https://testrpc.xlayer.tech (1952) or a BSC Testnet RPC (97), DEPLOY.md §2
export NFT=<ADDRESS>             # core.TapNetlistNFT
export VM=<ADDRESS>              # core.TapNetlistVM (library)
export COMPANION=<ADDRESS>       # companion.TapCompanion
export LEGACY=<ADDRESS>          # companion.collection
export CRED=<ADDRESS>            # soulbound.SoulboundNetlistCredential
export LOCK=<ADDRESS>            # containerLock.TapContainerLock (mainnet only; see §3.4)
```

Pin a block for a record that others can repeat: add `--block <N>` to every `cast call` and write `N` into the
Deployments section (TAP-10 does this: "read back at block …").

## 1. Code is there and is the reference code

```bash
cast code $NFT --rpc-url $RPC_URL | wc -c           # > 2, i.e. a contract, not an EOA
cast codesize $NFT --rpc-url $RPC_URL
cast keccak "$(cast code $NFT --rpc-url $RPC_URL)"   # runtime code hash, record it
```

The project compiles with `bytecode_hash = "none"` and `cbor_metadata = false` (`contracts/foundry.toml`), so the
runtime code is a pure function of the source, solc 0.8.28, optimizer 10,000 runs and EVM `shanghai`; it differs
between deployments only in the linked library address (`TapNetlistNFT`, `TapCompanion`) and immutables
(`TapCompanion`: legacy address and selector). To compare byte for byte, build locally with the deployed library
address linked and diff:

```bash
cd contracts
forge build --libraries src/core/TapNetlistVM.sol:TapNetlistVM:$VM
python3 - "$NFT" <<'EOF'
import json, subprocess, sys, os
onchain = subprocess.check_output(["cast", "code", sys.argv[1], "--rpc-url", os.environ["RPC_URL"]]).decode().strip()
local = json.load(open("out/TapNetlistNFT.sol/TapNetlistNFT.json"))["deployedBytecode"]["object"]
print("identical" if onchain.lower() == local.lower() else "DIFFERENT")
EOF
```

For `TapCompanion` the immutable slots differ as well; compare the two codes with the 20-byte legacy address and
the 4-byte selector masked, or rely on the explorer's source verification (§4), which does that for you. The
library itself has no link or immutable: `cast code $VM` must equal `deployedBytecode` of
`out/TapNetlistVM.sol/TapNetlistVM.json` except for the library's own address that solc writes into its first
instructions (the `PUSH20 <self>` call-protection prefix).

## 2. ERC-165

Every id below must answer `true` unless stated otherwise.

```bash
for id in 0x01ffc9a7 0x80ac58cd 0x5b5e139f 0x49064906 0x282b67f6 0xec7d7e20 0x3f7177c7; do
  echo -n "$id "; cast call $NFT "supportsInterface(bytes4)(bool)" $id --rpc-url $RPC_URL
done
```

| id | Interface | TapNetlistNFT | TapCompanion | SoulboundNetlistCredential |
|---|---|---|---|---|
| `0x01ffc9a7` | ERC-165 | true | true | true |
| `0x80ac58cd` | ERC-721 | true | false (the legacy contract is the ERC-721) | true |
| `0x5b5e139f` | ERC-721 Metadata | true | false | true |
| `0x49064906` | ERC-4906 | true | true | **false** (metadata fixed at mint) |
| `0x282b67f6` | `ITapNetlistNFT` | true | true | false |
| `0xec7d7e20` | `ITapNetlistEval` | true | true | false |
| `0x3f7177c7` | `ITapNetlistTokenSet` | true | true | false |
| `0x12b40a6c` | `ITapCompanion` | false | true | false |
| `0xb45a3c0e` | ERC-5192 | false | false | true |
| `0x5558759c` | `ITapCredential` | false | false | true |
| `0x07aaf2dc` | `ITapCredentialProven` | false | false | true |
| `0x7587c9da` | `ITapCredentialAttested` | false | false | true |
| `0x11e35684` | `ITapCredentialClaimed` | false | false | true |
| `0xffffffff` | (must be false, ERC-165 §) | false | false | false |

The ids are `XOR` of the function selectors of each interface; recompute any of them from the interface file with
`forge inspect src/interfaces/ITapNetlistNFT.sol:ITapNetlistNFT methods` and `cast sig`, or trust the ones the
script wrote into `deployments/<chainId>.json`.

## 3. Getters

### 3.1 Collection (`TapNetlistNFT`)

| Call | Expected (example deployment) |
|---|---|
| `cast call $NFT "name()(string)"` | `TAP-721 Example Collection` (or the author's `NAME`) |
| `cast call $NFT "symbol()(string)"` | `TAP721X` |
| `cast call $NFT "collection()(address)"` | `$NFT` itself |
| `cast call $NFT "tokenRange()(uint256,uint256)"` | `1 8` |
| `cast call $NFT "manifestHash()(bytes32)"` | `0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983` = `sha256sum assets/tap-draft-netlist-bound-nft/example/manifest.json` (= `example.manifestSha256` in `vectors.json`) |
| `cast call $NFT "masterSeed()(bytes32)"` | `0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f` (the example's fixed seed; a real collection would show its drand/VRF seed) |
| `cast call $NFT "revealBlock()(uint256)"` | `0` (seed set by `reveal`, not by block hash) |
| `cast call $NFT "pools()((string,uint8,bytes32)[])"` | `[("IMAGE_V1", 1, 0x74db282d145acb6d347e7d2bce76abf6b6f84e6ec46a8ef9973abefde313e27a), ("NETLIST_V1", 2, 0x376e16d74681f43023dedadee1612c20f7ecd2a7cd6231a8c959e772251608de)]`; the roots are `pools[].root` of `example/manifest.json` |
| `cast call $NFT "tokenSetHash()(bytes32)"` | `0x00…00` (range mode) |
| `cast call $NFT "tokenCount()(uint256)"` | `8` |
| `cast call $NFT "tokenAt(uint256)(uint256)" 0` / `"indexOf(uint256)(uint256)" 1` | `1` / `0` |
| `cast call $NFT "frozen()(bool)"` | `true` (the script freezes unless `FREEZE=false`) |
| `cast call $NFT "owner()(address)"` | `0x0000000000000000000000000000000000000000` once frozen (ownership renounced) |
| `cast call $NFT "baseURI()(string)"` and `"tokenURI(uint256)(string)" 1` | base, and base ‖ `1` |
| `cast call $NFT "ownerOf(uint256)(address)" 1` … `8` | the deployer (or `MINT_TO`); `ownerOf(9)` reverts |
| `cast call $NFT "poolLoaded(uint256)(bool)" 0` | `false` (pools proven by Merkle proofs, not loaded) |
| `cast call $NFT "MAX_TOKENS()(uint256)"`, `"NO_REVEAL()(bytes32)"` | `100000`, `0xff…ff` |

Per token (`t` = 1 … 8), the binding and the files:

```bash
t=1
cast call $NFT "entryIndexOf(uint256,uint256)(uint256)" $t 0 --rpc-url $RPC_URL   # image entry
cast call $NFT "entryIndexOf(uint256,uint256)(uint256)" $t 1 --rpc-url $RPC_URL   # netlist entry
cast call $NFT "imageHashOf(uint256)(bytes32)"   $t --rpc-url $RPC_URL
cast call $NFT "netlistHashOf(uint256)(bytes32)" $t --rpc-url $RPC_URL
cast call $NFT "netlistOf(uint256)(bytes)"       $t --rpc-url $RPC_URL             # the stored tapnet/1 file
```

- `imageHashOf(t)` must equal `pools[0].entries[entryIndexOf(t,0)].image` of the manifest, and
  `netlistHashOf(t)` must equal `pools[1].entries[entryIndexOf(t,1)].netlist`. The netlist pool holds the three
  mainnet circuits as A B C A B C A B (`0xecb6f097…`, `0x9ee488f5…`, `0x1013cbe3…`), so every token's netlist hash
  is one of those three and each occurs 2 or 3 times (editions).
- **The assignment depends on the chain and the address** (`poolSeed = SHA-256(masterSeed ‖ u64(chainId) ‖
  collection ‖ label)`, TAP-721 §6.2), so it differs from `vectors.json` `example.tokens[]`, which is computed for
  chain 196 and `0x…00aa`. Recompute it with the reference implementation: copy `example/manifest.json`, set
  `collection.chainId` and `collection.address` (lower-case) to the deployment, then

  ```bash
  cd assets/tap-draft-netlist-bound-nft
  python3 -c "
  import json, tapnft
  m = json.load(open('manifest.deployed.json'))
  seed = bytes.fromhex('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')
  for t in range(1, 9): print(t, tapnft.assignment(m, seed, t))"
  ```

  The entry indices printed must equal `entryIndexOf(t, 0)` and `entryIndexOf(t, 1)`. `poolSeed(0)` and
  `poolSeed(1)` on chain equal `tapnft.pool_seed(seed, chainId, address, label)`.
- Stored files: `netlistFile(h)` for each of the three hashes must return the bytes of
  `example/netlists/<h>.tapnet` (`sha256` of the returned bytes = `h`); `knownNetlist(h)` is `true`;
  `netlistPointer(h)` returns the SSTORE2 pointer, its size and chunk count. An unknown hash reverts.

  ```bash
  h=0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e
  cast call $NFT "netlistFile(bytes32)(bytes)" $h --rpc-url $RPC_URL | xxd -r -p | sha256sum   # = ecb6f097…
  cast call $NFT "netlistPointer(bytes32)(address,uint256,uint256)" $h --rpc-url $RPC_URL
  ```
- Evaluation (`ITapNetlistEval`): `0xecb6f097…` is circuit 17851 (2 inputs, 1 output, 4 NAND = XOR). For a token
  `t` with that netlist hash:

  ```bash
  cast call $NFT "evalOf(uint256,bytes)(bytes)" $t 0x00 --rpc-url $RPC_URL   # 0x00
  cast call $NFT "evalOf(uint256,bytes)(bytes)" $t 0x01 --rpc-url $RPC_URL   # 0x01
  cast call $NFT "evalOf(uint256,bytes)(bytes)" $t 0x02 --rpc-url $RPC_URL   # 0x01
  cast call $NFT "evalOf(uint256,bytes)(bytes)" $t 0x03 --rpc-url $RPC_URL   # 0x00
  cast call $NFT "evalFile(bytes32,bytes)(bytes)" $h 0x03 --rpc-url $RPC_URL  # the same by hash
  ```

  `0x9ee488f5…` (17852) has 9 LATCHes: `evalOf` reverts "has latch: use step" and `stepOf(t, state, inputs)` answers.
  Cross-check any output with `assets/tap-draft-netlist-bound-nft/tap02_reference.py`.

### 3.2 Companion (`TapCompanion`) and its legacy collection

| Call | Expected |
|---|---|
| `cast call $COMPANION "collection()(address)"` | `$LEGACY` |
| `cast call $LEGACY "owner()(address)"` | the deployer (example legacy) or the real collection's owner |
| `cast call $COMPANION "legacyOwner()(address)"` | the same value |
| `cast call $COMPANION "uriFrozenSelector()(bytes4)"` | `0x274e4a1d` = `cast sig "uriFrozen()"` |
| `cast call $COMPANION "legacyUriFrozen()(bool)"` | `true` (= `cast call $LEGACY "uriFrozen()(bool)"`) |
| `cast call $COMPANION "endorsed()(bool)"`, `"endorsedBy()(address)"` | `true`, the legacy owner |
| `cast call $COMPANION "isSealed()(bool)"`, `"owner()(address)"` | `true`, `0x0` |
| `cast call $COMPANION "frozen()(bool)"` | `true` (latched: sealed ∧ endorsed ∧ legacy frozen) |
| `manifestHash`, `masterSeed`, `tokenRange`, `pools`, `entryIndexOf`, `netlistHashOf`, `netlistFile`, `evalOf` | as §3.1, with `$COMPANION` in place of `$NFT`. The pool seeds use `collection()`, i.e. the **legacy** address, not the companion's (`TapNetlistCore._seedDomain`): recompute with `tapnft.pool_seed(seed, chainId, legacy, label)` and set `collection.address` to `$LEGACY` in the manifest copy |
| `cast call $LEGACY "ownerOf(uint256)(address)" 1` | the deployer; the legacy holds the ERC-721 tokens, the companion holds no token |

If the author passed `LEGACY_COLLECTION`, `endorsed()` and `isSealed()` are `false` until the legacy owner and the
deployer complete the two steps; `frozen()` is then `false` and the Deployments section must say so.

### 3.3 Soulbound credential (`SoulboundNetlistCredential`)

| Call | Expected |
|---|---|
| `cast call $CRED "name()(string)"`, `"symbol()(string)"` | `TAP-5192 Example Credential`, `TAP5192X` |
| `cast call $CRED "REBIND_DELAY()(uint64)"` | `604800` (7 days) |
| `cast call $CRED "checkBounds()(uint256,uint256)"` | `65536 131072` (`MAX_GATE_WORK`, `MAX_TABLE_BYTES`) |
| `cast call $CRED "MAX_FILE_BYTES()(uint256)"`, `"GATE_OVERHEAD()(uint256)"` | `49152`, `20` |
| `cast call $CRED "domainSeparator()(bytes32)"` | EIP-712 separator for (chainId, `$CRED`); recompute with `vectors.json` `eip712` (name/version there) |
| `cast call $CRED "netlistFile(bytes32)(bytes)" 0xecb6f097…073e` | the `xor` file of `vectors.json` `files.xor.file` (44 bytes) |
| `cast call $CRED "locked(uint256)(bool)" 1` | reverts (no credential issued by the script); after an issuance, `true` for every existing token |
| `cast call $CRED "statusOf(uint256)(uint8)" 1`, `"credentialOf(uint256)" 1` | `0` (none) / reverts until issued |
| `cast call $CRED "attestationStatus(bytes32)(uint8,uint256)" 0x…` | `0 0` for an unknown attestation id |
| `cast call $CRED "gateWork(uint256,uint256)(uint256)" 2 4` | `84` = `(max(1, 2^2/256) + 20) × 4` |

### 3.4 Container lock (`TapContainerLock`, mainnet tool)

Deployed only on a chain with TapeOut contracts (TAP-10 Deployments), not on the testnets. Read-only checks:

```bash
cast call $LOCK "processor()(address)"   --rpc-url $RPC_URL   # the processor of TAP-10 for that chain
cast call $LOCK "circuitId()(uint256)"   --rpc-url $RPC_URL
cast call $LOCK "container()(address)"   --rpc-url $RPC_URL
cast call $LOCK "opener()(address)"      --rpc-url $RPC_URL   # must be the chain's container opener (TAP-10)
cast call $LOCK "binding()(address)"     --rpc-url $RPC_URL   # the chain's DomainBinding proxy (TAP-10)
cast call $LOCK "onChainName()(string)"  --rpc-url $RPC_URL
cast call $LOCK "locked()(bool)"         --rpc-url $RPC_URL   # true once the circuit NFT was transferred to the lock
# the constructor's own check, repeated:
cast call <OPENER> "accountOf(address,uint256)(address)" <PROCESSOR> <CIRCUIT_ID> --rpc-url $RPC_URL   # = container()
cast call <PROCESSOR> "ownerOf(uint256)(address)" <CIRCUIT_ID> --rpc-url $RPC_URL                       # = $LOCK iff locked()
```

## 4. Source verification on the explorer

Not required for a read-only check (§1 compares code), but it lets anyone read the source on the explorer. Needs the
constructor arguments the script used (`deployments/<chainId>.json` has them) and the linked library address. An
API key of the explorer is the author's; the commands below name it as an environment variable only.

```bash
cd contracts
ARGS=$(cast abi-encode "constructor(string,string,string,address)" "TAP-721 Example Collection" "TAP721X" "https://example.invalid/tap-example/token/" <DEPLOYER>)

# BNB Smart Chain Testnet (97): BscScan through the Etherscan v2 API (one key for every Etherscan-family chain)
forge verify-contract --chain 97 --verifier etherscan --etherscan-api-key "$ETHERSCAN_API_KEY" \
  --constructor-args "$ARGS" --libraries src/core/TapNetlistVM.sol:TapNetlistVM:$VM \
  $NFT src/core/TapNetlistNFT.sol:TapNetlistNFT --watch

# X Layer Testnet (1952): OKLink's verification API (the explorer of X Layer; URL from the X Layer docs
# "Verify a contract" page, https://web3.okx.com/xlayer/docs, confirm it there before use)
forge verify-contract --chain 1952 --verifier oklink \
  --verifier-url https://www.oklink.com/api/v5/explorer/contract/verify-source-code-plugin/XLAYER_TESTNET \
  --etherscan-api-key "$OKLINK_API_KEY" \
  --constructor-args "$ARGS" --libraries src/core/TapNetlistVM.sol:TapNetlistVM:$VM \
  $NFT src/core/TapNetlistNFT.sol:TapNetlistNFT --watch

# Keyless alternative where the chain is listed at https://sourcify.dev/#/chains (97 is; check 1952):
forge verify-contract --chain 97 --verifier sourcify --constructor-args "$ARGS" \
  --libraries src/core/TapNetlistVM.sol:TapNetlistVM:$VM $NFT src/core/TapNetlistNFT.sol:TapNetlistNFT
```

Same shape for `TapNetlistVM` (no constructor), `TapCompanion` (`constructor(address,bytes4,address)`),
`ExampleLegacy721` (`constructor(string,string,string,address)`), `TapContainerLock`
(`constructor(address,uint256,address,address,address,string)`) and, from
`assets/tap-draft-soulbound-credentials/contracts`, `SoulboundNetlistCredential` (`constructor(string,string,string)`,
no library). `forge verify-contract --show-standard-json-input …` prints the standard JSON for the explorer's web
form if the API route is unavailable. Explorer API documentation: https://docs.etherscan.io (v2, chain 97) and
https://www.oklink.com/docs (X Layer Testnet).

## 5. Record

For the TAP's Deployments section write down: chain id, block read at, each address, the code hash of §1, the
`supportsInterface` results of §2, `manifestHash`, `masterSeed`, the pool roots, `frozen()` and `owner()`, and the
one netlist cross-check of §3.1 (a token, its hash, the file's SHA-256 and one `evalOf` result). The draft text with
placeholders is `docs/deploy/deployments-sections.md`.
