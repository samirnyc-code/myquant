"""verify_2e_stats.py — independent audit of every 2E setup's stats, straight from committed
data. No hidden state, no narration. Run it yourself and you get the exact numbers.

Reads:
  data/regime/hvl_2e_realtick_20260725.csv   (real-tick 2E trades, HVL-classified, per trade)
  data/regime/fade_full_hvl_20260725.csv     (f2EL/f2ES fade trades)

Prints per setup: n, PF, net, win%, avg win/loss, maxDD, and the top-5-trades share of net
(the tail-concentration robustness check — if that's ~100%, a few trades ARE the profit).

  python scripts/verify_2e_stats.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values; return float((e - np.maximum.accumulate(e)).min())


def row(name, x):
    v = x.net.values
    if not len(v):
        print(f"  {name:<26} (none)"); return
    w = v[v > 0]; l = v[v < 0]; top5 = np.sort(v)[::-1][:5].sum()
    print(f"  {name:<26} n={len(v):4d}  PF {pf(v):4.2f}  net ${v.sum():+9,.0f}  win {100*(v>0).mean():3.0f}%  "
          f"avgW ${w.mean():+5,.0f}  avgL ${l.mean() if len(l) else 0:+5,.0f}  maxDD ${mdd(x):+8,.0f}  "
          f"top5={100*top5/v.sum() if v.sum() else 0:4.0f}% of net")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "hvl_2e_realtick_20260725.csv")
    ab = d[d.above]
    print("=== 2E (real ticks), ABOVE the SPX-derived HVL, full 2021-2026 ===")
    print("    (NOTE: HVL is APPROXIMATE pre-2024 — real MQ ES levels only exist 2024-07+)")
    row("2EL long", ab[ab.dir == "L"])
    row("2ES short", ab[ab.dir == "S"])
    row("2E both", ab)
    row("2E both BELOW HVL", d[~d.above])
    print("  2EL-long per-year PF:", {int(y): pf(ab[(ab.dir == 'L') & (ab.yr == y)].net) for y in sorted(ab.yr.unique())})
    print("  2ES-short per-year PF:", {int(y): pf(ab[(ab.dir == 'S') & (ab.yr == y)].net) for y in sorted(ab.yr.unique())})

    fd = pd.read_csv(WT / "data" / "regime" / "fade_full_hvl_20260725.csv")
    print("\n=== fade sleeves (proxy) ===")
    row("f2EL (BEAR gate)", fd[(fd.fade == "f2EL") & (fd.reg == "BEAR")])
    row("f2ES (BULL gate)", fd[(fd.fade == "f2ES") & (fd.reg == "BULL")])

    print("\nread: PF is inflated when top5% is near/over 100 (a few trades are the whole edge).")
    print("2EL-long has the lowest tail share -> the most dependable. 2ES/f2EL are tail-driven.")


if __name__ == "__main__":
    main()
