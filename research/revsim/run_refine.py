"""Refine the strong-detection RevFT: combine quality levers (FT_ABR1.0 + OB_strict +
PriorOpp), then attack the huge drawdown with regime gate / exits / per-type / dir.
Goal: does net/DD get tradeable, or is it stuck at PF~1.05 marginal? OOS + per-year.
"""
import sys
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
sma = G.sma20d_map(df5)

# strong-detection base variants
bases = {
    "FT1": {"FT_ABR": 1.0},
    "FT1+OBs": {"FT_ABR": 1.0, "OB_Strict": True},
    "FT1+OBs+PO": {"FT_ABR": 1.0, "OB_Strict": True,
                   "Trap_Prior_OppClose": True, "BO_Prior_OppClose": True,
                   "OB_Prior_OppClose": True, "IB_Prior_OppClose": True},
    "FT1.5": {"FT_ABR": 1.5},
}
sigsets = {}
for nm, ov in bases.items():
    s = RD.detect(df5, ov); s["variant"] = nm; sigsets[nm] = s
    print(f"{nm:14s} {len(s)} signals  {s.rev.value_counts().to_dict()}")
allsig = pd.concat(sigsets.values(), ignore_index=True)

TYPES = ["Trap", "BO", "OB", "IB"]
def F(variant, types=None, side=None):
    def fn(s):
        m = (s.variant == variant)
        if types is not None: m &= s.rev.isin(types)
        if side is not None: m &= s.side == side
        return s[m]
    return fn

configs = []
for b in bases:
    configs.append((f"{b}|eod", F(b), dict(entry="market", hold_eod=True)))
    configs.append((f"{b}|eod|below", F(b), dict(entry="market", hold_eod=True, gate="below")))
    configs.append((f"{b}|eod|above", F(b), dict(entry="market", hold_eod=True, gate="above")))
    configs.append((f"{b}|rr2", F(b), dict(entry="market", rr=2.0)))
    configs.append((f"{b}|rr3", F(b), dict(entry="market", rr=3.0)))
    configs.append((f"{b}|eod|LONG", F(b, side=1), dict(entry="market", hold_eod=True)))
    configs.append((f"{b}|eod|SHORT", F(b, side=-1), dict(entry="market", hold_eod=True)))
# per-type on best base
for t in TYPES:
    configs.append((f"FT1+OBs|{t}|eod", F("FT1+OBs", types=[t]), dict(entry="market", hold_eod=True)))

print(f"{len(configs)} configs...")
res = R.run_configs(allsig, configs, sma=sma)
rows = []
for name, _, _ in configs:
    tr = res[name]
    if len(tr) == 0: continue
    tr["d"] = pd.to_datetime(tr["Date"]); trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo = E.metrics(trn), E.metrics(oos); al = E.metrics(tr)
    rows.append(dict(cfg=name, n=al["n"], all_pnl=al["pnl"], all_pf=al["pf"], all_dd=al["maxdd"], all_ndd=al["netdd"], all_shp=al["sharpe"],
                     tr_pf=mt["pf"], tr_pnl=mt["pnl"], oo_pf=mo["pf"], oo_pnl=mo["pnl"], both=(mt["pnl"] > 0 and mo["pnl"] > 0)))
D = pd.DataFrame(rows).sort_values("all_ndd", ascending=False)
D.to_csv(ROOT / "research" / "revsim" / "sweep_refine.csv", index=False)
pd.set_option("display.width", 240)
print(D.to_string(index=False))
print("\nBOTH-POS, ranked by net/DD (quality):")
print(D[D.both].sort_values("all_ndd", ascending=False).head(10).to_string(index=False))
# per-year for the best both-pos by net/DD
best = D[D.both].sort_values("all_ndd", ascending=False)
if len(best):
    bn = best.iloc[0]["cfg"]
    tr = res[bn]; tr["d"] = pd.to_datetime(tr["Date"])
    print(f"\nPER-YEAR best-by-netDD: {bn}")
    print(E.by_year(tr).to_string())
print("\nDONE_REFINE")
