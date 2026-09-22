"""Split the LIVE desk book (trades.parquet) P&L by strategy family.

Answers: how much of the live record came from streams the 4.3yr TD backtest
covered (EM condors, ATM flies) vs streams it did NOT (gamma-wall gx_*, STMR).
Closed trades only (pnl notna). Outputs a dated CSV next to the backtest data.
"""
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")

t = pd.read_parquet(BASE / "data" / "options_log" / "trades.parquet")
t = t[t["pnl"].notna()].copy()
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
t["month"] = t["entry_dt"].dt.to_period("M").astype(str)

FAMILY = {
    "eodic_p": "condor (backtested)", "eodic_c": "condor (backtested)",
    "openic_p": "condor (backtested)", "openic_c": "condor (backtested)",
    "eodfly_p": "fly (backtested)", "eodfly_c": "fly (backtested)",
    "openfly_p": "fly (backtested)", "openfly_c": "fly (backtested)",
    "gx_bps": "gamma-wall (NOT backtested)", "gx_bcs": "gamma-wall (NOT backtested)",
}
t["family"] = t["strategy_id"].map(FAMILY).fillna("other/STMR (NOT backtested)")

def table(df, label):
    g = (df.groupby(["family", "strategy_id"])
           .agg(pnl=("pnl", "sum"), n=("pnl", "size"),
                win_pct=("pnl", lambda s: 100 * (s > 0).mean()))
           .round(1).reset_index().sort_values("pnl"))
    fam = (df.groupby("family")["pnl"].agg(["sum", "size"]).round(0)
             .rename(columns={"sum": "pnl", "size": "n"}))
    print(f"\n===== {label} =====")
    print(fam.to_string())
    print(g.to_string(index=False))
    return g

all_g = table(t, f"ALL closed trades {t['entry_dt'].min():%Y-%m-%d} -> "
                 f"{t['entry_dt'].max():%Y-%m-%d}  total {t['pnl'].sum():.0f}")
aug = t[t["month"] == "2026-08"]
aug_g = table(aug, f"AUGUST 2026 only  total {aug['pnl'].sum():.0f}")

all_g.insert(0, "window", "all")
aug_g.insert(0, "window", "aug2026")
pd.concat([all_g, aug_g]).to_csv(
    OUT / f"live_book_strategy_split_{STAMP}.csv", index=False)
