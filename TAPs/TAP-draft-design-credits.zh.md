---
tap: TBD
title: Design Credits and Lineage for TapeOut Netlists
description: How tools show what the chain records about the first publication of a TapeOut circuit as checked facts, and how designers sign credit, lineage and revocation statements about netlists as claims, without mixing the two.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/72
status: Draft
type: Application
created: 2026-10-19
requires: TAP-02, TAP-10, TAP-draft-netlist-bound-nft, TAP-draft-netlist-structural-hash, EIP-712, ERC-721, ERC-1271
license: CC0-1.0
---

本文是 `TAP-draft-design-credits.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。

# TAP-TBD：TapeOut 网表的设计署名与谱系

## 概要

本 TAP 让钱包、浏览器和电路工具把"谁第一个把电路放上链"作为核验过的事实展示，把"谁说自己设计了它"作为签名声明展示，并且绝不把后者当作前者展示。

## 摘要

网表的作者身份无法在链上证明：网表是公开的，任何人都可以流片一份不是自己设计的网表，两位设计者也可能各自独立得到同一份网表，而流片电路的账户可能是中继者、钱包合约，或并未设计它的矿工。本 TAP 把信息分成两层。**事实层**存放任何人都能对照链上核查的内容：电路的*发布事实*（电路代币铸给的账户、链、处理器、电路编号、区块、交易和日志），附确切的核验流程；以及设计的*已知最早出现*，即索引者在声明的范围内作出的陈述，任何人只要出示一个更早的、已核验的、网表哈希或结构哈希相同的出现，就能驳倒它。**声明层**存放由外部账户或 ERC-1271 合约账户签名、使用与链无关的域的 EIP-712 陈述：*Credit*（对某设计的角色，如设计者或优化者，可附自报的显示名、以 SHA-256 固定的设计说明和许可）、*Lineage*（设计之间的 derivedFrom、supersedes、optimizes 边）和 *Revocation*（撤回）。事实和陈述装在*署名包*里传递：可以是独立的 JSON 文件，也可以是 TAP-721 代币元数据的 `tap.credits` 成员；还可以通过一种仅供参考的、只发事件的合约模式所产生的日志在时间上锚定。展示规则要求工具：只在核验后才把事实显示为已核验；把每条声明连同签名者作为声明显示；不让声明进入事实层；把相互冲突的声明并列显示。本 TAP 不授予版税、收益、排他权，也不做身份核验。

## 动机

TapeOut 电路是 ERC-721 代币，TAP-721 又把收藏类代币绑定到其网表。钱包、浏览器、集合页面和电路编辑器越来越多地在电路旁显示"设计者：……"这样一行。如今这一行用手边能拿到的任意地址填写：电路代币的当前持有人、发送流片交易的账户，或设计证明矿机记录里的 `registrant`。它们都不说明谁设计了网表；PoD 属性草案同样把注册者排除在其属性之外（`TAP-draft-pod-attributes` §3.5，参考性）。

这个缺口在主网上真实存在。BNB Smart Chain 电路 `17851.30.tape` 是一台设计证明矿机，也是 TAP-721 各草案的示例；它与电路 `3.635.tape` 的网表哈希相同，后者是处理器 "RefBench" 中 XOR 题目的参考电路，由另一个账户早 57 天流片（见测试用例）。扫描两个处理器还能找到另外 130 个具有该网表哈希的电路；其中最早的 `906.30.tape` 由第三个账户流片，比参考电路还早约 20 小时。这些电路都是正当的。这份网表是教科书式的四 NAND 异或，很多人会各自推导出来；相同的网表既可能是复制，也可能是独立推导。链无法区分这两者：它记录的是谁在何时流片了哪份网表，而不是谁设计了它、它从何而来。这正是本 TAP 存在的原因。把其中任何一个账户（包括最早的那个）标成设计者的工具，都只是在猜。

设计者仍然想要署名，收藏者和玩家也想知道一个设计的历史：某个优化改进了哪个设计，哪个版本取代了哪个，谁审阅过它。这些信息只能以声明的形式存在。声明要有用，就得有签名、能在工具和链之间携带、能被签名者撤回，并且显示方式让人不会把它误当成事实。没有任何 TapeOut 标准定义这样的陈述；通用的证明（attestation）方案也没有说明哪些 TapeOut 事实可以核查、如何核查、工具能从中得出什么。

因此本 TAP 定义一小组带确切流程的可核查事实、一小组带确切编码的签名声明，以及把两者分开的展示规则。

ERC-5375 让 NFT 的作者以 EIP-712 签名表示同意被列为作者，并说明这种同意不是作者身份的证明。本 TAP 把同样的思路用于 TapeOut 网表，并把签名声明与链上记录的事实分开。因此，作者申请编号 5375（提案名称 TAP-5375，与 ERC-5375 相呼应）；由于 TAP-01 §6.1 原本分配 10 以上最小的空闲编号，这需要编辑同意。在分配编号之前，本草案保留文件名 `TAP-draft-design-credits.md` 和 `tap: TBD`；最终编号由编辑分配，若与所申请的不同，本草案改用该编号。

## 规范

本文中的关键词 "MUST"、"MUST NOT"、"REQUIRED"、"SHALL"、"SHALL NOT"、"SHOULD"、"SHOULD NOT"、"RECOMMENDED"、"NOT RECOMMENDED"、"MAY" 与 "OPTIONAL"，当且仅当以全大写出现时，按 RFC 2119 与 RFC 8174 的描述解释。

### 1. 术语与记号

| 术语 | 含义 |
|---|---|
| 电路 | 由处理器合约（TAP-02）存储的电路，以（链 ID、处理器合约、电路编号）标识 |
| 网表文件、网表哈希 | 同 `TAP-draft-netlist-bound-nft` §2 对 `tapnet/1` 的定义：`tapnet/1` 文件及其 SHA-256（§2.3）。按其 §2.5 定义的其它网表格式不在本 TAP 范围内 |
| 结构哈希 | 同 `TAP-draft-netlist-structural-hash` §7 |
| 设计 | 一个网表哈希、一个结构哈希，或两者。只给结构哈希的设计引用，指所有具有该结构哈希的网表文件 |
| 电路的设计 | 由该电路构建的文件的网表哈希与结构哈希（§3.3） |
| 适用 | 设计引用中每个非零哈希都等于电路的相应哈希时，该引用适用于该电路（§3.3） |
| 发布事实 | 电路首次铸造的记录（§3.1） |
| 首个发布者 | 电路代币首次铸给的账户（§3.1） |
| 最终性标签区块 | TAP-10 §2.1 中该链的最终性标签所指的区块：BNB Smart Chain 为 `finalized`，Base 和 X Layer 为 `safe` |
| 最早出现陈述 | 索引者关于"某发布事实是某设计在某范围内最早出现"的陈述（§3.4） |
| 陈述 | 一条签名的 Credit、Lineage 或 Revocation 消息（§4） |
| 声明 | Credit 或 Lineage 陈述 |
| 签名账户 | 陈述的（`signer`, `signerChainId`）二元组（§4.4） |
| 核验区块 | 核验合约签名者陈述时所用的区块（§4.6 第 4 项） |
| 署名包 | 承载事实和陈述的 §5.1 JSON 对象 |
| 生成方 | 编写署名包的任何人 |
| 工具 | 按本 TAP 展示事实或声明的软件 |

JSON 中的字节串写作 `0x` 加小写十六进制数字：32 字节值为 64 位，地址为 40 位。`‖` 表示拼接。`keccak256` 是 EIP-712 所用的哈希函数；SHA-256 是 FIPS 180-4 定义的哈希函数。链上读取遵循 TAP-10 §5：下文"两个节点"指属于不同运营方（TAP-10 §5.1）的两个节点，各节点的答复按 TAP-10 §5.2 规范化后比较。

本 TAP 下的信息分为三类：**已核验事实**（核验后的 §3.1–§3.3）、**最早出现陈述**（§3.4：出现本身可核查，"最早"只能被驳倒）和**声明**（§4）。§6 规定每类如何展示。

### 2. 范围与不主张事项

本 TAP 定义事实、陈述和展示规则。本 TAP 下的事实、最早出现陈述或陈述，不授予以下任何东西，生成方和工具也 MUST NOT 把它展示为授予：版税、收益分成或任何付款；收益、挖矿所得或任何设计证明奖励；排他权，或阻止他人流片、复制或使用网表的任何权利；许可的强制执行；电路代币、容器或 TAP-721 代币的所有权；或对任何人身份的核验。

### 3. 事实

#### 3.1 发布事实

处理器合约流片一个电路时，会以从零地址发出的 ERC-721 `Transfer(address indexed from, address indexed to, uint256 indexed tokenId)` 铸造电路代币（TAP-02 §6）。该电路的**发布事实**是如下 JSON 对象：

| 成员 | 必需 | 类型 | 内容 |
|---|---|---|---|
| `chainId` | 是 | number | 链 ID（TAP-10 §2.1） |
| `processor` | 是 | string | 处理器合约地址 |
| `circuitId` | 是 | string | 电路编号，十进制 |
| `publisher` | 是 | string | 铸造日志的 `to` 地址：首个发布者 |
| `block` | 是 | number | 含铸造日志的区块号 |
| `blockHash` | 是 | string | 该区块的哈希 |
| `txHash` | 是 | string | 含铸造日志的交易哈希 |
| `logIndex` | 是 | number | `eth_getTransactionReceipt` 返回的铸造日志 `logIndex` |
| `timestamp` | 否 | number | 区块时间戳；在最早出现陈述（§3.4）内为必需 |
| `name` | 否 | string | 电路的链上名称（TAP-10 §3.1） |
| `txFrom` | 否 | string | 交易的发送者（仅供参考，§3.5） |

数值为 0 到 2^53 − 1 之间的 JSON 整数。含其他成员的发布事实格式错误。

#### 3.2 核验发布事实

工具在把发布事实视为已核验之前，MUST 按以下步骤核验。`chainId` MUST 是 TAP-10 §2.1 中的链。第 1–4 步和第 6 步的每次读取 MUST 在至少两个节点上进行，比较的每个值在规范化后 MUST 在所有节点上完全相同；回执按 `status`、`blockNumber`、`blockHash`、`transactionHash`、`from` 以及每条日志的 `address`、`topics`、`data`、`logIndex` 比较，区块头按 `number`、`hash`、`timestamp` 比较。第 1、4、6 步在 `block` 当时或之后的同一个区块读取合约状态，即**状态区块**，工具要记录它；工具 SHOULD 使用第 7 步的最终性标签区块（处理器编号只追加、永不复用，见 TAP-10 §1 和 §4.3，电路也不会被删除，因此任何这样的区块给出的答案都相同）。

1. 确认 `processor` 已在该链的处理器工厂注册（`isCPU(address)`，选择器 `0x5f5a364f`），只使用 TAP-10 在部署一节列出的工厂地址。
2. 读取 `txHash` 的回执（`eth_getTransactionReceipt`）。其 `status` MUST 为 1，`blockNumber` 等于 `block`，`blockHash` 等于 `blockHash`。读取区块 `block` 的区块头（`eth_getBlockByNumber`）；其哈希 MUST 等于 `blockHash`。
3. 回执 MUST 恰好包含一条这样的日志：由 `processor` 发出，有四个 topic，`topics[0]` = `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`（`Transfer`），`topics[1]` = 零，`topics[3]` = 以 32 字节大端整数表示的 `circuitId`。其 `logIndex` MUST 等于 `logIndex`，其 `topics[2]` MUST 等于左补零到 32 字节的 `publisher`。
4. `circuitInfo(circuitId)`（TAP-02 §6）在状态区块读取时 MUST NOT 回滚。
5. 若有 `timestamp`，它 MUST 等于第 2 步所读区块头的时间戳。若有 `txFrom`，它 MUST 等于回执的 `from`。
6. 若有 `name`，它 MUST 等于按 TAP-10 §3.1 由 `circuitId`、该链的区号和满足 `cpuAt(k)` 返回 `processor` 的处理器编号 `k` 计算出的链上名称。
7. `block` MUST NOT 高于所用任一节点报告的最终性标签区块（TAP-10 §2.1）。通过第 1–6 步但未通过第 7 步的事实为**未最终确定**；工具 MUST NOT 把它显示为已核验。

通过全部步骤的事实为**已核验**。工具记录核验时间、状态区块和所用节点。若工具知道同一处理器、同一电路编号存在不止一条铸造日志（例如来自日志索引），它 MUST 把该电路的所有发布事实视为失败，并 SHOULD 报告该冲突。

工具 MAY 另外检查回执中是否有一条由 `processor` 发出、`topics[0]` = `0xc11215e417669c143c8a07aeb778034c0a0a85ebdf305d64a629b19a7a9ce031`（已部署的 `TapedOut(uint256,address,uint32,uint32)` 事件）、`topics[1]` = `circuitId`、`topics[2]` = `publisher` 的日志。这条日志只作佐证；本 TAP 不解释它的数据字，它的缺失也不会让事实失败。

找到交易不属于核验。生成方可以在电路创建所在的区块范围内，对处理器用 `eth_getLogs` 查询 `topics[3]` = `circuitId` 的 `Transfer`，或 `topics[1]` = `circuitId` 的 `TapedOut` 事件来定位它。

#### 3.3 电路的设计

电路的设计这样计算：完全按照 `TAP-draft-netlist-bound-nft` §3.2 第 2–3 步，由 `circuitInfo(circuitId)` 和 `netlist(circuitId)` 构建 `tapnet/1` 文件，然后：

- `netlistHash` = 该文件的 SHA-256，前提是文件有效（`TAP-draft-netlist-bound-nft` §2.2）；
- `structuralHash` = 该文件的结构哈希（`TAP-draft-netlist-structural-hash` §7）。

网表含 REF 记录的电路在本版本下没有设计。设计引用 D（一个网表哈希与一个结构哈希组成的二元组，零表示"未给出"）**适用于**电路 C，当且仅当 C 有设计，且 D 中每个非零哈希都等于 C 的设计的相应哈希。陈述的 `subject` 适用于 C 时，该陈述适用于 C。当 D 适用于某个已核验发布事实的电路时，该事实是**设计 D 的**发布事实。

#### 3.4 最早出现陈述

**最早出现陈述**是一个 JSON 对象：

| 成员 | 必需 | 类型 | 内容 |
|---|---|---|---|
| `tapEarliest` | 是 | number | `1` |
| `key` | 是 | object | `kind`：`"netlist"` 或 `"structural"`；`hash`：网表哈希或结构哈希 |
| `occurrence` | 是 | object | 包含 `timestamp` 的发布事实（§3.1） |
| `scope` | 是 | array | 一个或多个对象，含 `chainId`（number）、`processors`（`"all"` 或由互不相同的处理器编号组成的非空数组，TAP-10 §1）和 `toBlock`（number） |
| `indexer` | 否 | string | 陈述者：自由文本或 URI，至多 256 字节可打印 ASCII；未经核验 |
| `asOf` | 否 | string | 扫描的 ISO 8601 日期时间 |

发布事实的**处理器编号**是满足 `cpuAt(k)` 返回其 `processor` 的 `k`（TAP-10 §4.3 第 3 步）。当 `scope` 中某一项的 `chainId` 与某发布事实相同、`processors` 为 `"all"` 或包含其处理器编号、且 `toBlock` 不低于其 `block` 时，该发布事实**落在范围内**。出现 MUST 落在范围内。

生成方 MUST 只在 `scope` 中列出它完整扫描过的处理器：所列每个处理器在 `toBlock` 时从 1 到最新编号的每个电路，或对 `"all"` 而言，`toBlock` 时工厂中的每个处理器。这条规则约束生成方。工具无法核查它，判定时也不使用它；不完整的扫描只有在有人发布更早的出现时才会暴露。

**顺序。** 对两个发布事实 `a` 和 `b`：若在同一条链上，当 `(a.block, a.logIndex)` 按字典序小于 `(b.block, b.logIndex)` 时 `a` 先于 `b`；若在不同链上，当 `a` 所在区块的时间戳小于 `b` 所在区块的时间戳时 `a` 先于 `b`（使用 §3.2 第 2 步读到的区块头时间戳，无论事实是否带 `timestamp`），不同链上时间戳相等的两个事实为**并列**。工具没有其区块头时间戳的事实，无法与其他链上的事实排序；工具在这些比较中略去它，并 SHOULD 说明这一点。

**判定。** 工具这样判定最早出现陈述 S：

1. 除非 S 符合上述格式，且其 `occurrence` 是一个已核验的发布事实（§3.2），其设计（§3.3）以 `key.hash` 为网表哈希（`kind` 为 `"netlist"`）或结构哈希（`kind` 为 `"structural"`），并且落在范围内，否则 S **无效**。不知道该出现的处理器编号的工具，只能通过 `processors` 为 `"all"` 的范围项认定它落在范围内。
2. 考虑工具所知的、设计具有同类相同哈希且先于 S 的出现的每个已核验发布事实 O′。若其中有落在范围内的，S 被其中最早者**驳倒**；否则若存在这样的 O′，S 被其中最早者**取代**。工具不知道其处理器编号的 O′ 视为落在范围外。
3. 否则 S **成立**。其**成立集合**是它的出现，加上所有已知的、与该出现并列、且没有任何已知的该设计已核验事实先于它的该设计已核验事实。

知道驳倒或取代者的工具 MUST NOT 把 S 的出现显示为已知最早出现，MUST 改为显示它所知道的最早出现。任何人只要发布一个更早出现的发布事实，就能驳倒或取代一条陈述，无需其他证据。跨链并列很常见：BNB Smart Chain 大约每 0.45 秒出一个块，而区块头时间戳以整秒计，所以它的多个区块共用同一个时间戳。

#### 3.5 事实不能证明什么

- 首个发布者是调用流片函数的账户。它可能是外部账户、钱包合约、中继者、通过 ERC-6551 `execute` 行事的 TapeOut 容器，或从别人那里拿到网表、或独立推导出网表的账户。工具 MUST NOT 把首个发布者描述为网表的设计者、作者或创作者。
- `txFrom` 是签署外层交易的账户。它与 `publisher` 不同时，说明流片是通过合约进行的。它 MUST NOT 在本 TAP 的任何规则中取代 `publisher`。
- 代用户流片的中继者或合约之后可能把电路代币转给该用户，这会产生一条较晚的 `Transfer` 日志。工具 MAY 显示这次转移，作为其所在区块的一次转移；它不改变发布事实或首个发布者。
- 电路代币的当前持有人（`ownerOf`）和设计证明矿机记录的 `registrant`（设计证明挖矿合约 `getMiner(bytes32)` 返回元组中从 0 起数的第 10 位）不是本 TAP 下的事实：二者都不是发布事实，也都不是设计者。工具 MUST NOT 把任一者展示为首个发布者或设计者。（参考性：`TAP-draft-pod-attributes` §3.4 列出该元组，其 §3.5 把 `registrant` 排除在属性之外；本条规则不依赖该草案。）
- 最早出现陈述对以下设计一无所知：从未流片的、在其范围之外流片的、含 REF 记录的，或仅在结构哈希不忽略的方面有差异的（`TAP-draft-netlist-structural-hash` §8）。工具 MUST NOT 把已知最早出现展示为设计的起源。

### 4. 声明：签名陈述

#### 4.1 信封

陈述装在**信封**里，信封是一个恰好有以下成员的 JSON 对象：

| 成员 | 类型 | 内容 |
|---|---|---|
| `tapCredit` | number | `1` |
| `type` | string | `"Credit"`、`"Lineage"` 或 `"Revocation"` |
| `message` | object | 消息，恰好含 §4.3 中该类型的成员 |
| `signature` | string | `0x` 加偶数个小写十六进制数字，至多 2,048 字节 |

信封的 UTF-8 序列化 MUST NOT 超过 8,192 字节。在 `message` 中，`address` 值为小写地址，`bytes32` 值为 32 字节串，`string` 值为 JSON 字符串，`uint64` 值以及 `uint256` 成员 `signerChainId` 和 `chainId` 为 0 到 2^53 − 1 之间的 JSON 整数，`uint256` 成员 `circuitId` 为无前导零的十进制字符串。工具 MUST 拒绝违反 §4.1–§4.4 任何规则的信封。

#### 4.2 域

陈述是 EIP-712 类型化数据，域为

```
EIP712Domain(string name,string version)
name    = "TAP Design Credits"
version = "1"
```

域中没有 `chainId`、`verifyingContract` 或 `salt`，因此陈述不属于任何特定链，同一陈述可以在每条链上展示。域分隔符列在测试用例中，附录 A 给出一份完整的 `eth_signTypedData_v4` 载荷。

#### 4.3 类型

```
DesignRef(bytes32 netlistHash,bytes32 structuralHash)

