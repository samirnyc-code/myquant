"""THE BOOK across the FULL 16 years (2010-2026) on Databento 1-min. Two-sided 2E + gate:
entry price > 20-day SMA of daily closes (prior day, causal). Uses the committed per-trade set
(oos_pertrade_full = all with-trend 2E entries 2010-2026, entry_px + net @0.30xADR/EOD) and
applies the SMA20 gate. No options, no HVL.

  python scripts/regime_2e_sma20_full16.py
Output: data/regime/book_sma20_full16_20260725.csv + tables.
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values; return float((e - np.maximum.accumulate(e)).min())


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    # net at 0.30xADR (the book's stop), EOD
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["net"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COMM - SLIP
    # 20-day SMA of daily closes (Databento 5m frame), prior-day, causal
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    dc = b.groupby("Date")["Close"].last().reset_index().sort_values("Date")
    dc["sma20"] = dc["Close"].rolling(20).mean().shift(1)
    d = d.merge(dc[["Date", "sma20"]], on="Date", how="left").dropna(subset=["sma20"])
    d["above"] = d.entry_px > d.sma20
    d.to_csv(WT / "data" / "regime" / "book_sma20_full16_20260725.csv", index=False)

    def show(nm, x):
        v = x.net.values
        if not len(v): print(f"{nm}: none"); return
        top5 = np.sort(v)[::-1][:5].sum(); v2 = np.sort(v)[::-1][5:]
        print(f"{nm}: n={len(v)} ({len(v)/16.5:.0f}/yr) PF {pf(v):.2f} net ${v.sum():+,.0f} (${v.sum()/16.5:+,.0f}/yr) "
              f"win {100*(v>0).mean():.0f}% maxDD ${mdd(x):+,.0f} top5={100*top5/v.sum():.0f}% minus-top5 PF {pf(v2):.2f}")

    ab = d[d.above]
    print("=== THE BOOK, full 16yr (2010-2026), Databento 1-min ===")
    show("2E both  ABOVE SMA20", ab)
    show("2EL long ABOVE SMA20", ab[ab.dir == "L"])
    show("2ES short ABOVE SMA20", ab[ab.dir == "S"])
    show("(contrast) both BELOW SMA20", d[~d.above])
    print("\n2E-both ABOVE SMA20, per 4-year block:")
    for y0, y1 in BLOCKS:
        x = ab[(ab.yr >= y0) & (ab.yr <= y1)]
        print(f"  {y0}-{y1}: n={len(x):4d} PF {pf(x.net):.2f} net ${x.net.sum():+8,.0f}")
    print("\n2E-both ABOVE SMA20, per year:")
    for y in range(2010, 2027):
        x = ab[ab.yr == y]
        if len(x): print(f"  {y}: n={len(x):3d} PF {pf(x.net):.2f} net ${x.net.sum():+7,.0f}")


if __name__ == "__main__":
    main()
