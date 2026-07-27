"""RevFT-extreme SALVAGE sweep — apply realistic filters to the correct-stop-entry per-trade set.
Reads data/regime/revft_extreme_trades_20260727.csv (already: 8-bar extreme + stop entry, 186 trades).
Filters swept: bars-to-fill<=K (no late entries), fill hour<=TOD (room to EOD), risk>=2pt, side, drop-BO.
Reports every combo's n/win/PF/net/$per-yr for EOD/2R/3R; flags positive cells with n>=30.
  python scripts/regime_revft_salvage.py
"""
from pathlib import Path
import numpy as np, pandas as pd
WT=Path(__file__).resolve().parent.parent
d=pd.read_csv(WT/"data"/"regime"/"revft_extreme_trades_20260727.csv")
d["btf"]=d.entry_bar-d.sig_bar                       # bars from reversal to stop-entry fill
d["fill_hr"]=(510+d.entry_bar*5)//60                 # RTH bar0=08:30 CT
yrs=(pd.to_datetime(d.Date).max()-pd.to_datetime(d.Date).min()).days/365.25
def pf(v):
    v=np.asarray(v,float);gp=v[v>0].sum();gl=-v[v<0].sum();return round(gp/gl,2) if gl else 0.0
print(f"base: {len(d)} trades, {yrs:.1f}yr.  btf: median {int(d.btf.median())} p90 {int(d.btf.quantile(.9))}   fill_hr spread {d.fill_hr.min()}-{d.fill_hr.max()}")
print(f"\n{'side':>5}{'K':>4}{'TOD':>5}{'r>=2':>6}{'noBO':>6}{'exit':>5}{'n':>6}{'win%':>6}{'PF':>6}{'net':>10}{'$/yr':>9}")
best=[]
for side in ("ALL","CT"):
    for K in (2,3,4,99):
        for tod in (12,13,15):
            for r2 in (0,2):
                for nobo in (0,1):
                    m=d.copy()
                    if side=="CT": m=m[m.side=="CT"]
                    m=m[m.btf<=K]; m=m[m.fill_hr<=tod]
                    if r2: m=m[m.risk_pts>=2]
                    if nobo: m=m[m.type!="BO"]
                    if len(m)<15: continue
                    for ex in ("net_eod","net_2R","net_3R"):
                        v=m[ex].values
                        row=(side,K,tod,r2,nobo,ex.split("_")[1],len(v),round(100*(v>0).mean()),pf(v),round(v.sum()),round(v.sum()/yrs))
                        if pf(v)>=1.15 and len(v)>=30 and v.sum()>0: best.append(row)
# print a compact core grid (side x K x exit at TOD<=13, r>=2, drop-BO) + the best cells
print("--- core: TOD<=13, risk>=2, drop-BO ---")
for side in ("ALL","CT"):
    for K in (2,3,4,99):
        m=d.copy()
        if side=="CT": m=m[m.side=="CT"]
        m=m[(m.btf<=K)&(m.fill_hr<=13)&(m.risk_pts>=2)&(m.type!="BO")]
        if len(m)<10: continue
        for ex in ("net_eod","net_2R","net_3R"):
            v=m[ex].values
            print(f"{side:>5}{K:>4}{13:>5}{2:>6}{1:>6}{ex.split('_')[1]:>5}{len(v):>6}{round(100*(v>0).mean()):>6}{pf(v):>6.2f}{v.sum():>+10,.0f}{v.sum()/yrs:>+9,.0f}")
print(f"\n=== POSITIVE ROBUST CELLS (PF>=1.15, n>=30, net>0): {len(best)} ===")
for r in sorted(best,key=lambda x:-x[10])[:20]:
    print(f"  side={r[0]} K<={r[1]} TOD<={r[2]} r>=2:{r[3]} noBO:{r[4]} {r[5]:>3}: n={r[6]} win{r[7]}% PF {r[8]} net ${r[9]:+,} (${r[10]:+,}/yr)")
if not best: print("  NONE — no filtered combo clears PF 1.15 with n>=30 and positive net.")
