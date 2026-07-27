"""FULL METRICS — 2EL+2ES with-trend book ONLY (no fades). Gate: entry>SMA20_D + skip-after-
trend-day, 09-13, retest 6t, 0.30xADR stop, EOD. From oos_pertrade_full (2E trades). Reports
2021+ and 16yr: trade + daily metrics, per-year, and 2EL/2ES side split.
  python scripts/regime_2e_book_metrics.py
"""
from pathlib import Path
import numpy as np, pandas as pd
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(x):
    e=x.sort_values("Date").net.cumsum().values; return float((e-np.maximum.accumulate(e)).min())
def main():
    d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
    d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
    S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR)
    d["net"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
    b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),L=("Low","min")).reset_index().sort_values("Date")
    g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.L).rolling(10).mean().shift(1)
    g["skip_after"]=((g.H-g.L)>1.6*g["adr10"]).shift(1).fillna(False)
    d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
    book=d[(d.entry_px>d.sma20)&(~d.skip_after)].copy()
    def metrics(x,yrs,label):
        v=x.net.values; w=v[v>0]; l=v[v<0]
        daily=x.groupby("Date").net.sum()
        sharpe=daily.mean()/daily.std()*np.sqrt(252) if daily.std()>0 else 0
        print(f"\n===== {label}  (n={len(v)}) =====")
        print(f"  net            ${v.sum():+,.0f}   (${v.sum()/yrs:+,.0f}/yr, 1 ES contract)")
        print(f"  PF             {pf(v):.2f}")
        print(f"  win rate       {100*(v>0).mean():.1f}%   ({len(w)}W / {len(l)}L)")
        print(f"  avg win        ${w.mean():+,.0f}    avg loss ${l.mean():+,.0f}    payoff {abs(w.mean()/l.mean()):.2f}")
        print(f"  expectancy     ${v.mean():+,.0f}/trade")
        print(f"  max drawdown   ${mdd(x):+,.0f}")
        print(f"  best / worst   ${v.max():+,.0f} / ${v.min():+,.0f}")
        print(f"  trades/yr      {len(v)/yrs:.0f}    daily Sharpe {sharpe:.2f}")
        print(f"  by side:  2EL n={sum(x.dir=='L')} PF {pf(x[x.dir=='L'].net):.2f} net ${x[x.dir=='L'].net.sum():+,.0f}"
              f"   2ES n={sum(x.dir=='S')} PF {pf(x[x.dir=='S'].net):.2f} net ${x[x.dir=='S'].net.sum():+,.0f}")
    for lbl,ymin,yrs in (("2021+ (tradeable era)",2021,5.5),("full 16yr",2010,16.5)):
        metrics(book[book.yr>=ymin],yrs,lbl)
    print("\nper-year (net | PF | n | win%):")
    for y,x in book.groupby("yr"):
        v=x.net.values
        print(f"  {int(y)}: ${v.sum():+8,.0f}  PF {pf(v):4.2f}  n={len(v):3d}  win {100*(v>0).mean():3.0f}%")
if __name__=="__main__": main()
