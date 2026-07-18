"""Find MenthorQ's expiration horizon: sweep dte cap, score cr/ps/hvl exact-match
across ALL 2023-2026 days (not just miss days)."""
import glob
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")
CAPS = [7, 14, 21, 30, 45, 60, 75, 90, 120, 180, 270, 365, 10**6]

days=[]
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[3456].parquet"))):
    yr=pd.read_parquet(f)
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c]=pd.to_numeric(yr[c],errors="coerce")
    for d,grp in yr.groupby("tradeDate"):
        d=str(d)
        if d not in MQ.index or pd.isna(MQ.loc[d,"cr"]): continue
        days.append((d, grp[["strike","gamma","callOpenInterest","putOpenInterest","dte","spotPrice"]]))
print(f"scoring {len(days)} days x {len(CAPS)} caps...")

res={}
for cap in CAPS:
    cr=ps=hv=n=0
    for d,g in days:
        spot=g["spotPrice"].median()
        s=g[(g.dte>1)&(g.dte<=cap)]
        if s.empty: continue
        ngex=(s.gamma*(s.callOpenInterest-s.putOpenInterest)*100*spot)
        p=ngex.groupby(s.strike).sum().sort_index()/1e6
        if p.empty: continue
        n+=1
        m=MQ.loc[d]
        cr += abs(p.idxmax()-m["cr"])<=0.01
        ps += abs(p.idxmin()-m["ps"])<=0.01
        fb=p[(p.index>=spot*0.90)&(p.index<=spot*1.10)]
        if not fb.empty and pd.notna(m["hvl"]):
            hv += abs(fb.cumsum().idxmin()-m["hvl"])<=0.01
    res[cap]=(n,cr/n*100,ps/n*100,hv/n*100)
    print(f"  dte<={cap:>7}: n={n}  cr {cr/n*100:5.1f}%  ps {ps/n*100:5.1f}%  hvl {hv/n*100:5.1f}%"
          f"   avg {(cr+ps+hv)/(3*n)*100:5.1f}%")
best=max(res.items(), key=lambda kv: sum(kv[1][1:]))
print(f"\nBEST cap: dte<={best[0]}  cr {best[1][1]:.1f}%  ps {best[1][2]:.1f}%  hvl {best[1][3]:.1f}%")
