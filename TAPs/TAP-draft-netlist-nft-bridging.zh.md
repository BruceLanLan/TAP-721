---
tap: TBD
title: Moving Netlist-Bound NFTs between TapeOut Chains
description: A lock-and-mint bridge for netlist-bound ERC-721 tokens across the TapeOut chains, with one payload format carried over LayerZero V2, the TAP-10 hub, or both at once.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-10, TAP-draft-netlist-bound-nft, ERC-165, ERC-721, ERC-4906, EIP-712, EIP-7702, LayerZero V2 EndpointV2 (deployed bytecode, code hashes in Deployments)
license: CC0-1.0
---

本文是 `TAP-draft-netlist-nft-bridging.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。

# TAP-TBD：在 TapeOut 各链之间转移网表绑定 NFT

## 概要

本 TAP 扩展 TAP-721（网表绑定 NFT），让 TAP-721 代币的持有人可以把它从创建它的链转移到另一条 TapeOut 链再转回来，网表和图像随之同行，且任何时刻只存在一份可用的副本。

## 摘要

本 TAP 是 TAP-721（网表绑定 NFT，`TAP-draft-netlist-bound-nft`）的扩展：它增加 TAP-721 代币的跨链转移，不改动 TAP-721 本身的任何内容。TAP-721 代币存在于 TAP-10 链表中某一条链上的一个 ERC-721 合约里，这条链即它的**原链**。本 TAP 规定这样的代币如何转移到其它 TapeOut 链：原链上的**网关合约（Gateway）**把代币锁入托管，其它每条链上的**镜像合约（Mirror）**铸造一个编号相同的代币，代币返回原链时再将其销毁；代币总是经由原链中转（星形路由，hub-and-spoke），因此网关合约知道每个代币在哪条链上。镜像合约是 ERC-721 合约，同时提供代币的网表哈希、图像哈希和清单哈希，并接受网表文件本身，使任何链上的游戏都能读取该电路。本 TAP 固定集合键、一个 320 字节的载荷及其消息 ID、端点状态机，以及一个屏蔽消息层差异的适配器接口。LayerZero V2（TapeOut 已用于其矿机桥）以规范性方式给出配置规范；TAP-10 DeWEB hub 的跨链验证仍待定，其配置规范仅作为参考信息给出。每条路由使用两种策略之一：`ONE`（一个消息层送达即可）或 `ALL`（所列每个消息层都必须送达完全相同的载荷，之后才发生任何效果）。

## 动机

TapeOut 运行在 BNB Smart Chain、Base 和 X Layer 上（TAP-10 §2.1）。集合在其中某一条链上创建：作为 TAP-721 缘起的集合 TapeCode-Test1 在 X Layer 上，而设计证明（Proof-of-Design）挖矿和大多数电路工具在 BNB Smart Chain 上。持有人和游戏开发者希望代币能在活动所在的链上使用，又不必放弃原件。

TapeOut 已经为一类资产解决了这个问题。它的矿机桥通过 LayerZero V2 把矿机从 BNB Smart Chain 转移到 X Layer：BNB Smart Chain 上的金库（`0x48D43345656f0f9510dC3c06CBa99dFf597617C2`）把每台矿机分别托管，X Layer 上的凭证合约（`0x9cfc959cd42B2e1d39a0d850c528210E818AE520`）铸造一个可以赎回的代币。这一设计专为矿机而做，不是标准：其它集合无法复用，它不携带网表数据，而且绑定在单一消息层上。

需要一个标准，原因有三：

- **既有集合无法修改。** TapeCode-Test1 已经部署，供应量已全部铸出，唯一可变的状态是 base URI。要求集合配合销毁与铸造的桥（如 LayerZero 原生形式的 ONFT721）无法服务它。锁定-铸造（lock-and-mint）适用于任何 ERC-721，无需改动。
- **网表必须随代币同行。** 只有当远端链能分辨镜像代币携带的是哪份网表时，它对电路游戏才有用。因此载荷携带网表、图像和清单哈希，镜像合约无需许可即可接受与之匹配的网表文件。
- **消息层是一种信任选择。** LayerZero V2 如今已在 TapeOut 生产环境中使用；TAP-10 hub 是 TapeOut 自己的消息层，但只把消息存在发送链上。无论使用哪个消息层，集合都需要同一种载荷和同一种端点行为；不愿依赖单一消息层的集合还需要能够要求两个相互独立的消息层。

## 规范

本文中的关键词 "MUST"、"MUST NOT"、"REQUIRED"、"SHALL"、"SHALL NOT"、"SHOULD"、"SHOULD NOT"、"RECOMMENDED"、"NOT RECOMMENDED"、"MAY" 与 "OPTIONAL"，当且仅当以全大写出现时，按 RFC 2119 与 RFC 8174 的描述解释。

标有 **[待定]**（[Open]）的条目尚未决定；它们列在"安全考虑"末尾的"待定问题"中。

### 1. 术语与记号

| 术语 | 含义 |
|---|---|
| 原链、原集合 | 创建该集合的链（TAP-10 §2.1）及 ERC-721 合约 |
| 数据源 | 实现 `ITapNetlistNFT`（TAP-721 §8.2）且其 `collection()` 为原集合的合约：集合本身，或其伴生合约（TAP-721 §8.3）。网关合约 MAY 有一个数据源 |
| 端点 | 网关合约或镜像合约 |
| 网关合约（Gateway） | 原链上的端点。托管已离开的代币 |
| 镜像合约（Mirror） | 任何其它 TapeOut 链上的端点。一个 ERC-721 合约，为到达的代币铸币，销毁离开的代币 |
| 适配器 | 通过某一个消息层在端点之间传送载荷的合约（§8） |
| 消息层 | 一种跨链传输：LayerZero V2（§9），或带验证器的 TAP-10 hub（§10，参考性） |
| 路由 | 端点面向另一条链的配置：策略、适配器列表、对端端点（§5.1） |
| 对端 | 路由另一条链上的端点合约 |
| 载荷 | §4 的 320 字节消息 |
| 来源端点 | 发送载荷的端点；适配器根据经过认证的远端适配器识别它（§8.2） |
| 消息 ID | `keccak256(sourceEndpoint ‖ payload)`，来源端点取其 20 字节地址（§4.1） |
| 活跃代币 | 存在于托管之外的代币：在原集合中由某个账户持有，或已在镜像合约上铸出 |

记号：`‖` 表示字节拼接。字节布局中的整数为大端序。`abi.encode` 为 Solidity ABI 编码。链 ID 为 TAP-10 链表中的 EIP-155 链 ID；TapeOut 各链为 56（BNB Smart Chain）、8453（Base）和 196（X Layer）。

### 2. 不变式

对集合的每个代币编号，在所有 TapeOut 链上至多存在一个活跃代币。每次离开都在发送载荷的同一笔交易中让代币退出流通（在原链上托管，在镜像合约上销毁）；每次到达都只有在该载荷满足路由策略（§7）之后才让代币重新进入流通（在原链上释放，在镜像合约上铸造）。对每个消息 ID，代币至多到达某条链一次。

代币只按原链 → 镜像和镜像 → 原链的方向转移（星形路由）；从一个镜像转到另一个镜像，需经原链两次转移。网关合约记录每个托管代币离开时前往的链，只有来自该链的消息才能释放它（§5.2）。以销毁代替托管的原生集合不在本版本范围之内。

### 3. 集合键

```
collectionKey = keccak256(abi.encode("TAP-NFT collection v1", uint64 homeChainId, address homeContract))
```

该字符串按动态 `string` 进行 ABI 编码。一个集合的所有端点 MUST 返回相同的 `collectionKey()` 和 `homeChainId()`，且 MUST 拒绝带有其它集合键的载荷。对 TapeCode-Test1（`homeChainId` 196，`homeContract` `0x0e91460d6823c711643e650a9a4c0cc21de41614`），集合键为 `0x8755cf608e750f9bd55ba6ac4c0e655dffffc199774518f82624273f5217b4bd`。

### 4. 载荷

#### 4.1 布局

```
payload   = abi.encode(uint8 version, bytes32 collectionKey, uint256 tokenId, address to,
                       bytes32 netlistHash, bytes32 imageHash, bytes32 manifestHash,
                       uint64 srcChainId, uint64 dstChainId, uint64 nonce)
