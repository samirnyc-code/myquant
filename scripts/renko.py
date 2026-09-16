"""renko.py — Renko brick chart from the tick trove, with volume per brick.

A structure lens for Wyckoff: Renko is price-movement (not time) — same family as the P&F the
book endorses (p.39) — so ranges, springs and breakouts read cleanly. CAVEAT (be honest): a
brick can span 30s or 30min, so volume-per-brick is NOT directly comparable the way Wyckoff
volume needs; use it for STRUCTURE and keep effort on the Weis wave (bar-agnostic). Renko also
hides the true wick extremes and the last brick "repaints" until price completes it.

Bricks built from OUR tick trove via canonical tickdata.py. Classic 1-brick construction:
a new brick prints each time price travels one brick size; direction flips on a brick against.

    python scripts/renko.py                              # latest RTH day, 5-pt bricks
    python scripts/renko.py --day 2026-09-15 --brick 5
    python scripts/renko.py --day 2026-09-15 --eth --brick 5
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def build_renko(df: pd.DataFrame, brick: float) -> pd.DataFrame:
    d = df.sort_values("DateTime").reset_index(drop=True)
    price = d["Price"].to_numpy()
    vol = d["Volume"].to_numpy()
    times = d["DateTime"].to_numpy()
    base = round(price[0] / brick) * brick        # snap the first brick to the grid
    bricks = []
    accum = 0.0
    for i in range(len(price)):
        accum += vol[i]
        pend = []
        while price[i] >= base + brick:
            base += brick; pend.append(("up", base - brick, base))
        while price[i] <= base - brick:
            base -= brick; pend.append(("dn", base, base + brick))
        if pend:
            per = accum / len(pend)
            for direction, bottom, top in pend:
                bricks.append(dict(dir=direction, bottom=bottom, top=top, vol=int(per), t=times[i]))
            accum = 0.0
    return pd.DataFrame(bricks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--brick", type=float, default=5.0, help="brick size in points")
    ap.add_argument("--eth", action="store_true")
    a = ap.parse_args()

    day = a.day or td.available("eth" if a.eth else "rth")[-1]
    raw = td.load_eth(day) if a.eth else td.load_rth(day)
    R = build_renko(raw, a.brick)
    if R.empty:
        print("no bricks — brick too large for the day's range"); return 1

    ups = int((R["dir"] == "up").sum()); dns = len(R) - ups
    lo, hi = float(R["bottom"].min()), float(R["top"].max())
    # swing volume (Weis on Renko): sum volume across runs of same-colour bricks
    R["swing"] = (R["dir"] != R["dir"].shift()).cumsum()
    swings = R.groupby("swing").agg(dir=("dir", "first"), vol=("vol", "sum"),
                                    b0=("bottom", "min"), b1=("top", "max"), n=("dir", "size"))

    print(f"\nRenko — {day} ({'ETH' if a.eth else 'RTH'}) · {a.brick:g}-pt bricks")
    print(f"  {len(R)} bricks ({ups} up / {dns} dn)  ·  {lo:.2f}–{hi:.2f}  ·  {len(swings)} swings")
    print(f"  up-brick vol {int(R[R.dir=='up'].vol.sum()):,}  |  dn-brick vol {int(R[R.dir=='dn'].vol.sum()):,}")

    # ---- chart: bricks + volume-per-brick ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(15, 8), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1.3]})
    for i, r in R.reset_index(drop=True).iterrows():
        up = r["dir"] == "up"
        c = "#26a69a" if up else "#ef5350"
        ax.add_patch(plt.Rectangle((i - 0.48, r["bottom"]), 0.96, a.brick,
                                    facecolor=c, edgecolor="white", lw=0.4))
    ax.set_xlim(-1, len(R)); ax.set_ylim(lo - a.brick, hi + a.brick)
    ax.axhline(lo, color="#c62828", lw=1.0, ls="--", label=f"low {lo:.2f}")
    ax.axhline(hi, color="#00897b", lw=1.0, ls="--", label=f"high {hi:.2f}")
    ax.set_ylabel("price"); ax.set_title(f"Renko — {day} ({'ETH' if a.eth else 'RTH'}) · {a.brick:g}-pt bricks", fontsize=11)
    ax.legend(loc="upper left", fontsize=8); ax.grid(axis="y", alpha=0.15)

    colors = ["#26a69a" if d == "up" else "#ef5350" for d in R["dir"]]
    axv.bar(range(len(R)), R["vol"], color=colors, width=0.9)
    axv.set_ylabel("brick vol"); axv.set_xlabel("brick #"); axv.grid(alpha=0.2)
    fig.tight_layout()
    png = OUT / f"renko_{day}_{'eth' if a.eth else 'rth'}_b{a.brick:g}.png"
    fig.savefig(png, dpi=110); plt.close(fig)
    print(f"\nchart: {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
