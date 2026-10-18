---
tap: TBD
title: Netlist-Bound NFTs
description: An ERC-721 extension that binds each token to a verifiable, REF-free TapeOut netlist and an image, with one identifier, one file format and one reveal procedure on every TapeOut chain.
author: Bruce (@BruceLanLan)
discussions-to: TBD
status: Draft
type: Standards
created: 2026-10-18
requires: TAP-02, TAP-10, ERC-165, ERC-173, ERC-721, ERC-4906, CAIP-19 (ChainAgnostic/CAIPs commit 1a897eede982d3d4eb68982f3798ebb0878c6ef5)
license: CC0-1.0
---

本文是 `TAP-draft-netlist-bound-nft.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。

# TAP-TBD：网表绑定 NFT

## 概要

本 TAP 让一个 NFT 在图片之外，再携带一个真正的 TapeOut 电路：任何人都能下载它、对照链上核验、模拟它，并在任意一条 TapeOut 链上重新流片。

## 摘要

网表绑定 NFT 是一种 ERC-721 代币，其元数据（以及可选地，其合约）把它绑定到一张图片和一份采用本文定义的 `tapnet/1` 格式的网表（不含 REF 记录、带输入数与输出数的 TAP-02 网表）。本 TAP 规定：该格式及其哈希；如何把网表追溯到它所复制的 TapeOut 电路；适用于 TAP-10 各链的全局代币标识符；在揭示前以 Merkle 根承诺图片池与网表池的集合清单（覆盖一个代币区间或一个显式代币集）；用一个随机种子把池条目分配给代币的带密钥置换；以及代币元数据中的 `tap` 成员。与 ERC-721 一样，它有一个强制核心，分两个一致性等级：L0（仅元数据，只能修改 base URI 的现有合约也能达到）与 L1（链上接口 `ITapNetlistNFT`，由集合本身或伴生合约实现）；另有若干扩展：代币集扩展（代币集模式下必需）、伴生合约扩展（每个伴生合约必需）、可选的求值扩展（让合约能运行代币的网表），以及在 TapeOut 容器中托管内容的规则。跨链转移、设计证明（PoD）属性与网表结构哈希是各自独立的 TAP-721 扩展提案。

## 动机

TapeOut 电路本身已经是 ERC-721 代币（TAP-10 §1）：每个处理器合约保存网表，并为每个电路铸造一个代币。这些代币是能干活的工具——矿机、元件、CPU——也被当作工具使用。社区开始要求第二类对象：一种以真实电路为身份的收藏对象，任何一条 TapeOut 链上的钱包、浏览器和游戏都能读取、核验并使用它。

起推动作用的案例是 TapeCode-Test1：X Layer 上一个已有的、10,000 枚代币的 ERC-721 集合，其合约只能修改 base URI。它的创始人希望每枚代币都显示一个头像，并携带一个设计证明矿机的网表，使该集合成为 X Layer 上电路游戏的基础，而不是一个只有图片的集合。它的部分代币由一个永远无法转出它们的地址持有，因此需要服务的代币不是一个连续区间。两篇社区文章（《TapeCode-Test1 NFT 图片及网表上传方案》与《NFT 头像图片与网表合并及跨链读取可行性方案》，均为 2026 年 10 月；仅作背景）提出了做法。它们在思路上一致，但在字段名、哈希定义、网表的核验方式和揭示算法上各不相同。

没有一份统一的文本，钱包、浏览器或游戏就无法用同一种方式读取两个这样的集合，持有人也无法核实一次揭示是否公平。现有标准覆盖了绑定周边的各个部件，但没有覆盖绑定本身：ERC-721 提供所有权与元数据 URI；ERC-4906 通知元数据变更；TAP-02 定义网表及其求值方式；TAP-10 定义链、链上名字以及对 TapeOut 容器中所存文件的核验读取。本 TAP 复用这四者，只补上缺失的部分。

ERC-721 之所以成为 NFT 的共同基础，是因为它是一份每个钱包都实现、后续 ERC 不断扩展的简短文档。本 TAP 希望在 TapeOut 各链上为网表绑定 NFT 扮演同样的角色，因此，作者申请编号 721（提案名称 TAP-721，与 ERC-721 相呼应）；由于 TAP-01 §6.1 原本分配 10 以上最小的空闲编号，这需要编辑同意。本文及其扩展草案为便于阅读称其为“TAP-721”；若编辑分配其它编号，各草案改用该编号。

## 规范

本文中的关键词 "MUST"、"MUST NOT"、"REQUIRED"、"SHALL"、"SHALL NOT"、"SHOULD"、"SHOULD NOT"、"RECOMMENDED"、"NOT RECOMMENDED"、"MAY" 与 "OPTIONAL"，当且仅当以全大写出现时，按 RFC 2119 与 RFC 8174 的描述解释。

**每个 L1 合约 MUST 实现 `ITapNetlistNFT` 与 ERC-165 接口**（以及 ERC-4906），并遵守 §8.2 的规则。无法修改的现有 ERC-721 合约，可以通过伴生合约（§8.3）达到 L1，或者在 L0（§8.1）上符合本 TAP——L0 是面向现有合约的仅元数据一致性路径：L0 集合不实现任何 TAP-721 接口，只需发布遵循 §7 的代币元数据，以及遵循 §5 与 §6 的清单与揭示。在两个等级上，每枚 TAP-721 代币的代币元数据都 MUST 遵循 §7。

核心（§1–§8.2）之后，是同一文档中的各扩展：

- **TAP-721 伴生合约扩展**（§8.3，`ITapCompanion`）：每个伴生合约 REQUIRED；
- **TAP-721 求值扩展**（§8.4，`ITapNetlistEval`）：对 L1 合约为 OPTIONAL；
- **TAP-721 代币集扩展**（§8.5，`ITapNetlistTokenSet`）：清单使用代币集模式（§5.4）的 L1 合约 REQUIRED，区间模式下 OPTIONAL；
- **TAP-721 容器托管与锁定**（§8.6）：为从 TapeOut 容器提供内容的集合给出的 SHOULD 级规则。

### 一致性摘要

本表是下文各节的导读；本表与某节不一致时，以该节为准。

| 部分 | 地位 | 章节 | 接口（ERC-165 标识） |
|---|---|---|---|
| `tapnet/1` 文件、网表哈希 | 核心：所有实现与工具 | §2 | — |
| 来源电路 | 可选声明；一旦声明即适用核验规则 | §3 | — |
| 代币标识符、内容位置 | 核心 | §4 | — |
| 清单、池、Merkle 树 | 对进行揭示或实现 L1 的集合为核心 | §5.1–§5.3 | — |
| 代币集（代币集模式） | 条件性：代币不构成一个连续区间的集合 | §5.4 | — |
| 揭示（主种子、池种子、置换、版次） | 对有清单的集合为核心 | §6 | — |
| 代币元数据（`tap` 成员） | 核心：L0 与 L1 | §7 | — |
| L0 | 一致性等级 | §8.1 | — |
| L1 | 一致性等级 | §8.2 | `ITapNetlistNFT`（`0x282b67f6`）、ERC-165（`0x01ffc9a7`）、ERC-4906（`0x49064906`） |
| TAP-721 伴生合约扩展 | 条件性：为现有 ERC-721 实现 L1 | §8.3 | `ITapCompanion`（`0x12b40a6c`） |
| TAP-721 求值扩展 | 可选 | §8.4 | `ITapNetlistEval`（`0xec7d7e20`） |
| TAP-721 代币集扩展 | 条件性：处于代币集模式的 L1 合约 | §8.5 | `ITapNetlistTokenSet`（`0x3f7177c7`） |
| TAP-721 容器托管与锁定 | 推荐：TapeOut 容器中的内容 | §8.6、§7.5 | — |

### 1. 术语

| 术语 | 含义 |
|---|---|
| 集合 | 其代币被绑定的 ERC-721 合约 |
| 网表绑定 NFT | 遵循本 TAP 的集合中的一枚代币 |
| 网表文件 | 采用 `tapnet/1` 格式（§2）的字节串 |
| 网表哈希 | 网表文件的 SHA-256 |
| 来源电路 | 一个 TapeOut 电路（链、处理器合约、电路编号），网表文件复现的正是它的网表（§3） |
| 容器 | 一个电路的 TapeOut 容器（TAP-10），其站点存储可以存放文件 |
| 清单 | 集合的 JSON 文件，列出集合可分配的每张图片与每份网表（§5） |
| 池 | 清单中的一个有序列表，每枚被覆盖的代币对应一个条目，存放图片哈希、网表哈希或两者 |
| 区间模式、代币集模式 | 清单指明其覆盖代币的两种方式：一个连续的代币编号区间，或一个显式的代币集（§5.4） |
| 序号 | 被覆盖代币的位置：区间模式下为它相对首个代币编号的偏移，代币集模式下为它在代币集中的排名 |
| 主种子 | 决定池条目如何分配给代币的 32 字节随机值（§6） |
| 版次 | 获得同一网表哈希的那些代币（§6.4） |
| 伴生合约 | 为一个现有 ERC-721 合约实现 L1 的独立合约（§8.3） |
| 链表 | TAP-10 §2.1。本 TAP 不自行定义链 |

字节串以带 `0x` 前缀的十六进制书写。`‖` 表示拼接。`u8(x)`、`u32be(x)` 与 `u64be(x)` 分别是 1、4、8 字节的大端无符号整数。`SHA-256` 指 FIPS 180-4。JSON 中的哈希写作 `0x` 加 64 位小写十六进制数字，地址写作 `0x` 加 40 位小写十六进制数字。

### 2. 网表文件（`tapnet/1`）

#### 2.1 布局

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0 | 6 | ASCII `TAPNET`（`0x5441504e4554`） |
| 6 | 1 | 格式版本，`0x01` |
| 7 | 1 | 保留，`0x00` |
| 8 | 4 | `nIn`，`u32be` |
| 12 | 4 | `nOut`，`u32be` |
| 16 | 其余 | TAP-02 记录（TAP-02 §2） |

#### 2.2 有效性

一个字节串是有效的 `tapnet/1` 文件，当且仅当以下各条全部成立：

1. 长度至少 16 字节，第 0–5 字节为 `TAPNET`，第 6 字节为 `0x01`，第 7 字节为 `0x00`；
2. 记录不为空；
3. 每条记录都是 NAND（`0x00`）或 LATCH（`0x01`）记录。出现 REF 记录（`0x02`）即为无效；
4. 这些记录连同文件头中的 `nIn` 与 `nOut`，按 TAP-02 §3 构成一个良构网表，包括其对 `nIn` 与 `nOut` 的取值范围限制。（没有 REF 记录时，TAP-02 §3 的条件 6 不会出现。）

工具 MUST 拒绝无效文件，且 MUST NOT 生成无效文件。工具 MUST 在读取前检查记录长度，并 MUST 在为记录分配内存之前限定记录数量（TAP-02 §7）。

有效文件的长度恰为 `16 + 7·nand + 4·latch` 字节，其中 `nand` 与 `latch` 是其 NAND 与 LATCH 记录的数量。

#### 2.3 网表哈希

```
netlistHash = SHA-256(netlist file)
```

网表哈希逐字节地标识一份网表文件。两份计算同一函数、但任一字节不同的文件，哈希不同。一种忽略门编号的结构标识符在 `TAP-draft-netlist-structural-hash` 中定义。

#### 2.4 指标

有效文件的指标为 `nIn`、`nOut`、`nand`、`latch` 以及 `gates = nand + latch`。由于文件不含 REF 记录，`latch` 等于电路的状态位数 `nState`，`gates` 等于 TAP-02 的 `gateCount`。

### 3. 来源电路

#### 3.1 声明来源

一份网表 MAY 声明一个来源电路：链表中某条链上的 `(chainId, processor contract, circuit id)`，以及读取时的区块号。它 SHOULD 同时给出该电路的链上名字（TAP-10 §3.1）：在 BNB Smart Chain 上为 `<#ID>.<processor number>.tape`，在其它链上为 `<#ID>.<area code>.<processor number>.tape`。

