"""Analysis of the full 3-EM iron-condor backtest (backtest_full/rows.csv).

Per EM method: total/yearly P&L, win%, stop%, avg credit, worst day, max drawdown
(on the daily 4-vertical book, $ per 1-lot). Re-runnable as more days land; writes
data/options_sim/backtest_full/analysis_summary.csv.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ROWS = ROOT / "data/options_sim/backtest_full/rows.csv"
METHODS = ["vix252", "vix365", "straddle"]


def dd(series):
    """max drawdown of a cumulative P&L curve built from daily P&L."""
    cum = series.cumsum()
    return (cum - cum.cummax()).min()


def main():
    d = pd.read_csv(ROWS)
    d = d[d["pnl"].notna()].copy()
    d["year"] = d["date"].str[:4]
    # drop years with <20 days of data (partial artifacts)
    keep_years = d.groupby("year")["date"].nunique()
    d = d[d["year"].isin(keep_years[keep_years >= 20].index)]
    print(f"window: {d.date.min()} -> {d.date.max()}   days: {d.date.nunique()}\n")

    # ---- headline per method ----
    print(f"{'method':10}{'total P&L':>12}{'P&L/day':>9}{'win%':>7}{'stop%':>7}"
          f"{'avg cr':>8}{'worst day':>11}{'max DD':>10}")
    summary = []
    for m in METHODS:
        g = d[d["method"] == m]
        daily = g.groupby("date")["pnl"].sum()
        row = dict(method=m, total=g.pnl.sum(), per_day=daily.mean(),
                   win=100 * (g.pnl > 0).mean(), stop=100 * (g.exit_kind == "stop").mean(),
                   avg_cr=g.credit.mean(), worst=daily.min(), maxdd=dd(daily))
        summary.append(row)
        print(f"{m:10}{row['total']:>12,.0f}{row['per_day']:>9,.0f}{row['win']:>6.0f}%"
              f"{row['stop']:>6.0f}%{row['avg_cr']:>8.2f}{row['worst']:>11,.0f}{row['maxdd']:>10,.0f}")

    # ---- yearly P&L per method ----
    print("\nyearly P&L:")
    yr = d.pivot_table(index="year", columns="method", values="pnl", aggfunc="sum")
    print(yr[METHODS].round(0).to_string())

    # ---- per strategy per method ----
    print("\nper-strategy total P&L:")
    st = d.pivot_table(index="strat", columns="method", values="pnl", aggfunc="sum")
    print(st[METHODS].round(0).to_string())

    # ---- yearly detail per method: win%, stops ----
    print("\nstop% by year:")
    sp = d.assign(is_stop=(d.exit_kind == "stop")).pivot_table(
        index="year", columns="method", values="is_stop", aggfunc="mean") * 100
    print(sp[METHODS].round(0).to_string())

    pd.DataFrame(summary).to_csv(ROOT / "data/options_sim/backtest_full/analysis_summary.csv", index=False)
    yr.to_csv(ROOT / "data/options_sim/backtest_full/analysis_yearly.csv")
    print("\n-> analysis_summary.csv, analysis_yearly.csv")


if __name__ == "__main__":
    main()
