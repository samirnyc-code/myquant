"""LOSER SCAN — disciplined, adversarial. On the current 461-book (WT, SMA20, skip, gap<=0.54,
0.30xADR, EOD, 2021+), condition on CAUSAL pre-entry features and report EVERY cell with
train(21-23)/test(24-26) so fitted cells (good full-sample, one half bad) are visible. A filter
only counts if it removes a cohort that LOSES in BOTH halves. No cherry-picking.
  python scripts/regime_2e_loser_scan.py
Output: data/regime/loser_scan_20260727.txt
"""
import numpy as np, pandas as pd
from pathlib import Path
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK
L=[]
def out(s=""): L.append(s); print(s)
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')

d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),Lo=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.Lo).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.Lo)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
d=d[(d.yr>=2021)&(d.entry_px>d.sma20)&(~d.skip_after)&(d.gap<=0.54)].copy().reset_index(drop=True)
S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR); d["net"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
# derived causal features
d["nth"]=d.groupby("Date").cumcount()+1           # setup # of day (emit order = chrono)
d["first"]=d.nth==1
d["distSMA"]=(d.entry_px-d.sma20)/d.adr            # how far above SMA20, in ADR
d["adr_q"]=pd.qcut(d.adr,3,labels=["loVol","midVol","hiVol"])
d["vix_q"]=pd.qcut(d.vix_prev,3,labels=["loVIX","midVIX","hiVIX"])
d["dow"]=pd.to_datetime(d.Date).dt.day_name().str[:3]

def cell(mask,lbl):
    x=d[mask];
    if not len(x): out(f"    {lbl:22s} n=0"); return
    tr=x[x.yr<=2023].net; te=x[x.yr>=2024].net
    flag=" <-- LOSES both halves" if pf(tr)<1.0 and pf(te)<1.0 else (" <-- fitted?" if (pf(tr)<1.0)!=(pf(te)<1.0) else "")
    out(f"    {lbl:22s} n={len(x):4d} net ${x.net.sum():+7,.0f} PF {pf(x.net):4.2f} | tr {pf(tr):4.2f} te {pf(te):4.2f}{flag}")

out("BOOK: n={} net ${:+,.0f} PF {:.2f} | tr {:.2f} te {:.2f}".format(
    len(d),d.net.sum(),pf(d.net),pf(d[d.yr<=2023].net),pf(d[d.yr>=2024].net)))
out("Goal: find a cohort that LOSES in BOTH halves (removable). Cells flagged.\n")

out("[nth setup of day]");
for v in [1,2,3]: cell(d.nth==v,f"nth=={v}")
cell(d.nth>=2,"nth>=2 (non-first)")
out("\n[fill hour]");
for h in [9,10,11,12,13]: cell(d.fill_hour==h,f"hour {h}")
cell(d.fill_hour>=12,"hour>=12 (late)")
out("\n[vol regime (ADR tertile)]");
for q in ["loVol","midVol","hiVol"]: cell(d.adr_q==q,q)
out("\n[VIX_prev tertile]");
for q in ["loVIX","midVIX","hiVIX"]: cell(d.vix_q==q,q)
out("\n[distance above SMA20 (ADR units)]");
cell(d.distSMA<0.25,"<0.25 ADR (barely)"); cell((d.distSMA>=0.25)&(d.distSMA<0.75),"0.25-0.75"); cell(d.distSMA>=0.75,">=0.75 (extended)")
out("\n[gap sub-bucket (all <=0.54)]");
cell(d.gap<0.10,"gap<0.10"); cell((d.gap>=0.10)&(d.gap<0.30),"0.10-0.30"); cell(d.gap>=0.30,"0.30-0.54")
out("\n[day of week]");
for w in ["Mon","Tue","Wed","Thu","Fri"]: cell(d.dow==w,w)
out("\n[side x nth]");
for s in ["L","S"]:
    cell((d.dir==s)&(d.first),f"{s} first"); cell((d.dir==s)&(~d.first),f"{s} non-first")

# combos of interest that MIGHT be cleanly removable
out("\n[candidate removable combos]")
cell((d.fill_hour>=12)&(d.adr_q=="loVol"),"late & loVol")
cell(d.first&(d.dir=="S"),"first & short")
cell((d.distSMA<0.25),"barely-above SMA (dup)")

(WT/"data"/"regime"/"loser_scan_20260727.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: loser_scan_20260727.txt")
