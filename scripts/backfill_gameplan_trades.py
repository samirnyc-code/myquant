"""backfill_gameplan_trades.py — reconstruct a day's MISSED desk entries at the correct
open NBBO, when the auto-desk didn't fire (e.g. gateway/NT down at the open).

READ-ONLY re: the live book. It reads the gameplan's fired triggers + pulls ThetaData at_time
NBBO for each leg at the entry time, computes the marketable-touch credit (SELL short @ bid,
BUY long @ ask — our validated realistic fill, S113), and writes a REPORT only:
    data/options_log/backfill_<date>_reconstruct.json
It does NOT write trades.parquet / live.json — booking into the daemon-managed book is a
separate, explicit step done with the desk owner.

    python scripts/backfill_gameplan_trades.py            # today's gameplan, entry 08:31 CT
    python scripts/backfill_gameplan_trades.py --date 20260921 --entry-ct 08:31
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V3 = "http://127.0.0.1:25503"
ROOT_SYM = "SPXW"


def at_time_nbbo(expiry: str, strike: float, right: str, et_hms: str):
    q = urllib.parse.urlencode({
        "symbol": ROOT_SYM, "expiration": expiry, "strike": f"{float(strike):.3f}",
        "right": right, "start_date": expiry, "end_date": expiry,
        "time_of_day": et_hms, "format": "csv"})
    url = f"{V3}/v3/option/at_time/quote?{q}"
    try:
        raw = urllib.request.urlopen(url, timeout=30).read().decode()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        return {"error": "no data"}
    r = rows[-1]
    return {"bid": float(r["bid"]), "ask": float(r["ask"]),
            "bid_size": r.get("bid_size"), "ask_size": r.get("ask_size"),
            "stamp": r.get("timestamp")}


MULT = 100.0        # SPX index-option multiplier
FEE = 1.63          # $/contract/execution (entry = 2 legs)
MIN_CREDIT = 0.10   # sim's min_credit_abs — sub-floor spreads are NOT taken


def _mid(n):
    return (n["bid"] + n["ask"]) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().strftime("%Y%m%d"))
    ap.add_argument("--entry-ct", default="08:31")   # desk fires at the open
    a = ap.parse_args()

    gp = json.loads((ROOT / "data" / "options_sim" / f"gameplan_{a.date}.json").read_text())
    hh, mm = a.entry_ct.split(":")
    et_entry = f"{int(hh)+1:02d}:{mm}:00"                       # CT -> ET (+1h, Sep)
    et_now = (dt.datetime.now() - dt.timedelta(hours=6)).strftime("%H:%M:%S")  # CEST machine -> ET

    verts = []
    for t in gp.get("triggers", []):
        s = t.get("structure", {})
        if s.get("kind") == "vertical" and "short" in s and "long" in s:
            verts.append((t["id"], t["name"], s["right"], float(s["short"]), float(s["long"])))

    print(f"backfill P&L — {a.date} — entry {a.entry_ct} CT ({et_entry} ET) -> mark now ({et_now} ET) — "
          f"{len(verts)} verticals, SPXW {a.date}")
    print(f"{'trigger':<10}{'structure':<26}{'entry_mid':>10}{'now_mid':>9}{'PnL_mid':>9}{'PnL_worst':>10}  take?")
    cache, out = {}, []
    tot_mid = tot_worst = 0.0
    for tid, name, right, short, long in verts:
        def leg(strike, et):
            k = (right, strike, et)
            if k not in cache:
                cache[k] = at_time_nbbo(a.date, strike, right, et)
            return cache[k]
        se, le = leg(short, et_entry), leg(long, et_entry)     # entry NBBO
        sn, ln = leg(short, et_now), leg(long, et_now)         # current NBBO
        if any("error" in x for x in (se, le, sn, ln)):
            print(f"{tid:<10}{name[:25]:<26} NBBO error");
            out.append({"id": tid, "error": True}); continue
        entry_mid = _mid(se) - _mid(le)                        # credit at combo-mid (sim proxy)
        entry_touch = se["bid"] - le["ask"]                    # worst-case credit
        now_mid = _mid(sn) - _mid(ln)                          # current spread value (to close)
        now_touch_close = sn["ask"] - ln["bid"]               # worst-case cost to close
        take = entry_mid >= MIN_CREDIT                         # sim's min-credit gate
        pnl_mid = (entry_mid - now_mid) * MULT - 2 * FEE       # entry fees only (open position)
        pnl_worst = (entry_touch - now_touch_close) * MULT - 2 * FEE
        if take:
            tot_mid += pnl_mid; tot_worst += pnl_worst
        out.append({"id": tid, "name": name, "entry_mid": round(entry_mid, 2),
                    "now_mid": round(now_mid, 2), "pnl_mid": round(pnl_mid, 2),
                    "pnl_worst": round(pnl_worst, 2), "taken": take})
        print(f"{tid:<10}{name[:25]:<26}{entry_mid:>10.2f}{now_mid:>9.2f}"
              f"{pnl_mid:>9.0f}{pnl_worst:>10.0f}  {'YES' if take else 'no (<0.10)'}")

    print(f"\n  BOUNDED P&L (open, marked to {et_now} ET, taken trades only, 1-lot, incl entry fees):")
    print(f"    central (combo-mid): {tot_mid:+,.0f}")
    print(f"    floor  (worst touch): {tot_worst:+,.0f}")
    print("  central = how the sim actually fills (net combo mid); floor = full-spread-cross worst case.")
    print("  APPROXIMATE — the sim's exact live combo quote was not recorded; not booked.")

    rep = {"date": a.date, "entry_ct": a.entry_ct, "entry_et": et_entry, "mark_et": et_now,
           "verticals": out, "pnl_central_mid": round(tot_mid, 2), "pnl_floor_worst": round(tot_worst, 2),
           "reconstructed_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "note": "READ-ONLY bounded reconstruction; APPROXIMATE (live combo quote not recorded); NOT booked."}
    p = ROOT / "data" / "options_log" / f"backfill_{a.date}_reconstruct.json"
    p.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(f"\nwrote {p} (report only — live book untouched)")


if __name__ == "__main__":
    main()
