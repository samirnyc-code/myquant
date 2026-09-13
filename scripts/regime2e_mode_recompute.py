"""Recompute the mode-sweep on the CORRECT static DD (floor = start - $4,500, EOD,
does NOT trail). Reads the model-independent per-trade CSV from regime2e_mode_sweep.

  python scripts/regime2e_mode_recompute.py [mode_sweep_csv]
"""
import sys
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

DD = 4500.0; SUB = 200.0
OUTDIR = Path(__file__).resolve().parent.parent / "reports" / "regime2e"
MODES = ["flip", "ignore", "close_reenter", "close_done", "one_per_day"]


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def acct(daily, mult, base, step):
    eq = 0.0; size = base; blown = None; min_eq = 0.0; sub = 0.0; pm = None
    for d, p1 in daily.items():
        m = d[:7]
        if m != pm:
            sub += SUB; pm = m
        size = min(15, base + int(max(eq, 0) // step)) if step else base
        eq += p1 * mult * size
        min_eq = min(min_eq, eq)
        if blown is None and eq <= -DD:
            blown = d
    return eq, eq - sub, min_eq, blown, size


def main():
    csvs = sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(csvs[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    print(f"{path.name}\nStatic DD floor = start - $4,500 (EOD, fixed).\n")
    for inst, mult, cost in (("MES", 5.0, 6.25), ("ES", 50.0, 17.5)):
        print("=" * 96)
        print(f"{inst} (${mult:.0f}/pt) — 1 contract fixed, then 1c +1/$20k ladder")
        print("=" * 96)
        print(f"{'mode':14} {'n':>4} {'net$':>9} {'PF':>5} {'win%':>4} "
              f"{'deepestEOD':>10} {'1c take$':>9} | {'ladder take$':>12} {'endc':>4} survive?")
        for m in MODES:
            g = df[df["mode"] == m]
            if g.empty:
                continue
            g = g.assign(net_pts=g["pts"] - cost / mult)
            daily = g.groupby("date")["net_pts"].sum()
            v = g["net_pts"].values * mult
            eq1, take1, min1, blown1, _ = acct(daily, mult, 1, 0)
            eqL, takeL, minL, blownL, endc = acct(daily, mult, 1, 20000)
            s1 = f"BLOWN {blown1}" if blown1 else "ok"
            print(f"{m:14} {len(g):>4} {v.sum():>+9,.0f} {pf(g.net_pts.values):>5.2f} "
                  f"{100*(v>0).mean():>4.0f} {min1:>+10,.0f} {take1:>+9,.0f} | "
                  f"{takeL:>+12,.0f} {endc:>3}c  {s1}")
    print("\n(deepestEOD = lowest the account ever closed below start; survives if > -$4,500)")


if __name__ == "__main__":
    main()
