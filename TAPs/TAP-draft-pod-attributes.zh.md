---
tap: TBD
title: Proof-of-Design Attributes for Netlist-Bound NFTs
description: How a netlist-bound NFT whose netlist comes from a BEM miner circuit records that circuit's Proof-of-Design facts as a labelled snapshot at a pinned BNB Smart Chain block, in metadata and optionally as ERC-7496 traits.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/66
status: Draft
type: Application
created: 2026-10-18
updated: 2026-10-21
requires: TAP-02, TAP-10, TAP-draft-netlist-bound-nft, ERC-7496 (ethereum/ERCs commit b7520ddde9f659fa40cda2e0849d987a4ff88bf5)
license: CC0-1.0
---

本文是 `TAP-draft-pod-attributes.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。

# TAP-TBD：网表绑定 NFT 的设计证明属性

## 概要

本 TAP 扩展 TAP-721（网表绑定 NFT），让由 TapeOut 挖矿电路制成的 TAP-721 代币能够展示该电路在设计证明（PoD）挖矿中的成绩，形式是一份任何人都能对照链上核查的、标明日期的记录，同时不暗示该 NFT 会赚取或拥有任何东西。

## 摘要

本 TAP 是 TAP-721（网表绑定 NFT，`TAP-draft-netlist-bound-nft`）的扩展：它为 TAP-721 代币增加设计证明属性，不改动 TAP-721 本身的任何内容。TAP-721 代币可以指明一个来源电路。当该电路在 BNB Smart Chain 上的 BEM 设计证明（PoD）挖矿合约中注册为矿机时，收藏者会关心它的 PoD 事实（例如题目、烧掉的 NAND 与 LATCH 数、设计成本和最优首创标志）。本 TAP 定义代币元数据中的 `tap.pod` 成员：在一个固定的区块上读取的这些事实的快照，每个字段都对应它所来自的确切读取函数，分为已记录的设计事实和随时间变化的现状两组，并标明区块。本 TAP 还定义：验证方如何重读并确认快照；供同时在链上发布快照的集合使用的十五个 ERC-7496 特征（trait）键及其取值编码；一个可选的、未经验证的 `tap.rig` 引用，指向 X Layer 上的矿机凭证；集合不得作出的声明；以及（仅供参考）集合如何从这些属性推导稀有度。本 TAP 不部署任何合约。

## 动机

作为 TAP-721 缘起的那些集合，其网表取自在 PoD 下挖矿的电路。收藏者和交易市场想展示这些电路为什么值得注意：它们解决的题目、烧掉多少个 NAND 与 LATCH 元件、设计成本与题目参考值相比如何、是否占有最优首创席位。如今这些事实以截图的形式流传，旁边常有社区对 TapeOut 三种基本元件的简写 "C/N/L"，其中只有 N 和 L 是 PoD 事实。矿机的"已验证"状态也常被当作设计可用的证明，而它只报告挖矿合约的抽样检查结果。

没有约定会出三类问题。第一，这些事实大多会变：最优首创席位随时可能被夺走，矿机可能停止，权重也随之变化。复制进元数据而不带区块号的值，会在无人察觉的情况下变得错误。第二，这些事实只有与产生它们的读取函数和公式放在一起才有意义；"成本 108" 不配上 β 和深度就毫无意义。第三，放在矿机或代币旁边的 PoD 属性，很容易被理解成对挖矿收益的主张。共同的格式、验证流程和明确的不主张声明可以同时解决这三点。ERC-7496 已经为 ERC-721 代币定义了链上特征，所以本 TAP 采用它，而不是另定新接口（TAP-01 §10）。

## 规范

本文中的关键词 "MUST"、"MUST NOT"、"REQUIRED"、"SHALL"、"SHALL NOT"、"SHOULD"、"SHOULD NOT"、"RECOMMENDED"、"NOT RECOMMENDED"、"MAY" 与 "OPTIONAL"，当且仅当以全大写出现时，按 RFC 2119 与 RFC 8174 的描述解释。

### 1. 术语与记号

| 术语 | 含义 |
|---|---|
| TAP-721 代币（网表绑定 NFT）、`tap` 成员、来源电路、`tap.source`、`tap.netlist` | 按 TAP-draft-netlist-bound-nft 的定义（该草案 §1、§3、§7.1） |
| 挖矿合约 | BNB Smart Chain（chainId 56）上的 BEM PoD 挖矿合约，代理地址 `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46`（见部署） |
| 矿机记录 | 对某电路调用 `getMiner(minerKey(processor, circuitId))` 返回的元组；当该元组的 `taskId` 非零且其 `circuits` 等于处理器合约时，称该电路**有矿机记录** |
| 快照 | 一个 `tap.pod` 对象（§3）：一条矿机记录的事实及其所依赖的参数，全部在同一区块读取 |
| 快照区块 | 快照所在的区块（`tap.pod.block`） |
| 生成方 | 把快照写入代币元数据或特征的一方（通常是集合） |
| 验证方 | 对照链上检查快照的软件（§4.2） |
| 实时值 | 在晚于快照区块的区块上读取的值，用于在快照旁边展示 |

`getMiner`、`minerKey`、`bestSlot`、`bonusOf`、`cachedDepth` 与 `processorMultiplier` 的名字，以及 `getMiner` 元组成员的名字，取自官方 PoD 前端（tapeout.net/pod）中挖矿合约的 ABI 片段。`getTask`、`lambda()`、`beta()`、`lambdaBurn()` 与 `circuitBurn` 不在其中；它们的签名是通过直接读取确定的，`getTask` 的成员名沿用前端 `TaskAdded` 事件中的名字（`refArea`、`refCost`），其含义已通过数值得到确认（见测试用例）。这些来源只提供名字；§3.4 与 §3.5 中的元组位置以及 §3.6 中的选择器才是规范性的。十进制字符串：由 ASCII 数字组成的 JSON 字符串，不带符号、指数或前导零（零写作 `"0"`）。地址：`0x` 后接 40 个小写十六进制数字。哈希：`0x` 后接 64 个小写十六进制数字。JSON 数字是 0 到 2^53 − 1 之间的整数，与 TAP-draft-netlist-bound-nft §7.1 相同。

### 2. 适用范围

1. 本 TAP 适用于这样的 TAP-721 代币：其 `tap.source` 指明 BNB Smart Chain 上的一个电路，该电路在快照区块有矿机记录。只有 BNB Smart Chain 处理器工厂（TAP-02、TAP-10）所建处理器合约中的电路，才能作为携带 `tap.pod` 的代币的来源；其它链上的来源（TAP-draft-netlist-bound-nft §3）没有 PoD 事实。
2. 一个代币 MUST 至多携带一个 `tap.pod` 成员，且它 MUST 描述 `tap.source` 所指的电路。存在 `tap.pod` 时 `tap.source` MUST 存在，且 `tap.source.chainId` MUST 为 `56`。
3. TAP-draft-netlist-bound-nft 的每项要求继续适用。`tap.pod` 与 `tap.rig` 是该草案 §7.1 意义下 `tap` 的附加成员；未实现本 TAP 的工具忽略它们。
4. 快照描述的是来源电路，而不是 NFT。只有当来源已确认（TAP-draft-netlist-bound-nft §3.2）时，其事实才描述 NFT 的网表。来源未确认时，工具 MUST NOT 把 PoD 事实当作关于 NFT 网表的事实展示；它 MAY 把它们展示为"由集合声明，未经验证"。

### 3. `tap.pod` 对象

#### 3.1 快照规则

1. 一份快照的所有值 MUST 在 BNB Smart Chain 的同一区块 `B` 读取，并以 `block` 给出。`B` MUST 是该电路有矿机记录的区块。
2. 生成方 SHOULD 选择不晚于读取时 `finalized` 区块的 `B`，SHOULD 从至少两个结果一致的独立节点运营方读取（TAP-10 §5），并且 SHOULD 记录 `blockHash`。较旧的 `B` 只能从归档节点读取；公共 BNB Smart Chain 节点只保留很短时间的状态，所以读取近期区块的生成方 SHOULD 立即交叉核对。
3. 各成员按其随时间的表现分组：
   - `design` 存放**已记录的设计事实**：电路注册时存入矿机记录的值，以及由它们推导出的成本。只要矿机记录存在，它们就不会改变，除非挖矿合约的行为改变（见部署）。`area` 与 `bstar` 是用注册时生效的参数计算的；`cost` 使用 `B` 时的 β（`params.beta`）。由于挖矿合约自区块 121815032 起自报已封存（见部署），此后 β 不能再因升级而改变；更早区块的快照可能使用另一个 β。
   - `params` 存放 `B` 时的合约参数。
   - `standing` 存放**易变事实**：状态、最优首创标志、奖励、系数、权重、`since` 与 `stopBlock`。它们在之后的任何区块都可能改变。尤其是最优首创席位：每当同一（题目，处理器）组合注册了成本严格更小的设计，它就转给另一台矿机；占有者也可能在出现反例后被移出席位（"kick"）。因此席位占有者并不总是成本最小的设计（见测试用例）。
4. 展示任何 `standing` 值的工具 MUST 标明快照区块（并 SHOULD 附上区块日期），例如"区块 128200681（2026-10-17 UTC）时为最优首创"。它 MUST NOT 把 `standing` 值作为当前值展示。它 MAY 读取并在快照旁展示实时值，标为实时并注明各自的区块。
5. 本 TAP 不规定快照的最大时效。工具 SHOULD 显示快照的时效。

#### 3.2 成员

| 成员 | 必需 | 类型 | 内容 |
|---|---|---|---|
| `v` | 是 | number | `1` |
| `chainId` | 是 | number | `56` |
| `block` | 是 | number | 快照区块 `B` |
| `blockHash` | 否（SHOULD） | hash | 区块 `B` 的哈希 |
| `timestamp` | 否 | number | 区块 `B` 的时间戳（秒） |
| `mining` | 是 | address | `0x7e2e0dc66a3bd9103e69b766afa62d9f7b697b46` |
| `implementation` | 否（SHOULD） | address | `B` 时挖矿代理的 ERC-1967 实现（存储槽 `0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc`） |
| `processor` | 是 | address | 来源电路的处理器合约；MUST 等于 `tap.source.processor` |
| `circuitId` | 是 | 十进制字符串 | 电路编号；MUST 等于 `tap.source.circuitId` |
| `minerKey` | 是 | hash | `B` 时的 `minerKey(processor, circuitId)` |
| `params` | 是 | object | §3.3 |
| `design` | 是 | object | §3.4 |
| `standing` | 是 | object | §3.5 |
| `functionCheck` | 否（§3.9） | object | 对照题目参考电路进行的独立功能检查的结果（§3.9） |

此处未列出的成员 MAY 出现；工具 MUST 忽略不认识的成员。在下面各表中，ABI 类型宽于 32 位的值为十进制字符串，较窄的值为 JSON 数字。

#### 3.3 `params`

| 成员 | 类型 | `B` 时的读取函数 | 公式符号 |
|---|---|---|---|
| `lambda` | number | `lambda()` → `uint16` | λ |
| `beta` | number | `beta()` → `uint8` | β |
| `lambdaBurn` | number | `lambdaBurn()` → `uint16` | λ_burn |
| `processorMultiplier` | 十进制字符串 | `processorMultiplier(processor)` → `uint256` | P（该处理器的当前值） |

#### 3.4 `design`（已记录的设计事实）

位置指 `getMiner(bytes32)` 返回的 22 成员元组中的位置，从 0 起计：`circuits` 0、`circuitId` 1、`taskId` 2、`gateCount` 3、`stateCount` 4、`depth` 5、`area` 6、`mult` 7、`since` 8、`status` 9、`registrant` 10、`nandBurn` 11、`latchBurn` 12、`bstar` 13、`bonus` 14、`optimal` 15、`commitBlock` 16、`firstUnusedId` 17、`stopBlock` 18、`verifWeight` 19、`unverWeight` 20、`debt` 21。

| 成员 | 类型 | 来源 | 含义 |
|---|---|---|---|
| `taskId` | number | `getMiner` [2] `taskId`（`uint32`） | 矿机注册时所针对的题目 |
| `gateCount` | number | `getMiner` [3] `gateCount`（`uint32`） | g，计入面积的元件数 |
| `stateCount` | number | `getMiner` [4] `stateCount`（`uint32`） | s，状态元件数 |
| `nandBurn` | number | `getMiner` [11] `nandBurn`（`uint32`） | n，烧掉的 NAND 元件数 |
| `latchBurn` | number | `getMiner` [12] `latchBurn`（`uint32`） | m，烧掉的 LATCH 元件数 |
| `depth` | number | `getMiner` [5] `depth`（`uint32`） | d，合约计算的逻辑深度 |
| `area` | 十进制字符串 | `getMiner` [6] `area`（`uint64`） | A = g + λ·s，按存储值 |
| `bstar` | 十进制字符串 | `getMiner` [13] `bstar`（`uint64`） | b* = n + λ_burn·m（工本），按存储值 |
| `cost` | 十进制字符串 | 推导：`area` · max(`depth`, 1)^`params.beta`，精确整数 | C，设计成本 |
| `task` | object，可选 | `getTask(taskId)` | `name`（string，元组成员 7）、`kTask`（十进制字符串，元组成员 8，`refArea`）、`cRef`（十进制字符串，元组成员 9，`refCost`） |

`cost` 不存于矿机记录中；它 MUST 按上式用 `params.beta`（即 `B` 时的 β，§3.1 第 3 条）精确计算。对占有最优首创席位的矿机，`bestSlot(taskId, processor)` 返回与 `cost` 相同的值（见测试用例）。在 `task` 中，`kTask` 是题目的 K_task（题目参考电路的工本），`cRef` 是其 C_ref，两者都在题目创建时冻结；前端把 `refArea` 显示为 K_task。

#### 3.5 `standing`（易变事实）

| 成员 | 类型 | 来源 | 含义 |
|---|---|---|---|
| `status` | number | `getMiner` [9] `status`（`uint8`） | 原始状态码 |
| `statusLabel` | string | 由 `status` 推导 | 1 为 `"mining"`，其它所有代码为 `"unknown"` |
| `optimal` | boolean | `getMiner` [15] `optimal` | `B` 时占有最优首创席位 |
| `bonus` | 十进制字符串 | `getMiner` [14] `bonus`（`uint64`） | `B` 时计入的设计奖励 K_task·q（据观察，非最优时为 0） |
| `multiplier` | number | `getMiner` [7] `mult`（`uint32`） | 适用于该矿机的 P |
| `verified` | boolean | 推导：`verifWeight` > 0 | `B` 时的 PoD 抽样状态：挖矿合约接受了其抽样向量。它并不表明网表计算的是题目的函数（§3.9） |
| `verifWeight` | 十进制字符串 | `getMiner` [19] `verifWeight`（`uint128`） | 已验证权重 H = (b* + bonus)·P |
| `unverWeight` | 十进制字符串 | `getMiner` [20] `unverWeight`（`uint128`） | 未验证权重 |
| `since` | 十进制字符串 | `getMiner` [8] `since`（`uint64`） | 矿机开始的时间（Unix 秒，据观察） |
| `stopBlock` | 十进制字符串 | `getMiner` [18] `stopBlock`（`uint64`） | 停止区块，未停止时为 0 |

1 以外的状态码没有已确认的含义（见待定问题）。对这些代码，工具 MUST 把 `statusLabel` `"unknown"` 与原始代码一起显示，且 MUST NOT 猜测其含义。`registrant`、`commitBlock`、`firstUnusedId` 与 `debt` 在本 TAP 下不是属性；生成方 SHOULD NOT 把它们复制进 `tap.pod`，且 `debt`（奖励记账）MUST NOT 作为 NFT 的属性展示。

#### 3.6 读取函数与选择器

除 `circuitInfo` 与 `netlist` 在处理器合约上调用外，其余都是对挖矿合约的 `view` 或 `pure` 调用。生成或验证快照都不需要发送交易。

| 函数 | 选择器 | 返回 |
|---|---|---|
| `minerKey(address,uint256)` | `0x10eafa00` | `bytes32` |
| `getMiner(bytes32)` | `0x0527edc2` | §3.4 的 22 成员元组 |
| `getTask(uint32)` | `0x57342d74` | `(uint8 kind, uint32 cycles, uint32 nIn, uint32 nOut, uint32 vectorCount, bool active, bytes32 vectorsRoot, string name, uint64 refArea, uint256 refCost, address refCircuits, uint64 refCircuitId)` |
| `lambda()` | `0xdad0be61` | `uint16` |
| `beta()` | `0x9faa3c91` | `uint8` |
| `lambdaBurn()` | `0xfd1b18bb` | `uint16` |
| `processorMultiplier(address)` | `0x0f03daba` | `uint256` |
| `circuitBurn(address,uint256)` | `0x6687aabd` | `(uint32 nandBurn, uint32 latchBurn)`，交叉核对用 |
| `cachedDepth(address,uint256)` | `0xa18136f6` | `(bool cached, uint32 depth, uint32 live)`，交叉核对用 |
| `bestSlot(uint32,address)` | `0x11d5a55c` | `(uint64 holderPlus1, uint256 cost)`，交叉核对用 |
| `bonusOf(uint32,uint256)` | `0x500446c4` | `uint64`，交叉核对用 |
| `isSealed()` | `0x631f9852` | `bool`（见部署） |
| `circuitInfo(uint256)`（处理器） | `0x084d60f1` | `(nIn, nOut, nState, gateCount)` |

#### 3.7 一致性规则

一份快照在遵循 §3.2–§3.5 并满足下列条件时为**格式良好**：

1. `design.cost` 等于 `design.area` · max(`design.depth`, 1)^`params.beta`；
2. `standing.verified` 等于 (`standing.verifWeight` ≠ `"0"`)；
3. `standing.statusLabel` 符合 §3.5 的表格。

工具 MUST 拒绝格式不良的快照。下列关系对本 TAP 读取过的每台矿机都成立，但不是挖矿合约公布的规则；工具 SHOULD 把违反其中任一条的快照报告为警告，而不是拒绝：`gateCount` = `nandBurn` + `latchBurn`；`area` = `gateCount` + λ·`stateCount` 且 `bstar` = `nandBurn` + λ_burn·`latchBurn`（若注册后参数有变，这两条可以合理地不成立）；`optimal` 为 false 时 `bonus` = 0；已验证时 `verifWeight` = (`bstar` + `bonus`)·`multiplier`；`multiplier` = `params.processorMultiplier`；`minerKey` = keccak256(`processor`（20 字节）‖ `circuitId`（32 字节，大端））；`tap.netlist.nand` = `nandBurn` 且 `tap.netlist.latch` = `latchBurn`。

#### 3.8 命名

实现在机器可读的输出中 MUST 使用本 TAP 的成员名和特征名（`nandBurn`、`latchBurn`、`cost`……）。用户界面 SHOULD 使用明确的标签 "NAND burn"、"LATCH burn" 和 "Design cost"（中文界面可作"烧掉的 NAND"、"烧掉的 LATCH"、"设计成本"）。社区简写 "C/N/L" 指 TapeOut 的三种基本元件：N 与 L 对应 `nandBurn` 与 `latchBurn`；C 指 TapeOut 容器（电容），本 TAP 不描述它——来源电路的容器由 TAP-721 记录（`tap.source.container`）。本 TAP 的 PoD 公式中的字母 C（C = A·max(d,1)^β）表示设计成本 `cost`，与 "C/N/L" 中的 C 无关；界面 MUST NOT 把 `cost` 标为 "C/N/L" 中的 "C"，使用该简写的界面 SHOULD 同时显示明确的标签。

#### 3.9 功能检查（`functionCheck`）

1. `standing.verified` 只报告挖矿合约的抽样状态。工具 MUST NOT 把 `verified`（或 `verifWeight` > 0）作为网表计算其题目函数的证据展示。
2. 把网表作为其题目的正确实现展示的集合或工具（例如使用"正确""已证明"之类的标签、特征，或把正确性作为资格或稀有度的条件），MUST 独立地对照题目的参考电路检查该网表：参考电路是 `B` 时 `getTask(taskId)` 返回的处理器合约 `refCircuits` 中的电路 `refCircuitId`。当两个电路都是组合电路（没有 LATCH 记录）且 nIn ≤ 16 时，检查 MUST 穷举全部 2^nIn 个输入模式；否则 MUST 按一个公布的抽样程序进行。下面的程序 `tap-pod-fc/1` 就是这样一个程序；使用其它程序的集合 MUST 公布它（§4.4）。
3. 结果 SHOULD 记录为 `tap.pod.functionCheck`，一个与 `standing.verified` 分开的对象：

   | 成员 | 必需 | 类型 | 内容 |
   |---|---|---|---|
   | `method` | 是 | string | `"exhaustive"`、`"sampled"` 或 `"unconfirmed"`（检查无法进行，例如参考电路含有检查程序无法解析的 REF 记录） |
   | `vectors` | 是 | number | 比较过的输入模式数（组合电路）或节拍数（时序电路）；不一致时，计到第一个不同的为止（含该个） |
   | `result` | 除 `unconfirmed` 外 | string | `"match"` 或 `"mismatch"`；`method` 为 `"unconfirmed"` 时不出现 |
   | `procedure` | 是 | string | `"tap-pod-fc/1"`，或集合所公布程序的标识 |
   | `seed` | `sampled` 时 | hash | 抽样程序的 32 字节种子 |
   | `reference` | 除 `unconfirmed` 外 | object | 参考电路的 `processor`（地址）与 `circuitId`（十进制字符串） |

   只有当 `design.stateCount` 为 0 时才允许 `method` 为 `"exhaustive"`；穷举一致时 `vectors` = 2^nIn。除非 `result` 为 `"match"`，工具 MUST NOT 把网表展示为正确；工具 SHOULD 显示方法，对 `sampled` 还应显示向量数。
4. 程序 `tap-pod-fc/1`。求值按 TAP-02 §4；输入 `j` 是信号 `2 + j`。若候选电路与参考电路的 `nIn` 或 `nOut` 不同，结果为 `"mismatch"`，`vectors` 为 0。`stream(seed, i_1, …, i_k)` 是比特串 SHA-256(seed ‖ u32be(i_1) ‖ … ‖ u32be(i_k) ‖ u32be(0)) ‖ SHA-256(… ‖ u32be(1)) ‖ …，按字节读取，每字节最低位在先。
   - 两者都是组合电路且 nIn ≤ 16（`exhaustive`）：模式 `i`，`i` = 0 … 2^nIn − 1，输入 `j` = `i` 的第 `j` 位。
   - 两者都是组合电路且 nIn > 16（`sampled`）：16,384 个模式；模式 `k` 的输入取自 `stream(seed, k)`。
   - 其它情况（`sampled`）：64 轮（nIn = 0 时 1 轮）；每轮让两个电路都从全零状态开始，施加 max(`cycles`, 32) 个节拍，`cycles` 取自 `getTask`；第 `r` 轮第 `t` 拍的输入取自 `stream(seed, r, t)`；每一拍都比较输出。
   - 默认种子是 ASCII 字符串 `TAP-pod functionCheck v1` 的 SHA-256，即 `0x2a8ae4d777d75596dacbaefb75c5ca2304bb0f292ce47b5a438665217d1b3a99`。把该检查用于资格或标签的集合 MUST 在其清单中固定所用的种子（§4.4）。

### 4. 生成、验证与刷新

#### 4.1 生成

要在区块 `B` 生成电路 `(processor, circuitId)` 的快照，生成方在 `B` 读取：`minerKey(processor, circuitId)`；该键的 `getMiner`，若电路没有矿机记录则停止；`getTask(taskId)`；`lambda()`、`beta()`、`lambdaBurn()`、`processorMultiplier(processor)`；可选地读取区块头和实现槽位。它构建 §3 的对象并计算 `cost`。它 SHOULD 同时按 TAP-draft-netlist-bound-nft §3.2 确认来源，最好在同一区块。

#### 4.2 验证

检查快照的验证方 MUST：

1. 检查快照格式良好（§3.7），且 `processor` 与 `circuitId` 等于 `tap.source`；
2. 若存在 `blockHash`，对照链 56 的区块 `block` 检查它；
3. 在 `block` 读取 §3.3–§3.5 中列出的每个读取函数，并把每个成员与读到的值比较（`cost` 与由读到的值重新计算出的值比较）。

每项比较都成立时结果为 `confirmed`，任一项不成立时为 `mismatch`，验证方无法取得 `block` 时的状态（例如所有可达节点都已裁剪该状态）时为 `unavailable`。验证方 MUST NOT 依据在其它区块的读取报告 `confirmed`。当 `block` 时挖矿代理的实现与部署一节所列不同时，它 SHOULD 发出警告，因为此时读取函数的含义可能不同。它 SHOULD 使用两个独立的节点运营方，并 SHOULD 把只由一个运营方提供的读取报告为单一来源。它 MAY 同时显示实时值（§3.1 第 4 条）。

#### 4.3 刷新

生成方 MAY 用较新的快照替换代币的快照。新的 `block` MUST 大于原先的。集合是否已冻结从链上读取，而不是从元数据读取（TAP-draft-netlist-bound-nft §7.2）：在 L1，`frozen()` 返回 true；在 L0，清单 `freeze` 成员所指的探测返回其 `expect` 值（该草案 §5.1、§8）。集合一旦在此意义上冻结，其快照不再被替换。刷新 MUST NOT 改变集合已承诺的规则由 PoD 事实推导出的特征、标签或稀有度（§4.4）；它们仍按承诺的区块计算。集合 SHOULD NOT 有选择地刷新（例如只刷新现状改善了的代币）；若要刷新，它 SHOULD 在同一区块刷新集合中每个携带快照的代币。元数据改变时，实现了 ERC-4906 的集合按 TAP-draft-netlist-bound-nft §8.2 的要求发出 `MetadataUpdate` 或 `BatchMetadataUpdate`。

#### 4.4 在清单中承诺

通过揭示（TAP-draft-netlist-bound-nft §6）为代币分配内容、且携带 `tap.pod` 的集合，或由 PoD 事实推导特征、标签、档位、稀有度或资格的集合，MUST 按 TAP-draft-netlist-bound-nft §6.1 的要求，在主种子可被知晓之前，在其清单中固定下列内容：

1. 快照区块，作为清单的 `pod.block`（number）；
2. 由 PoD 事实推导特征、标签、档位、稀有度或资格的每条规则，作为 `pod.rule`：一个含 `sha256`（规则文档的 SHA-256）与 `uris` 的对象。规则文档 MUST 在同一时间之前公布；
3. 若规则或标签使用 §3.9，则检查程序及其种子，作为 `pod.functionCheck`：一个含 `procedure` 与 `seed`（hash）的对象。

揭示时，每个代币的快照 MUST 在 `pod.block` 读取；之后的刷新（§4.3）只能增大 `tap.pod.block`。在种子已知之后才选定的快照区块或规则 MUST NOT 被使用。拥有清单的工具 SHOULD 检查这些承诺，并 SHOULD 报告违反它们的集合。

### 5. 链上特征（ERC-7496）

#### 5.1 接口

本 TAP 使用 ethereum/ERCs 仓库提交 `b7520ddde9f659fa40cda2e0849d987a4ff88bf5` 时的 ERC-7496 "NFT Dynamic Traits"（文件 `ERCS/erc-7496.md`，SHA-256 `a751a977c0b2db8904a2f976bf9f5afcafbecd06124754ebc94a7f3b2369a9d5`；Standards Track，类别 ERC，创建于 2023-07-28，requires EIP-165、EIP-721 与 EIP-1155；状态 **Draft**，最后核对于 2026-10-17 UTC）。下面的名字、接口标识符和模式取自该文本。集合 SHOULD 说明它实现的 ERC-7496 提交。

集合 MAY 通过 ERC-7496 在链上发布其快照。ERC-7496 特征从代币合约本身读取；伴生合约（TAP-draft-netlist-bound-nft §8.3）无法承载它们，所以代币合约无法更改的集合只在元数据中发布 `tap.pod`。若集合发布特征，它 MUST 完整实现 ERC-7496，包括 `supportsInterface(0xaf332f3e)` 返回 true，并且 MUST 定义 §5.2 的每个特征（不能只定义一部分）。所用的函数和事件为 ERC-7496 中的：

```solidity
function getTraitValue(uint256 tokenId, bytes32 traitKey) external view returns (bytes32 traitValue);     // 0xa28eec87
function getTraitValues(uint256 tokenId, bytes32[] calldata traitKeys) external view returns (bytes32[] memory traitValues); // 0xf80ecba3
function getTraitMetadataURI() external view returns (string memory uri);                                 // 0xde475bf9
function setTrait(uint256 tokenId, bytes32 traitKey, bytes32 newValue) external;                         // 0x2bf453e3
event TraitUpdated(bytes32 indexed traitKey, uint256 tokenId, bytes32 traitValue);
event TraitUpdatedRange(bytes32 indexed traitKey, uint256 fromTokenId, uint256 toTokenId);
event TraitUpdatedRangeUniformValue(bytes32 indexed traitKey, uint256 fromTokenId, uint256 toTokenId, bytes32 traitValue);
event TraitUpdatedList(bytes32 indexed traitKey, uint256[] tokenIds);
event TraitUpdatedListUniformValue(bytes32 indexed traitKey, uint256[] tokenIds, bytes32 traitValue);
event TraitMetadataURIUpdated();
```

#### 5.2 特征名与键

按 ERC-7496 的建议，每个特征键是 UTF-8 特征名的 `keccak256`。特征名带前缀 `tap.pod.`，以免与集合的其它特征冲突。

| 特征名 | 特征键 | dataType | 值 |
|---|---|---|---|
| `tap.pod.snapshotBlock` | `0x0c83b866c7f4ae4bc14376df103564c65d79f5d851284a0c11a210f1728bca19` | decimal | `block` |
| `tap.pod.taskId` | `0xfd64ebeaade5a108f78bfc94ee0edfe916c75d828e7c70129827ea0caa1a4723` | decimal | `design.taskId` |
| `tap.pod.nandBurn` | `0xe6812d63110001a7da779d278372a1b4831d829f2b26af45f40826e40274f42b` | decimal | `design.nandBurn` |
| `tap.pod.latchBurn` | `0x91b9d0cc668255fa778685c7338fe63d92e536385c87f08c6e17a26d42c0ef85` | decimal | `design.latchBurn` |
| `tap.pod.area` | `0xef44719e0caef64b0ad22f820f1708667b608e0c4c59a80c8deebf8688627337` | decimal | `design.area` |
| `tap.pod.depth` | `0x691e154bb3637b1685d381f103f429ac2d4cdc57f92fd1f1194b47f0bd316e3e` | decimal | `design.depth` |
| `tap.pod.cost` | `0x1553b0cf7ee3f2ca0aa45a80f70c798570abcdf04acf5aec1a612b21ecc5d29b` | decimal | `design.cost` |
| `tap.pod.bstar` | `0x13d8a1dcf1cef697a18c42ef48929ae6e6124242f366c4ea7440825c3883cd36` | decimal | `design.bstar` |
| `tap.pod.status` | `0x5c1f2b4070b54fc2f5561f38390399cf8d4c29b81499370517a16c2717151d39` | decimal | `standing.status` |
| `tap.pod.optimal` | `0x8cc64f68d1b65bf6912ce63a85a0f5816e9b5a3ee7bdbd8bef65d7f44ca4abdb` | boolean | `standing.optimal` |
| `tap.pod.bonus` | `0xeb0e1e58cd5de11d87fbfa80b7b0c7db07fe2927be7ec0031c9c85d8b62ddb4a` | decimal | `standing.bonus` |
| `tap.pod.multiplier` | `0x8e86769259637e5965f73f19f92dd8221947eee18e3eb2566926f6e2184725ea` | decimal | `standing.multiplier` |
| `tap.pod.verified` | `0xa5dba9952bac764a13016b30c24d35b2efb5d9d9b33f600d4dcbfc44500659c5` | boolean | `standing.verified` |
| `tap.pod.verifWeight` | `0x0314874f9605c7d0456f0d16f4f551a20fbd2861f171aed22417d41a6f5da2d3` | decimal | `standing.verifWeight` |
| `tap.pod.unverWeight` | `0x0717ebcfb36876929ba6257ed6a85a3c22cc4ed0348df2bb927e4dbf3dcc811a` | decimal | `standing.unverWeight` |

#### 5.3 取值编码

- `decimal` 特征：无符号整数，大端，左侧补零到 32 字节（`bytes32(uint256(x))`）；特征元数据 `"signed": false`、`"decimals": 0`。若某个值放不进 256 位（只可能出现在 β 很大时的 `cost`），集合 MUST NOT 为该代币发布特征。`tap.pod.status` 承载原始代码；它 MUST NOT 使用 `valueMappings`，因为并非每个代码都已知。
- `boolean` 特征：false 为 `bytes32(0)`，true 为 `bytes32(uint256(1))`，不使用 `valueMappings`；这种 0/1 编码是 ERC-7496 对布尔值的默认编码。
- 题目名称、`params`、`since`、`stopBlock` 与 `minerKey` 没有特征；它们只在元数据中。

#### 5.4 存在性、写入与事件

1. `tap.pod.snapshotBlock` 是存在标记：一个代币有 PoD 特征，当且仅当该值非零。没有快照的代币 MUST 对 §5.2 的每个特征返回 `bytes32(0)`（ERC-7496 本身已要求已定义但无值的特征返回 `bytes32(0)`）。除非 `tap.pod.snapshotBlock` 非零，工具 MUST NOT 把其它特征的零值当作事实读取；`latchBurn` 为 0 和 `bonus` 为 0 都是合理的值。
2. 特征值 MUST 只通过写入一份快照之值的显式交易改变。合约 MUST NOT 在读取时通过调用挖矿合约（或任何其它合约）来计算它们；ERC-7496 禁止没有显式链上操作和事件就改变的特征值。
3. 一次写入 MUST 在一笔交易中用同一份快照设置代币的全部十五个特征，并且 MUST 为每个特征键发出 `TraitUpdated` 或 ERC-7496 的某个范围或列表事件。`tap.pod.snapshotBlock` MUST NOT 减小。
4. 只要一个代币在元数据中携带 `tap.pod`，同时又有 §5.2 的特征，两者 MUST 描述同一份快照；两者不一致时，工具 MUST 把该代币视为 `mismatch`，直到集合更正。（ERC-7496 规定链上值优先于元数据；本 TAP 补充规定：不一致即为错误。）
5. 对 §5.2 的每个特征，`tokenOwnerCanUpdateValue` MUST 为 false。`setTrait` 以及任何写入这些键的其它函数 MUST 限于集合指定的账户；集合 SHOULD 把该账户公开为 `owner()`（ERC-173），或在特征元数据中写明。
6. 集合一旦按 §4.3 的意义冻结（L1 时 `frozen()` 返回 true，或 L0 时清单的 `freeze` 探测返回其 `expect` 值），§5.2 的特征 MUST NOT 再被写入。
7. 集合 MAY 对 `tap.pod.snapshotBlock` 把 `validateOnSale` 设为 `requireEq`，使针对某一快照发出的报价不能在刷新后成交。对 §5.2 的其它特征，它 SHOULD 为 `none`。

#### 5.5 特征元数据

`getTraitMetadataURI()` 返回的文档 MUST 在各特征名下列出 §5.2 的每个特征，并带 §5.2 给出的 `dataType`。`displayName` 的值 MUST 唯一（ERC-7496）；集合 SHOULD 使用 `assets/tap-draft-pod-attributes/trait-metadata.json` 中的值，对其做本地化的集合 SHOULD 为易变特征保留"at snapshot"（快照时）字样。

### 6. 矿机引用（`tap.rig`）

`tap.rig` 是未经验证的引用。它 MAY 出现，用来指向 X Layer 上的一张矿机凭证，集合认为它与来源电路的矿机相关：

| 成员 | 类型 | 内容 |
|---|---|---|
| `chainId` | number | `196` |
| `contract` | address | `0x9cfc959cd42b2e1d39a0d850c528210e818ae520`（官方 "TapeOut Rig" 凭证，见部署） |
| `id` | 十进制字符串 | 凭证的代币编号 |

1. 本 TAP 不定义任何方法来验证该凭证属于来源电路的矿机，工具 MUST NOT 把它作为已验证展示。
2. 展示它的工具 MUST 把它标为引用，例如"相关矿机凭证（仅供参考）"；MAY 读取凭证的当前持有人并作为实时值展示；且 MUST NOT 暗示 NFT 持有人持有、控制矿机或凭证，或从中获益。
3. `tap.rig` MUST NOT 用作稀有度或排名的输入（§8），其缺失 MUST NOT 被视为缺陷。

### 7. 声明

1. 快照是关于某个电路在某个区块的事实记录。持有携带 `tap.pod` 或 `tap.rig` 的 TAP-721 代币，不赋予对 BEM、挖矿奖励、矿机产出的任何份额、矿机或其凭证、来源电路或其容器的任何权利，也不带来任何形式的收益。
2. 遵循本 TAP 的集合 MUST NOT 在其元数据、特征元数据或挂单文字中把代币描述为使持有人有权获得上述任何一项，且 MUST NOT 把 `verifWeight`、`unverWeight` 或 `bonus` 描述为 NFT 的收入。它 MUST NOT 把代币描述为投资或金融工具。
3. 展示 `standing` 值的工具 SHOULD 在其附近显示一条提示，例如"来源电路在区块 B 时的挖矿事实。本 NFT 不挖矿，也不赚取任何东西。"
4. 在代币元数据中加入 `tap.pod` 或 `tap.rig` 并不使代币得到矿机支撑。例如，代币没有矿机支撑的集合不会因加入 `tap.rig` 而变得有支撑，且 MUST NOT 作出相反的暗示。

### 8. 推导稀有度（仅供参考）

本节仅供参考，不增加任何要求。按 PoD 属性给代币排名的集合，可以公布规则并只用快照值计算，使排名可复现，例如：

- **设计效率**，基于已记录的设计事实：按题目计算 `q = cRef / cost`（越高越好；挖矿公式把 q 限制在 [1/4, 4]，排名不必如此），或在同一题目内比较 `cost`；
- **元件构成**：`latchBurn` > 0 的设计（时序）与组合设计相对照；`nandBurn` 分档；
- **题目**：按集合中每个 `taskId` 的代币数衡量的较稀有题目；
- **快照时为最优首创**：一枚徽章，按 §3.1 第 4 条的要求与其快照区块一起显示，因为席位会转移。

排名规则属于 §4.4 的承诺，在种子之前固定。奖励低成本的排名应要求 `functionCheck.result` 为 `"match"`，因为计算错误函数的设计可能比每个正确设计都便宜。基于已记录设计事实的排名长期有效；基于 `standing` 的排名只与快照一样新。权重描述的是挖矿合约的记账，而不是 NFT，不适合作为稀有度的依据。`tap.rig` 被排除在外（§6）。

## 设计理由

- **与 TAP-721 的关系。** 本 TAP 是单独的 Application 类 TAP，而不是 TAP-721 的一部分，因为它绑定于一个具体部署：BNB Smart Chain 上的 BEM PoD 挖矿合约，及其读取函数、参数和代理合约。TAP-721 是 Standards 类 TAP，其规则适用于任何 TapeOut 链上的任何 TAP-721 集合；PoD 属性只适用于来源电路有矿机记录的代币，并且挖矿合约升级或被替换时必须随之调整，这不应导致 TAP-721 重新修订。不取材于挖矿电路的 TAP-721 集合可以忽略本 TAP；工具不认识 `tap.pod` 时忽略它，这正是 TAP-721 对其它 TAP 定义的成员的要求。
- **是快照，不是指针。** NFT 可能在 X Layer 上，而矿机在 BNB Smart Chain 上，任何一条链上的合约都读不了另一条链。带标签的快照如实交代生成方看到了什么、何时看到的，任何人都能对照归档节点核查。指针（"去查电路 #17851"）会显示链上今天的情况，引人把今天的现状当成 NFT 的属性。
- **两组，承诺不同。** 设计事实在注册时存储一次；现状随该题目每个新提交的设计而变。在对象中分组，而不是逐个字段打标记，使工具只需一条展示规则（§3.1 第 4 条），也使稀有度规则可以选择稳定的输入。
- **在读取函数层面定义。** 每个成员都写明它来自哪个读取函数和元组位置，所以两个生成方对同一区块得到完全相同的对象，验证方只需要 `eth_call`。`cost` 是唯一推导出的设计值；它由存储值定义，以便在 `bestSlot` 不返回它的地方也能核查（它只返回席位占有者的成本）。
- **明确的名字。** 在 "C/N/L" 中，N 和 L 是 NAND 与 LATCH 两种元件，挖矿合约把它们计为 `nandBurn` 与 `latchBurn`；C 是 TapeOut 容器（电容），是另一种对象，由 TAP-721 记录为 `tap.source.container`。PoD 公式也使用字母 C，表示设计成本。因此机器可读的名字采用合约自己的名字（`nandBurn`、`latchBurn`、`cost`），使两个字母都不会产生歧义。
- **用 ERC-7496，而不是新接口。** 它是现有的、为 ERC-721 代币定义链上特征的 ERC，带有交易市场能读取的模式。它规定特征只能通过显式、发出事件的写入来改变，这与快照模型完全吻合；实时读取挖矿合约的合约会违反这一点。存在标记解决了 ERC-7496 默认值为零的问题，否则"没有快照"与"烧掉的 LATCH 为 0"无法区分。
- **十五个特征要么全有要么全无，并且一起写入。** 部分写入或混合区块的特征会让一个代币显示来自一个区块的成本和来自另一个区块的最优标志。
- **`verified` 不等于正确。** 挖矿合约在抽样向量通过后接受设计，因此已验证的网表可能计算与其题目参考电路不同的函数，而这样的设计可能比每个正确设计都便宜（见测试用例）。把抽样状态命名为 `verified`、把独立检查命名为 `functionCheck`，并放在不同成员中，可以把合约的说法与集合的主张分开。nIn = 16 以内的穷举检查代价很小（65,536 个模式）；超过此数以及对时序设计，使用在揭示前固定种子的公布抽样程序是可行的上限。
- **在种子之前承诺。** 现状事实逐块变化。如果快照区块或稀有度规则可以在种子之后选择，集合就能挑选对它已知持有人的代币有利的区块或规则。按 TAP-draft-netlist-bound-nft §6.1 对每个分配与标注输入的要求，把两者都固定在清单中，就去掉了这种选择。
- **状态用原始代码。** 只有代码 1 已确认。把未知代码映射成文字等于编造语义；原始代码加 `unknown` 标签便于今后安全扩展。
- **矿机引用未经验证。** 矿机桥接确实存在，但链上没有任何东西以本 TAP 可以核查的方式把凭证编号与电路联系起来，而 NFT 与矿机之间一个看似已验证的链接，正是 §7 所禁止的误导性声明。
- **考虑过的替代方案。** 只把 PoD 事实放进 ERC-721 `attributes`：作为允许的重复保留（TAP-draft-netlist-bound-nft §7.3 第 4 条），但不够，因为 `attributes` 没有区块、没有类型，也没有验证规则。推送实时值的跨链预言机：本版本不采用；它引入一个受信中继，而且仍然无法让现状成为 NFT 的属性。

## 向后兼容

本 TAP 只增加成员 `tap.pod` 与 `tap.rig` 以及一组 ERC-7496 特征键。实现了 TAP-draft-netlist-bound-nft 但未实现本 TAP 的工具会忽略新成员（该草案 §7.1）。已经在 `attributes` 中展示 PoD 事实的集合可以保留它们并加上 `tap.pod`；两者不一致时以 `tap` 为准。

本草案依赖 TAP-721（`TAP-draft-netlist-bound-nft`），并在其之后提交。TAP-721 是核心草案申请的编号；若编辑分配了其它编号，本草案即采用该编号：本文中对 `TAP-draft-netlist-bound-nft` 和"TAP-721"的所有引用（包括 `requires` 字段）都替换为该编号。

## 测试用例

`assets/tap-draft-pod-attributes/vectors.json` 由 `make_vectors.py` 从记录下来的读取结果生成，无需网络访问，测试套件可逐字节复现它（SHA-256 `ade615b1a2e461d26bbf88b67eb93767eb88d26a189b824cf0c484108a4dbebb`；`trait-metadata.json` `336be474884b5cf2ce32ed77bdb05a75a02c8b96db1073e229fe287c6cdda0ac`）。读取以只读方式在 BNB Smart Chain 区块 128200681（哈希 `0xf4733a8a55285297dedf89f2ecf23911ecb2a5e3922cb3ab86690f5a278830c5`，时间戳 1792253755，2026-10-17 16:15:55 UTC）进行：`assets/tap-draft-netlist-bound-nft/chain-snapshot.json`（四个电路；TapeOut #17851 与 #17852 的读取在两个运营方之间一致，而 #3151 与 #38 的读取以及合约参数 `lambda()`、`beta()`、`lambdaBurn()`、`taskCount()` 和两个 `processorMultiplier` 值只来自归档节点 `https://tapeout.net/rpc`）以及 `assets/tap-draft-pod-attributes/raw/`（`pod_snapshot.py`，归档节点，区块头已与第二个运营方交叉核对）。对两个来源都包含的三个电路，读到的每个字段都一致。该区块时的参数：λ = 6，β = 3，λ_burn = 1；`processorMultiplier` 对 TapeOut（`0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`，处理器 30）为 1，对 Blonskr_No1（`0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c`，处理器 1）为 6；实现为 `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898`。

