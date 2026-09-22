"""Final-day capture of MenthorQ `levels-report/{sym}` (S92-MQ, 2026-08-02).

This surface is TODAY-ONLY and is NOT part of the daily `mq_mine.py` archive, so
it has never been persisted. It carries the per-level regime backtest stats MQ
shows on the "Backtest" tile: hold/success rate, come-back rate, and median /
average / worst adverse excursion (low & close) for put_support, call_resistance,
HVL, etc. -- each with a 0DTE variant.

The MenthorQ subscription ends today, so this is the last chance to archive it.
Writes RAW JSON per ticker to data/menthorq/mine/raw/levels_report/<SYM>_<date>.json
and a flat wide CSV to data/menthorq/levels_report_<date>.csv.

Run:  .venv/Scripts/python.exe scripts/mq_levels_report_capture.py
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
MQDIR = ROOT / "data" / "menthorq"
RAW = MQDIR / "mine" / "raw" / "levels_report"
ET = ZoneInfo("America/New_York")

# same universe as mq_mine.py
UNIVERSE = [
    "SPX", "NDX", "RUT",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "ES1!", "NQ1!", "RTY1!", "YM1!",
    "CL1!", "GC1!", "SI1!", "HG1!", "NG1!",
    "6E1!", "6J1!", "6A1!", "6B1!",
    "ZB1!", "ZN1!",
]


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    date = dt.datetime.now(ET).strftime("%Y%m%d")
    mq = MQ()
    rows = []
    ok = fail = 0
    for sym in UNIVERSE:
        try:
            r = mq.levels_report(sym)
            if not r or not isinstance(r, dict):
                print(f"  EMPTY {sym}")
                fail += 1
                continue
            (RAW / f"{sym.replace('!', '')}_{date}.json").write_text(
                json.dumps(r), encoding="utf-8")
            rows.append(r)
            ok += 1
            print(f"  OK    {sym:<6} ({len(r)} fields)")
        except Exception as e:
            print(f"  FAIL  {sym:<6} {type(e).__name__}: {str(e)[:60]}")
            fail += 1

    if rows:
        # union of all keys, ticker/date first
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
        for lead in ("date", "ticker"):
            if lead in keys:
                keys.remove(lead)
                keys.insert(0, lead)
        out = MQDIR / f"levels_report_{date}.csv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"\n{ok} ok / {fail} fail  ->  {out}")
    else:
        print(f"\n{ok} ok / {fail} fail  -- nothing captured")


if __name__ == "__main__":
    main()
