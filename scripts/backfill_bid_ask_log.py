"""backfill_bid_ask_log.py — backfill historical bid/ask-classified volume for the
live-only NT8 indicators (BidAskVolumeRatio.cs, BidAskVolumeDelta.cs,
BidAskVolumeSplit.cs, CumulativeDelta.cs), all of which depend on `OnMarketData` —
which NinjaTrader fires only on LIVE ticks, never on historical bars (same documented
limitation as the VP/POC-VA feature; see backfill_vp_log.py).

Writes ONE shared file every one of those indicators reads:

    data/bid_ask/bid_ask_vol_buckets.csv   date,timestamp,ask_vol,bid_vol

`timestamp` is a full CT-naive calendar+clock time, millisecond precision (not
time-of-day — avoids midnight-wrap ambiguity for overnight buckets, same reasoning
as session_vp_dev_trail.csv). Buckets are `--bucket-trades` TRADES wide (default 50
— NOT a fixed time width; see build_buckets()'s docstring for why: a fixed-time
bucket is too coarse during a fast burst, which is exactly when a tick-based bar
rolls fastest and needs the MOST resolution. Trade-count buckets adapt automatically
instead), so the NT8 side can sum exactly the buckets that fall inside each bar's
own (prevClose, thisClose] window and get a bar-ACCURATE reconstruction regardless
of bar type (tick/time/renko/whatever the chart uses).

Ask/bid volume per trade comes straight from the L1 tape's own `Aggr` column
(A=ask aggressor, B=bid aggressor) — the SAME classification
scripts/bid_ask_volume_ratio_l1.py already uses, and l1_footprint.py validated exact
vs MzPack. NOTE this is NOT guaranteed byte-identical to BidAskVolumeRatio.cs's own
live tick-rule (price vs last quote) or CumulativeDelta.cs's live embedded-quote-
with-midpoint-tiebreak rule — it's the tape's own pre-resolved aggressor tag, a very
close but independently-computed proxy. Documented, not hidden.

Only ADDS days missing from the log; never overwrites a day already written, unless
--force is passed.

    python scripts/backfill_bid_ask_log.py                  # all L1 tape days found
    python scripts/backfill_bid_ask_log.py --day 2026-10-13
    python scripts/backfill_bid_ask_log.py --bucket-trades 25
    python scripts/backfill_bid_ask_log.py --force

--incremental mode (2026-11-05): a SEPARATE fast path for the one actively-growing L1
file. The --day/--force path above re-reads AND rewrites the entire output log (all
days, 800k+ rows) every single call -- measured 9s for a half-day of today's data,
extrapolates to ~190s by end of day (the watchdog's own subprocess timeout is 180s),
because of the full read-concat-sort-rewrite of the OUTPUT log, not the input trades
(reading the input L1 tape alone measured ~1s). --incremental instead:
  - finds whichever L1 file has the newest mtime (the one actually receiving ticks)
  - tracks how many of its trades were already bucketed in data/bid_ask/_backfill_cursor.json
  - buckets ONLY the new trades past that cursor
  - APPENDS those bucket rows to the output log via a raw byte copy + append + os.replace
    (never parses/rewrites the existing 800k+ rows), so run time scales with how much is
    NEW, not with total history size -- safe to run every 60-90s instead of every 30min.
A trailing partial bucket (fewer than --bucket-trades new trades) is left unconsumed and
picked up whole on the next run, never double-counted. The existing --day/--force full
sweep keeps running on its own (slower) schedule as a self-healing safety net -- unchanged.

    python scripts/backfill_bid_ask_log.py --incremental
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

L1_DIR = ROOT / "data" / "l1_tape"
OUT_LOG = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
OUT_DIR = ROOT / "data" / "bid_ask" / "_analysis"
CURSOR_FILE = ROOT / "data" / "bid_ask" / "_backfill_cursor.json"
MIN_TRADE_ROWS = 10_000   # below this a file is a recorder stub/partial day, not a full session

DAY_RE = re.compile(r"ES_[\w-]+_l1_(\d{4}-\d{2}-\d{2})\.(parquet|csv)$")


def available_days() -> dict[str, Path]:
    """One file per day: prefer .parquet, else the biggest .csv found."""
    by_day: dict[str, Path] = {}
    for p in sorted(L1_DIR.glob("ES_*_l1_*.*")):
        m = DAY_RE.search(p.name)
        if not m:
            continue
        day = m.group(1)
        cur = by_day.get(day)
        if cur is None:
            by_day[day] = p
        elif p.suffix == ".parquet" and cur.suffix != ".parquet":
            by_day[day] = p
        elif p.suffix == cur.suffix and p.stat().st_size > cur.stat().st_size:
            by_day[day] = p
    return by_day


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, low_memory=False)
    trades = df[df["Ev"] == "T"].copy()
    trades["Time"] = pd.to_datetime(trades["Time"])
    trades["Size"] = trades["Size"].astype("int64")
    return trades


def build_buckets(trades: pd.DataFrame, bucket_trades: int) -> pd.DataFrame:
    """Bucket by a FIXED TRADE COUNT, not fixed time (2026-10-19 revision — fixed-time
    buckets were too coarse during fast bursts: a 500-tick bar can complete in 1-2 seconds
    during an active move, so a 1-second bucket gave that bar almost no intrabar variation
    to reconstruct, which is exactly why CumulativeDelta.cs's historical candles looked like
    a flat smooth line instead of real texture. Trade-count buckets adapt automatically: tight
    in TIME exactly when trading is fast (matching a tick-based bar's own pacing), wide during
    quiet periods (where the underlying bar is also slow, so there's nothing lost)."""
    t = trades.sort_values("Time").reset_index(drop=True)
    t["ask"] = (t["Aggr"].astype(str) == "A") * t["Size"]
    t["bid"] = (t["Aggr"].astype(str) == "B") * t["Size"]
    t["bucket"] = np.arange(len(t)) // bucket_trades
    g = t.groupby("bucket", sort=True).agg(timestamp=("Time", "last"), ask_vol=("ask", "sum"), bid_vol=("bid", "sum")).reset_index(drop=True)
    g = g[(g["ask_vol"] > 0) | (g["bid_vol"] > 0)]
    return g


def existing_days(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return set(pd.read_csv(log_path)["date"].astype(str))


def active_l1_file() -> tuple[str, Path] | tuple[None, None]:
    """Whichever L1 file has the newest mtime -- the one actually receiving ticks
    right now. Same logic as desk_watchdog.py's current_l1_day(), kept separately
    here since this script owns the L1_DIR glob/regex already."""
    files = sorted(L1_DIR.glob("ES_*_l1_*.*"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None, None
    m = DAY_RE.search(files[-1].name)
    return (m.group(1), files[-1]) if m else (None, None)


def load_cursor() -> dict:
    if not CURSOR_FILE.exists():
        return {"day": None, "trades_consumed": 0}
    try:
        return json.loads(CURSOR_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return {"day": None, "trades_consumed": 0}


def save_cursor(day: str, trades_consumed: int) -> None:
    CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CURSOR_FILE.with_suffix(CURSOR_FILE.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps({"day": day, "trades_consumed": trades_consumed}))
    os.replace(tmp, CURSOR_FILE)


def append_rows_fast(rows: list[tuple[str, str, int, int]], log_path: Path) -> None:
    """Append-only, atomic: copy existing bytes + append new lines + os.replace --
    never parses or rewrites the rows already on disk (that full round-trip is exactly
    what made --force too slow to run every minute; see module docstring)."""
    lines = "".join(f"{d},{t},{a},{b}\n" for d, t, a, b in rows)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = log_path.with_suffix(log_path.suffix + f".tmp{os.getpid()}")
    if log_path.exists():
        shutil.copyfile(log_path, tmp_path)
        with open(tmp_path, "a", newline="") as fh:
            fh.write(lines)
    else:
        with open(tmp_path, "w", newline="") as fh:
            fh.write("date,timestamp,ask_vol,bid_vol\n")
            fh.write(lines)
    os.replace(tmp_path, log_path)


def run_incremental(bucket_trades: int) -> int:
    day, path = active_l1_file()
    if path is None:
        print("incremental: no L1 tape file found.")
        return 0

    cursor = load_cursor()
    consumed = cursor["trades_consumed"] if cursor.get("day") == day else 0

    trades = load_trades(path)
    trades = trades.sort_values("Time").reset_index(drop=True)

    if consumed == 0 and len(trades) < MIN_TRADE_ROWS:
        print(f"incremental: {day} is a stub/partial file ({len(trades)} trade rows) -- skipping.")
        return 0

    new_trades = trades.iloc[consumed:]
    n_complete = len(new_trades) // bucket_trades
    if n_complete == 0:
        print(f"incremental: {day} -- {len(new_trades)} new trade(s), fewer than {bucket_trades}/bucket, nothing to flush yet.")
        return 0

    slice_ = new_trades.iloc[: n_complete * bucket_trades]
    buckets = build_buckets(slice_, bucket_trades)
    rows_new = [
        (day, r["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], int(r["ask_vol"]), int(r["bid_vol"]))
        for _, r in buckets.iterrows()
    ]
    append_rows_fast(rows_new, OUT_LOG)
    save_cursor(day, consumed + n_complete * bucket_trades)
    print(f"incremental: {day} -- appended {len(rows_new)} new bucket row(s) "
          f"({n_complete * bucket_trades} trades consumed, cursor now {consumed + n_complete * bucket_trades}/{len(trades)}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="single day YYYY-MM-DD (default: every L1 tape day found)")
    ap.add_argument("--bucket-trades", type=int, default=50, help="bucket width in TRADE COUNT, not time (default 50 -- adapts to bar speed; see build_buckets() docstring)")
    ap.add_argument("--force", action="store_true", help="recompute days already in the log and overwrite them")
    ap.add_argument("--incremental", action="store_true",
                     help="fast path: append only new trades from the active (newest-mtime) L1 file; see module docstring")
    a = ap.parse_args()

    if a.incremental:
        return run_incremental(a.bucket_trades)

    days = available_days()
    targets = [a.day] if a.day else sorted(days.keys())
    have = set() if a.force else existing_days(OUT_LOG)

    rows_new: list[tuple[str, str, int, int]] = []   # date, timestamp, ask_vol, bid_vol
    skipped: list[tuple[str, str]] = []
    trade_counts: dict[str, int] = {}   # day -> len(trades), so a rebuild of the live day can resync the incremental cursor

    for day in targets:
        if day in have:
            skipped.append((day, "already in log"))
            continue
        path = days.get(day)
        if path is None:
            skipped.append((day, "no L1 file"))
            continue
        trades = load_trades(path)
        if len(trades) < MIN_TRADE_ROWS:
            skipped.append((day, f"stub/partial file ({len(trades)} trade rows)"))
            continue

        trade_counts[day] = len(trades)
        buckets = build_buckets(trades, a.bucket_trades)
        for _, r in buckets.iterrows():
            rows_new.append((day, r["timestamp"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], int(r["ask_vol"]), int(r["bid_vol"])))
        print(f"{day}: {len(buckets):,} bucket(s) @ {a.bucket_trades} trades/bucket ({len(trades):,} trades, {path.name})")

    # 2026-11-05: if this run just rebuilt the SAME day --incremental is tracking, its cursor
    # is now stale (--force included every trade up to just now, incremental doesn't know that)
    # -- the next incremental run would re-append the overlap as duplicate buckets. Resync it.
    active_day, _ = active_l1_file()
    if active_day in trade_counts:
        save_cursor(active_day, trade_counts[active_day])
        print(f"resynced incremental cursor: {active_day} -> {trade_counts[active_day]} trades consumed.")

    if rows_new:
        # ALWAYS load whatever's already on disk, even under --force -- force only means
        # "recompute the targeted day(s)", never "discard every other day already backfilled".
        # (2026-10-19: this exact line previously had "and not a.force" here, which skipped
        # loading entirely under --force and wiped the whole file down to just the day(s)
        # being recomputed -- lost 21 days of prior backfill in one `--day ... --force` run,
        # caught immediately and restored from git. Not touching this logic again without
        # re-reading this comment.)
        existing = pd.read_csv(OUT_LOG) if OUT_LOG.exists() else pd.DataFrame(columns=["date", "timestamp", "ask_vol", "bid_vol"])
        if a.force:
            new_days = {r[0] for r in rows_new}
            existing = existing[~existing["date"].astype(str).isin(new_days)]
        new_df = pd.DataFrame(rows_new, columns=["date", "timestamp", "ask_vol", "bid_vol"])
        out = pd.concat([existing, new_df], ignore_index=True).sort_values(["date", "timestamp"])
        OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
        # 2026-10-20: write to a temp file then atomically replace -- this script now runs on a
        # 30-min watchdog timer from BOTH the daemon (10s loop) and the one-shot (5-min) task,
        # and `to_csv` writing the target path directly is not atomic: two invocations landing
        # close together raced and corrupted the file (a literal truncated row, "48,,,", found
        # mid-session). os.replace() is atomic on the same filesystem -- no reader (this script's
        # own `pd.read_csv` above, or NT8's indicator) can ever observe a half-written file, and
        # if two writers still race, the later rename just cleanly wins instead of interleaving.
        tmp_path = OUT_LOG.with_suffix(OUT_LOG.suffix + f".tmp{os.getpid()}")
        out.to_csv(tmp_path, index=False)
        os.replace(tmp_path, OUT_LOG)
        days_covered = out["date"].nunique()
        print(f"\nwrote {len(rows_new):,} new bucket row(s) to {OUT_LOG} (log now covers {days_covered} day(s), {len(out):,} rows total)")
    else:
        print("\nnothing new to backfill.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit = OUT_DIR / f"bid_ask_backfill_{stamp}.csv"
    added_days = sorted({r[0] for r in rows_new})
    added_df = pd.DataFrame({"date": added_days, "status": "added"})
    skipped_df = pd.DataFrame(skipped, columns=["date", "status"])
    pd.concat([added_df, skipped_df], ignore_index=True).to_csv(audit, index=False)
    print(f"audit trail: {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
