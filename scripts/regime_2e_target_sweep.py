"""TARGET sweep on the frozen 2E book (2021+), exact via mfe_bstop from target_emit.
For target T (pts or xADR): net = +T if mfe_bstop>=T (target hit before stop), else -S if
stopped, else eod_move. S=0.30xADR fixed. Gates = frozen (WT, 09-13, entry>SMA20, skip ON,
gap<=0.54). Compares fixed-pt and R-multiple and xADR targets vs EOD hold. Per side + train/test.
  python scripts/regime_2e_target_sweep.py
"""
import numpy as np, pandas as pd
from pathlib import Path
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK
L=[]
def out(s=""): L.append(s); print(s)
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(df):
    e=df.sort_values("Date").net.cumsum().values; return float((e-np.maximum.accumulate(e)).min())
def sharpe(df):
    dl=df.groupby("Date").net.sum(); return dl.mean()/dl.std()*np.sqrt(252) if dl.std()>0 else 0

d=pd.read_csv(WT/"data"/"regime"/"target_emit_20260727.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),Lo=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.Lo).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.Lo)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
d=d[(d.yr>=2021)&(d.entry_px>d.sma20)&(~d.skip_after)&(d.gap<=0.54)].copy()
d["S"]=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR)

def netT(df,T):
    """T in pts (scalar) or None=EOD. target hit iff mfe_bstop>=T."""
    if T is None:
        base=np.where(df.mae_pts.values>=df.S.values,-df.S.values,df.eod_move.values)
    else:
        stop_out=np.where(df.stopped.values,-df.S.values,df.eod_move.values)
        base=np.where(df.mfe_bstop.values>=T,T,stop_out)
    return base*PT-COMM-SLIP

def row(df,lbl,T):
    x=df.copy(); x["net"]=netT(df,T)
    tr=x[x.yr<=2023]; te=x[x.yr>=2024]
    out(f"  {lbl:16s} n={len(x):4d} net ${x.net.sum():+8,.0f} PF {pf(x.net):4.2f} win {100*(x.net>0).mean():4.1f}% "
        f"DD ${mdd(x):+8,.0f} Shp {sharpe(x):4.2f} | tr {pf(tr.net):.2f} te {pf(te.net):.2f}")

out("="*92); out("TARGET SWEEP — frozen book 2021+ (0.30xADR stop, skip ON, gap<=0.54, WT, 09-13)"); out("="*92)
out(f"loaded {len(d)} book trades (median ADR {d.adr.median():.1f}, median stop {d.S.median():.1f}pt)")

out("\n### Fixed-point targets (both sides) ###")
row(d,"EOD (no target)",None)
for T in [4,6,8,10,12,16,20,24,30]:
    row(d,f"target {T}pt",T)

out("\n### xADR targets (both sides) ###")
for k in [0.15,0.20,0.30,0.40,0.50,0.75,1.00]:
    x=d.copy(); x["net"]=np.where(x.mfe_bstop.values>=k*x.adr.values, k*x.adr.values,
                                  np.where(x.stopped.values,-x.S.values,x.eod_move.values))*PT-COMM-SLIP
    tr=x[x.yr<=2023]; te=x[x.yr>=2024]
    out(f"  {k:.2f}xADR target n={len(x):4d} net ${x.net.sum():+8,.0f} PF {pf(x.net):4.2f} win {100*(x.net>0).mean():4.1f}% "
        f"DD ${mdd(x):+8,.0f} Shp {sharpe(x):4.2f} | tr {pf(tr.net):.2f} te {pf(te.net):.2f}")

for side,lbl in [("L","2EL"),("S","2ES")]:
    out(f"\n### {lbl} only — fixed-pt targets ###")
    ds=d[d.dir==side]
    row(ds,"EOD",None)
    for T in [6,10,16,24]:
        row(ds,f"target {T}pt",T)

(WT/"data"/"regime"/"target_sweep_20260727.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: data/regime/target_sweep_20260727.txt")
