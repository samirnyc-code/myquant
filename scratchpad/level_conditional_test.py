"""THE test: intraday first-touch race, restricted to days the level is REACHABLE.

Conditioning: only sessions where the level sits within X% of spot (else it is
unreachable and pure noise — 58% of days had CR >1.5% away).

Control = PERMUTATION: this day's spot + the level-distance borrowed from a random
OTHER qualifying day. Same proximity band, same distance distribution, but not THIS
day's gamma wall. If the real level beats it, the specific strike carries information.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(23)

# front-month ES 5-min
fr=[]
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d=pd.read_parquet(f); d["contract"]=os.path.basename(f).split(".")[0]; fr.append(d)
ES=pd.concat(fr,ignore_index=True); ES["date"]=ES.DateTime.dt.strftime("%Y-%m-%d")
vol=ES.groupby(["date","contract"]).Volume.sum().reset_index()
front=vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES=ES[[c==front.get(d) for d,c in zip(ES.date,ES.contract)]].sort_values("DateTime")
bars={d:g.reset_index(drop=True) for d,g in ES.groupby("date")}

spx=pd.read_csv(ROOT/"data"/"options_sim"/"spx_daily_yahoo.csv"); spx["Date"]=spx.Date.astype(str)
S=spx.set_index("Date")
esC=ES.groupby("date").Close.last()
common=sorted(set(esC.index)&set(S.index))
basis=(esC.loc[common]-S.Close.loc[common])

MQ=pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"]=MQ.session_date.astype(str); MQ=MQ.set_index("session_date")
ours={}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[456].parquet"))):
    yr=pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c]=pd.to_numeric(yr[c],errors="coerce")
    yr=yr[(yr.dte>1)&(yr.gamma.abs()<0.1)&(yr.delta.abs()<=1.01)]
    for d,g in yr.groupby("tradeDate"):
        d=str(d)
        p=(g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum(); p=p[np.isfinite(p)]
        if not p.empty: ours[d]={"cr":p.idxmax(),"ps":p.idxmin()}

sess=sorted(set(S.index)&set(bars)); nxt={d:sess[i+1] for i,d in enumerate(sess[:-1])}

def build(getl, kind, maxpct):
    """qualifying days: level within maxpct of spot."""
    out=[]
    for d in ours:
        s=nxt.get(d)
        if s is None or s not in bars or d not in basis.index: continue
        L=getl(d)
        if L is None or not np.isfinite(L): continue
        spot=S.loc[d,"Close"]
        dist = (L-spot) if kind=="cr" else (spot-L)
        if dist<0 or dist/spot*100>maxpct: continue
        out.append({"d":d,"s":s,"spot":spot,"dist":dist,"basis":basis.loc[d]})
    return out

def race(rows, kind, z, R, B, permute=False):
    rej=brk=0
    dists=[r["dist"] for r in rows]
    for i,r in enumerate(rows):
        dist = rng.choice(dists) if permute else r["dist"]
        L = (r["spot"]+dist if kind=="cr" else r["spot"]-dist) + r["basis"]
        b=bars[r["s"]]
        hit = np.where(b.High.values>=L-z)[0] if kind=="cr" else np.where(b.Low.values<=L+z)[0]
        if len(hit)==0: continue
        post=b.iloc[hit[0]:]
        if kind=="cr":
            fav=np.where(post.Low.values<=L-R)[0]; adv=np.where(post.High.values>=L+B)[0]
        else:
            fav=np.where(post.High.values>=L+R)[0]; adv=np.where(post.Low.values<=L-B)[0]
        f=fav[0] if len(fav) else 10**9; a=adv[0] if len(adv) else 10**9
        if f==a==10**9: continue
        rej += f<a; brk += a<=f
    tot=rej+brk
    return tot,(rej/tot*100 if tot else float("nan"))

for maxpct in [0.5,1.0,1.5]:
    print(f"\n########## level within {maxpct}% of spot ##########")
    for kind,lbl,getl in [("cr","CR",lambda d: ours[d]["cr"]),
                          ("cr","MQ CR",lambda d: MQ.loc[d,"cr"] if d in MQ.index else None),
                          ("ps","PS",lambda d: ours[d]["ps"]),
                          ("ps","MQ PS",lambda d: MQ.loc[d,"ps"] if d in MQ.index else None)]:
        rows=build(getl,kind,maxpct)
        if len(rows)<20: print(f"  {lbl:6} only {len(rows)} qualifying days — skip"); continue
        for z,R,B in [(5,10,10),(5,15,15)]:
            tot,pct = race(rows,kind,z,R,B)
            # permutation control: mean of 20 shuffles
            ctrl=[race(rows,kind,z,R,B,permute=True) for _ in range(20)]
            cpct=np.nanmean([c[1] for c in ctrl]); ctot=int(np.mean([c[0] for c in ctrl]))
            se=(0.5/np.sqrt(tot)*100) if tot else float("nan")
            print(f"  {lbl:6} days={len(rows):3d}  z{z} R/B={R:<2}  "
                  f"REJECT {pct:5.1f}% (n={tot:3d}, +/-{se:.1f}pp)   "
                  f"CTRL {cpct:5.1f}% (n~{ctot})   edge {pct-cpct:+5.1f}pp")
