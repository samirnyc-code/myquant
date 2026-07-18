"""Do the levels actually WORK in price? Head-to-head: our ORATS-computed levels
vs MenthorQ's, plus a shifted-level CONTROL.

Design: levels computed from chain date D apply to the NEXT trading session D+1
(that is how MQ publishes them). For each level L and session D+1 with H/L/C:
  touch      = low <= L <= high
  rejection  = touched AND close on the expected side (CR: close<L ; PS: close>L)
  penetration= how far price pushed THROUGH the level (pts beyond), given touch
Control = same level shifted by a random +/-20..40 pts (is the exact strike special,
or would any nearby price do?).
"""
import glob
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(7)

px = pd.read_csv(ROOT/"data"/"options_sim"/"spx_daily_yahoo.csv")
px["Date"] = px.Date.astype(str)
px = px.sort_values("Date").reset_index(drop=True)
sessions = px.Date.tolist()
nxt = {d: sessions[i+1] for i, d in enumerate(sessions[:-1])}
P = px.set_index("Date")

MQ = pd.read_csv(ROOT/"data"/"menthorq"/"SPX_mq_levels_history.csv")
MQ["session_date"] = MQ.session_date.astype(str)
MQ = MQ.set_index("session_date")

# ---- our levels per chain date (with corrupt-greek filter) ----
ours = {}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_202[456].parquet"))):
    yr = pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c] = pd.to_numeric(yr[c], errors="coerce")
    yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
    for d, g in yr.groupby("tradeDate"):
        d = str(d)
        spot = g["spotPrice"].median()
        p = (g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum()
        p = p[np.isfinite(p)]
        if p.empty: continue
        fb = p[(p.index >= spot*0.90) & (p.index <= spot*1.10)]
        ours[d] = {"cr": p.idxmax(), "ps": p.idxmin(),
                   "hvl": fb.cumsum().idxmin() if not fb.empty else np.nan,
                   "spot": spot}

def evaluate(get_level, kind, label, shift=False):
    """kind: 'cr' (resistance) or 'ps' (support)."""
    touch=rej=n=0; pens=[]
    for d in ours:
        s = nxt.get(d)
        if s is None or s not in P.index: continue
        L = get_level(d)
        if L is None or not np.isfinite(L): continue
        if shift:
            L = L + rng.choice([-1,1])*rng.uniform(20,40)
        hi, lo, cl = P.loc[s,"High"], P.loc[s,"Low"], P.loc[s,"Close"]
        n += 1
        if lo <= L <= hi:
            touch += 1
            if kind=="cr":
                rej += cl < L
                pens.append(hi - L)          # how far through resistance
            else:
                rej += cl > L
                pens.append(L - lo)          # how far through support
    if not touch:
        print(f"  {label:34} no touches"); return
    print(f"  {label:34} n={n:4d}  touch {touch/n*100:5.1f}%  "
          f"hold|touch {rej/touch*100:5.1f}%  med penetration {np.median(pens):6.1f} pts")

print("=== RESISTANCE (Call Resistance) ===")
evaluate(lambda d: ours[d]["cr"], "cr", "OURS  cr")
evaluate(lambda d: MQ.loc[d,"cr"] if d in MQ.index else None, "cr", "MQ    cr")
evaluate(lambda d: ours[d]["cr"], "cr", "CONTROL ours cr shifted", shift=True)

print("\n=== SUPPORT (Put Support) ===")
evaluate(lambda d: ours[d]["ps"], "ps", "OURS  ps")
evaluate(lambda d: MQ.loc[d,"ps"] if d in MQ.index else None, "ps", "MQ    ps")
evaluate(lambda d: ours[d]["ps"], "ps", "CONTROL ours ps shifted", shift=True)

# ---- HVL regime test: is realized range bigger BELOW hvl (neg gamma) ? ----
print("\n=== HVL REGIME (expect: below HVL = higher realized range) ===")
for lbl, getl in [("OURS hvl", lambda d: ours[d]["hvl"]),
                  ("MQ   hvl", lambda d: MQ.loc[d,"hvl"] if d in MQ.index else np.nan)]:
    above=[]; below=[]
    for d in ours:
        s = nxt.get(d)
        if s is None or s not in P.index: continue
        L = getl(d)
        if L is None or not np.isfinite(L): continue
        rng_pct = (P.loc[s,"High"]-P.loc[s,"Low"])/P.loc[s,"Close"]*100
        (above if P.loc[s,"Close"] > L else below).append(rng_pct)
    if above and below:
        print(f"  {lbl}: close ABOVE hvl -> med range {np.median(above):.2f}%  (n={len(above)}) | "
              f"BELOW -> {np.median(below):.2f}%  (n={len(below)})")
