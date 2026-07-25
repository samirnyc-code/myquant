"""DURABLE + VOL-REGIME DAY FILTER — the durable book bleeds in low-vol years (90% underwater,
profit concentrated in high-vol 2022/2024). Test whether a causal vol-regime day-filter (skip
low-vol days) improves net/DD and the underwater profile WITHOUT killing the high-vol profit.

Filters (all causal, prior-day info): absolute ADR10 / VIX thresholds, and ROLLING-RELATIVE
(ADR10 vs its own trailing-100-session median) so 'elevated' means the same thing in every era.

Reads durable_20260725.csv (netd, adr, vix_prev, Date, yr). Reports per filter: trades kept,
net, PF, realized maxDD, net/maxDD, % sessions underwater, and pre/post-2021 net split.

  python scripts/regime_2e_durable_volfilter.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "durable_20260725.csv"


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def stats(d):
    """d: per-trade rows with netd, Date, yr. Return dict of metrics."""
    if not len(d):
        return None
    dd = d.groupby("Date")["netd"].sum().sort_index()
    eq = dd.cumsum(); uw = eq - eq.cummax()
    mdd = float(uw.min())
    v = d["netd"].values
    return {"n": len(d), "net": v.sum(), "PF": pf(v), "maxDD": mdd,
            "net/DD": v.sum() / -mdd if mdd < 0 else float("inf"),
            "uw%": 100 * (uw < 0).mean(),
            "pre": d[d.yr <= 2020]["netd"].sum(), "post": d[d.yr >= 2021]["netd"].sum(),
            "pf_pre": pf(d[d.yr <= 2020]["netd"]), "pf_post": pf(d[d.yr >= 2021]["netd"])}


def main():
    d = pd.read_csv(CSV).sort_values("Date").reset_index(drop=True)
    # per-date ADR + rolling-relative regime
    dd = d.groupby("Date").agg(adr=("adr", "first")).reset_index().sort_values("Date")
    dd["adr_med100"] = dd["adr"].rolling(100, min_periods=30).median().shift(1)
    dd["adr_rel"] = dd["adr"] / dd["adr_med100"]
    d = d.merge(dd[["Date", "adr_med100", "adr_rel"]], on="Date", how="left")

    filters = {
        "NONE (baseline)": np.ones(len(d), bool),
        "ADR>=18 (abs)": d.adr >= 18,
        "ADR>=22 (abs)": d.adr >= 22,
        "ADR>=26 (abs)": d.adr >= 26,
        "VIX>=15 (abs)": d.vix_prev >= 15,
        "VIX>=17 (abs)": d.vix_prev >= 17,
        "ADR>=median (rel)": d.adr_rel >= 1.0,
        "ADR>=1.15xmed (rel)": d.adr_rel >= 1.15,
        "ADR>=1.3xmed (rel)": d.adr_rel >= 1.30,
    }
    print("========== DURABLE + vol-regime day filter (causal) ==========")
    print(f"{'filter':<22}{'n':>5}{'net':>9}{'PF':>6}{'maxDD':>9}{'net/DD':>7}{'uw%':>6}"
          f"   {'pre-2021':>9}{'PFpre':>6}{'post-2021':>10}{'PFpost':>7}")
    for name, mask in filters.items():
        s = stats(d[mask.values if hasattr(mask, "values") else mask])
        if s is None:
            print(f"{name:<22} (empty)"); continue
        print(f"{name:<22}{s['n']:>5}{s['net']:>+9,.0f}{s['PF']:>6.2f}{s['maxDD']:>+9,.0f}"
              f"{s['net/DD']:>7.2f}{s['uw%']:>6.0f}   {s['pre']:>+9,.0f}{s['pf_pre']:>6.2f}"
              f"{s['post']:>+10,.0f}{s['pf_post']:>7.2f}")

    print("\nRead: a good filter RAISES net/DD and LOWERS uw% while keeping post-2021 net and")
    print("keeping pre-2021 net POSITIVE (proves it's regime-timing, not just dropping the bad era).")


if __name__ == "__main__":
    main()
