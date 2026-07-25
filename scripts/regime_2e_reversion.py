"""MEAN-REVERSION COMPLEMENT — the long-2E continuation edge lives on TRENDING (ER10-top) days
and is flat on CHOPPY (ER10-bottom) days. Hypothesis: on choppy days, the OPPOSITE (counter-
trend / fade the second entry) reverts and pays. If so, trend(efficient) + reversion(choppy)
= a smoother, higher-frequency all-weather book, uncorrelated by construction.

Counter-trend book = 2E fired AGAINST the phase regime (e.g., short-2E while regime BULL).
Test its edge conditioned on ER10 (causal), per block, both directions. All causal.

Reads oos_pertrade_full_20260725.csv + _db_es_5m_rth (daily ER10 causal).

  python scripts/regime_2e_reversion.py
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


def er10_causal():
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    d = b.groupby("Date").agg(C=("Close", "last")).reset_index().sort_values("Date")
    c = d["C"]; chg = c.diff().abs()
    d["er10"] = ((c - c.shift(10)).abs() / chg.rolling(10).sum()).shift(1)
    d["medexp"] = d["er10"].expanding(min_periods=60).median()
    d["er10_top"] = (d["er10"] > d["medexp"]).astype("float")
    return d.set_index("Date")["er10_top"]


def blockrow(name, m):
    row = f"{name:<28}"; ok = True
    for (y0, y1) in BLOCKS:
        b = m[(m.yr >= y0) & (m.yr <= y1)]
        mr = b.Rn.mean() if len(b) else float('nan')
        row += f"{mr:>+8.3f}" if len(b) else f"{'-':>8}"
        if not (len(b) and mr > 0):
            ok = False
    print(row + f"   PF {pf(m.net):.2f} n={len(m)} {'ROBUST' if ok else ''}")


def main():
    d = pd.read_csv(CSV)
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    d = d.merge(er10_causal().rename("er10_top"), left_on="Date", right_index=True, how="left")
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)
    ct = d[~d.with_trend].copy()   # counter-trend = fade

    print("net meanR by 4yr block  [2010-13][2014-17][2018-21][2022-26]\n")
    print("=== COUNTER-TREND (fade) book, conditioned on trend-efficiency ===")
    blockrow("fade ALL", ct)
    blockrow("fade on ER10-TOP (trend)", ct[ct.er10_top == 1])
    blockrow("fade on ER10-BOTTOM (chop)", ct[ct.er10_top == 0])
    print("\n=== fade by direction on CHOPPY (ER10-bottom) days ===")
    blockrow("fade LONG (buy dip) chop", ct[(ct.er10_top == 0) & (ct.dir == "L")])
    blockrow("fade SHORT (sell rip) chop", ct[(ct.er10_top == 0) & (ct.dir == "S")])

    print("\n=== the with-trend LONG book on the SAME cut (for correlation context) ===")
    wt = d[d.with_trend & (d.dir == "L")]
    blockrow("long-2E ER10-TOP", wt[wt.er10_top == 1])
    blockrow("long-2E ER10-BOTTOM", wt[wt.er10_top == 0])

    # if a fade sub-book is robust on choppy days, estimate the combined book
    fade = ct[(ct.er10_top == 0)]
    longbook = wt[wt.er10_top == 1]
    print("\n=== candidate combined: long-2E(ER10-top) + fade(ER10-bottom) ===")
    comb = pd.concat([longbook, fade]).sort_values("Date")
    blockrow("COMBINED", comb)
    # daily-PnL correlation
    lp = longbook.groupby("Date").net.sum(); fp = fade.groupby("Date").net.sum()
    j = pd.concat([lp.rename("L"), fp.rename("F")], axis=1).fillna(0)
    print(f"  daily-PnL corr(long-trend, fade-chop) = {j.L.corr(j.F):+.3f}  "
          f"(low = genuine diversification)")


if __name__ == "__main__":
    main()