Circuit(uint256 chainId,address processor,uint256 circuitId)

Credit(address signer,uint256 signerChainId,DesignRef subject,Circuit source,string role,string displayName,string noteURI,bytes32 noteSha256,string license,uint64 issuedAt,bytes32 nonce)

Lineage(address signer,uint256 signerChainId,DesignRef subject,string relation,DesignRef object,string reason,uint64 issuedAt,bytes32 nonce)

Revocation(address signer,uint256 signerChainId,bytes32 statement,string reason,uint64 issuedAt)
```

`hashStruct`、`encodeType`（被引用类型按字母序附在后面：先 `Circuit`，后 `DesignRef`）和摘要遵循 EIP-712：

```
digest = keccak256(0x19 ‖ 0x01 ‖ domainSeparator ‖ hashStruct(message))
```

摘要就是**陈述 ID**。类型和消息相同的两个信封是同一条陈述，即使签名不同。

#### 4.4 字段规则

| 字段 | 规则 |
|---|---|
| `signer` | 非零地址。作出陈述的账户 |
| `signerChainId` | `0`：`signer` 通过公钥恢复核验（§4.6 第 3 项）。否则为 `signer` 作为合约所在链的链 ID，通过 ERC-1271 核验（§4.6 第 4 项） |
| `subject`、`object` | 至少一个哈希非零的 `DesignRef`。零表示"未给出" |
| `source` | 三个成员全为零（无来源），或全不为零。非零来源指一个电路，签名者称其设计就是 subject |
| `role` | `designer`、`co-designer`、`optimizer`、`reviewer`、`tester` 之一（§4.5） |
| `displayName` | 至多 64 字节、Unicode 规范化形式 C 的 UTF-8，不含控制字符（U+0000–U+001F、U+007F–U+009F），也不含在 Unicode 15.1.0 中具有 `Default_Ignorable_Code_Point` 或 `Bidi_Control` 属性的任何码位（范围列在测试用例中）；为空表示没有 |
| `noteURI`、`noteSha256` | `noteURI` 至多 512 字节可打印 ASCII（`0x20`–`0x7e`）；`noteSha256` 是说明字节的 SHA-256。两者同为空和零，或同时给出 |
| `license` | 空，或 SPDX 许可表达式，或 URI，至多 256 字节可打印 ASCII |
| `relation` | `derivedFrom`、`supersedes`、`optimizes` 之一（§4.5） |
| `reason` | 字符规则同 `displayName`，至多 280 字节；可为空 |
| `statement` | 被撤回陈述的非零陈述 ID |
| `issuedAt` | 签名者声明的 Unix 时间（秒） |
| `nonce` | 任意 32 字节；用于区分其他方面相同的陈述 |

`displayName` 和 `reason` 的字符规则排除了零宽连接符（ZWJ）、变体选择符和标签字符等，因此用它们组成的 emoji 序列会被拒绝。

`subject` 与 `object` 共享一个非零 `netlistHash` 或共享一个非零 `structuralHash` 的 `Lineage` MUST 被拒绝。

若某个 `DesignRef` 同时给出两个哈希，且工具持有 SHA-256 等于其网表哈希的网表文件，则其结构哈希 MUST 是该文件的结构哈希；否则工具 MUST 拒绝该陈述。工具读取非零 `source` 时，除非 subject 适用于该电路（§3.3），否则 MUST 拒绝该 Credit。

#### 4.5 角色与关系的含义

Credit 的意思是：签名者声称在创建或检查设计 `subject` 中担任 `role`。

| 角色 | 声称的含义 |
|---|---|
| `designer` | 创建了该设计 |
| `co-designer` | 与他人共同创建了该设计 |
| `optimizer` | 通过改进另一个设计得到了该设计 |
| `reviewer` | 审查了该设计但未创建它 |
| `tester` | 编写或运行了该设计的测试 |

Lineage 的意思是：签名者声称 `subject` 与 `object` 之间存在 `relation`。

| 关系 | 声称的含义 |
|---|---|
| `derivedFrom` | `subject` 是以 `object` 为起点做成的 |
| `supersedes` | `subject` 取代 `object`，例如作为修正版本 |
| `optimizes` | `subject` 以更低成本计算与 `object` 相同的函数 |

`displayName` 是签名者给自己起的名字。`noteURI` 指向一份设计说明，其字节由 `noteSha256` 固定；取回说明的工具 MUST 检查其 SHA-256，MUST NOT 显示不匹配的说明。`license` 是签名者就其在设计和说明中享有的任何权利所提供的许可；它未经核验。`issuedAt` 不是事实。

#### 4.6 核验陈述

工具这样核验信封：

1. 检查 §4.1–§4.4。
2. 计算 §4.3 的摘要。
3. 若 `signerChainId` 为 0：签名 MUST 恰为 65 字节 `r ‖ s ‖ v`，`v` ∈ {0, 1, 27, 28}；`r` 和 `s` MUST 在 [1, n − 1] 内，且 `s` MUST NOT 超过 n/2，n 为 secp256k1 的阶；由摘要和签名恢复出的地址 MUST 等于 `signer`。
4. 若 `signerChainId` 不为 0：该链 MUST 是 TAP-10 §2.1 中的链；对其他任何链，陈述为**未核验**。**核验区块**是两个节点报告的最终性标签区块号中较低的那个。工具在核验区块、在两个节点上对 `signer` 调用 `isValidSignature(bytes32 digest, bytes signature)`（选择器 `0x1626ba7e`）；两个答复 MUST 完全相同，否则陈述为未核验。当且仅当调用返回的 32 字节值前四字节为 `0x1626ba7e` 时，陈述**在该区块**有效。工具记录链和核验区块。它 MUST NOT 回退到公钥恢复。对有锚点的陈述（§5.2），工具 MAY 另外在同一条链上、在其锚点所在区块调用 `isValidSignature`；这个结果只说明合约在那个区块接受了该签名。

通过的陈述**有效**；失败的**无效**。无法执行第 4 项的工具 MUST 把陈述视为**未核验**，MUST NOT 把它显示为有效。由于合约签名的有效性会变化，工具 SHOULD 在显示此类陈述时重新核验，并 MUST 显示其核验区块。

**跟随持有人的签名者。** 对合约签名者，工具 MUST 在链 `signerChainId` 上、在核验区块，按 TAP-10 §4.3 检查 `signer` 是否为某电路 N 的 TapeOut 容器。若是，持有 N 的人决定该容器接受哪些签名，工具 MUST 为它的每条陈述加上"N 的容器；有效性跟随其持有人"（或工具所用语言中的同义文字）标签，并 SHOULD NOT 对它的声明排名（§6.4）。

#### 4.7 撤回

一条有效的 Revocation R **撤回**陈述 S，当且仅当：S 有效，R 的 `statement` 等于 S 的陈述 ID，S 不是 Revocation，R 与 S 的签名账户（`signer` 和 `signerChainId`）相同，并且当 `signerChainId` 不为 0 时，R 与 S 在同一个核验区块有效。工具 MUST 在同一个核验区块判定合约签名者的陈述以及它所知道的、指向该陈述的每条 Revocation；在做不到时（例如某条 Revocation 未核验，或是在另一个区块核验的），它 MUST NOT 把 S 显示为生效。其他任何有效的 Revocation 均无效力。目标尚不为工具所知的 Revocation 会被保留，并在目标出现时生效。

没有任何陈述能恢复被撤回的陈述；想恢复某条声明的签名者，用新的 `nonce` 签一条新陈述。因此对外部账户签名者而言，撤回是永久的。对合约签名者而言，在合约接受 R 的每个核验区块，撤回都成立；在合约接受 S 但已不再接受 R 的区块（例如持有容器的电路易手之后），S 重新生效。工具 MUST NOT 把被撤回的陈述显示为生效；MAY 把它显示为已撤回。

### 5. 承载事实与陈述

#### 5.1 署名包与 `tap.credits`

**署名包**是一个 JSON 对象：

| 成员 | 必需 | 类型 | 内容 |
|---|---|---|---|
| `tapCreditBundle` | 独立文件中必需 | number | `1`。把独立文件标记为署名包，正如 `tapManifest` 和 `tapEarliest` 标记各自的对象。在 `tap.credits` 中 MAY 出现；出现时 MUST 为 `1` |
| `v` | 是 | number | `1` |
| `publications` | 否 | array | 发布事实（§3.1） |
| `earliest` | 否 | array | 最早出现陈述（§3.4） |
| `statements` | 否 | array | 信封（§4.1） |
| `anchors` | 否 | array | 含 `chainId`（number）、`contract`（string）、`txHash`（string）和 `logIndex`（number）的对象，每个指一条可能是锚点的日志（§5.2） |

任何生成方 MAY 为任何电路或设计把署名包作为独立文件发布；独立文件 MUST 含 `tapCreditBundle`，工具 MUST NOT 把不含它的独立 JSON 文件当作署名包。TAP-721 代币 MAY 把署名包作为其 `tap` 对象的 `credits` 成员携带（`TAP-draft-netlist-bound-nft` §7.1 允许其他 TAP 定义 `tap` 的更多成员）；`tap.credits` 不改变任何其他 `tap` 成员的含义。放入 `tap.credits` 的生成方 MUST NOT 用发布事实、最早出现陈述或声明去填写指明代币作者或制作者的元数据成员（例如 `created_by`、`artist`、`creator` 或 `author`）。

署名包中的一切都是核验的输入，而不是结果。工具 MUST 按 §3 和 §4 核验它所用的每个事实和陈述，MUST 忽略它不认识的成员。生成方 SHOULD 只放入能通过核验的事实和陈述，MUST NOT 放入它改动过的陈述。

#### 5.2 锚点与署名日志模式

陈述 S 的**锚点**是 TAP-10 §2.1 中某条链上的一条日志：它有四个 topic，`topics[0]` = `0x46f7d925bbc35e7f8caf9e4c0b850b7405b337d421079c498a73570c2758dfcb`（`CreditPosted(address,bytes32,bytes32,bytes)`），`topics[2]` 等于 S 的陈述 ID，其数据按 ABI 解码为一个 `bytes` 值，该值是 S 的某个信封的 UTF-8 序列化，并且 S 有效（§4.6）。`topics[1]` 和 `topics[3]` 在本 TAP 下没有意义，也不检查。锚点只证明 S 不晚于该日志所在区块在该链上的时间戳已经存在。工具在使用锚点日志前 MUST 按 §3.2 第 2 步和第 7 步（回执、区块一致性、最终性标签区块）读取它。

*署名日志（仅供参考）。* 下面这种只发事件的合约模式会产生锚点。本 TAP 不要求任何合约实现它，也不定义 ERC-165 标识符。

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapCreditLog {
    event CreditPosted(address indexed poster, bytes32 indexed digest, bytes32 indexed subjectKey, bytes statement);
    function postCredit(bytes32 digest, bytes32 subjectKey, bytes calldata statement) external;
}
```

