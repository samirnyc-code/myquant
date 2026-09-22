"""Killer-day forensics: 2023-05-02 (regional-bank rout, FOMC eve).

Extracts the morning-context row + all backtest trade rows for the day and
writes a dated findings CSV. Web-verified narrative is embedded in FINDINGS.

Sources (verified 2026-09-10):
- CNBC 2023-05-02: PacWest -28% (halts), regional banks slide to new lows
  https://www.cnbc.com/2023/05/02/pacwest-falls-30percent-as-regional-banks-stocks-slide-to-new-lows.html
- CNBC 2023-05-02: JOLTS March job openings 9.59M vs 9.64M est (10:00 ET)
  https://www.cnbc.com/2023/05/02/jolts-march-2023-.html
- Forbes 2023-05-02: Dow -540 (-1.6%), S&P -1.7% intraday, PacWest -39%
  intraday, Western Alliance -21%, KBW regional index -5.5% (worst since SVB)
  https://www.forbes.com/sites/jonathanponciano/2023/05/02/dow-plunges-500-points-as-more-bank-stocks-crash/
- Barchart 2023-05-02: WTI settled -5.29% at $71.66; all 11 S&P sectors red
- Nasdaq/press: Yellen letter (X-date "as early as June 1") released Mon
  2023-05-01 afternoon; JPM-First Republic seizure/deal announced pre-open
  2023-05-01 (2nd-largest US bank failure ever)
- CNBC 2023-05-03: FOMC +25bp to 5.00-5.25 (10th straight), May 4 PacWest
  -50% (exploring sale), May 5 +1.85% S&P rally (Apple + NFP beat)
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
CTX = os.path.join(REPO, "data", "options_sim", "backtest_full", "killer_context.csv")
ROWS = os.path.join(REPO, "data", "options_sim", "backtest_full", "rows.csv")
FLY = os.path.join(REPO, "data", "options_sim", "backtest_full", "fly_rows.csv")
OUTDIR = os.path.join(REPO, "data", "options_sim", "backtest_full", "killerday")
DAY = "2023-05-02"

FINDINGS = [
    ("cause", "Regional-bank contagion rout day after First Republic seizure: "
     "PacWest -28pct (multiple halts, -39pct intraday), Western Alliance -15pct, "
     "KBW regional index -5.5pct (worst since SVB March). Amplifiers: Yellen "
     "debt-ceiling X-date 'as early as June 1' letter (out Mon 5/1 PM), JOLTS "
     "9.59M miss at 10:00 ET, WTI -5.3pct, FOMC decision next day. SPX "
     "4167.87 -> 4119.58 (-1.16pct), low 4089.7 (-1.9pct)."),
    ("overnight", "Quiet: gap -0.09pct at open (open 4163-4164 vs 4167.87 close). "
     "Yellen letter and First Republic/JPM deal were known before the open; "
     "RBA surprise +25bp hike overnight; oil already sliding. Futures barely down."),
    ("prior_days", "Mon 5/1: First Republic seized + sold to JPM pre-open; SPX "
     "closed flat (-0.04pct) but regional banks (KRE) fell -2-3pct - stress was "
     "visible in banks, not in the index. Fri 4/28 +0.83pct. VIX 16.08, near lows."),
    ("aftermath", "No snap-back: 5/3 FOMC +25bp, SPX -0.70pct; 5/4 PacWest -50pct "
     "(exploring sale), SPX -0.72pct; 5/5 +1.85pct rally (Apple earnings + NFP "
     "beat). 3-day continuation of bank stress before relief."),
    ("morning_signals", "By 08:30 CT the numeric features were QUIET (gap -0.09, "
     "VIX 16.08 +0.3, EM 42pts, prior day flat). The loud signals were "
     "contextual: FOMC-eve + FOMC meeting starting that day, active bank "
     "failure 24h old, debt-ceiling X-date headline, JOLTS scheduled 09:00 CT. "
     "The single best mechanical tell was OUR OWN CREDIT ASYMMETRY at entry: "
     "call-side EOD-IC credit 0.00 (entry-gate 'broken') vs put-side 0.80 - "
     "the market was pricing pure downside. Put shorts sat only ~1pct OTM."),
    ("verdict", "Intraday ambush with a quiet open, but NOT an unknowable one: "
     "price/vol features gave nothing, while the event calendar (FOMC eve, "
     "bank crisis in progress) and the zero call credit at entry were "
     "observable warnings."),
]


def rows_matching(path, day):
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        return header, [row for row in r if row and row[0] == day]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"forensics_{DAY}.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        h, ctx = rows_matching(CTX, DAY)
        for row in ctx:
            for k, v in zip(h, row):
                w.writerow(["context", k, v])
        for name, path in (("ic_rows", ROWS), ("fly_rows", FLY)):
            h, rr = rows_matching(path, DAY)
            for row in rr:
                w.writerow([name, "|".join(h), "|".join(row)])
        for k, v in FINDINGS:
            w.writerow(["finding", k, v])
    print("wrote", out)


if __name__ == "__main__":
    main()
