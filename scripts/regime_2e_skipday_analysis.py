"""What do the skip-after-trend-days actually contain? How many days, what the book
skips, and whether those days suit a DIFFERENT setup (counter-trend / fade / opposite side).

Uses oos_pertrade_full (ALL 2E entries, both regimes, gate-free) + daily 5M stats.
  python scripts/regime_2e_skipday_analysis.py
Output: data/regime/skipday_analysis_20260727.csv + stdout tables.
"""
import numpy as np, pandas as pd
from pathlib import Path
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK

def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def stat(x, lbl):
    v=x.net.values
    if not len(v): print(f"  {lbl:28s} n=0"); return
    print(f"  {lbl:28s} n={len(v):4d}  net ${v.sum():+8,.0f}  PF {pf(v):5.2f}  win {100*(v>0).mean():4.1f}%  exp ${v.mean():+6.0f}")

d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR)
# book P&L for the with-trend direction as taken:
d["net_wt"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
# fade P&L = take the SAME signal in the OPPOSITE direction (mirror mae/eod):
# for a with-trend entry, the opposite side's adverse excursion ~ eod favorable of the wt side and vice versa.
# Approximate mirror: opp_mae = wt eod favorable distance capped; opp_eod = -wt eod. Use stop symmetric.
d["net_fade"]=np.where((-d.eod_move.values) <= -S, -S, -d.eod_move.values)*0  # placeholder, computed below properly

b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),L=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.L).rolling(10).mean().shift(1)
g["rng"]=g.H-g.L
g["trendday"]=(g["rng"]>1.6*g["adr10"])
g["skip_after"]=g["trendday"].shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
d["net"]=d["net_wt"]
d21=d[d.yr>=2021].copy()

# universe of trading days in 2021+ and how many are skip days
days=g[(g.Date>=d21.Date.min())&(g.Date<=d21.Date.max())]
n_skip_days=int(days.skip_after.sum()); n_days=len(days)
print(f"=== 2021+ ({d21.Date.min()}..{d21.Date.max()}) ===")
print(f"trading days: {n_days} | skip-after-trend days: {n_skip_days} ({100*n_skip_days/n_days:.1f}%) | "
      f"skip days WITH >=1 book signal: {d21[d21.skip_after & d21.with_trend & (d21.entry_px>d21.sma20)].Date.nunique()}")

book=d21[d21.with_trend & (d21.entry_px>d21.sma20)]
print("\n-- BOOK (with-trend, entry>sma20) --")
stat(book, "all book days")
stat(book[~book.skip_after], "  non-skip days (KEEP)")
stat(book[book.skip_after], "  skip days (REMOVED)")
sk=book[book.skip_after]
stat(sk[sk.dir=='L'], "    removed 2EL")
stat(sk[sk.dir=='S'], "    removed 2ES")

# what ELSE is on skip days? counter-trend 2E (the fade candidates), both gates
print("\n-- ALTERNATIVES ON SKIP DAYS (2021+) --")
sd=d21[d21.skip_after]
stat(sd[sd.with_trend & (sd.entry_px>sd.sma20)], "with-trend + entry>sma20 (book)")
stat(sd[~sd.with_trend & (sd.entry_px>sd.sma20)], "counter-trend + entry>sma20")
stat(sd[sd.with_trend & (sd.entry_px<=sd.sma20)], "with-trend + entry<=sma20")
stat(sd[~sd.with_trend], "all counter-trend (any gate)")
# by side on skip days regardless of gate
stat(sd[sd.dir=='L'], "all 2EL (any gate)")
stat(sd[sd.dir=='S'], "all 2ES (any gate)")

sk.to_csv(WT/"data"/"regime"/"skipday_analysis_20260727.csv", index=False)
print(f"\nsaved removed-trades detail: data/regime/skipday_analysis_20260727.csv")
