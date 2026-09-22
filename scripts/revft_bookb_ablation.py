"""RevFT Book B — filter-stack ablation (leave-one-out + leave-two-out). 2026-07-25 (S85).

Book B stack (things tweaked today):
  D = drop counter-trend (phase-machine gate: keep with-trend | neutral)
  G = negative-gamma day (MQ daily gamma)
  H = hours 09-13 fill window
  E = wide 0.30xADR stop + hold-to-EOD exit  (remove E -> native 1R target/stop)
(Sneaky-excluded is a fixed signal-clean, baked into the per-trade table; not ablatable here.)

Realistic/conservative modes: native next-tick MARKET entry (limit-back proven worse, 0015d);
CONSERVATIVE cost = $5 RT commission + 2 ticks slippage (1 in + 1 out) = $30/trade. The saved table
already charged $5 + 1 tick = $17.5, so we subtract an extra $12.5/trade (a flat, per-trade adjustment
since slippage is per-trade). Reads data/regime/revft_regime_full_20260725.parquet — no re-sim.

    python scripts/revft_bookb_ablation.py
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
OUT = ROOT / "data" / "regime" / "revft_bookb_ablation_20260725.csv"
EXTRA_COST = 12.5          # raise base $17.5 -> conservative $30/trade (extra 1 tick exit slip)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def maxdd(v):
    eq = np.cumsum(np.asarray(v, float)); return float((eq - np.maximum.accumulate(eq)).min())


def main():
    t = pd.read_parquet(T).sort_values("Date").reset_index(drop=True)
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    notCT = (L & bull) | (S & bear) | neu          # D applied
    neg = t.mq == "negative_gamma"                 # G applied
    hrs = t.hour.astype(str).isin(["09", "10", "11", "12", "13"])   # H applied

    def evaluate(useD, useG, useH, useE):
        m = pd.Series(True, index=t.index)
        if useD: m &= notCT
        if useG: m &= neg
        if useH: m &= hrs
        col = "w30eod" if useE else "n1r"
        v = (t.loc[m, col] - EXTRA_COST).values          # conservative cost
        if not len(v):
            return dict(n=0)
        yr = t.loc[m, "year"].values
        yy = {y: (v[yr == y]).sum() for y in np.unique(yr)}
        green = sum(1 for x in yy.values() if x > 0)
        return dict(n=len(v), total=v.sum(), avg=v.mean(), pf=pf(v),
                    win=100*(v > 0).mean(), dd=maxdd(v), green=green, nyr=len(yy))

    rows = []

    def add(label, kept, D, G, H, E):
        r = evaluate(D, G, H, E)
        rows.append((label, kept, r))

    # FULL
    add("FULL Book B", "D+G+H+E", 1, 1, 1, 1)
    # remove 1
    add("-D (keep trend-fades)", "G+H+E", 0, 1, 1, 1)
    add("-G (all gamma days)", "D+H+E", 1, 0, 1, 1)
    add("-H (all hours)", "D+G+E", 1, 1, 0, 1)
    add("-E (native 1R exit)", "D+G+H", 1, 1, 1, 0)
    # remove 2 (keep 2)
    add("-D-G (keep H+E)", "H+E", 0, 0, 1, 1)
    add("-D-H (keep G+E)", "G+E", 0, 1, 0, 1)
    add("-D-E (keep G+H)", "G+H", 0, 1, 1, 0)
    add("-G-H (keep D+E)", "D+E", 1, 0, 0, 1)
    add("-G-E (keep D+H)", "D+H", 1, 0, 1, 0)
    add("-H-E (keep D+G)", "D+G", 1, 1, 0, 0)
    # reference: no filters at all (all RevFT, native 1R = the firm loser)
    add("NONE (raw RevFT 1R)", "—", 0, 0, 0, 0)

    print(f"\nRevFT Book B — filter ablation | conservative cost $30/tr ($5 comm + 2t slip) | native mkt entry")
    print(f"{'config':26s} {'kept':7s} {'n':>5s} {'total$':>9s} {'$/tr':>6s} {'PF':>5s} {'win%':>5s} {'maxDD$':>9s} {'green':>6s}")
    print("-"*92)
    recs = []
    for (label, kept, r) in rows:
        if r.get("n", 0) == 0:
            print(f"{label:26s} {kept:7s}   n=0"); continue
        print(f"{label:26s} {kept:7s} {r['n']:>5d} {r['total']:>9,.0f} {r['avg']:>6.1f} {r['pf']:>5.2f} "
              f"{r['win']:>5.1f} {r['dd']:>9,.0f} {r['green']:>3d}/{r['nyr']}")
        recs.append(dict(config=label, kept=kept, **r))
    pd.DataFrame(recs).to_csv(OUT, index=False)
    print(f"\nsaved {OUT}")
    print("Read: D=drop-counter-trend, G=neg-gamma, H=hours09-13, E=wideADR+EOD exit (else native 1R).")


if __name__ == "__main__":
    main()
