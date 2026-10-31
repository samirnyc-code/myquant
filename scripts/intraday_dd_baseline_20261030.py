"""Intraday drawdown for 2026-10-30, baseline (non-duplicate) trades only.

The Analytics tab's "Max drawdown" tile is a DAY-LEVEL close-to-close number
across the whole account history (see analytics_tab_reconcile_20261030.py) --
it is NOT an intraday figure and was never going to answer "how far underwater
did today's correct 10 trades get while the market was open."

This pulls REAL intraday marks (data/options_sim/marks.csv unreal_pnl, written
~every 2min while options_mark.py was alive) for the 10 baseline (wave=1,
non-duplicate) trade_ids only, sums them into a book-level intraday equity
curve, and finds the running peak-to-trough drawdown.

KNOWN GAP: options_mark.py died and hit its restart cap at ~11:35 CT (see
duplicate_fire_incident_20261030.md); marks.csv has nothing after 11:48:49 CT.
From 11:48:49 to the 16:00 CT close/expiry there is NO real intraday mark for
the baseline trades. This script reports the max DD observed in the real-marked
window (09:32:34-11:48:49 CT) honestly as a FLOOR, not a complete-day number,
and separately shows the known EOD outcome (-$2,507.60, from trades.parquet) so
the gap is visible rather than silently interpolated.

Run: .venv/Scripts/python.exe scripts/intraday_dd_baseline_20261030.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DATE_ISO = "2026-10-30"

BASELINE_IDS = [
    "auto_20261030_083114", "auto_20261030_083220", "auto_20261030_083331",
    "auto_20261030_083446", "auto_20261030_083523", "auto_20261030_083640",
    "auto_20261030_083737", "auto_20261030_083844", "auto_20261030_083944",
    "auto_20261030_085926",
]


def load_baseline_trades() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    return df[df["trade_id"].isin(BASELINE_IDS)].copy()


def load_marks() -> pd.DataFrame:
    m = pd.read_csv(ROOT / "data" / "options_sim" / "marks.csv")
    m = m[m["trade_id"].isin(BASELINE_IDS)].copy()
    m["ts_et"] = pd.to_datetime(m["ts_et"])
    return m


def build_intraday_curve(marks: pd.DataFrame) -> pd.DataFrame:
    """Pivot to one column per trade_id, forward-fill gaps (a trade missing from
    one poll cycle keeps its last known mark rather than dropping to 0), sum
    across the 10 baseline positions at each real timestamp."""
    piv = marks.pivot_table(index="ts_et", columns="trade_id", values="unreal_pnl", aggfunc="last")
    piv = piv.sort_index().ffill()
    piv["book_unreal"] = piv.sum(axis=1, skipna=True)
    curve = piv[["book_unreal"]].reset_index()
    cum = 0.0
    peak = 0.0
    peaks, dds = [], []
    for v in curve["book_unreal"]:
        peak = max(peak, v)
        peaks.append(peak)
        dds.append(v - peak)
    curve["peak"] = peaks
    curve["dd"] = dds
    return curve


def load_underlying_tape() -> pd.DataFrame:
    u = pd.read_csv(ROOT / "data" / "options_sim" / f"underlying_{DATE_ISO.replace('-', '')}.csv")
    u["ts"] = pd.to_datetime(DATE_ISO + " " + u["ts_et"])
    return u[["ts", "und"]]


def intrinsic_book_pnl(trades: pd.DataFrame, spot: float) -> float:
    """Sum of (credit received + intrinsic owed) * 100 across the 10 baseline
    legs at a given spot -- ignores extrinsic/time value, so it UNDERSTATES
    unrealized loss while there's still time value left and OVERSTATES it only
    very close to expiry. Same method used earlier this session for the live
    mid-session estimate."""
    total = 0.0
    for _, r in trades.iterrows():
        legs = json.loads(r["legs"])
        intrinsic = 0.0
        for leg in legs:
            k, right, side = leg["strike"], leg["right"], leg["side"]
            iv = max(0.0, k - spot) if right == "P" else max(0.0, spot - k)
            intrinsic += iv if side == "buy" else -iv
        total += (r["credit"] + intrinsic) * 100
    return total


def main():
    trades = load_baseline_trades()
    marks = load_marks()
    curve = build_intraday_curve(marks)

    worst = curve.loc[curve["dd"].idxmin()]
    first = curve.iloc[0]
    last_marked = curve.iloc[-1]
    eod_actual = round(trades["pnl"].sum(), 2)

    # ---- extend past the marks-dead gap with an intrinsic-value estimate from
    # the underlying spot tape, calibrated against the real marks where they overlap ----
    tape = load_underlying_tape()
    tape["intrinsic_pnl"] = tape["und"].apply(lambda s: intrinsic_book_pnl(trades, s))
    overlap = tape[(tape["ts"] >= marks["ts_et"].min()) & (tape["ts"] <= marks["ts_et"].max())].copy()
    # nearest-mark comparison for calibration
    calib_rows = []
    for _, row in overlap.iterrows():
        nearest = curve.iloc[(curve["ts_et"] - row["ts"]).abs().argmin()]
        calib_rows.append(nearest["book_unreal"] - row["intrinsic_pnl"])
    calib_offset = sum(calib_rows) / len(calib_rows) if calib_rows else 0.0

    after_gap = tape[tape["ts"] > marks["ts_et"].max()].copy()
    after_gap["est_book_unreal"] = after_gap["intrinsic_pnl"] + calib_offset
    peak = max(curve["peak"].max(), curve["book_unreal"].max())
    peaks, dds = [], []
    for v in after_gap["est_book_unreal"]:
        peak = max(peak, v)
        peaks.append(peak)
        dds.append(v - peak)
    after_gap["peak"] = peaks
    after_gap["dd_est"] = dds
    worst_est = after_gap.loc[after_gap["dd_est"].idxmin()] if len(after_gap) else None

    lines = []
    lines.append(f"# Intraday drawdown — {DATE_ISO}, baseline (non-duplicate) trades only\n")
    lines.append(f"- 10 baseline trade_ids: {', '.join(BASELINE_IDS)}")
    lines.append(f"- Real marks window: {marks['ts_et'].min()} -> {marks['ts_et'].max()} CT "
                 f"({len(curve)} snapshots)")
    lines.append(f"- Book unrealized P&L at first mark ({first['ts_et']}): {first['book_unreal']:.2f}")
    lines.append(f"- Book unrealized P&L at last real mark ({last_marked['ts_et']}): {last_marked['book_unreal']:.2f}")
    lines.append(f"\n## Max intraday drawdown OBSERVED (real marks only, 09:32-11:48 CT)\n")
    lines.append(f"- **{worst['dd']:.2f}** at {worst['ts_et']} CT "
                 f"(book unrealized {worst['book_unreal']:.2f}, prior peak {worst['peak']:.2f})")
    lines.append(f"\n## Known gap\n")
    lines.append("- `options_mark.py` died ~11:35 CT, hit its 5/day restart cap, marks.csv has "
                 "nothing after 11:48:49 CT. There is NO real intraday mark for the baseline "
                 "trades between 11:48:49 CT and the 16:00 CT close/expiry.")
    lines.append(f"- Actual EOD outcome for these 10 trades (from trades.parquet, all expired "
                 f"at 16:00): **{eod_actual:.2f}**")

    lines.append("\n## Gap bridged with an intrinsic-value estimate (NOT a real mark)\n")
    lines.append(f"- Used `data/options_sim/underlying_{DATE_ISO.replace('-', '')}.csv` (spot tape, "
                 f"~1/min all day) to price the 10 baseline legs by intrinsic value only (credit + "
                 f"intrinsic owed, zero extrinsic/time value) at every tape timestamp.")
    lines.append(f"- Calibration: averaged (real mark - intrinsic estimate) over the "
                 f"{len(overlap)} tape points inside the real-marks window to correct for the "
                 f"missing extrinsic value -> offset {calib_offset:+.2f}. Applied as a constant "
                 f"shift to the post-gap intrinsic series (extrinsic value decays over the "
                 f"afternoon so this constant-offset approximation gets LESS accurate the further "
                 f"past 11:48:49 CT it's read — treat it as directional, not exact).")
    if worst_est is not None:
        lines.append(f"- **Estimated worst point after the gap: {worst_est['dd_est']:.2f} at "
                     f"{worst_est['ts']} CT** (est. book unrealized {worst_est['est_book_unreal']:.2f}, "
                     f"spot {worst_est['und']:.2f})")
        deeper = worst_est['dd_est'] < worst['dd']
        lines.append(f"- Combined with the observed window, the estimated full-day max intraday "
                     f"drawdown is **{min(worst['dd'], worst_est['dd_est']):.2f}**, occurring "
                     f"{'in the UNOBSERVED post-11:48 window (estimate, not a real mark)' if deeper else 'in the OBSERVED real-marks window (09:32-11:48 CT)'}.")
    lines.append("\n- Full extended curve (real marks + post-gap estimate) in "
                 f"`intraday_curve_baseline_extended_{DATE_ISO.replace('-', '')}.csv`.")

    report_path = OUT_DIR / f"intraday_dd_baseline_{DATE_ISO.replace('-', '')}.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    curve.to_csv(OUT_DIR / f"intraday_curve_baseline_{DATE_ISO.replace('-', '')}.csv", index=False)
    ext_cols = ["ts", "und", "intrinsic_pnl", "est_book_unreal", "peak", "dd_est"]
    after_gap[ext_cols].to_csv(
        OUT_DIR / f"intraday_curve_baseline_extended_{DATE_ISO.replace('-', '')}.csv", index=False)

    print("\n".join(lines))
    print(f"\nwrote {report_path}")


if __name__ == "__main__":
    main()
