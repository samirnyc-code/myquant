"""flex_renko_wick_check.py — does the VERIFIED flex_renko() engine actually produce
Sierra-style doji/long-wick bricks on real ES ticks, or is that absent even here?

Debugging aid for the NT8 FlexRenkoBarsType.cs port (S141): the user's live NT8 chart shows
near-zero wicks (solid blocky bricks) vs. a Sierra Chart reference screenshot full of
doji-looking bricks (tiny body, long wick) in a chop/consolidation zone. Since the NT8 port's
algorithm was just matched line-for-line to scripts/renko.py::flex_renko (same open-offset
formulas, same wick-excursion tracking), running the ALREADY-VERIFIED Python engine on real
ES ticks answers: is "mostly no visible wick" a property of the algorithm itself on this
instrument, or does the NT8 port have a real bug the Python reference doesn't?

    python scripts/flex_renko_wick_check.py --day 2026-09-15 --box 16 --trend 8 --rev 4
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td
from renko import flex_renko

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default=None)
    ap.add_argument("--box", type=int, default=16)
    ap.add_argument("--trend", type=int, default=8)
    ap.add_argument("--rev", type=int, default=4)
    ap.add_argument("--eth", action="store_true")
    a = ap.parse_args()

    day = a.day or td.available("eth" if a.eth else "rth")[-1]
    raw = td.load_eth(day) if a.eth else td.load_rth(day)
    R = flex_renko(raw, a.box, a.trend, a.rev)
    if R.empty:
        print("no bricks produced"); return 1

    body = (R["top"] - R["bottom"]).to_numpy()
    full_range = (R["whi"] - R["wlo"]).to_numpy()
    wick = full_range - body
    box_pts = a.box * 0.25

    print(f"day={day} box={a.box} trend={a.trend} rev={a.rev} (box={box_pts}pt)  n_bricks={len(R)}")
    print(f"body:  all == box size ({box_pts}pt)? {np.allclose(body, box_pts)}  "
          f"min={body.min():.2f} max={body.max():.2f}")
    print(f"wick (full range - body), in points:")
    print(f"  mean={wick.mean():.3f}  median={np.median(wick):.3f}  max={wick.max():.2f}  "
          f"p90={np.percentile(wick, 90):.3f}")
    print(f"  bricks with ZERO wick (wlo==bottom and whi==top): {int((wick <= 1e-9).sum())} / {len(R)} "
          f"({100*(wick <= 1e-9).mean():.1f}%)")
    print(f"  bricks with wick >= 1x box size (doji-ish, wick dominates body): "
          f"{int((wick >= box_pts).sum())} / {len(R)} ({100*(wick >= box_pts).mean():.1f}%)")

    dump = OUT / f"flex_renko_wickcheck_{day}_{a.box}-{a.trend}-{a.rev}.csv"
    dump.parent.mkdir(parents=True, exist_ok=True)
    R.assign(body=body, full_range=full_range, wick=wick).to_csv(dump, index=False)
    print(f"-> {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
