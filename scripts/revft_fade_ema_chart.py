"""Visualize the EMA-cross-strength feature: mark every downside 20-EMA cross by strength, on days
with f2EL fade entries. 2026-07-25 (S85). Reads the frozen-fade parquet (fill_bar + cs10 + net).

Picks example days — a STRONG-cross winning fade vs a WEAK-cross fade — so Samir can see what the
metric measures. Each downside EMA cross gets a triangle sized/coloured by cross_str; the fade entry
is marked; cross_str is annotated.

    python scripts/revft_fade_ema_chart.py
"""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars" / "_continuous.parquet"
FADE = ROOT / "data" / "regime" / "revft_fade_ema_frozen_20260725.parquet"
OUT = ROOT / "docs" / "living" / "revft_fade_ema_crosses_20260725.png"
EMA_N, K = 20, 10


def cross_str_at(ema, H, L, C, c, K):
    a = max(1, c - K); h, l, e = H[a:c+1], L[a:c+1], ema[a:c+1]
    if len(h) < 3:
        return 0.0
    atr = np.mean(H[a:c] - L[a:c]) or 1.0
    return float((h.max() - l.min()) / atr)


def day_bars(b, d):
    g = b[b["Date"] == d].sort_values("DateTime").reset_index(drop=True)
    return g


def draw_day(ax, g, fade_bars, title):
    C = g["Close"].values; H = g["High"].values; L = g["Low"].values; O = g["Open"].values
    ema = pd.Series(C).ewm(span=EMA_N, adjust=False).mean().values
    x = np.arange(len(g))
    # candles
    for i in x:
        up = C[i] >= O[i]
        ax.add_patch(Rectangle((i-0.3, min(O[i], C[i])), 0.6, abs(C[i]-O[i]) or 0.1,
                     color=("#2a9d5a" if up else "#c0392b"), alpha=.85, lw=0))
        ax.plot([i, i], [L[i], H[i]], color=("#2a9d5a" if up else "#c0392b"), lw=.6, zorder=1)
    ax.plot(x, ema, color="#2b6cb0", lw=1.4, label="EMA20", zorder=3)
    # downside crosses, coloured by strength
    for i in range(1, len(g)):
        if C[i-1] >= ema[i-1] and C[i] < ema[i]:              # downside cross
            cs = cross_str_at(ema, H, L, C, i, K)
            col = "#8e0b0b" if cs >= 2.0 else ("#e08a1e" if cs >= 1.0 else "#9aa0a6")
            sz = 60 + 90 * min(cs, 3) / 3
            ax.scatter(i, L[i] - (H-L).mean()*0.5, marker="v", s=sz, color=col, zorder=5,
                       edgecolor="black", linewidth=.4)
            ax.annotate(f"{cs:.1f}", (i, L[i] - (H-L).mean()*0.9), ha="center", fontsize=7,
                        color=col, fontweight=("bold" if cs >= 2.0 else "normal"))
    # fade entries
    for fb in fade_bars:
        if 0 <= fb < len(g):
            ax.scatter(fb, H[fb] + (H-L).mean()*0.6, marker="*", s=240, color="#111",
                       zorder=6, label="_f2EL fade entry")
            ax.annotate("fade", (fb, H[fb] + (H-L).mean()*1.1), ha="center", fontsize=8, fontweight="bold")
    ax.set_title(title, fontsize=10)
    ax.legend(loc="upper left", fontsize=8); ax.grid(alpha=.2)
    for s in ("top", "right"): ax.spines[s].set_visible(False)


def main():
    b = pd.read_parquet(BARS); b["Date"] = b["DateTime"].dt.date.astype(str)
    f = pd.read_parquet(FADE)
    # strongest-cross winning fade day, and a weak-cross fade day
    fw = f[(f.net > 0)].sort_values("cs10", ascending=False)
    strong_day = fw.iloc[0].Date if len(fw) else f.iloc[0].Date
    fl = f[f.cs10 < 0.8].sort_values("cs10")
    weak_day = fl.iloc[0].Date if len(fl) else f.iloc[-1].Date

    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    for ax, d, lab in ((axes[0], strong_day, "STRONG cross"), (axes[1], weak_day, "WEAK cross")):
        g = day_bars(b, d)
        fbars = f[f.Date == d].fill_bar.astype(int).tolist()
        cs = f[f.Date == d].cs10.max()
        nets = f[f.Date == d].net.sum()
        draw_day(ax, g, fbars, f"{d}  —  {lab}: max cross_str={cs:.1f}, fade net ${nets:+,.0f}   "
                              f"(▼ = downside EMA cross, labelled by strength; ★ = f2EL fade entry)")
    fig.suptitle("f2EL fade × strength of the move THROUGH the 20-EMA  (red ▼ ≥2.0 = strong, gray <1.0 = weak)",
                 fontsize=12, y=0.995)
    fig.tight_layout(); fig.savefig(OUT, facecolor="white", dpi=115)
    print(f"saved {OUT}  (strong day {strong_day}, weak day {weak_day})")


if __name__ == "__main__":
    main()
