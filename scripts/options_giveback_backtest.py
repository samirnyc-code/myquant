#!/usr/bin/env python
"""
options_giveback_backtest.py  (S84, 2026-07-24)

Replays the recorded intraday P&L path (data/options_sim/marks.csv) of every
options trade we have ever taken through a PEAK-GIVEBACK + HARD-STOP exit rule,
and reports what each trade WOULD have made vs what it actually made.

The rule (structure-agnostic, P&L-path based — the half the live daemon lacks):

  1. TRAIL / peak-giveback: track running peak of unrealized P&L. Once the peak
     clears an "arm" threshold (a real gain, not noise), exit the first time P&L
     retraces GIVEBACK of that peak. Upside stays uncapped — a runaway trend day
     keeps making new peaks and the trail rides up with it.
  2. HARD STOP: exit if unrealized P&L falls to -HARD_STOP of collateral.

Comparison caveats (stated, not hidden):
  - marks unreal_pnl is a MID-mark; the rule's exit P&L uses that mid minus a
    round-trip fee (FEE_RT). Real fills would be a touch worse (spread crossing).
  - Trades with no marks series are reported unchanged (no intraday data).
  - Trades where neither trail nor stop fires are held to their ACTUAL exit, so
    rule_pnl == actual pnl for those.

Output: data/options_sim/giveback_backtest_<DATE>.csv  (+ printed summary)
"""
import sys, csv
from pathlib import Path
from collections import defaultdict
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LEDGER = ROOT / "data" / "options_log" / "trades.parquet"
RUN_DATE = "20260724"  # passed explicitly; machine tz is unreliable

# ---- rule parameters (tune here) ----
# Chosen from --sweep: the hard stop is the robust workhorse; the trail must ARM HIGH
# ($800), otherwise a low arm ($300) whipsaws out of the big move on the first head-fake
# (07/24 straddle: armed at $355, exited +$227, then the trade ran to +$2,172). A high
# arm + looser 50% giveback rides the move and still gives back only half of a real peak.
GIVEBACK = 0.50        # exit after retracing this fraction of peak unrealized P&L
HARD_STOP = 0.25       # exit if unrealized P&L <= -HARD_STOP * collateral
ARM_FLOOR = 800.0      # trail arms only after peak >= max(ARM_FLOOR, ARM_PCT*collat)
ARM_PCT = 0.10
FEE_RT = 2.60          # round-trip fee assumed on a rule-forced close


def load_marks():
    series = defaultdict(list)
    with open(SIM / "marks.csv", newline="") as f:
        for r in csv.DictReader(f):
            try:
                series[r["trade_id"]].append((r["ts_et"], float(r["unreal_pnl"])))
            except (TypeError, ValueError):
                continue
    for tid in series:
        series[tid].sort(key=lambda x: x[0])
    return series


def simulate(path, collateral):
    """Return (rule_exit_pnl_or_None, reason, peak, exit_ts). None => never fired."""
    peak = float("-inf")
    peak_ts = None
    arm_min = max(ARM_FLOOR, ARM_PCT * (collateral or 0))
    armed = False
    for ts, p in path:
        if collateral and p <= -HARD_STOP * collateral:
            return p - FEE_RT, f"HARD STOP -{HARD_STOP:.0%} collat", peak, ts
        if p > peak:
            peak, peak_ts = p, ts
        if peak >= arm_min:
            armed = True
        if armed and p <= peak * (1 - GIVEBACK):
            return p - FEE_RT, f"TRAIL: gave back {GIVEBACK:.0%} of peak ${peak:,.0f}", peak, ts
    return None, "held to actual exit (rule never fired)", (peak if peak > float("-inf") else None), None


def run_params(marks, led, giveback, hard_stop, arm_floor, arm_pct=ARM_PCT, fee=FEE_RT):
    """Simulate one param set; return (total_rule_pnl, total_actual, today_straddle_pnl,
    n_winners_cut, sum_winners_cut) over closed comparable trades."""
    def sim(path, collat):
        peak = float("-inf"); arm_min = max(arm_floor, arm_pct * (collat or 0)); armed = False
        for ts, p in path:
            if collat and p <= -hard_stop * collat:
                return p - fee
            peak = max(peak, p)
            if peak >= arm_min:
                armed = True
            if armed and p <= peak * (1 - giveback):
                return p - fee
        return None
    tot_r = tot_a = 0.0; today = None; n_cut = 0; sum_cut = 0.0
    for tid, path in marks.items():
        rec = led.get(tid, {})
        collat = float(rec["collateral"]) if pd.notna(rec.get("collateral")) else None
        actual = float(rec["pnl"]) if pd.notna(rec.get("pnl")) else None
        r = sim(path, collat)
        rp = actual if r is None else r
        if tid == "auto_20260724_090200":
            today = rp
        if actual is not None and rp is not None:
            tot_r += rp; tot_a += actual
            if rp - actual < -1:
                n_cut += 1; sum_cut += (rp - actual)
    return tot_r, tot_a, today, n_cut, sum_cut


