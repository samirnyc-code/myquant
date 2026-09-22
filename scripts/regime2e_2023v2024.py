"""Why did the 2E book jump 2023 (PF 1.04) -> 2024 (PF 1.69) at similar VIX/ADR?

Uses the 16yr per-trade file (Databento proxy) with the book gates applied, then
decomposes 2023 vs 2024: win rate, avg win/loss, side split, monthly P&L, top
trades' contribution, and per-trade MAE/hold. Also checks whether ADR/VIX really
were 'similar' or whether the yearly means hide a within-year shift.

  python scripts/regime2e_2023v2024.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5; FLOOR = 8 * TICK
REPO = Path(__file__).resolve().parent.parent
WT = Path(r"C:\Users\Admin\myquant-regime")
DATA = REPO / "data"


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def load_book():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["pnl"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COST
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = (g.H - g.L).rolling(10).mean().shift(1)
    g["skip_after"] = ((g.H - g.L) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    d = d.merge(g[["Date", "sma20", "skip_after"]], on="Date", how="left").dropna(subset=["sma20"])
    return d[(d.entry_px > d.sma20) & (~d.skip_after)].copy()


def main():
    book = load_book()
    book["mon"] = book.Date.str[:7]
    for y in (2023, 2024):
        x = book[book.yr == y]; v = x.pnl.values
        w = v[v > 0]; l = v[v <= 0]
        print(f"\n===== {y} =====  net ${v.sum():+,.0f}  PF {pf(v):.2f}  n={len(v)}  win {100*(v>0).mean():.0f}%")
        print(f"  avg win ${w.mean():+,.0f}  avg loss ${l.mean():+,.0f}  payoff {abs(w.mean()/l.mean()):.2f}"
              f"  best ${v.max():+,.0f}  worst ${v.min():+,.0f}")
        for d_ in ("L", "S"):
            xx = v[(x.dir == d_).values]
            print(f"  {'2EL' if d_=='L' else '2ES'}: n={len(xx)} PF {pf(xx):.2f} net ${xx.sum():+,.0f}")
        # concentration: top-5 winners share of gross profit
        gp = w.sum(); top5 = np.sort(w)[::-1][:5].sum()
        print(f"  top-5 winners = ${top5:,.0f} of ${gp:,.0f} gross profit ({100*top5/gp:.0f}%)")
        print(f"  hold(bars) med {x.hold.median():.0f}  MAE avg ${x.mae_pts.mean()*PT:,.0f}")
        # monthly
        mm = x.groupby("mon").pnl.agg(["sum", "count"])
        print("  monthly:  " + "  ".join(f"{m[5:]}:${r['sum']:+,.0f}" for m, r in mm.iterrows()))

    # within-year vol: was 2024 really 'similar' to 2023?
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(H=("High", "max"), L=("Low", "min")).reset_index()
    g["yr"] = g.Date.str[:4].astype(int); g["rng"] = g.H - g.L
    vix = pd.read_csv(DATA / "vix_daily.csv"); vix["yr"] = pd.to_datetime(vix.date).dt.year
    print("\n===== VOL CONTEXT (are 2023 and 2024 actually similar?) =====")
    for y in (2023, 2024):
        r = g[g.yr == y].rng; vx = vix[vix.yr == y].close
        print(f"  {y}: ADR mean {r.mean():.1f}  median {r.median():.1f}  p90 {r.quantile(.9):.1f}   "
              f"VIX mean {vx.mean():.1f}  median {vx.median():.1f}  p90 {vx.quantile(.9):.1f}")
    # trend-day frequency proxy: fraction of days with range > 1.5x that year's median
    for y in (2023, 2024):
        r = g[g.yr == y].rng; med = r.median()
        print(f"  {y}: big-range days (>1.5x median) = {100*(r>1.5*med).mean():.0f}% of sessions")


if __name__ == "__main__":
    main()
