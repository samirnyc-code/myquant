"""Per-TYPE reversal x SHORT extreme-lookback sweep. Extreme = reversal bar (rb) is the
X-bar high(short)/low(long); poke = it sticks out beyond the prior X-bar extreme.
One tick pass (run_configs). Per-year + explicit EX-2025 P&L to expose 2025-dependence.
Honest bar: both halves positive AND positive ex-2025 AND green in >=4/6 years.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
d = df5.sort_values("DateTime").reset_index(drop=True)
H, L = d.High.values, d.Low.values
sma = G.sma20d_map(df5)
sg = RD.detect(df5, {"FT_ABR": 1.0})     # strong-FT base
rb = sg["rb"].values.astype(int)
side = sg["side"].values
print(f"{len(sg)} strong-FT signals")

# extreme + poke flags for several short lookbacks
for X in [3, 4, 5, 6, 8, 10]:
    hiX = pd.Series(H).rolling(X).max().values
    loX = pd.Series(L).rolling(X).min().values
    hiXp = pd.Series(H).shift(1).rolling(X).max().values
    loXp = pd.Series(L).shift(1).rolling(X).min().values
    sg[f"ext{X}"] = np.where(side > 0, L[rb] <= loX[rb] + 1e-9, H[rb] >= hiX[rb] - 1e-9)
    sg[f"poke{X}"] = np.where(side > 0, loXp[rb] - L[rb], H[rb] - hiXp[rb]) > 0

TYPES = ["Trap", "BO", "OB", "IB"]
def F(t, xcol=None, poke=None):
    def fn(s):
        m = s.rev == t
        if xcol is not None: m &= s[xcol]
        if poke is not None: m &= s[poke]
        return s[m]
    return fn

configs = []
for t in TYPES:
    configs.append((f"{t}|all", F(t), dict(entry="market", hold_eod=True)))
    for X in [3, 4, 5, 6, 8, 10]:
        configs.append((f"{t}|ext{X}", F(t, f"ext{X}"), dict(entry="market", hold_eod=True)))
        configs.append((f"{t}|ext{X}+poke", F(t, f"ext{X}", f"poke{X}"), dict(entry="market", hold_eod=True)))

print(f"{len(configs)} configs, one pass...")
res = R.run_configs(sg, configs, sma=sma)
rows = []
for name, _, _ in configs:
    tr = res[name]
    if len(tr) < 20:
        continue
    tr["d"] = pd.to_datetime(tr["Date"]); tr["y"] = tr.d.dt.year
    trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo, al = E.metrics(trn), E.metrics(oos), E.metrics(tr)
    yr = tr.groupby("y").pnl.sum(); green = int((yr > 0).sum())
    ex25 = tr[tr.y != 2025].pnl.sum()
    rows.append(dict(cfg=name, n=al["n"], pnl=al["pnl"], pf=al["pf"], ndd=al["netdd"],
                     tr_pf=mt["pf"], tr_pnl=mt["pnl"], oo_pf=mo["pf"], oo_pnl=mo["pnl"],
                     green=f"{green}/{len(yr)}", ex2025=round(ex25),
                     robust=(mt["pnl"] > 0 and mo["pnl"] > 0 and ex25 > 0 and green >= 4)))
D = pd.DataFrame(rows).sort_values(["cfg"])
pd.set_option("display.width", 220)
print("\n=== PER-TYPE x EXTREME-LOOKBACK (strong-FT, EOD hold) ===")
for t in TYPES:
    print(f"\n--- {t} ---")
    print(D[D.cfg.str.startswith(t + "|")].sort_values("ex2025", ascending=False).to_string(index=False))
print("\n*** ROBUST (both halves + ex-2025 positive + >=4/6 green) ***")
rob = D[D.robust]
print(rob.to_string(index=False) if len(rob) else "  NONE")
D.to_csv(ROOT / "research" / "revsim" / "sweep_pertype_extreme.csv", index=False)
# per-year for any robust
for name in list(rob.cfg)[:6]:
    tr = res[name]; tr["d"] = pd.to_datetime(tr["Date"])
    print(f"\nPER-YEAR {name}:"); print(E.by_year(tr).to_string())
print("\nDONE_PT")