messageId = keccak256(sourceEndpoint ‖ payload)        sourceEndpoint: the sending endpoint's 20-byte address
```

| 偏移 | 字 | 内容 |
|---|---|---|
| `0x000` | version | `1` |
| `0x020` | collectionKey | §3 |
| `0x040` | tokenId | 原集合中的代币编号 |
| `0x060` | to | 目标链上的接收方，左侧填充 12 个零字节；非零 |
| `0x080` | netlistHash | 绑定到该代币的 `tapnet/1` SHA-256（TAP-721 §2.3）；没有则为零 |
| `0x0a0` | imageHash | 绑定到该代币的图像 SHA-256；没有则为零 |
| `0x0c0` | manifestHash | 集合清单的 SHA-256；没有则为零 |
| `0x0e0` | srcChainId | 发送端点的链 ID |
| `0x100` | dstChainId | 接收端点的链 ID |
| `0x120` | nonce | 发送端点的外发计数器，从 0 开始，每次离开加 1 |

载荷恰为 320 字节。接收端点 MUST 拒绝（以 `BadPayload()` revert）载荷，除非：长度为 320；version 字等于 1；`to` 字非零且其高 96 位为零；三个 `uint64` 字各自的高 192 位为零。因此一个载荷恰有一种编码。发送端点用它自己的地址计算消息 ID，接收端点用其适配器认证过的来源端点计算（§8.2）。由于 `(source endpoint, nonce)` 永不重复，消息 ID 也不会重复，即使某个端点被替换、其继任者从 nonce 0 重新开始也是如此。

#### 4.2 哈希

- 有数据源的网关合约 MUST 在离开时用数据源的 `netlistHashOf(tokenId)`、`imageHashOf(tokenId)` 和 `manifestHash()` 填写 `netlistHash`、`imageHash` 和 `manifestHash`；若数据源的 `masterSeed()` 非零（包括无揭示集合的全 1 值，TAP-721 §8.2 第 2 条）、代币为清单所覆盖，且数据源有含网表字段的池而 `netlistHashOf(tokenId)` 为零，或有含图像字段的池而 `imageHashOf(tokenId)` 为零（字段以 `pools()` 为准，TAP-721 §5.2），MUST revert（`NotBound(uint256)`）：揭示之后，被覆盖的代币先绑定（TAP-721 §8.2）再离开。数据源若未通过 ERC-165 报告 `ITapNetlistTokenSet`，或其 `tokenSetHash()` 为零，则处于区间模式，代币编号位于数据源的 `tokenRange()` 之内即为被覆盖。否则处于代币集模式（TAP-721 §5.4），此时 `tokenRange()` 返回 `(0, count)`，并不是一个区间，网关合约 MUST NOT 用它做此判断：除非 `tokenAt(0)` 成功（表明代币集文件已记录到链上；在参考实现中，记录代币集无需许可），网关合约 MUST revert（`NotBound`）；此后 `indexOf(tokenId)` 不 revert 的代币即为被覆盖。未被覆盖的代币永远无法绑定，以零哈希离开。没有数据源的网关合约发送零。
- 镜像合约 MUST 发送它为该代币保存的值（§5.3）。
- 网关合约 MUST 忽略到达载荷中的哈希：原链数据源才是权威。

#### 4.3 完整示例

TapeCode-Test1 #7 离开 X Layer 前往 BNB Smart Chain，接收方为 `0x00000000000000000000000000000000000000b0`，是位于示例地址 `0x00000000000000000000000000000000000a0196` 的网关合约的第一次离开（nonce 0）。网表是 23 字节的 `tapnet/1` 文件 `5441504e45540100000000020000000100000002000003`（一个 NAND）；图像和清单哈希分别是 ASCII 字符串 `example image` 和 `example manifest` 的 SHA-256。（示例值；该向量即"测试用例"中的 `home-to-remote`。）

```
0x000  0000000000000000000000000000000000000000000000000000000000000001   version
0x020  8755cf608e750f9bd55ba6ac4c0e655dffffc199774518f82624273f5217b4bd   collectionKey
0x040  0000000000000000000000000000000000000000000000000000000000000007   tokenId
0x060  00000000000000000000000000000000000000000000000000000000000000b0   to
0x080  b6438e95fafa86bad91caa97b0893dbd520bb71b94cf053a7b677858c9609be8   netlistHash
0x0a0  0d85f5af1e0dfa09503f0bdb179ab8f37c4225b43d442a3a91e59c3c849bc99e   imageHash
0x0c0  89333bc71f02c647533ab52e592ad22c609728f12eabff6fda0920109db40401   manifestHash
0x0e0  00000000000000000000000000000000000000000000000000000000000000c4   srcChainId 196
0x100  0000000000000000000000000000000000000000000000000000000000000038   dstChainId 56
0x120  0000000000000000000000000000000000000000000000000000000000000000   nonce 0

