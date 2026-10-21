---
tap: TBD
title: Soulbound Netlist Credentials
description: Non-transferable TAP-721 tokens that record a skill, a result or a contribution together with a netlist, and say whether the credential was proven by an on-chain check, attested by a named issuer or claimed by its holder.
author: Bruce (@BruceLanLan)
discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/73
status: Draft
type: Standards
created: 2026-10-20
updated: 2026-10-21
requires: TAP-02, TAP-draft-netlist-bound-nft, TAP-draft-design-credits, ERC-165, ERC-721, ERC-1271, ERC-5192, EIP-712
license: CC0-1.0
---

本文是 `TAP-draft-soulbound-credentials.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。

# TAP-TBD：灵魂绑定网表凭证

## 概要

本 TAP 定义一种不能出售、不能转移的徽章，每枚都带着一个真实电路，并且始终讲清楚：是合约检查过这个电路，是某个机构为持有人担保，还是只是持有人自己声称。

## 摘要

灵魂绑定网表凭证是一个按 ERC-5192 锁定的 ERC-721 代币；它的元数据遵循 TAP-721（`TAP-draft-netlist-bound-nft`），网表在铸造时绑定；它的合约记录一条凭证：类别、主体、对凭证含义负责的账户、范围、制品（artifact）的网表哈希、可选的证据哈希、签发与到期时间，以及它所替换的代币。凭证有三种类别，信任模型各不相同。**proven（已证明）**凭证由合约自己铸造：提交的无 LATCH 网表输入不超过 16 个，并通过了链上已承诺的规格。合约计算每一个输入向量并比较真值表哈希，且只接受落在其公布的工作量上限之内的规格，使每次检查都能在一笔交易内完成。提交先承诺、后揭示，承诺按承诺者分别记录；规格可以用一个与结构哈希等价的"设计键"，拒绝对往届已接受设计的改名复制。**attested（已担保）**凭证由具名签发者（外部账户或 ERC-1271 合约）签名的 EIP-712 证明铸造，可选到期和撤销。**claimed（自称）**凭证由持有人就自己铸造。任何类别都可以把智能体账户作为主体。每次铸造都由接收者本人发出或授权；持有人随时可以放弃；丢失私钥的情形通过重新签发到新账户、并链接旧代币来处理，绝不通过转移；proven 凭证的重新签发要等待一段延迟，期间旧私钥可以否决。本 TAP 定义接口、哈希、`tap.credential` 元数据成员、展示规则和一个中立的只读查询。它不定义任何获得收入、利润、代币或其他支付的权利。

## 动机

TapeOut 社区需要持久、公开的记录，证明某个人或智能体在电路上做过某件事：

1. 对基金会和 TapeOut 项目的贡献；
2. 设计技能："用不超过 N 个门做出了 4 位加法器"；
3. 比赛的结果；
4. 设计署名：目前是 `TAP-draft-design-credits` 下的签名声明，希望以代币形式落到链上；
5. 设计或检查电路的智能体的身份与能力。

这些记录不应可交易：能买到的技能徽章对持有人毫无说明力。ERC-5192 为 ERC-721 代币提供了一个最小、广为识别的锁定标志，但它不说明代币由谁签发、为什么可信。实际上，三种截然不同的东西在钱包里看起来一模一样：合约因为网表通过了任何人都能复算的检查而签发的徽章、某个机构因为"它说是"而签发的徽章、某人给自己铸造的徽章。把它们混为一谈会误导持有人、雇主、比赛组织者，以及日后依赖凭证的任何人。

TapeOut 有一般灵魂绑定代币方案所没有的优势：凭证所关于的对象往往就是网表，而网表可以在链上求值。按 TAP-02，无 LATCH 的网表是纯函数，所以"这个网表在门数预算内计算了规定的函数"可以由合约检查，也可以由任何钱包复查，无需信任任何人。本 TAP 把这个检查定义精确，加上比赛需要的承诺-揭示和查重规则，并把 attested 和 claimed 凭证放进同一种代币格式，用标签把它们区分开。

每个凭证合约都实现 ERC-5192，即 ERC-721 代币的最小灵魂绑定接口；本 TAP 补上 ERC-5192 对网表凭证未作规定的部分：凭证由谁签发、依据什么、如何显示。因此，作者申请编号 5192（提案名称 TAP-5192，与 ERC-5192 相呼应）；由于 TAP-01 §6.1 原本分配 10 以上最小的空闲编号，这需要编辑同意。在分配编号之前，本草案保留文件名 `TAP-draft-soulbound-credentials.md` 和 `tap: TBD`；最终编号由编辑分配，若与所申请的不同，本草案改用该编号。

## 规范

本文中的关键词 "MUST"、"MUST NOT"、"REQUIRED"、"SHALL"、"SHALL NOT"、"SHOULD"、"SHOULD NOT"、"RECOMMENDED"、"NOT RECOMMENDED"、"MAY" 和 "OPTIONAL"，当且仅当以全大写出现时，按 RFC 2119 和 RFC 8174 的描述解释。

### 符合性概览

本表只是下文各节的导引；与各节不一致时以各节为准。

| 部分 | 状态 | 章节 | 接口（ERC-165 id） |
|---|---|---|---|
| 灵魂绑定、凭证记录、状态、同意、放弃、重新绑定 | 核心：每个凭证合约 | §3 | ERC-721（`0x80ac58cd`）、ERC-5192（`0xb45a3c0e`）、ERC-165（`0x01ffc9a7`） |
| 核心接口 | 核心 | §8.1 | `ITapCredential`（`0x5558759c`） |
| proven 签发 | 签发 proven 凭证的合约必须实现 | §4、§8.2 | `ITapCredentialProven`（`0x07aaf2dc`） |
| attested 签发 | 签发 attested 凭证的合约必须实现 | §5、§8.3 | `ITapCredentialAttested`（`0x7587c9da`） |
| claimed 签发 | 签发 claimed 凭证的合约必须实现 | §6、§8.4 | `ITapCredentialClaimed`（`0x11e35684`） |
| 智能体主体 | 任何类别可选 | §7 | — |
| 元数据（`tap.credential`） | 核心 | §9 | — |
| 展示规则 | 每个展示凭证的工具 | §10 | — |

### 1. 术语与记号

| 术语 | 含义 |
|---|---|
| 凭证合约 | 遵循本 TAP 的 ERC-721 合约 |
| 凭证 | 凭证合约的一个代币，连同其凭证记录（§3.4） |
| 持有人 | 凭证当前的 `ownerOf` |
| 类别 | `proven`（1）、`attested`（2）或 `claimed`（3） |
| 主体 | `account`（0）或 `agent`（1）：持有人地址代表什么（§7） |
| 制品 | 绑定到凭证的网表，以其网表哈希标识（`TAP-draft-netlist-bound-nft` §2.3） |
| 组合文件 | 不含 LATCH 记录的有效 `tapnet/1` 文件（`TAP-draft-netlist-bound-nft` §2.2） |
| 规格 | proven 凭证据以检查的、已承诺的规则（§4.4） |
| 轮次 | 一个规格：一个承诺窗口，接着一个揭示窗口 |
| 系列 | 同一登记者共享查重命名空间的各轮次（§4.4） |
| 签发者 | 对凭证含义负责的账户（§3.4）；不是经核验的身份 |
| 工具 | 展示凭证或替他人读取凭证的软件 |

字节串以带 `0x` 前缀的十六进制书写。`‖` 表示拼接。`u8(x)`、`u32be(x)`、`u64be(x)` 分别是 1、4、8 字节的大端无符号整数；地址取其 20 字节。SHA-256 指 FIPS 180-4；`keccak256` 指 EIP-712 所用的哈希。`ASCII(s)` 是字符串 `s` 的字节。JSON 中的哈希和地址是带 `0x` 的小写十六进制。时间是 Unix 秒，与 `block.timestamp` 比较。

### 2. 范围与不作主张

凭证记录的是某件事发生过或被检查过。它不是金融工具。

1. 凭证不赋予、且凭证合约、签发者、元数据制作者和工具 MUST NOT 将其表述为赋予：任何获得收入、营收、利润分成、收益、股息、代币、空投、配额、奖励或任何其他支付或资产的权利；对签发者、基金会或金库的任何请求权；对网表、电路代币、容器或凭证本身以外任何 TAP-721 代币的所有权；对某个设计的排他权；或对任何人身份的核验。
2. 凭证合约 MUST NOT 因签发、持有、放弃、重新绑定、撤销或查询凭证而转移、铸造、锁定或释放除其自身凭证代币以外的任何资产，并且 MUST NOT 在交易 gas 之外为签发收取费用。
3. 凭证的整份元数据文档（§9），包括 ERC-721 成员 `name`、`description` 和 `attributes`，MUST NOT 包含陈述或暗示货币价值、价格、收益、份额、权重、积分、等级、倍数、配额、空投、奖励、预期支付或支付资格的成员、属性或文字（§9 第 2 项）。`TAP-draft-pod-attributes` 的 `tap.pod` 成员不受此限；它适用该 TAP 自己的不赋权规则（§9 第 2 项）。
4. §8.1 的查询是中立的：它返回某一类别凭证的事实，不赋予它们任何权重。在自己的决策中使用凭证的计划不在本 TAP 范围内，并对自己的规则负责。

TAP-721 下的网表绑定代币不带有对来源电路或其任何收益的权利（`TAP-draft-netlist-bound-nft` §3.2）；本 TAP 维持这一立场，不作任何增添。

### 3. 凭证代币

#### 3.1 灵魂绑定

凭证合约 MUST 实现 ERC-721、ERC-165 和 ERC-5192，并 MUST 报告 ERC-721（`0x80ac58cd`）、ERC-5192（`0xb45a3c0e`）、ERC-165（`0x01ffc9a7`）和 `ITapCredential`（§8.1）的 ERC-165 标识符。

1. `locked(tokenId)` 对每个存在的凭证 MUST 返回 `true`，对不存在的代币 MUST 回滚；
2. `transferFrom` 和两个 `safeTransferFrom` 函数对每个凭证 MUST 回滚，无论谁调用；
3. `approve` 和 `setApprovalForAll` MUST 回滚，使任何授权都不会暗示转移是可能的；
4. 合约 MUST 在铸造凭证的交易中发出 `Locked(tokenId)`，并且 MUST NOT 发出 `Unlocked`；
5. 放弃（§3.7）会销毁凭证，它是凭证离开持有人的唯一方式。重新绑定（§3.8）铸造一个新代币，旧代币仍留在其持有人处。

#### 3.2 与 TAP-721 的关系

每个凭证都是一个网表在铸造时绑定的 TAP-721 代币：一个没有清单、在铸造时记录每个代币网表哈希的集合（`TAP-draft-netlist-bound-nft` §7.2），与 `TAP-draft-netlist-bound-nft` §8.2 的铸造即绑定的集合做法相同。其元数据 MUST 遵循 `TAP-draft-netlist-bound-nft` §7，`tap.state` = `revealed`，且不含 `tap.manifest`。TAP-721 §7.1 在 `revealed` 状态下要求 `tap.image`，它 MUST 存在；它 MAY 描述一张由许多凭证共用的徽章图像。`tap.netlist.sha256` MUST 等于凭证记录中的制品。凭证不构成 TAP-721 版次（`TAP-draft-netlist-bound-nft` §6.4），即使许多凭证共用一个制品（例如徽章电路）也是如此，因为它们随网表一起铸造，没有清单，也没有揭示；其元数据 MUST NOT 包含 `tap.edition`。

因此凭证合约在元数据上符合 TAP-721 的 L0。它 MUST NOT 报告 `ITapNetlistNFT`（`0x282b67f6`）的 ERC-165 标识符，除非完整实现该接口。没有清单时，只有实现了 `TAP-draft-netlist-bound-nft` §8.2 铸造即绑定配置（属于对该草案的一项尚未合并的修订提案）的合约才能达到 L1，而 L1 还要求 ERC-4906，凭证合约不报告它（见下文）；因此凭证合约停留在 L0。但制品仍然记录在链上：`netlistHashOf`（§8.1）返回它，工具把两项事实一并显示（§10.1 第 5 项）。

TAP-721 §8.1 把 L0 下"内容不会改变"的保证建立在集合放弃修改 `tokenURI` 的能力之上。凭证合约 MUST 在每个凭证铸造时固定其 `tokenURI`，并且 MUST 此后不提供任何修改途径；元数据制作者 MUST NOT 修改该 URI 所提供的文档，并 SHOULD 使用内容寻址的 URI，使读者能够核查这一点。状态由合约保存（§3.5），所以凭证的任何变化都不需要修改其元数据：凭证合约 MUST NOT 发出 ERC-4906 事件 `MetadataUpdate` 和 `BatchMetadataUpdate`，并且 MUST NOT 报告 ERC-4906 的 ERC-165 标识符（`0x49064906`）。`tokenURI` 是否固定无法从链上读出；工具通过 §10.1 第 4 项的代码核验来确认，并按 §10.1 第 5 项显示。

制品文件 MUST 是有效的 `tapnet/1` 文件。凭证合约 MUST 在第一个指向某制品的凭证铸造之前（或同时），使该制品文件可通过 `netlistFile`（§8.1）读取。

#### 3.3 类别与主体

| 类别 | 谁决定这个凭证是应得的 | 读者能核查什么 |
|---|---|---|
| `proven`（1） | 凭证合约，按 §4 的检查 | 制品是否符合规格，可重跑检查（§10.2） |
| `attested`（2） | 签发者，通过签署证明（§5） | 签发者的签名或合约批准；不涉及证明内容是否真实 |
| `claimed`（3） | 持有人，就自己铸造（§6） | 仅能确认持有人作出了这一声称 |

持有人地址代表个人或组织时，主体为 `account`（0）；代表某个软件智能体的运营账户时，主体为 `agent`（1）（§7）。主体不改变类别。

#### 3.4 凭证记录

合约为每个凭证保存下表所列记录，并由 `credentialOf`（§8.1）返回。记录一经铸造永不改变；状态变化另行保存（§3.5）。

| 字段 | 类型 | proven | attested | claimed |
|---|---|---|---|---|
| `kind` | `uint8` | 1 | 2 | 3 |
| `subject` | `uint8` | 0 或 1，由承诺固定（§4.5） | 取自证明 | 由持有人选择 |
| `issuer` | `address` | 规格的登记者：定义"何为通过"的人 | 证明的签发者 | 铸造它的持有人 |
| `scope` | `bytes32` | 规格 id（§4.4） | 证明的范围（§5.2） | 某个 Design Credits 声明 id 的声称范围，或零（§6） |
| `artifact` | `bytes32` | 被接受文件的网表哈希 | 证明中的制品 | 所声称文件的网表哈希 |
| `evidence` | `bytes32` | 零 | 证据文档的 SHA-256，或零 | 证据文档的 SHA-256，或零 |
| `issuedAt` | `uint64` | 铸造时的区块时间戳 | 证明中的 `issuedAt`，不晚于铸造时的区块时间戳（§5.4） | 铸造时的区块时间戳 |
| `expiresAt` | `uint64` | 零（不到期） | 取自证明；零表示不到期 | 零 |
| `replaces` | `uint256` | 重新绑定后为旧代币 id（§4.7），否则为零 | 重新签发后为旧代币 id（§5.6），否则为零 | 零 |

代币 id 从 1 开始，所以 `replaces` 为零表示没有。

#### 3.5 状态

`statusOf(tokenId)` 返回：

| 值 | 状态 | 含义 |
|---|---|---|
| 0 | none | 代币不存在（从未铸造，或已放弃） |
| 1 | active | 以下都不适用 |
| 2 | expired | `expiresAt` ≠ 0 且 `block.timestamp` ≥ `expiresAt` |
| 3 | revoked | 签发者撤销了铸造它所依据的证明（§5.5） |
| 4 | superseded | 重新绑定或重新签发铸造了替代品（§3.8） |

revoked 和 superseded 是永久的且互斥（§5.5、§5.6）；只有两者都不适用时才返回 expired。大于 4 的值保留。每次变为状态 3 或 4，MUST 发出 `CredentialStatusChanged(tokenId, status)`（§8.1）。状态是链上状态：MUST NOT 写进元数据（§9），工具 MUST 从合约读取（§10）。

#### 3.6 同意

不得向没有请求的账户铸造凭证。凭证合约 MUST 只在下列情形之一向 `recipient` 铸造凭证：

1. proven：`recipient` 发出了一笔承诺交易（§4.5），为 `recipient` 记录了写明它的承诺；揭示 MAY 由任何人发出；
2. attested：`recipient` 是兑现交易的 `msg.sender`（§5.4）；
3. claimed：持有人是声称交易的 `msg.sender`（§6）；
4. 重新绑定：新持有人是重新绑定请求及其完成的 `msg.sender`（§4.7），或是重新签发的 `msg.sender`（§5.6）。

合约账户（包括智能体账户，§7）通过自己发起调用表示同意。

#### 3.7 放弃

持有人调用 `renounce(tokenId)` 时 MUST 销毁该凭证，其他调用者调用时 MUST 回滚。销毁发出指向零地址的 ERC-721 `Transfer` 和 `CredentialStatusChanged(tokenId, 0)`。放弃 proven 凭证还会删除针对它的待处理重新绑定请求（§4.7）。放弃之后，`statusOf` 返回 0，`ownerOf`、`credentialOf`、`netlistHashOf` 和 `locked` 回滚，该代币永不再被铸造。其他账户都不能销毁凭证：签发者要收回证明，只能撤销（§5.5）。

#### 3.8 以重新绑定代替转移

丢失私钥的持有人无法移动其凭证。替代品是一个新代币：

- 对 attested 凭证，签发者签署一份 `replaces` = 旧代币 id 的新证明（§5.6）；
- 对 proven 凭证，若规格指定了恢复授权方（recovery authority），由它签署一个 `Rebind`；替代品只有在一段延迟之后才会铸造，期间旧持有人可以否决（§4.7）。

proven 替代品复制旧记录，只有 `issuedAt`（新的铸造时间）和 `replaces`（旧代币 id）不同，并且绝不铸造给持有或曾持有同一规格凭证的账户。attested 替代品的记录取自新证明，新证明的签发者必须与旧的相同（§5.6）；签发者可借此续期或更正范围。两种情形下旧代币都保留在原持有人处并变为 superseded；合约发出 `CredentialRebound(oldTokenId, newTokenId)`。superseded 的凭证不能再次重新绑定，revoked 的 attested 凭证不能重新签发。claimed 凭证不重新绑定：新私钥的持有人重新声称即可。

### 4. proven 凭证

#### 4.1 可以证明什么

第 1 版只证明一个命题：提交的文件是一个组合文件，其 `nIn`（至多 16）和 `nOut` 与规格相同，NAND 记录不超过 `maxGates` 条，并且在每一个输入向量上都计算出规定的函数。对 `0 ≤ x < 2^nIn`，输入向量 `x` 把输入 `i` 设为 `x` 的第 `i` 位，即把 TAP-02 §5 的打包方式读作小端整数。超过 16 个输入或含 LATCH 记录的文件、时序行为以及 `tapnet/2` 文件不在范围内（§4.8）。

#### 4.2 真值表

对 `nIn ≤ 16` 的组合文件，第 `j` 列（`0 ≤ j < nOut`）是一个 `2^nIn` 位的串，其第 `x` 位是输入向量 `x` 下的输出 `j`，按最高有效位在前书写：第 `x` 位是第 `⌊x / 8⌋` 字节的第 `7 − (x mod 8)` 位。每列 `max(1, 2^nIn / 8)` 字节；`nIn < 3` 时未用的低位为零。

```
truthTable     = u32be(nIn) ‖ u32be(nOut) ‖ column_0 ‖ … ‖ column_{nOut−1}
truthTableHash = SHA-256(ASCII("tap-credential-truth-table/1") ‖ 0x00 ‖ truthTable)
```

示例（仅供参考，取自 `vectors.json`）：两输入异或的 `truthTable` = `0x000000020000000160`，`truthTableHash` = `0xd33c6800252db2f67a985dbb4a7d7a68c0babd8b03d2f95bfea65d836990dd2e`。登记者可以从预期的函数直接算出该哈希，而无需公开任何网表。

#### 4.3 设计键

对组合文件，每个信号 `s` 有一个标签 `λ(s)`，其中 `L(x) = SHA-256(ASCII("TAPSH1") ‖ x)`，标签按 32 字节串比较：

- 常量 0（信号 0）：`L(0x00 ‖ 0x00)`；常量 1（信号 1）：`L(0x00 ‖ 0x01)`；
- 输入 `i`（信号 `2 + i`）：`L(0x01 ‖ u32be(i))`；
- 元件 `NAND(a, b)`：`L(0x02 ‖ min(λ(a), λ(b)) ‖ max(λ(a), λ(b)))`。

由于 NAND 只读取更小编号的信号，按文件顺序扫描一遍即可标记每个元件。这些就是 `TAP-draft-netlist-structural-hash` §4.1–§4.2 的标签在不含 LATCH 记录的文件上的限制。令 `S = 2 + nIn + nand`，输出 `j` 是信号 `S − nOut + j`（TAP-02 §3）。

```
designKey = SHA-256(ASCII("tap-credential-design-key/1") ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut)
                    ‖ λ(output 0) ‖ … ‖ λ(output nOut−1))
