"""RevFT extreme-filter DETAIL (n=8) — full metrics + per-trade dump for charting.
Massive 5M (_continuous.parquet) + real ticks (load_day). Filter: reversal bar + prior bar make the
8-bar extreme. Entry = first tick after signal bar; stop = signal StopPrice; exits EOD / 1R / 2R / 3R.
Full metrics per side (WT/CT/NEUT) + combined + per-year, and a per-trade CSV (for the chart gallery).

  python scripts/regime_revft_extreme_detail.py [--n 8] [--limit N]
Output: data/regime/revft_extreme_trades_20260727.csv  + stdout metrics.
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
N=int(sys.argv[sys.argv.index("--n")+1]) if "--n" in sys.argv else 8


def exit_detail(seg, segbar, entry, stop, short, tgt_R):
    risk=abs(entry-stop)
    js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]; si=js[0] if len(js) else np.inf
    if tgt_R is None:
        ix=(si if si<np.inf else len(seg)-1); ex=stop if si<np.inf else seg[-1]
    else:
        tgt=entry-tgt_R*risk if short else entry+tgt_R*risk
        jt=np.nonzero(seg<=tgt)[0] if short else np.nonzero(seg>=tgt)[0]; ti=jt[0] if len(jt) else np.inf
        if si==np.inf and ti==np.inf: ix=len(seg)-1; ex=seg[-1]
        elif ti<=si: ix=int(ti); ex=tgt
        else: ix=int(si); ex=stop
    net=((entry-ex) if short else (ex-entry))*PT-COMM-SLIP
    return round(net,1), round(float(ex),2), int(segbar[min(ix,len(segbar)-1)])


def main():
    limit=int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    s=pd.read_parquet(SIG); s["DateTime"]=pd.to_datetime(s["DateTime"]); s["Date"]=s.DateTime.dt.date.astype(str)
    b=pd.read_parquet(BARS); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    sdays=sorted(set(s.Date)&set(b.Date))
    if limit: sdays=sdays[:limit]
    recs=[]; t0=time.time()
    for di,dstr in enumerate(sdays):
        gd=load_day(b,dstr)
        if gd[0] is None: continue
        g,tP,tbar=gd; H,L=g.High.values,g.Low.values; nb=len(g)
        tmap={pd.Timestamp(t):i for i,t in enumerate(g.DateTime.values)}
        trans=pt_old(H,L,nb,tP,tbar); tr_ix=[t for(t,_)in trans]; tr_md=[m for(_,m)in trans]
        def regat(bar):
            z=int(np.searchsorted(tbar,bar,"right")); return tr_md[bisect_right(tr_ix,z-1)-1] if z else "NEUTRAL"
        for _,r in s[s.Date==dstr].iterrows():
            bi=tmap.get(pd.Timestamp(r.DateTime))
            if bi is None or bi<N or bi>=nb-1: continue
            short=r.Direction=="Short"
            ext=min(L[bi],L[bi-1]) if not short else max(H[bi],H[bi-1])
            lo=L[bi-N+1:bi+1].min(); hi=H[bi-N+1:bi+1].max()
            if not ((ext<=lo) if not short else (ext>=hi)): continue      # n-bar extreme filter
            reg=regat(bi)
            side="WT" if ((not short and reg=="BULL") or (short and reg=="BEAR")) else ("CT" if ((not short and reg=="BEAR") or (short and reg=="BULL")) else "NEUT")
            a=np.searchsorted(tbar,bi+1,"left")
            if a>=len(tP): continue
            entry=float(tP[a]); seg=tP[a:]; segbar=tbar[a:]; stop=float(r.StopPrice)
            if abs(entry-stop)<=0: continue
            rec={"Date":dstr,"yr":int(dstr[:4]),"sig_bar":bi,"entry_bar":int(bi+1),"dir":r.Direction,
                 "side":side,"type":r.SignalType,"entry":round(entry,2),"stop":round(stop,2),
                 "risk_pts":round(abs(entry-stop),2),"reg":reg}
            for tag,tr in [("eod",None),("1R",1.0),("2R",2.0),("3R",3.0)]:
                net,exx,exb=exit_detail(seg,segbar,entry,stop,short,tr)
                rec[f"net_{tag}"]=net; rec[f"expx_{tag}"]=exx; rec[f"exbar_{tag}"]=exb
            recs.append(rec)
        del tP,tbar; gc.collect()
        if (di+1)%250==0: print(f"[{di+1}/{len(sdays)}] {time.time()-t0:.0f}s",flush=True)
    d=pd.DataFrame(recs); d.to_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv",index=False)
    yrs=(pd.to_datetime(d.Date).max()-pd.to_datetime(d.Date).min()).days/365.25

    def pf(v):
        v=np.asarray(v,float);gp=v[v>0].sum();gl=-v[v<0].sum();return round(gp/gl,2) if gl else float('inf')
    def mdd(x):
        e=x.sort_values("Date")["net"].cumsum().values; return float((e-np.maximum.accumulate(e)).min()) if len(e) else 0
    def block(sub,exitcol,label):
        x=sub.rename(columns={exitcol:"net"}); v=x["net"].values
        if not len(v): print(f"  {label:<22} (none)"); return
        w=v[v>0]; l=v[v<0]
        print(f"  {label:<22} n={len(v):4d}  win {100*(v>0).mean():4.0f}%  PF {pf(v):5.2f}  net ${v.sum():+8,.0f}  ${v.sum()/yrs:+7,.0f}/yr  "
              f"avgW ${w.mean() if len(w) else 0:+6.0f}  avgL ${l.mean() if len(l) else 0:+6.0f}  payoff {abs(w.mean()/l.mean()) if len(l) and len(w) else 0:4.2f}  "
              f"exp ${v.mean():+5.0f}  DD ${mdd(x):+7,.0f}")

    print(f"\n===== RevFT n={N}-bar-extreme filter — FULL METRICS (Massive real ticks, {yrs:.1f}yr) =====")
    print(f"total filtered trades: {len(d)}  (~{len(d)/yrs:.0f}/yr)   fills across {len(sdays)} sig-days\n")
    for exitcol,exlab in [("net_eod","EOD hold"),("net_1R","target 1R"),("net_2R","target 2R"),("net_3R","target 3R")]:
        print(f"--- exit: {exlab} ---")
        for side in ("CT","NEUT","WT"):
            block(d[d.side==side],exitcol,side)
        block(d,exitcol,"ALL extreme")
        print()
    print("=== per-year (side=CT, exit 3R — the sleeve) ===")
    ct=d[d.side=="CT"].rename(columns={"net_3R":"net"})
    for y,x in ct.groupby("yr"):
        v=x["net"].values
        print(f"  {int(y)}: n={len(v):3d}  win {100*(v>0).mean():3.0f}%  PF {pf(v):5.2f}  net ${v.sum():+7,.0f}")
    print("\n=== by SignalType (side=CT, exit 3R) ===")
    for tp,x in ct.groupby("type"):
        v=x["net"].values; print(f"  {tp:<8} n={len(v):3d}  win {100*(v>0).mean():3.0f}%  PF {pf(v):5.2f}  net ${v.sum():+7,.0f}")
    print(f"\nsaved data/regime/revft_extreme_trades_20260727.csv ({len(d)} trades)  DONE {time.time()-t0:.0f}s")


if __name__=="__main__": main()