#### 3.2 核验来源

核验者 MUST 按以下步骤确认一个已声明的来源，并按 TAP-10 §5 的规则（独立节点、一个固定区块）读取来源链。它在按 TAP-10 §5.3 固定的区块上读取，或在具备归档访问能力时在声明的 `block` 上读取，并报告采用了哪一种；由于已存储的网表没有修改函数（TAP-02 §3），在声明区块或其之后的任一区块上确认，都构成对来源的确认：

1. 确认该处理器合约已在该链的处理器工厂中注册（`isCPU(address)`，选择器 `0x5f5a364f`），且只使用 TAP-10 在 Deployments 中列出的工厂地址；
2. 读取 `circuitInfo(id)` 与 `netlist(id)`（TAP-02 §6）；
3. 构造 `TAPNET ‖ 0x01 ‖ 0x00 ‖ u32be(nIn) ‖ u32be(nOut) ‖ netlist(id)`；
4. 当且仅当该文件有效（§2.2）且其 SHA-256 等于声明的网表哈希时，来源得到确认；
5. 若元数据声明了来源的 `container`，它 MUST 等于该链容器开启器的 `accountOf(processor contract, circuit id)`（TAP-10 附录 A）；工具 MUST NOT 接受仅凭报告而来的容器地址。

网表中含 REF 记录的电路，在本版本下不能作为来源。（每个设计证明矿机电路都满足条件，因为挖矿合约拒绝含 REF 记录的电路。）

来源链不必是集合所在的链。核验来源是对来源链的读取；它不需要跨链桥，本 TAP 也不要求任何合约执行它。

来源仅表示出处。来源电路代币此后的转移，或其名字、容器的变化，都不改变绑定到 NFT 的网表。持有网表绑定 NFT 不赋予对来源电路、其容器或该电路任何收益的任何权利。

### 4. 标识符与内容位置

#### 4.1 代币标识符

网表绑定 NFT 的全局标识符是它的 CAIP-19 资产 ID（CAIP-19，ChainAgnostic/CAIPs 提交 `1a897eede982d3d4eb68982f3798ebb0878c6ef5`）：

```
eip155:<chainId>/erc721:<collection address>/<tokenId>
```

其中链 ID 取自链表、以十进制书写，集合地址用小写十六进制，代币编号用十进制（无前导零）。索引、显示或引用多条链上代币的工具 MUST 使用该标识符，且 MUST NOT 仅凭代币编号标识代币。

#### 4.2 内容位置

图片、网表文件、代币集文件和清单通过 URI 定位。同一份内容的 URI 列表 SHOULD 至少包含一个 `tape://` URL（TAP-10 §3.2），其字节由 TAP-10 客户端对照链上核验；以及至少一个内容寻址 URI（`ipfs://` 或 `ar://`）。MAY 列出 `https://` URI，特别是为了让不解析其它方案的交易市场能显示图片。

工具 MUST 用给定的哈希核对它取得的任何字节的 SHA-256，并 MUST 把任何 URI、网关或服务器视为不可信。

从 TapeOut 容器提供的内容，还须遵守 TAP-721 容器托管与锁定的规则（§8.6）。

容器能证明某路径下存在某个哈希的文件，但不能证明哪枚代币获得该文件。这一绑定由元数据（L0）或链上接口（L1，§8）确立。

交易市场通常在其服务器上抓取 `tokenURI` 与 `image`，而浏览器 Service Worker 网关（TAP-10 §8.8）不在那里运行。依赖这类市场的集合需要一个服务器可以抓取的 HTTPS URI，并 SHOULD 同时列出一个内容寻址副本。

### 5. 清单与池

#### 5.1 清单文件

通过揭示把内容分配给代币的集合，或实现 L1 的集合，MUST 发布一份清单：一个 UTF-8 JSON 文件。其哈希为

```
manifestHash = SHA-256(manifest file bytes, exactly as published)
```

不定义规范化的 JSON 形式；被哈希的就是发布的字节。清单包含以下成员：

| 成员 | 类型 | 内容 |
|---|---|---|
| `tapManifest` | number | `1` |
| `collection` | object | `chainId`（number）、`address`（string，小写），以及二者择一：代币区间——`firstTokenId`（number，至多 2^53 − 1 − `supply`）与 `supply`（number）——或代币集——`tokenSet`：{`sha256`、`count`（number）、`uris`}（§5.4）——不得同时出现 |
| `reveal` | object | `source`（string）：`drand`、`vrf`、`blockhash` 或 `none`，以及 §6.1 的参数 |
| `pools` | array | 一个或两个池（§5.2），顺序固定 |
| `freeze` | object，可选 | 用于 L0：工具如何核实 `tokenURI` 已不能再改变。`chainId`、`contract`、`call`（一个无参数、返回 `bool` 的函数签名，例如 `"uriFrozen()"`）与 `expect`（`true`） |

区间模式下覆盖的代币为 `firstTokenId … firstTokenId + supply − 1`；代币集模式下为代币集中的编号（§5.4）。`supply`（区间模式）与 `count`（代币集模式），下文记作 `n`，MUST 满足 1 ≤ `n` ≤ 2^32。其它 TAP MAY 定义清单的更多成员（例如 `TAP-draft-pod-attributes` 中的 `pod`）；工具 MUST 忽略它不认识的成员。

