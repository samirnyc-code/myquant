"""Killer-day forensics extract: 2023-10-12 (Sept CPI day + failed 30y auction).

Pulls the morning-context row (+/- 2 days) from killer_context.csv and the
per-stream trade rows (rows.csv method==vix252, fly_rows.csv) for 2023-10-12,
and writes a dated CSV bundle for the killer-day dossier.

Web-verified narrative (2026-09-10 investigation):
- 08:30 ET (07:30 CT): Sept CPI hot on headline (+0.4% m/m vs +0.3% est,
  3.7% y/y vs 3.6% est; shelter >half the rise). Core 0.3%/4.1% IN LINE.
  Muted reaction -- stocks edged HIGHER at the open.
- Also 08:30 ET: jobless claims low (209k) -- labor still tight.
- Open quiet: gap +0.09%, SPX traded up to ~4385 in the morning.
- 13:00 ET (12:00 CT): 30-year Treasury auction stopped 4.837%, TAILED
  ~3.7bp, weak demand -- THIRD tailed auction of the week (3y Tue, 10y Wed).
  Long yields spiked; SPX reversed and slid all afternoon,
  closed 4349.61 (-0.62%), snapping a 4-day win streak.
- Damage to short-premium was an AFTERNOON intraday shock, not an open gap.
Sources: nasdaq.com stock-market-news-for-oct-12-2023 (note: that article
covers the 10/11 session), nasdaq.com TREASURIES US-yields-rise-after-
inflation-data-weak-30-year-bond-auction, cnbc.com/2023/10/12/cpi-
september-2023.html, bls.gov cpi_10122023.pdf, barchart 10/13 recap.
"""
import csv
import os

REPO = r"C:\Users\Admin\myquant"
BASE = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUT_DIR = os.path.join(BASE, "killerday")
DAY = "2023-10-12"
WINDOW = ["2023-10-10", "2023-10-11", "2023-10-12", "2023-10-13"]


def rows_from(path, keep):
    with open(path, newline="") as f:
        rdr = csv.DictReader(f)
        return rdr.fieldnames, [r for r in rdr if keep(r)]


def write(path, fields, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    f, ctx = rows_from(os.path.join(BASE, "killer_context.csv"),
                       lambda r: r["date"] in WINDOW)
    write(os.path.join(OUT_DIR, f"context_{DAY}.csv"), f, ctx)

    f, ic = rows_from(os.path.join(BASE, "rows.csv"),
                      lambda r: r["date"] == DAY and r["method"] == "vix252")
    write(os.path.join(OUT_DIR, f"ic_rows_{DAY}.csv"), f, ic)

    f, fly = rows_from(os.path.join(BASE, "fly_rows.csv"),
                       lambda r: r["date"] == DAY)
    write(os.path.join(OUT_DIR, f"fly_rows_{DAY}.csv"), f, fly)


if __name__ == "__main__":
    main()
