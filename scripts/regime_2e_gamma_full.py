"""GAMMA, THE FULL CAUSAL TEST — give the gamma-regime signal a fair, complete shot using ONLY
the PRIOR session's EOD gamma (published pre-open; net_total_gex shifted 1 session). Test sign,
MAGNITUDE (causal expanding percentile), and the MQ regime label, per 4-year block. If none
condition the 2E edge robustly, gamma regime is dead as a FORWARD signal — but tested properly.

Books: long-2E (with-trend) and the full with-trend book. Reads oos_pertrade_full + mq_regime_daily.

  python scripts/regime_2e_gamma_full.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
MQ = DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def brow(name, m):
    row = f"{name:<30}"; ok = True
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
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)

    mq = pd.read_csv(MQ).sort_values("date").reset_index(drop=True)
    mq["date"] = mq["date"].astype(str)
    # PRIOR-session EOD gamma (causal, published pre-open)
    mq["gex_prev"] = mq["net_total_gex"].shift(1)
    mq["greg_prev"] = mq["regime"].shift(1)
    # causal magnitude: expanding percentile of |gex| and signed gex (only past)
    mq["absgex_prev"] = mq["gex_prev"].abs()
    mq["absrank"] = mq["absgex_prev"].expanding(min_periods=100).apply(
        lambda x: (x.iloc[-1] >= x).mean(), raw=False)
    mq["signrank"] = mq["gex_prev"].expanding(min_periods=100).apply(
        lambda x: (x.iloc[-1] >= x).mean(), raw=False)
    m = mq[["date", "gex_prev", "greg_prev", "absrank", "signrank"]].rename(columns={"date": "Date"})
    d = d.merge(m, on="Date", how="left")

    for booknm, bk in (("LONG-2E", d[d.with_trend & (d.dir == "L")]),
                       ("FULL with-trend", d[d.with_trend])):
        g = bk[bk.gex_prev.notna()].copy()
        print(f"\n========== {booknm} — PRIOR-session gamma (causal), by 4yr block ==========")
        print(f"{'gate':<30}{'2010-13':>8}{'2014-17':>8}{'2018-21':>8}{'2022-26':>8}")
        brow("ALL (gamma-covered)", g)
        print("-- prior gamma SIGN --")
        brow("prior POS gamma", g[g.gex_prev >= 0]); brow("prior NEG gamma", g[g.gex_prev < 0])
        print("-- prior MQ regime LABEL --")
        for r in g.greg_prev.dropna().unique():
            brow(f"prior label={r}", g[g.greg_prev == r])
        print("-- prior gamma MAGNITUDE (|gex| causal pctile) --")
        brow("|gamma| top-third", g[g.absrank >= 0.667])
        brow("|gamma| mid-third", g[(g.absrank >= 0.333) & (g.absrank < 0.667)])
        brow("|gamma| bottom-third", g[g.absrank < 0.333])
        print("-- prior SIGNED gamma extremes --")
        brow("strong POS (signrank>0.8)", g[g.signrank > 0.8])
        brow("strong NEG (signrank<0.2)", g[g.signrank < 0.2])


if __name__ == "__main__":
    main()
