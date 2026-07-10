#!/usr/bin/env python3
"""
daily_data_update.py — Download yesterday's (and any other missing) Massive flat files,
build the per-day continuous tick parquets, and rebuild the continuous bar series.

Designed to run unattended (cron / launchd). Logs to stdout; redirect to a file in crontab:
    0 7 * * 1-5  /path/to/.venv/bin/python /path/to/scripts/daily_data_update.py >> /tmp/myquant_daily.log 2>&1
"""

import sys
import logging
from datetime import date, timedelta
from pathlib import Path

# ── Resolve project root (this script lives in <root>/scripts/) ───────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import boto3
from botocore.config import Config

from contracts import CATALOG, load_rolls, apply_back_adjustment
from data_loader import filter_excluded_dates
from massive import (
    _make_s3, _download_day, build_continuous_ticks_for_date,
    load_bars, _bars_path, _GZ_CACHE_DIR, _BARS_DIR, _TICKS_CONT_DIR,
    _ticks_to_5m_bars, _load_gz, _resample_5m_to_15m, _ensure_dirs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def _get_front_month_ticker(d: date, rolls: dict) -> str | None:
    """Return the front-month ES ticker for a given date, or None if outside catalog."""
    from contracts import get_active_contract
    a = get_active_contract(d, rolls)
    return a["ticker"] if a else None


def _rebuild_contract_parquet(ticker: str, rolls: dict) -> int:
    """Rebuild {ticker}.parquet from all gz files in the catalog window. Returns bar count."""
    from contracts import get_contract_windows
    windows = get_contract_windows([ticker], rolls)
    if not windows:
        return 0
    w = windows[0]
    start = w["start"]
    end   = date.today()

    frames = []
    d = start
    import pandas as pd
    while d <= end:
        gz = _GZ_CACHE_DIR / f"{d.isoformat()}.csv.gz"
        if gz.exists():
            day_df = _load_gz(gz, ticker)
            if not day_df.empty:
                bars = _ticks_to_5m_bars(day_df)
                if not bars.empty:
                    frames.append(bars)
        d += timedelta(days=1)

    if not frames:
        return 0

    import pandas as pd
    out = pd.concat(frames, ignore_index=True)
    out.sort_values("DateTime", inplace=True, ignore_index=True)
    out.to_parquet(_bars_path(ticker), index=False)
    return len(out)


def main() -> None:
    _ensure_dirs()
    rolls = load_rolls()
    today = date.today()

    # ── 1. Download any missing gz files (from last cached date to yesterday) ──
    existing = sorted(f.name.split(".")[0] for f in _GZ_CACHE_DIR.glob("*.csv.gz"))
    last_cached = date.fromisoformat(existing[-1]) if existing else date(2021, 6, 1)
    start_dl = last_cached + timedelta(days=1)
    end_dl   = today - timedelta(days=1)  # yesterday (today not yet on server)

    if start_dl > end_dl:
        log.info("Flat files already current through %s — nothing to download.", last_cached)
    else:
        log.info("Downloading flat files %s → %s …", start_dl, end_dl)
        s3 = _make_s3()
        downloaded = []
        d = start_dl
        while d <= end_dl:
            local = _download_day(s3, d)
            if local:
                downloaded.append(d)
                log.info("  OK  %s", d)
            else:
                log.info("  --  %s (weekend / holiday / not on server)", d)
            d += timedelta(days=1)
        log.info("Downloaded %d new file(s).", len(downloaded))

    # ── 2. Build missing continuous tick parquets ──────────────────────────────
    all_gz = sorted(f.name.split(".")[0] for f in _GZ_CACHE_DIR.glob("*.csv.gz"))
    built = 0
    for day_str in all_gz:
        d = date.fromisoformat(day_str)
        if not (_TICKS_CONT_DIR / f"{day_str}.parquet").exists():
            result = build_continuous_ticks_for_date(d, rolls)
            if result is not None:
                log.info("  Ticks built: %s (%d ticks)", d, len(result))
                built += 1
    log.info("Built %d new tick parquet(s).", built)

    # ── 3. Rebuild per-contract bar parquets for any contract with new days ───
    # Only update contracts that are in the "recent" window (last 2 quarters)
    recent_tickers = [c.ticker for c in CATALOG[-2:]]
    for ticker in recent_tickers:
        n = _rebuild_contract_parquet(ticker, rolls)
        if n:
            log.info("  %s.parquet: %d bars", ticker, n)

    # ── 4. Rebuild continuous series ───────────────────────────────────────────
    import pandas as pd
    bars_by_ticker = {}
    for c in CATALOG:
        p = _bars_path(c.ticker)
        if p.exists():
            bars_by_ticker[c.ticker] = load_bars(c.ticker)

    if bars_by_ticker:
        continuous = apply_back_adjustment(bars_by_ticker, rolls)
        continuous = filter_excluded_dates(continuous)
        continuous.to_parquet(_BARS_DIR / "_continuous.parquet", index=False)
        cont_15m = _resample_5m_to_15m(continuous)
        cont_15m.to_parquet(_BARS_DIR / "_continuous_15m.parquet", index=False)
        log.info(
            "Continuous rebuilt: %d bars, %s → %s",
            len(continuous),
            continuous["DateTime"].min().date(),
            continuous["DateTime"].max().date(),
        )
    else:
        log.warning("No contract parquets found — continuous not rebuilt.")

    log.info("Daily update complete.")


if __name__ == "__main__":
    main()
