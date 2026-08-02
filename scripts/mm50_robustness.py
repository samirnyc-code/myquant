#!/usr/bin/env python
"""mm50_robustness.py — S92-EA: is the 50% MM result a cross-day/overnight-gap artifact?

Classifies every trade from halsey_mm50_engine.py by how faithful it is to an intraday,
flat-EOD, single-session DH workflow, and reports expectancy for each class so we can see
whether the apparent edge survives when we keep ONLY clean intraday trades.

Classes:
  leg_sameday   : swing L and swing H are in the SAME RTH day (leg didn't span the gap)
  entry_sameday : the 50% fill is on the SAME day the leg confirmed
  fully_intraday: leg_sameday AND entry_sameday AND exit same day
"""
from __future__ import annotations

from pathlib import Path
import glob as _glob
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
sys.path.insert(0, str(ROOT / "scripts"))
from halsey_mm50_engine import build_15m  # noqa: E402


def st(d):
    if not len(d):
        return "n=0"
    w = d[d.R > 0].R.sum(); l = -d[d.R < 0].R.sum()
    pf = w / l if l else np.inf
    yr = d.groupby("year").R.mean()
    return (f"n={len(d):5d}  win={100*(d.R>0).mean():4.1f}%  exp={d.R.mean():+.3f}R  "
            f"PF={pf:4.2f}  years+={int((yr>0).sum())}/{len(yr)}  "
            f"$/t={50*(d.R*d.risk_pts).mean():+.0f}")


def main():
    g = build_15m().reset_index(drop=True)
    day = g["day"]
    tr = pd.read_csv(sorted(_glob.glob(str(MASTER_DIR / "mm50_trades_*.csv")))[-1])
    tr["dt"] = pd.to_datetime(tr["dt"])
    dcol = day.to_numpy()
    tr["leg_sameday"] = [dcol[int(a)] == dcol[int(b)] for a, b in zip(tr.jL, tr.jH)]
    tr["entry_sameday"] = [dcol[int(c)] == dcol[int(f)] for c, f in zip(tr.conf, tr.fill)]
    tr["exit_sameday"] = [dcol[int(f)] == dcol[int(e)] for f, e in zip(tr.fill, tr.exit)]
    tr["fully_intraday"] = tr.leg_sameday & tr.entry_sameday & tr.exit_sameday

    for N in sorted(tr.N.unique()):
        d = tr[tr.N == N]
        print(f"\n===== fractal N={N}  (total {len(d)} trades) =====")
        print(f"  ALL            : {st(d)}")
        print(f"  leg_sameday    : {st(d[d.leg_sameday])}   ({100*d.leg_sameday.mean():.0f}% of trades)")
        print(f"  entry_sameday  : {st(d[d.entry_sameday])}")
        print(f"  FULLY intraday : {st(d[d.fully_intraday])}   ({100*d.fully_intraday.mean():.0f}% of trades)")
        print(f"  cross-day only : {st(d[~d.fully_intraday])}")
    print("\nIf the edge lives mostly in cross-day trades, it's an overnight-gap artifact, "
          "not DH's intraday method. If FULLY-intraday holds up, it's worth a faithful 24H rebuild.")


if __name__ == "__main__":
    main()
