"""mfe_by_balance.py — MFE/MAE excursion profile: balance vs non-balance.

Answers two trade-management questions (ER>=0.30, single-leg, pinned 1.0R):
  • Target: do balance trades reach higher MFE (room for a bigger target)?
  • BE ratchet: are balance trades LESS prone to give it back after reaching +X R?
    i.e. P(eventual loss | MFE already reached +X R). If balance trades rarely
    reverse after +0.5R, a BE stop costs them winners; if non-balance trades give
    it back often, BE helps them.
"""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

_ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(_ROOT))
import massive, regime_filter as rf                                  # noqa: E402
from simulation_engine import simulate_trades                       # noqa: E402
from scripts.regime_overlay_phaseB import (BASE, CHOP_MIN, tag_states,  # noqa: E402
                                           _SIGNALS, _BARS, _SESS)


def main():
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig[er >= CHOP_MIN].reset_index(drop=True).copy()
    st = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, st], axis=1)
    sigf["bal"] = (sigf["open_loc"] == "inside") & (sigf["disc"] == "rotation")
    tk = {d: massive.load_continuous_ticks(d) for d in sorted(sigf["Date"].unique())}
    tk = {d: t for d, t in tk.items() if not t.empty}
    res = simulate_trades(signals=sigf, ticks_by_date=tk, bars_by_date=bbd, **BASE)
    f = res[res["Filled"] == True].copy()
    f["bal"] = sigf.loc[f.index, "bal"].values
    f["win"] = f["NetPnL"] > 0

    print(f"filled {len(f)}  | balance {int(f['bal'].sum())}\n")
    for lab, m in [("balance", f["bal"]), ("non-balance", ~f["bal"])]:
        g = f[m]; mfe = g["MFE_R"].clip(lower=0); mae = g["MAE_R"].clip(lower=0)
        print(f"== {lab} (n={len(g)}) ==")
        print(f"  MFE_R mean {mfe.mean():.2f}  median {mfe.median():.2f}  "
              f"p75 {mfe.quantile(.75):.2f}  p90 {mfe.quantile(.90):.2f}")
        print(f"  MAE_R mean {mae.mean():.2f}  median {mae.median():.2f}")
        print(f"  win% {g['win'].mean()*100:.0f}   exp ${g['NetPnL'].mean():.0f}")
        for thr in [0.25, 0.50, 0.75, 1.00]:
            reached = g[mfe >= thr]
            if len(reached):
                gaveback = (reached["NetPnL"] < 0).mean() * 100
                print(f"  reached +{thr:.2f}R: {len(reached):4d} ({len(reached)/len(g)*100:4.0f}%)"
                      f"   then LOST: {gaveback:4.0f}%")
        print()


if __name__ == "__main__":
    main()