def sweep(marks, led):
    print("\nPARAM SWEEP  (total = closed comparable; today = the motivating 07/24 straddle,\n"
          "             peak +$2,172; winners_cut = trades the rule exited BELOW their actual P&L)\n")
    hdr = f"{'giveback':>9}{'hard_stop':>10}{'arm_floor':>10}{'total_rule':>11}{'today':>8}{'win_cut':>9}{'cut_$':>9}"
    print(hdr); print("-" * len(hdr))
    # hard-stop ONLY (giveback=100% => trail can never fire): isolates the stop's contribution
    tr, ta, td, nc, sc = run_params(marks, led, 1.0, 0.25, 1e12)
    print(f"{'HARD STOP ONLY (no trail)':>29}{'':>0}{tr:>11,.0f}{(td or 0):>8,.0f}{nc:>9d}{sc:>+9,.0f}")
    print("-" * len(hdr))
    for arm in (300, 800, 1200):
        for gb in (0.33, 0.50):
            tr, ta, td, nc, sc = run_params(marks, led, gb, 0.25, arm)
            print(f"{gb:>9.0%}{0.25:>10.0%}{arm:>10,.0f}{tr:>11,.0f}"
                  f"{(td or 0):>8,.0f}{nc:>9d}{sc:>+9,.0f}")
    print("-" * len(hdr))
    book = sum(float(r["pnl"]) for tid, r in led.items() if pd.notna(r.get("pnl")) and tid in marks)
    print(f"actual book total, no rule (same comparable set): {book:,.0f}")


def main():
    marks = load_marks()
    df = pd.read_parquet(LEDGER)
    led = {r["trade_id"]: r for _, r in df.iterrows()}
    if "--sweep" in sys.argv:
        sweep(marks, led)
        return

    rows = []
    for tid, path in marks.items():
        rec = led.get(tid, {})
        collat = rec.get("collateral")
        collat = float(collat) if pd.notna(collat) else None
        actual = rec.get("pnl")
        actual = float(actual) if pd.notna(actual) else None  # None = still open
        structure = rec.get("structure", "?")
        actual_reason = rec.get("close_reason")
        rule_pnl, reason, peak, exit_ts = simulate(path, collat)
        peak_final = max(p for _, p in path)
        if rule_pnl is None:
            rule_pnl = actual  # held to real exit
        rows.append({
            "trade_id": tid,
            "structure": structure,
            "collateral": collat,
            "peak_unreal": round(peak_final, 0),
            "actual_pnl": None if actual is None else round(actual, 0),
            "rule_pnl": None if rule_pnl is None else round(rule_pnl, 0),
            "delta": None if (actual is None or rule_pnl is None) else round(rule_pnl - actual, 0),
            "rule_exit_reason": reason,
            "rule_exit_ts": exit_ts,
            "actual_close_reason": actual_reason if isinstance(actual_reason, str) else "",
        })

    rows.sort(key=lambda r: (r["delta"] is None, -(r["delta"] or 0)))
    out = SIM / f"giveback_backtest_{RUN_DATE}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ---- summary ----
    closed = [r for r in rows if r["actual_pnl"] is not None and r["rule_pnl"] is not None]
    tot_actual = sum(r["actual_pnl"] for r in closed)
    tot_rule = sum(r["rule_pnl"] for r in closed)
    changed = [r for r in closed if abs(r["delta"]) >= 1]

    print(f"\nGIVEBACK BACKTEST  giveback={GIVEBACK:.0%} hard_stop=-{HARD_STOP:.0%} "
          f"arm=max(${ARM_FLOOR:.0f},{ARM_PCT:.0%}·collat) fee_rt=${FEE_RT}")
    print(f"trades with marks: {len(rows)}   closed & comparable: {len(closed)}   "
          f"rule changed the exit on: {len(changed)}\n")

    hdr = f"{'trade_id':<30}{'struct':<18}{'peak':>7}{'actual':>9}{'rule':>9}{'delta':>9}  reason"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        a = "OPEN" if r["actual_pnl"] is None else f"{r['actual_pnl']:,.0f}"
        ru = "?" if r["rule_pnl"] is None else f"{r['rule_pnl']:,.0f}"
        d = "" if r["delta"] is None else f"{r['delta']:+,.0f}"
        print(f"{r['trade_id']:<30}{str(r['structure'])[:17]:<18}{r['peak_unreal']:>7,.0f}"
              f"{a:>9}{ru:>9}{d:>9}  {r['rule_exit_reason']}")

    print("-" * len(hdr))
    print(f"{'TOTAL (closed, comparable)':<48}{tot_actual:>9,.0f}{tot_rule:>9,.0f}"
          f"{tot_rule - tot_actual:>+9,.0f}")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
