import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "scratchpad" / "orats_SPX_2026-07-15.parquet")
for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte",
          "callMidIv","putMidIv"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
SPOT = 7572.40

def prof(sub):
    g = sub.copy()
    g["net"] = g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*SPOT
    return g.groupby("strike")["net"].sum()/1e6

main = prof(df[df.dte > 1])      # main levels: exclude expiring-today 0DTE
d0   = prof(df[df.dte == 1])     # 0DTE slice

# ---- d1 expected move: 30D constant-maturity ATM IV ----
atmiv = {}
for d, sub in df.groupby("dte"):
    a = sub.iloc[(sub.strike-SPOT).abs().argsort()[:2]]
    atmiv[d] = pd.concat([a.callMidIv, a.putMidIv]).mean()
s = pd.Series(atmiv).sort_index()
iv30 = np.interp(31, s.index, s.values)         # ~30 calendar days (dte=cal+1)
mv = SPOT*iv30*np.sqrt(1/252)
d1_min, d1_max = SPOT-mv, SPOT+mv

# ---- 0DTE family ----
cr0 = (main.idxmax(), main.max())               # MQ: cr0==cr byte-identical
gw0 = cr0
# ps0/hvl0 = 0DTE gamma flip strike nearest spot
cum0 = d0.cumsum(); flip0=None
band = d0[(d0.index>=SPOT-60)&(d0.index<=SPOT+60)].cumsum()
for i in range(1,len(band)):
    if (band.iloc[i-1]<0<=band.iloc[i]) or (band.iloc[i-1]>0>=band.iloc[i]):
        flip0=band.index[i]; break
ps0 = (flip0, d0.get(flip0, np.nan)) if flip0 else (np.nan, np.nan)

MQ = {
 "d1_min":(7512.78,None),"d1_max":(7631.62,None),
 "cr0":(7600,106.03),"gw0":(7600,106.03),"ps0":(7555,1.94),"hvl0":(7555,1.94),
}
MQgex = [(7550,36.94),(7575,55.24),(7620,46.83),(7580,41.61),(7625,39.69),
         (7500,16.59),(7650,68.90),(7675,26.22),(7475,-9.95),(7645,14.60)]

print("LEVEL       MQ_strike  MQ_gex(M)   MY_strike  MY_gex(M)")
print(f"d1_min      {7512.78:8.2f}      -       {d1_min:8.2f}      -    (iv30={iv30:.4f})")
print(f"d1_max      {7631.62:8.2f}      -       {d1_max:8.2f}      -")
print(f"cr0         {7600:8.0f}   {106.03:8.2f}   {cr0[0]:8.0f}   {cr0[1]:8.2f}")
print(f"gw0         {7600:8.0f}   {106.03:8.2f}   {gw0[0]:8.0f}   {gw0[1]:8.2f}")
print(f"ps0         {7555:8.0f}   {1.94:8.2f}   {ps0[0]:8.0f}   {ps0[1]:8.2f}")
print(f"hvl0        {7555:8.0f}   {1.94:8.2f}   {ps0[0]:8.0f}   {ps0[1]:8.2f}")
print("--- GEX 1..10 (magnitude at MQ's strike, main dte>1 profile) ---")
for i,(k,mv_) in enumerate(MQgex,1):
    print(f"gex_{i:<2}      {k:8.0f}   {mv_:8.2f}   {k:8.0f}   {main.get(k,np.nan):8.2f}")
