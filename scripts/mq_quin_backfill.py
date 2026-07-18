"""QUIN historical-levels backfill (S73) — month-by-month CR/PS/HVL time series.

QUIN's "Data Expert" answers historical range queries with one-row-per-day
tables (verified 2026-07-15). This loops months per symbol and accrues
data/menthorq/levels_history.csv (date, symbol, cr, ps, hvl), deduped.
Chunked + spaced to be polite; stops early if answers come back empty
(either the DB's history floor or a usage cap — both visible in the raw dumps).

Run: .venv/Scripts/python.exe scripts/mq_quin_backfill.py [--from 2025-07] [--symbols SPX,ES1!]
"""
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_quin_harvest import ask

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "data" / "menthorq" / "levels_history.csv"
RAW = ROOT / "data" / "menthorq" / "harvest" / "backfill_raw"

START = "2025-07"
SYMBOLS = ["SPX", "ES"]
if "--from" in sys.argv:
    START = sys.argv[sys.argv.index("--from") + 1]
if "--symbols" in sys.argv:
    SYMBOLS = sys.argv[sys.argv.index("--symbols") + 1].split(",")

ROW_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\t\$?([\d,]+\.?\d*)\t\$?([\d,]+\.?\d*)\t\$?([\d,]+\.?\d*)$")


def months(start):
    y, m = map(int, start.split("-"))
    today = dt.date.today()
    while (y, m) <= (today.year, today.month):
        first = dt.date(y, m, 1)
        last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
        yield first.isoformat(), min(last, today).isoformat()
        y, m = (y + (m == 12), m % 12 + 1)


def parse_rows(txt):
    rows = []
    for ln in txt.splitlines():
        m = ROW_RE.match(ln.strip())
        if m:
            d, cr, ps, hvl = m.groups()
            rows.append((d, float(cr.replace(",", "")), float(ps.replace(",", "")),
                         float(hvl.replace(",", ""))))
    return rows


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    existing = set()
    if OUT.exists():
        with open(OUT) as fh:
            existing = {(r["date"], r["symbol"]) for r in csv.DictReader(fh)}
    new_file = not OUT.exists()
    added = 0
    with sync_playwright() as pw, open(OUT, "a", newline="") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["date", "symbol", "cr", "ps", "hvl"])
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        for sym in SYMBOLS:
            empty_streak = 0
            for a, b in months(START):
                q = (f"Give me a table of the {sym} Call Resistance, Put Support, and HVL "
                     f"levels for each trading day from {a} through {b}, one row per day, "
                     f"columns: Date, Call Resistance, Put Support, HVL.")
                try:
                    txt = ask(page, q)
                except Exception as e:
                    print(f"  {sym} {a[:7]}: ask failed {e}")
                    continue
                (RAW / f"{sym.replace('!', '')}_{a[:7]}.txt").write_text(txt, encoding="utf-8")
                rows = parse_rows(txt)
                fresh = [(d, v1, v2, v3) for d, v1, v2, v3 in rows if (d, sym) not in existing]
                for d, v1, v2, v3 in fresh:
                    w.writerow([d, sym, v1, v2, v3])
                    existing.add((d, sym))
                fh.flush()
                added += len(fresh)
                print(f"  {sym} {a[:7]}: {len(rows)} rows parsed, {len(fresh)} new")
                empty_streak = empty_streak + 1 if not rows else 0
                if empty_streak >= 3:
                    print(f"  {sym}: 3 empty months in a row — stopping (history floor or cap)")
                    break
                page.wait_for_timeout(4000)  # spacing between queries
        ctx.storage_state(path=str(AUTH))
        br.close()
    print(f"\nbackfill added {added} rows -> {OUT}")


if __name__ == "__main__":
    main()
