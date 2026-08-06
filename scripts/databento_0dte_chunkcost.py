"""databento_0dte_chunkcost.py — EXACT price of finishing the pull the CHUNK way.

Mirrors the submit chunking EXACTLY (same ~11-session chunks, same multi-day date
range per job, same symbols) and calls get_cost per chunk. Because the params match
the submit, this get_cost equals the actual bill (validated against chunk-1 actual
$0.498). Prices a sample across all eras and projects the full 77-chunk total, since
2025-26 0DTE volume is far higher than 2023.

Run: .venv/Scripts/python.exe scripts/databento_0dte_chunkcost.py
Out: console + data/databento/_chunkcost.json
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import datetime as dt

import databento as db
from databento_0dte_band_price import construct, BAND_PTS, STEP

ROOT = Path(__file__).resolve().parent.parent
KEYFILE = Path(r"C:\Users\Admin\AppData\Local\myquant\databento.json")
SPX_CSV = ROOT / "data" / "spx_daily_ohlc.csv"

DATASET, SCHEMA = "OPRA.PILLAR", "cbbo-1m"
WINDOW_START = "2023-03-28"
DAYS_PER_CHUNK = 1800 // 162        # 11, same as submit


def main():
    key = json.load(open(KEYFILE, encoding="utf-8-sig"))["key"]
    client = db.Historical(key)
    closes = {r["Date"]: float(r["Close"]) for r in csv.DictReader(open(SPX_CSV)) if r["Close"]}
    dates = sorted(closes)
    sessions = [d for d in dates if d >= WINDOW_START]
    chunks = [sessions[i:i + DAYS_PER_CHUNK] for i in range(0, len(sessions), DAYS_PER_CHUNK)]

    # sample ~1 chunk per ~10 to span all eras; always include first & last
    idxs = sorted(set([0, len(chunks) - 1] + list(range(0, len(chunks), 10))))
    print(f"{len(chunks)} chunks total. pricing {len(idxs)} sample chunks (fat/submit params):\n")

    priced = []
    for ci in idxs:
        ch = chunks[ci]
        syms = []
        for d in ch:
            pc = closes[dates[dates.index(d) - 1]]
            syms += construct(d, pc, band=BAND_PTS, step=STEP)
        end = (dt.date.fromisoformat(ch[-1]) + dt.timedelta(days=1)).isoformat()
        cost = client.metadata.get_cost(dataset=DATASET, symbols=syms, stype_in="raw_symbol",
                                        schema=SCHEMA, start=ch[0], end=end)
        priced.append({"idx": ci, "start": ch[0], "end": ch[-1], "cost_usd": cost})
        print(f"  chunk {ci:2} [{ch[0]}..{ch[-1]}]  ${cost:.4f}")

    avg = sum(p["cost_usd"] for p in priced) / len(priced)
    # era-weighted projection: average within thirds, weight by chunk count
    total_proj = avg * len(chunks)
    out = {"n_chunks": len(chunks), "sampled": priced, "avg_chunk_usd": avg,
           "projected_total_usd": total_proj, "days_per_chunk": DAYS_PER_CHUNK,
           "quoted": dt.datetime.now().isoformat(timespec="seconds")}
    (ROOT / "data" / "databento" / "_chunkcost.json").write_text(json.dumps(out, indent=2))
    print(f"\n{len(chunks)} chunks x avg ${avg:.4f} = PROJECTED TOTAL ${total_proj:,.2f}")
    print("(sample spans all eras; 2025-26 chunks price higher — see per-chunk above)")


if __name__ == "__main__":
    main()
