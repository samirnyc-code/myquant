"""HONEST breakdown: (1) filter funnel 958->461 with net/PF and what each filter removed,
(2) top-20 trades + tail concentration (is the edge just a few fat trades?),
(3) does the book survive removing the top trades / best year.
  python scripts/regime_2e_funnel_tail.py
Outputs: data/regime/book_top20_20260727.csv + funnel_tail_20260727.txt
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

d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),Lo=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.Lo).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.Lo)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
d=d[d.yr>=2021].copy()
S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR)
d["net"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
d["above"]=d.entry_px>d.sma20

def stg(df): return f"n={len(df):4d}  net ${df.net.sum():+8,.0f}  PF {pf(df.net):4.2f}  DD ${mdd(df):+8,.0f}"

out("="*84); out("(1) FILTER FUNNEL  (2021+, base = with-trend + 09-13)"); out("="*84)
base=d
s1=d[d.above]
s2=s1[~s1.skip_after]
s3=s2[s2.gap<=0.54]
out(f"  base WT+0913          {stg(base)}")
rem=base[~base.above]
out(f"  - SMA20 gate removes {len(rem)} tr worth ${rem.net.sum():+,.0f} (PF {pf(rem.net):.2f})  ->  {stg(s1)}")
rem=s1[s1.skip_after]
out(f"  - skip-after removes {len(rem)} tr worth ${rem.net.sum():+,.0f} (PF {pf(rem.net):.2f})  ->  {stg(s2)}")
rem=s2[s2.gap>0.54]
out(f"  - gap>0.54 removes   {len(rem)} tr worth ${rem.net.sum():+,.0f} (PF {pf(rem.net):.2f})  ->  {stg(s3)}")
out(f"\n  Each removed cohort is a NET LOSER -> filters cut losers, they don't add winners.")
out(f"  gap-removed 79 trades: net ${s2[s2.gap>0.54].net.sum():+,.0f}, "
    f"win {100*(s2[s2.gap>0.54].net>0).mean():.0f}%, avg ${s2[s2.gap>0.54].net.mean():+.0f}")

book=s3.sort_values("Date").reset_index(drop=True)
V=book.net.values; tot=V.sum()
out("\n"+"="*84); out(f"(2) TAIL CONCENTRATION  (the {len(book)}-trade book, net ${tot:+,.0f})"); out("="*84)
sv=np.sort(V)[::-1]
for k in [1,2,3,5,10,20,30]:
    out(f"  top {k:2d} trades = ${sv[:k].sum():+8,.0f}  ({100*sv[:k].sum()/tot:4.0f}% of net)   "
        f"book ex-top{k}: net ${tot-sv[:k].sum():+8,.0f}  PF {pf(np.sort(V)[:-k] if k<len(V) else []):.2f}")
out(f"\n  median trade ${np.median(V):+.0f} | mean ${V.mean():+.0f} | winners {100*(V>0).mean():.1f}%")
pos=V[V>0]; possort=np.sort(pos)[::-1]; cum=np.cumsum(possort)/pos.sum()
out(f"  gross profit = ${pos.sum():+,.0f} from {len(pos)} winners; "
    f"top {np.searchsorted(cum,0.5)+1} winners = 50% of gross, top {np.searchsorted(cum,0.8)+1} = 80%")
# how many winners to cover all losses
losses=-V[V<0].sum()
out(f"  gross loss = ${-losses:+,.0f}; it takes the top {np.searchsorted(cum*pos.sum(),losses)+1} winners to erase ALL losses")

# per-year with and without that year's single best trade
out("\n  per-year  (net | PF | n | net WITHOUT that year's best trade):")
for y,x in book.groupby(book.Date.str[:4]):
    v=x.net.values; nb=v.sum()-v.max()
    out(f"    {y}: ${v.sum():+8,.0f}  PF {pf(v):4.2f}  n={len(v):3d}   ex-best ${nb:+8,.0f}")

# top 20 list
top=book.reindex(book.net.sort_values(ascending=False).index).head(20)
out("\n"+"="*84); out("(3) TOP 20 TRADES"); out("="*84)
out(f"  {'#':>2} {'Date':10s} {'dir':3s} {'net':>9s} {'adr':>6s} {'gap%':>5s} {'hold_bars':>9s}")
for i,(_,r) in enumerate(top.iterrows(),1):
    out(f"  {i:2d} {r.Date:10s} {r.dir:3s} ${r.net:+8,.0f} {r.adr:6.1f} {r.gap:5.2f} {int(r.hold):9d}")
top[["Date","dir","net","adr","gap","hold","regime","entry_px"]].to_csv(WT/"data"/"regime"/"book_top20_20260727.csv",index=False)

# robustness: drop worst month / best month
dm=book.copy(); dm["mo"]=dm.Date.str[:7]
mo=dm.groupby("mo").net.sum().sort_values()
out(f"\n  best month {mo.index[-1]} ${mo.iloc[-1]:+,.0f} | worst month {mo.index[0]} ${mo.iloc[0]:+,.0f}")
out(f"  book ex-best-month: net ${tot-mo.iloc[-1]:+,.0f} PF {pf(book[book.Date.str[:7]!=mo.index[-1]].net):.2f}")
out(f"  positive months: {int((mo>0).sum())}/{len(mo)} ({100*(mo>0).mean():.0f}%)")

(WT/"data"/"regime"/"funnel_tail_20260727.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: funnel_tail_20260727.txt + book_top20_20260727.csv")
