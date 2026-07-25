"""Does the inverted-U in vol (MID-vol best, both extremes worse) hold PER YEAR
with FIXED tercile boundaries? If mid-vol beats the extremes most years, it's a
stationary conditioner where any monotone VIX rule is not. Fixed edges are derived
from 2021-2023 (train) and applied to 2024-2026 (test) to avoid look-ahead.

  python scripts/regime_2e_vol_invertedU.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
d = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy()
d["yr"] = d.Date.str[:4]
vx = pd.read_csv(MAIN / "data" / "vix_daily.csv"); vx["dd"] = pd.to_datetime(vx.date).dt.date.astype(str)
vx = vx.sort_values("dd"); vx["p"] = vx.close.shift(1)
d["vix"] = d.Date.map(vx.set_index("dd")["p"]); d = d.dropna(subset=["vix"]).reset_index(drop=True)

# FIXED tercile edges from TRAIN (2021-2023 trades)
train = d[d.yr <= "2023"]
e1, e2 = train.vix.quantile([1/3, 2/3])
print(f"trades {len(d)}   TRAIN(2021-23) VIX tercile edges: {e1:.1f} / {e2:.1f}  (low<{e1:.1f}  mid  high>{e2:.1f})\n")


def band(v):
    return np.where(v <= e1, "low", np.where(v <= e2, "mid", "high"))


d["b"] = band(d.vix)
years = sorted(d.yr.unique())
print("Per-year PF by FIXED vol band (mid should win / extremes should lag):")
print(f"{'yr':6}{'low':>18}{'mid':>18}{'high':>18}   mid-best?")
midbest = 0; midnotworst = 0; ny = 0
for y in years:
    yd = d[d.yr == y]; r = {}
    for bb in ["low", "mid", "high"]:
        x = yd[yd.b == bb]; r[bb] = (len(x), pf(x.net))
    pfs = {k: v[1] for k, v in r.items() if v[0] >= 6}
    tag = ""
    if len(pfs) == 3:
        ny += 1
        if r["mid"][1] == max(pfs.values()): midbest += 1; tag = "MID best"
        if r["mid"][1] != min(pfs.values()): midnotworst += 1; tag = tag or "mid not worst"
    print(f"{y:6}" + "".join(f"{r[b][1]:>10.2f}(n{r[b][0]:<3})" for b in ["low", "mid", "high"]) + f"   {tag}")
print(f"\nmid-vol was BEST in {midbest}/{ny} testable years; NOT-WORST in {midnotworst}/{ny}")

print("\nFull-sample bands:")
for bb in ["low", "mid", "high"]:
    x = d[d.b == bb]
    print(f"  {bb:5} n={len(x):3d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  PF {pf(x.net)}")

# mid-only rule vs base, OOS (2024-26)
oos = d[d.yr >= "2024"]
mid_oos = oos[oos.b == "mid"]
print(f"\nOOS 2024-26  base: n={len(oos)} net {oos.net.sum():+,.0f} PF {pf(oos.net)} $/tr {oos.net.mean():+.0f}")
print(f"OOS 2024-26  MID-only: n={len(mid_oos)} net {mid_oos.net.sum():+,.0f} PF {pf(mid_oos.net)} $/tr {mid_oos.net.mean():+.0f}")
ext_oos = oos[oos.b != "mid"]
print(f"OOS 2024-26  extremes(low+high): n={len(ext_oos)} net {ext_oos.net.sum():+,.0f} PF {pf(ext_oos.net)} $/tr {ext_oos.net.mean():+.0f}")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
bands = ["low", "mid", "high"]
for y in years:
    yd = d[d.yr == y]
    ax[0].plot(bands, [pf(yd[yd.b == b].net) for b in bands], "-o", lw=1.6, alpha=.8, label=y)
ax[0].plot(bands, [pf(d[d.b == b].net) for b in bands], "-o", lw=4, color="k", label="ALL", zorder=5)
ax[0].axhline(1, ls="--", color="#999"); ax[0].legend(frameon=False, fontsize=8, ncol=2)
ax[0].set_ylabel("PF"); ax[0].set_title("Inverted-U in vol holds most years\n(mid-vol beats both extremes)", fontweight="bold")
allb = [d[d.b == b].net for b in bands]
ax[1].bar(bands, [x.sum() for x in allb], color=["#c99", "#2e8b57", "#c99"])
for i, x in enumerate(allb):
    ax[1].annotate(f"PF {pf(x)}\nn={len(x)}", (i, x.sum()), textcoords="offset points", xytext=(0, 5), ha="center", fontweight="bold")
ax[1].set_title("Net by vol band (full sample)", fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "vol_invertedU_20260725.png", facecolor="white")
print("\nsaved docs/living/vol_invertedU_20260725.png")
