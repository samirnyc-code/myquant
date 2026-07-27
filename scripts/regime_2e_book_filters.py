"""Layer the proven filters onto the SMA20-gated two-sided 2E book and measure each one's effect:
  base  = 2E both, entry > 20-day SMA (+ the always-on spec: 2E signal, with-trend, gap<=0.54,
          retest 6t, 09-13, 0.30xADR stop, EOD)
  +TD   = skip the day AFTER a trend day (prior-day range > 1.6 x ADR10) -- the handoff's clean skip
  +CG   = crash-guard: skip if prior-5-day return < -4%
  +ER   = ER10-top only (prior-day trend efficiency above its causal expanding median)
  ALL   = all three
All causal. Reports 2021+ and full 16yr for each layer.

  python scripts/regime_2e_book_filters.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values; return float((e - np.maximum.accumulate(e)).min())


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["net"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COMM - SLIP

    # daily features (causal)
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    c = g["C"]
    g["sma20"] = c.rolling(20).mean().shift(1)
    g["adr10"] = (g.H - g.L).rolling(10).mean().shift(1)
    g["rng"] = g.H - g.L
    g["trendday"] = (g["rng"] > 1.6 * g["adr10"])          # today an outsized/trend day
    g["skip_after"] = g["trendday"].shift(1).fillna(False).astype(bool)  # skip today if YESTERDAY was a trend day; astype(bool): object ~ was a no-op
    g["ret5"] = c.pct_change(5).shift(1)
    chg = c.diff().abs(); g["er10"] = ((c - c.shift(10)).abs() / chg.rolling(10).sum()).shift(1)
    g["er10_top"] = (g["er10"] > g["er10"].expanding(min_periods=60).median())
    d = d.merge(g[["Date", "sma20", "skip_after", "ret5", "er10_top"]], on="Date", how="left").dropna(subset=["sma20"])

    base = d.entry_px > d.sma20
    td = ~d.skip_after
    cg = d.ret5 >= -0.04
    er = d.er10_top == 1

    def rowf(name, mask):
        for lbl, yrmin in (("2021+", 2021), ("16yr", 2010)):
            x = d[mask & (d.yr >= yrmin)]
            v = x.net.values
            if not len(v):
                print(f"  {name:<20} {lbl:<6} (none)"); continue
            top5 = np.sort(v)[::-1][:5].sum()
            print(f"  {name:<20} {lbl:<6} n={len(v):4d} PF {pf(v):.2f} net ${v.sum():+8,.0f} (${v.sum()/(5.5 if yrmin==2021 else 16.5):+,.0f}/yr) "
                  f"win {100*(v>0).mean():3.0f}% maxDD ${mdd(x):+8,.0f} top5={100*top5/v.sum():3.0f}%")

    print("=== layering filters on the SMA20-gated two-sided book ===")
    rowf("base (SMA20)", base)
    rowf("+ skip-after-TD", base & td)
    rowf("+ crash-guard", base & cg)
    rowf("+ ER10-top", base & er)
    rowf("+ TD + CG", base & td & cg)
    rowf("ALL (TD+CG+ER)", base & td & cg & er)


if __name__ == "__main__":
    main()
