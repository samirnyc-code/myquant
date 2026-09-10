"""Killer-day forensics: 2023-02-14 (Jan-CPI day, Valentine's whipsaw).

Extracts the morning-context row + all backtest trade rows for the date,
joins the web-verified event narrative, and writes a dated findings CSV.

Book P&L that day (per killer-day shortlist): IC -510, ATM-fly -2116, puts-band -420.
NOTE: in rows.csv the vix252 IC streams all SETTLED GREEN (+927 combined in
killer_context.csv) -- the fly book took the entire hit (all 4 flies stopped,
both directions, both centers) because the day was a ~1.56% two-way range that
CLOSED FLAT (-0.03%). Classic fly-killer / IC-survivor day.

Web-verified narrative (sources in FINDINGS below):
- Scheduled event: Jan CPI 07:30 CT. Hot on all counts: headline +0.5% m/m,
  6.4% y/y vs 6.2% est (first y/y uptick in direction of surprise in 7 months);
  core +0.4% m/m, 5.6% y/y vs 5.5% est.
- Premarket: futures whipped on the print but the open was tame (cash gap
  -0.26%). Print was fully public an hour before 08:30 CT.
- Intraday: open ~4126.7 -> morning rally to ~4159 (high) -> midday/afternoon
  slide to 4095 low as 2y yield surged toward ~4.62% (highest since Nov 2022)
  and four Fed speakers (Barkin, Logan, Harker, Williams) leaned hawkish
  ("gradually raising ... until convincing evidence", "more persistence to
  inflation") -> late-afternoon rebound to close 4136.13, -0.03%.
- Prior days: Feb 13 pre-CPI relief rally +1.14%; prior week choppy post-NFP/
  Powell but VIX only ~20.3 and falling into the print. No visible panic.
- After: Feb 15 +0.28%, VIX -1.43 to 18.91 (snap-back calm); the inflation
  theme resurfaced Feb 16 (-1.38%, hot PPI + Bullard/Mester) and Feb 21 (-2%).
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
CTX = os.path.join(REPO, "data", "options_sim", "backtest_full", "killer_context.csv")
ROWS = os.path.join(REPO, "data", "options_sim", "backtest_full", "rows.csv")
FLY = os.path.join(REPO, "data", "options_sim", "backtest_full", "fly_rows.csv")
OUTDIR = os.path.join(REPO, "data", "options_sim", "backtest_full", "killerday")
DATE = "2023-02-14"

FINDINGS = [
    ("cause", "Jan CPI hot on all counts (6.4 y/y vs 6.2 est; core 5.6 vs 5.5) at 07:30 CT; "
              "rally-to-4159 then slide-to-4095 as 2y yield ran to ~4.62 (post-Nov high) on hawkish "
              "Fed speakers (Barkin/Logan/Harker/Williams); late rebound -> flat close 4136 (-0.03)"),
    ("overnight", "CPI print PUBLIC one hour before 08:30 CT; futures whipsawed on release; "
                  "cash gap only -0.26 -- tame open masking event risk"),
    ("prior_days", "Feb 13 pre-CPI relief rally +1.14; VIX 20.3 and FALLING into the event; no visible stress"),
    ("aftermath", "Feb 15 +0.28, VIX -1.43 to 18.91 = snap-back; theme returned Feb 16 (-1.38, hot PPI) and Feb 21 (-2.0)"),
    ("mechanics", "Two-way 64pt (~1.56%) range with flat close: all 4 flies stopped (eod P 13.2->14.1, "
                  "eod C 6.1->14.2, open P 8.7->18.0, open C 9.1->11.7) = -2116; all IC streams settled "
                  "worthless (close pinned near eod center 4137.29)"),
    ("signal_0830ct", "CPI on calendar (knowable premarket) + print already out and HOT by entry"),
    ("signal_0830ct", "EM 53pts elevated vs VIX 20.3 quiet -- options pricing event risk the tape wasn't"),
    ("signal_0830ct", "eodic put credit 5.4 vs call 0.85 -- extreme downside-skew richness at entry"),
    ("signal_0830ct", "gap only -0.26 despite hot CPI = quiet open; whipsaw risk NOT visible in gap/VIX"),
    ("verdict", "NOT an ambush: scheduled CPI, print public pre-entry. But direction/close were benign -- "
                "the kill was event-day PATH (two-way travel) which only the calendar flag + rich EM/put "
                "credit could proxy at 08:30 CT"),
    ("sources", "finance.yahoo.com/news/stock-market-news-today-february-14-2023-112357213.html"),
    ("sources", "investinglive.com/centralbank/federal-reserve-speakers-for-14-february-2023-barkin-logan-harker-willaims-20230214/"),
    ("sources", "seekingalpha.com/mp/1232-the-savvy-investor/articles/5838854 (Feb 14 chart update)"),
    ("sources", "zacks.com/stock/news/2054132/pre-markets-treat-strong-cpi-as-good-news"),
]


def rows_for_date(path, date):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, [row for row in r if row["date"] == date]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"forensics_{DATE.replace('-', '')}.csv")

    ctx_fields, ctx = rows_for_date(CTX, DATE)
    _, ic = rows_for_date(ROWS, DATE)
    _, fly = rows_for_date(FLY, DATE)

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for row in ctx:
            for k in ctx_fields:
                w.writerow(["context", k, row[k]])
        for row in ic:
            w.writerow(["ic_row", f"{row['strat']}/{row['method']}",
                        f"short {row['short_k']} credit {row['credit']} exit {row['exit_kind']} pnl {row['pnl']}"])
        for row in fly:
            w.writerow(["fly_row", row["strat"],
                        f"center {row['center']} credit {row['credit']} exit {row['exit_kind']}@{row['exit_val']} pnl {row['pnl']}"])
        for k, v in FINDINGS:
            w.writerow(["finding", k, v])
    print(f"wrote {out}")
    print(f"context rows: {len(ctx)}, ic rows: {len(ic)}, fly rows: {len(fly)}")


if __name__ == "__main__":
    main()
