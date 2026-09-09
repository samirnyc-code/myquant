"""Validate the v2 desk-faithful engine (august_rerun_v2) against the live book:
strike match rate, credit deltas, skip agreement, per-stream P&L, Aug 6-31.
Live side = trades.parquet. Engine side = deskwait policy + eod streams.
Output: dated CSV + stdout.
"""
import json
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "options_sim" / "backtest_full"
STAMP = dt.date.today().strftime("%Y%m%d")

v2 = pd.read_csv(BT / f"august_rerun_v2_{STAMP}.csv")
v2 = v2[v2["policy"].isin(["eod", "deskwait"])].copy()

t = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
t = t[(t["entry_dt"] >= "2026-08-06") & (t["entry_dt"] <= "2026-08-31 23:59")
      & t["pnl"].notna()].copy()
t["date"] = t["entry_dt"].dt.strftime("%Y-%m-%d")

def strikes(legs_json):
    legs = json.loads(legs_json)
    s = [l["strike"] for l in legs if l["side"] == "sell"]
    return s[0] if s else None

t["short_k"] = t["legs"].apply(strikes)
live = t[t["strategy_id"].isin(v2["strat"].unique())]
live = live[["date", "strategy_id", "short_k", "credit", "pnl"]].rename(
    columns={"strategy_id": "strat", "short_k": "k_live",
             "credit": "cr_live", "pnl": "pnl_live"})

m = v2.merge(live, on=["date", "strat"], how="outer")
m["k_match"] = m["short_k"] == m["k_live"]
m["d_cr"] = (m["credit"] - m["cr_live"]).round(2)

both = m[m["credit"].notna() & m["cr_live"].notna() & (m["exit_kind"] != "SKIP")]
print("===== v2 (desk-faithful) vs LIVE =====")
print(f"strike match: {both['k_match'].sum()}/{len(both)} "
      f"({100 * both['k_match'].mean():.0f}%)")
sk = both[both["k_match"]]
print(f"credit delta (same strike): median |d| "
      f"{sk['d_cr'].abs().median():.2f}  p90 {sk['d_cr'].abs().quantile(.9):.2f}")
print(f"pnl: engine {both['pnl'].sum():.0f}  live {both['pnl_live'].sum():.0f}")

eng_skip = m[m["exit_kind"] == "SKIP"]
live_absent = eng_skip["pnl_live"].isna()
print(f"skip agreement: engine skipped {len(eng_skip)}, live also absent on "
      f"{live_absent.sum()} of them")
extra_live = m[m["credit"].isna() & m["cr_live"].notna()]
print(f"live trades with no engine row: {len(extra_live)}")

print("\nmismatched strikes (remaining):")
mm = both[~both["k_match"]][["date", "strat", "short_k", "k_live", "credit",
                             "cr_live", "pnl", "pnl_live"]]
print(mm.to_string(index=False) if len(mm) else "  none")

print("\nper-stream totals:")
print(both.groupby("strat")[["pnl", "pnl_live"]].sum().round(0).to_string())

m.to_csv(BT / f"august_rerun_v2_vs_live_{STAMP}.csv", index=False)
print(f"\nsaved -> august_rerun_v2_vs_live_{STAMP}.csv")
