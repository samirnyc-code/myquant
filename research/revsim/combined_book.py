"""Per-type RevFT book (the conclusion of 'split by type + filter each correctly'):
  BO  -> all (no extreme needed)
  IB  -> only at an extreme (ext lookback swept)
  OB  -> only at an extreme
  Trap-> DROPPED (dead everywhere)
Test the combined book + a below-SMA20 variant. Honest: per-year + ex-2025 + train/OOS.
Also EXPORT the qualifying signals for the Book Review overlay.
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
sg = RD.detect(df5, {"FT_ABR": 1.0})
rb = sg["rb"].values.astype(int); side = sg["side"].values
for X in [8, 10]:
    hiX = pd.Series(H).rolling(X).max().values; loX = pd.Series(L).rolling(X).min().values
    sg[f"ext{X}"] = np.where(side > 0, L[rb] <= loX[rb] + 1e-9, H[rb] >= hiX[rb] - 1e-9)


def book(sg, ib_ext="ext8", ob_ext="ext8"):
    keep = ((sg.rev == "BO") |
            ((sg.rev == "IB") & sg[ib_ext]) |
            ((sg.rev == "OB") & sg[ob_ext]))
    return sg[keep]


def rep(name, sub, gate=None):
    tr = R.sim(sub, sma=sma, entry="market", hold_eod=True, gate=gate)
    tr["d"] = pd.to_datetime(tr["Date"]); tr["y"] = tr.d.dt.year
    trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    mt, mo, al = E.metrics(trn), E.metrics(oos), E.metrics(tr)
    yr = E.by_year(tr); green = int((yr.pnl > 0).sum()); ex25 = tr[tr.y != 2025].pnl.sum()
    print(f"\n=== {name} ===")
    print(f"ALL  n={al['n']} PF {al['pf']} ${al['pnl']:,} netDD {al['netdd']} Sharpe {al['sharpe']}")
    print(f"TRAIN PF {mt['pf']} ${mt['pnl']:,}   OOS PF {mo['pf']} ${mo['pnl']:,}   ex-2025 ${ex25:,.0f}   green {green}/{len(yr)}")
    print(yr.to_string())
    return tr


b1 = book(sg, "ext8", "ext8")
tr = rep("BOOK: BO-all + IB-ext8 + OB-ext8 (Trap dropped)", b1)
rep("BOOK + below-SMA20 gate", b1, gate="below")
rep("BOOK ib-ext10 + ob-ext10", book(sg, "ext10", "ext10"))
# BO alone vs book
rep("BO only (all)", sg[sg.rev == "BO"])

# export qualifying signals (book1) for Book Review overlay
exp = b1[["Date", "time", "rev", "side", "entry", "stop", "bar"]].copy()
exp["time"] = pd.to_datetime(exp["time"]).astype(str)
out = ROOT / "research" / "revsim" / "revft_book_signals.csv"
exp.to_csv(out, index=False)
print(f"\nexported {len(exp)} book signals -> {out}")
# also export ALL strong-FT with type+extreme flags for a full toggle
full = sg[["Date", "time", "rev", "side", "entry", "stop", "bar", "ext8", "ext10"]].copy()
full["time"] = pd.to_datetime(full["time"]).astype(str)
full.to_csv(ROOT / "research" / "revsim" / "revft_all_signals.csv", index=False)
print(f"exported {len(full)} all strong-FT signals -> revft_all_signals.csv")
print("DONE_BOOK")