keccak256(payload) = 0x11c7027b724893ce8f921c02e44af216e59a0878b57502bfe8c6edd032487497
messageId          = 0xc4ced4c2227e9504511e68531d1975140f510e3a0d19b5bcd44db3f33e681e58
```

### 5. 端点

#### 5.1 共同行为

每个端点实现 `ITapBridgeEndpoint` 与 `ITapBridgeTransfer`，通过 ERC-165 声明这两个接口，并记录：

- `departed[messageId]`：端点发送载荷时设置；
- `executed[messageId]`：载荷生效时设置；
- `confirmedBy[messageId][adapter]`：在 `ALL` 路由上，适配器送达载荷时设置。在 `ONE` 路由上不记录，`executed` 是唯一的记录。

**路由。** 对每条其它链，路由保存一个策略（`NONE` = 0、`ONE` = 1、`ALL` = 2）、一个有序的适配器列表和对端端点。`setRoute(chainId, policy, adapters, peer)` MUST revert（`NotOwner()`、`Sealed()` 或 `BadRoute()`），除非：调用者是所有者且路由尚未封存；`chainId` 既不是 0 也不是本链；`policy` 为 0、1 或 2；`NONE` 时适配器列表为空；`ONE` 时恰有一项；`ALL` 时有 2 至 8 项；各项非零且互不相同；`ONE` 和 `ALL` 时 `peer` 非零；在镜像合约上，`chainId` 为原链。`NONE` 在两个方向上关闭该路由。不存在其它策略值。

**封存。** `sealRoutes()` MUST revert，除非调用者是所有者、至少有一条路由开放，且任何路由上列出的每个适配器都报告 `adapterSealed()` = true（`AdapterNotSealed(address)`，§8.3）。随后它设置 `routesSealed`、清除所有者并发出 `RoutesSealed`；此操作不可逆。因此，已封存的端点同时保证它的任何适配器都无法再改变消息的认证方式。

**离开。** `bridge(tokenId, dstChainId, to, contractRecipientOk, options)` MUST 按以下顺序：

1. 在以下情况 revert：`to` 为零；`to` 在本链上有代码（EIP-7702 委托标识除外，即恰为 23 字节且以 `0xef0100` 开头）而 `contractRecipientOk` 为 false（`ContractRecipient(address)`）；路由为 `NONE`；或 `to` 是路由的对端或端点自身（`EndpointRecipient(address)`）；
2. 除非 `options` 为空或对路由的每个适配器各有一项，否则 revert；
3. 让代币退出流通（§5.2、§5.3）；除非调用者是代币持有人、获得持有人全部代币授权的操作者，或获得该代币授权的账户，否则此步 revert；
4. 用下一个 nonce 构造载荷，设置 `departed`，发出 `Departed`；
5. 按路由顺序对路由的每个适配器调用 `send`，附上该适配器 `quote` 返回的费用（§12），并把多余的价值退还给调用者。

`quoteBridge` 对相同参数返回总费用和各适配器的费用。

**到达。** `receivePayload(srcChainId, srcEndpoint, payload)` MUST 按以下顺序：

1. 若通往 `srcChainId` 的路由为 `NONE`、调用者不在其适配器列表中，或 `srcEndpoint` 不是该路由的 `peer`，则 revert；
2. 严格解码载荷（§4.1），除非 `srcChainId` 等于载荷的 `srcChainId`、载荷的 `dstChainId` 等于本链链 ID、其 `collectionKey` 等于本端点的集合键、且其 `to` 不是端点自身，否则 revert；
3. 计算 `messageId = keccak256(srcEndpoint ‖ payload)`；若 `executed[messageId]` 已设置，则 revert（`Replay(bytes32)`）；
4. 发出 `Confirmed(messageId, caller)`；
5. 在 `ALL` 路由上：若 `confirmedBy[messageId][caller]` 已设置则 revert，否则设置它；然后，除非路由**当前**适配器列表中的每个适配器 `a` 都已设置 `confirmedBy[messageId][a]`，否则直接返回、不产生效果；
6. 设置 `executed[messageId]`，为 `to` 让代币重新进入流通（§5.2、§5.3），并发出 `Arrived`。

本链链 ID 是构造时的 `block.chainid`。

**重发。** `resend(payload, adapterIndex, options)` 无需许可。除非 `departed[keccak256(endpoint ‖ payload)]` 已设置，否则 MUST revert；且 MUST 通过当前路由的第 `adapterIndex` 个适配器把载荷原样发往载荷的目标链，收取该适配器的报价并退还其余部分。由于到达按消息 ID 和适配器记录，重发可以补全一条挂起的 `ALL` 消息，但绝不会让一个载荷生效两次。

**接口。** 下列每个选择器是函数签名的 `keccak256` 的前 4 个字节，每个 ERC-165 标识符是该接口各函数选择器的异或；它们也都列在 `vectors.json` 中（测试用例）。

`ITapBridgeEndpoint`（标识符 `0x3d6a52e3`）：

| 函数 | 选择器 |
|---|---|
| `receivePayload(uint64 srcChainId, address srcEndpoint, bytes payload)` | `0xcb4d10e1` |
| `collectionKey() returns (bytes32)` | `0x11305740` |
| `homeChainId() returns (uint64)` | `0xef126967` |
| `route(uint64 chainId) returns (uint8 policy, address[] adapters, address peer)`（`policy` 是枚举，在 ABI 中为 `uint8`） | `0x9e38705d` |
| `routesSealed() returns (bool)` | `0x963d0c78` |

`ITapBridgeEndpoint` 还声明以下事件：

| 事件 | topic0 |
|---|---|
| `Departed(bytes32 indexed messageId, uint256 indexed tokenId, uint64 dstChainId, address to)` | `0xb5be151363c3a3ff877f22f1a2b29b927c303c39455f28969c828e77a284c564` |
| `Confirmed(bytes32 indexed messageId, address indexed adapter)` | `0xd4964a7cd99f5c1fa8f2420fb5e1d3bd26eadf16e2658cf2e29a67dfda38601e` |
| `Arrived(bytes32 indexed messageId, uint256 indexed tokenId, uint64 srcChainId, address to)` | `0x8b93f26fdf44f4f9532c9bccd40895f7bf298adc1902c7a86eb995ee36ba736a` |

`ITapBridgeTransfer`（标识符 `0xdbc2d1d3`）：

| 函数 | 选择器 |
|---|---|
| `quoteBridge(uint256 tokenId, uint64 dstChainId, address to, bytes[] options) returns (uint256 total, uint256[] fees)` | `0xaed4dd7d` |
| `bridge(uint256 tokenId, uint64 dstChainId, address to, bool contractRecipientOk, bytes[] options) payable returns (bytes32 messageId)` | `0x1ddf49a0` |
| `resend(bytes payload, uint256 adapterIndex, bytes options) payable returns (bytes32 transportId)` | `0x8dbe72e9` |
| `departed(bytes32) returns (bool)` | `0x2084e062` |
| `executed(bytes32) returns (bool)` | `0xa9fcfb33` |
| `confirmedBy(bytes32, address) returns (bool)` | `0x34a5b4aa` |
| `nextNonce() returns (uint64)` | `0xd69c3d30` |
| `setRoute(uint64 chainId, uint8 policy, address[] adapters, address peer)` | `0x9a50a738` |
| `sealRoutes()` | `0x14660214` |

`ITapBridgeTransfer` 声明 `RouteSet(uint64 indexed chainId, uint8 policy, address[] adapters, address peer)`（`0xa555875b3d8c275c0366501b23edd5240ebc78f5374d6b9983540a89b2eedcbd`）和 `RoutesSealed()`（`0x8b978f73eaca99332cb4c63aaaca48701bb356b32365e7e247fe9a0e65b5c370`）。

**错误。** 在本节和 §5.2–§5.3 指明之处，端点以下列错误 revert；工具 MAY 依据它们区分原因（§9"重试"）：

| 错误 | 选择器 | 触发条件 |
|---|---|---|
| `BadPayload()` | `0x442dd415` | §4.1 解码失败 |
| `RouteClosed(uint64)` | `0x0122f114` | 路由为 `NONE` |
| `NotAdapter(address)` | `0x08b4a225` | `receivePayload` 的调用者未列在路由上 |
| `WrongPeer(address)` | `0x70260226` | `srcEndpoint` 不是路由的对端 |
| `WrongSource()` / `WrongDestination()` / `WrongCollection()` | `0x83efd75c` / `0xef94f60c` / `0x747d07f2` | 载荷的链 ID 或集合键不匹配 |
| `Replay(bytes32)` | `0x7e7b2e50` | 该消息 ID 已执行 |
| `AlreadyConfirmed(bytes32,address)` | `0x900bdd46` | 在 `ALL` 路由上同一适配器送达两次 |
| `NotDeparted(bytes32)` | `0x830e142b` | `resend` 的载荷并非本端点发出 |
| `ZeroRecipient()` / `ContractRecipient(address)` / `EndpointRecipient(address)` | `0xd27b4443` / `0xc9cd32cd` / `0x777e60a5` | 离开与到达时的接收方检查 |
| `BadOptions()` / `InsufficientFee(uint256,uint256)` / `RefundFailed()` | `0x26864a7a` / `0xa458261b` / `0xf0c49d44` | 选项数量、费用、退款 |
| `NotOwner()` / `Sealed()` / `BadRoute()` / `AdapterNotSealed(address)` | `0x30cd7471` / `0x1b2d71eb` / `0xc4c321d1` / `0x4fec0d65` | 路由配置与封存 |
| `NotAuthorized()` / `AlreadyEscrowed(uint256)` / `NotEscrowed(uint256)` / `NotOnRoute(uint256,uint64)` / `EscrowFailed(uint256)` / `NotBound(uint256)` | `0xea8e4eb5` / `0xc826d283` / `0xa64a2c0c` / `0x62caffe3` / `0x054f9d0d` / `0xd0078a0a` | 网关合约（§5.2、§4.2） |
| `ERC721NotAuthorized(address,uint256)` / `AlreadyLive(uint256)` / `OutOfRange(uint256)` / `ManifestConflict(bytes32,bytes32)` / `NotHomeCollection()` | `0xb226c90b` / `0x6adc3ab8` / `0x6f2fb69e` / `0xda3bad61` / `0xbbfa1ada` | 镜像合约（§5.3） |

#### 5.2 网关合约

网关合约部署时给定原集合和一个可选的数据源；它的 `homeChainId` 就是本链。若给定的数据源其 `collection()` 不是原集合，构造函数 MUST revert。

- **离开：** 若代币已在其托管中，无论集合的授权语义如何，网关合约都 MUST revert（`AlreadyEscrowed`）；在 §5.1 的调用者检查之后，它在原集合上调用 `transferFrom(owner, gateway, tokenId)`，除非随后 `ownerOf(tokenId)` 为网关合约，否则 MUST revert，并把目标链记为该代币的位置（`locationOf(uint256) returns (uint64)`，`0x6b8b81b8`；0 = 未托管）。因此持有人在第一次离开之前要在原集合上授权网关合约。
- **到达：** 除非该代币有记录的位置且由网关合约持有，否则网关合约 MUST revert（`NotEscrowed`）；除非载荷的 `srcChainId` 等于该位置，否则 MUST revert（`NotOnRoute`）；它清除该记录并调用 `transferFrom(gateway, to, tokenId)`。它 MUST NOT 使用 `safeTransferFrom`（接收合约不能拒绝返回的代币）。
- 网关合约 MUST NOT 实现 `onERC721Received`，使得用 `safeTransferFrom` 转入托管会失败；在 `bridge` 之外用普通 `transferFrom` 转给网关合约会把代币永久锁住，钱包 SHOULD 对此发出警告。
- 除到达之外，网关合约没有任何能移动已托管代币的函数。

**发现集合的端点。** 原集合的代币元数据（TAP-721 §7.1）MAY 在其 `tap` 对象中包含 `"bridge": {"chainId": <home chain id>, "gateway": "<lowercase address>"}`。客户端找到它后，MUST 先检查网关合约的 `homeChainId()` 等于该集合所在链，且其 `collectionKey()` 等于由该链 ID 与集合地址按 §3 计算出的键，再使用它。集合在链 `c` 上的正式镜像合约是网关合约 `route(c)` 的 `peer`。客户端 MUST NOT 接受无法通过这种方式从网关合约到达的镜像合约，无论其名称、符号或集合键是什么。

#### 5.3 镜像合约

镜像合约部署在原链之外的链上，部署时给定 `homeChainId`、原集合地址、名称和符号、base URI，以及从原集合复制的代币区间 `(firstTokenId, supply)`。`supply` = 0 表示区间无上界；这属于 TAP-721 §8.2 所说的桥接副本情形。代币集模式（TAP-721 §5.4）下的集合，其镜像合约 MUST 以 `supply` = 0 部署，因为数据源的 `tokenRange()` 所返回的 `(0, count)` 并不是被覆盖编号的集合。镜像合约实现带元数据扩展的 ERC-721、ERC-165、ERC-4906、`ITapBridgeMirror`，以及下文 `ITapNetlistNFT` 的镜像配置规范。

- **到达：** 若该代币已存在于镜像合约上，镜像合约 MUST revert（`AlreadyLive`）；若 `supply` ≠ 0 且代币编号超出范围，MUST revert（`OutOfRange`）。若载荷的 `manifestHash` 非零：当镜像合约的 `manifestHash()` 为零时，存储它并发出 `ManifestCommitted`；当两者不同时，镜像合约 MUST revert（`ManifestConflict`）。镜像合约为该代币存储载荷中的 `netlistHash` 和 `imageHash`，把非零的 `netlistHash` 记为已知，不调用 `onERC721Received` 地把代币铸给 `to`，并发出 ERC-4906 `MetadataUpdate(tokenId)`。
- **离开：** 在 §5.1 的调用者检查之后，镜像合约销毁代币并发送它保存的哈希。销毁之后哈希仍保留：`netlistHashOf`、`imageHashOf` 和 `netlistOf` 继续返回最后一次带入的值，而 `ownerOf` 会 revert。之后的到达会覆盖它们。
- **网表文件：** `storeNetlist(file)` 及其别名 `materialize(file)` 无需许可。除非 SHA-256(`file`) 是已知网表哈希、文件不超过 49,152 字节且是有效的 `tapnet/1`（TAP-721 §2.2、§8.2 第 4 条），否则它们 MUST revert；存储后的文件可通过 `netlistFile(hash)` 和 `netlistOf(tokenId)` 读取。存储是幂等的。`storeNetlist(bytes)`（`0xf8b0cc86`）、`netlistFile(bytes32)`（`0x5267c429`）和 `netlistOf(uint256)`（`0xae502e0b`）的选择器，以及 `ManifestCommitted(bytes32)`（`0x283da7c24290f991388adb4188dab383e865d9edad5d228e8b95805b85bba620`）和 `NetlistStored(bytes32,address)`（`0x4095b27949435770a1b733b92eb73b92fb8d0c052ef06cf5db328010d57a64ed`）的 topic，均为 `ITapNetlistNFT` 的（TAP-721，测试用例）；`MetadataUpdate(uint256)` 属于 ERC-4906（`0xf8e1a15aba9398e019f0b49df1a4fde98ee17ae345cb5f6b5e2c27f5033e8ce7`）。
- **tokenURI：** `baseURI ‖ decimal tokenId`；base URI 为空时为空字符串。base URI 在部署时固定。镜像合约 `tokenURI` 处的文档 MUST 与原集合同一代币的文档逐字节相同，后者以原链标识符标识该代币（TAP-721 §4.1）。在原集合的元数据位置确定之前，SHOULD NOT 部署镜像合约。

**`ITapNetlistNFT` 的镜像配置规范。** 镜像合约没有自己的清单文件、池或揭示。它返回：`collection()` = 镜像合约自身；`tokenRange()` = 部署时的区间；`manifestHash()` = 第一个带入的非零清单哈希（一旦非零就不再改变）；`pools()` = 空；`masterSeed()` = 0；`frozen()` = false；`netlistHashOf`、`imageHashOf` = 代币携带的哈希（尚无已知哈希时为零），离开后仍保留。`entryIndexOf` 和 `bind` MUST 以错误 `NotHomeCollection()`（选择器 `0xbbfa1ada`）revert。镜像合约不计算条目索引；任何计算条目索引的扩展 MUST 用原链链 ID 和原集合地址（清单中的 `collection`，TAP-721 §6.2）派生池种子，绝不能用镜像合约自己的。这是 TAP-721 §8.2 允许的桥接副本情形。镜像合约通过 ERC-165 同时声明 `ITapNetlistNFT` 和 `ITapBridgeMirror`；客户端发现 `ITapBridgeMirror` 即知揭示和清单文件在原链上。

`ITapBridgeMirror`（标识符 `0xdba6a55e`）：

| 函数 | 选择器 |
|---|---|
| `knownNetlist(bytes32 netlistHash) returns (bool)` | `0xd86844a4` |
| `manifestHash() returns (bytes32)` | `0x337f3f32` |
| `materialize(bytes file) returns (bytes32 netlistHash)` | `0x30b1dec8` |

### 6. 状态机

按代币编号，跨所有链：

| 状态 | 活跃代币在哪里 | 如何离开该状态 |
|---|---|---|
| 在原链 | 原链上的某个账户 | 在网关合约调用 `bridge` → 在途 |
| 在途（原链 → c） | 不存在；原件在网关合约的托管中，位置为 `c` | 链 `c` 上的镜像合约接受到达 → 镜像于 `c` |
| 镜像于 `c` | 链 `c` 上的某个账户 | 在镜像合约调用 `bridge` → 在途（c → 原链） |
| 在途（c → 原链） | 不存在；已在 `c` 上销毁，原件仍在托管中、位置为 `c` | 网关合约接受来自 `c` 的到达 → 在原链 |

按消息 ID，在接收端点：

| 状态 | 含义 | 下一步 |
|---|---|---|
| 未知 | 尚无送达 | 某个所列适配器送达 → 已执行（`ONE`），或挂起（`ALL`） |
| 挂起（仅 `ALL`） | 当前路由的部分而非全部适配器已确认 | 最后一个缺失的适配器送达 → 已执行 |
| 已执行 | 代币已释放或铸出 | 终态；任何送达都以 `Replay` revert |

revert 的送达（错误的对端、错误的来源、`AlreadyLive`、`ManifestConflict`、`NotEscrowed` 等）使消息保持原状态。能否重试取决于消息层（§9、§10）。

### 7. 策略

- **`ONE`**（默认值，SHOULD 采用）：唯一所列适配器的送达立即生效。
- **`ALL`**：每个所列适配器都必须送达逐字节相同的载荷；代币在最后一次确认时释放或铸出。送达的载荷有任何一个字节不同的适配器，确认的是不同的消息 ID，两者都不会生效。
- 不存在 `ANY` 策略（多个适配器中任意一个即可）。

**卡住的适配器。** 端点 MUST NOT 自行从 `ALL` 退回到更少的适配器，也没有超时。若 `ALL` 路由的某个适配器始终不送达，消息保持挂起，代币保持退出流通。恢复途径，按优先顺序：

1. 消息层自身的重试：任何人重新执行失败的 LayerZero 送达（§9），或为 hub 消息提供新的见证人签名（§10）。
2. 在 `sealRoutes()` 之前：所有者在两端的端点上用另一个适配器替换卡住的适配器，任何人通过新适配器调用 `resend`。这依赖所有者，与封存前的每项更改一样。
3. 在 `sealRoutes()` 之后：只剩第一条途径。若封存后某个消息层永久失效，其 `ALL` 路由上在途的代币将丢失，任何账户都无法恢复。

### 8. 适配器

#### 8.1 接口

`ITapBridgeAdapter`（标识符 `0xaa621a3e`）：

| 函数 | 选择器 | 行为 |
|---|---|---|
| `layerId() returns (bytes32)` | `0xd3cf3ef1` | 命名消息层及配置版本的标签的 `keccak256`（§9、§10） |
| `quote(uint64 dstChainId, bytes payload, bytes options) returns (uint256)` | `0x49e6cd30` | 以相同参数调用 `send` 的原生代币费用 |
| `send(uint64 dstChainId, bytes payload, bytes options, address refundTo) payable returns (bytes32 transportId)` | `0x304be9ff` | 只有该适配器的端点可以调用。把载荷原样传送给 `dstChainId` 上的对端适配器 |

一个适配器只服务一个端点，在部署时固定，并且只对该端点调用 `receivePayload`。

#### 8.2 来源端点

适配器传送的是裸的 320 字节载荷。由于一个适配器只服务一个端点，经过认证的远端适配器即标识了发送端点。收到消息时，在消息层自身认证远端适配器之后，适配器 MUST 把该远端适配器所服务的端点作为 `srcEndpoint` 传给 `receivePayload(srcChainId, srcEndpoint, payload)`；若它没有为 `srcChainId` 配置这样的端点，MUST revert。该配置每条远端链设置一次，与对端适配器一起设置；适配器 SHOULD 以 `remoteEndpoint(uint64 chainId) returns (address)`（`0xf2d88e04`）公开它（参考适配器即如此）。随后端点按其路由检查来源端点（§5.1），因此决定另一条链上哪个合约可以代表该集合发言的是路由表，而不仅仅是适配器的对端表。

#### 8.3 适配器封存

适配器 MUST 实现 `ITapBridgeAdapterSealed`（标识符 `0xceebf7ce`）：`adapterSealed() returns (bool)`（`0xceebf7ce`），以及事件 `AdapterSealed()`（`0x16ce24d3a7b82addfa23f273f6be525d4610ab33551f22d0ca872db8e9ffbe9e`）。只有当任何账户都无法再更改影响适配器如何认证传入消息、或它报告哪个端点为消息来源的任何东西时，它才返回 true：对端、远端端点、hub 配置中的远端容器，以及 LayerZero 的 EndpointV2 委托方（委托方选择消息库、DVN 和确认数）。一旦为 true 就不再变回 false。在参考适配器中，`seal()`（`0x3fb27b85`，仅所有者，不可逆）执行该配置的冻结、清除所有者并发出 `AdapterSealed`。适配器的所有者 MUST NOT 能够以封存以外的方式放弃所有权（`transferOwnership(address(0))` 以 `ZeroOwner()`（`0x9905827b`）revert），因此没有所有者的适配器总是报告已封存。只要任何已配置的远端 eid 仍跟随端点所有者的默认值，LayerZero 适配器就 MUST NOT 报告已封存（§9，“封存”）。

封存之后，不再有任何影响认证的配置可以更改。仍然可以做的事：任何人都可以调用 `quote`、通过端点 `resend`、重新执行已存储的 LayerZero 送达，以及转发带有有效签名的 hub 消息；消息层工作者收取的费用可能变化，因为那是由这些工作者设定的。

### 9. LayerZero V2 配置规范

`layerId` = `keccak256("TAP-NFT adapter LayerZeroV2 v1")` = `0x117f05b8b59be0e82e43c9302d01f46e149b6a74d295ff09c2df95de7ff7ff97`。

该适配器是一个直接对接 EndpointV2 的 OApp（三条链上均为 `0x1a44076050125825900e736c501f859c50fE728c`，见"部署"）：

| 项目 | 要求 |
|---|---|
| 端点 ID | BNB Smart Chain 56 ↔ eid **30102**；Base 8453 ↔ eid **30184**；X Layer 196 ↔ eid **30274** |
| 对端 | `setPeer(uint64 chainId, uint32 eid, bytes32 peer, address remoteEndpoint)`（`0x2e50800b`），仅所有者，每条链一次：若该链 ID、eid 或对端槽位已设置，MUST revert。`peer` 是远端适配器，左侧填充到 32 字节；`remoteEndpoint` 是它所服务的端点（§8.2） |
| 发送 | `EndpointV2.send(MessagingParams(dstEid, peer, payload, options, false), refundTo)`（`0x2637a450`），附上端点传入的价值；费用仅以原生代币支付。`quote` 调用 `EndpointV2.quote(params, adapter)`（`0xddc28c58`）并返回 `nativeFee` |
| 选项 | 调用者的 `options` 非空时用之；否则为 `0x0003 ‖ 0x01 ‖ uint16(17) ‖ 0x01 ‖ uint128(gas)`（type-3 选项、执行者 worker、`lzReceive` gas）。400,000 gas 时为 `0x00030100110100000000000000000000000000061a80`。默认 gas SHOULD 至少为 400,000（镜像合约上的首次到达约需 236,000，见"参考实现"） |
| 接收 | `lzReceive(Origin origin, bytes32 guid, bytes message, address executor, bytes extraData)`（`0x13137d65`）MUST revert，除非调用者是 EndpointV2、`msg.value` 为 0，且 `peers[origin.srcEid]` 非零并等于 `origin.sender`；然后按 §8.2 处理，`srcChainId` = 与 `origin.srcEid` 绑定的链；LayerZero 消息就是载荷本身 |
| 路径 | `allowInitializePath(Origin)`（`0xff7bd03d`）返回 `peers[srcEid] == sender`（发送方为零时返回 false）；`nextNonce(uint32, bytes32)`（`0x7d25a05e`）返回 0（无序送达） |
| 委托方 | 构造函数调用 `EndpointV2.setDelegate(delegate)`（`0xca5eb5e1`）；在适配器封存之前，所有者可以更改它。委托方在 EndpointV2 上为该适配器选择消息库、DVN 和确认数。封存（§8.3）MUST 把委托方设为零 |
| 封存 | `seal()` MUST revert（`NotPinned(uint32 eid)`，`0xd2f23d72`），除非至少配置了一个远端 eid，且对每个已配置的 eid：`EndpointV2.isDefaultSendLibrary(adapter, eid)`（`0xdc93c8a2`）为 false；`EndpointV2.getReceiveLibrary(adapter, eid)`（`0x402f8468`）返回非零的库且 `isDefault` 为 false；`EndpointV2.receiveLibraryTimeout(adapter, eid)`（`0xef667aa1`）没有高于当前区块的到期；该库的 `getAppUlnConfig(adapter, eid)`（`0x39e3f938`，适配器自己的 ReceiveUln302 配置，不与默认值合并）的 `confirmations` 既不为 0（默认值）也不为 `type(uint64).max`（ULN302 的 NIL 值，即零确认），`requiredDVNCount` 既不为 0（默认值）也不为 255（NIL，即没有必需 DVN），且等于 `requiredDVNs` 的长度。因此，已封存的适配器不再依赖端点所有者的默认库或默认接收配置 |

**DVN 配置。** 在适配器封存之前，委托方 MUST 固定发送和接收库以及接收配置（封存时会检查），SHOULD 要求至少两个由不同方运营的 DVN，并 SHOULD 把区块确认数至少设为：BNB Smart Chain 15，Base 64，X Layer 300。（2026-10-17 17:45 至 17:46 UTC 测得，每条链三个样本：BNB Smart Chain 的 `finalized` 标签落后最新区块 2 个区块；`safe` 标签在 Base 上落后 11 至 34 个区块，在 X Layer 上落后 39 至 245 个区块。上述数值加了余量，X Layer 的数值等于 TAP-10 的最大固定滞后。）封存会冻结这一配置，包括日后停止工作的 DVN。

**重试。** 在 `lzReceive` 中 revert 的送达仍由 EndpointV2 保存，待原因消除后任何人都可以再次执行。`ManifestConflict` 永远不会消除，因此这样的消息永久失败。诚实的端点之间不会出现 `AlreadyLive`（已执行 ID 的重复消息会以 `Replay` revert）；它意味着某个消息层为一个活跃代币送达了第二条不同的消息，是遭到攻破的迹象，而不是应当重试的情况。

### 10. TAP-10 hub 配置规范（参考性）[待定]

本节在本版本中为参考性内容。遵循本节的适配器，在 hub 消息的验证器得到规定之前，不是本 TAP 的合规适配器；收录本节是为了让 `ALL(LayerZero, hub)` 的实现在此期间对格式保持一致。

TAP-10 hub（`0xe61A9C7213a6Aa616C246a2B569e555B417b25ee`，每条链上地址相同，TAP-10 §13.2）只在发送链上记录消息。目标合约无法读取另一条链的 hub，因此本配置需要一个验证器。本节描述发送端和一种验证器：一个固定的见证人集合。

`layerId` = `keccak256("TAP-NFT adapter TAP-10 hub relay v1")` = `0x52d641b576bf4d57ffe8457eeb80d8684348265b309a824d5c2a72ad11584ce2`。

**发送端。**

- 适配器持有一个容器已开通的电路 NFT（TAP-10 §13.4），用 `setCircuit(address circuits, uint256 circuitId)`（`0x6672d2d3`）设置一次；除非 `ownerOf(circuitId)` 是该适配器，否则它 revert（`NotCircuitHolder()`，`0x094c282c`）。该容器是适配器所写每条消息的作者。适配器没有把该电路转走的函数。
- 每条远端链用 `setRemote(uint64 chainId, address adapter, address container, address remoteEndpoint)`（`0x66bc31da`）设置一次：远端适配器、在其链上为它写消息的容器，以及它所服务的端点（§8.2）。
- `msg.value` ≠ 0 时 `send` revert；它调用 `hub.send(circuits, circuitId, to, ref, payload)`（`0xa181b579`），其中 `to = uint32(0) ‖ uint64(dstChainId) ‖ remote container`，即远端适配器容器的 TAP-10 §12.1 端点 ID，`ref` = 消息 ID（§4.1）。它把该条目的 TAP-10 §17 消息 ID 作为 `transportId` 返回。`quote` 返回 0：hub 不收费，由转发者支付目标链 gas。

**见证人验证器。** 目标适配器部署时给定一个按地址严格升序排列的见证人列表和阈值 `K`（1 ≤ K ≤ N）；两者都不能更改。任何人都可以调用

```
deliver(uint64 srcChainId, uint256 outboxIndex, bytes32 ref, bytes payload, bytes signatures)    0x1645190f
```

它在以下条件不全满足时 revert：`remoteContainer[srcChainId]` 已设置；`(srcChainId, outboxIndex)` 此前未送达；`ref == keccak256(remoteEndpoint[srcChainId] ‖ payload)`；`signatures` 恰为 `K` 个拼接的 65 字节 `r ‖ s ‖ v` 签名，`v` ∈ {27, 28}，`s` ≤ secp256k1n/2，按严格升序恢复为所列见证人，签名对象为以下内容的 EIP-712 哈希：

```
EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
  name = "TAP-NFT Hub Relay", version = "1", chainId = destination chain, verifyingContract = destination adapter
