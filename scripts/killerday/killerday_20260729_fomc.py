"""Killer-day forensics: 2026-07-29 (FOMC hold + hawkish Warsh presser).

Extracts the local backtest evidence for 2026-07-29 (context row, IC/fly trade
rows, surrounding days) and writes a dated findings CSV combining the local
data with web-verified narrative facts.

Backtest damage that day: IC condor -2131 (vix252 streams), fly rows net -826,
puts-band 0 (skipped: put credit 3.0 above the 0.5-2.5 band).

Web-verified narrative (sources listed in SOURCES below, retrieved 2026-09-09):
- FOMC day 2 of the Jul 28-29 meeting. FOMC voted 9-3 to HOLD at 3.50-3.75%
  (5th straight hold); Hammack, Kashkari, Logan dissented FOR a +25bp hike.
- Market had priced ~1-in-3 odds of a hike going in (per the minutes); nominal
  Treasury yields had risen 25-30bp over the intermeeting period on rising oil
  (Trump/Iran threats) and re-ignited inflation expectations.
- Morning session was QUIET: SPX ~+0.1% pre-decision. The damage came after
  the 13:00 CT statement and during Chair Warsh's presser ("There is no soft
  inflation target... it's 2%"): long yields spiked (30y ~5.19-5.21%, highest
  since 2007; 10y toward 4.69%) as the bond market read the hold as the Fed
  falling behind on inflation. SPX closed -1.52% at 7,316.15; Dow -1,153
  (-2.19%), worst day since Apr 2025. VIX 18.21 -> 20.66 (+2.45).
- Next day 2026-07-30: full snap-back. SPX +1.7%, Nasdaq +2.8%, Dow +1.2%,
  helped by Microsoft +16% (record 1-day value gain ~$450B) on Azure beat.
  VIX bled back (17.09 by 7/31 close).
- Prior 1-3 days: tape was flat/quiet (7/27 +0.05%, 7/28 +0.2%, ranges ~1%)
  but macro tension was visible: Asia chip rout Tue 7/28 (SK Hynix -11%,
  Samsung -9%), oil rising, long-end yields surging, hike odds being repriced.
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
CTX = os.path.join(REPO, "data", "options_sim", "backtest_full", "killer_context.csv")
ROWS = os.path.join(REPO, "data", "options_sim", "backtest_full", "rows.csv")
FLY = os.path.join(REPO, "data", "options_sim", "backtest_full", "fly_rows.csv")
OUTDIR = os.path.join(REPO, "data", "options_sim", "backtest_full", "killerday")
DAY = "2026-07-29"

SOURCES = [
    "https://www.cnbc.com/2026/07/28/stock-market-today-live-updates.html",
    "https://www.cnbc.com/2026/07/29/fed-meeting-today-live-updates.html",
    "https://www.cnn.com/2026/07/29/business/bond-yields-fed-warsh",
    "https://www.federalreserve.gov/monetarypolicy/fomcminutes20260729.htm",
    "https://www.cnbc.com/2026/08/19/fed-minutes-july-2026-officials-saw-need-for-rate-hike-if-inflation-doesnt-cool.html",
    "https://247wallst.com/investing/2026/07/29/stock-market-live-july-29-2026-sp-500-spy-slightly-higher-as-markets-wait-on-the-fed/",
    "https://www.cnbc.com/2026/07/29/stock-market-today-live-updates.html",
    "https://finance.yahoo.com/markets/live/stock-market-today-thursday-july-30-dow-sp-500-nasdaq-treasury-yields-microsoft-082255995.html",
]

def rows_for(path, day):
    with open(path, newline="") as f:
        r = list(csv.DictReader(f))
    return [x for x in r if x["date"] == day], r

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    ctx_rows, all_ctx = rows_for(CTX, DAY)
    ctx = ctx_rows[0]
    ic, _ = rows_for(ROWS, DAY)
    fly, _ = rows_for(FLY, DAY)

    # window: 3 prior trading days + day + 2 after
    idx = next(i for i, x in enumerate(all_ctx) if x["date"] == DAY)
    window = all_ctx[max(0, idx - 3): idx + 3]

    out = os.path.join(OUTDIR, f"killerday_{DAY.replace('-', '')}_findings.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        w.writerow(["verdict", "cause",
                    "FOMC 9-3 HOLD at 3.50-3.75% + hawkish Warsh presser; bond market "
                    "read hold as Fed behind on inflation (3 hawkish dissents, ~1/3 hike "
                    "odds priced); 30y yield to ~5.21% (highest since 2007); SPX -1.52% "
                    "to 7316.15, all damage after 13:00 CT"])
        w.writerow(["verdict", "intraday_shock", "yes - quiet open (SPX ~+0.1% pre-decision), gap only -0.14%"])
        w.writerow(["verdict", "detectable_by_0830CT",
                    "yes as EVENT RISK, no as direction: FOMC on calendar, put credit 3.0 "
                    "vs call 0.7 (put skew extreme), em 85.2pts elevated, VIX 18.2 flat; "
                    "no price signal"])
        for k, v in ctx.items():
            w.writerow(["context_row", k, v])
        for x in ic:
            w.writerow(["ic_row", f"{x['strat']}/{x['method']}",
                        f"short {x['short_k']} credit {x['credit']} exit {x['exit_kind']} pnl {x['pnl']}"])
        for x in fly:
            w.writerow(["fly_row", x["strat"],
                        f"short {x['short_k']} credit {x['credit']} exit {x['exit_kind']} pnl {x['pnl']}"])
        for x in window:
            w.writerow(["window", x["date"],
                        f"dow {x['dow']} event {x['event'] or '-'} gap {x['gap_pct']} "
                        f"prior_ret {x['prior_ret']} vix {x['vix_prior']} vixchg {x['vix_chg']} "
                        f"em {x['em_pts']} ic {x['ic_pnl']} next_ret {x['next_ret']}"])
        for s in SOURCES:
            w.writerow(["source", "", s])
    print("wrote", out)

if __name__ == "__main__":
    main()
