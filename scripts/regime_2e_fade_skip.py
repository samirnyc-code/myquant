"""FADE sleeve with corrected skip_after. The fade_stop_sweep CSV already gap-filters
(<=0.54) and holds per-trade net for every stop candidate. Merge the corrected skip_after
(day after trend day) and test: does skipping-after-trend help the fade? Per side
(short=True = f2EL tradeable; short=False = f2ES-long DEAD), per stop, train/test.
  python scripts/regime_2e_fade_skip.py
"""
import numpy as np, pandas as pd
from pathlib import Path
WT=Path(__file__).resolve().parent.parent; DATA=Path(r"C:/Users/Admin/myquant/data")
L=[]
def out(s=""): L.append(s); print(s)
def pf(v):
    v=np.asarray(v,float); gp=v[v>0].sum(); gl=-v[v<0].sum(); return gp/gl if gl else float('inf')
def mdd(v):
    e=np.cumsum(np.asarray(v,float)); return float((e-np.maximum.accumulate(e)).min())

d=pd.read_csv(WT/"data"/"regime"/"fade_stop_sweep_20260725.csv")
# skip_after from the fade's own price base (_continuous)
b=pd.read_parquet(DATA/"bars"/"_continuous.parquet"); b["Date"]=b.DateTime.dt.date.astype(str)
dly=b.groupby("Date").agg(dH=("High","max"),dL=("Low","min")).reset_index().sort_values("Date")
dly["adr10"]=(dly.dH-dly.dL).rolling(10).mean().shift(1)
dly["skip_after"]=((dly.dH-dly.dL)>1.6*dly["adr10"]).shift(1).fillna(False).astype(bool)
d=d.merge(dly[["Date","skip_after"]],on="Date",how="left")
d["skip_after"]=d["skip_after"].fillna(False).astype(bool)

STOPS=["fx2","fx3","fx4","fx5","fx6","fx8","adr0.08","adr0.1","adr0.12","EOD"]
def report(df,lbl):
    out(f"\n== {lbl}  (n={len(df)}) ==")
    out(f"  {'stop':8s} {'net(all)':>10s} {'PF':>5s} | {'net(skipON)':>12s} {'PF':>5s} {'n':>4s} {'DD':>8s} | tr/te PF")
    for s in STOPS:
        allv=df[s].values
        k=df[~df.skip_after]; kv=k[s].values
        tr=k[k.Date<='2023-12-31'][s].values; te=k[k.Date>='2024-01-01'][s].values
        out(f"  {s:8s} {allv.sum():+10,.0f} {pf(allv):5.2f} | {kv.sum():+12,.0f} {pf(kv):5.2f} {len(kv):4d} {mdd(kv):+8,.0f} | {pf(tr):.2f}/{pf(te):.2f}")

# f2EL = short=True (the tradeable fade); f2ES-long = short=False (dead)
report(d[d.short==True], "f2EL (fade of 2E-long = SHORT) — the tradeable sleeve")
report(d[d.short==False], "f2ES-long (fade of 2E-short = LONG) — memory says DEAD")

# how many fade days are skip-after days?
f=d[d.short==True]
out(f"\nf2EL: {int(f.skip_after.sum())} of {len(f)} on skip-after-trend days; "
    f"those at fx4 net ${f[f.skip_after].fx4.sum():+,.0f} PF {pf(f[f.skip_after].fx4):.2f}")
(WT/"data"/"regime"/"fade_skip_20260727.txt").write_text("\n".join(L),encoding="utf-8")
print("\nsaved: data/regime/fade_skip_20260727.txt")
