"""bid_ask_coverage_gap_scan.py — scan data/bid_ask/bid_ask_vol_buckets.csv for gaps inside
RTH hours (08:30-15:15 CT) on each day present in the log, bigger than --min-gap-min.

Built 2026-10-20 while root-causing a user-reported BidAskVolumeRatio flatline: found
2026-10-19 had a real ~70min RTH gap (14:49:43-15:59:xx CT) caused by `backfill_bid_ask_log.py`
having been force-run against a PARTIAL/still-growing parquet snapshot at some point, then never
revisited, because `desk_watchdog.py`'s `refresh_bid_ask_backfill` only ever re-forces TODAY's
calendar date -- it has no mechanism to go back and repair a day that's no longer "today" even
if that day's own last backfill run happened to catch it mid-write. This scan exists to check
how widespread that pattern is across the whole log, not just the one day already manually fixed.

    python scripts/bid_ask_coverage_gap_scan.py
    python scripts/bid_ask_coverage_gap_scan.py --min-gap-min 15
"""
from __future__ import annotations

import argparse
from datetime import datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
OUT_DIR = ROOT / "data" / "bid_ask" / "_analysis"

RTH_START = time(8, 30)
RTH_END = time(15, 15)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-gap-min", type=float, default=10.0, help="flag gaps at least this many minutes wide (default 10)")
    a = ap.parse_args()

    df = pd.read_csv(LOG)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values(["date", "timestamp"])

    rows = []
    for day, g in df.groupby("date"):
        g = g.sort_values("timestamp")
        ts = g["timestamp"]
        gaps = ts.diff().dt.total_seconds() / 60.0
        rth_mask = (ts.dt.time >= RTH_START) & (ts.dt.time <= RTH_END)
        for i in range(1, len(g)):
            if not (rth_mask.iloc[i] and rth_mask.iloc[i - 1]):
                continue
            gap_min = gaps.iloc[i]
            if gap_min >= a.min_gap_min:
                rows.append({
                    "date": day,
                    "gap_start_ct": ts.iloc[i - 1],
                    "gap_end_ct": ts.iloc[i],
                    "gap_min": round(gap_min, 1),
                })

    out = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"bid_ask_coverage_gap_scan_{stamp}.csv"
    out.to_csv(out_path, index=False)

    if out.empty:
        print(f"no RTH gaps >= {a.min_gap_min} min found across {df['date'].nunique()} day(s) in the log.")
    else:
        print(f"{len(out)} RTH gap(s) >= {a.min_gap_min} min found across {out['date'].nunique()} day(s):")
        print(out.to_string(index=False))
    print(f"\nsaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
