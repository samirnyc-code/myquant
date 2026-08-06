"""databento_def_cost.py — READ-ONLY cost of the SPXW definitions pull.

Prices the `definition` schema for SPXW.OPT (parent) over the cbbo-1m-priceable
window (2023-03-28 -> today) BEFORE any download. Also prices SPX.OPT (AM monthlies)
separately in case both roots are wanted. get_cost/get_billable_size are spend-free.

Run: .venv/Scripts/python.exe scripts/databento_def_cost.py
Out: console + data/databento/_def_cost.json
"""
from __future__ import annotations
import json
from pathlib import Path
import datetime as dt

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")

DATASET = "OPRA.PILLAR"
START = "2023-03-28"                # cbbo-1m availability start
END = dt.date.today().isoformat()
PARENTS = ["SPXW.OPT", "SPX.OPT"]   # weeklies/dailies (0DTE) ; monthlies


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    out = {"dataset": DATASET, "schema": "definition", "start": START, "end": END,
           "quoted": dt.datetime.now().isoformat(timespec="seconds"), "parents": {}}
    print(f"definition cost  {DATASET}  {START} -> {END}\n")
    for parent in PARENTS:
        try:
            size = client.metadata.get_billable_size(
                dataset=DATASET, symbols=parent, stype_in="parent",
                schema="definition", start=START, end=END)
            cost = client.metadata.get_cost(
                dataset=DATASET, symbols=parent, stype_in="parent",
                schema="definition", start=START, end=END)
        except Exception as e:
            print(f"{parent:10}  ERROR: {str(e)[:120]}")
            out["parents"][parent] = {"error": str(e)[:200]}
            continue
        out["parents"][parent] = {"bytes": size, "cost_usd": cost}
        print(f"{parent:10}  {size/1e6:8.1f} MB   ${cost:7.2f}")
    outfile = ROOT / "data" / "databento" / "_def_cost.json"
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(out, indent=2))
    print(f"\nsaved -> {outfile}")


if __name__ == "__main__":
    main()
