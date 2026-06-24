"""QS Breakouts — breakeven-stop trigger sweep (headless, frictionless).

Question: does a mechanical BE stop reproduce Ali's ~83% win + shrink avg loss
toward his ~0.18R — and do the $ survive (BE always costs some winners)?

Mechanic = engine ratchet: after +X*R favorable, move stop -> entry (BE).
Subset = FT-only (WP BO+FT, entry bar 2). Target 1R. No costs.
X=0.00 is the no-BE baseline.

Run: python scripts/qs_breakouts_be_sweep.py
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
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, commission=0.0,
            multileg=False, threeleg=False, overrides=None, entry_model="market",
            entry_slip=0, exit_slip=0, target_r=1.0, ratchet_dest="BE",
            ratchet_lock_r=0.0)
RATCHETS = [0.0, 0.25, 0.5, 0.75, 1.0]   # 0 = no BE
N_CHUNKS = 6


def log(m): print(f"[qsbe] {m}", flush=True)


def stat(pnl, r):
    n = len(pnl)
    wins = r > 0
    std = np.nanstd(r, ddof=1) if n > 1 else np.nan
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    return dict(n=n, win=wins.mean()*100, expR=np.nanmean(r),
                pf=(gw/gl if gl > 0 else np.inf),
                sqn=(np.nanmean(r)/std*np.sqrt(n) if (n > 1 and std > 0) else np.nan),
                net=pnl.sum(),
                avgW=(r[wins].mean() if wins.any() else np.nan),
                avgL=(r[~wins].mean() if (~wins).any() else np.nan),
                scratch=float((np.abs(r) < 0.05).mean()*100))


def main():
    bars = pd.read_parquet(_BARS)
    sig = detect(bars, QSConfig.paper())
    ft = sig[(sig["SignalType"] == "BO+FT") & (sig["FilterStatus"] == "ok")].reset_index(drop=True)
    ft["_date"] = pd.to_datetime(ft["DateTime"]).dt.date
    bbd = {d: g.reset_index(drop=True) for d, g in
           bars.drop(columns=["Contract"], errors="ignore").groupby(bars["DateTime"].dt.date)}
    dates = np.array(sorted(ft["_date"].unique()), object)
    log(f"FT-only ok signals: {len(ft):,}")

    acc = {x: {"pnl": [], "r": []} for x in RATCHETS}
    for ci, chunk in enumerate(np.array_split(dates, N_CHUNKS)):
        sub = ft[ft["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for x in RATCHETS:
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  ratchet_r=x, **BASE).reset_index(drop=True)
            fl = (res["Filled"] == True).values
            rf = res.loc[fl]
            pnl = rf["NetPnL"].values
            r = pnl / rf["RiskDollar"].replace(0, np.nan).values
            acc[x]["pnl"].append(pnl); acc[x]["r"].append(r)
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS}")

    log("\n===== BE-trigger sweep (FT-only, 1R, frictionless, 1 ES contract) =====")
    log(f"{'BE@+R':>6s} {'n':>5s} {'win%':>6s} {'expR':>7s} {'avgW':>6s} "
        f"{'avgL':>6s} {'scr%':>5s} {'PF':>5s} {'SQN':>6s} {'net$':>11s}")
    for x in RATCHETS:
        s = stat(np.concatenate(acc[x]["pnl"]), np.concatenate(acc[x]["r"]))
        lbl = "none" if x == 0 else f"{x:.2f}"
        pf = "inf" if s["pf"] == np.inf else f"{s['pf']:.2f}"
        log(f"{lbl:>6s} {s['n']:5,d} {s['win']:6.1f} {s['expR']:+7.3f} "
            f"{s['avgW']:6.2f} {s['avgL']:6.2f} {s['scratch']:5.1f} {pf:>5s} "
            f"{s['sqn']:6.2f} ${s['net']:>10,.0f}")
    log("\nAli (WP): win ~83-86%, avgL ~ -0.18R, SQN 7.4-8.9 (hold 1R, no scaling)")


if __name__ == "__main__":
    main()
