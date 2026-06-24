"""Dump the per-trade list for the WP setup (FT-only, paper, 1R, frictionless).

Writes a CSV of every filled trade with entry/stop/target/exit + R + $, so the
~1,100 trades can be inspected directly. Run: python scripts/qs_dump_trades.py
"""
from __future__ import annotations
import sys, gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
import massive                                          # noqa: E402
from simulation_engine import simulate_trades           # noqa: E402
from qs_setups import detect, QSConfig                  # noqa: E402

_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT = _ROOT / "docs" / "living" / "qs_periods"
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, commission=0.0,
            multileg=False, threeleg=False, overrides=None, entry_model="market",
            entry_slip=0, exit_slip=0, target_r=1.0)


def main():
    _OUT.mkdir(parents=True, exist_ok=True)
    bars = pd.read_parquet(_BARS)
    sig = detect(bars, QSConfig.paper())
    ft = sig[(sig["SignalType"] == "BO+FT") & (sig["FilterStatus"] == "ok")].reset_index(drop=True)
    ft["_date"] = pd.to_datetime(ft["DateTime"]).dt.date
    bbd = {d: g.reset_index(drop=True) for d, g in
           bars.drop(columns=["Contract"], errors="ignore").groupby(bars["DateTime"].dt.date)}
    dates = np.array(sorted(ft["_date"].unique()), object)

    out = []
    for ci, chunk in enumerate(np.array_split(dates, 6)):
        sub = ft[ft["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd, **BASE).reset_index(drop=True)
        # carry signal context onto results (row-aligned with sub)
        for col in ["SignalType", "Direction", "DateTime", "BarNum"]:
            if col in sub.columns and col not in res.columns:
                res[col] = sub[col].values
        out.append(res[res["Filled"] == True].copy())
        del tbd; gc.collect()
        print(f"chunk {ci+1}/6", flush=True)

    res = pd.concat(out, ignore_index=True)
    res["R"] = (res["NetPnL"] / res["RiskDollar"].replace(0, np.nan)).round(3)
    res = res.sort_values("DateTime").reset_index(drop=True)
    path = _OUT / "FTonly_1R_frictionless_TRADES.csv"
    res.to_csv(path, index=False)
    print(f"\nwrote {len(res):,} trades -> {path}")
    print("columns:", ", ".join(res.columns))
    # quick console peek
    cols = [c for c in ["DateTime", "Direction", "SignalPrice", "EntryPrice",
                        "ActualStop", "Target", "ExitTime", "ExitPrice",
                        "ExitReason", "NetPnL", "R"] if c in res.columns]
    print("\nfirst 12 trades:")
    print(res[cols].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
