"""
migrate_bar_labels.py — ONE-TIME S60 migration of existing bar parquets from
open-time labels to close-time labels. Idempotent: a file whose earliest
time-of-day label is 08:30 is open-labelled (shift by its bar period); a file
already starting later is skipped. Exact relabel — no rebuild, OHLCV untouched.
Covers: data/bars/*.parquet (5M per-contract + _continuous*), 15M (+15m),
1M (+1m). Tick parquets are real timestamps and are NOT touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars"


def offset_for(name: str) -> pd.Timedelta:
    if name == "_continuous_15m.parquet":
        return pd.Timedelta(minutes=15)
    if name == "_continuous_1m.parquet":
        return pd.Timedelta(minutes=1)
    return pd.Timedelta(minutes=5)


def main() -> None:
    undo = "--undo" in sys.argv   # revert close labels back to open labels
    shifted = skipped = 0
    for f in sorted(BARS.glob("*.parquet")):
        df = pd.read_parquet(f)
        if "DateTime" not in df.columns or df.empty:
            print(f"  ?? {f.name}: no DateTime column / empty — skipped")
            continue
        dt = pd.to_datetime(df["DateTime"])
        first_tod = min(dt.dt.time)
        is_open_labelled = first_tod == pd.Timestamp("08:30:00").time()
        if undo == is_open_labelled:   # nothing to do in this direction
            skipped += 1
            continue
        off = offset_for(f.name)
        df["DateTime"] = dt - off if undo else dt + off
        df.to_parquet(f, index=False)
        shifted += 1
        sign = "-" if undo else "+"
        print(f"  -> {f.name}: {sign}{int(off.total_seconds()//60)}m "
              f"({len(df):,} bars)")
    print(f"\n{'reverted' if undo else 'shifted'} {shifted} file(s), "
          f"skipped {skipped}")


if __name__ == "__main__":
    main()
