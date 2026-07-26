"""HVL-GATED 2E — within-modern-era TRAIN/TEST. The 2E>HVL book (PF 1.50, net/DD 9.6) is on
2021-2026, all in-sample for the 'above HVL' cut. Honest test: TRAIN 2021-2023, HOLD OUT
2024-2026, tune NOTHING, and check (a) the book holds OOS and (b) the above/below-HVL regime
split itself generalizes (not just the aggregate).

Spec is a FIXED rule (no fitted params): with-trend 2E | entry above prior-day HVL | 0.30xADR
stop | 09-13 | EOD hold. The stop/window are inherited from the original 2021-23 spec.

Reads oos_pertrade_full (entry_px) + mq_regime_daily (hvl) + _db_es_5m_rth (ES close, basis).

  python scripts/regime_2e_hvl_traintest.py
Output: docs/living/hvl_traintest_20260725.png + tables.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def maxdd(v):
    e = np.cumsum(v); return float((e - np.maximum.accumulate(e)).min())


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13}) & d.with_trend].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values); d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spx": "spx"}).set_index("Date")
    dd = dd.rename(columns={"spot": "spx"}).join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    d = d[(d.prior_hvl_es.notna()) & (d.yr >= 2021)].copy()
    d["above"] = d.entry_px > d.prior_hvl_es
    tr = d[d.yr <= 2023]; te = d[d.yr >= 2024]

    def show(nm, x):
        ab = x[x.above]; be = x[~x.above]
        print(f"  {nm:<18} above-HVL: n={len(ab):4d} PF {pf(ab.net):.2f} net ${ab.net.sum():+8,.0f} mR {ab.Rn.mean():+.3f}   "
              f"|  below-HVL: n={len(be):4d} PF {pf(be.net):.2f} net ${be.net.sum():+8,.0f}")

    print("=== HVL-gated 2E: does the above/below split generalize OOS? ===")
    show("TRAIN 2021-2023", tr)
    show("TEST  2024-2026", te)

    print("\n=== the traded book (above-HVL, two-sided) — TRAIN vs HOLDOUT ===")
    for nm, x in (("TRAIN 2021-23", tr[tr.above]), ("HOLDOUT 2024-26", te[te.above])):
        v = x.net.values
        print(f"  {nm:<16} n={len(v):4d} ({len(v)/(2.5 if 'TRAIN' in nm else 2.5):.0f}/yr)  net ${v.sum():+8,.0f}  PF {pf(v):.2f}  "
              f"meanR {x.Rn.mean():+.3f}  win {100*(v>0).mean():.0f}%  maxDD ${maxdd(x.sort_values('Date').net.values):+,.0f}")
        print(f"     L: PF {pf(x[x.dir=='L'].net):.2f} ${x[x.dir=='L'].net.sum():+,.0f}  |  S: PF {pf(x[x.dir=='S'].net):.2f} ${x[x.dir=='S'].net.sum():+,.0f}")

    print("\n=== HOLDOUT by year ===")
    hb = te[te.above]
    for y in (2024, 2025, 2026):
        x = hb[hb.yr == y]; print(f"  {y}: n={len(x):3d} PF {pf(x.net):.2f} net ${x.net.sum():+,.0f} mR {x.Rn.mean():+.3f}")

    # chart: train then holdout, one equity, boundary marked
    full = d[d.above].sort_values("Date"); v = full.net.values; eq = np.cumsum(v)
    ntr = int((full.yr <= 2023).sum())
    fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
    ax.plot(range(ntr), eq[:ntr], lw=1.8, color="#8b8f96", label=f"TRAIN 2021-23: {v[:ntr].sum():+,.0f} PF {pf(v[:ntr])}")
    ax.plot(range(ntr - 1, len(eq)), eq[ntr - 1:], lw=2, color="#27a35a", label=f"HOLDOUT 2024-26: {v[ntr:].sum():+,.0f} PF {pf(v[ntr:])}")
    ax.axvline(ntr, color="#c0392b", ls="--", lw=1.2); ax.axhline(0, color="#c3c2b7", lw=0.8)
    ax.legend(frameon=False); ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("HVL-gated two-sided 2E — TRAIN 2021-23 / HOLDOUT 2024-26 (tune nothing)", fontweight="bold")
    fig.tight_layout(); p = WT / "docs" / "living" / "hvl_traintest_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
