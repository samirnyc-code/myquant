#!/usr/bin/env python
"""ingest_nt_ticks.py — extend data/ticks_continuous/ from NT8 RawTickExporter dumps (S90).

WHY
    The continuous DB (data/ticks_continuous/{date}.parquet -> research/scalp_swing/
    es_5m_rth.parquet) is normally fed by Massive/Databento flatfiles via massive.py.
    When those aren't available, this ingests NT8's own exported ticks instead, writing
    byte-compatible daily parquets so the downstream 5M build is unchanged.

WHAT IT GUARANTEES (the user's offset+contract ask)
    - CONTRACT: it maps the export's full contract name (e.g. "ES 09-26") to a ticker
      (ESU6) and, for EVERY date in the dump, asserts that ticker was the front-month
      contract per rolls.json (contracts.get_active_contract). If a roll happened inside
      the window, it ABORTS — a single-contract dump can't be spliced across a roll.
    - OFFSET: it applies exactly the Panama cum_offset contracts.py assigns that contract
      (0.0 for the current anchor ESU6), the same value massive.py bakes in. Never guessed.
    - It mirrors massive.build_continuous_ticks_for_date precisely: UTC-naive CT DateTime,
      RTH [08:30,15:15), schema DateTime(datetime64[ns]),Price(float64),Volume(int64).

USAGE
    python scripts/ingest_nt_ticks.py --glob "data/nt_ticks/ES_09-26_ticks_*.csv"
    # add --src-tz Europe/Berlin if NT is on PC-local time instead of exchange/Central
    # add --force to overwrite days that already have a parquet (default: skip them)
    # add --dry-run to validate + report without writing anything

After it writes, rebuild the 5M cache:
    python research/scalp_swing/build_5m.py
"""
from __future__ import annotations

import argparse
import glob as _glob
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from contracts import load_rolls, get_active_contract, _MONTH_TO_CODE  # noqa: E402

TICKS_DIR = ROOT / "data" / "ticks_continuous"
RTH_START, RTH_END = "08:30:00", "15:15:00"


def contract_to_ticker(full: str) -> str:
    """'ES 09-26' -> 'ESU6' (base + month code + last year digit)."""
    base, mmyy = full.strip().split(" ")
    mm, yy = mmyy.split("-")
    code = _MONTH_TO_CODE[int(mm)]
    return f"{base}{code}{yy[-1]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/nt_ticks/*_ticks_*.csv",
                    help="glob for RawTickExporter CSVs (relative to repo root)")
    ap.add_argument("--files", nargs="*", help="explicit file list (overrides --glob)")
    ap.add_argument("--src-tz", default="America/Chicago",
                    help="time zone the NT export timestamps are in "
                         "(default America/Chicago = NT set to exchange time)")
    ap.add_argument("--force", action="store_true", help="overwrite existing daily parquets")
    ap.add_argument("--dry-run", action="store_true", help="validate + report, write nothing")
    a = ap.parse_args()

    paths = a.files if a.files else sorted(_glob.glob(str(ROOT / a.glob)))
    if not paths:
        print(f"! no files matched ({a.files or a.glob})"); return 2

    print(f"reading {len(paths)} file(s):")
    frames = []
    contracts_seen: set[str] = set()
    for p in paths:
        fp = Path(p)
        # contract is the filename prefix before '_ticks_': ES_09-26_ticks_... -> "ES 09-26"
        stem = fp.name.split("_ticks_")[0].replace("_", " ")
        contracts_seen.add(stem)
        df = pd.read_csv(fp)
        print(f"  {fp.name}: {len(df):,} rows  contract='{stem}'")
        frames.append(df)

    if len(contracts_seen) != 1:
        print(f"! files span multiple contracts {contracts_seen} — ingest one contract at a time")
        return 2
    full_contract = contracts_seen.pop()
    ticker = contract_to_ticker(full_contract)
    print(f"\ncontract '{full_contract}' -> ticker {ticker}")

    raw = pd.concat(frames, ignore_index=True)
    raw = raw.drop_duplicates()  # re-loads / overlapping dumps
    _n0 = len(raw)
    raw = raw.dropna(subset=["Time", "Price", "Volume"])  # drop partial/truncated trailing rows
    if len(raw) != _n0:
        print(f"  dropped {_n0 - len(raw)} incomplete row(s)")
    # tz: localize the source zone, convert to Chicago, strip tz -> CT-naive (matches massive.py)
    ts = pd.to_datetime(raw["Time"])
    ts = (ts.dt.tz_localize(a.src_tz, ambiguous="infer", nonexistent="shift_forward")
            .dt.tz_convert("America/Chicago").dt.tz_localize(None))
    ticks = pd.DataFrame({
        "DateTime": ts,
        "Price": raw["Price"].astype(float).values,
        "Volume": raw["Volume"].astype(int).values,
    }).sort_values("DateTime").reset_index(drop=True)

    rolls = load_rolls()

    # per-date guard + offset, then RTH filter and write
    written, skipped, aborted = [], [], []
    for d, g in ticks.groupby(ticks["DateTime"].dt.date):
        active = get_active_contract(d, rolls)
        if active is None:
            print(f"! {d}: no active contract in catalog — SKIP"); aborted.append(d); continue
        if active["ticker"] != ticker:
            print(f"! {d}: front-month is {active['ticker']} but export is {ticker} "
                  f"(a roll crossed this window) — ABORT this day"); aborted.append(d); continue

        off = active["cum_offset"]
        day = g.copy()
        day["Price"] = day["Price"] + off  # Panama offset (0.0 for the anchor)

        t = day["DateTime"].dt.time
        rth = (t >= pd.Timestamp(RTH_START).time()) & (t < pd.Timestamp(RTH_END).time())
        day = day[rth].reset_index(drop=True)[["DateTime", "Price", "Volume"]]
        if day.empty:
            print(f"! {d}: no RTH ticks — SKIP"); skipped.append(d); continue

        out = TICKS_DIR / f"{d.isoformat()}.parquet"
        exists = out.exists()
        tag = "OVERWRITE" if (exists and a.force) else ("EXISTS-skip" if exists else "new")
        # seam continuity vs the immediately-preceding stored day
        seam = ""
        prev_days = sorted(p.stem for p in TICKS_DIR.glob("*.parquet") if p.stem < d.isoformat())
        if prev_days:
            pv = pd.read_parquet(TICKS_DIR / f"{prev_days[-1]}.parquet")
            gap = day["Price"].iloc[0] - pv["Price"].iloc[-1]
            seam = f" | seam vs {prev_days[-1]}: prevClose {pv['Price'].iloc[-1]:.2f} -> open {day['Price'].iloc[0]:.2f} (d={gap:+.2f})"

        print(f"  {d} [{tag}] off {off:+.2f}  {len(day):,} ticks  "
              f"{day['DateTime'].iloc[0].time()} to {day['DateTime'].iloc[-1].time()}  "
              f"px {day['Price'].min():.2f}..{day['Price'].max():.2f}{seam}")

        if exists and not a.force:
            skipped.append(d); continue
        if not a.dry_run:
            day["Volume"] = day["Volume"].astype("int64")
            day.to_parquet(out, index=False)
        written.append(d)

    print(f"\n{'DRY-RUN - nothing written' if a.dry_run else 'done'}: "
          f"{len(written)} written, {len(skipped)} skipped, {len(aborted)} aborted")
    if written and not a.dry_run:
        print("NEXT: python research/scalp_swing/build_5m.py  (rebuild es_5m_rth.parquet)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
