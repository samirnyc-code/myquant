"""dtdb_horizon_sweep.py — is the null result a timeframe problem? Every prior test
used ONE forward-outcome horizon (20 bars) and ONE threshold (3pt). If CVD/VR
divergence predicts something, it might show up at a different horizon -- a fast
scalp horizon (does it resolve in the next few bars) or a slower one (does it take
longer to play out) -- and a single arbitrary choice could have missed it entirely.

Sweeps horizon x confirm-pts for BOTH scoring methods (CVD rolling-sum, VR Sierra
ratio) on 2000-tick bars (the largest sample, n=1096), reports the full grid so
nothing is cherry-picked -- same discipline as every other check in this series.

    python scripts/dtdb_horizon_sweep.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from dtdb_cvd_backtest import build_tick_bars, find_confirmed, all_dates, SWING_STRENGTH, CVD_PERIOD, CVD_MODE, cvd_hist
from dtdb_cvd_outcome_check import forward_outcome
from dtdb_vr_outcome_check import vr_hist

OUT = L1_DIR / "_analysis"

HORIZONS = [5, 10, 20, 40, 80]
CONFIRM_PTS = [1.0, 2.0, 3.0, 5.0, 8.0]


def main() -> int:
    dates = all_dates()
    instances = []   # (day, kind, p1_bar, p2_bar, confirm_bar, cvd_agrees, vr_agrees) + bars per day cached
    bars_by_day = {}
    hist_by_day = {}
    vr_by_day = {}

    for d in dates:
        try:
            df = load_day(d)
            rth = rth_only(df, d)
            bars = build_tick_bars(rth, 2000)
        except SystemExit as e:
            print(f"  {d}: skipped ({e})")
            continue
        if len(bars) < 2 * SWING_STRENGTH + 10:
            continue
        insts = find_confirmed(bars, d)
        hist = cvd_hist(bars, CVD_PERIOD, CVD_MODE)
        vr = vr_hist(bars, 14, "exponential")
        bars_by_day[d] = bars
        hist_by_day[d] = hist
        vr_by_day[d] = vr
        for x in insts:
            instances.append((d, x.kind, x.p1_bar, x.p2_bar, x.confirm_bar, x.agrees))
        print(f"  {d}: {len(bars)} bars, {len(insts)} confirmed DT/DB")

    print(f"\n{len(instances)} confirmed DT/DB total across {len(bars_by_day)} days\n")

    rows = []
    for horizon in HORIZONS:
        for cpts in CONFIRM_PTS:
            for score_name in ["cvd", "vr"]:
                cont_a = cont_d = rev_a = rev_d = n_a = n_d = 0
                for (d, kind, p1b, p2b, cbar, cvd_agrees) in instances:
                    bars = bars_by_day[d]
                    is_top = kind == "DT"
                    if score_name == "cvd":
                        agrees = cvd_agrees
                    else:
                        vr = vr_by_day[d]
                        v1, v2 = vr[p1b], vr[p2b]
                        agrees = bool((v2 < v1) if is_top else (v2 > v1))
                    outcome = forward_outcome(bars, cbar, is_top, horizon, cpts)
                    if agrees:
                        n_a += 1
                        cont_a += outcome == "continued"
                        rev_a += outcome == "reversed"
                    else:
                        n_d += 1
                        cont_d += outcome == "continued"
                        rev_d += outcome == "reversed"
                cont_a_pct = 100 * cont_a / n_a if n_a else float("nan")
                cont_d_pct = 100 * cont_d / n_d if n_d else float("nan")
                rows.append(dict(score=score_name, horizon=horizon, confirm_pts=cpts,
                                  n_agree=n_a, n_disagree=n_d,
                                  cont_agree=cont_a_pct, cont_disagree=cont_d_pct,
                                  cont_gap=cont_a_pct - cont_d_pct))

    sweep = pd.DataFrame(rows)
    csv_out = OUT / f"dtdb_horizon_sweep_{dates[0]}_{dates[-1]}.csv"
    sweep.to_csv(csv_out, index=False)

    pd.set_option("display.width", 160)
    for score_name in ["cvd", "vr"]:
        print(f"=== {score_name.upper()} scoring: continuation-rate gap (agree% - disagree%) by horizon x confirm_pts ===")
        sub = sweep[sweep["score"] == score_name]
        pivot = sub.pivot(index="horizon", columns="confirm_pts", values="cont_gap")
        print(pivot.round(1).to_string())
        print()

    max_row = sweep.loc[sweep["cont_gap"].abs().idxmax()]
    print(f"largest |gap| across the whole sweep: {max_row['score'].upper()} horizon={max_row['horizon']} "
          f"confirm_pts={max_row['confirm_pts']}  gap={max_row['cont_gap']:+.1f}pt  "
          f"(n_agree={max_row['n_agree']:.0f}, n_disagree={max_row['n_disagree']:.0f})")
    print(f"\nsaved: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
