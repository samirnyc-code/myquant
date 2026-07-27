"""Full-metric tables for RevFT-extreme (correct spec). All metrics per cut/exit:
n, win%, PF, net, $/yr, avgWin, avgLoss, payoff, expectancy, maxDD, return/DD.
  python scripts/regime_revft_tables.py   -> prints tables + saves data/regime/revft_tables_20260727.csv
"""
from pathlib import Path
import numpy as np, pandas as pd
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date")["Close"].last().reset_index().sort_values("Date"); g["sma20d"]=g["Close"].rolling(20).mean().shift(1)
d=d.merge(g[["Date","sma20d"]],on="Date",how="left").dropna(subset=["sma20d"]); d["above"]=d.entry>d.sma20d
yrs=(pd.to_datetime(d.Date).max()-pd.to_datetime(d.Date).min()).days/365.25
def M(x,ex):
    v=x[ex].values.astype(float)
    if not len(v): return None
    w=v[v>0]; l=v[v<0]; gp=w.sum(); gl=-l.sum()
    e=x.sort_values("Date")[ex].cumsum().values; dd=float((e-np.maximum.accumulate(e)).min())
    py=v.sum()/yrs
    return dict(n=len(v),win=100*(v>0).mean(),PF=(gp/gl if gl else np.inf),net=v.sum(),per_yr=py,
                avgW=(w.mean() if len(w) else 0),avgL=(l.mean() if len(l) else 0),
                payoff=(abs(w.mean()/l.mean()) if len(l) and len(w) else 0),exp=v.mean(),mdd=dd,
                rdd=(py/abs(dd) if dd else 0))
def tbl(title,cuts,ex):
    print(f"\n### {title}  (exit {ex.split('_')[1]})")
    print(f"{'cut':<26}{'n':>5}{'win%':>6}{'PF':>6}{'net':>10}{'$/yr':>9}{'avgW':>7}{'avgL':>7}{'payoff':>7}{'exp':>6}{'maxDD':>9}{'ret/DD':>7}")
    for name,x in cuts:
        m=M(x,ex)
        if not m: continue
        print(f"{name:<26}{m['n']:>5}{m['win']:>6.0f}{m['PF']:>6.2f}{m['net']:>+10,.0f}{m['per_yr']:>+9,.0f}{m['avgW']:>+7.0f}{m['avgL']:>+7.0f}{m['payoff']:>7.2f}{m['exp']:>+6.0f}{m['mdd']:>+9,.0f}{m['rdd']:>7.2f}")
        rows.append(dict(table=title,exit=ex.split('_')[1],cut=name,**m))
rows=[]
NEUT=d.reg=="NEUTRAL"
bytype=[(t,d[d.type==t]) for t in ["BO","Sneaky","IB","OB","Trap"]]
sleeves=[("A NEUT-only",d[NEUT]),("B drop OB + Trap-only-NEUT",d[(d.type!='OB')&~((d.type=='Trap')&~NEUT)]),
         ("C BO+Sneaky+IB",d[d.type.isin(['BO','Sneaky','IB'])]),("D NEUT + not-OB",d[NEUT&(d.type!='OB')]),
         ("E <SMA20 + not-OB",d[(~d.above)&(d.type!='OB')]),("RAW all",d)]
for ex in ("net_eod","net_2R","net_3R"):
    tbl("BY REVTYPE",bytype,ex)
for ex in ("net_eod","net_2R","net_3R"):
    tbl("CANDIDATE SLEEVES",sleeves,ex)
# revtype x regime (EOD)
rr=[]
for t in ["BO","Sneaky","IB","OB","Trap"]:
    for lbl,mask in [(">SMA20",d.above),("<SMA20",~d.above),("BULL",d.reg=="BULL"),("BEAR",d.reg=="BEAR"),("NEUT",NEUT)]:
        rr.append((f"{t} {lbl}", d[(d.type==t)&mask]))
tbl("REVTYPE x REGIME",rr,"net_eod")
pd.DataFrame(rows).to_csv(WT/"data"/"regime"/"revft_tables_20260727.csv",index=False)
print(f"\nspan {yrs:.1f}yr. saved data/regime/revft_tables_20260727.csv")
