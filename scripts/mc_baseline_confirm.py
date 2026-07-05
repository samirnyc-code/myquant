"""Confirm the UNFILTERED MC baseline of record (S53 / Fable 2026-07-04).

Target to reproduce (docs/living/fable5_mc_findings.md):
    All MC @ 1R:  n=5540  +0.021R [-0.002,+0.044]  WR=51%  PF=1.10  $+184,296  yrs+5/6
    Longs  @ 1R:  n=2959  +0.035R  WR=53%  PF=1.15  $+143,986
    All MC @ 2R:  n=5540  +0.038R  WR=44%  PF=1.13  $+262,621

Realistic exec: entry next-bar-open +1 tick slip, exit_slip=1, stop_offset=1,
commission $4.36/RT, 1 contract. NO filters (truly all signals).

Mirrors scripts/run_setup_pipeline.py's simulate_trades call exactly — same engine
as the app. Reads the latest committed signal export from data/signals/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive  # noqa: E402
from bar_analysis import parse_signals  # noqa: E402
from simulation_engine import simulate_trades, compute_summary, INSTRUMENTS  # noqa: E402

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_COMM = 4.36  # baseline-of-record commission (NOT the current INSTRUMENTS default 5.0)


def _log(m):
    print(m, flush=True)


def _boot_ci(pnl_r, iters=5000, seed=42):
    """95% CI on mean R via bootstrap (matches project convention)."""
    rng = np.random.default_rng(seed)
    n = len(pnl_r)
    means = np.array([rng.choice(pnl_r, n, replace=True).mean() for _ in range(iters)])
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def _report(filled, label):
    """ExpR / WR / PF / net / CI / per-year from a filled results frame."""
    r = filled["R_achieved"].to_numpy()                       # GROSS R (engine exp_r)
    net_r = (filled["NetPnL"] / filled["RiskDollar"]).to_numpy()  # NET R (after comm)
    net = float(filled["NetPnL"].sum())
    wr = float((filled["NetPnL"] > 0).mean()) * 100
    gains = filled.loc[filled["NetPnL"] > 0, "NetPnL"].sum()
    losses = filled.loc[filled["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(gains / abs(losses)) if losses else float("inf")
    lo, hi = _boot_ci(net_r)  # CI on NET R (matches Fable's reported metric)
    nlo, nhi = lo, hi
    yr = pd.to_datetime(filled["Date"]).dt.year
    by = filled.groupby(yr)["NetPnL"].sum()
    pos = int((by > 0).sum())
    _log(f"{label:14s} n={len(filled):5d}  netR={net_r.mean():+.3f} "
         f"[{nlo:+.3f},{nhi:+.3f}]  grossR={r.mean():+.3f}  "
         f"WR={wr:.0f}%  PF={pf:.2f}  ${net:+,.0f}  yrs+{pos}/{len(by)}  "
         f"(comm drag={r.mean() - net_r.mean():+.4f}R, avgRisk=${filled['RiskDollar'].mean():,.0f})")
    _log("   " + "  ".join(f"{y}:${v:+,.0f}" for y, v in by.items()))
    return dict(n=len(filled), expR=float(r.mean()), ci=(lo, hi), wr=wr, pf=pf, net=net)


def main():
    _log(f"Signals: {_SIG_TXT.name}")
    sig = parse_signals(_SIG_TXT.read_text())
    _log(f"Parsed {len(sig)} MC signals ({sig['Date'].min()} → {sig['Date'].max()})")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    dates = sorted(sig["Date"].unique())
    _log(f"Loading tick cache for {len(dates)} signal-days…")
    ticks_by_date = {}
    for i, d in enumerate(dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
        if (i + 1) % 200 == 0:
            _log(f"  …{i + 1}/{len(dates)} days")
    _log(f"Tick cache loaded for {len(ticks_by_date)}/{len(dates)} days.\n")

    bp = dict(entry_slip=1.0, exit_slip=1.0, stop_offset=1,
              tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
              commission=_COMM, ratchet_r=0.0, pb_round="nearest")

    _log("=" * 78)
    _log("TARGET OF RECORD (Fable 2026-07-04):")
    _log("  All MC @ 1R:  n=5540  +0.021R [-0.002,+0.044]  WR=51%  PF=1.10  $+184,296")
    _log("  Longs  @ 1R:  n=2959  +0.035R              WR=53%  PF=1.15  $+143,986")
    _log("  All MC @ 2R:  n=5540  +0.038R              WR=44%  PF=1.13  $+262,621")
    _log("=" * 78 + "\n")

    for tr in (1.0, 2.0):
        raw = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                              bars_by_date=bars_by_date, target_r=tr,
                              multileg=False, threeleg=False, **bp)
        rs = compute_summary(raw, commission=_COMM, contracts=1)
        filled = raw[raw["Filled"] == True].copy()  # noqa: E712
        filled.to_parquet(_ROOT / "data" / "signals" / f"_mc_baseline_filled_{tr:g}R.parquet")
        _log(f"--- target {tr:g}R ---  (compute_summary xcheck: "
             f"ExpR={rs.get('exp_r', float('nan')):+.4f} "
             f"[{rs.get('exp_r_ci_lo', float('nan')):+.4f},{rs.get('exp_r_ci_hi', float('nan')):+.4f}] "
             f"PF={rs.get('pf', float('nan')):.3f})")
        _report(filled, f"All MC @ {tr:g}R")
        if tr == 1.0:
            _report(filled[filled["Direction"] == "Long"], "  Longs @ 1R")
            _report(filled[filled["Direction"] == "Short"], "  Shorts @ 1R")
        _log("")


if __name__ == "__main__":
    main()
