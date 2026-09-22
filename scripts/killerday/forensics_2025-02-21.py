"""Killer-day forensics extract: 2025-02-21 (Feb monthly OpEx Friday).

Pulls the morning-context row + all backtest trade rows for the day and writes
a dated CSV under data/options_sim/backtest_full/killerday/.

Findings summary (web-verified 2026-09-10, sources in killerday CSV notes):
- SPX -1.71% to 6013.13, Dow -748 (worst day of 2025 to that point). VIX 15.66 -> ~18.2.
- Open was quiet: gap -0.06%, S&P futures ~flat premarket (Dow dragged by UNH -11%
  on WSJ DOJ Medicare-billing probe headline). Genuine intraday ambush.
- Kill sequence (all AFTER 08:30 CT): 08:45 CT S&P flash services PMI 49.7 vs 52.8
  exp (contraction, ~2-yr low); 09:00 CT UMich final Feb sentiment 64.7 with 1-yr
  inflation exp 4.3% and 5-10yr 3.5% (highest since Apr 1995) + existing home sales
  miss (4.08M); midday "new bat coronavirus study" (Wuhan) headline; selling
  accelerated into the close on OpEx (~$2.7T) + fear of weekend tariff headlines.
- Prior days: SPX record closes Feb 19 (ATH twice that week); Feb 20 -0.43% on
  Walmart's weak consumer guidance. Mild tension, nothing screaming.
- After: continuation, not snap-back. Feb 24 -0.5%, Feb 25 -0.47% (4th straight
  down day), Feb 26/27 worse -> start of the Feb-Mar 2025 tariff correction.
- Observable by 08:30 CT: monthly-OpEx Friday + PMI/UMich slate on the calendar,
  ATH market with a consumer warning the day before, call credit 0.05 (thin per
  our own <0.10 gate). VIX 15.66, no gap, normal put credit 0.80 -> no mechanical
  red flag on vol/gap/credit-richness alone.
"""
import csv
import os

REPO = r"C:\Users\Admin\myquant"
DAY = "2025-02-21"
CTX = os.path.join(REPO, r"data\options_sim\backtest_full\killer_context.csv")
ROWS = os.path.join(REPO, r"data\options_sim\backtest_full\rows.csv")
FLY = os.path.join(REPO, r"data\options_sim\backtest_full\fly_rows.csv")
OUTDIR = os.path.join(REPO, r"data\options_sim\backtest_full\killerday")
OUT = os.path.join(OUTDIR, f"forensics_{DAY}.csv")


def rows_for(path, day):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [(r.fieldnames, row) for row in r if row.get("date") == day]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    out = []
    for src, path in (("context", CTX), ("ic_rows", ROWS), ("fly_rows", FLY)):
        for fields, row in rows_for(path, DAY):
            out.append({"source": src, **row})
    keys = ["source"]
    for rec in out:
        for k in rec:
            if k not in keys:
                keys.append(k)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print(f"wrote {OUT} ({len(out)} rows)")


if __name__ == "__main__":
    main()
