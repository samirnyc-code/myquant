"""Is the 2E book edge concentrated in a few fat-tail / short-side event days?

Loads the 16yr per-trade proxy with book gates, then:
  - lists the 10 biggest |P&L| trades and identifies them
  - measures top-10 winners' share of 2021+ net (concentration)
  - short vs long net by year (is the yearly swing a directional/short thing?)
  - recomputes 2021+ net with the single biggest winner removed

  python scripts/regime2e_fattail_check.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5; FLOOR = 8 * TICK
REPO = Path(__file__).resolve().parent.parent
WT = Path(r"C:\Users\Admin\myquant-regime")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    b = pd.read_parquet(REPO / "data" / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = (g.H - g.L).rolling(10).mean().shift(1)
    g["skip_after"] = ((g.H - g.L) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    d = d.merge(g[["Date", "sma20", "skip_after"]], on="Date", how="left").dropna(subset=["sma20"])
    d = d[(d.entry_px > d.sma20) & (~d.skip_after)].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["pnl"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COST

    d21 = d[d.yr >= 2021]
    print("2021+ book: net ${:+,.0f}  PF {:.2f}  n={}".format(d21.pnl.sum(), pf(d21.pnl.values), len(d21)))

    big = d.reindex(d.pnl.abs().sort_values(ascending=False).index).head(10)
    print("\nTop 10 |trades| by abs P&L over 16yr (real event days, back-adjusted px):")
    print(big[["Date", "dir", "adr", "mae_pts", "eod_move", "pnl"]].to_string(index=False))

    top10 = d21.pnl.sort_values(ascending=False).head(10).sum()
    print("\n2021+ concentration: top-10 winners = ${:,.0f} of ${:,.0f} net ({:.0f}%)"
          .format(top10, d21.pnl.sum(), 100 * top10 / d21.pnl.sum()))
    without_best = d21.pnl.sum() - d21.pnl.max()
    print("2021+ net WITHOUT the single biggest winner (${:,.0f}): ${:,.0f}  PF {:.2f}"
          .format(d21.pnl.max(), without_best,
                  pf(d21[d21.pnl < d21.pnl.max()].pnl.values)))

    print("\nshort vs long net by year:")
    for y in range(2021, 2027):
        s = d[(d.yr == y) & (d.dir == "S")].pnl; l = d[(d.yr == y) & (d.dir == "L")].pnl
        print("  {}: 2ES ${:+8,.0f} (PF {:.2f}, n={:3d})   2EL ${:+8,.0f} (PF {:.2f}, n={:3d})"
              .format(y, s.sum(), pf(s.values), len(s), l.sum(), pf(l.values), len(l)))


if __name__ == "__main__":
    main()
