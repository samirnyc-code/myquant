"""QUIN backfill #3 (S73): extended daily levels — 0DTE set + 1D Min/Max.
Monthly tables per symbol -> data/menthorq/levels0_history.csv
(date, symbol, cr0, ps0, hvl0, gw0, d1_min, d1_max), deduped/idempotent.
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
OUT = ROOT / "data" / "menthorq" / "levels0_history.csv"
RAW = ROOT / "data" / "menthorq" / "harvest" / "backfill_0dte_raw"

START = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2025-07"
SYMBOLS = sys.argv[sys.argv.index("--symbols") + 1].split(",") if "--symbols" in sys.argv else ["ES", "SPX"]

NUM = r"(\$?[\d,]+\.?\d*|—|-|N/A|null)"   # value or missing marker
ROW = re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})\t{NUM}\t{NUM}\t{NUM}\t{NUM}\t{NUM}\t{NUM}$")


def _num(s):
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None   # "—" / "N/A" -> null


def parse(txt):
    rows = []
    for ln in txt.splitlines():
        m = ROW.match(ln.strip())
        if m:
            rows.append((m.group(1), *[_num(m.group(i)) for i in range(2, 8)]))
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
            w.writerow(["date", "symbol", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max"])
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        for sym in SYMBOLS:
            empty = 0
            for a, b in months(START):
                q = (f"Give me a table of the {sym} gamma levels for each trading day from {a} "
                     f"through {b}, one row per day, EXACTLY these columns in this order: "
                     f"Date, Call Resistance 0DTE, Put Support 0DTE, HVL 0DTE, Gamma Wall 0DTE, "
                     f"1D Min, 1D Max. ISO dates, numbers only.")
                try:
                    txt = ask(page, q)
                except Exception as e:
                    print(f"  {sym} {a[:7]}: ask failed {e}")
                    continue
                (RAW / f"{sym}_{a[:7]}.txt").write_text(txt, encoding="utf-8")
                rows = parse(txt)
                fresh = [r for r in rows if (r[0], sym) not in existing]
                for r in fresh:
                    w.writerow([r[0], sym, *r[1:]])
                    existing.add((r[0], sym))
                fh.flush()
                added += len(fresh)
                print(f"  {sym} {a[:7]}: {len(rows)} parsed, {len(fresh)} new", flush=True)
                empty = empty + 1 if not rows else 0
                if empty >= 3:
                    print(f"  {sym}: 3 empty months — stopping")
                    break
                page.wait_for_timeout(4000)
        ctx.storage_state(path=str(AUTH))
        br.close()
    print(f"\n0DTE backfill added {added} rows -> {OUT}")


if __name__ == "__main__":
    main()
