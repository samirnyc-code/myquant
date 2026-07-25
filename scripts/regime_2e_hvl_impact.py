"""What does the HVL-proximity gate do to the OVERALL three-book system?
Reads gamma_hvl_20260725.csv (three-book trades + prior-day HVL distance, causal).
Compares BASE (all) vs GATE (near-HVL, |dist|<=median) on: net/PF/$tr, maxDD,
per-year, tail concentration, and whether the gate just re-expresses the gap filter.

  python scripts/regime_2e_hvl_impact.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
d["yr"] = d.Date.str[:4]
med = d.absdist.median()


def pf(s):
    s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(s):
    e = np.cumsum(np.asarray(s)); return float((e - np.maximum.accumulate(e)).min())
def tail(s, k):
    s = np.sort(np.asarray(s))[::-1]; return round(100*s[:k].sum()/s.sum())


gate = d[d.absdist <= med]
print(f"{'':14s}{'n':>5}{'net':>10}{'$/tr':>7}{'PF':>6}{'maxDD':>9}{'top5%net':>9}")
for lab, x in [("BASE (all)", d), ("GATE near-HVL", gate)]:
    print(f"{lab:14s}{len(x):5d}{x.net.sum():>10,.0f}{x.net.mean():>7.0f}{pf(x.net):>6.2f}"
          f"{mdd(x.net):>9,.0f}{tail(x.net,5):>8}%")

print("\nper-year (net | PF):")
print(f"{'yr':6}{'BASE':>18}{'GATE':>18}")
for y in sorted(d.yr.unique()):
    b = d[d.yr == y].net; g = gate[gate.yr == y].net
    print(f"{y:6}{b.sum():>10,.0f}/{pf(b):<5}{'':2}{g.sum():>10,.0f}/{pf(g):<5}")

print(f"\ngate keeps {len(gate)}/{len(d)} trades ({100*len(gate)/len(d):.0f}%), "
      f"{100*gate.net.sum()/d.net.sum():.0f}% of the net")
dropped = d[d.absdist > med]
print(f"dropped (far) half: n={len(dropped)}  net {dropped.net.sum():+,.0f}  PF {pf(dropped.net)}  "
      f"$/tr {dropped.net.mean():+.0f}")

# is the gate just re-expressing the already-applied gap filter?
if "gap" in d.columns:
    print(f"\ncorr(|HVL dist|, gap) = {d.absdist.corr(d.gap):+.2f}  (near 0 => orthogonal to gap filter)")
else:
    print("\n(gap not in this CSV; |HVL dist| is measured on already-gap-filtered trades, so the gate is ADDITIVE by construction)")
