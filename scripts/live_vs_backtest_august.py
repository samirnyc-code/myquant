"""Side-by-side: every LIVE desk trade Aug-6..Aug-31 2026 vs the TD backtest
row for the same (date, strategy stream).

Live = trades.parquet (closed trades, entry-date basis; dashboard-calendar may
differ slightly — it includes open marks). Backtest = rows.csv (vix252) +
fly_rows.csv, fills at touch, $1.63 fees.
Streams with no backtest counterpart (gx_bps/gx_bcs/STMR/orphans) are listed
in their own section. Output: dated CSV + stdout.
"""
import json
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")
LO, HI = "2026-08-06", "2026-08-31"

# ---- live ----
t = pd.read_parquet(BASE / "data" / "options_log" / "trades.parquet")
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
t = t[(t["entry_dt"] >= LO) & (t["entry_dt"] <= HI + " 23:59")
      & t["pnl"].notna()].copy()
t["date"] = t["entry_dt"].dt.strftime("%Y-%m-%d")

def strikes(legs_json):
    legs = json.loads(legs_json)
    short = [l["strike"] for l in legs if l["side"] == "sell"]
    long_ = [l["strike"] for l in legs if l["side"] == "buy"]
    return (short[0] if short else None), (long_[0] if long_ else None)

t[["short_k", "long_k"]] = t["legs"].apply(lambda s: pd.Series(strikes(s)))
live = t[["date", "strategy_id", "short_k", "long_k", "credit", "pnl",
          "close_reason"]].rename(columns={"strategy_id": "strat"})

# ---- backtest ----
ic = pd.read_csv(BT / "rows.csv", parse_dates=["date"])
ic = ic[ic["method"] == "vix252"].drop(columns=["method", "center", "em"])
fly = pd.read_csv(BT / "fly_rows.csv", parse_dates=["date"]).drop(columns=["center"])
bt = pd.concat([ic, fly], ignore_index=True)
bt["date"] = bt["date"].dt.strftime("%Y-%m-%d")
bt = bt[(bt["date"] >= LO) & (bt["date"] <= HI)]
bt = bt[["date", "strat", "short_k", "long_k", "credit", "exit_kind", "pnl"]]

BT_STREAMS = set(bt["strat"])
matched = live[live["strat"].isin(BT_STREAMS)]
extra = live[~live["strat"].isin(BT_STREAMS)]

side = matched.merge(bt, on=["date", "strat"], how="outer",
                     suffixes=("_live", "_bt")).sort_values(["date", "strat"])
side["d_pnl"] = (side["pnl_live"] - side["pnl_bt"]).round(0)
side["d_strike"] = (side["short_k_live"] - side["short_k_bt"]).abs()

def short_exit(reason):
    if pd.isna(reason):
        return "SKIP"
    if reason.startswith("level ACCEPTED"):
        return "stop"
    if reason.startswith("time stop"):
        return "time"
    return "exp"

side["exit_live"] = side["close_reason"].apply(short_exit)
side["exit_bt"] = side["exit_kind"].map({"stop": "stop", "settle": "exp"}).fillna("SKIP")

pd.set_option("display.width", 250)
print(f"===== MATCHED STREAMS (live vs backtest), {LO}..{HI} =====")
cols = ["date", "strat", "short_k_live", "short_k_bt",
        "credit_live", "credit_bt", "exit_live", "exit_bt",
        "pnl_live", "pnl_bt", "d_pnl"]
print(side[cols].to_string(index=False))

print("\n===== per-stream totals =====")
tot = (side.groupby("strat")[["pnl_live", "pnl_bt"]].sum().round(0))
tot["delta"] = tot["pnl_live"] - tot["pnl_bt"]
print(tot.to_string())
print(f"matched totals: live {side['pnl_live'].sum():.0f}  "
      f"bt {side['pnl_bt'].sum():.0f}")
print(f"strike match: {(side['d_strike'] == 0).sum()}/{side['d_strike'].notna().sum()} identical, "
      f"median |d| {side['d_strike'].median():.1f} pts")

print(f"\n===== LIVE-ONLY streams (no backtest counterpart) =====")
print(extra.sort_values(["date", "strat"]).to_string(index=False))
print(f"live-only total: {extra['pnl'].sum():.0f}  n {len(extra)}")
print(f"\nLIVE grand total {LO}..{HI}: {live['pnl'].sum():.0f}  n {len(live)}")

side.to_csv(BT / f"live_vs_backtest_aug_{STAMP}.csv", index=False)
extra.to_csv(BT / f"live_only_trades_aug_{STAMP}.csv", index=False)
