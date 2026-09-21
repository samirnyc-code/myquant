#!/usr/bin/env python3
"""Render regime_data.json (from run_regime.py) as a hi-res candlestick chart
with bull/bear/range regime bands.

Usage:
  python plot_regime.py [regime_data.json] [--out regime_chart.png]
"""
import sys, json, argparse
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, Patch
from matplotlib.lines import Line2D

# status palette (dataviz skill reference palette) -- bull=good, bear=critical, range=warning
COLOR = {
    "Bull": "#0ca30c",
    "Bear": "#d03b3b",
    "Range": "#fab219",
}
BAND_ALPHA = 0.28
PIVOT_COLOR = "#eb6834"
SURFACE = "#fcfcfb"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", nargs="?", default="regime_data.json")
    ap.add_argument("--out", default="regime_chart.png")
    a = ap.parse_args()

    d = json.load(open(a.data))
    bars = d["bars"]
    n = len(bars)
    dates = [datetime.fromisoformat(b["t"]) for b in bars]
    x = mdates.date2num(dates)
    O = [b["o"] for b in bars]; H = [b["h"] for b in bars]
    L = [b["l"] for b in bars]; C = [b["c"] for b in bars]

    fig, ax = plt.subplots(figsize=(15, 7.5), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # regime bands (half-bar-width padding, in the same units as the bar spacing --
    # a hardcoded 0.5 assumes daily bars; on 5-minute bars that's ~144 bar-widths
    # of misalignment and blows out the axis autoscale)
    half_bar = (x[1] - x[0]) / 2 if n > 1 else 0.5
    for seg in d["segments"]:
        s, e = seg["start"], min(seg["end"], n - 1)
        x0 = x[s] - half_bar
        x1 = x[e] + (half_bar if e == n - 1 else -half_bar)
        if x1 <= x0:
            x1 = x[s] + half_bar
        ax.axvspan(x0, x1, color=COLOR[seg["regime"]], alpha=BAND_ALPHA, lw=0, zorder=0)

    # candlesticks -- classic monochrome OHLC style (hollow white up, solid black
    # down) so bar direction doesn't visually compete with the regime bands, which
    # carry the actual bull/bear/range signal
    width = (x[1] - x[0]) * 0.6 if n > 1 else 0.6
    for i in range(n):
        up = C[i] >= O[i]
        ax.add_line(Line2D([x[i], x[i]], [L[i], H[i]], color=TEXT_PRIMARY, linewidth=0.9, zorder=2))
        body_lo, body_hi = (O[i], C[i]) if up else (C[i], O[i])
        ax.add_patch(Rectangle((x[i] - width / 2, body_lo), width, max(body_hi - body_lo, 1e-6),
                                facecolor=(SURFACE if up else TEXT_PRIMARY), edgecolor=TEXT_PRIMARY,
                                linewidth=0.6, zorder=3))

    # swing pivot markers -- small dots just outside the bar (below swing lows,
    # above swing highs), like NinjaTrader's SwingLow/SwingHigh dot style
    lows = d["pivot_lows"]; highs = d["pivot_highs"]
    price_span = max(H) - min(L)
    pivot_offset = price_span * 0.012
    def plot_pivots(pivots, sign):
        for is_major, size, alpha in ((True, 30, 0.95), (False, 10, 0.45)):
            pts = [p for p in pivots if p["major"] == is_major]
            if pts:
                ax.scatter([x[p["i"]] for p in pts], [p["price"] + sign * pivot_offset for p in pts],
                           marker="o", s=size, color=PIVOT_COLOR, alpha=alpha, linewidths=0, zorder=4, label=None)

    plot_pivots(lows, -1)
    plot_pivots(highs, 1)

    # BOS / ChoCh markers -- the level that broke, drawn from the major pivot
    # that set it across to the bar that took it out. Only the breaks that
    # actually move the state are drawn; continuation BOS fire on almost every
    # leg and would bury the chart.
    turning = {s["start"] for s in d["segments"]}
    for ev in d.get("events", []):
        i, lvl = ev["i"], ev["level"]
        if lvl is None or i not in turning:
            continue
        up = ev["dir"] == "up"
        is_choch = ev["kind"] == "ChoCh"
        col = COLOR["Bear"] if is_choch else TEXT_SECONDARY
        src = i
        for p in (highs if up else lows):
            if p["major"] and p["i"] < i and abs(p["price"] - lvl) < 1e-9:
                src = p["i"]
        ax.plot([x[max(src, 0)], x[i]], [lvl, lvl], color=col, linewidth=1.1,
                linestyle=(0, (4, 2)) if is_choch else "-", alpha=0.85, zorder=5)
        ax.annotate(ev["kind"], xy=(x[i], lvl),
                    xytext=(0, 7 if up else -14), textcoords="offset points",
                    ha="center", fontsize=7.5, fontweight="bold", color=col, zorder=6)

    ax.xaxis_date()
    span = dates[-1] - dates[0]
    if span.total_seconds() <= 2 * 86400:
        fmt = "%H:%M"
    elif span.days <= 90:
        fmt = "%d %b"
    else:
        fmt = "%b %Y"
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
    ax.tick_params(colors=TEXT_MUTED, labelsize=9)

    # bar index numbers on a secondary top axis, so a screenshot can reference
    # an exact bar ("bar 52") without reading times off the gridlines
    bar_axis = ax.secondary_xaxis("top")
    bar_axis.set_xticks(x, [str(i + 1) for i in range(n)])
    bar_axis.tick_params(colors=TEXT_MUTED, labelsize=5, rotation=90, length=2)
    for spine in bar_axis.spines.values():
        spine.set_color(AXIS)
    for spine in ax.spines.values():
        spine.set_color(AXIS)
    ax.grid(True, color=GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)

    ax.set_title("Regime Tracker — Bull / Bear / Trading Range (mywedge swing structure)",
                 color=TEXT_PRIMARY, fontsize=13, fontweight="bold", loc="left", pad=12)
    ax.set_ylabel("Price", color=TEXT_SECONDARY, fontsize=10)

    legend_elems = [
        Patch(facecolor=COLOR["Bull"], alpha=BAND_ALPHA * 2.2, edgecolor=COLOR["Bull"], label="Bull  (higher highs + higher lows)"),
        Patch(facecolor=COLOR["Bear"], alpha=BAND_ALPHA * 2.2, edgecolor=COLOR["Bear"], label="Bear  (lower highs + lower lows)"),
        Patch(facecolor=COLOR["Range"], alpha=BAND_ALPHA * 2.2, edgecolor=COLOR["Range"], label="Range  (mixed structure)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=PIVOT_COLOR, markersize=8, alpha=0.95, label="major pivot (drives regime)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=PIVOT_COLOR, markersize=5, alpha=0.45, label="minor pivot (context only)"),
    ]
    leg = ax.legend(handles=legend_elems, loc="upper left", frameon=True, fontsize=8.5,
                    facecolor=SURFACE, edgecolor=AXIS, labelcolor=TEXT_PRIMARY)
    leg.get_frame().set_linewidth(0.7)

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(a.out, facecolor=SURFACE, dpi=200)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
