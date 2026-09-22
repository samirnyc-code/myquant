"""flip_wf2_sar_trace.py — why did the walk-forward add SAR only in 2026? (S119)

Traces the two head-to-head configs the WF was choosing between in its stable family
(IBS + noEB + RR2 + skipH8basic, with vs without SAR): per-year results and the
CUMULATIVE train totals/PF the selector saw at each year boundary.

    python tempo/scripts/flip_wf2_sar_trace.py
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

CFGS = {"IBS+SAR+noEB+RR2+skipH8b": (True, True, "none", 2, True),
        "IBS+noSAR+noEB+RR2+skipH8b": (True, False, "none", 2, True)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    years = sorted({d["year"] for d in days})

    per = {}
    for name, cfg in CFGS.items():
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += [x[0] for x in sim_day(day, *cfg)]
        per[name] = yp

    rows = []
    for y in years:
        rec = {"year": y}
        for name in CFGS:
            p = np.array(per[name][y])
            gp = p[p > 0].sum(); gl = -p[p < 0].sum()
            tag = "SAR" if "+SAR" in name else "noSAR"
            rec[f"{tag}_n"] = len(p)
            rec[f"{tag}_pts"] = round(p.sum(), 1)
            rec[f"{tag}_PF"] = round(gp / gl, 3) if gl > 0 else np.inf
        rows.append(rec)
    peryear = pd.DataFrame(rows)
    print("=== per-year, head to head ===")
    print(peryear.to_string(index=False))

    rows2 = []
    for Y in [y for y in years if y >= 2023]:
        rec = {"selecting_for": Y, "train": f"21..{Y-1}"}
        for name in CFGS:
            p = np.concatenate([per[name][y] for y in years if y < Y])
            gp = p[p > 0].sum(); gl = -p[p < 0].sum()
            tag = "SAR" if "+SAR" in name else "noSAR"
            rec[f"{tag}_cum_pts"] = round(p.sum(), 1)
            rec[f"{tag}_cum_PF"] = round(gp / gl, 3)
        rec["PF_gap"] = round(rec["SAR_cum_PF"] - rec["noSAR_cum_PF"], 3)
        rows2.append(rec)
    cum = pd.DataFrame(rows2)
    print("\n=== what the selector saw at each boundary (cumulative train) ===")
    print(cum.to_string(index=False))

    peryear.to_csv(OUT / f"flip_wf2_sar_trace_yearly_{today}.csv", index=False)
    cum.to_csv(OUT / f"flip_wf2_sar_trace_cum_{today}.csv", index=False)


if __name__ == "__main__":
    main()
