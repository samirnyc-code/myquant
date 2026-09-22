"""Check alignment between killer_context.vix_prior and vix_daily-derived prior close.

Output: data/options_sim/backtest_full/killerday/vix_align_check.csv (mismatch days)
"""
import os
import pandas as pd

ROOT = r"C:\Users\Admin\myquant"
ctx = pd.read_csv(os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv"),
                  parse_dates=["date"])
vix = pd.read_csv(os.path.join(ROOT, "data", "vix_daily.csv"), parse_dates=["date"]).sort_values("date")

feat = vix[["date", "close"]].rename(columns={"close": "v_close"})
m = pd.merge_asof(ctx.sort_values("date"), feat, on="date",
                  direction="backward", allow_exact_matches=False)
m["diff"] = (m["vix_prior"] - m["v_close"]).abs()
bad = m[m["diff"] > 0.05][["date", "dow", "vix_prior", "v_close", "diff"]]
out = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday", "vix_align_check.csv")
bad.to_csv(out, index=False)
print(f"{len(bad)} / {len(m)} days with |diff| > 0.05; wrote {out}")
print(bad.to_string(index=False))
print("last vix_daily date:", vix["date"].max().date())
