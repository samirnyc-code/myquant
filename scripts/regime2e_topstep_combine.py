"""Topstep TRADING COMBINE (evaluation): how long to pass + odds, for Regime2E.

Combine rules (scraped/verified): targets $3,000 / $6,000 / $9,000 for 50K/100K/150K;
Maximum Loss Limit (EOD trailing) $2,000 / $3,000 / $4,500; consistency = best single
day <= 50% of profit target (else the target rises to best_day / 0.50); no minimum
trading days (removed). MLL locks once it reaches the starting balance.

For every possible START session we count TRADING DAYS until cumulative profit reaches
the (consistency-adjusted) target WITHOUT the EOD balance touching the MLL floor.
pass% = fraction of starts that pass before blowing / running out of record.
Daily-realized model (matches regime2e_time_to_goal): the Combine checks the EOD
balance; a rare intraday MLL touch is not modeled (would only lower pass% slightly).

MES fractional sizing: size in ES-equivalents (0.1 ES = 1 MES).

  python scripts/regime2e_topstep_combine.py
"""
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

MULT = 50.0; COST = 17.5
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"
# (name, target, MLL)
PLANS = [("50K", 3000, 2000), ("100K", 6000, 3000), ("150K", 9000, 4500)]
SIZES = [0.3, 0.5, 0.7, 1.0, 1.5, 2.0]


def daily_1c():
    path = Path(sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))[-1])
    df = pd.read_csv(path); df = df[df["mode"] == "one_per_day"].copy()
    df["date"] = df["date"].astype(str)
    df["net_pts"] = df["pts"] - COST / MULT
    per = df.groupby("date")["net_pts"].sum() * MULT
    sess = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    lo, hi = per.index.min(), per.index.max()
    sess = [s for s in sess if lo <= s <= hi]
    return pd.Series([per.get(s, 0.0) for s in sess], index=sess)


def time_to_pass(daily, target, T, size):
    """EOD trailing (lock at start), consistency: best day <= 50% of effective target."""
    v = daily.values * size
    n = len(v); days = []; blew = 0
    for i in range(n):
        eq = 0.0; peak = 0.0; best_day = 0.0; hit = None
        for j in range(i, n):
            eq += v[j]; peak = max(peak, eq)
            best_day = max(best_day, v[j])
            floor = min(peak - T, 0.0)          # EOD trailing, locks at start
            if eq <= floor:
                blew += 1; break
            eff_target = max(target, 2.0 * best_day)   # consistency-adjusted
            if eq >= eff_target:
                hit = j - i + 1; break
        if hit is not None:
            days.append(hit)
    censored = n - len(days) - blew
    return days, blew, n, censored


def main():
    daily = daily_1c()
    yr = daily.sum() / (len(daily) / 252)
    print(f"TOPSTEP COMBINE — Regime2E one_per_day, {len(daily)} sessions "
          f"{daily.index.min()}->{daily.index.max()}, 1 ES ~${yr:,.0f}/yr")
    print("EOD trailing DD, consistency (best day <=50% of target), MES sizes (0.1ES=1MES)\n")
    for name, target, T in PLANS:
        print(f"=== {name}: target ${target:,} · MLL ${T:,} ===")
        print(f"  {'ES':>4} {'MES':>4} {'median':>8} {'25th':>6} {'75th':>6}  "
              f"{'pass-odds':>9} {'blow%':>6}  (pass-odds = pass/(pass+blow), ex-censored)")
        for s in SIZES:
            days, blew, n, cens = time_to_pass(daily, target, T, s)
            if not days:
                print(f"  {s:>4.1f} {int(s*10):>4}   (never reached without blowing)")
                continue
            d = np.array(days)
            resolved = len(d) + blew
            odds = 100.0 * len(d) / resolved if resolved else 0.0
            print(f"  {s:>4.1f} {int(s*10):>4} {int(np.median(d)):>6}d {int(np.percentile(d,25)):>4}d "
                  f"{int(np.percentile(d,75)):>4}d  {odds:>7.0f}% {100.0*blew/n:>5.0f}%"
                  f"  (~{np.median(d)/21:.1f}mo median)")
        print()


if __name__ == "__main__":
    main()
