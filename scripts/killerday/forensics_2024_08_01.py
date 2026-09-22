"""Killer-day forensics: 2024-08-01 (ISM-shock reversal day, start of the Aug-2024 growth-scare cascade).

Extracts the local backtest evidence (context row, IC rows, fly rows) for 2024-08-01
and writes a dated evidence CSV plus a signals CSV encoding the web-verified
morning-knowable warning signals. Local CSVs only; no ThetaData calls.

Outputs:
  data/options_sim/backtest_full/killerday/forensics_2024-08-01_evidence.csv
  data/options_sim/backtest_full/killerday/forensics_2024-08-01_signals.csv
"""
import csv
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BT = REPO / "data" / "options_sim" / "backtest_full"
OUT = BT / "killerday"
OUT.mkdir(parents=True, exist_ok=True)
DATE = "2024-08-01"


def rows_for(path, date):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return r.fieldnames, [row for row in r if row.get("date") == date]


def main():
    ev_path = OUT / f"forensics_{DATE}_evidence.csv"
    with open(ev_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "record"])
        for name, path in [("killer_context", BT / "killer_context.csv"),
                           ("ic_rows", BT / "rows.csv"),
                           ("fly_rows", BT / "fly_rows.csv")]:
            fields, rows = rows_for(path, DATE)
            for row in rows:
                w.writerow([name, ";".join(f"{k}={row[k]}" for k in fields)])
    print(f"wrote {ev_path}")

    # Web-verified narrative signals (sources: CNBC 8/1/24 recap, investing.com
    # instant-view 8/1/24, Bloomberg jobless-claims 8/1/24, ISM PMI release,
    # CNBC 8/2/24 NFP recap; CNN/JPM FOMC 7/31/24; barchart BOJ/yen 7/31/24).
    signals = [
        ("jobless_claims_249k_spike", "premarket",
         "Initial claims 249k vs 236k exp (7:30 CT release), biggest rise since Aug 2023 - labor-weakness tell out BEFORE entry"),
        ("scheduled_ISM_10ET", "premarket",
         "ISM manufacturing on the calendar for 9:00 CT, 30 min after entry, with claims already soft - known event risk unpriced by the gap"),
        ("boj_hike_yen_surge", "premarket",
         "BOJ hiked 7/31, yen at 4.5-month high - carry-unwind stress building, visible in overnight FX"),
        ("post_FOMC_euphoria_gap", "at-entry",
         "Prior day +1.58% Powell-cut rally, gap +0.28% to new local high, VIX down 1.33 to 16.36 - entries sold into complacency after a vertical up-day"),
        ("put_credit_thin_call_rich", "at-entry",
         "eodic put credit 0.65 vs call 2.9: downside wings priced cheap vs 56.9-pt EM; put side offered almost nothing for the risk"),
        ("ISM_46.8_print", "intraday-only",
         "9:00 CT ISM 46.8 (8-mo low) flipped +0.5% early rally into -2% risk-off; 10y broke below 4%; VIX +4.7%; Nasdaq -3% intraday; SPX closed 5446.68 -1.37%"),
        ("next_day_cascade", "intraday-only",
         "Aug 2 NFP 114k/4.3% (Sahm rule) -1.84%, Aug 5 yen-carry crash - Aug 1 was day one of a 3-day cascade, no snap-back"),
    ]
    sig_path = OUT / f"forensics_{DATE}_signals.csv"
    with open(sig_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["signal", "knowable_at", "note"])
        w.writerows(signals)
    print(f"wrote {sig_path}")


if __name__ == "__main__":
    main()
