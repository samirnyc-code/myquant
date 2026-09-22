"""Is the flip-mode 2E edge REAL or fat-tail luck? Stats + graphic.

Reads the saved flip trades (regime2e_flip_scale_sim.py). ES economics ($50/pt,
$17.50/trade). Produces reports/regime2e/edge_2e_flip.png with:
  1. cumulative equity curve (1 ES)
  2. per-trade P&L sorted (fat-tail visual) + top-N share
  3. BOOTSTRAP 95% CI of mean expectancy  <- the "does the bar cross 0?" test
     (full book, AND with the top-10 winners removed)
  4. distribution of 10k bootstrapped mean-expectancies vs the 0 line

Also prints: t-stat, bootstrap p(mean<=0), Sharpe, edge with/without fat tail.

  python scripts/regime2e_edge_graphic.py [flip_trades_csv]
"""
import sys
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MULT = 50.0; COST = 17.5
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "reports" / "regime2e"
RNG = np.random.default_rng(42)


def boot_ci(x, n=10000):
    means = np.array([RNG.choice(x, len(x), replace=True).mean() for _ in range(n)])
    return means, np.percentile(means, 2.5), np.percentile(means, 97.5), (means <= 0).mean()


def main():
    csvs = sorted(glob(str(OUTDIR / "flip_trades_*.csv")))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(csvs[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    v = (df["pts"].values - COST / MULT) * MULT      # $ per trade, 1 ES, net of cost
    n = len(v)
    eq = np.cumsum(v)

    mean = v.mean(); sd = v.std(ddof=1); tstat = mean / (sd / np.sqrt(n))
    daily = df.assign(p=v).groupby("date")["p"].sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(252)
    means, lo, hi, p0 = boot_ci(v)
    # fat-tail: remove top-10 winners
    order = np.argsort(v)[::-1]
    v_ex = np.delete(v, order[:10])
    means_ex, lo_ex, hi_ex, p0_ex = boot_ci(v_ex)
    top10_share = v[order[:10]].sum() / v[v > 0].sum() * 100

    print(f"flip 2E, 1 ES, net: n={n}  total ${v.sum():+,.0f}  mean ${mean:+.0f}/tr  sd ${sd:,.0f}")
    print(f"  t-stat {tstat:.2f}   daily Sharpe {sharpe:.2f}")
    print(f"  bootstrap 95% CI of mean expectancy: [${lo:+.0f}, ${hi:+.0f}]  p(mean<=0)={p0:.4f}"
          f"  -> {'EXCLUDES 0 (edge)' if lo > 0 else 'INCLUDES 0'}")
    print(f"  top-10 winners = {top10_share:.0f}% of gross profit")
    print(f"  WITHOUT top-10 winners: mean ${v_ex.mean():+.0f}/tr  CI [${lo_ex:+.0f}, ${hi_ex:+.0f}]"
          f"  p(mean<=0)={p0_ex:.4f}  -> {'still EXCLUDES 0' if lo_ex > 0 else 'now INCLUDES 0'}")

    fig, ax = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle("REGIME-2E flip mode, 1 ES net — is the edge real?", fontsize=14, weight="bold")

    ax[0, 0].plot(eq, lw=1.3, color="#2e7d32")
    ax[0, 0].axhline(0, color="#888", lw=0.8)
    ax[0, 0].set_title(f"Cumulative equity  (end ${eq[-1]:+,.0f})")
    ax[0, 0].set_xlabel("trade #"); ax[0, 0].set_ylabel("$")

    sv = np.sort(v)
    ax[0, 1].bar(range(n), sv, color=["#c62828" if z < 0 else "#2e7d32" for z in sv])
    ax[0, 1].axhline(0, color="#888", lw=0.8)
    ax[0, 1].set_title(f"Per-trade P&L sorted  (top-10 = {top10_share:.0f}% of gross profit)")
    ax[0, 1].set_xlabel("trade (sorted)"); ax[0, 1].set_ylabel("$")

    for m, c, lbl, L, H in [(means, "#1565c0", "full book", lo, hi),
                            (means_ex, "#ef6c00", "ex top-10 win", lo_ex, hi_ex)]:
        ax[1, 0].hist(m, bins=60, alpha=0.55, color=c, label=f"{lbl}  CI[{L:+.0f},{H:+.0f}]")
    ax[1, 0].axvline(0, color="#c62828", lw=2, ls="--", label="zero (no edge)")
    ax[1, 0].set_title("Bootstrap of mean expectancy — does it cross 0?")
    ax[1, 0].set_xlabel("$/trade"); ax[1, 0].legend(fontsize=8)

    monthly = df.assign(p=v, ym=df["date"].str[:7]).groupby("ym")["p"].sum()
    ax[1, 1].bar(range(len(monthly)), monthly.values,
                 color=["#c62828" if z < 0 else "#2e7d32" for z in monthly.values])
    ax[1, 1].axhline(0, color="#888", lw=0.8)
    ax[1, 1].set_title(f"Monthly P&L  ({(monthly > 0).mean()*100:.0f}% of months green)")
    ax[1, 1].set_xlabel("month"); ax[1, 1].set_ylabel("$")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = OUTDIR / "edge_2e_flip.png"
    fig.savefig(out, dpi=110)
    print(f"\ngraphic: {out}")


if __name__ == "__main__":
    main()
