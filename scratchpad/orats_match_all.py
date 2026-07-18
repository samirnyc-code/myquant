"""Match ALL MQ levels for SPX 2026-07-15 from the cached chain (free iteration).
Read GEX at each exact MQ strike to reverse-engineer the expiration set per family."""
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "scratchpad" / "orats_SPX_2026-07-15.parquet")
for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte",
          "stockPrice","spotPrice","callMidIv","putMidIv","callValue","putValue"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")

print("spot candidates: stockPrice.median=%.2f  spotPrice.median=%.2f  MQ spot_eod=7572.40"
      % (df.stockPrice.median(), df.spotPrice.median()))
SPOT = 7572.40  # MQ's spot_eod — use it for scaling

def netgex_by_strike(sub, spot=SPOT):
    g = sub.copy()
    g["net"] = g.gamma * (g.callOpenInterest - g.putOpenInterest) * 100 * spot
    return g.groupby("strike")["net"].sum()  # dollars per $1 move

allp = netgex_by_strike(df) / 1e6
dte1 = netgex_by_strike(df[df.dte == 1]) / 1e6           # true 0DTE (their dte=cal+1)
wk   = netgex_by_strike(df[df.dte <= 8]) / 1e6

def show(name, target_strike, target_gex, profile):
    v = profile.get(target_strike, np.nan)
    print(f"  {name:6} MQ={target_strike:.0f}@{target_gex/1e6:7.1f}M   "
          f"my@{target_strike:.0f}={v:7.1f}M   argmax={profile.idxmax():.0f}@{profile.max():.1f}M "
          f"argmin={profile.idxmin():.0f}@{profile.min():.1f}M")

print("\n=== cr / ps / hvl  (test ALL-expiry) ===")
show("cr", 7600, 106025733.70, allp)
show("ps", 7300, -34972479.61, allp)
show("hvl", 7535, -6161886.72, allp)

print("\n=== cr0/ps0/hvl0/gw0  (test 0DTE dte==1) ===")
n0 = (df.dte == 1).sum(); print(f"  (0DTE rows: {n0})")
show("cr0", 7600, 106025733.70, dte1)
show("ps0", 7555, 1937473.65, dte1)
show("hvl0", 7555, 1937473.65, dte1)
show("gw0", 7600, 106025733.70, dte1)

print("\n=== gex_1..10 (MQ strike -> my ALL-expiry GEX at that strike) ===")
gex = [(7550,36.94),(7575,55.24),(7620,46.83),(7580,41.61),(7625,39.69),
       (7500,16.59),(7650,68.90),(7675,26.22),(7475,-9.95),(7645,14.60)]
for k,mv in gex:
    print(f"  {k:.0f}: MQ={mv:6.1f}M  ALL={allp.get(k,np.nan):6.1f}M  0DTE={dte1.get(k,np.nan):6.1f}M")

print("\n=== my ALL-expiry top-12 by |GEX| ===")
top = allp.reindex(allp.abs().sort_values(ascending=False).index).head(12)
print("  " + ", ".join(f"{int(k)}:{v:.1f}" for k,v in top.items()))

print("\n=== d1_min/d1_max: 1-day expected move test ===")
# ATM IV of front expiry
front = df[df.dte == df.dte.min()]
atm = front.iloc[(front.strike - SPOT).abs().argsort()[:4]]
iv = pd.concat([atm.callMidIv, atm.putMidIv]).mean()
print(f"  front dte={df.dte.min()} ATM IV~{iv:.4f}")
for basis,lbl in [(252,"sqrt(1/252)"),(365,"sqrt(1/365)")]:
    mv = SPOT*iv*np.sqrt(1/basis)
    print(f"   +/- {lbl}: {SPOT-mv:.2f} .. {SPOT+mv:.2f}   [MQ 7512.78 .. 7631.62]")
