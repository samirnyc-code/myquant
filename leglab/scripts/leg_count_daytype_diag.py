"""
Diagnostic: WHY do strong bear-trend days show more legs?
Tests two mechanisms per net-move quintile on ES:
  (A) lagging-threshold/vol:  range/ADR higher on down days -> fixed 0.15*ADR
      threshold is small vs the day's actual swings -> more crossings.
  (B) whippiness:  trend efficiency |net|/range LOWER on down days -> more
      back-and-forth per unit of net travel -> more legs.
Reads leg_count_es.py per-day CSV.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "leglab" / "outputs"
RUN = "20260906"
df = pd.read_csv(OUTDIR / f"leg_count_es_5m_{RUN}.csv")

df["range_over_adr"] = df["d_range"] / df["adr"]
df["efficiency"] = df["net"].abs() / df["d_range"]     # 1=clean trend, 0=pure chop
df["net_q"] = pd.qcut(df["net"], 5, labels=["ext_down", "down", "flat", "up", "ext_up"])

g = df.groupby("net_q", observed=True).agg(
    n=("legs_closed", "size"),
    legs=("legs_closed", "mean"),
    range_over_adr=("range_over_adr", "mean"),
    efficiency=("efficiency", "mean"),
    d_range=("d_range", "mean"),
).round(3)

print("ES by net-move quintile:")
print(g.to_string())
print("\n(A) range/ADR  : higher => today's swings big vs lagging 8d threshold => more legs")
print("(B) efficiency : lower  => whippier (more travel per unit net move)  => more legs")

out = OUTDIR / f"leg_count_daytype_diag_{RUN}.csv"
g.to_csv(out)
print(f"\ncsv -> {out}")
