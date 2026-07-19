"""TEST H — SECOND-TOUCH FADE AT THE ATR ZONE EDGE.

Rationale (Samir): levels get front-run, so the reaction happens at the EDGE of the
zone, not at the level. Every prior test measured at the level itself and would miss
this by construction.

SETUP (fade, counter to the approach):
  zone      = level +/- 1 x ATR(14, 5-min, gap-adjusted)
  touch     = price enters the zone from outside; a NEW touch requires leaving first
  entry     = at the near zone edge, on the Nth touch (N = 1 and 2 both reported)
  stop      = far side of the zone (level +/- 1 ATR on the other side)  -> risk ~ 2 ATR
  target    = R x risk
  costs     = 1.25 ES pts all-in

CONTROL: identical logic - including the touch counting - at distance-matched RANDOM
levels. This is essential: 2nd touches are pre-selected for mean reversion, so the
control must inherit the same selection.

FULL GRID REPORTED. No configuration is dropped.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(2029)
COST = 1.25

fr = []
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d = pd.read_parquet(f); d["contract"] = os.path.basename(f).split(".")[0]; fr.append(d)
ES = pd.concat(fr, ignore_index=True); ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
vol = ES.groupby(["date","contract"]).Volume.sum().reset_index()
front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES = ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime").reset_index(drop=True)
ES["bar"] = ES.groupby("date").cumcount()
pc = ES.Close.shift(1)
tr = pd.concat([ES.High-ES.Low, (ES.High-pc).abs(), (ES.Low-pc).abs()], axis=1).max(axis=1)
ES["atr"] = pd.Series(np.where(ES.bar == 0, ES.High-ES.Low, tr)).rolling(14).mean()
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
        p = (g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum()
        p = p[np.isfinite(p)]
        if not p.empty:
            lv[str(d)] = {"cr": float(p.idxmax()), "ps": float(p.idxmin())}

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}


def trades(kind, touch_no, Rm, randomize=False):
    out = []
    for d in lv:
        s = nxt.get(d)
        if s is None or s not in bars or d not in basis.index or d not in S.index: continue
        spot = float(S.Close.loc[d])
        dist = (lv[d][kind]-spot) if kind == "cr" else (spot-lv[d][kind])
        if dist < 0 or dist/spot*100 > 1.0: continue
        if randomize: dist = rng.uniform(0.10, 1.0)/100*spot
        L = (spot+dist if kind == "cr" else spot-dist) + float(basis.loc[d])
        b = bars[s]
        if b.atr.isna().all(): continue
        atr = float(b.atr.iloc[0])
        if not np.isfinite(atr) or atr <= 0: continue
        hi, lo, cl = b.High.values, b.Low.values, b.Close.values
        near = L - atr if kind == "cr" else L + atr     # the edge price arrives at first
        far  = L + atr if kind == "cr" else L - atr     # stop lives beyond here
        inzone = (hi >= near) if kind == "cr" else (lo <= near)
        idxs, armed = [], True
        for i, z in enumerate(inzone):
            if z and armed: idxs.append(i); armed = False
            elif not z: armed = True
        if len(idxs) < touch_no: continue
        i0 = idxs[touch_no-1]
        if i0 >= len(b)-3: continue
        entry = near                                   # filled at the zone edge
        risk = abs(far - entry)
        if risk <= 0: continue
        if kind == "cr":                               # fade a resistance = short
            stop, targ = far, entry - Rm*risk
            st = np.where(hi[i0+1:] >= stop)[0]; tg = np.where(lo[i0+1:] <= targ)[0]
        else:                                          # fade a support = long
            stop, targ = far, entry + Rm*risk
            st = np.where(lo[i0+1:] <= stop)[0]; tg = np.where(hi[i0+1:] >= targ)[0]
        si = st[0] if len(st) else 10**9
        ti = tg[0] if len(tg) else 10**9
        if si == ti == 10**9:
            ex = cl[-1]
            r = ((entry-ex) if kind == "cr" else (ex-entry))/risk
        else:
            r = -1.0 if si < ti else float(Rm)
        out.append(r - COST/risk)
    return np.array(out)


print("TEST H - fade at the ATR ZONE EDGE (front-running hypothesis)")
print("entry at near zone edge | stop at far edge (risk ~2 ATR) | costs 1.25 pts\n")
print(f"  {'touch':>6}{'target':>8}{'':>3}{'n':>6}{'win%':>7}{'expectancy':>13}"
      f"{'':>4}{'n':>6}{'win%':>7}{'expectancy':>13}{'':>4}{'edge':>8}")
print(f"  {'':>6}{'':>8}{'':>3}{'------- GAMMA ZONE -------':>26}"
      f"{'':>4}{'------ RANDOM ZONE ------':>26}")
for tn in (1, 2, 3):
    for Rm in (1.0, 1.5, 2.0):
        a = np.concatenate([trades("cr", tn, Rm), trades("ps", tn, Rm)])
        c = np.concatenate([trades("cr", tn, Rm, True) for _ in range(4)] +
                           [trades("ps", tn, Rm, True) for _ in range(4)])
        if len(a) < 12:
            print(f"  {tn:>6}{Rm:>8.1f}{'':>3}{len(a):>6}   (too few)"); continue
        sea = a.std()/np.sqrt(len(a)); sec = c.std()/np.sqrt(len(c))
        edge = a.mean()-c.mean(); see = np.sqrt(sea**2+sec**2)
        print(f"  {tn:>6}{Rm:>8.1f}{'':>3}{len(a):>6}{(a>0).mean()*100:>6.1f}%"
              f"{a.mean():>9.3f}+/-{sea:.3f}"
              f"{'':>4}{len(c):>6}{(c>0).mean()*100:>6.1f}%{c.mean():>9.3f}+/-{sec:.3f}"
              f"{'':>4}{edge:>+7.3f} ({edge/see:+.1f}sd)")
    print()
