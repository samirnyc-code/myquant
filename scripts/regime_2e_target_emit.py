"""Emit per-trade MFE-before-stop so TARGET sweeps are exact in-memory. Re-runs the frozen
2E engine (Databento 5M + 1m pseudo-ticks, same as oos_pertrade) with stop S=0.30xADR fixed,
and for each filled 2E entry records: mae_pts, eod_move, and mfe_bstop = max favorable
excursion over [fill .. stop-or-EOD]. Then a target T hits-before-stop iff mfe_bstop>=T, so
net(T) = +T (target), else -S (stopped) or eod_move (EOD). Plus gate metadata (gap, entry_px,
with_trend, dir, regime, adr).  python scripts/regime_2e_target_emit.py
Output: data/regime/target_emit_20260727.csv
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK; GOOD={"09","10","11","12","13"}
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0,str(WT/"scripts"))
from regime_second_entry_study import phase_transitions as ptf
from regime_2e_causal_check import detect_entries_causal
from regime_2e_tickproxy_fidelity import proxy_ticks
M5=DATA/"bars"/"_db_es_5m_rth.parquet"; M1=DATA/"bars"/"_db_es_1m_rth.parquet"

def emit_day(g,tP,tbar,adr,dstr):
    H,L=g["High"].values,g["Low"].values; n=len(g)
    trans=ptf(H,L,n,tP,tbar); tr_ix=[t for (t,_) in trans]; tr_md=[m for (_,m) in trans]
    entries=detect_entries_causal(g,tP,tbar); g_dt=g["DateTime"].values
    wide=max(round(0.30*adr/TICK)*TICK,FLOOR); rows=[]
    for (fb,sb,dr,cnt,trig) in entries:
        if cnt!=2: continue
        short=dr=="S"; want="BEAR" if short else "BULL"
        a=np.searchsorted(tbar,fb,"left"); z=np.searchsorted(tbar,fb,"right")
        hit=np.nonzero(tP[a:z]<=trig)[0] if short else np.nonzero(tP[a:z]>=trig)[0]
        if not len(hit): continue
        jf=a+int(hit[0]); reg=tr_md[bisect_right(tr_ix,jf)-1]
        lim=trig+6*TICK if short else trig-6*TICK; s0=tP[jf:]
        jl=np.nonzero(s0>lim)[0] if short else np.nonzero(s0<lim)[0]
        if not len(jl): continue
        jfl=jf+int(jl[0]); fb2=int(tbar[jfl])
        if fb2-fb>6: continue
        if pd.Timestamp(g_dt[min(fb2,n-1)]).strftime("%H") not in GOOD: continue
        stop=lim+wide if short else lim-wide; seg=tP[jfl:]
        js=np.nonzero(seg>=stop)[0] if short else np.nonzero(seg<=stop)[0]
        stop_i=int(js[0]) if len(js) else len(seg)-1
        # favorable-signed path over [fill..stop-or-EOD]; mfe before stop
        fav = (lim-seg[:stop_i+1]) if short else (seg[:stop_i+1]-lim)
        mfe_bstop=float(fav.max()) if len(fav) else 0.0
        mae_pts=float(lim-seg.min()) if not short else float(seg.max()-lim)
        eod_move=float(seg[-1]-lim) if not short else float(lim-seg[-1])
        rows.append({"Date":dstr,"yr":int(dstr[:4]),"dir":dr,"regime":reg,"with_trend":reg==want,
                     "adr":round(float(adr),2),"entry_px":round(float(lim),2),
                     "mae_pts":round(mae_pts,2),"eod_move":round(eod_move,2),
                     "mfe_bstop":round(mfe_bstop,2),"stopped":bool(len(js)),
                     "fill_hour":pd.Timestamp(g_dt[min(fb2,n-1)]).strftime("%H")})
    return rows

def main():
    b=pd.read_parquet(M5); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b["DateTime"].dt.date.astype(str)
    m1=pd.read_parquet(M1); m1["DateTime"]=pd.to_datetime(m1["DateTime"]); m1["Date"]=m1["DateTime"].dt.date.astype(str)
    m1g={d:x.sort_values("DateTime").reset_index(drop=True) for d,x in m1.groupby("Date")}
    dly=b.groupby("Date").agg(dO=("Open","first"),dC=("Close","last"),dH=("High","max"),dL=("Low","min")).reset_index()
    dly["adr10"]=(dly.dH-dly.dL).rolling(10).mean().shift(1)
    dly["gap"]=((dly.dO-dly.dC.shift(1))/dly.dC.shift(1)*100).abs()
    gm=dly.set_index("Date")[["adr10","gap"]]
    days=sorted(b["Date"].unique()); rows=[]; t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g: continue
        adr,gapv=gm.loc[dstr,"adr10"],gm.loc[dstr,"gap"]
        if not np.isfinite(adr): continue
        g=b[b.Date==dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g)<30: continue
        m1day=m1g[dstr]; m1day=m1day[m1day.DateTime>=g["DateTime"].values[0]]
        if len(m1day)<30: continue
        try:
            tP,tbar=proxy_ticks(g,m1day)
            for r in emit_day(g,tP,tbar,adr,dstr):
                r["gap"]=round(float(gapv),3); rows.append(r)
        except Exception as e:
            print(dstr,"ERR",repr(e),flush=True)
        del g,m1day; gc.collect()
        if (di+1)%400==0: print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)",flush=True)
    pd.DataFrame(rows).to_csv(WT/"data"/"regime"/"target_emit_20260727.csv",index=False)
    print(f"DONE {time.time()-t0:.0f}s -> target_emit_20260727.csv ({len(rows)} trades)")

if __name__=="__main__": main()