按此模式的署名日志原样发出 `CreditPosted(msg.sender, digest, subjectKey, statement)`，不存储也不核验任何东西，不收费，从不回滚，没有所有者也没有升级路径，因而无法审查或重新解释陈述。`subjectKey` 是用于发现的提示：陈述 subject 的网表哈希（若非零），否则为其结构哈希；对 Revocation，取它所撤回陈述的 subjectKey。这样工具只需对 `topics[3]` 做一次 `eth_getLogs` 过滤，就能找到关于某设计的有锚点陈述，并按上面的规则检查每条日志。

### 6. 展示规则

这些规则适用于展示本 TAP 任何事实、最早出现陈述或声明的每个工具。

#### 6.1 事实

1. 工具 MUST 只在发布事实通过 §3.2 后才把它显示为已核验，并 MUST 写明链和区块。未核验的事实 MUST 要么不显示，要么显示为未核验。（参考性：这里的"已核验"指通过 §3.2 的发布事实，与 `TAP-draft-pod-attributes` 的 `standing.verified` 无关，后者报告的是挖矿合约的抽样检查。）
2. 工具 MUST 用"首次流片者"或"首个发布者"之类的措辞描述首个发布者，MUST NOT 对其使用"设计者""作者""创作者""由……制作"或同义说法。
3. 首个发布者在所读区块有合约代码时，工具 SHOULD 加以提示，因为它可能是中继者或钱包合约。

