"""Backfill FULL MenthorQ gamma levels history from the qbot-service /levels endpoint.

DISCOVERED 2026-07-16 (S75): the /en/levels "Request Levels" page fires
  GET https://cf.menthorq.io/qbot-service/api/web/v1/levels
      ?tickers=SPX&level_types=gamma_levels&dates=YYYY-MM-DD
which returns the FULL labeled level set for ANY past session date — cr/ps/hvl,
0DTE (cr0/ps0/hvl0/gamma_wall), 1D min/max, GEX 1..10 — AND the signed GEX
magnitude at each level. History goes back to 2021-09-28 (empty before).

This replaces the dead QUIN scrape and gives ~5yr of fully-labeled levels for free
(no ORATS needed for the answer key). Auth reuses mq_api.MQ (Playwright token grab).

Row key = the SESSION date (what MQ plots for that day); the levels are computed
from the prior EOD (stored as eod_date). We keep a row only when the requested date
was itself a real trading session (price.eod.date == requested date).

Usage:
  .venv/Scripts/python.exe scripts/mq_levels_backfill.py [--ticker SPX] [--from 2021-09-28]
Writes data/menthorq/<tkr>_mq_levels_history.csv (+ _raw.jsonl for audit). Resumable.
"""
import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mq_api import MQ  # noqa

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "menthorq"
BASE = "https://cf.menthorq.io/qbot-service/api/web/v1/levels"
EARLIEST = "2021-09-28"

# level name -> column stem
STEM = {
    "Call Resistance": "cr", "Put Support": "ps", "HVL": "hvl",
    "1D Min": "d1_min", "1D Max": "d1_max",
    "Call Resistance 0DTE": "cr0", "Put Support 0DTE": "ps0",
    "HVL 0DTE": "hvl0", "Gamma Wall 0DTE": "gw0",
    **{f"GEX {i}": f"gex_{i}" for i in range(1, 11)},
}
COLS = ["session_date", "eod_date", "spot_eod", "spot_intraday"]
for stem in ["cr", "ps", "hvl", "d1_min", "d1_max", "cr0", "ps0", "hvl0", "gw0"] + \
        [f"gex_{i}" for i in range(1, 11)]:
    COLS += [stem, f"{stem}_gex"]


def parse(js, req_date):
    """Return a flat row dict, or None if req_date wasn't a real trading session."""
    data = js.get("data") or []
    if not data:
        return None
    d = data[0]
    price = d.get("price") or {}
    eod = price.get("eod") or {}
    # keep only if the requested date was itself a trading session
    if eod.get("date") != req_date:
        return None
    row = {c: "" for c in COLS}
    row["session_date"] = req_date
    row["eod_date"] = d.get("date")
    row["spot_eod"] = eod.get("value")
    row["spot_intraday"] = (price.get("intraday") or {}).get("value")
    # data[0].levels is a list of blocks; each block has level_values[]. Prefer eod.
    blocks = d.get("levels") or []
    block = next((b for b in blocks if b.get("kind") == "eod"), blocks[0] if blocks else None)
    if not block:
        return None
    for lv in block.get("level_values") or []:
        stem = STEM.get(lv.get("name"))
        if not stem:
            continue
        row[stem] = lv.get("value")
        row[f"{stem}_gex"] = lv.get("gex")
    return row


def main():
    tkr = sys.argv[sys.argv.index("--ticker") + 1] if "--ticker" in sys.argv else "SPX"
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else EARLIEST
    OUT.mkdir(parents=True, exist_ok=True)
    csv_f = OUT / f"{tkr}_mq_levels_history.csv"
    raw_f = OUT / f"{tkr}_mq_levels_history_raw.jsonl"

    have = set()
    if csv_f.exists():
        have = {r["session_date"] for r in csv.DictReader(open(csv_f))}
    print(f"{tkr}: {len(have)} sessions already on disk")

    mq = MQ()
    days = [d.date().isoformat()
            for d in __import__("pandas").bdate_range(start, dt.date.today())]
    todo = [d for d in days if d not in have]
    print(f"{tkr}: {len(todo)} business days to try ({days[0]}..{days[-1]})")

    rows, kept, req = [], 0, 0
    raw_out = open(raw_f, "a", encoding="utf-8")
    for i, d in enumerate(todo):
        for attempt in range(3):
            try:
                r = mq.s.get(BASE, headers={"accept": "application/json",
                                            "authorization": mq.token},
                             params={"tickers": tkr, "level_types": "gamma_levels",
                                     "dates": d}, timeout=30)
                req += 1
                if r.status_code in (401, 403):
                    mq._auth()
                    continue
                r.raise_for_status()
                js = r.json()
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  {d}: FAILED {str(e)[:60]}")
                    js = None
                time.sleep(2)
        if not js:
            continue
        row = parse(js, d)
        if row:
            rows.append(row)
            kept += 1
            raw_out.write(json.dumps({"req": d, "data": js.get("data")}) + "\n")
        if i % 100 == 99:
            print(f"  ...{i+1}/{len(todo)}  kept {kept} sessions  ({req} requests)", flush=True)
        time.sleep(0.15)
    raw_out.close()

    # merge + write CSV
    all_rows = []
    if csv_f.exists():
        all_rows = list(csv.DictReader(open(csv_f)))
    all_rows += [{c: ("" if row[c] is None else row[c]) for c in COLS} for row in rows]
    seen, dedup = set(), []
    for r in sorted(all_rows, key=lambda x: x["session_date"]):
        if r["session_date"] in seen:
            continue
        seen.add(r["session_date"])
        dedup.append(r)
    with open(csv_f, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(dedup)
    print(f"\nDONE — {kept} new sessions kept, {req} requests used.")
    print(f"CSV: {csv_f}  ({len(dedup)} total sessions"
          + (f", {dedup[0]['session_date']}..{dedup[-1]['session_date']})" if dedup else ")"))


if __name__ == "__main__":
    main()
