"""flip_sar_by_year.py — year-by-year robustness of the SAR/IBS flip variants (S117-tempo).
Reads the dated flip_sar_trades CSV (full scope).

    python tempo/scripts/flip_sar_by_year.py [--date YYYY-MM-DD]
"""
from __future__ import annotations
import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tempo" / "outputs"

ap = argparse.ArgumentParser()
ap.add_argument("--date", default=dt.date.today().isoformat())
a = ap.parse_args()
t = pd.read_csv(OUT / f"flip_sar_trades_{a.date}.csv")
t = t[t["scope"] == "full"].copy()
t["year"] = t["date"].str[:4]
piv = t.pivot_table(index="year", columns="variant", values="pnl", aggfunc="sum").round(1)
print("total pts by year:")
print(piv.to_string())
n = t.pivot_table(index="year", columns="variant", values="pnl", aggfunc="size")
print("\ntrades by year:")
print(n.to_string())
ibs_sar = t[t["variant"] == "IBS-SAR"]
rev = ibs_sar[ibs_sar["res"] == "rev"]
print(f"\nIBS-SAR rev exits: n={len(rev)}  avg pnl {rev['pnl'].mean():+.3f} pt  "
      f"median {rev['pnl'].median():+.3f}  share>0 {(rev['pnl']>0).mean():.1%}")
