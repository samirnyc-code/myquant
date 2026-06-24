"""validate_multileg_invariant.py — the 2-leg scale-in does what the design says.

The 2-leg is a scale-IN: E1 at the signal; E2 only exists if price pulls back to the PB
level. Two scale-in styles:
  * "e2"      = E1 break-even — the WHOLE position exits at E1's entry price (any PB%);
                E1 scratches, E2 banks the pullback. target_r is irrelevant.
  * "blended" = ride to a T2 computed off the blended average entry.

This asserts the engine's per-trade P&L on hand-checked synthetic ticks:
  A. E1-BE win   — pullback fills E2, price returns to E1 entry → E1 ≈ $0, E2 ≈ +PB gain
  B. full stop   — pullback fills E2, then both stop → loss = E1 risk + E2 risk
  C. T1 pre-PB   — T1 hits before any pullback → E1 takes profit, E2 never exists (single leg)

(Earlier this file tested the bogus ml_pb_r=0 "scale-out"; that config is now removed and
guarded in the engine, so it no longer exists to test.)

Run: .venv/Scripts/python.exe scripts/validate_multileg_invariant.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from simulation_engine import _simulate_one_multileg, simulate_trades  # noqa: E402

TV = 12.5  # per 0.25 tick = $50/pt
DOL = TV / 0.25  # $/point


def ticks(sig_dt, prices):
    dts = [sig_dt + pd.Timedelta(seconds=i + 1) for i in range(len(prices))]
    return pd.DataFrame({"DateTime": pd.to_datetime(dts), "Price": np.asarray(prices, float)})


def scalein(sig, d, sp, stop, t1, t2, pb, path, style="e2"):
    return _simulate_one_multileg(sig, d, sp, stop, ticks(sig, path), t2, t1, "exit",
                                  0, 0, 0, TV, TV, ml_pb_r=pb, scale_in_style=style,
                                  entry_model="market", calc_delay_ms=0)


def check(name, r, exp_gross, exp_reason=None, exp_l1=None, exp_l2=None):
    if not r.get("ok"):
        print(f"  FAIL {name}: no fill ({r.get('FilterStatus')})"); return 1
    g = float(r["GrossPnL"]); ok = abs(g - exp_gross) < 1e-6
    extra = ""
    if exp_l1 is not None:
        l1 = float(r.get("Leg1GrossPnL", np.nan)); ok &= abs(l1 - exp_l1) < 1e-6
        extra += f" L1={l1:+.0f}(exp {exp_l1:+.0f})"
    if exp_l2 is not None:
        l2 = float(r.get("Leg2GrossPnL") or 0.0); ok &= abs(l2 - exp_l2) < 1e-6
        extra += f" L2={l2:+.0f}(exp {exp_l2:+.0f})"
    if exp_reason is not None:
        ok &= (r["ExitReason"] == exp_reason); extra += f" [{r['ExitReason']}]"
    print(f"  {'OK ' if ok else 'BUG'} {name}: gross={g:+.0f} (exp {exp_gross:+.0f}){extra}")
    return 0 if ok else 1


def main() -> int:
    sig = pd.Timestamp("2024-01-02 14:35:00")
    fails = 0
    print("2-leg scale-in, style=e2 (E1 break-even).  risk=10pt ($500), PB=-0.5R (5pt)")
    print("-" * 78)

    # LONG: entry 5000, stop 4990, PB @4995, T1 @5010, E1-BE exit @5000
    # A win: enter, dip to 4994 (E2 fills @4995), recover to 5001 -> exit both @5000
    fails += check("LONG  E1-BE win", scalein(sig, "Long", 5000, 4990, 1.0, 2.0, -0.5,
                   [5000, 4994, 5001]), exp_gross=250, exp_l1=0, exp_l2=250)
    # B stop: enter, dip to 4994 (E2 fills), drop to 4989 -> both stop @4990
    fails += check("LONG  full stop", scalein(sig, "Long", 5000, 4990, 1.0, 2.0, -0.5,
                   [5000, 4994, 4989]), exp_gross=-750, exp_l1=-500, exp_l2=-250)
    # C T1 pre-PB: enter, jump to 5011 (T1 @5010) before any pullback -> E1 only
    fails += check("LONG  T1 pre-PB ", scalein(sig, "Long", 5000, 4990, 1.0, 2.0, -0.5,
                   [5000, 5011]), exp_gross=500, exp_reason="T1_only", exp_l2=0)

    print("-" * 78)
    # SHORT mirror: entry 5000, stop 5010, PB @5005, T1 @4990, E1-BE exit @5000
    fails += check("SHORT E1-BE win", scalein(sig, "Short", 5000, 5010, 1.0, 2.0, -0.5,
                   [5000, 5006, 4999]), exp_gross=250, exp_l1=0, exp_l2=250)
    fails += check("SHORT full stop", scalein(sig, "Short", 5000, 5010, 1.0, 2.0, -0.5,
                   [5000, 5006, 5011]), exp_gross=-750, exp_l1=-500, exp_l2=-250)

    print("-" * 78)
    # Guard: multileg=True + ml_pb_r=0 (no pullback) must run as single-leg, not the old
    # degenerate path. Verify via the wrapper that GrossPnL == a 1-contract single-leg.
    bars = {}  # market-model entry doesn't need bars_by_date for these ticks
    sigdf = pd.DataFrame({"DateTime": [sig], "Date": [sig.date()], "Direction": ["Long"],
                          "SignalPrice": [5000.0], "StopPrice": [4990.0], "BarNum": [1]})
    tbd = {sig.date(): ticks(sig, [5000, 5005, 5012, 5021])}
    base = dict(ticks_by_date=tbd, bars_by_date=bars, target_r=2.0, entry_slip=0, exit_slip=0,
                stop_offset=0, tick_value=TV, contracts=1, commission=0.0, pb_round="nearest")
    single = simulate_trades(signals=sigdf, multileg=False, **base)
    guarded = simulate_trades(signals=sigdf, multileg=True, ml_pb_r=0.0,
                              contracts_t1=1, contracts_t2=1, t1_r=1.0, t1_action="exit", **base)
    s_pnl = float(single["NetPnL"].iloc[0]); g_pnl = float(guarded["NetPnL"].iloc[0])
    ok = abs(s_pnl - g_pnl) < 1e-6
    fails += 0 if ok else 1
    print(f"  {'OK ' if ok else 'BUG'} GUARD: multileg+ml_pb_r=0 -> single-leg "
          f"(single={s_pnl:+.0f}, guarded={g_pnl:+.0f})")

    print("-" * 78)
    print(f"\n{'ALL SCALE-IN INVARIANTS PASS' if fails == 0 else f'{fails} FAIL'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
