"""wall_pnl_stops.py — re-run the 77-day wall backtest with the DESK'S LIVE STOP RULE.

Baseline (wall_pnl_3way.py) held every 0DTE vertical to CASH SETTLEMENT. This adds
the production exit rule (options_trigger_daemon.thesis_broken):
  * LEVEL ACCEPTANCE — close a side when spot holds BEYOND the short strike for
    >= ACCEPT_MINS consecutive minutes (wicks back inside reset the clock).
  * TIME STOP — force-close by 15:45 ET (= 14:45 CT) regardless.
So NOTHING is held to settlement; every side is bought back at the option mid at exit.

Intraday source = ThetaData option 1-min NBBO (SPXW; entitled). SPX index intraday is
NOT entitled (403), so the spot path is derived by PUT-CALL PARITY at the short strike:
  spot(t) = K + call_mid(t) - put_mid(t)     (0DTE, r~0, no intraday div)

Walls per day/source come from data/options_sim/wall_pnl_3way.csv (already computed:
gx/td/mq/fx put/call walls + otm flag + the settle baseline {src}_pnl).

Fees/fills match the baseline: mid-fill, 4*FEE per vertical (entry 2 + exit 2 legs).

Out: data/options_sim/wall_pnl_stops.csv  (per day x source: exit time, accepted?, stopped vs settle)
Run: .venv/Scripts/python.exe scripts/wall_pnl_stops.py [--limit N] [--accept-mins 10]
     (needs the Theta Terminal up at 127.0.0.1:25503)
"""
from __future__ import annotations

import argparse
import csv
import statistics as stat
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
IN_CSV = SIM / "wall_pnl_3way.csv"
OUT_CSV = SIM / "wall_pnl_stops.csv"
BASE = "http://127.0.0.1:25503/v3"
WING, FEE, STEP, MULT = 25.0, 1.63, 5.0, 100
SOURCES = ["gx", "td", "mq", "fx"]
LABEL = {"gx": "gexlog", "td": "ThetaData", "mq": "MenthorQ", "fx": "fixed-offset"}
ENTRY_HM = "09:31"
TIME_STOP_HM = "15:45"      # 14:45 CT
_cache: dict = {}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hm(ts: str) -> str:
    # '2026-05-13T09:31:00.000' -> '09:31'
    return ts[11:16]


def opt_path(date: str, strike: float, right: str) -> dict:
    """{ 'HH:MM': mid } for the 1-min NBBO path of one SPXW option. {} on no-data/err."""
    key = (date, round(strike, 3), right)
    if key in _cache:
        return _cache[key]
    exp = date.replace("-", "")
    url = (f"{BASE}/option/history/quote?symbol=SPXW&expiration={exp}"
           f"&strike={strike:.3f}&right={right}&start_date={exp}&end_date={exp}"
           f"&interval=1m&format=csv")
    path: dict = {}
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            rows = list(csv.DictReader(line.decode() for line in r))
        for row in rows:
            b, a = fnum(row.get("bid")), fnum(row.get("ask"))
            if b is not None and a is not None and (b > 0 or a > 0):
                path[_hm(row["timestamp"])] = (b + a) / 2.0
    except urllib.error.HTTPError as e:
        if e.code != 472:                     # 472 = no prints; anything else is a real error
            path = {}
    except Exception:
        path = {}
    _cache[key] = path
    return path


def _minutes(a: str, b: str):
    """inclusive 'HH:MM' grid from a to b."""
    h, m = int(a[:2]), int(a[3:])
    eh, em = int(b[:2]), int(b[3:])
    out = []
    while (h, m) <= (eh, em):
        out.append(f"{h:02d}:{m:02d}")
        m += 1
        if m == 60:
            h, m = h + 1, 0
    return out


def _at_or_before(path: dict, hm: str):
    """mid at hm, else the nearest earlier minute (stale-quote carry)."""
    if hm in path:
        return path[hm]
    prior = [k for k in path if k <= hm]
    return path[max(prior)] if prior else None


def stopped_side(date, short_k, right, accept_mins):
    """Desk-rule exit P&L for one vertical. Returns dict or None (missing data)."""
    long_k = short_k - WING if right == "P" else short_k + WING
    o = "put" if right == "P" else "call"
    opp = "call" if right == "P" else "put"
    short_p = opt_path(date, short_k, o)
    long_p = opt_path(date, long_k, o)
    opp_p = opt_path(date, short_k, opp)        # for parity spot at the short strike
    if not short_p or not long_p or not opp_p:
        return None
    if ENTRY_HM not in short_p or ENTRY_HM not in long_p:
        return None
    credit = short_p[ENTRY_HM] - long_p[ENTRY_HM]

    grid = _minutes(ENTRY_HM, TIME_STOP_HM)
    run = 0
    exit_hm = TIME_STOP_HM
    reason = "time_stop"
    for hm in grid[1:]:                          # from 09:32; entry minute is the anchor
        # parity spot at the SHORT strike: spot = K + call_mid - put_mid
        cm = _at_or_before(opp_p if right == "P" else short_p, hm)   # call mid @ short_k
        pm = _at_or_before(short_p if right == "P" else opp_p, hm)   # put  mid @ short_k
        if cm is None or pm is None:
            continue
        spot = short_k + cm - pm
        beyond = spot < short_k if right == "P" else spot > short_k
        run = run + 1 if beyond else 0
        if run >= accept_mins:
            exit_hm, reason = hm, "acceptance"
            break

    sm, lm = _at_or_before(short_p, exit_hm), _at_or_before(long_p, exit_hm)
    if sm is None or lm is None:
        return None
    exit_cost = sm - lm
    pnl = (credit - exit_cost) * MULT - 4 * FEE
    return {"credit": credit, "exit_hm": exit_hm, "reason": reason,
            "exit_cost": exit_cost, "pnl": pnl}


