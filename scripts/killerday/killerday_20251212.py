"""Killer-day forensics: 2025-12-12 (Fri) — AI-trade unwind day (Broadcom -11%, Oracle/OpenAI delay report).

Extracts local evidence from the backtest CSVs (context row, surrounding days,
IC rows, fly rows) and writes a dated evidence CSV. No ThetaData requests.

Backtest day P&L (vix252 IC book): IC -420 (task framing) / context-table ic_pnl -2005
(context table sums eod+open IC put+call streams), fly +1435 table / -760 task framing,
puts-band -2003.

Web findings (researched 2026-09-10, sources in killerday_20251212_findings.csv):
- Cause: AI-trade unwind. Broadcom (reported Thu 12/11 after close) fell ~-11.5%
  on margin/backlog commentary despite beat; Bloomberg/The Information report that
  Oracle delayed OpenAI data centers 2027->2028 hit during the AFTERNOON session,
  accelerating the slide. SPX -1.07% to 6,827.41, Nasdaq -1.69%, Dow -0.51%
  (Dow made an intraday record high that morning). SOX -5% intraday at worst.
- Overnight/premarket: quiet. S&P futures +0.17%, Dow futs +0.34%, Nasdaq futs
  -0.07%; AVGO only ~-4/-5% premarket (bounced after-hours first, then reversed).
  Cash gap -0.21%. No US economic data that morning.
- Prior days: 12/10 FOMC 25bp cut (3rd cut) +0.67%, Oracle Q2 FY26 miss after
  close 12/10 -> ORCL -11% on 12/11, yet SPX +0.21% to a RECORD close 12/11 with
  VIX down to 14.85. Index masked the single-name AI stress.
- After: no snap-back. 12/15 -0.16%, 12/16 -0.24% (delayed Nov NFP), 12/17 -1.16%,
  bounce only 12/18 (+0.79%, CPI day) / 12/19 (+0.88%).
- 08:30 CT observability: LOW for a mechanical system. VIX 14.85 and falling,
  green futures, small gap, no scheduled event. Only soft tells: AVGO -5% premarket
  after a week of AI-name stress, put credit 1.1 vs call credit 0.00 (call side
  untradeable-thin = skew already one-sided), day-after-record + Friday OpEx-adjacent
  low IV. The kill shot (Oracle delay headline) was an afternoon intraday ambush.
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
BASE = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUT_DIR = os.path.join(BASE, "killerday")
DAY = "2025-12-12"


def rows_from(path, datecol="date", dates=None):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if row[datecol] in dates]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    window = ["2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12",
              "2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19"]

    ctx = rows_from(os.path.join(BASE, "killer_context.csv"), dates=set(window))
    ics = rows_from(os.path.join(BASE, "rows.csv"), dates={DAY})
    flys = rows_from(os.path.join(BASE, "fly_rows.csv"), dates={DAY})

    out = os.path.join(OUT_DIR, "killerday_20251212_evidence.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "detail"])
        w.writerow(["context_header", "date,dow,event,gap_pct,prior_ret,prior_range,prior2_ret,vix_prior,vix_chg,em_pts,cr_eodic_c,cr_eodic_p,ic_pnl,fly_pnl,puts_band_pnl,next_ret"])
        for r in ctx:
            w.writerow(["context", ",".join(r.values())])
        w.writerow(["ic_header", "date,strat,method,center,em,short_k,long_k,credit,exit_kind,exit_val,pnl,note"])
        for r in ics:
            w.writerow(["ic_row", ",".join(v or "" for v in r.values())])
        w.writerow(["fly_header", "date,strat,center,short_k,long_k,credit,exit_kind,exit_val,pnl,note"])
        for r in flys:
            w.writerow(["fly_row", ",".join(v or "" for v in r.values())])

    find = os.path.join(OUT_DIR, "killerday_20251212_findings.csv")
    with open(find, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["item", "value"])
        w.writerow(["cause", "AI-trade unwind: Broadcom -11.5% (margin/backlog commentary after 12/11 post-close earnings beat) + afternoon Bloomberg/The Information report Oracle delayed OpenAI data centers 2027->2028 (Oracle denied it). SPX -1.07% to 6827.41 from 12/11 record; Nasdaq -1.69%; Dow -0.51% after intraday record; SOX -5% at worst; NVDA -2.9%."])
        w.writerow(["overnight", "Quiet/green: SPX futs +0.17%, Dow futs +0.34%, NQ futs -0.07% premarket; AVGO ~-4/-5% premarket (first rose after hours, reversed on Hock Tan backlog/margin commentary); no US data before open; cash gap -0.21%."])
        w.writerow(["prior_days", "12/10 FOMC 25bp cut, SPX +0.67%; Oracle Q2 FY26 cloud-rev miss + capex jump after close 12/10 -> ORCL -11% on 12/11; yet SPX +0.21% RECORD close 12/11, VIX 14.85 (-0.92). AI stress visible in single names, masked at index level."])
        w.writerow(["aftermath", "No snap-back: 12/15 -0.16%, 12/16 -0.24% (delayed Nov jobs), 12/17 -1.16%, then bounce 12/18 +0.79% (CPI) and 12/19 +0.88%. VIX 15.74 close 12/12 (+0.89 only)."])
        w.writerow(["intraday_shock", "TRUE - mixed open, Dow record intraday, selling accelerated on afternoon Oracle-delay headline; put wing 6835/6810 (66pts below 6901 close) stopped at 12.1 vs 1.1 credit."])
        w.writerow(["detectable_0830ct", "MOSTLY NO - VIX 14.85 falling, green futures, gap -0.21%, no event. Soft tells only: AVGO -5% premkt after ORCL -11% the day before (AI-complex stress 2 days running); call-side credit 0.00 (untradeable) vs put 1.1 = one-sided skew; day-after-record complacency; EM 64.6pts vs realized -74pt drop."])
        w.writerow(["source", "https://www.cnbc.com/2025/12/11/stock-market-today-live-updates.html"])
        w.writerow(["source", "https://finance.yahoo.com/news/live/stock-market-today-dow-sp-500-nasdaq-sink-to-cap-brutal-week-for-tech-stocks-210016552.html"])
        w.writerow(["source", "https://www.cnbc.com/2025/12/12/broadcom-tumbles-10percent-after-earnings-as-ai-trade-sells-off-.html"])
        w.writerow(["source", "https://www.bloomberg.com/news/articles/2025-12-12/some-oracle-data-centers-for-openai-delayed-to-2028-from-2027"])
        w.writerow(["source", "https://www.cnbc.com/2025/12/12/oracle-says-there-have-been-no-delays-in-openai-arrangement.html"])
        w.writerow(["source", "https://fortune.com/2025/12/11/oracle-earnings-stock-falls-11-percent-why-investors-disappointed-data-centers-cloud/"])
        w.writerow(["source", "https://www.forbes.com/sites/tylerroush/2025/12/12/broadcom-shares-plummet-10-after-sales-forecast-falls-short/"])

    print("wrote", out)
    print("wrote", find)
    print("context rows:", len(ctx), "ic rows:", len(ics), "fly rows:", len(flys))


if __name__ == "__main__":
    main()
