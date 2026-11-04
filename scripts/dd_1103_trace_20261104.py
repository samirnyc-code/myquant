"""Trace exactly how 2026-11-03 got an EOD drawdown of -$5,949 -- user disputed
the peak-to-trough DD numbers, asked to see the derivation for that one day.

EOD dd(day) = cum(day) - peak(cum up to and including day), where cum is the
running sum of daily realized P&L (same bucketing as analytics_payload /
buildDaily() in options_dashboard.py: closed trades bucket on exit date).
This prints the peak day, every day's pnl/cum/dd from the peak through
2026-11-03, and every individual trade bucketed into 2026-11-03 so the day's
own -$363 can be checked against the raw trade log, not just trusted.

Usage: .venv/Scripts/python.exe scripts/dd_1103_trace_20261104.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import options_dashboard as dash
import options_trade_log as tlog


def main():
    raw = tlog.load()
    shown = dash._shown(raw)
    trades = pd.concat([shown, dash._recon_df()], ignore_index=True)

    rows = []
    for _, r in trades.iterrows():
        is_open = pd.isna(r.exit_dt)
        if is_open:
            continue   # pnl is None for open trades -> excluded from the dd series, same as JS
        pnl = float(r.pnl) if pd.notna(r.pnl) else None
        if pnl is None:
            continue
        entry = str(r.entry_dt) if pd.notna(r.entry_dt) else ""
        exitd = str(r.exit_dt) if pd.notna(r.exit_dt) else ""
        bucket_date = exitd[:10] if exitd else entry[:10]
        rows.append({"trade_id": r.trade_id, "strategy": r.strategy_id,
                      "entry_dt": entry, "exit_dt": exitd, "bucket_date": bucket_date, "pnl": pnl})
    df = pd.DataFrame(rows)

    by_day = df.groupby("bucket_date")["pnl"].sum().sort_index()
    days = by_day.index.tolist()

    cum, peak, peak_day = 0.0, 0.0, None
    series = []
    for d in days:
        cum += by_day[d]
        if cum >= peak:
            peak, peak_day = cum, d
        series.append({"d": d, "pnl": round(by_day[d], 2), "cum": round(cum, 2),
                        "peak_so_far": round(peak, 2), "peak_day": peak_day,
                        "dd": round(cum - peak, 2)})

    target = "2026-11-03"
    idx_target = next(i for i, s in enumerate(series) if s["d"] == target)
    idx_peak = next(i for i, s in enumerate(series) if s["d"] == series[idx_target]["peak_day"])

    print(f"peak cum reached on {series[idx_peak]['d']}: {series[idx_peak]['cum']:,.0f}")
    print(f"cum on {target}: {series[idx_target]['cum']:,.0f}")
    print(f"dd = {series[idx_target]['cum']:,.0f} - {series[idx_peak]['cum']:,.0f} "
          f"= {series[idx_target]['dd']:,.0f}\n")

    print(f"{'date':<12}{'day pnl':>10}{'cum':>10}{'peak-so-far':>13}{'dd':>10}")
    for s in series[idx_peak:idx_target + 1]:
        print(f"{s['d']:<12}{s['pnl']:>10,.0f}{s['cum']:>10,.0f}{s['peak_so_far']:>13,.0f}{s['dd']:>10,.0f}")

    print(f"\n--- every trade bucketed into {target} (sums to {by_day[target]:,.2f}) ---")
    day_trades = df[df.bucket_date == target].sort_values("exit_dt")
    print(day_trades[["trade_id", "strategy", "entry_dt", "exit_dt", "pnl"]].to_string(index=False))
    print(f"\nsum check: {day_trades['pnl'].sum():,.2f}")


if __name__ == "__main__":
    main()
