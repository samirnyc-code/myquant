"""backfill_vp_log.py — backfill SessionSRLevelsV10's developing-POC/VA log
(data/vp_levels/session_vp_live_log.csv) from the recorded L1 tape, instead of
waiting for the live NT8 feature to build history one day at a time going
forward (its documented limitation — see SessionSRLevelsV10.cs header comment
and FinalizeDevPocVa).

V10's live OnMarketData bins EVERY trade tick of the FULL Globex trading day
(no RTH/ETH split — FinalizeDevPocVa fires at the whole-day roll, not the RTH
roll), so this mirrors that exactly: all Ev=='T' rows for the day, using the
already-validated volume_at_price()/value_area() from volume_profile.py
(pct=0.70, matching the indicator's VaPercent default). Computed straight from
the raw per-contract L1 tape (data/l1_tape/), NOT tickdata.py's back-adjusted
continuous troves — same reasoning as dtdb_sr_filter_check.py: the live NT8
chart shows the actual contract's raw price, so levels must come from the same
raw-contract source or they'd be off by the roll-adjustment amount.

Only ADDS rows for dates missing from the log; never overwrites a date the
live indicator already wrote, unless --force is passed.

    python scripts/backfill_vp_log.py                 # all L1 tape days found
    python scripts/backfill_vp_log.py --day 2026-10-13
    python scripts/backfill_vp_log.py --force          # recompute every day, overwrite log
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
from volume_profile import volume_at_price, value_area

L1_DIR = ROOT / "data" / "l1_tape"
VP_LOG = ROOT / "data" / "vp_levels" / "session_vp_live_log.csv"
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
    return trades


def existing_dates() -> set[str]:
    if not VP_LOG.exists():
        return set()
    return set(pd.read_csv(VP_LOG)["date"].astype(str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None, help="single day YYYY-MM-DD (default: every L1 tape day found)")
    ap.add_argument("--pct", type=float, default=0.70, help="value-area fraction, matches V10's VaPercent default")
    ap.add_argument("--force", action="store_true", help="recompute days already in the log and overwrite them")
    a = ap.parse_args()

    days = available_days()
    targets = [a.day] if a.day else sorted(days.keys())
    have = set() if a.force else existing_dates()

    rows_new: list[tuple[str, float, float, float]] = []
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
        vap = volume_at_price(trades)
        if len(vap) < 3:
            skipped.append((day, "too few price levels"))
            continue
        vpoc, va_lo, va_hi = value_area(vap, a.pct)
        rows_new.append((day, round(vpoc, 2), round(va_hi, 2), round(va_lo, 2)))
        print(f"{day}: VPOC {vpoc:.2f}  VA {va_lo:.2f}-{va_hi:.2f}  ({len(trades):,} trades, {path.name})")

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
        print("\nnothing new to backfill.")

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
