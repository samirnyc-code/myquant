"""Every August-2026 trade from the 4.3yr TD backtest, full detail.

Source = backtest_full/rows.csv (IC streams, vix252 = the desk EM formula) and
fly_rows.csv (ATM-vertical 'fly' streams). These rows were built from ThetaData
quotes + the mechanical strike rules ONLY — independent of the live desk's
trade log, which this script does NOT read.

Columns: date, strat, center (spot ref), em, short_k, long_k, credit (fill at
touch), exit_kind (stop/settle), exit_val (stop debit or settle intrinsic),
pnl ($, 1-lot, $1.63/contract/exec fees), note.
Output: dated CSV + stdout tables + per-stream totals.
"""
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")

ic = pd.read_csv(BT / "rows.csv", parse_dates=["date"])
ic = ic[(ic["method"] == "vix252")
        & (ic["date"] >= "2026-08-01") & (ic["date"] <= "2026-08-31")].copy()
ic = ic.drop(columns=["method"])

fly = pd.read_csv(BT / "fly_rows.csv", parse_dates=["date"])
fly = fly[(fly["date"] >= "2026-08-01") & (fly["date"] <= "2026-08-31")].copy()
fly.insert(4, "em", "")          # fly strikes are ATM, no EM column in source

both = pd.concat([ic, fly], ignore_index=True).sort_values(["date", "strat"])
both["date"] = both["date"].dt.strftime("%Y-%m-%d")
out = BT / f"august2026_backtest_trades_{STAMP}.csv"
both.to_csv(out, index=False)

pd.set_option("display.width", 200)
for name, df in (("IC CONDOR (vix252)", ic), ("FLY STREAMS", fly)):
    print(f"\n===== {name} — {len(df)} trades =====")
    print(df.sort_values(["date", "strat"]).to_string(index=False))
    tot = (df.groupby("strat")
             .agg(pnl=("pnl", "sum"), n=("pnl", "size"),
                  stops=("exit_kind", lambda s: (s == "stop").sum()),
                  win=("pnl", lambda s: (s > 0).sum()))
             .round(2))
    print(tot.to_string())
    print(f"TOTAL {df['pnl'].sum():.2f}  over {df['date'].nunique()} days")

print(f"\nsaved -> {out}")
