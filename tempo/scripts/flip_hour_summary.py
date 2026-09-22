"""flip_hour_summary.py — post-hoc check: is the first-hour tilt in the 1yr RR3 flip
backtest also present over the full history? (S117-tempo; reads the dated trades CSV.)

    python tempo/scripts/flip_hour_summary.py [--date YYYY-MM-DD]
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
t = pd.read_csv(OUT / f"flip_backtest_trades_{a.date}.csv")
t = t[(t["scope"] == "full") & (t["variant"] == "RR3")].copy()
t["hour"] = (t["session_min"] // 60).astype(int)
t["year"] = t["date"].str[:4]
print("full-history RR3 by session hour:")
print(t.groupby("hour").agg(n=("pnl_pts", "size"), avg_pts=("pnl_pts", "mean"),
                            total=("pnl_pts", "sum"), win=("res", lambda s: (s == "target").mean())).round(3).to_string())
print("\nfirst hour (h0) by year:")
h0 = t[t["hour"] == 0]
print(h0.groupby("year").agg(n=("pnl_pts", "size"), avg_pts=("pnl_pts", "mean"),
                             total=("pnl_pts", "sum")).round(2).to_string())
