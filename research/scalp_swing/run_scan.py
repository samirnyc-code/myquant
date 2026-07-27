"""Tick-accurate grid scan. Loads each day's ticks once, evaluates all configs.
Reports TRAIN (2021-23) vs OOS (2024-26). Saves ranked CSV.
Usage: python run_scan.py [scalp|swing]
"""
import sys, itertools
from pathlib import Path
import pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E, strategies as S

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
mode = sys.argv[1] if len(sys.argv) > 1 else "scalp"

if mode == "scalp":
    combos = list(itertools.product([3, 6, 9], [3, 4, 5, 6], [2.0, 2.5, 3.0]))  # or_bars, risk, rr
    fns = [S.make_range(o, r, rr, buf_ticks=1) for (o, r, rr) in combos]
    max_hold = 60
elif mode == "swing":
    combos = list(itertools.product([12, 18, 24], [6, 8, 10, 12, 15], [2.0, 2.5, 3.0]))
    fns = [S.make_range(o, r, rr, buf_ticks=1) for (o, r, rr) in combos]
    max_hold = None
elif mode == "pb":       # trend pullback scalp (max hold 60m)
    combos = list(itertools.product([20, 40], [10, 14], [1.0, 1.5, 2.0], [2.0, 2.5, 3.0]))  # ema,atr,stopATR,rr
    fns = [S.make_pullback(e, a, s, rr) for (e, a, s, rr) in combos]
    max_hold = 60
elif mode == "pbswing":  # trend pullback held to RTH close
    combos = list(itertools.product([20, 40], [14], [1.5, 2.0, 2.5], [2.0, 2.5, 3.0]))
    fns = [S.make_pullback(e, a, s, rr) for (e, a, s, rr) in combos]
    max_hold = None
elif mode == "gscalp":   # gated breakout, short hold
    fns = []
    for orb in [3, 6]:
        for risk in [4, 5, 6]:
            for rr in [2.0, 3.0]:
                for exp in [0.0, 1.2]:
                    fns.append(S.make_gated(orb, risk, rr, tod_lo=orb, tod_hi=48,
                                            need_vwap=True, need_expand=exp,
                                            tag=f"tod{orb}-48_x{exp}"))
    combos = [None] * len(fns)
    max_hold = 60
elif mode == "fscalp":   # vwap-fade mean reversion, short hold
    fns = []
    for ext in [1.5, 2.0, 2.5]:
        for a in [14, 20]:
            for sb in [1.0, 2.0]:
                fns.append(S.make_fade(ext, a, sb, target="vwap", tod_lo=6, tod_hi=54, tag="v"))
    combos = [None] * len(fns); max_hold = 45
elif mode == "fswing":   # vwap-fade held to RTH close
    fns = []
    for ext in [1.5, 2.0, 2.5, 3.0]:
        for a in [14, 20]:
            for sb in [1.0, 2.0]:
                fns.append(S.make_fade(ext, a, sb, target="vwap", tod_lo=6, tod_hi=60, tag="v"))
    combos = [None] * len(fns); max_hold = None
elif mode == "gswing":   # gated breakout, hold to close
    fns = []
    for orb in [6, 12]:
        for risk in [6, 8, 10]:
            for rr in [2.0, 3.0]:
                for exp in [0.0, 1.2]:
                    fns.append(S.make_gated(orb, risk, rr, tod_lo=orb, tod_hi=54,
                                            need_vwap=True, need_expand=exp,
                                            tag=f"tod{orb}-54_x{exp}"))
    combos = [None] * len(fns)
    max_hold = None

print(f"MODE={mode}  {len(fns)} configs, loading ticks once/day ...")
res = E.run_many(df5, fns, max_hold_minutes=max_hold)

rows = []
for combo, f in zip(combos, fns):
    tr = res[f.__name__]
    if len(tr) == 0:
        continue
    tr["d"] = pd.to_datetime(tr["Date"])
    trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo = E.metrics(trn), E.metrics(oos)
    rows.append(dict(cfg=f.__name__,
                     tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"], tr_win=mt["win"], tr_dd=mt["maxdd"], tr_ndd=mt["netdd"], tr_shp=mt["sharpe"],
                     oo_n=mo["n"], oo_pnl=mo["pnl"], oo_pf=mo["pf"], oo_win=mo["win"], oo_dd=mo["maxdd"], oo_ndd=mo["netdd"], oo_shp=mo["sharpe"]))

R = pd.DataFrame(rows).sort_values("tr_pnl", ascending=False)
out = ROOT / "research" / "scalp_swing" / f"scan_{mode}.csv"
R.to_csv(out, index=False)
print(f"saved {out.name}")
print(R.to_string(index=False))
