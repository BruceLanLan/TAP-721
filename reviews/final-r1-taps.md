# Final review r1: TAP-721 family (editor pass)

Reviewer: final-round editor (read-only). Date: 2026-10-18.
Scope: `TAPs/TAP-draft-netlist-bound-nft.md` (core, TAP-721), `TAP-draft-netlist-nft-bridging.md` (B), `TAP-draft-pod-attributes.md` (C), `TAP-draft-netlist-structural-hash.md` (D), and their `.zh.md` files. Rules: TAP-template.md, TAP-01 §6–§7, CONTRIBUTING §2–§4 and §6.

**Verdict: not ready to submit. 4 Blockers, 13 Should, 12 Nits.** None of the Blockers needs a change of design. Each one is a text or process fix.

ZH line numbers: every `.zh.md` file runs exactly **+2 lines** from its English file (a header line and a blank line). Where a fix applies to both, the ZH line is given as "ZH +2" and the ZH text gets the same change in translation.

---

## What was checked and passed

| Check | Method | Result |
|---|---|---|
| Section order and presence (TAP-01 §7.2) | Heading dump of all 8 files | All 8 files follow Summary → … → Copyright. The optional sections (Backwards Compatibility, Deployments) are present. |
| Preamble fields | Compared with TAP-01 §7.1 | All required fields are present. `type` is correct (core, B and D are Standards; C is Application). `license: CC0-1.0`. Exception: `discussions-to` (B-4). |
| RFC 2119 keywords outside Specification | Script over 8 files, section-aware | 0 hits |
| EN/ZH structure parity | Script: heading count and level, per-section counts of tables, lists and code blocks, hex values, `§` refs, backtick tokens | All match. Heading counts: 49/49, 34/34, 22/22, 39/39. Hex values are identical in every section. The only differences are the ZH translator notes and number formatting (1300万 for 13.0 million). |
| Function selectors (core 31, B 50+, C 13, ERC-7496 4, LayerZero/hub 21) | `cast sig` | All correct |
| ERC-165 ids | XOR of the selectors | `0x282b67f6`, `0x3f7177c7`, `0x12b40a6c`, `0xec7d7e20`, `0x3d6a52e3`, `0xdbc2d1d3`, `0xdba6a55e`, `0xaa621a3e`, `0xceebf7ce` and ERC-7496 `0xaf332f3e`: all correct |
| Event topics and other keccak values | `cast keccak` | All correct: 7 core topics plus `FileSet`, 6 bridge topics, `AdapterSealed`, both layer ids, the collection key, and the 15 trait keys |
| B §4.3 worked example | Recomputed with `cast` and `shasum` | All three hashes, `keccak256(payload)` and `messageId` match. The LayerZero option bytes match. |
| Vector-file hashes against `assets/*/README.md` | `shasum -a 256` plus regeneration in the scratchpad | B, C and D match. **Core does not match (B-2).** |
| Core §7.1 example | Compared with `assets/tap-netlist-bound-nft/example/token/4.json` | Matches. The manifest hash `0x2315…5983` equals the SHA-256 of `example/manifest.json`. |
| Miner ids, functions and counts | Compared with `vectors.json`, `chain-snapshot.json` and the snapshot tables | Consistent across core, C and D. #17851 XOR (task 3, 4 NAND). #17852 Johnson counter (task 220, NAND/LATCH 1/9, nIn/nOut 0/8). #3151 popcount8 (task 48, 55 NAND, 51 live). #38 REF, rejected. Slot holders #906/#2033/#14947 match `optimalHolders`. All cost, bonus and weight formulas recompute. The `verifiedButWrong` example also recomputes (the real instance is withheld in the public copy; see the PoD TAP). |
| `TAP-02 §…`, `TAP-10 §…`, `TAP-01 §…` references | Script against the heading sets of TAP-02.md, TAP-10.md and TAP-01.md in the scratchpad | All resolve. Meaning spot-checked: TAP-10 §8.8, §12.1, §13.x, §17, §18.3, Appendix A; TAP-02 §3 (no setter), §7 requirements 1–2. |
| "four TAPs" wording | grep EN and ZH | None found. Core:538 "for four reasons" is about reasons, not TAPs. |

---

## Blockers

### B-1. Summary is two sentences in all three extensions (CONTRIBUTING §4: "the Summary is one sentence")

**B: `TAP-draft-netlist-nft-bridging.md:20`** (ZH +2)
> This TAP is an extension of TAP-721 (Netlist-Bound NFTs) that adds cross-chain transfer. It lets the owner of a TAP-721 token move it …

