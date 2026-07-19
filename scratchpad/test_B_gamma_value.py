"""TEST B (pre-registered, docs/living/prereg_S75P.md) — does gamma add anything
beyond free price/vol/trend data for predicting next-session realized range?"""
import glob
import numpy as np, pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error
ROOT = Path(__file__).resolve().parents[1]

# ---------- price / vol baseline ----------
S = pd.read_csv(ROOT/"data"/"spx_daily_full.csv"); S["Date"] = S.Date.astype(str)
V = pd.read_csv(ROOT/"data"/"vix_daily_full.csv"); V["Date"] = V.Date.astype(str)
df = S.merge(V, on="Date").sort_values("Date").reset_index(drop=True)
df["rng"] = (df.High - df.Low)/df.Close*100
df["ma20"] = df.Close.rolling(20).mean()
df["ma20_dist"] = (df.Close - df.ma20)/df.Close*100
df["rng5"] = df.rng.rolling(5).mean()
df["rng20"] = df.rng.rolling(20).mean()
df["target"] = df.rng.shift(-1)          # next-session realized range
df = df.set_index("Date")

# ---------- gamma features from the ORATS chain ----------
rows = {}
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
        hvl = float(fb.cumsum().idxmin()); cr = float(p.idxmax()); ps = float(p.idxmin())
        a = p.abs()
        rows[d] = {"hvl_dist": (spot-hvl)/spot*100,
                   "cr_dist": (cr-spot)/spot*100,
                   "ps_dist": (spot-ps)/spot*100,
                   "net_gex": float(p.sum())/1e6,
                   "concentration": float(a.nlargest(3).sum()/a.sum()) if a.sum() > 0 else np.nan}
G = pd.DataFrame(rows).T
G.index.name = "Date"

D = df.join(G, how="inner").dropna(subset=["target","vix","ma20_dist","rng5","rng20",
                                           "hvl_dist","cr_dist","ps_dist","net_gex","concentration"])
BASE = ["vix","ma20_dist","rng5","rng20"]
GAM  = ["hvl_dist","cr_dist","ps_dist","net_gex","concentration"]

tr = D[D.index <= "2024-12-31"]
te = D[D.index >= "2025-01-01"]
print(f"TEST B — pre-registered.  train {tr.index.min()}..{tr.index.max()} (n={len(tr)})")
print(f"                          test  {te.index.min()}..{te.index.max()} (n={len(te)})\n")

def run(feats, seed):
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                      max_depth=4, random_state=seed)
    m.fit(tr[feats], tr.target)
    pr = m.predict(te[feats])
    return r2_score(te.target, pr), mean_absolute_error(te.target, pr)

res = {}
for lbl, feats in [("baseline (price/vol only)", BASE), ("baseline + GAMMA", BASE+GAM)]:
    sc = [run(feats, s) for s in range(5)]
    r2 = np.array([x[0] for x in sc]); mae = np.array([x[1] for x in sc])
    res[lbl] = (r2, mae)
    print(f"  {lbl:28} OOS R2 {r2.mean():+.4f} (spread {r2.max()-r2.min():.4f})   MAE {mae.mean():.4f}")

r2b, _ = res["baseline (price/vol only)"]; r2g, _ = res["baseline + GAMMA"]
gain = r2g.mean() - r2b.mean()
spread = max(r2b.max()-r2b.min(), r2g.max()-r2g.min())
print(f"\n  gamma gain in OOS R2: {gain:+.4f}   |  seed spread: {spread:.4f}")
print(f"  VERDICT: {'PASS — gamma adds signal' if gain > spread else 'FAIL — gamma adds nothing beyond free data'}")

# gamma-only, for context (not a pass/fail criterion)
sc = [run(GAM, s) for s in range(5)]
print(f"\n  (context) gamma features ALONE: OOS R2 {np.mean([x[0] for x in sc]):+.4f}")
