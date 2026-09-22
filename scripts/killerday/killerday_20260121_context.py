"""Killer-day forensics: 2026-01-21 (IC -2180 on rebound rally).

Extracts the context window (2026-01-14..2026-01-26) from killer_context.csv
plus VIX OHLC, and writes a dated findings CSV combining local data with
web-verified event facts (Greenland tariff threat Sat 1/18 -> Tue 1/20 -2.1%
selloff -> Wed 1/21 intraday Truth Social walk-back -> +1.2% rip).

Run: python scripts/killerday/killerday_20260121_context.py
Output: data/options_sim/backtest_full/killerday/killerday_20260121_context.csv
        data/options_sim/backtest_full/killerday/killerday_20260121_findings.csv
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/options_sim/backtest_full/killerday"
OUT.mkdir(parents=True, exist_ok=True)

DAY = "2026-01-21"
W0, W1 = "2026-01-14", "2026-01-26"

ctx = pd.read_csv(ROOT / "data/options_sim/backtest_full/killer_context.csv")
win = ctx[(ctx["date"] >= W0) & (ctx["date"] <= W1)].copy()

vix = pd.read_csv(ROOT / "data/vix_daily.csv", header=None,
                  names=["date", "open", "high", "low", "close"])
vwin = vix[(vix["date"] >= W0) & (vix["date"] <= W1)].copy()
win = win.merge(vwin.add_prefix("vix_"), left_on="date", right_on="vix_date",
                how="left").drop(columns=["vix_date"])
win.to_csv(OUT / "killerday_20260121_context.csv", index=False)

# Web-verified event facts (sources in notes column)
findings = pd.DataFrame([
    ("cause", "Trump Truth Social post DURING US hours Wed 1/21: no Feb-1 tariffs on 8 EU nations, "
     "'framework' Greenland/Arctic deal after Davos meeting with NATO SecGen Rutte; SPX +1.2% to 6875.62 "
     "(biggest gain since Nov), all 11 sectors up, ~400 constituents up; VIX 20.09->16.90. IC call side "
     "(credit 1.45) run over.", "nbcnews rcna255270; cnbc 2026/01/20 live; bloomberg 2026-01-21"),
    ("trigger_origin", "Threat announced Sat 1/18 (MLK long weekend): 10% tariff Feb 1 -> 25% Jun 1 on 8 European "
     "nations unless Greenland sold to US; EU emergency meeting; 'Anti-Coercion Instrument' retaliation fear.",
     "newsonair 1/18; baird selloff summary 1/20"),
    ("prior_day", "Tue 1/20: gap -1.08%, close -2.06% (worst since Oct 2025), Dow -870, VIX +4.23 to 20.09; "
     "secondary stress: 40y JGB through 4% (carry-unwind fear); positioning had been max-bullish ('ripe for a check').",
     "baird; finviz 281592"),
    ("overnight", "Asia set to fall Wed as global selloff deepened (Bloomberg wrap), but Trump due at Davos; "
     "he told WEF Wed morning (Davos time = US premarket) he wanted 'immediate negotiations' with Denmark; "
     "US futures recovered to +0.2% gap by 08:30 CT open. VIX opened 19.31, intraday high 20.81 before the crush.",
     "bloomberg asian-stocks-set-to-fall wrap; nbcnews"),
    ("aftermath", "Continuation of relief, no snap-back: Thu 1/22 +0.55% (VIX 15.64), Fri 1/23 ~flat, VIX back to "
     "pre-shock mid-15s within 2 sessions. IC +372 Thu, +142 Fri.", "killer_context rows 925-927"),
    ("signal_0830ct_1", "VIX prior close 20.09 (+4.23 d/d), day-after a -2% headline-driven shock => elevated "
     "snap-back-rally risk; EM 86pts vs ~70 norm.", "local: killer_context, vix_daily"),
    ("signal_0830ct_2", "Call-side EOD-IC credit 1.45 vs 0.0-0.9 on all surrounding days: upside tail priced rich "
     "at entry = market itself flagged rebound risk on the exact side that lost.", "local: killer_context"),
    ("signal_0830ct_3", "Known catalyst live that morning: Trump physically at Davos speaking/meeting Rutte, "
     "tariff deadline headline tape two-sided and binary. Not on the scheduled-macro calendar but foreseeable "
     "headline risk.", "nbcnews; wikipedia Greenland_crisis"),
    ("verdict", "NOT a pure ambush: quiet +0.2% open, yes, and the exact Truth Social timing was unknowable, but "
     "the danger regime (VIX>20 after -2% shock, rich call credit, live binary headline) was fully visible at "
     "08:30 CT. A day-after-shock filter skips this day.", "synthesis"),
], columns=["item", "note", "sources"])
findings.insert(0, "date", DAY)
findings.to_csv(OUT / "killerday_20260121_findings.csv", index=False)

print(win.to_string(index=False))
print(f"\nWrote {OUT}/killerday_20260121_context.csv and _findings.csv")
