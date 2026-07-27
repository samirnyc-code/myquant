"""Corrected report for the 6500V 2E book — reads the per-trade CSV emitted by
regime_2e_volbars.py and computes the frozen book (with skip_after applied), plus the
5M frozen book over matched windows, and an equity chart. Recompute from the raw CSV so
the earlier object-dtype skip_after no-op (fixed in regime_2e_volbars.py) is corrected
without re-running the 8-min bar build. 5M book reproduces PF 1.46 as a sanity check.

  python scripts/regime_2e_volbars_report.py [VOLTAG]     # default 6500V_2026-07-09
"""
import sys
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK
TAG = sys.argv[1] if len(sys.argv) > 1 else "6500V_2026-07-09"

def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(x):
    e=x.sort_values("Date").net.cumsum().values; return float((e-np.maximum.accumulate(e)).min())
def sharpe(x):
    dl=x.groupby("Date").net.sum(); return dl.mean()/dl.std()*np.sqrt(252) if dl.std()>0 else 0
def booknet(df):
    S=np.maximum(np.round(0.30*df.adr.values/TICK)*TICK,FLOOR)
    return np.where(df.mae_pts.values>=S,-S,df.eod_move.values)*PT-COMM-SLIP

# ---- 5M frozen book (sanity + matched-window comparison) ----
d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy(); d["net"]=booknet(d)
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(C=("Close","last"),H=("High","max"),L=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.L).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.L)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(g[["Date","sma20","skip_after"]],on="Date",how="left").dropna(subset=["sma20"])
m5=d[(d.entry_px>d.sma20)&(~d.skip_after)].copy()

# ---- 6500V frozen book (corrected: skip_after as real bool) ----
vb=pd.read_csv(WT/"data"/"regime"/f"volbars_2e_pertrade_{TAG}.csv"); vb["net"]=booknet(vb)
vb["skip_after"]=vb["skip_after"].astype(bool)
book=vb[vb.with_trend & vb.fill_hour.astype(int).isin({9,10,11,12,13}) & (vb.entry_px>vb.sma20) & (~vb.skip_after)].copy()

lines=[]
def out(s=""): lines.append(s); print(s)
m5_21=m5[m5.yr>=2021]
out(f"SANITY 5M book 2021+: n={len(m5_21)} net ${m5_21.net.sum():+,.0f} PF {pf(m5_21.net):.2f}  (expect 589 / +$77,118 / 1.46)")

for tag, lo in [("FULL 2021+","2021-06-18"),("TRAILING YEAR","2025-07-09")]:
    x=book[book.Date>=lo]; m=m5[m5.Date>=lo]
    yrs=(pd.to_datetime(x.Date.max())-pd.to_datetime(x.Date.min())).days/365.25
    out(f"\n===== {tag}  ({x.Date.min()} -> {x.Date.max()}, {yrs:.2f}yr) =====")
    out(f"  6500V book : n={len(x):4d}  net ${x.net.sum():+8,.0f} (${x.net.sum()/yrs:+7,.0f}/yr)  PF {pf(x.net):.2f}  win {100*(x.net>0).mean():4.1f}%  maxDD ${mdd(x):+8,.0f}  Sharpe {sharpe(x):.2f}")
    out(f"  5M book    : n={len(m):4d}  net ${m.net.sum():+8,.0f} (${m.net.sum()/yrs:+7,.0f}/yr)  PF {pf(m.net):.2f}  win {100*(m.net>0).mean():4.1f}%  maxDD ${mdd(m):+8,.0f}  Sharpe {sharpe(m):.2f}")
    L=x[x.dir=='L']; S=x[x.dir=='S']
    out(f"  6500V side : 2EL n={len(L)} PF {pf(L.net):.2f} ${L.net.sum():+,.0f}   2ES n={len(S)} PF {pf(S.net):.2f} ${S.net.sum():+,.0f}")
    if tag=="FULL 2021+":
        out("  6500V per-year: " + "  ".join(f"{y}:${v.net.sum():+,.0f}/PF{pf(v.net):.2f}/n{len(v)}" for y,v in x.groupby(x.Date.str[:4])))

(WT/"data"/"regime"/f"volbars_2e_metrics_{TAG}_CORRECTED.txt").write_text("\n".join(lines),encoding="utf-8")

# ---- equity chart, full 2021+ ----
lo=book.Date.min()
m5f=m5[m5.Date>=lo].copy()
vbe=book.sort_values("Date").groupby("Date").net.sum().cumsum()
m5e=m5f.sort_values("Date").groupby("Date").net.sum().cumsum()
fig,ax=plt.subplots(figsize=(12,6.5),dpi=130)
ax.plot(pd.to_datetime(m5e.index),m5e.values,color="#26a69a",lw=1.7,
        label=f"5-min bars — frozen book  (PF {pf(m5f.net):.2f}, ${m5f.net.sum():+,.0f}, Sharpe {sharpe(m5f):.2f}, DD ${mdd(m5f):+,.0f})")
ax.plot(pd.to_datetime(vbe.index),vbe.values,color="#ef5350",lw=1.7,
        label=f"6500V bars — same book  (PF {pf(book.net):.2f}, ${book.net.sum():+,.0f}, Sharpe {sharpe(book):.2f}, DD ${mdd(book):+,.0f})")
ax.axhline(0,color="#888",lw=0.6)
ax.set_title("2E frozen book: 5-min vs 6500-volume bars  —  ES 2021-06 → 2026-07 (1 ES, skip_after corrected)",fontsize=11)
ax.set_ylabel("cumulative net P&L  ($)"); ax.legend(loc="upper left",fontsize=9); ax.grid(alpha=0.15)
ax.yaxis.set_major_formatter(lambda x,_:f"${x:,.0f}"); fig.autofmt_xdate(); fig.tight_layout()
outp=Path("C:/Users/Admin/myquant/reports/volume_bars/2E_5m_vs_6500V_equity_fullhist.png"); fig.savefig(outp)
print("\nsaved chart:",outp)