HubMessage(uint64 srcChainId,address hub,address fromContainer,uint256 outboxIndex,bytes32 digest)
  hub = the hub address, fromContainer = remoteContainer[srcChainId],
  digest = keccak256(ref ‖ keccak256(payload))          (TAP-10 §13.6)
```

随后它把 `(srcChainId, outboxIndex)` 标为已送达，并按 §8.2 继续。`hubMessageHash(uint64, address, uint256, bytes32)`（`0xbd48a881`）返回待签名的哈希；若 `block.chainid` 改变，域分隔符会重新计算。

见证人只在以下检查之后签名：在 TAP-10 严格一致的条件下，于源链 hub 上、在不高于该链终局性标签确认高度的区块（TAP-10 §17）读取 `fromContainer` 的发件箱条目 `outboxIndex`，并检查该条目的 digest 等于 `digest`、条目的 `to` 等于目标适配器容器的端点 ID，且其 `Sent` 日志携带 `ref` 和 `payload`（TAP-10 §18.3）。见证人还检查源 hub 是被接受的、处理器实现未变（TAP-10 §13.8），以及写入该条目时电路由源适配器持有。

**链上验证器需要什么。** 目标链需要在不依赖可信方的情况下验证源 hub 的存储中有该发件箱条目：目标链上一个可信的源链区块哈希（源链的轻客户端或有效性证明；对 Base 和 X Layer 则为以太坊的，外加它们在 L1 上的结算），以及 hub 的 `deweb.hub.v1` 命名空间（TAP-10 §13.3）的存储证明（`eth_getProof`）。这样的验证器将取代 `deliver` 中的见证人检查，其余部分保持不变。

### 11. 角色与封存

| 合约 | 部署者 | 封存前的所有者 | 所有者权限 | 封存之后 |
|---|---|---|---|---|
| 网关合约、镜像合约 | 任何人；所有者是构造函数参数 | 部署时指定的账户 | `setRoute` | `sealRoutes()`（仅当所列每个适配器都已封存）设置 `routesSealed` 并清除所有者；不再保留任何权限 |
| LayerZero 适配器 | 任何人 | 部署时指定的账户 | 每条链一次 `setPeer`、`setDelegate`、`transferOwnership`、`seal` | `seal()`（仅当每个已配置 eid 的库和接收配置都已固定）把 EndpointV2 委托方设为零并清除所有者；不再保留任何权限 |
| Hub 转发适配器 | 任何人 | 部署时指定的账户 | 一次 `setCircuit`、每条链一次 `setRemote`、`transferOwnership`、`seal` | `seal()` 清除所有者；见证人集合自部署起即不可变 |

任何端点或适配器都不可升级，也都没有暂停、救援函数或移动已托管代币的途径。端点 SHOULD 在其路由配置并测试完成后封存。客户端 SHOULD 显示集合的端点是否已封存以及每条路由使用的策略。

### 12. 费用

`bridge` 和 `resend` 的调用者在一笔交易中支付每个适配器当时报价的原生代币费用；多余的价值退还给调用者，不足则整个调用 revert。LayerZero 把它自己的多余部分退还给 `refundTo`（即调用者）。端点自身不收取任何费用，交易之间也不持有余额。LayerZero 的目标链执行费用通过选项支付；hub 配置的目标链执行费用由调用 `deliver` 的人支付 **[待定]**。

## 设计理由

- **与 TAP-721 的关系。** 本 TAP 是单独的扩展，而不是 TAP-721 的一节，因为它的安全性依赖仍可升级的消息层：LayerZero V2 的端点配置、DVN 和执行器，以及跨链验证仍待定的 TAP-10 hub。依赖可升级合约的 TAP 在这些合约封存之前只能停留在 Candidate（TAP-01 §5.1）；若放在 TAP-721 之内，这一依赖会拖住整个标准，而 TAP-721 集合在原链上铸造、揭示和核验都不需要它。分开之后，TAP-721 可以独立推进，本 TAP 在路由和适配器封存后推进（§8.3、§11），而且桥从不改变原链上的 TAP-721 集合。
- **锁定-铸造，原件是唯一的事实来源。** 在原链上销毁需要集合配合，而 TapeCode-Test1 这样的既有集合做不到。托管适用于任何 ERC-721，原集合、其供应量及其交易市场都保持不变；回到原链的代币就是原件本身。
- **为什么不直接用 ONFT721，以及本草案保留的另一种方案。** LayerZero 的 ONFT721 是单一消息层的库模式，不是 ERC。它的适配器形式（`ONFT721Adapter`）与网关合约完全一样地托管一个未经修改的 ERC-721，镜像合约也可以是 `ONFT721` 的子类。对本草案的一份跨链审查建议任何部署都采用这种设计：在标准 ONFT 消息后附加三个哈希，原样保留 §5.3 的镜像配置规范和 `materialize`，以来自不同运营方的至少三个必需 DVN 代替 `ALL` 策略，并在原链适配器上采用星形路由和按路由记账。它的收益是：现成的 LayerZero 工具（连线和配置检查）、小得多的新增审计面（在已审计的库代码之上增加几百行，而不是自定义的端点和适配器），并且与 TapeOut 自己的生产桥（一个标准的 `OFTAdapter`）形态相同。它的损失是：没有独立于消息层的 `ALL` 策略，也没有适配器接口；它只支持 LayerZero，日后若要加入第二个独立的消息层，就需要一个新的标准。本草案规定自定义设计，使比较具体可见，并采纳了审查建议的星形路由和按路由记账，同时请 TAPs 讨论在两者之间作出选择。TapeCode-Test1 v1 没有部署计划。
- **为什么不用 ERC-7786。** ERC-7786 定义了一个通用的跨链消息网关接口。本 TAP 的 `ITapBridgeAdapter` 不采用它，因为 ERC-7786 仍是草案，而且它的属性模型既不固定载荷，也不固定多个适配器之间的策略，而这恰恰是本 TAP 必须确定的部分。
- **为什么载荷中要有哈希。** 这样镜像合约无需信任消息层之外的任何人，就能回答 `netlistHashOf` 并接受网表文件，各条链上的游戏读到的是同一个电路。图像和清单哈希只多两个字，却让镜像代币能像原件一样被展示和核验。
- **为什么消息 ID 包含来源端点。** 端点可以在封存前被替换，而替换后的端点从 nonce 0 开始。若不包含来源端点，它的最初几个载荷可能与其前任发出的消息逐字节相同，目标链会把它们当作重放拒绝，而此时代币已被托管或销毁。把经过认证的来源端点与载荷一起哈希，可以使载荷格式保持固定的 320 字节。
- **为什么没有 `ANY` 策略。** 若多个消息层中任意一个即可，攻击者只需攻破最弱的那个；`ANY` 严格地比在最好的消息层上使用 `ONE` 更不安全。`ALL` 迫使攻击者攻破每个消息层，代价是活性：一个停滞的消息层会让整条路由停滞。
- **为什么不从 `ALL` 自动退回。** 超时后触发的退回会让控制一个消息层、又能让另一个停滞的攻击者独自铸币。因此恢复是显式的（§7），封存之后只限于消息层自身提供的途径。
- **为什么两种消息层都支持。** LayerZero V2 如今已在 TapeOut 生产环境中使用（矿机桥），也是唯一无需新基础设施就能送达消息的消息层。TAP-10 hub 是 TapeOut 自己的消息层，其信任独立于 LayerZero，但它需要一个验证器，因此其配置规范目前为参考性。`ONE` 是默认值；`ALL` 用于不能信任单一消息层的路由。
- **为什么由端点检查来源端点。** 适配器认证远端适配器；`receivePayload` 还接收来源端点，因此端点的路由表（随路由一起封存）对哪个合约可以代表该集合发言拥有最终决定权，配置错误的适配器无法独自改变路由的指向。
- **为什么封存要涵盖适配器。** 能更改路由、对端或 LayerZero 委托方的所有者，可以让一条路由送达伪造的消息。因此 `sealRoutes()` 要求所列每个适配器先行封存，使一个链上标志即可告诉客户端：没有任何账户保有这样的权限。代价是封存之后适配器的故障无法由所有者修复。
- **为什么采用星形路由。** 若允许镜像之间直接转移，网关合约无法知道代币在哪里，于是攻破通往网关合约的最弱路由，就能释放所有托管代币。让每次转移都经过原链，镜像之间的转移要多一次转移（这对 NFT 来说很少见），却使网关合约只在代币被发往的那条路由上释放它。
- **为什么从原链元数据开始发现。** 网关合约的地址必须来自持有人已经信任的地方；原集合自己的元数据就是这个地方，而且这样任何集合都能使用本 TAP，无需修改本文。
- **为什么镜像合约在销毁后保留哈希。** 这让 `netlistOf` 和已存储的文件在历史查询中仍然有用，也让往返更便宜；`ownerOf` 已经能说明代币是否在场。

## 向后兼容

原集合不会被修改；从不跨链转移的持有人感受不到任何变化。TapeCode-Test1 和其它既有 ERC-721 集合可以原样使用网关合约；它们的数据源（如有）是伴生合约（TAP-721 §8.3）。本 TAP 不改变矿机桥，矿机桥也不遵循本 TAP：矿机不是 TAP-721 代币，矿机金库和凭证合约保留各自的接口。

索引原集合的索引器会看到已离开的代币由网关合约持有；它们可以通过网关合约的 `Departed` 事件和镜像合约的 `Arrived` 事件找到活跃代币。

本草案依赖 TAP-721（`TAP-draft-netlist-bound-nft`），并在其之后提交。TAP-721 是核心草案申请的编号；若编辑分配了其它编号，本草案即采用该编号：本文中对 `TAP-draft-netlist-bound-nft` 和"TAP-721"的所有引用（包括 `requires` 字段）都替换为该编号。

## 测试用例

`assets/tap-draft-netlist-nft-bridging/vectors.json`（格式 `tap-netlist-nft-bridging-vectors/2`）由同一目录下的 `make_vectors.py` 生成（无依赖的 Python，自带 Keccak-256），可逐字节复现：`python3 make_vectors.py --check`（SHA-256 `bcfd12c1a2f6d875ce602da32632c260afcd6c5b560a97297044f1f690224f51`）。它包含：

- **集合键**：X Layer 上的 TapeCode-Test1，以及一个 BNB Smart Chain 示例；
- **有效载荷**，每个都带有字段、载荷字节、`keccak256(payload)`、一个示例来源端点、消息 ID、hub `ref` 和 hub digest：`home-to-remote`（§4.3）、`remote-to-home`（BNB Smart Chain → X Layer，nonce 3）、`remote-to-home-unbound`（哈希为零）、`extremes`（最大的代币编号、链 ID 和 nonce）；
- **无效载荷**，每个端点都拒绝（§4.1）：长度 319 和 321、version 2、不规范的 version 字、为零的 `to`、`to` 字高位非零，以及每个 `uint64` 字溢出；
- **LayerZero**：eid、400,000 和 300,000 gas 的默认选项字节、layer id；
- **Hub 转发**：layer id、一个示例容器的 `to` 端点 ID、EIP-712 类型哈希、一个域分隔符、一个结构哈希，以及一条固定消息的待签名哈希；
- **接口**：本 TAP 列出的选择器、ERC-165 标识符、事件 topic 和错误选择器。

https://github.com/BruceLanLan/TAP-721 中的 Solidity 参考实现（见参考实现）复现每个向量（该仓库中的 `contracts/test/bridge/TapBridgeVectors.t.sol`）。

同一仓库中的行为测试（`contracts/test/bridge/TapBridge.t.sol`、`TapBridgeCompanion.t.sol`，通过切换 `block.chainid` 在一个 EVM 中模拟三条链）：往返 原链 → 远端 → 原链 以及 BNB Smart Chain → 原链 → Base → 原链，并拒绝镜像之间的路由；在模拟消息层、LayerZero（模拟 EndpointV2）和 hub（带持有人检查和见证人签名的模拟 hub）上的 `ONE`；`ALL(LayerZero, hub)`，其中任一消息层单独都不会铸币，第二次确认才铸币，两种顺序都测试，并测试返回原链；`ALL` 路由的两个适配器送达不一致的载荷时永不执行；同一适配器确认两次；执行后的重放，包括代币再次离开之后；错误的 LayerZero 对端、伪造的 origin、所列适配器给出不是路由对端的来源端点；未列在路由上的适配器；错误的来源、目标和集合；重复铸币、释放不在托管中的代币，以及按路由记账（位于 BNB Smart Chain 的代币不会被 Base 路由上的消息释放）；清单冲突和超出范围的编号；路由校验、适配器封存（包括只要任何 eid 仍跟随默认库、默认接收配置或处于接收库宽限期，LayerZero 适配器就不能封存，且拒绝 ULN302 的 NIL 值）和端点封存；通过替换和 `resend` 恢复卡住的 `ALL` 适配器；费用、退款和选项数量；未确认时拒绝合约接收方、确认后接受，以及把 EIP-7702 账户视为普通账户；揭示后先绑定的规则以及托管记录；网表物化、49,016 字节文件的分块存储以及镜像合约上的 `netlistOf`；镜像配置规范中空的揭示接口；一个形如 TapeCode-Test1 的既有集合（`setBaseURI`、`freezeBaseURI`、无 ERC-4906），以 TAP-721 核心实现的 `TapCompanion` 作为数据源，经过提交、揭示、绑定、跨链和物化。同在该仓库中的、来自安全审查的回归测试（`contracts/test/audit/AuditBridge.t.sol`，针对清单区间之外代币的 `AuditFixes.t.sol`（该代币以零哈希离开），以及针对代币集成员资格和 NIL ULN 值的 `AuditPass3.t.sol`）：端点作为接收方、被替换且 nonce 重新开始的网关合约（合法消息得以执行）、转移后仍保留授权的集合（已托管代币不会第二次离开），以及适配器封存（封存后委托方和对端都不能更改）。

模拟 EndpointV2 不运行 DVN 验证，也不做 EndpointV2 自身的 nonce 与载荷哈希记账，因此重放测试检验的是端点合约的防护，而真实的 EndpointV2 通常会更早拦截。模拟 hub 不检查容器是否已开通。

## 参考实现

Solidity：https://github.com/BruceLanLan/TAP-721（Foundry 项目 `contracts/`，solc 0.8.28，优化器 10,000 runs，EVM `shanghai`），将在进入 Review 之前以一个固定提交链接（TAP-01 §7.2 第 8 条）。下表路径均相对于该仓库中的 `contracts/`。

| 路径 | 内容 |
|---|---|
| `src/interfaces/ITapBridge.sol` | `ITapBridgeAdapter`、`ITapBridgeEndpoint` |
| `src/interfaces/ITapBridgeTransfer.sol`、`ITapBridgeMirror.sol`、`ITapBridgeAdapterSealed.sol` | §5.1、§5.3 和 §8.3 的接口 |
| `src/bridge/TapBridgePayload.sol` | 集合键、载荷编码、严格解码、消息 ID |
| `src/bridge/TapBridgeEndpoint.sol` | 路由、策略、封存、重放防护、分发、重发 |
| `src/bridge/TapGateway.sol` | 原链端点（托管） |
| `src/bridge/TapMirror.sol` | 远端端点；使用 TAP-721 的 `src/vendor/ERC721Min.sol`、`src/core/TapNetlistStore.sol` 和 `src/core/TapNetlistCheck.sol` |
| `src/bridge/TapAdapterBase.sol`、`LayerZeroV2Adapter.sol`、`ILayerZeroEndpointV2Min.sol` | 适配器基类（含封存）和 LayerZero V2 配置规范，不依赖 LayerZero 库 |
| `src/bridge/HubRelayAdapter.sol` | 参考性的 hub 配置规范及见证人验证器 |
| `test/bridge/`、`test/audit/AuditBridge.t.sol` | 测试和模拟合约（EndpointV2、hub、模拟消息层、既有集合、数据源） |

运行时大小：网关合约 16,114 字节，镜像合约 21,345，LayerZero 适配器 8,676，hub 转发适配器 8,259。

实测执行 gas（Foundry，在调用前后取 `gasleft()`；*模拟传输不存储任何东西*，因此消息层自身的成本需另行加上）：

| 操作 | Gas |
|---|---|
| 网关合约 `bridge`（托管及位置记录、三次数据源读取、载荷、一次适配器调用） | 206,066 |
| `ONE` 路由上镜像合约的到达（铸币、两个哈希、已知网表、首次到达时的清单） | 236,441 |
| 镜像合约 `bridge`（销毁、载荷） | 152,696 |
| `ONE` 路由上网关合约的到达（位置检查、释放） | 127,818 |
| Hub 转发 `deliver`，2-of-3 签名，补全 `ALL` 路由并铸币 | 348,317 |
| `materialize`，23 字节文件 / 49,016 字节文件 | 89,479 / 12,355,979（约每字节 252 gas） |

## 部署

本 TAP 的合约均未部署，TapeCode-Test1 v1 也没有部署计划。每个端点和适配器的所有者都是构造函数参数；在某个拉取请求把地址加入此处之前，客户端不接受任何部署作为 TapeCode-Test1 的正式端点。本 TAP 记录部署，但不能下令部署。

本 TAP 依赖以下已部署的合约。

**LayerZero V2 EndpointV2。** 于 2026-10-17 16:19 至 16:43 UTC 只读**实测**（`eth_call` 和 `eth_getStorageAt`，每条链一个节点，非严格一致）：X Layer 区块 73,484,955–73,486,332，经 `rpc.xlayer.tech`；BNB Smart Chain 区块 128,201,222–128,204,265，经 `tapeout.net/rpc`；Base 区块 52,732,329–52,733,011，经 `mainnet.base.org`（每个值读取一次，取读取时的最新区块）。端点地址、eid 和默认库与 LayerZero 的部署元数据一致（`https://metadata.layerzero-api.com/v1/metadata/deployments`，于 2026-10-17 约 16:19 UTC 获取，SHA-256 `d1898aa5ec6f6fc0af3d31b1cafd50f636b68ca9e0521e1c21f1e0fd164a18f9`），该数据即 LayerZero"Deployed Contracts"文档页面背后的数据。

