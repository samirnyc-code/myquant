"""Killer-day forensics: 2026-02-12 (Thu) — AI-displacement contagion day.

Extracts the local context (killer_context.csv rows 02-09..02-17, trade rows for
02-12 from rows.csv/fly_rows.csv) and writes a dated findings CSV combining the
local data with web-researched narrative facts (sources listed in FINDINGS).

Output: data/options_sim/backtest_full/killerday/2026-02-12_forensics.csv
Run:    python scripts/killerday/forensics_2026_02_12.py
"""
import csv
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BT = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUTDIR = os.path.join(BT, "killerday")
OUT = os.path.join(OUTDIR, "2026-02-12_forensics.csv")

DATES = {"2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13", "2026-02-17"}

# Web-researched facts (verified 2026-09-10). Sources:
#   finance.yahoo.com/news/stock-market-today-feb-12-224958163.html
#   finance.yahoo.com/news/live/stock-market-today-dow-sp-500-nasdaq-sink-as-tech-gets-hit-...-210353533.html
#   finance.yahoo.com/news/us-software-stocks-stabilize-bruising-121536263.html
#   fortune.com/2026/02/13/stocks-friday-the-13th-global-selloff-gold-ai-fear-markets
#   nasdaq.com/articles/stock-market-news-feb-12-2026 (Feb 11 close/NFP recap)
FINDINGS = [
    ("close_stats", "SPX -1.57% to 6832.76; Nasdaq -2.03%; Dow -669 (-1.34%). "
     "VIX 17.65 -> 20.82 (+3.17). Gold -3%; bitcoin ~78k -> ~65k (broad de-grossing)."),
    ("cause", "AI-displacement contagion day: week-long 'software-mageddon' (S&P software "
     "index ~-$1T since Jan 28, blamed on Anthropic Claude enterprise plug-in fears) jumped "
     "sectors intraday into trucking/logistics (CH Robinson -14.5%, RXO -20%, Russell 3000 "
     "trucking -6.6%), real-estate services, wealth management. Cisco -12% on weak guidance "
     "(reported Wed after close). Apple -5% on Siri delay reports. Palantir down on Burry short call."),
    ("overnight", "Quiet/green premarket: ES +0.17%, Dow futs +0.32%, NQ -0.07%. Cash gap "
     "+0.23% (open 6957.54 vs 6941.47). 07:30 CT initial claims 227k vs 223k est (benign). "
     "Only visible premarket warning: Cisco down high-single-digits on guidance."),
    ("intraday", "Opened up ~0.3%, turned red through LATE MORNING, accelerated in the "
     "afternoon as AI-fear headlines rolled sector to sector. Open-to-close ~-1.8%. "
     "No data print, Fed speech, or geopolitical trigger during RTH — a flow/narrative cascade."),
    ("prior_days", "Feb 10 -0.33%, Feb 11 -0.01% (third straight down day). Tension visible in "
     "SOFTWARE (7 straight down sessions, index ~21% under its 200dma, 'no dip-buying') but NOT "
     "at index level. Wed Feb 11: delayed Jan NFP +130k vs +53k est, unemp 4.3% -> rate-cut "
     "bets dampened. CPI scheduled next day (Fri Feb 13)."),
    ("aftermath", "SNAP-BACK, not continuation: Fri Feb 13 flat (+0.05%) despite Nikkei -1.2%/"
     "CSI300 -1.25%; CPI passed without damage (IC +597 that day); Feb 17 +0.05 prior/+0.56 next. "
     "Street called the AI-job-loss trade 'overdone'."),
    ("verdict", "Genuine intraday ambush with a quiet open. Nothing mechanical at 08:30 CT "
     "flagged it: no event, gap UP +0.23%, VIX 17.65 and falling, EM 77pts normal, claims benign. "
     "The one at-entry red flag was CREDIT THINNESS: eodic credits 0.2c/0.3p (vs 2.5p on 02-09, "
     "1.6/1.7 on 02-13) — vol too cheap to pay for the tail. Soft/contextual flags: 3rd straight "
     "down day, $1T software rout with zero dip-buying, Cisco premarket, CPI next day."),
]


def read_rows(path, datecol=0):
    with open(path, newline="") as f:
        r = csv.reader(f)
        hdr = next(r)
        return hdr, [row for row in r if row and row[datecol][:10] in DATES]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    ctx_hdr, ctx = read_rows(os.path.join(BT, "killer_context.csv"))
    rows_hdr, tr = read_rows(os.path.join(BT, "rows.csv"))
    fly_hdr, fl = read_rows(os.path.join(BT, "fly_rows.csv"))
    tr = [r for r in tr if r[0] == "2026-02-12"]
    fl = [r for r in fl if r[0] == "2026-02-12"]

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for k, v in FINDINGS:
            w.writerow(["finding", k, v])
        w.writerow(["context_header", "", "|".join(ctx_hdr)])
        for r in ctx:
            w.writerow(["context", r[0], "|".join(r)])
        w.writerow(["trade_header", "", "|".join(rows_hdr)])
        for r in tr:
            w.writerow(["trade", r[1] + "/" + r[2], "|".join(r)])
        w.writerow(["fly_header", "", "|".join(fly_hdr)])
        for r in fl:
            w.writerow(["fly", r[1], "|".join(r)])
    print("wrote", OUT, "findings:", len(FINDINGS), "ctx:", len(ctx), "trades:", len(tr), "flies:", len(fl))


if __name__ == "__main__":
    main()
