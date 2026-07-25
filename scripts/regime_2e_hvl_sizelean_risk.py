"""HVL size-lean — DD/tail check (the last gate before it could go live).
Does leaning size UP near-HVL / DOWN far-HVL move the block-bootstrap DD envelope
(-27.6k/-35.4k) or worsen the top-20 tail concentration vs equal-weight base?
Weighted three-book nets; block-bootstrap (5-trade blocks, 5000 paths) + tail top-N.

Schemes (weight x per-trade net):
  BASE          all 1.0
  LEAN 2:1      near 1.0 / far 0.5
  LEAN+skip     near 1.0 / far 0.5, but far & low-gap = 0 (the lone dead bucket, PF 0.95)
All normalised to "mean weight = 1" so DD/net are compared per unit of capital deployed.

  python scripts/regime_2e_hvl_sizelean_risk.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(v):
    e = np.cumsum(np.asarray(v, float)); return float((e - np.maximum.accumulate(e)).min())
def boot(v, k=5, paths=5000):
    v = np.asarray(v, float); nb = int(np.ceil(len(v)/k)); blocks = [v[i:i+k] for i in range(0, len(v), k)]
    dd = np.empty(paths)
    for j in range(paths):
        idx = rng.integers(0, len(blocks), nb)
        p = np.concatenate([blocks[i] for i in idx])[:len(v)]
        e = np.cumsum(p); dd[j] = (e - np.maximum.accumulate(e)).min()
    return np.percentile(dd, 5), np.percentile(dd, 1)
def tail(v, k):
    s = np.sort(np.asarray(v, float))[::-1]; return round(100*s[:k].sum()/s.sum())


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
b = pd.read_parquet(MAIN / "data" / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
dd_ = b.groupby("Date").agg(o=("Open", "first"), c=("Close", "last")).reset_index()
dd_["gap"] = (dd_.o - dd_.c.shift(1)).abs() / dd_.c.shift(1) * 100
d = d.merge(dd_[["Date", "gap"]], on="Date", how="left").dropna(subset=["gap", "absdist"])
med = d.absdist.median(); gmed = d.gap.median(); far = d.absdist > med

W = {
    "BASE (equal)":  np.ones(len(d)),
    "LEAN 2:1":      np.where(far, 0.5, 1.0),
    "LEAN+skip dead": np.where(far & (d.gap <= gmed), 0.0, np.where(far, 0.5, 1.0)),
}
print(f"trades {len(d)}   HVL median {med:.2f}%   (all normalised to mean-weight 1)\n")
print(f"{'scheme':16}{'net':>10}{'$/tr':>7}{'PF':>6}{'maxDD':>9}{'boot-5%':>10}{'boot-1%':>10}{'top20%':>8}{'DD/net':>8}")
for nm, w in W.items():
    w = w / w.mean()                        # normalise mean weight to 1 (same capital)
    s = d.net.values * w
    b5, b1 = boot(s)
    print(f"{nm:16}{s.sum():>10,.0f}{s[w>0].mean():>7.0f}{pf(s):>6.2f}{mdd(s):>9,.0f}"
          f"{b5:>10,.0f}{b1:>10,.0f}{tail(s,20):>7}%{abs(b1)/s.sum():>8.2f}")
print("\nreference: BASE block-bootstrap from stress #6 = worst-5% -27,565 / worst-1% -35,445")
print("PASS if lean does NOT deepen boot-1% and does NOT raise top20% materially.")
