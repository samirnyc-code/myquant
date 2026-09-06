"""
Does the down-day leg EXCESS survive controlling for volatility?

Mechanism #1 (established) = down days have bigger range/ADR -> smaller relative
threshold -> more legs. This test asks: at the SAME range/ADR, do DOWN days still
show more legs than UP days? A residual = something beyond raw range is adding
legs on selloffs (candidate: negative-gamma whip / short-covering two-sidedness).
No residual = volatility fully explains it (gamma/VWAP would only be upstream
causes of that volatility, not a separate effect).

Bins by range/ADR decile; within each bin compares mean legs_closed for
down (net<0) vs up (net>0) days.
Reads leg_count_es.py per-day CSV.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "leglab" / "outputs"
RUN = "20260906"
df = pd.read_csv(OUTDIR / f"leg_count_es_5m_{RUN}.csv")

df["range_over_adr"] = df["d_range"] / df["adr"]
df["dir"] = df["net"].apply(lambda x: "down" if x < 0 else "up")
df["rr_bin"] = pd.qcut(df["range_over_adr"], 10, labels=False)

# mean legs by (vol bin, direction)
piv = df.pivot_table(index="rr_bin", columns="dir",
                     values="legs_closed", aggfunc="mean").round(2)
cnt = df.pivot_table(index="rr_bin", columns="dir",
                     values="legs_closed", aggfunc="size")
band = df.groupby("rr_bin")["range_over_adr"].agg(["min", "max"]).round(2)
piv["down_minus_up"] = (piv["down"] - piv["up"]).round(2)
piv["rr_lo"] = band["min"]
piv["rr_hi"] = band["max"]
piv["n_down"] = cnt["down"]
piv["n_up"] = cnt["up"]

print("Mean legs_closed by range/ADR decile, DOWN vs UP days:")
print(piv[["rr_lo", "rr_hi", "n_down", "n_up", "down", "up", "down_minus_up"]].to_string())

# volume-weighted average residual (weight each bin by min of the two counts)
w = pd.concat([cnt["down"], cnt["up"]], axis=1).min(axis=1)
resid = (piv["down_minus_up"] * w).sum() / w.sum()
print(f"\nVol-controlled mean (down - up) legs = {resid:+.2f}")
print("~0  => volatility fully explains the asymmetry")
print(">0  => residual excess on down days beyond raw range (positioning/gamma candidate)")

piv.to_csv(OUTDIR / f"leg_count_vol_control_{RUN}.csv")
print(f"\ncsv -> {OUTDIR / f'leg_count_vol_control_{RUN}.csv'}")
