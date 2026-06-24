"""Reproduce Ali's stated geometry for FT-only (entry bar 2, hold for 1R).

Ali's text is self-inconsistent on stop vs target, so test the candidates:
  A1  stop = 2x combined, target = 1x combined   (RR 1:2; literal "1R=combined")
  A2  stop = 1x combined, target = 1x combined   (RR 1:1; symmetric measured move)
  A3  stop = 2x combined, target = 2x combined   (what I ran before -> EOD drift, ref)

Compare win%, exp, hold-to-target bars, EOD% to Ali (win 83-86%, lifecycle ~7-8 bars).
Frictionless. Run: python scripts/qs_ali_geometry.py
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
            entry_slip=0, exit_slip=0)
N_CHUNKS = 6

# (label, twobar_stop_mult, target_r)
CONFIGS = [
    ("A1 stop2x / tgt1x (RR 1:2)", 2.0, 0.5),
    ("A2 stop1x / tgt1x (RR 1:1)", 1.0, 1.0),
    ("A3 stop2x / tgt2x (ref/EOD)", 2.0, 1.0),
]


def log(m): print(f"[ali] {m}", flush=True)


def main():
    bars = pd.read_parquet(_BARS)
    bbd = {d: g.reset_index(drop=True) for d, g in
           bars.drop(columns=["Contract"], errors="ignore").groupby(bars["DateTime"].dt.date)}

    # detect once per distinct stop_mult
    sigs = {}
    for mult in {c[1] for c in CONFIGS}:
        cfg = QSConfig.paper(twobar_stop_mult=mult)
        s = detect(bars, cfg)
        s = s[(s["SignalType"] == "BO+FT") & (s["FilterStatus"] == "ok")].reset_index(drop=True)
        s["_date"] = pd.to_datetime(s["DateTime"]).dt.date
        sigs[mult] = s
    dates = np.array(sorted(sigs[CONFIGS[0][1]]["_date"].unique()), object)

    acc = {lbl: [] for lbl, _, _ in CONFIGS}
    for ci, chunk in enumerate(np.array_split(dates, N_CHUNKS)):
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for lbl, mult, tr in CONFIGS:
            sub = sigs[mult][sigs[mult]["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  target_r=tr, **BASE).reset_index(drop=True)
            res = res[res["Filled"] == True].copy()
            res["held"] = res["ExitBarNum"] - res["EntryBarNum"]
            res["r"] = res["NetPnL"] / res["RiskDollar"].replace(0, np.nan)
            acc[lbl].append(res[["NetPnL", "r", "held", "ExitReason"]])
        del tbd; gc.collect()
        log(f"chunk {ci+1}/{N_CHUNKS}")

    log("\n===== Ali geometry test (FT-only, frictionless, 1 ES) =====")
    log(f"{'config':30s} {'n':>5s} {'win%':>6s} {'exp$':>7s} {'expR':>7s} "
        f"{'tgt%':>5s} {'eod%':>5s} {'medHold':>8s} {'tgtHold':>8s} {'net$':>10s}")
    for lbl, _, _ in CONFIGS:
        d = pd.concat(acc[lbl], ignore_index=True)
        n = len(d); win = (d.NetPnL > 0).mean()*100
        tgt = (d.ExitReason == "Target").mean()*100
        eod = (d.ExitReason == "EOD").mean()*100
        medhold = d.held.median()
        tgthold = d.loc[d.ExitReason == "Target", "held"].median()
        log(f"{lbl:30s} {n:5,d} {win:6.1f} {d.NetPnL.mean():7.0f} {d.r.mean():+7.3f} "
            f"{tgt:5.1f} {eod:5.1f} {medhold:8.0f} {tgthold:8.0f} ${d.NetPnL.sum():>9,.0f}")
    log("\nAli (WP): win 83-86%, lifecycle ~7-8 bars to the 1R target")


if __name__ == "__main__":
    main()
