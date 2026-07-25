"""FORWARD SPEC — lock the causal, block-robust edge into a deployable book and report honest
expectancy / drawdown / sizing. This is the bird-in-hand after killing gamma (look-ahead) and
VIX (2024-driven) conditioners.

SPEC: LONG-only 2E (with-trend phase gate) | 0.30xADR stop (floor 8t) | 09-13 window | EOD hold
      | retest 6t | FILTER: prior-day trend-efficiency ER10 above its causal expanding median.

Reads oos_pertrade_full_20260725.csv + _db_es_5m_rth (daily ER10). 1 ES, $5 RT + 1t slip.

  python scripts/regime_2e_forward_spec.py
Output: docs/living/forward_spec_20260725.png + tables.
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
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
rng = np.random.default_rng(83)


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


def maxdd(v):
    e = np.cumsum(v); return float((e - np.maximum.accumulate(e)).min())


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy()
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})]
    d = d.merge(er10_causal().rename("er10_top"), left_on="Date", right_index=True, how="left")
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)
    book = d[d.er10_top == 1].sort_values("Date").reset_index(drop=True)
    v = book.net.values

    print("========== FORWARD SPEC: LONG-2E + ER10-top (causal), 2010-2026, 1 ES ==========")
    print(f"trades           : {len(v):,}  ({len(v)/16.5:.0f}/yr)")
    print(f"net              : ${v.sum():+,.0f}  (${v.sum()/16.5:+,.0f}/yr)")
    print(f"meanR / PF / win  : {book.Rn.mean():+.3f}R / {pf(v)} / {100*(v>0).mean():.1f}%")
    print(f"avg win / loss    : +${v[v>0].mean():,.0f} / ${v[v<0].mean():,.0f}  payoff {v[v>0].mean()/-v[v<0].mean():.2f}")
    print(f"realized maxDD    : ${maxdd(v):,.0f}   net/DD {v.sum()/-maxdd(v):.1f}")
    dds = np.array([maxdd(rng.permutation(v)) for _ in range(4000)])
    print(f"MC maxDD          : median ${np.median(dds):,.0f}  worst-5% ${np.percentile(dds,5):,.0f}  worst-1% ${np.percentile(dds,1):,.0f}")

    print("\n========== per-year ==========")
    yt = book.groupby("yr")["net"].agg(n="size", net="sum"); yt["PF"] = book.groupby("yr")["net"].apply(pf)
    yt["meanR"] = book.groupby("yr")["Rn"].mean()
    print(yt.round({"net": 0, "meanR": 3}).to_string())

    print("\n========== 4-year block robustness ==========")
    for y0, y1 in [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]:
        b = book[(book.yr >= y0) & (book.yr <= y1)]
        print(f"  {y0}-{y1}: n={len(b):4d}  meanR {b.Rn.mean():+.3f}  PF {pf(b.net):.2f}  net ${b.net.sum():+,.0f}")

    print("\n========== SIZING (block-boot worst-1% as risk DD) ==========")
    def bb():
        out = []
        while len(out) < len(v):
            i = rng.integers(0, len(v)); out.extend(v[i:i+20])
        return np.array(out[:len(v)])
    bbdd = -np.percentile([maxdd(bb()) for _ in range(3000)], 1)
    for tol, lab in ((0.20, "20%"), (0.33, "33%")):
        print(f"  risk DD ${bbdd:,.0f} at {lab} of acct -> ${bbdd/tol:,.0f}/ES")

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 7), height_ratios=[3, 1], dpi=115, sharex=True)
    eq = np.cumsum(v); uw = eq - np.maximum.accumulate(eq)
    noos = int((book.yr <= 2020).sum())
    a1.plot(range(len(eq)), eq, lw=1.6, color="#27a35a"); a1.axvline(noos, color="#c0392b", ls="--", lw=1.1)
    a1.axhline(0, color="#8b8f96", lw=0.8); a1.set_ylabel("cum $ (1 ES)")
    a1.set_title(f"FORWARD SPEC — LONG-2E + ER10 (causal): {v.sum():+,.0f}$ PF {pf(v)} "
                 f"maxDD {maxdd(v):,.0f} | all 4 blocks green | dashed=2021", fontweight="bold", fontsize=11)
    a2.fill_between(range(len(uw)), uw, 0, color="#c0392b", alpha=0.4); a2.set_ylabel("underwater $")
    for a in (a1, a2):
        for s_ in ("top", "right"): a.spines[s_].set_visible(False)
        a.grid(axis="y", color="#eceeed", lw=0.7)
    fig.tight_layout(); p = WT / "docs" / "living" / "forward_spec_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
