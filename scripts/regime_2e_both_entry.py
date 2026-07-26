"""Samir's idea: enter BOTH — stop-entry at the trigger (catches runners) AND the 6t retest
limit (adds on pullbacks). From missed_pnl.csv (per-signal stop_net + retest_net + filled).
Compares Retest-only / Stop-only / BOTH (full) / BOTH (half-size each = same capital as 1 unit).
  python scripts/regime_2e_both_entry.py
"""
from pathlib import Path
import numpy as np, pandas as pd
WT = Path(__file__).resolve().parent.parent
d = pd.read_csv(WT/"data"/"regime"/"missed_pnl.csv").sort_values("Date").reset_index(drop=True)


def pf(vals):
    s=np.asarray(vals,float); s=s[~np.isnan(s)]; gp=s[s>0].sum(); gl=-s[s<0].sum(); return round(gp/gl,2) if gl else 0
def mdd(v): e=np.cumsum(v); return float((e-np.maximum.accumulate(e)).min())


d["ret"]=np.where(d.filled, d.retest_net, np.nan)             # retest fill (retracers only)
# per-signal combined pnl for each strategy + units deployed
strat={
 "A Retest-only (current)": (np.where(d.filled, d.retest_net, 0.0), d.filled.astype(int)),
 "B Stop-only (all 727)":   (d.stop_net.values,                    np.ones(len(d),int)),
 "C BOTH (stop + retest add)": (d.stop_net.values + np.where(d.filled, d.retest_net, 0.0),
                                1 + d.filled.astype(int)),
 "D BOTH half-size (0.5+0.5)": (0.5*d.stop_net.values + 0.5*np.where(d.filled, d.retest_net, 0.0),
                                0.5*(1 + d.filled.astype(int))),
}
# PF on individual fills (each stop fill + each retest fill counts once)
indiv={
 "A Retest-only (current)": d.ret.dropna().values,
 "B Stop-only (all 727)":   d.stop_net.values,
 "C BOTH (stop + retest add)": np.concatenate([d.stop_net.values, d.ret.dropna().values]),
 "D BOTH half-size (0.5+0.5)": np.concatenate([0.5*d.stop_net.values, 0.5*d.ret.dropna().values]),
}
print(f"{'strategy':30}{'net':>10}{'units':>7}{'$/unit':>8}{'PF':>6}{'maxDD':>9}")
for nm,(pnl,units) in strat.items():
    U=units.sum(); print(f"{nm:30}{pnl.sum():>10,.0f}{U:>7.0f}{pnl.sum()/U:>8.0f}{pf(indiv[nm]):>6.2f}{mdd(pnl):>9,.0f}")
print("\nread: BOTH catches the 154 runners (+$48k) but includes the worse trigger fills on the 573")
print("retracers, and deploys ~1.8 units/signal. Half-size BOTH = same capital as 1 unit/signal.")
