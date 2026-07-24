"""The five decision checks on the COMMITTED SPEC (adr.30 x 6t x gap x EOD).
1 L/S split (x year)   3 top-10 removal   4 MC reshuffle maxDD dist
5 ADR-quintile buckets   + 2021 frequency explanation.
  python scripts/regime_2e_five_checks.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
mg = pd.read_csv(ROOT / "data" / "regime" / "mgmt_sweep_20260724.csv")
_b = pd.read_parquet(Path(r"C:/Users/Admin/myquant/data") / "bars" / "_continuous.parquet")
_b["Date"] = _b["DateTime"].dt.date.astype(str)
_d = _b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last")).reset_index()
_d["gap"] = ((_d.dO - _d.dC.shift(1)) / _d.dC.shift(1) * 100).abs()
s3 = mg[mg.variant == "retest6"].copy()
s3["gap"] = s3.Date.map(_d.set_index("Date")["gap"])
s3 = s3[s3.gap <= 0.54].sort_values("Date").reset_index(drop=True)   # committed spec book
s3["yr"] = s3.Date.str[:4]
rng = np.random.default_rng(83)


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else float("inf")


print("== 1) LONG vs SHORT ==")
for dr in ("L", "S"):
    x = s3[s3["dir"] == dr]
    print(f"{dr}: n={len(x):3d}  net {x.net.sum():+9,.0f}  $/tr {x.net.mean():+7.1f}  PF {pf(x.net)}")
print("\nby year x dir (PF):")
piv = s3.pivot_table(index="yr", columns="dir", values="net", aggfunc=pf)
cnt = s3.pivot_table(index="yr", columns="dir", values="net", aggfunc="size")
print(pd.concat([piv, cnt], axis=1, keys=["PF", "n"]).to_string())

print("\n== 3) TOP-10 REMOVAL ==")
drop = s3.nlargest(10, "net")
kept = s3.drop(drop.index)
print(f"full: PF {pf(s3.net)}  |  minus top-10 (avg winner {drop.net.mean():+,.0f}): "
      f"n={len(kept)} net {kept.net.sum():+,.0f}  PF {pf(kept.net)}")
d20 = s3.drop(s3.nlargest(20, "net").index)
print(f"minus top-20: net {d20.net.sum():+,.0f}  PF {pf(d20.net)}")

print("\n== 4) MONTE CARLO maxDD (5,000 reshuffles of trade order) ==")
vals = s3.net.values
dds = np.empty(5000)
for i in range(5000):
    p = rng.permutation(vals)
    eq = np.cumsum(p)
    dds[i] = (eq - np.maximum.accumulate(eq)).min()
q = np.percentile(dds, [50, 75, 95, 99])
print(f"realized path: -8,308 (test) / {float((s3.net.cumsum()-s3.net.cumsum().cummax()).min()):,.0f} (lifetime)")
print(f"reshuffled: median {q[0]:,.0f}  75th {q[1]:,.0f}  95th {q[2]:,.0f}  99th {q[3]:,.0f}")

print("\n== 5) ADR-QUINTILE BUCKETS ==")
b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
dly = b.groupby("Date").agg(dH=("High", "max"), dL=("Low", "min")).reset_index()
dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
s3a = s3.merge(dly[["Date", "adr10"]], on="Date", how="left")
s3a["q"] = pd.qcut(s3a.adr10, 5, labels=["Q1 low-vol", "Q2", "Q3", "Q4", "Q5 high-vol"])
t = s3a.groupby("q", observed=True).net.agg(n="size", net="sum", mean="mean").round(1)
t["PF"] = s3a.groupby("q", observed=True).net.apply(pf)
t["adr_range"] = s3a.groupby("q", observed=True).adr10.agg(lambda x: f"{x.min():.0f}-{x.max():.0f}pt")
print(t.to_string())

print("\n== 2021 FREQUENCY ==")
days_cov = b.groupby(b.Date.str[:4]).Date.nunique()
tr_yr = s3.groupby("yr").size()
for y in tr_yr.index:
    print(f"{y}: {tr_yr[y]:3d} trades / {days_cov.get(y,0):3d} covered sessions "
          f"= {tr_yr[y]/days_cov.get(y,1):.2f}/day")

# graphics
fig, axes = plt.subplots(2, 2, figsize=(15, 9), dpi=115)
ax = axes[0][0]
for dr, c in (("L", "#1f7a3d"), ("S", "#b23a2e")):
    x = s3[s3["dir"] == dr].sort_values("Date")
    ax.plot(range(len(x)), x.net.cumsum().values, lw=2, color=c,
            label=f"{dr}: n={len(x)} {x.net.sum():+,.0f}$ PF {pf(x.net)}")
ax.axhline(0, color="#c3c2b7", lw=1); ax.legend(frameon=False)
ax.set_title("1) Long vs Short equity", fontweight="bold")
ax = axes[0][1]
ax.hist(dds, bins=60, color="#9ec5f4", edgecolor="#2a78d6")
for v, lab in ((q[2], "95th"), (q[3], "99th")):
    ax.axvline(v, ls="--", color="#b23a2e"); ax.text(v, ax.get_ylim()[1]*0.9, f" {lab}\n {v:,.0f}", fontsize=9)
ax.axvline(-8308, ls="-", color="#33454d"); ax.text(-8308, ax.get_ylim()[1]*0.6, " realized\n test", fontsize=9)
ax.set_title("4) Monte-Carlo maxDD distribution (5,000 reshuffles)", fontweight="bold")
ax = axes[1][0]
tt = t.reset_index()
cols = ["#b23a2e" if v < 1 else "#1f7a3d" for v in tt.PF]
ax.bar(tt["q"].astype(str), tt.PF, color=cols, width=0.55)
for i, r in tt.iterrows():
    ax.text(i, r.PF + 0.02, f"{r.PF:.2f}\nn={r.n}", ha="center", fontsize=9, fontweight="bold")
ax.axhline(1.0, ls="--", color="#33454d")
ax.set_title("5) PF by ADR quintile", fontweight="bold")
ax = axes[1][1]
srt = np.sort(vals)[::-1]
cum = np.cumsum(srt)
ax.plot(range(1, len(cum) + 1), cum, lw=2, color="#4a3aa7")
ax.axhline(s3.net.sum(), ls="--", color="#8b8f96")
ax.set_xlabel("trades, best first"); ax.set_ylabel("cumulative $")
ax.set_title("3) Concentration: cumulative net, best-first", fontweight="bold")
for a_ in axes.flat:
    a_.grid(axis="y", color="#eceeed", lw=0.6)
    for s_ in ("top", "right"): a_.spines[s_].set_visible(False)
fig.tight_layout()
p = ROOT / "docs" / "living" / "five_checks_20260724.png"
fig.savefig(p, facecolor="white")
print("\nsaved", p)