L0 集合 SHOULD 使发布时间可证明：把清单上传到一个 TapeOut 容器，或在伴生合约中承诺其哈希（§8.3）。对容器上传，发布区块是该容器与路径上 `sha256Hash` 等于清单哈希的最早一条站点存储事件 `FileSet(address indexed container, string path, uint32 size, bytes32 sha256Hash, string contentType)`（主题 `0x13b9b0f05b22c496a9d9a29e7041c56c04670dc98ab327448870f18eb07b6773`，TAP-10 附录 A）所在的区块；对伴生合约，是 `ManifestCommitted` 所在的区块。工具核对该区块早于主种子变得可知的时刻；找不到该区块的工具把发布时间视为未经证明，并如实说明。

#### 5.2 池

池是一个对象，包含：

| 成员 | 类型 | 内容 |
|---|---|---|
| `label` | string | 1–64 字节的可打印 ASCII（`0x20`–`0x7e`），在清单内唯一。用于 §6.2 |
| `fields` | array | `["image"]`、`["netlist"]` 或 `["image", "netlist"]` |
| `root` | string | 池的 Merkle 根（§5.3），`0x` 加 64 位小写十六进制数字 |
| `entries` | array | 恰好 `n` 个条目（`supply` 或 `count`） |

每个条目是一个对象，每个字段对应一个成员，名为 `image` 或 `netlist`，其值为图片文件的 SHA-256 或网表哈希，写作 `0x` 加 64 位小写十六进制数字。条目 MAY 携带 `uris`：在单字段池中，是该字段内容的非空 URI 字符串数组；在双字段池中，是一个含 `image` 与 `netlist` 成员的对象，每个成员都是非空 URI 字符串数组。条目还 MAY 携带 `attributes`（该条目贡献的 ERC-721 元数据属性）、`source`（§3.1，用于网表字段）及其它成员；工具 MUST 忽略它不认识的成员。

每个池条目 MUST 为其池的每个字段携带非零值，网表字段中的每个网表哈希 MUST 对应一个有效的 `tapnet/1` 文件。把每张图片与一份固定网表配对的集合，使用一个含两个字段的池；图片与网表独立分配的集合，使用两个池。

链上使用的字段位掩码为 `image = 1`、`netlist = 2`。在叶子内，值按先图片、后网表的顺序排列。每个字段至多出现在一个池中，因此清单有一个或两个池。集合 MAY 只使用一个单字段池（只揭示图片或只揭示网表）。没有任何池携带的字段不由揭示分配：集合在每枚代币的元数据中固定它，§7.3 第 3 条不适用于它，并且在 L1，对应的读取函数（`imageHashOf` 或 `netlistHashOf`）对它永久返回零（§8.2）。根与条目值 MUST NOT 为零；在链上，零表示“未绑定”。

#### 5.3 Merkle 树

对于条目为 `0 … n−1` 的池：

```
leaf(i)  = SHA-256(0x00 ‖ u32be(i) ‖ value_1 ‖ … ‖ value_k)     values in field order, 32 bytes each
node     = SHA-256(0x01 ‖ left ‖ right)
```

树从叶子开始逐层构建：某一层的第 `2j` 与第 `2j+1` 个节点合并为下一层的第 `j` 个节点；若某层节点数为奇数，其最后一个节点原样升入下一层。根是最后一层的唯一节点。只有一个条目的池，`root = leaf(0)`。

条目 `i` 的证明，是从叶子层向上的兄弟节点列表，省略节点原样上升的那些层。核验证明需要根、池大小、序号、叶子和证明：

```
verify(root, size, index, leaf, proof):
    if index ≥ size: fail
    h = leaf ; i = index ; n = size ; k = 0
    while n > 1:
        if i is odd:          h = SHA-256(0x01 ‖ proof[k] ‖ h) ; k = k + 1
        else if i + 1 < n:    h = SHA-256(0x01 ‖ h ‖ proof[k]) ; k = k + 1
        i = i >> 1 ; n = (n + 1) >> 1
    succeed if and only if k = len(proof) and h = root
```

叶子中的序号把每个值绑定到它的位置，因此一个位置的证明不能用于另一个位置。

#### 5.4 代币集

被覆盖代币不构成一个连续区间的集合——例如部分代币由一个永远无法转出它们的地址持有——使用代币集模式。代币集文件是把每个被覆盖代币编号的 `u32be(tokenId)` 按严格升序拼接而成（因此每个编号 MUST 小于 2^32），`tokenSet.sha256` 是其 SHA-256。该文件 MUST 与清单一同发布，位于 `tokenSet.uris` 所列的 URI。代币集是分配的输入，因此 MUST 在主种子可能被知晓之前固定（§6.1 第 3 条）。工具 MUST 拒绝非严格升序、长度不等于 `4 × count`、或 SHA-256 不符的代币集文件。

被覆盖代币 `t` 的序号是它在代币集中的排名：比 `t` 小的被覆盖编号的个数。

代币集之外的代币现在和将来都不获得池条目。它们的元数据 MUST NOT 携带 `tap.image` 或 `tap.netlist`。集合 SHOULD 仍为其中每一枚提供一个元数据文件，以免交易市场收到错误；这样的文件携带 `tap.v`、`tap.id`、`tap.state` = `unrevealed` 与 `tap.manifest`；其 ERC-721 `image`（§7.1 要求必须有）是一个占位图。拥有代币集的工具 MUST NOT 把这样的代币显示为等待揭示，并 SHOULD 把它显示为不在清单覆盖范围内。在 L1，对这样的代币 `netlistHashOf` 与 `imageHashOf` 永久返回零，`entryIndexOf` 回滚（§8.2）。

### 6. 揭示

#### 6.1 主种子

清单的 `reveal` 对象在种子可能被知晓之前，固定主种子的来源：

| `source` | 参数 | 主种子 |
|---|---|---|
| `drand` | `chainHash`（64 位小写十六进制数字，不带 `0x`，与 drand 发布的形式一致）、`round`（number） | 该 drand 链该轮次的 32 字节 `randomness` |
| `vrf` | — | 保留。版本 1 不定义 VRF 来源；工具 MUST 拒绝使用它的清单 |
| `blockhash` | `chainId`（number）、`blockNumber`（number） | 该区块的哈希 |
| `none` | — | 不揭示：池条目 `x` 归序号为 `x` 的代币（§6.3） |

要求：

1. 清单哈希 MUST 在主种子可能被知晓之前发布，对 L1 还要在链上承诺（§8）：即在 drand 轮次产生之前，或在该区块产生之前；
2. 主种子 MUST 恰好使用一次。集合 MUST NOT 请求或选择第二个种子，且在第一份清单的种子已知之后，MUST NOT 为同一批代币承诺第二份清单；
3. 影响代币如何分配或标注的每一项输入——池顺序、代币集、档位与稀有度规则、资格规则，以及 `TAP-draft-pod-attributes` 等属性来源的快照区块——MUST 在主种子可能被知晓之前由清单固定（写在清单字节中，或写在一个其 SHA-256 包含于清单中的文件里）；
4. `reveal.source` 不为 `none` 的集合 SHOULD 在主种子可能被知晓之前完成铸造，因为种子一旦已知，任何人都能算出哪个未铸造的代币编号会获得哪个条目；
5. 集合 SHOULD 在种子已知后及时发布揭示后的元数据，并 SHOULD 事先提醒持有人：从那一刻起，任何人都能算出每枚代币的分配；
6. 在区块由单一排序器产生的链上，`blockhash` 为 NOT RECOMMENDED，因为该排序器可以在区块内容之间做选择；X Layer 与 Base 都是这样的链（截至 2026-10-17 UTC）。区块哈希只在其区块之后的 256 个区块内可在链上读取；未在该窗口内记录的揭示，在这份清单下无法进行；
7. 核验 `drand` 种子的工具 MUST 确认 `randomness` 等于该轮 `signature` 的 SHA-256，MUST 从至少两个独立的、其链信息哈希等于 `chainHash` 的 drand 中继取得相同的签名，并 SHOULD 用该链的公钥核验 BLS 签名；
8. 主种子如何写入链上由实现决定；L1 合约 MUST 把它设为本节针对清单来源所定义的值，其 `Revealed(masterSeed)` 事件让任何人都能比对。

#### 6.2 池种子

```
poolSeed = SHA-256(masterSeed ‖ u64be(chainId) ‖ collection address (20 bytes) ‖ UTF-8(label))
```

