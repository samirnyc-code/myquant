"""TEST C — does the HVL regime SEPARATE outcomes at CR/PS, in opposite directions?

MenthorQ's stated framework:
   above HVL (positive gamma)  -> mean-reverting: levels should REJECT price
   below HVL (negative gamma)  -> momentum:       levels should BREAK

My earlier Test A pooled both regimes, which would cancel two opposite effects.
This measures them separately. Pure measurement — no entry rules, no targets.

Also splits by touch NUMBER (their most-repeated rule: skip the 1st test, take 2nd/3rd).
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(31)

fr = []
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d = pd.read_parquet(f); d["contract"] = os.path.basename(f).split(".")[0]; fr.append(d)
ES = pd.concat(fr, ignore_index=True); ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
vol = ES.groupby(["date","contract"]).Volume.sum().reset_index()
front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES = ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime")
bars = {d: g.reset_index(drop=True) for d, g in ES.groupby("date")}

S = pd.read_csv(ROOT/"data"/"spx_daily_full.csv"); S["Date"] = S.Date.astype(str); S = S.set_index("Date")
esC = ES.groupby("date").Close.last()
common = sorted(set(esC.index) & set(S.index))
basis = esC.loc[common] - S.Close.loc[common]

lv = {}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_*.parquet"))):
    yr = pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c] = pd.to_numeric(yr[c], errors="coerce")
    yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
    for d, g in yr.groupby("tradeDate"):
        d = str(d); spot = g.spotPrice.median()
        p = (g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum()
        p = p[np.isfinite(p)]
        if p.empty or not np.isfinite(spot): continue
        fb = p[(p.index >= spot*0.90) & (p.index <= spot*1.10)]
        if fb.empty: continue
        lv[d] = {"cr": float(p.idxmax()), "ps": float(p.idxmin()),
                 "hvl": float(fb.cumsum().idxmin())}

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}
Z, R, B, GATE = 5.0, 10.0, 10.0, 1.0

def touches(kind):
    """Every touch of the level, tagged with regime and touch number."""
    out = []
    for d in lv:
        s = nxt.get(d)
        if s is None or s not in bars or d not in basis.index or d not in S.index: continue
        spot = float(S.Close.loc[d]); L0 = lv[d][kind]; hvl = lv[d]["hvl"]
        dist = (L0-spot) if kind == "cr" else (spot-L0)
        if dist < 0 or dist/spot*100 > GATE: continue
        # REGIME from prior close vs HVL — known before the session
        regime = "above HVL (+gamma)" if spot > hvl else "below HVL (-gamma)"
        L = L0 + float(basis.loc[d])
        b = bars[s]; hi = b.High.values; lo = b.Low.values
        inzone = (hi >= L-Z) if kind == "cr" else (lo <= L+Z)
        # separate touches: a new touch requires leaving the zone first
        idxs, armed = [], True
        for i, z in enumerate(inzone):
            if z and armed: idxs.append(i); armed = False
            elif not z: armed = True
        for n, i0 in enumerate(idxs, 1):
            post = b.iloc[i0:]
            if kind == "cr":
                fav = np.where(post.Low.values  <= L-R)[0]; adv = np.where(post.High.values >= L+B)[0]
            else:
                fav = np.where(post.High.values >= L+R)[0]; adv = np.where(post.Low.values  <= L-B)[0]
            f = fav[0] if len(fav) else 10**9; a = adv[0] if len(adv) else 10**9
            if f == a == 10**9: continue
            out.append({"kind":kind,"regime":regime,"touch":min(n,3),"reject": f < a})
    return out

T = pd.DataFrame(touches("cr") + touches("ps"))
print("TEST C — HVL regime separation.  'reject' = price moved 10pts AWAY before 10pts THROUGH\n")
print("MenthorQ claim: above HVL levels should REJECT (mean-revert); below HVL they should BREAK.\n")
for kind, lbl in [("cr","CALL RESISTANCE"), ("ps","PUT SUPPORT")]:
    sub = T[T.kind == kind]
    print(f"  {lbl}")
    for reg in ["above HVL (+gamma)", "below HVL (-gamma)"]:
        r = sub[sub.regime == reg]
        if len(r) < 15: print(f"    {reg:22} n={len(r):>4}  (too few)"); continue
        se = 0.5/np.sqrt(len(r))*100
        print(f"    {reg:22} n={len(r):>4}  reject {r.reject.mean()*100:5.1f}%  (+/-{se:.1f})")
    a = sub[sub.regime.str.startswith("above")].reject
    b_ = sub[sub.regime.str.startswith("below")].reject
    if len(a) > 15 and len(b_) > 15:
        diff = (a.mean()-b_.mean())*100
        se = np.sqrt(a.mean()*(1-a.mean())/len(a) + b_.mean()*(1-b_.mean())/len(b_))*100
        print(f"    {'SEPARATION':22} {diff:+.1f}pp  (se {se:.1f})  "
              f"{'SIGNIFICANT' if abs(diff) > 2*se else 'not significant'}\n")

print("\n  --- by touch number (their rule: skip the 1st test) ---")
for kind, lbl in [("cr","CR"), ("ps","PS")]:
    for n in (1, 2, 3):
        r = T[(T.kind == kind) & (T.touch == n)]
        if len(r) < 15: continue
        print(f"    {lbl} touch {n}: n={len(r):>4}  reject {r.reject.mean()*100:5.1f}%  (+/-{0.5/np.sqrt(len(r))*100:.1f})")
