"""TEST A (pre-registered, docs/living/prereg_S75P.md) — CR/PS intraday repulsion.
Full sample now that SPX daily goes back to 1990 (basis available for every ES session)."""
import glob, os
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(23)

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

ours = {}
for f in sorted(glob.glob(str(ROOT/"data"/"orats"/"SPX"/"SPX_*.parquet"))):
    yr = pd.read_parquet(f)
    for c in ["strike","gamma","delta","callOpenInterest","putOpenInterest","dte","spotPrice"]:
        yr[c] = pd.to_numeric(yr[c], errors="coerce")
    yr = yr[(yr.dte > 1) & (yr.gamma.abs() < 0.1) & (yr.delta.abs() <= 1.01)]
    for d, g in yr.groupby("tradeDate"):
        p = (g.gamma*(g.callOpenInterest-g.putOpenInterest)).groupby(g.strike).sum()
        p = p[np.isfinite(p)]
        if not p.empty:
            ours[str(d)] = {"cr": float(p.idxmax()), "ps": float(p.idxmin())}

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}

Z, R, B, GATE = 5.0, 10.0, 10.0, 1.0   # pre-registered

def build(kind):
    rows = []
    for d in ours:
        s = nxt.get(d)
        if s is None or s not in bars or d not in basis.index or d not in S.index: continue
        L = ours[d][kind]; spot = float(S.Close.loc[d])
        dist = (L - spot) if kind == "cr" else (spot - L)
        if dist < 0 or dist/spot*100 > GATE: continue
        rows.append({"s": s, "spot": spot, "dist": dist, "basis": float(basis.loc[d])})
    return rows

def race(rows, kind, permute=False):
    rej = brk = 0
    dists = [r["dist"] for r in rows]
    for r in rows:
        dist = rng.choice(dists) if permute else r["dist"]
        L = (r["spot"] + dist if kind == "cr" else r["spot"] - dist) + r["basis"]
        b = bars[r["s"]]
        hit = np.where(b.High.values >= L-Z)[0] if kind == "cr" else np.where(b.Low.values <= L+Z)[0]
        if len(hit) == 0: continue
        post = b.iloc[hit[0]:]
        if kind == "cr":
            fav = np.where(post.Low.values  <= L-R)[0]; adv = np.where(post.High.values >= L+B)[0]
        else:
            fav = np.where(post.High.values >= L+R)[0]; adv = np.where(post.Low.values  <= L-B)[0]
        f = fav[0] if len(fav) else 10**9; a = adv[0] if len(adv) else 10**9
        if f == a == 10**9: continue
        rej += f < a; brk += a <= f
    tot = rej + brk
    return tot, (rej/tot*100 if tot else float("nan"))

print("TEST A — pre-registered. gate<=1.0% | zone +/-5 | race 10 vs 10 | perm control x20\n")
print(f"  {'level':6}{'days':>7}{'resolved':>10}{'REJECT':>9}{'CONTROL':>9}{'edge':>8}{'SE':>7}{'verdict':>12}")
for kind, lbl in [("cr","CR"), ("ps","PS")]:
    rows = build(kind)
    tot, pct = race(rows, kind)
    ctrl = [race(rows, kind, permute=True) for _ in range(20)]
    cpct = float(np.nanmean([c[1] for c in ctrl]))
    se = 0.5/np.sqrt(tot)*100 if tot else float("nan")
    edge = pct - cpct
    verdict = "PASS" if edge > 2*se else "no edge"
    print(f"  {lbl:6}{len(rows):>7}{tot:>10}{pct:>8.1f}%{cpct:>8.1f}%{edge:>+7.1f}{se:>7.1f}{verdict:>12}")
print("\n  (PASS requires edge > 2 SE, per pre-registration)")
