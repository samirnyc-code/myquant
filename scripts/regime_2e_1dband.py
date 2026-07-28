"""1D MIN/MAX (MQ IV expected-move band) applied to the 2E book as a RUNWAY-TO-EOD filter.
Band reconstructed in the sim price base: d1max/min = prior_close*(1 +- (VIX/100)*sqrt(1/365)).
Hypothesis: with-trend longs entered NEAR/ABOVE 1D Max (short below 1D Min) have no room to run
to EOD -> worse. Test pos-in-band + beyond-edge as a skip, train(21-23)/test(24-26). Also
sanity-check containment (% book-day closes inside band).
  python scripts/regime_2e_1dband.py
Output: data/regime/band1d_20260728.txt
"""
import numpy as np, pandas as pd
from pathlib import Path
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
TICK=0.25; PT=50.0; COMM=5.0; SLIP=12.5; FLOOR=8*TICK; ROOT1=np.sqrt(1/365)
L=[]
def out(s=""): L.append(s); print(s)
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(df):
    e=df.sort_values("Date").net.cumsum().values; return float((e-np.maximum.accumulate(e)).min())

d=pd.read_csv(WT/"data"/"regime"/"oos_pertrade_full_20260725.csv")
d=d[d.with_trend & d.fill_hour.astype(int).isin({9,10,11,12,13})].copy()
b=pd.read_parquet(DATA/"bars"/"_db_es_5m_rth.parquet"); b["Date"]=pd.to_datetime(b["DateTime"]).dt.date.astype(str)
g=b.groupby("Date").agg(O=("Open","first"),C=("Close","last"),H=("High","max"),Lo=("Low","min")).reset_index().sort_values("Date")
g["sma20"]=g.C.rolling(20).mean().shift(1); g["adr10"]=(g.H-g.Lo).rolling(10).mean().shift(1)
g["skip_after"]=((g.H-g.Lo)>1.6*g["adr10"]).shift(1).fillna(False).astype(bool)
g["pc"]=g.C.shift(1)                 # prior close (band anchor), sim price base
g["dayclose"]=g.C                    # today's close for containment check
d=d.merge(g[["Date","sma20","skip_after","pc","dayclose"]],on="Date",how="left").dropna(subset=["sma20","pc"])
d=d[d.yr>=2021].copy()
# band from prior close + prior-day VIX (both causal)
hw=d.pc.values*(d.vix_prev.values/100.0)*ROOT1
d["d1max"]=d.pc.values+hw; d["d1min"]=d.pc.values-hw; d["bw"]=2*hw
S=np.maximum(np.round(0.30*d.adr.values/TICK)*TICK,FLOOR); d["net"]=np.where(d.mae_pts.values>=S,-S,d.eod_move.values)*PT-COMM-SLIP
# frozen book (with gap<=0.54)
d=d[(d.entry_px>d.sma20)&(~d.skip_after)&(d.gap<=0.54)].copy()
# runway features (causal)
d["pos"]=(d.entry_px-d.d1min)/d.bw                      # 0=at 1D Min, 1=at 1D Max
# room to the WITH-TREND edge, in ADR units
d["room_adr"]=np.where(d.dir=="L",(d.d1max-d.entry_px)/d.adr,(d.entry_px-d.d1min)/d.adr)
d["beyond"]=d.room_adr<0                                # entered past the with-trend band edge

def rep(mask,lbl):
    x=d[mask]
    if not len(x): out(f"  {lbl:26s} n=0"); return
    tr=x[x.yr<=2023].net; te=x[x.yr>=2024].net
    flag=" <-- loses BOTH" if pf(tr)<1 and pf(te)<1 else (" <-- fitted" if (pf(tr)<1)!=(pf(te)<1) else "")
    out(f"  {lbl:26s} n={len(x):4d} net ${x.net.sum():+7,.0f} PF {pf(x.net):4.2f} DD ${mdd(x):+7,.0f} | tr {pf(tr):4.2f} te {pf(te):4.2f}{flag}")

out(f"BOOK (with gap): n={len(d)} net ${d.net.sum():+,.0f} PF {pf(d.net):.2f} | tr {pf(d[d.yr<=2023].net):.2f} te {pf(d[d.yr>=2024].net):.2f}")
# containment sanity (sim base): does today's close land inside the band?
inb=((d.dayclose>=d.d1min)&(d.dayclose<=d.d1max)); ab_min=d.dayclose>=d.d1min; be_max=d.dayclose<=d.d1max
out(f"containment (unique days): close inside {100*inb.groupby(d.Date).first().mean():.1f}% | "
    f">1DMin {100*ab_min.groupby(d.Date).first().mean():.1f}% | <1DMax {100*be_max.groupby(d.Date).first().mean():.1f}%  (MQ: 74/88/86)")

out("\n[pos in band — LONGS] (low pos = near 1D Min = most room up)")
for lo,hi in [(-9,0.25),(0.25,0.5),(0.5,0.75),(0.75,1.0),(1.0,9)]:
    rep((d.dir=="L")&(d.pos>=lo)&(d.pos<hi),f"L pos {lo:+.2f}..{hi:+.2f}")
out("\n[pos in band — SHORTS] (high pos = near 1D Max = most room down)")
for lo,hi in [(-9,0),(0,0.25),(0.25,0.5),(0.5,0.75),(0.75,9)]:
    rep((d.dir=="S")&(d.pos>=lo)&(d.pos<hi),f"S pos {lo:+.2f}..{hi:+.2f}")

out("\n[room-to-with-trend-edge, ADR units — both sides]")
for lo,hi in [(-9,0),(0,0.25),(0.25,0.5),(0.5,1.0),(1.0,9)]:
    rep((d.room_adr>=lo)&(d.room_adr<hi),f"room {lo:+.2f}..{hi:+.2f} ADR")

out("\n[candidate skip filters]")
rep(~d.beyond,"KEEP room>=0 (skip beyond-edge)")
rep(d.beyond,"  removed: beyond-edge")
rep(d.room_adr>=0.25,"KEEP room>=0.25 ADR")
rep((d.room_adr>=0)&(d.room_adr<0.25),"  removed: 0..0.25 ADR")
rep(d.room_adr>=0.5,"KEEP room>=0.5 ADR")

(WT/"data"/"regime"/"band1d_20260728.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: band1d_20260728.txt")
