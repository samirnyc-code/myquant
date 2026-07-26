"""SWING STOP from the regime engine: trail the stop to the last CONFIRMED structural
swing (HL for longs / LH for shorts) the phase machine prints; exit on break or EOD.
Initial stop = 0.30xADR (validated), then trail UP (long)/DOWN (short) to regime swings.
Tested on with-trend retest entries for ALL entry counts (1E/2E/3E), vs 0.30xADR/EOD.
  python scripts/regime_2e_swing_stop.py
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
    s=np.asarray(s,float); s=s[~np.isnan(s)]; gp=s[s>0].sum(); gl=-s[s<0].sum(); return round(gp/gl,2) if gl else 0


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
        H,L=g.High.values,g.Low.values; n=len(g); gdt=g.DateTime.values; trace={}
        try:
            trans=phase_transitions(H,L,n,tP,tbar,trace=trace); entries=detect_entries_causal(g,tP,tbar)
        except Exception: continue
        tix=[t for (t,_) in trans]; tmd=[m for (_,m) in trans]; sd=max(round(0.30*adr/TICK)*TICK,FLOOR)
        # trailing swing arrays by bar (confirmed structural lows/highs)
        piv=trace.get("piv",[])
        Lp=sorted([(int(p["conf"]), L[p["bar"]]-TICK) for p in piv if p["side"]=="L" and p.get("conf") is not None])
        Hp=sorted([(int(p["conf"]), H[p["bar"]]+TICK) for p in piv if p["side"]=="H" and p.get("conf") is not None])
        trailL=np.full(n,-np.inf); cur=-np.inf; li=0
        for bb in range(n):
            while li<len(Lp) and Lp[li][0]<=bb: cur=max(cur,Lp[li][1]); li+=1
            trailL[bb]=cur
        trailH=np.full(n,np.inf); cur=np.inf; hi=0
        for bb in range(n):
            while hi<len(Hp) and Hp[hi][0]<=bb: cur=min(cur,Hp[hi][1]); hi+=1
            trailH[bb]=cur
        for (fb,sb,dr,cnt,trig) in entries:
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
            fill=lim; seg=tP[jfl:]; segb=tbar[jfl:]; fb2=int(tbar[jfl])
            # baseline ADR/EOD
            stop0=fill-sd if not short else fill+sd
            hs=np.nonzero(seg<=stop0)[0] if not short else np.nonzero(seg>=stop0)[0]
            ex0=stop0 if len(hs) else seg[-1]
            net_adr=round(((fill-ex0) if short else (ex0-fill))*PT-COMM-SLIP,1)
            # swing-trail: init 0.30ADR, trail ONLY to swings CONFIRMED AFTER ENTRY (no stop-above-entry)
            if not short:
                rel=[(c,v) for (c,v) in Lp if c>fb2 and v<fill]
                sser=np.full(len(seg),stop0)
                if rel:
                    cf=np.array([c for c,_ in rel]); cv=np.maximum.accumulate([v for _,v in rel])
                    idx=np.searchsorted(cf,segb,"right"); tv=np.where(idx>0, cv[np.clip(idx-1,0,len(cv)-1)], -np.inf)
                    sser=np.maximum(stop0, tv)
                h=np.nonzero(seg<=sser)[0]; exs=sser[h[0]] if len(h) else seg[-1]
            else:
                rel=[(c,v) for (c,v) in Hp if c>fb2 and v>fill]
                sser=np.full(len(seg),stop0)
                if rel:
                    cf=np.array([c for c,_ in rel]); cv=np.minimum.accumulate([v for _,v in rel])
                    idx=np.searchsorted(cf,segb,"right"); tv=np.where(idx>0, cv[np.clip(idx-1,0,len(cv)-1)], np.inf)
                    sser=np.minimum(stop0, tv)
                h=np.nonzero(seg>=sser)[0]; exs=sser[h[0]] if len(h) else seg[-1]
            net_sw=round(((fill-exs) if short else (exs-fill))*PT-COMM-SLIP,1)
            rows.append((dstr, "2ES" if short else "2EL", int(cnt), net_adr, net_sw))
        del tP,tbar; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)",flush=True)

    d=pd.DataFrame(rows,columns=["Date","book","cnt","adr_eod","swing"]); d.to_csv(WT/"data"/"regime"/"swing_stop.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  with-trend retest entries (all counts)={len(d)}\n")
    def rep(x,lab):
        print(f"  {lab:16} n={len(x):4d}  ADR/EOD net {x.adr_eod.sum():+8,.0f}/PF{pf(x.adr_eod):<5}  "
              f"SWING net {x.swing.sum():+8,.0f}/PF{pf(x.swing)}")
    print("by entry count (1E/2E/3E):")
    for c in sorted(d.cnt.unique()): rep(d[d.cnt==c], f"count={c}")
    print("\ncombined:")
    rep(d[d.cnt==2],"2E only (book)"); rep(d[d.cnt!=2],"non-2E entries"); rep(d,"ALL entries")


if __name__=="__main__":
    main()
