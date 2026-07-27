"""DEEP sweep: trade-LOCATION x type x regime x exit on PORT signals (default detection).
Location is the hypothesised key to the reversal edge. Reports TRAIN/OOS, saves CSV.
Only reports configs POSITIVE IN BOTH halves prominently (robust = both green).
"""
import sys, itertools
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, location as LOC, engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
sma = G.sma20d_map(df5)
port = RD.detect(df5)
sg = LOC.augment(port, df5)          # add location features
print(f"{len(sg)} port signals with location features")

TYPES = ["Trap", "BO", "OB", "IB"]


def F(types=None, side=None, loc_max=None, loc_min=None, fresh=None, dext_max=None):
    """Per-signal filter using location columns."""
    def fn(s):
        m = pd.Series(True, index=s.index)
        if types is not None: m &= s.rev.isin(types)
        if side is not None: m &= s.side == side
        # location: for a fade, 'good' = near the day extreme in trade direction.
        # long wants loc_pct LOW (near day low); short wants loc_pct HIGH (near day high).
        if loc_max is not None:
            m &= ((s.side > 0) & (s.loc_pct <= loc_max)) | ((s.side < 0) & (s.loc_pct >= 1 - loc_max))
        if fresh is not None: m &= s.fresh_ext == fresh
        if dext_max is not None: m &= s.dist_ext <= dext_max
        return s[m]
    return fn


configs = []
# 1) location threshold on the full set (EOD hold)
for lm in [0.20, 0.33, 0.50, 1.0]:
    configs.append((f"ALL|eod|loc{lm}", F(TYPES, loc_max=lm), dict(entry="market", hold_eod=True)))
# 2) fresh-extreme filter (the indicator's own Extreme filter)
configs.append(("ALL|eod|fresh", F(TYPES, fresh=True), dict(entry="market", hold_eod=True)))
configs.append(("ALL|eod|fresh|loc.33", F(TYPES, fresh=True, loc_max=0.33), dict(entry="market", hold_eod=True)))
# 3) location + regime (below-SMA20 = negative gamma)
for lm in [0.33, 0.5]:
    configs.append((f"ALL|eod|loc{lm}|below", F(TYPES, loc_max=lm), dict(entry="market", hold_eod=True, gate="below")))
    configs.append((f"ALL|eod|loc{lm}|fresh", F(TYPES, loc_max=lm, fresh=True), dict(entry="market", hold_eod=True)))
# 4) per-type with best location (loc .33 + fresh)
for t in TYPES:
    configs.append((f"{t}|eod|loc.33|fresh", F([t], loc_max=0.33, fresh=True), dict(entry="market", hold_eod=True)))
    configs.append((f"{t}|eod|loc.33", F([t], loc_max=0.33), dict(entry="market", hold_eod=True)))
# 5) location + RR targets (instead of EOD)
for lm, rr in itertools.product([0.33, 0.5], [1.5, 2.0]):
    configs.append((f"ALL|rr{rr}|loc{lm}|fresh", F(TYPES, loc_max=lm, fresh=True), dict(entry="market", rr=rr)))
# 6) direction split with location
configs.append(("ALL|eod|loc.33|fresh|LONG", F(TYPES, side=1, loc_max=0.33, fresh=True), dict(entry="market", hold_eod=True)))
configs.append(("ALL|eod|loc.33|fresh|SHORT", F(TYPES, side=-1, loc_max=0.33, fresh=True), dict(entry="market", hold_eod=True)))
# 7) BO+IB good-type combo with location
configs.append(("BO+IB|eod|loc.33|fresh", F(["BO", "IB"], loc_max=0.33, fresh=True), dict(entry="market", hold_eod=True)))
configs.append(("BO+IB|eod|loc.5|fresh|below", F(["BO", "IB"], loc_max=0.5, fresh=True), dict(entry="market", hold_eod=True, gate="below")))

print(f"{len(configs)} configs, loop days once...")
res = R.run_configs(sg, configs, sma=sma)
rows = []
for name, _, _ in configs:
    tr = res[name]
    if len(tr) == 0:
        rows.append(dict(cfg=name, tr_n=0)); continue
    tr["d"] = pd.to_datetime(tr["Date"]); trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo = E.metrics(trn), E.metrics(oos)
    rows.append(dict(cfg=name, tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"], tr_win=mt["win"], tr_dd=mt["maxdd"],
                     oo_n=mo["n"], oo_pnl=mo["pnl"], oo_pf=mo["pf"], oo_win=mo["win"], oo_dd=mo["maxdd"],
                     both_pos=(mt["pnl"] > 0 and mo["pnl"] > 0)))
D = pd.DataFrame(rows).sort_values("oo_pnl", ascending=False, na_position="last")
D.to_csv(ROOT / "research" / "revsim" / "sweep_location.csv", index=False)
pd.set_option("display.width", 200)
print(D.to_string(index=False))
print("\n*** BOTH-HALVES POSITIVE (robust candidates) ***")
print(D[D.both_pos == True].to_string(index=False))
print("\nDONE_LOC")
