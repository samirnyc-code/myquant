"""STRESS BATTERY #2/#6/#7/#8 — reads wf_dataset_20260725.csv (three-book, all days,
per-trade gross + net at stop-mults). Fast, no tick pass.

#2 COST STRESS   : double commission ($10 RT) + 2-tick slip on BOTH sides.
#6 DROUGHT/BOOTSTRAP: block-bootstrap (5-trade blocks) -> DD + worst flat-stretch distribution.
#7 PARAM NEIGHBORHOOD: cross stop-mult {0.20,0.30,0.40} x gap-threshold {0.45,0.54,0.60};
                    is 0.30/0.54 a plateau or a peak?
#8 JACKKNIFE     : leave-one-year-out; tail removal (top-N winners) on the three-book.

  python scripts/regime_2e_stress_battery.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
DS = WT / "data" / "regime" / "wf_dataset_20260725.csv"
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0


def maxdd(v):
    e = np.cumsum(v); return float((e - np.maximum.accumulate(e)).min())


d = pd.read_csv(DS); d["dt"] = pd.to_datetime(d.Date); d["yr"] = d.Date.str[:4]
# committed config: gap<=0.54, stop-mult 0.30
base = d[d.gap <= 0.54].sort_values("Date").reset_index(drop=True)
net = base["net_30"].values; gross = base["gross_30"].values
print(f"BASE three-book (gap<=0.54, 0.30xADR stop): n={len(base)}  net {net.sum():+,.0f}  PF {pf(net)}  maxDD {maxdd(net):+,.0f}")

# ===== #2 COST STRESS =====
print("\n===== #2 COST STRESS =====")
for lab, comm, slipt in [("base $5RT+1t", 5, 1), ("$10RT+2t both sides", 10, 4)]:
    ns = gross - comm - slipt * 12.5
    print(f"  {lab:22s}: net {ns.sum():+,.0f}  $/tr {ns.mean():+.1f}  PF {pf(ns)}  maxDD {maxdd(ns):+,.0f}")

# ===== #6 DROUGHT / BLOCK BOOTSTRAP =====
print("\n===== #6 DROUGHT / BLOCK BOOTSTRAP (5-trade blocks, 5000 paths) =====")
BL = 5; nblk = int(np.ceil(len(net) / BL))
blocks = [net[i:i+BL] for i in range(0, len(net), BL)]
dds = np.empty(5000); flats = np.empty(5000)
for k in range(5000):
    idx = rng.integers(0, len(blocks), nblk)
    path = np.concatenate([blocks[j] for j in idx])[:len(net)]
    e = np.cumsum(path); dd = e - np.maximum.accumulate(e)
    dds[k] = dd.min()
    uw = 0; mx = 0
    for v in dd:
        uw = uw + 1 if v < -1e-9 else 0; mx = max(mx, uw)
    flats[k] = mx
print(f"  bootstrap maxDD: median {np.percentile(dds,50):,.0f}  worst-5% {np.percentile(dds,5):,.0f}  "
      f"worst-1% {np.percentile(dds,1):,.0f}")
print(f"  longest flat stretch (trades underwater): median {int(np.percentile(flats,50))}  "
      f"worst-5% {int(np.percentile(flats,95))}  worst-1% {int(np.percentile(flats,99))} "
      f"(~{int(np.percentile(flats,99)/(len(net)/60.5))} months at {len(net)/60.5:.0f} tr/mo)")

# ===== #7 PARAM NEIGHBORHOOD =====
print("\n===== #7 PARAMETER NEIGHBORHOOD (stop-mult x gap-threshold) =====")
print("            gap<=0.45    gap<=0.54    gap<=0.60")
for mlt in (20, 30, 40):
    row = f"  {mlt/100:.2f}xADR  "
    for thr in (0.45, 0.54, 0.60):
        x = d[d.gap <= thr][f"net_{mlt}"]
        row += f"  PF{pf(x):.2f}/{x.sum()/1000:+.0f}k"
    print(row)
print("  (0.30/0.54 = the adopted cell; broad plateau ⇒ robust)")

# ===== #8 JACKKNIFE =====
print("\n===== #8 JACKKNIFE =====")
print("  leave-one-year-out (drop each year, is the REST still positive?):")
for y in sorted(base.yr.unique()):
    rest = base[base.yr != y]["net_30"]
    print(f"    drop {y}: remaining n={len(rest)}  net {rest.sum():+,.0f}  PF {pf(rest)}")
print("  tail removal (drop top-N winners of the three-book):")
srt = np.sort(net)[::-1]
for kk in (2, 5, 10, 20):
    rem = net.sum() - srt[:kk].sum()
    kept = np.sort(net)[:len(net)-kk] if kk else net
    print(f"    drop top-{kk}: net {rem:+,.0f}  PF {pf(kept)}  (top-{kk} = {100*srt[:kk].sum()/net.sum():.0f}% of net)")


if __name__ == "__main__":
    pass
