"""vix252 (desk EM formula) deep-dive: monthly P&L vs the killer days.

Claim under test: '2022-2025 contained a dozen days that each gave back a month.'
Shows: monthly P&L distribution, the worst days, and each worst day expressed in
units of the median WINNING month. Writes analysis CSVs.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    d = pd.read_csv(ROOT / "data/options_sim/backtest_full/rows.csv")
    d = d[(d.pnl.notna()) & (d.method == "vix252") & (d.date <= "2025-10-24")].copy()
    daily = d.groupby("date").pnl.sum()
    monthly = d.assign(month=d.date.str[:7]).groupby("month").pnl.sum()

    print(f"vix252 book, {d.date.nunique()} days, {len(monthly)} months\n")
    print("monthly P&L:")
    for m, p in monthly.items():
        bar = "#" * min(40, int(abs(p) / 150))
        print(f"  {m}  {p:>8,.0f}  {'+' if p>0 else '-'}{bar}")
    pos = monthly[monthly > 0]
    print(f"\npositive months: {len(pos)}/{len(monthly)}  median winning month: {pos.median():+,.0f}"
          f"   best: {monthly.max():+,.0f}   worst: {monthly.min():+,.0f}")

    med_win = pos.median()
    worst = daily.sort_values().head(14)
    print(f"\nworst days vs the median winning month ({med_win:+,.0f}):")
    print(f"{'date':12}{'day P&L':>10}{'= months given back':>22}")
    for dt_, p in worst.items():
        print(f"  {dt_:12}{p:>10,.0f}{abs(p)/med_win:>18.1f}x")

    monthly.to_csv(ROOT / "data/options_sim/backtest_full/vix252_monthly.csv")
    worst.to_csv(ROOT / "data/options_sim/backtest_full/vix252_worst_days.csv")
    print("\n-> vix252_monthly.csv, vix252_worst_days.csv")


if __name__ == "__main__":
    main()