```

对组合文件，两个文件设计键相同当且仅当它们的结构哈希相同（`TAP-draft-netlist-structural-hash` §7），前提是 SHA-256 在相关输入上没有碰撞（见原理）。之所以单独定义设计键，是因为合约只需一遍扫描、每个门一次 SHA-256 调用即可算出它，而不需要结构哈希所需的规范排序。工具显示结构哈希（§9）；合约比较设计键。

#### 4.4 规格

规格是如下元组

| 字段 | 类型 | 规则 |
|---|---|---|
| `registrant` | `address` | 登记它的账户；MUST 等于 `registerSpec` 的 `msg.sender` |
| `nIn`、`nOut` | `uint32` | `0 ≤ nIn ≤ 16`，`1 ≤ nOut ≤ 65536` |
| `target` | `bytes32` | 该函数的 `truthTableHash`（§4.2）。不为零 |
| `maxGates` | `uint32` | NAND 记录数的上限，至少为 `nOut` |
| `unique` | `bool` | 是否拒绝本系列任何往届已揭示的设计（§4.6 第 8 项）。要求 `series` 非零 |
| `series` | `bytes32` | 零，或登记者为把轮次分组而选的值 |
| `commitStart`、`commitEnd`、`revealEnd` | `uint64` | `commitStart < commitEnd < revealEnd` |
| `recoveryAuthority` | `address` | 零，或可以签署重新绑定的账户（§4.7） |
| `infoHash` | `bytes32` | 以文字描述任务的文档的 SHA-256；MAY 为零 |

```
specId    = SHA-256(ASCII("tap-credential-spec/1") ‖ 0x00 ‖ registrant ‖ u32be(nIn) ‖ u32be(nOut) ‖ target
                    ‖ u32be(maxGates) ‖ u8(unique) ‖ series ‖ u64be(commitStart) ‖ u64be(commitEnd)
                    ‖ u64be(revealEnd) ‖ recoveryAuthority ‖ infoHash)
