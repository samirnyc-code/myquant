"""Killer-day forensics: 2026-06-17 (FOMC — Warsh's first meeting, hawkish hold).

Extracts the local context/trade rows for the date and writes a findings CSV
combining backtest data with web-verified event forensics.

Sources (web, checked 2026-09-09):
- cnbc.com/2026/06/16/stock-market-today-live-updates.html (Dow -500, yields surge, Warsh first meeting)
- cnbc.com/2026/06/17/fed-interest-rate-decision-june-2026.html (hold 3.50-3.75%, statement shortened, easing bias removed)
- cnbc.com/2026/06/17/warsh-fed-meeting-stock-market.html (worst first-Fed-day for a new chair since 1994; losses steepened during/after presser)
- federalreserve.gov/monetarypolicy/fomcprojtabl20260617.htm (SEP: median 2026 EOY 3.8% vs 3.4% March; 9/19 dots see a hike)
- thestreet.com stock-market-today-june-17-2026 (SPX -1.21% to 7420.10, Nasdaq -1.34%)
- icmarkets.com blog 2026-06-17 (premarket: futures flat, SPX/NDX near flatline, Dow +47; decision 2pm ET)
- cnbc.com/2026/06/14/stock-market-today-live-updates.html + 247wallst 2026-06-15 (Mon 6/15 +1.65% on US-Iran war-end deal, oil 3-mo low, SpaceX IPO rally)
- metatradingclub.com market-close-june-18-2026 (Thu 6/18 SPX +1.08% to 7500.58, Nasdaq +1.91% on Intel-Apple chip deal)
"""
import csv
import pathlib

ROOT = pathlib.Path(r"c:\Users\Admin\myquant")
CTX = ROOT / "data/options_sim/backtest_full/killer_context.csv"
ROWS = ROOT / "data/options_sim/backtest_full/rows.csv"
OUT = ROOT / "data/options_sim/backtest_full/killerday/killerday_20260617_findings.csv"

DATE = "2026-06-17"
WINDOW = {"2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18"}


def read_rows(path, datecol="date", keep=None):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if row[datecol] in (keep or {DATE})]


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ctx = read_rows(CTX, keep=WINDOW)
    trades = read_rows(ROWS)

    findings = [
        ("cause", "FOMC hawkish hold, Kevin Warsh's FIRST meeting as Fed chair: rate held "
                  "3.50-3.75% but statement dramatically shortened with easing bias removed; "
                  "SEP dot plot flipped - median 2026 EOY 3.8% vs 3.4% in March, 9/19 members "
                  "see at least one HIKE in 2026. 2yr yield +~11bp. SPX -1.21% to 7420.10, "
                  "worst first-Fed-day for a new chair since 1994; losses steepened during/after "
                  "the 13:30 CT presser (price stability emphasis)."),
        ("overnight", "Nothing. Futures flat premarket (SPX/NDX near flatline, Dow +47); no data "
                      "prints or news before 08:30 CT; everyone waiting on 13:00 CT Fed decision."),
        ("prior_days", "Opposite of tension: euphoric. Mon 6/15 +1.65% (US-Iran war-end deal, oil "
                       "to 3-mo low ~$80, SpaceX post-IPO surge, best Nasdaq day since 3/31). "
                       "Tue 6/16 mixed: Dow RECORD high +0.64% (crossed 52,000 intraday), SPX -0.57%. "
                       "VIX 16.41 into the event, +0.21 on the day - complacent."),
        ("aftermath", "Snap-back next day: Thu 6/18 gap +0.91%, SPX +1.08% to 7500.58, Nasdaq +1.91% "
                      "on Intel-Apple chip deal (INTC +10.6%); narrow chip-led leadership. VIX had "
                      "risen +2.03 to 18.44 on FOMC day. No continuation."),
        ("backtest_damage", "Entry ref 7511.35 (EOD) / 7524.5 (open). ALL put wings stopped "
                            "(short 7435-7475 across methods, exits 14-18); ALL call wings settled "
                            "worthless. SPX closed 7420.10, 15pts through the vix252 short put. "
                            "ic_pnl -2695, fly_pnl -566, puts_band_pnl -2943 (context row; fly row sum "
                            "matches -566, task brief said -640)."),
        ("observable_0830ct", "CALENDAR ONLY: (1) FOMC decision day - known for months; (2) not just "
                              "any FOMC: quarterly SEP/dot-plot meeting AND the first meeting + presser "
                              "of a brand-new Fed chair (maximum reaction-function uncertainty); "
                              "(3) EM 77.6 pts = 1.03% vs realized -1.21% - move exceeded EM; "
                              "(4) credits 1.7c/1.6p, richer than the surrounding non-event days "
                              "(6/16: 0.45/0.5) - the market WAS charging event premium; "
                              "(5) tape itself gave nothing: gap +0.18%, VIX 16.41 +0.21, futures flat."),
        ("verdict", "Scheduled-event ambush, not a news surprise. Quiet open by design (market pinned "
                    "ahead of 13:00 CT), all damage after the Fed release/presser. A mechanical system "
                    "could NOT have seen it in the tape but COULD have seen it in the calendar: "
                    "FOMC+SEP+new-chair-debut is a skip/size-down/close-before-14ET candidate."),
    ]

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for k, v in findings:
            w.writerow(["finding", k, v])
        for row in ctx:
            w.writerow(["context_row", row["date"], "|".join(f"{k}={v}" for k, v in row.items())])
        for row in trades:
            w.writerow(["trade_row", f"{row['strat']}/{row['method']}",
                        "|".join(f"{k}={v}" for k, v in row.items())])
    print(f"wrote {OUT} ({len(ctx)} context rows, {len(trades)} trade rows)")


if __name__ == "__main__":
    main()
