"""RevFT-extreme breakdown by RevType x regime (SMA20_D AND the phase engine). Reads the per-trade
CSV (correct spec: BTCPrice entry, 3-bar/N-bar filter, fill-vs-stop race). Adds prior-day SMA20_D
(20-day SMA of daily closes on Massive _continuous) and splits net by RevType x {>SMA20 / <SMA20}
and RevType x {BULL/BEAR/NEUT phase regime}, for EOD/2R/3R. Flags positive cells (n>=25, PF>=1.1).
  python scripts/regime_revft_breakdown.py
"""
from pathlib import Path
import numpy as np, pandas as pd
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date")["Close"].last().reset_index().sort_values("Date")
g["sma20d"]=g["Close"].rolling(20).mean().shift(1)
d=d.merge(g[["Date","sma20d"]],on="Date",how="left").dropna(subset=["sma20d"])
d["smaside"]=np.where(d.entry>d.sma20d,">SMA20","<SMA20")
yrs=(pd.to_datetime(d.Date).max()-pd.to_datetime(d.Date).min()).days/365.25
def pf(v):
    v=np.asarray(v,float);gp=v[v>0].sum();gl=-v[v<0].sum();return round(gp/gl,2) if gl else 0.0
def line(lbl,x,ex):
    v=x[ex].values
    if len(v)<5: return None
    return f"    {lbl:<10} n={len(v):4d} win {100*(v>0).mean():3.0f}% PF {pf(v):5.2f} net ${v.sum():+8,.0f} (${v.sum()/yrs:+7,.0f}/yr)"
best=[]
for ex in ("net_3R","net_2R","net_eod"):
    print(f"\n================= exit {ex.split('_')[1]} =================")
    for tp in ["Sneaky","BO","IB","OB","Trap"]:
        sub=d[d.type==tp]
        if not len(sub): continue
        print(f"  --- {tp}  (n={len(sub)}) ---")
        for lbl,x in [("ALL",sub),(">SMA20",sub[sub.smaside==">SMA20"]),("<SMA20",sub[sub.smaside=="<SMA20"]),
                      ("BULL",sub[sub.reg=="BULL"]),("BEAR",sub[sub.reg=="BEAR"]),("NEUT",sub[sub.reg=="NEUTRAL"])]:
            s=line(lbl,x,ex)
            if s: print(s)
            v=x[ex].values
            if len(v)>=25 and pf(v)>=1.1 and v.sum()>0: best.append((ex.split('_')[1],tp,lbl,len(v),round(100*(v>0).mean()),pf(v),round(v.sum()),round(v.sum()/yrs)))
print(f"\n=== POSITIVE cells (n>=25, PF>=1.1): {len(best)} ===")
for r in sorted(best,key=lambda x:-x[7]):
    print(f"  {r[0]:>3} {r[1]:<7} {r[2]:<7} n={r[3]:4d} win{r[4]}% PF {r[5]} ${r[6]:+,} (${r[7]:+,}/yr)")
