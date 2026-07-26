"""HVL SENSITIVITY — how fragile is the 2E-above-HVL edge to error in the HVL level? We know the
pre-2024 HVL is approximate (my SPX+basis vs MQ's real ES HVL = 34pt medAE, ~50pt mean/std).
So: perturb each session's HVL by Gaussian noise of magnitude sigma, re-classify every trade
above/below, recompute the above-HVL book, and see how PF/net move. Noise is PER SESSION
(the HVL error is a daily quantity, correlated within a day).

If PF stays well above 1 out to sigma ~50pt, the approximate levels don't much matter.
If it collapses, we need correct ES levels before trusting the full 5-yr result.

Reads hvl_2e_realtick_20260725.csv (real-tick 2E trades, entry_px + baseline prior_hvl_es).

  python scripts/regime_2e_hvl_sensitivity.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
rng = np.random.default_rng(83)
M = 400   # Monte-Carlo iterations per sigma


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else 0.0


def main():
    d = pd.read_csv(WT / "data" / "regime" / "hvl_2e_realtick_20260725.csv")
    d = d.dropna(subset=["prior_hvl_es"]).reset_index(drop=True)
    dates = d["Date"].values
    uniq = pd.unique(dates)
    dix = {dt: i for i, dt in enumerate(uniq)}
    day_idx = np.array([dix[dt] for dt in dates])   # which session each trade belongs to
    entry = d["entry_px"].values
    hvl0 = d["prior_hvl_es"].values
    net = d["net"].values
    base_above = entry > hvl0
    base_pf = pf(net[base_above]); base_net = net[base_above].sum()
    print(f"baseline (sigma=0): above-HVL n={base_above.sum()}  PF {base_pf:.2f}  net ${base_net:+,.0f}\n")
    print(f"{'sigma(pt)':>9} {'PF mean':>8} {'PF p5':>7} {'PF p95':>7} {'net mean':>10} {'%flip':>7} {'%iters PF>1.4':>13}")
    for sig in (0, 10, 20, 30, 50, 80, 120):
        pfs = np.empty(M); nets = np.empty(M); flips = np.empty(M)
        for m in range(M):
            noise = rng.normal(0, sig, size=len(uniq))[day_idx]   # per-session noise
            above = entry > (hvl0 + noise)
            pfs[m] = pf(net[above]); nets[m] = net[above].sum()
            flips[m] = np.mean(above != base_above)
        print(f"{sig:>9} {pfs.mean():>8.2f} {np.percentile(pfs,5):>7.2f} {np.percentile(pfs,95):>7.2f} "
              f"{nets.mean():>+10,.0f} {100*flips.mean():>6.0f}% {100*np.mean(pfs>1.4):>12.0f}%")
    print("\nread: if PF stays comfortably >1.3 and %iters-PF>1.4 stays high out to sigma~50, the")
    print("edge is robust to the level error -> approximate pre-2024 HVL is 'good enough'.")


if __name__ == "__main__":
    main()
