"""eod_whatif_stops.py — for each trade CLOSED early today, would holding to the
0DTE settle have beaten the stop? Answers 'how could we have made more?'

Settlement value of a vertical at SPX S: intrinsic of short leg minus intrinsic of
long leg (per point), so held P&L = (credit - settle_debit) * 100 * qty. Compares
that against the actual realized P&L of the early exit.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
sys.path.insert(0, str(ROOT / "scripts"))


def _legs(r):
    return json.loads(r.legs) if isinstance(r.legs, str) else r.legs


def _settle_debit(legs, S):
    """What you'd pay to settle the spread at spot S (0 for OTM, intrinsic for ITM)."""
    debit = 0.0
    for lg in legs:
        k, right = float(lg["strike"]), lg["right"]
        intrinsic = max(0.0, (S - k) if right == "C" else (k - S))
        debit += intrinsic if lg["side"] == "sell" else -intrinsic
    return debit


def main():
    S = json.loads((SIM / "live.json").read_text()).get("spx")
    d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    d["e"] = pd.to_datetime(d["entry_dt"], errors="coerce")
    t = d[d["e"] >= "2026-08-17"]
    closed = t[t.pnl.notna()]
    print(f"settle SPX ~{S}\n")
    print(f"{'strategy':<12} {'shorts':>10} {'actual$':>8} {'ifHeld$':>8} {'left$':>7}  verdict")
    total_left = 0.0
    for _, r in closed.iterrows():
        legs = _legs(r)
        shorts = "/".join(f"{float(l['strike']):.0f}{l['right']}" for l in legs if l["side"] == "sell")
        qty = int(legs[0].get("qty", 1))
        held = (float(r.credit) - _settle_debit(legs, S)) * 100 * qty
        actual = float(r.pnl)
        left = held - actual
        total_left += left
        verdict = "STOP SAVED us" if left < 0 else ("held would beat" if left > 0 else "wash")
        print(f"{r.strategy_id:<12} {shorts:>10} {actual:>8.0f} {held:>8.0f} {left:>+7.0f}  {verdict}")
    print(f"\nnet 'money left on the table' by stopping early: ${total_left:+,.0f}")
    print("(positive = holding would have made more; negative = the stops correctly avoided bigger losses)")


if __name__ == "__main__":
    main()