def run_day_source(row, src, accept_mins):
    pw, cw = fnum(row.get(f"{src}_pw")), fnum(row.get(f"{src}_cw"))
    otm = str(row.get(f"{src}_otm")) == "True"
    settle = fnum(row.get(f"{src}_pnl"))
    if not otm or pw is None or cw is None:
        return None
    bps = stopped_side(row["date"], pw, "P", accept_mins)
    bcs = stopped_side(row["date"], cw, "C", accept_mins)
    if bps is None or bcs is None:
        return None
    stopped = bps["pnl"] + bcs["pnl"]
    return {
        "date": row["date"], "source": src, "pw": pw, "cw": cw,
        "settle_pnl": settle, "stopped_pnl": round(stopped, 2),
        "delta": round(stopped - settle, 2) if settle is not None else None,
        "bps_pnl": round(bps["pnl"], 2), "bcs_pnl": round(bcs["pnl"], 2),
        "bps_exit": bps["exit_hm"], "bps_reason": bps["reason"],
        "bcs_exit": bcs["exit_hm"], "bcs_reason": bcs["reason"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="first N days only (smoke-test)")
    ap.add_argument("--accept-mins", type=int, default=10, help="consecutive min beyond short strike")
    ap.add_argument("--validate", type=int, metavar="N",
                    help="sanity: parity-spot @09:31 & @15:45 vs SPX close, first N days")
    a = ap.parse_args()
    if a.validate:
        rows = list(csv.DictReader(open(IN_CSV, encoding="utf-8")))[:a.validate]
        errs = []
        print(f"{'date':12}{'K(cw)':>8}{'parity@1559':>13}{'spx_close':>11}{'err@1559':>10}")
        for row in rows:
            cw = fnum(row.get("gx_cw"))
            if cw is None:
                continue
            cp, pp = opt_path(row["date"], cw, "call"), opt_path(row["date"], cw, "put")
            if not cp or not pp:
                print(f"{row['date']:12}{cw:>8.0f}   (no path)"); continue

            def par(hm):
                c, p = _at_or_before(cp, hm), _at_or_before(pp, hm)
                return (cw + c - p) if (c is not None and p is not None) else None
            s1, sc = par("15:59"), fnum(row.get("spx_close"))
            err = (s1 - sc) if (s1 is not None and sc is not None) else None
            if err is not None:
                errs.append(abs(err))
            print(f"{row['date']:12}{cw:>8.0f}{(s1 or 0):>13.1f}{(sc or 0):>11.1f}"
                  f"{(err if err is not None else 0):>10.1f}")
        if errs:
            print(f"\nmean |err| @15:59 = {stat.mean(errs):.2f} pt   max = {max(errs):.1f} pt")
        return 0
    if not IN_CSV.exists():
        print(f"missing {IN_CSV} — run wall_pnl_3way.py first."); return 1
    rows = list(csv.DictReader(open(IN_CSV, encoding="utf-8")))
    if a.limit:
        rows = rows[:a.limit]
    print(f"days={len(rows)}  accept_mins={a.accept_mins}  time_stop={TIME_STOP_HM} ET  (terminal @ {BASE})\n")

    jobs = [(row, src) for row in rows for src in SOURCES]
    out = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(lambda j: run_day_source(*j, a.accept_mins), jobs):
            if res:
                out.append(res)
            if (len(out)) and len(out) % 40 == 0:
                print(f"  ...{len(out)} day-source results")

    if not out:
        print("no results (no OTM day/source with data)."); return 1
    fields = ["date", "source", "pw", "cw", "settle_pnl", "stopped_pnl", "delta",
              "bps_pnl", "bcs_pnl", "bps_exit", "bps_reason", "bcs_exit", "bcs_reason"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    print(f"\n{'source':12}{'n':>4}{'settle $':>12}{'stopped $':>12}{'chg $':>10}"
          f"{'win%':>7}{'acc%':>7}")
    for src in SOURCES:
        rs = [r for r in out if r["source"] == src]
        if not rs:
            continue
        settle = sum(r["settle_pnl"] for r in rs if r["settle_pnl"] is not None)
        stopped = sum(r["stopped_pnl"] for r in rs)
        win = 100 * sum(1 for r in rs if r["stopped_pnl"] > 0) / len(rs)
        acc = 100 * sum(1 for r in rs if "acceptance" in (r["bps_reason"], r["bcs_reason"])) / len(rs)
        print(f"{LABEL[src]:12}{len(rs):>4}{settle:>12,.0f}{stopped:>12,.0f}"
              f"{stopped - settle:>10,.0f}{win:>7.0f}{acc:>7.0f}")
    print(f"\nsaved -> {OUT_CSV.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
