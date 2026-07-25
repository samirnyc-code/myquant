"""What IS the effective sample size / statistical confidence of the three-book edge?
Replaces the parroted "~20 effective observations" (which was just a loose restatement
of top-20=99%-of-net) with actual numbers:
  1 tail concentration of GROSS PROFIT (how many winners for 50/80/95%)
  2 Kish effective N of the winning contributions  n_eff = (Σw)^2 / Σ(w^2)
  3 bootstrap CI on total net & PF (resample trades) -> is the edge > 0 with confidence?
  4 same but BLOCK bootstrap (5-trade blocks) to respect any clustering

  python scripts/regime_2e_effective_n.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(83)
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
d = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy()
net = d.net.values
n = len(net); tot = net.sum()
def pf(s): s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return gp/gl if gl else 0
print(f"three-book: n={n} trades, net ${tot:+,.0f}, PF {pf(net):.2f}\n")

# 1 gross-profit concentration
win = np.sort(net[net > 0])[::-1]; gp = win.sum()
print("1) GROSS-PROFIT concentration (winners only):")
for frac in (0.5, 0.8, 0.95):
    k = np.searchsorted(np.cumsum(win), frac*gp) + 1
    print(f"   {frac*100:.0f}% of gross profit = top {k} winners ({k/len(win)*100:.0f}% of the {len(win)} winners)")

# 2 Kish effective N of winning contributions
neff_win = win.sum()**2 / (win**2).sum()
neff_all = (np.abs(net).sum())**2 / (net**2).sum()
print(f"\n2) Kish effective N:")
print(f"   winners:  n_eff = {neff_win:.0f}  (of {len(win)} winning trades)")
print(f"   all |net|: n_eff = {neff_all:.0f}  (of {n} trades)")

# 3 iid bootstrap of the edge
def boot(v, blocks=False, k=5, paths=20000):
    tots = np.empty(paths); pfs = np.empty(paths)
    if blocks:
        blk = [v[i:i+k] for i in range(0, len(v), k)]; nb = int(np.ceil(len(v)/k))
        for j in range(paths):
            p = np.concatenate([blk[i] for i in rng.integers(0, len(blk), nb)])[:len(v)]
            tots[j] = p.sum(); pfs[j] = pf(p)
    else:
        for j in range(paths):
            p = v[rng.integers(0, len(v), len(v))]; tots[j] = p.sum(); pfs[j] = pf(p)
    return tots, pfs

for lab, blk in [("iid bootstrap", False), ("block bootstrap (5)", True)]:
    tots, pfs = boot(net, blocks=blk)
    print(f"\n3) {lab} (20k resamples):")
    print(f"   net:  median ${np.median(tots):+,.0f}  5th–95th [${np.percentile(tots,5):+,.0f}, ${np.percentile(tots,95):+,.0f}]  "
          f"P(net>0) = {(tots>0).mean()*100:.1f}%")
    print(f"   PF:   median {np.median(pfs):.2f}   5th pct {np.percentile(pfs,5):.2f}   P(PF>1) = {(pfs>1).mean()*100:.1f}%")

# 4 what if the top-K winners never happened?
print("\n4) robustness — remove the biggest winners entirely:")
for k in (5, 10, 20, 40):
    rem = np.sort(net)[::-1]; kept = np.concatenate([rem[k:]])
    print(f"   drop top-{k}: net ${kept.sum():+,.0f}  PF {pf(kept):.2f}  (still {'profitable' if kept.sum()>0 else 'LOSS'})")
