"""Root-cause the live-vs-backtest divergence (Aug 6-31): entry-time anchors
and credit deltas.

Backtest anchors (backtest_full_em_2022.ENTRY_ET): eod* @ 09:31:00 ET,
open* @ 10:05:00 ET. This script pulls the LIVE entry timestamps per stream
from trades.parquet and quantifies, per stream:
  - live entry time (median, CT as logged)
  - strike delta distribution vs backtest
  - credit delta distribution (all rows, and same-strike rows only)
so we can see how much of the credit gap is entry-TIME mismatch vs fill model.
Output: dated CSV + stdout.
"""
import json
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")
LO, HI = "2026-08-06", "2026-08-31"

t = pd.read_parquet(BASE / "data" / "options_log" / "trades.parquet")
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
t = t[(t["entry_dt"] >= LO) & (t["entry_dt"] <= HI + " 23:59") & t["pnl"].notna()]
t = t.copy()
t["date"] = t["entry_dt"].dt.strftime("%Y-%m-%d")
t["entry_hm"] = t["entry_dt"].dt.strftime("%H:%M")

print("===== LIVE entry times per stream (CT as logged) =====")
et = (t.groupby("strategy_id")["entry_hm"]
        .agg(["min", lambda s: sorted(s)[len(s) // 2], "max", "size"])
        .rename(columns={"<lambda_0>": "median"}))
print(et.to_string())

side = pd.read_csv(BT / "live_vs_backtest_aug_20260909.csv")
side["d_credit"] = side["credit_live"] - side["credit_bt"]
side["same_strike"] = side["short_k_live"] == side["short_k_bt"]
m = side[side["credit_live"].notna() & side["credit_bt"].notna()]

rows = []
for strat, g in m.groupby("strat"):
    ss = g[g["same_strike"]]
    rows.append({
        "strat": strat, "n": len(g),
        "same_strike_n": len(ss),
        "med_abs_dK": g["d_strike"].median(),
        "max_dK": g["d_strike"].max(),
        "med_dCr_all": round(g["d_credit"].median(), 2),
        "med_absdCr_all": round(g["d_credit"].abs().median(), 2),
        "med_absdCr_sameK": round(ss["d_credit"].abs().median(), 2),
        "max_absdCr_sameK": round(ss["d_credit"].abs().max(), 2),
        "med_absdCr_sameK_pct": round(
            100 * (ss["d_credit"].abs() / ss["credit_live"]).median(), 1),
    })
out = pd.DataFrame(rows)
out.to_csv(BT / f"divergence_dig_{STAMP}.csv", index=False)
print("\n===== credit/strike deltas per stream (matched, both traded) =====")
print(out.to_string(index=False))

print("\nBacktest anchors: eod* 09:31 ET (=08:31 CT), open* 10:05 ET (=09:05 CT)")
print("\n===== open-stream anchor check: live entry time vs strike delta =====")
lt = t[["date", "strategy_id", "entry_hm"]].rename(columns={"strategy_id": "strat"})
oc = (m[m["strat"].isin(["openfly_c", "openfly_p", "openic_c", "openic_p"])]
      .merge(lt, on=["date", "strat"], how="left"))
oc["early"] = oc["entry_hm"] < "08:50"   # CT; bt anchor = 09:05 CT (10:05 ET)
print(oc.groupby("early")[["d_strike"]].agg(["median", "max", "count"]).to_string())
print("\nper-day openfly_c:")
print(oc[oc["strat"] == "openfly_c"]
      [["date", "entry_hm", "short_k_live", "short_k_bt", "d_strike",
        "credit_live", "credit_bt"]].to_string(index=False))

print("\n===== worst same-strike credit misses =====")
worst = (m[m["same_strike"]]
         .assign(absd=lambda x: x["d_credit"].abs())
         .nlargest(12, "absd")
         [["date", "strat", "short_k_live", "credit_live", "credit_bt", "d_credit"]])
print(worst.to_string(index=False))