| 电路 | 题目（K_task, C_ref） | g, s | n, m | d | A | b* | C | 区块 128200681 时的现状 |
|---|---|---|---|---|---|---|---|---|
| TapeOut #17851 | 3 XOR (4, 108) | 4, 0 | 4, 0 | 3 | 4 | 4 | 108 | status 1，非最优（席位：#906，C 108），bonus 0，P 1，verifWeight 4 |
| TapeOut #17852 | 220 8 位约翰逊计数器 (25, 584) | 10, 9 | 1, 9 | 1 | 64 | 10 | 64 | status 1，非最优（席位：#2033，C 64），bonus 0，P 1，verifWeight 10 |
| TapeOut #3151 | 48 8 位置位计数 (71, 290816) | 55, 0 | 55, 0 | 16 | 55 | 55 | 225280 | status 1，非最优（席位：#14947，C 45056），bonus 0，P 1，verifWeight 55 |
| Blonskr_No1 #38 | — | — | — | — | — | — | — | 无矿机记录（其网表含 REF 记录，挖矿合约拒收此类电路）：没有 `tap.pod`；每个特征均为 `bytes32(0)` |
| TapeOut #906（席位占有者） | 3 | 4, 0 | 4, 0 | 3 | 4 | 4 | 108 | 最优，bonus 4，verifWeight 8；`bestSlot` cost 108 |
| TapeOut #2033（席位占有者） | 220 | 10, 9 | 1, 9 | 1 | 64 | 10 | 64 | 最优，bonus 100，verifWeight 110；`bestSlot` cost 64 |
| TapeOut #14947（席位占有者） | 48 | 88, 0 | 88, 0 | 8 | 88 | 88 | 45056 | 最优，bonus 284，verifWeight 372；`bestSlot` cost 45056 |

