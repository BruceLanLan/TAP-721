# Testnet deployment of the TAP-721 family / TAP-721 家族的测试网部署

This package lets the author deploy the reference contracts of the TAP-721 family to a public **testnet** with one
command and their own test key, and gives editors a read-only way to check every deployed address
(`docs/deploy/VERIFY.md`). Nobody but the author ever sees the key: the scripts read `PRIVATE_KEY` from the
environment at run time and never print it. The TAP-7007 contracts (tapnet/2 store, verifier, game) live in their
own repository and have the same package there (`tap-large-netlists/DEPLOY.md`).

本包让作者用自己的测试密钥、一条命令把 TAP-721 家族的参考合约部署到公开**测试网**，并给编辑提供只读核验手册
（`docs/deploy/VERIFY.md`）。密钥只在作者本机：脚本在运行时从环境变量 `PRIVATE_KEY` 读取，从不打印。
TAP-7007 的合约（tapnet/2 存储、验证器、争议游戏）在它自己的仓库里，那里有同样的一套（`tap-large-netlists/DEPLOY.md`）。

## 1. Safety note / 安全提示

- **Use a throw-away test key.** Create a fresh account for this, fund it only from the faucets below, and never
  reuse a key that holds mainnet assets. The scripts refuse the mainnet chain ids 1, 56, 196 and 8453 unless
  `ALLOW_MAINNET=true` is set; that override is not meant for this package.
- Put the key in the environment of one shell (`export PRIVATE_KEY=0x…`) or in `contracts/.env` (git-ignored) and
  `source` it. Never paste it into a file that is committed, a chat, or a command line that ends up in shell history
  of a shared machine.
- The scripts send transactions **only** when `--broadcast` is given. Without it, `forge script` simulates and prints
  what it would do.
- **只用一次性的测试密钥。** 新建一个账户，只从下面的水龙头领测试币，绝不复用持有主网资产的密钥。脚本遇到主网
  链 id（1、56、196、8453）会拒绝，除非设置 `ALLOW_MAINNET=true`，本包不打算用这个开关。
- 密钥放在一个 shell 的环境变量里（`export PRIVATE_KEY=0x…`）或 `contracts/.env`（已被 git 忽略）里再 `source`。
  不要写进会提交的文件、聊天或共享机器的 shell 历史。
- 只有带 `--broadcast` 时脚本才会发交易；不带时 `forge script` 只做模拟并打印将要做的事。

## 2. Chains / 链

| | X Layer Testnet (recommended) | BNB Smart Chain Testnet (second option) |
|---|---|---|
| chainId | **1952** (0x7a0) | **97** |
| Public RPC (`RPC_URL`) | `https://testrpc.xlayer.tech` or `https://xlayertestrpc.okx.com` | `https://bsc-testnet-rpc.publicnode.com` or `https://data-seed-prebsc-1-s1.bnbchain.org:8545` |
| Gas token | test OKB | tBNB |
| Faucet | https://www.okx.com/xlayer/faucet | https://www.bnbchain.org/en/testnet-faucet (also https://testnet.bnbchain.org/faucet-smart) |
| Explorer | https://www.oklink.com/xlayer-test (OKLink; also https://web3.okx.com/explorer/x-layer-testnet) | https://testnet.bscscan.com |
| `eth_gasPrice` seen on 2026-10-21 | 0.020000001 gwei (the same 0.02 gwei minimum as X Layer mainnet, `measurements/l1fee.md` in tap-large-netlists) | 0.1 gwei |
| CREATE2 factory `0x4e59b44847b379578588920cA78FbF26c0B4956C` (forge deploys linked libraries through it) | present (141 bytes of code read on 2026-10-21) | present |

Sources: the EIP-155 chain registry `ethereum-lists/chains` (`_data/chains/eip155-1952.json`, `eip155-97.json`;
chainlist.org serves the same data, https://chainlist.org/chain/1952), the X Layer developer portal
https://web3.okx.com/xlayer/docs, and the BNB Chain docs https://docs.bnbchain.org. Chain ids and gas prices were
confirmed read-only with `cast chain-id --rpc-url …` and `cast gas-price --rpc-url …` on 2026-10-21. The mainnet
figures the TAPs cite (X Layer 196, BNB Smart Chain 56, Base 8453) come from `measurements/l1fee.md` of
tap-large-netlists and the fork test `contracts/test/fork/ContainerLock.t.sol`.

X Layer Testnet is the first choice because the family's mainnet target is X Layer (the manifest example, the
companion for TapeCode-Test1, the container lock) and the testnet runs the same OP-Stack rules and fee floor. BNB
Smart Chain Testnet is the fallback if the X Layer faucet is dry: same EVM version (`shanghai` in `foundry.toml`),
different gas token.

