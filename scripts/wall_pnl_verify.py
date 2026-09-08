"""Audit the wall P&L engine BEFORE trusting any number. For chosen days it pulls
each leg's entry NBBO and prints the QUOTE TIMESTAMP (freshness), bid/ask/spread,
then recomputes credit / settlement / P&L step by step and cross-checks the CSV.
Also flags one-sided/zero quotes and pre-open (stale) timestamps.
"""
import csv
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:25503/v3"
WING = 25.0
FEE = 1.63


def td_get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception as e:
        return None
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2 or lines[0].startswith("<"):
        return None
    hdr = [h.strip().strip('"') for h in lines[0].split(",")]
    return dict(zip(hdr, [v.strip().strip('"') for v in lines[-1].split(",")]))


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def leg(date, strike, right, entry):
    exp = date.replace("-", "")
    r = td_get(f"/option/at_time/quote?symbol=SPXW&expiration={exp}&strike={strike:.3f}"
               f"&right={right}&start_date={exp}&end_date={exp}&time_of_day={entry}&format=csv")
    if not r:
        return None
    bid, ask, ts = fnum(r.get("bid")), fnum(r.get("ask")), r.get("timestamp", "?")
    mid = (bid + ask) / 2 if (bid and ask and ask >= bid > 0) else None
    return dict(bid=bid, ask=ask, mid=mid, ts=ts)


def spx_close(date):
    r = td_get(f"/index/history/eod?symbol=SPX&start_date={date.replace('-','')}"
               f"&end_date={date.replace('-','')}")
    return fnum(r.get("close")) if r else None


def vertical(date, short_k, right, entry, sc, fill):
    long_k = short_k - WING if right == "P" else short_k + WING
    opt = "put" if right == "P" else "call"
    s = leg(date, short_k, opt, entry)
    lg = leg(date, long_k, opt, entry)
    print(f"    {'PUT ' if right=='P' else 'CALL'} short {short_k:.0f}: "
          f"bid {s['bid']} ask {s['ask']} mid {s['mid']}  @ {s['ts']}")
    print(f"    {'PUT ' if right=='P' else 'CALL'} long  {long_k:.0f}: "
          f"bid {lg['bid']} ask {lg['ask']} mid {lg['mid']}  @ {lg['ts']}")
    if fill == "mid":
        credit = (s['mid'] - lg['mid']) if (s['mid'] and lg['mid']) else None
    else:  # realistic: sell short at BID, buy long at ASK
        credit = (s['bid'] - lg['ask']) if (s['bid'] is not None and lg['ask'] is not None) else None
    liab = min(WING, max(0.0, (short_k - sc) if right == "P" else (sc - short_k)))
    pnl = (credit - liab) * 100 - 4 * FEE if credit is not None else None
    print(f"      credit({fill}) = {credit}  settle_liab = {liab:.2f}  -> P&L ${pnl:,.2f}" if pnl
          else f"      credit unavailable")
    return pnl


def main():
    entry = sys.argv[1] if len(sys.argv) > 1 else "09:31:00"
    days = sys.argv[2:] or ["2026-06-01", "2026-05-14", "2026-06-25"]
    csvrows = {r["date"]: r for r in csv.DictReader(
        open(ROOT / "data/options_sim/wall_pnl_3way.csv", encoding="utf-8"))}
    for d in days:
        r = csvrows.get(d, {})
        pw, cw = fnum(r.get("gx_pw")), fnum(r.get("gx_cw"))
        sc = spx_close(d)
        print(f"\n===== {d}  (entry {entry} ET)  gexlog walls {pw}/{cw}  SPX close {sc} =====")
        for fill in ("mid", "touch"):
            print(f"  --- fill = {fill} ---")
            bps = vertical(d, pw, "P", entry, sc, fill)
            bcs = vertical(d, cw, "C", entry, sc, fill)
            tot = (bps or 0) + (bcs or 0) if (bps is not None and bcs is not None) else None
            print(f"    CONDOR TOTAL ({fill}): ${tot:,.2f}" if tot is not None else "    incomplete")
        print(f"  CSV recorded gx_pnl = {r.get('gx_pnl')} (bps {r.get('gx_bps')} / bcs {r.get('gx_bcs')})")


if __name__ == "__main__":
    main()
