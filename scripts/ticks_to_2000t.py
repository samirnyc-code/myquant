"""ticks_to_2000t.py — build N-tick bars from a trove day and render them, bar by bar.

Groups the day's RTH ticks into fixed-size (default 2000) tick bars (OHLCV), prints
every bar, saves a dated CSV, and renders a candlestick PNG so it can be compared
against NT8's own N-tick chart.

    python scripts/ticks_to_2000t.py --date 2026-08-17 [--size 2000]
"""
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
TROVE = ROOT / "data" / "ticks_continuous"
OUT = ROOT / "data" / "ticks_continuous" / "_2000t"


def bars(df, size):
    df = df.reset_index(drop=True)
    df["grp"] = df.index // size
    g = df.groupby("grp")
    b = pd.DataFrame({
        "start": g["DateTime"].first(),
        "end": g["DateTime"].last(),
        "open": g["Price"].first(),
        "high": g["Price"].max(),
        "low": g["Price"].min(),
        "close": g["Price"].last(),
        "vol": g["Volume"].sum(),
        "ticks": g["Price"].size(),
    }).reset_index(drop=True)
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--size", type=int, default=2000)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    f = TROVE / f"{a.date}.parquet"
    if not f.exists():
        raise SystemExit(f"no trove day {a.date}")
    df = pd.read_parquet(f)
    b = bars(df, a.size)
    print(f"{a.date}: {len(df):,} RTH ticks -> {len(b)} x {a.size}-tick bars\n")
    print(f"{'#':>3} {'start':>12} {'open':>9} {'high':>9} {'low':>9} {'close':>9} {'vol':>7}")
    for i, r in b.iterrows():
        print(f"{i:>3} {r['start'].strftime('%H:%M:%S'):>12} {r['open']:>9.2f} {r['high']:>9.2f} "
              f"{r['low']:>9.2f} {r['close']:>9.2f} {int(r['vol']):>7}")

    csv = OUT / f"{a.date}_{a.size}t.csv"
    b.to_csv(csv, index=False)

    # candlestick render
    fig, ax = plt.subplots(figsize=(max(10, len(b) * 0.16), 6))
    for i, r in b.iterrows():
        up = r["close"] >= r["open"]
        c = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [r["low"], r["high"]], color=c, linewidth=0.7, zorder=1)
        ax.add_patch(plt.Rectangle((i - 0.3, min(r["open"], r["close"])), 0.6,
                                   max(abs(r["close"] - r["open"]), 0.01), color=c, zorder=2))
    ax.set_title(f"ES 09-26  {a.date}  {a.size}-tick bars ({len(b)} bars, from trove)")
    ax.set_xlabel("bar #"); ax.set_ylabel("price")
    ax.grid(True, alpha=0.2)
    png = OUT / f"{a.date}_{a.size}t.png"
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    print(f"\nsaved bars -> {csv.relative_to(ROOT)}\nsaved chart -> {png.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