seriesKey = SHA-256(ASCII("tap-credential-series/1") ‖ 0x00 ‖ registrant ‖ series)
```

除非上述每条规则都成立，并且另外满足以下各项，否则登记 MUST 回滚：

1. 不存在 `specId` 相同的规格；
2. 对规格所允许的每一个文件，合约都能在一笔不超过 16,777,216 gas（EIP-7825 的交易 gas 上限）的交易内完成 §4.6 的全部检查（包括存储文件），并为 calldata 留出余量。合约 MUST 拒绝登记它无法检查的规格，MUST 以常量以及通过 `checkBounds` 和 `specOf`（§8.2）公布其上限，并且 MUST NOT 修改它们。参考实现使用两个根据实测选定的上限（见原理）：
   - 门工作量：`(max(1, 2^nIn / 256) + 20) · maxGates ≤ 65,536`，其中一个单位是在一个 256 路字上求值一个 NAND，`+ 20` 计入与 `nIn` 无关的每门开销（文件检查、设计键、存储文件）；
   - 真值表缓冲区：`nOut · max(1, 2^nIn / 8) ≤ 131,072` 字节；
3. 若 `series` 非零，`commitStart` 不早于同一 `seriesKey` 下每个更早轮次的 `revealEnd`。因此同一系列的轮次永不重叠。

登记一个规格并不使登记者的描述成真：规格的文字含义由 `infoHash` 固定，工具会显示登记者（§10）。

#### 4.5 承诺

```
commitment = SHA-256(ASCII("tap-credential-commit/1") ‖ 0x00 ‖ specId ‖ recipient ‖ u8(subject)
                     ‖ netlistHash ‖ salt)
```

其中 `netlistHash` 是将要揭示的文件的 SHA-256，`salt` 是接收者选择的 32 字节，SHOULD 是随机的。`commit(specId, commitment)` 在 `commitStart ≤ block.timestamp < commitEnd` 之外、对未知规格、以及对 `msg.sender` 已为该规格记录过的承诺 MUST 回滚；否则为 `msg.sender` 记录该承诺并发出 `Committed(specId, msg.sender, commitment)`。承诺按承诺者分别记录：另一个账户记录的相同承诺既不妨碍、也不帮助 `msg.sender`。揭示只有使用由承诺中写明的接收者所记录的承诺才能成功（§4.6 第 2 项），所以承诺不能被改投给另一个接收者，抄袭他人待上链的承诺交易也一无所获。

#### 4.6 揭示

`reveal(specId, recipient, subject, file, salt)` MAY 由任何人发出。除非以下各项全部成立（检查顺序不限），否则 MUST 回滚：

1. `commitEnd ≤ block.timestamp < revealEnd`；
2. 由参数计算出的承诺已由 `recipient` 为该规格记录（§4.5）且尚未被消耗；
3. `recipient` 未持有、也从未持有该规格的凭证，无论是通过揭示获得还是通过重新绑定（§4.7）获得：每个账户在每个规格下至多获得一个 proven 凭证；
4. `file` 是不超过 49,152 字节的组合文件；
5. 其 `nIn` 和 `nOut` 与规格相同，NAND 记录数不超过 `maxGates`；
6. 其 `truthTableHash`（§4.2）等于 `target`；
7. 已计算出其设计键（§4.3）；
8. 若 `unique` 为真：同一系列的更早轮次（无论是否 `unique`）没有记录过相同的设计键（见下）。同一轮次内的提交互不排斥，因为它们全都在任何一个被揭示之前就已承诺。

成功时，合约消耗该承诺、存储文件、向 `recipient` 铸造凭证，并发出 `Accepted(tokenId, specId, recipient, netlistHash, designKey)`。若 `series` 非零，无论 `unique` 是否为真，还会为该系列记录这个设计键，使该系列以后每个 `unique` 轮次都拒绝它。

`unique` 的保证范围很窄。它比较的是设计键，所以保持功能不变的改写（例如双重取反，紧的 `maxGates` 不一定能排除）可以绕过它；而且它只覆盖同一登记者同一系列的各轮：另一个登记者的规格或一个新系列看不到以前的答案。`unique` 规格的凭证说明其设计键没有在该系列更早的轮次中被揭示过，而不说明该设计是原创的（§10.2 第 4 项）。

#### 4.7 proven 凭证的恢复

若规格指定了 `recoveryAuthority`，该账户 MAY 签署 `Rebind`（§5.1）。恢复需要三次调用：

1. `requestRebind(request, signature)`：除非 `msg.sender` 是 `request.newHolder`；旧代币存在、是 proven 且不是 superseded；其规格的 `recoveryAuthority` 非零且等于 `request.authority`；`deadline` 为零或尚未过去；`newHolder` 未持有、也从未持有该规格的凭证；签名按 §5.3 对授权方有效；且同一 `Rebind` 摘要此前未被使用过，否则 MUST 回滚。随后它把该摘要标为已用，记录该请求及 `readyAt = block.timestamp + REBIND_DELAY`（替换为该旧代币记录的任何请求），并发出 `RebindRequested(oldTokenId, newHolder, readyAt)`。参考实现把 `REBIND_DELAY` 设为 604,800 秒（七天）；合约 MUST 公布其延迟，并且 MUST NOT 把它设为少于一天。
2. `vetoRebind(oldTokenId)`：除非 `msg.sender` 持有旧代币且存在针对它的待处理请求，否则 MUST 回滚。它删除该请求并发出 `RebindVetoed(oldTokenId)`。仍掌握私钥的持有人由此可以阻止腐败或出错的授权方；放弃旧代币也有同样效果。
3. `completeRebind(oldTokenId)`：除非存在针对旧代币的待处理请求、`msg.sender` 是其 `newHolder`、`readyAt ≤ block.timestamp < readyAt + REBIND_DELAY`、旧代币仍然存在且不是 superseded、并且 `newHolder` 仍未持有、也从未持有该规格的凭证，否则 MUST 回滚。随后它删除该请求，记录 `newHolder` 持有该规格的凭证，并按 §3.8 重新绑定。

请求自其 `RebindRequested` 起处于待处理状态，直到被完成、否决或替换，直到旧代币被放弃，或直到 `readyAt + REBIND_DELAY`：在就绪后 `REBIND_DELAY` 之内未完成的请求即告失效，不能再被完成或否决。由授权方签署、按第 1 项请求的新 `Rebind` 会替换待处理或已失效的请求，并重新开始计算延迟；这样，无人完成的请求不能阻塞恢复，而能够被完成的请求总是给旧持有人留下完整的一段延迟来否决。放弃旧代币会删除其请求（§3.7）。被否决或被替换的请求不会复活：其摘要仍为已用，授权方若仍想重新绑定，须以新的 `nonce` 签署新的 `Rebind`。若规格未指定授权方，proven 凭证不能重新绑定；对未设 `unique` 的规格，新私钥的持有人可以在以后的轮次中再次获得该凭证。

#### 4.8 更大的、时序的以及乐观的检查（仅供参考）

第 1 版只证明合约能在一笔交易内完整检查的内容（§4.4 第 2 项）。较早的草案曾以一个公开的参考网表为准乐观地接受更大的文件；这一模式已被移除，原因是：最大的文件放不进一笔交易，公开的参考网表泄露了答案，"已证明"也变成了"尚未被驳倒"。以后的版本可以用 `TAP-draft-large-netlists` §7 的争议博弈来证明更大的、时序的（LATCH）或 `tapnet/2` 网表，但要有自己的接口、表示主张被推翻的自己的状态，以及有别于"已证明"的自己的标签。

### 5. attested 凭证

#### 5.1 EIP-712 域与类型

```
EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)
name    = "TAP Soulbound Credentials"
version = "1"
chainId = 凭证合约所在链的 chain id
verifyingContract = 凭证合约

