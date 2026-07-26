"""VALIDATE the gamma-regime PROXY (no options) as the 2E gate. Fixed, canonical thresholds
(not data-fit): 'near 20-day high' (within 1.5 ADR), 'above 20-day SMA', 'low VIX' (below causal
expanding median), and combos. Compare each to the HVL gate and no-gate, per year, and OOS
(train 2021-23 / holdout 2024-26, tune nothing).

Reads hvl_proxy_features_20260725.csv (2E trades + features + HVL 'above' label + net).

  python scripts/regime_2e_proxy_validate.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values; return float((e - np.maximum.accumulate(e)).min())


def report(name, x, full):
    v = x.net.values
    if not len(v):
        print(f"{name:<30} (none)"); return
    top5 = np.sort(v)[::-1][:5].sum()
    ov = 100 * (x.index.isin(full[full.above].index)).mean()
    yrs = " ".join(f"{y}:{pf(x[x.yr==y].net):.2f}" for y in sorted(x.yr.unique()))
    tr = pf(x[x.yr <= 2023].net); te = pf(x[x.yr >= 2024].net)
    print(f"{name:<30} n={len(v):4d} PF {pf(v):.2f} net ${v.sum():+8,.0f} win {100*(v>0).mean():3.0f}% "
          f"top5 {100*top5/v.sum():3.0f}% maxDD ${mdd(x):+7,.0f} | train {tr} test {te} | HVLoverlap {ov:.0f}%")
    print(f"{'':32}per-yr {yrs}")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "hvl_proxy_features_20260725.csv")
    d = d.dropna(subset=["sma20", "vix_prev", "dist_hi20"]).reset_index(drop=True)
    # causal expanding-median VIX threshold (no look-ahead)
    dv = d.sort_values("Date")
    dsess = dv.drop_duplicates("Date")[["Date", "vix_prev"]].reset_index(drop=True)
    dsess["vmed"] = dsess["vix_prev"].expanding(min_periods=60).median()
    d = d.merge(dsess[["Date", "vmed"]], on="Date", how="left")

    near = d.dist_hi20 <= 1.5          # within 1.5 ADR of the 20-day high
    asma = d.entry_px > d.sma20        # above 20-day SMA
    lowv = d.vix_prev < d.vmed         # below causal expanding-median VIX

    print("baseline no gate: ", end="")
    report("ALL 2E (no gate)", d, d)
    print("\nHVL gate (needs options): ", end="")
    report("2E above HVL", d[d.above], d)
    print("\n=== PROXY gates (NO options) ===")
    report("near 20d-high (<=1.5 ADR)", d[near], d)
    report("above 20d-SMA", d[asma], d)
    report("low VIX (< exp-median)", d[lowv & d.vmed.notna()], d)
    report("near-high AND low-VIX", d[near & lowv & d.vmed.notna()], d)
    report("near-high OR above-SMA", d[near | asma], d)
    report("above-SMA AND low-VIX", d[asma & lowv & d.vmed.notna()], d)

    print("\n=== the excluded side (proxy=FALSE) should be the weak regime ===")
    report("NOT near-high (far below hi)", d[~near], d)
    report("below 20d-SMA", d[~asma], d)


if __name__ == "__main__":
    main()
