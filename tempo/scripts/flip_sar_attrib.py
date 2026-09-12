"""flip_sar_attrib.py — is SAR a lucky regime artifact or a conditional tool? (S119)

SAR and noSAR produce identical trades EXCEPT on days where an opposite flip signal
fires while a trade is open (SAR reverses; noSAR skips). Decompose the SAR-minus-noSAR
edge per year into:
  freq  — share of days where the two configs diverge (opportunity frequency)
  edge  — avg (SAR pts - noSAR pts) on those divergent days (per-opportunity edge)
If 2025-26 outperformance comes from FREQ: the rule is stable, the tape just offers
more chain days (observable live). If it comes from EDGE flipping sign: the rule
itself only worked recently ('lucky').

Config family: IBS + noEB + RR2 + skipH8basic (the WF's stable pick), SAR on/off.

    python tempo/scripts/flip_sar_attrib.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tempo" / "scripts"))
from flip_walkforward_v2 import prep_days, sim_day  # noqa: E402

ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
PT_USD = 50.0
A = (True, True, "none", 2, True)     # SAR
B = (True, False, "none", 2, True)    # noSAR


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)

    rows = []
    for day in days:
        pa = [x[0] for x in sim_day(day, *A)]
        pb = [x[0] for x in sim_day(day, *B)]
        diverge = (len(pa) != len(pb)) or (not np.allclose(pa, pb))
        rows.append({"date": day["date"], "year": day["year"], "diverge": diverge,
                     "sar_pts": sum(pa), "nosar_pts": sum(pb),
                     "delta": sum(pa) - sum(pb),
                     "n_sar": len(pa), "n_nosar": len(pb)})
    d = pd.DataFrame(rows)
    d.to_csv(OUT / f"flip_sar_attrib_days_{today}.csv", index=False)

    out = []
    for y, g in d.groupby("year"):
        dv = g[g["diverge"]]
        out.append({"year": y, "days": len(g), "diverge_days": len(dv),
                    "freq%": round(100 * len(dv) / len(g), 1),
                    "edge_pts/divday": round(dv["delta"].mean(), 2) if len(dv) else np.nan,
                    "edge_$/divday": round(dv["delta"].mean() * PT_USD, 0) if len(dv) else np.nan,
                    "win_divday%": round(100 * (dv["delta"] > 0).mean(), 1) if len(dv) else np.nan,
                    "tot_delta_pts": round(dv["delta"].sum(), 1)})
    res = pd.DataFrame(out)
    res.to_csv(OUT / f"flip_sar_attrib_{today}.csv", index=False)
    print(res.to_string(index=False))

    tr = d[(d["year"] <= 2024) & d["diverge"]]
    te = d[(d["year"] >= 2025) & d["diverge"]]
    print(f"\n21-24: freq {100 * len(tr) / len(d[d['year'] <= 2024]):.1f}%  "
          f"edge {tr['delta'].mean():+.2f} pts/div-day (n={len(tr)})")
    print(f"25-26: freq {100 * len(te) / len(d[d['year'] >= 2025]):.1f}%  "
          f"edge {te['delta'].mean():+.2f} pts/div-day (n={len(te)})")


if __name__ == "__main__":
    main()