#### 6.2 声明

1. 工具 MUST 在显示每条声明时附上：表明其为声明的标签；其角色或关系；其签名者地址（完整显示，或一步操作即可看到完整地址），`signerChainId` 不为 0 时一并显示，容器还要附上 §4.6 的标签。
2. 工具 MUST 只在签名者地址旁、并标为自报地显示 `displayName`，MUST NOT 用它代替地址或给它加任何核验标记。
3. 工具 MUST NOT 用显示已核验事实的样式显示声明，MUST NOT 用声明填写或改变事实，MUST NOT 从声明推出事实。
4. 工具 MUST 说明声明指向哪种设计：一个确切文件（`netlistHash`），或具有某结构的所有文件（`structuralHash`）。
5. 工具 MUST NOT 把来自其他来源的名称、账号或资料当作签名者签过的那样附加到签名者上。

#### 6.3 最早出现陈述

工具 MUST 把成立的最早出现陈述显示为**已知**最早出现，并附上其范围和 `indexer`（若有），MUST NOT 把它描述为该设计的原创、史上第一或发明。成立集合有不止一个成员时，工具 MUST 把它们全部显示为并列。被驳倒和被取代的陈述按 §3.4 处理。

#### 6.4 多条声明

1. 对于工具显示了任何声明的设计，工具 MUST 显示其所有生效的声明（受 §6.6 约束），包括相互矛盾的声明。它 MUST NOT 挑出一条声明作为该设计的设计者，并 MUST 显示每个角色各有多少条生效的声明。
2. 关于同一设计的生效 Credit 声明按角色分组，组序按 §4.5。同一角色内，有锚点（§5.2）的声明在前，锚点时间戳早的在前；签名者为 TapeOut 容器（§4.6）的声明在最后，且不排名。其余无锚点声明之间、以及容器声明之间的顺序不作规定：工具 SHOULD NOT 把它呈现为先后之分，MAY 在每次显示时打乱。§6.5 的标记、`issuedAt` 和 `displayName` MUST NOT 影响顺序。
3. 对 `supersedes` 声明，工具 SHOULD 显示同一签名账户是否有关于 `object` 的生效 Credit。对 `optimizes` 声明，工具 MAY 显示它从两个网表文件计算出的事实（例如门数）；"相同函数"仍是声明，除非工具检查过，检查过的工具 MUST 说明如何检查。

