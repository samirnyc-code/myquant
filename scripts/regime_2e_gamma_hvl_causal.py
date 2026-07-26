"""GAMMA REGIME, THE USER'S ACTUAL METHOD (causal) — take the PRIOR-session HVL (gamma flip
level, known pre-open) and classify each 2E entry by whether its ENTRY PRICE is above (positive
gamma) or below (negative gamma) that level. No same-day look-ahead: prior-day HVL + entry price,
both known at entry.

Scale handling: ES entry_px is panama-adjusted; MQ HVL is real SPX. Map prior HVL into the ES
frame via that day's ES-SPX basis (basis = ES_close - SPX_close), which absorbs the panama offset
and cancels since entry and HVL share the same day's frame.

Reads oos_pertrade_full_20260725.csv (now with entry_px) + mq_regime_daily (hvl, spot) +
_db_es_5m_rth (ES daily close). Tests long-2E and full with-trend, per block AND modern-era.

  python scripts/regime_2e_gamma_hvl_causal.py
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
    row = f"{name:<26}"; ok = True
    for (y0, y1) in BLOCKS:
        b = m[(m.yr >= y0) & (m.yr <= y1)]
        mr = b.Rn.mean() if len(b) else float('nan')
        row += f"{mr:>+8.3f}" if len(b) else f"{'-':>8}"
        if not (len(b) and mr > 0):
            ok = False
    mod = m[m.yr >= 2021]
    print(row + f"  PF {pf(m.net):.2f} n={len(m):4d} | 2021+ PF {pf(mod.net):.2f} mR {mod.Rn.mean():+.3f} {'ROBUST' if ok else ''}")


def main():
    d = pd.read_csv(CSV)
    if "entry_px" not in d.columns:
        print("entry_px missing — re-run emitter with --full first"); sys.exit(1)
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)

    # daily ES close (panama) + SPX close/hvl (backfill), prior-session HVL in ES frame
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(MQ); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx_close"}).set_index("Date")
    dd = dd.join(esc, how="inner").sort_index()
    dd["basis"] = dd["es_close"] - dd["spx_close"]
    dd["hvl_es"] = dd["hvl"] + dd["basis"]              # SPX HVL mapped to ES frame
    dd["prior_hvl_es"] = dd["hvl_es"].shift(1)          # PRIOR session (causal)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[d.prior_hvl_es.notna()].copy()
    d["ggamma"] = np.where(d.entry_px > d.prior_hvl_es, "pos", "neg")  # user's method
    print(f"coverage: {len(d)} trades with prior-HVL | pos {100*(d.ggamma=='pos').mean():.0f}% / neg {100*(d.ggamma=='neg').mean():.0f}%")

    for nm, bk in (("LONG-2E", d[d.with_trend & (d.dir == "L")]),
                   ("FULL with-trend", d[d.with_trend])):
        print(f"\n===== {nm} by PRICE vs PRIOR-DAY HVL (causal, your method) =====")
        print(f"{'gate':<26}{'2010-13':>8}{'2014-17':>8}{'2018-21':>8}{'2022-26':>8}")
        brow("ALL", bk)
        brow("above prior HVL (pos)", bk[bk.ggamma == "pos"])
        brow("below prior HVL (neg)", bk[bk.ggamma == "neg"])

    print("\n===== FULL with-trend, ABOVE prior HVL — PER YEAR 2021+ (is it one-year-driven?) =====")
    full = d[d.with_trend]; pos = full[full.ggamma == "pos"]
    for y in range(2021, 2027):
        x = pos[pos.yr == y]; a = full[(full.yr == y) & (full.ggamma == "neg")]
        print(f"  {y}: ABOVE n={len(x):3d} PF {pf(x.net):.2f} mR {x.Rn.mean():+.3f}   |  below n={len(a):3d} PF {pf(a.net):.2f} mR {a.Rn.mean():+.3f}")


if __name__ == "__main__":
    main()
