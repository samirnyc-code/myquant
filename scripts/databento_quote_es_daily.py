"""databento_quote_es_daily.py — cost QUOTE (no purchase) for the ES history extension pull.

THE PROPOSED PULL (what this script prices, exactly):
  dataset:   GLBX.MDP3
  symbols:   ES.v.0            (continuous front month, volume-based roll)
  stype_in:  continuous
  schemas:   ohlcv-1d  AND  ohlcv-1h
  range:     2010-06-06 (GLBX.MDP3 start) -> 2021-06-17 (day before our own bars begin)
  purpose:   extend the regime event studies from 1,300 to ~4,000 daily bars
             (2011 crash, 2015-08, 2018 Q4, 2020 COVID, 2022 bear all enter the sample).
  We stitch panama-style onto data/bars/_continuous_1m_24h-derived dailies (same method
  as the existing pipeline); overlap 2021-06 -> today comes from data we already own.

This script only calls metadata endpoints (get_dataset_range, get_cost) — READ-ONLY,
zero spend. The actual pull happens in a separate script only after user approval.

Run: .venv/Scripts/python.exe scripts/databento_quote_es_daily.py
Out: console + data/regime/databento_quote_<tag>.json
"""
from __future__ import annotations
import json
from pathlib import Path
import datetime as dt

import databento as db

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")

DATASET = "GLBX.MDP3"
SYMBOLS = ["ES.v.0"]
STYPE_IN = "continuous"
START = "2010-06-06"
END = "2021-06-17"
SCHEMAS = ["ohlcv-1d", "ohlcv-1h"]


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)

    rng = client.metadata.get_dataset_range(dataset=DATASET)
    print(f"dataset range: {rng}")

    out = {"dataset": DATASET, "symbols": SYMBOLS, "stype_in": STYPE_IN,
           "start": START, "end": END, "quoted": str(dt.datetime.now()), "quotes": {}}
    total = 0.0
    for schema in SCHEMAS:
        cost = client.metadata.get_cost(
            dataset=DATASET, symbols=SYMBOLS, stype_in=STYPE_IN,
            schema=schema, start=START, end=END)
        size = client.metadata.get_billable_size(
            dataset=DATASET, symbols=SYMBOLS, stype_in=STYPE_IN,
            schema=schema, start=START, end=END)
        out["quotes"][schema] = {"usd": cost, "billable_bytes": size}
        total += cost
        print(f"{schema:9s}  ${cost:.4f}   ({size:,} billable bytes)")
    out["total_usd"] = round(total, 4)
    print(f"TOTAL: ${total:.4f}")

    # cross-check: published unit price ($/GB) x billable bytes must reproduce get_cost
    prices = client.metadata.list_unit_prices(dataset=DATASET)
    for mode_entry in prices:
        mode = getattr(mode_entry, "mode", None) or mode_entry.get("mode")
        um = getattr(mode_entry, "unit_prices", None) or mode_entry.get("unit_prices")
        rel = {s: um.get(s) for s in SCHEMAS if s in um}
        if rel:
            print(f"unit prices [{mode}]: " + ", ".join(f"{s} ${p}/GB" for s, p in rel.items()))
            for s, p in rel.items():
                gb = out["quotes"][s]["billable_bytes"] / 1e9
                print(f"   check {s}: {gb:.6f} GB x ${p}/GB = ${gb * p:.4f} "
                      f"(get_cost said ${out['quotes'][s]['usd']:.4f})")
    out["unit_prices"] = [dict(m) if not hasattr(m, "mode") else
                          {"mode": m.mode, "unit_prices": m.unit_prices} for m in prices]

    tag = dt.datetime.now().strftime("%Y%m%d")
    outp = ROOT / "data" / "regime" / f"databento_quote_{tag}.json"
    json.dump(out, open(outp, "w"), indent=1)
    print(f"quote -> {outp}")


if __name__ == "__main__":
    main()
