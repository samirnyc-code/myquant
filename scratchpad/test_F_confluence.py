"""TEST F — CONFLUENCE, the claim MenthorQ emphasises most.

Fabio (CEO): "combining gamma levels, blind spots - when there is OVERLAPPING areas,
especially around the primary level - those become really important reaction zones."
Patrick: "we're not looking into price areas, we're looking more into zones, in clusters."

Claim: price reacts MORE at prices where several levels cluster than at isolated levels.

Method: for each session, take all available levels (our CR/PS/HVL + MQ 1D min/max +
GEX 1-10). Cluster them at 1-ATR tolerance. Then measure the reaction when price first
reaches each cluster, split by how many levels it contains.
If confluence is real, reaction should INCREASE with cluster size.
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
            for k in ["d1_min","d1_max"] + [f"gex_{i}" for i in range(1,11)]:
                if pd.notna(m.get(k)): L.append(float(m[k]))
        lv[d] = sorted(L)

sess = sorted(set(basis.index) & set(bars))
nxt = {d: sess[i+1] for i, d in enumerate(sess[:-1])}

def cluster(levels, tol):
    """group levels within tol of each other -> (centre, count)"""
    out, cur = [], [levels[0]]
    for x in levels[1:]:
        if x - cur[-1] <= tol: cur.append(x)
        else: out.append((float(np.mean(cur)), len(cur))); cur = [x]
    out.append((float(np.mean(cur)), len(cur)))
    return out

rows = []
for d in lv:
    s = nxt.get(d)
    if s is None or s not in bars or d not in basis.index: continue
    b = bars[s]
    if len(b) < 20 or b.atr.isna().all(): continue
    atr = float(b.atr.iloc[0])
    if not np.isfinite(atr) or atr <= 0: continue
    hi, lo, cl = b.High.values, b.Low.values, b.Close.values
    open_px = float(b.Open.iloc[0])
    for centre, cnt in cluster(lv[d], atr):
        L = centre + float(basis.loc[d])
        above = L > open_px                      # approach direction
        arr = np.where(hi >= L)[0] if above else np.where(lo <= L)[0]
        if len(arr) == 0: continue
        i0 = arr[0]
        if i0 >= len(b)-3: continue
        post = slice(i0, len(b))
        # reaction = max move AWAY from the level after first touch, in ATR
        react = (L - lo[post].min())/atr if above else (hi[post].max() - L)/atr
        # penetration = max move THROUGH the level
        pen = (hi[post].max() - L)/atr if above else (L - lo[post].min())/atr
        rows.append({"n_levels": min(cnt,4), "react": react, "pen": pen,
                     "rejected": react > pen})
R = pd.DataFrame(rows)
print("TEST F — CONFLUENCE. clusters formed at 1-ATR tolerance.\n")
print("  reaction = max move AWAY from level after first touch (ATR)")
print("  penetration = max move THROUGH it (ATR);  rejected = reaction > penetration\n")
print(f"  {'levels in cluster':>18}{'n':>7}{'med reaction':>14}{'med penetration':>17}{'rejected %':>12}")
for k in sorted(R.n_levels.unique()):
    g = R[R.n_levels == k]
    lbl = f"{k}" if k < 4 else "4+"
    print(f"  {lbl:>18}{len(g):>7}{g.react.median():>14.2f}{g.pen.median():>17.2f}{g.rejected.mean()*100:>11.1f}%")
iso = R[R.n_levels == 1]; conf = R[R.n_levels >= 3]
if len(iso) > 20 and len(conf) > 20:
    se = np.sqrt(iso.react.var()/len(iso) + conf.react.var()/len(conf))
    d_ = conf.react.mean() - iso.react.mean()
    print(f"\n  cluster(3+) vs isolated: reaction diff {d_:+.2f} ATR (se {se:.2f}, {d_/se:+.1f} sd)")
    pr_i, pr_c = iso.rejected.mean(), conf.rejected.mean()
    se2 = np.sqrt(pr_i*(1-pr_i)/len(iso) + pr_c*(1-pr_c)/len(conf))
    print(f"  rejected-rate diff {(pr_c-pr_i)*100:+.1f}pp (se {se2*100:.1f}pp, {(pr_c-pr_i)/se2:+.1f} sd)")
    print(f"  VERDICT: {'SUPPORTS confluence' if d_ > 2*se else 'does NOT support confluence'}")
