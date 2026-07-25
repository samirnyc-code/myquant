"""HVL-distance SIZING schemes + VIX-conditional gate, in MES contract terms.
Reads gamma_hvl_20260725.csv (three-book trades + causal prior-day |HVL dist|).
All results normalised to "full size = 1 MES" (ES net / 10 per full-weight trade),
so schemes are compared apples-to-apples; a sizing line scales to the $4,500 prop DD.

Schemes:
  A Base            near full / far full
  B Hard gate       near full / far 0
  C 2:1             near full / far 1/2
  D 3:1             near full / far 1/3
  E 4-tier quartile Q1 1.0 / Q2 0.7 / Q3 0.4 / Q4 0.2  (by |HVL dist| quartile)
  F VIX-conditional far size depends on prior-day VIX: low->1/2, high->full (keep trend tail)

VIX + HVL are prior-session/EOD known -> causal.  python scripts/regime_2e_hvl_sized.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
MES = 10.0                       # 1 ES-dollar of net = 1/10 MES-dollar

d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
d["yr"] = d.Date.str[:4]
d["mes"] = d.net / MES           # net for ONE MES at full weight
med = d.absdist.median()
d["q"] = pd.qcut(d.absdist, 4, labels=[0, 1, 2, 3]).astype(int)   # 0=nearest

# causal prior-day VIX (EOD known before the session)
vx = pd.read_csv(MAIN / "data" / "vix_daily.csv")
vx["d"] = pd.to_datetime(vx.date).dt.date.astype(str)
vx = vx.sort_values("d"); vx["vix_prev"] = vx["close"].shift(1)
d["vix"] = d.Date.map(vx.set_index("d")["vix_prev"])
d = d.dropna(subset=["vix"]).reset_index(drop=True)
vmed = d.vix.median()
far = d.absdist > med
lowvix = d.vix <= vmed


def pf(s):
    s = np.asarray(s); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0
def mdd(s):
    e = np.cumsum(np.asarray(s)); return float((e - np.maximum.accumulate(e)).min())


# weight vector per scheme (multiplies d.mes)
W = {
    "A Base":        np.ones(len(d)),
    "B Hard gate":   np.where(far, 0.0, 1.0),
    "C 2:1":         np.where(far, 0.5, 1.0),
    "D 3:1":         np.where(far, 1/3, 1.0),
    "E 4-tier":      np.array([1.0, 0.7, 0.4, 0.2])[d.q.values],
    "F VIX-cond":    np.where(far, np.where(lowvix, 0.5, 1.0), 1.0),   # far: cut only in low VIX
}

print(f"trades {len(d)}  |HVL| median {med:.2f}%  VIX median {vmed:.1f}  (all in 'full=1 MES' units)\n")
print(f"{'scheme':13}{'netMES':>9}{'$/tr':>7}{'PF':>6}{'maxDD':>9}{'2022':>9}{'contracts@$4.5kDD':>18}")
rows = {}
for nm, w in W.items():
    s = d.mes.values * w
    m = mdd(s)
    y22 = s[d.yr.values == "2022"].sum()
    # honest DD scaling: block-boot worst-1% ~ 3.7x realized (from #6); size so that fits 4500
    honest_dd = abs(m) * 3.7
    ncontr = int(4500 / honest_dd) if honest_dd > 0 else 0
    rows[nm] = s
    print(f"{nm:13}{s.sum():>9,.0f}{s[w>0].mean() if (w>0).any() else 0:>7.1f}{pf(s):>6.2f}"
          f"{m:>9,.0f}{y22:>9,.0f}{ncontr:>15} MES")

print("\n--- VIX x HVL interaction (does high VIX rescue far-HVL?) [full=1 MES units] ---")
for fl, flab in [(~far, "near-HVL"), (far, "far-HVL")]:
    for vl, vlab in [(lowvix, "lowVIX"), (~lowvix, "highVIX")]:
        x = d[fl & vl]
        print(f"  {flab:9} {vlab:8} n={len(x):4d}  netMES {x.mes.sum():+8,.0f}  $/tr {x.mes.mean():+6.1f}  PF {pf(x.mes)}")

print("\n--- per-year netMES (full=1 MES) ---")
print(f"{'yr':6}" + "".join(f"{k.split()[0]:>9}" for k in W))
for y in sorted(d.yr.unique()):
    mask = d.yr.values == y
    print(f"{y:6}" + "".join(f"{rows[k][mask].sum():>9,.0f}" for k in W))

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(14, 5.2), dpi=120)
cols = {"A Base": "#33454d", "B Hard gate": "#b23a2e", "C 2:1": "#2a78d6", "F VIX-cond": "#2e8b57"}
for nm, c in cols.items():
    ax[0].plot(range(len(d)), np.cumsum(rows[nm]), lw=2, color=c,
               label=f"{nm}  PF{pf(rows[nm])}  DD{mdd(rows[nm]):,.0f}")
ax[0].axhline(0, color="#999", lw=1); ax[0].legend(frameon=False, fontsize=9)
ax[0].set_title("Equity by sizing scheme (full = 1 MES)", fontweight="bold")
ax[0].set_xlabel("trade #"); ax[0].set_ylabel("cum net ($, 1 MES)")
cells = [("near\nlowVIX", ~far & lowvix), ("near\nhighVIX", ~far & ~lowvix),
         ("FAR\nlowVIX", far & lowvix), ("FAR\nhighVIX", far & ~lowvix)]
pfs = [pf(d.mes[m]) for _, m in cells]; bc = ["#2e8b57" if p >= 1.1 else "#b23a2e" for p in pfs]
ax[1].bar(range(4), pfs, color=bc)
for i, (p, (_, m)) in enumerate(zip(pfs, cells)):
    ax[1].annotate(f"PF {p}\nn={m.sum()}", (i, p), textcoords="offset points", xytext=(0, 5),
                   ha="center", fontsize=9, fontweight="bold")
ax[1].axhline(1, ls="--", color="#33454d"); ax[1].set_xticks(range(4))
ax[1].set_xticklabels([c[0] for c in cells]); ax[1].set_ylim(0, 2.8)
ax[1].set_title("VIX × HVL: FAR is churn only in LOW vix (0.98); HIGH-vix far is the trend tail (1.15)",
                fontsize=9.5, fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "hvl_sized_20260725.png", facecolor="white")
print("\nsaved docs/living/hvl_sized_20260725.png")