`chainId` 与地址取清单的 `collection.chainId` 与 `collection.address`，无论置换在何处计算（伴生合约，或集合在另一条链上的副本，都使用本链的原始值）。每个池有自己的种子，因此各池由同一个主种子独立分配。希望图片稀有度与网表稀有度相互独立的集合，把它们放在两个池中。

#### 6.3 带密钥置换

序号为 `x` 的代币 `t`——区间模式下为 `t − firstTokenId`，代币集模式下为它在代币集中的排名（§5.4）——获得每个池的第 `permute(poolSeed, n, x)` 个条目，其中 `n` 为 `supply` 或 `count`：

```
permute(seed, n, x):
    if n = 1: return 0
    b    = max(1, bitlength(n − 1))
    h    = ceil(b / 2)
    mask = 2^h − 1
    E(v):
        L = v >> h ; R = v & mask
        for r in 0, 1, 2, 3:
            (L, R) = (R, L xor F(r, R))
        return (L << h) | R
    F(r, R) = uint256(SHA-256(seed ‖ u8(r) ‖ u32be(R))) & mask
    y = E(x)
    while y ≥ n: y = E(y)
    return y
```

`E` 是 `[0, 4^h)` 上的四轮 Feistel 置换，且 `4^h < 4n`，因此循环游走必然终止，`permute(seed, n, ·)` 是 `[0, n)` 上的一个置换。任何一方都能单独算出任意一枚代币的条目，而无需计算其它代币，链上链下皆可。

#### 6.4 版次

当同一网表哈希在集合的网表字段中出现不止一次时，获得它的那些代币构成一个版次。这样一枚代币的版次为 `(index, of)`，其中 `of` 是获得该网表哈希的代币数量，`index` 是该代币在其中按代币编号升序的排名，从 1 开始。版次由揭示决定；集合 MUST NOT 通过改变门编号或编码，使一份网表看起来像多份（见安全考虑）。

### 7. 代币元数据

#### 7.1 `tap` 成员

`tokenURI` 返回的 JSON 文档 MUST 包含 ERC-721 元数据成员 `name` 与 `image`，并 MUST 包含成员 `tap`：

| 成员 | 是否必需 | 类型 | 内容 |
|---|---|---|---|
| `v` | 是 | number | `1` |
| `id` | 是 | string | §4.1 的代币标识符 |
| `state` | 是 | string | `unrevealed` 或 `revealed` |
| `manifest` | 集合有清单时 | object | `sha256`（清单哈希）、`uris` |
| `image` | `revealed` 时 | object | `sha256`、`uris` |
| `netlist` | `revealed` 时 | object | `format`（`"tapnet/1"`）、`sha256`（网表哈希）、`bytes`、`nIn`、`nOut`、`nand`、`latch`（number）、`uris`；可选 `structuralHash`（该文件按 `TAP-draft-netlist-structural-hash` 计算的结构哈希，`0x` 加 64 位小写十六进制数字） |
| `edition` | `of > 1` 时 | object | `index`、`of`（§6.4） |
| `source` | 否 | object | `chainId`（number）、`processor`（小写地址）、`circuitId`（十进制字符串）与 `block`（number），均为必需；`name`（链上名字）与 `container`（来源电路的容器地址，小写）可选 |
| `content` | 否 | object | 集合文件在某个 TapeOut 容器中的存放位置（§7.5） |
| `license` | 否 | object | `image`、`netlist`：各为一个 SPDX 标识符或一个 URI |
| `companion` | 集合通过元数据指明其伴生合约时（§8.3，方式 1） | object | `chainId`、`address`（§8.3） |

在 `manifest`、`image` 与 `netlist` 中，除 `structuralHash` 外，所列成员均为必需；`uris` 是非空的 URI 字符串数组。为一份网表给出 `structuralHash` 的集合 SHOULD 为每份网表都给出。数字为 0 到 2^53 − 1 之间的 JSON 整数。未在此列出的成员 MAY 出现；工具 MUST 忽略它不认识的成员。其它 TAP MAY 定义 `tap` 的更多成员。

示例（仅供参考；`vectors.json` 中完整示例第 4 号代币的 `tap` 成员，URI 有缩略）：

```json
{
  "v": 1,
  "id": "eip155:196/erc721:0x00000000000000000000000000000000000000aa/4",
  "state": "revealed",
  "manifest": {"sha256": "0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983", "uris": ["https://example.invalid/tap-example/manifest.json"]},
  "image": {"sha256": "0x2da1fc59339f21ea2cd41bffc0136e4a399f64ce690e0ca06e0bb90f6e589b9e", "uris": ["https://example.invalid/tap-example/images/0.png"]},
  "netlist": {"format": "tapnet/1", "sha256": "0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e", "bytes": 44, "nIn": 2, "nOut": 1, "nand": 4, "latch": 0, "uris": ["https://example.invalid/tap-example/netlists/ecb6….tapnet"]},
  "edition": {"index": 1, "of": 3},
  "source": {"chainId": 56, "processor": "0xb1024b89886b9a34aa4ff5f31c411d708b20a14c", "circuitId": "17851", "block": 128200681, "name": "17851.30.tape"}
}
```

#### 7.2 状态

- `unrevealed`：代币尚无内容，或它在代币集之外（§5.4）。`netlist` MUST 缺省，`manifest` MUST 出现（没有清单的集合在铸造时分配内容，从不使用此状态）。对等待揭示的代币，MAY 出现一个占位的 `tap.image` 成员；对代币集之外的代币（§5.4），它 MUST 缺省；ERC-721 的 `image` 仍是必需的（§7.1），并 MAY 为占位图；出现的任何其它成员仍 MUST 遵循 §7.1；
- `revealed`：内容已分配。

内容是否仍可改变不是一种元数据状态：在冻结之前写下的文件无法如实宣告这一点。工具从链上得出它（§8）：L1 读 `frozen()`，L0 读清单在 `freeze` 中指定的探测（§5.1）。

#### 7.3 一致性

1. `image`（ERC-721 成员）以及 `tap.image.uris` 中的每个 URI，MUST 提供 SHA-256 为 `tap.image.sha256` 的字节；
2. `tap.netlist.bytes` MUST 等于 `16 + 7·nand + 4·latch`；
3. 揭示后，`tap.image.sha256` 与 `tap.netlist.sha256` MUST 对每个由池携带的字段（§5.2）等于该代币按 §6 获得的池条目的值，`tap.edition` MUST 遵循 §6.4（对只被一枚代币获得的网表哈希，缺省或为 `1/1`）。版次只能在整个集合范围内核对；拥有每枚代币元数据的索引器 MUST 核对它们；
4. `attributes`（ERC-721 成员）MAY 为交易市场重复 `tap` 中的事实；二者不一致时，以 `tap` 为准。

#### 7.4 核验一枚代币

把一枚代币显示为网表绑定的工具，MUST 至少：解析元数据，并检查 §7.1–§7.3 中无需网络访问的规则；从 `tap.netlist.uris` 之一取得网表文件；核对其 SHA-256 等于 `tap.netlist.sha256`、文件有效（§2.2）且其指标与声明一致。它 SHOULD 取得清单（代币集模式下还有代币集文件），核对其哈希并重新计算该代币的分配（§6），并 SHOULD 核验已声明的来源（§3.2）。它 MUST 显示一致性等级（§8），且 MUST NOT 把 L0 代币显示为已在链上核验。

#### 7.5 TapeOut 容器中的内容

把文件存放在某个 TapeOut 容器中的集合，MAY 在 `tap.content` 中描述它们：

| 成员 | 是否必需 | 类型 | 内容 |
|---|---|---|---|
| `chainId` | 是 | number | 容器所在的链，取自链表 |
| `container` | 是 | string | 容器地址，小写 |
| `name` | 是 | string | 容器所属电路的链上名字（TAP-10 §3.1） |
| `paths` | 是 | object | 容器站点内的路径（TAP-10 §7.2），每项为字符串，均可选：`image`、`netlist`、`metadata` |
| `lock` | 否 | string | 持有容器电路的锁定合约（§8.6）的地址，小写 |

使用 `tap.content` 的工具：

1. MUST 在链 `chainId` 上按 TAP-10 §4.2 从 `name` 推导出容器，除非 `container` 等于推导出的地址，否则 MUST NOT 使用它；
2. MUST 按 TAP-10 §7.1 读取文件，并 MUST 用 `tap.image.sha256` 与 `tap.netlist.sha256` 核对图片与网表文件，而不只是核对站点存储声明的哈希；
3. SHOULD 显示容器的电路是否由 `lock` 持有（在固定区块上读取处理器合约对该电路的 `ownerOf`），且 MUST NOT 仅凭 `lock` 就把文件描述为已锁定。