Replace with:
> This TAP extends TAP-721 (Netlist-Bound NFTs) so that the owner of a TAP-721 token can move it from the chain where it was created to another TapeOut chain and back, with its netlist and image, while only one usable copy exists at any time.

ZH: `本 TAP 扩展 TAP-721（网表绑定 NFT），让 TAP-721 代币的持有人可以把它从创建它的链转移到另一条 TapeOut 链再转回来，网表和图像随之同行，且任何时刻只存在一份可用的副本。`

**D: `TAP-draft-netlist-structural-hash.md:20`** (ZH +2)
> This TAP is an extension of TAP-721 (Netlist-Bound NFTs) that adds a structural hash of netlists. It gives every flat TapeOut netlist a fingerprint …

Replace with:
> This TAP extends TAP-721 (Netlist-Bound NFTs) with a fingerprint for every flat TapeOut netlist that stays the same when the same design is merely renumbered, reordered, padded with unused gates or duplicated, so that such copies cannot be passed off as different designs.

ZH: `本 TAP 扩展 TAP-721（网表绑定 NFT），为每份扁平 TapeOut 网表提供一个指纹：同一设计只是被重新编号、重新排序、填充了不用的门或被复制时，指纹保持不变，因此这样的副本无法冒充成不同的设计。`

**C: `TAP-draft-pod-attributes.md:20`** (ZH +2)
> This TAP is an extension of TAP-721 (Netlist-Bound NFTs) that adds Proof-of-Design attributes. It lets a TAP-721 token built from a TapeOut mining circuit show …

Replace with:
> This TAP extends TAP-721 (Netlist-Bound NFTs) so that a TAP-721 token built from a TapeOut mining circuit can show how that circuit scored in Proof-of-Design mining, as a dated record that anyone can check against the chain, without suggesting that the NFT earns or owns anything.

ZH: `本 TAP 扩展 TAP-721（网表绑定 NFT），让由 TapeOut 挖矿电路制成的 TAP-721 代币能够展示该电路在设计证明（PoD）挖矿中的成绩，形式是一份任何人都能对照链上核查的、标明日期的记录，同时不暗示该 NFT 会赚取或拥有任何东西。`

(The core Summary at core:18 is already one sentence.)

### B-2. Core Test Cases gives the wrong SHA-256 for `vectors.json`

**`TAP-draft-netlist-bound-nft.md:548`** (ZH 550)
> … reproducible byte for byte, with SHA-256 `16c45ff3b3ec0172dcd5cfcd86df0118ef8438077d8b4d78d3d65bd93ea708f0`.

The actual file, `assets/tap-netlist-bound-nft/README.md`, and a fresh run of `make_vectors.py` in the scratchpad all give `bb77433f2d3a5e89267eb590206beb2d17a67158ba4ad1f317ed663645dfb3fe`. Replace with:
> … reproducible byte for byte, with SHA-256 `bb77433f2d3a5e89267eb590206beb2d17a67158ba4ad1f317ed663645dfb3fe`.

Apply the same fix to the ZH line. Recheck this value after any later regeneration.

### B-3. The number request contradicts itself across drafts and conflicts with TAP-01 §6.1 / CONTRIBUTING §3 item 3

- **core:22** (ZH 24) and **core:32** (ZH 34): "if the editors assign another number, the community name TAP-721 stays."
- **bridging:402** (ZH 404): "Once editors assign that draft a number, every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, will be replaced by that number."
- TAP-01 §6.1: "Authors do not pick their own numbers". Numbers are assigned as "the lowest number above 10 that is neither reserved nor already used". CONTRIBUTING §3 item 3: "Do not keep a self-assigned number."

The core says the name survives a different number; the bridging draft says it is replaced. The core position also conflicts directly with CONTRIBUTING §3 item 3, and the number 721 can only be granted as an editors' exception to TAP-01 §6.1. An editor will stop here. Use one position everywhere and phrase it as a request.

core:32, replace the last sentence with:
> This TAP aims to play the same role for netlist-bound NFTs on TapeOut chains. The authors therefore ask the editors to assign the number 721, so that it is known as TAP-721, mirroring ERC-721. Because TAP-01 §6.1 otherwise assigns the lowest free number above 10, this needs the editors' agreement. This text calls the standard "TAP-721" for readability; if another number is assigned, every occurrence is replaced by it.

core:22: delete the sentence "The authors request the number 721, … the community name TAP-721 stays." The Abstract does not need to repeat the Motivation.

