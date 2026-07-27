"""RevFT EXTREME-FILTER sweep (Samir, 2026-07-27) — MASSIVE data + REAL ticks.
Keep only RevFT signals where the reversal bar AND the bar before it make the n-bar extreme
(n-bar low for a Long reversal, n-bar high for a Short). Sweep n=6..10. Split with-trend /
counter-trend / neutral (phase-machine regime at the signal bar vs signal dir). Re-sim on the
Massive ES 5M bars (data/bars/_continuous.parquet) + real ticks (ticks_continuous via load_day):
entry = first tick after the signal bar close, stop = the signal's own StopPrice, exit = EOD
(+ 1R/2R/3R targets). Signals 2021-06..2026.

  python scripts/regime_revft_extreme_sweep.py [--limit N]
Output: data/regime/revft_extreme_sweep_YYYYMMDD.csv + stdout.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions as pt_old, load_day
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
SIG=Path(r"C:/Users/Admin/myquant/saved_signals/ba_signals_revft.parquet")
BARS=DATA/"bars"/"_continuous.parquet"
NS=[6,7,8,9,10]; RT=[None,1.0,2.0,3.0]


def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return round(gp/gl,2) if gl else 0.0


def resim(seg, entry, stop, short, tgt_R):
    risk=abs(entry-stop)
    if risk<=0: return None
    js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]; si=js[0] if len(js) else np.inf
    if tgt_R is None:
        ex=stop if si<np.inf else seg[-1]
    else:
        tgt=entry-tgt_R*risk if short else entry+tgt_R*risk
        jt=np.nonzero(seg<=tgt)[0] if short else np.nonzero(seg>=tgt)[0]; ti=jt[0] if len(jt) else np.inf
        ex=(seg[-1] if si==np.inf and ti==np.inf else (tgt if ti<=si else stop))
    return ((entry-ex) if short else (ex-entry))*PT-COMM-SLIP


def main():
    limit=int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    s=pd.read_parquet(SIG); s["DateTime"]=pd.to_datetime(s["DateTime"]); s["Date"]=s.DateTime.dt.date.astype(str)
    b=pd.read_parquet(BARS); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    sdays=sorted(set(s.Date)&set(b.Date))
    if limit: sdays=sdays[:limit]
    rows={}; base={}
    def acc(store,k,v):
        if v is not None: store.setdefault(k,[]).append(v)
    t0=time.time(); nfilled=0; nsig=0
    for di,dstr in enumerate(sdays):
        gd=load_day(b,dstr)
        if gd[0] is None: continue
        g,tP,tbar=gd; H,L=g.High.values,g.Low.values; n=len(g)
        tmap={pd.Timestamp(t):i for i,t in enumerate(g.DateTime.values)}
        trans=pt_old(H,L,n,tP,tbar); tr_ix=[t for(t,_)in trans]; tr_md=[m for(_,m)in trans]
        def regat(bar):
            z=int(np.searchsorted(tbar,bar,"right")); return tr_md[bisect_right(tr_ix,z-1)-1] if z else "NEUTRAL"
        for _,r in s[s.Date==dstr].iterrows():
            nsig+=1
            bi=tmap.get(pd.Timestamp(r.DateTime))
            if bi is None or bi<10 or bi>=n-1: continue
            short=r.Direction=="Short"; reg=regat(bi)
            side = "WT" if ((not short and reg=="BULL") or (short and reg=="BEAR")) else ("CT" if ((not short and reg=="BEAR") or (short and reg=="BULL")) else "NEUT")
            a=np.searchsorted(tbar,bi+1,"left")
            if a>=len(tP): continue
            entry=float(tP[a]); seg=tP[a:]; stop=float(r.StopPrice)
            nfilled+=1
            nb=resim(seg,entry,stop,short,None); acc(base,("ALL",side),nb)
            ext=min(L[bi],L[bi-1]) if not short else max(H[bi],H[bi-1])
            for nn in NS:
                lo=L[bi-nn+1:bi+1].min(); hi=H[bi-nn+1:bi+1].max()
                if (ext<=lo) if not short else (ext>=hi):
                    for tr in RT: acc(rows,(nn,side,tr),resim(seg,entry,stop,short,tr))
        del tP,tbar; gc.collect()
        if (di+1)%250==0: print(f"[{di+1}/{len(sdays)}] {time.time()-t0:.0f}s",flush=True)
    span=(pd.to_datetime(sdays[-1])-pd.to_datetime(sdays[0])).days/365.25; yrs=max(span,0.1)
    print(f"\nRevFT (MASSIVE real ticks) {sdays[0]}..{sdays[-1]} ({yrs:.1f}yr).  signals filled {nfilled}/{nsig}")
    print("\n--- BASELINE (all RevFT, no extreme filter, EOD, stop=signal StopPrice) ---")
    for side in ("WT","CT","NEUT","ALL"):
        allv=[v for k,l in base.items() if (k[1]==side or side=="ALL") for v in l]
        if allv: print(f"  {side:<5} n={len(allv):4d}  PF {pf(allv):4.2f}  net ${sum(allv):+9,.0f}  (${sum(allv)/yrs:+7,.0f}/yr)  win {100*np.mean(np.array(allv)>0):3.0f}%")
    print("\n--- EXTREME-FILTERED (2-bar = n-bar extreme), EOD exit ---")
    print(f"{'n':>3}{'side':>6}{'trades':>8}{'PF':>6}{'net':>11}{'$/yr':>9}{'win%':>6}")
    out=[]
    for nn in NS:
        for side in ("WT","CT","NEUT"):
            va=np.asarray(rows.get((nn,side,None),[]),float)
            if len(va): print(f"{nn:>3}{side:>6}{len(va):>8}{pf(va):>6.2f}{va.sum():>+11,.0f}{va.sum()/yrs:>+9,.0f}{100*(va>0).mean():>6.0f}")
            for tr in RT:
                vv=np.asarray(rows.get((nn,side,tr),[]),float)
                out.append({"n":nn,"side":side,"target":("EOD" if tr is None else f"{tr}R"),"trades":len(vv),"pf":pf(vv),"net":vv.sum(),"per_yr":vv.sum()/yrs,"win":(100*(vv>0).mean() if len(vv) else 0)})
        print()
    print("--- target sweep per (n, side) ---")
    for nn in NS:
        for side in ("WT","CT"):
            cells=[f"{('EOD' if tr is None else str(tr)+'R')}:{pf(np.asarray(rows.get((nn,side,tr),[]),float)):.2f}/{np.asarray(rows.get((nn,side,tr),[]),float).sum()/yrs:+.0f}" for tr in RT if len(rows.get((nn,side,tr),[]))]
            if cells: print(f"  n={nn} {side}: "+"  ".join(cells))
    pd.DataFrame(out).to_csv(WT/"data"/"regime"/"revft_extreme_sweep_20260727.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  saved data/regime/revft_extreme_sweep_20260727.csv")


if __name__=="__main__": main()
