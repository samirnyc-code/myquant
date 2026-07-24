"""KILL-RULE BACKTEST — would the proposed kill criteria have stopped the book
before its good years? Run each rule over the committed spec's own history.

Rules under test (from the draft doc):
  K1: trailing 12-month PF < 1.0          (evaluated monthly)
  K2: closed-trade DD beyond -$25k
  K3: either side (L/S) PF < 1.0 for 2+ consecutive quarters
Alternates evaluated for survivability:
  A1: trailing 12-month NET < -$10k
  A2: side rule at 4 consecutive quarters
  A3: DD beyond MC worst-1% (-$25.5k)  [same as K2 effectively]

For every firing: date, and the book's net from that date to end (opportunity cost).
Output: data/regime/kill_rules_20260724.csv + tables + PNG.
  python scripts/regime_2e_kill_rules.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
mg = pd.read_csv(ROOT / "data" / "regime" / "mgmt_sweep_20260724.csv")
b = pd.read_parquet(Path(r"C:/Users/Admin/myquant/data") / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
d = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last")).reset_index()
d["gap"] = ((d.dO - d.dC.shift(1)) / d.dC.shift(1) * 100).abs()
s = mg[mg.variant == "retest6"].copy()
s["gap"] = s.Date.map(d.set_index("Date")["gap"])
s = s[s.gap <= 0.54].sort_values("Date").reset_index(drop=True)
s["dt"] = pd.to_datetime(s.Date)
total = s.net.sum()


def pf(x):
    gp = x[x > 0].sum(); gl = -x[x < 0].sum()
    return gp / gl if gl > 0 else np.inf


# monthly evaluation points
months = pd.period_range(s.dt.min(), s.dt.max(), freq="M").to_timestamp("M")
rows = []
r12 = {}
for m in months:
    w = s[(s.dt > m - pd.DateOffset(months=12)) & (s.dt <= m)]
    r12[m] = (len(w), pf(w.net), w.net.sum())

print("== K1: trailing 12-mo PF < 1.0 (monthly) ==")
fires = [(m, *r12[m]) for m in months if r12[m][0] >= 30 and r12[m][1] < 1.0]
for (m, n, p_, nt) in fires:
    after = s[s.dt > m].net.sum()
    print(f"  FIRES {m.date()}  (12mo n={n} PF {p_:.2f} net {nt:+,.0f})  -> forgone after: {after:+,.0f}")
if not fires:
    print("  never fires")
k1_forgone = s[s.dt > fires[0][0]].net.sum() if fires else 0

print("\n== K2: closed DD beyond -25k ==")
eq = s.net.cumsum(); dd = eq - eq.cummax()
print(f"  lifetime maxDD {dd.min():+,.0f} -> {'FIRES' if dd.min() < -25000 else 'never fires'}")

print("\n== K3: either side PF<1.0 for 2+ consecutive quarters ==")
s["q"] = s.dt.dt.to_period("Q")
fires3 = []
for dr in ("L", "S"):
    x = s[s["dir"] == dr]
    qpf = x.groupby("q").net.apply(pf)
    qn = x.groupby("q").size()
    streak = 0
    for qq in qpf.index:
        if qn[qq] >= 8 and qpf[qq] < 1.0:
            streak += 1
            if streak >= 2:
                fdate = qq.to_timestamp(how="end")
                after = s[s.dt > fdate].net.sum()
                fires3.append((dr, str(qq), after))
                print(f"  FIRES {dr} after {qq}  -> whole-book forgone after: {after:+,.0f}")
                streak = 0          # re-arm
        else:
            streak = 0
if not fires3:
    print("  never fires")

print("\n== A1: trailing 12-mo NET < -$10k ==")
fa = [(m) for m in months if r12[m][0] >= 30 and r12[m][2] < -10000]
print("  never fires" if not fa else f"  fires: {[str(m.date()) for m in fa]}")

print("\n== A2: side PF<1.0 for 4+ consecutive quarters ==")
fires_a2 = []
for dr in ("L", "S"):
    x = s[s["dir"] == dr]
    qpf = x.groupby("q").net.apply(pf)
    qn = x.groupby("q").size()
    streak = 0
    for qq in qpf.index:
        if qn[qq] >= 8 and qpf[qq] < 1.0:
            streak += 1
            if streak >= 4:
                fires_a2.append((dr, str(qq)))
                streak = 0
        else:
            streak = 0
print("  never fires" if not fires_a2 else f"  fires: {fires_a2}")

# chart: rolling 12m PF + side quarterly PF
fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), dpi=115)
mm = [m for m in months if r12[m][0] >= 30]
a1.plot(mm, [r12[m][1] for m in mm], lw=2, color="#2a78d6")
a1.axhline(1.0, ls="--", color="#b23a2e")
for (m, n, p_, nt) in fires:
    a1.axvline(m, color="#b23a2e", alpha=0.4)
a1.set_title("K1: trailing 12-month PF (red line = kill threshold; red bands = fires)",
             fontweight="bold")
for dr, c in (("L", "#1f7a3d"), ("S", "#b23a2e")):
    x = s[s["dir"] == dr]
    qpf = x.groupby("q").net.apply(pf).clip(upper=3)
    a2.plot([q.to_timestamp() for q in qpf.index], qpf.values, "o-", lw=1.6, color=c, label=dr)
a2.axhline(1.0, ls="--", color="#33454d")
a2.legend(frameon=False)
a2.set_title("K3 inputs: quarterly PF by side (capped at 3)", fontweight="bold")
for ax in (a1, a2):
    ax.grid(axis="y", color="#eceeed", lw=0.6)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
p = ROOT / "docs" / "living" / "kill_rules_20260724.png"
fig.savefig(p, facecolor="white")
print("\nsaved", p)
