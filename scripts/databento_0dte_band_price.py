"""databento_0dte_band_price.py — READ-ONLY exact price of the one-shot 0DTE grid.

Constructs the deterministic OSI raw_symbols for a WIDE contiguous 5-pt strike grid
(calls+puts) centered on the prior cash close, expiring same-day (0DTE), then prices
cbbo-1m via get_cost on several representative sessions and scales to the full window.
No download, no purchase — get_cost/get_billable_size are spend-free.

The download is structure-agnostic: it grabs every strike in the band so the backtest
can assemble ANY spread (any short placement, any wing width) and any intraday exit.

Run: .venv/Scripts/python.exe scripts/databento_0dte_band_price.py
Out: console + data/databento/_band_price.json
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import datetime as dt

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
SPX_CSV = ROOT / "data" / "spx_daily_full.csv"      # Date,High,Low,Close (has Close hist)

DATASET = "OPRA.PILLAR"
WINDOW_START = "2023-03-28"                          # cbbo-1m availability
BAND_PTS = 200                                       # +/- around prior close (wide = one-shot safe)
STEP = 5                                             # SPXW near-money strike spacing
SCHEMA = "cbbo-1m"

# representative sessions to price (spread across the window). center = PRIOR close.
SAMPLE_DATES = ["2023-06-15", "2024-01-17", "2024-09-18",
                "2025-03-19", "2025-11-19", "2026-07-16"]


def load_closes():
    closes = {}
    with open(SPX_CSV) as f:
        for r in csv.DictReader(f):
            closes[r["Date"]] = float(r["Close"])
    return closes


def construct(date_iso: str, center: float, band=BAND_PTS, step=STEP):
    """Deterministic OSI raw_symbols, 0DTE (expiry == date), C+P, 5-pt grid."""
    d = dt.date.fromisoformat(date_iso)
    yymmdd = d.strftime("%y%m%d")
    lo = int((center - band) // step * step)
    hi = int((center + band) // step * step)
    syms = []
    for k in range(lo, hi + step, step):
        kk = f"{int(k * 1000):08d}"          # strike * 1000, 8 digits
        syms.append(f"SPXW  {yymmdd}C{kk}")
        syms.append(f"SPXW  {yymmdd}P{kk}")
    return syms


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    closes = load_closes()
    dates = sorted(closes)

    def prior_close(date_iso):
        i = dates.index(date_iso) if date_iso in dates else None
        if i is None:
            # nearest prior available
            prev = [x for x in dates if x < date_iso]
            return closes[prev[-1]] if prev else None
        return closes[dates[i - 1]]

    out = {"dataset": DATASET, "schema": SCHEMA, "band_pts": BAND_PTS, "step": STEP,
           "window_start": WINDOW_START, "quoted": dt.datetime.now().isoformat(timespec="seconds"),
           "samples": []}
    per_day_costs = []
    print(f"{SCHEMA}  grid = prior_close +/- {BAND_PTS}pt, {STEP}pt step, C+P\n")
    for date_iso in SAMPLE_DATES:
        pc = prior_close(date_iso)
        if pc is None:
            print(f"{date_iso}  no prior close"); continue
        syms = construct(date_iso, pc)
        end = (dt.date.fromisoformat(date_iso) + dt.timedelta(days=1)).isoformat()
        try:
            size = client.metadata.get_billable_size(
                dataset=DATASET, symbols=syms, stype_in="raw_symbol",
                schema=SCHEMA, start=date_iso, end=end)
            cost = client.metadata.get_cost(
                dataset=DATASET, symbols=syms, stype_in="raw_symbol",
                schema=SCHEMA, start=date_iso, end=end)
        except Exception as e:
            print(f"{date_iso}  ERROR: {str(e)[:110]}"); continue
        per_day_costs.append(cost)
        out["samples"].append({"date": date_iso, "prior_close": pc, "n_symbols": len(syms),
                               "bytes": size, "cost_usd": cost})
        print(f"{date_iso}  center {pc:7.1f}  {len(syms):3} syms  {size/1e6:6.2f} MB  ${cost:.4f}")

    # scale: count priceable sessions in window
    sessions = [d for d in dates if d >= WINDOW_START]
    n_sessions = len(sessions)
    avg = sum(per_day_costs) / len(per_day_costs) if per_day_costs else float("nan")
    full = avg * n_sessions
    out["avg_per_day_usd"] = avg
    out["n_sessions_in_window"] = n_sessions
    out["full_pull_est_usd"] = full
    print(f"\navg/day ${avg:.4f}  x  {n_sessions} sessions (>= {WINDOW_START}, to 7/17)")
    print(f"FULL ONE-SHOT PULL est: ${full:,.2f}")

    outfile = ROOT / "data" / "databento" / "_band_price.json"
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(out, indent=2))
    print(f"saved -> {outfile}")


if __name__ == "__main__":
    main()