首选 X Layer 测试网：家族的主网目标就是 X Layer（示例清单、TapeCode-Test1 的伴生合约、容器锁），测试网与主网
同为 OP Stack、同样的最低 gas 价。X Layer 水龙头领不到币时用 BSC 测试网：EVM 版本相同（`foundry.toml` 的
`shanghai`），只是 gas 代币不同。

## 3. Prerequisites / 前提

- Foundry **v1.8.3** (`forge`, `cast`, `anvil`; the CI pins the same version). `foundryup -v v1.8.3`.
- Python 3.9+ (only for the gas summary of the dry run and the off-chain re-checks of `VERIFY.md`).
- The repository with its submodule: `git submodule update --init` (forge-std v1.17.0 under `contracts/lib`).
  The soulbound project links the same checkout: `ln -sfn ../../../../contracts/lib/forge-std assets/tap-draft-soulbound-credentials/contracts/lib/forge-std`
  (the CI does the same).
- A funded test account on the chosen chain. The whole family costs about 23 million gas (§6), i.e. about
  0.0005 OKB on X Layer Testnet at 0.02 gwei or about 0.0023 tBNB on BSC Testnet at 0.1 gwei; one faucet claim is
  plenty. The deployer address is `cast wallet address --private-key "$PRIVATE_KEY"` (prints only the address).

## 4. What gets deployed / 部署什么

Every script uses the worked example of `assets/tap-draft-netlist-bound-nft/example` so that an editor can check the
deployment against committed test vectors, not against values only the author knows.

