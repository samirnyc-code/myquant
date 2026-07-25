"""Is the VIX->system relationship STATIONARY, or did it really flip 2022 vs 2024-26?
If absolute VIX flips sign across years but a NORMALISED vol measure (percentile,
vs-SMA, rate-of-change) stays consistent, that normalised measure is the usable
conditioner. If nothing is stable across years -> conditioning on vol is unsafe and
the unconditional base is the right call.

Full 5yr three-book (678), prior-day (causal) VIX features. Per-year PF for HI vs LO
half of each feature: a usable signal keeps the SAME sign every year.

  python scripts/regime_2e_vix_stationarity.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


# three-book trades
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
d = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy()
d["yr"] = d.Date.str[:4]

# VIX features on the daily series, then shift(1) -> known at open
vx = pd.read_csv(MAIN / "data" / "vix_daily.csv"); vx["dd"] = pd.to_datetime(vx.date).dt.date.astype(str)
vx = vx.sort_values("dd").reset_index(drop=True)
vx["lvl"] = vx.close
vx["pct252"] = vx.close.rolling(252).apply(lambda w: (w < w.iloc[-1]).mean(), raw=False) * 100
vx["sma20"] = vx.close.rolling(20).mean(); vx["vs_sma"] = vx.close / vx.sma20
vx["chg5"] = vx.close - vx.close.shift(5)
for c in ["lvl", "pct252", "vs_sma", "chg5"]:
    vx[c + "_p"] = vx[c].shift(1)          # causal
vm = vx.set_index("dd")
for c in ["lvl", "pct252", "vs_sma", "chg5"]:
    d[c] = d.Date.map(vm[c + "_p"])
d = d.dropna(subset=["lvl", "pct252", "vs_sma", "chg5"]).reset_index(drop=True)

FEATS = [("lvl", "abs VIX level"), ("pct252", "VIX %ile (252d)"),
         ("vs_sma", "VIX / 20d-SMA"), ("chg5", "VIX 5d change")]
years = sorted(d.yr.unique())
print(f"trades {len(d)}   overall PF {pf(d.net)}\n")
print("Per-year PF of the LO half (below median) — a stationary signal keeps LO consistently good/bad:")
print(f"{'feature':18}" + "".join(f"{y:>8}" for y in years) + f"{'ALLlo':>8}{'ALLhi':>8}{'consistent?':>13}")
for c, lab in FEATS:
    med = d[c].median(); lo = d[d[c] <= med]; hi = d[d[c] > med]
    per = []
    for y in years:
        yl = lo[lo.yr == y]
        per.append(pf(yl.net) if len(yl) >= 8 else np.nan)
    # consistency: does LO-half beat HI-half in the same direction every year with enough n?
    signs = []
    for y in years:
        yl, yh = lo[lo.yr == y], hi[hi.yr == y]
        if len(yl) >= 8 and len(yh) >= 8:
            signs.append(np.sign(pf(yl.net) - pf(yh.net)))
    consistent = "YES" if len(set(signs)) == 1 and signs else f"no ({signs.count(1)}+/{signs.count(-1)}-)"
    print(f"{lab:18}" + "".join(f"{p:>8.2f}" if not np.isnan(p) else f"{'-':>8}" for p in per)
          + f"{pf(lo.net):>8.2f}{pf(hi.net):>8.2f}{consistent:>13}")

print("\nExplicit VIX-level flip (LO=calm vs HI=elevated), net per year:")
med = d.lvl.median()
for y in years:
    yl = d[(d.yr == y) & (d.lvl <= med)]; yh = d[(d.yr == y) & (d.lvl > med)]
    print(f"  {y}  calm n={len(yl):3d} {yl.net.sum():+7,.0f}/PF{pf(yl.net):<5}  elevated n={len(yh):3d} {yh.net.sum():+7,.0f}/PF{pf(yh.net)}")

print("\nBest stationary conditioner -> tercile detail (full sample):")
for c, lab in FEATS:
    d["t"] = pd.qcut(d[c], 3, labels=["low", "mid", "high"], duplicates="drop")
    parts = "  ".join(f"{t}:PF{pf(d[d.t==t].net)}/{d[d.t==t].net.mean():+.0f}$" for t in d.t.cat.categories)
    print(f"  {lab:18} {parts}")
