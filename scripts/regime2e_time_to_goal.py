"""How long to reach each Apex eval profit goal? Empirical, from the 5-yr record.

Walks EVERY possible start session and counts TRADING DAYS until cumulative profit
reaches the goal (applying the Apex EOD trailing DD so blow-during-eval counts as a
fail, not a pass). Reports the distribution (median / 25th / 75th / worst) because
the book is lumpy — a fast start and a slow start differ a lot.

Plans: 150K goal $9,000 (eval contract cap 8) · 250K $15,000 (13) · 300K $20,000 (17).
Mode: one_per_day (recommended). ES $50/pt, net $17.50/trade. Threshold locks per Apex.

  python scripts/regime2e_time_to_goal.py
"""
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

MULT = 50.0; COST = 17.5
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"
# plan: (name, goal, threshold, eval contract cap = half of full)
PLANS = [("150K", 9000, 5000, 8), ("250K", 15000, 6500, 13), ("300K", 20000, 7500, 17)]
SIZES = [1, 2, 3, 5, 8]


def daily_1c():
    path = Path(sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))[-1])
    df = pd.read_csv(path); df = df[df["mode"] == "one_per_day"].copy()
    df["date"] = df["date"].astype(str)
    df["net_pts"] = df["pts"] - COST / MULT
    per = df.groupby("date")["net_pts"].sum() * MULT      # $ per date at 1 ES
    # full session calendar (incl. no-trade days) from the trove, over the traded span
    sess = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    lo, hi = per.index.min(), per.index.max()
    sess = [s for s in sess if lo <= s <= hi]
    return pd.Series([per.get(s, 0.0) for s in sess], index=sess)


def time_to_goal(daily, goal, T, size):
    """For each start, trading-days to reach goal at `size` contracts under Apex EOD DD.
    Returns list of day-counts for starts that PASSED (blow/never excluded)."""
    v = daily.values * size
    n = len(v); days = []; blew = 0; never = 0
    for i in range(n):
        eq = 0.0; peak = 0.0; locked = False; hit = None
        for j in range(i, n):
            eq += v[j]; peak = max(peak, eq)
            if not locked and peak >= T + 100:
                locked = True
            floor = 100.0 if locked else peak - T
            if eq <= floor:
                blew += 1; break
            if eq >= goal:
                hit = j - i + 1; break
        if hit is not None:
            days.append(hit)
        elif blew and j == n - 1 and eq > floor and eq < goal:
            never += 1
    return days, blew, n


def main():
    daily = daily_1c()
    print(f"one_per_day, {len(daily)} sessions {daily.index.min()}→{daily.index.max()}, "
          f"1 ES ~${daily.sum()/ (len(daily)/252):,.0f}/yr\n")
    for name, goal, T, cap in PLANS:
        print(f"=== {name}: goal ${goal:,} · DD ${T:,} · eval cap {cap} ES ===")
        print(f"  {'size':>4} {'median':>8} {'25th':>6} {'75th':>6} {'worst':>7}  {'pass%':>6}")
        for size in SIZES:
            if size > cap:
                continue
            days, blew, n = time_to_goal(daily, goal, T, size)
            if not days:
                print(f"  {size:>4}   (never reached without blowing)")
                continue
            d = np.array(days)
            passpct = 100.0 * len(d) / n
            def wk(x): return x / 5.0
            print(f"  {size:>4} {int(np.median(d)):>6}d  {int(np.percentile(d,25)):>4}d {int(np.percentile(d,75)):>4}d "
                  f"{int(d.max()):>5}d  {passpct:>5.0f}%   (~{np.median(d)/21:.1f} mo median)")
        print()


if __name__ == "__main__":
    main()