`tap.content` 增加了位置信息；它不取代 `uris`，§7.1 的哈希仍具权威性。

### 8. 一致性等级与扩展

§8.1 与 §8.2 定义核心的两个一致性等级。§8.3–§8.6 定义 TAP-721 的各扩展；合约通过 ERC-165 恰好报告它所实现的扩展接口。

#### 8.1 L0：元数据

若一个集合的代币元数据遵循 §7，且在进行揭示时其清单与揭示遵循 §5 与 §6，则该集合符合 L0。L0 不要求修改合约：只能设置 base URI 的集合，通过发布元数据文件即可符合。在 L0，内容不会改变的保证，取决于集合放弃修改 `tokenURI` 的能力（例如一个不可逆的 `freezeBaseURI()`）；工具 MUST 把这类集合标注为“L0（仅元数据）”。

#### 8.2 L1：链上接口

若一个合约实现下面的 `ITapNetlistNFT`、ERC-165（报告 `ITapNetlistNFT` `0x282b67f6`、ERC-165 `0x01ffc9a7` 与 ERC-4906 `0x49064906` 的接口标识）以及 ERC-4906，并满足以下各条，则它符合 L1：

1. `manifestHash()` 与 `masterSeed()` 一旦非零、`pools()` 与 `tokenRange()` 一旦设定（非空，`supply` ≥ 1），就永不改变；`pools()[i]` 等于清单 `pools[i]` 的标签、字段掩码与根；
2. 一旦 `masterSeed()` 非零，`entryIndexOf(t, p)` 返回以 §6.3 的序号 `x` 计算的 `permute(poolSeed_p, n, x)`；在此之前、对未被覆盖的代币（§5.4）、以及对不存在的池序号，它回滚。若清单的 `reveal.source` 为 `none`，合约在承诺清单时把 `masterSeed()` 设为 `0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff`，`entryIndexOf(t, p)` 返回序号 `x`，并且对第 5 条而言种子视为已设定。对任何其它来源，合约 MUST NOT 把零或该值记录为主种子；
3. `bind` 在按条目序号 `entryIndexOf(t, p)` 对照池根核验一个 Merkle 证明（§5.3）之后，为任何调用者记录一枚代币获得的条目；它是幂等的。实现 MAY 在用完整值列表重建池根并与已承诺的根核对之后，一次调用或分多次调用记录一个池的全部条目；种子设定后，`netlistHashOf` 与 `imageHashOf` 即可无需 `bind` 地为每枚被覆盖代币作答；
4. 一个网表哈希为已知，当它已由 `bind` 记录；或在 `masterSeed()` 设定之后，某个无需许可的函数为获得它的某枚代币、从按第 3 条记录的池中推导出它并加以记录（参考实现中为 `markKnown(uint256 tokenId)`）；或它随代币按某个跨链 TAP 到达。`storeNetlist` 只接受 SHA-256 为已知网表哈希、且长度至多 49,152 字节的文件，并使其可通过 `netlistFile` 与 `netlistOf` 读取。它 SHOULD 在链上检查有效性（§2.2），若合约实现了 TAP-721 求值扩展（§8.4）则 MUST 检查。`NetlistStored.pointer` 背后的布局仅供参考；客户端通过 `netlistFile` 读取文件。回滚数据不属于本接口；
5. 只有当清单已承诺、种子已设定，且没有任何账户能改变 `tokenURI`、清单、池或种子时，`frozen()` 才返回 true；一旦为 true，就永不再返回 false。位于可升级代理之后的合约，只要其升级路径存在，就不是冻结的；
6. 每当代币的元数据可能已改变（承诺、揭示、绑定、记录池或代币集、冻结）时，它发出 ERC-4906 的 `MetadataUpdate` 或 `BatchMetadataUpdate`，以便交易市场刷新。在代币集模式下，覆盖 `0 … 2^256 − 1` 的 `BatchMetadataUpdate` 即满足此条。

如何承诺清单、写入种子、记录池与代币集以及冻结合约，由实现决定；`ITapNetlistNFT` 的事件让任何人都能核对结果。

L1 集合的 `tokenURI` 仍 MUST 遵循 §7，且其元数据中的值 MUST 等于接口返回的值；没有任何池携带的字段（§5.2）除外，接口对它返回零。

清单使用代币集模式（§5.4）的 L1 合约，还 MUST 实现 TAP-721 代币集扩展（§8.5）。

**跨链副本。** 由建立在本 TAP 之上的某个跨链 TAP 在另一条链上创建的集合副本，MAY 在没有清单的情况下实现 `ITapNetlistNFT`：在那里，`entryIndexOf` 与 `bind` MAY 以该跨链 TAP 定义的错误回滚，`netlistHashOf` 与 `imageHashOf` 返回随代币到达的哈希。在这样的副本中，`collection()` 返回副本本身，`tokenRange()` MAY 对无界区间返回 `supply` = 0，`frozen()` MAY 一直为 false，元数据的 `tap.id` 是原链代币的标识符（§4.1）。在任何实现中，`netlistHashOf` 与 `imageHashOf` 只在某代币尚无已知哈希时返回零，或对没有任何池携带的字段（§5.2）永久返回零。

```solidity
// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.28;

interface ITapNetlistNFT {
    struct Pool { string label; uint8 fields; bytes32 root; }

    function collection() external view returns (address);
    function tokenRange() external view returns (uint256 firstTokenId, uint256 supply);
    function manifestHash() external view returns (bytes32);
    function pools() external view returns (Pool[] memory);
    function masterSeed() external view returns (bytes32);
    function entryIndexOf(uint256 tokenId, uint256 poolIndex) external view returns (uint256);
    function bind(uint256 tokenId, uint256 poolIndex, bytes32[] calldata values, bytes32[] calldata proof) external;
    function netlistHashOf(uint256 tokenId) external view returns (bytes32);
    function imageHashOf(uint256 tokenId) external view returns (bytes32);
    function storeNetlist(bytes calldata file) external returns (bytes32 netlistHash);
    function netlistFile(bytes32 netlistHash) external view returns (bytes memory);
    function netlistOf(uint256 tokenId) external view returns (bytes memory);
    function frozen() external view returns (bool);

    event ManifestCommitted(bytes32 indexed manifestHash);
    event Revealed(bytes32 masterSeed);
    event Bound(uint256 indexed tokenId, uint256 indexed poolIndex, uint256 entryIndex);
    event NetlistStored(bytes32 indexed netlistHash, address pointer);
    event Frozen();
}
```

`bind` 中的 `values` 按字段顺序（先图片、后网表）存放该条目的 32 字节字段值。函数选择器、ERC-165 接口标识与事件主题列于测试用例。

#### 8.3 TAP-721 伴生合约扩展

无法修改的现有 ERC-721 合约 MAY 通过伴生合约达到 L1：伴生合约是同一条链上的一个独立合约，它实现 `ITapNetlistNFT`，且 `collection()` 返回该现有合约。绑定是双向的：

1. 伴生合约指明集合（`collection()`）；
2. 集合一方以两种方式之一指明伴生合约：其元数据携带 `tap.companion`，或集合的所有者已在链上为该伴生合约背书。第二种方式在集合的 URI 冻结之后依然有效。

每个伴生合约 MUST 实现 `ITapCompanion` 并报告其 ERC-165 标识 `0x12b40a6c`。除非调用时 `msg.sender` 等于集合的 `owner()`（ERC-173），`endorse()` 回滚；首次成功调用永久记录调用者并发出 `Endorsed(address by)`，此后的调用不产生效果。实现 MAY 在清单承诺之前拒绝背书。`endorsedBy()` 返回所记录的地址或零。集合所有者此后的变更不撤销背书。

```solidity
interface ITapCompanion {
    function endorse() external;
    function endorsedBy() external view returns (address);
    event Endorsed(address by);
}
```

只有当没有任何账户能改变伴生合约的清单、池或种子，伴生合约已获集合背书或指明，且现有合约已不能再改变 `tokenURI` 时，伴生合约的 `frozen()` 才返回 true。伴生合约 MAY 实时读取现有合约的冻结标志，但 MUST 锁存它观察到的第一个 `true`，并 SHOULD 提供一个无需许可即可调用的锁存函数，使 `frozen()` 永不回到 false。伴生合约的 ERC-4906 事件来自伴生合约的地址；只监听集合地址的交易市场可能看不到它们。

#### 8.4 TAP-721 求值扩展（可选）

