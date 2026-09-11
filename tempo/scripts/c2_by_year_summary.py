"""c2_by_year_summary.py — by-year stability of the C2 (efficiency-collapse) cell
from climax_conditioning_events (S116-tempo). Reads the dated events CSV.

    python tempo/scripts/c2_by_year_summary.py [--date 2026-09-11]
"""
from __future__ import annotations
import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tempo" / "outputs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    ev = pd.read_csv(OUT / f"climax_conditioning_events_{a.date}.csv")
    r = ev[ev["label"].isin(["reversal", "continuation"]) & ev["eff_fall"].notna()].copy()
    r["year"] = r["date"].str[:4]
    rows = []
    for (yr, grp), g in r.groupby(["year", "grp"]):
        fall = g[g["eff_fall"] == True]      # noqa: E712
        hold = g[g["eff_fall"] == False]     # noqa: E712
        rows.append({"year": yr, "grp": grp,
                     "n_fall": len(fall), "P_rev_fall": round((fall["label"] == "reversal").mean(), 3),
                     "n_hold": len(hold), "P_rev_hold": round((hold["label"] == "reversal").mean(), 3),
                     "edge": round((fall["label"] == "reversal").mean()
                                   - (hold["label"] == "reversal").mean(), 3)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"c2_by_year_{a.date}.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
