"""Killer-day forensics: 2023-12-20 (SPX -1.47%, late-day 0DTE-flow flush).

Reads the morning-context row from killer_context.csv, writes the window
(D-3..D+2) plus a findings/signals table to dated CSVs under
data/options_sim/backtest_full/killerday/.

Web findings baked in (researched 2026-09-09; sources listed in SOURCES):
- No news catalyst. SPX hit a fresh 52-wk high ~4778 intraday (9-day win
  streak post 12/13 FOMC pivot), then dropped ~1.5% in the final ~90 min,
  closing 4698.35 (-1.47%), worst day since Sep. Trading community blamed
  heavy 0DTE/1DTE put volume concentrated at 4755-4765 strikes (billions
  notional, one of the year's highest SPX put volumes) into an overbought,
  holiday-thinned tape. Cboe disputed the 0DTE-causation claim next day.
- Overnight/premarket was QUIET: ES ~-11 at 8:10 ET, ~17pt overnight range,
  Asia up, Europe mostly up. UK CPI downside surprise (3.9% vs 4.6% prior)
  rallied global bonds. FedEx -10% premarket on guidance cut (single-stock).
  10:00 ET data were BEATS (Conf. Board confidence 110.7 vs 104.5 exp;
  existing home sales +0.8% vs decline exp) - bullish, not bearish.
- Prior days: melt-up. 12/13 FOMC dovish pivot -> 9 straight up days,
  VIX ~12.5 (multi-year lows), small quiet ranges. No visible tension.
- Day after (12/21): snap-back +1.03% (next_ret in CSV), recovering most
  of the drop. VIX popped 12.53 -> 13.67 on the event day then faded.
"""
from __future__ import annotations

import csv
from pathlib import Path

REPO = Path(r"c:\Users\Admin\myquant")
CTX = REPO / "data/options_sim/backtest_full/killer_context.csv"
OUT = REPO / "data/options_sim/backtest_full/killerday"
DAY = "2023-12-20"
WINDOW = ["2023-12-15", "2023-12-18", "2023-12-19", "2023-12-20",
          "2023-12-21", "2023-12-22"]

SOURCES = [
    "https://www.barchart.com/story/news/22887500/zero-day-options-in-spotlight-for-sp-500s-sharp-decline",
    "https://www.bloomberg.com/news/articles/2023-12-21/zero-day-options-catch-blame-for-selloff-cboe-says-not-so-fast",
    "https://www.cnbc.com/2023/12/21/profit-taking-economic-worries-or-options-trading-sudden-sell-off-confounds-analysts.html",
    "https://quantpartners.substack.com/p/qpi-note-122023-stocks-lower-on-some",
    "https://www.fxstreet.com/news/forex-today-soft-uk-inflation-weighs-on-pound-sterling-focus-shifts-to-us-data-202312200714",
]

# signal, knowable_at, note
SIGNALS = [
    ("VIX 12.53, multi-year low regime", "premarket",
     "Premium floor: em_pts 37.6 but credits collapsed - richness was NOT there"),
    ("Call-side credit 0.05 (cr_eodic_c)", "at-entry",
     "Near-zero call credit after 9 up days = market paying nothing for upside risk; "
     "book was effectively short-put-skewed for pennies"),
    ("Put-side credit 0.70 (cr_eodic_p)", "at-entry",
     "All the credit on the put side; skew said downside was the priced risk"),
    ("Gap -0.08%, ES overnight range ~17pt", "premarket",
     "Dead-quiet open - nothing to warn on"),
    ("9 straight up days, RSI-overbought, 52-wk high tape", "premarket",
     "Fragility/positioning signal, not a timing signal"),
    ("No scheduled macro event (only 2nd-tier 10:00 data + 20y auction)", "premarket",
     "Calendar was clean; both 10:00 prints BEAT (bullish surprise)"),
    ("Heavy 0DTE/1DTE put prints 4755-4765 mid-session", "intraday-only",
     "The actual trigger per Cantor/Bloomberg; unknowable at 08:30 CT"),
]

FINDINGS = {
    "date": DAY,
    "spx_close_ret_pct": -1.47,
    "intraday_high": 4778.01,
    "close": 4698.35,
    "drop_from_high_pct": -1.67,
    "cause": ("No news catalyst. Late-day (~14:00-15:30 ET) flow flush blamed on "
              "heavy 0DTE/1DTE SPX put buying at 4755-4765 into overbought, "
              "holiday-thin tape after a 9-day win streak; dealer hedging cascade. "
              "Cboe disputed 0DTE causation next day. Worst day since September."),
    "detectable_by_0830ct": False,
    "intraday_shock": True,
    "next_day_ret_pct": 1.03,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with CTX.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["date"] in WINDOW]
    assert any(r["date"] == DAY for r in rows), "context row missing"

    wpath = OUT / f"killerday_{DAY.replace('-', '')}_window.csv"
    with wpath.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    spath = OUT / f"killerday_{DAY.replace('-', '')}_signals.csv"
    with spath.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["signal", "knowable_at", "note"])
        w.writerows(SIGNALS)

    fpath = OUT / f"killerday_{DAY.replace('-', '')}_findings.csv"
    with fpath.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in FINDINGS.items():
            w.writerow([k, v])
        for s in SOURCES:
            w.writerow(["source", s])

    for r in rows:
        if r["date"] == DAY:
            print("context row:", r)
    print("wrote:", wpath, spath, fpath, sep="\n  ")


if __name__ == "__main__":
    main()
