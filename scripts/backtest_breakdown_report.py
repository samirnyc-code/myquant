"""Full breakdown of the 4.3yr TD backtest (2022-05-16 -> 2026-09-04).

Slices rows.csv (IC streams, vix252 method = the desk/gexlog EM formula) and
fly_rows.csv (ATM fly streams v3) by year, month, weekday, strategy stream,
and prior-close VIX bucket. Also reports the puts-only + credit-band 0.5-2.5
variant on the same slices.

Outputs (dated) to data/options_sim/backtest_full/breakdown_<slice>_YYYYMMDD.csv
and prints all tables to stdout.
"""
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")

ic = pd.read_csv(BT / "rows.csv", parse_dates=["date"])
ic = ic[ic["method"] == "vix252"].copy()
fly = pd.read_csv(BT / "fly_rows.csv", parse_dates=["date"])
fly["method"] = "fly"

vix = pd.read_csv(BASE / "data" / "vix_daily.csv", parse_dates=["date"])
vix = vix[["date", "close"]].rename(columns={"close": "vix_close"})
# EM uses PRIOR-close VIX -> bucket each trade day by the previous session's close
vix["vix_prior"] = vix["vix_close"].shift(1)

def prep(df):
    df = df.merge(vix[["date", "vix_prior"]], on="date", how="left")
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["weekday"] = df["date"].dt.day_name()
    df["vix_bucket"] = pd.cut(
        df["vix_prior"], [0, 15, 20, 25, 30, 200],
        labels=["<15", "15-20", "20-25", "25-30", "30+"])
    return df

ic, fly = prep(ic), prep(fly)

# The robust variant from the overnight run: put spreads only, credit 0.5-2.5
puts = ic[ic["strat"].isin(["eodic_p", "openic_p"])
          & ic["credit"].between(0.5, 2.5)].copy()

def agg(df, by):
    g = (df.groupby(by, observed=True)
           .agg(pnl=("pnl", "sum"), n=("pnl", "size"),
                win_pct=("pnl", lambda s: 100 * (s > 0).mean()),
                avg=("pnl", "mean"))
           .round(2).reset_index())
    return g

books = {"ic_condor": ic, "fly": fly, "puts_credit_band": puts}
slices = {"year": "year", "month": "month", "weekday": "weekday",
          "strat": "strat", "vix": "vix_bucket"}

for sname, col in slices.items():
    frames = []
    for bname, df in books.items():
        t = agg(df, col)
        t.insert(0, "book", bname)
        frames.append(t)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(BT / f"breakdown_{sname}_{STAMP}.csv", index=False)
    print(f"\n===== {sname.upper()} =====")
    print(out.pivot_table(index=col, columns="book", values="pnl",
                          observed=True).round(0).to_string())

# daily book P&L + best/worst days (IC condor book)
daily = ic.groupby("date")["pnl"].sum()
dd = (daily.cumsum() - daily.cumsum().cummax()).min()
print("\n===== IC CONDOR DAILY =====")
print(f"days {daily.size}  avg/day {daily.mean():.0f}  "
      f"best {daily.max():.0f} ({daily.idxmax():%Y-%m-%d})  "
      f"worst {daily.min():.0f} ({daily.idxmin():%Y-%m-%d})  maxDD {dd:.0f}")
worst = daily.nsmallest(15).round(0)
worst.to_csv(BT / f"breakdown_worst_days_{STAMP}.csv")
print("\n15 worst days:")
print(worst.to_string())

pdaily = puts.groupby("date")["pnl"].sum()
pdd = (pdaily.cumsum() - pdaily.cumsum().cummax()).min()
print("\n===== PUTS+BAND DAILY =====")
print(f"days {pdaily.size}  total {pdaily.sum():.0f}  avg/day {pdaily.mean():.0f}  "
      f"worst {pdaily.min():.0f} ({pdaily.idxmin():%Y-%m-%d})  maxDD {pdd:.0f}")

# monthly totals for the three books side by side
mon = pd.concat([
    ic.groupby("month")["pnl"].sum().rename("ic_condor"),
    fly.groupby("month")["pnl"].sum().rename("fly"),
    puts.groupby("month")["pnl"].sum().rename("puts_band")], axis=1).round(0)
mon.to_csv(BT / f"breakdown_monthly_side_by_side_{STAMP}.csv")
print("\n===== MONTHLY (side by side) =====")
print(mon.to_string())
