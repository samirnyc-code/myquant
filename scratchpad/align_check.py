"""CRITICAL: are the continuous-ES bars price-aligned with MenthorQ levels
across the whole year, or does roll adjustment shift older bars?"""
import pandas as pd
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
b = pd.read_parquet(_ROOT / "data" / "bars" / "_continuous.parquet")
b["DateTime"] = pd.to_datetime(b["DateTime"])
b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
lv0 = pd.read_csv(_ROOT / "data" / "menthorq" / "levels0_history.csv")
lv0 = lv0[lv0.symbol == "ES"]
lv1 = pd.read_csv(_ROOT / "data" / "menthorq" / "levels_history.csv")
lv1 = lv1[lv1.symbol == "ES"]

print(f"{'date':12s} {'bar range':>15s} {'d1 band':>15s} {'mid-gap':>8s} {'CR':>7s}")
for d in ["2025-07-15", "2025-08-15", "2025-10-15", "2025-12-15",
          "2026-01-15", "2026-03-16", "2026-04-15", "2026-06-15"]:
    day = b[b.date == d]
    if not len(day):
        continue
    r0 = lv0[lv0.date == d]
    r1 = lv1[lv1.date == d]
    bar_mid = (day.Low.min() + day.High.max()) / 2
    band = f"{r0.d1_min.values[0]:.0f}-{r0.d1_max.values[0]:.0f}" if len(r0) else "?"
    band_mid = (r0.d1_min.values[0] + r0.d1_max.values[0]) / 2 if len(r0) else None
    gap = f"{bar_mid - band_mid:+.0f}" if band_mid else "?"
    cr = f"{r1.cr.values[0]:.0f}" if len(r1) else "?"
    print(f"{d:12s} {day.Low.min():7.0f}-{day.High.max():7.0f} {band:>15s} {gap:>8s} {cr:>7s}")
