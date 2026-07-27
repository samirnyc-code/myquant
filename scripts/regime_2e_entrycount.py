"""ENTRY-COUNT breakdown (Samir, 2026-07-27): should we trade 1E (esp. 1ES)? Re-sim with-trend
1E/2E/3E with the BOOK's exact exit (retest 6t, 0.30xADR stop, 09-13, EOD), split by direction
and gamma-side (entry vs prior-day SMA20), 2021+ Databento proxy. Book unchanged.
  python scripts/regime_2e_entrycount.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions as pt_old
from regime_2e_causal_check import detect_entries_causal
from regime_2e_tickproxy_fidelity import proxy_ticks
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
GOOD={9,10,11,12,13}
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return round(gp/gl,2) if gl else 0.0
def main():
    limit=int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    m1=pd.read_parquet(DATA/"bars"/"_db_es_1m_rth.parquet"); m1["DateTime"]=pd.to_datetime(m1["DateTime"]); m1["Date"]=m1.DateTime.dt.date.astype(str)
    m1g={d:x.sort_values("DateTime").reset_index(drop=True) for d,x in m1.groupby("Date")}
    dly=b.groupby("Date").agg(dC=("Close","last"),dH=("High","max"),dL=("Low","min")).reset_index().sort_values("Date").reset_index(drop=True)
    dly["adr10"]=(dly.dH-dly.dL).rolling(10).mean().shift(1); dly["sma20"]=dly.dC.rolling(20).mean().shift(1)
    gm=dly.set_index("Date"); days=[d for d in sorted(b.Date.unique()) if d>="2021-01-01"]
    if limit: days=days[:limit]
    rows={}; 
    def acc(k,v): rows.setdefault(k,[]).append(v)
    t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g: continue
        row=gm.loc[dstr]; adr,sma=row.adr10,row.sma20
        if not np.isfinite(adr) or not np.isfinite(sma): continue
        g=b[b.Date==dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g)<30: continue
        m1d=m1g[dstr]; m1d=m1d[m1d.DateTime>=g.DateTime.values[0]]
        if len(m1d)<30: continue
        H,L=g.High.values,g.Low.values; n=len(g); g_dt=g.DateTime.values
        tP,tbar=proxy_ticks(g,m1d); trans=pt_old(H,L,n,tP,tbar); tr_ix=[t for(t,_)in trans]; tr_md=[m for(_,m)in trans]
        wide=max(round(0.30*adr/TICK)*TICK,FLOOR)
        for (fb,sb,dr,cnt,trig) in detect_entries_causal(g,tP,tbar):
            if cnt not in (1,2,3): continue
            short=dr=="S"; want="BEAR" if short else "BULL"
            a=np.searchsorted(tbar,fb,"left"); zz=np.searchsorted(tbar,fb,"right")
            hit=np.nonzero(tP[a:zz]<=trig)[0] if short else np.nonzero(tP[a:zz]>=trig)[0]
            if not len(hit): continue
            jf=a+int(hit[0]); reg=tr_md[bisect_right(tr_ix,jf)-1]
            if reg!=want: continue
            lim=trig+6*TICK if short else trig-6*TICK; s0=tP[jf:]
            jl=np.nonzero(s0>lim)[0] if short else np.nonzero(s0<lim)[0]
            if not len(jl): continue
            jfl=jf+int(jl[0]); fb2=int(tbar[jfl])
            if fb2-fb>6 or int(pd.Timestamp(g_dt[min(fb2,n-1)]).hour) not in GOOD: continue
            stop=lim+wide if short else lim-wide; seg=tP[jfl:]
            js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]
            ex=stop if len(js) else seg[-1]
            net=round(((lim-ex) if short else (ex-lim))*PT-COMM-SLIP,1)
            side="above" if lim>sma else "below"
            acc((cnt,dr,side),net)
        del tP,tbar; gc.collect()
    yrs=5.5
    print(f"\nENTRY-COUNT x SIDE x GAMMA (with-trend, book exit, 2021+, {len(days)} days scanned)")
    print(f"{'setup':<20}{'n':>6}{'PF':>7}{'net':>11}{'$/yr':>9}{'win%':>6}")
    for cnt in (1,2,3):
        for dr in ("L","S"):
            for side in ("above","below"):
                v=rows.get((cnt,dr,side),[])
                if not v: continue
                va=np.asarray(v,float)
                tag=f"{cnt}E{dr} {side}SMA"
                print(f"{tag:<20}{len(v):>6}{pf(va):>7.2f}{va.sum():>+11,.0f}{va.sum()/yrs:>+9,.0f}{100*(va>0).mean():>6.0f}")
        # combined above-gate (the book style) per count
        vv=np.asarray(rows.get((cnt,'L','above'),[])+rows.get((cnt,'S','above'),[]),float)
        if len(vv): print(f"{'  '+str(cnt)+'E both >SMA':<20}{len(vv):>6}{pf(vv):>7.2f}{vv.sum():>+11,.0f}{vv.sum()/yrs:>+9,.0f}{100*(vv>0).mean():>6.0f}")
        print()
if __name__=="__main__": main()