这些向量说明：对每个席位占有者，`bestSlot(taskId, processor).cost` 等于由存储的面积和深度算出的 C = A·max(d,1)^β，而 `bonusOf(taskId, C)` 等于存储的奖励，后者等于 ⌊K_task·clamp(C_ref/C, 1/4, 4)⌋（对 #14947，C_ref/C ≈ 6.45 被限制为 4：71·4 = 284）。#17851 与 #17852 的成本与席位占有者相同却不是最优，与"严格更小"一致。成员 `verifiedButWrong` 是一个合成示例，标有 `"synthetic": true`，由 `synthetic/verified-but-wrong.json` 生成：一个由三个 NAND 构成的或门网表，以虚构的处理器和电路编号、在 #906 公开读取结果的上下文中，被记录为公开 XOR 题目 3 的已验证矿机。它计算的函数与题目参考电路不同（`functionCheck` 穷举不一致，四个模式中有一个不同），比席位占有者便宜（C 24 对 108）却不占有席位。链上确有这样的矿机；真实实例在向 TapeOut 团队披露之前不放入这些向量，合成示例覆盖的是同一项检查。每个存储的 `area` 与 `bstar` 都符合 A = g + λ·s 与 b* = n + λ_burn·m；`nandBurn` 与 `latchBurn` 等于 `netlist(id)` 中 NAND 与 LATCH 记录的数目，也等于 `circuitBurn` 的结果；verifWeight = (b* + bonus)·P。`cachedDepth` 的第二个返回值是存储的深度；它的第三个值（`live`：4、10、51）对这三个电路等于结构哈希草案（TAP-draft-netlist-structural-hash）§3 意义下的活元件数；这是观察结果，不是公布的规则，本 TAP 不使用该值。每份快照都带有按 `tap-pod-fc/1`、对照 `raw/ref-task<id>.json` 中记录的参考电路（处理器 `0xF4412C52ec3DDf7CAf5f518B6662F77B02Bde28E`，电路 3、48、220）得到的 `functionCheck`：XOR 与置位计数设计穷举一致（4 与 256 个模式），两个约翰逊计数器在 32 拍内一致（抽样，默认种子），合成的 `verifiedButWrong` 例子虽然 `verified` 为 true，却是穷举不一致。文件中还包含每份快照的特征值、特征元数据、十二份必须被拒绝的快照（每份违反一条规则）、五个清单承诺用例（§4.4），以及一份完整的代币元数据示例，含 `tap.source`、`tap.netlist`、`tap.pod` 与 `tap.rig`，能同时通过本 TAP 的验证器和 TAP-draft-netlist-bound-nft 的参考检查。

