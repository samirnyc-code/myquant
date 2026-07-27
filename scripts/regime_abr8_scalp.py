"""ABR8 REVERSION SCALP test (Samir, 2026-07-27): is there a scalp around ABR8? Theory-consistent
angle = mean-reversion in positive gamma (above SMA20_D). Signal: a 5m bar closes >= k*ABR8 away
from the 5m EMA20 -> FADE back toward the EMA. Target = EMA (revert) or a fraction of ABR8; stop =
s*ABR8; time-stop = T bars; 09-13 only. Reports GROSS (frictionless, directional edge only) and NET
($5 RT + 12.5 slip) so we see if anything survives costs. Databento proxy 2021+.

  python scripts/regime_abr8_scalp.py [--limit N]
Output: data/regime/abr8_scalp_YYYYMMDD.csv + stdout grid (gross PF / net PF / net $per-yr / win%).
"""
import sys, gc, time
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_2e_tickproxy_fidelity import proxy_ticks
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
GOOD={9,10,11,12,13}
KS=[0.8,1.0,1.5]                 # stretch trigger: |close-ema| >= k*ABR8
STOPS=[1.0,1.5,2.5]              # stop = s*ABR8 beyond entry
TGTS=["ema",0.5,1.0]            # target: revert to EMA, or f*ABR8 toward EMA
TSTOP=8                          # bars time-stop


def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return round(gp/gl,2) if gl else 0.0


def main():
    limit=int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else None
    b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    b=b.sort_values("DateTime").reset_index(drop=True); b["ema20i"]=b["Close"].ewm(span=20,adjust=False).mean()
    m1=pd.read_parquet(DATA/"bars"/"_db_es_1m_rth.parquet"); m1["DateTime"]=pd.to_datetime(m1["DateTime"]); m1["Date"]=m1.DateTime.dt.date.astype(str)
    m1g={d:x.sort_values("DateTime").reset_index(drop=True) for d,x in m1.groupby("Date")}
    dly=b.groupby("Date").agg(dC=("Close","last")).reset_index().sort_values("Date")
    dly["sma20"]=dly.dC.rolling(20).mean().shift(1); sma=dly.set_index("Date")["sma20"]
    days=[d for d in sorted(b.Date.unique()) if d>="2021-01-01"]
    if limit: days=days[:limit]
    rows={}; abrs=[]
    def acc(k,g,n): rows.setdefault(k,[[],[]]); rows[k][0].append(g); rows[k][1].append(n)
    t0=time.time()
    for di,dstr in enumerate(days):
        if dstr not in m1g or dstr not in sma.index or not np.isfinite(sma[dstr]): continue
        smaD=sma[dstr]
        g=b[b.Date==dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g)<25: continue
        m1d=m1g[dstr]; m1d=m1d[m1d.DateTime>=g.DateTime.values[0]]
        if len(m1d)<25: continue
        H,L,C=g.High.values,g.Low.values,g.Close.values; E=g.ema20i.values; n=len(g); g_dt=g.DateTime.values; rng=H-L
        tP,tbar=proxy_ticks(g,m1d)
        for i in range(8,n-1):
            if int(pd.Timestamp(g_dt[i]).hour) not in GOOD: continue
            if not (C[i]>smaD): continue            # positive-gamma (above SMA20_D) only
            A=float(rng[max(0,i-7):i+1].mean())
            if A<=0: continue
            dev=C[i]-E[i]
            for k in KS:
                if abs(dev)<k*A: continue
                short = dev>0                          # stretched ABOVE ema -> fade short
                ei=i+1; a=np.searchsorted(tbar,ei,"left")
                if a>=len(tP): continue
                fill=tP[a]                             # next-bar entry at market
                seg=tP[a:]; segbar=tbar[a:]
                # time-stop cutoff index
                tcut=np.searchsorted(segbar,ei+TSTOP,"left"); tcut=tcut if tcut>0 else len(seg)
                for s in STOPS:
                    stop=fill+s*A if short else fill-s*A
                    for tg in TGTS:
                        tgt = E[i] if tg=="ema" else (fill-tg*A if short else fill+tg*A)
                        sseg=seg[:tcut]
                        js=np.nonzero(sseg>=stop)[0] if short else np.nonzero(sseg<=stop)[0]; si=js[0] if len(js) else np.inf
                        jt=np.nonzero(sseg<=tgt)[0] if short else np.nonzero(sseg>=tgt)[0]; ti=jt[0] if len(jt) else np.inf
                        if si==np.inf and ti==np.inf: ex=sseg[-1]
                        elif ti<=si: ex=tgt
                        else: ex=stop
                        move=((fill-ex) if short else (ex-fill))*PT
                        acc((k,s,tg),move,move-COMM-SLIP)
                        abrs.append(A)
        del tP,tbar; gc.collect()
        if (di+1)%300==0: print(f"[{di+1}/{len(days)}] {time.time()-t0:.0f}s",flush=True)
    yrs=5.5; out=[]
    print(f"\nABR8 median {np.median(abrs):.1f}pt.  REVERSION SCALP (fade EMA stretch, above SMA20_D, time-stop {TSTOP} bars)")
    print(f"{'k*ABR trig':>10}{'stop':>7}{'tgt':>6}{'n':>7}{'grossPF':>9}{'netPF':>7}{'net $/yr':>11}{'win%':>6}")
    for k in KS:
        for s in STOPS:
            for tg in TGTS:
                key=(k,s,tg)
                if key not in rows: continue
                gpnl=np.array(rows[key][0]); npnl=np.array(rows[key][1])
                out.append({"k":k,"stop":s,"tgt":tg,"n":len(npnl),"gross_pf":pf(gpnl),"net_pf":pf(npnl),"net_per_yr":npnl.sum()/yrs,"win":100*(npnl>0).mean()})
                print(f"{k:>10}{s:>7}{str(tg):>6}{len(npnl):>7}{pf(gpnl):>9.2f}{pf(npnl):>7.2f}{npnl.sum()/yrs:>+11,.0f}{100*(npnl>0).mean():>6.0f}")
    pd.DataFrame(out).to_csv(WT/"data"/"regime"/"abr8_scalp_20260727.csv",index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  saved data/regime/abr8_scalp_20260727.csv")


if __name__=="__main__": main()
