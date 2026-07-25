"""DURABLE STRESS — cost/slippage robustness + long-only alternative for the durable book.
Re-derives net from per-trade MAE/EOD (in durable_20260725.csv) so higher costs are exact.

Stops: longs 0.40xADR, shorts 0.30xADR (the durable spec). Cost scenarios:
  base   = $5 RT + 1t slip   (the headline)
  stress = $10 RT + 3t slip  (double commission, triple slippage — pessimistic fills)

Also: LONG-ONLY durable (drop the short sleeve) vs full durable — is the gated-short book
worth the added complexity?

  python scripts/regime_2e_durable_stress.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "durable_20260725.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def netc(d, comm, slip_ticks):
    """re-derive net: longs stop 0.40xADR, shorts 0.30xADR; cost = comm + slip_ticks*$12.5."""
    m = np.where(d.dir.values == "L", 0.40, 0.30)
    S = np.maximum(np.round(m * d.adr.values / TICK) * TICK, FLOOR)
    move = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    return move * PT - comm - slip_ticks * 12.5


def maxdd(d, col):
    dd = d.groupby("Date")[col].sum().sort_index().cumsum()
    return float((dd - dd.cummax()).min())


def block(name, d, col):
    v = d[col].values
    if not len(v):
        print(f"{name:<34} (empty)"); return
    print(f"{name:<34} n={len(v):5d}  net {v.sum():+9,.0f}  PF {pf(v):4.2f}  "
          f"maxDD {maxdd(d, col):+8,.0f}  net/DD {v.sum()/-maxdd(d,col):4.2f}  "
          f"pre {d[d.yr<=2020][col].sum():+8,.0f} ({pf(d[d.yr<=2020][col])})  "
          f"post {d[d.yr>=2021][col].sum():+8,.0f} ({pf(d[d.yr>=2021][col])})")


def main():
    d = pd.read_csv(CSV).sort_values("Date").reset_index(drop=True)
    d["base"] = netc(d, 5.0, 1)
    d["stress"] = netc(d, 10.0, 3)
    L = d[d.dir == "L"].copy()

    print("========== COST / SLIPPAGE STRESS (full durable book) ==========")
    block("BASE  ($5 RT + 1t slip)", d, "base")
    block("STRESS ($10 RT + 3t slip)", d, "stress")
    dp = 100 * (d.stress.sum() - d.base.sum()) / d.base.sum()
    print(f"  -> stress cuts net by {abs(dp):.0f}% ({d.base.sum():+,.0f} -> {d.stress.sum():+,.0f}); "
          f"edge {'SURVIVES' if pf(d.stress)>1.1 else 'FRAGILE'} (PF {pf(d.stress)})")

    print("\n========== LONG-ONLY durable vs FULL durable (base costs) ==========")
    block("FULL (longs + gated shorts)", d, "base")
    block("LONG-ONLY (drop shorts)", L, "base")
    short_add = d.base.sum() - L.base.sum()
    print(f"  -> the gated-short sleeve adds {short_add:+,.0f} over 16yr "
          f"(pre {d[d.yr<=2020].base.sum()-L[L.yr<=2020].base.sum():+,.0f} / "
          f"post {d[d.yr>=2021].base.sum()-L[L.yr>=2021].base.sum():+,.0f})")

    print("\n========== LONG-ONLY under stress ==========")
    block("LONG-ONLY stress", L, "stress")


if __name__ == "__main__":
    main()
