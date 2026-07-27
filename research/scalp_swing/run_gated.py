"""Apply the STRUCTURAL-LEVEL gate to (a) a short-hold SCALP and (b) a 1.5:1 SWING.
Uses the same make_level_ib (price vs prior-day SMA20-D, single arm/day, anticipate).
"""
import sys
from pathlib import Path
import pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
sma = G.sma20d_map(df5)


def report(fns, max_hold, min_rr, name):
    res = E.run_many(df5, fns, max_hold_minutes=max_hold, min_rr=min_rr)
    rows = []
    for f in fns:
        tr = res[f.__name__]
        if len(tr) == 0:
            continue
        tr["d"] = pd.to_datetime(tr["Date"])
        trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
        mt, mo = E.metrics(trn), E.metrics(oos)
        rows.append(dict(cfg=f.__name__, tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"], tr_win=mt["win"],
                         tr_dd=mt["maxdd"], tr_ndd=mt["netdd"], oo_n=mo["n"], oo_pnl=mo["pnl"],
                         oo_pf=mo["pf"], oo_win=mo["win"], oo_dd=mo["maxdd"], oo_ndd=mo["netdd"]))
    R = pd.DataFrame(rows).sort_values("tr_pnl", ascending=False)
    R.to_csv(ROOT / "research" / "scalp_swing" / f"scan_{name}.csv", index=False)
    print(f"\n===== {name} =====")
    print(R.to_string(index=False))
    return R


# (a) GATED SCALP: short hold, moderate stops, lower RR
scalp_fns = []
for ib in [3, 6]:
    for r in [3, 4, 6]:
        for rr in [1.0, 1.5]:
            scalp_fns.append(G.make_level_ib(sma, ib, r, rr=rr, cutoff_bar=60, min_dist=3.0, tag="sma20d"))
report(scalp_fns, max_hold=30, min_rr=0.9, name="gscalp_lvl")

# (b) GATED SWING at 1.5:1
swing_fns = []
for ib in [12, 18]:
    for r in [8, 10, 12]:
        swing_fns.append(G.make_level_ib(sma, ib, r, rr=1.5, cutoff_bar=54, min_dist=3.0, tag="sma20d"))
report(swing_fns, max_hold=None, min_rr=1.4, name="gswing15_lvl")
print("\nDONE_GATED")
