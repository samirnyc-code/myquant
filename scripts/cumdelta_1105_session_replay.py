"""Clean, single-reset replay of the 2026-11-05 ES session's cumulative delta from the
raw bucket data, to compare against the live NT8 CumulativeDelta.cs chart -- which
shows 3 sharp drops to near-zero across the session (visually confirmed ~09:04 CT,
~11:01 CT, and a third one later), each looking exactly like a spurious
Bars.IsFirstBarOfSession reset. This script sums the SAME buckets in the SAME order
with NO resets (bid_ask_vol_buckets.csv's own column 1 is already the SESSION label,
not calendar date -- "2026-11-05" session data starts 2026-11-04 17:00 CT, confirmed),
so if the true running total is smooth and non-zero at those 3 timestamps while NT8
shows ~0, that proves the resets are spurious (a session-template issue), not real.

Usage: .venv/Scripts/python.exe scripts/cumdelta_1105_session_replay.py
"""
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
SESSION = "2026-11-05"
# the 3 apparent reset points off the chart, anchored to full calendar date+time (the
# session spans 2026-11-04 17:00 -> 2026-11-05 16:00, so a plain HH:MM:SS string match
# wrongly matches the first (11-04 17:00) bucket for any check time < "17:00:00" -- fixed
# by using full datetimes).
CHECK_TIMES = [
    datetime(2026, 11, 5, 9, 4, 0),
    datetime(2026, 11, 5, 11, 1, 0),
    datetime(2026, 11, 5, 18, 19, 0),
]


def load_session_buckets():
    rows = []
    with open(BUCKETS, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        for row in r:
            if not row or row[0] != SESSION:
                continue
            try:
                ts = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                ts = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S")
            ask, bid = float(row[2]), float(row[3])
            rows.append((ts, ask, bid))
    rows.sort(key=lambda x: x[0])
    return rows


def main():
    rows = load_session_buckets()
    if not rows:
        print(f"no buckets found for session {SESSION}")
        return
    print(f"session {SESSION}: {len(rows)} buckets, {rows[0][0]} -> {rows[-1][0]}")

    run_cum = 0.0
    checks = {t: None for t in CHECK_TIMES}
    hourly = {}
    for ts, ask, bid in rows:
        run_cum += ask - bid
        hour_key = ts.strftime("%m-%d %H:00")
        hourly[hour_key] = run_cum   # last value seen in that hour -> running snapshot
        for t in CHECK_TIMES:
            if checks[t] is None and ts >= t:
                checks[t] = (ts, run_cum)

    print(f"\nfinal session runCum (should match NT8's end-of-session value, no resets applied): {run_cum:+.0f}")

    print("\n--- true runCum at the 3 apparent reset points on the chart (should be non-zero/smooth) ---")
    for t in CHECK_TIMES:
        hit = checks[t]
        if hit:
            print(f"  ~{t} CT: true runCum = {hit[1]:+.0f}  (actual bucket ts {hit[0]})")
        else:
            print(f"  ~{t} CT: no bucket data at/after this time in the session")

    print("\n--- hourly snapshot of the clean single-reset running total ---")
    for k in sorted(hourly, key=lambda k: datetime.strptime(k, "%m-%d %H:00")):
        print(f"  {k}: {hourly[k]:+.0f}")


if __name__ == "__main__":
    main()
