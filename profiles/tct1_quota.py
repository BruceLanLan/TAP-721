#!/usr/bin/env python3
"""TapeCode-Test1 slot quotas and netlist edition plan (stdlib only, MIT).

Usage:
  python3 tct1_quota.py                 # snapshot counts from the original plan (block 127,841,896)
  python3 tct1_quota.py --designs 30,110,400,800,520   # counts from a fresh audit snapshot

1. Tier quotas: supply x percentage, rounded by the largest-remainder method (exact for 10,000, but the
   method is stated so other supplies stay reproducible). The sum MUST equal the supply.
2. Edition plan per netlist tier: q = slots // designs, r = slots % designs. After sorting the tier's
   distinct netlist hashes ascending (a rule nobody can steer), the first r designs get q+1 copies and the
   rest get q. Sum MUST equal the tier's slots.
"""
import argparse
from fractions import Fraction

TIERS = ["Mythic", "Legendary", "Epic", "Rare", "Common"]
PCT = [1, 4, 15, 30, 50]                      # original plan, section 9
SNAPSHOT = [26, 103, 388, 776, 501]           # original plan, section 10 (block 127,841,896)


def quotas(supply: int, pct: list[int]) -> list[int]:
    assert sum(pct) == 100
    exact = [Fraction(supply * p, 100) for p in pct]
    base = [int(x) for x in exact]
    left = supply - sum(base)
    order = sorted(range(len(pct)), key=lambda i: (-(exact[i] - base[i]), i))
    for i in order[:left]:
        base[i] += 1
    assert sum(base) == supply
    return base


def editions(slots: int, designs: int) -> tuple[int, int, int]:
    """Return (q, designs with q+1 copies, designs with q copies)."""
    if designs <= 0:
        raise SystemExit("a tier has no eligible designs; the quota cannot be filled")
    q, r = divmod(slots, designs)
    assert r * (q + 1) + (designs - r) * q == slots
    return q, r, designs - r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--supply", type=int, default=10000)
    ap.add_argument("--designs", default=",".join(map(str, SNAPSHOT)),
                    help="distinct proven netlists per tier, Mythic..Common")
    a = ap.parse_args()
    designs = [int(x) for x in a.designs.split(",")]
    assert len(designs) == 5
    qs = quotas(a.supply, PCT)

    print(f"supply {a.supply}")
    print(f"{'tier':10} {'pct':>4} {'slots':>6} {'designs':>8} {'avg':>6}  edition plan")
    for t, p, s, d in zip(TIERS, PCT, qs, designs):
        q, hi, lo = editions(s, d)
        plan = f"{hi} x {q+1} + {lo} x {q}" if hi else f"{lo} x {q}"
        print(f"{t:10} {p:>3}% {s:>6} {d:>8} {s/d:>6.2f}  {plan}  (= {hi*(q+1)+lo*q})")
    print(f"{'total':10} {sum(PCT):>3}% {sum(qs):>6} {sum(designs):>8}")
    assert sum(qs) == a.supply
    print("check: slot sum == supply OK")


if __name__ == "__main__":
    main()
