"""Sweep the DETECTION parameters inside each setup (the actual NT knobs).
Each variant = one detect() run with a modified param dict; all variants tagged and
tick-simmed in one day-loop pass. EOD hold, all types (neutral base; location did not
help). Reports TRAIN/OOS; flags BOTH-halves-positive (robust) configs.
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

# --- variant param dicts (name -> overrides on DEFAULTS) ---
variants = {"default": {}}
# global ABR tighten (bigger reversal bars = higher quality) — scale all setup ABRs
for f in [1.5, 2.0, 3.0]:
    variants[f"ABRx{f}"] = {k: RD.DEFAULTS[k] * f for k in ["Trap_ABR", "BO_ABR", "OB_ABR"]} | {"FT_ABR": RD.DEFAULTS["FT_ABR"] * f}
# IBS strength up (stronger closes)
for v in [60, 70, 80]:
    variants[f"IBS{v}"] = {k: v for k in ["Trap_IBS", "BO_IBS", "OB_IBS", "IB_IBS", "FT_IBS"]}
# FT strength
variants["FT_ABR0.5"] = {"FT_ABR": 0.5}
variants["FT_ABR1.0"] = {"FT_ABR": 1.0}
variants["FT_CB_off"] = {"FT_CloseBeyond": False}
variants["FT_UL20"] = {"FT_UL": 20}
# prior opposite close on all setups (quality)
variants["PriorOpp"] = {k: True for k in ["Trap_Prior_OppClose", "BO_Prior_OppClose", "OB_Prior_OppClose", "IB_Prior_OppClose"]}
# OB strict + body checks
variants["OB_strict"] = {"OB_Strict": True}
variants["OB_CB"] = {"OB_CloseBeyond": True}
variants["BodyChecks"] = {"Trap_BodyCheck": True, "OB_BodyCheck": True, "IB_BodyCheck": True}
# body minimums up
variants["BiggerBody"] = {"BO_Body": 30, "OB_Body": 30, "Trap_Body": 30, "IB_Body": 30, "FT_Body": 30}
# Trap-specific: bigger tail, tighter ABR
variants["Trap_tail40"] = {"Trap_Tail": 40}
variants["Trap_ABR0.6"] = {"Trap_ABR": 0.6}
# IB prior tail stricter
variants["IB_ptail20"] = {"IB_Prior_Tail": 20}
# combos of the promising ones
variants["ABRx2+IBS70"] = {k: RD.DEFAULTS[k]*2 for k in ["Trap_ABR", "BO_ABR", "OB_ABR"]} | {"FT_ABR": RD.DEFAULTS["FT_ABR"]*2} | {k: 70 for k in ["Trap_IBS", "BO_IBS", "OB_IBS", "IB_IBS", "FT_IBS"]}
variants["ABRx2+PriorOpp"] = {k: RD.DEFAULTS[k]*2 for k in ["Trap_ABR", "BO_ABR", "OB_ABR"]} | {k: True for k in ["Trap_Prior_OppClose", "BO_Prior_OppClose", "OB_Prior_OppClose", "IB_Prior_OppClose"]}

print(f"detecting {len(variants)} variants ...")
allsig = []
counts = {}
for name, ov in variants.items():
    s = RD.detect(df5, ov)
    counts[name] = len(s)
    s["variant"] = name
    allsig.append(s)
    print(f"  {name:16s} {len(s)} signals")
sg = pd.concat(allsig, ignore_index=True)

# one sim pass: config per variant, EOD hold all types
def F(name):
    return lambda s: s[s.variant == name]
configs = [(name, F(name), dict(entry="market", hold_eod=True)) for name in variants]
print("sim (one pass over days)...")
res = R.run_configs(sg, configs, sma=sma)

rows = []
for name in variants:
    tr = res[name]
    if len(tr) == 0:
        continue
    tr["d"] = pd.to_datetime(tr["Date"]); trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo = E.metrics(trn), E.metrics(oos)
    rows.append(dict(variant=name, sig=counts[name], tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"],
                     tr_win=mt["win"], tr_dd=mt["maxdd"], oo_n=mo["n"], oo_pnl=mo["pnl"], oo_pf=mo["pf"],
                     oo_win=mo["win"], oo_dd=mo["maxdd"], both=(mt["pnl"] > 0 and mo["pnl"] > 0)))
D = pd.DataFrame(rows).sort_values("oo_pnl", ascending=False)
D.to_csv(ROOT / "research" / "revsim" / "sweep_detect.csv", index=False)
pd.set_option("display.width", 220)
print(D.to_string(index=False))
print("\n*** BOTH-HALVES POSITIVE ***")
print(D[D.both].to_string(index=False))
print("\nDONE_DETECT")
