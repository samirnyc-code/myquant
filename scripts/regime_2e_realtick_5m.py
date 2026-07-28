"""REAL-TICK sim of the v1.1 2E book — 5-min bars built from the REAL continuous tick cache,
stop/EOD decided by the REAL intraday min/max after entry (no Databento 1m pseudo-ticks
anywhere). Same audited engine (phase_transitions + detect_entries_causal). Answers: do the
proxy-based PF 1.54 (no gap) / 1.64 (gap<=0.54) hold on real ticks?

Daily SMA20/ADR10/skip_after/gap from the tick daily OHLC (same price base as the bars).
  python scripts/regime_2e_realtick_5m.py
Output: data/regime/realtick5m_2e_pertrade_20260728.csv + _metrics.txt
"""
import sys, glob, os, time
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK; GOOD={"09","10","11","12","13"}
WT=Path(__file__).resolve().parent.parent; MAIN=Path(r"C:/Users/Admin/myquant/data"); TDIR=MAIN/"ticks_continuous"
sys.path.insert(0,str(WT/"scripts"))
from regime_second_entry_study import phase_transitions as ptf
from regime_2e_causal_check import detect_entries_causal

def build_5m(tk):
    """5-min RTH OHLC bars from ticks + per-tick bar index (real path). pandas floor('5min')
    — numpy astype('datetime64[5m]') does NOT floor to 5-min (it mangles the timestamps)."""
    bucket=tk["DateTime"].dt.floor("5min")
    codes,ub=pd.factorize(bucket,sort=True)               # codes = bar idx per tick (monotonic), ub = bucket times
    p=tk["Price"].values
    df=pd.DataFrame({"b":codes,"p":p}); grp=df.groupby("b",sort=True)["p"]
    bars=pd.DataFrame({"DateTime":pd.DatetimeIndex(ub),"Open":grp.first().values,
                       "High":grp.max().values,"Low":grp.min().values,"Close":grp.last().values})
    return bars, p, codes.astype(np.int64)

def emit_day(g,tP,tbar,adr):
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
        seg=tP[jfl:]                                       # REAL ticks fill->EOD
        mae_pts=float(lim-seg.min()) if not short else float(seg.max()-lim)   # real intraday extreme
        eod_move=float(seg[-1]-lim) if not short else float(lim-seg[-1])
        rows.append({"dir":dr,"regime":reg,"with_trend":reg==want,"adr":round(float(adr),2),
                     "mae_pts":round(mae_pts,2),"eod_move":round(eod_move,2),
                     "fill_hour":pd.Timestamp(g_dt[min(fb2,n-1)]).strftime("%H"),"entry_px":round(float(lim),2)})
    return rows

def daily_stats(days):
    rec=[]
    for d in days:
        p=pd.read_parquet(TDIR/f"{d}.parquet",columns=["Price"])["Price"].to_numpy()
        rec.append((d,p[0],p.max(),p.min(),p[-1]))
    g=pd.DataFrame(rec,columns=["Date","dO","dH","dL","dC"]).sort_values("Date")
    g["sma20"]=g.dC.rolling(20).mean().shift(1); g["adr10"]=(g.dH-g.dL).rolling(10).mean().shift(1)
    g["skip_after"]=((g.dH-g.dL)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
    g["gap"]=((g.dO-g.dC.shift(1))/g.dC.shift(1)*100).abs()
    return g.set_index("Date")

def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(df):
    e=df.sort_values("Date").net.cumsum().values; return float((e-np.maximum.accumulate(e)).min())
def sharpe(df):
    dl=df.groupby("Date").net.sum(); return dl.mean()/dl.std()*np.sqrt(252) if dl.std()>0 else 0

def main():
    days=[os.path.basename(f)[:10] for f in sorted(glob.glob(str(TDIR/"*.parquet")))]
    ds=daily_stats(days); rows=[]; t0=time.time()
    for i,d in enumerate(days):
        if d not in ds.index: continue
        adr=ds.loc[d,"adr10"]
        if not np.isfinite(adr): continue
        tk=pd.read_parquet(TDIR/f"{d}.parquet").sort_values("DateTime").reset_index(drop=True)
        if len(tk)<1000: continue
        g,tP,tbar=build_5m(tk)
        if len(g)<30: continue
        try:
            for r in emit_day(g,tP,tbar,adr):
                r.update({"Date":d,"yr":int(d[:4]),"gap":round(float(ds.loc[d,"gap"]),3)}); rows.append(r)
        except Exception as e:
            print(d,"ERR",repr(e),flush=True)
        if (i+1)%150==0: print(f"[{i+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)",flush=True)
    d=pd.DataFrame(rows).merge(ds[["sma20","skip_after"]],left_on="Date",right_index=True,how="left").dropna(subset=["sma20"])
    S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR); d["net"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
    d.to_csv(WT/"data"/"regime"/"realtick5m_2e_pertrade_20260728.csv",index=False)
    base=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13}) & (d.entry_px>d.sma20) & (~d.skip_after)]
    L=[]
    def out(s=""): L.append(s); print(s)
    for lbl,x in [("v1.1 (no gap)",base),("v1.1 + gap<=0.54",base[base.gap<=0.54])]:
        x21=x[x.yr>=2021]; tr=x21[x21.yr<=2023]; te=x21[x21.yr>=2024]
        out(f"\n=== REAL-TICK 5M  {lbl}  (2021+) ===")
        out(f"  n={len(x21)}  net ${x21.net.sum():+,.0f}  PF {pf(x21.net):.2f}  win {100*(x21.net>0).mean():.1f}%  "
            f"maxDD ${mdd(x21):+,.0f}  Sharpe {sharpe(x21):.2f}  | train PF {pf(tr.net):.2f} / test PF {pf(te.net):.2f}")
        Ls=x21[x21.dir=='L']; Ss=x21[x21.dir=='S']
        out(f"  2EL n={len(Ls)} PF {pf(Ls.net):.2f} ${Ls.net.sum():+,.0f}   2ES n={len(Ss)} PF {pf(Ss.net):.2f} ${Ss.net.sum():+,.0f}")
    out("\n-- proxy (Databento 1m) ref: v1.1 PF 1.54 / +$82.3k / DD -$10.2k ; +gap PF 1.64 / +$78.6k / DD -$7.1k --")
    (WT/"data"/"regime"/"realtick5m_2e_metrics_20260728.txt").write_text("\n".join(L),encoding="utf-8")
    print(f"\nDONE {time.time()-t0:.0f}s")

if __name__=="__main__": main()