## 参考实现

Python 3.9，位于 `assets/tap-draft-pod-attributes/`（MIT）；ABI 处理使用 Foundry 的 `cast`，keccak-256 使用 pycryptodome：

| 文件 | 覆盖内容 |
|---|---|
| `pod_snapshot.py` | §4.1 在固定区块的读取（只读 JSON-RPC、跨节点交叉核对、单一来源报告）、§3 对象、§5.3 特征值、§5.5 特征元数据、测试用例中的交叉核对 |
| `pod_validate.py` | §3.7 格式良好检查与警告、§3.9 `functionCheck` 格式、§2 与 `tap.source` 的绑定、§4.4 清单承诺、§6 `tap.rig` 格式 |
| `function_check.py` | §3.9 程序 `tap-pod-fc/1`（使用 TAP-02 参考求值器）；`pod_snapshot.py --check` 读取参考电路并加入 `functionCheck` |
| `make_vectors.py` | `vectors.json`、`trait-metadata.json` |
| `test_pod.py` | 测试；重新生成向量并逐字节比较 |

使用 `assets/tap-draft-netlist-bound-nft/tapnft.py`、`tap02_reference.py` 与 `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`；分配编号后这些文件夹改名为 `assets/tap-<nn>/` 时，这些路径随之更新。

