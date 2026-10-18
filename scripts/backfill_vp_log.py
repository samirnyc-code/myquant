"""backfill_vp_log.py — backfill SessionSRLevelsV10's developing-POC/VA from the
recorded L1 tape, instead of waiting for the live NT8 feature to build history one
day at a time going forward (its documented limitation — see SessionSRLevelsV10.cs
header comment and FinalizeDevPocVa).

Writes TWO logs from the same source data:

  session_vp_live_log.csv       date,vpoc,vah,val          -- each day's FINAL value
  session_vp_dev_trail.csv      date,timestamp,poc,vah,val -- the INTRADAY SHAPE: the
                                 developing POC/VAH/VAL recomputed cumulatively every
                                 `--bucket-minutes` of session time (default 5), so NT8
                                 can draw how the level actually moved through a
                                 historical session bar-by-bar, not just its finished
                                 end-of-day value. `timestamp` is the bucket's own real
                                 CT-naive calendar+clock time (may fall on the calendar
                                 date BEFORE `date` for early-session/overnight buckets
                                 — stored as a full timestamp, not just a time-of-day,
                                 specifically so NT8 can compare it directly against a
                                 bar's own converted time without any midnight-wrap
                                 ambiguity). Consecutive buckets with an unchanged
                                 result are not re-emitted (keeps the file small).

Both derived from the SAME cumulative-from-session-open volume_at_price()/value_area()
as volume_profile.py (pct=0.70, matching V10's VaPercent default), from ALL Ev=='T'
rows of the FULL Globex trading day (no RTH/ETH split — matches FinalizeDevPocVa's own
scope exactly). Computed straight from the raw per-contract L1 tape (data/l1_tape/),
NOT tickdata.py's back-adjusted continuous troves — same reasoning as
dtdb_sr_filter_check.py: the live NT8 chart shows the actual contract's raw price, so
levels must come from the same raw-contract source or they'd be off by the roll amount.

Only ADDS rows for dates missing from a log; never overwrites a date already written,
unless --force is passed.

    python scripts/backfill_vp_log.py                 # all L1 tape days found
    python scripts/backfill_vp_log.py --day 2026-10-13
    python scripts/backfill_vp_log.py --bucket-minutes 1   # finer trail resolution
    python scripts/backfill_vp_log.py --force          # recompute every day, overwrite both logs
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from volume_profile import TICK, value_area, volume_at_price

L1_DIR = ROOT / "data" / "l1_tape"
VP_LOG = ROOT / "data" / "vp_levels" / "session_vp_live_log.csv"
TRAIL_LOG = ROOT / "data" / "vp_levels" / "session_vp_dev_trail.csv"
OUT_DIR = ROOT / "data" / "vp_levels" / "_analysis"
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
    trades["Volume"] = trades["Size"].astype("int64")
    trades["Time"] = pd.to_datetime(trades["Time"])
    return trades


def build_dev_trail(trades: pd.DataFrame, pct: float, bucket_minutes: int, tick: float = TICK) -> list[tuple[str, float, float, float]]:
    """Replay a day's trades cumulatively in `bucket_minutes` buckets, recomputing the
    developing POC/VAH/VAL after each bucket (running price->volume dict, updated
    incrementally — NOT a full rescan of all trades per bucket). Same cumulative-from-
    session-open semantic as the live NT8 OnMarketData/RecomputeDevPocVa path. Returns
    (timestamp_str, poc, vah, val) rows, de-duped on unchanged consecutive results."""
    t = trades.sort_values("Time")
    buckets = t["Time"].dt.floor(f"{bucket_minutes}min")
    running: dict[float, float] = {}
    rows: list[tuple[str, float, float, float]] = []
    prev: tuple[float, float, float] | None = None
    for bucket_time, g in t.groupby(buckets, sort=True):
        binned = (np.round(g["Price"] / tick) * tick).round(2)
        for px, v in g.groupby(binned)["Volume"].sum().items():
            running[px] = running.get(px, 0.0) + float(v)
        prices = np.array(sorted(running.keys()))
        if len(prices) < 3:
            continue
        full = np.round(np.round(np.arange(prices.min(), prices.max() + tick, tick) / tick) * tick, 2)
        vap = pd.Series([running.get(p, 0.0) for p in full], index=full)
        poc, va_lo, va_hi = value_area(vap, pct)
        cur = (round(poc, 2), round(va_hi, 2), round(va_lo, 2))
        if cur != prev:
            rows.append((bucket_time.strftime("%Y-%m-%d %H:%M"), cur[0], cur[1], cur[2]))
            prev = cur
    return rows


def existing_dates(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return set(pd.read_csv(log_path)["date"].astype(str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="single day YYYY-MM-DD (default: every L1 tape day found)")
    ap.add_argument("--pct", type=float, default=0.70, help="value-area fraction, matches V10's VaPercent default")
    ap.add_argument("--bucket-minutes", type=int, default=5, help="dev-trail snapshot resolution in session minutes")
    ap.add_argument("--force", action="store_true", help="recompute days already in the logs and overwrite them")
    a = ap.parse_args()

    days = available_days()
    targets = [a.day] if a.day else sorted(days.keys())
    have_final = set() if a.force else existing_dates(VP_LOG)
    have_trail = set() if a.force else existing_dates(TRAIL_LOG)
    have = have_final & have_trail   # only fully skip a day if BOTH logs already have it

    rows_new: list[tuple[str, float, float, float]] = []
    trail_rows_new: list[tuple[str, str, float, float, float]] = []   # date, timestamp, poc, vah, val
    skipped: list[tuple[str, str]] = []

    for day in targets:
        if day in have:
            skipped.append((day, "already in both logs"))
            continue
        path = days.get(day)
        if path is None:
            skipped.append((day, "no L1 file"))
            continue
        trades = load_trades(path)
        if len(trades) < MIN_TRADE_ROWS:
            skipped.append((day, f"stub/partial file ({len(trades)} trade rows)"))
            continue

        if day not in have_final:
            vap = volume_at_price(trades)
            if len(vap) < 3:
                skipped.append((day, "too few price levels"))
                continue
            vpoc, va_lo, va_hi = value_area(vap, a.pct)
            rows_new.append((day, round(vpoc, 2), round(va_hi, 2), round(va_lo, 2)))
            print(f"{day}: VPOC {vpoc:.2f}  VA {va_lo:.2f}-{va_hi:.2f}  ({len(trades):,} trades, {path.name})")

        if day not in have_trail:
            trail = build_dev_trail(trades, a.pct, a.bucket_minutes)
            for ts, poc, vah, val in trail:
                trail_rows_new.append((day, ts, poc, vah, val))
            print(f"{day}: dev trail {len(trail)} snapshot(s) @ {a.bucket_minutes}min buckets")

    if rows_new:
        existing = pd.read_csv(VP_LOG) if VP_LOG.exists() and not a.force else pd.DataFrame(columns=["date", "vpoc", "vah", "val"])
        if a.force:
            new_days = {r[0] for r in rows_new}
            existing = existing[~existing["date"].astype(str).isin(new_days)]
        new_df = pd.DataFrame(rows_new, columns=["date", "vpoc", "vah", "val"])
        out = (pd.concat([existing, new_df], ignore_index=True)
                 .drop_duplicates("date", keep="last")
                 .sort_values("date"))
        VP_LOG.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(VP_LOG, index=False)
        print(f"\nwrote {len(rows_new)} new day(s) to {VP_LOG} (log now has {len(out)} day(s) total)")
    else:
        print("\nnothing new for the final-value log.")

    if trail_rows_new:
        existing_t = pd.read_csv(TRAIL_LOG) if TRAIL_LOG.exists() and not a.force else pd.DataFrame(columns=["date", "timestamp", "poc", "vah", "val"])
        if a.force:
            new_days = {r[0] for r in trail_rows_new}
            existing_t = existing_t[~existing_t["date"].astype(str).isin(new_days)]
        new_t_df = pd.DataFrame(trail_rows_new, columns=["date", "timestamp", "poc", "vah", "val"])
        out_t = pd.concat([existing_t, new_t_df], ignore_index=True).sort_values(["date", "timestamp"])
        TRAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
        out_t.to_csv(TRAIL_LOG, index=False)
        days_in_trail = out_t["date"].nunique()
        print(f"wrote {len(trail_rows_new)} new snapshot row(s) to {TRAIL_LOG} (log now covers {days_in_trail} day(s))")
    else:
        print("nothing new for the dev-trail log.")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audit = OUT_DIR / f"vp_backfill_{stamp}.csv"
    added_df = pd.DataFrame(rows_new, columns=["date", "vpoc", "vah", "val"])
    added_df["status"] = "added"
    skipped_df = pd.DataFrame(skipped, columns=["date", "status"])
    pd.concat([added_df, skipped_df], ignore_index=True).to_csv(audit, index=False)
    print(f"audit trail: {audit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
