# TAP-721 family checker (`tapfam`) / TAP-721 家族检查器

[中文](#中文) · [English](#english)

---

## 中文

`tapfam.py` 是 TAP-721 家族**工具侧展示规则**的参考实现：给定一枚代币，输出一份报告，报告的每一行都标注它所实现的草案章节。
它回答的是"一个钱包、市场或索引器按照这些草案**必须**怎样显示这枚代币"，而不是"这枚代币好不好"。

六份草案在报告中的缩写：`TAP-721`（Netlist-Bound NFTs，核心）、`TAP-SH`（结构哈希）、`TAP-DC`（设计署名）、
`TAP-SB`（灵魂绑定凭证）、`TAP-PoD`（PoD 属性）、`TAP-BR`（跨链）。

纯标准库，Python 3.9+。每条规则都是对各资产目录里参考实现的调用（`_paths.py`）：`tapnft.py`、`canon.py`、`canon2.py`、
`credits.py`、`soulbound.py`、`pod_validate.py`（后者需要 pycryptodome；缺失时 PoD 行报告为未检查）。这里不重新实现任何规则。

### 用法

```
python3 tapfam.py token --rpc URL [--source-rpc URL]... --contract 0x… --id N [--metadata FILE|URL] [--netlist FILE]
                        [--manifest FILE|URL] [--token-set FILE] [--collection-dir DIR] [--master-seed 0x…] [--json]
python3 tapfam.py metadata FILE [--netlist FILE] [--manifest FILE] [--collection-dir DIR]       # 只做离线检查
python3 tapfam.py bundle FILE [--source-rpc URL --source-rpc URL]                               # 署名包
python3 tapfam.py credential --rpc URL --contract 0x… --id N [--metadata FILE] [--artifact FILE] [--statement FILE]
任何子命令加 --offline [--fixture FILE]：所有链上读取来自录制夹具 fixtures/recorded-rpc.json
```

- 链访问只经由一个很小的 JSON-RPC 客户端（`chain.py`，urllib）：`eth_call`、`eth_getCode`、`eth_getBlockByNumber`、
  `eth_getTransactionReceipt`、`eth_getLogs`。**从不发送交易。** 每条链的读取都钉在一个区块上（终局性标签或最新块，TAP-10 §5）。
- `--rpc` 是集合所在链的节点；`--source-rpc` 是来源链（如 BNB Smart Chain）的节点，署名事实的核验（TAP-DC §3.2）要求同一条链给出**两个**节点。
- `--metadata` 省略时从 `tokenURI` 取；`--netlist`/`--manifest` 省略时在线模式按 `uris` 抓取 https（其他 scheme 不解析）。
- 退出码：有任何 MUST 级失败（状态 `fail`）为 1，否则 0。`--json` 输出 `tap-family-checker-report/1`。

### 报告的每一行

格式：`[草案 §章节] 键: 状态 — 文字`。状态：`ok`/`fail` 是检查结果；`warn` 是 SHOULD 级发现或未成立的交叉核对；`info` 是展示的事实；
`unverifiable` 是本工具不支持的网表格式（TAP-721 §2.5，不是无效，也绝不显示为已验证）；`unverified` 是未能核验的事实或主张（绝不显示为已验证）；
`skip` 是没有运行的检查（缺文件、缺 RPC、夹具里没有）。

| 键 | 规则 | 含义 |
|---|---|---|
| `metadata` | TAP-721 §7.1–§7.3 | `tapnft.check_metadata`：不需网络的元数据规则；失败即无效 |
| `token.id` | §4.1 / TAP-BR §5.3 | CAIP-19 标识；与所查代币不符则 `fail`，除非合约是跨链副本（副本的 `tap.id` 指向主链代币） |
| `manifest.declared` | §5.1 / §8.1 | 有无 `tap.manifest`：无清单的集合在铸造时绑定内容、不形成版次 |
| `freeze.probe` | §5.1 | `tap.freeze` 只命名一个检查，不是状态；冻结状态从链上读（§7.2） |
| `netlist.declared` | §7.1 / §2.5 | 声明的网表；非 `tapnet/1` 格式显示为 `unverifiable` |
| `erc165`, `level` | §8, §8.1–§8.3; TAP-SB §10.1 | 通过 ERC-165 判定等级（绝不凭选择器存在判定）。L1 = ITapNetlistNFT + ERC-165 + ERC-4906；经 companion 达到 L1 需双向绑定；L0 标注 "L0 (metadata only)"，无清单再加 "no manifest: content not committed"；凭证合约标 "L0 (metadata only); metadata can change" |
| `netlist.file` | §7.4 / §2.2 / §2.5 | 抓到的文件：哈希、有效性、度量三者相符才 `ok`；其他格式按 §2.5 给 `unverifiable` 或 `fail`（原因在文字里） |
| `structural.hash`, `structural.declared` | TAP-SH §7, §9, §10 | 结构哈希 v1（`tapnet/1` 下 v2 与 v1 相同）；与 `tap.netlist.structuralHash` 比对；并声明"只标识结构，不说明功能或度量" |
| `source.check`, `source.name`, `source.container` | §3.2, §3.1 | 工厂 `isCPU`、`circuitInfo`+`netlist` 重建文件并比对哈希（先按声明区块读，读不到再按钉定区块，并说明）；链上名；容器地址必须等于 opener 的 `accountOf`，不接受仅被报告的地址 |
| `profile` | §8.2; TAP-BR §5.3 | 有清单 / mint-bound（`manifestHash()`、`masterSeed()` 为零且 `pools()` 为空、元数据无 `tap.manifest`）/ 跨链副本（报告 ITapBridgeMirror）/ 清单尚未提交 |
| `manifest.onchain` | §7.1 | `tap.manifest.sha256` 必须等于非零的 `manifestHash()` |
| `state.chain`, `state.consistency` | §7.2, §8.2 第 2 条 | 揭示状态从链上推导：种子为零=未揭示，全 1=`none` 来源已视作设定，否则已揭示；与 `tap.state` 交叉比对 |
| `frozen` | §7.2, §8.2 第 5 条, §8.1 | L1 读 `frozen()`（忽略 `tap.freeze`）；L0 读清单的 `freeze` 探针，无清单时读 `tap.freeze` 探针（有清单时不用 `tap.freeze`） |
| `netlist.onchain`, `image.onchain` | §8.2 | `netlistHashOf`/`imageHashOf` 必须等于元数据；零表示尚未绑定或该字段不由池承载 |
| `coverage` | §8.2, §8.5, §5.4 | 范围模式看 `tokenRange()`；集合模式由 `tokenSetHash()` 非零判定并用 `indexOf` |
| `manifest.file`, `tokenset.file`, `pools.onchain` | §5.1–§5.4, §6.1, §8.2 第 1 条 | `tapnft.check_manifest`；哈希；集合模式的 token 集合文件；`pools()` 与清单逐项相等 |
| `assignment`, `image.entry`, `netlist.entry` | §6.2–§6.3, §7.3 第 3 条, §8.2 第 2 条 | 用主种子重算该代币分到的条目，与 `entryIndexOf` 和元数据哈希比对；集合外代币不显示为等待揭示 |
| `edition.declared`, `edition.check`, `collection.*` | §6.4, §7.3 第 3 条, §7.1, §5.1 | 版次只能在全集合层面核对（`--collection-dir`）；同时检查全集合的 `tap.manifest` 一致性和 `tap.freeze` 一致性；无清单不形成版次；其他格式 `unverifiable` |
| `pod.format` … `pod.notice` | TAP-PoD §3.7, §3.1, §3.4, §3.5, §3.9, §7, §2 第 4 条 | 快照格式（含清单承诺 §4.4）；`standing` 值一律带快照区块、不作为当前值；`verified` 只是抽样状态；功能检查只有 `match` 才说"正确"；来源未确认时所有 PoD 事实标 "declared by the collection, not verified" |
| `pod.verify` | §4.2 | 在快照区块重读全部 getter：`confirmed` / `mismatch` / `unavailable`（绝不用别的区块报 confirmed） |
| `pod.traits` | §5.4 | 合约报告 ERC-7496 时读 15 个 trait，与 `tap.pod` 不一致即 mismatch |
| `rig` | §6 | "related rig voucher (informative)"，不验证，不暗示持有或收益 |
| `bridge.declared`, `bridge.gateway` | TAP-BR §5.2, §3 | 网关的 `homeChainId()` 与 `collectionKey()` 必须匹配集合 |
| `credits.bundle`, `credits.fact`, `credits.claim`, `credits.claims`, `credits.earliest`, `credits.revoked` | TAP-DC §5.1, §3.2, §4.6–§4.7, §6.1–§6.4 | 事实只有通过 §3.2（两个节点、回执、区块、铸造日志、终局性）才显示为 `[verified fact]`，并用 "first taped out by"（绝不用 designer/author）；主张一律带 `[claim]`、角色/关系、签名者地址，`displayName` 标为自声明；说明主张命名的是精确文件还是结构；按角色统计数目且不选出"设计者"；最早出现只说"earliest known"；撤销的不显示为生效 |
| `credential.*` | TAP-SB §3.1, §8, §9, §10 | ERC-165 必须报 ERC-721/ERC-5192/ITapCredential、不得报 ERC-4906；`credentialOf` 记录优先于元数据；标签：Proven per contract (not re-checked) / Proven: passes its specification (re-checked)（给 `--artifact` 重算 §4.6）/ Attested by 0x…（issuer identity not verified）/ Self-claimed；非 active 状态必须显示，superseded 链接到替代代币；"unverified contract" 除非 `--known-code-hash` 匹配；等级行固定为 L0 并注明 "metadata can change"，`netlistHashOf` 等于 `tap.netlist.sha256` 时加 "artifact recorded by the credential contract"；绝不显示 L1 或 "verified on chain" |
| `verdict` | §7.4 / §2.5 | 网表文件核对通过且无 MUST 失败才称 "checked netlist-bound NFT"；L0 另注"not shown as verified on chain" |

### 已实现 / 未实现

已实现的展示规则：上表全部。未实现（报告里以 `skip`/`unverified` 明示，不会伪装成已验证）：

- TAP-721 §5.1 清单发布时间（`FileSet` / `ManifestCommitted` 的区块早于种子可知的时刻）和 §6.1 第 7 条 drand 种子核验：需要容器事件扫描和 drand 中继，超出"一枚代币一次读取"的范围（`tools/collection/verify_collection.py` 做 drand 部分）。
- TAP-721 §7.5 容器内容读取与 §8.6 锁状态：需要 TAP-10 站点存储读取，这里只展示声明。
- TAP-DC §5.2 锚点：不读取 `CreditPosted` 日志，锚定的主张按未锚定排序，并说明。
- TAP-DC §4.6 在线的容器签名者判定（TAP-10 §4.3）：离线用夹具表；在线不判定，主张不会得到 "container of N" 标签。
- TAP-SB §10.1 第 4 条合约代码核验：没有已知部署，只提供 `--known-code-hash` 比对；默认一律 "unverified contract"。
- TAP-SB §10.4 claimed 凭证的 statement：需要 `--statement` 给出 envelope（在线则按 `uris` 抓 https）。
- PoD §4.2 的双节点核对与 single-source 报告：离线夹具只有一组读数；在线按一个节点读。
- 来源验证（§3.2）只知道 BNB Smart Chain 的工厂与 opener（docs/FACTS.md）；其他链报 "not known to this tool"。
- TAP-721 §7.3 第 1 条 / §4.2 图片字节：不抓取 ERC-721 `image` 和 `tap.image.uris` 的字节与 `tap.image.sha256` 比对（离线模式无法抓取；§7.4 的最低要求只涉及网表文件），只比对 `imageHashOf` 与池条目。
- TAP-BR §11 / Security：不读取端点是否已封印、各路由的策略和主链集合的权力（升级、销毁），这些是端点层面的读取，超出一枚代币的范围。

### 离线夹具与测试

`make_fixture.py` 生成 `fixtures/recorded-rpc.json`（`--check` 校验字节一致）。其中 **recorded** 部分是仓库里已有的真实读数重新编码为 JSON-RPC 答案：
`assets/tap-draft-design-credits/chain-reads.json`（区块 128,542,889）和 `assets/tap-draft-netlist-bound-nft/chain-snapshot.json`（区块 128,200,681）；
**synthetic** 部分是不存在于任何链上的合约，按参考合约对向量的应答构造（`synthetic` 成员列出地址）：8 枚代币的示例集合（L1，0x…aa）、mint-bound 合约（0x…bb）、
带 `uriFrozen()` 的 L0 合约（0x…cc）、跨链副本（0x…ee）、灵魂绑定参考合约在向量 scenario 结束后的状态（链 31337，0x…c1）。

`python3 test_family_checker.py`：47 个测试，全部离线——示例 8 枚代币的完整报告、`noManifest` 与 `otherFormats` 向量、版次与清单一致性篡改、
全集合 `tap.freeze` 探针不一致时 `token` 不报告冻结、署名包与展示排序场景、凭证 7 枚代币的标签与状态、PoD 真实快照在录制读数下 `confirmed`、
合成的 "verified but wrong"、结构哈希向量、跨链 collection key 向量、ABI 编解码。CI 的 Python 矩阵运行它（缺 pycryptodome 时 PoD 的 5 个测试跳过）。

### 完整示例报告（示例集合代币 4，离线）

```
$ python3 tapfam.py token --offline --contract 0x00000000000000000000000000000000000000aa --id 4 \
    --metadata ../../assets/tap-draft-netlist-bound-nft/example/token/4.json \
    --netlist ../../assets/tap-draft-netlist-bound-nft/example/netlists/ecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e.tapnet \
    --manifest ../../assets/tap-draft-netlist-bound-nft/example/manifest.json \
    --collection-dir ../../assets/tap-draft-netlist-bound-nft/example/token
# tapfam token
[TAP-721 §7.1] metadata.source: info — ../../assets/tap-draft-netlist-bound-nft/example/token/4.json (1377 bytes)
[TAP-721 §7.1] metadata: ok — the tap member follows §7.1–§7.3 (offline rules)
[TAP-721 §4.1] token.id: info — eip155:196/erc721:0x00000000000000000000000000000000000000aa/4
[TAP-721 §7.2] state.declared: info — tap.state = revealed
[TAP-721 §5.1] manifest.declared: info — tap.manifest.sha256 = 0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983 (content committed by a manifest)
[TAP-721 §7.1] netlist.declared: info — tapnet/1 0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e (44 bytes, nIn 2, nOut 1, nand 4, latch 0)
[TAP-721 §6.4] edition.declared: info — edition 1/3 (declared)
[TAP-721 §3.1] source.declared: info — 17851.30.tape on chain 56 at block 128200681 (provenance only: no right over the source circuit, §3.2)
[TAP-721 §8] erc165: info — reported: ERC165, ERC721, ERC4906, ITapNetlistNFT (chain 196 at block 73600000 (recorded fixture))
[TAP-721 §8.2] level: ok — L1 (on-chain interface): ITapNetlistNFT, ERC-165 and ERC-4906 reported
[TAP-721 §7.4] netlist.file: ok — file hashes to tap.netlist.sha256, is a valid tapnet/1 file (§2.2) and its metrics match (nIn 2, nOut 1, nand 4, latch 0, gates 4)
[TAP-SH §7] structural.hash: info — structural hash 0x74db11f36d199cb879579afd309cf617144eeddea574fba590c088fbf2fc559b (version 2 equals version 1 for a tapnet/1 file, §10.1); identifies structure only: it says nothing about function or metrics (§9 item 3)
[TAP-721 §3.2] source.check: ok — source confirmed: isCPU at block 128542889; circuitInfo/netlist read at the declared block, block 128200681, rebuild to 0xecb6f09704b29cd02c9e5255b41c4a3139e0dca1a172782bea855db91cde073e
[TAP-721 §3.1] source.name: ok — on-chain name 17851.30.tape matches cpuAt(30)
[TAP-721 §8.2] profile: info — collection with a manifest: manifestHash() = 0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983, 2 pool(s) committed
[TAP-721 §7.1] manifest.onchain: ok — tap.manifest.sha256 equals manifestHash()
[TAP-721 §7.2] state.chain: info — revealed on chain: masterSeed() = 0x000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
[TAP-721 §7.2] frozen: ok — frozen: frozen() returns true (manifest committed, seed set, nothing can change; latched)
[TAP-721 §8.2] netlist.onchain: ok — netlistHashOf() equals tap.netlist.sha256
[TAP-721 §8.2] image.onchain: ok — imageHashOf() equals tap.image.sha256
[TAP-721 §8.2] coverage: ok — token in tokenRange() 1…8, index 3
[TAP-721 §5.1] manifest.file: ok — manifest 0x231570124fd096137b329f71472ce4ac06c8195f457c20d485bfce4605ca5983 valid (§5.1–§5.2 and §6.1 parameters): range 1…8, reveal drand, pools ['IMAGE_V1', 'NETLIST_V1']
[TAP-721 §8.2] pools.onchain: ok — pools() equals the manifest's pools (label, field mask, root; item 1)
[TAP-721 §6.3] assignment: ok — pool 'IMAGE_V1': entry 0; entryIndexOf(4, 0) = 0
[TAP-721 §7.3] image.entry: ok — tap.image.sha256 equals the pool entry's image value (item 3)
[TAP-721 §6.3] assignment: ok — pool 'NETLIST_V1': entry 6; entryIndexOf(4, 1) = 6
[TAP-721 §7.3] netlist.entry: ok — tap.netlist.sha256 equals the pool entry's netlist value (item 3)
[TAP-721 §7.3] collection.size: info — 8 token metadata files from ../../assets/tap-draft-netlist-bound-nft/example/token
[TAP-721 §7.1] collection.manifest: ok — every token carries the same tap.manifest.sha256
[TAP-721 §6.4] edition.check: ok — editions of every netlist hash are consistent across the collection (§7.3 item 3)
[TAP-721 §7.4] verdict: ok — checked netlist-bound NFT at L1
# ok 19, info 12
# verdict: no MUST-level failure
```

（示例集合的合约 0x…aa 是夹具里的合成合约：链 196 上不存在它；来源电路 17851.30.tape 的读数是真实的 BNB Smart Chain 录制读数。）

---

## English

`tapfam.py` is the reference implementation of the **tool-side display rules** of the TAP-721 family: given one token it prints a report
whose every line is tagged with the section of the draft it implements. It answers "how MUST a wallet, marketplace or indexer display
this token under these drafts", not "is this token good".

Draft abbreviations in the report: `TAP-721` (Netlist-Bound NFTs, the core), `TAP-SH` (structural hash), `TAP-DC` (design credits),
`TAP-SB` (soulbound credentials), `TAP-PoD` (PoD attributes), `TAP-BR` (bridging).

Standard library only, Python 3.9+. Every rule is a call into the reference modules of the asset folders (`_paths.py`): `tapnft.py`,
`canon.py`, `canon2.py`, `credits.py`, `soulbound.py`, `pod_validate.py` (the last needs pycryptodome; without it the PoD lines are
reported as not checked). Nothing is reimplemented here.

### Usage

```
python3 tapfam.py token --rpc URL [--source-rpc URL]... --contract 0x… --id N [--metadata FILE|URL] [--netlist FILE]
                        [--manifest FILE|URL] [--token-set FILE] [--collection-dir DIR] [--master-seed 0x…] [--json]
python3 tapfam.py metadata FILE [--netlist FILE] [--manifest FILE] [--collection-dir DIR]       # offline checks only
python3 tapfam.py bundle FILE [--source-rpc URL --source-rpc URL]                               # a credit bundle
python3 tapfam.py credential --rpc URL --contract 0x… --id N [--metadata FILE] [--artifact FILE] [--statement FILE]
any subcommand with --offline [--fixture FILE]: every chain read comes from the recorded fixture fixtures/recorded-rpc.json
```

- Chain access goes only through a tiny JSON-RPC client (`chain.py`, urllib): `eth_call`, `eth_getCode`, `eth_getBlockByNumber`,
  `eth_getTransactionReceipt`, `eth_getLogs`. **No transaction is ever sent.** Every read of a chain is pinned to one block (the finality
  tag, or the latest block; TAP-10 §5).
- `--rpc` is a node of the collection's chain; `--source-rpc` a node of a source chain (BNB Smart Chain, say). Verifying a publication fact
  (TAP-DC §3.2) needs **two** nodes of the fact's chain.
- Without `--metadata` the document comes from `tokenURI`; without `--netlist`/`--manifest` the online mode fetches https `uris` (other
  schemes are not resolved).
- Exit status 1 when any MUST-level check failed (status `fail`), else 0. `--json` prints a `tap-family-checker-report/1` document.

### Every line of the report

Format: `[draft §section] key: status — text`. Statuses: `ok`/`fail` is the outcome of a check; `warn` a SHOULD-level finding or a
cross-check that did not hold; `info` a displayed fact; `unverifiable` a netlist in a format this tool does not support (TAP-721 §2.5:
not invalid, and never shown as verified); `unverified` a fact or claim the tool could not verify (never shown as verified); `skip` a
check that was not run (no file, no RPC, nothing recorded).

| Key | Rule | Meaning |
|---|---|---|
| `metadata` | TAP-721 §7.1–§7.3 | `tapnft.check_metadata`: the metadata rules that need no network; a failure makes the token invalid |
| `token.id` | §4.1 / TAP-BR §5.3 | CAIP-19 identifier; `fail` when it is not the token asked for, unless the contract is a bridged copy (its `tap.id` names the home token) |
| `manifest.declared` | §5.1 / §8.1 | whether `tap.manifest` is present: a collection without a manifest binds content at mint and forms no editions |
| `freeze.probe` | §5.1 | `tap.freeze` names a check, not a state; the frozen state is read from the chain (§7.2) |
| `netlist.declared` | §7.1 / §2.5 | the declared netlist; a format other than `tapnet/1` is shown as `unverifiable` |
| `erc165`, `level` | §8, §8.1–§8.3; TAP-SB §10.1 | the level is decided by ERC-165, never by the presence of selectors. L1 = ITapNetlistNFT + ERC-165 + ERC-4906; L1 through a companion needs the two-way binding; L0 is labelled "L0 (metadata only)", plus "no manifest: content not committed" without a manifest; a credential contract gets "L0 (metadata only); metadata can change" |
| `netlist.file` | §7.4 / §2.2 / §2.5 | the fetched file: `ok` only when hash, validity and metrics all match; other formats get `unverifiable` or `fail` per §2.5, with the reason |
| `structural.hash`, `structural.declared` | TAP-SH §7, §9, §10 | structural hash v1 (v2 equals v1 for a `tapnet/1` file); compared with `tap.netlist.structuralHash`; stated as identifying structure only, nothing about function or metrics |
| `source.check`, `source.name`, `source.container` | §3.2, §3.1 | factory `isCPU`; the file rebuilt from `circuitInfo` + `netlist` must hash to the declared hash (read at the declared block, else at the pinned block, and the report says which); on-chain name; a declared container must equal the opener's `accountOf`, a merely reported address is not accepted |
| `profile` | §8.2; TAP-BR §5.3 | with a manifest / mint-bound (`manifestHash()` and `masterSeed()` zero, `pools()` empty, no `tap.manifest`) / bridged copy (ITapBridgeMirror reported) / manifest not yet committed |
| `manifest.onchain` | §7.1 | `tap.manifest.sha256` must equal a non-zero `manifestHash()` |
| `state.chain`, `state.consistency` | §7.2, §8.2 item 2 | the reveal state is derived from the chain: seed zero = not revealed, all-ones = source `none` counts as set, else revealed; cross-checked with `tap.state` |
| `frozen` | §7.2, §8.2 item 5, §8.1 | L1 reads `frozen()` (and ignores `tap.freeze`); L0 reads the manifest's `freeze` probe, or `tap.freeze` only without a manifest |
| `netlist.onchain`, `image.onchain` | §8.2 | `netlistHashOf`/`imageHashOf` must equal the metadata; zero means not bound yet or a field no pool carries |
| `coverage` | §8.2, §8.5, §5.4 | range mode from `tokenRange()`; set mode is told by a non-zero `tokenSetHash()` and uses `indexOf` |
| `manifest.file`, `tokenset.file`, `pools.onchain` | §5.1–§5.4, §6.1, §8.2 item 1 | `tapnft.check_manifest`; the hash; the token set file in set mode; `pools()` equal to the manifest's pools |
| `assignment`, `image.entry`, `netlist.entry` | §6.2–§6.3, §7.3 item 3, §8.2 item 2 | the token's entries recomputed from the master seed, compared with `entryIndexOf` and with the metadata hashes; a token outside the token set is not shown as awaiting a reveal |
| `edition.declared`, `edition.check`, `collection.*` | §6.4, §7.3 item 3, §7.1, §5.1 | editions can only be checked across the collection (`--collection-dir`), together with the collection-wide `tap.manifest` and `tap.freeze` consistency; no editions without a manifest; `unverifiable` for other formats |
| `pod.format` … `pod.notice` | TAP-PoD §3.7, §3.1, §3.4, §3.5, §3.9, §7, §2 item 4 | snapshot well-formedness (and the manifest commitments of §4.4); every `standing` value carries its snapshot block and is never presented as current; `verified` is the sampling status only; a netlist is called correct only on a functional-check `match`; while the source is not confirmed every PoD fact is "declared by the collection, not verified" |
| `pod.verify` | §4.2 | every getter re-read at the snapshot block: `confirmed` / `mismatch` / `unavailable` (never confirmed from another block) |
| `pod.traits` | §5.4 | when the contract reports ERC-7496, the fifteen traits are read and a disagreement with `tap.pod` is a mismatch |
| `rig` | §6 | "related rig voucher (informative)": not verified, implies no holding or benefit |
| `bridge.declared`, `bridge.gateway` | TAP-BR §5.2, §3 | the gateway's `homeChainId()` and `collectionKey()` must match the collection |
| `credits.bundle`, `credits.fact`, `credits.claim`, `credits.claims`, `credits.earliest`, `credits.revoked` | TAP-DC §5.1, §3.2, §4.6–§4.7, §6.1–§6.4 | a fact is `[verified fact]` only after §3.2 (two nodes, receipt, header, mint log, finality) and reads "first taped out by" (never designer/author); every claim carries `[claim]`, its role or relation and its signer, `displayName` marked self-declared; whether the claim names an exact file or a structure; counts per role and no claim selected as the designer; an earliest occurrence is only "earliest known"; revoked statements are not shown as active |
| `credential.*` | TAP-SB §3.1, §8, §9, §10 | ERC-165 must report ERC-721/ERC-5192/ITapCredential and must not report ERC-4906; the `credentialOf` record prevails over the metadata; labels Proven per contract (not re-checked) / Proven: passes its specification (re-checked) (with `--artifact`, §4.6 recomputed) / Attested by 0x… (issuer identity not verified) / Self-claimed; a status other than active is always shown, superseded links to the replacement; "unverified contract" unless `--known-code-hash` matches; the level line is always L0 with "metadata can change", plus "artifact recorded by the credential contract" when `netlistHashOf` equals `tap.netlist.sha256`; never L1, never "verified on chain" |
| `verdict` | §7.4 / §2.5 | "checked netlist-bound NFT" only when the netlist file passed and nothing failed; an L0 token adds "not shown as verified on chain" |

### Implemented / not implemented

Implemented: everything in the table. Not implemented (the report says so with `skip`/`unverified`; nothing is ever dressed up as verified):

- TAP-721 §5.1 publication time of the manifest (the `FileSet` / `ManifestCommitted` block before the seed became known) and §6.1 item 7
  drand seed checks: they need a container event scan and drand relays, beyond one token's reads (`tools/collection/verify_collection.py`
  covers the drand part).
