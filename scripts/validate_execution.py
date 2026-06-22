"""ESA execution-model acceptance + regression harness.

Synthetic, controlled price paths — no historical tick data (the full validators
exhaust memory loading every parquet). Covers the design spec §17 acceptance tests
plus the baseline-equivalence guard: market entry + delay 0 + fixed slip must fill
at the first tick of the next bar exactly as the pre-ESA engine did.

Run: python scripts/validate_execution.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from simulation_engine import (  # noqa: E402
    _resolve_entry, _simulate_one, simulate_trades, TICK_SIZE,
    EXECUTION_MODEL_VERSION,
)

TS = TICK_SIZE
SIG = pd.Timestamp("2024-01-02 09:00:00")

_n_pass = 0
_n_fail = 0


def check(name, cond, detail=""):
    global _n_pass, _n_fail
    if cond:
        _n_pass += 1
        print(f"  PASS  {name}")
    else:
        _n_fail += 1
        print(f"  FAIL  {name}  {detail}")


def _times(n, t0=SIG, spacing_ms=1000, start_ms=1000):
    """n tick timestamps strictly after t0 (1s spacing by default)."""
    base = np.datetime64(pd.Timestamp(t0))
    return np.array([base + np.timedelta64(start_ms + i * spacing_ms, "ms") for i in range(n)])


def _day_ticks(prices, t0=SIG, spacing_ms=1000):
    times = _times(len(prices), t0, spacing_ms)
    return pd.DataFrame({"DateTime": pd.to_datetime(times), "Price": np.asarray(prices, float)})


# ── Entry-model acceptance (§17 Tests 1,2,3,7) — reference = SEPrice (first tick) ──

def test_entry_models():
    print("Entry models (§6/§7, ref = SEPrice = first tick):")

    # Test 1 — Long STOP invalid: no retrace below SEPrice → NO FILL
    p = np.array([6000.00, 6000.25])
    r = _resolve_entry(p, _times(2), SIG, True, "stop", 0, 0, TS)
    check("T1 long stop invalid → NO FILL", r is None, f"got {r}")

    # Test 2 — Long STOP valid: retrace (5999.75) then through (6000.25) → FILL @ ref+1t
    p = np.array([6000.00, 5999.75, 6000.25])
    r = _resolve_entry(p, _times(3), SIG, True, "stop", 0, 0, TS)
    check("T2 long stop valid → FILL @6000.25",
          r is not None and abs(r["raw_fill"] - 6000.25) < 1e-9 and abs(r["se_price"] - 6000.00) < 1e-9,
          f"got {r}")

    # Test 3 — Short STOP valid: retrace up (6000.25) then through down (5999.75) → FILL
    p = np.array([6000.00, 6000.25, 5999.75])
    r = _resolve_entry(p, _times(3), SIG, False, "stop", 0, 0, TS)
    check("T3 short stop valid → FILL @5999.75",
          r is not None and abs(r["raw_fill"] - 5999.75) < 1e-9, f"got {r}")

    # Short STOP invalid: no retrace up → NO FILL
    p = np.array([6000.00, 5999.75])
    r = _resolve_entry(p, _times(2), SIG, False, "stop", 0, 0, TS)
    check("short stop invalid → NO FILL", r is None, f"got {r}")

    # Test 7 — Market entry honors delay: fill at first tick at/after T+delay,
    # but SEPrice (entry reference) is ALWAYS prices[0] (ESA v2).
    p = np.array([6000.00, 6000.50, 6001.00])  # ticks at +1s, +2s, +3s
    r = _resolve_entry(p, _times(3), SIG, True, "market", 1500, 0, TS)  # 1.5s delay → fill @idx1
    check("T7 market delay 1500ms → fill @6000.50 idx1, SEPrice=6000.00",
          r is not None and r["fill_idx"] == 1 and abs(r["raw_fill"] - 6000.50) < 1e-9
          and abs(r["se_price"] - 6000.00) < 1e-9,
          f"got {r}")

    # Market delay 0 → first tick
    r = _resolve_entry(p, _times(3), SIG, True, "market", 0, 0, TS)
    check("market delay 0 → first tick 6000.00 @idx0",
          r is not None and r["fill_idx"] == 0 and abs(r["se_price"] - 6000.00) < 1e-9, f"got {r}")

    # Wire delay: market + 500ms reaction + 100ms wire → total 600ms → fill at idx1 (+2s tick)
    r = _resolve_entry(p, _times(3), SIG, True, "market", 500, 0, TS, wire_delay_ms=100)
    check("market delay 500+wire 100 → fill @idx0 (600ms < 1s)",
          r is not None and r["fill_idx"] == 0 and abs(r["raw_fill"] - 6000.00) < 1e-9,
          f"got {r}")

    # Wire delay: stop entry — ref is always prices[0], scan starts after delay+wire
    p2 = np.array([6000.00, 6000.25, 5999.75, 6000.25])  # ref=6000, then up, retrace, through
    r = _resolve_entry(p2, _times(4), SIG, True, "stop", 0, 0, TS, wire_delay_ms=1500)
    # wire 1500ms → scan starts at idx1 (+2s), retrace=5999.75@idx2, through=6000.25@idx3
    check("stop + wire 1500ms → scan from idx1, fill @idx3",
          r is not None and r["fill_idx"] == 3 and abs(r["se_price"] - 6000.00) < 1e-9
          and abs(r["raw_fill"] - 6000.25) < 1e-9,
          f"got {r}")

    # Fill timeout: stop entry fills at idx3 (+4s), timeout at 3s → NO FILL
    r = _resolve_entry(p2, _times(4), SIG, True, "stop", 0, 0, TS, max_fill_ms=3000)
    check("stop + timeout 3s → NO FILL (fill at 4s exceeds deadline)",
          r is None, f"got {r}")

    # Fill timeout: stop entry fills at idx3 (+4s), timeout at 5s → FILL
    r = _resolve_entry(p2, _times(4), SIG, True, "stop", 0, 0, TS, max_fill_ms=5000)
    check("stop + timeout 5s → FILL (fill at 4s within deadline)",
          r is not None and r["fill_idx"] == 3, f"got {r}")

    # Fill timeout: market entry, timeout at 500ms → still fills (idx0 is at +1s but that's the first tick)
    p3 = np.array([6000.00, 6001.00])
    r = _resolve_entry(p3, _times(2), SIG, True, "market", 0, 0, TS, max_fill_ms=2000)
    check("market + timeout 2s → FILL at idx0 (+1s within deadline)",
          r is not None and r["fill_idx"] == 0, f"got {r}")


# ── Exit-model acceptance (§17 Tests 4,5,6) via full single-leg sim ──

def _sim(prices, direction="Long", sb=6000.0, stop=5990.0, target_r=2.0,
         entry_slip=0, exit_slip=0, entry_model="market", delay_ms=0):
    return _simulate_one(SIG, direction, sb, stop, _day_ticks(prices),
                         target_r, entry_slip, exit_slip, 0, 12.5,
                         entry_model=entry_model, delay_ms=delay_ms)


def test_exit_models():
    print("Exit models (§10):")
    # entry @6000, stop 5990, risk 10, target_r 2.0 → target 6020.00
    # Test 4 — Long target invalid: prints 6020.00 but not 6020.25 → NO EXIT (EOD)
    r = _sim([6000.00, 6020.00])
    check("T4 long target 6020.00 (no through) → EOD", r["ExitReason"] == "EOD", f"got {r['ExitReason']}")

    # Test 5 — Long target valid: 6020.25 prints → Target
    r = _sim([6000.00, 6020.25])
    check("T5 long target 6020.25 → Target", r["ExitReason"] == "Target", f"got {r['ExitReason']}")

    # Test 6 — Stop touch: 5990.00 prints → Stop (fills on touch, no through)
    r = _sim([6000.00, 5990.00])
    check("T6 stop 5990.00 touch → Stop", r["ExitReason"] == "Stop", f"got {r['ExitReason']}")


# ── Baseline equivalence + audit fields ──

def test_baseline_and_audit():
    print("Baseline + audit:")
    # Market, delay 0, slip 0 → SEPrice & fill = first tick; SBClose = signal price
    r = _sim([6000.00, 6020.25], sb=5999.50)  # signal bar close distinct from first tick
    check("baseline SEPrice = first tick 6000.00", abs(r["SEPrice"] - 6000.00) < 1e-9, f"got {r['SEPrice']}")
    check("baseline EntryPrice = first tick (slip 0)", abs(r["EntryPrice"] - 6000.00) < 1e-9, f"got {r['EntryPrice']}")
    check("baseline SBClose = signal price 5999.50", abs(r["SBClose"] - 5999.50) < 1e-9, f"got {r['SBClose']}")
    check("EntryType recorded", r["EntryType"] == "market", f"got {r['EntryType']}")
    check("ExecModelVersion recorded", r["ExecModelVersion"] == EXECUTION_MODEL_VERSION)

    # Entry slip applied: long fill = first tick + slip ticks
    r = _sim([6000.00, 6020.25], entry_slip=2, exit_slip=0)
    check("entry slip 2t → EntryPrice 6000.50", abs(r["EntryPrice"] - (6000.00 + 2 * TS)) < 1e-9, f"got {r['EntryPrice']}")

    # Exit slip applied on a long target: exit = target - slip ticks
    r = _sim([6000.00, 6020.25], entry_slip=0, exit_slip=1)
    check("exit slip 1t on target → ExitPrice 6019.75", abs(r["ExitPrice"] - (6020.00 - TS)) < 1e-9, f"got {r['ExitPrice']}")

    # ESA v2: SEPrice is ALWAYS prices[0] (first tick), delay only shifts the fill.
    # With 2500ms delay, fill is at idx2 (6010.00) but SEPrice stays 6000.00.
    r = _sim([6000.00, 6005.00, 6010.00, 6020.25], delay_ms=2500)
    check("delay 2500ms → SEPrice still 6000.00 (ESA v2)", abs(r["SEPrice"] - 6000.00) < 1e-9, f"got {r['SEPrice']}")
    check("delay 2500ms → EntryPrice at delayed tick", abs(r["EntryPrice"] - 6010.00) < 1e-9, f"got {r['EntryPrice']}")
    check("delay recorded ActualDelayMs=2500", int(r["ActualDelayMs"]) == 2500, f"got {r['ActualDelayMs']}")


# ── Seeded determinism for slippage ranges (via simulate_trades) ──

def _signals_df():
    return pd.DataFrame([{
        "SignalNum": 1, "SignalType": "CC2", "Direction": "Long",
        "DateTime": SIG, "BarNum": 5, "SignalPrice": 6000.0, "StopPrice": 5990.0,
        "Date": SIG.date(), "FilterStatus": "ok",
    }])


def test_range_determinism():
    print("Slippage ranges + determinism:")
    sigs = _signals_df()
    ticks = {SIG.date(): _day_ticks([6000.00, 6020.25])}
    kw = dict(target_r=2.0, stop_offset=0, tick_value=12.5, contracts=1, commission=4.36)
    a = simulate_trades(sigs, ticks, entry_slip=(0, 3), exit_slip=(0, 3), exec_seed=7, **kw)
    b = simulate_trades(sigs, ticks, entry_slip=(0, 3), exit_slip=(0, 3), exec_seed=7, **kw)
    check("same seed → identical EntryPrice",
          abs(float(a["EntryPrice"].iloc[0]) - float(b["EntryPrice"].iloc[0])) < 1e-9)
    es = int(a["EntrySlipTicks"].iloc[0])
    check("entry slip draw within [0,3]", 0 <= es <= 3, f"got {es}")

    # Fixed int slip must NOT consume the RNG → identical to a pre-ESA fixed run
    c = simulate_trades(sigs, ticks, entry_slip=1, exit_slip=1, exec_seed=7, **kw)
    check("fixed slip 1t → EntryPrice 6000.25",
          abs(float(c["EntryPrice"].iloc[0]) - (6000.00 + TS)) < 1e-9,
          f"got {float(c['EntryPrice'].iloc[0])}")


def main():
    print(f"\nESA validation — model {EXECUTION_MODEL_VERSION}\n")
    test_entry_models()
    test_exit_models()
    test_baseline_and_audit()
    test_range_determinism()
    print(f"\n{_n_pass} passed, {_n_fail} failed\n")
    sys.exit(1 if _n_fail else 0)


if __name__ == "__main__":
    main()
