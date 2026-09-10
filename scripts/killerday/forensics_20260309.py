"""Killer-day forensics: 2026-03-09 (Mon) — Iran-war oil-spike whipsaw / Trump headline reversal.

Extracts the local backtest evidence (context row, IC rows, fly rows for 2026-03-05..03-11)
and writes the dated evidence CSV + a findings/signals CSV under
data/options_sim/backtest_full/killerday/.

Web findings (researched 2026-09-10, sources listed in findings CSV):
- Backdrop: US/Israel began bombing Iran the weekend of Feb 28-Mar 1, 2026; Iran shut the
  Strait of Hormuz. Oil rose ~35% the week of Mar 2-6 (WTI > $90, Brent ~$92 Friday).
- Fri 2026-03-06: NFP printed -92k (vs -50k exp), unemployment 4.4%; SPX -1.3% to 6740,
  worst week since mid-October; VIX +24% (+5.74) to 29.49.
- Mon 2026-03-09: oil spiked above $119 intraday (from ~$90-92) on escalation; SPX gapped
  down -0.6% (open ~6700) and extended losses in the morning. Midday, Trump comments to
  CBS News (posted on X) signaled the war could end "very soon"; oil collapsed back below
  $90; SPX reversed as much as +1% and closed +0.83% at 6795.99 (Nasdaq +1.38%).
  Formal Doral press conference (waive oil sanctions, Navy escorts through Hormuz) came
  7:44 PM ET, after the close. Day range 2.57%.
- After: Tue -0.21% but realized range stayed huge (fly -1426 Tue); Wed CPI ~flat;
  Thu -1.52%. War/headline whipsaw regime persisted for weeks (South Pars attacked Mar 18;
  more Trump strike-delay headlines Mar 23-24). No clean resolution; chop, not snap-back.
"""
import csv
import os

ROOT = r"C:\Users\Admin\myquant"
BF = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUT = os.path.join(BF, "killerday")
os.makedirs(OUT, exist_ok=True)

DATES = {"2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10", "2026-03-11"}
DAY = "2026-03-09"


def extract(src, dates, dst):
    with open(src, newline="") as f:
        rows = list(csv.reader(f))
    keep = [rows[0]] + [r for r in rows[1:] if r and r[0] in dates]
    with open(dst, "w", newline="") as f:
        csv.writer(f).writerows(keep)
    return len(keep) - 1


n_ctx = extract(os.path.join(BF, "killer_context.csv"), DATES,
                os.path.join(OUT, f"{DAY}_context_window.csv"))
n_ic = extract(os.path.join(BF, "rows.csv"), {DAY},
               os.path.join(OUT, f"{DAY}_ic_rows.csv"))
n_fly = extract(os.path.join(BF, "fly_rows.csv"), {DAY},
                os.path.join(OUT, f"{DAY}_fly_rows.csv"))

SIGNALS = [
    # signal, knowable_at, note
    ("VIX 29.49 prior close, +5.74 (+24%) on Friday", "premarket",
     "Highest of the episode to that point; pure regime alarm"),
    ("Oil shock: WTI +35% on the week, spiking toward $119 overnight/Mon AM", "premarket",
     "Hormuz closed; supply-shock tape visible in globex crude before 08:30 CT"),
    ("Active shooting war + prior headline-driven reversals (Mar 4 bounce on CIA-contact report)",
     "premarket", "Two-sided headline whipsaw risk was already demonstrated that week"),
    ("Gap -0.6% after Friday -1.33%", "at-entry", "Accelerating downtrend into the open"),
    ("Expected move 125.2 pts (~1.86%) via vix252", "at-entry",
     "Roughly 2x a normal day; options market priced the chaos"),
    ("EOD-IC call credit 0.05 (engine 'thin' gate <0.10)", "at-entry",
     "Zero call premium = no compensation for upside risk; fly call wing sold 5.2 died at 22.8"),
    ("No scheduled US macro Monday (CPI Wed)", "premarket",
     "Calendar was clean; risk was entirely headline-driven"),
    ("Trump CBS de-escalation comment -> oil < $90, SPX V-reversal to +0.83%", "intraday-only",
     "The actual killer for ATM flies; unschedulable, midday"),
]

with open(os.path.join(OUT, f"{DAY}_findings.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["signal", "knowable_at", "note"])
    w.writerows(SIGNALS)
    w.writerow([])
    w.writerow(["sources"])
    for s in [
        "https://finviz.com/news/333787/stock-market-news-for-mar-9-2026",
        "https://fortune.com/2026/03/09/trump-iran-war-end-very-soon-oil-sanctions-strait-hormuz-navy-escort/",
        "https://www.cnbc.com/2026/03/09/trump-iran-war-end.html",
        "https://www.cnbc.com/2026/03/08/stock-market-today-live-updates.html",
        "https://www.csmonitor.com/layout/set/amphtml/Business/2026/0310/oil-iran-war-economy-trump",
        "https://finviz.com/news/329448/stock-futures-boosted-by-middle-east-headlines",
        "https://www.barchart.com/story/news/899848/pre-markets-hopeful-for-a-near-term-solution-on-iran",
    ]:
        w.writerow([s])

print(f"context rows: {n_ctx}, ic rows: {n_ic}, fly rows: {n_fly} -> {OUT}")