#### 6.5 由首个发布者签名

当且仅当工具显示了电路 N 的已核验发布事实，声明适用于 N（§3.3），声明的 `signer` 等于该事实的 `publisher`，并且 `signerChainId` 为 0，或 `signerChainId` 等于该事实的 `chainId` 且 `signer` 上的 `isValidSignature` 在该事实的 `block` 接受了该声明（按 §4.6 第 4 项调用，但用该区块代替核验区块）时，工具 MAY 把该声明标为"由 N 的首个发布者签名"，其中 N 是电路的链上名称（或处理器与电路编号）。该标记 MUST 写明 N，MUST NOT 在措辞或样式上表现为作者身份的证明，也不改变 §6.4 的顺序。

对合约签名者，这需要读取发布区块时的合约状态；没有归档节点的工具无法判定，此时 MUST NOT 显示该标记。

#### 6.6 不受欢迎的声明

工具 MAY 把声明折叠在一个计数后面，例如既无锚点、也没有按 §6.5 标记的声明。被折叠的声明 MUST 仍可查看。工具 MUST NOT 因 `displayName` 折叠声明，MUST NOT 折叠按 §6.5 标记的声明。按本地名单隐藏声明的工具 MUST 说明有声明被隐藏。

#### 6.7 个人数据

`displayName`、`noteURI` 和说明可能含有签名者选择公开的个人数据。工具 SHOULD 停止显示已撤回陈述的显示名和说明，并 SHOULD 在得知撤回时把它们从自己控制的缓存中删除。

## 设计理由

**事实与声明分层。** 链能证明谁收到了铸造、在哪个区块；它不能证明谁有了这个想法。任何只靠链上数据拼出的"设计者"一行，都在悄悄把前者变成后者。两层、不同标签，加上"声明不流入事实"的规则，使这一区别清晰可见。还需要第三类，即最早出现陈述，因为"最早"是一个否定性陈述（不存在更早的出现）：其出现可以核查，但其"最早"只能被驳倒。

**相同的网表不是复制的证据。** 小电路的好网表不多，像示例中的四 NAND 异或这样的教科书构造会被一再推导出来。因此示例只用相同的网表和相等的哈希来描述，本 TAP 也不从中推断谁设计了什么、谁从谁那里拿了网表。

**以铸造接收者为首个发布者。** 一次流片有三个候选地址：交易发送者、铸造接收者和 `tapeout` 的 `msg.sender`。TAP-02 §6 依据 BNB Smart Chain 实现的已验证源码说明，`tapeout(bytes,uint32,uint32)` 铸给调用者，所以铸造接收者就是调用者。为确认没有其他入口，本草案在 BNB Smart Chain 区块 128,542,889 和 X Layer 区块 73,638,715 读取了电路信标背后的电路实现的运行时字节码（分别为 `0x8E1D125Def6d3826C278299273a0760D47626068` 和 `0x977f217887E085D298Cb3819cDAD5A0ee35F29B2`，即 TAP-10 列出的实现）。每个实现分派 26 个选择器（每个与 `EQ` 比较的 `PUSH4`），26 个都通过对候选签名重新计算 `keccak256` 得到了名称，其中五个名称来自公开的签名数据库：ERC-721 函数、除 `beat` 以外的 TAP-02 §6 函数（`beat` 的选择器 `0x1fc0021d` 不在任一分派表中）、`TAPEOUT_FEE()`、`TREASURY()`、`factory()`、`transistors()`、`transistorsContract()`、`sweepFees()` 和 `initialize(string,string,address,address)`（记录在 `assets/tap-draft-design-credits/chain-reads.json`）。按名称和 TAP-02 §6，其中只有 `tapeout` 是铸造函数。名称不等于行为：这次枚举排除了其他入口，但不排除某个具名函数内部的铸造。`Transfer` 日志是 ERC-721 的一部分，因此它在任何遵循 TAP-02 的处理器上都有这个含义，并且不依赖未写入文档的 `TapedOut` 事件。交易发送者是更弱的标识：钱包合约、中继者或容器流片时，发送者是付 gas 的那一方。

**为什么 `TapedOut` 事件只作佐证。** 它的签名 `TapedOut(uint256,address,uint32,uint32)` 是凭 topic 哈希匹配出来的，本草案没有读过电路实现的源码。在主网上，它的数据字对电路 17851 是 (4, 0)，对电路 17852 是 (10, 9)，与（门数、状态数）吻合，而不是 17852 的（NAND, LATCH）数 (1, 9)；这一含义是观察所得，未经确认。

**最终性标签区块与两个运营方。** 发布事实决定出现的先后，被重组的区块可能改变哪个出现在前。要求区块不高于该链的最终性标签区块（TAP-10 §2.1）、两个运营方的读数一致，沿用 TAP-10 §5 和 TAP-721 的来源核验。

**最早出现作为可驳倒的索引者陈述。** 对每条 TapeOut 链上每个电路建立完整索引是可能的，但规模大（仅 BNB Smart Chain 在区块 128,542,889 就有 1,341 个处理器），随每个区块变化，且钱包无法核查。带明确范围的陈述可以由任何索引者生成，一个已核验的反例就能驳倒它。跨链按时间戳比较是粗略的，而在单一排序器的链上，时间戳由排序器设定；因此并列就显示为并列，不去打破。有已知前驱的并列事实不在成立集合中，因为那个前驱同样与该出现并列或更早。

