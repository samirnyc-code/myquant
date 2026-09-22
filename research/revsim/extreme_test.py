"""Test the user's read: reversals ONLY at a genuine EXTREME, and NOT in a dead TR.
Extreme is measured at the REVERSAL bar (rb = FT bar - 1) — the bar that made the
high/low — not the follow-through bar (my earlier bug).

Features at the reversal bar (all causal, computed on the continuous 5M series):
  ext{X}   : rb high (short) / low (long) is the max/min of the last X bars (a swing extreme)
  poke{X}  : ticks the rb extreme pokes BEYOND the prior X-bar extreme (>0 = sticks out)
  er{N}    : Kaufman efficiency ratio over N bars (|dC| / sum|dC|), high = trending/energy
  adx{N}   : ADX (trend strength)
  emaslp   : EMA20 slope over 10 bars (points)
Base signals = strong-FT (FT_ABR>=1). EOD hold. Report per-year + OOS; no cherry-pick;
require BOTH halves positive AND not carried by one year.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, engine_ticks as E
import swing_level_gated as G
TICK = 0.25


def ema(x, span):
    a = 2/(span+1); o = np.empty_like(x, float); o[0] = x[0]
    for i in range(1, len(x)): o[i] = a*x[i] + (1-a)*o[i-1]
    return o

def adx(H, L, C, n=14):
    up = H[1:]-H[:-1]; dn = L[:-1]-L[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(H[1:]-L[1:], np.maximum(np.abs(H[1:]-C[:-1]), np.abs(L[1:]-C[:-1])))
    def rma(a):
        o = np.empty_like(a); o[0] = a[:n].mean() if len(a) >= n else a[0]
        for i in range(1, len(a)): o[i] = (o[i-1]*(n-1)+a[i])/n
        return o
    atr = rma(tr); pdi = 100*rma(pdm)/np.where(atr == 0, 1, atr); ndi = 100*rma(ndm)/np.where(atr == 0, 1, atr)
    dx = 100*np.abs(pdi-ndi)/np.where((pdi+ndi) == 0, 1, pdi+ndi)
    ax = rma(dx)
    return np.concatenate([[np.nan], ax])   # align to len

def er(C, n=10):
    out = np.full(len(C), np.nan)
    for i in range(n, len(C)):
        change = abs(C[i]-C[i-n]); vol = np.abs(np.diff(C[i-n:i+1])).sum()
        out[i] = change/vol if vol > 0 else 0
    return out


df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
d = df5.sort_values("DateTime").reset_index(drop=True)
H, L, C = d.High.values, d.Low.values, d.Close.values
e20 = ema(C, 20); ADX = adx(H, L, C, 14); ER = er(C, 10)
# rolling extremes (max/min of prior X bars, EXCLUDING current, for the poke)
def roll_ext(arr, X, fn):
    s = pd.Series(arr); return s.rolling(X).apply(lambda v: fn(v), raw=True).values

sma = G.sma20d_map(df5)
sg = RD.detect(df5, {"FT_ABR": 1.0})
print(f"{len(sg)} strong-FT signals")

rb = sg["rb"].values.astype(int)
def feat_ext(X):
    # is rb the X-bar extreme, and how far it pokes beyond prior X-bar extreme
    hiX = pd.Series(H).rolling(X).max().values      # max incl current
    loX = pd.Series(L).rolling(X).min().values
    hiXprev = pd.Series(H).shift(1).rolling(X).max().values  # prior X bars (excl rb)
    loXprev = pd.Series(L).shift(1).rolling(X).min().values
    is_ext = np.where(sg.side.values > 0, L[rb] <= loX[rb] + 1e-9, H[rb] >= hiX[rb] - 1e-9)
    poke = np.where(sg.side.values > 0, (loXprev[rb] - L[rb]), (H[rb] - hiXprev[rb]))  # >0 = sticks out
    return is_ext, poke

for X in [10, 15, 20]:
    ie, pk = feat_ext(X); sg[f"ext{X}"] = ie; sg[f"poke{X}"] = pk
sg["er"] = ER[rb]; sg["adx"] = ADX[rb]
sg["emaslp"] = e20[rb] - e20[np.maximum(rb-10, 0)]

print("feature coverage:")
for X in [10, 15, 20]:
    print(f"  ext{X}: {100*sg[f'ext{X}'].mean():.0f}% at extreme   poke{X}>0: {100*(sg[f'poke{X}']>0).mean():.0f}%")
print(f"  er median {np.nanmedian(sg.er):.2f}  adx median {np.nanmedian(sg.adx):.1f}")


def run(name, mask, cfg):
    sub = sg[mask]
    tr = R.sim(sub, sma=sma, **cfg)
    if len(tr) == 0: return None, None
    tr["d"] = pd.to_datetime(tr["Date"]); trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo, al = E.metrics(trn), E.metrics(oos), E.metrics(tr)
    yr = E.by_year(tr); wy = int((yr.pnl > 0).sum())
    return dict(cfg=name, n=al["n"], pnl=al["pnl"], pf=al["pf"], ndd=al["netdd"], shp=al["sharpe"],
                tr_pf=mt["pf"], tr_pnl=mt["pnl"], oo_pf=mo["pf"], oo_pnl=mo["pnl"],
                green=f"{wy}/{len(yr)}", both=(mt["pnl"] > 0 and mo["pnl"] > 0)), yr

S = sg
cfg = {"entry": "market", "hold_eod": True}
tests = [
    ("baseline strong-FT", pd.Series(True, index=S.index)),
    ("ext10", S.ext10), ("ext20", S.ext20),
    ("ext20+poke", S.ext20 & (S.poke20 > 0)),
    ("er>0.3", S.er > 0.3), ("er>0.4", S.er > 0.4),
    ("adx>20", S.adx > 20), ("adx>25", S.adx > 25),
    ("ext20 & er>0.3", S.ext20 & (S.er > 0.3)),
    ("ext20 & adx>20", S.ext20 & (S.adx > 20)),
    ("ext20 & er>0.3 & adx>20", S.ext20 & (S.er > 0.3) & (S.adx > 20)),
    ("ext20+poke & er>0.3 & adx>20", S.ext20 & (S.poke20 > 0) & (S.er > 0.3) & (S.adx > 20)),
    # + below-SMA20 combined with extreme
    ("ext20 & er>0.3 & below", S.ext20 & (S.er > 0.3)),
]
rows = []; yrs = {}
for name, m in tests:
    extra = {}
    if "below" in name: extra["gate"] = "below"
    r, yr = run(name, m.fillna(False) if hasattr(m, "fillna") else m, {**cfg, **extra})
    if r: rows.append(r); yrs[name] = yr
D = pd.DataFrame(rows).sort_values("ndd", ascending=False)
pd.set_option("display.width", 200)
print("\n=== EXTREME + NOT-TR TEST (strong-FT base, EOD hold) ===")
print(D.to_string(index=False))
for name in list(D[D.both].sort_values("ndd", ascending=False).cfg)[:4]:
    print(f"\nPER-YEAR {name}:"); print(yrs[name].to_string())
D.to_csv(ROOT / "research" / "revsim" / "sweep_extreme.csv", index=False)
print("\nDONE_EXT")
