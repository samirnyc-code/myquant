"""Diagnostic: 10 consecutive sessions of intraday ES (shown in SPX-equivalent pts)
with MenthorQ's CR / PS / HVL for that session overlaid.

Level for session S comes from chain date D = prior session (how MQ publishes).
ES is converted to SPX-equivalent by subtracting that day's basis, so the LEVELS
are plotted untransformed in their native SPX units.
"""
import glob, os
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CR_C, PS_C, HVL_C, INK = "#D1495B", "#2A78D6", "#E9A23B", "#1a1a19"

fr=[]
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d=pd.read_parquet(f); d["contract"]=os.path.basename(f).split(".")[0]; fr.append(d)
ES=pd.concat(fr,ignore_index=True); ES["date"]=ES.DateTime.dt.strftime("%Y-%m-%d")
vol=ES.groupby(["date","contract"]).Volume.sum().reset_index()
front=vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES=ES[[c==front.get(d) for d,c in zip(ES.date,ES.contract)]].sort_values("DateTime")

spx=pd.read_csv(ROOT/"data"/"options_sim"/"spx_daily_yahoo.csv"); spx["Date"]=spx.Date.astype(str)
spxC=spx.set_index("Date").Close
esC=ES.groupby("date").Close.last()
common=sorted(set(esC.index)&set(spxC.index))
basis=(esC.loc[common]-spxC.loc[common])

MQ=pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"]=MQ.session_date.astype(str); MQ=MQ.set_index("session_date")

sess=[d for d in common if d in ES.date.values]
sess=sorted(sess)[-11:]                      # 11 -> 10 plotted (need prior for level)
plot_sess=sess[1:]

fig,ax=plt.subplots(figsize=(15,7.5))
x0=0; ticks=[]; lab=[]
for si,s in enumerate(plot_sess):
    b=ES[ES.date==s]
    px=b.Close.values-basis.loc[s]           # SPX-equivalent
    xs=np.arange(x0,x0+len(px))
    ax.plot(xs,px,color=INK,lw=1.4,zorder=3,
            label="ES price (SPX-equiv)" if si==0 else None)
    d=sess[si]                               # chain date = prior session
    if d in MQ.index:
        m=MQ.loc[d]
        for val,c,nm in [(m.get("cr"),CR_C,"CR"),(m.get("ps"),PS_C,"PS"),(m.get("hvl"),HVL_C,"HVL")]:
            if pd.notna(val):
                ax.plot([xs[0],xs[-1]],[val,val],color=c,lw=2,solid_capstyle="round",
                        zorder=2,label=nm if si==0 else None)
                ax.annotate(f"{nm} {val:.0f}",(xs[-1],val),xytext=(3,0),
                            textcoords="offset points",va="center",fontsize=7.5,color=c)
    ticks.append(xs[len(xs)//2]); lab.append(s[5:])
    if si: ax.axvline(x0-0.5,color="#00000018",lw=1,zorder=1)
    x0+=len(px)

ax.set_xticks(ticks); ax.set_xticklabels(lab,fontsize=9)
ax.set_ylabel("SPX points"); ax.set_xlabel("session (5-min bars, RTH)")
ax.set_title("MenthorQ CR / PS / HVL vs intraday price — 10 consecutive sessions",
             fontsize=13,fontweight="600",loc="left")
ax.grid(axis="y",color="#00000012",lw=1); ax.set_axisbelow(True)
for sp in ("top","right"): ax.spines[sp].set_visible(False)
ax.spines["left"].set_color("#00000030"); ax.spines["bottom"].set_color("#00000030")
ax.legend(frameon=False,ncol=4,loc="upper left",fontsize=9)
plt.tight_layout()
out=ROOT/"scratchpad"/"levels_10d.png"
plt.savefig(out,dpi=140,facecolor="#fcfcfb")
print("wrote",out)

print("\n=== numeric check: level vs that session's actual SPX-equiv range ===")
print(f"{'session':11}{'low':>8}{'high':>8}{'close':>8} | {'CR':>7}{'PS':>7}{'HVL':>7} | touched")
for si,s in enumerate(plot_sess):
    b=ES[ES.date==s]; px=b.Close.values-basis.loc[s]
    d=sess[si]
    if d not in MQ.index: continue
    m=MQ.loc[d]; lo,hi=px.min(),px.max()
    t=[nm for val,nm in [(m.get("cr"),"CR"),(m.get("ps"),"PS"),(m.get("hvl"),"HVL")]
       if pd.notna(val) and lo<=val<=hi]
    print(f"{s:11}{lo:8.0f}{hi:8.0f}{px[-1]:8.0f} | {m.get('cr',np.nan):7.0f}"
          f"{m.get('ps',np.nan):7.0f}{m.get('hvl',np.nan):7.0f} | {','.join(t) if t else '-'}")
