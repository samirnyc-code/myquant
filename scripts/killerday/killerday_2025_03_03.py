"""Killer-day forensics: 2025-03-03 (Mon) — tariff-confirmation afternoon selloff.

Extracts the context window (2025-02-26 .. 2025-03-06) from killer_context.csv
and the 2025-03-03 trade rows from rows.csv / fly_rows.csv, and writes a dated
findings CSV combining backtest facts with the verified news timeline.

Run:  python scripts/killerday/killerday_2025_03_03.py
Outputs (dated):
  data/options_sim/backtest_full/killerday/killerday_2025-03-03_context.csv
  data/options_sim/backtest_full/killerday/killerday_2025-03-03_trades.csv
  data/options_sim/backtest_full/killerday/killerday_2025-03-03_findings.csv

News timeline (verified via web, 2026-09-09):
  - Sun 3/2 evening: Trump announces "Crypto Strategic Reserve" (BTC/ETH/XRP/SOL/ADA);
    crypto spikes; US equity futures rise slightly Sunday night (CNBC).
  - Mon 3/3 premarket: quiet/slightly positive; SPX cash gap +0.23%. Europe rallied
    (defense/rearmament theme post-2/28 Zelensky Oval Office clash).
  - 09:00 CT: ISM Manufacturing 50.3 (est 50.6), prices paid 62.4 (+7.5, highest
    since mid-2022), new orders/employment contracting -> stagflation flavor; market
    starts leaking. Atlanta Fed GDPNow cut to -2.8% same day.
  - ~13:00-13:30 CT: Trump (White House, TSMC $100B event + presser) confirms 25%
    tariffs on Canada+Mexico effective NEXT DAY: "no room left" for a deal. SPX
    sells off hard into the close, accelerating in the last hour.
  - Close: SPX 5849.72, -1.76% (worst day of 2025 to date); NDX -2.64%; NVDA -8.7%;
    VIX 22.78 (+3.15, highest since December); BTC -8% (full round-trip of Sunday pop).
  - Aftermath: 3/4 tariffs take effect, SPX -1.22%, VIX 23.51; 3/5 +1.12% relief
    (one-month automaker exemption); 3/6 -1.78%; correction continued to -10% by 3/13.
Sources:
  cnbc.com/2025/03/02/stock-futures-rise-slightly-in-overnight-trading-...
  finance.yahoo.com/news/live/stock-market-today-dow-sinks-sp-500-posts-worst-day-of-2025...
  fintwit.substack.com/p/march-3-2025
  forbes.com .../2025/03/05/trump-exempts-carmakers-from-canada-and-mexico-tariffs...
  en.wikipedia.org/wiki/2025_stock_market_crash
"""
import os
import pandas as pd

ROOT = r"c:\Users\Admin\myquant"
BT = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUT = os.path.join(BT, "killerday")
os.makedirs(OUT, exist_ok=True)

DAY = "2025-03-03"
W0, W1 = "2025-02-26", "2025-03-06"

ctx = pd.read_csv(os.path.join(BT, "killer_context.csv"))
win = ctx[(ctx["date"] >= W0) & (ctx["date"] <= W1)]
win.to_csv(os.path.join(OUT, f"killerday_{DAY}_context.csv"), index=False)

rows = pd.read_csv(os.path.join(BT, "rows.csv"))
tr = rows[(rows["date"] == DAY) & (rows["method"] == "vix252")]
fly = pd.read_csv(os.path.join(BT, "fly_rows.csv"))
ftr = fly[fly["date"] == DAY].copy()
ftr["method"] = "fly"
trades = pd.concat([tr, ftr], ignore_index=True)
trades.to_csv(os.path.join(OUT, f"killerday_{DAY}_trades.csv"), index=False)

findings = pd.DataFrame(
    [
        ("cause", "Trump confirmed ~13:00-13:30 CT that 25% Canada+Mexico tariffs start 3/4: 'no room left'. Last-hour selloff; SPX -1.76% to 5849.72, worst day of 2025 to date; NVDA -8.7%; VIX 22.78."),
        ("secondary", "09:00 CT ISM mfg 50.3 miss w/ prices-paid 62.4 spike (stagflation); Atlanta Fed GDPNow cut to -2.8% same day."),
        ("overnight", "Quiet/positive: Sunday crypto-reserve pop, futures slightly up, Europe rallying (defense). Cash gap +0.23%."),
        ("prior_days", "Tension visible: 2/27 SPX -1.59% after Trump reaffirmed 3/4 tariff date; 2/28 Zelensky Oval Office blowup yet +1.59% month-end rally. Whipsaw +-1.6% days, realized >> implied."),
        ("aftermath", "Continuation: 3/4 -1.22% (tariffs live, VIX 23.51), 3/5 +1.12% (auto exemption), 3/6 -1.78%; -10% correction by 3/13."),
        ("trade_detail", "Killed on the put side only: eodic_p 5880/5855 cr 1.05 stopped @16.4 (-1542); close 5849.72 breached short put. All call sides settled worthless."),
        ("observable_0830ct", "KNOWN: 3/4 tariff deadline next day (public since 2/27); ISM on calendar 09:00 CT; realized vol (2.3 rng, back-to-back +-1.6% days) >> EM 73.6 (1.24%); VIX 19.63 near YTD highs. NOT known: exact Trump presser. Verdict: intraday ambush on a quiet open, but the event calendar (tariff D-day eve + ISM) and realized>implied vol were premarket red flags."),
    ],
    columns=["item", "note"],
)
findings.to_csv(os.path.join(OUT, f"killerday_{DAY}_findings.csv"), index=False)
print(win.to_string(index=False))
print(trades.to_string(index=False))
print("wrote 3 CSVs to", OUT)
