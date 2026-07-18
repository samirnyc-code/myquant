"""cr/ps definition bakeoff: is MenthorQ using NET gamma, CALL-only/PUT-only,
and/or STRIKE-weighting (which changes ranking, unlike spot-weighting)?"""
import glob
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")

days=[]
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[3456].parquet"))):
    yr=pd.read_parquet(f)
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c]=pd.to_numeric(yr[c],errors="coerce")
    yr=yr[yr.dte>1]
    for d,grp in yr.groupby("tradeDate"):
        d=str(d)
        if d in MQ.index and pd.notna(MQ.loc[d,"cr"]): days.append((d,grp))
print(f"{len(days)} days")

DEFS={
 "net":            lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest),
 "net*K":          lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest)*g.strike,
 "net*K^2":        lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest)*g.strike**2,
 "callOI":         lambda g: g.gamma*g.callOpenInterest,
 "callOI*K^2":     lambda g: g.gamma*g.callOpenInterest*g.strike**2,
}
PDEFS={
 "net":            lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest),
 "net*K":          lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest)*g.strike,
 "net*K^2":        lambda g: g.gamma*(g.callOpenInterest-g.putOpenInterest)*g.strike**2,
 "putOI":          lambda g: -g.gamma*g.putOpenInterest,
 "putOI*K^2":      lambda g: -g.gamma*g.putOpenInterest*g.strike**2,
}
crh={k:0 for k in DEFS}; psh={k:0 for k in PDEFS}; n=0
for d,g in days:
    m=MQ.loc[d]; n+=1
    for k,fn in DEFS.items():
        p=fn(g).groupby(g.strike).sum()
        if len(p) and abs(p.idxmax()-m["cr"])<=0.01: crh[k]+=1
    for k,fn in PDEFS.items():
        p=fn(g).groupby(g.strike).sum()
        if len(p) and abs(p.idxmin()-m["ps"])<=0.01: psh[k]+=1
print("\nCR definition (exact-match %):")
for k,v in sorted(crh.items(),key=lambda kv:-kv[1]): print(f"  {k:14}: {v/n*100:5.1f}%")
print("PS definition (exact-match %):")
for k,v in sorted(psh.items(),key=lambda kv:-kv[1]): print(f"  {k:14}: {v/n*100:5.1f}%")
