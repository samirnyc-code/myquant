"""
or12_render_pairs.py — render the tightest first-12-bar pattern matches as
side-by-side candlestick images for eyeball verification. Only bars 1-12 are
drawn (that is all the matcher saw). Output: docs/living/or12_pairs/ PNGs +
index.html gallery.
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

OUT_DIR = ROOT / "docs" / "living" / "or12_pairs"
N_PAIRS = 12


def draw_candles(ax, g: pd.DataFrame, title: str) -> None:
    g = g.sort_values("DateTime").head(N_BARS).reset_index(drop=True)
    o = g["Open"].to_numpy(float); h = g["High"].to_numpy(float)
    l = g["Low"].to_numpy(float);  c = g["Close"].to_numpy(float)
    for i in range(len(g)):
        up = c[i] >= o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, linewidth=1.2)
        body_lo, body_hi = min(o[i], c[i]), max(o[i], c[i])
        if body_hi - body_lo < 1e-9:
            body_hi = body_lo + (h[i] - l[i]) * 0.01 + 1e-9
        ax.add_patch(plt.Rectangle((i - 0.3, body_lo), 0.6, body_hi - body_lo,
                                   facecolor=col, edgecolor=col))
    ax.set_xlim(-0.8, N_BARS - 0.2)
    ax.set_xticks(range(N_BARS))
    ax.set_xticklabels([str(i + 1) for i in range(N_BARS)], fontsize=8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.25)
    ax.set_facecolor("#fafafa")


def main() -> None:
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    by_date = {d: g for d, g in bars.groupby(bars["DateTime"].dt.date)}

    df, Xz, _cols = build_features()
    pairs = same_bucket_pairs(df, Xz, N_PAIRS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for rank, (da, db_, dist) in enumerate(pairs, 1):
        bucket = df.loc[da, "bucket"]
        gap_a, gap_b = df.loc[da, "gap_norm"], df.loc[db_, "gap_norm"]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
        draw_candles(axes[0], by_date[da], f"{da}   gap {gap_a:+.0%} of yRange")
        draw_candles(axes[1], by_date[db_], f"{db_}   gap {gap_b:+.0%} of yRange")
        fig.suptitle(f"Match #{rank}   {da}  ↔  {db_}   "
                     f"(dist {dist:.2f}, both open {bucket})", fontsize=13)
        fig.tight_layout(rect=(0, 0, 1, 0.93))
        fname = f"pair_{rank:02d}_{da}_{db_}.png"
        fig.savefig(OUT_DIR / fname, dpi=110)
        plt.close(fig)
        entries.append((rank, da, db_, dist, fname))
        print(f"  rendered #{rank}: {da} <-> {db_}")

    html = ["<html><head><title>OR12 pattern matches</title>",
            "<style>body{font-family:sans-serif;background:#222;color:#eee;"
            "text-align:center}img{max-width:95%;margin:12px 0;border-radius:6px}"
            "h1{font-size:20px}</style></head><body>",
            "<h1>First-12-bars pattern matches — tightest pairs, "
            "same open-location bucket (bars 1–12 + prior-day context, "
            "nothing after bar 12)</h1>"]
    for rank, da, db_, dist, fname in entries:
        html.append(f"<div><img src='{fname}' alt='pair {rank}'></div>")
    html.append("</body></html>")
    (OUT_DIR / "index.html").write_text("\n".join(html), encoding="utf-8")
    print(f"gallery: {OUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
