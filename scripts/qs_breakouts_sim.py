"""QS Breakouts — first cost-aware P&L (headless).

Detection = QSConfig.paper() (the whitepaper SQN-study config). Sim = the project
tick engine (simulate_trades) with real costs. Two trade definitions, per the open
question:
    (a) BO-family : SignalType in {BO, BO+FT, BigBO}   (~9/day)
    (b) FT-only   : SignalType == BO+FT  (completed 2-bar)  (~2/day)

R = |SignalPrice - StopPrice| (the paper iStop). Target = cfg.target_r (1R).
Entry = market at signal-bar close (BTC ~ next tick). Costs: $4.36 RT + slip.

Run: python scripts/qs_breakouts_sim.py
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

# FRICTIONLESS — reproduce the whitepaper (no commission, no slippage).
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, commission=0.0,
            multileg=False, threeleg=False, overrides=None, entry_model="market")
SLIPS = [("frictionless", 0, 0)]
TARGETS = [1.0, 2.0]
N_CHUNKS = 6


def log(m): print(f"[qsim] {m}", flush=True)


def stat(pnl, r):
    n = len(pnl)
    if n == 0:
        return None
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    return dict(n=n, net=net, expR=float(np.nanmean(r)),
                pf=(gw / gl if gl > 0 else float("inf")),
                win=float((pnl > 0).mean() * 100),
                ciR=(float(1.96 * np.nanstd(r, ddof=1) / np.sqrt(n)) if n > 1 else np.nan),
                sqn=(float(np.nanmean(r) / np.nanstd(r, ddof=1) * np.sqrt(n))
                     if n > 1 and np.nanstd(r, ddof=1) > 0 else np.nan))


def row(lbl, s):
    if s is None:
        return f"| {lbl} | 0 | — | — | — | — | — |"
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return (f"| {lbl} | {s['n']:,} | ${s['net']:,.0f} | {s['expR']:+.3f}±{s['ciR']:.3f} "
            f"| {s['win']:.1f}% | {pf} | {s['sqn']:.2f} |")


def run(sig, label):
    """Sim one signal subset across slips x targets; print a table."""
    sig = sig[sig["FilterStatus"] == "ok"].reset_index(drop=True)
    sig["_date"] = pd.to_datetime(sig["DateTime"]).dt.date
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    dates = np.array(sorted(sig["_date"].unique()), object)

    acc = {(tr, sl[0]): {"pnl": [], "r": []} for tr in TARGETS for sl in SLIPS}
    for ci, chunk in enumerate(np.array_split(dates, N_CHUNKS)):
        sub = sig[sig["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for tr in TARGETS:
            for lbl, es, xs in SLIPS:
                res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                      target_r=tr, entry_slip=es, exit_slip=xs,
                                      **BASE).reset_index(drop=True)
                fl = (res["Filled"] == True).values
                rf = res.loc[fl]
                pnl = rf["NetPnL"].values
                r = pnl / rf["RiskDollar"].replace(0, np.nan).values
                acc[(tr, lbl)]["pnl"].append(pnl)
                acc[(tr, lbl)]["r"].append(r)
        del tbd; gc.collect()
        log(f"  [{label}] chunk {ci+1}/{N_CHUNKS}")

    log(f"\n===== {label} =====")
    log("| target / slip | n | net $ | exp R | win | PF | SQN |")
    log("|---|---|---|---|---|---|---|")
    for tr in TARGETS:
        for lbl, _, _ in SLIPS:
            a = acc[(tr, lbl)]
            s = stat(np.concatenate(a["pnl"]), np.concatenate(a["r"])) if a["pnl"] else None
            log(row(f"{tr:.1f}R / {lbl}", s))


def main():
    bars = pd.read_parquet(_BARS)
    cfg = QSConfig.paper()
    sig = detect(bars, cfg)
    log(f"paper config: {len(sig):,} signals, "
        f"{(sig['FilterStatus']=='ok').sum():,} ok")
    bo_family = sig[sig["SignalType"].isin(["BO", "BO+FT", "BigBO"])]
    ft_only = sig[sig["SignalType"] == "BO+FT"]
    log(f"  BO-family: {len(bo_family):,}   FT-only: {len(ft_only):,}")
    run(bo_family, "(a) BO-family")
    run(ft_only, "(b) FT-only")


if __name__ == "__main__":
    main()
