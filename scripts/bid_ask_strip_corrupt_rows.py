"""bid_ask_strip_corrupt_rows.py — remove rows from data/bid_ask/bid_ask_vol_buckets.csv
whose `date` column isn't a real YYYY-MM-DD date.

Built 2026-11-05 after finding a literal truncated row ("48,,,") at the tail of the log,
left over from the pre-atomic-write race that backfill_bid_ask_log.py's 2026-10-20 os.replace()
fix (see its own comment) prevents going forward but doesn't retroactively clean. Harmless to
the NT8 readers (they TryParse and skip it) but not harmless to this script's own existing_days()
set, which would otherwise carry "48" around as a phantom already-backfilled "day" forever.

    python scripts/bid_ask_strip_corrupt_rows.py
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> int:
    df = pd.read_csv(LOG, dtype=str)
    bad = ~df["date"].astype(str).str.match(DATE_RE)
    n_bad = int(bad.sum())
    if n_bad == 0:
        print("no corrupt rows found.")
        return 0
    print(f"dropping {n_bad} corrupt row(s):")
    print(df[bad].to_string())
    df = df[~bad]
    tmp_path = LOG.with_suffix(LOG.suffix + f".tmp{os.getpid()}")
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, LOG)
    print(f"wrote {len(df):,} rows back to {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
