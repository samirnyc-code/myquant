"""Killer-day forensics: 2022-06-09 (Thu) — ECB hawkish surprise + CPI-eve de-risk.

Backtest damage that day: IC condor -2135, ATM-fly -1120, puts-band -940.
Reads the morning-context row(s) from killer_context.csv, attaches the
web-verified event narrative + 08:30-CT-observable signals, and writes a
dated findings CSV under data/options_sim/backtest_full/killerday/.

Local CSVs only (no ThetaData — terminal owned by a bulk job). No commits.
"""
import csv
import os

REPO = r"c:\Users\Admin\myquant"
SRC = os.path.join(REPO, "data", "options_sim", "backtest_full", "killer_context.csv")
OUTDIR = os.path.join(REPO, "data", "options_sim", "backtest_full", "killerday")
OUT = os.path.join(OUTDIR, "killerday_20220609_findings.csv")

WINDOW = ["2022-06-06", "2022-06-07", "2022-06-08", "2022-06-09", "2022-06-10", "2022-06-13"]
TARGET = "2022-06-09"

# Web-verified narrative (sources in findings rows below).
FINDINGS = [
    # (field, value, source)
    ("cause", "ECB Governing Council (scheduled meeting, decision 07:45 ET / 06:45 CT; "
              "Lagarde presser 08:30 ET / 07:30 CT): ended APP net purchases as of Jul 1, "
              "pre-announced 25bp July hike and opened the door to 50bp in September. "
              "Global bond yields jumped (10y bund 1.452% 8-yr high; 10y UST to ~3.07%). "
              "Plus CPI-eve de-risking (May CPI due 06/10 08:30 ET, printed 8.6% vs 8.3% exp) "
              "and Shanghai re-lockdown news (Minhang 2.7M closed management + mass tests in "
              "7 districts, announced Thu). SPX -2.38% to 4017.82, sold off all session, "
              "closed at the low.",
     "ecb.europa.eu mp220609; barchart 8630133; bloomberg 2022-06-09 shanghai"),
    ("overnight", "US futures were UP overnight, erased gains after the 06:45 CT ECB release "
                  "(barchart headline: 'Stocks Erase Overnight Gains on a Hawkish ECB'). "
                  "Eurozone bonds sold off hard; Euro Stoxx fell post-ECB. Shanghai Minhang "
                  "lockdown announced Thursday (overnight US time). 07:30 CT jobless claims "
                  "229k, highest since mid-January. Cash gap only -0.34%, VIX ~flat (23.96, "
                  "chg -0.06).",
     "barchart 8630133; zacks 1936845; killer_context.csv row 2022-06-09"),
    ("prior_days", "Tension visibly building: 06/07 +0.31% after Target's 2nd margin warning; "
                   "06/08 -1.08% close near lows on oil at 3-month high $122, 10y UST back "
                   "above 3.00%, OECD global growth cut to 3.0% from 4.5% — all pre-CPI "
                   "anxiety. Late-May bear-market rally was rolling over.",
     "zacks 1936718/1936845; nasdaq stock-market-news-for-jun-9-2022"),
    ("aftermath", "Continuation, no snap-back: 06/10 CPI 8.6% (40-yr high) SPX -2.91%; "
                  "06/13 -3.88% into official bear market (-21% from high) as WSJ signaled "
                  "75bp; 06/15 FOMC hiked 75bp. 06/09 was day 1 of a ~-10% four-session "
                  "cascade.",
     "spglobal jun-2022 market attributes; cnbc"),
    ("verdict_0830ct", "NOT a pure ambush, but the vol market gave no warning. Knowable by "
                       "08:30 CT: scheduled ECB meeting already delivered hawkish (06:45 CT) "
                       "with Lagarde presser underway; CPI next morning (event-eve); EU bonds/"
                       "stocks selling off; put credit 2.85 vs call 0.35 (8:1 skew = market "
                       "paying up for downside); prior day -1.08% weak close. NOT knowable: "
                       "gap only -0.34%, VIX flat at 23.96 — gap/VIX-chg filters would NOT "
                       "trigger. The -2.38% grind-down (accelerating PM, close at low) was "
                       "an intraday trend day off a quiet-looking open with a premarket-known "
                       "catalyst.",
     "killer_context.csv; barchart 8630133"),
]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    with open(SRC, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["date"] in WINDOW]
    assert any(r["date"] == TARGET for r in rows), "target row missing"

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "field", "value", "source"])
        for r in rows:
            tag = "TARGET" if r["date"] == TARGET else "window"
            w.writerow(["context_row", r["date"] + " (" + tag + ")",
                        "; ".join(f"{k}={v}" for k, v in r.items() if k != "date"),
                        "killer_context.csv"])
        for field, value, source in FINDINGS:
            w.writerow(["narrative", field, value, source])

    print(f"wrote {OUT} ({len(rows)} context rows + {len(FINDINGS)} narrative rows)")
    t = next(r for r in rows if r["date"] == TARGET)
    print("target row:", t)


if __name__ == "__main__":
    main()
