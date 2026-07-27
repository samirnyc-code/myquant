"""Full-size, fully-labeled single-trade charts for RevFT extreme-filter trades (stop-entry).
Reads data/regime/revft_extreme_trades_20260727.csv + Massive 5M (_continuous.parquet).
One BIG figure per trade: candles with time x-axis + price y-axis, labeled entry/stop/2R/3R lines,
reversal 2 bars + 8-bar window shaded, entry marker, straight entry->exit line, exit dot, full title.

  python scripts/regime_revft_chart_full.py [--year 2025] [--n 5] [--dates d1,d2,...] [--minrisk 2]
Output: docs/living/revft_charts/full_<date>_<dir>.png  (opened in VSCode)
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
BARS=DATA/"bars"/"_continuous.parquet"; N=8
year=int(sys.argv[sys.argv.index("--year")+1]) if "--year" in sys.argv else 2025
K=int(sys.argv[sys.argv.index("--n")+1]) if "--n" in sys.argv else 5
minrisk=float(sys.argv[sys.argv.index("--minrisk")+1]) if "--minrisk" in sys.argv else 0.0
dates=sys.argv[sys.argv.index("--dates")+1].split(",") if "--dates" in sys.argv else None


def main():
    d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
    if minrisk>0: d=d[d.risk_pts>=minrisk]
    if dates: d=d[d.Date.isin(dates)]
    else: d=d[d.yr==year]
    d=d.sort_values(["Date","sig_bar"]).reset_index(drop=True)
    if not dates: d=d.iloc[np.linspace(0,len(d)-1,min(K,len(d))).astype(int)]   # spread across the year
    b=pd.read_parquet(BARS); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    byd={dt:x.sort_values("DateTime").reset_index(drop=True) for dt,x in b.groupby("Date")}
    outdir=WT/"docs"/"living"/"revft_charts"; outdir.mkdir(parents=True,exist_ok=True); paths=[]
    for _,r in d.iterrows():
        g=byd.get(r.Date)
        if g is None: continue
        bi=int(r.sig_bar); eb=int(r.entry_bar); x2=int(r.exbar_2R)
        i0=max(0,bi-N-3); i1=min(len(g)-1,max(x2,eb,bi)+6); seg=g.iloc[i0:i1+1].reset_index(drop=True)
        short=r.dir=="Short"; risk=r.risk_pts
        tgt2=r.entry-2*risk if short else r.entry+2*risk; tgt3=r.entry-3*risk if short else r.entry+3*risk
        fig,ax=plt.subplots(figsize=(15,8)); fig.patch.set_facecolor("#0c0f13"); ax.set_facecolor("#0c0f13")
        xs=np.arange(len(seg))
        for j,(_,bar) in enumerate(seg.iterrows()):
            up=bar.Close>=bar.Open; col="#26a65b" if up else "#d64541"
            ax.plot([j,j],[bar.Low,bar.High],color=col,lw=1.4)
            ax.add_patch(Rectangle((j-.34,min(bar.Open,bar.Close)),.68,max(abs(bar.Close-bar.Open),.03),color=col))
        gi=lambda k:k-i0
        ax.axvspan(gi(bi-N+1)-.5,gi(bi)+.5,color="#ffffff",alpha=.05,label="8-bar window")
        ax.axvspan(gi(bi-1)-.5,gi(bi)+.5,color="#f1c40f",alpha=.22,label="reversal (2 bars)")
        for yv,c,ls,lab in [(r.entry,"#ffffff","-","entry "+str(r.entry)),(r.stop,"#ff5a5a","--","stop "+str(r.stop)),
                            (tgt2,"#4a9eff",":",f"2R {tgt2:.2f}"),(tgt3,"#2ecc71",":",f"3R {tgt3:.2f}")]:
            ax.axhline(yv,color=c,lw=1.3,ls=ls); ax.text(len(seg)-.5,yv,"  "+lab,color=c,fontsize=10,va="center")
        ax.plot([gi(eb),gi(x2)],[r.entry,r.expx_2R],color="#00e5ff",lw=2.2,zorder=5,label="entry→2R exit")
        ax.plot(gi(eb),r.entry,"v" if short else "^",color="#fff",ms=13,zorder=6,mec="#000",label="stop-entry fill")
        win=r.net_2R>0
        ax.plot(gi(x2),r.expx_2R,"o",color=("#2ecc71" if win else "#ff5a5a"),ms=13,zorder=6,mec="#fff",label="exit (2R hit / stopped)")
        # x ticks = bar times
        tk=list(range(0,len(seg),max(1,len(seg)//12)))
        ax.set_xticks(tk); ax.set_xticklabels([pd.Timestamp(seg.DateTime[j]).strftime("%H:%M") for j in tk],color="#8b93a0",fontsize=9)
        ax.tick_params(colors="#8b93a0"); [sp.set_color("#2b333d") for sp in ax.spines.values()]
        ax.grid(True,color="#161c23",lw=.6)
        ax.set_title(f"{r.Date}  RevFT {r.dir} · type={r.type} · regime-side={r.side}   [{'WIN' if win else 'LOSS'} @2R]\n"
                     f"STOP-ENTRY fill {r.entry}  ·  stop {r.stop} (risk {risk:.2f}pt)  ·  2R ${r.net_2R:+.0f}   3R ${r.net_3R:+.0f}",
                     color="#e6e9ec",fontsize=13)
        ax.set_ylabel("ES price",color="#8b93a0"); ax.set_xlabel("RTH 5-min bars (time)",color="#8b93a0")
        ax.legend(loc="upper left",facecolor="#1a1f26",edgecolor="#2b333d",labelcolor="#e6e9ec",fontsize=9)
        plt.tight_layout()
        p=outdir/f"full_{r.Date}_{r.dir}.png"; fig.savefig(p,dpi=120,facecolor="#0c0f13"); plt.close(); paths.append(str(p)); print("saved",p.name)
    print("PATHS:"+"|".join(paths))


if __name__=="__main__": main()
