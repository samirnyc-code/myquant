"""Vol-stop study report: full grids + per-year + profiles + PNGs (equity, heatmaps).

  python scripts/regime_2e_volstops_report.py
Writes docs/living/volstops_equity_20260724.png + volstops_heatmap_20260724.png
and prints every table.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "volstops_20260724.csv")
d["is_tr"] = d.Date <= "2023-12-31"
STOPS = ["abr1.0", "abr1.5", "abr2.0", "abr3.0", "abr4.0",
         "adr.10", "adr.15", "adr.20", "adr.30", "fx4p"]
TGT = ["eod", "t2x", "t3x"]


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else float("inf")


rows = []
for sid in STOPS:
    for t in TGT:
        x = d[(d["stop"] == sid) & (d.target == t)]
        if not len(x):
            continue
        trn, tst = x[x.is_tr], x[~x.is_tr]
        rows.append((sid, t, len(x), round(x.dist_pts.median(), 1),
                     round((x.net > 0).mean() * 100, 1), round(trn.net.sum()),
                     pf(trn.net), round(tst.net.sum()), pf(tst.net),
                     round(x.net.sum())))
grid = pd.DataFrame(rows, columns=["stop", "target", "n", "medStop", "win%",
                                   "net_tr", "PF_tr", "net_te", "PF_te", "net_tot"])
print("== FULL GRID =="); print(grid.to_string(index=False))

LEAD = ["adr.30", "abr3.0", "abr1.5", "fx4p"]
print("\n== PER-YEAR (EOD hold) ==")
for sid in LEAD:
    x = d[(d["stop"] == sid) & (d.target == "eod")].copy()
    x["yr"] = x.Date.str[:4]
    t = x.groupby("yr").net.agg(n="size", net="sum")
    t["PF"] = x.groupby("yr").net.apply(pf)
    print(f"\n-- {sid} --"); print(t.to_string())

print("\n== PROFILE (EOD hold) ==")
for sid in LEAD:
    x = d[(d["stop"] == sid) & (d.target == "eod")].sort_values("Date")
    eq = x.net.cumsum(); dd = (eq - eq.cummax()).min()
    w = x[x.net > 0]; l = x[x.net <= 0]
    print(f"{sid:7s} n={len(x)} win%={(x.net>0).mean()*100:4.1f} avgW={w.net.mean():+7.0f} "
          f"avgL={l.net.mean():+6.0f} maxDD={dd:+9.0f} net/DD={x.net.sum()/-dd:4.2f} "
          f"worst={x.net.min():+6.0f} L_PF={pf(x[x['dir']=='L'].net)} S_PF={pf(x[x['dir']=='S'].net)}")

# equity curves
fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
COLS = {"adr.30": "#2a78d6", "abr3.0": "#eb6834", "abr1.5": "#1baf7a", "fx4p": "#8b8f96"}
for sid in LEAD:
    x = d[(d["stop"] == sid) & (d.target == "eod")].sort_values("Date")
    ax.plot(range(len(x)), x.net.cumsum().values, lw=2 if sid != "fx4p" else 1.4,
            color=COLS[sid], label=f"{sid}  ({x.net.sum():+,.0f}$)")
yrs = d[(d["stop"] == "fx4p") & (d.target == "eod")].sort_values("Date").Date.str[:4].values
for i in range(1, len(yrs)):
    if yrs[i] != yrs[i - 1]:
        ax.axvline(i, color="#e3e2dc", lw=0.8)
        ax.text(i, ax.get_ylim()[0], yrs[i], fontsize=9, color="#8b8f96")
ax.axhline(0, color="#c3c2b7", lw=1)
ax.legend(frameon=False); ax.grid(axis="y", color="#eceeed", lw=0.7)
for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
ax.set_title("Vol-scaled stops × EOD hold — closed equity, strict fills, 1 ES",
             fontweight="bold")
fig.tight_layout()
p1 = ROOT / "docs" / "living" / "volstops_equity_20260724.png"
fig.savefig(p1, facecolor="white"); plt.close(fig)

# heatmaps: PF train / PF test
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), dpi=115)
for ax, col, ttl in ((axes[0], "PF_tr", "PF — train 2021-23"),
                     (axes[1], "PF_te", "PF — test 2024-26")):
    m = grid.pivot(index="stop", columns="target", values=col).reindex(STOPS)[TGT]
    im = ax.imshow(m.values, cmap="RdYlGn", vmin=0.4, vmax=1.6, aspect="auto")
    ax.set_xticks(range(len(TGT)), TGT); ax.set_yticks(range(len(STOPS)), STOPS)
    for i in range(len(STOPS)):
        for j in range(len(TGT)):
            v = m.values[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=10,
                        fontweight="bold", color="#111")
    ax.set_title(ttl, fontweight="bold")
fig.colorbar(im, ax=axes, shrink=0.8, label="profit factor")
p2 = ROOT / "docs" / "living" / "volstops_heatmap_20260724.png"
fig.savefig(p2, facecolor="white"); plt.close(fig)
print(f"\nsaved {p1}\nsaved {p2}")
