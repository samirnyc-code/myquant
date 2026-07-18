import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "scratchpad" / "orats_SPX_2026-07-15.parquet")
for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","stockPrice",
          "spotPrice","callMidIv","putMidIv","callValue","putValue","smvVol"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
SPOT = 7572.40

def prof(sub):
    g = sub.copy()
    g["net"] = g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*SPOT
    return g.groupby("strike")["net"].sum()/1e6

# ---- d1 expected move: MQ target +/-59.4 (7512.78..7631.62) ----
print("=== d1 expected move (MQ ±59.4) ===")
d0 = df[df.dte==1]
atm0 = d0.iloc[(d0.strike-SPOT).abs().argsort()[:2]]
straddle = (atm0.callValue+atm0.putValue).mean()
print(f"  0DTE ATM straddle price     = {straddle:.2f}")
print(f"  0.7*straddle                = {0.7*straddle:.2f}")
for cap in [1,2,8,23,30,60]:
    s = df[df.dte<=cap]
    a = s.iloc[(s.strike-SPOT).abs().argsort()[:4]]
    iv = pd.concat([a.callMidIv,a.putMidIv]).mean()
    print(f"  dte<={cap:2d}: ATM IV={iv:.4f}  ->±{SPOT*iv*np.sqrt(1/252):.2f}  (implied IV for ±59.4 = {59.4/(SPOT*np.sqrt(1/252)):.4f})")

# ---- 0DTE set: what gives ps0/hvl0 = 7555 @ +1.94M ----
print("\n=== ps0/hvl0 target 7555 @ +1.94M : scan expiry sets, read @7555 & argmin near spot ===")
for cap in [1,2,3,5,8]:
    p = prof(df[df.dte<=cap])
    near = p[(p.index>=7450)&(p.index<=7650)]
    print(f"  dte<={cap}: @7555={p.get(7555,np.nan):6.2f}M  argmin_near={near.idxmin():.0f}@{near.min():.2f}  argmax_near={near.idxmax():.0f}@{near.max():.2f}")

# ---- wall selection: MQ picks these 10 (excl 7600). near-spot peaks? ----
print("\n=== wall selection: all-expiry, round-$25 grid, |dist|<=110 ===")
p = prof(df)
grid = p[(p.index % 25 == 0) & (np.abs(p.index-SPOT)<=110)]
grid = grid.reindex(grid.abs().sort_values(ascending=False).index)
mqset = {7550,7575,7620,7580,7625,7500,7650,7675,7475,7645}
print("  top round-25 near-spot:", ", ".join(f"{int(k)}:{v:.0f}" for k,v in grid.head(12).items()))
print("  MQ set:", sorted(mqset))
# hvl = per-strike sign-flip (highest negative strike below the +cluster)?
print("\n=== hvl selection (MQ=7535, small negative) ===")
near = p[(p.index>=7500)&(p.index<=7600)]
print("  per-strike GEX 7500-7600:", ", ".join(f"{int(k)}:{v:.1f}" for k,v in near.items()))
