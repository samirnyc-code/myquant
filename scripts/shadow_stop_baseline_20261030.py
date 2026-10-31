"""The actual Analytics-tab intraday DD metric (shadow_stop_monitor.py's
portfolio_curve/trough), recomputed for ONLY the trades that were supposed to
fire under the gameplan's rules on 2026-10-30 -- not shadow_stop_monitor's
current n=27 (every duplicate-fire copy counted).

This does NOT reinvent a methodology. It reuses shadow_stop_monitor.portfolio_curve()
verbatim (same marks.csv pivot/ffill/fillna(0)/sum, same WARN/STOP levels, same
trough = curve.min()) -- the only change is filtering marks to the 10 correct
trade_ids before summing, so the number is apples-to-apples with the existing
shadow_stop_log.csv row for this day:

    2026-10-30,27,-3590,10:24,True,10:12,-2015,True,10:24,-3590,-3010,HURT,...

The 10 correct trade_ids = the gameplan's 10 setups, each taken ONCE, at the
first time it actually filled under the 'time_at not_before 08:30' rule:

  9 of 10 filled clean and on-time (entry_note='ok', 08:31-08:39 CT).
  gx_bcs did NOT: its only fill anywhere in the log is tagged
    'late fill +29min (fixed strike; fill only)' -- the bug didn't just create
    duplicates, it also meant NO clean on-time gx_bcs fill ever happened. That
    trade is flagged, not silently treated as clean.

Run: .venv/Scripts/python.exe scripts/shadow_stop_baseline_20261030.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import shadow_stop_monitor as ssm  # reuse its exact portfolio_curve logic

OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DAY = "2026-10-30"

CORRECT_IDS = {
    "auto_20261030_083114": ("eodic_p", "ok"),
    "auto_20261030_083220": ("eodic_c", "ok"),
    "auto_20261030_083331": ("eodfly_p", "ok"),
    "auto_20261030_083446": ("eodfly_c", "ok"),
    "auto_20261030_083523": ("openic_p", "ok"),
    "auto_20261030_083640": ("openic_c", "ok"),
    "auto_20261030_083737": ("openfly_p", "ok"),
    "auto_20261030_083844": ("openfly_c", "ok"),
    "auto_20261030_083944": ("gx_bps", "ok"),
    "auto_20261030_085926": ("gx_bcs", "late fill +29min -- NOT a clean on-time execution"),
}


def portfolio_curve_filtered(day, ids):
    """Identical to shadow_stop_monitor.portfolio_curve() except the marks are
    filtered to `ids` before pivoting/summing."""
    if not ssm.MARKS.exists():
        return None
    m = pd.read_csv(ssm.MARKS)
    m = m[m["trade_id"].isin(ids)]
    m["ts"] = pd.to_datetime(m["ts_et"], errors="coerce")
    m = m.dropna(subset=["ts"])
    m = m[m["ts"].dt.strftime("%Y-%m-%d") == day]
    if m.empty:
        return None
    m["unreal_pnl"] = pd.to_numeric(m["unreal_pnl"], errors="coerce")
    piv = m.pivot_table(index="ts", columns="trade_id", values="unreal_pnl", aggfunc="last")
    piv = piv.sort_index().ffill().fillna(0.0)
    return piv.sum(axis=1)


def main():
    curve = portfolio_curve_filtered(DAY, list(CORRECT_IDS))
    trades = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    correct = trades[trades["trade_id"].isin(CORRECT_IDS)]
    booked_total = round(correct["pnl"].sum(), 2)

    lines = [f"# Correct-trades-only intraday DD — {DAY} (shadow_stop_monitor's exact methodology)\n"]
    lines.append("## The 10 trades that were supposed to execute under the gameplan's rules\n")
    for tid, (setup, note) in CORRECT_IDS.items():
        row = trades[trades["trade_id"] == tid].iloc[0]
        flag = "" if note == "ok" else f"  [FLAG] {note}"
        lines.append(f"- {tid} ({setup}): entered {row['entry_dt']}, final pnl {row['pnl']:.2f}{flag}")
    lines.append(f"\n**Final P&L, correct trades only: {booked_total:.2f}**")
    lines.append("(gx_bcs's only available fill is included above since there is no clean "
                  "alternative in the log -- flagged, not fabricated.)\n")

    if curve is None:
        lines.append("## No marks found for the correct trade_ids on this day.")
    else:
        trough = round(curve.min(), 2)
        trough_ct = curve.idxmin().strftime("%H:%M:%S")
        crossed_warn = curve[curve <= ssm.WARN]
        crossed_stop = curve[curve <= ssm.STOP]
        lines.append(f"## Intraday DD (shadow_stop_monitor.portfolio_curve, same method as the Analytics tab)\n")
        lines.append(f"- Real-marks window: {curve.index.min()} -> {curve.index.max()} CT")
        lines.append(f"- **Trough: {trough:.2f} at {trough_ct} CT**")
        lines.append(f"- Crossed WARN ({ssm.WARN}): "
                      f"{'YES at ' + crossed_warn.index[0].strftime('%H:%M:%S') + ' CT (' + str(round(crossed_warn.iloc[0],2)) + ')' if len(crossed_warn) else 'no'}")
        lines.append(f"- Crossed STOP ({ssm.STOP}): "
                      f"{'YES at ' + crossed_stop.index[0].strftime('%H:%M:%S') + ' CT (' + str(round(crossed_stop.iloc[0],2)) + ')' if len(crossed_stop) else 'no'}")
        lines.append(f"\n- Same gap as every other intraday reconstruction this session: "
                      f"`options_mark.py` died ~11:35 CT, so this trough is only provable up to "
                      f"{curve.index.max()} CT -- it is a FLOOR, not a full-day guarantee.")
        lines.append(f"\n## For comparison, the CURRENT (bug-inflated, n=27) shadow_stop_log.csv row\n")
        lines.append("- `2026-10-30,27,-3590,10:24,True,10:12,-2015,True,10:24,-3590,-3010,HURT,...`")
        lines.append(f"- trough -3590 @ 10:24 (27 trades) vs trough {trough:.2f} @ {trough_ct} CT (10 correct trades)")

    report = OUT_DIR / "shadow_stop_baseline_20261030.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {report}")


if __name__ == "__main__":
    main()
