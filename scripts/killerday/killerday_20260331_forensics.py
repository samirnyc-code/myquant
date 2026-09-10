"""Killer-day forensics: 2026-03-31 (Iran-war de-escalation melt-up).

Extracts the morning-context row and all backtest trade rows for 2026-03-31,
attaches the web-forensics findings (cause / overnight / prior days / aftermath /
0830CT-observable signals), and writes a dated CSV bundle under
data/options_sim/backtest_full/killerday/.

Run:  python scripts/killerday/killerday_20260331_forensics.py
"""
import csv
import os

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BT = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUT_DIR = os.path.join(BT, "killerday")
DATE = "2026-03-31"


def rows_for_date(path, date):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, [row for row in r if row.get("date") == date]


FINDINGS = [
    ("cause", "SPX +2.91% to 6528.52 (best day since May 2025) on US-Iran war "
              "de-escalation: unconfirmed report that Iranian President Pezeshkian is "
              "open to ending the war with guarantees (phone call w/ EU Council's Costa, "
              "Mar 31) + Trump telling NY Post the same day he believes the war will "
              "likely end soon. Relief rally after ~-8% war selloff; killed the CALL side."),
    ("overnight", "Premarket already firming on early de-escalation signals; SPX cash "
                  "gapped +0.82% (6343.72 -> 6395.88 open). Oil spiked first overnight "
                  "(Brent topped ~$108, WTI ~$107) then reversed hard intraday on the "
                  "peace headlines (Brent -2.8% to ~$105)."),
    ("prior_days", "War regime since 2026-02-28; ~5 weeks of war-driven volatility; SPX "
                   "-8% through Mar 30; Mar 30 (Mon): opened +0.9%, faded to -0.3%, worst "
                   "week since war began, weekend Houthi entry, WTI settled $102.88; "
                   "prior2 ret -1.67%; VIX prior close 30.61."),
    ("aftermath", "Continuation, not snap-back: Apr 1 +0.72%; rally ran ~2 weeks; SPX "
                  "wiped out entire war-era decline and hit record highs by Apr 15. VIX "
                  "collapsed >4 pts to ~26 on the day."),
    ("signal_0830ct_1", "VIX prior close 30.61 - extreme-vol regime; +/-3% daily tails live."),
    ("signal_0830ct_2", "Active war headline regime = unscheduled binary catalysts both "
                        "directions; a peace headline in an oversold tape is an upside bomb."),
    ("signal_0830ct_3", "Gap +0.82% UP after -8% multi-week selloff: classic relief/short-"
                        "cover setup; upside tail asymmetry against short calls."),
    ("signal_0830ct_4", "Credit asymmetry at entry: cr_eodic_p 0.05 (below own 0.10 thin "
                        "gate) vs cr_eodic_c 3.90 - position was effectively a naked short "
                        "call bet; the market was paying nothing for downside."),
    ("signal_0830ct_5", "EM 122.3 pts (~1.9% of spot) - day's realized +2.9% was only "
                        "~1.5x EM; condor wings were inside a fairly-priced vol regime."),
    ("signal_0830ct_6", "Quarter-end (worst quarter since 2022) - rebalance buy-flow day; "
                        "plus prior-day open-fade whipsaw showed headline sensitivity."),
    ("scheduled_event", "Conference Board Consumer Confidence (91.8 vs 91.2 prior) - minor, "
                        "not the driver. No FOMC/CPI/NFP."),
    ("verdict", "NOT a quiet-open ambush. Catalyst headlines hit intraday, but by 08:30 CT "
                "the tape was screaming: VIX 30.6, war regime, up-gap in oversold market, "
                "put credit 0.05 vs call credit 3.90. A mechanical gate on (VIX>25 & gap-up "
                "& one-sided credit) flags this day premarket."),
]

SOURCES = [
    "https://www.cnbc.com/2026/03/30/stock-market-today-live-updates.html",
    "https://finance.yahoo.com/markets/stocks/articles/stock-market-today-march-31-214400738.html",
    "https://www.rferl.org/a/pezeshkian-iran-peace-us-war-talks/33721776.html",
    "https://resources.quantel.ai/daily-market-summary/stock-market-summary-march-31-2026",
    "https://tradingeconomics.com/commodity/brent-crude-oil/news/537978",
    "https://www.fortune.com/2026/03/30/markets-react-iran-war-oil-price-keeps-going-higher",
    "https://www.pbs.org/newshour/economy/wall-street-hits-record-as-sp-500-continues-2-week-rally-boosted-by-hopes-for-iran-wars-end",
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    ctx_fields, ctx = rows_for_date(os.path.join(BT, "killer_context.csv"), DATE)
    rows_fields, trades = rows_for_date(os.path.join(BT, "rows.csv"), DATE)

    out = os.path.join(OUT_DIR, f"forensics_{DATE.replace('-', '')}.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for row in ctx:
            for k in ctx_fields:
                w.writerow(["context_row", k, row[k]])
        for i, row in enumerate(trades):
            for k in rows_fields:
                if k:
                    w.writerow([f"trade_row_{i}", k, row[k]])
        for k, v in FINDINGS:
            w.writerow(["finding", k, v])
        for s in SOURCES:
            w.writerow(["source", "url", s])
    print(f"wrote {out}: {len(ctx)} context row(s), {len(trades)} trade rows, "
          f"{len(FINDINGS)} findings")


if __name__ == "__main__":
    main()
