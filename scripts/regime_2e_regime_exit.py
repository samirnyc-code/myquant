"""Test the intuition directly: EXIT WHEN THE TREND BREAKS = exit at the regime engine's
own termination (BULL->NEUTRAL for a long / BEAR->NEUTRAL for a short), or the 0.30xADR
stop, whichever first; else EOD. vs the EOD-hold book. Then autopsy WHY: how much of the
fat tail (top-20 EOD winners) does the regime-exit give up?  2E WT book, 5yr ES.
  python scripts/regime_2e_regime_exit.py
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
            fill=lim; seg=tP[jfl:]; stop=fill-sd if not short else fill+sd
            hs=np.nonzero(seg<=stop)[0] if not short else np.nonzero(seg>=stop)[0]
            stop_i=jfl+int(hs[0]) if len(hs) else 10**9
            # regime termination tick after entry (trend broken -> leaves BULL/BEAR)
            term_i=10**9
            for (tk,md) in trans:
                if tk>jfl and md!=want: term_i=tk; break
            # EOD net
            ex_e=stop if stop_i<10**9 else seg[-1]
            net_eod=round(((fill-ex_e) if short else (ex_e-fill))*PT-COMM-SLIP,1)
            # regime-exit net (min of stop / termination / EOD)
            ei=min(stop_i, term_i)
            ex_r=stop if ei==stop_i and stop_i<10**9 else (tP[term_i] if ei==term_i and term_i<10**9 else seg[-1])
            net_reg=round(((fill-ex_r) if short else (ex_r-fill))*PT-COMM-SLIP,1)
            cut = term_i<10**9 and term_i<stop_i and term_i<jfl+len(seg)-1
            rows.append((dstr, net_eod, net_reg, cut))
        del tP,tbar; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)",flush=True)

    d=pd.DataFrame(rows,columns=["Date","eod","reg","cut"]); d.to_csv(WT/"data"/"regime"/"regime_exit.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  2E trades={len(d)}\n")
    print(f"  EOD-hold (book)     : net {d.eod.sum():+,.0f}  PF {pf(d.eod)}  win {(d.eod>0).mean()*100:.0f}%")
    print(f"  exit-on-trend-break : net {d.reg.sum():+,.0f}  PF {pf(d.reg)}  win {(d.reg>0).mean()*100:.0f}%  "
          f"(regime cut {d.cut.mean()*100:.0f}% of trades before EOD)")
    print(f"\nWHY — the fat tail: top-20 EOD winners")
    top=d.sort_values("eod",ascending=False).head(20)
    print(f"  those 20 trades: EOD ${top.eod.sum():+,.0f}  ->  exit-on-break kept ${top.reg.sum():+,.0f}  "
          f"(gave up ${top.eod.sum()-top.reg.sum():+,.0f} = {(1-top.reg.sum()/top.eod.sum())*100:.0f}% of the tail)")
    print(f"  whole book give-up from cutting early: ${d.eod.sum()-d.reg.sum():+,.0f}")
    # where does regime-exit help vs hurt?
    print(f"  on trades the regime CUT early: EOD ${d[d.cut].eod.sum():+,.0f} vs break-exit ${d[d.cut].reg.sum():+,.0f} (n={d.cut.sum()})")


if __name__=="__main__":
    main()
