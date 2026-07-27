"""Chart extreme-filtered RevFT trades for one year — paginated, 9/page, with the 2R price PATH.
Reads data/regime/revft_extreme_trades_20260727.csv + Massive 5M (_continuous.parquet). Each panel:
local 5M candles, 8-bar window (faint) + reversal 2 bars (yellow), lines = entry(white)/stop(red
dash)/2R target(blue), and the CYAN PATH of bar-closes from entry to the 2R exit (dot: green=2R hit,
red=stopped). Border green = 2R winner. 9 panels/page -> multiple PNGs.

  python scripts/regime_revft_chart_year.py [--year 2025] [--side CT|ALL] [--per 9]
Output: docs/living/revft_charts/revft_<year>_<side>_pN.png  (all opened in VSCode)
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
DATA=Path(r"C:/Users/Admin/myquant/data"); WT=Path(__file__).resolve().parent.parent
BARS=DATA/"bars"/"_continuous.parquet"; N=8
year=int(sys.argv[sys.argv.index("--year")+1]) if "--year" in sys.argv else 2025
sidef=sys.argv[sys.argv.index("--side")+1] if "--side" in sys.argv else "ALL"
per=int(sys.argv[sys.argv.index("--per")+1]) if "--per" in sys.argv else 9
minrisk=float(sys.argv[sys.argv.index("--minrisk")+1]) if "--minrisk" in sys.argv else 0.0
LEG=("legend:  white=entry   red dash=stop   blue dot=2R target   yellow=reversal (2 bars)   "
     "grey shade=8-bar window   CYAN=price path entry→exit   dot=exit (grn=2R hit / red=stopped)")


def main():
    d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
    d=d[d.yr==year]
    if sidef!="ALL": d=d[d.side==sidef]
    if minrisk>0: d=d[d.risk_pts>=minrisk]
    d=d.sort_values(["Date","sig_bar"]).reset_index(drop=True)
    b=pd.read_parquet(BARS); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    byd={dt:x.sort_values("DateTime").reset_index(drop=True) for dt,x in b.groupby("Date")}
    m=len(d); cols=3; rowsper=int(np.ceil(per/cols)); npages=int(np.ceil(m/per))
    outdir=WT/"docs"/"living"/"revft_charts"; outdir.mkdir(parents=True,exist_ok=True)
    paths=[]
    for pg in range(npages):
        sl=d.iloc[pg*per:(pg+1)*per].reset_index(drop=True)
        fig,axs=plt.subplots(rowsper,cols,figsize=(cols*4.2,rowsper*3.1)); axs=np.array(axs).reshape(-1)
        fig.suptitle(f"RevFT n{N}-extreme — {year} ({sidef}) — page {pg+1}/{npages}  (trades {pg*per+1}-{pg*per+len(sl)} of {m})\n{LEG}",
                     fontsize=9,color="w")
        for k,(_,r) in enumerate(sl.iterrows()):
            ax=axs[k]; g=byd.get(r.Date)
            if g is None: ax.axis("off"); continue
            bi=int(r.sig_bar); eb=int(r.entry_bar); x2=int(r.exbar_2R)
            i0=max(0,bi-N-2); i1=min(len(g)-1,max(x2,bi)+3)
            seg=g.iloc[i0:i1+1]
            for j,(_,bar) in enumerate(seg.iterrows()):
                gi=i0+j; up=bar.Close>=bar.Open; col="#26a65b" if up else "#d64541"
                ax.plot([gi,gi],[bar.Low,bar.High],color=col,lw=.8)
                ax.add_patch(Rectangle((gi-.32,min(bar.Open,bar.Close)),.64,max(abs(bar.Close-bar.Open),.02),color=col))
            ax.axvspan(bi-N+1-.5,bi+.5,color="#ffffff",alpha=.05)          # 8-bar window
            ax.axvspan(bi-1-.5,bi+.5,color="#f1c40f",alpha=.20)            # reversal 2 bars
            short=r.dir=="Short"; risk=r.risk_pts; tgt2=r.entry-2*risk if short else r.entry+2*risk
            ax.axhline(r.entry,color="#ffffff",lw=.9)
            ax.axhline(r.stop,color="#ff5a5a",lw=.9,ls="--")
            ax.axhline(tgt2,color="#4a9eff",lw=.9,ls=":")
            # straight line from entry to the 2R exit (target or stop)
            ax.plot([eb,x2],[r.entry,r.expx_2R],color="#00e5ff",lw=1.6,alpha=.9,zorder=5)
            win=r.net_2R>0
            ax.plot(x2,r.expx_2R,"o",color=("#2ecc71" if win else "#ff5a5a"),ms=7,zorder=6,mec="w",mew=.5)
            ax.plot(eb,r.entry,"^" if not short else "v",color="#ffffff",ms=6,zorder=6)
            for sp in ax.spines.values(): sp.set_color("#2ecc71" if win else "#e74c3c"); sp.set_linewidth(2)
            ax.set_title(f"{r.Date} {r.dir} · {r.type} · {r.side} · risk {risk:.1f}pt\n2R ${r.net_2R:+.0f}   (3R ${r.net_3R:+.0f})",fontsize=8,color="w")
            ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor("#0c0f13")
        for k in range(len(sl),len(axs)): axs[k].axis("off")
        fig.patch.set_facecolor("#0c0f13"); plt.tight_layout(rect=[0,0,1,0.95])
        p=outdir/f"revft_{year}_{sidef}_p{pg+1}.png"; fig.savefig(p,dpi=115,facecolor="#0c0f13"); plt.close()
        paths.append(str(p)); print("saved",p.name)
    print("PATHS:"+"|".join(paths))


if __name__=="__main__": main()
