"""Gamma-source bakeoff: does recomputing Black-Scholes gamma from ORATS IV
match MenthorQ better than ORATS's supplied gamma? Also test 0DTE inclusion."""
import glob
import pandas as pd, numpy as np
from pathlib import Path
from math import pi
ROOT = Path(__file__).resolve().parents[1]
MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv").set_index("session_date")

def bs_gamma(S, K, sigma, T, r=0.04):
    with np.errstate(all="ignore"):
        sig = np.where(sigma>0, sigma, np.nan)
        TT  = np.where(T>0, T, np.nan)
        d1 = (np.log(S/K) + (r + 0.5*sig**2)*TT) / (sig*np.sqrt(TT))
        pdf = np.exp(-0.5*d1**2)/np.sqrt(2*pi)
        return pdf/(S*sig*np.sqrt(TT))

days=[]
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[3456].parquet"))):
    yr=pd.read_parquet(f)
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte",
              "spotPrice","callMidIv","putMidIv"]:
        yr[c]=pd.to_numeric(yr[c],errors="coerce")
    for d,g in yr.groupby("tradeDate"):
        d=str(d)
        if d in MQ.index and pd.notna(MQ.loc[d,"cr"]): days.append((d,g))
print(f"{len(days)} days")

def score(gamma_col_fn, dte_lo, label):
    cr=ps=hv=n=0
    for d,g in days:
        spot=g["spotPrice"].median()
        s=g[g.dte>=dte_lo]
        if s.empty: continue
        gam=gamma_col_fn(s, spot)
        ngex=(gam*(s.callOpenInterest-s.putOpenInterest))
        p=ngex.groupby(s.strike).sum().sort_index()
        p=p[np.isfinite(p)]
        if p.empty: continue
        n+=1; m=MQ.loc[d]
        cr += abs(p.idxmax()-m["cr"])<=0.01
        ps += abs(p.idxmin()-m["ps"])<=0.01
        fb=p[(p.index>=spot*0.90)&(p.index<=spot*1.10)]
        if not fb.empty and pd.notna(m["hvl"]):
            hv += abs(fb.cumsum().idxmin()-m["hvl"])<=0.01
    print(f"  {label:38} n={n}  cr {cr/n*100:5.1f}%  ps {ps/n*100:5.1f}%  hvl {hv/n*100:5.1f}%  avg {(cr+ps+hv)/(3*n)*100:5.1f}%")
    return (cr+ps+hv)/(3*n)

sup = lambda s,spot: s.gamma
bsC = lambda s,spot: bs_gamma(spot, s.strike.values, s.callMidIv.values, s.dte.values/365.0)
bsA = lambda s,spot: bs_gamma(spot, s.strike.values, ((s.callMidIv+s.putMidIv)/2).values, s.dte.values/365.0)

print("\n=== gamma source x 0DTE inclusion ===")
score(sup, 2, "ORATS supplied gamma, dte>1 (baseline)")
score(sup, 1, "ORATS supplied gamma, incl 0DTE")
score(bsC, 2, "BS gamma (callMidIv), dte>1")
score(bsA, 2, "BS gamma (avg call/put IV), dte>1")
score(bsA, 1, "BS gamma (avg IV), incl 0DTE")
