#!/usr/bin/env python3
"""
One-time script: build per-quarter Parquet cache from all SCID files.

Each SCID file is read once with the optimised loader (integer UTC pre-filter +
integer RTH check), then split by calendar quarter and written as individual
snappy-compressed Parquet files in the cache directory.

Usage
-----
    python scripts/build_scid_cache.py              # skip already-cached quarters
    python scripts/build_scid_cache.py --force      # overwrite everything

Output
------
    <SCID_DATA_DIR>/_scid_cache/<quarter>.parquet   e.g. 2024Q1.parquet
    <SCID_DATA_DIR>/_scid_cache/last_selection.json (not written by this script)

After this script finishes, open the app and click "Load selected quarters" — all
quarters will be in cache and will load in seconds instead of minutes.
"""

import argparse
import sys
import time
from pathlib import Path

# Make data_loader importable from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from data_loader import (
    SCID_DATA_DIR,
    SCID_CACHE_DIR,
    build_scid_quarter_map,
    load_scid_ticks_chunked,
    list_cached_quarters,
)


def build_cache(force: bool = False) -> None:
    SCID_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"SCID source : {SCID_DATA_DIR}")
    print(f"Cache target: {SCID_CACHE_DIR}")
    print()

    print("Scanning SCID files for available quarters…", flush=True)
    q_map = build_scid_quarter_map()   # {quarter_str: scid_path}
    if not q_map:
        print("No SCID files found.")
        return

    already_cached = set(list_cached_quarters())
    print(f"Found {len(q_map)} quarters across {len(set(q_map.values()))} files.")
    print(f"Already cached: {len(already_cached)}")
    print()

    # Group quarters by SCID file so each file is read only once
    by_file: dict[Path, list[str]] = {}
    for q, path in q_map.items():
        by_file.setdefault(path, []).append(q)

    total_written = total_skipped = 0

    for path, quarters in sorted(by_file.items(), key=lambda x: x[0].name):
        todo   = [q for q in quarters if force or q not in already_cached]
        cached = [q for q in quarters if q in already_cached and not force]

        if cached:
            print(f"{path.name}: skip {cached}")
            total_skipped += len(cached)

        if not todo:
            continue

        size_gb = path.stat().st_size / 1e9
        print(f"{path.name}  ({size_gb:.2f} GB)  →  parsing {todo} …", flush=True)
        t0 = time.perf_counter()

        ticks = load_scid_ticks_chunked(path, set(todo))
        elapsed = time.perf_counter() - t0

        if ticks.empty:
            print(f"  no RTH ticks found  ({elapsed:.1f}s)")
            continue

        # Split by calendar quarter and write one Parquet per quarter
        yq_int = ticks["DateTime"].dt.year * 10 + ((ticks["DateTime"].dt.month - 1) // 3 + 1)
        for q in todo:
            yr, qn = int(q[:4]), int(q[5])
            subset = ticks[yq_int == yr * 10 + qn].reset_index(drop=True)
            if subset.empty:
                print(f"  {q}: 0 ticks (no output)")
                continue
            out = SCID_CACHE_DIR / f"{q}.parquet"
            subset.to_parquet(out, index=False, compression="snappy")
            size_kb = out.stat().st_size // 1024
            print(f"  {q}: {len(subset):,} RTH ticks  →  {out.name}  ({size_kb:,} KB)")
            total_written += 1

        print(f"  file done in {elapsed:.1f}s")

    print()
    print(f"Done.  Wrote {total_written} quarters, skipped {total_skipped}.")
    print(f"Cache: {SCID_CACHE_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build per-quarter Parquet cache from all SCID files"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite already-cached quarters",
    )
    args = parser.parse_args()

    t_start = time.perf_counter()
    build_cache(force=args.force)
    print(f"\nTotal time: {(time.perf_counter() - t_start) / 60:.1f} min")
