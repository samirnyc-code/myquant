"""Always-In flip test — headless BA-style sim.

Compares the corrected-engine baseline (all MC signals) against the Always-In gates:
  - dir_match      : with-regime only (longs on AIL, shorts on AIS)
  - first_after    : the FIRST with-regime MC strictly after each flip
  - on_flip        : the MC fires on the very bar that flipped the regime (with-regime)

Single-leg pinned 1.0R, entry_slip=1, exit_slip=0, commission=$4.36 — matches the
corrected-engine defaults used by zlo_filter_sweep.py. Look-ahead-safe: AID state is
the most recent flip at/<= the signal bar's close (backward as-of).
"""
from __future__ import annotations
import sys
import gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                    # noqa: E402
import simulation_engine as sim   # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_AI      = Path(r"C:\Users\Admin\Documents\NinjaTrader 8\MCVolumeExport\AlwaysIn_State.csv")

SIM_PARAMS = dict(
    target_r=1.0, entry_slip=1, exit_slip=0, stop_offset=1,
    tick_value=12.5, contracts=1, commission=4.36,
)


def log(m): print(f"[ai-flip] {m}", flush=True)


def merge_alwaysin(signals: pd.DataFrame, ai: pd.DataFrame) -> pd.DataFrame:
    """Attach AID_State / AID_BarsSinceFlip / AID_OnFlipBar / AID_DirMatch /
    AID_FirstMatch — identical logic to bar_analysis.merge_alwaysin_overlay."""
    ai = ai.sort_values("BarTime").reset_index(drop=True)
    flip_dt = pd.to_datetime(ai["BarTime"])
    flip_dir = (ai["NewDir"].astype(str).str.upper().str.startswith("L")
                .map({True: 1, False: -1}).to_numpy())
    sig_dt = pd.to_datetime(signals["DateTime"])

    idx = flip_dt.searchsorted(sig_dt, side="right") - 1
    pre = idx < 0
    idx_c = idx.clip(0, len(ai) - 1)

    state = flip_dir[idx_c].astype(float); state[pre] = 0.0
    gov_dt = flip_dt.to_numpy()[idx_c]
    bars = (sig_dt.to_numpy() - gov_dt) / np.timedelta64(5, "m")
    bars = np.where(pre, np.nan, np.round(bars))

    out = signals.copy()
    out["AID_State"] = state
    out["AID_FlipIdx"] = np.where(pre, -1, idx_c)
    out["AID_BarsSinceFlip"] = bars
    out["AID_OnFlipBar"] = (bars == 0)
    is_long = out["Direction"].astype(str).str.upper().str.startswith("L")
    out["AID_DirMatch"] = ((is_long & (out["AID_State"] == 1))
                           | (~is_long & (out["AID_State"] == -1)))

    first = np.zeros(len(out), dtype=bool)
    cand = out["AID_DirMatch"].to_numpy() & (np.nan_to_num(bars, nan=0.0) >= 1)
    fidx = out["AID_FlipIdx"].to_numpy()
    seen = set()
    for i in np.argsort(sig_dt.to_numpy(), kind="stable"):
        if cand[i] and fidx[i] not in seen:
            first[i] = True; seen.add(fidx[i])
    out["AID_FirstMatch"] = first
    return out


def run_full_daybyday(signals, bars_by_date):
    """Simulate the full population one day at a time (bounds tick memory) and
    return the concatenated per-trade results df. AID_* columns ride through
    because simulate_trades seeds each result row from the input signal."""
    out = []
    days = sorted(signals["Date"].unique())
    for i, d in enumerate(days):
        ss = signals[signals["Date"] == d]
        try:
            t = massive.load_continuous_ticks(d)
            if not t.empty:
                res = sim.simulate_trades(ss, {d: t}, bars_by_date=bars_by_date,
                                          **SIM_PARAMS)
                out.append(res)
            del t
        except MemoryError:
            log(f"  !! MemoryError on {d} — skipped")
        gc.collect()
        if (i + 1) % 200 == 0:
            log(f"  ...{i+1}/{len(days)} days")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def summ(results):
    if results is None or results.empty:
        return None
    s = sim.compute_summary(results, SIM_PARAMS["commission"])
    return s or None


def fmt(label, s):
    if not s:
        return f"  {label:<14} 0 trades"
    return (f"  {label:<14} {s.get('n_trades',0):>5}t  "
            f"win={s.get('win_pct',0):>5.1f}%  "
            f"net=${s.get('net_total',0):>10,.0f}  "
            f"exp=${s.get('exp_dollar',0):>7.2f}  "
            f"expR={s.get('exp_r',0):>7.4f}  "
            f"PF={s.get('pf',0):>4.2f}  "
            f"maxDD=${s.get('max_dd',0):>9,.0f}  "
            f"PnL/DD={s.get('pnl_dd',0) if not np.isnan(s.get('pnl_dd',float('nan'))) else 0:>5.1f}")


def main():
    log("Loading data...")
    sig_raw = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    ai = pd.read_csv(_AI, parse_dates=["BarTime"])
    log(f"  Signals: {len(sig_raw)}, Bars: {len(bars)}, AID flips: {len(ai)}")

    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    sig = merge_alwaysin(sig_raw, ai)

    log("Simulating full population day-by-day...")
    res = run_full_daybyday(sig, bars_by_date)
    log(f"  {len(res)} result rows.\n")

    masks = {
        "baseline":    pd.Series(True, index=res.index),
        "dir_match":   res["AID_DirMatch"] == True,
        "first_after": res["AID_FirstMatch"] == True,
        "on_flip":     (res["AID_OnFlipBar"] == True) & (res["AID_DirMatch"] == True),
    }

    print("=" * 112)
    print("ALWAYS-IN FLIP TEST — full population, both directions, single-leg 1R")
    print("=" * 112)
    for name, m in masks.items():
        print(fmt(name, summ(res[m])))

    fa = res[masks["first_after"]]
    print("\n" + "-" * 112)
    print("FIRST-MC-AFTER-FLIP — by year (concentration check)")
    print("-" * 112)
    fa_years = pd.to_datetime(fa["DateTime"]).dt.year
    for yr in sorted(fa_years.unique()):
        print(fmt(str(yr), summ(fa[fa_years.values == yr])))

    print("\n" + "-" * 112)
    print("FIRST-MC-AFTER-FLIP — by direction")
    print("-" * 112)
    is_long = fa["Direction"].astype(str).str.upper().str.startswith("L")
    print(fmt("Long", summ(fa[is_long])))
    print(fmt("Short", summ(fa[~is_long])))


if __name__ == "__main__":
    main()
