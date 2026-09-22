"""databento_0dte_cost_probe.py — READ-ONLY cost probe for the 0DTE SPXW pull.

Resolves the unknown $/GB rate for cbbo-1m (and trades, for comparison) by pricing
a KNOWN set of 0DTE SPXW instruments for ONE session via metadata endpoints only.
get_cost / get_billable_size are SPEND-FREE. No data is downloaded, nothing is bought.

Method: 6 real 0DTE strikes from the 2026-08-05 tape (both C and P, edge-ish strikes)
-> per-instrument-day bytes+cost -> scale to the full pull (~30 strikes/day x ~1,050
sessions). Prints both schemas so we can pick the cheaper one under the $125 budget.

Run: .venv/Scripts/python.exe scripts/databento_0dte_cost_probe.py
Out: console + data/databento/_cost_probe_<date>.json
"""
from __future__ import annotations
import json
from pathlib import Path
import datetime as dt

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")

DATASET = "OPRA.PILLAR"
PROBE_DATE = "2026-08-05"          # a session with SPXW 0DTE; from our own order tape
STYPE_IN = "raw_symbol"
SCHEMAS = ["cbbo-1m", "trades"]    # the candidate + the whole-range comparison

# 6 real 0DTE SPXW strikes traded 2026-08-05 (both sides). OSI raw_symbol = 2 spaces.
PROBE_SYMBOLS = [
    "SPXW  260805P07780000",
    "SPXW  260805P07755000",
    "SPXW  260805P07735000",
    "SPXW  260805P07710000",
    "SPXW  260805C07750000",
    "SPXW  260805C07775000",
]

# full-pull scaling assumptions (edit if the design changes)
STRIKES_PER_DAY = 30               # both C+P, +/-2 strikes at 4 band edges (close & open anchored)
SESSIONS = 1050                    # ~5/2022 -> 8/2026, weekday 0DTE


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)

    n_probe = len(PROBE_SYMBOLS)
    end = (dt.date.fromisoformat(PROBE_DATE) + dt.timedelta(days=1)).isoformat()

    out = {"dataset": DATASET, "probe_date": PROBE_DATE, "n_probe_symbols": n_probe,
           "strikes_per_day": STRIKES_PER_DAY, "sessions": SESSIONS,
           "quoted": dt.datetime.now().isoformat(timespec="seconds"), "schemas": {}}

    print(f"probe: {n_probe} symbols x 1 day ({PROBE_DATE}) on {DATASET}\n")
    scale = (STRIKES_PER_DAY / n_probe) * SESSIONS

    for schema in SCHEMAS:
        try:
            size = client.metadata.get_billable_size(
                dataset=DATASET, symbols=PROBE_SYMBOLS, stype_in=STYPE_IN,
                schema=schema, start=PROBE_DATE, end=end)
            cost = client.metadata.get_cost(
                dataset=DATASET, symbols=PROBE_SYMBOLS, stype_in=STYPE_IN,
                schema=schema, start=PROBE_DATE, end=end, mode="historical")
        except Exception as e:
            print(f"{schema:10}  ERROR: {str(e)[:120]}")
            out["schemas"][schema] = {"error": str(e)[:200]}
            continue

        gb = size / 1e9
        rate = cost / gb if gb else float("nan")
        per_inst_day = cost / n_probe
        full = per_inst_day * STRIKES_PER_DAY * SESSIONS
        out["schemas"][schema] = {
            "probe_bytes": size, "probe_cost_usd": cost, "rate_usd_per_gb": rate,
            "per_instrument_day_usd": per_inst_day, "full_pull_usd": full}
        print(f"{schema:10}  probe {size/1e6:7.2f} MB  ${cost:7.4f}   "
              f"rate ~${rate:6.1f}/GB   per-inst-day ${per_inst_day:.4f}")
        print(f"{'':10}  -> FULL PULL est ({STRIKES_PER_DAY}/day x {SESSIONS}d): "
              f"${full:,.0f}\n")

    outfile = ROOT / "data" / "databento" / f"_cost_probe_{PROBE_DATE}.json"
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(out, indent=2))
    print(f"saved -> {outfile}")


if __name__ == "__main__":
    main()
