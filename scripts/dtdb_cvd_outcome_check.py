"""dtdb_cvd_outcome_check.py — the real test dtdb_cvd_backtest.py never ran: does
"CVD agrees" at a confirmed DT/DB actually precede a better forward outcome than "CVD
disagrees"? Single-instance chart deep-dives (dtdb_ibs_inspect.py) can't answer this --
only a forward-outcome frequency check across many instances can, same method
order_flow_turning_points.py (S142) used to correctly catch that a DIFFERENT order-flow
signal had no edge. NOT a backtest (no entries/fills/costs) -- a frequency check of
whether CVD-agrees precedes continuation more often than CVD-disagrees or a flat
baseline.

    python scripts/dtdb_cvd_outcome_check.py --horizon 20 --confirm-pts 3
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from dtdb_cvd_backtest import build_bars, find_confirmed, all_dates, SWING_STRENGTH

OUT = L1_DIR / "_analysis"


def forward_outcome(bars: pd.DataFrame, confirm_bar: int, is_top: bool, horizon: int, confirm_pts: float) -> str:
    """First-touch outcome from the confirm bar's close: did price move >= confirm_pts
    in the CONTINUATION direction (down for DT, up for DB) before moving that far in the
    REVERSAL direction? Same ambiguous/ bug-fixed logic as order_flow_turning_points.py."""
    n = len(bars)
    piv = bars["close"].iat[confirm_bar]
    for j in range(confirm_bar + 1, min(n, confirm_bar + 1 + horizon)):
        if is_top:
            hit_cont = bars["low"].iat[j] <= piv - confirm_pts
            hit_rev = bars["high"].iat[j] >= piv + confirm_pts
        else:
            hit_cont = bars["high"].iat[j] >= piv + confirm_pts
            hit_rev = bars["low"].iat[j] <= piv - confirm_pts
        if hit_cont and hit_rev:
            return "ambiguous"
        if hit_cont:
            return "continued"
        if hit_rev:
            return "reversed"
    return "neither"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--minutes", type=int, default=None, help="use N-minute time bars instead of tick bars")
    ap.add_argument("--renko", type=int, nargs=3, default=None, metavar=("BOX", "TREND", "REV"),
                     help="use Flex Renko bricks instead of tick/time bars, e.g. --renko 16 8 4")
    ap.add_argument("--horizon", type=int, default=20, help="bars forward to check for the outcome")
    ap.add_argument("--confirm-pts", type=float, default=3.0, help="points of move to call continued/reversed")
    ap.add_argument("--day", default=None, help="single day; default = every L1 day on disk")
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
        insts = find_confirmed(bars, d)
        for x in insts:
            is_top = x.kind == "DT"
            outcome = forward_outcome(bars, x.confirm_bar, is_top, a.horizon, a.confirm_pts)
            rows.append(dict(day=d, kind=x.kind, confirm_bar=x.confirm_bar, agrees=x.agrees,
                              cvd_delta=x.cvd2 - x.cvd1, outcome=outcome))
        print(f"  {d}: {len(bars)} bars, {len(insts)} confirmed DT/DB")

    if not rows:
        print("no confirmed instances across any day")
        return 1

    ev = pd.DataFrame(rows)
    csv_out = OUT / f"dtdb_cvd_outcome_{bar_label}_{dates[0]}_{dates[-1]}.csv"
    ev.to_csv(csv_out, index=False)

    print(f"\n=== {len(ev)} confirmed DT/DB across {len(dates)} days ({dates[0]} -> {dates[-1]}) ===")
    print(f"outcome = first-touch {a.confirm_pts}pt move within {a.horizon} bars of confirm\n")

    def report(label: str, sub: pd.DataFrame):
        n = len(sub)
        if n == 0:
            print(f"{label:>14}: 0 instances")
            return
        cont = (sub["outcome"] == "continued").sum()
        rev = (sub["outcome"] == "reversed").sum()
        neith = (sub["outcome"] == "neither").sum()
        amb = (sub["outcome"] == "ambiguous").sum()
        print(f"{label:>14}: {n:>4}  continued {cont:>4} ({100*cont/n:5.1f}%)  "
              f"reversed {rev:>4} ({100*rev/n:5.1f}%)  neither {neith:>4} ({100*neith/n:5.1f}%)  "
              f"ambiguous {amb:>4} ({100*amb/n:5.1f}%)")

    report("ALL (baseline)", ev)
    report("CVD agrees", ev[ev["agrees"] == True])
    report("CVD disagrees", ev[ev["agrees"] == False])
    print()
    report("DT only - agrees", ev[(ev["kind"] == "DT") & (ev["agrees"] == True)])
    report("DT only - disagrees", ev[(ev["kind"] == "DT") & (ev["agrees"] == False)])
    report("DB only - agrees", ev[(ev["kind"] == "DB") & (ev["agrees"] == True)])
    report("DB only - disagrees", ev[(ev["kind"] == "DB") & (ev["agrees"] == False)])

    print(f"\nsaved: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