| Script | Contracts | Constructor arguments (defaults; env overrides in the script header) | Lifecycle run by the script |
|---|---|---|---|
| `contracts/script/DeployCore.s.sol:DeployCore` | `TapNetlistVM` (library, deployed by forge through CREATE2 and linked), `TapNetlistNFT` | `("TAP-721 Example Collection", "TAP721X", "https://example.invalid/tap-example/token/", deployer)` | `commitManifest(sha256(example/manifest.json), 1, 8, pools IMAGE_V1/NETLIST_V1)` → `mint` 1..8 to the deployer → `reveal(0x000102…1f)` (the example's fixed seed) → `bind` every token in both pools → `storeNetlist` of the three example `.tapnet` files → `freeze()` (skip with `FREEZE=false`) |
| `contracts/script/DeployCompanion.s.sol:DeployCompanion` | `ExampleLegacy721` (test stand-in for a legacy ERC-721, lives in `script/`), `TapCompanion` | legacy: `("TAP-721 Example Legacy", "TAP721L", baseURI, deployer)`; companion: `(legacy, bytes4(keccak256("uriFrozen()")), deployer)` | legacy: mint 1..8, `freezeURI()`; companion: commit, reveal, bind, store, `endorse()` (the deployer owns the legacy), `seal()` → `frozen()` latches. With `LEGACY_COLLECTION=<address>` the script deploys only the companion and stops after commit + reveal. |
| `contracts/script/DeployContainerLock.s.sol:DeployContainerLock` | `TapContainerLock` (tool, not a standard) | `PROCESSOR, CIRCUIT_ID, CONTAINER, OPENER, BINDING, ON_CHAIN_NAME` from the environment | none. Needs the TapeOut contracts of TAP-10, which exist on the mainnets only; on anvil it deploys mocks. **Not part of the testnet run.** |
| `assets/tap-draft-soulbound-credentials/contracts/script/DeploySoulbound.s.sol:DeploySoulbound` | `SoulboundNetlistCredential` | `("TAP-5192 Example Credential", "TAP5192X", "https://example.invalid/tap-5192/")`; the rebind delay is the contract constant `REBIND_DELAY = 7 days` | `storeNetlist` of the `xor` example of `vectors.json`. No credential is issued. |
| *(TODO hook)* | mint-bound collection | — | `DeployCore.s.sol` has a `TODO(mint-bound)` comment where the mint-bound contract of another branch is to be added once it lands under `src/core/`. |

Each script writes its addresses and the values an editor compares to `deployments/<chainId>.json` of its Foundry
project (`contracts/deployments/…` and `assets/tap-draft-soulbound-credentials/contracts/deployments/…`), one
section per script, merged when the file exists. `foundry.toml` grants read-write access to `./deployments` for this.

## 5. Commands / 命令

Names only; never write the values into this file.

```bash
# once per shell / 每个 shell 一次
export PRIVATE_KEY=…            # the test key (0x-prefixed hex)   测试密钥
export RPC_URL=…                # https://testrpc.xlayer.tech or a BSC Testnet RPC of §2

# one command for the whole family (core, companion, soulbound) / 一条命令部署全家族
contracts/script/deploy-testnet.sh
```

The wrapper runs, in this order, the three commands below; they can also be run one by one:

```bash
cd contracts
forge script script/DeployCore.s.sol:DeployCore           --rpc-url "$RPC_URL" --broadcast --slow
forge script script/DeployCompanion.s.sol:DeployCompanion --rpc-url "$RPC_URL" --broadcast --slow
cd ../assets/tap-draft-soulbound-credentials/contracts
forge script script/DeploySoulbound.s.sol:DeploySoulbound --rpc-url "$RPC_URL" --broadcast --slow
```

Leave out `--broadcast` to simulate first. Keep `--slow`: it waits for each receipt before sending the next
transaction. Without it forge sends the whole batch at once, and a node that cannot fit the batch into one block
(anvil did not: 28.4 million gas went into one block and the next transaction stayed pending, `docs/deploy/anvil-dry-run.md`)
or a public RPC with rate limits leaves `forge script` waiting. Add `--legacy` only if the RPC does not support
EIP-1559 (both testnets do). The gas price is taken from the node;
nothing in the scripts sets a price.

A failed script can be rerun: `forge script … --resume` continues the broadcast that was interrupted. A script that
already finished creates new contracts when run again (the example collection is cheap, so that is harmless), except
the `TapNetlistVM` library, which forge re-uses at its CREATE2 address.

Optional (the explorer's source verification; needs an explorer API key, see `docs/deploy/VERIFY.md` §4):
`--verify --verifier … --etherscan-api-key "$EXPLORER_API_KEY"` on the same commands.

## 6. Expected gas (anvil dry run) / 预计 gas（anvil 预演）

Measured with `contracts/script/anvil-dry-run.sh` and
`assets/tap-draft-soulbound-credentials/contracts/script/anvil-dry-run.sh` on Foundry 1.8.3 (receipts of the
local anvil node; `docs/deploy/anvil-dry-run.md` has the per-transaction tables and the resulting JSON):

| Script | Transactions | Gas used | at 0.02 gwei (X Layer Testnet) | at 0.1 gwei (BSC Testnet) |
|---|---|---|---|---|
| DeployCore (library + collection, full lifecycle) | 32 | 8,650,578 | 0.000173 OKB | 0.000865 tBNB |
| DeployCompanion (legacy stand-in + companion, full lifecycle) | 34 | 8,849,372 | 0.000177 OKB | 0.000885 tBNB |
| DeploySoulbound (credential + one stored file) | 2 | 5,191,911 | 0.000104 OKB | 0.000519 tBNB |
| **Family total** | **68** | **22,691,861** | **about 0.00045 OKB** | **about 0.0023 tBNB** |
| DeployContainerLock (mainnet tool; anvil mocks only) | 5 | 1,167,475 (690,546 for the lock itself) | — | — |

`forge script` prints an "estimated total gas" about 1.3× higher than the receipts (its safety margin); fund for
the estimate. No single transaction exceeds 5.4 million gas, far below both chains' block limits.

## 7. What to send back / 部署后发回什么

1. `contracts/deployments/<chainId>.json` and `assets/tap-draft-soulbound-credentials/contracts/deployments/<chainId>.json`
   (commit them on a branch, or attach them). They hold every address, the deployer, the block, the manifest hash,
   the seed, the pool roots and the interface ids.
2. The broadcast records `contracts/broadcast/*/<chainId>/run-latest.json` (git-ignored; attach them): transaction
   hashes for the explorer.
3. The chain, RPC used and the date. Nothing else: no key, no faucet account.

With these the editors run `docs/deploy/VERIFY.md` and paste the result into the "Deployments" sections drafted in
`docs/deploy/deployments-sections.md`.

发回 `deployments/<chainId>.json`（两个 Foundry 项目各一个）、`broadcast/*/<chainId>/run-latest.json`（含交易哈希）、
所用的链与 RPC、日期。不要发任何密钥。

## 8. Dry run without a chain / 不上链的预演

```bash
cd contracts && ./script/anvil-dry-run.sh
cd assets/tap-draft-soulbound-credentials/contracts && ./script/anvil-dry-run.sh
```

Starts a local `anvil`, runs every script with anvil's public default account 0 (a well-known constant, not a
secret), prints the gas per transaction and the resulting `deployments/31337.json`, and stops anvil. The CI job
`forge` runs the same.
