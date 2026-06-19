"""
Scale-in sweep validator — proves the FAST sweep == the ENGINE reference.

`bar_analysis._run_ml_scalein_sweep` (fast, prefix-scan, what the app runs) must
produce byte-identical rows to `_run_ml_scalein_sweep_engine` (slow, = simulate_
trades + compute_summary per combo, i.e. the main-sim path) for every combo and
every column. The fast path is a second implementation of the exit logic, so this
is the guard that keeps it from silently drifting — run it after ANY change to
either function.

    .venv\\Scripts\\python scripts\\validate_scalein_sweep.py            # 64-combo subset (~2 min)
    .venv\\Scripts\\python scripts\\validate_scalein_sweep.py --full     # full default grid (slow: ~40 min)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bar_analysis as ba  # noqa: E402
from validate_engine import _load_ticks, DEFAULTS, SIGNALS_PARQUET  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2021-06-18")
    ap.add_argument("--end", default="2022-06-18")
    ap.add_argument("--full", action="store_true", help="full default grid (slow)")
    ap.add_argument("--style", choices=["e2", "blended"], default="e2")
    ap.add_argument("--pb-round", choices=["floor_ceil", "nearest"], default="floor_ceil")
    ap.add_argument("--first-trade-only", action="store_true")
    ap.add_argument("--first-2-filled-only", action="store_true")
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    s = pd.read_parquet(SIGNALS_PARQUET)
    s["DateTime"] = pd.to_datetime(s["DateTime"])
    if "Date" not in s.columns:
        s["Date"] = s["DateTime"].dt.date
    s = s[(s["DateTime"] >= pd.Timestamp(args.start)) &
          (s["DateTime"] <= pd.Timestamp(args.end) + pd.Timedelta(days=1))]
    tbd = {d: _load_ticks(d) for d in sorted(s["Date"].unique()) if not _load_ticks(d).empty}
    s = s[s["Date"].isin(tbd)].copy()
    print(f"signals: {len(s)}  days: {len(tbd)}")

    if args.full:
        grid = dict(pb_vals=None, t1_vals=None, t2_vals=None)  # function defaults
    else:
        grid = dict(
            pb_vals=[-0.25, -0.50, -0.75, -1.0],
            t1_vals=[0.5, 1.0, 1.5, 2.5],          # spans T1<T2 and T1>T2
            t2_vals=[0.5, 1.0, 1.5, 2.0],
        )

    common = dict(
        entry_slip=cfg["entry_slip"], exit_slip=cfg["exit_slip"], stop_offset=cfg["stop_offset"],
        tick_value=cfg["tick_value"], contracts=cfg["contracts_t1"] + cfg["contracts_t2"],
        commission=cfg["commission"], contracts_t1=cfg["contracts_t1"], contracts_t2=cfg["contracts_t2"],
        first_trade_only=args.first_trade_only, first_2_filled_only=args.first_2_filled_only,
        scale_in_style=args.style, pb_round=args.pb_round,
        **grid,
    )

    print("running FAST…")
    fast = ba._run_ml_scalein_sweep(s, tbd, **common)
    print(f"  {len(fast)} rows")
    print("running ENGINE reference (slow)…")
    ref = ba._run_ml_scalein_sweep_engine(s, tbd, **common)
    print(f"  {len(ref)} rows")

    keys = ["PB_R", "T1_R", "T2_R"]
    fast = fast.sort_values(keys).reset_index(drop=True)
    ref = ref.sort_values(keys).reset_index(drop=True)

    if fast.shape != ref.shape:
        print(f"SHAPE DIFF fast={fast.shape} ref={ref.shape}")
        sys.exit(1)

    total_diff = 0
    for col in ref.columns:
        a, b = fast[col].values, ref[col].values
        if pd.api.types.is_float_dtype(ref[col]):
            neq = ~np.isclose(a, b, rtol=0, atol=1e-9, equal_nan=True)
        else:
            neq = ~((a == b) | (pd.isna(a) & pd.isna(b)))
        ndiff = int(neq.sum())
        if ndiff:
            total_diff += ndiff
            print(f"  [{col}] {ndiff} diffs")
            ex = ref[neq][keys].head(5)
            for _, r in ex.iterrows():
                m = (ref[keys] == r[keys].values).all(axis=1)
                print(f"      PB={r['PB_R']} T1={r['T1_R']} T2={r['T2_R']}: "
                      f"fast={fast.loc[m, col].values}  ref={ref.loc[m, col].values}")

    print("=" * 60)
    if total_diff == 0:
        print(f"IDENTICAL — fast == engine on all {len(ref)} combos, {len(ref.columns)} cols")
    else:
        print(f"{total_diff} CELL DIFFERENCES — fast path has drifted")
        sys.exit(1)


if __name__ == "__main__":
    main()
