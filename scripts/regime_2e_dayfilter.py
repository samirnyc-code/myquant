"""DAY-TYPE FILTER sweep on the best book (adr.30 stop x retest6 x EOD) — +10% lever 2.

All filters use ONLY information available before the 09:00 window opens:
  |gap|%          : |open - prior close| / prior close
  prev_rng ratio  : prior-day range / ADR10
  adr trend       : ADR5 / ADR10  (vol expanding vs contracting)
  VIX             : prior close
  DOW             : day of week
Cut points fit on TRAIN quartiles only; evaluated train/test. Also 2-filter combos.

Reads the retest6 trades from mgmt_sweep_20260724.csv (net of all costs already).
Output: data/regime/dayfilter_20260724.csv + tables + PNG.
  python scripts/regime_2e_dayfilter.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
TRAIN_END = "2023-12-31"

tr = pd.read_csv(ROOT / "data" / "regime" / "mgmt_sweep_20260724.csv")
tr = tr[tr.variant == "retest6"].copy()

b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
dly = b.groupby("Date").agg(dO=("Open", "first"), dH=("High", "max"),
                            dL=("Low", "min"), dC=("Close", "last")).reset_index()
dly["rng"] = dly.dH - dly.dL
dly["adr10"] = dly.rng.rolling(10).mean().shift(1)
dly["adr5"] = dly.rng.rolling(5).mean().shift(1)
dly["prevC"] = dly.dC.shift(1)
dly["prev_rng"] = dly.rng.shift(1)
dly["gap_abs"] = (dly.dO - dly.prevC).abs() / dly.prevC * 100
dly["prev_ratio"] = dly.prev_rng / dly.adr10
dly["adr_trend"] = dly.adr5 / dly.adr10
dly["dow"] = pd.to_datetime(dly.Date).dt.dayofweek
vix = pd.read_csv(ROOT / "data" / "VIX_History.csv")
vix["Date"] = pd.to_datetime(vix.DATE).dt.date.astype(str)
vix = vix.sort_values("Date")
vix["vix_prev"] = vix.CLOSE.shift(1)
dly = dly.merge(vix[["Date", "vix_prev"]], on="Date", how="left")

d = tr.merge(dly[["Date", "gap_abs", "prev_ratio", "adr_trend", "vix_prev", "dow"]],
             on="Date", how="left")
d["is_tr"] = d.Date <= TRAIN_END


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else float("inf")


def stats(x):
    if not len(x):
        return (0, 0, 0, 0, 0, 0)
    eq = x.sort_values("Date").net.cumsum()
    dd = float((eq - eq.cummax()).min()) if len(eq) else 0
    trn, tst = x[x.is_tr], x[~x.is_tr]
    return (len(x), round(x.net.mean(), 1), pf(x.net), round(dd),
            f"{trn.net.sum():+,.0f}/{pf(trn.net)}", f"{tst.net.sum():+,.0f}/{pf(tst.net)}")


trn_d = d[d.is_tr]
conds = {"none": pd.Series(True, d.index)}
for c in ["gap_abs", "prev_ratio", "adr_trend", "vix_prev"]:
    q1, q3 = trn_d[c].quantile(0.25), trn_d[c].quantile(0.75)
    conds[f"{c}<=q3"] = d[c] <= q3          # skip the top-quartile days
    conds[f"{c}>=q1"] = d[c] >= q1          # skip the bottom-quartile days
conds["not_monday"] = d.dow != 0
conds["not_friday"] = d.dow != 4

rows = []
names = list(conds)
for nm in names:
    x = d[conds[nm]]
    rows.append((nm, "") + stats(x))
# 2-combos of the singles that don't butcher n
for i in range(1, len(names)):
    for j in range(i + 1, len(names)):
        m = conds[names[i]] & conds[names[j]]
        if m.sum() < 500:
            continue
        rows.append((names[i], names[j]) + stats(d[m]))
res = pd.DataFrame(rows, columns=["f1", "f2", "n", "$/tr", "PF", "maxDD",
                                  "train", "test"])
res.to_csv(ROOT / "data" / "regime" / "dayfilter_20260724.csv", index=False)
print(res.to_string(index=False))

base = d
best = res.iloc[1:].sort_values("$/tr", ascending=False).head(6)
fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
eqb = base.sort_values("Date").net.cumsum()
ax.plot(range(len(eqb)), eqb.values, lw=1.6, color="#8b8f96",
        label=f"no filter ({base.net.sum():+,.0f}$)")
palette = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]
for k, (_, r) in enumerate(best.iterrows()):
    m = conds[r.f1] & (conds[r.f2] if r.f2 else pd.Series(True, d.index))
    x = d[m].sort_values("Date")
    ax.plot(range(len(x)), x.net.cumsum().values, lw=1.6, color=palette[k % 6],
            label=f"{r.f1}{' & '+r.f2 if r.f2 else ''} ({x.net.sum():+,.0f}$)")
ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False, fontsize=8.5)
ax.grid(axis="y", color="#eceeed", lw=0.7)
for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
ax.set_title("Day-type filters on adr.30 x retest6 x EOD — net of all costs", fontweight="bold")
fig.tight_layout()
p = ROOT / "docs" / "living" / "dayfilter_20260724.png"
fig.savefig(p, facecolor="white")
print("saved", p)
