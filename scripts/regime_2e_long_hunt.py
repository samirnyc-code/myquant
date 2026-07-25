"""LONG-BOOK CONDITIONER HUNT — the long-only 2E book is the real edge (net-positive every
4yr block). Hunt for conditioners that SHARPEN it, but keep ONLY those that improve across
ALL blocks (block-robust). A conditioner that only lifts the aggregate is curve-fit.

Base = LONG with-trend, 0.30xADR stop, 09-13, no gap filter. Attach causal daily features
(above SMA20/50, daily ER10 trend-efficiency, prior-day return, day-of-week, entry hour) and
report each conditioner's net meanR + PF per 4-year block. Keep block-robust ones.

Reads oos_pertrade_full_20260725.csv + _db_es_5m_rth.parquet (daily features).

  python scripts/regime_2e_long_hunt.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def daily_feats():
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    d = b.groupby("Date").agg(C=("Close", "last")).reset_index().sort_values("Date")
    c = d["C"]
    d["sma20"] = c.rolling(20).mean(); d["sma50"] = c.rolling(50).mean()
    d["above20"] = (c > d.sma20).astype(int); d["above50"] = (c > d.sma50).astype(int)
    chg = c.diff().abs()
    d["er10"] = (c - c.shift(10)).abs() / chg.rolling(10).sum()      # daily efficiency ratio
    d["ret5"] = c.pct_change(5)
    d["dow"] = pd.to_datetime(d["Date"]).dt.dayofweek                # 0=Mon
    for f in ["above20", "above50", "er10", "ret5"]:                 # causal: prior day
        d[f] = d[f].shift(1)
    # CAUSAL threshold: expanding median of PRIOR er10 only (no full-sample look-ahead)
    d["er10_medexp"] = d["er10"].expanding(min_periods=60).median()
    d["er10_top"] = (d["er10"] > d["er10_medexp"]).astype("float")   # NaN until 60 days seen
    return d.set_index("Date")[["above20", "above50", "er10", "er10_top", "ret5", "dow"]]


def report(name, m):
    row = f"{name:<26}"
    ok = True
    for (y0, y1) in BLOCKS:
        b = m[(m.yr >= y0) & (m.yr <= y1)]
        mr = b.Rn.mean() if len(b) else float('nan')
        row += f"{mr:>+8.3f}"
        if not (mr > 0):
            ok = False
    row += f"   full netPF {pf(m.net):.2f}  n={len(m)}  {'ROBUST' if ok else ''}"
    print(row)


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy(); d["fh"] = d.fill_hour.astype(int)
    d = d[d.fh.isin({9, 10, 11, 12, 13})]
    ft = daily_feats(); d = d.merge(ft, left_on="Date", right_index=True, how="left")
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    move = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = move * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)

    print("net meanR by 4yr block  [2010-13][2014-17][2018-21][2022-26]  (ROBUST = >0 all blocks)\n")
    report("BASE long (all)", d)
    print("-- trend alignment --")
    report("above SMA50", d[d.above50 == 1]); report("below SMA50", d[d.above50 == 0])
    report("above SMA20", d[d.above20 == 1]); report("below SMA20", d[d.above20 == 0])
    print("-- efficiency / momentum (CAUSAL expanding-median threshold) --")
    report("er10 top (causal)", d[d.er10_top == 1]); report("er10 bottom (causal)", d[d.er10_top == 0])
    report("er10 top (LEAKY full-median)", d[d.er10 >= d.er10.median()])  # for contrast only
    report("prior 5d ret>0", d[d.ret5 > 0]); report("prior 5d ret<0", d[d.ret5 <= 0])
    print("-- entry hour --")
    for h in (9, 10, 11, 12, 13):
        report(f"hour {h:02d}", d[d.fh == h])
    print("-- day of week --")
    for dw, nm in zip(range(5), ["Mon", "Tue", "Wed", "Thu", "Fri"]):
        report(nm, d[d.dow == dw])
    print("-- combos (causal er10) --")
    report("above50 & er10-top", d[(d.above50 == 1) & (d.er10_top == 1)])
    report("above50 & h09-12", d[(d.above50 == 1) & (d.fh <= 12)])


if __name__ == "__main__":
    main()
