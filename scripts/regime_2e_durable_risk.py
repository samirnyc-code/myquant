"""DURABLE RISK / SIZING — drawdown, Monte-Carlo, prop-fit, account sizing for the durable
2E book (longs 0.40 all + shorts below-50d-SMA 0.30), 2010-2026, 1 ES, $5 RT + slip.

Reads data/regime/durable_20260725.csv (col netd). Reports realized maxDD, high-water
underwater stats, block-bootstrap + shuffle MC drawdown, per-year, and account-size /
prop-fit implications. Chart: equity + underwater with the 2021 OOS boundary.

  python scripts/regime_2e_durable_risk.py
Output: docs/living/durable_risk_20260725.png
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
CSV = WT / "data" / "regime" / "durable_20260725.csv"
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def maxdd(eq):
    return float((eq - np.maximum.accumulate(eq)).min())


def main():
    d = pd.read_csv(CSV).sort_values("Date").reset_index(drop=True)
    v = d["netd"].values
    eq = np.cumsum(v)
    peak = np.maximum.accumulate(eq)
    uw = eq - peak
    realized_dd = maxdd(eq)
    # longest underwater run (in trades)
    underwater = uw < 0
    longest = cur = 0
    for x in underwater:
        cur = cur + 1 if x else 0
        longest = max(longest, cur)
    # daily aggregation for time-based underwater
    dd = d.groupby("Date")["netd"].sum().sort_index()
    deq = dd.cumsum(); dpk = deq.cummax(); duw = deq - dpk
    days_uw = int((duw < 0).sum()); tot_days = len(duw)

    # MC: shuffle trade order
    sh = np.array([maxdd(np.cumsum(rng.permutation(v))) for _ in range(5000)])
    # MC: block bootstrap (block=20 trades) to preserve streaks
    def block_boot():
        out = []
        n = len(v)
        while len(out) < n:
            i = rng.integers(0, n)
            out.extend(v[i:i + 20])
        return np.array(out[:n])
    bb = np.array([maxdd(np.cumsum(block_boot())) for _ in range(3000)])

    print("========== DURABLE BOOK RISK (1 ES, $5 RT, 2010-2026) ==========")
    print(f"trades           : {len(v):,}   ({len(v)/16.5:.0f}/yr)")
    print(f"net              : ${v.sum():+,.0f}   (${v.sum()/16.5:+,.0f}/yr)")
    print(f"PF               : {pf(v)}   win {100*(v>0).mean():.1f}%")
    print(f"avg win / loss   : +${v[v>0].mean():,.0f} / ${v[v<0].mean():,.0f}   payoff {v[v>0].mean()/-v[v<0].mean():.2f}")
    print(f"best / worst trade: +${v.max():,.0f} / ${v.min():,.0f}")
    print(f"\nrealized maxDD   : ${realized_dd:,.0f}")
    print(f"longest underwater: {longest} trades / {days_uw} of {tot_days} sessions ({100*days_uw/tot_days:.0f}%)")
    print(f"MC shuffle  maxDD : median ${np.median(sh):,.0f}  worst-5% ${np.percentile(sh,5):,.0f}  worst-1% ${np.percentile(sh,1):,.0f}")
    print(f"MC block-boot maxDD: median ${np.median(bb):,.0f}  worst-5% ${np.percentile(bb,5):,.0f}  worst-1% ${np.percentile(bb,1):,.0f}")

    print("\n========== per-year ==========")
    yt = d.groupby("yr")["netd"].agg(n="size", net="sum")
    yt["PF"] = d.groupby("yr")["netd"].apply(pf)
    print(yt.round({"net": 0}).to_string())

    print("\n========== SIZING implications (block-boot worst-1% as risk DD) ==========")
    riskdd = -np.percentile(bb, 1)
    for tol, lab in ((0.20, "conservative 20%"), (0.33, "moderate 33%"), (0.50, "aggressive 50%")):
        print(f"  DD={riskdd:,.0f} at {lab} of account -> ${riskdd/tol:,.0f} capital per 1 ES")
    print(f"  net/maxDD (realized) = {v.sum()/-realized_dd:.2f}   net/MC-1% = {v.sum()/riskdd:.2f}")
    print(f"  prop $4,500 trailing: 1 ES worst-1% ${-riskdd:,.0f} -> {'FITS' if riskdd<4500 else 'does NOT fit'} 1 ES; "
          f"MES(1/10) worst-1% ${-riskdd/10:,.0f} -> {'fits' if riskdd/10<4500 else 'no'}")

    # chart
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 7), dpi=115, height_ratios=[3, 1], sharex=True)
    a1.plot(range(len(eq)), eq, lw=1.6, color="#2a78d6")
    n_oos = int((d.yr <= 2020).sum())
    a1.axvline(n_oos, color="#c0392b", lw=1.1, ls="--"); a1.text(n_oos, eq.max()*0.05, "  2021 ->", color="#c0392b", fontsize=9)
    a1.axhline(0, color="#c3c2b7", lw=1); a1.grid(axis="y", color="#eceeed", lw=0.7)
    a1.set_title(f"DURABLE 2E (long-biased + trend-gated shorts) — {v.sum():+,.0f}$ PF {pf(v)} "
                 f"maxDD {realized_dd:,.0f} | pre-2021 {d[d.yr<=2020].netd.sum():+,.0f}$ PF {pf(d[d.yr<=2020].netd)}",
                 fontweight="bold", fontsize=11)
    for s_ in ("top", "right"): a1.spines[s_].set_visible(False)
    a2.fill_between(range(len(uw)), uw, 0, color="#c0392b", alpha=0.5)
    a2.axvline(n_oos, color="#c0392b", lw=1.1, ls="--"); a2.set_ylabel("underwater $")
    a2.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): a2.spines[s_].set_visible(False)
    fig.tight_layout()
    p = WT / "docs" / "living" / "durable_risk_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
