"""verify_nt_checks_20260724.py — prove the fixed NT8 depth checks against live state.

Context (2026-07-24): NT8 Restart / Pre-Open Verify exited 1 every night since the
depth collector moved from the MarketDepthRecorder STRATEGY to the AddOn
(writes data/depth/addon_test/). Two stale checks caused the false alarms:
  - nt8_maintenance.depth_size() globbed only data/depth root (addon_test invisible)
  - nt8_maintenance._armed_state() grepped for strategy 'Enabling' log lines the
    AddOn never writes -> "recorder never enabled this session"
This runs the fixed versions read-only (no telegram pings) and saves dated output.
"""
import datetime as dt
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline_health as ph
import nt8_maintenance as ntm

buf = io.StringIO()


def out(m):
    print(m)
    buf.write(m + "\n")


out(f"run: {dt.datetime.now().isoformat()} (machine time)")
out(f"market_state: {ph.market_state()}")

d = ph.check_depth()
out(f"pipeline_health.check_depth: state={d['state']} detail={d['detail']}")

sz = ntm.depth_size()
out(f"nt8_maintenance.depth_size: {sz/1e6:,.1f} MB (must be >0 while recording)")

armed, detail = ntm._armed_state()
out(f"nt8_maintenance._armed_state: armed={armed} detail={detail}")

ok = d["state"] == ph.OK and sz > 0 and armed
out(f"VERDICT: {'PASS' if ok else 'FAIL'}")

stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
res = ROOT / "data" / "_catalog" / f"verify_nt_checks_{stamp}.txt"
res.write_text(buf.getvalue(), encoding="utf-8")
print(f"saved: {res}")
sys.exit(0 if ok else 1)
