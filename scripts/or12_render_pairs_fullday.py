"""
or12_render_pairs_fullday.py — for the tightest same-bucket first-12-bar
matches, render the FULL RTH day (all 5M bars) side by side:
  - IB area (first 12 bars = first 60 min) shaded, IB High/Low extended across
    the session
  - prior-day High / Low / Close drawn as dashed reference lines
  - label per chart: open context vs yesterday + IB characteristics
The match itself still uses ONLY bars 1-12 + prior-day context (or12_pattern_groups).
Output: docs/living/or12_pairs_fullday/ PNGs + index.html gallery.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from or12_pattern_groups import (  # noqa: E402
    build_features, same_bucket_pairs, BARS_PQ, N_BARS)

OUT_DIR = ROOT / "docs" / "living" / "or12_pairs_fullday"
N_PAIRS = 12

BUCKET_TXT = {
    "above_yH":   "opens ABOVE yHigh",
    "upper_half": "opens upper half of yRange",
    "lower_half": "opens lower half of yRange",
    "below_yL":   "opens BELOW yLow",
}


def draw_day(ax, g: pd.DataFrame, prior: pd.Series | None, label: str) -> None:
    g = g.sort_values("DateTime").reset_index(drop=True)
    o = g["Open"].to_numpy(float); h = g["High"].to_numpy(float)
    l = g["Low"].to_numpy(float);  c = g["Close"].to_numpy(float)
    n = len(g)

    ib_hi, ib_lo = h[:N_BARS].max(), l[:N_BARS].min()

    # IB shading + extended IB levels
    ax.axvspan(-0.6, N_BARS - 0.4, color="#4a6fa5", alpha=0.12, zorder=0)
    ax.hlines([ib_hi, ib_lo], N_BARS - 0.4, n - 0.6, colors="#4a6fa5",
              linestyles="solid", linewidth=1.4, alpha=0.9, zorder=1)
    ax.text(N_BARS + 0.4, ib_hi, "IB High", fontsize=7, color="#4a6fa5",
            va="bottom")
    ax.text(N_BARS + 0.4, ib_lo, "IB Low", fontsize=7, color="#4a6fa5",
            va="top")

    # prior-day reference levels
    if prior is not None:
        for val, name, col in ((prior["H"], "yH", "#999999"),
                               (prior["C"], "yC", "#bbaa55"),
                               (prior["L"], "yL", "#999999")):
            ax.axhline(val, color=col, linestyle="--", linewidth=1.0,
                       alpha=0.8, zorder=1)
            ax.text(n - 0.2, val, name, fontsize=7, color=col, va="center")

    for i in range(n):
        up = c[i] >= o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, linewidth=0.9, zorder=2)
        body_lo, body_hi = min(o[i], c[i]), max(o[i], c[i])
        if body_hi - body_lo < 1e-9:
            body_hi = body_lo + max(h[i] - l[i], 1e-6) * 0.02
        ax.add_patch(plt.Rectangle((i - 0.32, body_lo), 0.64,
                                   body_hi - body_lo,
                                   facecolor=col, edgecolor=col, zorder=2))

    ax.set_xlim(-1.2, n + 2.5)
    ticks = list(range(0, n, 12)) + [n - 1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(t + 1) for t in ticks], fontsize=8)
    ax.set_xlabel("bar # (5M, RTH)", fontsize=8)
    ax.grid(True, alpha=0.22)
    ax.set_facecolor("#fafafa")
    ax.set_title(label, fontsize=9.5, loc="left", family="monospace")


def main() -> None:
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    by_date = {d: g for d, g in bars.groupby(bars["DateTime"].dt.date)}

    daily = bars.groupby(bars["DateTime"].dt.date).agg(
        O=("Open", "first"), H=("High", "max"),
        L=("Low", "min"),    C=("Close", "last"))
    daily["rng"] = daily["H"] - daily["L"]
    daily["adr14"] = daily["rng"].rolling(14, min_periods=7).mean().shift(1)
    dates_sorted = list(daily.index)
    prior_of = {d: dates_sorted[i - 1] if i > 0 else None
                for i, d in enumerate(dates_sorted)}

    df, Xz, _cols = build_features()
    pairs = same_bucket_pairs(df, Xz, N_PAIRS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for rank, (da, db_, dist) in enumerate(pairs, 1):
        fig, axes = plt.subplots(1, 2, figsize=(16, 5.2))
        for ax, d in zip(axes, (da, db_)):
            row = df.loc[d]
            g = by_date[d]
            ib_bars = g.sort_values("DateTime").head(N_BARS)
            ib_rng = ib_bars["High"].max() - ib_bars["Low"].min()
            adr = daily.loc[d, "adr14"]
            pd_ = prior_of[d]
            prior = daily.loc[pd_] if pd_ is not None else None
            shape_bits = []
            if row["dt"] > 0: shape_bits.append("DT")
            if row["db"] > 0: shape_bits.append("DB")
            if row["fbo"] >= 2: shape_bits.append(f"{int(row['fbo'])}xfBO")
            label = (
                f"{d}   {BUCKET_TXT[row['bucket']]}, gap {row['gap_norm']:+.0%} of yRange\n"
                f"IB: rng {ib_rng:.2f}pt = {ib_rng/adr:.2f}x ADR14 | "
                f"drive {row['net_drive']:+.2f} | flips {int(row['flips'])} | "
                f"closes @{row['close_loc']:.0%} of IB"
                + (" | " + ",".join(shape_bits) if shape_bits else "")
            )
            draw_day(ax, g, prior, label)
        fig.suptitle(f"Match #{rank}   {da}  ↔  {db_}   (dist {dist:.2f}) — "
                     f"matched on IB only; rest of day = outcome", fontsize=12)
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        fname = f"fullday_{rank:02d}_{da}_{db_}.png"
        fig.savefig(OUT_DIR / fname, dpi=110)
        plt.close(fig)
        entries.append(fname)
        print(f"  rendered #{rank}: {da} <-> {db_}")

    html = ["<html><head><title>OR12 matches — full day</title>",
            "<style>body{font-family:sans-serif;background:#222;color:#eee;"
            "text-align:center}img{max-width:97%;margin:12px 0;border-radius:6px}"
            "h1{font-size:20px}</style></head><body>",
            "<h1>Matched openings — FULL day, IB marked "
            "(match used bars 1–12 + prior-day context only)</h1>"]
    html += [f"<div><img src='{f}'></div>" for f in entries]
    html.append("</body></html>")
    (OUT_DIR / "index.html").write_text("\n".join(html), encoding="utf-8")
    print(f"gallery: {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
