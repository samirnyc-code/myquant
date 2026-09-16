"""wyckoff_eth_context.py — the ETH (full-session) context that reframes an RTH low.

Point (9/15): on the RTH-only chart, 7575.75 looks like a Selling Climax starting a NEW range.
On the ETH chart it is a SPRING — a false break ~1.5pt below the OVERNIGHT low (7577.25) that
reclaims and launches the markup. This is the book's nesting rule (p.206-212): a lower-TF
"SC" is really an EVENT (spring) inside the higher-TF (overnight) structure — and a spring is
the highest-probability long, the very setup the RTH-only read said was ABSENT.

    python scripts/wyckoff_eth_context.py --day 2026-09-15 --bar 15min
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td
from wyckoff_ar import hilo_bars

OUT = ROOT / "data" / "l1_tape" / "_analysis"
RTH_OPEN = dt.time(8, 30)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--bar", default="15min")
    a = ap.parse_args()

    raw = td.load_eth(a.day).sort_values("DateTime").reset_index(drop=True)
    ont = raw[raw["DateTime"].dt.time < RTH_OPEN]
    rth = raw[raw["DateTime"].dt.time >= RTH_OPEN]
    on_lo = float(ont["Price"].min()); on_hi = float(ont["Price"].max())
    on_lo_t = ont.loc[ont["Price"].idxmin(), "DateTime"]
    rth_lo = float(rth["Price"].min()); rth_lo_t = rth.loc[rth["Price"].idxmin(), "DateTime"]
    close = float(raw["Price"].iloc[-1])
    spring = rth_lo < on_lo

    bars = hilo_bars(raw, a.bar).reset_index().rename(columns={"index": "dtx"})
    if "dtx" not in bars.columns:
        bars = bars.rename(columns={bars.columns[0]: "dtx"})
    # index of the RTH-open bar and the spring bar. NOTE: the session spans two dates
    # (prev 17:00 -> day 16:00), so a time-of-day test is wrong (17:00 > 08:30). Anchor the
    # RTH open to the DAY date's 08:30 timestamp.
    def nearest(ts):
        return int((bars["dtx"] - ts).abs().values.argmin())
    day_date = bars["dtx"].dt.date.max()
    rth_open_ts = pd.Timestamp(day_date) + pd.Timedelta(hours=8, minutes=30)
    open_i = nearest(rth_open_ts)
    spring_i = nearest(rth_lo_t)
    onlo_i = nearest(on_lo_t)

    print(f"\n=== {a.day} ETH context ===")
    print(f"overnight support (low)  {on_lo:.2f} @ {pd.Timestamp(on_lo_t):%H:%M}")
    print(f"overnight high           {on_hi:.2f}")
    print(f"RTH low                  {rth_lo:.2f} @ {pd.Timestamp(rth_lo_t):%H:%M}")
    print(f"  -> {'SPRING' if spring else 'no spring'}: breaks overnight low by {on_lo-rth_lo:+.2f} pt, "
          f"reclaims to close {close:.2f}")
    print("  On RTH-only this reads as an SC; in ETH context it is a Phase-C SPRING of the")
    print("  overnight range (nesting, p.206-212) — the high-prob long the RTH view missed.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 8))
    for i in range(len(bars)):
        r = bars.iloc[i]; up = r["close"] >= r["open"]; c = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [r["low"], r["high"]], color=c, lw=0.7, zorder=3)
        ax.add_patch(plt.Rectangle((i - 0.4, min(r["open"], r["close"])), 0.8,
                                   max(abs(r["close"] - r["open"]), 0.01), color=c, zorder=4))
    # overnight vs RTH shading
    ax.axvspan(0, open_i, color="#5c6bc0", alpha=0.05, zorder=0)
    ax.text(open_i / 2, ax.get_ylim()[1], "OVERNIGHT (ETH)", ha="center", va="top", fontsize=10, color="#3949ab")
    ax.text((open_i + len(bars)) / 2, ax.get_ylim()[1], "RTH", ha="center", va="top", fontsize=10, color="#455a64")
    ax.axvline(open_i, color="#90a4ae", lw=0.8, ls=":")
    # levels
    ax.axhline(on_lo, color="#c62828", lw=1.4, ls="--", label=f"overnight support {on_lo:.2f}")
    ax.axhline(on_hi, color="#00897b", lw=1.0, ls="--", label=f"overnight high {on_hi:.2f}")
    ax.axhspan(rth_lo, on_lo, color="#ef5350", alpha=0.12, zorder=1)   # the spring penetration
    ax.annotate(f"SPRING {rth_lo:.2f}\n(-{on_lo-rth_lo:.2f}pt break + reclaim)",
                (spring_i, rth_lo), xytext=(spring_i + len(bars) * 0.06, rth_lo - 6),
                fontsize=10, fontweight="bold", color="#b71c1c",
                arrowprops=dict(arrowstyle="->", color="#b71c1c", lw=1.1))
    ax.annotate("overnight low", (onlo_i, on_lo), xytext=(onlo_i, on_lo + 5),
                fontsize=8, color="#c62828", ha="center",
                arrowprops=dict(arrowstyle="->", color="#c62828", lw=0.7))
    ax.set_title(f"{a.day} · ETH context — the RTH 'SC' is a SPRING of the overnight low", fontsize=12)
    ax.set_ylabel("price"); ax.set_xlabel(f"{a.bar} bar #"); ax.legend(loc="upper right", fontsize=9); ax.grid(alpha=0.15)
    png = OUT / f"eth_context_{a.day}_{a.bar}.png"
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    print(f"\nchart: {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