L1 合约 MAY 让其所在链上的任何合约运行一枚代币的网表。此时它实现 `ITapNetlistEval` 并报告其 ERC-165 标识 `0xec7d7e20`。

```solidity
interface ITapNetlistEval {
    function evalOf(uint256 tokenId, bytes calldata inputs) external view returns (bytes memory outputs);
    function stepOf(uint256 tokenId, bytes calldata state, bytes calldata inputs)
        external view returns (bytes memory newState, bytes memory outputs);
    function evalFile(bytes32 netlistHash, bytes calldata inputs) external view returns (bytes memory outputs);
    function stepFile(bytes32 netlistHash, bytes calldata state, bytes calldata inputs)
        external view returns (bytes memory newState, bytes memory outputs);
}
```

1. 一次调用是在已存储网表文件上执行 TAP-02 §4 的一拍，输入、状态与输出按 TAP-02 §5 打包（输入与状态宽松读取；输出与新状态恰为 `ceil(n/8)` 字节，以零填充）。对每一组输入与状态，结果 MUST 与 TAP-02 的结果相同；
2. 当网表含 LATCH 记录时，`evalOf` 与 `evalFile` MUST 回滚，与 TAP-02 的 `eval` 一致；
3. 当网表文件未存储在本链上时，四个函数都 MUST 回滚；当某代币没有已知网表哈希时，`evalOf` 与 `stepOf` MUST 回滚。

由于文件不含 REF 记录，一拍的成本与文件大小成正比，调用者可以在调用前读取指标。

#### 8.5 TAP-721 代币集扩展

清单使用代币集模式（§5.4）的 L1 合约，还 MUST 实现 `ITapNetlistTokenSet` 并报告其 ERC-165 标识 `0x3f7177c7`。在代币集模式下，`tokenRange()` 返回 `(0, count)`，`tokenSetHash()` 返回 `tokenSet.sha256`，并且在代币集文件被记录到链上、并与 `tokenSet.sha256` 核对之前，`entryIndexOf` 回滚。在此之前，`tokenAt` 与 `indexOf` MUST 回滚。区间模式的 L1 合约 MAY 实现该接口；此时 `tokenSetHash()` 返回零，`tokenAt(i)` 返回 `firstTokenId + i`，`indexOf(t)` 返回 `t − firstTokenId`。工具凭 `tokenSetHash()` 是否非零区分两种模式，而不是凭 `tokenRange()`。

代币集如何记录由实现决定。参考实现直接载入打包的代币集文件字节（`loadTokenSet(bytes)`，或分多笔交易使用 `loadTokenSetChunk(uint256,bytes)`），用 `tokenSet.sha256` 核对，并使每笔交易的 calldata 不超过 128 KiB，约 32,000 个编号。

```solidity
interface ITapNetlistTokenSet {
    function tokenSetHash() external view returns (bytes32);            // tokenSet.sha256; zero in range mode
    function tokenCount() external view returns (uint256);              // n (count or supply)
    function tokenAt(uint256 index) external view returns (uint256);    // token id of that index
    function indexOf(uint256 tokenId) external view returns (uint256);  // index; reverts if not covered or not recorded
}
```

#### 8.6 TAP-721 容器托管与锁定

本节适用于从 TapeOut 容器提供内容（§4.2）或元数据的集合，以及显示它们的工具；`tap.content`（§7.5）在元数据中描述这类内容。本节不定义接口。

TapeOut 容器中的文件可以被该容器电路的持有人、或持有人设置的站点操作员替换或删除。从容器提供内容的集合，在内容上传并核对完毕后，SHOULD 清除所有操作员，并把该电路转给一个永远无法写入站点存储的合约（锁定合约）。把电路转入它自己的容器同样会停止一切写入，但此后无人能为该容器续期激活（TAP-10 §6.3），付费期结束后合规外壳会停止显示它；只能续期的锁定合约可以避免这一点。

锁定去除了持有人修改文件的能力，但不能去除站点存储升级者的能力。让替换可被发现的，是 §5 与 §7 的哈希，而不是锁定。

工具 SHOULD 显示为集合提供内容的容器是否已锁定。提供代币元数据的容器 SHOULD NOT 设置回退路径（TAP-10 §7.2），以便缺失的文件被报告为缺失，而不是由另一个页面作答。

## 设计理由

**网表字节，而非指向电路的指针。** 把 NFT 绑定到“处理器 P 的电路 N”，会使 NFT 依赖于另一个可被转移的代币，以及一条 NFT 不一定所在的链。绑定一个自包含文件的哈希，使网表随 NFT 一起流转，可在任意链上核验并重新流片；来源保留为出处（§3）。

**版本 1 不含 REF。** REF 记录指向一条链上的处理器合约地址与电路编号，因此含 REF 记录的网表既不独立于链，也不自包含。把 REF 记录展平为门是可能的，但需要一条精确的重新编号规则，而首个用例并不需要它：设计证明矿机本就禁止 REF。后续版本可以在不改变 `tapnet/1` 的前提下加入展平。

**字节哈希加独立的结构哈希。** 网表哈希必须对合约和钱包而言廉价且无歧义；文件的 SHA-256 两者兼备。识别两份网表在门重新编号后是否为同一设计是另一个问题，且有已知局限；它在单独的 TAP 中规定，以便其算法可以演进而不触及本 TAP。

**SHA-256。** TAP-10 用 SHA-256 核验容器文件，drand、IPFS 以及大多数工具也使用它，因此一个哈希可以同时服务于文件、清单、代币集、Merkle 树和置换。在全部三条链上它都以地址 `0x02` 的预编译合约提供（2026-10-17 UTC 在 BNB Smart Chain、Base 与 X Layer 上以输入 `abc` 进行 `eth_call` 核实，均返回 `0xba7816bf…f20015ad`）。

**带密钥置换，而非洗牌。** 对 10,000 个条目做 Fisher–Yates 洗牌无法在一笔交易内完成，而且必须先在链下完整算出，才能核对任何一枚代币。带循环游走的 Feistel 置换让每枚代币用几次哈希就能独立得到自己的条目，链上链下皆可，并且按构造即为双射。

**Merkle 根，而非存储每个条目。** 在合约存储中保存 10,000 对哈希要花费数亿 gas；一个根只占一个存储槽。`bind` 让任何人——通常是持有人或索引器——在需要时记录一枚代币的条目。一次记录整个池（§8.2 第 3 条）作为一条更便宜的路径被允许，适合希望从揭示起每枚代币都能在链上读取的集合；它对照的是同一个根，因此不增加信任。

**一个主种子，多个池。** 图片稀有度与网表稀有度往往需要相互独立。按域分离的池种子用一次随机数请求就做到这一点，也允许把图片与网表放在同一个池中配对的集合。

**按排名的代币集。** 可用代币存在空缺的集合，否则要么把内容分配给无人能用的代币——浪费稀缺的网表并误报稀缺性——要么重新部署。代币集模式保持置换不变，只改变序号：代币在一个升序列表中的排名。打包的 `u32be` 列表在链上链下都很容易哈希，排名也不需要列表以外的数据。带空洞的包围区间被否决，因为那样池大小将不再等于所服务的代币数。在种子之前固定代币集（§6.1 第 3 条），可以防止发行方在看到分配结果后纳入或排除代币。为被排除的代币提供单独的文件（§5.4），让交易市场正常工作，又不暗示将来会有内容。

**容器、名字与锁定。** 社区把 TapeOut 的三种基本元素简称为 C/N/L：容器（社区俗称“电容”）、NAND 与 LATCH。本 TAP 在 `tapnet/1` 中使用后两者，用第一种来存储。容器是存放内容的理想位置，因为 TAP-10 客户端会对照链上核验其文件；但其持有人可以修改文件，其站点存储也可升级。因此本设计依靠哈希保证完整性，只用锁定合约阻止随意修改；`tap.content` 以链上名字指明容器，工具由此推导出地址，因此元数据中错误或恶意的地址无法把工具引向别处。

**两个等级。** 没有 L0，合约无法修改、只能设置 base URI 的集合——即起推动作用的案例——就无法符合本 TAP。只有 L0，链上其它合约就无法读取网表，而电路游戏需要读取。通过伴生合约实现的 L1 在不替换集合的情况下弥补了这一缺口。

**一份文档中的核心与扩展。** 与 ERC-721 一样，核心接口是强制的，扩展是同一文档中可选或条件性的部分。代币集、伴生合约与求值扩展的接口与 `ITapNetlistNFT` 分开，使其 ERC-165 标识 `0x282b67f6` 对每个 L1 合约都保持不变，且合约恰好报告它所实现的部分。