Attestation(address issuer,address recipient,uint8 subject,bytes32 scope,bytes32 artifact,bytes32 evidence,uint64 issuedAt,uint64 expiresAt,uint64 deadline,uint256 replaces,bytes32 nonce)

Rebind(address authority,uint256 oldTokenId,address newHolder,uint64 deadline,bytes32 nonce)
```

`digest = keccak256(0x19 ‖ 0x01 ‖ domainSeparator ‖ hashStruct(message))`，同 EIP-712。证明的摘要就是其**证明 id**。类型哈希为 `Attestation` `0x228dbd1f2d086ffc2f8992a5c372964d588ea1745ce363fb4a770c7848126d5e` 和 `Rebind` `0x608e975c3778a409ea42f524f1487367e7114b1e711368291409ea557222972d`。与 Design Credits 声明不同，证明绑定到一条链上的一个合约，因为合约要据此铸造。

#### 5.2 字段规则

| 字段 | 规则 |
|---|---|
| `issuer` | 不为零。签署该证明，或作为合约按 ERC-1271 批准它 |
| `recipient` | 不为零。唯一可以兑现它的账户 |
| `subject` | 0 或 1（§3.3） |
| `scope` | 不为零。证明所关于的事项。用文字命名范围的签发者 SHOULD 使用 `SHA-256(ASCII("tap-credential-scope/1") ‖ 0x00 ‖ UTF-8(label))`，以便工具显示该标签（§9） |
| `artifact` | 不为零。凭证制品的网表哈希：通过的设计、参赛作品或徽章电路 |
| `evidence` | 零，或证据文档的 SHA-256 |
| `issuedAt` | 签发者作出证明的时间，由签发者声明；不晚于兑现时间。它成为记录中的 `issuedAt` |
| `expiresAt` | 零，或晚于 `issuedAt` 的凭证到期时间；`expiresAt` 已过的证明不能兑现 |
| `deadline` | 零，或证明可被兑现的最后时间 |
| `replaces` | 零，或它所替换的代币 id（§5.6） |
| `nonce` | 任意 32 字节；用于区分其他方面完全相同的证明 |

#### 5.3 签名

签名者 `A` 对摘要 `h` 的签名，在以下任一项成立时有效，按此顺序检查：

1. 签名恰为 65 字节 `r ‖ s ‖ v`，`v` ∈ {0, 1, 27, 28}，其中 0 和 1 代表 27 和 28（与 `TAP-draft-design-credits` §4.6 相同）；`r` 和 `s` 不为零；`s ≤ n/2`，`n` 为 secp256k1 的阶；且 `ecrecover(h, v, r, s)` 返回 `A`；
2. 调用时 `A` 有代码，且在 `A` 上调用 `isValidSignature(h, signature)`（ERC-1271，选择器 `0x1626ba7e`）返回的值前四个字节为 `0x1626ba7e`。

无论 `A` 是否有代码，合约都 MUST 先尝试第 1 项再尝试第 2 项：带有 EIP-7702 委托的外部账户有代码但仍保有私钥，其私钥签名 MUST NOT 取决于委托代码如何应答。

#### 5.4 兑现

`redeem(attestation, signature)` 除非满足以下全部条件，否则 MUST 回滚：字段遵循 §5.2；`issuedAt ≤ block.timestamp`；`expiresAt` 为零或大于 `block.timestamp`；`msg.sender` 是 `recipient`；该证明 id 既未被兑现也未被撤销；`deadline` 为零或尚未过去；签名对 `issuer` 有效（§5.3）；制品文件可通过 `netlistFile` 读取（任何账户都可以用 `storeNetlist` 存储有效文件，§8.1）；以及 `replaces` 非零时满足 §5.6。随后它按 §3.4 的记录铸造凭证（其 `issuedAt` 取自证明），并记住由该证明 id 铸造的代币。attested 凭证可以累积：没有"每个签发者和范围一个"的限制，一个账户可以持有签发者和范围都相同的多个 attested 凭证，每个都由各自的证明兑现。

#### 5.5 撤销

`revokeAttestation(attestation)` 除非 `msg.sender` 是该证明的签发者，否则 MUST 回滚。它把该证明 id 标为已撤销，发出 `AttestationRevoked(attestationId, issuer)`，并把由它铸造的凭证（若存在且为 active 或 expired）设为 revoked。兑现前被撤销的证明永远不能兑现。撤销不销毁凭证：持有人保留一个可见的、已撤销的代币，可以自行放弃。对合约签发者，该调用由合约本身发出。

#### 5.6 重新签发

`replaces` = `t` 的证明只有在代币 `t` 存在、是 attested、`issuer` 相同、且既非 superseded 也非 revoked 时才能兑现。已到期的凭证可以重新签发；签发者正是这样续期。兑现后按 §3.8 重新绑定。替代品的接收者 MAY 与旧持有人不同：签发者正是通过重新签发，把凭证移到持有人的新私钥上。重新签发没有延迟、也不能否决：签发者本来就决定其凭证的含义（见安全考虑）。

#### 5.7 签发者身份

attested 凭证的签发者是一个地址。本 TAP 不确立是谁控制它。签发者的名称只以元数据中自报的 `issuerName` 出现（§9），并按 §10.3 展示。

### 6. claimed 凭证

`claim(file, statementId, evidence, subject)` 向 `msg.sender` 铸造一个 claimed 凭证，其 `issuer` 为 `msg.sender`，制品为 `file` 的网表哈希，`scope` 为 `statementId` 的声称范围：

```
claimScope(statementId) = 0x00…00                                                        若 statementId = 0
                        = SHA-256(ASCII("tap-credential-claim/1") ‖ 0x00 ‖ statementId)   否则
```

除非 `file` 是不超过 49,152 字节的有效 `tapnet/1` 文件、`subject` 为 0 或 1，否则 MUST 回滚；它会存储该文件。对声明 id 取哈希，使 claimed 凭证的范围与规格 id 和证明范围相互隔离，持有人无法让自己的声称与某个 proven 或 attested 凭证共用同一个范围值。

一次声称 MAY 把一条 Design Credits 声明（`TAP-draft-design-credits` §4）落到链上：此时 `statementId` 是该声明的 id，元数据携带该声明（§9）。凭证合约不核验该声明。展示该声明的工具 MUST 按 `TAP-draft-design-credits` §4.6 核验它，并且只有在以下各项全部成立时，MAY 把它显示为持有人关于该制品的声明：

1. 其签名者对应持有人：`signer` 等于持有人，且 `signerChainId` 为 0（私钥签名）或凭证合约所在链的 chain id（同一条链上、持有人地址处的合约账户）；
2. 其 `subject` 按 `TAP-draft-design-credits` §3.3 适用于该制品：非零的 `netlistHash` 等于制品，非零的 `structuralHash` 等于制品文件的结构哈希；
3. 结合工具所知的每一条 Revocation 判断，它未按 `TAP-draft-design-credits` §4.7 被撤销。

否则，工具 MUST 把声明的签名者与持有人并排显示，并把该声明标为"不符"（第 1 或第 2 项）或"已撤销"（第 3 项），并且 MUST NOT 把它表述为支持该凭证。工具每次展示该声明时 MUST 重新检查撤销情况，使声称之后才被撤销的声明显示为已撤销；凭证本身的状态不变，因为声称始终只是声称（持有人可以放弃它）。MUST NOT 把合约显示为已核验该声明；claimed 凭证只是持有人的声称，仅此而已，即便其制品也出现在某个 proven 凭证中。

### 7. 智能体凭证

主体为 `agent` 的凭证表示其持有人地址是某个软件智能体的运营账户；其类别与其他凭证一样，说明是谁决定它应得。智能体能力凭证可以是 proven（例如智能体账户通过了某个规格），也可以是 attested（运营方或评测方为某个智能体担保）。

1. 持有人 MUST 是智能体的运营账户（外部账户或合约），该账户按 §3.6 亲自发出承诺或兑现交易以表示同意。
2. 凭证绑定在该账户上，而不是任何可转移的身份代币上。可以易手的注册条目（例如 ERC-8004 智能体身份）MUST NOT 作为持有人。
3. 元数据 MAY 在 `agent`（§9）中以 `eip155:<chainId>:<注册表地址>` 加十进制 `agentId` 的形式指明一个智能体身份。该链接是元数据制作者的陈述。展示它的工具 SHOULD 在一个较新的区块上、以该注册表提供的方式，检查注册表是否把 `agentId` 关联到持有人地址；若不是，或工具无法检查，MUST 把该链接标为"未确认"。ERC-8004 是 Draft，其接口可能改变；本 TAP 不依赖它的任何函数（见原理）。

### 8. 接口

#### 8.1 `ITapCredential`

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapCredential {
    struct Credential {
        uint8 kind;          // 1 proven, 2 attested, 3 claimed
        uint8 subject;       // 0 account, 1 agent
        address issuer;
        bytes32 scope;
        bytes32 artifact;    // netlist hash
        bytes32 evidence;
        uint64 issuedAt;
        uint64 expiresAt;
        uint256 replaces;
    }

    function credentialOf(uint256 tokenId) external view returns (Credential memory);
    function statusOf(uint256 tokenId) external view returns (uint8);   // §3.5
    function credentialsOf(address holder, uint8 kind, address issuer, bytes32 scope, bool activeOnly,
        uint256 cursor, uint256 limit) external view returns (uint256[] memory tokenIds, uint256 nextCursor);
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);
    function renounce(uint256 tokenId) external;

    event CredentialIssued(uint256 indexed tokenId, address indexed holder, uint8 indexed kind,
        uint8 subject, address issuer, bytes32 scope, bytes32 artifact);
    event CredentialStatusChanged(uint256 indexed tokenId, uint8 status);
    event CredentialRebound(uint256 indexed oldTokenId, uint256 indexed newTokenId);
}
```

