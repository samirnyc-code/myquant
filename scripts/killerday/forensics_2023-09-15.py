"""Killer-day forensics extract: 2023-09-15 (triple-witching Friday; UAW strike day 1; TSMC delay report).

Pulls the morning-context row + all backtest trade rows for the day (and the
1-3 days around it) from the local CSVs and writes a dated evidence CSV.
Web findings (verified 2026-09-10, sources in docstring bottom) are embedded
as constant notes so the record is self-contained.

Run: python scripts/killerday/forensics_2023-09-15.py
Output: data/options_sim/backtest_full/killerday/2023-09-15_forensics.csv
"""
import csv
import os

DAY = "2023-09-15"
WINDOW = {"2023-09-12", "2023-09-13", "2023-09-14", "2023-09-15", "2023-09-18", "2023-09-19"}
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BT = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUT_DIR = os.path.join(BT, "killerday")
OUT = os.path.join(OUT_DIR, f"{DAY}_forensics.csv")

WEB_NOTES = [
    ("cause", "SPX -1.22% 4505.10->4450.32; Nasdaq100 -1.75%. Quarterly triple-witching OpEx; "
              "Reuters report TSMC told vendors to delay high-end chip equipment deliveries "
              "(published 02:50-05:54 AM EDT, premarket) hit semis (ASML/AMAT/LRCX); "
              "UAW strike vs all Big-3 began midnight ET; UMich Sept prelim sentiment fell more "
              "than expected at 10:00 ET, selling extended; T-note yields rose."),
    ("overnight", "S&P futures ~-0.1%, Nasdaq futures ~-0.3% premarket (quiet). UAW strike "
                  "headline out overnight; TSMC/Reuters story out 02:50 AM EDT. GM -0.3%, F -1.2% premkt."),
    ("prior_days", "9/13 CPI in-line-core (flat +0.12%); 9/14 +0.84% risk-on ARM IPO +25%, strong "
                   "retail sales, VIX crushed to 12.82 (-0.66, near cycle lows). No visible tension; complacent tape."),
    ("aftermath", "Mon 9/18 +0.07% (no continuation, no snap-back), Tue 9/19 -0.22%, then FOMC 9/20 "
                  "hawkish dots -0.94% and 9/21 bigger break. 9/15 was the front edge of the "
                  "higher-for-longer September slide."),
]


def rows_from(path, datecol="date", keep=None, extra_filter=None):
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r.get(datecol) in (keep or WINDOW):
                if extra_filter is None or extra_filter(r):
                    out.append(r)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    ctx = rows_from(os.path.join(BT, "killer_context.csv"))
    ic = rows_from(os.path.join(BT, "rows.csv"), keep={DAY},
                   extra_filter=lambda r: r.get("method") == "vix252")
    fly = rows_from(os.path.join(BT, "fly_rows.csv"), keep={DAY})

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "key", "value"])
        for r in ctx:
            w.writerow(["context", r["date"], "|".join(f"{k}={v}" for k, v in r.items())])
        for r in ic:
            w.writerow(["ic_trade", r["strat"], "|".join(f"{k}={v}" for k, v in r.items())])
        for r in fly:
            w.writerow(["fly_trade", r["strat"], "|".join(f"{k}={v}" for k, v in r.items())])
        for k, v in WEB_NOTES:
            w.writerow(["web", k, v])
        w.writerow(["verdict", "detectable_by_0830ct",
                    "YES-partial: quiet gap (-0.16%) but three premarket-knowable warnings: "
                    "(1) quarterly triple-witching OpEx on calendar; (2) TSMC delay report + UAW "
                    "strike out hours before entry with semis red premkt; (3) our own entry credits "
                    "screamed skew: eodic put 2.20 vs call 0.05 at same EM distance (fly put 13.0 "
                    "vs call 3.4) with VIX 12.82 near lows = downside priced, premium thin on calls."])
    print(f"wrote {OUT}: ctx={len(ctx)} ic={len(ic)} fly={len(fly)}")


# Sources:
# https://www.marketscreener.com/quote/stock/TAIWAN-SEMICONDUCTOR-MANU-6492349/news/TSMC-tells-vendors-to-delay-chip-equipment-deliveries-sources-44850791/  (02:50 AM EDT)
# https://www.marketscreener.com/quote/stock/TAIWAN-SEMICONDUCTOR-MANU-6492349/news/TSMC-tells-vendors-to-delay-chip-equipment-deliveries-sources-44852024/  (05:54 AM EDT)
# https://www.barchart.com/story/news/20315465/stocks-slump-as-tech-stock-weakness-weighs-on-the-overall-market
# https://www.cnn.com/business/live-news/strike-uaw-stellantis-ford-09-15-23/h_80aa5c3348777a71dff75028fedd19fd
# https://www.kiplinger.com/investing/stocks/stock-market-today-uaw-strike-sends-stocks-lower
# https://www.npr.org/2023/09/15/1199673197/uaw-strike-big-3-automakers
# https://www.nasdaq.com/articles/stock-market-news-for-sep-15-2023  (prior-day 9/14 close context)
# https://www.theregister.com/2023/09/15/tsmc_equipment_delay/
if __name__ == "__main__":
    main()
