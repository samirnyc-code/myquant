"""0DTE MQ levels vs three-book trades — exploratory (Samir, 2026-07-25).
File: data/menthorq/ES1!_mq_levels_history.csv  (ES1! price scale, NO SPX basis conv).
  - dedup: keep LAST row per session_date.
  - session_date = the trading day the levels APPLY to -> join directly, NO shift.
  - levels: cr0/ps0/hvl0/gw0 (0DTE), cr/ps/hvl, d1_min/d1_max, gex_1..10 (+ _gex mags).

Coverage 2024-07..2026-07 = entirely post-2023 (all OOS vs the original split), ~2yr.
Day-level features (all known at the open, causal):
  A  open position vs 0DTE range [ps0,cr0]: below / inside / above
  B  |open - hvl0| proximity quartiles (0DTE magnet analog of the HVL finding)
  C  0DTE range width (cr0-ps0) quartiles           -> narrow = pin day
  D  d1 expected-move envelope (d1_max-d1_min) quartiles -> small = compressed day
  E  directional break: long above cr0 / short below ps0
Basis is sanity-checked inside (open vs range mid). Outcome = trade net, PF.

  python scripts/regime_2e_0dte_levels.py
Output: data/regime/tradeday_0dte_20260725.csv + tables + PNG.
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return round(gp/gl, 2) if gl else 0


# --- MQ levels: dedup, join key ---
mq = pd.read_csv(WT / "data" / "menthorq" / "ES1!_mq_levels_history.csv", parse_dates=["session_date"])
mq = mq.sort_values("session_date").drop_duplicates("session_date", keep="last")
mq["Date"] = mq.session_date.dt.date.astype(str)
LV = ["cr0", "ps0", "hvl0", "gw0", "cr", "ps", "hvl", "d1_min", "d1_max"]
mq = mq[["Date"] + LV].copy()

# --- our continuous OHLC per day ---
b = pd.read_parquet(WT.parent.joinpath("myquant/data/bars/_continuous.parquet")) if (WT.parent/"myquant"/"data").exists() \
    else pd.read_parquet(Path(r"C:/Users/Admin/myquant/data/bars/_continuous.parquet"))
b["Date"] = b["DateTime"].dt.date.astype(str)
day = b.groupby("Date").agg(o=("Open", "first"), c=("Close", "last"), hi=("High", "max"), lo=("Low", "min")).reset_index()

# --- trades ---
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")
tr = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts["dir"] == "S"))].copy()

d = tr.merge(mq, on="Date", how="inner").merge(day, on="Date", how="inner")
print(f"three-book trades inside MQ 0DTE window: {len(d)}  ({d.Date.min()} .. {d.Date.max()})")

# --- basis sanity ---
mid = (d.cr0 + d.ps0) / 2
off = d.o - mid
print(f"BASIS check  open - 0DTE-range-mid: median {off.median():+.1f}pt  IQR[{off.quantile(.25):+.0f},{off.quantile(.75):+.0f}]  "
      f"frac open inside [ps0,cr0]: {((d.o>=d.ps0)&(d.o<=d.cr0)).mean():.0%}")
rng = (d.hi - d.lo); d["rw0"] = d.cr0 - d.ps0; d["d1w"] = d.d1_max - d.d1_min
print(f"overall trades: net {d.net.sum():+,.0f}  PF {pf(d.net)}  $/tr {d.net.mean():+.0f}\n")


def show(title, groups):
    print(title)
    for lab, x in groups:
        if len(x) < 8:
            print(f"  {lab:22s} n={len(x):4d}  (too few)"); continue
        print(f"  {lab:22s} n={len(x):4d}  net {x.net.sum():+8,.0f}  $/tr {x.net.mean():+6.1f}  PF {pf(x.net):4.2f}")


# A: open vs 0DTE range
posA = pd.cut(pd.Series(np.where(d.o < d.ps0, -1, np.where(d.o > d.cr0, 1, 0)), index=d.index),
              [-2, -0.5, 0.5, 2], labels=["below ps0", "inside range", "above cr0"])
show("A) OPEN vs 0DTE range [ps0,cr0]:", [(l, d[posA == l]) for l in ["below ps0", "inside range", "above cr0"]])

# B: proximity to hvl0
d["dh0"] = (d.o - d.hvl0).abs()
d["qb"] = pd.qcut(d.dh0, 4, labels=["Q1 near hvl0", "Q2", "Q3", "Q4 far"])
show("\nB) |open - hvl0| quartiles (0DTE magnet):", [(str(q), d[d.qb == q]) for q in d.qb.cat.categories])

# C: 0DTE range width
d["qc"] = pd.qcut(d.rw0, 4, labels=["Q1 narrow", "Q2", "Q3", "Q4 wide"])
show("\nC) 0DTE range width cr0-ps0 (narrow=pin day):", [(str(q), d[d.qc == q]) for q in d.qc.cat.categories])

# D: d1 expected-move envelope
show("\nD) d1 expected-move envelope (d1_max-d1_min):",
     [(str(q), d[pd.qcut(d.d1w, 4, labels=["Q1 tight", "Q2", "Q3", "Q4 loose"]) == q])
      for q in ["Q1 tight", "Q2", "Q3", "Q4 loose"]])

# E: directional break of the 0DTE range at open
lng = d[d["dir"] == "L"]; sht = d[d["dir"] == "S"]
show("\nE) directional open-break of 0DTE range:",
     [("L open>cr0", lng[lng.o > lng.cr0]), ("L open<=cr0", lng[lng.o <= lng.cr0]),
      ("S open<ps0", sht[sht.o < sht.ps0]), ("S open>=ps0", sht[sht.o >= sht.ps0])])

# per-year robustness of the strongest cut (open inside vs outside range)
d["outside"] = (d.o < d.ps0) | (d.o > d.cr0)
print("\nper-year: OUTSIDE-range vs INSIDE-range (net | PF):")
for y in sorted(d.Date.str[:4].unique()):
    yd = d[d.Date.str[:4] == y]; out = yd[yd.outside]; ins = yd[~yd.outside]
    print(f"  {y}  outside n={len(out):3d} {out.net.sum():+7,.0f}/{pf(out.net):<5}   inside n={len(ins):3d} {ins.net.sum():+7,.0f}/{pf(ins.net)}")

d.to_csv(WT / "data" / "regime" / "tradeday_0dte_20260725.csv", index=False)
print("\nsaved data/regime/tradeday_0dte_20260725.csv")
