"""VALIDATION BATTERY for the stage-3/4 filters — the five demands (S83).

From existing trade files (instant):
  1. N per stage + trades removed by each filter
  2a. GAP THRESHOLD sweep surface (0.30..1.20%) on the retest6 all-days book
  2b. cancel-bars surface (from gapday_cancel run) - restated
  3. PF BY YEAR for every stage
  4. slip sensitivity: 1t vs 2t exit slip per stage
Charts: threshold curve, yearly PF heatmap, stage waterfall, slip bars.

The tick-pass part (regime_2e_validation_tick.py) runs separately:
  5. filters applied to STAGE-0 config + retest-depth 8t point.

  python scripts/regime_2e_validation.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "data" / "regime"
TRAIN_END = "2023-12-31"
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else float("inf")


# day features
b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last")).reset_index()
dly["gap_abs"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
gap_map = dly.set_index("Date")["gap_abs"].to_dict()

# stage books (all net of $5 + 1t slip already except volstops which is gross-of-slip)
vol = pd.read_csv(R / "volstops_20260724.csv")
s0 = vol[(vol["stop"] == "fx4p") & (vol.target == "eod")].copy(); s0["net"] -= 12.5
s1 = vol[(vol["stop"] == "adr.30") & (vol.target == "eod")].copy(); s1["net"] -= 12.5
mg = pd.read_csv(R / "mgmt_sweep_20260724.csv")
s2 = mg[mg.variant == "retest6"].copy()
gc_ = pd.read_csv(R / "gapday_cancel_20260724.csv")
s3 = gc_[(gc_.scope == "NRM") & (gc_.variant == "cxl999")].copy()
s4 = gc_[(gc_.scope == "NRM") & (gc_.variant == "cxl6")].copy()
STAGES = [("0: 4pt/4t", s0), ("1: adr.30 stop", s1), ("2: +retest6", s2),
          ("3: +skip gap>0.54", s3), ("4: +cxl 6 bars", s4)]

print("== 1) N PER STAGE / removed ==")
prev_n = None
for name, x in STAGES:
    rm = "" if prev_n is None else f"  removed {prev_n - len(x)}"
    print(f"{name:20s} n={len(x):4d}{rm}")
    prev_n = len(x)

print("\n== 3) PF BY YEAR per stage ==")
yr_tab = {}
for name, x in STAGES:
    x = x.copy(); x["yr"] = x.Date.str[:4]
    yr_tab[name] = x.groupby("yr").net.apply(pf)
yrdf = pd.DataFrame(yr_tab).round(2)
print(yrdf.to_string())

print("\n== 4) SLIP SENSITIVITY (exit slip 1t -> 2t) ==")
for name, x in STAGES:
    n2 = x.net - 12.5
    print(f"{name:20s} 1t: {x.net.mean():+6.1f}$/tr PF {pf(x.net):4.2f}   |   "
          f"2t: {n2.mean():+6.1f}$/tr PF {pf(n2):4.2f}")

# 2a) gap threshold sweep on the stage-2 book (retest6 all days)
print("\n== 2a) GAP THRESHOLD surface (stage-2 book, skip days with |gap|>thr) ==")
s2g = s2.copy(); s2g["gap"] = s2g.Date.map(gap_map)
thr_rows = []
for thr in [0.30, 0.40, 0.50, 0.54, 0.60, 0.70, 0.80, 1.00, 1.20, 99.0]:
    x = s2g[s2g.gap <= thr]
    trn, tst = x[x.Date <= TRAIN_END], x[x.Date > TRAIN_END]
    thr_rows.append((thr, len(x), round(x.net.mean(), 1), pf(x.net),
                     pf(trn.net), pf(tst.net)))
    print(f"thr {thr:5.2f}%  n={len(x):4d}  $/tr {x.net.mean():+7.1f}  PF {pf(x.net):4.2f}  "
          f"train {pf(trn.net):4.2f} | test {pf(tst.net):4.2f}")
thr_df = pd.DataFrame(thr_rows, columns=["thr", "n", "tr", "PF", "PF_tr", "PF_te"])

# charts
fig, axes = plt.subplots(2, 2, figsize=(14, 9), dpi=110)
ax = axes[0][0]
tt = thr_df[thr_df.thr < 99]
ax.plot(tt.thr, tt.PF_tr, "o-", color="#2a78d6", label="train PF")
ax.plot(tt.thr, tt.PF_te, "o-", color="#eb6834", label="test PF")
ax.axvline(0.54, ls="--", color="#8b8f96"); ax.text(0.545, ax.get_ylim()[0], "adopted", fontsize=9)
ax.set_xlabel("skip days with |gap| > thr (%)"); ax.set_ylabel("PF"); ax.legend(frameon=False)
ax.set_title("Gap-threshold surface (stage-2 book)", fontweight="bold")

ax = axes[0][1]
cx = []
for v in ["cxl1", "cxl2", "cxl3", "cxl6", "cxl12", "cxl999"]:
    x = gc_[(gc_.scope == "NRM") & (gc_.variant == v)]
    trn, tst = x[x.Date <= TRAIN_END], x[x.Date > TRAIN_END]
    cx.append((v.replace("cxl", ""), pf(trn.net), pf(tst.net)))
cxd = pd.DataFrame(cx, columns=["bars", "tr", "te"])
ax.plot(cxd.bars, cxd.tr, "o-", color="#2a78d6", label="train PF")
ax.plot(cxd.bars, cxd.te, "o-", color="#eb6834", label="test PF")
ax.set_xlabel("cancel unfilled limit after N bars"); ax.legend(frameon=False)
ax.set_title("Limit-lifetime surface (gap-filtered book)", fontweight="bold")

ax = axes[1][0]
m = yrdf.T
im = ax.imshow(m.values.astype(float), cmap="RdYlGn", vmin=0.5, vmax=1.7, aspect="auto")
ax.set_xticks(range(len(m.columns)), m.columns)
ax.set_yticks(range(len(m.index)), [i.split(":")[0] for i in m.index])
for i in range(m.shape[0]):
    for j in range(m.shape[1]):
        v = m.values[i, j]
        if np.isfinite(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9, fontweight="bold")
ax.set_title("PF by YEAR x stage (heatmap)", fontweight="bold")

ax = axes[1][1]
names = [n_.split(":")[0] for n_, _ in STAGES]
ns = [len(x) for _, x in STAGES]
pfs = [pf(x.net) for _, x in STAGES]
ax2 = ax.twinx()
ax.bar(names, ns, color="#9ec5f4", width=0.55)
ax2.plot(names, pfs, "o-", color="#b23a2e", lw=2)
ax.set_ylabel("trades (bars)"); ax2.set_ylabel("PF (line)", color="#b23a2e")
ax.set_title("N shrinks as PF rises — the shape of selection risk", fontweight="bold")
for a_ in axes.flat:
    a_.grid(axis="y", color="#eceeed", lw=0.6)
fig.tight_layout()
p = ROOT / "docs" / "living" / "validation_battery_20260724.png"
fig.savefig(p, facecolor="white")
print("\nsaved", p)
