"""
Idea — FIRST breakout-of-structure of the day. The last clean directional test.

Build the opening swing range from the first up-leg pivot (initial HIGH) and the
first down-leg pivot (initial LOW). The FIRST leg whose pivot breaks beyond that
range is the day's first BOS; its direction is the candidate signal.

Question: after the first BOS (say up, at price P, time T), does the day CLOSE
beyond P in that direction (continuation), or does the breakout fail as often as
it runs? If continuation ~ 50% and mean go-with return ~ 0, legs have no
directional edge and the question is closed. If it's clearly > / < 50%, there's a
join / fade edge.

Reads via leg_engine. Writes dated CSV + summary + chart.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leg_engine import load_bars, daily_table, legs_for_day, iter_days

OUTDIR = Path(__file__).resolve().parents[2] / "leglab" / "outputs"
RUN = "20260906"


def first_bos(legs):
    """Return (dir, leg_index, pivot_price) of the first structural break, or None."""
    hi = lo = None
    for k, lg in enumerate(legs):
        p = lg["p1"]
        if lg["dir"] == 1:
            if hi is None:
                hi = p
            elif lo is not None and p > hi:
                return (1, k, hi)      # broke above the opening-swing high
            else:
                hi = max(hi, p)
        else:
            if lo is None:
                lo = p
            elif hi is not None and p < lo:
                return (-1, k, lo)     # broke below the opening-swing low
            else:
                lo = min(lo, p)
    return None


def main():
    df = load_bars()
    daily = daily_table(df)
    rows = []
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); c = g["Close"].to_numpy(); t = g["DateTime"].to_numpy()
        adr = float(daily.loc[date, "adr"])
        if adr <= 0:
            continue
        legs = [lg for lg in legs_for_day(o, h, l, t, thr) if lg["closed"]]
        if len(legs) < 3:
            continue
        fb = first_bos(legs)
        if fb is None:
            continue
        d, k, brk = fb
        n = len(g)
        # bar index where the breakout level was crossed: use the leg's end bar
        bar = legs[k]["i1"]
        d_open, d_close = o[0], c[-1]
        d_high, d_low = h.max(), l.min()
        rng = d_high - d_low
        rows.append({
            "date": date, "bos_dir": d, "bos_bar": bar, "bos_frac": bar / n,
            "bos_price": brk, "adr": adr,
            # continuation: did the day close beyond the breakout level, in the BOS direction?
            "cont": int(np.sign(d_close - brk) == d) if d_close != brk else 0,
            # go-with return from the breakout level to the close, ADR units
            "gowith_adr": (d_close - brk) * d / adr,
            # does the close agree with the BOS direction (vs the open)?
            "daydir_match": int(np.sign(d_close - d_open) == d) if d_close != d_open else 0,
            "close_loc": (d_close - d_low) / rng if rng > 0 else 0.5,
        })

    R = pd.DataFrame(rows)
    R.to_csv(OUTDIR / f"leg_first_bos_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    p(f"First breakout-of-structure of the day — ES 5M RTH, n={len(R)} days\n")
    up = (R["bos_dir"] == 1).mean()
    p(f"first BOS direction: {up*100:.1f}% up / {(1-up)*100:.1f}% down")
    p(f"first BOS timing: median bar {R['bos_bar'].median():.0f} "
      f"({R['bos_frac'].median()*100:.0f}% into the day)\n")

    p("DIRECTIONAL EDGE (the question):")
    p(f"  P(close continues past the breakout level, in BOS dir) = {R['cont'].mean():.3f}")
    p(f"  P(day close agrees with BOS direction)                 = {R['daydir_match'].mean():.3f}")
    p(f"  mean go-with return (breakout->close, ADR units)       = {R['gowith_adr'].mean():+.3f}")
    p(f"  median go-with return (ADR)                            = {R['gowith_adr'].median():+.3f}")
    p("  (~0.50 and ~0.00 => breakouts fail as often as they run => NO directional edge)\n")

    # split up vs down
    p("Split by first-BOS direction:")
    sp = R.groupby("bos_dir").agg(
        n=("cont", "size"), cont=("cont", "mean"),
        daydir=("daydir_match", "mean"), gowith_adr=("gowith_adr", "mean"),
    ).round(3)
    sp.index = ["first BOS DOWN", "first BOS UP"]
    p(sp.to_string())

    # split by timing (early vs late first BOS)
    R["timing"] = pd.qcut(R["bos_frac"], 4, labels=["earliest", "early", "late", "latest"])
    p("\nBy first-BOS timing (does an early break predict better?):")
    tm = R.groupby("timing", observed=True).agg(
        n=("cont", "size"), cont=("cont", "mean"),
        gowith_adr=("gowith_adr", "mean"), close_loc=("close_loc", "mean"),
    ).round(3)
    p(tm.to_string())

    # chart
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    ax[0].bar(["continues\npast breakout", "close agrees\nw/ BOS dir"],
              [R["cont"].mean(), R["daydir_match"].mean()], color=["#2b7a3f", "#2b5fa8"])
    ax[0].axhline(0.5, color="k", ls="--", lw=1, label="coin flip")
    ax[0].set_ylim(0, 0.7); ax[0].set_ylabel("probability")
    ax[0].set_title("Does the first breakout predict the day?"); ax[0].legend()
    ax[0].grid(axis="y", alpha=0.3)
    ax[1].bar(tm.index.astype(str), tm["gowith_adr"], color="#e08a2b")
    ax[1].axhline(0, color="k", lw=1)
    ax[1].set_ylabel("mean go-with return (ADR)")
    ax[1].set_title("Go-with return by breakout timing"); ax[1].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab — first breakout-of-structure of the day (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"leg_first_bos_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_first_bos_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
