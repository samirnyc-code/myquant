"""QUIN backfill #2 (S73): historical daily Total NetGEX / NetDEX / 0DTE skew.

Confirmed 2026-07-15: QUIN's Data Expert serves these as monthly tables.
Accrues data/menthorq/gex_history.csv (date, symbol, net_gex, net_dex, skew_0dte)
— the gamma-REGIME time series for conditioning backtests. Values arrive like
"$1.20B" / "-$560.21M" / "45.2%"; parsed to floats ($ in raw units, skew in %).

Run: .venv/Scripts/python.exe scripts/mq_quin_backfill_gex.py [--from 2025-07]
"""
import csv
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_quin_backfill import months
from mq_quin_harvest import ask

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "data" / "menthorq" / "gex_history.csv"
RAW = ROOT / "data" / "menthorq" / "harvest" / "backfill_gex_raw"

START = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2025-07"
SYMBOLS = ["SPX", "ES"]

MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
ROW = re.compile(r"^([A-Z][a-z]{2} \d{1,2}|\d{4}-\d{2}-\d{2})\t(-?\$[\d.]+[KMBT]?)\t(-?\$[\d.]+[KMBT]?)\t(-?[\d.]+)%$")


def money(s):
    s = s.replace("$", "")
    m = MULT.get(s[-1], 1)
    return float(s[:-1] if s[-1] in MULT else s) * m


def parse(txt, year_month):
    rows = []
    for ln in txt.splitlines():
        m = ROW.match(ln.strip())
        if not m:
            continue
        d, gex, dex, skew = m.groups()
        if not d[0].isdigit():  # "Jun 5" -> ISO
            import datetime as dt
            mon, day = d.split()
            d = dt.datetime.strptime(f"{year_month[:4]} {mon} {day}", "%Y %b %d").date().isoformat()
        rows.append((d, money(gex), money(dex), float(skew)))
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
            w.writerow(["date", "symbol", "net_gex", "net_dex", "skew_0dte"])
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        for sym in SYMBOLS:
            empty = 0
            for a, b in months(START):
                q = (f"For {sym}, give me a table with one row per trading day from {a} "
                     f"through {b}: columns Date, Total Net GEX, Net DEX, 0DTE Skew.")
                try:
                    txt = ask(page, q)
                except Exception as e:
                    print(f"  {sym} {a[:7]}: ask failed {e}")
                    continue
                (RAW / f"{sym}_{a[:7]}.txt").write_text(txt, encoding="utf-8")
                rows = parse(txt, a[:7])
                fresh = [r for r in rows if (r[0], sym) not in existing]
                for d, g, x, sk in fresh:
                    w.writerow([d, sym, g, x, sk])
                    existing.add((d, sym))
                fh.flush()
                added += len(fresh)
                print(f"  {sym} {a[:7]}: {len(rows)} parsed, {len(fresh)} new")
                empty = empty + 1 if not rows else 0
                if empty >= 3:
                    print(f"  {sym}: 3 empty months — stopping")
                    break
                page.wait_for_timeout(4000)
        ctx.storage_state(path=str(AUTH))
        br.close()
    print(f"\ngex backfill added {added} rows -> {OUT}")


if __name__ == "__main__":
    main()
