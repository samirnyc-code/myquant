"""Replay bid_ask_vol_buckets.csv through the EXACT same algorithm CumulativeDelta.cs
uses (runCum += askVol - bidVol per bucket, reset to 0 at session's first bar) to get
real numbers for the two square-pulse-looking spikes the user saw on the 2026-11-05
chart (~08:48-09:01 CT and ~10:23-10:50 CT), instead of reading pixels off a
screenshot. Prints the running total bucket-by-bucket through both windows plus the
single largest buckets in each, so the actual shape (gradual vs instant) is visible.

Usage: .venv/Scripts/python.exe scripts/cumdelta_1105_spike_check.py
"""
import csv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUCKETS = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
DAY = "2026-11-05"
SESSION_START = datetime.strptime(f"{DAY} 00:00:00", "%Y-%m-%d %H:%M:%S")   # Session reset is Bars.IsFirstBarOfSession; ETH session for ES starts ~17:00 CT prior day, but checking same-day-only is enough to see the spike shape


def load_buckets():
    rows = []
    with open(BUCKETS, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        for row in r:
            if not row or row[0] != DAY:
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
    rows = load_buckets()
    print(f"{len(rows)} buckets loaded for {DAY}")

    run_cum = 0.0
    windows = [("08:45:00", "09:10:00"), ("10:20:00", "10:55:00")]
    window_hits = {w: [] for w in windows}

    for ts, ask, bid in rows:
        run_cum += ask - bid
        hhmmss = ts.strftime("%H:%M:%S")
        for w in windows:
            if w[0] <= hhmmss <= w[1]:
                window_hits[w].append((ts, ask, bid, run_cum))

    for w in windows:
        hits = window_hits[w]
        print(f"\n=== window {w[0]}-{w[1]} CT: {len(hits)} buckets ===")
        if not hits:
            continue
        print(f"runCum at window start: {hits[0][3] - (hits[0][1] - hits[0][2]):.0f}")
        print(f"runCum at window end:   {hits[-1][3]:.0f}")
        biggest = sorted(hits, key=lambda h: abs(h[1] - h[2]), reverse=True)[:5]
        print("5 largest single-bucket moves in this window:")
        for ts, ask, bid, cum in biggest:
            print(f"  {ts.strftime('%H:%M:%S.%f')[:-3]}  ask={ask:>6.0f} bid={bid:>6.0f}  "
                  f"delta={ask-bid:>+7.0f}  runCum after={cum:>+9.0f}")
        # print the full sequence so a sudden jump is visible as a single-row outlier vs gradual
        print("full sequence (runCum after each bucket):")
        for ts, ask, bid, cum in hits:
            print(f"  {ts.strftime('%H:%M:%S.%f')[:-3]}  ask={ask:>6.0f} bid={bid:>6.0f}  runCum={cum:>+9.0f}")


if __name__ == "__main__":
    main()
