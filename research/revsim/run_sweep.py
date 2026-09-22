"""RevFT filter/combo sweep on the exported MyReversals signals (default detection).
Loops days once. Reports TRAIN 2021-23 / OOS 2024-26. Saves ranked CSV.
Levers: RevType subset, direction, SMA20-D regime gate, time-of-day, entry model, exit(RR/EOD).
"""
import sys, itertools
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, engine_ticks as E
import swing_level_gated as G

sg = R.parse_signals()
sg = sg[sg.Date >= "2021-06-18"].reset_index(drop=True)
df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
sma = G.sma20d_map(df5)


def F(types=None, side=None):
    def fn(s):
        m = pd.Series(True, index=s.index)
        if types is not None: m &= s.rev.isin(types)
        if side is not None: m &= s.side == side
        return s[m]
    return fn


configs = []
TYPES = ["Trap", "BO", "OB", "IB"]
# per-type solo, EOD hold + RR2 target, market entry
for t in TYPES + [tuple(TYPES)]:
    tl = [t] if isinstance(t, str) else list(t)
    nm = t if isinstance(t, str) else "ALL"
    configs.append((f"{nm}|eod", F(tl), dict(entry="market", hold_eod=True)))
    configs.append((f"{nm}|rr2", F(tl), dict(entry="market", rr=2.0)))
# best-looking combos from prior work: BO+IB, BO+IB+Trap
for combo in [("BO", "IB"), ("BO", "IB", "Trap"), ("BO", "IB", "OB")]:
    configs.append(("+".join(combo) + "|eod", F(list(combo)), dict(entry="market", hold_eod=True)))
    configs.append(("+".join(combo) + "|rr2", F(list(combo)), dict(entry="market", rr=2.0)))
# regime gate (below-SMA20 = negative-gamma where reversals live, per S85)
for t in [("BO", "IB"), tuple(TYPES)]:
    configs.append(("+".join(t) + "|eod|below", F(list(t)), dict(entry="market", hold_eod=True, gate="below")))
    configs.append(("+".join(t) + "|eod|above", F(list(t)), dict(entry="market", hold_eod=True, gate="above")))
# retest entry (limit at BTC) for the all-set
configs.append(("ALL|retest|rr2", F(TYPES), dict(entry="retest", rr=2.0)))
configs.append(("ALL|retest|eod", F(TYPES), dict(entry="retest", hold_eod=True)))
# direction split on the all-set EOD
configs.append(("ALL|eod|LONG", F(TYPES, side=1), dict(entry="market", hold_eod=True)))
configs.append(("ALL|eod|SHORT", F(TYPES, side=-1), dict(entry="market", hold_eod=True)))
# time-of-day: only first 2h (open reversals)
configs.append(("ALL|eod|open", F(TYPES), dict(entry="market", hold_eod=True, tod=(830, 1030))))
configs.append(("BO+IB|eod|open", F(["BO", "IB"]), dict(entry="market", hold_eod=True, tod=(830, 1030))))

print(f"{len(configs)} configs, {len(sg)} signals, loop days once...")
res = R.run_configs(sg, configs, sma=sma)

rows = []
for name, _, _ in configs:
    tr = res[name]
    if len(tr) == 0:
        continue
    tr["d"] = pd.to_datetime(tr["Date"])
    trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo = E.metrics(trn), E.metrics(oos)
    rows.append(dict(cfg=name, tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"], tr_win=mt["win"], tr_dd=mt["maxdd"],
                     oo_n=mo["n"], oo_pnl=mo["pnl"], oo_pf=mo["pf"], oo_win=mo["win"], oo_dd=mo["maxdd"]))
D = pd.DataFrame(rows).sort_values("oo_pnl", ascending=False)
D.to_csv(ROOT / "research" / "revsim" / "sweep_filters.csv", index=False)
print(D.to_string(index=False))
print("\nDONE_SWEEP")
