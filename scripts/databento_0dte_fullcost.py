"""databento_0dte_fullcost.py — EXACT full-window cost of the one-shot 0DTE grid.

No sampling: constructs each session's real 0DTE grid (prior_close +/- BAND, 5-pt, C+P)
and calls get_cost per day, summing to the precise total that the batch submit will bill.
get_cost is spend-free. Checkpoints so it can resume. Prints the running total.

Range: 2023-03-28 -> last close on disk (extend once Yahoo close series is refreshed).

Run: .venv/Scripts/python.exe scripts/databento_0dte_fullcost.py
Out: console + data/databento/_fullcost.json (checkpointed)
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import datetime as dt

import databento as db
from databento_0dte_band_price import construct, BAND_PTS, STEP  # reuse the constructor

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
SPX_CSV = ROOT / "data" / "spx_daily_full.csv"
OUT = ROOT / "data" / "databento" / "_fullcost.json"

DATASET = "OPRA.PILLAR"
SCHEMA = "cbbo-1m"
WINDOW_START = "2023-03-28"


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)

    closes = {}
    with open(SPX_CSV) as f:
        for r in csv.DictReader(f):
            closes[r["Date"]] = float(r["Close"])
    dates = sorted(closes)
    sessions = [d for d in dates if d >= WINDOW_START]

    done = {}
    if OUT.exists():
        done = {s["date"]: s for s in json.loads(OUT.read_text()).get("days", [])}

    days = list(done.values())
    total = sum(d["cost_usd"] for d in days)
    print(f"{SCHEMA} EXACT cost, {len(sessions)} sessions {WINDOW_START}..{dates[-1]}")
    print(f"(resuming: {len(done)} already priced, ${total:.4f})\n")

    for i, date_iso in enumerate(sessions, 1):
        if date_iso in done:
            continue
        pc = closes[dates[dates.index(date_iso) - 1]]         # prior close
        syms = construct(date_iso, pc, band=BAND_PTS, step=STEP)
        end = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
        try:
            cost = client.metadata.get_cost(
                dataset=DATASET, symbols=syms, stype_in="raw_symbol",
                schema=SCHEMA, start=date_iso, end=end)
        except Exception as e:
            print(f"[{i}/{len(sessions)}] {date_iso} ERROR {str(e)[:70]}")
            continue
        total += cost
        days.append({"date": date_iso, "prior_close": pc, "n_symbols": len(syms), "cost_usd": cost})
        if i % 50 == 0 or i == len(sessions):
            OUT.write_text(json.dumps(
                {"dataset": DATASET, "schema": SCHEMA, "band_pts": BAND_PTS,
                 "window_start": WINDOW_START, "window_end": dates[-1],
                 "n_sessions": len(sessions), "priced": len(days),
                 "total_usd": total, "days": sorted(days, key=lambda x: x["date"])}, indent=2))
            print(f"[{i}/{len(sessions)}] {date_iso}  running total ${total:.4f}")

    print(f"\nEXACT TOTAL ({len(days)} sessions): ${total:.2f}")
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
