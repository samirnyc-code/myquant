"""dtdb_ibs_inspect.py — inspect the bar-by-bar detail (incl. IBS = Internal Bar
Strength = (Close-Low)/(High-Low)) around one confirmed DT/DB instance, pulling the
instance's own row (p1/p2/confirm/retest bars + CVD divergence numbers) straight from
a dtdb_cvd_backtest.py CSV so nothing is hand-retyped. Marks P1, P2, the NECKLINE BREAK
bar (= the confirm bar -- confirmation IS the neckline break, same bar, same thing),
and the RETEST bar (if one was found) directly in the printed table. Saves a dated CSV.

Look up an instance by day + p1_bar (unique per day in practice):
    python scripts/dtdb_ibs_inspect.py --day 2026-10-13 --p1-bar 675 --window 15
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR
from dtdb_cvd_backtest import (build_tick_bars, cvd_hist, CVD_PERIOD, CVD_MODE,
                                neckline_low, neckline_high, RETEST_TOLERANCE_TICKS, TICK)

OUT = L1_DIR / "_analysis"


def find_row(day: str, p1_bar: int) -> pd.Series:
    import glob
    hits = sorted(glob.glob(str(OUT / f"dtdb_cvd_backtest_*.csv")))
    for f in hits:
        df = pd.read_csv(f)
        m = df[(df["day"] == day) & (df["p1_bar"] == p1_bar)]
        if not m.empty:
            return m.iloc[0]
    raise SystemExit(f"no instance found for day={day} p1_bar={p1_bar} in {hits} -- run dtdb_cvd_backtest.py first")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--p1-bar", type=int, required=True)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--window", type=int, default=15, help="bars of context before p1 and after the retest/confirm")
    a = ap.parse_args()

    row = find_row(a.day, a.p1_bar)
    p1_bar, p2_bar, confirm_bar = int(row.p1_bar), int(row.p2_bar), int(row.confirm_bar)
    retest_bar = None if pd.isna(row.retest_bar) else int(row.retest_bar)

    df = load_day(a.day)
    rth = rth_only(df, a.day)
    bars = build_tick_bars(rth, a.ticks)
    hist = cvd_hist(bars, CVD_PERIOD, CVD_MODE)
    is_top = row.kind == "DT"
    neck = neckline_low(bars, p1_bar, p2_bar) if is_top else neckline_high(bars, p1_bar, p2_bar)
    neck_price = neck[1] if neck else float("nan")
    tol_rt = RETEST_TOLERANCE_TICKS * TICK

    print(f"=== {row.kind}  day={a.day}  P1@{p1_bar}={row.p1_price}  P2@{p2_bar}={row.p2_price}  "
          f"NECKLINE={neck_price:.2f} (bar {neck[0] if neck else '?'}) ===")
    print(f"CVD at P1={row.cvd1:.0f}  CVD at P2={row.cvd2:.0f}  delta={row.cvd_delta:+.0f}  "
          f"agrees={'YES' if row.agrees else 'NO'}")
    if retest_bar is not None:
        band = (f"Low<={neck_price+tol_rt:.2f} & Close>={neck_price:.2f}" if not is_top
                else f"High>={neck_price-tol_rt:.2f} & Close<={neck_price:.2f}")
        print(f"RETEST found at bar {retest_bar} ({retest_bar - confirm_bar} bars after neckline break)  "
              f"CVD delta since break={row.retest_cvd_delta:+.0f}  (retest band: {band})")
    else:
        print(f"no retest found within the watch window")
    print()

    lo = max(0, p1_bar - a.window)
    hi_anchor = retest_bar if retest_bar is not None else confirm_bar
    hi = min(len(bars) - 1, hi_anchor + a.window)
    w = bars.iloc[lo:hi + 1].copy()
    w["bar"] = w.index
    w["delta"] = w["askVol"] - w["bidVol"]
    w["cvd_hist"] = hist[lo:hi + 1]
    rng = (w["high"] - w["low"]).replace(0, pd.NA)
    w["ibs"] = ((w["close"] - w["low"]) / rng).astype(float)
    w["role"] = ""
    roles = [(p1_bar, "<<< P1 (trough 1)"),
             (p2_bar, "<<< P2 (trough 2)"),
             (confirm_bar, "<<< NECKLINE BREAK (confirm)")]
    if retest_bar is not None:
        roles.append((retest_bar, "<<< RETEST"))
    for b, label in roles:
        w.loc[w["bar"] == b, "role"] = label

    cols = ["bar", "t", "open", "high", "low", "close", "ibs", "askVol", "bidVol", "delta", "cvd_hist", "role"]
    out = w[cols].round({"ibs": 2})
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 200)
    print(out.to_string(index=False))

    price_at_confirm = bars["close"].iat[confirm_bar]
    price_20later = bars["close"].iat[min(len(bars) - 1, confirm_bar + 20)]
    price_50later = bars["close"].iat[min(len(bars) - 1, confirm_bar + 50)]
    print(f"\nclose@neckline-break={price_at_confirm:.2f}  +20bars={price_20later:.2f} ({price_20later-price_at_confirm:+.2f})"
          f"  +50bars={price_50later:.2f} ({price_50later-price_at_confirm:+.2f})")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_out = OUT / f"dtdb_ibs_inspect_{a.day}_{p1_bar}_{p2_bar}_{stamp}.csv"
    out.to_csv(csv_out, index=False)
    print(f"\nsaved: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
