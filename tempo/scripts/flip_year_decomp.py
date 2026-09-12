"""flip_year_decomp.py — why do 2025-26 look so much better? (S119-tempo)

Decomposes the per-year $/trade of the frozen RR2 control into:
  scale  — avg risk per trade in points (box size grows with price/vol level)
  edge   — avg R per trade (risk-normalized quality of the setup)
$/trade ~= avgR x avg_risk_pts x $50 (plus a small covariance term).
Also reports price level, win%, PF-in-R, and $/trade RESCALED to the all-period
average risk (what each year would pay if every year traded today's == average box).

    python tempo/scripts/flip_year_decomp.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tempo" / "outputs" / "flip_bucket_trades_2026-09-12.csv"
OUT = ROOT / "tempo" / "outputs"
PT_USD = 50.0


def main():
    today = dt.date.today().isoformat()
    t = pd.read_csv(SRC)
    rk_all = t["rk"].mean()
    rows = []
    for y, g in t.groupby("year"):
        gp = g.loc[g["R"] > 0, "R"].sum(); gl = -g.loc[g["R"] < 0, "R"].sum()
        rows.append({
            "year": y, "n": len(g),
            "avg_price": round(g["en"].mean(), 0),
            "avg_risk_pts": round(g["rk"].mean(), 2),
            "win%": round(100 * (g["pnl"] > 0).mean(), 1),
            "avgR": round(g["R"].mean(), 4),
            "PF_R": round(gp / gl, 2) if gl > 0 else np.inf,
            "$/trade": round(g["pnl"].mean() * PT_USD, 1),
            "$/tr_fixedrisk": round(g["R"].mean() * rk_all * PT_USD, 1),
        })
    gp = t.loc[t["R"] > 0, "R"].sum(); gl = -t.loc[t["R"] < 0, "R"].sum()
    rows.append({"year": "ALL", "n": len(t), "avg_price": round(t["en"].mean(), 0),
                 "avg_risk_pts": round(rk_all, 2),
                 "win%": round(100 * (t["pnl"] > 0).mean(), 1),
                 "avgR": round(t["R"].mean(), 4),
                 "PF_R": round(gp / gl, 2),
                 "$/trade": round(t["pnl"].mean() * PT_USD, 1),
                 "$/tr_fixedrisk": round(t["R"].mean() * rk_all * PT_USD, 1)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"flip_year_decomp_{today}.csv", index=False)
    print(res.to_string(index=False))

    print("\nkey filters in R (edge only, no scale), train 21-24 vs test 25-26:")
    tr = t[t["year"] <= 2024]; te = t[t["year"] >= 2025]
    t["kind"] = np.where(t["prev_res_day"] == "rev", "SAR", "Basic")
    basic8 = (t["kind"] == "Basic") & (t["hour_ct"] == 8)
    for name, mask in [("Basic hour-8", basic8),
                       ("beyond prior-day H/L", t["beyond_pd"].astype(bool)),
                       ("new session extreme", t["newsess"].astype(bool))]:
        a = t[mask & (t["year"] <= 2024)]; b = t[mask & (t["year"] >= 2025)]
        ra = t[~mask & (t["year"] <= 2024)]; rb = t[~mask & (t["year"] >= 2025)]
        print(f"  {name:<22} flagged avgR {a['R'].mean():+.3f} (n={len(a)}) | "
              f"{b['R'].mean():+.3f} (n={len(b)})   rest {ra['R'].mean():+.3f} | "
              f"{rb['R'].mean():+.3f}")


if __name__ == "__main__":
    main()
