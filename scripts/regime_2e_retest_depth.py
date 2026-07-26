"""(A) Is 6t the ideal retest limit? Sweep retest depth {1..16 ticks}: deeper = better fill
    but fewer fills (more misses). Net/PF/fills vs depth -> is 6t the peak or a plateau?
(B) Are the RUNNERS (never retrace) predictable at the trigger from CAUSAL signal-bar features
    (SB size, SB close position, EMA extension, time-of-day)? Runner-rate by feature bucket +
    train/test. Anti-overfit: features known BY the trigger only; univariate; coarse; train vs test.
2EL(long,BULL)+2ES(short,BEAR), 5yr ES.   python scripts/regime_2e_retest_depth.py
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK; GOOD={"09","10","11","12","13"}
DEPTHS=[1,2,3,4,6,8,10,12,16]
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s=np.asarray(s,float); s=s[~np.isnan(s)]; gp=s[s>0].sum(); gl=-s[s<0].sum(); return round(gp/gl,2) if gl else 0


def main():
    b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=b.DateTime.dt.date.astype(str)
    b["ema20"]=b.Close.ewm(span=20,adjust=False).mean()
    dly=b.groupby("Date").agg(dO=("Open","first"),dC=("Close","last"),dH=("High","max"),dL=("Low","min")).reset_index()
    dly["gap"]=((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs(); dly["adr10"]=(dly.dH-dly.dL).rolling(10).mean().shift(1)
    gm=dly.set_index("Date")[["gap","adr10"]]; days=sorted(b.Date.unique()); rows=[]; t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in gm.index: continue
        gapv,adr=gm.loc[dstr,"gap"],gm.loc[dstr,"adr10"]
        if not np.isfinite(adr) or gapv>0.54: continue
        g,tP,tbar=load_day(b,dstr)
        if g is None: continue
        H,L=g.High.values,g.Low.values; C=g.Close.values; n=len(g); gdt=g.DateTime.values
        ema=b[b.Date==dstr]["ema20"].values
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
            def sim(fill,et):
                stop=fill+sd if short else fill-sd; seg=tP[et:]
                js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]
                ex=stop if len(js) else seg[-1]; return round(((fill-ex) if short else (ex-fill))*PT-COMM-SLIP,1)
            rec={"Date":dstr,"book":"2ES" if short else "2EL","yr":dstr[:4]}
            seg0=tP[jf:]
            for d in DEPTHS:
                lim=trig+d*TICK if short else trig-d*TICK
                jl=np.nonzero(seg0>lim)[0] if short else np.nonzero(seg0<lim)[0]
                nd=np.nan
                if len(jl):
                    jfl=jf+int(jl[0])
                    if int(tbar[jfl])-fb<=6 and pd.Timestamp(gdt[min(int(tbar[jfl]),n-1)]).strftime("%H") in GOOD:
                        nd=sim(lim,jfl)
                rec[f"d{d}"]=nd
            # causal SB features (known by the trigger)
            rng=H[sb]-L[sb]+1e-9
            rec["sb_atr"]=rng/adr
            rec["sb_pos"]=(H[sb]-C[sb])/rng if short else (C[sb]-L[sb])/rng   # close strength in trade dir
            rec["ema_ext"]=abs(trig-ema[sb])/adr
            rec["tod"]=int(pd.Timestamp(gdt[min(fb,n-1)]).strftime("%H"))
            rec["stop_net"]=sim(trig+TICK if short else trig-TICK, jf)
            rows.append(rec)
        del tP,tbar; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] {len(rows)} ({time.time()-t0:.0f}s)",flush=True)

    d=pd.DataFrame(rows); d.to_csv(WT/"data"/"regime"/"retest_depth.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  signals={len(d)}\n")
    print("===== (A) RETEST-DEPTH SWEEP (fill within 6 bars) =====")
    print(f"{'depth':7}{'fills':>7}{'miss%':>7}{'net':>10}{'$/tr':>8}{'PF':>6}")
    for dp in DEPTHS:
        v=d[f"d{dp}"]; fl=v.notna(); star=" <== current" if dp==6 else ""
        print(f"{dp}t {'':2}{int(fl.sum()):>7}{(1-fl.mean())*100:>6.0f}%{v.sum():>10,.0f}{v[fl].mean():>8.1f}{pf(v):>6.2f}{star}")

    print("\n===== (B) ARE RUNNERS PREDICTABLE? (runner = not filled at 6t) =====")
    d["runner"]=d["d6"].isna(); d["tr"]=d.Date<="2023-12-31"
    print(f"base runner rate: {d.runner.mean()*100:.0f}%  (n={len(d)})")
    for f in ["sb_atr","sb_pos","ema_ext"]:
        med=d[f].median(); hi=d[d[f]>med]; lo=d[d[f]<=med]
        # train/test runner-rate split
        def rr(x): return f"{x.runner.mean()*100:.0f}%"
        print(f"  {f:8}: HI runner {rr(hi)} (tr {rr(hi[hi.tr])}/te {rr(hi[~hi.tr])}) | "
              f"LO runner {rr(lo)} (tr {rr(lo[lo.tr])}/te {rr(lo[~lo.tr])})")
    # tod
    early=d[d.tod<=10]; late=d[d.tod>=12]
    print(f"  tod     : early(<=10h) runner {early.runner.mean()*100:.0f}% | late(>=12h) {late.runner.mean()*100:.0f}%")

    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(11,5),dpi=120); ax2=ax.twinx()
    nets=[d[f"d{dp}"].sum() for dp in DEPTHS]; pfs=[pf(d[f"d{dp}"]) for dp in DEPTHS]; fills=[d[f"d{dp}"].notna().sum() for dp in DEPTHS]
    ax.bar([str(x)+"t" for x in DEPTHS],nets,color="#2a78d6",alpha=.75,label="net $")
    ax2.plot([str(x)+"t" for x in DEPTHS],pfs,"-o",color="#b23a2e",label="PF")
    for i,dp in enumerate(DEPTHS): ax.annotate(f"{fills[i]}\nfills",(i,nets[i]),textcoords="offset points",xytext=(0,3),ha="center",fontsize=7.5,color="#555")
    ax.axvline(DEPTHS.index(6),ls="--",color="#333",alpha=.5)
    ax.set_ylabel("net $ (blue)"); ax2.set_ylabel("PF (red)"); ax.set_xlabel("retest depth (ticks back from trigger)")
    ax.set_title("Retest-depth sweep — is 6t ideal? (dashed = current 6t)",fontweight="bold")
    for s_ in ("top",): ax.spines[s_].set_visible(False); ax2.spines[s_].set_visible(False)
    fig.tight_layout(); fig.savefig(WT/"docs"/"living"/"retest_depth.png",facecolor="white")
    print("\nsaved docs/living/retest_depth.png")


if __name__=="__main__":
    main()
