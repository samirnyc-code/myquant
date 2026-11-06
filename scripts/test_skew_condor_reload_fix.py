"""Regression test for the 2026-11-05 skew_condor_shadow.py fix: main()'s poll loop
must re-read the gameplan every iteration, not once at startup, or a trigger that
fires AFTER the script's own startup moment is invisible to it for the rest of the
session (confirmed live cause of zero pairs entered all day on 2026-11-05).

Does NOT require IB or a real trading day -- uses a throwaway scratch gameplan
date (2099-12-31, cleaned up after) and calls the real load_plan()/plan_path()
functions directly, plus reproduces the exact gate condition process() uses on
the put trigger. This proves the two things the fix depends on:
  1. load_plan() has no caching -- re-calling it sees whatever is on disk NOW.
  2. The main()-loop pattern (`fresh = load_plan(date); if fresh: plan = fresh`)
     correctly swaps in the updated triggers before the put-fired gate is checked.

Usage: .venv/Scripts/python.exe scripts/test_skew_condor_reload_fix.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skew_condor_shadow import load_plan, plan_path

TEST_DATE = "2099-12-31"   # far-future scratch date, can't collide with real data


def put_gate_blocks(plan, put_setup="eodic_p"):
    """Exact condition from process(): True means the anchor would be skipped."""
    put_trig = next((t for t in plan["triggers"] if t.get("setup") == put_setup), None)
    return not put_trig or not put_trig.get("fired") or not put_trig.get("filled_legs")


def main():
    p = plan_path(TEST_DATE)
    assert not p.exists(), f"refusing to run: {p} already exists (not a scratch file)"

    try:
        # --- step 1: simulate the script's startup moment -- put NOT fired yet ---
        not_fired = {
            "date": TEST_DATE.replace("-", ""),
            "triggers": [
                {"setup": "eodic_p", "fired": False},
                {"setup": "eodic_c", "fired": True, "structure": {"short": 100}},
            ],
        }
        p.write_text(json.dumps(not_fired), encoding="utf-8")

        plan = load_plan(TEST_DATE)   # this is what main() does ONCE at startup
        blocked_before = put_gate_blocks(plan)
        print(f"poll 1 (pre-fire snapshot): gate blocks entry = {blocked_before}")
        assert blocked_before, "test setup wrong -- should be blocked pre-fire"

        # --- step 2: the REAL trigger daemon fires eodic_p 6 min later, rewrites the file ---
        fired = {
            "date": TEST_DATE.replace("-", ""),
            "triggers": [
                {"setup": "eodic_p", "fired": True,
                 "filled_legs": [{"side": "sell", "strike": 100.0}]},
                {"setup": "eodic_c", "fired": True, "structure": {"short": 100}},
            ],
        }
        p.write_text(json.dumps(fired), encoding="utf-8")

        # --- step 3a: OLD (buggy) behavior -- reuse the stale `plan` object, never reload ---
        blocked_with_stale_plan = put_gate_blocks(plan)
        print(f"poll 2, OLD behavior (reusing stale `plan`): gate blocks entry = "
              f"{blocked_with_stale_plan}  <-- this was the 2026-11-05 bug")
        assert blocked_with_stale_plan, "stale plan should still show blocked (reproduces the bug)"

        # --- step 3b: NEW (fixed) behavior -- exact line from main()'s loop ---
        fresh = load_plan(TEST_DATE)
        if fresh:
            plan = fresh
        blocked_with_reload = put_gate_blocks(plan)
        print(f"poll 2, FIXED behavior (fresh = load_plan(date); plan = fresh): "
              f"gate blocks entry = {blocked_with_reload}")
        assert not blocked_with_reload, "fix did not work -- should be unblocked after reload"

        print("\nPASS: stale-plan reuse reproduces the bug; the fix's reload line clears it.")
    finally:
        if p.exists():
            p.unlink()
            print(f"cleaned up scratch file {p}")


if __name__ == "__main__":
    main()
