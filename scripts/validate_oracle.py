"""
Layer B (scoped) — independent oracle for exit sequencing.

Re-derives each trade's outcome from the documented 2-leg / single-leg spec using
a numpy first-hit-index method — a deliberately different mechanism from the
engine's sequential break-loop. Runs on a stratified sample (N per exit reason)
and diffs ExitReason / ExitPrice / GrossPnL / E2 fill against simulate_trades().

The point is to catch sequencing / priority / off-by-one / comparator-direction
bugs that Layer A's internal-consistency checks cannot see.

Usage:
    .venv\\Scripts\\python scripts\\validate_oracle.py --mode multileg --per-reason 80
    .venv\\Scripts\\python scripts\\validate_oracle.py --mode single
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

from simulation_engine import simulate_trades, TICK_SIZE  # noqa: E402
from validate_engine import _load_ticks, _round_tick, DEFAULTS, SIGNALS_PARQUET  # noqa: E402

TS = TICK_SIZE


def _first(mask: np.ndarray):
    nz = np.flatnonzero(mask)
    return int(nz[0]) if len(nz) else None


def oracle_single(after: pd.DataFrame, is_long: bool, cfg: dict, stop_csv: float):
    """Independent single-leg outcome from raw ticks."""
    ts = TS
    es, xs, so = cfg["entry_slip"], cfg["exit_slip"], cfg["stop_offset"]
    tv = cfg["tick_value"] * cfg["contracts_t1"]
    sgn = 1.0 if is_long else -1.0

    px = after["Price"].values.astype(float)
    entry = float(px[0]) + sgn * es * ts
    stop = stop_csv - sgn * so * ts
    risk = abs(entry - stop)
    target = entry + sgn * cfg["target_r"] * risk

    elig = np.arange(len(px)) >= 1
    stop_m = ((px <= stop) if is_long else (px >= stop)) & elig
    tgt_m = ((px > target) if is_long else (px < target)) & elig
    si, ti = _first(stop_m), _first(tgt_m)

    if si is None and ti is None:
        exit_px = float(px[-1]) - sgn * xs * ts
        reason = "EOD"
    elif ti is not None and (si is None or ti < si):
        exit_px = target - sgn * xs * ts
        reason = "Target"
    else:
        exit_px = stop - sgn * xs * ts
        reason = "Stop"

    gross_pts = (exit_px - entry) if is_long else (entry - exit_px)
    return {"ExitReason": reason, "ExitPrice": exit_px, "GrossPnL": gross_pts / ts * tv,
            "EntryPrice": entry, "E2FillPrice": np.nan}


def oracle_multileg(after: pd.DataFrame, is_long: bool, cfg: dict, stop_csv: float):
    """Independent 2-leg PB scale-in outcome from raw ticks."""
    ts = TS
    es, xs, so = cfg["entry_slip"], cfg["exit_slip"], cfg["stop_offset"]
    tv1 = cfg["tick_value"] * cfg["contracts_t1"]
    tv2 = cfg["tick_value"] * cfg["contracts_t2"]
    tv_tot = tv1 + tv2
    sgn = 1.0 if is_long else -1.0
    pb_r, t1_r, t2_r = cfg["ml_pb_r"], cfg["t1_r"], cfg["target_r"]

    px = after["Price"].values.astype(float)
    n = len(px)
    entry = float(px[0]) + sgn * es * ts
    stop = stop_csv - sgn * so * ts
    risk = abs(entry - stop)
    t1 = entry + sgn * t1_r * risk

    pb_level_raw = entry + sgn * pb_r * risk           # pb_r is negative
    pb_trigger = round(float(np.floor(pb_level_raw / ts) if is_long else np.ceil(pb_level_raw / ts)) * ts, 10)

    elig = np.arange(n) >= 1
    pb_m = ((px < pb_trigger) if is_long else (px > pb_trigger)) & elig
    stop_m = ((px <= stop) if is_long else (px >= stop)) & elig
    t1_m = ((px > t1) if is_long else (px < t1)) & elig

    pb_i = _first(pb_m)

    def _leg1(exit_px):
        return ((exit_px - entry) if is_long else (entry - exit_px)) / ts * tv1

    # ── No scale-in ever ──
    if pb_i is None:
        si, ti = _first(stop_m), _first(t1_m)
        if si is None and ti is None:
            exit_px = float(px[-1]) - sgn * xs * ts
            return {"ExitReason": "EOD", "ExitPrice": exit_px, "GrossPnL": _leg1(exit_px),
                    "EntryPrice": entry, "E2FillPrice": np.nan}
        if ti is not None and (si is None or ti < si):
            exit_px = t1 - sgn * xs * ts
            return {"ExitReason": "T1_only", "ExitPrice": exit_px, "GrossPnL": _leg1(exit_px),
                    "EntryPrice": entry, "E2FillPrice": np.nan}
        exit_px = stop - sgn * xs * ts
        return {"ExitReason": "Stop", "ExitPrice": exit_px, "GrossPnL": _leg1(exit_px),
                "EntryPrice": entry, "E2FillPrice": np.nan}

    # ── Pre-PB: only T1 can fire before pb_i (stop is deeper than pb_trigger,
    #    so any sub-stop tick is also a PB tick) ──
    t1_pre = _first(t1_m & (np.arange(n) < pb_i))
    if t1_pre is not None:
        exit_px = t1 - sgn * xs * ts
        return {"ExitReason": "T1_only", "ExitPrice": exit_px, "GrossPnL": _leg1(exit_px),
                "EntryPrice": entry, "E2FillPrice": np.nan}

    # ── PB fills at pb_i ──
    e2 = _round_tick(pb_trigger + sgn * es * ts)
    blended = (entry * tv1 + e2 * tv2) / tv_tot
    b_risk = abs(blended - stop)
    t2 = _round_tick(blended + sgn * t2_r * b_risk)

    post = np.arange(n) > pb_i
    stop_post = _first(stop_m & post)
    t2_m = ((px > t2) if is_long else (px < t2)) & elig
    t2_post = _first(t2_m & post)

    def _both(exit_px):
        l1 = ((exit_px - entry) if is_long else (entry - exit_px)) / ts * tv1
        l2 = ((exit_px - e2) if is_long else (e2 - exit_px)) / ts * tv2
        return l1 + l2

    if stop_post is None and t2_post is None:
        exit_px = float(px[-1]) - sgn * xs * ts
        return {"ExitReason": "E1E2+EOD", "ExitPrice": exit_px, "GrossPnL": _both(exit_px),
                "EntryPrice": entry, "E2FillPrice": e2}
    if t2_post is not None and (stop_post is None or t2_post < stop_post):
        exit_px = t2 - sgn * xs * ts
        return {"ExitReason": "E1E2+Target", "ExitPrice": exit_px, "GrossPnL": _both(exit_px),
                "EntryPrice": entry, "E2FillPrice": e2}
    exit_px = stop - sgn * xs * ts
    return {"ExitReason": "Stop", "ExitPrice": exit_px, "GrossPnL": _both(exit_px),
            "EntryPrice": entry, "E2FillPrice": e2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["multileg", "single"], default="multileg")
    ap.add_argument("--start", default="2021-06-18")
    ap.add_argument("--end", default="2022-06-18")
    ap.add_argument("--per-reason", type=int, default=80, help="max sampled trades per exit reason")
    ap.add_argument("--max-examples", type=int, default=8)
    args = ap.parse_args()

    cfg = dict(DEFAULTS)
    common = dict(entry_slip=cfg["entry_slip"], exit_slip=cfg["exit_slip"], stop_offset=cfg["stop_offset"],
                  tick_value=cfg["tick_value"], commission=cfg["commission"])
    oracle = oracle_multileg if args.mode == "multileg" else oracle_single

    all_sigs = pd.read_parquet(SIGNALS_PARQUET)
    all_sigs["DateTime"] = pd.to_datetime(all_sigs["DateTime"])
    if "Date" not in all_sigs.columns:
        all_sigs["Date"] = all_sigs["DateTime"].dt.date

    fields = ["ExitReason", "ExitPrice", "GrossPnL", "E2FillPrice"]
    stats = {f: {"match": 0, "mismatch": 0, "examples": []} for f in fields}
    reason_counts: dict = {}
    n_filled = 0

    # Process in yearly chunks so a year's tick cache fits in memory (full-history
    # all-at-once is ~444M ticks → MemoryError; the app loads per-day for the same reason).
    range_start = pd.Timestamp(args.start)
    range_end = pd.Timestamp(args.end)
    win_start = range_start
    while win_start <= range_end:
        win_end = min(win_start + pd.DateOffset(years=1) - pd.Timedelta(days=1), range_end)
        sigs = all_sigs[(all_sigs["DateTime"] >= win_start) &
                        (all_sigs["DateTime"] <= win_end + pd.Timedelta(days=1))]
        if sigs.empty:
            win_start = win_end + pd.Timedelta(days=1)
            continue

        ticks_by_date = {}
        for d in sorted(sigs["Date"].unique()):
            t = _load_ticks(d)
            if not t.empty:
                ticks_by_date[d] = t
        sigs = sigs[sigs["Date"].isin(ticks_by_date.keys())].copy()
        if sigs.empty:
            win_start = win_end + pd.Timedelta(days=1)
            continue

        if args.mode == "multileg":
            results = simulate_trades(sigs, ticks_by_date, cfg["target_r"], **common,
                                      contracts=cfg["contracts_t1"] + cfg["contracts_t2"],
                                      multileg=True, t1_r=cfg["t1_r"], t1_action="exit",
                                      contracts_t1=cfg["contracts_t1"], contracts_t2=cfg["contracts_t2"],
                                      ml_pb_r=cfg["ml_pb_r"])
        else:
            results = simulate_trades(sigs, ticks_by_date, cfg["target_r"], **common, contracts=cfg["contracts_t1"])

        filled = results[results["Filled"] == True]
        sample = pd.concat([g.head(args.per_reason) for _, g in filled.groupby("ExitReason", sort=False)],
                           ignore_index=True) if len(filled) else filled
        n_filled += len(filled)
        for rs, c in sample["ExitReason"].value_counts().items():
            reason_counts[rs] = reason_counts.get(rs, 0) + int(c)

        for _, r in sample.iterrows():
            is_long = r["Direction"] == "Long"
            after = ticks_by_date[r["Date"]]
            after = after[after["DateTime"] > pd.Timestamp(r["DateTime"])]
            if after.empty:
                continue
            o = oracle(after, is_long, cfg, float(r["StopPrice"]))
            sn = r.get("SignalNum", "?")
            for f in fields:
                ev, ov = r.get(f), o.get(f)
                ev_nan = isinstance(ev, float) and np.isnan(ev)
                ov_nan = isinstance(ov, float) and np.isnan(ov)
                if f == "ExitReason":
                    ok = str(ev) == str(ov)
                elif ev_nan or ov_nan:
                    ok = ev_nan and ov_nan
                else:
                    tol = 0.01 if f == "GrossPnL" else 1e-6
                    ok = abs(float(ev) - float(ov)) <= tol
                if ok:
                    stats[f]["match"] += 1
                else:
                    stats[f]["mismatch"] += 1
                    if len(stats[f]["examples"]) < args.max_examples:
                        stats[f]["examples"].append(f"    #{sn} {r['Direction']} {r['Date']}: engine={ev}  oracle={ov}")

        del ticks_by_date, results, filled, sample
        win_start = win_end + pd.Timedelta(days=1)

    print(f"Mode: {args.mode}  |  range {args.start}..{args.end}  |  filled checked: {n_filled}")
    print("Per reason:", reason_counts, "\n")

    print("=" * 66)
    print(f"{'FIELD':<16}{'MATCH':>8}{'MISMATCH':>10}")
    print("-" * 66)
    total_mm = 0
    for f in fields:
        total_mm += stats[f]["mismatch"]
        flag = "  <-- MISMATCH" if stats[f]["mismatch"] else ""
        print(f"{f:<16}{stats[f]['match']:>8}{stats[f]['mismatch']:>10}{flag}")
    print("=" * 66)

    if total_mm:
        print("\nMismatch examples:\n")
        for f in fields:
            if stats[f]["mismatch"]:
                print(f"[{f}]  ({stats[f]['mismatch']} total)")
                for ex in stats[f]["examples"]:
                    print(ex)
                print()
        sys.exit(1)
    print("\nOracle agrees with the engine on every sampled trade.")


if __name__ == "__main__":
    main()
