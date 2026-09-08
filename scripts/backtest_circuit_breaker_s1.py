"""Stage 1 — idealized daily circuit-breaker study on the vix252 book.

Approximation: cap each day's final P&L at -X, as if the book were flattened the
moment the day hit -X. This is an UPPER BOUND on the breaker's benefit:
  optimistic  - assumes flattening exactly at -X with zero slippage;
  and it MISSES the cost side - days that dipped below -X intraday but recovered
  by the close would in reality have been locked at -X (worse than baseline).
Stage 2 (backtest_circuit_breaker_s2) rebuilds the true intraday book path from
1-min quotes on every day where the breaker could bind, and prices the flatten
at the touch - the real number, both benefit and cost.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    d = pd.read_csv(ROOT / "data/options_sim/backtest_full/rows.csv")
    d = d[(d.pnl.notna()) & (d.method == "vix252")].copy()
    daily = d.groupby("date").pnl.sum()
    base = daily.sum()
    print(f"vix252 daily book: {len(daily)} days, baseline {base:+,.0f}\n")
    print(f"{'cap':>8}{'total P&L':>12}{'vs base':>10}{'days capped':>13}{'avg saved/cap day':>19}")
    for cap in (1000, 1500, 2000, 2500, 3000):
        capped = daily.clip(lower=-cap)
        n = (daily < -cap).sum()
        tot = capped.sum()
        saved = (capped - daily)[daily < -cap]
        print(f"{-cap:>8}{tot:>12,.0f}{tot-base:>+10,.0f}{n:>10}{saved.mean() if n else 0:>16,.0f}")
    # which days does a -2k breaker touch?
    hit = daily[daily < -2000].sort_values()
    print(f"\ndays a -2,000 breaker touches ({len(hit)}):")
    for dt_, p in hit.items():
        print(f"  {dt_}  {p:>9,.0f} -> capped -2,000  (saves {abs(p)-2000:,.0f})")
    print("\nCAVEAT: upper bound. Stage 2 prices the real flatten AND the recovered-day cost.")


if __name__ == "__main__":
    main()
