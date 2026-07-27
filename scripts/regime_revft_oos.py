"""OOS split (TRAIN 2021-23 / TEST 2024-26) for RevFT-extreme candidate cuts. Shows the narrow
BO<SMA20 NEUT pocket FAILS in-sample (PF 0.91) and only works 2024-26 -> curve-fit; the broad
sleeves hold in both halves but lean on the modern regime.
  python scripts/regime_revft_oos.py
"""
from pathlib import Path
import numpy as np, pandas as pd
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date")["Close"].last().reset_index().sort_values("Date"); g["sma20d"]=g["Close"].rolling(20).mean().shift(1)
d=d.merge(g[["Date","sma20d"]],on="Date",how="left").dropna(subset=["sma20d"]); d["above"]=d.entry>d.sma20d
NEUT=d.reg=="NEUTRAL"
def line(x,ex,yr):
    v=x[ex].values.astype(float)
    if not len(v): return "(none)"
    w=v[v>0];l=v[v<0];gp=w.sum();gl=-l.sum()
    return f"n={len(v):4d} win{100*(v>0).mean():3.0f}% PF {(gp/gl if gl else 99):5.2f} net ${v.sum():+8,.0f} (${v.sum()/yr:+7,.0f}/yr)"
cuts=[("BO <SMA20 NEUT", d[(d.type=='BO')&(~d.above)&NEUT]),
      ("BO <SMA20 (NEUT+BULL)", d[(d.type=='BO')&(~d.above)&(d.reg!='BEAR')]),
      ("B drop-OB+Trap-NEUT", d[(d.type!='OB')&~((d.type=='Trap')&~NEUT)]),
      ("C BO+Sneaky+IB", d[d.type.isin(['BO','Sneaky','IB'])]),
      ("E <SMA20 not-OB", d[(~d.above)&(d.type!='OB')])]
for ex in ("net_eod","net_3R"):
    print(f"\n=== OOS split, exit {ex.split('_')[1]}  (TRAIN 2021-23 | TEST 2024-26) ===")
    for name,x in cuts:
        print(f"  {name:<24} TRAIN {line(x[x.yr<=2023],ex,3.0)}")
        print(f"  {'':<24} TEST  {line(x[x.yr>=2024],ex,2.5)}")
if __name__=="__main__": pass
