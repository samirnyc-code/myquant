"""Strategy (flat-1 ES / 2:1 lean / flat-2 ES) vs BUY-AND-HOLD SPX over the SAME period,
on the SAME capital (= each scheme's required account @33% of honest boot-1% DD).
Reports: total return, CAGR, max drawdown ($ and %), $ profit on that capital, and the
strategy<->SPX daily-return correlation (diversification value).

Caveat surfaced, not hidden: strategy capital is RISK/margin collateral (flat ~55% of days,
market-neutral), B&H is fully invested with beta. So also shown: you can run BOTH on the same
collateral (futures use margin) — they're near-uncorrelated.

  python scripts/regime_2e_vs_spx.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
rng = np.random.default_rng(83)


def boot1(v, k=5, paths=5000):
    v = np.asarray(v, float); nb = int(np.ceil(len(v)/k)); blk = [v[i:i+k] for i in range(0, len(v), k)]
    dd = np.empty(paths)
    for j in range(paths):
        p = np.concatenate([blk[i] for i in rng.integers(0, len(blk), nb)])[:len(v)]
        e = np.cumsum(p); dd[j] = (e - np.maximum.accumulate(e)).min()
    return np.percentile(dd, 1)
def mdd(v):
    e = np.cumsum(np.asarray(v, float)); return float((e - np.maximum.accumulate(e)).min())


d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv").sort_values("Date").reset_index(drop=True)
med = d.absdist.median(); d["near"] = d.absdist <= med
d0, d1 = d.Date.min(), d.Date.max()
yrs = (pd.to_datetime(d1) - pd.to_datetime(d0)).days / 365.25

# SPX daily close over the exact period
spx = pd.read_csv(MAIN / "data" / "options_sim" / "spx_daily_yahoo.csv")
spx["dt"] = pd.to_datetime(spx.Date).dt.date.astype(str)
spx = spx[(spx.dt >= d0) & (spx.dt <= d1)].sort_values("dt").reset_index(drop=True)
p0, p1 = spx.Close.iloc[0], spx.Close.iloc[-1]
spx_tot = p1/p0 - 1; spx_cagr = (p1/p0)**(1/yrs) - 1
sp_eq = spx.Close.values / p0                     # normalized equity path
sp_ddpct = float((sp_eq/np.maximum.accumulate(sp_eq) - 1).min())
print(f"period {d0} -> {d1}  ({yrs:.2f} yrs)")
print(f"SPX buy&hold: {p0:.0f} -> {p1:.0f}  total {spx_tot*100:+.0f}%  CAGR {spx_cagr*100:+.1f}%  maxDD {sp_ddpct*100:.0f}%\n")

SCH = {"flat 1 ES": np.ones(len(d)), "LEAN 2:1": np.where(d.near, 2, 1), "flat 2 ES": np.full(len(d), 2)}
print(f"{'scheme':11}{'acct@33%':>10}{'5yr net':>10}{'totRet%':>9}{'CAGR*':>8}{'maxDD$':>9}{'maxDD%':>8}"
      f"{'  vs SPX same-$':>16}")
for nm, c in SCH.items():
    tr = d.net.values * c; acct = abs(boot1(tr))/0.33
    tot = tr.sum()/acct; cagr = (1+tot)**(1/yrs)-1           # *fixed-contract, not compounded
    dd = mdd(tr); ddpct = dd/acct
    spx_gain = acct * spx_tot                                 # if that capital were in SPX instead
    edge = tr.sum() - spx_gain
    print(f"{nm:11}{acct:>10,.0f}{tr.sum():>10,.0f}{tot*100:>8.0f}%{cagr*100:>7.1f}%{dd:>9,.0f}{ddpct*100:>7.0f}%"
          f"   {edge:>+12,.0f}")

# diversification: strategy daily PnL vs SPX daily return
dly = pd.Series(d.net.values, index=d.Date).groupby(level=0).sum()
spx["ret"] = spx.Close.pct_change()
j = pd.DataFrame({"strat": dly}).join(spx.set_index("dt")["ret"]).dropna()
corr = j.strat.corr(j.ret)
print(f"\nstrategy daily PnL vs SPX daily return: corr {corr:+.2f}  (near 0 = uncorrelated diversifier)")
print("* CAGR here = fixed-contract simple return annualized (strategy does NOT compound; SPX does).")
print("Strategy capital is idle collateral ~55% of days & market-neutral -> can be run ALONGSIDE a")
print("SPX holding on the same portfolio margin, not instead of it.")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(13, 5), dpi=120)
acct1 = abs(boot1(d.net.values))/0.33
for nm, c, col in [("flat 1 ES", np.ones(len(d)), "#33454d"), ("LEAN 2:1", np.where(d.near, 2, 1), "#2e8b57")]:
    tr = d.net.values * c; acct = abs(boot1(tr))/0.33
    ax[0].plot(pd.to_datetime(d.Date), acct + np.cumsum(tr), lw=2, color=col, label=f"{nm} on ${acct/1000:.0f}k")
ax[0].plot(pd.to_datetime(spx.dt), acct1 * spx.Close.values/p0, lw=2, color="#c0392b", label=f"SPX B&H on ${acct1/1000:.0f}k")
ax[0].legend(frameon=False, fontsize=8); ax[0].set_title("Account value: strategy vs SPX buy&hold (same $)", fontweight="bold")
ax[1].scatter(j.ret*100, j.strat, s=8, alpha=.4, color="#2a78d6")
ax[1].axhline(0, color="#999"); ax[1].axvline(0, color="#999")
ax[1].set_xlabel("SPX daily return %"); ax[1].set_ylabel("strategy daily PnL ($, 1 ES)")
ax[1].set_title(f"Uncorrelated to SPX (corr {corr:+.2f})", fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "vs_spx_20260725.png", facecolor="white")
print("\nsaved docs/living/vs_spx_20260725.png")
