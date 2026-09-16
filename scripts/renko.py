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
from wyckoff_ar import ar_levels

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def build_renko(df: pd.DataFrame, brick: float) -> pd.DataFrame:
    """Classic Renko + WICKS. Pure Renko has no tails (a brick is a fixed block), which HIDES
    real extremes — e.g. a spring that pokes below support but doesn't complete a brick just
    vanishes. So we also track the price excursion during each brick's formation and expose it
    as wlo/whi: the first brick of a move carries the counter-excursion wick (the low it dipped
    to before an up-brick completed, or the high before a down-brick). That is where springs
    and upthrusts show up."""
    d = df.sort_values("DateTime").reset_index(drop=True)
    price = d["Price"].to_numpy()
    vol = d["Volume"].to_numpy()
    times = d["DateTime"].to_numpy()
    base = round(price[0] / brick) * brick        # snap the first brick to the grid
    bricks = []
    accum = 0.0
    hi_since = lo_since = price[0]                 # price excursion since the last brick printed
    for i in range(len(price)):
        accum += vol[i]
        if price[i] > hi_since: hi_since = price[i]
        if price[i] < lo_since: lo_since = price[i]
        pend = []
        while price[i] >= base + brick:
            base += brick; pend.append(("up", base - brick, base))
        while price[i] <= base - brick:
            base -= brick; pend.append(("dn", base, base + brick))
        if pend:
            per = accum / len(pend)
            for k, (direction, bottom, top) in enumerate(pend):
                # only the FIRST brick of the group carries the pre-move excursion wick
                wlo = min(lo_since, bottom) if k == 0 else bottom
                whi = max(hi_since, top) if k == 0 else top
                bricks.append(dict(dir=direction, bottom=bottom, top=top,
                                   wlo=wlo, whi=whi, vol=int(per), t=times[i]))
            accum = 0.0
            hi_since = lo_since = price[i]         # reset excursion from this completion point
    return pd.DataFrame(bricks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--brick", type=float, default=5.0, help="brick size in points")
    ap.add_argument("--eth", action="store_true")
    ap.add_argument("--dump", action="store_true", help="print every brick + INDEPENDENTLY verify each wick against the raw tape")
    a = ap.parse_args()

    day = a.day or td.available("eth" if a.eth else "rth")[-1]
    raw = td.load_eth(day) if a.eth else td.load_rth(day)
    R = build_renko(raw, a.brick)
    if R.empty:
        print("no bricks — brick too large for the day's range"); return 1

    if a.dump:
        # PROVE the wicks are data-derived, not invented: recompute each brick's excursion
        # STRAIGHT from the raw ticks in that brick's time window and compare to wlo/whi.
        rr = raw.sort_values("DateTime").reset_index(drop=True)
        print(f"{'#':>4}{'dir':>4}{'bottom':>9}{'top':>9}{'wlo':>9}{'whi':>9}   raw-tick check in window")
        prev_t = rr["DateTime"].iloc[0]
        bad = 0
        for i, r in R.reset_index(drop=True).iterrows():
            win = rr[(rr["DateTime"] > prev_t) & (rr["DateTime"] <= r["t"])]
            raw_lo = float(win["Price"].min()) if len(win) else r["bottom"]
            raw_hi = float(win["Price"].max()) if len(win) else r["top"]
            # the wick must equal the raw excursion clamped by the body (first-brick logic)
            exp_wlo = min(raw_lo, r["bottom"]); exp_whi = max(raw_hi, r["top"])
            ok = abs(exp_wlo - r["wlo"]) < 1e-6 and abs(exp_whi - r["whi"]) < 1e-6
            if not ok: bad += 1
            if i < 40 or not ok:
                print(f"{i:>4}{r['dir']:>4}{r['bottom']:>9.2f}{r['top']:>9.2f}{r['wlo']:>9.2f}{r['whi']:>9.2f}"
                      f"   raw {raw_lo:.2f}-{raw_hi:.2f}  {'OK' if ok else 'MISMATCH'}")
            prev_t = r["t"]
        print(f"\n{len(R)-bad}/{len(R)} bricks: wick == independent raw-tape excursion  ({'ALL VERIFIED' if bad==0 else str(bad)+' MISMATCH'})")
        return 0

    ups = int((R["dir"] == "up").sum()); dns = len(R) - ups
    lo, hi = float(R["bottom"].min()), float(R["top"].max())
    true_lo, true_hi = float(R["wlo"].min()), float(R["whi"].max())   # incl. wick excursions
    # swing volume (Weis on Renko): sum volume across runs of same-colour bricks
    R["swing"] = (R["dir"] != R["dir"].shift()).cumsum()
    swings = R.groupby("swing").agg(dir=("dir", "first"), vol=("vol", "sum"),
                                    b0=("bottom", "min"), b1=("top", "max"), n=("dir", "size"))

    print(f"\nRenko — {day} ({'ETH' if a.eth else 'RTH'}) · {a.brick:g}-pt bricks")
    print(f"  {len(R)} bricks ({ups} up / {dns} dn)  ·  brick body {lo:.2f}-{hi:.2f}  ·  {len(swings)} swings")
    print(f"  TRUE extremes incl wicks: {true_lo:.2f}-{true_hi:.2f}  "
          f"(pure Renko would hide the {true_lo:.2f} low)")
    print(f"  up-brick vol {int(R[R.dir=='up'].vol.sum()):,}  |  dn-brick vol {int(R[R.dir=='dn'].vol.sum()):,}")

    # ---- chart: bricks + volume-per-brick ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig_w = min(40, max(14, len(R) * 0.22))          # scale width to brick count (thin bricks)
    fig, (ax, axv) = plt.subplots(2, 1, figsize=(fig_w, 8), sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1.3]})
    for i, r in R.reset_index(drop=True).iterrows():
        up = r["dir"] == "up"
        c = "#26a69a" if up else "#ef5350"
        # wick = intrabar excursion beyond the brick body (this is where springs/upthrusts show)
        ax.plot([i, i], [r["wlo"], r["whi"]], color="#455a64", lw=0.6, zorder=2)
        ax.add_patch(plt.Rectangle((i - 0.30, r["bottom"]), 0.60, a.brick,
                                    facecolor=c, edgecolor="white", lw=0.5, zorder=3))
    ax.set_xlim(-1, len(R)); ax.set_ylim(true_lo - 1, true_hi + 1)
    # reference lines = the TRUE wick extremes (not the brick-body min/max), so the lines match
    # what the wicks actually reach. Brick-body edges drawn faint for contrast.
    ax.axhline(true_lo, color="#c62828", lw=1.2, ls="--", label=f"true low {true_lo:.2f} (wick)")
    ax.axhline(true_hi, color="#00897b", lw=1.2, ls="--", label=f"true high {true_hi:.2f} (wick)")
    ax.axhline(lo, color="#c62828", lw=0.6, ls=":", alpha=0.5, label=f"brick body {lo:.0f}")
    ax.axhline(hi, color="#00897b", lw=0.6, ls=":", alpha=0.5, label=f"brick body {hi:.0f}")
    # AR RANGE box (SC low -> AR high, derived on the 5M context) shaded across the chart
    sc_low, ar_hi, _ = ar_levels(raw)
    if ar_hi:
        ax.axhspan(sc_low, ar_hi, color="#1e88e5", alpha=0.13, zorder=1,
                   label=f"AR range {sc_low:.2f}-{ar_hi:.2f}")
        ax.axhline(ar_hi, color="#1565c0", lw=1.3, ls="-.")
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
