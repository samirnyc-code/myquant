"""TEST G — EXPECTANCY, not hit rate.

MenthorQ are explicit that hit rate is the wrong metric:
  Patrick: "if you have a win rate of 90, 80, 70% they will say you're doing the wrong
   job... cut your losses very fast... sometimes you have only a win rate of 30%...
   you need only a few times but sometimes a very huge trade."
  Fabio:   "the goal is not to make you all the successful trade but to help you
   manage the risk."

Their claim is about PAYOFF GEOMETRY: at a level you can place a tight stop just beyond
it ("call resistance protection - that's my team") while targeting something far away.

TEST: fade the level with a fixed stop of 1 ATR beyond it, and a target of R x that
distance. Simulate bar-by-bar which is hit first. Report EXPECTANCY in R.
CONTROL: identical geometry, identical stop/target distances, at RANDOM prices.
If the level adds nothing, expectancy will match the control at every R.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(101)

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
        if d in MQ.index:
            m = MQ.loc[d]
            for k in ["d1_min","d1_max"] + [f"gex_{i}" for i in range(1,5)]:
                if pd.notna(m.get(k)): L.append(float(m[k]))
        lv[d] = L

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}

def trades(Rmult, randomize=False):
    """Fade the level: short if approached from below, long if from above.
       stop = 1 ATR beyond the level. target = Rmult * that distance."""
    out = []
    for d in lv:
        s = nxt.get(d)
        if s is None or s not in bars or d not in basis.index: continue
        b = bars[s]
        if len(b) < 20 or b.atr.isna().all(): continue
        atr = float(b.atr.iloc[0])
        if not np.isfinite(atr) or atr <= 0: continue
        hi, lo, cl = b.High.values, b.Low.values, b.Close.values
        open_px = float(b.Open.iloc[0]); bs = float(basis.loc[d])
        levels = ([x + bs for x in lv[d]] if not randomize
                  else [open_px + rng.uniform(-1.5, 1.5)*atr*4 for _ in lv[d]])
        for L in levels:
            above = L > open_px
            arr = np.where(hi >= L)[0] if above else np.where(lo <= L)[0]
            if len(arr) == 0 or arr[0] >= len(b)-2: continue
            i0 = arr[0]
            if above:   # fade = short at resistance
                stop, targ = L + atr, L - Rmult*atr
                st = np.where(hi[i0+1:] >= stop)[0]
                tg = np.where(lo[i0+1:] <= targ)[0]
            else:       # fade = long at support
                stop, targ = L - atr, L + Rmult*atr
                st = np.where(lo[i0+1:] <= stop)[0]
                tg = np.where(hi[i0+1:] >= targ)[0]
            si = st[0] if len(st) else 10**9
            ti = tg[0] if len(tg) else 10**9
            if si == ti == 10**9:                      # neither hit: mark to close
                exitp = cl[-1]
                r = ((L-exitp) if above else (exitp-L))/atr
            else:
                r = -1.0 if si < ti else float(Rmult)
            out.append(r)
    return np.array(out)

print("TEST G — EXPECTANCY in R.  fade the level, stop 1 ATR beyond, target R x ATR.\n")
print("  (their own framing: hit rate is NOT the metric; asymmetry is)\n")
print(f"  {'target':>8}{'n':>7}{'win%':>8}{'expectancy(R)':>16}{'  |  ':>5}{'n':>7}{'win%':>8}{'expectancy(R)':>16}")
print(f"  {'':>8}{'--- GAMMA LEVELS ---':>31}{'  |  ':>5}{'--- RANDOM LEVELS ---':>31}")
for Rm in [1.0, 1.5, 2.0, 3.0]:
    a = trades(Rm); c = np.concatenate([trades(Rm, True) for _ in range(3)])
    wa = (a > 0).mean()*100; wc = (c > 0).mean()*100
    sea = a.std()/np.sqrt(len(a)); sec = c.std()/np.sqrt(len(c))
    print(f"  {Rm:>8.1f}{len(a):>7}{wa:>7.1f}%{a.mean():>12.3f} +/-{sea:.3f}{'  |  ':>5}"
          f"{len(c):>7}{wc:>7.1f}%{c.mean():>12.3f} +/-{sec:.3f}")
print("\n  positive expectancy at gamma levels AND above the random control = a real edge.")
