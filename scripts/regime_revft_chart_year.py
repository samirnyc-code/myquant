"""Chart every extreme-filtered RevFT trade for one year (default 2025) as a grid montage.
Reads data/regime/revft_extreme_trades_20260727.csv + Massive 5M (_continuous.parquet). Each panel:
the trade's local 5M candles, the n=8 window shaded, reversal bar marked, entry/stop/2R+3R target
lines, exit dot (3R). Green border = winner (net_2R>0), red = loser.

  python scripts/regime_revft_chart_year.py [--year 2025] [--side CT|ALL]
Output: docs/living/revft_charts/revft_extreme_<year>.png  (opened in VSCode)
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


def main():
    d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
    d=d[d.yr==year]
    if sidef!="ALL": d=d[d.side==sidef]
    d=d.sort_values(["Date","sig_bar"]).reset_index(drop=True)
    b=pd.read_parquet(BARS); b["DateTime"]=pd.to_datetime(b["DateTime"]); b["Date"]=b.DateTime.dt.date.astype(str)
    byd={dt:x.sort_values("DateTime").reset_index(drop=True) for dt,x in b.groupby("Date")}
    m=len(d); cols=6; rows=int(np.ceil(m/cols))
    fig,axs=plt.subplots(rows,cols,figsize=(cols*3.0,rows*2.4)); axs=np.array(axs).reshape(-1)
    fig.suptitle(f"RevFT n{N}-extreme trades — {year} ({sidef}) — {m} trades  [border: grn=2R win, red=loss]",fontsize=12,color="w")
    for k,(_,r) in enumerate(d.iterrows()):
        ax=axs[k]; g=byd.get(r.Date)
        if g is None: ax.axis("off"); continue
        bi=int(r.sig_bar); exb=int(r.exbar_3R)
        i0=max(0,bi-N-2); i1=min(len(g)-1,max(exb,bi)+3)
        seg=g.iloc[i0:i1+1]; xs=np.arange(len(seg))
        for j,(_,bar) in enumerate(seg.iterrows()):
            up=bar.Close>=bar.Open; col="#26a65b" if up else "#d64541"
            ax.plot([j,j],[bar.Low,bar.High],color=col,lw=.6)
            ax.add_patch(Rectangle((j-.3,min(bar.Open,bar.Close)),.6,max(abs(bar.Close-bar.Open),.01),color=col))
        # n-window shade + reversal bar
        ax.axvspan(bi-N+1-i0-.5,bi-i0+.5,color="#ffffff",alpha=.05)
        ax.axvspan(bi-1-i0-.5,bi-i0+.5,color="#f1c40f",alpha=.18)
        short=r.dir=="Short"; risk=r.risk_pts
        tgt2=r.entry-2*risk if short else r.entry+2*risk
        tgt3=r.entry-3*risk if short else r.entry+3*risk
        for yv,c,ls in [(r.entry,"#ffffff","-"),(r.stop,"#ff5a5a","--"),(tgt2,"#4a9eff",":"),(tgt3,"#2ecc71",":")]:
            ax.axhline(yv,color=c,lw=.8,ls=ls)
        ax.plot(exb-i0,r.expx_3R,"o",color="#2ecc71",ms=4)
        win=r.net_2R>0
        for sp in ax.spines.values(): sp.set_color("#2ecc71" if win else "#e74c3c"); sp.set_linewidth(1.6)
        ax.set_title(f"{r.Date[5:]} {r.dir[0]} {r.type} {r.side}\n2R ${r.net_2R:+.0f} 3R ${r.net_3R:+.0f}",fontsize=6.5,color="w")
        ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor("#0c0f13")
    for k in range(m,len(axs)): axs[k].axis("off")
    fig.patch.set_facecolor("#0c0f13")
    plt.tight_layout(rect=[0,0,1,0.985])
    out=WT/"docs"/"living"/"revft_charts"; out.mkdir(parents=True,exist_ok=True)
    p=out/f"revft_extreme_{year}_{sidef}.png"; fig.savefig(p,dpi=110,facecolor="#0c0f13"); plt.close()
    print(f"saved {p}  ({m} trades)")


if __name__=="__main__": main()
