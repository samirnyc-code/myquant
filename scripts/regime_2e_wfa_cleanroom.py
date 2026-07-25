"""CLEAN-ROOM WFA from 2010 — re-optimize the 4 main P&L levers (gap threshold, stop mult,
TOD window, side) walk-forward with ZERO 2021-era priors, objective in scale-free R.

Answers the honest question: if you'd started in 2010 and only ever optimized on data you'd
already seen, would this strategy have made money going forward? Reports stitched OOS in BOTH
R and $, the per-year parameter picks (stable = robust; thrashing = overfit noise), vs the
frozen 2021-tuned config over the same span.

NOT varied (these DEFINE the second-entry strategy, not free knobs): the tick phase-machine
regime gate, 2E entry count, the 6t retest limit, EOD hold. Only the 4 levers above move.

Reads oos_pertrade_full_20260725.csv (ALL days, gap per trade -> gap threshold is free).

  python scripts/regime_2e_wfa_cleanroom.py
Output: data/regime/wfa_cleanroom_20260725.csv (per-year picks) + tables.
"""
import sys, itertools
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"

GAPS = [0.30, 0.40, 0.54, 0.75, 1.00, 99.0]
MULTS = [0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
WINS = {"09-13": {9, 10, 11, 12, 13}, "09-11": {9, 10, 11}, "09-12": {9, 10, 11, 12}, "10-13": {10, 11, 12, 13}}
SIDES = {"both": {"L", "S"}, "long": {"L"}, "short": {"S"}}
GRID = list(itertools.product(GAPS, MULTS, WINS.keys(), SIDES.keys()))


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def evaluate(d, gap, mult, win, side):
    """return (net_array, R_array) for the gated book under the 4 levers."""
    m = d[(d.gap <= gap) & d.dir.isin(SIDES[side]) & d.fh.isin(WINS[win])]
    if not len(m):
        return np.array([]), np.array([])
    S = np.maximum(np.round(mult * m.adr.values / TICK) * TICK, FLOOR)
    move = np.where(m.mae_pts.values >= S, -S, m.eod_move.values)
    net = move * PT - COMM - SLIP
    R = net / (S * PT)
    return net, R


def main():
    d = pd.read_csv(CSV)
    d = d[d.with_trend].copy()
    d["fh"] = d.fill_hour.astype(int)
    years = sorted(d.yr.unique())

    def best_on(train):
        best, bk = -1e18, None
        for (gap, mult, win, side) in GRID:
            _, R = evaluate(train, gap, mult, win, side)
            if len(R) >= 40 and R.sum() > best:   # objective = train total-R (scale-free)
                best, bk = R.sum(), (gap, mult, win, side)
        return bk

    FROZEN = (0.54, 0.30, "09-13", "both")
    print("NOT varied: phase-gate, 2E count, 6t retest, EOD hold (= the strategy). "
          "Varied: gap, stop-mult, window, side.\n")

    # ---- ANCHORED: expanding train from 2010, 1-yr OOS test ----
    oos_net, oos_R, picks = [], [], []
    fz_net = []
    for y in [yy for yy in years if yy >= 2012]:
        train = d[d.yr < y]; test = d[d.yr == y]
        bp = best_on(train)
        if bp is None:
            continue
        n_, R_ = evaluate(test, *bp); oos_net.append(n_); oos_R.append(R_)
        fn, _ = evaluate(test, *FROZEN); fz_net.append(fn)
        picks.append({"yr": y, "gap": bp[0], "mult": bp[1], "win": bp[2], "side": bp[3],
                      "oos_net": n_.sum(), "oos_R": R_.sum(), "n": len(n_)})
    pk = pd.DataFrame(picks); pk.to_csv(WT / "data" / "regime" / "wfa_cleanroom_20260725.csv", index=False)

    print("========== ANCHORED CLEAN-ROOM WFA (train 2010..Y-1, test Y), per-year picks ==========")
    print(f"{'yr':>4} {'gap':>5} {'mult':>5} {'win':>6} {'side':>5} {'n':>4} {'OOS_R':>7} {'OOS_$':>9}")
    for r in picks:
        print(f"{r['yr']:>4} {r['gap']:>5} {r['mult']:>5} {r['win']:>6} {r['side']:>5} "
              f"{r['n']:>4} {r['oos_R']:>+7.1f} {r['oos_net']:>+9,.0f}")

    on = np.concatenate(oos_net); oR = np.concatenate(oos_R); fn = np.concatenate(fz_net)
    print("\n========== STITCHED OOS 2012-2026 ==========")
    print(f"CLEAN-ROOM WFA : n={len(on):5d}  totalR {oR.sum():+7.1f}  meanR {oR.mean():+.3f}  "
          f"net ${on.sum():+9,.0f}  PF {pf(on):.2f}  win {100*(on>0).mean():.1f}%")
    print(f"FROZEN (2021-tuned): n={len(fn):5d}  net ${fn.sum():+9,.0f}  PF {pf(fn):.2f}  "
          f"meanR (approx via R col not recomputed)")
    # OOS pre/post split
    yv = np.concatenate([[r["yr"]] * r["n"] for r in picks])
    print(f"\n  WFA OOS pre-2021 (2012-20): net ${on[yv<=2020].sum():+8,.0f}  R {oR[yv<=2020].sum():+6.1f}  "
          f"meanR {oR[yv<=2020].mean():+.3f}  PF {pf(on[yv<=2020]):.2f}")
    print(f"  WFA OOS 2021+           : net ${on[yv>=2021].sum():+8,.0f}  R {oR[yv>=2021].sum():+6.1f}  "
          f"meanR {oR[yv>=2021].mean():+.3f}  PF {pf(on[yv>=2021]):.2f}")

    print("\n========== PICK STABILITY (are the levers stable or thrashing?) ==========")
    for col in ("gap", "mult", "win", "side"):
        vc = pk[col].value_counts()
        print(f"  {col:<5}: " + ", ".join(f"{k}x{v}" for k, v in vc.items()))


if __name__ == "__main__":
    main()
