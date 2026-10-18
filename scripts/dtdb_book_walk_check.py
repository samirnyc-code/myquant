"""dtdb_book_walk_check.py — for a bar range where CVD/delta was heavily negative
while price rose, check whether the best bid/ask quotes (Ev=="A"/"B" rows in the L1
tape, NOT the Ev=="T" trades) were walking UP over the same stretch. If so, that's the
mechanism: aggressive sellers were hitting the bid, but the bid itself kept getting
replaced higher, so sell-aggressor trades still print at rising prices. Trade aggressor
side tells you who crossed the spread on each print; it does not by itself tell you
which way the book is moving.

    python scripts/dtdb_book_walk_check.py --day 2026-10-13 --from-bar 685 --to-bar 700
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from dtdb_cvd_backtest import build_tick_bars

OUT = L1_DIR / "_analysis"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--from-bar", type=int, required=True)
    ap.add_argument("--to-bar", type=int, required=True)
    a = ap.parse_args()

    df = load_day(a.day)
    rth = rth_only(df, a.day)
    bars = build_tick_bars(rth, a.ticks)

    t_lo = bars["t"].iat[max(0, a.from_bar - 1)]
    t_hi = bars["t"].iat[min(len(bars) - 1, a.to_bar)]
    window = rth[(rth["Time"] >= t_lo) & (rth["Time"] <= t_hi)]

    bid = window[window["Ev"] == "B"]
    ask = window[window["Ev"] == "A"]
    trades = window[window["Ev"] == "T"]

    print(f"window: bar {a.from_bar} -> {a.to_bar}  ({t_lo} -> {t_hi})")
    print(f"best BID quotes: first={bid['Price'].iloc[0]:.2f}  last={bid['Price'].iloc[-1]:.2f}  "
          f"min={bid['Price'].min():.2f}  max={bid['Price'].max():.2f}  "
          f"net change={bid['Price'].iloc[-1]-bid['Price'].iloc[0]:+.2f}")
    print(f"best ASK quotes: first={ask['Price'].iloc[0]:.2f}  last={ask['Price'].iloc[-1]:.2f}  "
          f"min={ask['Price'].min():.2f}  max={ask['Price'].max():.2f}  "
          f"net change={ask['Price'].iloc[-1]-ask['Price'].iloc[0]:+.2f}")

    sell_hits = trades[trades["Aggr"] == "B"]   # sell-aggressor trades (hit the bid)
    buy_hits = trades[trades["Aggr"] == "A"]
    print(f"\nsell-aggressor trades (hit the bid): {len(sell_hits)}  total size {sell_hits['Size'].sum()}")
    print(f"buy-aggressor trades (lifted the ask): {len(buy_hits)}  total size {buy_hits['Size'].sum()}")

    if len(sell_hits) > 1:
        print(f"\nsell-aggressor trade prices, first 5 -> last 5 (were they rising even though seller-initiated?):")
        print("  first 5:", sell_hits["Price"].head(5).tolist())
        print("  last 5: ", sell_hits["Price"].tail(5).tolist())
        print(f"  net change in sell-hit price: {sell_hits['Price'].iloc[-1] - sell_hits['Price'].iloc[0]:+.2f}")

    # bid-level walk: sample every Nth bid update to show the climb without flooding output
    n = len(bid)
    step = max(1, n // 25)
    print(f"\nbid price sampled every {step} updates ({n} total bid updates in window):")
    sample = bid.iloc[::step][["Time", "Price", "Size"]]
    print(sample.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
