"""Time-of-day signal analysis — price out every session window.

Three analyses:
1. Per-bar-number expectancy (every 5M bar from open to close)
2. Session-phase breakdown (Open/Mid/Lunch/Afternoon/Close)
3. Cumulative: what if we drop signals after a cutoff time?

Uses ER>=0.30 + pinned 1.0R singleleg as the baseline config.
Pure diagnostic — does NOT modify data or run WFA.
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
import regime_filter as rf                      # noqa: E402
from simulation_engine import simulate_trades, compute_summary, RTH_END_MIN  # noqa: E402
from data_loader import bar_num_from_dt          # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)
CHOP_MIN = 0.30

# RTH session phases (CT times): 8:30-11:30 Open, 11:30-13:00 Lunch, 13:00-14:15 Afternoon, 14:15-15:15 Close
PHASES = [
    ("Open (8:30-10:00)",     8*60+30,  10*60),
    ("Mid (10:00-11:30)",     10*60,    11*60+30),
    ("Lunch (11:30-13:00)",   11*60+30, 13*60),
    ("Afternoon (13:00-14:15)", 13*60,  14*60+15),
    ("Close (14:15-15:15)",   14*60+15, 15*60+15),
]


def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[tod] [{ts}] {m}", flush=True)


def bucket_stats(pnl_array):
    """Compute standard metrics from a PnL array."""
    pnl = pnl_array
    if len(pnl) == 0:
        return {}
    wins = (pnl > 0).sum()
    gross_w = float(pnl[pnl > 0].sum())
    gross_l = float(abs(pnl[pnl < 0].sum()))
    return {
        "trades": len(pnl),
        "net": float(pnl.sum()),
        "exp": float(pnl.mean()),
        "median": float(np.median(pnl)),
        "win_pct": float(wins / len(pnl) * 100),
        "pf": gross_w / gross_l if gross_l > 0 else float("nan"),
        "best": float(pnl.max()),
        "worst": float(pnl.min()),
    }


def main():
    log("Loading signals + bars...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    log("Tagging for ER filter...")
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float)
    sig_filtered = sig[er.fillna(0) >= CHOP_MIN].copy()
    log(f"Signals after ER>=0.30: {len(sig_filtered)}")

    all_dates = sorted(sig_filtered["Date"].unique())
    log(f"Loading ticks for {len(all_dates)} days...")
    ticks_by_date = {}
    for d in all_dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"Ticks loaded: {len(ticks_by_date)} days")

    log("Simulating all trades at 1.0R singleleg...")
    results = simulate_trades(
        signals=sig_filtered,
        ticks_by_date=ticks_by_date,
        bars_by_date=bars_by_date,
        **BASE,
    )
    filled = results[results["Filled"] == True].copy()
    log(f"Filled trades: {len(filled)}")

    sig_dt = pd.to_datetime(filled["DateTime"])
    filled["sig_hour"] = sig_dt.dt.hour
    filled["sig_min_of_day"] = sig_dt.dt.hour * 60 + sig_dt.dt.minute
    filled["min_before_close"] = RTH_END_MIN - filled["sig_min_of_day"]
    filled["bar_num"] = sig_dt.apply(bar_num_from_dt)

    # ══════════════════════════════════════════════════════════════════════════
    # 1. PER-BAR-NUMBER EXPECTANCY
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("1. PER-BAR-NUMBER EXPECTANCY (5M bars, RTH)")
    print("   Bar 1 = 8:30-8:35 CT ... Bar 81 = 15:10-15:15 CT")
    print("=" * 80)
    bar_rows = []
    for bn in sorted(filled["bar_num"].unique()):
        mask = filled["bar_num"] == bn
        pnl = filled.loc[mask, "NetPnL"].to_numpy()
        t = sig_dt[mask].iloc[0]
        time_label = f"{t.hour:02d}:{t.minute:02d}"
        stats = bucket_stats(pnl)
        bar_rows.append({"bar": int(bn), "time": time_label, **stats})
    df_bars = pd.DataFrame(bar_rows)
    print(df_bars.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # ══════════════════════════════════════════════════════════════════════════
    # 2. SESSION-PHASE BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("2. SESSION-PHASE BREAKDOWN")
    print("=" * 80)
    phase_rows = []
    for label, lo, hi in PHASES:
        mask = (filled["sig_min_of_day"] >= lo) & (filled["sig_min_of_day"] < hi)
        pnl = filled.loc[mask, "NetPnL"].to_numpy()
        stats = bucket_stats(pnl)
        phase_rows.append({"phase": label, **stats})
    df_phases = pd.DataFrame(phase_rows)
    print(df_phases.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # ══════════════════════════════════════════════════════════════════════════
    # 3. CUMULATIVE CUTOFF: drop everything after time X
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("3. CUMULATIVE: keep only signals before cutoff time (CT)")
    print("=" * 80)
    total_pnl = filled["NetPnL"].to_numpy()
    total_net = float(total_pnl.sum())

    cutoff_times = [
        ("no cutoff",  999),
        ("before 14:45", 14*60+45),
        ("before 14:30", 14*60+30),
        ("before 14:15", 14*60+15),
        ("before 14:00", 14*60),
        ("before 13:30", 13*60+30),
        ("before 13:00", 13*60),
        ("before 12:30", 12*60+30),
        ("before 12:00", 12*60),
        ("before 11:30", 11*60+30),
        ("before 11:00", 11*60),
    ]
    cum_rows = []
    for label, cutoff in cutoff_times:
        if cutoff == 999:
            kept = filled
        else:
            kept = filled[filled["sig_min_of_day"] < cutoff]
        kpnl = kept["NetPnL"].to_numpy()
        if len(kpnl) == 0:
            continue
        stats = bucket_stats(kpnl)
        dropped = len(filled) - len(kept)
        dropped_pnl = total_net - float(kpnl.sum())
        cum_rows.append({
            "cutoff": label,
            **stats,
            "delta_net": float(kpnl.sum()) - total_net,
            "dropped": dropped,
            "dropped_net": -dropped_pnl,
        })
    df_cum = pd.DataFrame(cum_rows)
    print(df_cum.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # ══════════════════════════════════════════════════════════════════════════
    # 4. WORST BARS — which individual bars are net negative?
    # ══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 80)
    print("4. WORST BARS (net negative, sorted by PnL)")
    print("=" * 80)
    df_neg = df_bars[df_bars["net"] < 0].sort_values("net")
    if len(df_neg):
        print(df_neg.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))
        print(f"\nTotal damage from net-negative bars: ${df_neg['net'].sum():,.0f} "
              f"across {int(df_neg['trades'].sum())} trades")
    else:
        print("No net-negative bars found.")

    # ── Save report ────────────────────────────────────────────────────────────
    out_file = _OUT / "tod_analysis.md"
    with open(out_file, "w") as f:
        f.write("# Time-of-Day Signal Analysis\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Filter:** ER_intra_6 >= {CHOP_MIN}, pinned 1.0R singleleg\n")
        f.write(f"**Total filled trades:** {len(filled)}\n\n")

        f.write("## 1. Per-bar expectancy\n\n")
        f.write(df_bars.to_markdown(index=False, floatfmt=".1f"))

        f.write("\n\n## 2. Session phases\n\n")
        f.write(df_phases.to_markdown(index=False, floatfmt=".1f"))

        f.write("\n\n## 3. Cumulative cutoff\n\n")
        f.write(df_cum.to_markdown(index=False, floatfmt=".1f"))

        f.write("\n\n## 4. Worst bars (net negative)\n\n")
        if len(df_neg):
            f.write(df_neg.to_markdown(index=False, floatfmt=".1f"))
            f.write(f"\n\nTotal damage: ${df_neg['net'].sum():,.0f} across "
                    f"{int(df_neg['trades'].sum())} trades\n")
        else:
            f.write("None.\n")

    log(f"Saved: {out_file}")


if __name__ == "__main__":
    main()
