"""Diagnose cr/ps/hvl MISS cases (2023-2026): is MQ's level near the top of OUR
profile (recipe gap, fixable) or nowhere (data gap, fundamental)?"""
import glob
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")

def prof(d, dte_lo=2, dte_hi=10**6):
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    spot=d["spotPrice"].median()
    g=d[(d.dte>=dte_lo)&(d.dte<=dte_hi)].copy()
    g["n"]=g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*spot
    return g.groupby("strike")["n"].sum().sort_index()/1e6, spot

cr_rank={}; cr_ptmiss=[]; ps_rank={}
alt_hits={"dte>1":0,"dte 1-90":0,"dte 1-45":0,"all":0}; nmiss=0; ntot=0
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[3456].parquet"))):
    yr=pd.read_parquet(f)
    for d,grp in yr.groupby("tradeDate"):
        d=str(d)
        if d not in MQ.index or pd.isna(MQ.loc[d,"cr"]): continue
        p,spot=prof(grp.copy())
        if p.empty: continue
        ntot+=1
        mqcr=MQ.loc[d,"cr"]; mycr=p.idxmax()
        if abs(mycr-mqcr)>0.01:
            nmiss+=1
            # rank of MQ's cr strike in my |profile| (1 = my top pick)
            order=p.sort_values(ascending=False)
            pos_order=order[order>0]
            rk = list(pos_order.index).index(mqcr)+1 if mqcr in pos_order.index else 99
            cr_rank[rk]=cr_rank.get(rk,0)+1
            cr_ptmiss.append(abs(mycr-mqcr))
            # would a different expiration set have picked MQ's cr?
            for lbl,(lo,hi) in {"dte>1":(2,10**6),"dte 1-90":(2,91),"dte 1-45":(2,46),"all":(1,10**6)}.items():
                pp,_=prof(grp.copy(),lo,hi)
                if not pp.empty and pp.idxmax()==mqcr: alt_hits[lbl]+=1
        # ps rank too
        mqps=MQ.loc[d,"ps"]; myps=p.idxmin()
        if abs(myps-mqps)>0.01:
            order=p.sort_values()  # most negative first
            neg=order[order<0]
            rk=list(neg.index).index(mqps)+1 if mqps in neg.index else 99
            ps_rank[rk]=ps_rank.get(rk,0)+1

print(f"2023-2026: {ntot} days, cr MISSES on {nmiss} ({nmiss/ntot*100:.1f}%)")
print(f"  cr miss median |error|: {np.median(cr_ptmiss):.0f} pts, p90 {np.percentile(cr_ptmiss,90):.0f} pts")
print("  RANK of MQ's cr in my positive-GEX profile (on miss days):")
for rk in sorted(cr_rank):
    print(f"    rank {rk if rk<99 else 'not in profile':>14}: {cr_rank[rk]:>4} days ({cr_rank[rk]/nmiss*100:.0f}%)")
print("  on cr-miss days, which expiration set's argmax = MQ cr:")
for lbl,h in alt_hits.items():
    print(f"    {lbl:10}: recovers {h}/{nmiss} ({h/nmiss*100:.0f}%)")
print("  ps miss rank distribution:", {k:ps_rank[k] for k in sorted(ps_rank)})