1. `credentialOf` 和 `netlistHashOf` 对不存在的代币回滚；`netlistHashOf` 返回记录中的 `artifact`。`statusOf` 从不回滚。
2. `credentialsOf` 是中立查询。除非 `kind` 为 1、2 或 3 且 `limit` 至少为 1，否则它 MUST 回滚：一次查询总是只读一个类别，使不同类别的凭证永远不会作为同一个列表被返回、计数或比较。它按铸造顺序返回 `holder` 当前持有的、该类别下与其余每个给定过滤条件都匹配的凭证：`issuer`（零 = 任意）、`scope`（零 = 任意），以及若 `activeOnly` 则要求在当前区块为 active。它至多返回 `limit` 个 id。列表完整时 `nextCursor` 为零；否则把它作为 `cursor` 传入即可继续列出。游标值除此之外不透明。该函数只返回事实，MUST NOT 对凭证加权、打分或排序。
3. `storeNetlist` 接受任何调用者提交的、不超过 49,152 字节的任何有效 `tapnet/1` 文件，存储它并返回其网表哈希；`netlistFile` 返回已存储的文件，对未知哈希回滚。已存储的文件不说明任何凭证的任何事情。
4. 每次铸造都在 ERC-721 `Transfer` 和 ERC-5192 `Locked` 之后发出 `CredentialIssued`。

#### 8.2 `ITapCredentialProven`

```solidity
interface ITapCredentialProven {
    struct Spec {
        address registrant; uint32 nIn; uint32 nOut; bytes32 target; uint32 maxGates; bool unique;
        bytes32 series; uint64 commitStart; uint64 commitEnd; uint64 revealEnd; address recoveryAuthority;
        bytes32 infoHash;
    }
    struct Rebind { address authority; uint256 oldTokenId; address newHolder; uint64 deadline; bytes32 nonce; }

    function registerSpec(Spec calldata spec) external returns (bytes32 specId);
    function specOf(bytes32 specId) external view
        returns (Spec memory spec, uint256 maxGateWork, uint256 maxTableBytes);
    function checkBounds() external view returns (uint256 maxGateWork, uint256 maxTableBytes);
    function commit(bytes32 specId, bytes32 commitment) external;
    function reveal(bytes32 specId, address recipient, uint8 subject, bytes calldata file, bytes32 salt)
        external returns (uint256 tokenId);
    function requestRebind(Rebind calldata request, bytes calldata signature) external returns (uint64 readyAt);
    function vetoRebind(uint256 oldTokenId) external;
    function completeRebind(uint256 oldTokenId) external returns (uint256 tokenId);

    event SpecRegistered(bytes32 indexed specId, address indexed registrant);
    event Committed(bytes32 indexed specId, address indexed committer, bytes32 commitment);
    event Accepted(uint256 indexed tokenId, bytes32 indexed specId, address indexed recipient,
        bytes32 netlistHash, bytes32 designKey);
    event RebindRequested(uint256 indexed oldTokenId, address indexed newHolder, uint64 readyAt);
    event RebindVetoed(uint256 indexed oldTokenId);
}
```

`specOf` 对未知 id 回滚；它连同规格一起返回合约登记该规格时所依据的上限。`checkBounds` 在任何登记之前就返回同样的上限，使工具能预先判断某个规格是否会被接受。这两个数字的含义由合约自己定义，MUST 随合约一并公布（§4.4 第 2 项）；参考实现按那里给出的公式返回 65,536 和 131,072。

#### 8.3 `ITapCredentialAttested`

```solidity
interface ITapCredentialAttested {
    struct Attestation {
        address issuer; address recipient; uint8 subject; bytes32 scope; bytes32 artifact; bytes32 evidence;
        uint64 issuedAt; uint64 expiresAt; uint64 deadline; uint256 replaces; bytes32 nonce;
    }

    function redeem(Attestation calldata attestation, bytes calldata signature) external returns (uint256 tokenId);
    function revokeAttestation(Attestation calldata attestation) external;
    function attestationStatus(bytes32 attestationId) external view returns (uint8 state, uint256 tokenId);

    event AttestationRevoked(bytes32 indexed attestationId, address indexed issuer);
}
```

`attestationStatus` 返回 `state` 0（未知）、1（已兑现）或 2（已撤销），以及由该证明铸造的代币或零。

#### 8.4 `ITapCredentialClaimed`

```solidity
interface ITapCredentialClaimed {
    function claim(bytes calldata file, bytes32 statementId, bytes32 evidence, uint8 subject)
        external returns (uint256 tokenId);
}
```

#### 8.5 标识符

合约通过 ERC-165 恰好报告它所实现的接口。标识符、函数选择器和事件主题列在 `vectors.json`（`interfaces` 部分）中：

| 接口 | ERC-165 id |
|---|---|
| `ITapCredential` | `0x5558759c` |
| `ITapCredentialProven` | `0x07aaf2dc` |
| `ITapCredentialAttested` | `0x7587c9da` |
| `ITapCredentialClaimed` | `0x11e35684` |
| ERC-5192 | `0xb45a3c0e` |

`netlistHashOf(uint256)`、`netlistFile(bytes32)` 和 `storeNetlist(bytes)` 与 TAP-721 `ITapNetlistNFT` 中的同名函数选择器相同，但 `storeNetlist` 的规则不同（见安全考虑）。回滚数据不属于这些接口。

### 9. 元数据

凭证的元数据遵循 `TAP-draft-netlist-bound-nft` §7（§3.2），其 `tap` 对象 MUST 包含成员 `credential`：

| 成员 | 必需 | 类型 | 内容 |
|---|---|---|---|
| `v` | 是 | number | `1` |
| `kind` | 是 | string | `"proven"`、`"attested"` 或 `"claimed"` |
| `subject` | 是 | string | `"account"` 或 `"agent"` |
| `contract` | 是 | object | `chainId`（number）和 `address`（小写）：凭证合约，即状态来源（§3.5）。MUST 与 `tap.id` 一致 |
| `issuer` | 是 | string | 记录中的 `issuer` |
| `scope` | 是 | string | 记录中的 `scope` |
| `issuedAt`、`expiresAt` | 是 | number | 记录中的值 |
| `replaces` | 非零时 | string | 记录中的 `replaces`，十进制 |
| `evidence` | 记录中 `evidence` 非零时 | object | `sha256`（等于记录中的值）、`uris` |
| `spec` | proven：必需；其他类别：不得出现 | object | `id`（= `scope`）、`nIn`、`nOut`、`target`、`maxGates`、`unique`、`series`；可选 `info`：`sha256`（= `infoHash`）、`uris` |
| `scopeLabel` | attested：可选；其他类别：不得出现 | string | 至多 256 字节；其范围哈希（§5.2）MUST 等于 `scope` |
| `issuerName` | attested：可选；其他类别：不得出现 | string | 至多 64 字节；由制作者自报（§10.3） |
| `statement` | claimed：可选；其他类别：不得出现 | object | `id`（Design Credits 声明 id；`claimScope(id)`（§6）MUST 等于 `scope`）和该声明信封的 `uris` |
| `cohort` | 可选 | string | 批次名称，例如某轮比赛或某个年份，至多 64 字节，由元数据制作者选定；仅用于显示（§10.1 第 6 项） |
| `agent` | 主体为 agent：可选；否则不得出现 | object | `registry`（`eip155:<chainId>:<address>`）和 `agentId`（十进制字符串）（§7） |

文本成员是 Unicode 规范化形式 C 的 UTF-8，MUST NOT 包含控制字符（U+0000–U+001F、U+007F–U+009F）或任何在 Unicode 15.1.0 中具有 `Default_Ignorable_Code_Point` 或 `Bidi_Control` 属性的码位（即 `TAP-draft-design-credits` 中 `displayName` 的规则，在此复述）。哈希为 `0x` 加 64 个小写十六进制数字；数字为 0 到 2^53 − 1 之间的 JSON 整数。

1. 凭证记录中的每个值 MUST 等于 `credentialOf` 返回的记录；两者不一致时以记录为准。某类别标为"不得出现"的成员一旦出现，该类别的元数据即无效；`tap.edition` 出现时亦然（§3.2）。
2. 状态 MUST NOT 出现在元数据中：`credential` 中名为 `status`、`revoked`、`expired` 或 `superseded` 的成员使元数据无效。在文档的任何位置，包括 ERC-721 `attributes`（按 `trait_type`）和嵌套对象中，名称或含义为 §2 第 3 项所禁止的成员或属性都使元数据无效；诸如 `value`、`price`、`yield`、`share`、`allocation`、`airdrop`、`reward`、`points`、`weight`、`tier`、`multiplier`、`bonus`、`payout`、`eligibility` 或 `entitlement` 这样的名称（任何语言或拼写）只是例子，而非完整清单。ERC-721 属性条目中的 `value` 成员是该格式的一部分，按其 `trait_type` 判断。`tap.pod` 成员（`TAP-draft-pod-attributes`）不受此限：其中的名称，例如 `bonus`、`multiplier` 和 `verifWeight`，描述的是挖矿合约的记账，并适用该 TAP 的不赋权规则（其 §7）。豁免只覆盖 `tap.pod` 成员：重复其事实的 ERC-721 属性与其他属性一样判断。本项适用于文档的其余所有部分。
3. 对 proven 凭证，`tap.netlist.latch` MUST 为 0，`tap.netlist.nand` 不超过 `spec.maxGates`，并且 SHOULD 提供 `tap.netlist.structuralHash`。
4. 工具 MUST 忽略不认识的成员，但 MUST 拒绝第 2 项判为无效的元数据，并按含义判断名称，而不只看所列的例子；对文字（例如 `description`）陈述或暗示了 §2 第 3 项所禁止内容的元数据，工具也 MUST 拒绝。机器检查（包括参考检查和向量）只覆盖成员名称；文字由工具判断（见测试用例）。

