"""alwaysin_htf_ema_breakdown.py — post-hoc breakdown of a saved flip CSV.

Reads the latest (or a given) alwaysin_flips_*.csv from
data/alwaysin_htf_ema/_analysis/ (produced by alwaysin_htf_ema_study.py) and
splits every descriptive stat by flip `mechanism` (consecutive_close /
strong_breakout / gap). No re-pull of tick data — pure re-slicing of an
already-persisted result, so this is cheap to re-run as new slicing
questions come up (TOD buckets, dist_beyond_ema_abr buckets, etc. can be
added the same way).

Usage:
    python scripts/alwaysin_htf_ema_breakdown.py [path/to/alwaysin_flips_*.csv]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "data" / "alwaysin_htf_ema" / "_analysis"

METRICS = [
    "dist_beyond_ema_abr", "htf_ibs_signed", "thrust_distance_abr",
    "bars_to_extreme", "bars_extreme_to_pullback_start",
    "max_pullback_depth_abr", "deepest_bar_ibs_signed", "deepest_bar_range_abr",
]


def latest_csv() -> Path:
    files = sorted(ANALYSIS_DIR.glob("alwaysin_flips_*.csv"))
    if not files:
        raise FileNotFoundError(f"no alwaysin_flips_*.csv in {ANALYSIS_DIR}")
    return files[-1]


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_csv()
    print(f"Reading: {path}")
    df = pd.read_csv(path)
    n_days = df["date"].nunique()

    print(f"\nTotal flips: {len(df)}  |  Days: {n_days}  |  Flips/day: {len(df) / n_days:.2f}")
    counts = df["mechanism"].value_counts()
    print("\nBy mechanism (count, share, flips/day):")
    for mech, n in counts.items():
        print(f"  {mech:<18} n={n:>6}  {n / len(df):>5.1%}  {n / n_days:>5.2f}/day")

    print("\nPullback-found rate by mechanism:")
    print(df.groupby("mechanism")["pullback_found"].mean())

    print("\nPullback-touched-EMA rate by mechanism (of flips with a pullback):")
    pf = df[df["pullback_found"] == True]  # noqa: E712
    print(pf.groupby("mechanism")["pullback_touched_ema"].mean())

    print("\nMedian of each metric, by mechanism:")
    print(df.groupby("mechanism")[METRICS].median().T)

    print("\nMean of each metric, by mechanism:")
    print(df.groupby("mechanism")[METRICS].mean().T)

    print("\nTOD distribution (minutes since 08:30 open), by mechanism:")
    print(df.groupby("mechanism")["tod_minute_of_day"].describe()[["mean", "50%", "std"]])

    print("\nBy flip direction (+1 long / -1 short), overall:")
    print(df.groupby("direction")[METRICS].median().T)


if __name__ == "__main__":
    main()
