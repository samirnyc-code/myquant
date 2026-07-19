"""Probe whether the MQ gamma-levels endpoint honors a date param under ANY name.

Grab the token, then hit gamma-levels/SPX/eod with a battery of date param names
and a known-past date. Compare the returned report_date / values to today's.
Also try the /levels endpoint variants the /en/levels page might use.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mq_api import MQ, GW, CF  # noqa

PAST = "2026-07-01"
mq = MQ()

def show(tag, js):
    if isinstance(js, dict):
        rd = js.get("report_date") or js.get("date") or js.get("tradeDate")
        cr = js.get("call_resistance") or js.get("cr")
        keys = list(js.keys())[:12]
        print(f"  {tag:38s} report_date={rd} cr={cr} keys={keys}")
    elif isinstance(js, list):
        print(f"  {tag:38s} list len={len(js)} first={json.dumps(js[0])[:120] if js else None}")
    else:
        print(f"  {tag:38s} {str(js)[:120]}")

# 0) baseline today
print("=== baseline gamma-levels/SPX/eod (no date) ===")
base = mq.get("gamma-levels/SPX/eod")
Path("scratchpad/mq_levels_today_raw.json").write_text(json.dumps(base, indent=1), encoding="utf-8")
show("no-date", base)
print("  ALL KEYS:", list(base.keys()) if isinstance(base, dict) else type(base))

print("\n=== try date param names on gamma-levels/SPX/eod ===")
for p in ["date", "report_date", "tradeDate", "trade_date", "eod_date", "day", "from", "to", "as_of", "asOf"]:
    try:
        js = mq.get("gamma-levels/SPX/eod", **{p: PAST})
        rd = js.get("report_date") if isinstance(js, dict) else None
        changed = "CHANGED!" if rd and str(rd) != str(base.get("report_date")) else ""
        show(f"?{p}={PAST} {changed}", js)
    except Exception as e:
        print(f"  ?{p}={PAST}  ERR {str(e)[:60]}")

print("\n=== try alternate endpoints/paths ===")
for path in [
    f"gamma-levels/SPX?date={PAST}",
    "gamma-levels/SPX",
    f"gamma-levels/SPX/history",
    f"levels/SPX/eod",
    f"levels/SPX?date={PAST}",
    f"gamma-levels/SPX/eod/history",
]:
    for base_host in [GW, CF]:
        try:
            # split query
            if "?" in path:
                p, q = path.split("?"); k, v = q.split("=")
                js = mq.get(p, base=base_host, **{k: v})
            else:
                js = mq.get(path, base=base_host)
            show(f"{base_host.split('//')[1][:12]} {path}", js)
        except Exception as e:
            print(f"  {base_host.split('//')[1][:12]} {path}  ERR {str(e)[:50]}")
