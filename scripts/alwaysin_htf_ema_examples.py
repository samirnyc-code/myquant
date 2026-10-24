"""alwaysin_htf_ema_examples.py — visual chart examples of each flip mechanism.

Picks one representative (near-median) flip per mechanism from the saved
alwaysin_flips_*.csv (see alwaysin_htf_ema_study.py) and renders a candlestick
chart of the 2000-tick bars around it: price + EMA(20), the flip bar, the
post-flip thrust extreme, and the first pullback — so the abstract stats in
the base-rate study are visible as an actual chart, not just numbers.

Rebuilds tick bars fresh per example (flip day + the prior RTH day for
EMA/ABR warmup) rather than reusing the full-history run's in-memory state —
cheap for a handful of examples, avoids re-running the 13-minute full pull.
Same known simplifications as alwaysin_htf_ema_study.py (see its docstring).

Usage:
    python scripts/alwaysin_htf_ema_examples.py [path/to/alwaysin_flips_*.csv]

Output:
    data/alwaysin_htf_ema/_analysis/charts/<mechanism>_<date>_<stamp>.png
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tickdata  # noqa: E402
import alwaysin_htf_ema_study as study  # noqa: E402

ANALYSIS_DIR = ROOT / "data" / "alwaysin_htf_ema" / "_analysis"
CHART_DIR = ANALYSIS_DIR / "charts"

UP_COLOR = "#1a8f4e"      # matches NT8 LimeGreen-family "long" convention used elsewhere in this repo
DOWN_COLOR = "#c0392b"    # matches NT8 Red-family "short" convention
EMA_COLOR = "#4a6fa5"
FLIP_COLOR = "#8e44ad"
EXTREME_COLOR = "#e07b00"
PULLBACK_COLOR = "#c0392b"


def latest_csv() -> Path:
    files = sorted(ANALYSIS_DIR.glob("alwaysin_flips_*.csv"))
    if not files:
        raise FileNotFoundError(f"no alwaysin_flips_*.csv in {ANALYSIS_DIR}")
    return files[-1]


def pick_example(df: pd.DataFrame, mechanism: str) -> pd.Series:
    """Pick the flip of this mechanism whose dist_beyond_ema_abr is closest
    to that mechanism's own median — a 'typical', not cherry-picked, case."""
    sub = df[(df["mechanism"] == mechanism) & (df["pullback_found"])].copy()
    med = sub["dist_beyond_ema_abr"].median()
    sub["dist_to_median"] = (sub["dist_beyond_ema_abr"] - med).abs()
    return sub.sort_values("dist_to_median").iloc[0]


def rebuild_two_day_bars(date: str):
    all_days = tickdata.available("rth")
    i = all_days.index(date)
    prev_day = all_days[i - 1]

    tb1 = study.build_tick_bars(tickdata.load_rth(prev_day))
    tb1, ema1, hist1 = study.add_ema_abr(tb1, None, [])
    tb2 = study.build_tick_bars(tickdata.load_rth(date))
    tb2, _, _ = study.add_ema_abr(tb2, ema1, hist1)

    tb1 = tb1.reset_index(drop=True)
    tb2 = tb2.reset_index(drop=True)
    tb1["global_pos"] = np.arange(len(tb1))
    tb2["global_pos"] = np.arange(len(tb1), len(tb1) + len(tb2))
    return pd.concat([tb1, tb2], ignore_index=True)


def locate_flip_pos(all_bars: pd.DataFrame, flip_time: pd.Timestamp) -> int:
    eligible = all_bars[all_bars["end_time"] <= flip_time]
    return int(eligible.index[-1])


def trace_pullback(all_bars: pd.DataFrame, flip_pos: int, direction: int, max_bars: int = 150):
    """Same logic as study.find_pullback, but returns absolute positions so
    they can be drawn on the chart (the shared function only returns
    relative counts/metrics, not positions)."""
    end_pos = min(flip_pos + max_bars, len(all_bars))
    sub = all_bars.iloc[flip_pos:end_pos].reset_index(drop=True)
    flip_price = sub["close"].iloc[0]
    extreme, extreme_pos = flip_price, 0
    pullback_start_pos = None

    for i in range(1, len(sub)):
        c, abr_i = sub["close"].iloc[i], sub["abr"].iloc[i]
        if direction == 1 and c > extreme:
            extreme, extreme_pos = c, i
        elif direction == -1 and c < extreme:
            extreme, extreme_pos = c, i
        retrace = (extreme - c) if direction == 1 else (c - extreme)
        if abr_i > 0 and retrace >= study.PULLBACK_RETRACE_ABR * abr_i and i > extreme_pos:
            pullback_start_pos = i
            break

    if pullback_start_pos is None:
        return flip_pos, flip_pos + extreme_pos, None, None

    max_retrace, deepest_pos, pullback_end_pos = -np.inf, pullback_start_pos, None
    for i in range(pullback_start_pos, len(sub)):
        c = sub["close"].iloc[i]
        retrace = (extreme - c) if direction == 1 else (c - extreme)
        if retrace > max_retrace:
            max_retrace, deepest_pos = retrace, i
        if (direction == 1 and c > extreme) or (direction == -1 and c < extreme):
            pullback_end_pos = i
            break

    return (flip_pos, flip_pos + extreme_pos, flip_pos + pullback_start_pos,
            flip_pos + deepest_pos)