**为无揭示集合保留的种子。** `reveal.source` 为 `none` 时没有随机值，但 L1 需要一个非零的 `masterSeed()` 来表示分配已确定。全 1 值不会与“未揭示”（零）混淆，随机来源产生它的概率可以忽略；合约拒绝把它作为随机种子。

**已存储网表的大小上限。** 49,152 字节是参考实现在一笔 16,777,216 gas 的交易（BNB Smart Chain 的上限）内能存储并检查有效性的最大文件。为更大的文件定义分段上传仍是开放问题。

**清单按发布时的字节哈希。** 规范化 JSON 形式会增加一项依赖却毫无收益：清单只发布一次，永不重新序列化。

**求值扩展。** 设计证明挖矿只在 BNB Smart Chain 上运行。在其它链上，携带真实网表的意义在于合约能使用它：调用某枚代币电路的游戏、谜题与竞赛。该扩展使网表成为集合所在链上一个可调用的函数，语义与 TapeOut 处理器相同，而无需重新流片。

**单一主题。** 文件格式、来源核验、标识符、清单、揭示与元数据，是钱包端到端核验一枚代币所需的全部；L1 只是对同样的值增加链上读取，别无其它。若编辑希望文本更窄，TAP-721 求值扩展（§8.4）是第一个可以独立成文的部分，`tapnet/1`（§2）也可以成为单独的格式 TAP；`TAP-draft-netlist-structural-hash` 已经只依赖它。

**现有规范。** 代币标识符采用 CAIP-19，因为钱包和索引器已经能解析它。哈希由专用函数提供而不是 ERC-7496 特征，因为它们由清单固定并由 Merkle 证明证实，而 ERC-7496 特征是所有者可以设置的值；`TAP-draft-pod-attributes` 用 ERC-7496 表示作为另一合约快照的事实。没有现成的 ERC 定义一种经承诺、可公开重算的揭示，因此 §5–§6 用所有链上都可用的最少原语定义了一种。

**与其它 TAP 的关系。** 有三份提案扩展 TAP-721 并以它为前提，正如 ERC-4906 与 ERC-7496 扩展 ERC-721：`TAP-draft-netlist-nft-bridging`（在链间转移 TAP-721 代币）、`TAP-draft-pod-attributes`（TAP-721 代币的设计证明属性）与 `TAP-draft-netlist-structural-hash`（`tapnet/1` 文件的结构哈希）。它们单独成文，原因有四。一个 TAP 一个主题：每一份都可以单独评审、接受或拒绝，而无需重开本 TAP。可升级的依赖：跨链转移依赖一个消息层及其自身的安全分析，PoD 属性读取的合约可以升级；二者都不应拖住本核心，也不应把本核心绑在它们的变化上。应用类型：设计证明事实（任务、燃烧、成本、首个最优状态）会随时间变化且专属于一个应用，因此是 Application TAP，而本 TAP 是 Standards TAP。算法演进：在门重新编号后识别同一设计有已知局限，其算法可以改变，而不改变 §2.3 的网表哈希。

**未纳入的内容。** 内嵌网表的 PNG 文件可以作为附加内容，但不是事实来源，因为交易市场和通讯软件会重新编码图片并丢弃辅助数据块。

## 向后兼容

网表绑定 NFT 是 ERC-721 代币；忽略 `tap` 的钱包和交易市场照旧显示名称、图片和属性。TapeOut 电路代币不受影响；它们可以作为来源（§3）。现有集合通过修改元数据达到 L0，通过伴生合约达到 L1，无需重新部署。

## 测试用例

`assets/tap-netlist-bound-nft/vectors.json` 由 `assets/tap-netlist-bound-nft/make_vectors.py` 生成，可逐字节复现，SHA-256 为 `bb77433f2d3a5e89267eb590206beb2d17a67158ba4ad1f317ed663645dfb3fe`。其成员 `format` 与 `generator` 标识该文件；各部分为：

- `chain`：链上输入的链 ID 与固定区块（BNB Smart Chain 区块 128,200,681，`assets/chain-snapshot.json`）；
- `tapnet`：由在该区块读取的四个 BNB Smart Chain 主网电路构造的网表文件，含网表哈希、指标、链上名字与有效性（其中一个电路含 REF 记录，列为被拒绝）；
- `invalidFiles`：§2.2 每条规则各一个被拒绝的文件，附预期错误；
- `merkle`：含 1、2、3、5、8 个条目、单字段与双字段的池，含根、每个证明、失败的证明与错误用例；
- `permutation`：池种子，以及池大小为 1、2、3、7、10、255、256、257 和 1,000 时的完整 `permute` 输出，池大小为 10,000 时的前 64 个输出与整个置换的哈希，附错误用例与供移植调试用的中间值；
- `metadata`：有效与无效的 `tap` 成员，每个无效成员各违反 §7 的一条规则；
- `manifests`：有效清单（区间模式与代币集模式、一个与两个池、对象形式的 `uris`）与无效清单，每个无效清单各违反 §5.1、§5.2、§5.4 或 §6.1 的一条规则；
- `tokenSets`：代币集模式（§5.4）：一个 20 取 10 的代币集，含其文件、哈希、清单与每枚代币的分配（集合外的代币为无）；一个 10,000 取 7,000 的代币集，含其哈希、前 32 个分配与全部分配的哈希；代币集文件与哈希的错误用例；
- `editions`：对示例进行的集合级版次核对（§6.4、§7.3 第 3 条），以及三个失败用例；
- `netlistChecks`：对照元数据核对取得的文件（§7.4），一个匹配、两个拒绝；
- `example`：一个完整的八枚代币集合，含两个池、清单文件及其哈希、一个固定的主种子、分配结果与每枚代币的元数据（也位于 `example/` 下）。

Solidity 参考实现的测试从一个由 `vectors.json` 生成的数据文件复现这些值，包括对主网电路 #17851（XOR，全部 4 种输入）、#3151（popcount8，全部 256 种输入）与 #17852（约翰逊计数器，从零状态起 20 拍）对照 TAP-02 参考实现进行的求值（§8.4）。

接口（每个 ERC-165 标识是其选择器的异或；用 `cast sig` 重新计算）：

| 接口 | 地位 | ERC-165 标识 | 函数（选择器） |
|---|---|---|---|
| `ITapNetlistNFT` | TAP-721 核心（L1） | `0x282b67f6` | `bind(uint256,uint256,bytes32[],bytes32[])` `0x25944f76`、`collection()` `0x7de1e536`、`entryIndexOf(uint256,uint256)` `0x6b3b2d25`、`frozen()` `0x054f7d9c`、`imageHashOf(uint256)` `0xa7257a04`、`manifestHash()` `0x337f3f32`、`masterSeed()` `0x3982d13f`、`netlistFile(bytes32)` `0x5267c429`、`netlistHashOf(uint256)` `0x32d9b670`、`netlistOf(uint256)` `0xae502e0b`、`pools()` `0xc5c51dca`、`storeNetlist(bytes)` `0xf8b0cc86`、`tokenRange()` `0x40698418` |
| `ITapNetlistTokenSet` | TAP-721 代币集扩展（代币集模式） | `0x3f7177c7` | `tokenSetHash()` `0xa36c08c6`、`tokenCount()` `0x9f181b5e`、`tokenAt(uint256)` `0x92a91a3a`、`indexOf(uint256)` `0x91ac7e65` |
| `ITapCompanion` | TAP-721 伴生合约扩展 | `0x12b40a6c` | `endorse()` `0xf4fbaf58`、`endorsedBy()` `0xe64fa534` |
| `ITapNetlistEval` | TAP-721 求值扩展（可选） | `0xec7d7e20` | `evalOf(uint256,bytes)` `0x3097c028`、`stepOf(uint256,bytes,bytes)` `0x6ff2b6b8`、`evalFile(bytes32,bytes)` `0xf822bb64`、`stepFile(bytes32,bytes,bytes)` `0x4b3ab3d4` |

本 TAP 使用的其它标识：ERC-165 `0x01ffc9a7`、ERC-4906 `0x49064906`、`isCPU(address)` `0x5f5a364f`、ERC-173 `owner()` `0x8da5cb5b`。

