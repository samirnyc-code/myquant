"""GAMMA REGIME x HVL PROXIMITY x three-book trades — S83 (Samir's idea, 2026-07-25).

Daily gamma file: data/regime/mq_regime_daily_2007_2026_v2.csv (spot, hvl, regime,
net_total_gex). Both spot & hvl are in the SAME basis, so distance-as-%-of-spot is
basis-independent (works despite our panama-adjusted ES).

Features joined to each three-book trade by date (all known at/ before the open):
  gamma_regime  : positive_gamma / negative_gamma (dealers suppress vs amplify vol)
  net_gex       : net total gamma (magnitude of the regime)
  hvl_dist_pct  : (spot - hvl)/spot*100  (signed: + = spot ABOVE hvl)
  |hvl_dist|    : proximity magnitude (near hvl = pinning/chop; far = room to run)
  side_hvl      : above/below

Hypothesis: trend-harvest 2E should work BETTER in NEGATIVE gamma (dealers amplify ->
trends) and FAR from HVL (room to run); WORSE in positive gamma / near HVL (pinning).
Uses PRIOR-day gamma (shift 1) to stay causal (today's gamma is EOD-computed).

  python scripts/regime_2e_gamma_hvl.py
Output: data/regime/gamma_hvl_20260725.csv + tables + PNG.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
TRAIN_END = "2023-12-31"


def pf(s):
    s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0


# gamma daily (use PRIOR day's regime -> causal at today's open)
gm = pd.read_csv(MAIN / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv")
gm["date"] = pd.to_datetime(gm.date).dt.date.astype(str)
gm = gm.sort_values("date")
gm["hvl_dist_pct"] = (gm.spot - gm.hvl) / gm.spot * 100
for c in ["regime", "hvl_dist_pct", "net_total_gex"]:
    gm[c + "_p"] = gm[c].shift(1)          # prior-day (causal)
gmap = gm.set_index("date")

# three-book trades
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
d = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy()
d["reg"] = d.Date.map(gmap["regime_p"])
d["hvl_dist"] = d.Date.map(gmap["hvl_dist_pct_p"])
d["gex"] = d.Date.map(gmap["net_total_gex_p"])
d = d.dropna(subset=["reg", "hvl_dist"])
d["is_tr"] = d.Date <= TRAIN_END
d["absdist"] = d.hvl_dist.abs()
d.to_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv", index=False)
print(f"three-book trades with prior-day gamma joined: {len(d)}")
print(f"overall: net {d.net.sum():+,.0f}  PF {pf(d.net)}")

print("\n===== 1) GAMMA REGIME (prior-day) =====")
for r, x in d.groupby("reg"):
    trn, tst = x[x.is_tr], x[~x.is_tr]
    print(f"  {r:16s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  "
          f"PF {pf(x.net):4.2f}  (tr {pf(trn.net)} te {pf(tst.net)})")

print("\n===== 2) HVL PROXIMITY (|spot-hvl| as % of spot), quartiles =====")
d["pq"] = pd.qcut(d.absdist, 4, labels=["Q1 nearest", "Q2", "Q3", "Q4 farthest"])
for q, x in d.groupby("pq", observed=True):
    trn, tst = x[x.is_tr], x[~x.is_tr]
    print(f"  {str(q):12s} (|dist| {x.absdist.min():.2f}-{x.absdist.max():.2f}%)  n={len(x):4d}  "
          f"net {x.net.sum():+8,.0f}  PF {pf(x.net):4.2f}  (tr {pf(trn.net)} te {pf(tst.net)})")

print("\n===== 3) SIDE of HVL (spot above/below) x trade dir =====")
d["side"] = np.where(d.hvl_dist >= 0, "spot>HVL", "spot<HVL")
for (sd, dr), x in d.groupby(["side", "dir"]):
    if len(x) < 20:
        continue
    print(f"  {sd:9s} {dr}: n={len(x):4d}  net {x.net.sum():+7,.0f}  PF {pf(x.net):4.2f}")

print("\n===== 4) INTERACTION: gamma regime x proximity =====")
d["near"] = np.where(d.absdist <= d.absdist.median(), "near-HVL", "far-HVL")
piv = d.pivot_table(index="reg", columns="near", values="net", aggfunc=pf)
cnt = d.pivot_table(index="reg", columns="near", values="net", aggfunc="size")
print("PF:"); print(piv.to_string()); print("n:"); print(cnt.to_string())

print("\n===== 5) candidate filters (train+test both must beat base) =====")
base_tr, base_te = pf(d[d.is_tr].net), pf(d[~d.is_tr].net)
print(f"  BASE: PF {pf(d.net)} (tr {base_tr} te {base_te}), n={len(d)}, $/tr {d.net.mean():+.0f}")
cands = {
    "neg-gamma only": d.reg == "negative_gamma",
    "pos-gamma only": d.reg == "positive_gamma",
    "far-HVL only (>median)": d.absdist > d.absdist.median(),
    "near-HVL only": d.absdist <= d.absdist.median(),
    "neg-gamma & far-HVL": (d.reg == "negative_gamma") & (d.absdist > d.absdist.median()),
}
for nm, m in cands.items():
    x = d[m]; trn, tst = x[x.is_tr], x[~x.is_tr]
    better = pf(trn.net) > base_tr and pf(tst.net) > base_te and x.net.mean() > d.net.mean()
    print(f"  {nm:24s} keep {len(x):4d}/{len(d)}  $/tr {x.net.mean():+6.1f}  PF {pf(x.net):4.2f}  "
          f"(tr {pf(trn.net)} te {pf(tst.net)}){'  <== CANDIDATE' if better else ''}")

fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=115)
for r, c in (("negative_gamma", "#b23a2e"), ("positive_gamma", "#2a78d6")):
    x = d[d.reg == r].sort_values("Date")
    ax[0].plot(range(len(x)), x.net.cumsum().values, lw=2, color=c, label=f"{r} (PF {pf(x.net)})")
ax[0].axhline(0, color="#c3c2b7", lw=1); ax[0].legend(frameon=False)
ax[0].set_title("Equity by prior-day gamma regime", fontweight="bold")
pq = d.groupby("pq", observed=True).net.apply(pf)
ax[1].bar(range(len(pq)), pq.values, color="#2a78d6")
ax[1].set_xticks(range(len(pq))); ax[1].set_xticklabels(pq.index, rotation=20, fontsize=8)
ax[1].axhline(1, ls="--", color="#33454d"); ax[1].set_title("PF by HVL-proximity quartile", fontweight="bold")
for a in ax:
    a.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "gamma_hvl_20260725.png", facecolor="white")
print("\nsaved docs/living/gamma_hvl_20260725.png")