| 链（chainId） | EndpointV2 | `eid()` | `owner()` | 代码哈希 | ERC-1967 槽 | 默认发送 / 接收库（通往其它链的路径） | 已封存？ |
|---|---|---|---|---|---|---|---|
| BNB Smart Chain (56) | `0x1a44076050125825900e736c501f859c50fE728c` | 30102 | `0xEFACCEc3B9661b5ff62418243c013f2F58Ce1350` | `0x5ed1f4ec5f4d6bd5eac1fa92e0fb7474be2607dfc5f3eb82ced1c183b64fbeb9` | 0（不是代理） | `0x9F8C645f2D0b2159767Bd6E0839DE4BE49e823DE` / `0xB217266c3A98C8B2709Ee26836C98cf12f6cCEC1` | 不可升级；所有者设定默认库 |
| Base (8453) | 同上 | 30184 | `0xa0392d116D71ED3b75086194aBa6De3CD1e39B7E` | `0x086c2e9e37f5bdaf45013882cf40f7a43b35c879302ff1ad4a4010d09b4d7237` | 0 | `0xB5320B0B3a13cC860893E2Bd79FCd7e13484Dda2` / `0xc70AB6f32772f59fBfc23889Caf4Ba3376C84bAf` | 同上 |
| X Layer (196) | 同上 | 30274 | `0xE590a6730D7a8790E99ce3db11466Acb644c3942` | `0x21c2d567afee99c79aa52beca53380975509c8d5bedd5ff55ff6c5451dec378f` | 0 | `0xe1844c5D63a9543023008D332Bd3d2e6f1FE1043` / `0x2367325334447C5E1E0f1b3a6fB947b262F58312` | 同上 |

