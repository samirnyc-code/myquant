"""Scan range-breakout params on TRAIN (2021-23), report OOS (2024-26).
Scalp = short opening range + tight fixed risk. Swing = 60-90min IB + wider risk,
held to RTH close. Saves ranked results CSV. Pessimistic same-bar fills.
"""
import sys, itertools
from pathlib import Path
import pandas as pd
import numpy as np
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine, strategies as S

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["d"] = pd.to_datetime(df5["Date"])
train_dates = set(df5[df5.d < "2024-01-01"].Date)

def run_split(sig_fn, max_hold):
    tr = engine.run(df5, sig_fn, max_hold_bars=max_hold)
    if len(tr) == 0:
        return None
    tr["d"] = pd.to_datetime(tr["Date"])
    trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    return tr, engine.metrics(trn, "train"), engine.metrics(oos, "oos")

mode = sys.argv[1] if len(sys.argv) > 1 else "scalp"
rows = []
if mode == "scalp":
    grid = itertools.product([3, 6], [2, 3, 4, 5], [2.0, 2.5, 3.0])   # or_bars(15/30m), risk_pts, rr
    max_hold = 12   # <=60 min hold = scalp
    for orb, risk, rr in grid:
        f = S.make_range(orb, risk, rr, buf_ticks=1)
        res = run_split(f, max_hold)
        if res is None: continue
        _, mt, mo = res
        rows.append(dict(orb=orb, risk=risk, rr=rr, **{f"tr_{k}": v for k, v in mt.items() if k != "label"},
                         **{f"oo_{k}": v for k, v in mo.items() if k != "label"}))
else:  # swing
    grid = itertools.product([12, 18], [6, 8, 10, 12], [2.0, 2.5, 3.0])  # IB 60/90m, wider risk
    max_hold = None  # hold to RTH close
    for orb, risk, rr in grid:
        f = S.make_range(orb, risk, rr, buf_ticks=1)
        res = run_split(f, max_hold)
        if res is None: continue
        _, mt, mo = res
        rows.append(dict(orb=orb, risk=risk, rr=rr, **{f"tr_{k}": v for k, v in mt.items() if k != "label"},
                         **{f"oo_{k}": v for k, v in mo.items() if k != "label"}))

R = pd.DataFrame(rows)
R = R.sort_values("tr_pnl", ascending=False)
out = ROOT / "research" / "scalp_swing" / f"search_{mode}.csv"
R.to_csv(out, index=False)
cols = ["orb", "risk", "rr", "tr_n", "tr_pnl", "tr_pf", "tr_win", "tr_maxdd", "tr_netdd",
        "oo_n", "oo_pnl", "oo_pf", "oo_win", "oo_maxdd", "oo_netdd"]
print(f"MODE={mode}  (train 2021-23 vs OOS 2024-26)  saved {out.name}")
print(R[cols].to_string(index=False))
