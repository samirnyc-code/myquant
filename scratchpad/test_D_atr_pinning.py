"""TEST D — MenthorQ's ATR pinning / breakout rule, as stated on video.

Their rule (transcript: 'Strategies to trade levels'):
  pinning zone = level +/- 1 x ATR(14) on 5-min bars
  "If you want to take a breakout trade on call resistance, WAIT FOR THE ATR.
   It's much more likely that you have follow-through if you're ABOVE the pinning area."

Claim under test: after price reaches a level, clearing level + 1*ATR produces more
follow-through than not clearing it.

THE CONTROL THAT MATTERS: run the identical rule at distance-matched RANDOM levels.
If clearing +1 ATR predicts follow-through everywhere, it is momentum, not gamma.
Gamma only earns credit if the effect is BIGGER at CR/PS than at random levels.
"""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(47)

fr = []
for f in sorted(glob.glob(str(ROOT/"data"/"bars"/"ES*.parquet"))):
    d = pd.read_parquet(f); d["contract"] = os.path.basename(f).split(".")[0]; fr.append(d)
ES = pd.concat(fr, ignore_index=True); ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
vol = ES.groupby(["date","contract"]).Volume.sum().reset_index()
front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"].to_dict()
ES = ES[[c == front.get(d) for d, c in zip(ES.date, ES.contract)]].sort_values("DateTime").reset_index(drop=True)

# --- 5-min ATR(14), continuous across sessions (as a chart indicator would be) ---
pc = ES.Close.shift(1)
tr = pd.concat([ES.High-ES.Low, (ES.High-pc).abs(), (ES.Low-pc).abs()], axis=1).max(axis=1)
ES["atr"] = tr.rolling(14).mean()
ES["volma"] = ES.Volume.rolling(20).mean()
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

def events(kind, randomize=False):
    """One event per session: first arrival at the level's ATR zone."""
    out = []
    for d in lv:
        s = nxt.get(d)
        if s is None or s not in bars or d not in basis.index or d not in S.index: continue
        spot = float(S.Close.loc[d])
        dist = (lv[d][kind]-spot) if kind == "cr" else (spot-lv[d][kind])
        if dist < 0 or dist/spot*100 > 1.0: continue
        if randomize:                       # distance-matched random level
            dist = rng.uniform(0.10, 1.0)/100*spot
        L = (spot + dist if kind == "cr" else spot - dist) + float(basis.loc[d])
        b = bars[s]
        if b.atr.isna().all(): continue
        atr = float(b.atr.iloc[0])
        if not np.isfinite(atr) or atr <= 0: continue
        hi, lo, cl, vv, vm = (b.High.values, b.Low.values, b.Close.values,
                              b.Volume.values, b.volma.values)
        # first arrival into the pinning zone
        arr = np.where(hi >= L-atr)[0] if kind == "cr" else np.where(lo <= L+atr)[0]
        if len(arr) == 0: continue
        i0 = arr[0]
        post = slice(i0, len(b))
        # did it CLEAR the pinning area (beyond level +/- 1 ATR)?
        if kind == "cr":
            clr = np.where(cl[post] > L+atr)[0]
        else:
            clr = np.where(cl[post] < L-atr)[0]
        cleared = len(clr) > 0
        if cleared:
            j = i0 + clr[0]
            entry = cl[j]
            volok = bool(np.isfinite(vm[j]) and vv[j] > vm[j])
            # follow-through AFTER clearing, in ATR units
            if kind == "cr":
                ft = (hi[j:].max() - entry)/atr
            else:
                ft = (entry - lo[j:].min())/atr
        else:
            j = i0; entry = cl[i0]; volok = None
            if kind == "cr":
                ft = (hi[i0:].max() - entry)/atr
            else:
                ft = (entry - lo[i0:].min())/atr
        out.append({"cleared": cleared, "ft": ft, "volok": volok})
    return pd.DataFrame(out)

print("TEST D — ATR pinning rule. zone = level +/- 1*ATR(14,5min). ES bars.\n")
print("follow-through measured in ATR units, from the clearing bar (or arrival if never cleared)\n")
for kind, lbl in [("cr","CALL RESISTANCE"), ("ps","PUT SUPPORT")]:
    real = events(kind)
    ctrl = pd.concat([events(kind, randomize=True) for _ in range(5)], ignore_index=True)
    print(f"  {lbl}   (n={len(real)} real events)")
    for nm, D in [("GAMMA level", real), ("random level", ctrl)]:
        c = D[D.cleared]; n = D[~D.cleared]
        if len(c) < 10 or len(n) < 10:
            print(f"    {nm:14} insufficient"); continue
        se = np.sqrt(c.ft.var()/len(c) + n.ft.var()/len(n))
        print(f"    {nm:14} cleared +1ATR: n={len(c):>4} median FT {c.ft.median():5.2f} ATR | "
              f"not cleared: n={len(n):>4} median FT {n.ft.median():5.2f} ATR | "
              f"mean diff {c.ft.mean()-n.ft.mean():+5.2f} (se {se:.2f})")
    # does volume confirmation add anything?
    c = real[real.cleared]
    if len(c) > 20 and c.volok.notna().any():
        a = c[c.volok == True].ft; b_ = c[c.volok == False].ft
        if len(a) > 8 and len(b_) > 8:
            print(f"    volume filter  with vol: n={len(a):>4} median FT {a.median():5.2f} | "
                  f"without: n={len(b_):>4} median FT {b_.median():5.2f}")
    print()
