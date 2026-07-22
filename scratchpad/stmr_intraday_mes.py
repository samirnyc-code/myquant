# -*- coding: utf-8 -*-
"""STMR signal on intraday ES -> MES 1-contract, across timeframes. S80, SAVED (was inline).
Signal (canonical): %K8<15 & Close>SMA100 ; exit Close>SMA5. LONG only, one at a time, NO stop yet.
Source: data/bars/_continuous_1m.parquet (2021-06->2026-07). MES: $5/pt, $5 RT fee, 1-tick slip.
Writes a DATED trade list per timeframe -> scratchpad/intraday_trades/<tf>.csv so results are reproducible.
NEXT: tick-based stop+target sweep (intrabar scan of data/ticks_continuous/).
"""
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(r"c:\Users\Admin\myquant")
PT, FEE, SLIP = 5, 5, 0.25
OUT = ROOT / "scratchpad" / "intraday_trades"; OUT.mkdir(exist_ok=True)
d = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_1m.parquet")
d["DateTime"] = pd.to_datetime(d["DateTime"]); d = d.set_index("DateTime").sort_index()


def rs(df, m):
    return df if m == 1 else df.resample(f"{m}min").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()


def run(df, filt=False):
    C, H, L, O = df.Close, df.High, df.Low, df.Open
    s100 = C.rolling(100).mean(); s5 = C.rolling(5).mean()
    k8 = 100 * (C - L.rolling(8).min()) / (H.rolling(8).max() - L.rolling(8).min()).replace(0, np.nan)
    ibs = (C - L) / (H - L).replace(0, np.nan); body = (C - O).abs(); rng = (H - L)
    fok = ((ibs < 0.40) & ((body > rng / 2.7) | (body.shift(1) > rng.shift(1) / 2.5))).values
    ent = ((k8 < 15) & (C > s100)).values; exi = (C > s5).values
    Cv = C.values; s1 = s100.values; kv = k8.values; idx = df.index
    rows = []; inp = False
    for i in range(1, len(Cv)):
        if not inp and ent[i] and (not filt or fok[i]) and np.isfinite(s1[i]) and np.isfinite(kv[i]):
            e = Cv[i]; ei = i; inp = True; mae = 0.0
        elif inp:
            mae = min(mae, Cv[i] - e)
            if exi[i]:
                rows.append({"entry_dt": idx[ei], "exit_dt": idx[i], "entry": e, "exit": Cv[i],
                             "pts": round((Cv[i] - e) - SLIP, 2), "bars": i - ei, "mae_pts": round(mae, 2)})
                inp = False
    return pd.DataFrame(rows)


print("MES 1c | $5/pt | $5 RT | STMR K8<15 & C>SMA100, exit C>SMA5 | ES 2021-06->2026-07")
print(f"{'TF':>4} {'n':>5} {'win%':>5} {'avg$':>6} {'total$':>8} {'PF':>5} {'worst$':>8}")
for tf, m in [("15m", 15), ("30m", 30), ("1h", 60), ("2h", 120), ("4h", 240)]:
    g = run(rs(d, m))
    g["pnl"] = g.pts * PT - FEE
    g.to_csv(OUT / f"stmr_mes_{tf}.csv", index=False)   # DATED trade list saved
    gp, gl = g.pnl[g.pnl > 0].sum(), -g.pnl[g.pnl < 0].sum(); pf = gp / gl if gl else 99
    print(f"{tf:>4} {len(g):>5} {(g.pnl>0).mean()*100:>4.0f}% {g.pnl.mean():>6.1f} "
          f"{g.pnl.sum():>8.0f} {pf:>5.2f} {(g.mae_pts.min()*PT-FEE):>8.0f}")
print(f"dated trade lists -> {OUT}")
