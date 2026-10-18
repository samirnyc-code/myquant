"""dtdb_vr_outcome_check.py — same forward-outcome test as dtdb_cvd_outcome_check.py,
but scoring divergence with Sierra Chart's actual "Bid Ask Volume Ratio" formula
(bounded, normalized, EMA-smoothed -- scripts/bid_ask_volume_ratio_l1.py /
nt8/indicators/BidAskVolumeRatio.cs) instead of a raw rolling-sum CVD. Requested after
the CVD test (unbounded rolling sum) came back null three ways -- fair challenge: that's
one specific construction, not "CVD" in general, and it's not what the ratio-based
tooling we already built and validated computes.

DT/DB structure detection is UNCHANGED (same find_confirmed as dtdb_cvd_backtest.py) --
only the divergence SCORING at the two pivots changes: VR2 vs VR1 (normalized ratio,
EMA-smoothed) instead of CVD2 vs CVD1 (raw rolling sum).

    python scripts/dtdb_vr_outcome_check.py --vr-length 14 --vr-ma exponential
    python scripts/dtdb_vr_outcome_check.py --minutes 5 --vr-length 14
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from bid_ask_volume_ratio_l1 import smooth
from dtdb_cvd_backtest import build_bars, find_confirmed, all_dates, SWING_STRENGTH
from dtdb_cvd_outcome_check import forward_outcome

OUT = L1_DIR / "_analysis"


def vr_hist(bars: pd.DataFrame, length: int, ma: str) -> np.ndarray:
    denom = bars["askVol"] + bars["bidVol"]
    raw = np.where(denom > 0, 100.0 * (bars["askVol"] - bars["bidVol"]) / denom, 0.0)
    return smooth(raw, length, ma)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--minutes", type=int, default=None)
    ap.add_argument("--renko", type=int, nargs=3, default=None, metavar=("BOX", "TREND", "REV"),
                     help="use Flex Renko bricks instead of tick/time bars, e.g. --renko 16 8 4")
    ap.add_argument("--vr-length", type=int, default=14)
    ap.add_argument("--vr-ma", default="exponential",
                     choices=["simple", "exponential", "weighted", "linreg", "wilders", "smoothed"])
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--confirm-pts", type=float, default=3.0)
    ap.add_argument("--day", default=None)
    a = ap.parse_args()
    renko = tuple(a.renko) if a.renko else None
    bar_label = f"renko{a.renko[0]}-{a.renko[1]}-{a.renko[2]}" if renko else (f"{a.minutes}min" if a.minutes else f"{a.ticks}tick")

    dates = [a.day] if a.day else all_dates()
    rows = []
    for d in dates:
        try:
            df = load_day(d)
            rth = rth_only(df, d)
            bars = build_bars(rth, a.ticks, a.minutes, renko)
        except SystemExit as e:
            print(f"  {d}: skipped ({e})")
            continue
        if len(bars) < 2 * SWING_STRENGTH + 10:
            continue
        insts = find_confirmed(bars, d)   # structure detection UNCHANGED
        vr = vr_hist(bars, a.vr_length, a.vr_ma)
        for x in insts:
            is_top = x.kind == "DT"
            vr1, vr2 = vr[x.p1_bar], vr[x.p2_bar]
            vr_agrees = bool((vr2 < vr1) if is_top else (vr2 > vr1))
            outcome = forward_outcome(bars, x.confirm_bar, is_top, a.horizon, a.confirm_pts)
            rows.append(dict(day=d, kind=x.kind, confirm_bar=x.confirm_bar,
                              vr1=vr1, vr2=vr2, vr_delta=vr2 - vr1, vr_agrees=vr_agrees,
                              cvd_agrees=x.agrees, outcome=outcome))
        print(f"  {d}: {len(bars)} bars, {len(insts)} confirmed DT/DB")

    if not rows:
        print("no confirmed instances")
        return 1

    ev = pd.DataFrame(rows)
    csv_out = OUT / f"dtdb_vr_outcome_{bar_label}_{dates[0]}_{dates[-1]}.csv"
    ev.to_csv(csv_out, index=False)

    print(f"\n=== {len(ev)} confirmed DT/DB, VR({a.vr_ma},{a.vr_length}) scoring, "
          f"{bar_label} bars, {dates[0]} -> {dates[-1]} ===")
    print(f"outcome = first-touch {a.confirm_pts}pt move within {a.horizon} bars of confirm\n")

    def report(label: str, sub: pd.DataFrame):
        n = len(sub)
        if n == 0:
            print(f"{label:>18}: 0 instances")
            return
        cont = (sub["outcome"] == "continued").sum()
        rev = (sub["outcome"] == "reversed").sum()
        print(f"{label:>18}: {n:>4}  continued {cont:>4} ({100*cont/n:5.1f}%)  "
              f"reversed {rev:>4} ({100*rev/n:5.1f}%)")

    report("ALL (baseline)", ev)
    report("VR agrees", ev[ev["vr_agrees"] == True])
    report("VR disagrees", ev[ev["vr_agrees"] == False])
    print()
    report("DT - VR agrees", ev[(ev["kind"] == "DT") & (ev["vr_agrees"] == True)])
    report("DT - VR disagrees", ev[(ev["kind"] == "DT") & (ev["vr_agrees"] == False)])
    report("DB - VR agrees", ev[(ev["kind"] == "DB") & (ev["vr_agrees"] == True)])
    report("DB - VR disagrees", ev[(ev["kind"] == "DB") & (ev["vr_agrees"] == False)])

    print(f"\nVR vs CVD agreement overlap: both agree {((ev['vr_agrees']) & (ev['cvd_agrees'])).sum()}, "
          f"both disagree {((~ev['vr_agrees']) & (~ev['cvd_agrees'])).sum()}, "
          f"split {(ev['vr_agrees'] != ev['cvd_agrees']).sum()}/{len(ev)}")
    print(f"saved: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
