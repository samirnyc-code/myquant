"""backfill_bid_ask_log.py — backfill historical bid/ask-classified volume for the
live-only NT8 indicators (BidAskVolumeRatio.cs, BidAskVolumeDelta.cs,
BidAskVolumeSplit.cs, CumulativeDelta.cs), all of which depend on `OnMarketData` —
which NinjaTrader fires only on LIVE ticks, never on historical bars (same documented
limitation as the VP/POC-VA feature; see backfill_vp_log.py).

Writes ONE shared file every one of those indicators reads:

    data/bid_ask/bid_ask_vol_buckets.csv   date,timestamp,ask_vol,bid_vol

`timestamp` is a full CT-naive calendar+clock time (not time-of-day — avoids
midnight-wrap ambiguity for overnight buckets, same reasoning as
session_vp_dev_trail.csv). Buckets are `--bucket-seconds` wide (default 1s — far
finer than any realistic bar), so the NT8 side can sum exactly the buckets that fall
inside each bar's own (prevClose, thisClose] window and get a bar-ACCURATE
reconstruction regardless of bar type (tick/time/renko/whatever the chart uses),
instead of a pre-baked bar-type-specific guess.

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
    python scripts/backfill_bid_ask_log.py --bucket-seconds 2
    python scripts/backfill_bid_ask_log.py --force
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))

L1_DIR = ROOT / "data" / "l1_tape"
OUT_LOG = ROOT / "data" / "bid_ask" / "bid_ask_vol_buckets.csv"
OUT_DIR = ROOT / "data" / "bid_ask" / "_analysis"
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


def build_buckets(trades: pd.DataFrame, bucket_seconds: int) -> pd.DataFrame:
    t = trades.copy()
    t["ask"] = (t["Aggr"].astype(str) == "A") * t["Size"]
    t["bid"] = (t["Aggr"].astype(str) == "B") * t["Size"]
    t["bucket"] = t["Time"].dt.floor(f"{bucket_seconds}s")
    g = t.groupby("bucket", sort=True).agg(ask_vol=("ask", "sum"), bid_vol=("bid", "sum")).reset_index()
    g = g[(g["ask_vol"] > 0) | (g["bid_vol"] > 0)]   # drop empty buckets (shouldn't exist after groupby, but cheap safety)
    return g


def existing_days(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    return set(pd.read_csv(log_path)["date"].astype(str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="single day YYYY-MM-DD (default: every L1 tape day found)")
    ap.add_argument("--bucket-seconds", type=int, default=1, help="bucket width in seconds (default 1 -- widen if this proves too large/slow)")
    ap.add_argument("--force", action="store_true", help="recompute days already in the log and overwrite them")
    a = ap.parse_args()

    days = available_days()
    targets = [a.day] if a.day else sorted(days.keys())
    have = set() if a.force else existing_days(OUT_LOG)

    rows_new: list[tuple[str, str, int, int]] = []   # date, timestamp, ask_vol, bid_vol
    skipped: list[tuple[str, str]] = []

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

        buckets = build_buckets(trades, a.bucket_seconds)
        for _, r in buckets.iterrows():
            rows_new.append((day, r["bucket"].strftime("%Y-%m-%d %H:%M:%S"), int(r["ask_vol"]), int(r["bid_vol"])))
        print(f"{day}: {len(buckets):,} bucket(s) @ {a.bucket_seconds}s ({len(trades):,} trades, {path.name})")

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
        out.to_csv(OUT_LOG, index=False)
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
