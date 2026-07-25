"""0DTE EXPANSION-DAY signal — is it real, and is it NEW vs VIX / gap?
Only the offset-invariant level-SPREAD features survive the panama-basis drift:
  rw0 = cr0 - ps0            (0DTE range width)
  d1w = d1_max - d1_min      (0DTE expected-move envelope)
Both known at the open (causal). Question: do they classify expansion vs pin days
better than / independently of VIX and the gap filter?

  python scripts/regime_2e_0dte_expansion.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


d = pd.read_csv(WT / "data" / "regime" / "tradeday_0dte_20260725.csv")
d["yr"] = d.Date.str[:4]
# causal prior-day VIX
vx = pd.read_csv(MAIN / "data" / "vix_daily.csv"); vx["dd"] = pd.to_datetime(vx.date).dt.date.astype(str)
vx = vx.sort_values("dd"); vx["vp"] = vx.close.shift(1)
d["vix"] = d.Date.map(vx.set_index("dd")["vp"])
# gap (prior close -> open, %), from our continuous
b = pd.read_parquet(MAIN / "data" / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
dd = b.groupby("Date").agg(o=("Open", "first"), c=("Close", "last")).reset_index()
dd["gap"] = (dd.o - dd.c.shift(1)).abs() / dd.c.shift(1) * 100
d = d.merge(dd[["Date", "gap"]], on="Date", how="left").dropna(subset=["vix", "gap"])

print(f"trades {len(d)}   overall net {d.net.sum():+,.0f} PF {pf(d.net)}\n")
print("--- redundancy: is the 0DTE envelope just VIX / gap? (Spearman) ---")
for a in ["d1w", "rw0"]:
    print(f"  corr({a}, VIX)={d[a].corr(d.vix,'spearman'):+.2f}   "
          f"corr({a}, gap)={d[a].corr(d.gap,'spearman'):+.2f}   corr(VIX,gap)={d.vix.corr(d.gap,'spearman'):+.2f}")

print("\n--- univariate expansion cut (top-half vs bottom-half by each signal) ---")
for a, lab in [("d1w", "0DTE d1-envelope"), ("rw0", "0DTE range width"), ("vix", "VIX"), ("gap", "gap")]:
    m = d[a] > d[a].median(); hi, lo = d[m], d[~m]
    print(f"  {lab:18s} HI n={len(hi):3d} {hi.net.sum():+7,.0f}/PF{pf(hi.net):<4}   LO n={len(lo):3d} {lo.net.sum():+7,.0f}/PF{pf(lo.net)}")

print("\n--- does d1-envelope add ON TOP of VIX? (2x2 median splits) ---")
dhi = d.d1w > d.d1w.median(); vhi = d.vix > d.vix.median()
for vl, vlab in [(vhi, "VIX-hi"), (~vhi, "VIX-lo")]:
    for dl, dlab in [(dhi, "d1-loose"), (~dhi, "d1-tight")]:
        x = d[vl & dl]
        print(f"  {vlab} {dlab:9s} n={len(x):3d}  net {x.net.sum():+7,.0f}  $/tr {x.net.mean():+6.1f}  PF {pf(x.net)}")

print("\n--- per-year: d1-loose (>med) vs d1-tight (net|PF) ---")
for y in sorted(d.yr.unique()):
    yd = d[d.yr == y]; lo = yd[yd.d1w > d.d1w.median()]; ti = yd[yd.d1w <= d.d1w.median()]
    print(f"  {y}  loose n={len(lo):3d} {lo.net.sum():+7,.0f}/{pf(lo.net):<5}  tight n={len(ti):3d} {ti.net.sum():+7,.0f}/{pf(ti.net)}")

# skip-tight rule impact
keep = d[d.d1w > d.d1w.quantile(0.25)]  # drop only the tightest quartile
print(f"\nrule 'skip tightest-quartile d1 days': keep {len(keep)}/{len(d)}  "
      f"net {keep.net.sum():+,.0f} (base {d.net.sum():+,.0f})  PF {pf(keep.net)} (base {pf(d.net)})  $/tr {keep.net.mean():+.0f} (base {d.net.mean():+.0f})")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13.5, 5), dpi=120)
sigs = [("d1w","0DTE\nd1-env"),("rw0","0DTE\nrange"),("vix","VIX"),("gap","gap")]
hi=[pf(d[d[a]>d[a].median()].net) for a,_ in sigs]; lo=[pf(d[d[a]<=d[a].median()].net) for a,_ in sigs]
x=np.arange(len(sigs))
ax[0].bar(x-0.2,hi,0.4,label="HI half",color="#b23a2e"); ax[0].bar(x+0.2,lo,0.4,label="LO half",color="#2a78d6")
ax[0].axhline(1,ls="--",color="#333"); ax[0].set_xticks(x); ax[0].set_xticklabels([l for _,l in sigs],fontsize=9)
ax[0].set_ylabel("PF"); ax[0].legend(frameon=False); ax[0].set_title("Day-type signals: HI vs LO half\n(VIX-LO 2.58 dominates; VIX-HI 0.79 loses)",fontsize=10,fontweight="bold")
cells=[("VIXlo\nd1-loose",(d.vix<=d.vix.median())&(d.d1w>d.d1w.median())),
       ("VIXlo\nd1-tight",(d.vix<=d.vix.median())&(d.d1w<=d.d1w.median())),
       ("VIXhi\nd1-loose",(d.vix>d.vix.median())&(d.d1w>d.d1w.median())),
       ("VIXhi\nd1-tight",(d.vix>d.vix.median())&(d.d1w<=d.d1w.median()))]
pfs=[pf(d[m].net) for _,m in cells]; nn=[int(m.sum()) for _,m in cells]; net=[d[m].net.sum() for _,m in cells]
bc=["#2e8b57" if p>=1.1 else "#b23a2e" for p in pfs]
ax[1].bar(range(4),pfs,color=bc)
for i,(p,n,nt) in enumerate(zip(pfs,nn,net)): ax[1].annotate(f"PF {p}\nn={n}\n${nt/1000:+.0f}k",(i,p),textcoords="offset points",xytext=(0,4),ha="center",fontsize=8.5,fontweight="bold")
ax[1].axhline(1,ls="--",color="#333"); ax[1].set_xticks(range(4)); ax[1].set_xticklabels([c[0] for c in cells],fontsize=9); ax[1].set_ylim(0,7)
ax[1].set_title("VIX x 0DTE-envelope: only LOW-VIX + loose is the edge\n(39 trades = 100%+ of all profit — fragile)",fontsize=10,fontweight="bold")
for a in ax:
    for s_ in ("top","right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT/"docs"/"living"/"0dte_expansion_20260725.png",facecolor="white")
print("saved docs/living/0dte_expansion_20260725.png")
