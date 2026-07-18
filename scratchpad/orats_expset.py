import pandas as pd, numpy as np
df = pd.read_parquet('scratchpad/orats_SPX_2026-07-15.parquet')
for c in ['strike','gamma','callOpenInterest','putOpenInterest','dte']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
SPOT=7572.40
MQ=[7475,7500,7550,7575,7580,7620,7625,7645,7650,7675]
df['net']=df.gamma*(df.callOpenInterest-df.putOpenInterest)*100*SPOT/1e6

# ---- 1) sweep dte cap: top-10 |GEX| (no peak/window), overlap with MQ ----
print("=== dte-cap sweep: top-10 |GEX|, exclude cr=7600 ===")
for cap in [2,4,6,9,16,23,32,45,60,90,180,3000]:
    p=df[(df.dte>1)&(df.dte<=cap)].groupby('strike')['net'].sum()
    top=[k for k in p.reindex(p.abs().sort_values(ascending=False).index).index if k!=7600][:10]
    ov=len(set(int(k) for k in top)&set(MQ))
    print(f"  dte<= {cap:4d}: {ov}/10  {sorted(int(k) for k in top)}")

# ---- 2) decompose disputed strikes by expiry (which expiries feed them) ----
disp=[7475,7500,7580,7590,7605,7620,7625,7630,7645,7660]
print("\n=== disputed strikes: GEX by dte bucket ($M) ===")
buckets=[(2,2),(3,9),(10,16),(17,32),(33,60),(61,180),(181,3000)]
hdr="strike  inMQ  "+" ".join(f"{a}-{b}" for a,b in buckets)
print(hdr)
for k in disp:
    row=df[df.strike==k]
    vals=[]
    for a,b in buckets:
        vals.append(row[(row.dte>=a)&(row.dte<=b)]['net'].sum())
    flag='Y' if k in MQ else '.'
    print(f"{k:6d}   {flag}   "+" ".join(f"{v:6.1f}" for v in vals))
