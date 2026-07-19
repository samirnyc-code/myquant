"""TEST E — 'no man's land' claim.

MenthorQ (Location transcript):
  "let's say you had a selloff where there was no major gamma levels, no major blind
   spot levels - it basically sold off in no man's land - then maybe question: this
   selloff doesn't really make sense for it to continue, because it never reacted
   from an important level."

Claim: an impulse that ORIGINATES at a gamma level continues better than one that
originates away from any level.

This treats levels as the ORIGIN of sustainable moves, not as barriers - the opposite
framing to everything tested so far.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

fr = []
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d = pd.read_parquet(f); d["contract"] = os.path.basename(f).split(".")[0]; fr.append(d)
ES = pd.concat(fr, ignore_index=True); ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
vol = ES.groupby(["date","contract"]).Volume.sum().reset_index()
front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES = ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime").reset_index(drop=True)
pc = ES.Close.shift(1)
tr = pd.concat([ES.High-ES.Low, (ES.High-pc).abs(), (ES.Low-pc).abs()], axis=1).max(axis=1)
ES["atr"] = tr.rolling(14).mean()
bars = {d: g.reset_index(drop=True) for d, g in ES.groupby("date")}

S = pd.read_csv(ROOT/"data"/"spx_daily_full.csv"); S["Date"] = S.Date.astype(str); S = S.set_index("Date")
V = pd.read_csv(ROOT/"data"/"vix_daily_full.csv"); V["Date"] = V.Date.astype(str); V = V.set_index("Date")
esC = ES.groupby("date").Close.last()
common = sorted(set(esC.index) & set(S.index))
basis = esC.loc[common] - S.Close.loc[common]

MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"] = MQ.session_date.astype(str); MQ = MQ.set_index("session_date")

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
        L = [float(p.idxmax()), float(p.idxmin()), float(fb.cumsum().idxmin())]
        if d in MQ.index:                      # + MQ's 1D band and GEX 1-4
            m = MQ.loc[d]
            for k in ["d1_min","d1_max"] + [f"gex_{i}" for i in range(1,5)]:
                if pd.notna(m.get(k)): L.append(float(m[k]))
        lv[d] = L

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}

IMP, WIN = 1.5, 6      # impulse = 1.5 ATR inside 6 bars (30 min)
rows = []
for d in lv:
    s = nxt.get(d)
    if s is None or s not in bars or d not in basis.index: continue
    b = bars[s]
    if len(b) < 30 or b.atr.isna().all(): continue
    atr = float(b.atr.iloc[0])
    if not np.isfinite(atr) or atr <= 0: continue
    L = np.array(lv[d]) + float(basis.loc[d])          # levels in ES terms
    hi, lo, cl = b.High.values, b.Low.values, b.Close.values
    # find first impulse: |close[i+WIN] - close[i]| >= IMP*ATR
    for i in range(0, len(b)-WIN-6):
        mv = cl[i+WIN] - cl[i]
        if abs(mv) < IMP*atr: continue
        direction = np.sign(mv)
        origin = cl[i]
        # did the impulse START at a level? (origin within 1 ATR of any level)
        near = np.min(np.abs(L - origin))
        at_level = near <= atr
        # continuation: further move in same direction over the REST of the session
        rest = slice(i+WIN, len(b))
        if direction > 0:
            cont = (hi[rest].max() - cl[i+WIN])/atr
        else:
            cont = (cl[i+WIN] - lo[rest].min())/atr
        rows.append({"date": s, "at_level": at_level, "cont": cont,
                     "near_atr": near/atr, "dir": direction})
        break                                            # one impulse per session

R = pd.DataFrame(rows)
print("TEST E — does an impulse that ORIGINATES at a gamma level continue better?\n")
print(f"impulse = {IMP} ATR within {WIN} bars (30min). continuation measured in ATR, rest of session.")
print(f"levels used: our CR/PS/HVL + MQ 1D min/max + GEX 1-4   (origin 'at level' = within 1 ATR)\n")
print(f"  n sessions with an impulse: {len(R)}")
a = R[R.at_level].cont; b_ = R[~R.at_level].cont
print(f"    origin AT a level     : n={len(a):>4}  median continuation {a.median():5.2f} ATR  mean {a.mean():5.2f}")
print(f"    origin NO MAN'S LAND  : n={len(b_):>4}  median continuation {b_.median():5.2f} ATR  mean {b_.mean():5.2f}")
if len(a) > 15 and len(b_) > 15:
    se = np.sqrt(a.var()/len(a) + b_.var()/len(b_))
    diff = a.mean()-b_.mean()
    print(f"    difference in mean    : {diff:+.2f} ATR  (se {se:.2f}, {diff/se:+.1f} sd)")
    print(f"    VERDICT: {'SUPPORTS the claim' if diff > 2*se else 'does NOT support the claim'}")
print()
print("  continuation by distance of origin from nearest level (ATR units):")
R["bucket"] = pd.cut(R.near_atr, [0,0.5,1,2,4,99], labels=["<0.5","0.5-1","1-2","2-4",">4"])
g = R.groupby("bucket", observed=True).cont.agg(["size","median","mean"]).round(2)
print(g.to_string())
