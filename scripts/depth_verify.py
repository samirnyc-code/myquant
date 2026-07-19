"""depth_verify.py — is the L2 (market-depth) feed actually landing?

Run this after applying MarketDepthLogger to a live ES chart with a CME depth
subscription active. It answers three questions:

  1. Are BOOK events arriving at all?  (the 7/17 capture had ZERO — trades only,
     which is how we proved the depth subscription was missing)
  2. Does the book look sane?          (levels 0..N, both sides, plausible prices)
  3. What is the REAL data rate?       (MB/hour + projected MB/day, so we stop
     guessing at disk burn before recording unattended)

Usage:
    python scripts/depth_verify.py                      # today's ES file
    python scripts/depth_verify.py --date 2026-07-20
    python scripts/depth_verify.py --watch              # re-check every 60s

Exit code 0 = book events present, 1 = trades only / no file (feed not live).
"""
import argparse
import datetime as dt
import os
import sys
import time

import pandas as pd

DEPTH_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "depth")
COLS = ["Time", "Ev", "Side", "Pos", "Price", "Size"]


def chicago_today():
    """MarketDepthLogger names files from NT8's clock (Chicago), but this PC runs on
    Berlin time. At the 17:00 CT ETH open it is already tomorrow in Berlin, so a naive
    date.today() looks for a file that does not exist. Always anchor to Chicago."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    except Exception:
        # zoneinfo missing (no tzdata): fall back to a fixed CDT offset
        return (dt.datetime.utcnow() - dt.timedelta(hours=5)).date().isoformat()


def find_file(date, symbol):
    """A single ETH session straddles Chicago midnight, so the session that opened at
    17:00 CT lands in TWO files. Return every file that could hold live data, newest last."""
    import glob as _glob
    hits = []
    d0 = dt.date.fromisoformat(date)
    for delta in (-1, 0):
        day = (d0 + dt.timedelta(days=delta)).isoformat()
        # filenames carry the FULL contract now (ES_09-26_depth_...), and the legacy
        # bare-symbol files (ES_depth_...) must still be readable
        hits += sorted(_glob.glob(os.path.join(DEPTH_DIR, f"{symbol}*_depth_{day}.csv")))
    return hits


def load(path):
    # tail-tolerant: the logger flushes every 5000 lines, so the last row can be partial
    d = pd.read_csv(path, on_bad_lines="skip")
    if list(d.columns) != COLS:
        raise SystemExit(f"unexpected columns {list(d.columns)} — is this a MarketDepthLogger file?")
    d["Time"] = pd.to_datetime(d["Time"], errors="coerce")
    return d.dropna(subset=["Time"])


def report(path):
    size_mb = os.path.getsize(path) / 1e6
    d = load(path)
    if d.empty:
        print(f"  {os.path.basename(path)} — EMPTY")
        return False

    book = d[d.Ev != "T"]
    tape = d[d.Ev == "T"]
    span = (d.Time.iloc[-1] - d.Time.iloc[0]).total_seconds()
    hours = span / 3600 if span > 0 else 0

    print(f"  file          : {os.path.basename(path)}  ({size_mb:,.1f} MB)")
    print(f"  span          : {d.Time.iloc[0]}  ->  {d.Time.iloc[-1]}   ({hours:.2f}h)")
    print(f"  rows          : {len(d):,}   book={len(book):,}   tape={len(tape):,}")

    if book.empty:
        print()
        print("  *** NO BOOK EVENTS - trades only. ***")
        print("  The depth subscription is NOT active on this feed (or the chart has")
        print("  no depth). Check: SuperDOM shows 10 levels => subscription is live.")
        return False

    # --- book sanity ---
    lv = sorted(book.Pos.unique())
    ev = book.Ev.value_counts().to_dict()
    sides = book.Side.value_counts().to_dict()
    print(f"  book levels   : {lv[0]}..{lv[-1]}  ({len(lv)} distinct)")
    print(f"  book events   : " + "  ".join(f"{k}={v:,}" for k, v in sorted(ev.items())))
    print(f"  sides         : bid={sides.get('B', 0):,}  ask={sides.get('A', 0):,}")

    best_bid = book[(book.Side == "B") & (book.Pos == 0)].Price
    best_ask = book[(book.Side == "A") & (book.Pos == 0)].Price
    if len(best_bid) and len(best_ask):
        print(f"  best bid rng  : {best_bid.min():,.2f} .. {best_bid.max():,.2f}")
        print(f"  best ask rng  : {best_ask.min():,.2f} .. {best_ask.max():,.2f}")
        if best_ask.median() <= best_bid.median():
            print("  !! WARNING: median ask <= median bid — sides may be mislabelled")

    # --- the number we actually came for ---
    if hours > 0:
        mb_h = size_mb / hours
        rows_s = len(d) / span
        print()
        print(f"  RATE          : {mb_h:,.1f} MB/hour   ({rows_s:,.0f} rows/sec)")
        print(f"  projected     : {mb_h * 23:,.0f} MB/day  (23h CME session)")
        print(f"                  {mb_h * 23 * 21 / 1000:,.1f} GB/month   "
              f"{mb_h * 23 * 252 / 1000:,.1f} GB/year")
        free_gb = free_space_gb()
        if free_gb and mb_h > 0:
            days = free_gb * 1000 / (mb_h * 23)
            print(f"  disk runway   : {free_gb:,.0f} GB free  =>  ~{days:,.0f} days uncompressed")
            print(f"                  ~{days * 10:,.0f} days if gzipped nightly (~10x on this data)")
    return True


def free_space_gb():
    try:
        return os.statvfs(DEPTH_DIR).f_bavail * os.statvfs(DEPTH_DIR).f_frsize / 1e9
    except AttributeError:  # Windows
        import ctypes
        free = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(
            ctypes.c_wchar_p(DEPTH_DIR), None, None, ctypes.pointer(free))
        return free.value / 1e9
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Chicago date (default: today in Chicago)")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--watch", action="store_true", help="re-check every 60s")
    a = ap.parse_args()
    date = a.date or chicago_today()

    while True:
        print(f"\n=== depth check  {a.symbol}  {date} (Chicago)  "
              f"| PC {dt.datetime.now():%H:%M} local ===")
        paths = find_file(date, a.symbol)
        if not paths:
            print(f"  no file: {DEPTH_DIR}\\{a.symbol}_depth_{date}.csv")
            print("  MarketDepthLogger is not running (or no events yet).")
            ok = False
        else:
            ok = False
            for p in paths:
                ok = report(p) or ok
                print()
        if not a.watch:
            sys.exit(0 if ok else 1)
        time.sleep(60)


if __name__ == "__main__":
    main()