各链代码哈希不同，是因为端点的 eid 是不可变量。三条链上 `nativeToken()` 均为零（以 BNB、ETH 或 OKB 支付费用）。LayerZero eid 30155 是 OKXChain（66），一条已弃用的链，不是 X Layer。默认库是读取时端点所有者的选择，可能改变；建议适配器固定自己的库（§9）。

**TAP-10 DeWEB hub。** 每条链上均为 `0xe61A9C7213a6Aa616C246a2B569e555B417b25ee`；实现、所有者和封存状态见 TAP-10 的"部署"一节（截至 TAP-10 最近一次读取均未封存）。参考性的 hub 配置规范还依赖各链的处理器工厂和电路 beacon（TAP-10 §13.4、§13.8），它们均未封存。

**现有矿机桥（先例，不是依赖）。** BNB Smart Chain 金库 `0x48D43345656f0f9510dC3c06CBa99dFf597617C2` 和 X Layer 凭证合约 `0x9cfc959cd42B2e1d39a0d850c528210E818AE520`，两者都是由 `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138` 管理的可升级代理，eid 为 30102 和 30274。它们的 `endpoint()` 返回 `0x1a44076050125825900e736c501f859c50fE728c`（2026-10-17 读取，UTC）；它们的对端配置未读取（两者的 `peers(uint32)` 都 revert），且矿机桥不包括 Base。

