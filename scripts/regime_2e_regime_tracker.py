"""REGIME TRACKER + detection-lag measurement (Samir, 2026-07-25).
Question: how soon do we know a 2022-style macro-vol regime is back, how do we
track it, what do we do?

Three trackers, fastest->slowest / leading->definitive:
  1 MARKET (leading, fast): 50d-median VIX vs a band; contiguous "elevated" runs.
    Measure the LAG between the vol turn and a sustained-flag firing.
  2 GAMMA (context): sign of net_total_gex (19yr file), 20d-smoothed -> % negative/yr.
  3 SYSTEM (definitive, slow): chronological equity of the three-book; rolling
    40-trade PF; running drawdown vs the #6 block-bootstrap envelope
    (worst-5% -27.5k, worst-1% -35.4k). The circuit-breaker levels.

Also: how long is a NORMAL drought, so we know the floor on system-based detection.
  python scripts/regime_2e_regime_tracker.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
BOOT5, BOOT1 = -27565, -35445          # from stress #6 (block-bootstrap)
DROUGHT_MED, DROUGHT_99 = 143, 493      # normal flat-stretch (trades)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


# --- 1 MARKET: 50d median VIX regime ---
vx = pd.read_csv(MAIN / "data" / "vix_daily.csv"); vx["dt"] = pd.to_datetime(vx.date)
vx = vx.sort_values("dt").reset_index(drop=True)
vx["med50"] = vx.close.rolling(50).median()
vx = vx[vx.dt >= "2020-06-01"].reset_index(drop=True)
THR = 21.9                              # train high-tercile edge
vx["elev"] = vx.med50 > THR
# contiguous elevated runs >= 15 trading days
runs = []
i = 0
e = vx.elev.values
while i < len(vx):
    if e[i]:
        j = i
        while j < len(vx) and e[j]:
            j += 1
        if j - i >= 15:
            runs.append((vx.dt[i].date(), vx.dt[j-1].date(), j - i))
        i = j
    else:
        i += 1
print(f"=== 1 MARKET TRACKER: 50d-median VIX > {THR} sustained >=15d ===")
for a, b, n in runs:
    print(f"  elevated {a} -> {b}  ({n} trading days)")

# detection lag for the 2022 regime: when did raw VIX first sustain >THR vs when did med50 flag?
raw22 = vx[(vx.dt >= "2021-11-01") & (vx.dt <= "2022-06-01")]
first_raw = raw22[raw22.close > THR].dt.min()
first_flag = vx[(vx.elev) & (vx.dt >= "2021-11-01")].dt.min()
if pd.notna(first_raw) and pd.notna(first_flag):
    lag = (first_flag - first_raw).days
    print(f"  2022 regime: raw VIX first crossed {THR} on {first_raw.date()}; "
          f"50d-median flag fired {first_flag.date()}  -> LAG {lag} calendar days (~{lag//7} wks)")

# --- 2 GAMMA context ---
gm = pd.read_csv(MAIN / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv")
gm["dt"] = pd.to_datetime(gm.date); gm = gm.sort_values("dt")
gm["neg"] = (gm.net_total_gex < 0).astype(int)
gm["neg20"] = gm.neg.rolling(20).mean()
gm["yr"] = gm.dt.dt.year
print("\n=== 2 GAMMA CONTEXT: % of days net-GEX negative, by year ===")
for y in range(2021, 2027):
    x = gm[gm.yr == y]
    if len(x):
        print(f"  {y}: {x.neg.mean()*100:4.0f}% negative-gamma days   median net_gex {x.net_total_gex.median()/1e9:+.2f}e9")

# --- 3 SYSTEM: rolling PF + drawdown vs envelope ---
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
d = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy().sort_values("Date").reset_index(drop=True)
d["eq"] = d.net.cumsum(); d["peak"] = d["eq"].cummax(); d["dd"] = d["eq"] - d["peak"]
d["rpf"] = [pf(d.net.iloc[max(0, i-39):i+1]) for i in range(len(d))]
worst_dd = d.dd.min(); worst_dd_date = d.loc[d.dd.idxmin(), "Date"]
# longest realised flat stretch (trades underwater)
uw = (d.dd < -1e-9).values; cur = mx = 0
for v in uw:
    cur = cur + 1 if v else 0; mx = max(mx, cur)
print("\n=== 3 SYSTEM TRACKER (definitive but slow) ===")
print(f"  realised worst DD: {worst_dd:+,.0f} at {worst_dd_date}   longest realised flat stretch: {mx} trades")
print(f"  block-bootstrap envelope: worst-5% {BOOT5:+,} | worst-1% {BOOT1:+,}")
print(f"  normal drought length: median {DROUGHT_MED} trades, worst-1% {DROUGHT_99} trades "
      f"(~{DROUGHT_99//11} months at 11 tr/mo)")
n_below1 = (d.rpf < 1.0).sum()
print(f"  rolling-40 PF below 1.0 on {n_below1}/{len(d)} trades ({n_below1/len(d)*100:.0f}% of the time) "
      f"-> a dip under 1 is NORMAL, not a regime signal")

print("\n=== CIRCUIT-BREAKER PROTOCOL (objective, size in MES-of-choice) ===")
print(f"  WATCH  : 50d-median VIX > {THR} for >=15d  OR  20d neg-gamma share > 60%  -> pre-emptive half size")
print(f"  DE-RISK: live DD breaches bootstrap worst-5% ({BOOT5:+,} per 1-ES unit) -> cut to half size")
print(f"  HALT   : live DD breaches worst-1% ({BOOT1:+,})  OR  rolling-{DROUGHT_99}-trade net still negative -> pause + re-audit")

import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(3, 1, figsize=(13, 10), dpi=115, sharex=False)
ax[0].plot(vx.dt, vx.close, color="#c3c2b7", lw=.6, label="VIX")
ax[0].plot(vx.dt, vx.med50, color="#b23a2e", lw=2, label="50d median VIX")
ax[0].axhline(THR, ls="--", color="#33454d", label=f"regime thr {THR}")
for a, b, n in runs:
    ax[0].axvspan(pd.Timestamp(a), pd.Timestamp(b), color="#b23a2e", alpha=.12)
ax[0].legend(frameon=False, fontsize=8, ncol=4); ax[0].set_title("1 · Market: sustained elevated-vol regimes (shaded)", fontweight="bold")
ax[1].plot(gm.dt, gm.neg20 * 100, color="#2a78d6", lw=1.5)
ax[1].axhline(60, ls="--", color="#b23a2e"); ax[1].set_ylabel("% neg-gamma (20d)")
ax[1].set_xlim(pd.Timestamp("2020-06-01"), gm.dt.max()); ax[1].set_title("2 · Gamma context: 20d negative-gamma share", fontweight="bold")
dts = pd.to_datetime(d.Date)
ax[2].plot(dts, d.dd, color="#33454d", lw=1.2, label="running drawdown ($, 1-ES)")
ax[2].axhline(BOOT5, ls="--", color="#d98a2b", label=f"boot worst-5% {BOOT5:,}")
ax[2].axhline(BOOT1, ls="--", color="#b23a2e", label=f"boot worst-1% {BOOT1:,}")
ax[2].legend(frameon=False, fontsize=8); ax[2].set_title("3 · System: running DD vs bootstrap breaker levels (never breached in-sample)", fontweight="bold")
for a in ax:
    for s_ in ("top", "right"): a.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig(WT / "docs" / "living" / "regime_tracker_20260725.png", facecolor="white")
print("\nsaved docs/living/regime_tracker_20260725.png")
