"""Headline metrics for the TD backtest — August-2026 and full 4.3yr.

Per book (IC condor vix252 / fly streams / combined):
total P&L, n, win %, expectancy $/trade, profit factor, max drawdown (daily
close basis), max concurrent collateral (worst single day: sum over that day's
entered verticals of (width - credit) * 100 — SPX defined-risk margin), and a
derived account size = max collateral + 2x |maxDD| (stated heuristic, not a
broker number). August is shown incl. and excl. the 08-25 eodic negative-credit
artifact rows. Output: dated CSV + stdout.
"""
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")

ic = pd.read_csv(BT / "rows.csv", parse_dates=["date"])
ic = ic[ic["method"] == "vix252"].drop(columns=["method"])
fly = pd.read_csv(BT / "fly_rows.csv", parse_dates=["date"])
ic["book"], fly["book"] = "ic", "fly"
allrows = pd.concat([ic, fly], ignore_index=True)
allrows["width"] = (allrows["long_k"] - allrows["short_k"]).abs()
allrows["collateral"] = (allrows["width"] - allrows["credit"].clip(lower=0)) * 100

def metrics(df, label):
    d = df[df["pnl"].notna()]
    daily = d.groupby("date")["pnl"].sum()
    cum = daily.cumsum()
    dd = (cum - cum.cummax()).min()
    gw = d.loc[d["pnl"] > 0, "pnl"].sum()
    gl = d.loc[d["pnl"] < 0, "pnl"].sum()
    coll = d.groupby("date")["collateral"].sum().max()
    acct = coll + 2 * abs(dd)
    return {"slice": label, "total": round(d["pnl"].sum()), "n": len(d),
            "win_pct": round(100 * (d["pnl"] > 0).mean(), 1),
            "exp_per_trade": round(d["pnl"].mean(), 1),
            "pf": round(gw / abs(gl), 2) if gl else float("inf"),
            "max_dd": round(dd), "max_collateral": round(coll),
            "acct_heuristic": round(acct, -2)}

aug = allrows[(allrows["date"] >= "2026-08-01") & (allrows["date"] <= "2026-08-31")]
bad = (aug["book"].eq("ic") & (aug["credit"] < 0) & aug["date"].eq("2026-08-25"))

rows = [
    metrics(aug[aug["book"] == "ic"], "AUG26 ic"),
    metrics(aug[aug["book"] == "ic"] [~bad[aug["book"] == "ic"]], "AUG26 ic ex-artifact"),
    metrics(aug[aug["book"] == "fly"], "AUG26 fly"),
    metrics(aug, "AUG26 combined"),
    metrics(aug[~bad], "AUG26 combined ex-artifact"),
    metrics(allrows[allrows["book"] == "ic"], "4.3yr ic"),
    metrics(allrows[allrows["book"] == "fly"], "4.3yr fly"),
    metrics(allrows, "4.3yr combined"),
]
out = pd.DataFrame(rows)
out.to_csv(BT / f"backtest_metrics_summary_{STAMP}.csv", index=False)
print(out.to_string(index=False))
