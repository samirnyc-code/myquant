"""Ratchet regression: vectorized first-hit ratchet path == Python loop.

Proves the new vectorized ratchet scan in `_simulate_one` (and, when added,
`_simulate_one_multileg`) produces byte-identical trades to the long-standing
Python loop, across a MATRIX of ratchet settings over the full 1-yr window —
the same "fast == oracle over a big enough dataset" bar used for the scale-in
sweep (`validate_scalein_sweep.py`).

Both paths run in one process: `_force_loop=True` forces the loop reference,
`_force_loop=False` takes the vectorized path. No git-stash needed.

    .venv\\Scripts\\python scripts\\validate_ratchet.py
    .venv\\Scripts\\python scripts\\validate_ratchet.py --mode single --start 2021-06-18 --end 2022-06-19
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

from simulation_engine import simulate_trades  # noqa: E402
from validate_engine import _load_ticks, DEFAULTS, SIGNALS_PARQUET  # noqa: E402

# Ratchet settings to sweep (dest, ratchet_r, lock_r). Covers BE and Lock-in,
# thresholds below / around / above the target so every code path is exercised.
RATCHET_GRID = [
    ("BE", 0.50, 0.0), ("BE", 0.75, 0.0), ("BE", 1.00, 0.0),
    ("BE", 1.50, 0.0), ("BE", 2.00, 0.0),
    ("Lock-in", 0.75, 0.25), ("Lock-in", 1.00, 0.50),
    ("Lock-in", 1.50, 0.50), ("Lock-in", 2.00, 1.00),
]


def _load_sigs(start, end):
    s = pd.read_parquet(SIGNALS_PARQUET)
    s["DateTime"] = pd.to_datetime(s["DateTime"])
    if "Date" not in s.columns:
        s["Date"] = s["DateTime"].dt.date
    s = s[(s["DateTime"] >= pd.Timestamp(start)) & (s["DateTime"] <= pd.Timestamp(end))]
    tbd = {}
    for d in sorted(s["Date"].unique()):
        t = _load_ticks(d)
        if not t.empty:
            tbd[d] = t
    return s[s["Date"].isin(tbd)].copy(), tbd


def _cmp(df_loop, df_vec, label):
    if df_loop.shape != df_vec.shape:
        print(f"  [{label}] SHAPE DIFF {df_loop.shape} vs {df_vec.shape}")
        return df_loop.shape[0]
    cols = [c for c in df_loop.columns if c in df_vec.columns]
    ndiff = {}
    for c in cols:
        a, b = df_loop[c], df_vec[c]
        if pd.api.types.is_float_dtype(a) and pd.api.types.is_float_dtype(b):
            neq = ~np.isclose(a.values, b.values, rtol=0, atol=1e-9, equal_nan=True)
        else:
            neq = ~((a.values == b.values) | (pd.isna(a.values) & pd.isna(b.values)))
        n = int(neq.sum())
        if n:
            ndiff[c] = n
    if ndiff:
        print(f"  [{label}] DIFFERS: {ndiff}")
        return sum(ndiff.values())
    print(f"  [{label}] identical ({len(df_loop)} rows, {len(cols)} cols)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["single", "multileg"], default="single")
    ap.add_argument("--style", choices=["e2", "blended"], default="e2",
                    help="2-leg scale-in target style (multileg only)")
    ap.add_argument("--start", default="2021-06-18")
    ap.add_argument("--end", default="2022-06-19")
    args = ap.parse_args()

    sigs, tbd = _load_sigs(args.start, args.end)
    print(f"signals: {len(sigs)}  days: {len(tbd)}  mode: {args.mode}"
          + (f"  style: {args.style}" if args.mode == "multileg" else ""))

    cfg = dict(DEFAULTS)
    common = dict(entry_slip=cfg["entry_slip"], exit_slip=cfg["exit_slip"],
                  stop_offset=cfg["stop_offset"], tick_value=cfg["tick_value"],
                  commission=cfg["commission"])

    def run(force_loop, dest, rr, lock):
        if args.mode == "multileg":
            return simulate_trades(
                sigs, tbd, cfg["target_r"], **common,
                contracts=cfg["contracts_t1"] + cfg["contracts_t2"], multileg=True,
                t1_r=cfg["t1_r"], t1_action="exit",
                contracts_t1=cfg["contracts_t1"], contracts_t2=cfg["contracts_t2"],
                ml_pb_r=cfg["ml_pb_r"], scale_in_style=args.style,
                ratchet_r=rr, ratchet_dest=dest, ratchet_lock_r=lock,
                _force_loop=force_loop,
            )
        return simulate_trades(
            sigs, tbd, cfg["target_r"], **common, contracts=cfg["contracts_t1"],
            ratchet_r=rr, ratchet_dest=dest, ratchet_lock_r=lock,
            _force_loop=force_loop,
        )

    total = 0
    for dest, rr, lock in RATCHET_GRID:
        label = f"{dest} r={rr:.2f}" + (f" lock={lock:.2f}" if dest == "Lock-in" else "")
        loop = run(True, dest, rr, lock)
        vec = run(False, dest, rr, lock)
        total += _cmp(loop, vec, label)

    print("=" * 60)
    if total == 0:
        print(f"IDENTICAL — vectorized == loop on all {len(RATCHET_GRID)} ratchet settings")
        sys.exit(0)
    print(f"{total} differences")
    sys.exit(1)


if __name__ == "__main__":
    main()
