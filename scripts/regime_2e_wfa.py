"""WALK-FORWARD ANALYSIS — fit params on EARLY data, test FORWARD. Consumes the enriched
oos_pertrade CSV (per-trade MAE + EOD-move) so ANY stop mult / window / side is re-derived
exactly in-memory: net(S) = -S if mae_pts>=S else eod_move  (x$50, - $5 RT - 1t slip).

Experiments:
  A. Train on 2010-2011 ONLY, pick best params, test 2012-2026 (the 'use early data' ask).
  B. Anchored WFA: expanding train (all prior years), 1-yr test, roll 2012->2026.
  C. Rolling WFA: 3-yr train / 1-yr test, roll.
  Baseline: FIXED frozen params (m=0.30, both sides, h09-13) over the same OOS spans.

Grid: stop mult m in {.15,.20,.25,.30,.40,.50}; side in {both,long_only,short_only};
window in {09-13, 09-11, 09-12, 10-13}. Gate always with-trend. Objective = train net,
guard n>=40. All books are the gated with-trend book.

  python scripts/regime_2e_wfa.py
"""
import sys, itertools
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_20260725.csv"

WINDOWS = {"09-13": {"09", "10", "11", "12", "13"}, "09-11": {"09", "10", "11"},
           "09-12": {"09", "10", "11", "12"}, "10-13": {"10", "11", "12", "13"}}
MULTS = [.15, .20, .25, .30, .40, .50]
SIDES = {"both": {"L", "S"}, "long": {"L"}, "short": {"S"}}
GRID = list(itertools.product(MULTS, SIDES.keys(), WINDOWS.keys()))


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def net_of(sub, m, side, win):
    """Vectorized net for the gated book under (mult, side, window)."""
    d = sub[sub.dir.isin(SIDES[side]) & sub.fill_hour.astype(str).str.zfill(2).isin(WINDOWS[win])]
    if not len(d):
        return np.array([])
    S = np.maximum(np.round(m * d.adr.values / TICK) * TICK, FLOOR)
    stopped = d.mae_pts.values >= S
    move = np.where(stopped, -S, d.eod_move.values)
    return move * PT - COMM - SLIP


def best_params(train):
    best, bkey = -1e18, None
    for (m, side, win) in GRID:
        v = net_of(train, m, side, win)
        if len(v) >= 40 and v.sum() > best:
            best, bkey = v.sum(), (m, side, win)
    return bkey


def report(name, oos_net, extra=""):
    v = np.asarray(oos_net, float)
    if not len(v):
        print(f"{name:<34} (empty)"); return
    print(f"{name:<34} n={len(v):5d}  net {v.sum():+9,.0f}  $/tr {v.mean():+6.1f}  PF {pf(v):4.2f}  "
          f"win {100*(v>0).mean():4.1f}% {extra}")


def main():
    df = pd.read_csv(CSV)
    g = df[df.with_trend].copy()          # gated with-trend book
    years = sorted(g.yr.unique())
    FROZEN = (0.30, "both", "09-13")

    print("========== A. TRAIN on 2010-2011, TEST forward 2012-2026 ==========")
    train = g[g.yr <= 2011]; test = g[g.yr >= 2012]
    bp = best_params(train)
    print(f"best params on 2010-2011 (max train net, n>=40): m={bp[0]} side={bp[1]} window={bp[2]}")
    report("  train 2010-2011 (in-sample)", net_of(train, *bp))
    report("  TEST 2012-2026 (OOS, chosen)", net_of(test, *bp))
    report("  TEST 2012-2026 (frozen 0.30/both/09-13)", net_of(test, *FROZEN))
    # per-year OOS under chosen params
    print("  chosen-param OOS by year:")
    for y in [yy for yy in years if yy >= 2012]:
        report(f"     {y}", net_of(g[g.yr == y], *bp))

    print("\n========== B. ANCHORED WFA (expanding train, 1-yr test, roll) ==========")
    oos_chosen, oos_frozen, picks = [], [], []
    for y in [yy for yy in years if yy >= 2012]:
        train = g[g.yr < y]; test = g[g.yr == y]
        bp = best_params(train)
        if bp is None:
            continue
        oos_chosen.append(net_of(test, *bp)); oos_frozen.append(net_of(test, *FROZEN))
        picks.append((y, bp, net_of(test, *bp).sum()))
    print("  per-year picks (year: params -> OOS net):")
    for (y, bp, nt) in picks:
        print(f"     {y}: m={bp[0]} {bp[1]:<5} {bp[2]}  -> {nt:+,.0f}")
    report("  ANCHORED WFA stitched OOS", np.concatenate(oos_chosen))
    report("  FROZEN over same span", np.concatenate(oos_frozen))

    print("\n========== C. ROLLING WFA (3-yr train, 1-yr test, roll) ==========")
    oos_roll = []
    for y in [yy for yy in years if yy >= 2013]:
        train = g[(g.yr >= y - 3) & (g.yr < y)]; test = g[g.yr == y]
        bp = best_params(train)
        if bp is None:
            continue
        oos_roll.append(net_of(test, *bp))
    report("  ROLLING WFA stitched OOS (2013-2026)", np.concatenate(oos_roll))

    print("\n========== D. reference: FIXED frozen over full 2010-2026 & sub-spans ==========")
    report("  frozen 2010-2026", net_of(g, *FROZEN))
    report("  frozen 2010-2020", net_of(g[g.yr <= 2020], *FROZEN))
    report("  frozen 2021-2026", net_of(g[g.yr >= 2021], *FROZEN))


if __name__ == "__main__":
    main()