示例（仅供参考；`vectors.json` 场景中的 proven 凭证，URI 已缩短）：

```json
{
  "v": 1, "kind": "proven", "subject": "account",
  "contract": {"chainId": 31337, "address": "0x00000000000000000000000000000000000000c1"},
  "issuer": "0x243d1e8bc2c6aee4bf41136cb139010bb6a20f08",
  "scope": "0xe56510eca6a8ec58dabdec3ed6b77cc1bcbd8cf99f6fa60edab6a8bb1b092b4f",
  "issuedAt": 2000, "expiresAt": 0,
  "spec": {"id": "0xe56510eca6a8ec58dabdec3ed6b77cc1bcbd8cf99f6fa60edab6a8bb1b092b4f",
           "nIn": 2, "nOut": 1, "target": "0xd33c6800252db2f67a985dbb4a7d7a68c0babd8b03d2f95bfea65d836990dd2e",
           "maxGates": 4, "unique": true, "series": "0x…", "info": {"sha256": "0x…", "uris": ["https://…"]}}
}
```

### 10. 展示规则

以下规则适用于每个展示凭证或向他人报告凭证的工具。

#### 10.1 所有凭证

1. 工具 MUST 用 §10.2–§10.4 的标签（或其语言中的同义表述）显示每个凭证的类别，连同凭证合约所在的链和地址，并且 MUST NOT 以使不同类别看起来相似的样式展示它们。
2. 工具 MUST 在一个较新的区块上从合约读取状态，并 MUST 显示 active 以外的任何状态。它 MUST NOT 把 revoked、superseded 或 expired 的凭证显示为 active，并 SHOULD 把 superseded 凭证链接到其替代品，把替代品链接到它所替换的代币。它 SHOULD 向旧代币的持有人显示待处理的 proven 重新绑定（§4.7）。
3. 工具 MUST NOT 把凭证或凭证数量表述为获得任何支付或配额的资格（§2），并且 MUST NOT 把不同类别的凭证相加或排名。
4. 工具 MUST NOT 仅因合约这样报告就认定其类别属实。它 SHOULD 只对已核验其运行时代码实现了本 TAP 的合约（例如与参考实现的已知构建比对）使用 §10.2 的标签，否则 MUST 加注"未核验的合约"。
5. 工具显示 TAP-721 符合性级别（`TAP-draft-netlist-bound-nft` §7.4）时，按 TAP-721 §8.1 的要求，对每个凭证 MUST 显示"L0（仅元数据）"；除非已通过第 4 项的代码核验确认合约在铸造时固定 `tokenURI`（§3.2），否则 MUST 加注"元数据可能改变"；`tokenURI` 固定不是 TAP-721 §7.2 意义上的冻结，也不改变级别。在核对 `netlistHashOf(tokenId)` 等于 `tap.netlist.sha256` 之后，MAY 在旁边加上"制品由凭证合约记录"。它 MUST NOT 把凭证显示为 L1，或显示为 TAP-721 §7.4 意义上的"已在链上核验"。工具 MUST 通过 ERC-165 判断合约是否实现 `ITapNetlistNFT`，而不能凭是否存在具有其选择器的函数来判断（§8.5），并且 MUST 通过 `netlistHashOf` 读取凭证的制品，而不能从已存储文件的集合中读取。
6. `cohort` 由元数据制作者选定。工具 MAY 把它作为标签显示，MUST NOT 把它表述为任何组织者、比赛或基金会的背书，也 MUST NOT 把它做成类别标签的一部分。

#### 10.2 proven

1. 工具 MUST 获取制品文件、核对其哈希，并对照 `specOf(scope)` 重新计算 §4.6 第 4–6 项的检查，之后才能标为"已证明：通过其规格"。未这样做的工具 MUST 标为"据合约已证明（未复查）"。
2. 工具 MUST 把规格的登记者显示为定义该规格的账户，MUST 显示 `maxGates`，并 SHOULD 显示 `infoHash` 所固定的描述。
3. 工具 MUST NOT 把 proven 凭证描述为证明了谁设计了该网表：接收者只是揭示了一个通过检查的文件。系列未设 `unique` 时，许多持有人可以为同一设计持有凭证。
4. 工具 MUST NOT 把 `unique` 规格的凭证描述为证明了设计是原创的（§4.6）。

#### 10.3 attested

1. 标签 MUST 说明凭证是被担保的以及由谁担保：签发者地址（完整显示或一步可见），例如"由 0x12…ab 担保（签发者身份未核验）"。
2. `issuerName` 和 `scopeLabel` MAY 只对 attested 凭证显示，只显示在签发者地址旁边并标为自报；工具 MUST NOT 用名称替代地址或给名称加核验标记，除非工具自己用其说明的方法确立了这一关联。
3. `expiresAt` 非零时，工具 SHOULD 显示它。

#### 10.4 claimed

标签 MUST 为"自称"（或工具语言中的同义表述）。工具 MUST NOT 以 proven 或 attested 的样式展示 claimed 凭证，对其携带的任何声明遵循 §6，并按 `TAP-draft-design-credits` §6.2 展示该声明。

#### 10.5 智能体与个人数据

1. 工具 MUST 显示主体 `agent`，并对任何智能体身份链接遵循 §7 第 3 项。
2. 凭证是公开且永久的。工具 SHOULD 为持有人提供在日常展示中隐藏已放弃和已撤销凭证的视图，并 SHOULD 停止显示已放弃凭证的 `issuerName`、`scopeLabel` 和证据文档。

## 原理

**ERC-721 加 ERC-5192，而不是 ERC-4973。** ERC-4973（账户绑定代币，仍在 Review）要求代币不报告 ERC-721 接口；TAP-721 代币是 ERC-721 代币，两者无法结合。ERC-5192 已 Final，只在 ERC-721 上增加一个函数和两个事件，钱包已能识别。同意模型借鉴了 ERC-4973"接收账户必须同意"的思路，这里通过要求接收者亲自发送交易来实现（§3.6）。

**不要求 ERC-5484。** ERC-5484 增加一个在签发时固定的销毁授权值。本 TAP 下，所有类别都只有持有人能销毁（§3.7），签发者以状态撤销而不是销毁，从而保留可见的记录。合约可以对每个代币以 `OwnerOnly` 实现 ERC-5484 而不冲突；强制要求它只会增加接口而不增加信息（见待决问题）。

**用状态代替签发者销毁。** 销毁已撤销的凭证会抹去"曾签发、后撤销"这一读者可能需要的事实；状态标志两者都保留。到期由区块时间计算，凭证到期无需任何人发交易。由于状态从合约读取、元数据永不改变，合约不发出任何 ERC-4906 事件：`MetadataUpdate` 宣告的将是一个不可能发生的变化。

**以接收者发出的交易作为同意。** 基于签名的同意方案可以免 gas 签发，但需要多一种签名类型，而且垃圾凭证问题就变成了中继者的策略问题。要求接收者亲自发送承诺、兑现、声称或重新绑定交易，从构造上杜绝了不请自来的凭证，并且适用于合约账户和智能体。中继路径可以以后再加（见待决问题）。

**类别由签发路径固定。** 合约只通过 §4 铸造 proven 凭证、只通过 §5 铸造 attested 凭证，所以记录中的类别描述的是代币如何被铸造，而不是某人对它的说法。工具仍可能被一个只是假装遵循本 TAP 的合约欺骗，因此 §10.1 第 4 项把标签与经核验的合约代码绑定，§10.2 要求工具自己重跑检查。

**以真值表哈希做穷举检查。** 比较完整真值表的哈希，让登记者无需公开实现就能承诺一个函数，也让每个钱包用同样几行代码就能复查凭证。列布局采用最高有效位在前，使合约能在每个 256 位字中求值 256 个输入向量：每个门每个字一次 NAND。

**第 1 版只做穷举。** proven 凭证应当意味着合约检查了整个命题。较早的乐观模式除非有人针对公开参考网表找到反例，否则就接受网表；参考网表因此泄露了答案，驳倒可能在接受之后任何时候到来，而且对允许的最大文件做单拍求值放不进一笔交易。把第 1 版限制在合约能完整检查的范围内，使"已证明"成为代币在铸造时就具有的性质，并把更大的电路留给为之设计的方案（§4.8）。

**两个经实测的工作量上限。** 一次揭示的成本由三部分组成：在每个 256 路字上求值每个门（每单位约 150 gas）；与 `nIn` 无关的每门开销（文件检查、设计键以及把文件存为合约代码，合计每门约 3,000 gas，由 `+ 20` 计入）；以及写入并哈希真值表缓冲区（每字节约 8 gas）。像较早草案那样只限制 `max(1, 2^nIn/256) · maxGates`，会接受输出成千上万、仅缓冲区就需要数兆字节内存的规格，也会接受输入很少但门很多、每门开销超出一笔交易的规格。采用 §4.4 第 2 项的两个上限后，参考合约所允许的每个角落情形，揭示的执行 gas 都不超过 1180 万（用 Foundry 测量，`SoulboundGas.t.sol`，每个规格各在自己的 `unique` 系列中，因此计入了 §4.6 的设计键记录）：16 输入、16 输出、237 门：11,781,572 gas；14 输入、64 输出、780 门：11,137,269；9 输入、2,048 输出、2,978 门：11,087,930；8 输入、3,120 输出、3,120 门：10,976,589。calldata 至多再增加约 240,000 gas，所以每次揭示都能宽裕地放进 EIP-7825 的 16,777,216 gas 交易上限。用 `storeNetlist` 存储一个达到上限 49,152 字节的有效文件（三个代码分块）花费 12,516,900 gas，声称它花费 12,680,600。上限要公布（`checkBounds`、`specOf`），因为工具应当在登记之前就知道规格是否会被接受。

