"""QS Breakouts — stop × target robustness surface (FT-only, frictionless).

NOT an optimizer — a ROBUSTNESS MAP (tests Ali's footnote-[1] claim that a robust
system shouldn't break when you change a variable). We report the whole surface;
we do NOT pick the peak cell to trade.

Grid:
  stop_mult  in {1.0,1.5,2.0,2.5,3.0}  (x combined range, 2-bar iStop)
  target_r   in {0.25,0.5,0.75,1.0,1.5,2.0}  (x R, R = stop distance)
Ali = (stop 2.0, target 0.5). Your "wide" version = (2.0, 1.0).

Efficient: detect once per stop_mult, load ticks once per chunk, score every
(stop x target) cell on the loaded ticks. Output: expR / net$ / win% / maxDD$ /
MAR matrices to docs/living/qs_periods/.

Run: python scripts/qs_stop_target_sweep.py
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
            entry_slip=0, exit_slip=0)
STOP_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
N_CHUNKS = 6


def log(m): print(f"[sweep] {m}", flush=True)


def main():
    _OUT.mkdir(parents=True, exist_ok=True)
    bars = pd.read_parquet(_BARS)
    bbd = {d: g.reset_index(drop=True) for d, g in
           bars.drop(columns=["Contract"], errors="ignore").groupby(bars["DateTime"].dt.date)}

    sigs = {}
    for sm in STOP_MULTS:
        s = detect(bars, QSConfig.paper(twobar_stop_mult=sm))
        s = s[(s["SignalType"] == "BO+FT") & (s["FilterStatus"] == "ok")].reset_index(drop=True)
        s["_date"] = pd.to_datetime(s["DateTime"]).dt.date
        sigs[sm] = s
    dates = np.array(sorted(sigs[STOP_MULTS[0]]["_date"].unique()), object)
    log(f"detected; ~{len(sigs[STOP_MULTS[0]]):,} FT-only/stop. running grid "
        f"{len(STOP_MULTS)}x{len(TARGET_RS)}...")

    acc = {(sm, tr): {"pnl": [], "r": []} for sm in STOP_MULTS for tr in TARGET_RS}
    for ci, chunk in enumerate(np.array_split(dates, N_CHUNKS)):
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        cs = set(chunk.tolist())
        for sm in STOP_MULTS:
            sub = sigs[sm][sigs[sm]["_date"].isin(cs)].reset_index(drop=True)
            for tr in TARGET_RS:
                res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                      target_r=tr, **BASE).reset_index(drop=True)
                rf = res[res["Filled"] == True]
                pnl = rf["NetPnL"].values
                r = pnl / rf["RiskDollar"].replace(0, np.nan).values
                acc[(sm, tr)]["pnl"].append(pnl); acc[(sm, tr)]["r"].append(r)
        del tbd; gc.collect()
        log(f"chunk {ci+1}/{N_CHUNKS}")

    def cell(sm, tr, what):
        pnl = np.concatenate(acc[(sm, tr)]["pnl"]); r = np.concatenate(acc[(sm, tr)]["r"])
        if len(pnl) == 0:
            return np.nan
        if what == "expR": return round(float(np.nanmean(r)), 3)
        if what == "net":  return round(float(pnl.sum()), 0)
        if what == "win":  return round(float((pnl > 0).mean() * 100), 1)
        if what == "maxDD":
            cum = np.cumsum(pnl); return round(float((cum - np.maximum.accumulate(cum)).min()), 0)
        if what == "MAR":
            cum = np.cumsum(pnl); dd = (cum - np.maximum.accumulate(cum)).min()
            return round(float(pnl.sum() / abs(dd)), 2) if dd < 0 else np.inf
        if what == "n": return len(pnl)

    for what in ["expR", "net", "win", "maxDD", "MAR"]:
        df = pd.DataFrame({tr: [cell(sm, tr, what) for sm in STOP_MULTS] for tr in TARGET_RS},
                          index=[f"stop{sm}x" for sm in STOP_MULTS])
        df.columns = [f"tgt{tr}R" for tr in TARGET_RS]
        df.to_csv(_OUT / f"stoptgt_{what}.csv")
        log(f"\n===== {what} (rows=stop× combined, cols=target×R) =====")
        log(df.to_string())
    log("\nAli=(stop2.0x,tgt0.5R)  Wide=(stop2.0x,tgt1.0R). Look for a PLATEAU, not a peak.")
    log(f"[saved matrices -> {_OUT}/stoptgt_*.csv]")


if __name__ == "__main__":
    main()
