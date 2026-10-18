# TapeCode-Test1 netlist rarity rule (7,000 valid tokens), v1

This is a public rule that anyone can recompute. Every parameter below is fixed in the manifest's `rules` member **before** the drand round is announced. The resulting design list is in `rarity-7000.json` (snapshot block 128,200,681).

## 1. Rule (formula sheet)

```json
"rules": {
  "rarity": "tct1-rarity-7000/v1",
  "snapshot": {"chainId": 56, "block": 128200681, "mining": "0x7E2E0DC66a3bD9103E69b766afA62d9f7b697b46"},
  "eligible": [
    "miner record at block with verifWeight > 0",
    "tapnet/1 file valid (draft A §2.2) and <= 49,152 bytes",
    "functionally equal to getTask(taskId).refCircuits/refCircuitId at block (tools/collection/verify_function.py): combinational = all 2^nIn inputs if nIn <= 16, else 16,384 inputs from seed 1; sequential = equal outputs at every beat from the zero state over max(cycles,32) beats (--seq every-beat); 'unconfirmed' or any difference = not eligible",
    "one design per distinct netlist SHA-256; canonical miner = earliest registration (processor, circuitId tie-break)"
  ],
  "size": "S = min(N_live + L_live, 3 * min over eligible designs of the same task of (N_live + L_live))",
  "live": "N_live, L_live = NAND and LATCH elements in the backward cone of the outputs (NAND inputs and LATCH d-inputs followed transitively)",
  "order": ["S desc", "A desc (A = getMiner.area = N + 7L)", "depth desc", "netlistSha256 asc"],
  "tiers": [
    {"tier": "Mythic",    "designs": 70,  "copies": 1, "tokens": 70},
    {"tier": "Legendary", "designs": 140, "copies": 2, "tokens": 280},
    {"tier": "Epic",      "designs": 350, "copies": 3, "tokens": 1050},
    {"tier": "Rare",      "designs": 350, "copies": 6, "tokens": 2100},
    {"tier": "Common",    "designs": 500, "copies": 7, "tokens": 3500}
  ],
  "fill": "walk the order; the first 70 designs are Mythic, the next 140 Legendary, and so on; designs after the first 1,410 are not used",
  "pool": "each design appears 'copies' times in NETLIST_V1, tiers Mythic..Common, then netlistSha256 asc, copies consecutive; 7,000 entries"
}
```

## 2. Result at block 128,200,681

| Tier | Designs × copies | Tokens | Size S of its designs |
|---|---|---|---|
| Mythic | 70 × 1 | 70 | 342 – 1,196 |
| Legendary | 140 × 2 | 280 | 143 – 342 |
| Epic | 350 × 3 | 1,050 | 73 – 143 |
| Rare | 350 × 6 | 2,100 | 44 – 73 |
| Common | 500 × 7 | 3,500 | 24 – 44 |
| **Total** | **1,410 designs** | **7,000** | |

Notes on the table:
- A size value at a boundary (342, 143, 73, 44, 24) can appear in both neighbouring tiers. Which tier such a design gets is decided by the tie-breaks.
- Designs smaller than the Common band are not used. If Common used all of them, each Common design would have fewer copies than each Rare design, and the rule that smaller designs have more copies would break.

## 3. Why these choices

- **Size = live element count N + L.** The PoD area A = N + 7L (the contract's `area`: gateCount + λ·stateCount with λ = 6) weights each latch seven times. Measured on the snapshot, that lets trivial circuits padded with long latch chains (for example a divide-by-2 built with about 145 latches) reach Mythic. Counting each element once avoids this. A is still used, as the first tie-break.
- **Only the live cone counts.** Gates that cannot affect an output are not part of the design and add nothing to its size.
- **The 3× cap per task.** A design counts at most three times the size of the smallest correct design for the same task. This stops inflating a simple function to look rare, while genuinely large functions (multipliers, 16-bit adders, squarers) stay at the top.
- **Only functionally correct designs.** Mining checks a sample of input vectors, which is not a proof. Every design here was compared with its task's reference circuit on all inputs (or on a large fixed sample for wide circuits). Anyone can re-run the check with `verify_function.py`.
- **Copies fall as size grows.** 1 / 2 / 3 / 6 / 7: Mythic designs are one-of-ones, Common designs appear 7 times each.

Known property: large designs come from a few hard tasks. The 70 Mythic designs belong to 7 tasks, mostly multipliers and squarers. This is a direct consequence of "bigger = rarer". A per-task cap would add variety, but tiers would then overlap in size, so v1 does not use one.

## 4. 给社区的说明（中文）

**为什么越大越稀有？** 每个网表都是一份真实的数字电路设计。门越多（NAND 与 LATCH 的数量），完成的功能通常越复杂，比如 8×8 乘法器、16 位加法器，这样的设计数量也越少。所以我们按电路规模分档：最大的 70 款各只发 1 枚（神话），然后依次是传奇每款 2 枚、史诗 3 枚、稀有 6 枚、普通 7 枚。为了防止有人用无意义的“凑门”把简单电路做大，规则只计算真正影响输出的门；同一任务的设计，最多按最小正确设计的 3 倍计规模。

**为什么只用正确的设计？** 挖矿合约只抽查部分输入，抽查通过不等于电路完全正确。我们把每份网表和该任务的链上参考电路逐一比对（输入位数不超过 16 时穷举全部输入），只收录结果完全一致的设计。比对脚本和全部参数都已公开，规则在随机数产生之前写入 manifest，任何人都可以用同一区块的数据复算出完全相同的名单。

**它不是什么。** 网表规模和稀有度只描述电路本身，与 BEM 收益、挖矿份额无关。持有 NFT 不产生任何收益。

## 5. Recompute

1. Read all miner records at the block (registration event topic `0x7c9c1f2b…2f94937`, then `getMiner`).
2. Keep the verified ones and build their tapnet files.
3. Run `verify_function.py --csv … --seq every-beat`.
4. Apply §1.
5. Compare with `rarity-7000.json`: the per-design fields `netlistSha256`, `N`, `L`, `A`, `N_live`, `L_live`, `S` and `tier`.