**承诺中包含接收者，且按承诺者分别记录。** 先承诺后揭示，可以阻止任何人抄袭在内存池或本轮更早的揭示中看到的答案。把接收者和主体放进承诺，并且只接受由该接收者记录的承诺所对应的揭示，意味着已揭示的承诺不能被他人冒领，而任何人都可以代付揭示的 gas。较早的草案对每个承诺只记录一次，记在最先发出它的人名下，于是抄袭一笔待上链的承诺交易就能把原发送者挡在本轮之外；按承诺者分别记录使这种抄袭无害。

**用设计键代替链上结构哈希。** 结构哈希需要活性分析、合并、按深度排序和规范文件，在链上代价高昂。对组合文件，输出的有序标签已经决定了合并后的结构：`TAP-draft-netlist-structural-hash` §4.2 的结构标签是该标签整个输入锥的哈希，所以两个文件输出标签相等，恰好当它们合并后的结构在输入、输出顺序相同的前提下同构，这正是结构哈希相等的刻画（见该文 §8）。`test_soulbound.py` 在随机文件及其随机重编号上检查这一等价性。改名复制、交换输入、死门和重复门都会被拒绝；双重取反这类保持功能的改写则不会，紧的 `maxGates` 可以加以限制。

**只跨轮次查重。** 对小函数，许多人会各自找到相同的网表；Design Credits 草案记录了 BNB Smart Chain 上 132 个完全相同的四门异或电路。同一轮内，每个提交都在任何提交被揭示之前就已承诺，所以相同的设计要么是独立得出，要么是链下共享，合约无法区分。跨轮次时，早先的答案已经公开，接受它的改名复制品就是奖励阅读而非设计。因此 `unique` 是规格和系列的属性，而不是类别的属性。系列中的每次揭示都记录其设计键，所以 `unique` 轮次也会拒绝往届非 `unique` 轮次的答案。加上轮次互不重叠，这条规则只取决于下一轮开始之前已经公开的内容。

**每个账户每个规格一个凭证。** 没有这条规则，一个账户可以通过提交变体、或者让其他账户的凭证重新绑定到自己名下，为同一任务收集许多凭证，从而抬高任何基于凭证的计数。因此这条规则也约束重新绑定（§4.7）。

**证明绑定到一个合约。** Design Credits 声明与链无关，因为它们只用于展示。证明要由合约兑现为代币，所以域中包含 chain id 和合约，杜绝在别处重放。签发者写在消息内，理由与 Design Credits 把签名者写进去相同：对一个账户的 ERC-1271 批准不能被拿去冒充同一所有者的另一个账户。记录证明中的 `issuedAt`，是因为那是签发者所签署的内容；兑现不能早于它。

**私钥签名先于 ERC-1271。** 在 EIP-7702 下，外部账户可以带有委托代码。若先询问这类账户的代码，就等于让委托决定账户自己的私钥签名算不算数；先恢复私钥，能保持私钥签名有效，只有当签名不是该地址的私钥签名时才询问代码。接受 `v` ∈ {0, 1, 27, 28} 与 Design Credits 一致，使同一个签名工具可以同时服务两者。

**用重新绑定代替转移或社交恢复。** 转移函数即使加以限制，也会让凭证可被出售。由持有人自选的恢复账户同样可被出售。由本来就决定凭证含义的一方（签发者，或在任何人承诺之前就写进规格的恢复授权方）重新签发，保持了该类别的信任模型，并留下可见的链接。对 proven 凭证，授权方并不决定何为通过，所以其权力受到一段延迟的限制，期间旧私钥可以否决；真正丢失私钥的持有人无法否决，而私钥仍然可用的持有人可以阻止自己没有请求的重新绑定。请求若在就绪后一段延迟之内未完成即告失效，较新的签名请求会替换较旧的，所以无人完成的错误请求不能永久阻塞恢复，而每个能够被完成的请求都已给旧私钥留出完整的一段延迟来否决。

**每次查询一个类别。** 如果一次查询把 proven、attested 和 claimed 凭证作为同一个列表返回，就会诱使读者把它们当作等同来计数，而这正是本 TAP 要防止的混淆。要求 `credentialsOf` 指定类别，并把 claimed 的范围哈希得与规格 id 隔离，意味着没有任何一次调用会把自称的代币返回在 proven 代币的位置上。

**把智能体当作账户。** 把智能体凭证绑定到 ERC-8004 身份，会使它在该身份代币转移时跟着转移；ERC-8004 草案正是因为控制权改变而在转移时清除智能体钱包。绑定到运营账户、并把注册表链接当作需检查的提示，可以保持凭证的灵魂绑定。由于 ERC-8004 是 Draft，§7 不点名它的任何函数。

**中立查询，不涉支付。** 一个通用查询使读者不必为每个合约各自实现。权重属于政策，归采用它的一方；把它排除在标准之外，使持不同立场的读者都能使用本标准，也使凭证本身不带任何承诺。

**Standards 类型。** 本 TAP 定义带 ERC-165 标识符的合约接口、独立合约和钱包必须一致计算的哈希，以及工具规则；按 TAP-01 §3 属于 Standards TAP。

**依赖。** TAP-02 定义真值表和设计键所求值的网表语义（§4.1–§4.3）。`TAP-draft-netlist-bound-nft` 定义 `tapnet/1`、网表哈希和本 TAP 所扩展的元数据。`TAP-draft-design-credits` 定义 claimed 凭证可以携带的声明、其核验与撤销（§6）以及其展示（§10.4）。ERC-721、ERC-165 和 ERC-5192 定义代币；EIP-712 定义证明的编码；ERC-1271 定义合约签发者和授权方。`TAP-draft-netlist-structural-hash`、`TAP-draft-pod-attributes`、`TAP-draft-large-netlists`、EIP-7702、EIP-7825 和 ERC-8004 只为比较、一项豁免和测量而引用；任何必需内容都不依赖它们：结构哈希草案的标签函数已在 §4.3 中复述，Design Credits 草案的字符规则已在 §9 中复述。

## 向后兼容

本 TAP 增加一种新的合约和一个 TAP-721 元数据成员；不改变任何现有合约。了解 ERC-721 的钱包把凭证显示为 NFT；了解 ERC-5192 的钱包把它们显示为灵魂绑定。

凭证在铸造时绑定网表，所以它们在 TAP-721 中符合 L0，并通过自己的接口公开网表哈希（§3.2）。对 TAP-721 的一项尚未合并的修订提案为这类合约增加了一条符合性路径：`TAP-draft-netlist-bound-nft` §8.2 的铸造即绑定配置（"铸造即绑定的集合"），按此配置，在代币铸造时一次性记录其网表哈希且永不修改的合约，可以在没有清单的情况下实现 `ITapNetlistNFT`。凭证合约不使用它：该配置属于 L1，L1 要求 ERC-4906，而 §3.2 禁止凭证使用 ERC-4906（待决问题 1）。本草案引用该节，不重述其内容。

同一修订提案还在 TAP-721 §6.4 中规定：没有清单的集合不构成版次，其元数据不得包含 `tap.edition`，§3.2 已对凭证提出同样的要求；它还把 `tap.credential` 列入其他草案使用的 `tap` 成员。

本草案依赖 TAP-721（`TAP-draft-netlist-bound-nft`），并在其之后提交。TAP-721 是核心草案申请的编号；若编辑分配了其它编号，本草案即采用该编号：本文中对 `TAP-draft-netlist-bound-nft` 和"TAP-721"的所有引用（包括 `requires` 字段）都替换为该编号。

## 测试用例

`assets/tap-draft-soulbound-credentials/vectors.json`（格式 `tap-soulbound-credentials-vectors/1`）由同一目录下的 `make_vectors.py` 生成，可逐字节复现；其 SHA-256 为 `f33709c7e436ba68d89df9adb60f3251172397d82800ab2a0b2592a8f2a64e9b`。其中的私钥为 `keccak256("tap-soulbound test key <n>")`，标为 `testOnly`，绝不能用于其他任何用途。向量的 EIP-712 域使用 chain id 31337 和合约 `0x00000000000000000000000000000000000000c1`。各部分：

- `interfaces`：§8.5 的 ERC-165 标识符、每个函数选择器和每个事件主题；
- `eip712`：域、域分隔符 `0x755b328ff65f3428bb3f6e2e59f1e83ad5ac34b67e98e431204365d3c1392b92`，以及 §5.1 的 encodeType 字符串和类型哈希；
- `files`：十个网表文件（异或及其重编号、交换输入、死门和双重取反变体，与门，半加器，16 输入奇偶校验，8 位加法器，以及 24 输入奇偶校验），附度量、网表哈希、设计键、结构哈希，以及输入不超过 16 个时的真值表哈希；
- `truthTables`：由函数计算的哈希，以及三个小真值表的精确字节（§4.2 的位序）；
- `designKeyPairs`：每一对引脚相同的文件，表明设计键相等与结构哈希相等一致；
- `specs`、`bounds`、`specChecks`：规格及其字节和 id；§4.4 第 2 项的参考上限及算例；以及违反每条登记规则的规格，包括两个工作量上限；
- `commitments`、`submissions`：承诺和内容检查（接受、门数过多、函数错误、引脚不符）；
- `attestations`、`rebind`、`rebindToHolder`、`rebindVetoed`、`rebindLapsed`、`rebindReplacement`、`rebindReplacement2`：签名的证明（账户、智能体、重新签发、错误签名者、一个高 s 变体和一个 `v` ∈ {0, 1} 变体）以及六条签名的 `Rebind` 消息；
- `claimStatements`：一个声称范围（§6），以及由声称携带的 Design Credits 声明及其应得的展示（一致、不符、已撤销）；
- `scenario`：在可执行模型上执行的一串登记、承诺（包括一个已不再妨碍其原主的抄袭承诺）、揭示、重新绑定请求、否决与完成（包括一个失效的请求、一个被替换的请求和一个重新开始计算延迟的替换请求）、声称、兑现、撤销和放弃，附每个预期错误、代币 1–7 在两个时刻的最终状态，以及 `credentialsOf` 查询，包括被拒绝的未指定类别的查询，以及游标跨过已放弃代币的分页；
- `metadata`：有效和无效的 `tap.credential` 成员及文档，附预期错误，包括出现在 `credential` 之外和 ERC-721 属性中的禁用名称、`tap.edition`、含挖矿名称的 `tap.pod` 成员（豁免，有效）及在 ERC-721 属性中重复的同一名称（不豁免）、`cohort`，以及一份 `description` 许诺奖励的文档：机器检查接受它，它带有一条注记，说明工具必须拒绝它（工具判断：机器检查只覆盖名称）；
- `differential`：74 个随机组合文件（第二轮审阅的生成器，种子 2026），着重覆盖不超过 9 个输入且输出很多的情形、12、15 和 16 个输入，以及每个门都是输出的文件，每个都附设计键和真值表哈希。