bridging:402: keep as is (it now agrees with the core).

C and D: add the same body sentence as bridging:402 at the end of Backwards Compatibility (C:335, D:180). Today they carry it only in an HTML comment at line 14, which an editor applying CONTRIBUTING §3 item 3 may not see:
> This draft depends on TAP-721 (`TAP-draft-netlist-bound-nft`; 721 is the requested number) and is submitted after it. Once editors assign that draft a number, every reference to `TAP-draft-netlist-bound-nft` and to "TAP-721" here, including the `requires` field, will be replaced by that number.

### B-4. `discussions-to: TBD` in all 8 files

**core:6, bridging:6, pod:6, structural-hash:6** (ZH: the same line 6)
> discussions-to: TBD

TAP-01 §7.1 requires a URL. CONTRIBUTING §1 step 2 and §2 step 2 say to open the Idea issue first and set `discussions-to` to it. Replace with:
> discussions-to: https://github.com/TapeOutProtocol/TAPs/issues/<idea issue number>

This needs one Idea issue per TAP, or one issue that covers the family, with each draft linking to it. It is a process step plus a one-line edit ×8.

---

## Should

### S-1. Bridging Test Cases: a stale sentence contradicts the reference implementation and the preceding paragraph
**bridging:419** (ZH 421)
> The set-mode rule of §4.2 is not yet implemented by the reference gateway, which tests `tokenRange()` only, and has no test.

bridging:417 cites `AuditPass3.t.sol` "for token-set membership". `contracts/src/bridge/TapGateway.sol:70–88` implements the `tokenSetHash()` / `tokenAt(0)` / `indexOf` rule, and `contracts/test/audit/AuditPass3.t.sol:20` (`test_audit_gatewaySetModeUsesWrongRange`) tests it. Delete the sentence. The paragraph then ends at "…does not check that the container is opened."

### S-2. Core: "Every TAP-721 compliant contract MUST implement" contradicts L0 in the same paragraph
**core:38** (ZH 40)
> **Every TAP-721 compliant contract MUST implement the `ITapNetlistNFT` and ERC-165 interfaces** (and ERC-4906), subject to the rules of §8.2; this is conformance level L1. … an L0 collection implements no TAP-721 interface …

Replace the first sentence with:
> **Every L1 contract MUST implement the `ITapNetlistNFT` and ERC-165 interfaces** (and ERC-4906), subject to the rules of §8.2.

### S-3. Core: placeholder `image` wording contradicts §7.1's mandatory ERC-721 `image`
- core:310: the document "MUST contain the ERC-721 metadata members `name` and `image`".
- core:245 (ZH 247): "…and MAY carry a placeholder ERC-721 `image`."
- core:345 (ZH 347): "A placeholder `image` member MAY be present for a token awaiting a reveal and MUST be absent for a token outside the token set".

Read literally, §7.2 requires the ERC-721 `image` to be absent for an excluded token, while §7.1 requires it to be present. The reference validator (`tapnft.py:347, 362–366`) always requires the ERC-721 `image` and only forbids `tap.image`. Replace as follows.

core:245, "…and `tap.manifest`, and MAY carry a placeholder ERC-721 `image`." becomes:
> …and `tap.manifest`; its ERC-721 `image` (required by §7.1) is a placeholder.

core:345, "A placeholder `image` member MAY be present … MUST be absent for a token outside the token set;" becomes:
> A placeholder `tap.image` member MAY be present for a token awaiting a reveal and MUST be absent for a token outside the token set (§5.4); the ERC-721 `image` remains required (§7.1) and MAY be a placeholder;

### S-4. Cross-draft gap: the bridging gateway relies on `tokenAt(0)` reverting before the token set is recorded, but core §8.5 never says so
- bridging:106: "the gateway MUST revert (`NotBound`) unless `tokenAt(0)` succeeds, which shows that the token set file has been recorded on chain".
- core:481 says only that `entryIndexOf` reverts until the set is recorded. The `indexOf` comment (core:488) mentions "not recorded", and `tokenAt` says nothing.

Add to core:481, after "…checked against `tokenSet.sha256`.":
> Until then, `tokenAt` and `indexOf` MUST revert.

### S-5. Bridging: `homeContract()` is called but defined nowhere
**bridging:230**
> A client that finds it MUST check that the gateway's `homeContract()`, `homeChainId()` and `collectionKey()` match the collection …

