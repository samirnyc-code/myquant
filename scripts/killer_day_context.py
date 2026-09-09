"""Per-day feature table for the killer-day mitigation study (S115 overnight).

One row per backtest day (2022-05-16 -> 2026-09-04) with everything a filter
could have known BY 08:30 CT that morning, plus the day's realized P&L:

  gap_pct        open vs prior close (overnight gap)
  prior_ret      prior day close-to-close return
  prior_range    prior day (high-low)/close
  prior2_ret     two days back return (pre-cursor window)
  vix_prior      prior VIX close (the EM input)
  vix_chg        prior VIX close minus the close before it
  em_pts         the day's EM in points (vix252)
  cr_eodic_c/p   the morning's condor credits (richness = danger per S114)
  event          FOMC/CPI/NFP from data/econ_calendar_2022_2026.csv
  ic_pnl fly_pnl puts_band_pnl   realized day P&L per book
  next_ret       NEXT day close-to-close (aftermath, for day-after rules)

Output: backtest_full/killer_context.csv + worst-day shortlists to stdout.
"""
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "options_sim" / "backtest_full"

spx = pd.read_csv(BT / "spx_daily_ohlc.csv").set_index("date")
vix = pd.read_csv(ROOT / "data" / "vix_daily.csv").set_index("date")["close"]
events = pd.read_csv(ROOT / "data" / "econ_calendar_2022_2026.csv")
ev = events.groupby("date")["event"].apply("+".join)

ic = pd.read_csv(BT / "rows.csv")
ic = ic[ic["method"] == "vix252"]
fly = pd.read_csv(BT / "fly_rows.csv")
puts = ic[ic["strat"].isin(["eodic_p", "openic_p"]) & ic["credit"].between(0.5, 2.5)]

ic_d = ic.groupby("date")["pnl"].sum().rename("ic_pnl")
fly_d = fly.groupby("date")["pnl"].sum().rename("fly_pnl")
pb_d = puts.groupby("date")["pnl"].sum().rename("puts_band_pnl")
cr_c = ic[ic["strat"] == "eodic_c"].set_index("date")["credit"].rename("cr_eodic_c")
cr_p = ic[ic["strat"] == "eodic_p"].set_index("date")["credit"].rename("cr_eodic_p")
em = ic[ic["strat"] == "eodic_p"].set_index("date")["em"].rename("em_pts")

rows = []
dates = sorted(ic_d.index)
sidx = list(spx.index)
for d in dates:
    if d not in spx.index:
        continue
    i = sidx.index(d)
    if i < 2:
        continue
    p1, p2 = sidx[i - 1], sidx[i - 2]
    nxt = sidx[i + 1] if i + 1 < len(sidx) else None
    r = dict(
        date=d,
        dow=dt.datetime.strptime(d, "%Y-%m-%d").strftime("%a"),
        event=ev.get(d, ""),
        gap_pct=round(100 * (spx.loc[d, "open"] / spx.loc[p1, "close"] - 1), 2),
        prior_ret=round(100 * (spx.loc[p1, "close"] / spx.loc[p2, "close"] - 1), 2),
        prior_range=round(100 * (spx.loc[p1, "high"] - spx.loc[p1, "low"])
                          / spx.loc[p1, "close"], 2),
        prior2_ret=round(100 * (spx.loc[p2, "close"]
                                / spx.loc[sidx[i - 3], "close"] - 1), 2) if i >= 3 else None,
        vix_prior=round(vix.get(p1, float("nan")), 2),
        vix_chg=round(vix.get(p1, float("nan")) - vix.get(p2, float("nan")), 2),
        em_pts=em.get(d),
        cr_eodic_c=cr_c.get(d), cr_eodic_p=cr_p.get(d),
        ic_pnl=round(ic_d.get(d, 0), 0), fly_pnl=round(fly_d.get(d, 0), 0),
        puts_band_pnl=round(pb_d.get(d, 0), 0),
        next_ret=round(100 * (spx.loc[nxt, "close"] / spx.loc[d, "close"] - 1), 2)
        if nxt and nxt in spx.index else None,
    )
    rows.append(r)

df = pd.DataFrame(rows)
out = BT / "killer_context.csv"
df.to_csv(out, index=False)
print(f"saved {len(df)} days -> {out}")

for col, n in (("ic_pnl", 16), ("fly_pnl", 10), ("puts_band_pnl", 10)):
    print(f"\nworst {n} days by {col}:")
    print(df.nsmallest(n, col)[["date", "dow", "event", "gap_pct", "prior_ret",
                                "vix_prior", "vix_chg", "cr_eodic_c", "cr_eodic_p",
                                col]].to_string(index=False))
