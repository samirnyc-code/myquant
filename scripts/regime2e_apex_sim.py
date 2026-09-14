"""Does the 2E book survive APEX's trailing-threshold accounts? (EOD model)

Apex rules modeled (from the 2026 rule references):
  - Trailing threshold T trails the HIGHEST end-of-day balance: floor = peak_EOD - T.
  - Once EOD balance reaches Safety Net = start + T + $100, the threshold LOCKS at
    start + $100 and never moves. floor = start + 100 thereafter.
  - Blow if EOD balance <= floor. (EOD-model check is end-of-day.)
  - Plans: 150K T=$5,000 (17c), 250K T=$6,500 (27c), 300K T=$7,500 (35c).
  - Eval profit goal: 150K $9,000 / 250K $15,000 / 300K $20,000 (same trailing rule).
  - Pre-safety-net contract cap = half; we trade 1 ES so irrelevant.

NOTE: the INTRADAY Apex model (legacy "Full", Daily-DD None) trails the real-time
peak INCLUDING UNREALIZED profit — strictly harsher. Our measured intraday equity
maxDD (~$7-9k, open positions marked) exceeds every plan's threshold, so a hold-to-
EOD book is a poor fit for the intraday model; this sim is the FAVOURABLE (EOD) case.

  python scripts/regime2e_apex_sim.py [mode_sweep_csv]
"""
import sys
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

MULT = 50.0; COST = 17.5
OUTDIR = Path(__file__).resolve().parent.parent / "reports" / "regime2e"
PLANS = [("150K", 5000.0, 9000.0), ("250K", 6500.0, 15000.0), ("300K", 7500.0, 20000.0)]


def apex_eod(daily, T):
    """Return (blown_date, deepest_margin, lock_date, pass_date, final). Relative to start=0."""
    eq = 0.0; peak = 0.0; locked = False; blown = None; lock_date = None; pass_date = None
    margin = 1e9
    for d, p in daily.items():
        eq += p
        peak = max(peak, eq)
        if not locked and peak >= T + 100:
            locked = True; lock_date = d
        floor = 100.0 if locked else peak - T
        margin = min(margin, eq - floor)
        if blown is None and eq <= floor:
            blown = d
        if pass_date is None and eq >= 0:  # placeholder, set below
            pass
    return blown, margin, lock_date, eq


def pass_eval(daily, goal, T):
    """When (if ever) cumulative EOD hits the profit goal WITHOUT first breaching floor."""
    eq = 0.0; peak = 0.0; locked = False
    for d, p in daily.items():
        eq += p; peak = max(peak, eq)
        if not locked and peak >= T + 100:
            locked = True
        floor = 100.0 if locked else peak - T
        if eq <= floor:
            return None, d          # blew before passing
        if eq >= goal:
            return d, None          # passed
    return None, None               # never reached goal, never blew


def main():
    csvs = sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(csvs[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    print(f"{path.name}  (ES $50/pt, cost ${COST}/tr, Apex EOD trailing model)\n")
    for mode in ["one_per_day", "flip"]:
        g = df[df["mode"] == mode]
        if g.empty:
            continue
        g = g.assign(net=(g["pts"] - COST / MULT) * MULT)
        daily = g.groupby("date")["net"].sum()
        print(f"=== MODE {mode} ===")
        for name, T, goal in PLANS:
            blown, margin, lock_date, final = apex_eod(daily, T)
            pdate, pblow = pass_eval(daily, goal, T)
            surv = f"BLOWN {blown}" if blown else f"survives (closest to floor ${margin:,.0f})"
            ev = (f"eval PASSED {pdate}" if pdate else
                  (f"eval BLEW {pblow}" if pblow else "eval goal never reached"))
            print(f"  {name} (T=${T:,.0f}, goal ${goal:,.0f}): {surv}   | {ev}   | 5yr final ${final:+,.0f}")
        print()
    # also show the EOD equity peak-to-trough (the number the trailing DD watches)
    for mode in ["one_per_day", "flip"]:
        g = df[df["mode"] == mode]
        g = g.assign(net=(g["pts"] - COST / MULT) * MULT)
        daily = g.groupby("date")["net"].sum()
        eq = daily.cumsum()
        dd = (eq - eq.cummax())
        print(f"{mode}: worst EOD peak-to-trough drawdown = ${dd.min():,.0f} "
              f"(this must stay < the plan threshold during the un-locked ramp)")


if __name__ == "__main__":
    main()
