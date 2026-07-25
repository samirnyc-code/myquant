"""mc_pnl_exec_modes.py — MC book PnL across the app's EXECUTION PRESETS (slippage modes).

Reproduces the ES app's "Execution model (ESA)" presets exactly by feeding
simulation_engine.EXECUTION_PRESETS (Optimistic/Realistic/Conservative/Brutal)
into simulate_trades the same way bar_analysis.py does: preset entry/exit slip
RANGES + calc_delay_ms + wire_delay_ms + entry_model='market' + exec_seed=42.
UI default preset = "Realistic". Also shows my earlier fixed-1t custom run.

Exit held at the APP DEFAULT single-leg exec (target_r=1.0, ratchet_r=0.0,
commission = ES default) so the only thing varying is the slippage mode. Exp $/tr
in every row.
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
from simulation_engine import (simulate_trades, INSTRUMENTS,  # noqa: E402
                               EXECUTION_PRESETS)
from stack_filter import compute_stack_columns  # noqa: E402

_SIG_TXT = _ROOT / "data" / "signals" / (
    "MyMicroChannel Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
)
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_COMM = INSTRUMENTS["ES"]["default_commission"]
_TARGET_R = 1.0
_RATCHET_R = 0.0
_STAMP = "20260725"


def _log(m):
    sys.stdout.buffer.write((str(m) + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()


def _row(f, label):
    if f.empty:
        _log(f"{label:26s} n=0")
        return dict(mode=label, n=0)
    net = float(f["NetPnL"].sum())
    n = len(f)
    exp = net / n
    net_r = (f["NetPnL"] / f["RiskDollar"]).to_numpy()
    wr = float((f["NetPnL"] > 0).mean()) * 100
    g = f.loc[f["NetPnL"] > 0, "NetPnL"].sum()
    l = f.loc[f["NetPnL"] < 0, "NetPnL"].sum()
    pf = float(g / abs(l)) if l else float("inf")
    fillrate = None
    by = f.groupby(pd.to_datetime(f["Date"]).dt.year)["NetPnL"].sum()
    pos = int((by > 0).sum())
    _log(f"{label:26s} n={n:5d}  Exp=${exp:+6.1f}/tr  ExpR={net_r.mean():+.3f}  "
         f"WR={wr:4.1f}%  PF={pf:4.2f}  net=${net:+10,.0f}  "
         f"worstYr=${by.min():+9,.0f}  yrs+{pos}/{len(by)}")
    return dict(mode=label, n=n, exp=exp, expR=float(net_r.mean()), wr=wr, pf=pf,
                net=net, worst_yr=float(by.min()), yrs_pos=pos, yrs=int(len(by)))


def main():
    sig = parse_signals(_SIG_TXT.read_text()).reset_index(drop=True)
    sig["MYID"] = np.arange(len(sig))
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    st = compute_stack_columns(sig, bars)
    sig["stack_pass"] = st["stack_pass"].to_numpy()
    dates = sorted(sig["Date"].unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {k: v for k, v in ticks_by_date.items() if not v.empty}

    _log(f"Exit fixed at APP DEFAULT: target_r={_TARGET_R}, ratchet_r={_RATCHET_R}, "
         f"commission=${_COMM}, entry_model=market, exec_seed=42")
    _log("Only the SLIPPAGE MODE varies. (UI default preset = Realistic)")
    _log("=" * 108)

    def run(entry_slip, exit_slip, calc_ms, wire_ms, label):
        raw = simulate_trades(
            signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
            target_r=_TARGET_R, ratchet_r=_RATCHET_R,
            entry_slip=entry_slip, exit_slip=exit_slip, stop_offset=1,
            tick_value=INSTRUMENTS["ES"]["tick_value"], contracts=1,
            commission=_COMM, entry_model="market",
            calc_delay_ms=calc_ms, wire_delay_ms=wire_ms, max_fill_ms=0,
            exec_seed=42, pb_round="nearest")
        f = raw[raw["Filled"] == True].copy()  # noqa: E712
        f["stack_pass"] = f["MYID"].map(sig.set_index("MYID")["stack_pass"])
        filled_rate = (raw["Filled"] == True).mean() * 100  # noqa: E712
        _log(f"### {label}   (fill rate {filled_rate:.1f}%)")
        _row(f, "  ALL MC (no filters)")
        _row(f[f["stack_pass"].astype(bool)], "  Stack v2 (S53 filters)")

    # my earlier fixed 1-tick custom (for reference)
    run(1.0, 1.0, 0, 0, "CUSTOM fixed 1t slip, no delay (what I quoted earlier)")
    # the four app presets, exactly as bar_analysis feeds them
    for name, pp in EXECUTION_PRESETS.items():
        run(pp["entry_slip"], pp["exit_slip"],
            int(pp["calc_delay_ms"]), int(pp.get("wire_delay_ms", 0)),
            f"{name}  (calc {pp['calc_delay_ms']}ms / wire {pp.get('wire_delay_ms',0)}ms / "
            f"in-slip {pp['entry_slip']} / out-slip {pp['exit_slip']})"
            + ("   <-- UI DEFAULT" if name == "Realistic" else ""))
    _log("=" * 108)
    _log("Trades scored independently (unlimited concurrent positions). Slip ranges are "
         "randomized within [min,max] ticks, seeded (exec_seed=42) to match the app.")


if __name__ == "__main__":
    main()
