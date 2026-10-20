"""bid_ask_window_check.py — ad-hoc verification tool: aggregate
data/bid_ask/bid_ask_vol_buckets.csv into fixed time bins over a requested CT window and
print/save the ask/bid split + resulting ratio, so a flatline complaint on the live NT8
BidAskVolumeRatio/Delta/Split panel can be checked against the real underlying data instead
of guessed at. Built 2026-10-20 to verify a specific overnight-session flatline report.

    python scripts/bid_ask_window_check.py --date 2026-10-20 --start 04:25 --end 05:40
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
OUT_DIR = ROOT / "data" / "bid_ask" / "_analysis"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (the bucket log's own `date` column)")
    ap.add_argument("--start", required=True, help="HH:MM CT")
    ap.add_argument("--end", required=True, help="HH:MM CT")
    ap.add_argument("--bin-min", type=float, default=1.0, help="aggregation bin width in minutes (default 1)")
    a = ap.parse_args()

    df = pd.read_csv(LOG)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df = df[df["date"].astype(str) == a.date]

    start = pd.to_datetime(f"{a.date} {a.start}")
    end = pd.to_datetime(f"{a.date} {a.end}")
    win = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].sort_values("timestamp")

    if win.empty:
        print(f"NO ROWS AT ALL for {a.date} {a.start}-{a.end} CT -- genuine data gap.")
        return 0

    win = win.set_index("timestamp")
    agg = win.resample(f"{a.bin_min}min").agg(ask_vol=("ask_vol", "sum"), bid_vol=("bid_vol", "sum"))
    agg["total"] = agg["ask_vol"] + agg["bid_vol"]
    agg["ratio_pct"] = (100.0 * (agg["ask_vol"] - agg["bid_vol"]) / agg["total"]).where(agg["total"] > 0, 0.0)

    print(f"{a.date} {a.start}-{a.end} CT, {a.bin_min}-min bins, {len(win)} raw bucket rows:")
    print(agg.to_string())

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"bid_ask_window_check_{a.date}_{stamp}.csv"
    agg.to_csv(out_path)
    print(f"\nsaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
