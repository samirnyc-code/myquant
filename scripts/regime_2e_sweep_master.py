"""MASTER SWEEP — 2E book, EOD exit, all in-memory from oos_pertrade_full (mae/eod let any
stop + gate be re-derived exactly, no look-ahead). Now that skip_after is FIXED (astype bool),
sweep: STOP mult x GAP threshold x skip_after on/off x SMA gate, both sides + per side, with
per-year + train(2021-23)/test(2024-26) stability. EOD hold only (targets are a separate engine
re-run — see regime_2e_target_sweep.py).

  python scripts/regime_2e_sweep_master.py
Outputs: data/regime/sweep_master_20260727.txt (+ stdout)
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
def netcol(d, mult):
    S=np.maximum(np.round(mult*d.adr.values/TICK)*TICK,FLOOR)
    return np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP

# --- load per-trade + daily gate (same source as canonical book_metrics) ---
d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),Lo=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.Lo).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.Lo)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
d=d[d.yr>=2021].copy()
d["above"]=d.entry_px>d.sma20

def book(df, mult=0.30, gap=None, use_skip=True, use_sma=True, side=None):
    x=df
    if use_sma: x=x[x.above]
    if use_skip: x=x[~x.skip_after]
    if gap is not None: x=x[x.gap<=gap]
    if side: x=x[x.dir==side]
    x=x.copy(); x["net"]=netcol(x,mult); return x
def line(tag, x):
    if not len(x): out(f"  {tag:34s} n=0"); return
    tr=x[x.yr<=2023]; te=x[x.yr>=2024]
    out(f"  {tag:34s} n={len(x):4d}  net ${x.net.sum():+8,.0f}  PF {pf(x.net):4.2f}  "
        f"DD ${mdd(x):+8,.0f}  Shp {sharpe(x):4.2f}  | tr PF {pf(tr.net):4.2f} te PF {pf(te.net):4.2f}")

out("="*96); out("2E BOOK MASTER SWEEP (2021+, EOD hold, skip_after FIXED)  — base: WT, 09-13, entry>SMA20"); out("="*96)

out("\n### A. BASELINE frozen book (0.30xADR, skip ON, NO gap filter) ###")
line("frozen (both sides)", book(d))
line("  2EL", book(d,side="L")); line("  2ES", book(d,side="S"))

out("\n### B. STOP-MULT sweep (skip ON, no gap filter, both sides) ###")
for m in [0.15,0.20,0.25,0.30,0.35,0.40,0.50,0.60]:
    line(f"stop {m:.2f}xADR", book(d,mult=m))

out("\n### C. GAP-THRESHOLD sweep (0.30xADR, skip ON, both sides) — skip days with |gap|% > thr ###")
line("no gap filter", book(d))
for thr in [1.50,1.00,0.75,0.54,0.40,0.30,0.20]:
    line(f"gap <= {thr:.2f}%", book(d,gap=thr))

out("\n### D. GAP sweep PER SIDE (0.30xADR, skip ON) ###")
for side,lbl in [("L","2EL"),("S","2ES")]:
    out(f"  -- {lbl} --")
    line(f"    no gap filter", book(d,side=side))
    for thr in [0.75,0.54,0.40,0.30]:
        line(f"    gap<={thr:.2f}", book(d,gap=thr,side=side))

out("\n### E. FILTER ISOLATION (0.30xADR, both sides) ###")
line("no skip, no sma, no gap (raw WT)", book(d,use_skip=False,use_sma=False))
line("sma only", book(d,use_skip=False))
line("sma + skip (=frozen)", book(d))
line("sma + skip + gap0.54", book(d,gap=0.54))
line("sma + skip + gap0.40", book(d,gap=0.40))
line("skip only (no sma)", book(d,use_sma=False))

out("\n### F. 2D STOP x GAP (both sides, skip ON) — PF | net$k | DD$k ###")
gaps=[None,0.75,0.54,0.40]; mults=[0.20,0.25,0.30,0.35,0.40]
hdr="  stop\\gap  " + "".join(f"{'none' if gp is None else f'{gp:.2f}':>16}" for gp in gaps); out(hdr)
for m in mults:
    row=f"  {m:.2f}xADR  "
    for gp in gaps:
        x=book(d,mult=m,gap=gp); row+=f"  PF{pf(x.net):4.2f} {x.net.sum()/1000:+5.1f}k {mdd(x)/1000:+5.1f}k"
    out(row)

(WT/"data"/"regime"/"sweep_master_20260727.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: data/regime/sweep_master_20260727.txt")
