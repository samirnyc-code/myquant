"""The 2:1 HVL lean in REAL MES contracts, 5 years. What is '2' and '1'?
  near-HVL trade (|dist| <= median) -> 2 MES ;  far-HVL trade -> 1 MES.
Compares flat-1 MES, flat-2 MES, and the 2:1 lean on:
  - 5yr net, per-year, per-trade contracts, avg contracts/day
  - EOD-TRAIL max drawdown (prop rule trails peak of daily CLOSED equity) vs $4,500
  - block-bootstrap (daily blocks) worst-1% EOD-trail DD
MES economics: 1 contract net = ES_net/10 - $2.5  ($3 RT + 1-tick $1.25 slip vs the
CSV's $5 RT + $12.5 slip on ES). Also illustrates strategic step-up + defensive cut.

  python scripts/regime_2e_lean_contracts.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(83)
PROP = 4500


def mes1(es_net):                      # ES-net -> 1-MES-contract net
    return es_net / 10.0 - 2.5


def eod_trail_dd(daily):               # prop trails peak of daily CLOSED equity
    e = np.cumsum(daily); return float((e - np.maximum.accumulate(e)).min())


def boot_eod1(daily, k=5, paths=5000):
    daily = np.asarray(daily, float); nb = int(np.ceil(len(daily)/k))
    blk = [daily[i:i+k] for i in range(0, len(daily), k)]
    dd = np.empty(paths)
    for j in range(paths):
        p = np.concatenate([blk[i] for i in rng.integers(0, len(blk), nb)])[:len(daily)]
        e = np.cumsum(p); dd[j] = (e - np.maximum.accumulate(e)).min()
    return np.percentile(dd, 1)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
d["yr"] = d.Date.str[:4]
med = d.absdist.median()
d["near"] = d.absdist <= med
d["m1"] = mes1(d.net)                   # per-1-MES net for this trade

SCHEMES = {
    "flat 1 MES": np.ones(len(d)),
    "flat 2 MES": np.full(len(d), 2),
    "LEAN 2:1 (near2/far1)": np.where(d.near, 2, 1),
}
print(f"trades {len(d)}  near {d.near.sum()} / far {(~d.near).sum()}  (|HVL| median {med:.2f}%)\n")
print(f"{'scheme':22}{'contracts':>10}{'5yr net':>10}{'/yr':>8}{'EOD-DD':>9}{'boot1':>9}{'fit $4.5k?':>11}")
res = {}
for nm, c in SCHEMES.items():
    tr = d.m1.values * c
    dly = pd.Series(tr, index=d.Date).groupby(level=0).sum()
    dd = eod_trail_dd(dly.values); b1 = boot_eod1(dly.values)
    res[nm] = (tr, dly)
    avgc = c.mean()
    fit = "YES" if b1 > -PROP else "no"
    print(f"{nm:22}{avgc:>9.2f}x{tr.sum():>10,.0f}{tr.sum()/5:>8,.0f}{dd:>9,.0f}{b1:>9,.0f}{fit:>11}")

print("\nper-year net ($):")
print(f"{'yr':6}" + "".join(f"{k.split()[0]+k.split()[1]:>12}" for k in SCHEMES))
for y in sorted(d.yr.unique()):
    m = (d.yr == y).values
    print(f"{y:6}" + "".join(f"{res[k][0][m].sum():>12,.0f}" for k in SCHEMES))

# contracts traded per year (how much '2' vs '1' fires)
print("\nnear(2 MES) vs far(1 MES) trades per year:")
for y in sorted(d.yr.unique()):
    yy = d[d.yr == y]
    print(f"  {y}: near {yy.near.sum():2d} (->2MES)  far {(~yy.near).sum():2d} (->1MES)  "
          f"avg {(np.where(yy.near,2,1)).mean():.2f} MES/trade")

lean_dly = res["LEAN 2:1 (near2/far1)"][1]
print(f"\nLEAN 2:1 active trading days: {len(lean_dly)}  median day PnL ${lean_dly.median():+.0f}  "
      f"best +${lean_dly.max():,.0f}  worst -${abs(lean_dly.min()):,.0f}")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
for nm, col in [("flat 1 MES", "#33454d"), ("flat 2 MES", "#c0392b"), ("LEAN 2:1 (near2/far1)", "#2e8b57")]:
    dly = res[nm][1]; e = dly.cumsum()
    ax[0].plot(pd.to_datetime(e.index), e.values, lw=2, color=col,
               label=f"{nm}: +${dly.sum()/1000:.0f}k  EODdd ${eod_trail_dd(dly.values):,.0f}")
ax[0].axhline(0, color="#999"); ax[0].legend(frameon=False, fontsize=8)
ax[0].set_title("Equity in MES $ — flat-1 vs flat-2 vs 2:1 lean", fontweight="bold")
lean = res["LEAN 2:1 (near2/far1)"][1]
e = lean.cumsum().values; dd = e - np.maximum.accumulate(e)
ax[1].fill_between(pd.to_datetime(lean.index), dd, 0, color="#2e8b57", alpha=.4)
ax[1].axhline(-PROP, ls="--", color="#b23a2e", label=f"$4,500 prop trail")
ax[1].axhline(boot_eod1(lean.values), ls=":", color="#d98a2b", label=f"boot worst-1% ${boot_eod1(lean.values):,.0f}")
ax[1].legend(frameon=False, fontsize=8); ax[1].set_title("2:1 lean EOD-trail drawdown vs prop limit", fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "lean_contracts_20260725.png", facecolor="white")
print("\nsaved docs/living/lean_contracts_20260725.png")
