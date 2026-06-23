"""Fade test on the RevFT (MyReversals) signal set.

Shows the gross/cost/net split for the ORIGINAL signals vs the FADE (reverse
direction + mirror stop across entry => stop<->target at 1:1). Proves whether the
losing curve has a fadeable directional edge or is just a cost/whipsaw bleed.

  gross  = frictionless (commission=0, slip=0)      -> directional edge only
  net    = realistic (commission=$5, entry_slip=1)  -> what you'd actually book
  costs  = gross - net                              -> the friction drag

Run day-by-day to bound tick memory; trades are scored independently.
"""
from __future__ import annotations
import sys, gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
import massive                    # noqa: E402
import simulation_engine as sim   # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_revft.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"

REAL = dict(target_r=1.0, entry_slip=1, exit_slip=0, stop_offset=1,
            tick_value=12.5, contracts=1, commission=5.0)
GROSS = dict(target_r=1.0, entry_slip=0, exit_slip=0, stop_offset=1,
             tick_value=12.5, contracts=1, commission=0.0)


def log(m): print(f"[fade-revft] {m}", flush=True)


def apply_fade(df):
    out = df.copy()
    is_long = out["Direction"].astype(str).str.upper().str.startswith("L")
    out["Direction"] = np.where(is_long, "Short", "Long")
    out["StopPrice"] = 2.0 * out["SignalPrice"] - out["StopPrice"]
    return out


def run_multi(scenarios, bars_by_date):
    """scenarios: {name: (signals_df, params)} — single tick-load pass for all."""
    acc = {name: [] for name in scenarios}
    days = sorted(set().union(*[set(s["Date"].unique()) for s, _ in scenarios.values()]))
    for i, d in enumerate(days):
        try:
            t = massive.load_continuous_ticks(d)
            if not t.empty:
                for name, (sg, params) in scenarios.items():
                    ss = sg[sg["Date"] == d]
                    if not ss.empty:
                        acc[name].append(
                            sim.simulate_trades(ss, {d: t}, bars_by_date=bars_by_date, **params))
            del t
        except MemoryError:
            pass
        gc.collect()
        if (i + 1) % 250 == 0:
            log(f"  ...{i+1}/{len(days)} days")
    return {name: (pd.concat(v, ignore_index=True) if v else pd.DataFrame())
            for name, v in acc.items()}


def summ(res, commission):
    return sim.compute_summary(res, commission) if res is not None and not res.empty else None


def line(label, gross, net):
    if not net:
        return f"  {label:<10} (no trades)"
    g = gross.get("net_total", 0) if gross else float("nan")
    n = net.get("net_total", 0)
    costs = (g - n) if gross else float("nan")
    dd = net.get("pnl_dd", float("nan"))
    return (f"  {label:<10} {net.get('n_trades',0):>5}t  win={net.get('win_pct',0):>5.1f}%  "
            f"gross=${g:>11,.0f}  costs=${costs:>10,.0f}  net=${n:>11,.0f}  "
            f"PF={net.get('pf',0):>4.2f}  expR={net.get('exp_r',0):>7.4f}  "
            f"maxDD=${net.get('max_dd',0):>10,.0f}  P/DD={dd if not np.isnan(dd) else 0:>5.1f}")


def main():
    log("Loading...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    fade = apply_fade(sig)
    log(f"{len(sig)} signals, {len(bars)} bars.\n")

    log("Running orig+fade x gross+net in one tick pass...")
    R = run_multi({
        "o_g": (sig, GROSS), "o_n": (sig, REAL),
        "f_g": (fade, GROSS), "f_n": (fade, REAL),
    }, bars_by_date)

    print("\n" + "=" * 118)
    print("FADE TEST — RevFT (MyReversals) set, single-leg 1R   [gross=frictionless, net=$5 comm + 1t entry slip]")
    print("=" * 118)
    print(line("ORIGINAL", summ(R["o_g"], 0.0), summ(R["o_n"], 5.0)))
    print(line("FADE", summ(R["f_g"], 0.0), summ(R["f_n"], 5.0)))

    print("\n" + "-" * 118)
    print("FADE net — by year (from the single full run, masked)")
    print("-" * 118)
    fn = R["f_n"]
    fy = pd.to_datetime(fn["DateTime"]).dt.year
    for yr in sorted(fy.unique()):
        print(line(str(yr), None, summ(fn[fy.values == yr], 5.0)))


if __name__ == "__main__":
    main()
