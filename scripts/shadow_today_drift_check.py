"""Quantify today's IB-vs-TD shadow-book deltas and mark which rows are
late-start artifacts (2026-09-10: td_shadow_live started ~09:15 CT, so fills
for orders issued 08:30-08:33 were back-filled at start-time quotes; entries
get corrected by the 22:20 reprice, exits that happened before the start do
not). Prints per-trade: IB credit/exit vs TD credit/exit, delta, artifact flag.
"""
import json
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
day = dt.date.today().strftime("%Y-%m-%d")
book = json.loads((ROOT / f"data/options_sim/shadow_td/shadow_book_{day}.json")
                  .read_text(encoding="utf-8"))

rows = book.get("orders") or book.get("trades") or []
if isinstance(rows, dict):
    rows = list(rows.values())
print(f"{len(rows)} shadowed orders\n")
for r in rows:
    ex = r.get("exited") or {}
    ib_fill, td_open = r.get("ib_fill_at", "?"), r.get("td_open_at", "?")
    late = str(td_open)[:5] > str(ib_fill)[:5] if "?" not in (str(ib_fill), str(td_open)) else "?"
    d = round((r.get("ib_credit") or 0) - (r.get("td_credit") or 0), 2)
    print(f"{r.get('id'):24s} ib_fill {ib_fill}  td_open {td_open}  LATE={late}")
    print(f"   entry IB {r.get('ib_credit')} vs TD {r.get('td_credit')}  d={d}")
    if ex:
        print(f"   exit: {ex}")
print("\nexited-dict keys of first exited row:",
      next((list((r.get('exited') or {}).keys()) for r in rows if r.get('exited')), 'none'))