**两种哈希。** 网表哈希标识文件；结构哈希标识在重新编号、输入交换、死门和重复门下不变的设计。署名可以附在任一者上：设计者可以声明结构，而关于某种编码的陈述附在文件上。从别人那里拿来、又改到结构哈希变化（例如插入双重取反）的网表能同时逃过两者；这是 `TAP-draft-netlist-structural-hash` 的局限，在安全考虑中说明。

**与链无关域的 EIP-712。** 常见钱包会逐字段显示类型化数据，而不像原始哈希那样（TAP-10 §8.4 禁止外壳对原始哈希签名）。网表和声明与链无关，所以域中没有链 ID 或验证合约。但合约账户是按链存在的，所以 `signerChainId` 是签名消息的一部分：它指明由哪条链上的代码决定签名是否有效。

**`signer` 写进消息。** 否则，一个 ERC-1271 账户接受的签名，可能被拿去冒充同一所有者的另一个账户。两个电路由同一持有人持有的 TapeOut 容器就是这样一对。在 X Layer 区块 73,638,715、两个运营方上读取：`1.2.282.tape` 的容器（用开启器的 `accountOf` 找到）是 `0xAC4F791353eE9F06e2C50Ae4C34680D28Ea52a57` 的 EIP-1167 克隆，后者就是 TAP-10 列出的容器实现；该合约是一个信标代理，其信标 `0x9b135f586f7850a3fa92210c298f732b20bc8f44` 返回的实现为 `0x6B6fDa1483367e939314070a4f233c1DFD35996B`。容器的 `owner()` 等于该电路的持有人，对一个并不持有该电路的公开测试密钥所作的签名，其 `isValidSignature` 返回零（`assets/tap-draft-design-credits/chain-reads.json`）。把账户绑定进摘要就防止了这种重放。

**合约签名者在同一区块判定。** `isValidSignature` 的答复取决于合约状态，而容器的状态在其电路售出时会变。在同一区块判定一条陈述和指向它的 Revocation，可让两个答复保持一致：不会出现撤回按早先的持有人核验、声明按后来的持有人核验，从而声明显得生效的情况。使用最终性标签区块并要求两个运营方一致，让每个工具对同一区块得到同一答案。§6.5 的标记关乎谁收到了铸造，所以对合约，它询问的是铸造所在区块时的合约。

**低 s 与陈述 ID。** 陈述 ID 是摘要而不是签名，所以可延展的签名不会造出第二条陈述。可接受的 `v` 取值以及对 `r`、`s` 的范围检查沿用 TAP-10 §14.2；另外要求低 s（与以太坊对交易的要求相同），使外部账户的每个签名只有一种被接受的编码。

**五个角色、三种关系，不允许自由文本。** 自由文本角色会招来"已验证作者"之类的标签。封闭的列表让显示可比较；以后的版本可以增加取值。

**显示名的字符。** 默认可忽略字符和双向控制字符显示为空或会重排文字，使两个看起来一样的名字比较结果不同，或让一个名字看起来像另一个。在固定的 Unicode 版本下引用 Unicode 属性，让每个实现使用同一张表。

**锚点作为参考模式。** 陈述能自证，所以链上存储只会增加成本而不会增加真实性。链能补充的只有时间：日志证明某些字节不晚于某个区块已经存在。本 TAP 定义什么样的日志算锚点，而把合约留作参考，因此不需要任何特定的部署。一个无所有者、不可升级、不做核验的合约无法审查或重新解释陈述，工具也会忽略一切不能通过核验的内容。`subjectKey` topic 让工具无需读取每条日志就能找到关于某设计的锚点。

**有顺序而无先后。** 只有锚点给声明一个签名者事后无法选择的顺序，而即便这个顺序也可以被抢先（见安全考虑）。在无锚点的声明之间，任何顺序都会偏袒某人，例如陈述 ID 最小者，而签名者可以刷出小的陈述 ID；不规定顺序并允许打乱，可以避免工具暗示先后。

**依赖。** 需要 `TAP-draft-netlist-bound-nft`，因为网表文件和网表哈希在那里定义；需要 `TAP-draft-netlist-structural-hash`（它本身也依赖前者）来获得结构哈希。`TAP-draft-pod-attributes` 只是参考性引用：§3.5 自行按 `getMiner` 元组中的位置指明 `registrant`，本 TAP 的任何要求都不依赖该草案。TAP-10 提供链、最终性标签、处理器编号、名称、工厂、容器解析和读取规则；TAP-02 提供处理器接口，ERC-721 提供发布事实所依据的 `Transfer` 铸造事件。EIP-712 定义陈述编码，ERC-1271 定义合约签名。`tap.credits` 是可选的：从不显示 TAP-721 代币的工具，只用署名包就能实现本 TAP。

**Application 类型。** 本 TAP 是关于应用如何给信息打标签的约定；它不改变任何合约、文件格式或哈希，只给 TAP-721 元数据增加一个成员而不改变任何现有成员，因此不会削弱任何 Standards TAP（TAP-01 §3）。

**本 TAP 不包括的内容。** 身份核验、信誉分、争议裁决和付款都需要可信方或经济机制，本 TAP 不想定义它们。签名声明加可核查事实，是不需要信任的那一部分。

## 向后兼容

本 TAP 增加一个 JSON 成员和新的文件；不改变任何现有内容。忽略 `tap.credits` 的工具和交易市场不受影响。现有电路无需任何改动：它们的发布事实今天就能读取。

本草案依赖 TAP-721（`TAP-draft-netlist-bound-nft`），并在其之后提交。TAP-721 是核心草案申请的编号；若编辑分配了其它编号，本草案即采用该编号：本文中对 `TAP-draft-netlist-bound-nft` 和"TAP-721"的所有引用（包括 `requires` 字段）都替换为该编号。

## 测试用例

`assets/tap-draft-design-credits/vectors.json`（格式 `tap-design-credits-vectors/1`）由 `assets/tap-draft-design-credits/make_vectors.py` 生成，可逐字节复现；其 SHA-256 为 `de1eda4fa7f1ca31449bb73af72a55e1f4416c00d20fd63512873858b11aae8c`。其中所有私钥均按 `keccak256("tap-design-credits test key <n>")` 派生，标为 `testOnly`，是公开的测试密钥，绝不可用于任何其他用途。各节：

- `eip712`：域分隔符 `0x609a43feee15b09b02f48f2488d2a7657b828fb16b36dee7b3526a2ff4029450`，以及 `encodeType` 字符串和类型哈希：`DesignRef` `0xe0d77062a697623ec32ae3015da3f13817cf501f710e8d996629e77a6d550baf`，`Circuit` `0xd386bc95eeb878ae451ff972a49c90176c5ffbb790c94c9b2c539724163e02c0`，`Credit` `0xa3bd8c54c1373e9324d0fa362dc5f6a5d661d6de82130ec9307a8363c04f8cdf`，`Lineage` `0x83b976bf8511fef7567e8d66114d0a392d99e6acbaf0dfd878b4c40b9107f1ae`，`Revocation` `0xcca803a0f1cf651afe8aaa284da73db5bd30450c60f69823b9e19427c55a3370`；以及 `typedDataExample`，即附录 A 的载荷及其摘要和签名；
- `keys`：测试密钥及其地址；
- `unicode`：Unicode 版本以及 §4.4 排除的码位范围；
- `valid`：能通过核验的信封及其陈述 ID 和恢复出的签名者（带与不带来源、说明和许可的 Credit；每种关系的 Lineage；Revocation；`v` 的两种编码）；
- `invalid`：各违反一条规则的信封及预期错误（包括零宽字符、软连字符、ZWJ、变体选择符和标签字符）；
- `erc1271`：带记录的 `isValidSignature` 调用和核验区块的合约签名者陈述（合成数据），包括设计理由中的账户重放情形、TAP-10 §2.1 之外的链，以及带容器标签的签名者；
- `revocations`：若干场景及每条陈述的最终状态，包括合约签名者的撤回在同一区块判定、在另一区块判定以及未核验三种情形；
- `publication`：下面的示例及记录的读数、在 §3.2 每一步失败的变体（包括错误的最终性标签、TAP-10 之外的链和早于铸造的状态区块），以及只在 §3.2 不比较的字段上不同的变体；
- `earliest`：判定为成立、被驳倒、被取代、并列和无效的最早出现陈述，每条附工具所知的事实，包括处理器编号未知的情形和没有区块头时间戳的事实；
- `anchors`：是与不是锚点的日志；
- `display`：一个排序场景（§6.4、§6.5）及预期分组、标记（包括在发布区块被接受和被拒绝的合约签名者）和容器标签；无锚点组和容器组内部的顺序标为不作规定；
- `bundle`：示例的完整 `tap.credits` 成员、作为独立文件并带 `tapCreditBundle` 的同一署名包，以及因缺少 `tapCreditBundle` 或其取值错误而被拒绝的独立文件。

