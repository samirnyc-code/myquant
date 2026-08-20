"""feed_watch.py — passively confirm the realtime OPRA feed STAYS live through the
session close, without probing IB (a probe is itself a connection that can disturb
the shared paper feed). The only signal used is the 0DTE chain recorder's row
count: its realtime-guard writes a row ONLY when IB returns realtime, so a growing
file == realtime is flowing. A flat file across a sample == delayed/stalled.

Samples every 90s until the CT stop time, appends a dated CSV, prints each line so
the result is visible inline.

    python scripts/feed_watch.py               # until 15:05 CT
    python scripts/feed_watch.py --stop 15:05
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")


def ct_now():
    return dt.datetime.now(CT)


def chain_rows(date):
    f = SIM / f"chain_{date}.csv"
    if not f.exists():
        return None
    try:
        with f.open("rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return None


def live_state():
    f = SIM / "live.json"
    try:
        d = json.loads(f.read_text())
        return d.get("state"), d.get("spx"), d.get("ts_et")
    except Exception:
        return None, None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", default="15:05", help="CT HH:MM to stop")
    ap.add_argument("--every", type=int, default=90)
    a = ap.parse_args()
    hh, mm = map(int, a.stop.split(":"))

    date = ct_now().strftime("%Y%m%d")
    out = SIM / f"feed_watch_{date}.csv"
    new = not out.exists()
    log = out.open("a", newline="")
    w = csv.writer(log)
    if new:
        w.writerow(["ct_time", "chain_rows", "delta", "verdict", "live_state", "spx", "live_ts"])

    prev = chain_rows(date)
    print(f"feed_watch: baseline {prev} rows @ {ct_now():%H:%M:%S} CT, stop {a.stop} CT")
    live_samples = 0
    total = 0
    while True:
        now = ct_now()
        if (now.hour, now.minute) >= (hh, mm):
            break
        time.sleep(a.every)
        now = ct_now()
        cur = chain_rows(date)
        delta = (cur - prev) if (cur is not None and prev is not None) else None
        verdict = "LIVE" if (delta or 0) > 0 else "flat/delayed"
        st, spx, lts = live_state()
        w.writerow([now.strftime("%H:%M:%S"), cur, delta, verdict, st, spx, lts])
        log.flush()
        print(f"  {now:%H:%M:%S} CT | rows {cur} (+{delta}) | {verdict} | live={st} spx={spx}")
        total += 1
        if (delta or 0) > 0:
            live_samples += 1
        prev = cur

    pct = (100 * live_samples / total) if total else 0
    print(f"DONE @ {ct_now():%H:%M:%S} CT — {live_samples}/{total} samples LIVE ({pct:.0f}%)  -> {out.relative_to(ROOT)}")
    log.close()


if __name__ == "__main__":
    main()
