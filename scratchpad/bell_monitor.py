"""Wait for the 08:30 CT bell sequence, then dump a status report (exit -> notification)."""
import time, json, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
CT = ZoneInfo("America/Chicago")
SIM = Path("data/options_sim")

target = dt.datetime.now(CT).replace(hour=8, minute=33, second=0, microsecond=0)
wait = (target - dt.datetime.now(CT)).total_seconds()
print(f"[{dt.datetime.now(CT):%H:%M:%S CT}] sleeping {wait/60:.0f}min until 08:33 CT", flush=True)
if wait > 0:
    time.sleep(wait)

print(f"=== BELL REPORT {dt.datetime.now(CT):%H:%M:%S CT} ===", flush=True)
# 1. plan state
try:
    d = json.loads((SIM / f"gameplan_{dt.datetime.now(CT):%Y%m%d}.json").read_text())
    fired = [t["id"] for t in d["triggers"] if t.get("fired")]
    errs = [(t["id"], t.get("status"), t.get("error") or t.get("skip_reason"))
            for t in d["triggers"] if t.get("status") not in ("armed", "fired", None)]
    print("generated:", d.get("generated_at"), "| band:", d.get("em_low"), "-", d.get("em_high"))
    print("open_spot:", d.get("open_spot"), "@", d.get("open_spot_at"))
    print(f"fired {len(fired)}: {fired}")
    print("non-clean statuses:", errs or "none")
except Exception as e:
    print("PLAN READ FAIL:", e)
# 2. feed
try:
    lv = json.loads((SIM / "live.json").read_text())
    print("feed:", lv.get("state"), lv.get("spx"), "@", lv.get("ts_et"))
except Exception as e:
    print("live.json:", e)
# 3. recorder file
ch = SIM / f"chain_{dt.datetime.now(CT):%Y%m%d}.csv"
print("recorder:", f"{ch.name} {ch.stat().st_size/1024:.0f}KB" if ch.exists() else "NO FILE")
# 4. trades
try:
    import pandas as pd
    t = pd.read_parquet("data/options_log/trades.parquet")
    print(f"ledger: {len(t)} rows")
    if len(t):
        print(t[["trade_id", "strategy_id", "credit", "pnl"]].to_string(index=False))
except Exception as e:
    print("ledger:", e)
