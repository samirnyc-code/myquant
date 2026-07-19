"""Find the depth of gamma-levels/{sym}/eod/history and its param surface."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mq_api import MQ  # noqa

mq = MQ()

def span(js):
    if not isinstance(js, list) or not js:
        return f"(not list / empty: {type(js)})"
    ts = sorted(x.get("timestamp") or x.get("report_date") or "" for x in js)
    return f"n={len(js)}  {ts[0]} .. {ts[-1]}"

print("=== default ===")
print(" ", span(mq.get("gamma-levels/SPX/eod/history")))

print("\n=== limit param sweep ===")
for lim in [30, 90, 365, 1000, 5000]:
    for pn in ["limit", "count", "days", "n"]:
        try:
            js = mq.get("gamma-levels/SPX/eod/history", **{pn: lim})
            if isinstance(js, list):
                print(f"  ?{pn}={lim:<5} -> {span(js)}")
                break  # first working param name
        except Exception as e:
            print(f"  ?{pn}={lim:<5} ERR {str(e)[:45]}")
    else:
        continue

print("\n=== date-range params ===")
for pn_from, pn_to in [("from", "to"), ("start", "end"), ("from_date", "to_date")]:
    try:
        js = mq.get("gamma-levels/SPX/eod/history", **{pn_from: "2025-01-01", pn_to: "2026-07-15"})
        print(f"  ?{pn_from}/{pn_to} -> {span(js)}")
    except Exception as e:
        print(f"  ?{pn_from}/{pn_to} ERR {str(e)[:45]}")

# Save the deepest pull we got with limit=5000
best = mq.get("gamma-levels/SPX/eod/history", limit=5000)
Path("scratchpad/mq_spx_eod_history_raw.json").write_text(json.dumps(best, indent=1), encoding="utf-8")
print(f"\nsaved deepest pull: {span(best)}")
print("sample keys:", list(best[0].keys()) if isinstance(best, list) and best else None)
