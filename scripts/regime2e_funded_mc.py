"""Funded-account: annual P&L at 1 ES + odds of blowing up (Apex trailing DD).

- Annual P&L: actual per-calendar-year net from the record, plus a block-bootstrap
  distribution of a simulated year (median / 10th / 90th / P(down year)).
- Blow odds: Monte-Carlo a FRESH funded account (starts at balance, floor = start−T)
  using a moving-block bootstrap of the daily returns (block=15d preserves streaks).
  Reports P(blow before the floor LOCKS at breakeven) and P(blow within 1 year).
  Once locked (after banking T+$100) you only blow by giving it all back to BE.

Mode one_per_day (recommended), ES $50/pt, net $17.50/trade. Plans: 150K T$5k / 250K T$6.5k / 300K T$7.5k.

  python scripts/regime2e_funded_mc.py
"""
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

MULT = 50.0; COST = 17.5
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"
PLANS = [("150K", 5000), ("250K", 6500), ("300K", 7500)]
RNG = np.random.default_rng(7)
NPATH = 20000; HORIZON = 252; BLOCK = 15


def daily_series(mode):
    path = Path(sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))[-1])
    df = pd.read_csv(path); df = df[df["mode"] == mode].copy()
    df["date"] = df["date"].astype(str)
    df["net_pts"] = df["pts"] - COST / MULT
    per = df.groupby("date")["net_pts"].sum() * MULT
    sess = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    lo, hi = per.index.min(), per.index.max()
    sess = [s for s in sess if lo <= s <= hi]
    s = pd.Series([per.get(d, 0.0) for d in sess], index=sess)
    return s


def boot_path(v, length):
    out = np.empty(length); i = 0
    while i < length:
        st = RNG.integers(0, len(v) - BLOCK)
        take = min(BLOCK, length - i)
        out[i:i + take] = v[st:st + take]
        i += take
    return out


def mc(v, T, size):
    blow_pre = 0; blow_yr = 0; locked_ct = 0; annual = np.empty(NPATH)
    for k in range(NPATH):
        path = boot_path(v, HORIZON) * size
        eq = 0.0; peak = 0.0; locked = False; blew = False
        for x in path:
            eq += x; peak = max(peak, eq)
            if not locked and peak >= T + 100:
                locked = True
            floor = 100.0 if locked else peak - T
            if eq <= floor:
                blew = True
                if not locked:
                    blow_pre += 1
                break
        if locked:
            locked_ct += 1
        if blew:
            blow_yr += 1
        annual[k] = eq
    return dict(blow_pre=blow_pre / NPATH, blow_yr=blow_yr / NPATH, locked=locked_ct / NPATH,
                med=np.median(annual), p10=np.percentile(annual, 10), p90=np.percentile(annual, 90),
                pneg=(annual < 0).mean())


def main():
    for mode in ["one_per_day", "flip"]:
        v = daily_series(mode).values
        yrs = len(v) / 252
        print("=" * 74)
        print(f"MODE {mode} — 1 ES realized ${v.sum():+,.0f} over {yrs:.1f}yr "
              f"= ${v.sum()/yrs:+,.0f}/yr avg")
        print("=" * 74)
        # actual per-calendar-year
        s = daily_series(mode)
        by_yr = pd.Series(s.values, index=pd.to_datetime(s.index)).groupby(lambda d: d.year).sum()
        print("  actual per year (1 ES, net): " + "  ".join(f"{y}:${p:+,.0f}" for y, p in by_yr.items()))
        print(f"\n  {'plan':>5} {'size':>4} | {'med yr$':>9} {'10th':>8} {'90th':>8} {'P(down yr)':>10} |"
              f" {'P(blow<lock)':>12} {'P(blow<1yr)':>11}")
        for name, T in PLANS:
            for size in (1, 2, 3):
                r = mc(v, T, size)
                print(f"  {name:>5} {size:>4} | ${r['med']:>+7,.0f} ${r['p10']:>+6,.0f} ${r['p90']:>+6,.0f} "
                      f"{100*r['pneg']:>9.0f}% | {100*r['blow_pre']:>11.1f}% {100*r['blow_yr']:>10.1f}%")
        print()


if __name__ == "__main__":
    main()
