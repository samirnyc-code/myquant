"""ZLO Filter Sweep — headless BA-style sim across ZLO filter combinations.

Runs two passes:
  1. All filters off (baseline) + each ZLO filter combo
  2. Same, but sliced by ER10 thresholds (0.1, 0.2, ..., 0.9)

Uses the full signal set + tick data, single-leg pinned 1.0R, entry_slip=1,
exit_slip=0, commission=$4.36 — matches the S26 corrected-engine defaults.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import date

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                    # noqa: E402
import indicators as ind          # noqa: E402
import simulation_engine as sim   # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_ZLO     = _ROOT / "saved_signals" / "ba_zlo_overlay.parquet"
_OUT     = _ROOT / "docs" / "living" / "zlo_filter_sweep.csv"

SIM_PARAMS = dict(
    target_r=1.0, entry_slip=1, exit_slip=0, stop_offset=1,
    tick_value=12.5, contracts=1, commission=4.36,
)


def log(m):
    print(f"[zlo-sweep] {m}", flush=True)


def merge_zlo(signals: pd.DataFrame, zlo: pd.DataFrame) -> pd.DataFrame:
    """Left-join ZLO data onto signals by nearest DateTime."""
    zlo_dt = pd.to_datetime(zlo["DateTime"])
    sig_dt = pd.to_datetime(signals["DateTime"])
    idx = zlo_dt.searchsorted(sig_dt, side="right") - 1
    idx = idx.clip(0, len(zlo) - 1)
    out = signals.copy()
    for col in ["Oscillator", "BaseTrend", "TrendState",
                "LongMomSig", "ShortMomSig", "LongKeyRetSig",
                "ShortKeyRetSig", "LongRetSig", "ShortRetSig"]:
        if col in zlo.columns:
            out[f"ZLO_{col}"] = zlo[col].values[idx]
    return out


def apply_zlo_filter(df: pd.DataFrame, filt_name: str) -> pd.DataFrame:
    """Return subset of df matching the named ZLO filter."""
    if filt_name == "none":
        return df

    is_long = df["Direction"].str.upper().str.startswith("L")

    if filt_name == "trend_dir":
        mask = ((is_long & (df["ZLO_BaseTrend"] == 1))
                | (~is_long & (df["ZLO_BaseTrend"] == -1)))
    elif filt_name == "trend_dir_strict":
        mask = ((is_long & (df["ZLO_BaseTrend"] == 1))
                | (~is_long & (df["ZLO_BaseTrend"] == -1)))
        mask = mask & (df["ZLO_TrendState"].abs() >= 3)
    elif filt_name == "ts_ge3":
        mask = df["ZLO_TrendState"].abs() >= 3
    elif filt_name == "ts_ge4":
        mask = df["ZLO_TrendState"].abs() >= 4
    elif filt_name == "ts_dir_ge3":
        mask = ((is_long & (df["ZLO_TrendState"] >= 3))
                | (~is_long & (df["ZLO_TrendState"] <= -3)))
    elif filt_name == "ts_dir_ge4":
        mask = ((is_long & (df["ZLO_TrendState"] >= 4))
                | (~is_long & (df["ZLO_TrendState"] <= -4)))
    elif filt_name == "osc_sign":
        mask = ((is_long & (df["ZLO_Oscillator"] > 0))
                | (~is_long & (df["ZLO_Oscillator"] < 0)))
    elif filt_name == "osc_sign+trend":
        mask = (((is_long & (df["ZLO_Oscillator"] > 0))
                 | (~is_long & (df["ZLO_Oscillator"] < 0)))
                & ((is_long & (df["ZLO_BaseTrend"] == 1))
                   | (~is_long & (df["ZLO_BaseTrend"] == -1))))
    elif filt_name == "osc_sign+ts3":
        mask = (((is_long & (df["ZLO_Oscillator"] > 0))
                 | (~is_long & (df["ZLO_Oscillator"] < 0)))
                & (df["ZLO_TrendState"].abs() >= 3))
    elif filt_name == "confluence_mom":
        mask = ((is_long & (df["ZLO_LongMomSig"] == 1))
                | (~is_long & (df["ZLO_ShortMomSig"] == 1)))
    elif filt_name == "confluence_any":
        mask = ((is_long & ((df["ZLO_LongMomSig"] == 1)
                             | (df["ZLO_LongKeyRetSig"] == 1)
                             | (df["ZLO_LongRetSig"] == 1)))
                | (~is_long & ((df["ZLO_ShortMomSig"] == 1)
                                | (df["ZLO_ShortKeyRetSig"] == 1)
                                | (df["ZLO_ShortRetSig"] == 1))))
    else:
        raise ValueError(f"Unknown filter: {filt_name}")

    return df[mask.fillna(False)].copy()


ZLO_FILTERS = [
    "none",
    "trend_dir",
    "ts_ge3",
    "ts_ge4",
    "ts_dir_ge3",
    "ts_dir_ge4",
    "osc_sign",
    "trend_dir_strict",
    "osc_sign+trend",
    "osc_sign+ts3",
    "confluence_mom",
    "confluence_any",
]

ER10_THRESHOLDS = [round(x * 0.1, 1) for x in range(1, 10)]  # 0.1 .. 0.9


EMPTY_ROW = dict(trades=0, net=0, exp=0, exp_r=0, pf=0, win_pct=0,
                  avg_win=0, avg_loss=0, maxdd=0, pnl_dd=0, sqn=0, sharpe=0,
                  n_wins=0, n_stop=0, n_sess=0)


def run_sim(signals: pd.DataFrame, ticks_by_date: dict,
            bars_by_date: dict | None) -> dict:
    """Run simulate_trades and return summary stats."""
    if signals.empty:
        return EMPTY_ROW.copy()

    results = sim.simulate_trades(
        signals, ticks_by_date, bars_by_date=bars_by_date, **SIM_PARAMS)

    s = sim.compute_summary(results, SIM_PARAMS["commission"])
    if not s:
        return EMPTY_ROW.copy()

    return dict(
        trades=s.get("n_trades", 0),
        net=round(s.get("net_total", 0), 0),
        exp=round(s.get("exp_dollar", 0), 1),
        exp_r=round(s.get("exp_r", 0), 4),
        pf=round(s.get("pf", 0), 2),
        win_pct=round(s.get("win_pct", 0), 1),
        avg_win=round(s.get("avg_win", 0), 0),
        avg_loss=round(s.get("avg_loss", 0), 0),
        maxdd=round(s.get("max_dd", 0), 0),
        pnl_dd=round(s.get("pnl_dd", 0), 2) if not np.isnan(s.get("pnl_dd", float("nan"))) else 0,
        sqn=round(s.get("sqn", 0), 2),
        sharpe=round(s.get("sharpe", 0), 2),
        n_wins=s.get("n_wins", 0),
        n_stop=s.get("n_stop", 0),
        n_sess=s.get("n_sess", 0),
    )


def main():
    log("Loading data...")
    sig_raw = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    zlo = pd.read_parquet(_ZLO)
    log(f"  Signals: {len(sig_raw)}, Bars: {len(bars)}, ZLO: {len(zlo)}")

    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # Merge ZLO onto signals
    sig = merge_zlo(sig_raw, zlo)

    # Tag signals for ER10
    log("Tagging signals for ER10...")
    tags = ind.tag_signals(sig, bars, periods=("session",))
    er10 = tags["ER_intra_2"].astype(float) if "ER_intra_2" in tags.columns else None
    if er10 is not None:
        sig["ER10"] = er10.values

    # Load ticks for all signal dates
    all_dates = sorted(sig["Date"].unique())
    log(f"Loading ticks for {len(all_dates)} signal days...")
    ticks_by_date = {}
    for d in all_dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"  Loaded {len(ticks_by_date)} days of ticks.")

    rows = []

    # -- Pass 1: All filters off, sweep ZLO filters --------------------------
    log("\n=== PASS 1: NO ER FILTER (all signals) ===")
    for filt_name in ZLO_FILTERS:
        subset = apply_zlo_filter(sig, filt_name)
        log(f"  {filt_name}: {len(subset)} signals...")
        stats = run_sim(subset, ticks_by_date, bars_by_date)
        stats["er10_min"] = "none"
        stats["zlo_filter"] = filt_name
        rows.append(stats)
        log(f"    -> {stats['trades']}t W{stats['n_wins']}/S{stats['n_stop']} "
            f"win={stats['win_pct']:.1f}% net=${stats['net']:,.0f} exp=${stats['exp']:.1f} "
            f"PF={stats['pf']:.2f} maxDD=${stats['maxdd']:,.0f} PnL/DD={stats['pnl_dd']:.1f}")

    # -- Pass 2: ER10 slices × ZLO filters ------------------------------------
    if er10 is not None:
        for thr in ER10_THRESHOLDS:
            er_mask = sig["ER10"] >= thr
            sig_er = sig[er_mask].copy()
            if sig_er.empty:
                log(f"\n=== ER10 >= {thr:.1f}: 0 signals — skipping ===")
                continue
            log(f"\n=== ER10 >= {thr:.1f}: {len(sig_er)} signals ===")
            for filt_name in ZLO_FILTERS:
                subset = apply_zlo_filter(sig_er, filt_name)
                if subset.empty:
                    stats = EMPTY_ROW.copy()
                else:
                    log(f"  {filt_name}: {len(subset)} signals...")
                    stats = run_sim(subset, ticks_by_date, bars_by_date)
                stats["er10_min"] = f"{thr:.1f}"
                stats["zlo_filter"] = filt_name
                rows.append(stats)
                log(f"    -> {stats['trades']}t W{stats['n_wins']}/S{stats['n_stop']} "
                    f"win={stats['win_pct']:.1f}% net=${stats['net']:,.0f} exp=${stats['exp']:.1f} "
                    f"PF={stats['pf']:.2f} maxDD=${stats['maxdd']:,.0f} PnL/DD={stats['pnl_dd']:.1f}")

    # -- Output --------------------------------------------------------------─
    df = pd.DataFrame(rows)
    col_order = ["er10_min", "zlo_filter", "trades", "n_wins", "n_stop", "n_sess",
                 "win_pct", "net", "exp", "exp_r", "pf", "avg_win", "avg_loss",
                 "maxdd", "pnl_dd", "sqn", "sharpe"]
    df = df[[c for c in col_order if c in df.columns]]
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_OUT, index=False)

    pd.set_option("display.width", 240, "display.max_columns", 20)
    print("\n" + "=" * 100)
    print("ZLO FILTER SWEEP — FULL RESULTS")
    print("=" * 100)

    for er_val in ["none"] + [f"{t:.1f}" for t in ER10_THRESHOLDS]:
        chunk = df[df["er10_min"] == er_val]
        if chunk.empty:
            continue
        label = "NO ER FILTER" if er_val == "none" else f"ER10 >= {er_val}"
        print(f"\n-- {label} --")
        print(chunk.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    log(f"\nResults saved to {_OUT}")


if __name__ == "__main__":
    main()
