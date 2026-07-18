"""Level test WITH tolerance zones (fixing the exact-containment flaw).

touch(z)  = day's range comes within z of the level  (high >= L-z and low <= L+z)
hold(z)   = touched AND close is beyond the zone on the expected side
            (CR resistance: close < L-z ; PS support: close > L+z)
Control gets the SAME zone so comparison is fair.
"""
import glob
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(7)

px = pd.read_csv(ROOT/"data"/"options_sim"/"spx_daily_yahoo.csv")
px["Date"]=px.Date.astype(str); px=px.sort_values("Date").reset_index(drop=True)
sess=px.Date.tolist(); nxt={d:sess[i+1] for i,d in enumerate(sess[:-1])}
P=px.set_index("Date")
MQ=pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"]=MQ.session_date.astype(str); MQ=MQ.set_index("session_date")

ours={}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[456].parquet"))):
    yr=pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c]=pd.to_numeric(yr[c],errors="coerce")
    yr=yr[(yr.dte>1)&(yr.gamma.abs()<0.1)&(yr.delta.abs()<=1.01)]
    for d,g in yr.groupby("tradeDate"):
        d=str(d); spot=g["spotPrice"].median()
        p=(g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum(); p=p[np.isfinite(p)]
        if p.empty: continue
        ours[d]={"cr":p.idxmax(),"ps":p.idxmin(),"spot":spot}

def ev(getl, kind, z, shift=False):
    touch=hold=n=0
    for d in ours:
        s=nxt.get(d)
        if s is None or s not in P.index: continue
        L=getl(d)
        if L is None or not np.isfinite(L): continue
        if shift: L=L+rng.choice([-1,1])*rng.uniform(20,40)
        hi,lo,cl=P.loc[s,"High"],P.loc[s,"Low"],P.loc[s,"Close"]
        n+=1
        if hi>=L-z and lo<=L+z:
            touch+=1
            hold += (cl < L-z) if kind=="cr" else (cl > L+z)
    return n,touch,(hold/touch*100 if touch else float("nan"))

print("zone-swept level test (SPX pts). 'hold' = closed back beyond the zone.\n")
for z in [0,2.5,5,10,15,25]:
    print(f"--- zone +/-{z} pts ---")
    for lbl,getl,kind,sh in [
        ("OURS cr", lambda d: ours[d]["cr"], "cr", False),
        ("MQ   cr", lambda d: MQ.loc[d,"cr"] if d in MQ.index else None, "cr", False),
        ("CTRL cr", lambda d: ours[d]["cr"], "cr", True),
        ("OURS ps", lambda d: ours[d]["ps"], "ps", False),
        ("MQ   ps", lambda d: MQ.loc[d,"ps"] if d in MQ.index else None, "ps", False),
        ("CTRL ps", lambda d: ours[d]["ps"], "ps", True)]:
        n,t,h=ev(getl,kind,z,sh)
        print(f"   {lbl}  touch {t/n*100:5.1f}% (n={t:3d})  hold|touch {h:5.1f}%")
    print()
