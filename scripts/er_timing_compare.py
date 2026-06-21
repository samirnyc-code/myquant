"""ER timing comparison — current bar T vs lagged bar T-1.

The question: does ER_intra_6 include the signal bar's own move (which could
inflate ER on strong breakout bars)? Compare:
  - ER at bar T (current behavior) — the ER value AT the signal bar
  - ER at bar T-1 (lagged) — the ER value BEFORE the signal bar

For each, apply the >=0.30 filter and compare the resulting trade populations.
If the edge holds on T-1 ER, the filter is measuring pre-signal regime (good).
If not, the filter is partly selecting FOR signal bars (bad).

Pure diagnostic — does NOT modify engine or data.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                  # noqa: E402
import indicators                               # noqa: E402
from simulation_engine import simulate_trades, compute_summary  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

CHOP_THRESHOLDS = [0.25, 0.28, 0.30, 0.32, 0.35]


def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[er-cmp] [{ts}] {m}", flush=True)


def run_and_summarize(sig_subset, ticks_by_date, bars_by_date):
    """Simulate and return summary dict."""
    if sig_subset.empty:
        return {"trades": 0}
    results = simulate_trades(
        signals=sig_subset,
        ticks_by_date=ticks_by_date,
        bars_by_date=bars_by_date,
        **BASE,
    )
    filled = results[results["Filled"] == True]
    if filled.empty:
        return {"trades": 0}
    pnl = filled["NetPnL"].to_numpy()
    gross_w = float(pnl[pnl > 0].sum())
    gross_l = float(abs(pnl[pnl < 0].sum()))
    return {
        "trades": len(filled),
        "net": float(pnl.sum()),
        "exp": float(pnl.mean()),
        "win_pct": float((pnl > 0).mean() * 100),
        "pf": gross_w / gross_l if gross_l > 0 else float("nan"),
        "median": float(np.median(pnl)),
    }


def main():
    log("Loading data...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # Compute ER at bar T (current) and bar T-1 (lagged)
    log("Computing ER_intra_6 (current + lagged)...")
    eri = indicators.bar_kaufman_er(bars, spans=(6,))
    eri_sorted = eri.sort_values("DateTime").reset_index(drop=True)

    # Current: merge_asof backward (same as tag_signals)
    sig_sorted = sig.sort_values("DateTime").copy()
    if str(sig_sorted["DateTime"].dtype) != "datetime64[ns]":
        sig_sorted["DateTime"] = sig_sorted["DateTime"].astype("datetime64[ns]")
    if str(eri_sorted["DateTime"].dtype) != "datetime64[ns]":
        eri_sorted["DateTime"] = eri_sorted["DateTime"].astype("datetime64[ns]")

    # T: ER at the signal bar
    merged_t = pd.merge_asof(
        sig_sorted, eri_sorted[["DateTime", "ER_intra_6"]].rename(columns={"ER_intra_6": "ER_T"}),
        on="DateTime", direction="backward",
    )

    # T-1: shift ER by 1 row before merging (the value from the bar BEFORE the signal bar)
    eri_lagged = eri_sorted.copy()
    eri_lagged["ER_intra_6"] = eri_lagged["ER_intra_6"].shift(1)
    merged = pd.merge_asof(
        merged_t, eri_lagged[["DateTime", "ER_intra_6"]].rename(columns={"ER_intra_6": "ER_T1"}),
        on="DateTime", direction="backward",
    )

    log(f"Signals tagged: {len(merged)}")
    log(f"ER_T  mean={merged['ER_T'].mean():.3f}  median={merged['ER_T'].median():.3f}")
    log(f"ER_T1 mean={merged['ER_T1'].mean():.3f}  median={merged['ER_T1'].median():.3f}")

    # Correlation between T and T-1
    valid = merged[["ER_T", "ER_T1"]].dropna()
    corr = valid["ER_T"].corr(valid["ER_T1"])
    log(f"Correlation ER_T vs ER_T1: {corr:.3f}")

    # How often does the filter decision differ?
    for thr in CHOP_THRESHOLDS:
        agree = ((merged["ER_T"] >= thr) == (merged["ER_T1"] >= thr)).mean() * 100
        log(f"  ER>={thr}: agree {agree:.1f}%")

    # Load ticks
    all_dates = sorted(merged["Date"].unique())
    log(f"Loading ticks for {len(all_dates)} days...")
    ticks_by_date = {}
    for d in all_dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"Ticks loaded: {len(ticks_by_date)} days")

    # Compare at each threshold
    rows = []
    for thr in CHOP_THRESHOLDS:
        # ER at T
        mask_t = merged["ER_T"].fillna(0) >= thr
        sig_t = sig.loc[mask_t.values].copy()
        stats_t = run_and_summarize(sig_t, ticks_by_date, bars_by_date)

        # ER at T-1
        mask_t1 = merged["ER_T1"].fillna(0) >= thr
        sig_t1 = sig.loc[mask_t1.values].copy()
        stats_t1 = run_and_summarize(sig_t1, ticks_by_date, bars_by_date)

        # Only in T but not T-1 (signals that pass because the signal bar boosted ER)
        only_t = mask_t & ~mask_t1
        sig_only = sig.loc[only_t.values].copy()
        stats_only = run_and_summarize(sig_only, ticks_by_date, bars_by_date)

        rows.append({"threshold": thr, "method": "ER_T (current)", **stats_t})
        rows.append({"threshold": thr, "method": "ER_T-1 (lagged)", **stats_t1})
        rows.append({"threshold": thr, "method": "only_in_T (boosted)", **stats_only})

        log(f"ER>={thr}: T={stats_t['trades']} trades/${stats_t.get('net',0):,.0f}  "
            f"T-1={stats_t1['trades']}/${stats_t1.get('net',0):,.0f}  "
            f"boosted-only={stats_only['trades']}/${stats_only.get('net',0):,.0f}")

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 220, "display.max_columns", 15)
    print("\n" + "=" * 80)
    print("ER TIMING COMPARISON: bar T (current) vs bar T-1 (lagged)")
    print("=" * 80)
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    out_file = _OUT / "er_timing_compare.md"
    with open(out_file, "w") as f:
        f.write("# ER Timing Comparison: Bar T vs Bar T-1\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Correlation ER_T vs ER_T-1:** {corr:.3f}\n\n")
        f.write("**Method:**\n")
        f.write("- `ER_T (current)`: ER_intra_6 at the signal bar (includes signal bar's move)\n")
        f.write("- `ER_T-1 (lagged)`: ER_intra_6 one bar before the signal (excludes signal bar)\n")
        f.write("- `only_in_T (boosted)`: signals that ONLY pass at T, not T-1 ")
        f.write("(the signal bar's move pushed ER above threshold)\n\n")
        f.write("## Results\n\n")
        f.write(df.to_markdown(index=False, floatfmt=".1f"))
        f.write("\n\n## Interpretation\n\n")
        f.write("If `only_in_T` trades have WORSE metrics than the main set, the signal bar ")
        f.write("is inflating ER (selecting FOR itself). If they're similar or better, ")
        f.write("the timing doesn't matter much.\n")
    log(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