同一目录也以固定提交保存在 [BruceLanLan/TAP-721，提交 `a39f30b538e723e918bf9c3bb2998ee95f8e2f1a`](https://github.com/BruceLanLan/TAP-721/tree/a39f30b538e723e918bf9c3bb2998ee95f8e2f1a) 的 `assets/tap-draft-pod-attributes/` 下（逐字节相同），同一提交中还有在一个固定区块上对一组矿机电路运行 §3.9 功能检查的 `tools/collection/verify_function.py`。

## 部署

本 TAP 不部署任何合约。它读取：

| 链（chainId） | 合约 | 地址 | 本草案读取的状态 | 是否已封存？ |
|---|---|---|---|---|
| BNB Smart Chain (56) | PoD 挖矿合约（ERC-1967 代理，UUPS） | `0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46` | 在 119600000 至 128200681 之间抽样的每个区块，实现均为 `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898`；区块 128200681 时 `isSealed()` 为 true，`owner()` 为零地址 | 是，据其自报：`seal()` 在区块 121815032 执行（交易 `0xb42998938688380c395a904e055ffc98e7d4e67cae274228b793aeec715a300d`），发出转给零地址的 `OwnershipTransferred` 与 `Sealed()`。此前的所有者为 `0xbc951f39eA94818f54A6AbBF0FAC1Fe6AEce4876`，一个时间锁（`getMinDelay()` 172800 秒），由 `0x571d447f4f24688eC35Ccf07f1D6993655F6aF15` 执行 |
| BNB Smart Chain (56) | 作为来源的处理器合约 | 例如 TapeOut `0xb1024b89886B9a34Aa4ff5F31C411D708b20a14C`、Blonskr_No1 `0x1f5cb4aeae1807bf60c3b9c0d8adbcc14e91f12c` | `circuitInfo`、`netlist`（来源检查，TAP-draft-netlist-bound-nft §3.2） | 未封存工厂之后的信标代理（TAP-02） |
| X Layer (196) | TapeOut 矿机凭证（"TapeOut Rig"/RIG，代理） | `0x9cfc959cd42B2e1d39a0d850c528210E818AE520` | 本 TAP 不读取；仅在 `tap.rig` 中提及 | 否（所有者 `0xB3D85b42A045c1A88D800CAD0F55d2566a4D3138`） |

任何人都可以用 `eth_call`（`isSealed()` `0x631f9852`、`owner()` `0x8da5cb5b`）以及对 §3.2 所列槽位的 `eth_getStorageAt` 重复对挖矿合约的检查。

**这对快照意味着什么。** 在挖矿合约仍可升级时，一次升级可能改变任何读取函数的含义，所以快照只是关于其区块时生效的实现的陈述；记录 `implementation` 把这一点显式化。链上显示所有权已放弃，且该合约自区块 121815032 起自报已封存；因此，如果 `seal()` 去掉了所有升级途径，读取函数的含义就不会再因升级而改变。没有实现的源码，这一点无法完全确认，而在公开的区块浏览器上没有找到经验证的源码（见待定问题）。为此 §3.2 建议记录 `implementation`，§4.2 要求验证方在它与此处所列实现不同时发出警告。由于本 TAP 依赖挖矿合约的行为，只有该合约已封存时本 TAP 才能成为 Final（TAP-01 §5.1）；如果封存从源码得到确认，这个条件即已满足。

## 安全考虑

- **过时的快照。** 快照在其区块为真，晚一个区块就可能为假。主要风险在展示：一个显示"最优首创"却不带区块的交易市场，暗示了一个早已转给另一个设计的属性。§3.1 第 4 条，以及每个对象和特征集中都有的 `block`，就是防线；在快照旁显示实时值的工具能让过时一目了然。
- **挑选区块。** 区块由生成方选择。它可以挑一个电路恰好为最优或权重较高的区块，并只刷新有所改善的代币。验证（§4.2）证明的是这些值在该区块为真，而不是该区块具有代表性。工具应显示快照日期，并尽可能显示实时值；§4.3 要求集合统一刷新。
- **合约行为。** 这些事实的含义就是挖矿合约算出来的含义。区块 121815032 之前，其所有者可通过 48 小时时间锁升级它；此后它自报已封存。如果封存没有覆盖所有升级或参数途径，较晚的快照可能遵循与较早快照不同的规则。记录每份快照的 `implementation` 与 `params`，能保持快照之间可比，或表明它们不可比。
- **链上特征的受信写入者。** X Layer 上的 NFT 合约读不了 BNB Smart Chain。它的 ERC-7496 值是写入者提交的任何东西。这些值可核查（§4.2），但不自证；依赖它们的交易市场应对照 BNB Smart Chain 验证，或把它们标为由集合报告。
- **误导性营销。** PoD 权重看起来像收益，矿机引用看起来像背书。§7 禁止这两种声明；工具应显示 §7 第 3 条的提示，且不得把 `tap.rig` 显示为已验证。违反 §7 的集合不遵循本 TAP，无论它还实现了什么。
- **未验证的来源。** 快照可以附加到任何 NFT 上。没有已确认的来源（TAP-draft-netlist-bound-nft §3.2），PoD 事实属于某个电路，不一定属于该 NFT 的网表；§2 第 4 条限制了它们的展示方式。
- **节点的回答。** 撒谎的节点可以伪造任何读取。两个独立运营方可以挫败一个撒谎者；旧区块往往只有一个归档运营方提供，验证方应如实说明。`blockHash` 能发现错误的链或被重组的区块。
- **对草案的依赖。** ERC-7496 本身也是 Draft。如果它的接口或模式改变，按本 TAP 写入的链上特征可能不再符合交易市场的预期；集合说明其实现的提交（§5.1），而元数据快照不依赖 ERC-7496。
- **把错误设计展示为正确。** 把"已验证"显示为"正确"，或不做功能检查就按成本排名的集合，可能把最稀有的标签给一个计算错误函数的设计（见测试用例）。§3.9 禁止前者，并对后者要求检查。
- **种子之后的刻意挑选。** 没有 §4.4，集合可以在看到哪些代币得到哪些网表之后，再选择快照区块或稀有度规则。
- **不可信字符串。** 题目名称由题目创建者在链上设置，并被复制进 `tap.pod.design.task.name`。工具必须把它们当作不可信文本（HTML 转义，不做富文本渲染），且不得把它们用作标识符；标识符是 `taskId`。

### 待定问题

1. **状态码。** 只有 `status` 1（"mining"）已确认：官方前端检测的是 `status === 1`。据观察前端对代码 3 提供重新启动，暗示其含义为 "restartable"，但无法在其已发布的代码包中得到确认，所以本 TAP 把 3 与代码 0、2 和 4–255 一样标为 `"unknown"`。PoD 作者能否公布完整的对照表？
2. **挖矿合约源码。** 实现 `0xa3dbe873da37cd4e4a13c7cef23a7db6ca60f898` 在公开区块浏览器上未找到经验证的源码。没有源码，字段语义（尤其是 `stateCount`、`depth`、`unverWeight`、`cachedDepth` 的第三个值（据观察等于活元件数，见测试用例），以及 `seal()` 是否去掉了所有升级和参数途径）只能从观察和前端推断。
3. **`refArea` 即 K_task。** ABI 成员 `refArea` 的表现就是 K_task（它在三个题目上与 `bonusOf` 吻合；对题目 220，它不是参考电路的面积，因为 584 不是 25 的倍数）。`tap.pod` 是否应保留 `kTask` 这个名字？
4. **题目编号是否稳定。** 停止后重新启动的矿机能否改变 `taskId`？如果能，`taskId` 应归入 `standing`。
5. **时序检查语义。** `tap-pod-fc/1` 从全零状态起逐拍比较时序设计。向量允许预热或相位偏移的题目可能需要另一个程序；题目向量格式尚未公布。一旦 PoD 作者的向量语义可用，是否应以其取代？
6. **矿机映射。** 链上是否存在从矿机凭证编号到（处理器，电路编号）矿机的映射，可供后续版本验证？
7. **第二个运营方。** #3151、#38、参考电路以及合约参数的读取只来自一个归档运营方（见测试用例）。进入 Review 之前，应使用另一个能提供区块 128200681 状态的运营方重新读取。
8. **`exhaustive` 的适用范围。** 是否应把 `method` `"exhaustive"` 限定为两个电路都是组合电路且 nIn ≤ 16 的情形？

## 版权

版权及相关权利依 [CC0](../LICENSE) 放弃。