## 安全考虑

- **`ONE` 下的适配器被攻破。** 能让路由唯一的适配器送达任意载荷的人，可以把原链上所有托管代币释放给自己，并铸造任何不在镜像合约上活跃的代币。对 LayerZero 而言，这意味着所配置的 DVN（以及在适配器封存之前，它的所有者和委托方）；对 hub 配置而言，意味着 `K` 个见证人。一条路由的安全性恰好等于它唯一那个消息层的安全性。
- **网关合约按路由记账。** 网关合约记录每个托管代币离开时前往的链，只在来自该链的消息到达时才释放它（§5.2）。因此，被攻破的路由只能释放位于其链上的代币，并只能在它自己的镜像合约上铸造在那里不活跃的代币。不能依赖单一消息层的集合仍在每条路由上使用 `ALL`（或多个必需 DVN）。
- **`ALL` 下的适配器被攻破。** 攻击者必须对同一载荷控制每个所列消息层。单独一个被攻破的消息层只能确认其它消息层从不送达的载荷；它也可以拒绝送达，从而使路由停滞（§7）。
- **封存后仍保留的配置。** 只有当所列每个适配器都已封存（§8.3）时 `sealRoutes()` 才会成功，而已封存的 LayerZero 适配器没有委托方，也没有跟随默认库或默认接收配置的远端 eid。端点自身的适配器检查信任每个适配器的报告，因此客户端只认可其代码已知的适配器（参考适配器或经审计的等价实现）。在此之前，适配器所有者可以更改委托方、设置缺失的对端，从而让一条路由送达伪造的消息；只有当 `routesSealed()` 为 true 时，客户端才把集合视为已封存。
- **DVN 配置。** 跟随端点所有者默认值的 LayerZero 适配器，会继承所有者日后设置的一切，包括 DVN 集合。在封存前固定库并要求至少两个独立 DVN，会把这一信任转移到封存时选定的配置上，包括日后失效的 DVN。
- **卡住的消息。** 在途代币在其消息执行之前一直退出流通。因永久性原因在目标链 revert 的消息（`ManifestConflict`）永远不会执行；`AlreadyLive` revert 表明某个消息层被攻破或出错（§9）。封存之后，没有所有者能修复路由（§7，途径 3）。
- **重组与终局性。** 若源链在目标链执行载荷之后发生重组，代币可能同时存在两份：源链上的离开被撤销，而目标链上的到达依然有效。因此 LayerZero 确认数（§9）和见证人签名要等待 TAP-10 §2.1 的终局性标签（BNB Smart Chain 为 `finalized`；Base 和 X Layer 为 `safe`，它们的单一排序器可以改写未确认的区块）。作为对现行做法的观察而非要求：TapeOut 的生产 BEM 桥（矿机也经由它传送）在两个方向上都使用 20 个区块确认。于 2026-10-17 约 18:32 UTC 用 `EndpointV2.getConfig(oapp, receiveLibrary, eid, 2)`（以及接收库上的 `getAppUlnConfig`）读取：X Layer 上的 BEM OFT `0x60e62Efa9405d6873C5deaBD4E6CC91c25363952` 从 BNB Smart Chain 接收（eid 30102，库 `0x2367325334447C5E1E0f1b3a6fB947b262F58312`）时返回 20 个确认、1 个必需 DVN 和 3 选 2 的可选 DVN；BNB Smart Chain 上的 `OFTAdapter` `0xa84B8D3893De6e9922f2B29bE1e1b115845F5E72` 从 X Layer 接收（eid 30274，库 `0xB217266c3A98C8B2709Ee26836C98cf12f6cCEC1`）时返回 20 个确认、2 个必需 DVN 和 2 选 1 的可选 DVN。20 个 X Layer 区块远不及 X Layer 的 `safe` 区块头（测量时落后最新区块 39 至 245 个区块，§9），因此在 X Layer → BNB Smart Chain 路径上，这些送达依赖 X Layer 排序器不发生重组。
- **端点所有者。** EndpointV2 不是代理，但每条链的端点都有一个所有者（见"部署"），负责注册消息库和设置默认值。对固定了自己库的适配器，它的权力限于这些库所允许的范围；对没有固定的适配器，它的权力是完全的。
- **未封存的 TapeOut 合约（hub 配置）。** 在处理器工厂封存之前，控制它的人可以替换处理器实现，并以任何容器的身份写入 hub（TAP-10 安全考虑），包括适配器的容器；在 hub 封存之前，其所有者可以改写发件箱条目。遵循 TAP-10 §13.8 的见证人能发现持久的更改，但不一定能发现临时的更改。
- **伪造的镜像合约和元数据。** 任何人都可以部署一个带有该集合名称、符号、集合键和哈希的合约。只有能从网关合约路由到达的镜像合约（§5.2）才是真的，而镜像合约上的哈希只和路由策略一样可信。镜像合约的元数据就是原链文档，由链下提供；工具按哈希核对图像和网表（TAP-721 §4.2）。
- **重复铸币。** `AlreadyLive`、`NotEscrowed` 和 `AlreadyEscrowed` 检查能阻止同一条链上活跃代币的第二次到达以及已托管代币的第二次离开，但看不到其它链。在代币不活跃的链上伪造一次到达，就会铸出第二个活跃代币；防止这一点是策略和消息层的职责。
- **接收方。** 一条链上地址 `X` 处的智能合约钱包，在另一条链上的 `X` 处通常并未部署，或由别人部署；发给它的代币可能无法找回，或落入陌生人之手。这就是为什么 `bridge` 拒绝在源链上有代码的接收方，除非调用者设置 `contractRecipientOk`（§5.1），TapeOut 的矿机桥也是这样做的。该检查只在源链上进行：目标链无法判断 `to` 在那里是否由发送者控制，而一个在源链上没有代码的地址，在目标链上仍可能是合约或尚未部署的反事实钱包。设置该标志的调用者，以及提供该选项的界面，都明确承担这一风险。端点作为接收方会永久持有代币，因此离开时拒绝路由的对端和发送端点，到达时拒绝接收端点。
- **授权。** 离开要求调用者是持有人或获得该代币的授权，此外还需网关合约在原集合上的授权，因此为网关合约授权了全部代币的持有人，不会被陌生人把代币转走。持有操作者授权的交易市场可以跨链转移持有人的代币，正如它可以转移代币一样。托管记录使不变式不依赖于转移后仍保留单个代币授权的集合。
- **原集合的权限。** 网关合约的托管只和原集合一样安全。所有者能移动或销毁代币、或可升级的集合，可以从原链一侧破坏不变式；建议客户端显示这一点。TapeCode-Test1 的所有者只能更改并冻结其 base URI。
- **Hub 转发的特点。** 见证人是固定的 `K`-of-`N` 集合，不能轮换；丢失超过 `N − K` 个密钥会使路由停止，`K` 个串通的密钥可以攻破它。转发没有报酬，因此送达依赖于愿意支付目标链 gas 的人。签名消息中的 `hub` 字段是目标链的 hub 地址，它之所以等于源链的地址，只是因为 hub 在每条链上地址相同（TAP-10 §13.2）。
- **链接库。** 若原集合或数据源通过 DELEGATECALL 调用链接库（例如 TAP-721 的求值库），该库对其存储（包括网关合约读取的数据）拥有完全写权限。在信任网关合约携带的哈希之前，客户端按公布的库地址和代码哈希核对已部署字节码中的链接地址。
- **大型网表。** 存储网表约需每字节 252 gas，且镜像合约只接受不超过 49,152 字节的文件（§5.3）；更大的文件无法在镜像合约上物化，但其哈希仍可随代币转移。

### 待定问题

1. **Hub 验证器。** 目前还没有在另一条链上验证 TAP-10 hub 消息的链上方法。谁来运行见证人、需要多少个、如何更换（只能通过部署新适配器并在封存前更改路由）？BNB Smart Chain、Base 和 X Layer 的轻客户端或有效性证明验证器是否可行？在此问题解决之前，§10 保持参考性。
2. hub 配置的**转发者激励**：无报酬、由发送者通过适配器支付，还是由见证人支付。

## 版权

依据 [CC0](../LICENSE) 放弃版权及相关权利。