- TAP-721 §7.5 container reads and §8.6 lock status: they need TAP-10 site-store reads; only the declaration is shown.
- TAP-DC §5.2 anchors: `CreditPosted` logs are not read; anchored claims are ordered as unanchored, and the report says so.
- TAP-DC §4.6 online container-signer detection (TAP-10 §4.3): offline from the fixture table; online not performed, so no claim gets the
  "container of N" label.
- TAP-SB §10.1 item 4 code verification: no known deployment exists; `--known-code-hash` compares a keccak of the runtime code; by default
  every credential is "unverified contract".
- TAP-SB §10.4 the statement of a claimed credential needs its envelope (`--statement`, or https `uris` online).
- PoD §4.2 two-operator reads and single-source reporting: the fixture holds one set of reads; online one node is read.
- Source verification (§3.2) knows the factory and opener of BNB Smart Chain only (docs/FACTS.md); other chains get "not known to this tool".
- TAP-721 §7.3 item 1 / §4.2 image bytes: the bytes behind the ERC-721 `image` and `tap.image.uris` are not fetched and hashed against
  `tap.image.sha256` (no fetch offline; §7.4's minimum concerns the netlist file); only `imageHashOf` and the pool entry are compared.
- TAP-BR §11 / Security: whether the endpoints are sealed, each route's policy and the home collection's powers (upgrade, burn) are not
  shown; they are endpoint-level reads beyond one token.

### Offline fixture and tests

`make_fixture.py` writes `fixtures/recorded-rpc.json` (`--check` compares bytes). Its **recorded** part re-encodes real reads already in
this repository as JSON-RPC answers: `assets/tap-draft-design-credits/chain-reads.json` (block 128,542,889) and
`assets/tap-draft-netlist-bound-nft/chain-snapshot.json` (block 128,200,681). Its **synthetic** part is contracts that exist on no chain,
answering as the reference contracts do for the vectors (the `synthetic` member lists the addresses): the eight-token worked example as an
L1 collection (0x…aa), a mint-bound contract (0x…bb), an L0 contract with `uriFrozen()` (0x…cc), a bridged copy (0x…ee), and the soulbound
reference contract after the vectors' scenario (chain 31337, 0x…c1).

`python3 test_family_checker.py`: 47 tests, all offline — the full report of each of the eight example tokens, the `noManifest` and
`otherFormats` vectors, tampered editions and manifest consistency, no freeze reported by `token` when a collection's `tap.freeze` probes
differ, the credit bundle and the display-order scenario, the labels and statuses of seven credential tokens, real PoD snapshots
`confirmed` against the recorded reads, the synthetic "verified but wrong" case, the structural-hash vectors, the bridging collection-key
vectors, and the ABI helpers. CI runs it in the Python matrix (without pycryptodome the five PoD tests are skipped).

The full example report (example token 4, offline) is shown in the Chinese section above; the contract 0x…aa is the fixture's synthetic
L1 collection, while the reads for the source circuit 17851.30.tape are real recorded BNB Smart Chain reads.
