"""Exit matrix on the 573 filled 6t-retest WT trades (2EL+2ES, 5yr ES).
Schemes (R = risk = stop distance):
  ADR/EOD  (current book) · ADR/1:1 · ADR/2:1 · SB/1:1 · SB/2:1 · SB/EOD
where ADR stop = 0.30xADR (floor 8t), SB stop = signal-bar extreme ±1t.
Reports WIN RATE (target hit, or net>0 for EOD), net, PF, $/tr. Then the same for the
FIRST trade of each day only.  python scripts/regime_2e_exit_matrix.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK; GOOD={"09","10","11","12","13"}
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s=np.asarray(s,float); gp=s[s>0].sum(); gl=-s[s<0].sum(); return round(gp/gl,2) if gl else 0


def main():
    b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=b.DateTime.dt.date.astype(str)
    dly=b.groupby("Date").agg(dO=("Open","first"),dC=("Close","last"),dH=("High","max"),dL=("Low","min")).reset_index()
    dly["gap"]=((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs(); dly["adr10"]=(dly.dH-dly.dL).rolling(10).mean().shift(1)
    gm=dly.set_index("Date")[["gap","adr10"]]; days=sorted(b.Date.unique()); rows=[]; t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in gm.index: continue
        gapv,adr=gm.loc[dstr,"gap"],gm.loc[dstr,"adr10"]
        if not np.isfinite(adr) or gapv>0.54: continue
        g,tP,tbar=load_day(b,dstr)
        if g is None: continue
        H,L=g.High.values,g.Low.values; n=len(g); gdt=g.DateTime.values
        try:
            trans=phase_transitions(H,L,n,tP,tbar); entries=detect_entries_causal(g,tP,tbar)
        except Exception: continue
        tix=[t for (t,_) in trans]; tmd=[m for (_,m) in trans]; sd=max(round(0.30*adr/TICK)*TICK,FLOOR)
        first=True
        for (fb,sb,dr,cnt,trig) in entries:
            if cnt!=2: continue
            short=dr=="S"; a=np.searchsorted(tbar,fb,"left"); z=np.searchsorted(tbar,fb,"right")
            hit=np.nonzero(tP[a:z]<=trig)[0] if short else np.nonzero(tP[a:z]>=trig)[0]
            if not len(hit): continue
            jf=a+int(hit[0]); reg=tmd[bisect_right(tix,jf)-1]; want="BEAR" if short else "BULL"
            if reg!=want or pd.Timestamp(gdt[min(fb,n-1)]).strftime("%H") not in GOOD: continue
            lim=trig+6*TICK if short else trig-6*TICK
            seg0=tP[jf:]; jl=np.nonzero(seg0>lim)[0] if short else np.nonzero(seg0<lim)[0]
            if not len(jl): continue
            jfl=jf+int(jl[0])
            if int(tbar[jfl])-fb>6 or pd.Timestamp(gdt[min(int(tbar[jfl]),n-1)]).strftime("%H") not in GOOD: continue
            fill=lim; seg=tP[jfl:]
            r_adr=sd
            r_sb=(fill-(L[sb]-TICK)) if not short else ((H[sb]+TICK)-fill)
            if r_sb<=0: r_sb=r_adr                       # degenerate guard
            def outcome(R, tmult):                        # returns net; win flag via caller
                stop=fill+R if short else fill-R
                tgt=(fill-tmult*R) if short else (fill+tmult*R) if tmult else None
                sh=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]
                si=sh[0] if len(sh) else 10**9
                if tmult:
                    th=np.nonzero(seg<=tgt)[0] if short else np.nonzero(seg>=tgt)[0]
                    ti=th[0] if len(th) else 10**9
                else:
                    ti=10**9
                if ti<si: ex=tgt; res="win"
                elif si<10**9: ex=stop; res="stop"
                else: ex=seg[-1]; res="eod"
                net=round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP,1)
                return net,res
            rec={"Date":dstr,"first":first}
            for lab,(R,tm) in {"ADR/EOD":(r_adr,0),"ADR/1:1":(r_adr,1),"ADR/2:1":(r_adr,2),
                               "SB/1:1":(r_sb,1),"SB/2:1":(r_sb,2),"SB/EOD":(r_sb,0)}.items():
                net,res=outcome(R,tm); rec[lab]=net; rec[lab+"_r"]=res
            rows.append(rec); first=False
        del tP,tbar; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)",flush=True)

    d=pd.DataFrame(rows); d.to_csv(WT/"data"/"regime"/"exit_matrix.csv",index=False)
    SCH=["ADR/EOD","ADR/1:1","ADR/2:1","SB/1:1","SB/2:1","SB/EOD"]
    def report(x,title):
        print(f"\n===== {title} (n={len(x)}) =====")
        print(f"{'scheme':10}{'win%':>7}{'target%':>9}{'stop%':>7}{'eod%':>6}{'net':>10}{'$/tr':>8}{'PF':>6}")
        for s in SCH:
            v=x[s]; wr=(v>0).mean()*100
            tgt=(x[s+'_r']=='win').mean()*100; stp=(x[s+'_r']=='stop').mean()*100; eo=(x[s+'_r']=='eod').mean()*100
            print(f"{s:10}{wr:>6.0f}%{tgt:>8.0f}%{stp:>6.0f}%{eo:>5.0f}%{v.sum():>10,.0f}{v.mean():>8.1f}{pf(v):>6.2f}")
    print(f"\nDONE {time.time()-t0:.0f}s  filled 6t trades={len(d)}")
    report(d,"ALL 6t trades")
    report(d[d.first],"FIRST trade of the day only")
    report(d[~d.first],"NON-first trades")


if __name__=="__main__":
    main()
