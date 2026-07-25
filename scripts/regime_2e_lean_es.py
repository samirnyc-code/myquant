"""The 2:1 HVL lean in ES (full-size) contracts, 5 years.
  near-HVL trade -> 2 ES ;  far-HVL trade -> 1 ES.  (CSV net is already per-1-ES.)
ES frame = account sizing (honest block-bootstrap worst-1% DD / tolerance), not a prop trail.
Compares flat-1 ES, flat-2 ES, 2:1 lean on: 5yr net, /yr, realized DD, block-boot worst-1%,
required account @33% & @25% tolerance, and return-on-required-capital.

  python scripts/regime_2e_lean_es.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(v):
    e = np.cumsum(np.asarray(v, float)); return float((e - np.maximum.accumulate(e)).min())
def boot1(v, k=5, paths=5000):
    v = np.asarray(v, float); nb = int(np.ceil(len(v)/k)); blk = [v[i:i+k] for i in range(0, len(v), k)]
    dd = np.empty(paths)
    for j in range(paths):
        p = np.concatenate([blk[i] for i in rng.integers(0, len(blk), nb)])[:len(v)]
        e = np.cumsum(p); dd[j] = (e - np.maximum.accumulate(e)).min()
    return np.percentile(dd, 1)


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
d["yr"] = d.Date.str[:4]
med = d.absdist.median(); d["near"] = d.absdist <= med

SCH = {"flat 1 ES": np.ones(len(d)), "flat 2 ES": np.full(len(d), 2),
       "LEAN 2:1 (near2/far1)": np.where(d.near, 2, 1)}
print(f"trades {len(d)}  near {d.near.sum()}/far {(~d.near).sum()}  (ES = $50/pt)\n")
print(f"{'scheme':22}{'5yr net':>10}{'/yr':>9}{'realDD':>9}{'boot1':>9}{'acct@33%':>10}{'acct@25%':>10}{'ROC/yr':>8}")
res = {}
for nm, c in SCH.items():
    tr = d.net.values * c; res[nm] = tr
    b1 = boot1(tr); acct33 = abs(b1)/0.33; acct25 = abs(b1)/0.25
    roc = (tr.sum()/5)/acct33*100
    print(f"{nm:22}{tr.sum():>10,.0f}{tr.sum()/5:>9,.0f}{mdd(tr):>9,.0f}{b1:>9,.0f}"
          f"{acct33:>10,.0f}{acct25:>10,.0f}{roc:>7.0f}%")

print("\nper-year net ($):")
print(f"{'yr':6}" + "".join(f"{k.split()[0]+k.split()[1]:>13}" for k in SCH))
for y in sorted(d.yr.unique()):
    m = (d.yr == y).values
    print(f"{y:6}" + "".join(f"{res[k][m].sum():>13,.0f}" for k in SCH))

print("\nnote: ROC/yr = (net/yr) / (required account @33% tolerance). flat-1 ES reconciles to the")
print("config's ~18% CAGR & ~$105k account on the honest -$35k DD.")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
for nm, col in [("flat 1 ES", "#33454d"), ("flat 2 ES", "#c0392b"), ("LEAN 2:1 (near2/far1)", "#2e8b57")]:
    e = np.cumsum(res[nm])
    ax[0].plot(pd.to_datetime(d.Date), e, lw=2, color=col,
               label=f"{nm}: +${res[nm].sum()/1000:.0f}k  boot1 ${boot1(res[nm]):,.0f}")
ax[0].axhline(0, color="#999"); ax[0].legend(frameon=False, fontsize=8)
ax[0].set_title("Equity in ES $ — flat-1 vs flat-2 vs 2:1 lean", fontweight="bold")
labels = list(SCH); accts = [abs(boot1(res[k]))/0.33 for k in labels]; rocs = [(res[k].sum()/5)/(abs(boot1(res[k]))/0.33)*100 for k in labels]
axx = ax[1]; x = np.arange(len(labels))
b = axx.bar(x, accts, color=["#33454d", "#c0392b", "#2e8b57"])
for i, (a_, r) in enumerate(zip(accts, rocs)):
    axx.annotate(f"${a_/1000:.0f}k\nROC {r:.0f}%", (i, a_), textcoords="offset points", xytext=(0, 4), ha="center", fontweight="bold", fontsize=9)
axx.set_xticks(x); axx.set_xticklabels([l.split('(')[0] for l in labels], fontsize=8)
axx.set_ylabel("required account @33% ($)"); axx.set_title("Capital required (honest -DD/0.33) & return-on-capital", fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "lean_es_20260725.png", facecolor="white")
print("\nsaved docs/living/lean_es_20260725.png")