def plot_example(all_bars: pd.DataFrame, flip_row: pd.Series, out_path: Path):
    direction = int(flip_row["direction"])
    flip_pos, extreme_pos, pullback_start_pos, deepest_pos = trace_pullback(
        all_bars, locate_flip_pos(all_bars, pd.Timestamp(flip_row["flip_time"])), direction,
    )

    lead, trail = 15, 55
    lo = max(0, flip_pos - lead)
    hi = min(len(all_bars), (deepest_pos or extreme_pos) + trail)
    window = all_bars.iloc[lo:hi].reset_index(drop=True)
    flip_x = flip_pos - lo

    fig, ax = plt.subplots(figsize=(14, 7), dpi=130)
    width = 0.6
    for i, row in window.iterrows():
        color = UP_COLOR if row["close"] >= row["open"] else DOWN_COLOR
        ax.plot([i, i], [row["low"], row["high"]], color=color, linewidth=0.9, zorder=2)
        y0, h = min(row["open"], row["close"]), abs(row["close"] - row["open"])
        ax.add_patch(Rectangle((i - width / 2, y0), width, max(h, 1e-9),
                                facecolor=color, edgecolor=color, linewidth=0.6, zorder=3))

    ax.plot(range(len(window)), window["ema"], color=EMA_COLOR, linewidth=1.6,
            label="EMA(20) on 2000t bars", zorder=4)

    ax.axvline(flip_x, color=FLIP_COLOR, linestyle="--", linewidth=1.3, zorder=1)
    ax.annotate(f"FLIP  ({flip_row['mechanism']})", xy=(flip_x, window["high"].max()),
                xytext=(flip_x, window["high"].max()), color=FLIP_COLOR, fontsize=9,
                fontweight="bold", ha="center", va="bottom")

    if extreme_pos is not None:
        ex = extreme_pos - lo
        ax.scatter([ex], [window["close"].iloc[ex]], color=EXTREME_COLOR, zorder=5, s=50,
                   marker="^" if direction == 1 else "v", label="post-flip extreme")
    if pullback_start_pos is not None:
        ps = pullback_start_pos - lo
        ax.axvspan(ps, (deepest_pos - lo) if deepest_pos is not None else ps + 1,
                   color=PULLBACK_COLOR, alpha=0.12, zorder=0, label="pullback window")
    if deepest_pos is not None:
        dp = deepest_pos - lo
        ax.scatter([dp], [window["close"].iloc[dp]], color=PULLBACK_COLOR, zorder=5, s=50,
                   marker="o", label="deepest pullback bar")

    stats = (f"dist beyond EMA: {flip_row['dist_beyond_ema_abr']:.2f}x ABR   "
             f"flip-bar IBS: {flip_row['htf_ibs_signed']:.2f}   "
             f"thrust: {flip_row['thrust_distance_abr']:.2f}x ABR   "
             f"pullback depth: {flip_row['max_pullback_depth_abr']:.2f}x ABR   "
             f"touched EMA: {flip_row['pullback_touched_ema']}")
    ax.set_title(f"AlwaysInHtfEma flip — {flip_row['mechanism']}  |  "
                 f"{flip_row['date']} {pd.Timestamp(flip_row['flip_time']).strftime('%H:%M')}  "
                 f"({'LONG' if direction == 1 else 'SHORT'})\n{stats}", fontsize=10)
    ax.set_xlabel("2000-tick bar #  (price-based x-axis, not time)")
    ax.set_ylabel("ES price")

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles, labels, loc="best", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Saved: {out_path}")


def main():
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_csv()
    df = pd.read_csv(csv_path)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

    out_paths = []
    for mech in ["consecutive_close", "strong_breakout", "gap"]:
        row = pick_example(df, mech)
        all_bars = rebuild_two_day_bars(str(row["date"]))
        out_path = CHART_DIR / f"{mech}_{row['date']}_{stamp}.png"
        plot_example(all_bars, row, out_path)
        out_paths.append(out_path)

    print("\n".join(str(p) for p in out_paths))


if __name__ == "__main__":
    main()
