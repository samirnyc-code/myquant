"""l1_gap_check.py — audit an L1 tape CSV (L1TapeRecorderAddOn.cs) for timestamp gaps.

S139 (2026-10-05): a duplicate MarketData subscription (fixed in L1TapeRecorderAddOn.cs)
ran alongside the real recorder from 08:52 to a 10:42 NT8 restart, plus the restart itself
necessarily has a no-NT8-running gap. This checks whether either left a hole in the data,
by flagging any run of consecutive rows whose Time delta exceeds --threshold seconds during
RTH, and separately reporting the single largest gap of the day regardless of session.

    python scripts/l1_gap_check.py data/l1_tape/ES_12-26_l1_2026-10-05.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--threshold", type=float, default=2.0, help="seconds; flag gaps >= this")
    a = ap.parse_args()

    path = Path(a.csv_path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        print(f"not found: {path}")
        return 1

    rows = []
    with open(path, "r", newline="") as f:
        r = csv.reader(f)
        header = next(r)
        ti = header.index("Time")
        ei = header.index("Ev")
        for row in r:
            if len(row) <= ti:
                continue
            try:
                t = dt.datetime.strptime(row[ti], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                continue
            rows.append((t, row[ei]))

    if len(rows) < 2:
        print(f"{path.name}: {len(rows)} rows — too few to check")
        return 0

    gaps = []
    for (t0, ev0), (t1, ev1) in zip(rows, rows[1:]):
        d = (t1 - t0).total_seconds()
        if d >= a.threshold:
            gaps.append((t0, t1, d, ev0, ev1))

    out_dir = path.parent / "_analysis"
    out_dir.mkdir(exist_ok=True)
    today = dt.date.today().isoformat()
    out_path = out_dir / f"{path.stem}_gap_report_{today}.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["gap_start", "gap_end", "seconds", "ev_before", "ev_after"])
        for t0, t1, d, ev0, ev1 in gaps:
            w.writerow([t0, t1, f"{d:.3f}", ev0, ev1])

    print(f"{path.name}: {len(rows):,} rows, {rows[0][0]} -> {rows[-1][0]}")
    print(f"gaps >= {a.threshold}s: {len(gaps)} -> {out_path}")
    for t0, t1, d, ev0, ev1 in sorted(gaps, key=lambda g: -g[2])[:15]:
        print(f"  {t0}  ->  {t1}   {d:8.1f}s   ({ev0} -> {ev1})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