**示例（BNB Smart Chain，只读，2026-10-19）。** `assets/tap-draft-design-credits/fetch_reads.py` 把读数记录在 `assets/tap-draft-design-credits/chain-reads.json` 中；未发送任何交易。所有合约状态读取（`isCPU`、`cpuAt`、`circuitInfo`、`netlist`、`nextId`、`eth_getCode`）都在同一个区块 128,542,889（哈希 `0x7cc64dc1ec1e0e7eb8e20b104bb80a99c838a537b4776cd07d75b8171e5e6ecd`，2026-10-19 11:03:12 UTC）进行，它是 `bsc-dataseed.bnbchain.org` 与 `bsc-dataseed1.defibit.io` 报告的 `finalized` 区块中较低的一个；这些读取在这两个节点和归档节点 `tapeout.net/rpc`（共三个运营方）上返回相同的值。回执和区块头在 `bsc-dataseed.bnbchain.org`、`bsc-dataseed1.defibit.io` 和 `bsc-dataseed1.ninicoin.io` 上完全一致；日志和历史 `nextId()` 观测来自归档节点。下文把首个发布者称为账户 A、B、C、D。这些标签只属于本示例，与 `vectors.json` 的测试密钥无关；地址见 `assets/tap-draft-design-credits/chain-reads.json`。

| | `17851.30.tape` | `3.635.tape` |
|---|---|---|
| 处理器 | `0xb1024b89886b9a34aa4ff5f31c411d708b20a14c`（"TapeOut"，编号 30） | `0xf4412c52ec3ddf7caf5f518b6662f77b02bde28e`（"RefBench"，编号 635） |
| 铸造日志 | `Transfer(0 → 账户 A, 17851)`，日志索引 604 | `Transfer(0 → 账户 B, 3)`，日志索引 1166 |
| 区块 | 128,194,577，哈希 `0x2dadb1cb05354bc0759be63a7c2b354c8bd45ff7d2742c8532c62b06ac024867`，2026-10-17 15:30:08 UTC | 117,235,964，哈希 `0xf222237677fab4031938cb50bd8242f20fdaadea629ae205b2fe8c48402023ef`，2026-08-21 12:57:05 UTC |
| 交易 | `0x0d2638af463201264353140faa4b9740bfb92dae626ca1d4dedcf2b7010b3c18`，`tapeout`（`0x7bd3ac1d`），发送者 = 发布者 | `0xeeaba590bdd88a8da2ed6aa28dd2bf260f7f431479e69addd4ba6265c881a72c`，`tapeout`，发送者 = 发布者 |
| `TapedOut` 日志 | `topics[1]` = 17851，`topics[2]` = 发布者，数据 (4, 0) | `topics[1]` = 3，`topics[2]` = 发布者，数据 (4, 0) |
| 网表 | `0x00000002000003000000020000040000000300000400000005000006`，`nIn` 2，`nOut` 1 | 相同 |
| 网表哈希 | `0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e` | 相同 |
| 结构哈希 | `0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b` | 相同 |

两个发布事实都能通过核验。对 17851 而言，首个发布者、交易发送者和其矿机记录中的设计证明 `registrant` 是同一个账户 A；按 §3.5，这些都不能使 A 成为设计者。`3.635.tape` 是 XOR 题目的参考电路（`getTask(3)` 指向它），它的发布早于 17851。两个电路的网表哈希相同，这并不说明其中一个是否由另一个得来。

`assets/tap-draft-design-credits/scan_occurrences.py` 在同一个区块 128,542,889 读取了处理器 30 和 635 的每个电路，只用归档节点（公共节点只保留约一百个区块的状态，不够完成一次完整扫描）；`assets/tap-draft-design-credits/fetch_reads.py` 已在该区块、在两个公共节点上检查过界定扫描范围的两次读取。`nextId()` 对处理器 30 返回 17,975，对处理器 635 返回 267；在该区块，`circuitInfo(nextId())` 成功而 `circuitInfo(nextId() + 1)` 回滚，三个运营方结果一致，因此编号 1 到 `nextId()` 就是全部电路（见待定问题）。扫描计算了其中 `nIn` 为 2、`nOut` 为 1 的 4,248 个电路的设计（结构哈希涵盖 `nIn` 和 `nOut`，其他电路不可能匹配）；结果见 `assets/tap-draft-design-credits/occurrences.json`。共找到 132 个具有该网表哈希的电路（处理器 30 中 131 个，从 #906 到 #17975；处理器 635 中的 #3），以及 134 个具有其结构哈希的电路；多出的两个，处理器 30 的 #1045 和 #15368，是重新编号的变体（#1045 中间两条 NAND 记录对调）。同一处理器内编号按铸造顺序分配，所以 #906 是处理器 30 中最早的；不同处理器之间由铸造区块决定，#906 的区块早于 #3 的。下文范围的 `toBlock` 就是扫描区块。最早的并不是参考电路：

| | `906.30.tape` | `1045.30.tape` |
|---|---|---|
| 铸造日志 | `Transfer(0 → 账户 C, 906)`，日志索引 569 | `Transfer(0 → 账户 D, 1045)`，日志索引 72 |
| 区块 | 117,079,378，2026-08-20 17:22:18 UTC | 117,249,114，2026-08-21 14:35:46 UTC |
| 交易 | `0x7ac6baada39c8a5d45dc269c02b1c998a4c9098a880e38d9c56f8c99b35c0cef` | `0x7e1169b907a5137267ed03f438646b6f447b361d13aeaa8392616581be66c9d1` |
| 网表哈希 | 与 17851 相同 | `0x6b90490a18ea09ab2ad0d126773444705dd23c9a9b8d619e5f7d1571b1872ab4` |
| 结构哈希 | 与 17851 相同 | 与 17851 相同 |

对知道这四个出现的工具而言，陈述"结构哈希 `0x74db…559b` 的已知最早出现：`906.30.tape`；范围为链 56、处理器 [30, 635]、至区块 128,542,889"成立。同一陈述若指向 17851、`3.635.tape` 或 1045，则被 `906.30.tape` 驳倒；指向 `3.635.tape`、范围为 [635] 的被它取代；指向 17851、范围为 [635] 的无效，因为其出现落在自身范围之外；指向 1045、键类型为 `"netlist"` 且哈希为 17851 网表哈希的也无效。`906.30.tape` 由账户 C 流片，比题目的参考电路早约 20 小时：已知最早出现未必是参考设计，这些事实也都不能指认设计者。

## 参考实现

位于 `assets/tap-draft-design-credits/`（MIT；Python 3.9+，仅用标准库）：

- `credits.py`：纯 Python 的 keccak-256 和 secp256k1（RFC 6979 签名、公钥恢复）；三种陈述类型的 EIP-712 编码；信封和字段检查，包括 Unicode 15.1.0 字符表；可注入 ERC-1271 读取器（核验区块或指定区块）和容器解析器的陈述核验；在同一核验区块判定的撤回；基于记录读数的发布事实核验，含 §3.2 的回执规范化；电路的设计与 `applies` 关系；带成立集合的最早出现判定；锚点；署名排序、§6.5 标记和仅供参考的显示文字。
- `make_vectors.py` 写出 `vectors.json`；`test_credits.py` 检查向量，检查本文（以及其译文，若存在）的附录 A 与向量一致，并在已安装时把 keccak-256 与 pycryptodome、签名与 `eth_keys`、EIP-712 摘要和附录 A 的签名与 `eth_account`、附录 A 的载荷与 Foundry `cast wallet sign --data` 交叉核对。
- `fetch_reads.py` 记录示例和设计理由（选择器枚举、X Layer 容器）的链上读数；`scan_occurrences.py` 是用于最早出现示例的最小出现索引器。
- `canon.py`、`tapnft.py` 和 `tap02_reference.py` 原样复制自 `TAP-draft-netlist-structural-hash` 和 `TAP-draft-netlist-bound-nft` 的参考实现（来源与 SHA-256 见该目录的 README），使该目录可以独立运行。

