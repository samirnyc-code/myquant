"""mc_pnl_reconcile.py — MC book PnL across exec configs, app-faithful, with Exp $.

Reconciles the numbers I quoted (3R + BE ratchet + $4.36) against the ES app's
DEFAULT single-leg exec (target_r=1.0, ratchet_r=0.0, commission = ES default),
which is what run_setup_pipeline.py / the Bar Analyzer main-sim use. Same engine
(simulation_engine.simulate_trades). Every row reports Exp $/tr (expectancy).
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
from simulation_engine import simulate_trades, INSTRUMENTS  # noqa: E402
from stack_filter import compute_stack_columns  # noqa: E402

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_APP_COMM = INSTRUMENTS["ES"]["default_commission"]


def _log(m):
    sys.stdout.buffer.write((str(m) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def _report(f, comm, label):
    if f.empty:
        _log(f"{label:34s} n=0")
        return
    net = float(f["NetPnL"].sum())
    n = len(f)
    exp = net / n                          # Exp $/tr (expectancy)
    net_r = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    wr = float((f["NetPnL"] > 0).mean()) * 100
    g = f.loc[f["NetPnL"] > 0, "NetPnL"].sum()
    l = f.loc[f["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(g / abs(l)) if l else float("inf")
    yr = pd.to_datetime(f["Date"]).dt.year
    by = f.groupby(yr)["NetPnL"].sum()
    pos = int((by > 0).sum())
    _log(f"{label:34s} n={n:5d}  Exp=${exp:+6.1f}/tr  ExpR={net_r.mean():+.3f}  "
         f"WR={wr:4.1f}%  PF={pf:4.2f}  net=${net:+10,.0f}  "
         f"worstYr=${by.min():+9,.0f}  yrs+{pos}/{len(by)}")


def main():
    sig = parse_signals(_SIG_TXT.read_text()).reset_index(drop=True)
    sig["MYID"] = np.arange(len(sig))
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    st = compute_stack_columns(sig, bars)
    sig["stack_pass"] = st["stack_pass"].to_numpy()

    dates = sorted(sig["Date"].unique())
    ticks_by_date = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t

    _log(f"ES app default commission = ${_APP_COMM}/RT   (my study used $4.36)")
    _log("=" * 104)

    configs = [
        # (label, target_r, ratchet_r, comm)
        ("APP DEFAULT 1R no-ratchet $5", 1.0, 0.0, _APP_COMM),
        ("1R no-ratchet $4.36",          1.0, 0.0, 4.36),
        ("2R no-ratchet $5",             2.0, 0.0, _APP_COMM),
        ("3R BE-ratchet@1R $4.36 (mine)", 3.0, 1.0, 4.36),
        ("3R BE-ratchet@1R $5",          3.0, 1.0, _APP_COMM),
    ]
    for label, tr, rr, comm in configs:
        raw = simulate_trades(
            signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
            target_r=tr, ratchet_r=rr, ratchet_dest="BE",
            entry_slip=1.0, exit_slip=1.0, stop_offset=1,
            tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
            commission=comm, pb_round="nearest")
        f = raw[raw["Filled"] == True].copy()  # noqa: E712
        f["stack_pass"] = f["MYID"].map(sig.set_index("MYID")["stack_pass"])
        _log(f"--- {label} ---")
        _report(f, comm, "  ALL MC (no filters)")
        _report(f[f["stack_pass"].astype(bool)], comm, "  Stack v2 (S53 filters)")
    _log("=" * 104)
    _log("Note: trades scored independently (unlimited concurrent positions) — a net-$ "
         "signal-quality total, NOT a 1-contract sequential equity curve.")


if __name__ == "__main__":
    main()
