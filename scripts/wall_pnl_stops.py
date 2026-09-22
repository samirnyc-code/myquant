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
ENTRY_HM = "09:31:00"
TIME_STOP_HM = "15:45:00"   # 14:45 CT
FILL = "mid"               # mid = tight-combo proxy (live fills the combo net, ~mid);
#                            cross = leg-by-leg bid/ask (pessimistic FLOOR, double-counts spread)
INTERVAL = "1m"            # 1m | tick   (tick = second-level acceptance, closer to the daemon poll)
_cache: dict = {}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hms(ts: str) -> str:
    # '2026-05-13T09:31:00.980' -> '09:31:00'  (second-resolution key)
    return ts[11:19]


def opt_path(date: str, strike: float, right: str) -> dict:
    """{ 'HH:MM:SS': (bid, ask) } NBBO path of one SPXW option at INTERVAL. Last quote per
    second wins (tick can have many/sec). {} on no-data. Cached per (date,K,right,INTERVAL)."""
    key = (date, round(strike, 3), right, INTERVAL)
    if key in _cache:
        return _cache[key]
    exp = date.replace("-", "")
    url = (f"{BASE}/option/history/quote?symbol=SPXW&expiration={exp}"
           f"&strike={strike:.3f}&right={right}&start_date={exp}&end_date={exp}"
           f"&interval={INTERVAL}&format=csv")
    path: dict = {}
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            rows = list(csv.DictReader(line.decode() for line in r))
        for row in rows:
            b, a = fnum(row.get("bid")), fnum(row.get("ask"))
            if b is not None and a is not None and (b > 0 or a > 0):
                path[_hms(row["timestamp"])] = (b, a)     # last quote in the second wins
    except urllib.error.HTTPError as e:
        if e.code != 472:                     # 472 = no prints; anything else is a real error
            path = {}
    except Exception:
        path = {}
    _cache[key] = path
    return path


def _mid(v):
    return (v[0] + v[1]) / 2.0 if v else None


def _bid(v):
    return v[0] if v else None


def _ask(v):
    return v[1] if v else None


def _secs(hms: str) -> int:
    return int(hms[:2]) * 3600 + int(hms[3:5]) * 60 + int(hms[6:8])


def _at_or_before(path: dict, hms: str):
    """(bid,ask) at hms, else the nearest earlier observation (stale-quote carry)."""
    if hms in path:
        return path[hms]
    prior = [k for k in path if k <= hms]
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
    se0, le0 = _at_or_before(short_p, ENTRY_HM), _at_or_before(long_p, ENTRY_HM)
    if se0 is None or le0 is None:
        return None
    # OPEN the credit spread. cross = sell short@bid / buy long@ask (leg-by-leg FLOOR);
    # mid = net of leg mids (~ the combo net NBBO the live book actually fills).
    credit = (_bid(se0) - _ask(le0)) if FILL == "cross" else (_mid(se0) - _mid(le0))

    # every observed second (union of the three legs) after entry, through the stop —
    # so tick data drives second-level acceptance, 1m data drives minute-level.
    grid = sorted(t for t in (set(short_p) | set(long_p) | set(opp_p))
                  if ENTRY_HM < t <= TIME_STOP_HM)
    call_src = short_p if right == "C" else opp_p    # parity: spot = K + call_mid - put_mid
    put_src = short_p if right == "P" else opp_p
    accept_secs = accept_mins * 60
    beyond_start = None
    exit_hm, reason = TIME_STOP_HM, "time_stop"
    for t in grid:
        cm, pm = _mid(_at_or_before(call_src, t)), _mid(_at_or_before(put_src, t))
        if cm is None or pm is None:
            continue
        spot = short_k + cm - pm
        beyond = spot < short_k if right == "P" else spot > short_k
        if beyond:
            if beyond_start is None:
                beyond_start = t
            if _secs(t) - _secs(beyond_start) >= accept_secs:     # held continuously >= N min
                exit_hm, reason = t, "acceptance"
                break
        else:
            beyond_start = None

    se, le = _at_or_before(short_p, exit_hm), _at_or_before(long_p, exit_hm)
    if se is None or le is None:
        return None
    # CLOSE: cross = buy short@ask / sell long@bid (FLOOR); mid = net of leg mids.
    exit_cost = (_ask(se) - _bid(le)) if FILL == "cross" else (_mid(se) - _mid(le))
    pnl = (credit - exit_cost) * MULT - 4 * FEE
    return {"credit": credit, "exit_hm": exit_hm, "reason": reason,
            "exit_cost": exit_cost, "pnl": pnl}


def _settle_side(credit, short_k, right, sc):
    """Hold-to-settlement P&L for one vertical, SAME cross-fill entry credit."""
    liab = min(WING, max(0.0, (short_k - sc) if right == "P" else (sc - short_k)))
    return (credit - liab) * MULT - 4 * FEE


def run_day_source(row, src, accept_mins):
    pw, cw = fnum(row.get(f"{src}_pw")), fnum(row.get(f"{src}_cw"))
    otm = str(row.get(f"{src}_otm")) == "True"
    sc = fnum(row.get("spx_close"))
    if not otm or pw is None or cw is None or sc is None:
        return None
    bps = stopped_side(row["date"], pw, "P", accept_mins)
    bcs = stopped_side(row["date"], cw, "C", accept_mins)
    if bps is None or bcs is None:
        return None
    stopped = bps["pnl"] + bcs["pnl"]
    settle = _settle_side(bps["credit"], pw, "P", sc) + _settle_side(bcs["credit"], cw, "C", sc)
    return {
        "date": row["date"], "source": src, "pw": pw, "cw": cw,
        "settle_pnl": round(settle, 2), "stopped_pnl": round(stopped, 2),
        "delta": round(stopped - settle, 2),
        "bps_pnl": round(bps["pnl"], 2), "bcs_pnl": round(bcs["pnl"], 2),
        "bps_exit": bps["exit_hm"], "bps_reason": bps["reason"],
        "bcs_exit": bcs["exit_hm"], "bcs_reason": bcs["reason"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="first N days only (smoke-test)")
    ap.add_argument("--accept-mins", type=int, default=10, help="consecutive min beyond short strike")
    ap.add_argument("--fill", choices=["mid", "cross"], default="mid",
                    help="mid = combo-net proxy (default, ~live); cross = leg-by-leg bid/ask FLOOR")
    ap.add_argument("--interval", choices=["1m", "tick"], default="1m",
                    help="tick = second-level acceptance (closer to the daemon poll); heavier pull")
    ap.add_argument("--since", help="only days >= this date YYYY-MM-DD (scoped test)")
    ap.add_argument("--validate", type=int, metavar="N",
                    help="sanity: parity-spot @15:59 vs SPX close, first N days")
    a = ap.parse_args()
    global FILL, INTERVAL
    FILL, INTERVAL = a.fill, a.interval
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
                c, p = _mid(_at_or_before(cp, hm)), _mid(_at_or_before(pp, hm))
                return (cw + c - p) if (c is not None and p is not None) else None
            s1, sc = par("15:59:00"), fnum(row.get("spx_close"))
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
    if a.since:
        rows = [r for r in rows if r["date"] >= a.since]
    if a.limit:
        rows = rows[:a.limit]
    print(f"days={len(rows)}  interval={INTERVAL}  fill={FILL}  accept_mins={a.accept_mins}  "
          f"time_stop={TIME_STOP_HM} ET  (terminal @ {BASE})\n")

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