不提供署名日志合约；§5.2 的模式仅供参考。`credits.py` 不做网络读取（§3.2 和 §4.6 第 4 项使用记录的读数和注入的读取器），不从链上取锚点日志（§5.2），并把 §4.4 的 subject 与 source 检查留给调用方（`applies`、`consistent_with_file`），因为它们需要网表文件。

## 部署

本 TAP 不依赖自己部署的任何合约，也未部署任何署名日志。发布事实依据 TAP-10 在部署一节列出的处理器工厂核验；在 BNB Smart Chain 上该工厂是未封存的可升级代理（TAP-02，部署），所以核验者记录其读取的状态区块。

## 安全考虑

- **通过显示名冒充。** 任何人都可以用任意 `displayName` 签署 Credit，包括知名设计者的名字或账号。§6.2 让名字紧挨签名者地址并标为自报；§4.4 的字符规则去掉了控制字符、默认可忽略字符和双向控制字符，但没有去掉形近字符，所以工具不应依靠名字识别任何人。
- **错误的"首个发布者"推理。** 首个发布者可能是复制者、中继者或合约。§3.5 和 §6.1 禁止把它展示为设计者，§6.5 把标记限定为关于"谁签了名"的陈述。
- **中继者与合约发布者。** 代用户流片的中继者或合约，会成为它提交的每个电路的首个发布者。给这种地址的标记，对其背后的用户什么也说明不了。
- **复制与规避结构哈希。** 复制公开网表没有成本，复制者还能通过保持功能的改动改变结构哈希（`TAP-draft-netlist-structural-hash`，安全考虑）。此时最早出现陈述会把副本当作新设计。Lineage 声明和审阅者可以指出这一点；本 TAP 无法检测。反过来，相同的网表也不是复制的证据。
- **抢先流片。** 任何人在网表流片前看到它（在交易池、共享文件或设计说明里），都可以抢先流片，成为已知最早出现。最早不等于起源（§3.5、§6.3）。
- **抢先与抢注锚点。** 锚点决定声明的顺序，而任何人都可以发布。在设计者为声明加锚点之前看到该设计的人，可以签一条自己的 Credit 并抢先加锚点；看到待上链的 `postCredit` 的人，可以更早地发布同一条陈述。锚点的顺序是发布的顺序，而不是作者身份的顺序，工具也按此显示。
- **密钥泄露。** 被盗的密钥可以签署声明，也可以撤回所有者的声明。外部账户的撤回是永久的，本 TAP 没有密钥轮换。设计者应使用专门为此保管的密钥签名，或使用所有者可以更换的合约账户；这种账户的陈述只在账户接受它们的区块有效（§4.6）。
- **会变化的合约签名。** ERC-1271 账户可能在某个区块接受一个签名、之后拒绝，或反过来；容器跟随其电路的持有人，所以它的声明随电路易手。工具显示核验区块、重新核验、在同一区块判定撤回（§4.7），并为容器加标签（§4.6）。
- **垃圾声明。** 签署声明不花钱，向署名日志发布只花 gas。§6.6 允许工具折叠无锚点、无标记的声明而不隐藏它们，§6.4 也不给无锚点声明任何先后之分。
- **重组与说谎的节点。** 发布事实和锚点在两个运营方上读取，并且只取不高于最终性标签区块的区块（§3.2、§5.2）；合约签名在两个运营方上、在最终性标签区块检查（§4.6）。
- **跨链排序。** 单一排序器链上的时间戳由该排序器选择；跨链并列显示为并列（§3.4）。
- **可升级的处理器。** 处理器合约是未封存工厂背后的信标代理（TAP-02）；一次升级可能加入其他铸造途径。发布事实记录区块，TAP-02 §7 第 3 项要求核验者记录该区块时的实现。
- **说明被替换。** 只有 SHA-256 与 `noteSha256` 匹配时才接受说明（§4.5）。
- **个人数据。** 显示名、账号和说明由签名者公开，是公开的，无法从副本中抹去。撤回能让合规工具停止显示它们（§6.7），但不能把它们从存档或署名日志中删除。

### 待定问题

1. 一旦有了展开规则，含 REF 记录的电路是否应获得设计（从而可以被声明）？
2. 是否应在每条 TapeOut 链上以同一地址部署一个署名日志，由谁部署？
3. 最早出现陈述是否应由索引者签名（一个 EIP-712 类型），让工具能衡量索引者？
4. 是否应接受尚未部署的合约账户的 ERC-6492 签名？
5. 在已部署的处理器上，`nextId()` 返回的是最新电路的编号：在铸造 17851 的区块 128,194,577 返回 17851；处理器 30 在区块 128,542,889 返回 17,975，此时 `circuitInfo(17975)` 成功而 `circuitInfo(17976)` 回滚，三个运营方结果一致。TAP-02 §6 把它描述为下一个电路将得到的编号。TAP-02 是否应更正？
6. 以后的版本是否应增加角色（例如 `compiler-author`），或为引脚置换变体增加一种关系？

## 版权

版权及相关权利通过 [CC0](../LICENSE) 放弃。

## 附录 A. `eth_signTypedData_v4` 载荷（仅供参考）

下面的载荷是 `assets/tap-draft-design-credits/vectors.json` 中的 Credit `credit_full`（`valid` 一节；也见 `eip712.typedDataExample`），即钱包通过 `eth_signTypedData_v4` 收到的形式。它使用公开测试密钥 1（地址 `0x541378bc90ff35563c25197869b436889f6caf4c`），绝不可用于任何真实用途。其摘要为 `0x453a0e24cda12aaf737632a3d3926de9d0cae46ca83c72ae8632b3a433165233`，签名为 `0xc07119a0cad762a825412457012608626f597908f513a80668858443711c892a2d5ac1d66827c1d598213784e0074b93fc5e2514d36fb17ba747ba431cb993101b`；`test_credits.py` 用 `eth_account` 和 Foundry `cast wallet sign --data` 检查两者。`circuitId` 按 §4.1 为十进制字符串。

```json
{
  "types": {
    "EIP712Domain": [
      { "name": "name", "type": "string" },
      { "name": "version", "type": "string" }
    ],
    "Credit": [
      { "name": "signer", "type": "address" },
      { "name": "signerChainId", "type": "uint256" },
      { "name": "subject", "type": "DesignRef" },
      { "name": "source", "type": "Circuit" },
      { "name": "role", "type": "string" },
      { "name": "displayName", "type": "string" },
      { "name": "noteURI", "type": "string" },
      { "name": "noteSha256", "type": "bytes32" },
      { "name": "license", "type": "string" },
      { "name": "issuedAt", "type": "uint64" },
      { "name": "nonce", "type": "bytes32" }
    ],
    "Circuit": [
      { "name": "chainId", "type": "uint256" },
      { "name": "processor", "type": "address" },
      { "name": "circuitId", "type": "uint256" }
    ],
    "DesignRef": [
      { "name": "netlistHash", "type": "bytes32" },
      { "name": "structuralHash", "type": "bytes32" }
    ]
  },
  "primaryType": "Credit",
  "domain": {
    "name": "TAP Design Credits",
    "version": "1"
  },
  "message": {
    "signer": "0x541378bc90ff35563c25197869b436889f6caf4c",
    "signerChainId": 0,
    "subject": {
      "netlistHash": "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e",
      "structuralHash": "0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b"
    },
    "source": {
      "chainId": 56,
      "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c",
      "circuitId": "17851"
    },
    "role": "designer",
    "displayName": "Ada (test) — 测试",
    "noteURI": "ipfs://bafy-test-note",
    "noteSha256": "0x478290f500973e722f5bf60c0a8e0ae51b9774e7b1582c44bacaf2445250b731",
    "license": "CC0-1.0",
    "issuedAt": 1792000000,
    "nonce": "0xc9d4ad756c3d2ec3f4f350c4e8013414968064454ea7b9040b16e4c5cfe1d690"
  }
}
```
