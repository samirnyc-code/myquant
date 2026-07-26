"""Validate the gamma/levels BACKFILL against ACTUAL PUBLISHED MQ levels (scraped truth) on a
recent window, with a chart. Also checks date alignment (same-day vs shifted) empirically.

Backfill: data/regime/mq_regime_daily_2007_2026_v2.csv (date = chain tradeDate, same-day EOD).
Truth:    data/regime/mq_reveng/mq_truth.csv (MQ's own published cr/ps/hvl/gex, by session_date).

  python scripts/mq_backfill_vs_published.py [N]   (N = recent trading days, default 120)
Output: docs/living/mq_backfill_vs_published_20260725.png + match stats.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 120


def main():
    b = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv")
    b["date"] = b["date"].astype(str)
    t = pd.read_csv(DATA / "regime" / "mq_reveng" / "mq_truth.csv")
    t["session_date"] = t["session_date"].astype(str)
    t["treg"] = np.where(t.spot_eod > t.hvl, "positive_gamma", "negative_gamma")

    # SAME-DATE join (backfill date == truth session_date)
    m = b.merge(t[["session_date", "spot_eod", "cr", "ps", "hvl", "treg"]],
                left_on="date", right_on="session_date", suffixes=("_bf", "_mq"))
    m = m.sort_values("date").tail(N)

    def stats(x):
        cr_ex = 100 * (x.cr_bf == x.cr_mq).mean()
        ps_ex = 100 * (x.ps_bf == x.ps_mq).mean()
        cr_w25 = 100 * ((x.cr_bf - x.cr_mq).abs() <= 25).mean()
        ps_w25 = 100 * ((x.ps_bf - x.ps_mq).abs() <= 25).mean()
        hvl_ae = (x.hvl_bf - x.hvl_mq).abs().median()
        reg = 100 * (x.regime == x.treg).mean()
        return cr_ex, cr_w25, ps_ex, ps_w25, hvl_ae, reg

    print(f"===== BACKFILL vs PUBLISHED MQ — last {len(m)} sessions ({m.date.min()}..{m.date.max()}) =====")
    print(f"  CR  exact {stats(m)[0]:.0f}%  within-25 {stats(m)[1]:.0f}%")
    print(f"  PS  exact {stats(m)[2]:.0f}%  within-25 {stats(m)[3]:.0f}%")
    print(f"  HVL median abs err {stats(m)[4]:.1f} pt")
    print(f"  gamma-regime (pos/neg) agreement {stats(m)[5]:.0f}%")

    # empirical date-alignment check: does same-date or shifted match better?
    print("\n  date-alignment check (regime agreement):")
    for k in (-1, 0, 1):
        bb = b.copy(); bb["j"] = (pd.to_datetime(bb.date) + pd.Timedelta(days=k)).dt.strftime("%Y-%m-%d")
        mm = bb.merge(t[["session_date", "spot_eod", "hvl", "treg"]], left_on="j", right_on="session_date")
        lbl = {-1: "backfill[D-1] vs MQ[D]", 0: "backfill[D] vs MQ[D] (same-date)", 1: "backfill[D+1] vs MQ[D]"}[k]
        if len(mm):
            print(f"    {lbl:<34} CR-exact {100*(mm.cr==mm.cr).mean():.0f}%  reg-agree {100*(mm.regime==mm.treg).mean():.0f}%  n={len(mm)}")

    # chart
    fig, ax = plt.subplots(figsize=(15, 7), dpi=115)
    x = np.arange(len(m)); dts = pd.to_datetime(m.date)
    ax.plot(x, m.spot_eod, color="#111", lw=1.4, label="SPX spot (EOD)")
    ax.plot(x, m.cr_mq, color="#c0392b", lw=2.2, alpha=0.5, label="CR published")
    ax.plot(x, m.cr_bf, color="#c0392b", lw=1, ls="--", label="CR backfill")
    ax.plot(x, m.ps_mq, color="#2a78d6", lw=2.2, alpha=0.5, label="PS published")
    ax.plot(x, m.ps_bf, color="#2a78d6", lw=1, ls="--", label="PS backfill")
    ax.plot(x, m.hvl_mq, color="#27a35a", lw=2.2, alpha=0.5, label="HVL published")
    ax.plot(x, m.hvl_bf, color="#27a35a", lw=1, ls="--", label="HVL backfill")
    step = max(1, len(m) // 15)
    ax.set_xticks(x[::step]); ax.set_xticklabels([d.strftime("%m-%d") for d in dts[::step]], rotation=45, fontsize=8)
    s = stats(m)
    ax.set_title(f"Backfill vs PUBLISHED MenthorQ levels — last {len(m)} sessions | "
                 f"CR exact {s[0]:.0f}%/w25 {s[1]:.0f}% · PS exact {s[2]:.0f}%/w25 {s[3]:.0f}% · "
                 f"HVL medAE {s[4]:.0f}pt · regime {s[5]:.0f}%", fontweight="bold", fontsize=10)
    ax.legend(ncol=4, fontsize=8, frameon=False); ax.grid(axis="y", color="#eceeed", lw=0.7)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    fig.tight_layout(); p = WT / "docs" / "living" / "mq_backfill_vs_published_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
