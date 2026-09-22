"""Killer-day forensics: 2025-10-10 (Trump 100% China tariff / rare-earth ambush).

Reads the context row + trade rows for 2025-10-10, joins them with the
web-verified event narrative, and writes a dated findings CSV.

Sources (verified 2026-09-09):
- CNBC 2025-10-11: Trump Truth Social post 10:57 a.m. ET wiped ~$2T off stocks.
  https://www.cnbc.com/2025/10/11/trump-post-costs-stocks-2-trillion-in-single-day.html
- Fortune 2025-10-11: SPX was within ~2 pts of an all-time high Friday morning
  before the post; -2.7% close, worst day since April.
  https://fortune.com/2025/10/11/stocks-worst-day-since-april-sp-500-liberation-day-trade-war/
- CBS News: S&P -2.7% to 6,552; after the close Trump announced 100% tariff on
  Chinese imports effective Nov 1 + software export controls.
  https://www.cbsnews.com/news/stocks-today-trump-china-tariffs-dow-nasdaq-s-p-500/
- YCharts / FinancialContent: China MOFCOM Announcement No. 61 (Oct 9) — rare
  earth export controls expanded to 12 of 17 elements + first use of the
  foreign-direct-product rule (0.1% content threshold).
- CNBC 2025-10-13: Monday rebound +1.56% (S&P 6,654.72) after Trump's Sunday
  "Don't worry about China, it will all be fine!" post.
  https://www.cnbc.com/2025/10/12/stock-market-today-live-updates.html
- FXStreet: UMich prelim sentiment 10/10 10:00 ET: 55.0 vs 54.2 f'cast (flat,
  non-event). Gov't shutdown day 10 -> CPI/PPI/claims all suspended.
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
BT = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUTDIR = os.path.join(BT, "killerday")
DATE = "2025-10-10"

os.makedirs(OUTDIR, exist_ok=True)


def rows_for(path, date):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if row["date"] == date]


ctx = rows_for(os.path.join(BT, "killer_context.csv"), DATE)[0]
ic = [r for r in rows_for(os.path.join(BT, "rows.csv"), DATE) if r["method"] == "vix252"]
fly = rows_for(os.path.join(BT, "fly_rows.csv"), DATE)

findings = [
    ("context_row", str(ctx)),
    ("ic_vix252_rows", str(ic)),
    ("fly_rows", str(fly)),
    ("vix_ohlc_1010", "open 16.36 / high 22.44 / close 21.66 (data/vix_daily.csv)"),
    ("cause", "10:57 a.m. ET Trump Truth Social: China 'very hostile' on rare earths, "
              "'no reason' to meet Xi, threatens 'massive increase of tariffs'; after the "
              "close: 100% tariff on Chinese imports (eff. Nov 1) + software export controls. "
              "SPX -2.7% to 6,552, worst day since April; ~$2T market cap erased; Nasdaq -3.6%."),
    ("overnight", "Quiet. Gap +0.08%; futures slightly up premarket near record highs; "
                  "no US data (shutdown day 10); UMich 10:00 ET a non-event (55.0)."),
    ("prior_days", "Oct 8 SPX/Nasdaq record closing highs; Oct 9 -0.28% mild fade. China "
                   "MOFCOM Announcement No.61 (rare-earth controls, 12 of 17 elements, FDPR) "
                   "published Oct 9 and NOT priced by equities; White House response pending."),
    ("aftermath", "Snap-back: Sunday Trump 'Don't worry about China'; Mon 10/13 SPX +1.56% "
                  "to 6,654.72 (56% retrace, biggest gain since May); next_ret in ctx = 1.56."),
    ("detectable_0830ct", "NO on the numbers: VIX prior close 16.43 / +0.13 chg, gap +0.08%, "
                          "flat put credit 0.25 on a 69.7pt-EM condor, no scheduled event. "
                          "Only qualitative tell: China's biggest-ever rare-earth escalation was "
                          "24h old with no US response yet — pure headline-pending risk. Call-side "
                          "credit 0.00 (dead call skew at ATH) was the one structural oddity."),
    ("classification", "GENUINE INTRADAY AMBUSH — quiet open, single social-media post at "
                       "09:57 CT; VIX open 16.36 -> high 22.44 same day."),
]

out = os.path.join(OUTDIR, f"killerday_{DATE.replace('-', '')}_findings.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["key", "value"])
    w.writerows(findings)
print("wrote", out)
