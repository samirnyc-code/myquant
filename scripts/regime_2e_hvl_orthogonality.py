"""Is HVL-proximity ORTHOGONAL to the gap filter, or redundant with it?
The three-book trades already have gap<=0.54 applied. Question: does near-HVL still
stratify outcomes AFTER controlling for gap? If near>far inside every gap bucket ->
additive (HVL earns a size-lean). If the HVL effect vanishes once gap is controlled
-> redundant (close the gamma book).

Tests:
  1 corr(|HVL dist|, gap)
  2 2x2: (near/far HVL) x (low/high gap, within the allowed <=0.54 band)
  3 near-vs-far HVL inside gap terciles (does HVL survive gap control?)
  4 gap-vs-HVL: which better separates winners? (PF spread of each stratifier)

  python scripts/regime_2e_hvl_orthogonality.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv")
# per-trade gap from continuous OHLC
b = pd.read_parquet(MAIN / "data" / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
dd = b.groupby("Date").agg(o=("Open", "first"), c=("Close", "last")).reset_index()
dd["gap"] = (dd.o - dd.c.shift(1)).abs() / dd.c.shift(1) * 100
d = d.merge(dd[["Date", "gap"]], on="Date", how="left").dropna(subset=["gap", "absdist"])
med = d.absdist.median()
print(f"trades {len(d)}   (all already gap<=0.54)   overall PF {pf(d.net)}\n")

print(f"1) corr(|HVL dist|, gap) = {d.absdist.corr(d.gap, 'spearman'):+.2f}  "
      f"(near 0 => the two carry different info)")

print("\n2) 2x2  (near/far HVL) x (low/high gap, split at gap median):")
gmed = d.gap.median(); near = d.absdist <= med; logap = d.gap <= gmed
for nm, nmask in [("near-HVL", near), ("far-HVL", ~near)]:
    for gm_, gmask in [("lo-gap", logap), ("hi-gap", ~logap)]:
        x = d[nmask & gmask]
        print(f"   {nm:8} {gm_}: n={len(x):3d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  PF {pf(x.net)}")

print("\n3) near-vs-far HVL INSIDE gap terciles (HVL survives gap control if near>far each row):")
d["gt"] = pd.qcut(d.gap, 3, labels=["gap-low", "gap-mid", "gap-high"])
print(f"   {'gap band':10}{'near PF':>10}{'far PF':>10}{'near $/tr':>11}{'far $/tr':>10}   HVL adds?")
survive = 0
for g in d["gt"].cat.categories:
    x = d[d["gt"] == g]; nr = x[x.absdist <= med]; fr = x[x.absdist > med]
    add = pf(nr.net) > pf(fr.net) and nr.net.mean() > fr.net.mean()
    survive += add
    print(f"   {str(g):10}{pf(nr.net):>10.2f}{pf(fr.net):>10.2f}{nr.net.mean():>11.0f}{fr.net.mean():>10.0f}   {'YES' if add else 'no'}")
print(f"   -> near beat far in {survive}/3 gap bands")

print("\n4) which stratifier separates winners better (PF spread hi-vs-lo half)?")
for nm, key in [("|HVL dist|", "absdist"), ("gap", "gap")]:
    m = d[key] <= d[key].median()
    print(f"   {nm:11}: favorable-half PF {pf(d[m].net)}  vs  unfavorable-half PF {pf(d[~m].net)}  "
          f"(spread {pf(d[m].net)-pf(d[~m].net):+.2f})")

# verdict
d["gt2"] = pd.qcut(d.gap, 3, labels=[0, 1, 2]).astype(int)
nr_all = [d[(d.gt2 == g) & (d.absdist <= med)].net.mean() for g in range(3)]
fr_all = [d[(d.gt2 == g) & (d.absdist > med)].net.mean() for g in range(3)]
print(f"\nVERDICT: HVL near-minus-far $/tr within gap bands = "
      f"{[round(a-b) for a, b in zip(nr_all, fr_all)]}  "
      f"-> {'ADDITIVE (survives gap control)' if survive >= 2 else 'REDUNDANT with gap (close it)'}")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
grid = np.array([[pf(d[(d.absdist<=med)&(d.gap<=gmed)].net), pf(d[(d.absdist<=med)&(d.gap>gmed)].net)],
                 [pf(d[(d.absdist>med)&(d.gap<=gmed)].net), pf(d[(d.absdist>med)&(d.gap>gmed)].net)]])
im=ax[0].imshow(grid, cmap="RdYlGn", vmin=0.8, vmax=2.4)
ax[0].set_xticks([0,1]); ax[0].set_xticklabels(["lo-gap","hi-gap"]); ax[0].set_yticks([0,1]); ax[0].set_yticklabels(["near-HVL","far-HVL"])
for i in range(2):
    for j in range(2): ax[0].text(j,i,f"PF {grid[i,j]}",ha="center",va="center",fontweight="bold")
ax[0].set_title("2x2 PF: near-HVL wins in BOTH gap columns\n(HVL orthogonal to gap, corr -0.09)",fontsize=10,fontweight="bold")
bands=list(d["gt"].cat.categories); x=np.arange(len(bands))
nr=[d[(d["gt"]==g)&(d.absdist<=med)].net.mean() for g in bands]; fr=[d[(d["gt"]==g)&(d.absdist>med)].net.mean() for g in bands]
ax[1].bar(x-0.2,nr,0.4,label="near-HVL",color="#2e8b57"); ax[1].bar(x+0.2,fr,0.4,label="far-HVL",color="#b23a2e")
ax[1].axhline(0,color="#999"); ax[1].set_xticks(x); ax[1].set_xticklabels(bands); ax[1].set_ylabel("$/trade"); ax[1].legend(frameon=False)
ax[1].set_title("near vs far $/tr inside gap terciles\n(HVL survives gap control in low+mid)",fontsize=10,fontweight="bold")
for a in ax:
    for s_ in ("top","right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT/"docs"/"living"/"hvl_orthogonality_20260725.png",facecolor="white")
print("saved docs/living/hvl_orthogonality_20260725.png")
