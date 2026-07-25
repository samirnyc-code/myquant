"""Re-examine the 'skip dead bucket' (far-HVL & low-gap) rejection — was it fair?
Two questions I owe an honest answer to:
  A) Is far+low-gap RELIABLY dead (train AND test), or is PF 0.95 just noise near 1.0?
     A hard skip on a noisy-breakeven bucket = fitting noise. Must be stable to justify.
  B) The DD comparison: same-capital normalization (redeploy freed capital -> bigger per-trade
     size -> mechanically deeper $ DD) vs FIXED-per-trade-size (just drop the trades). The
     'breach' of -35.4k came from (a); on risk-per-$ (DD/net) skip-dead was actually BEST.

  python scripts/regime_2e_skipdead_check.py
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
def boot1(v, k=5, paths=5000):
    v = np.asarray(v, float); nb = int(np.ceil(len(v)/k)); blk = [v[i:i+k] for i in range(0, len(v), k)]
    dd = np.empty(paths)
    for j in range(paths):
        p = np.concatenate([blk[i] for i in rng.integers(0, len(blk), nb)])[:len(v)]
        e = np.cumsum(p); dd[j] = (e - np.maximum.accumulate(e)).min()
    return np.percentile(dd, 1)


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
b = pd.read_parquet(MAIN / "data" / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
g = b.groupby("Date").agg(o=("Open", "first"), c=("Close", "last")).reset_index()
g["gap"] = (g.o - g.c.shift(1)).abs() / g.c.shift(1) * 100
d = d.merge(g[["Date", "gap"]], on="Date", how="left").dropna(subset=["gap", "absdist"])
d["tr"] = d.Date <= "2023-12-31"
med = d.absdist.median(); gmed = d.gap.median()
far = d.absdist > med; logap = d.gap <= gmed
dead = far & logap

print("=== A) Is far+low-gap STABLY dead? ===")
x = d[dead]
print(f"  dead bucket (far-HVL & gap<=median): n={len(x)}  net {x.net.sum():+,.0f}  PF {pf(x.net)}  $/tr {x.net.mean():+.0f}")
print(f"     train(<=2023): n={x.tr.sum():3d}  net {x[x.tr].net.sum():+8,.0f}  PF {pf(x[x.tr].net)}")
print(f"     test (2024+ ): n={(~x.tr).sum():3d}  net {x[~x.tr].net.sum():+8,.0f}  PF {pf(x[~x.tr].net)}")
print(f"     per-year:")
for y in sorted(d.Date.str[:4].unique()):
    xy = x[x.Date.str[:4] == y]
    if len(xy): print(f"        {y}: n={len(xy):2d}  net {xy.net.sum():+7,.0f}  PF {pf(xy.net)}")

print("\n=== B) DD under two framings ===")
# framing 1: SAME CAPITAL (mean-weight normalised) — what was reported
def report(nm, w):
    w = np.asarray(w, float)
    s_fixed = d.net.values * w                       # fixed per-trade size (weights as-is)
    wn = w / w[w > 0].mean() if (w > 0).any() else w  # normalise over TRADED legs
    # same-capital: normalise mean weight across ALL slots to 1
    wsc = w / w.mean()
    s_sc = d.net.values * wsc
    print(f"  {nm:18} | fixed-size: net {s_fixed.sum():+8,.0f}  maxDD {mdd(s_fixed):+8,.0f}  boot1 {boot1(s_fixed):+8,.0f}"
          f"   || same-capital: net {s_sc.sum():+8,.0f}  maxDD {mdd(s_sc):+8,.0f}  boot1 {boot1(s_sc):+8,.0f}  DD/net {abs(boot1(s_sc))/s_sc.sum():.2f}")

report("BASE", np.ones(len(d)))
report("LEAN 2:1", np.where(far, 0.5, 1.0))
report("LEAN+skip dead", np.where(dead, 0.0, np.where(far, 0.5, 1.0)))
print("\n  fixed-size = drop/downsize trades, keep survivors at same contracts (absolute risk FALLS).")
print("  same-capital = redeploy freed capital into survivors (bigger per-trade size -> $ DD rises,")
print("  but risk-per-$ DD/net can still improve). The -35.4k 'breach' was purely the same-capital framing.")
