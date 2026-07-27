"""ABR8 stop/target sweep (Samir, 2026-07-27): scale stop & target to ABR8 = avg of the last 8
bars' (H-L) range (intraday vol), NOT ADR10 (daily). Sweep stop = a*ABR8 x target = b*ABR8
(+ EOD + trailing) with first-touch ordered exits, for 2E entries broken out by regime-at-fill
(WT / BULL / BEAR / NEUTRAL / all) and for the FADES. 2021+ Databento proxy. Book unchanged.

  python scripts/regime_2e_abr8_sweep.py [--limit N]
Output: data/regime/abr8_sweep_YYYYMMDD.csv + stdout grids (PF / $per-yr).
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions as pt_old
from regime_2e_causal_check import detect_entries_causal
from regime_2e_tickproxy_fidelity import proxy_ticks
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
GOOD={9,10,11,12,13}; KFADE=2
STOPS=[0.5,1.0,1.5,2.0,3.0]                       # x ABR8
TGTS=[None,1.0,2.0,3.0,4.0,6.0,"trail"]           # x ABR8 (None=EOD, trail=trailing by stop)


def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return round(gp/gl,2) if gl else 0.0


def exit_net(seg, fill, short, stop_pts, tgt_pts, trail):
    stop = fill+stop_pts if short else fill-stop_pts
    if trail:
        if short:
            tstop=np.minimum.accumulate(seg)+stop_pts; hit=np.nonzero(seg>=tstop)[0]
        else:
            tstop=np.maximum.accumulate(seg)-stop_pts; hit=np.nonzero(seg<=tstop)[0]
        ex=seg[hit[0]] if len(hit) else seg[-1]
        return ((fill-ex) if short else (ex-fill))*PT-COMM-SLIP
    js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]; si=js[0] if len(js) else np.inf
    if tgt_pts is None:
        ex=stop if si<np.inf else seg[-1]
    else:
        tgt=fill-tgt_pts if short else fill+tgt_pts
        jt=np.nonzero(seg<=tgt)[0] if short else np.nonzero(seg>=tgt)[0]; ti=jt[0] if len(jt) else np.inf
        ex=(seg[-1] if (si==np.inf and ti==np.inf) else (tgt if ti<=si else stop))
    return ((fill-ex) if short else (ex-fill))*PT-COMM-SLIP


def main():
    limit=int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    m1=pd.read_parquet(DATA/"bars"/"_db_es_1m_rth.parquet"); m1["DateTime"]=pd.to_datetime(m1["DateTime"]); m1["Date"]=m1.DateTime.dt.date.astype(str)
    m1g={d:x.sort_values("DateTime").reset_index(drop=True) for d,x in m1.groupby("Date")}
    days=[d for d in sorted(b.Date.unique()) if d>="2021-01-01"]
    if limit: days=days[:limit]
    rows={}; abrs=[]
    def acc(k,v): rows.setdefault(k,[]).append(v)
    t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in m1g: continue
        g=b[b.Date==dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g)<30: continue
        m1d=m1g[dstr]; m1d=m1d[m1d.DateTime>=g.DateTime.values[0]]
        if len(m1d)<30: continue
        H,L=g.High.values,g.Low.values; n=len(g); g_dt=g.DateTime.values; rng=H-L
        tP,tbar=proxy_ticks(g,m1d); trans=pt_old(H,L,n,tP,tbar); tr_ix=[t for(t,_)in trans]; tr_md=[m for(_,m)in trans]
        def abr8(bar):
            a=max(0,bar-7); return float(rng[a:bar+1].mean()) if bar>=a else float(rng[:bar+1].mean())
        for (fb,sb,dr,cnt,trig) in detect_entries_causal(g,tP,tbar):
            if cnt!=2: continue
            short=dr=="S"; want="BEAR" if short else "BULL"
            a=np.searchsorted(tbar,fb,"left"); zz=np.searchsorted(tbar,fb,"right")
            hit=np.nonzero(tP[a:zz]<=trig)[0] if short else np.nonzero(tP[a:zz]>=trig)[0]
            if not len(hit): continue
            jf=a+int(hit[0]); reg=tr_md[bisect_right(tr_ix,jf)-1]
            # ---- 2E retest fill (both dirs, ALL regimes) ----
            lim=trig+6*TICK if short else trig-6*TICK; s0=tP[jf:]
            jl=np.nonzero(s0>lim)[0] if short else np.nonzero(s0<lim)[0]
            if len(jl):
                jfl=jf+int(jl[0]); fb2=int(tbar[jfl])
                if fb2-fb<=6 and int(pd.Timestamp(g_dt[min(fb2,n-1)]).hour) in GOOD:
                    A=abr8(fb2); abrs.append(A); seg=tP[jfl:]
                    grp=[("2E_all",dr),("2E_"+reg,dr)]+([("2E_WT",dr)] if reg==want else [])
                    for sa in STOPS:
                        sp=sa*A
                        for tg in TGTS:
                            net=exit_net(seg,lim,short,sp,(None if tg in (None,"trail") else tg*A),tg=="trail")
                            for gk in grp: acc((gk[0],gk[1],sa,tg),net)
            # ---- FADE fill (f2EL short / f2ES long) ----
            if reg!=want:
                fs=not short; need="BEAR" if fs else "BULL"
                if reg==need:
                    sb_ext=L[sb] if fs else H[sb]; fail=sb_ext-TICK if fs else sb_ext+TICK
                    zlim=np.searchsorted(tbar,fb+KFADE+1,"left"); segf=tP[jf:zlim]
                    w=np.nonzero(segf<=fail)[0] if fs else np.nonzero(segf>=fail)[0]
                    if len(w):
                        jx=jf+int(w[0]); fb2=int(tbar[min(jx,len(tbar)-1)])
                        if int(pd.Timestamp(g_dt[min(fb2,n-1)]).hour) in GOOD:
                            fill=fail-TICK if fs else fail+TICK; A=abr8(fb2); seg=tP[jx:]
                            fdr="S" if fs else "L"
                            for sa in STOPS:
                                sp=sa*A
                                for tg in TGTS:
                                    net=exit_net(seg,fill,fs,sp,(None if tg in (None,"trail") else tg*A),tg=="trail")
                                    acc(("fade",fdr,sa,tg),net)
        del tP,tbar; gc.collect()
        if (di+1)%300==0: print(f"[{di+1}/{len(days)}] {time.time()-t0:.0f}s",flush=True)
    yrs=5.5; out=[]
    def colhdr(t): return "EOD" if t is None else ("TRAIL" if t=="trail" else f"{t:g}A")
    def grid(gk,dr,title):
        anyv=[rows.get((gk,dr,sa,tg),[]) for sa in STOPS for tg in TGTS]
        nn=max((len(x) for x in anyv),default=0)
        if not nn: return
        print(f"\n===== {title}  (n~{len(rows.get((gk,dr,STOPS[0],TGTS[0]),[]))}) =====")
        print("stop\\tgt " + "".join(f"{colhdr(t):>12}" for t in TGTS))
        for sa in STOPS:
            cells=[]
            for tg in TGTS:
                v=rows.get((gk,dr,sa,tg),[])
                if v:
                    va=np.asarray(v,float); cells.append(f"{pf(va):.2f}/{va.sum()/yrs:+5.0f}")
                    out.append({"group":gk,"dir":dr,"stop_abr":sa,"tgt":colhdr(tg),"n":len(v),"pf":pf(va),"net":va.sum(),"per_yr":va.sum()/yrs})
                else: cells.append("-")
            print(f"{sa:>6}A " + "".join(f"{c:>12}" for c in cells))
    print(f"\nABR8 median {np.median(abrs):.1f}pt (${np.median(abrs)*50:.0f})  mean {np.mean(abrs):.1f}pt   [cells = PF / $per-yr]")
    for gk,ti in [("2E_WT","2E WITH-TREND"),("2E_all","2E ALL REGIMES"),("2E_BULL","2E in BULL"),("2E_BEAR","2E in BEAR"),("2E_NEUTRAL","2E in NEUTRAL")]:
        for dr in ("L","S"): grid(gk,dr,f"{ti} {dr}")
    for dr,nm in (("S","f2EL fade-short"),("L","f2ES fade-long")): grid("fade",dr,nm)
    pd.DataFrame(out).to_csv(WT/"data"/"regime"/"abr8_sweep_20260727.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  saved data/regime/abr8_sweep_20260727.csv")


if __name__=="__main__": main()
