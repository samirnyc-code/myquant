"""HVL rule bakeoff — find MenthorQ's exact HVL definition on the liquid era (2023+)."""
import glob
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")

def rules(d):
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    spot=d["spotPrice"].median()
    if not np.isfinite(spot): return None,None
    g=d[d.dte>1].copy()
    g["n"]=g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*spot
    p=g.groupby("strike")["n"].sum().sort_index()/1e6
    if p.empty: return None,spot
    def band(w): return p[(p.index>=spot*(1-w))&(p.index<=spot*(1+w))]
    out={}
    # R1 cumsum argmin (current), various bands
    for w in (0.05,0.10,0.20):
        b=band(w)
        out[f"cumsum_argmin_{int(w*100)}"]= b.cumsum().idxmin() if not b.empty else np.nan
    # R2 cumsum zero-crossing nearest spot
    b=band(0.10); cum=b.cumsum(); xs=[]
    for i in range(1,len(cum)):
        a,bb=cum.iloc[i-1],cum.iloc[i]
        if (a<0<=bb) or (a>0>=bb): xs.append(cum.index[i])
    out["zero_cross"]=min(xs,key=lambda s:abs(s-spot)) if xs else np.nan
    # R3 biggest negative single strike near spot (put wall)
    b=band(0.05); neg=b[b<0]
    out["max_put_wall"]= neg.idxmin() if not neg.empty else np.nan
    # R4 per-strike sign flip: highest neg strike that is immediately below a pos run
    b=band(0.05); flip=np.nan
    idx=list(b.index)
    for i in range(len(idx)-1):
        if b.iloc[i]<0 and b.iloc[i+1]>0: flip=idx[i]
    out["signflip_lowpos"]=flip
    return out,spot

def main():
    files=sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[3456].parquet")))
    tally={}; n=0
    for f in files:
        yr=pd.read_parquet(f)
        for d,grp in yr.groupby("tradeDate"):
            d=str(d)
            if d not in MQ.index or pd.isna(MQ.loc[d,"hvl"]): continue
            out,spot=rules(grp.copy())
            if not out: continue
            mqh=MQ.loc[d,"hvl"]; n+=1
            for k,v in out.items():
                if pd.isna(v): continue
                t=tally.setdefault(k,{"exact":0,"w1":0,"w2":0,"nn":0,"abs":[]})
                e=abs(v-mqh); t["nn"]+=1
                t["exact"]+= e<=0.01; t["w1"]+= e<=5.01; t["w2"]+= e<=10.01
                t["abs"].append(e)
    print(f"HVL bakeoff on {n} days (2023-2026):")
    print(f"  {'rule':22}{'exact%':>8}{'<=1strk%':>9}{'<=2strk%':>9}{'medErr':>8}")
    for k,t in sorted(tally.items(),key=lambda kv:-kv[1]['exact']/max(kv[1]['nn'],1)):
        nn=t["nn"]
        print(f"  {k:22}{t['exact']/nn*100:>7.1f}%{t['w1']/nn*100:>8.1f}%"
              f"{t['w2']/nn*100:>8.1f}%{np.median(t['abs']):>8.1f}")

if __name__=="__main__":
    main()