`homeContract()` (`0xfdc70e0c`) is not in `ITapBridgeEndpoint` or in any table. Either add a row to the §5.1 `ITapBridgeEndpoint` table (`homeContract() returns (address)` | `0xfdc70e0c`), which changes the interface id from `0x3d6a52e3` to `0x3d6a52e3 ^ 0xfdc70e0c`, so the id, `vectors.json` and the reference implementation must be updated. Or rewrite the check without it:
> A client that finds it MUST check that the gateway's `homeChainId()` equals the chain of the collection and that its `collectionKey()` equals the key of §3 computed from that chain id and the collection address, before using it.

### S-6. Bridging §5.3: set-mode sentence stated twice, once without a keyword
**bridging:234** (ZH 236)
> A mirror of a collection whose manifest uses a token set (not a contiguous range) is deployed with `supply` = 0. A mirror of a collection in set mode (TAP-721 §5.4) MUST be deployed with `supply` = 0, because …

Delete the first sentence ("A mirror of a collection whose manifest uses a token set … is deployed with `supply` = 0.").

### S-7. "First TAP-721 collection(s)" asserts something that does not exist yet
- bridging:28 (ZH 30): "TapeCode-Test1, the first TAP-721 collection, is on X Layer"
- pod:28 (ZH 30): "The first TAP-721 collections draw their netlists from circuits that were mined under PoD."

Nothing is deployed or published yet (core:28 "Its founders want…"; bridging Deployments). Replace:
- bridging:28: "TapeCode-Test1, the collection that motivates TAP-721, is on X Layer"
- pod:28: "The collections that motivate TAP-721 draw their netlists from circuits that were mined under PoD."

### S-8. Financial or market wording (task bar: no financial language)
| Location | Quote | Replacement |
|---|---|---|
| core:22 (ZH 24) | "committed by Merkle roots before the sale" | "committed by Merkle roots before the reveal" |
| core:266 (ZH 268) | "and SHOULD warn holders in advance that blind listings become mispriced at that moment" | "and SHOULD warn holders in advance that from that moment anyone can compute every token's assignment" |
| core:594 (ZH 596) | "lets minters pick valuable tokens" | "lets minters pick the tokens they prefer" |
| core:595 (ZH 597) | "so blind listings are mispriced until metadata is updated" | "so listings made before the reveal no longer reflect public knowledge until metadata is updated" |
| bridging:36 (ZH 38) | "and high-value collections need the option to require two independent layers" | "and collections that do not want to rely on one layer need the option to require two independent layers" |
| bridging:473 (ZH 475) | "Collections that hold high value still use `ALL`" | "Collections that must not depend on a single layer still use `ALL`" |
| pod:298 (ZH 300) | "MUST NOT be used as an input to rarity, ranking or valuation (§8)" | "MUST NOT be used as an input to rarity or ranking (§8)" |

The disclaimers in pod §7 ("no yield", "investment or financial instrument") are prohibitions and should stay.

