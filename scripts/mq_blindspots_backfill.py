"""MenthorQ Blind Spots (BL 1..10) backfill + daily capture  (S75V, 2026-07-20).

WHY THIS EXISTS
    The gateway route `blindspot-levels/{sym}` is TODAY-ONLY (no history, every date
    param ignored). But the qbot `/levels` endpoint accepts `level_types=blindspots`
    (no underscore) and serves ANY past session — validated to the penny against the
    old local QUIN `bl_levels.json` archive on 2026-07-02. Coverage starts ~2025-10-31.
    This is the clean, fresh-auth (Playwright token) replacement for the dead QUIN
    nonce scrape (menthorq_backfill.py).

    Blind Spots V2 (what the API returns as bl_1..bl_10) is a cross-asset OVERLAP model
    computed upstream from the per-strike option surface of a correlated proxy basket
    (odd 2-decimal values prove it is NOT a copy of the published round gamma levels).
    It is therefore NOT reconstructible from our gamma archive — capture is the only way
    to get history. See docs/living/handoff.md (S75V blind-spot reverse-engineering).

STORAGE  (one pair of files per ticker, '!' kept to match the gamma archive naming)
    data/menthorq/<SYM>_mq_blindspots_history.csv      # date, bl_1..bl_10  (tidy, sorted)
    data/menthorq/<SYM>_mq_blindspots_history_raw.jsonl # one raw row per session (audit)

MODES
    # daily (default): incremental — fetch from a few days before the last stored
    # session through today, dedup, append. Self-heals small gaps. Safe to re-run.
    .venv/Scripts/python.exe scripts/mq_blindspots_backfill.py
    .venv/Scripts/python.exe scripts/mq_blindspots_backfill.py --full          # from EARLIEST
    .venv/Scripts/python.exe scripts/mq_blindspots_backfill.py --from 2026-01-01
    .venv/Scripts/python.exe scripts/mq_blindspots_backfill.py --tickers ES1!,NQ1!,SPX

The daily MenthorQ chain (mq_mine.py) also calls update_history() so the tidy CSV
stays current without a separate scheduled task.
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq"
EARLIEST = dt.date(2025, 10, 1)          # empty before ~2025-10-31; a little slack
CHUNK = 5                                 # qbot 400s past ~5 dates/call (hard cap)
BL_COLS = [f"bl_{i}" for i in range(1, 11)]
# tickers that return BL (SI1! and a few illiquids come back empty — harmless, skipped)
DEFAULT_TICKERS = ["ES1!", "NQ1!", "RTY1!", "YM1!", "SPX", "NDX", "RUT",
                   "AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA",
                   "CL1!", "GC1!", "SPY", "QQQ", "IWM"]


def _csv_path(sym):
    return OUT / f"{sym}_mq_blindspots_history.csv"


def _jsonl_path(sym):
    return OUT / f"{sym}_mq_blindspots_history_raw.jsonl"


def _load_existing(sym):
    """Return {session_date: row_dict} already stored for sym."""
    p = _csv_path(sym)
    rows = {}
    if p.exists():
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows[r["date"]] = r
    return rows


def _write_csv(sym, rows_by_date):
    p = _csv_path(sym)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date"] + BL_COLS, extrasaction="ignore")
        w.writeheader()
        for d in sorted(rows_by_date):
            w.writerow(rows_by_date[d])


def _cal_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:               # Mon-Fri (the endpoint skips weekends anyway)
            yield d
        d += dt.timedelta(days=1)


def update_history(mq=None, tickers=None, start=None, verbose=True):
    """Fetch missing BL sessions for each ticker and persist. Returns per-ticker counts.

    Idempotent: only sessions not already in the CSV are added. `start` overrides the
    incremental lookback (defaults to a few days before the last stored session, or
    EARLIEST on first run).
    """
    tickers = tickers or DEFAULT_TICKERS
    mq = mq or MQ()
    today = dt.datetime.now(dt.timezone.utc).date()
    added = {}

    for sym in tickers:
        existing = _load_existing(sym)
        if start is not None:
            frm = start
        elif existing:
            last = max(dt.date.fromisoformat(d) for d in existing)
            frm = last - dt.timedelta(days=4)      # small overlap self-heals gaps
        else:
            frm = EARLIEST
        # request one calendar day AHEAD of today (date-shift: req D -> session D-1)
        want = [d.isoformat() for d in _cal_days(frm, today + dt.timedelta(days=1))]
        want = [d for d in want if d not in existing]   # cheap pre-skip (approx)
        new = 0
        for i in range(0, len(want), CHUNK):
            chunk = want[i:i + CHUNK]
            if not chunk:
                continue
            try:
                recs = mq.blindspots(sym, chunk)
            except Exception as e:
                if verbose:
                    print(f"  XX {sym:6} chunk {chunk[0]}..{chunk[-1]}: "
                          f"{type(e).__name__}: {str(e)[:60]}")
                continue
            for r in recs:
                d = r["date"]
                if d in existing:
                    continue
                existing[d] = {"date": d, **{c: r.get(c) for c in BL_COLS}}
                with open(_jsonl_path(sym), "a", encoding="utf-8") as f:
                    f.write(json.dumps(r) + "\n")
                new += 1
        if new:
            _write_csv(sym, existing)
        added[sym] = new
        if verbose:
            span = f"{min(existing)}..{max(existing)}" if existing else "—"
            print(f"  OK {sym:6} +{new:4} new  ({len(existing)} total, {span})")
    return added


def main():
    args = sys.argv[1:]
    tickers = DEFAULT_TICKERS
    if "--tickers" in args:
        tickers = args[args.index("--tickers") + 1].split(",")
    start = None
    if "--full" in args:
        start = EARLIEST
    if "--from" in args:
        start = dt.date.fromisoformat(args[args.index("--from") + 1])

    mode = "FULL" if "--full" in args else (f"from {start}" if start else "incremental")
    print(f"MQ Blind Spots backfill — {mode} — {len(tickers)} tickers")
    added = update_history(mq=MQ(), tickers=tickers, start=start)
    total = sum(added.values())
    print(f"\nDone. {total} new sessions across {len(tickers)} tickers -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