事件主题（签名的 `cast keccak`）：`ManifestCommitted(bytes32)` `0x283da7c24290f991388adb4188dab383e865d9edad5d228e8b95805b85bba620`、`Revealed(bytes32)` `0xd5e62fe0c4e6bd40a7736fb2ab572a9a0f5e742f27741505011b9bc89c7ead19`、`Bound(uint256,uint256,uint256)` `0x2893e106f460291bc3157184f05db4c33b0b5f3f34eccce325296bfaaa71436a`、`NetlistStored(bytes32,address)` `0x4095b27949435770a1b733b92eb73b92fb8d0c052ef06cf5db328010d57a64ed`、`Frozen()` `0xa8cab3d1893ed53071b052fafa843143492f25d1d6b0170d460789f7ab1954be`、`Endorsed(address)` `0x403ec5d7987cb23abdef39abe83a6e7f084b84f0809eeda3c3a5b64df6679c56`，以及站点存储事件 `FileSet(address,string,uint32,bytes32,string)` `0x13b9b0f05b22c496a9d9a29e7041c56c04670dc98ab327448870f18eb07b6773`。

参考实现在池大小为 10,000 时的实测成本（仅供参考；交易 gas，括号内为执行 gas）：`entryIndexOf` 平均 25,700、至多 35,300（7,200 与 16,800）；深度 14 证明的 `bind` 约 128,000（76,000）；含有效性检查的 `storeNetlist`，8,444 字节、1,204 个门的文件为 228 万（217 万），49,152 字节的上限文件为 1300 万（1245 万）；记录一个 10,000 条目的单字段池，一笔交易需 8400 万，或分七笔、每笔至多 1310 万。对一个 1,204 个门的文件，求值器约为每门 290 gas。

## 参考实现

- Python，仅用标准库：`assets/tap-netlist-bound-nft/tapnft.py`（文件检查、哈希、来源文件构造、Merkle 树、池种子、置换、清单与代币集检查、分配、元数据与版次检查），附原样复制的 TAP-02 参考实现 `tap02_reference.py`、生成器 `make_vectors.py` 与测试套件 `test_tapnft.py`。
- Solidity：https://github.com/BruceLanLan/TAP-721，将在进入 Review 之前以一个固定提交链接（TAP-01 §7.2 第 8 条）。其中包含 §8 的各接口；`TapNetlistNFT`（一个 L1 集合）、`TapCompanion`（为现有 ERC-721 实现 L1）、库 `TapPermutation`、`TapMerkle`、`TapNetlistCheck`、`TapNetlistStore` 与 `TapNetlistVM`，以及它们的测试。
- 参考 L1 合约中由实现决定、客户端会遇到的入口：`commitManifest`、`commitManifestTokenSet` 与 `commitManifestNoReveal`（§5.1、§6.1）；`scheduleBlockhashReveal` 与 `revealFromBlockhash`，延迟至多 1,000,000 个区块；`loadTokenSet` 与 `loadTokenSetChunk`（§8.5）；`loadPool` 与 `loadPoolChunk`（§8.2 第 3 条）；`markKnown(uint256 tokenId)`（§8.2 第 4 条）；`poolSeed(uint256)`（§6.2）。参考合约至多接受 100,000 枚被覆盖代币，这是实现的限制，不是本 TAP 的限制。
- 参考库未实现 §3.2（第 1、2、5 步）、§5.1 的发布区块、§6.1 第 7 条与 §7.5 的网络核验。`assets/` 下的路径在分配编号时更新。

## 部署

本 TAP 不依赖它自己的任何已部署合约。核验来源（§3.2）使用 TAP-02 与 TAP-10 在其 Deployments 中列出的处理器工厂与处理器合约；在 BNB Smart Chain 上，处理器工厂是一个未封存的可升级代理（TAP-02，Deployments），因此核验者在固定区块上读取，并依赖 NFT 中固定的网表哈希，而不是工厂将来的行为。

## 安全考虑

- **冻结前内容被替换。** 在 L0，以及 L1 中 `frozen()` 之前，集合所有者可以改变 `tokenURI`。在种子之前发布的清单哈希使任何替换都可被发现：内容与其按 §6 获得的池条目不符的代币，无法通过 §7.3。工具必须显示一致性等级与冻结状态。
- **种子操纵。** 如果发布清单的一方能先看到种子，它就能选择一份偏向特定代币的清单。§6.1 要求先有清单、且只有一个种子；在单一排序器链上不推荐 `blockhash`，因为排序器可以操纵。
- **错失的区块哈希揭示。** 区块哈希只在 256 个区块内可在链上读取。安排了 `blockhash` 揭示却错过该窗口的集合，无法在其清单下揭示，而改选另一个区块就成了第二个种子（§6.1 第 2、6 条）。
- **种子之后做出的选择。** 由种子之后选定的区块或公式计算出的代币集、标签或规则，会让发行方偏向特定代币；§6.1 第 2、3 条禁止这样做。
- **种子之后继续铸造。** 种子一旦已知，任何人都能算出哪个未铸造的代币编号获得哪个条目；继续铸造的集合会让铸造者挑选自己偏好的代币（§6.1 第 4 条）。
- **种子之后的公开信息。** 种子一旦已知，任何人都能算出全部分配，因此在元数据更新之前，揭示前挂出的单子不再反映公开信息（§6.1 第 5 条）。
- **被排除的代币。** 在代币集模式下，代币集之外的代币永远得不到内容；若某枚这样的代币后来被证明可以转移，也没有定义补救办法。对某地址能否转移其代币没有把握的集合，应把这些代币留在代币集内。
- **虚假稀缺。** 集合可以通过重新编号门，把一个设计呈现为多个。版次（§6.4）统计相同的文件；`TAP-draft-netlist-structural-hash` 统计相同的设计。宣传网表稀有度的集合应同时声明两者；§7.1 要求声明了 `structuralHash` 的集合为每份网表都声明它，以便索引器能按设计、而不仅按文件统计代币。
- **恶意文件。** 网表来自不可信的来源。没有 REF 记录时，求值成本受文件大小约束（TAP-02 §7 第 1 条要求仍适用于同时处理含 REF 的 TAP-02 网表的工具）。解析器必须先检查长度，且永远不得执行内嵌内容。
- **可变的容器文件。** 在容器电路由一个无法写入的合约持有之前，其持有人可以替换每一个文件（§8.6），站点存储的升级者也可以随时改变其行为。`tap.content` 成员可能指向一个并非由集合控制的容器；§7.5 要求工具从名字推导容器，并用 §7.1 的哈希核对每个文件。
- **网关与交易市场替换。** HTTPS 网关和交易市场会缓存并可能篡改内容。每次取得的内容都要对照其哈希核对；`tape://` URL 由 TAP-10 客户端逐字节核验。容器的回退页面可能替缺失的文件作答；§8.6 要求集合不要设置回退路径。
- **出处不等于所有权。** 来源电路证明一份网表在某个区块时来自何处；它不赋予 NFT 持有人对该电路、其容器、其挖矿产出或任何 BEM 的任何主张。集合不得作出相反的暗示。
- **来源方的核验。** 以抽样向量进行的挖矿核验并不意味着功能正确；`TAP-draft-pod-attributes` 要求按质量标注网表的集合，用任务的参考电路核对它们。
- **不止一个伴生合约。** 集合的所有者可以为多个伴生合约背书，伴生合约无法阻止。工具应把最早获得背书的伴生合约视为正统，并标记其所有者为多个伴生合约背书的集合。
- **网表是公开数据。** 链上的每一份网表都可以被任何人读取并流片。网表绑定 NFT 不赋予对设计的任何独占性：它承载的是绑定关系、公平分配与出处。许可声明（`tap.license`）描述集合授予的权利，而不是它能够对抗副本的权利。
- **已承诺但格式错误的文件的求值。** 清单可能承诺了一个无效文件的哈希。对网表求值的合约在存储前检查有效性（§8.2 第 4 条），求值器必须对任何无法解码的字节串回滚。
- **可升级的来源合约。** 处理器合约是位于未封存工厂之后的信标代理（TAP-02 §3 与 Deployments）。之后的升级可能改变 `netlist(id)` 的返回值；核验者记录其读取的区块，具有权威性的是 NFT 的网表哈希，而不是链上的实时状态。
- **哈希选择。** SHA-256 碰撞遥不可及；格式版本字节与 `tapManifest` 允许将来更换。

### 开放问题

1. `tapnet/2` 是否应允许按某条确定规则展平的 REF 记录？如果允许，该规则应放在本 TAP 中，还是放在 `TAP-draft-netlist-structural-hash` 中？
2. 清单是否应要求按池而不是按代币给出许可？
3. 是否应为超过 49,152 字节的网表文件定义分段上传？
4. 是否应标准化一个最小的锁定合约接口（例如 `locked()`），使工具无需了解锁定合约的代码就能把容器显示为已锁定？
5. 是否应定义 `vrf` 种子来源？若定义，应以哪项 VRF 服务的哪个固定版本为准？

## 版权

版权及相关权利依 [CC0](../LICENSE) 放弃。