### S-9. Pod Test Cases does not inline its vector hash (the other three do)
**pod:339** (ZH 341)
> … reproduced byte for byte by the test suite (SHA-256 in the folder's README).

Replace with:
> … reproduced byte for byte by the test suite (SHA-256 `ade615b1a2e461d26bbf88b67eb93767eb88d26a189b824cf0c484108a4dbebb`; `trait-metadata.json` `336be474884b5cf2ce32ed77bdb05a75a02c8b96db1073e229fe287c6cdda0ac`).

### S-10. `requires` lists an external spec without a version (TAP-01 §7.1: "external specifications with their versions")
**core:10** (ZH 10): `requires: …, ERC-4906, CAIP-19`. core:152 pins CAIP-19 only "as published on 2026-10-18", which is not a fixed version. Replace with:
> requires: TAP-02, TAP-10, ERC-165, ERC-173, ERC-721, ERC-4906, CAIP-19 (ChainAgnostic/CAIPs commit <sha>)

Also update core:152 to "(CAIP-19, ChainAgnostic/CAIPs commit `<sha>`)".

### S-11. Reference implementations are not at a fixed commit "when submitted"
- core:582 (ZH 584): "Solidity: linked at a fixed commit of https://github.com/BruceLanLan/TAP-721 when submitted."
- bridging:423 (ZH 425): "In this repository (fixed commit TBD), Foundry project `contracts/` … Before the pull request, the project is either moved under `assets/tap-<nn>/` or linked here at a fixed commit…"

This is the submission, so "when submitted" means now. TAP-01 §7.2 item 8 allows this to wait until Review, but the text promises it for this point. Either insert the commit now ("…at commit `<40-hex sha>` of https://github.com/BruceLanLan/TAP-721") or reword to "will be linked at a fixed commit before Review (TAP-01 §7.2 item 8)". Do the same for bridging:423 and pod:365.

### S-12. Translations and the PR shape conflict with CONTRIBUTING §2 item 4 and §6
CONTRIBUTING §2 item 4 says a pull request "adds only that file (and its `assets/` files, if any)". §6 and TAP-01 §6.2 place translations at `TAPs/TAP-<nn>.<lang>.md`, which presupposes a number. Recommended:
1. Submit four PRs, core first. B, C and D can follow with `requires: TAP-draft-netlist-bound-nft` but cannot merge before the core has a number.
2. Keep the `.zh.md` files out of the first PRs, or say in each PR body that they are offered for convenience and will be renamed `TAP-<nn>.zh.md` on number assignment.

### S-13. Shared assets cross folder boundaries that will be renamed to `assets/tap-<nn>/`
- D:226: `canon.py` imports `assets/tap-netlist-bound-nft/tapnft.py` and `tap02_reference.py`.
- core:550, C:339, D:212 use `assets/chain-snapshot.json` at the assets root.

When the folders become `assets/tap-<nn>/` (TAP-01 §6.2), these paths break. Either copy the dependencies into each folder (as core does with `tap02_reference.py`) or state in D's Reference Implementation: "Requires `assets/tap-<core nn>/tapnft.py`; paths are updated on number assignment."

---

## Nits

1. **core:22/32**: the number request is repeated in the Abstract and the Motivation. Handled by B-3: keep it in the Motivation only.
2. **core:458 (ZH 460)**: `#### 8.4 TAP-721 Eval extension (OPTIONAL)`. A capitalised keyword in a heading is not a requirement. Use `#### 8.4 TAP-721 Eval extension (optional)`.
3. **core:26 (ZH 28)**: "and are traded as such" → "and are used as such".
4. **D:28 (ZH 30)**: "Buyers, marketplaces and rarity tools need…" → "Holders, marketplaces and rarity tools need…". **D:236**: "buyers should read a structural-hash count as…" → "readers should read a structural-hash count as…".
5. **D:218 (ZH 220)**: "#3151 (8-bit population count)" → "#3151 (8-bit population count, PoD miner)". It has a miner record (pod:345), like the other two rows.
6. **D:152**: "it rewards each registered design separately" → "it scores each registered design separately".
7. **bridging:49**: "(§8.3 of that draft)" → "(TAP-721 §8.3)", the form used everywhere else in B.
8. **pod:221 (ZH 223)**: "the snapshot of every token MUST be taken at `pod.block`, and `tap.pod.block` MUST NOT be smaller than `pod.block`" reads as two different rules. Use: "the snapshot of every token MUST be taken at `pod.block`; a later refresh (§4.3) may only increase `tap.pod.block`."
9. **pod:186**: the `functionCheck` table sits inside list item 3 at column 0, which ends the list. The following "`method` …" paragraph (3-space indent) renders outside the list. Indent the table, or move it after the list.
10. **ZH section names are inconsistent across the four translations and with TAP-02.zh.md**, which uses 设计理由 / 向后兼容 / 安全考虑:
    - core: 理由 (zh:504), 向后兼容, 安全考虑
    - B: 设计理由, 向后兼容性 (zh:398), 安全考量 (zh:472)
    - C: 原理 (zh:320), 向后兼容, 安全考量 (zh:383)
    - D: 原理 (zh:150), 向后兼容, 安全考量 (zh:235)

    Use 设计理由 / 向后兼容 / 安全考虑 in all four.
11. **core .zh:14**: the translator note "本文是本 TAP 的中文译文…" omits the file name, unlike the other three ("本文是 `TAP-draft-….md` 的中文译文…"). Use: "本文是 `TAP-draft-netlist-bound-nft.md` 的中文译文，仅供参考；与英文不一致时以英文为准（TAP-01 §6.2）。"
12. **`assets/tap-netlist-bound-nft/.pytest_cache/`**: a stray test cache in the asset folder. Delete it before the PR and add it to `.gitignore`.

---

## Submission order (for the PR author)
1. Open the Idea issue(s), then set `discussions-to` (B-4).
2. Apply B-1, B-2 and B-3, then S-1 to S-9.
3. Open the core PR alone (CONTRIBUTING §2 item 4) and ask for number 721 in the PR body.
4. After the core is numbered, open B, C and D as separate PRs, with `requires` and every `TAP-draft-netlist-bound-nft` replaced by the assigned number.
