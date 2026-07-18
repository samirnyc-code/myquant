"""Pull MenthorQ Swing Trading Model levels (SPX + MAG7) and accumulate history.

The API hard-caps at 5 trading days per call (see mq_api.py docstring) -- this
script is the only way to build a longer record: run it daily, append new
(ticker, date) rows, dedup.

Usage:
  python scripts/mq_swing_pull.py

Output: data/menthorq/swing_levels/swing_levels_history.csv
"""
import csv
from pathlib import Path

from mq_api import MQ

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "menthorq" / "swing_levels" / "swing_levels_history.csv"

TICKERS = ["SPX", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]


def main():
    mq = MQ()

    existing = set()
    if OUT_CSV.exists():
        with open(OUT_CSV) as f:
            for row in csv.DictReader(f):
                existing.add((row["ticker"], row["date"]))

    all_new = []
    for ticker in TICKERS:
        try:
            data = mq.swing_levels(ticker)
        except Exception as e:
            print(f"  {ticker}: FAILED ({e})")
            continue
        fresh = [
            {"ticker": ticker, "date": r["date"], "direction": r["direction"],
             "band": r["band"], "trigger": r["trigger"]}
            for r in data if (ticker, r["date"]) not in existing
        ]
        all_new.extend(fresh)
        latest = data[0] if data else None
        print(f"  {ticker}: {len(fresh)} new row(s)"
              + (f" -- latest {latest['date']} {latest['direction']} band={latest['band']:.2f}"
                 if latest else ""))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not OUT_CSV.exists()
    with open(OUT_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "date", "direction", "band", "trigger"])
        if write_header:
            w.writeheader()
        w.writerows(all_new)

    print(f"\n{len(all_new)} new rows appended -> {OUT_CSV}")


if __name__ == "__main__":
    main()
