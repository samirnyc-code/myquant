"""WP-detector sim: BO+FT and Rev+FT, Ali geometry (stop 1x signal range, tgt 1R).
Frictionless. Compare to Ali: BO win 76%/SQN 6.3/AvgR 0.6; Rev SQN 4.4 (pre-filter).
Run: python scripts/qs_wp_sim.py
"""
from __future__ import annotations
import sys, gc
from pathlib import Path
import numpy as np, pandas as pd
_ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(_ROOT))
import massive
from simulation_engine import simulate_trades
from qs_setups import detect_wp, QSConfig

_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, commission=0.0, multileg=False,
            threeleg=False, overrides=None, entry_model="market", entry_slip=0, exit_slip=0)


def stat(pnl, r):
    n = len(pnl); wins = pnl > 0; std = np.nanstd(r, ddof=1) if n > 1 else np.nan
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    return (f"n={n:,} win={wins.mean()*100:4.1f}% expR={np.nanmean(r):+.3f} "
            f"avgR={np.nanmean(r):+.2f} PF={gw/gl if gl>0 else 99:4.2f} "
            f"SQN={np.nanmean(r)/std*np.sqrt(n) if (n>1 and std>0) else 0:5.2f} "
            f"net=${pnl.sum():,.0f}")


def run(stype, target_r):
    bars = pd.read_parquet(_BARS)
    cfg = QSConfig.wp()  # stop=1x signal_range already set
    sig = detect_wp(bars, cfg)
    sig = sig[(sig.SignalType == stype) & (sig.FilterStatus == "ok")].reset_index(drop=True)
    sig["_d"] = pd.to_datetime(sig.DateTime).dt.date
    bbd = {d: g.reset_index(drop=True) for d, g in
           bars.drop(columns=["Contract"], errors="ignore").groupby(bars.DateTime.dt.date)}
    dates = np.array(sorted(sig["_d"].unique()), object)
    P, R = [], []
    for chunk in np.array_split(dates, 6):
        sub = sig[sig["_d"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd, target_r=target_r, **BASE)
        rf = res[res.Filled == True]
        P.append(rf.NetPnL.values); R.append(rf.NetPnL.values / rf.RiskDollar.replace(0, np.nan).values)
        del tbd; gc.collect()
    print(f"  {stype} @ {target_r}R : {stat(np.concatenate(P), np.concatenate(R))}", flush=True)


def main():
    print("WP detector, Ali geometry (stop 1x signal range), frictionless, 1 ES, 2021-2026")
    for st in ["BO+FT", "Rev+FT"]:
        for tr in [1.0, 2.0]:
            run(st, tr)
    print("\nAli (2020, 100 hand-picked): BO win 76% SQN 6.3 AvgR 0.6 | Rev SQN 4.4 (pre legs/PB filter)")


if __name__ == "__main__":
    main()
