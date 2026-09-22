"""Killer-day forensics: 2025-10-22 (Wed).

Backtest day P&L (rows.csv vix252 / killer_context.csv): IC -1695, fly +1890,
puts-band -1683. Extracts the context window + all trade rows for the day and
persists the web-researched findings/signals table.

Cause (verified via CNBC / Reuters / Yahoo Finance, 2026-09-10):
  - Overnight (Oct 21 after close): Netflix earnings miss (Brazil tax dispute,
    stock -10%) and Texas Instruments weak Q4 guidance (-5.6%, dragged semis).
  - Open was quiet: gap +0.09%, VIX 17.87 (falling), EM only 75.8 pts.
  - ~midday/early-afternoon ET: Reuters EXCLUSIVE - Trump admin considering
    broad curbs on exports to China of anything made with/containing US
    software (retaliation for Beijing rare-earth controls, follow-through on
    the Oct 10 "critical software" threat). White House confirmed it was
    weighing the plan. Tech-led flush: SPX -1.2% / NDX -1.9% / Dow -400 at lows.
  - SPX prior close 6735.35 -> intraday low ~6655 -> close 6699.40 (-0.53%).
    The -1.2% flush blew through the put shorts (6660/6665, EM was only ~1.1%);
    bounce into the close let the ATM fly win (+1890).
  - Prior days: melt-up recovery from the Oct 10 tariff scare; Mon Oct 20
    +1.07% (Dow record), Tue Oct 21 flat 0.00% with 0.45% range; VIX bled
    20.78 -> 18.23 -> 17.87. BUT Oct 21 had a cross-asset shock: gold -6%
    (worst day in 12+ years), silver -9%. Ongoing gov't shutdown = data
    blackout; delayed CPI scheduled Fri Oct 24; Trump-Xi meeting anticipated.
  - After: snap-back. Thu Oct 23 +0.58%; Fri Oct 24 cooler delayed CPI ->
    rally to record highs. One-day ambush, no continuation.

Verdict: genuine intraday ambush on a quiet open. Not detectable by 08:30 CT
as a market-level warning; the one mechanical tell in our own pricing was the
BROKEN call-side credit (eodic_c vix252 = -0.05, openic_c = 0.00) with all
premium stuffed in the puts (0.75) - heavy put skew on a small EM, and the put
side is exactly what died.
"""
import os
import pandas as pd

BASE = r"C:\Users\Admin\myquant"
FULL = os.path.join(BASE, "data", "options_sim", "backtest_full")
OUT = os.path.join(FULL, "killerday")
DAY = "2025-10-22"

os.makedirs(OUT, exist_ok=True)

# 1) context window
ctx = pd.read_csv(os.path.join(FULL, "killer_context.csv"))
win = ctx[(ctx["date"] >= "2025-10-16") & (ctx["date"] <= "2025-10-27")]
win.to_csv(os.path.join(OUT, f"killerday_{DAY}_context.csv"), index=False)

# 2) trade rows for the day (all IC streams + fly)
rows = pd.read_csv(os.path.join(FULL, "rows.csv"))
day_rows = rows[rows["date"] == DAY]
day_rows.to_csv(os.path.join(OUT, f"killerday_{DAY}_ic_rows.csv"), index=False)

fly_path = os.path.join(FULL, "fly_rows.csv")
if os.path.exists(fly_path):
    fly = pd.read_csv(fly_path)
    fly[fly["date"] == DAY].to_csv(
        os.path.join(OUT, f"killerday_{DAY}_fly_rows.csv"), index=False)

# 3) findings / signals table
findings = pd.DataFrame([
    ("cause", "intraday-only",
     "Reuters exclusive ~midday ET: US considering broad software-linked "
     "export curbs on China (laptops-to-jet-engines); White House confirmed "
     "weighing it. Tech flush to SPX -1.2% lows, close -0.53%."),
    ("earnings_drag", "premarket",
     "Netflix -10% (miss, Brazil tax dispute) and TXN -5.6% (weak Q4 guide) "
     "both reported Oct 21 after close; known before open but read as "
     "single-name/semis drag, index gap only +0.09%."),
    ("gap_pct=+0.09", "premarket", "Quiet open; no index-level warning."),
    ("vix_17.87_falling", "premarket",
     "VIX 17.87, -0.36 d/d, third straight decline; complacent, no warning."),
    ("em_75.8pts_~1.1%", "at-entry",
     "Small expected move; day's -1.2% flush exceeded it. Small EM = thin "
     "cushion, but that is a regime fact, not a day-specific alarm."),
    ("call_credit_broken_-0.05", "at-entry",
     "eodic_c vix252 credit -0.05 (openic_c 0.00): call side unquotable/"
     "broken while puts paid 0.75. Extreme put skew on tiny EM. Entry gate "
     "'credit<=0 broken' fired on the call side. Strongest mechanical tell; "
     "advisory-only per desk rule."),
    ("china_theme_live", "premarket",
     "Trump Oct 10 threat of 'critical software' export controls (Nov 1) "
     "was public; Oct 22 Reuters story was an escalation of a known theme, "
     "but its timing/content was not knowable premarket."),
    ("gold_silver_crash_oct21", "premarket",
     "Oct 21: gold -6% (worst in 12+ yrs), silver -9%. Cross-asset "
     "deleveraging shock the day before, while equities sat flat."),
    ("shutdown_data_blackout", "premarket",
     "Gov't shutdown since Oct 1; macro data delayed (CPI moved to Oct 24). "
     "No scheduled US release on Oct 22 - event calendar was CLEAN."),
    ("aftermath_snapback", "n/a",
     "Oct 23 +0.58%; Oct 24 cooler delayed CPI -> record highs. No "
     "continuation; one-day headline ambush."),
], columns=["signal", "knowable_at", "note"])
findings.insert(0, "date", DAY)
findings.to_csv(os.path.join(OUT, f"killerday_{DAY}_findings.csv"), index=False)

print(win.to_string(index=False))
print(day_rows.to_string(index=False))
print(f"wrote 3-4 CSVs to {OUT}")