Foundry 测试针对 Solidity 参考实现重放静态向量和整个场景，把其真值表哈希和设计键与 `differential` 部分比对，测量工作量上限每个角落情形的揭示 gas，并把两轮审阅的攻击测试作为回归测试纳入，这些攻击必须失败。

## 参考实现

在本仓库中，位于 `assets/tap-draft-soulbound-credentials/`：

- `assets/tap-draft-soulbound-credentials/soulbound.py`（MIT，Python 3.9+，仅标准库）：按位切片求值的真值表、设计键、规格 id 与工作量上限、承诺、提交检查、声称范围与声称所携带的 Design Credits 声明的展示、EIP-712 类型与签名检查、元数据检查、展示标签、接口标识符，以及参考合约的可执行模型；`make_vectors.py` 写出 `vectors.json`；`test_soulbound.py` 检查向量、在随机文件上检查设计键与结构哈希的等价性、按位切片求值与 TAP-02 求值的一致性、按承诺者记录承诺、系列对设计键的记录、失效与被替换的重新绑定请求、放弃之后的游标以及 attested 凭证的累积，并在已安装时用 `eth_account` 交叉检查签名、用 Foundry `cast` 交叉检查选择器。`canon.py`、`tapnft.py`、`tap02_reference.py` 和 `credits.py` 从 TAP-721 系列和 Design Credits 草案原样复制（来源与 SHA-256 见该目录的 README），使该目录可以独立运行。
- `assets/tap-draft-soulbound-credentials/contracts/src/SoulboundNetlistCredential.sol`（MIT，Solidity 0.8.28）：实现全部四个接口，无所有者、无升级路径、无费用，基础 URI 在部署时固定；文件以合约代码形式存储，与 TAP-721 参考存储相同。`assets/tap-draft-soulbound-credentials/contracts/src/TapCredentialCheck.sol`：按位切片的真值表哈希和设计键。`assets/tap-draft-soulbound-credentials/contracts/test/`：Foundry 测试（读取 `../vectors.json`；forge-std v1.17.0 需另行安装，见该目录的 README），包括场景、差分测试、工作量上限各角落的 gas、ERC-1271 与 EIP-7702 签发者，以及两轮审阅的攻击回归测试。`ERC721Min.sol`、`IERC4906.sol` 和 `TapNetlistCheck.sol` 从 TAP-721 参考合约原样复制；凭证合约重写了 `supportsInterface`，使其不报告 ERC-4906，并且不发出任何 ERC-4906 事件（§3.2）。
- 同一目录（含 `contracts/`）也以固定提交保存在 [BruceLanLan/TAP-721，提交 `a39f30b538e723e918bf9c3bb2998ee95f8e2f1a`](https://github.com/BruceLanLan/TAP-721/tree/a39f30b538e723e918bf9c3bb2998ee95f8e2f1a) 的 `assets/tap-draft-soulbound-credentials/` 下（逐字节相同）。

## 部署

本 TAP 不依赖任何已部署的合约。任何人都可以部署凭证合约；由工具决定识别哪些合约代码（§10.1 第 4 项）。参考合约目前未部署；进入 Review 之前，本节将加入它的一次测试网部署，并附上只读核验其地址、代码哈希与接口标识符的步骤。

## 安全考虑

- **伪造的 proven 标签。** 任何合约都可以返回类别 1。工具把标签与经核验的代码绑定并重跑检查（§10.1、§10.2）；合约未被识别的凭证会如实显示。
- **弱规格。** 登记者可以定义一个平凡的任务或宽松的门数预算，而且任何人都能登记规格。登记者会被显示，`infoHash` 固定描述，由读者决定看重谁的规格。proven 凭证证明的就是规格所说的内容，仅此而已。
- **抢跑承诺。** 承诺在内存池中是公开的。由于按承诺者分别记录（§4.5），抄袭一笔待上链的承诺交易只会为抄袭者记录一个承诺；它既不能阻挡原发送者，也不能为抄袭者揭示，因为接收者写在承诺之内。
- **抢跑揭示。** 揭示在承诺中写明接收者，所以被复制的揭示交易仍铸造给同一接收者。抢跑者最多只是替接收者付了 gas。
- **抄袭。** 承诺-揭示防止轮内抄袭；`unique` 只在同一系列内拒绝对往届答案的改名复制；保持功能的改写可以绕过设计键，只受 `maxGates` 限制（§4.6）。轮次结束前在链下共享的答案无法检测。
- **女巫账户。** 一个人可以控制许多账户，用每个账户各获得一个 proven 凭证，或者给自己担保。灵魂绑定阻止的是交易，而不是复制。
- **签发者私钥泄露。** 被盗的签发者私钥可以签署证明，也可以撤销证明。签发者应使用签名者可以轮换的合约账户；被攻破的 EOA 签发者从被攻破之时起应视为不可信，而工具只能从链下得知这一时间。
- **签发者的重新签发权。** 签发者可以把其任何一个 active 或已到期的 attested 凭证重新签发给兑现新证明的任何账户，立即生效且无法否决（§5.6）。若签发者腐败或私钥被盗，这实际上就是一次转移。这源于 attested 的信任模型：签发者本来就决定其凭证的含义。签发者应公布其重新签发政策，工具应显示指向被替换代币的链接。
- **恢复授权方滥用。** 恢复授权方可以为任何提出请求的账户发起替代请求。授权方在任何承诺之前就写进规格，重新绑定请求在链上可见，私钥仍可用的持有人可以在延迟期内否决（§4.7），未指定授权方的规格没有这条路径。已丢失私钥的持有人无法否决，所以延迟只保护关注自己凭证的持有人；工具应提醒持有人注意待处理的请求（§10.1 第 2 项）。无人完成的请求会失效，新请求会以一段新的延迟替换较旧的请求（§4.7），所以工具应提醒持有人注意每一个新请求，而不只是第一个。
- **合约签发者改变主意。** ERC-1271 批准在兑现时检查；合约签发者事后可以改变它批准哪些摘要，这只影响尚未兑现的证明。撤销是显式的（§5.5）。
- **EIP-7702 账户。** 带有委托代码的账户首先按其私钥签名被接受（§5.3）。按 ERC-1271 批准摘要的委托还可以替该账户签名；那段代码是账户所有者自己选的。
- **与 TAP-721 的选择器重叠。** `netlistHashOf`、`netlistFile` 和 `storeNetlist` 具有 `ITapNetlistNFT` 的选择器。按函数探测而非按 ERC-165 判断的工具，可能把凭证合约误认为 L1 集合，也可能把某个已存储的文件当作某个代币的内容。这里的 `storeNetlist` 接受任何有效文件，而在 TAP-721 下它只接受已知的网表哈希。工具按 ERC-165 判断符合性，并且只通过 `netlistHashOf` 读取凭证的制品（§10.1 第 5 项）。
- **gas 破坏。** 揭示要对网表求值。规格在登记时受上限约束（§4.4 第 2 项），使每次被允许的揭示都能放进一笔交易；文件以 49,152 字节为上限；`storeNetlist` 只存储有效文件，费用由调用者支付。参考实现中的 `inspect` 是供链下调用的便利函数，没有上限。
- **时间戳。** 窗口和重新绑定延迟使用区块时间戳，出块者可以把它挪动几秒；窗口应远长于此。
- **隐私。** 凭证把一个地址与技能、比赛、贡献和智能体永久关联。放弃会销毁代币，但无法抹去历史或已归档的元数据。签发者应把个人数据排除在证据文档和范围标签之外，或只公布其哈希；想要隔离的持有人应使用不同的账户。
- **对凭证的依赖。** 凭证不能证明不同的凭证属于不同的人；基于凭证作出的任何承诺都是作出者自己的承诺。

### 待决问题

1. 凭证合约是否应实现 TAP-721 §8.2 的铸造即绑定配置并报告 `ITapNetlistNFT`（L1）？这需要 ERC-4906（§3.2 目前禁止），以及按该配置定义的 `frozen()`（见向后兼容）。
2. 是否应增加一条中继的、免 gas 的同意路径（由接收者签署的 EIP-712 `Consent`）？
3. 合约是否也应以 `OwnerOnly` 实现 ERC-5484，以照顾读取它的钱包？
4. 以后的版本是否应基于 `TAP-draft-large-netlists` 的争议博弈增加一个时序或大网表接口（§4.8）？
5. 重新绑定延迟是否应作为规格的一个字段，而不是合约的常量？
6. 本 TAP 是否应定义一个已识别凭证合约代码哈希的登记表，还是留给工具？
7. 智能体凭证是否应把智能体注册表链接记录在链上（并在每次读取状态时重新检查），而不是放在元数据中？

## 版权

依 [CC0](../LICENSE) 放弃版权及相关权利。
