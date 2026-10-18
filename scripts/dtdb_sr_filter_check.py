"""dtdb_sr_filter_check.py — restrict the CVD/VR divergence outcome check to DT/DB
instances that form AT an established level (prior-day HOY/LOY/COY, OoD/OoW/OoM opens,
prior-day settlement, prior-day POC/VAH/VAL) instead of every confirmed instance
anywhere. SR levels computed directly from the L1 tape (same price source as the
DT/DB detection + CVD/VR scoring, avoids any back-adjusted-continuous-vs-raw-contract
price mismatch with tickdata.py's canonical trove). POC/VA reuse the validated
value_area()/volume_at_price() algorithm from volume_profile.py.

    python scripts/dtdb_sr_filter_check.py --tolerance-pts 3
    python scripts/dtdb_sr_filter_check.py --tolerance-pts 3 --score vr
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
from volume_profile import volume_at_price, value_area
from dtdb_cvd_backtest import build_tick_bars, find_confirmed, all_dates, SWING_STRENGTH, CVD_PERIOD, CVD_MODE, cvd_hist
from dtdb_cvd_outcome_check import forward_outcome
from dtdb_vr_outcome_check import vr_hist

OUT = L1_DIR / "_analysis"


def session_levels(day: str, prev_day: str | None, week_open_day: str | None, month_open_day: str | None) -> dict:
    """HOY/LOY/COY (prior RTH H/L/C), OoD/OoW/OoM (RTH opens), Settlement (prior full-
    session close), POC/VAH/VAL (prior day's RTH volume profile). Missing inputs (first
    day of the dataset, no clean week/month anchor yet) just drop that level, not a crash."""
    levels: dict[str, float] = {}

    today_df = load_day(day)
    today_rth = rth_only(today_df, day)
    today_trades = today_rth[today_rth["Ev"] == "T"].sort_values("Time")
    if not today_trades.empty:
        levels["OoD"] = float(today_trades["Price"].iloc[0])

    if prev_day:
        try:
            prev_df = load_day(prev_day)
            prev_rth = rth_only(prev_df, prev_day)
            prev_trades = prev_rth[prev_rth["Ev"] == "T"].sort_values("Time")
            if not prev_trades.empty:
                levels["HOY"] = float(prev_trades["Price"].max())
                levels["LOY"] = float(prev_trades["Price"].min())
                levels["COY"] = float(prev_trades["Price"].iloc[-1])
                levels["Settlement"] = float(prev_df.sort_values("Time")["Price"].iloc[-1])  # full-session (ETH) close

                vap = volume_at_price(prev_trades.rename(columns={"Size": "Volume"}))
                if len(vap) >= 3:
                    poc, va_lo, va_hi = value_area(vap)
                    levels["POC"] = poc
                    levels["VAL"] = va_lo
                    levels["VAH"] = va_hi
        except SystemExit:
            pass

    for label, anchor_day in [("OoW", week_open_day), ("OoM", month_open_day)]:
        if anchor_day and anchor_day != day:
            try:
                a_df = load_day(anchor_day)
                a_rth = rth_only(a_df, anchor_day)
                a_trades = a_rth[a_rth["Ev"] == "T"].sort_values("Time")
                if not a_trades.empty:
                    levels[label] = float(a_trades["Price"].iloc[0])
            except SystemExit:
                pass
        elif anchor_day == day and "OoD" in levels:
            levels[label] = levels["OoD"]

    return levels


def near_any_level(price: float, levels: dict, tol: float) -> tuple[bool, str]:
    hits = [name for name, lvl in levels.items() if abs(price - lvl) <= tol]
    return (len(hits) > 0, ",".join(hits))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--tolerance-pts", type=float, default=3.0, help="max distance from P2 to a level to count as 'at' it")
    ap.add_argument("--score", choices=["cvd", "vr"], default="vr")
    ap.add_argument("--vr-length", type=int, default=14)
    ap.add_argument("--vr-ma", default="exponential")
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--confirm-pts", type=float, default=3.0)
    a = ap.parse_args()

    dates = all_dates()
    date_week = pd.Series(pd.to_datetime(dates)).dt.isocalendar().week.tolist()
    date_month = pd.Series(pd.to_datetime(dates)).dt.month.tolist()

    rows = []
    for idx, d in enumerate(dates):
        prev_day = dates[idx - 1] if idx > 0 else None
        week_open = next((dates[j] for j in range(len(dates)) if date_week[j] == date_week[idx]
                           and pd.to_datetime(dates[j]).year == pd.to_datetime(d).year), None)
        month_open = next((dates[j] for j in range(len(dates)) if date_month[j] == date_month[idx]
                            and pd.to_datetime(dates[j]).year == pd.to_datetime(d).year), None)
        try:
            levels = session_levels(d, prev_day, week_open, month_open)
            df = load_day(d)
            rth = rth_only(df, d)
            bars = build_tick_bars(rth, a.ticks)
        except SystemExit as e:
            print(f"  {d}: skipped ({e})")
            continue
        if len(bars) < 2 * SWING_STRENGTH + 10 or not levels:
            continue

        insts = find_confirmed(bars, d)
        hist = cvd_hist(bars, CVD_PERIOD, CVD_MODE) if a.score == "cvd" else None
        vr = vr_hist(bars, a.vr_length, a.vr_ma) if a.score == "vr" else None

        for x in insts:
            is_top = x.kind == "DT"
            near, which = near_any_level(x.p2_price, levels, a.tolerance_pts)
            if a.score == "cvd":
                agrees = x.agrees
            else:
                v1, v2 = vr[x.p1_bar], vr[x.p2_bar]
                agrees = bool((v2 < v1) if is_top else (v2 > v1))
            outcome = forward_outcome(bars, x.confirm_bar, is_top, a.horizon, a.confirm_pts)
            rows.append(dict(day=d, kind=x.kind, p2_price=x.p2_price, near_sr=near, near_which=which,
                              agrees=agrees, outcome=outcome))
        print(f"  {d}: {len(bars)} bars, {len(insts)} confirmed DT/DB, {len(levels)} levels ({list(levels)})")

    if not rows:
        print("no instances")
        return 1

    ev = pd.DataFrame(rows)
    csv_out = OUT / f"dtdb_sr_filter_{a.score}_{dates[0]}_{dates[-1]}.csv"
    ev.to_csv(csv_out, index=False)

    def report(label: str, sub: pd.DataFrame):
        n = len(sub)
        if n == 0:
            print(f"{label:>26}: 0 instances")
            return
        cont = (sub["outcome"] == "continued").sum()
        rev = (sub["outcome"] == "reversed").sum()
        print(f"{label:>26}: {n:>4}  continued {cont:>4} ({100*cont/n:5.1f}%)  reversed {rev:>4} ({100*rev/n:5.1f}%)")

    print(f"\n=== {len(ev)} confirmed DT/DB, {a.score.upper()} scoring, tolerance={a.tolerance_pts}pt, "
          f"{dates[0]} -> {dates[-1]} ===")
    print(f"near-SR instances: {ev['near_sr'].sum()}/{len(ev)} ({100*ev['near_sr'].sum()/len(ev):.1f}%)\n")

    report("ALL", ev)
    report("near SR (any level)", ev[ev["near_sr"]])
    report("away from SR", ev[~ev["near_sr"]])
    print()
    near = ev[ev["near_sr"]]
    report("near SR - agrees", near[near["agrees"] == True])
    report("near SR - disagrees", near[near["agrees"] == False])
    away = ev[~ev["near_sr"]]
    report("away - agrees", away[away["agrees"] == True])
    report("away - disagrees", away[away["agrees"] == False])

    print(f"\nsaved: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
