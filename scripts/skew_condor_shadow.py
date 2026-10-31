"""Skew-matched condor — OBSERVATIONAL SHADOW, no orders, ever.

Candidate idea from the 2026-11-01 "wall already blown through" forensics:
`eodic_c`/`openic_c` strike the call the same POINT-distance from center as the
put, but OTM calls carry less premium than OTM puts at equal distance (vol
skew) -- that's why the call side chronically runs thin/zero credit and stands
down far more often than the put side (confirmed: 30 of 35 "broken" events
were calls, all 65-220pt OTM, not real breaches -- see
docs/living/duplicate_fire_incident... no, broken_wall_forensics_20261101.py).

This shadows an ALTERNATIVE call strike for each of the two EM-condors (eod,
open): instead of mirroring the put's point-distance, pick the call strike
whose IB-quoted delta magnitude matches the put's delta magnitude -- i.e.
strike both sides to equal probability, not equal points. Per user decision
(2026-11-01): delta via IB's own option-computation tick (genericTickList
"106", modelGreeks.delta), NOT ThetaData (retired, not in use).

Zero interaction with the real book: never calls placeOrder, never writes to
trades.parquet/marks.csv/any gameplan file. Reads today's gameplan (to know
when eodic_p/openic_p actually fire and at what strike) and IB market data
only. Writes its own file: data/options_sim/skew_condor_shadow/shadow_<date>.json.

Simplification (v1, flagged not hidden): holds to a fixed 14:45 CT time-stop
(matching the real desk's own time-stop convention) rather than mirroring the
real structure's active-close/level-acceptance exit logic. A cleaner
apples-to-apples comparison would mirror that too -- not done yet.

Usage:
  .venv/Scripts/python.exe scripts/skew_condor_shadow.py [--until 14:45]
  .venv/Scripts/python.exe scripts/skew_condor_shadow.py --dry 2026-10-30   # parse-only, no IB
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
OUTDIR = SIM / "skew_condor_shadow"
OUTDIR.mkdir(parents=True, exist_ok=True)
CT = ZoneInfo("America/Chicago")
WING = 25            # same protective-wing width as every other setup on this desk
STRIKE_STEP = 5       # SPXW strike granularity
SEARCH_RANGE = 60     # +/- points around the real EM-condor call strike to search
TIME_STOP = "14:45"   # matches the real desk's own EOD time-stop


def now_ct():
    return dt.datetime.now(CT)


def hhmm(t, ref=None):
    ref = ref or now_ct()
    return ref.replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)


def plan_path(date):
    return SIM / f"gameplan_{date.replace('-', '')}.json"


def load_plan(date):
    p = plan_path(date)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def book_path(date):
    return OUTDIR / f"shadow_{date}.json"


def load_book(date):
    p = book_path(date)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"date": date, "pairs": {}}


def save_book(date, book):
    book_path(date).write_text(json.dumps(book, indent=2), encoding="utf-8")


# ---------- IB helpers (reused patterns from options_trigger_daemon.py) ----------

def get_delta(ib, qualify_fn, exp, strike, right, wait=4):
    """IB's own modelled delta via genericTickList '106' (option computation).
    Read-only market data subscription, cancelled immediately after. None on
    failure (thin/no model greeks at that moment -- caller must handle)."""
    try:
        c = qualify_fn(ib, exp, strike, right)
    except Exception:
        return None
    t = ib.reqMktData(c, "106", snapshot=False)
    ib.sleep(wait)
    delta = None
    try:
        if t.modelGreeks and t.modelGreeks.delta is not None and t.modelGreeks.delta == t.modelGreeks.delta:
            delta = t.modelGreeks.delta
    except Exception:
        pass
    ib.cancelMktData(c)
    return delta


def find_skew_matched_strike(ib, qualify_fn, exp, right, target_abs_delta, center_strike):
    """Search call strikes around `center_strike` (step STRIKE_STEP, +/- SEARCH_RANGE)
    for whichever has |delta| closest to target_abs_delta. One batched IB
    request for the whole window (subscribe all, one sleep, read all, cancel
    all) instead of one round-trip per candidate."""
    candidates = list(range(int(center_strike) - SEARCH_RANGE, int(center_strike) + SEARCH_RANGE + 1, STRIKE_STEP))
    contracts = {}
    for k in candidates:
        try:
            contracts[k] = qualify_fn(ib, exp, k, right)
        except Exception:
            continue
    tickers = {k: ib.reqMktData(c, "106", snapshot=False) for k, c in contracts.items()}
    ib.sleep(5)
    deltas = {}
    for k, t in tickers.items():
        try:
            if t.modelGreeks and t.modelGreeks.delta == t.modelGreeks.delta:
                deltas[k] = t.modelGreeks.delta
        except Exception:
            pass
        ib.cancelMktData(contracts[k])
    if not deltas:
        return None, None
    best_k = min(deltas, key=lambda k: abs(abs(deltas[k]) - target_abs_delta))
    return best_k, deltas[best_k]


def quote_vertical_open(ib, qualify_fn, exp, short_k, long_k, right, wait=6):
    """Marketable-touch net CREDIT to open a short `short_k` / long `long_k`
    vertical: sell short @bid, buy long @ask. Same bid/ask pattern as the real
    daemon's quote_legs(), just 2 legs instead of a combo bag."""
    return _quote_vertical(ib, qualify_fn, exp, short_k, long_k, right,
                            short_side="bid", long_side="ask", wait=wait)


def quote_vertical_close(ib, qualify_fn, exp, short_k, long_k, right, wait=6):
    """Marketable-touch net DEBIT to close the same vertical: buy back the
    short @ask (pay), sell the long @bid (receive)."""
    return _quote_vertical(ib, qualify_fn, exp, short_k, long_k, right,
                            short_side="ask", long_side="bid", wait=wait)


def _quote_vertical(ib, qualify_fn, exp, short_k, long_k, right, short_side, long_side, wait):
    try:
        c_short = qualify_fn(ib, exp, short_k, right)
        c_long = qualify_fn(ib, exp, long_k, right)
    except Exception:
        return None
    t_short = ib.reqMktData(c_short, "", snapshot=False)
    t_long = ib.reqMktData(c_long, "", snapshot=False)
    ib.sleep(wait)
    px_short = getattr(t_short, short_side)
    px_long = getattr(t_long, long_side)
    net = None
    if px_short == px_short and px_long == px_long and px_short is not None and px_long is not None:
        net = round(px_short - px_long, 2)
    ib.cancelMktData(c_short)
    ib.cancelMktData(c_long)
    return net


# ---------- main loop ----------

PAIRS = {"eod": ("eodic_p", "eodic_c"), "open": ("openic_p", "openic_c")}


def process(ib, qualify_fn, date, plan, book):
    exp = plan["date"]
    for anchor, (put_setup, call_setup) in PAIRS.items():
        if anchor in book["pairs"] and book["pairs"][anchor].get("entered"):
            continue  # already shadowed today for this anchor
        put_trig = next((t for t in plan["triggers"] if t.get("setup") == put_setup), None)
        call_trig = next((t for t in plan["triggers"] if t.get("setup") == call_setup), None)
        if not put_trig or not put_trig.get("fired") or not put_trig.get("filled_legs"):
            continue  # the real put hasn't fired yet -- nothing to match against
        put_legs = put_trig["filled_legs"]
        put_short = next(l["strike"] for l in put_legs if l["side"] == "sell")
        real_call_short = (call_trig.get("structure", {}).get("short")
                            if call_trig else None)
        if real_call_short is None:
            continue  # can't anchor the search window without the real call's strike

        put_delta = get_delta(ib, qualify_fn, exp, put_short, "P")
        if put_delta is None:
            print(f"  [skew-shadow] {anchor}: no put delta yet for {put_short}P, retry next poll")
            continue
        target = abs(put_delta)
        matched_k, matched_delta = find_skew_matched_strike(
            ib, qualify_fn, exp, "C", target, real_call_short)
        if matched_k is None:
            print(f"  [skew-shadow] {anchor}: no call delta match found, retry next poll")
            continue
        net = quote_vertical_open(ib, qualify_fn, exp, matched_k, matched_k + WING, "C")

        book["pairs"][anchor] = {
            "entered": True, "entered_at": now_ct().strftime("%H:%M:%S"),
            "put_short": put_short, "put_delta": round(put_delta, 4),
            "real_call_short": real_call_short,
            "real_call_credit": (call_trig or {}).get("fill", {}).get("net"),
            "skew_call_short": matched_k, "skew_call_delta": round(matched_delta, 4),
            "skew_call_long": matched_k + WING, "skew_call_credit": net,
            "exited": False,
        }
        print(f"  [skew-shadow] {anchor}: put {put_short}P delta {put_delta:.3f} -> "
              f"matched call {matched_k}C delta {matched_delta:.3f} (real call was "
              f"{real_call_short}C) | skew credit {net} vs real credit "
              f"{book['pairs'][anchor]['real_call_credit']}")

    save_book(date, book)


def close_open(ib, qualify_fn, exp, book):
    for anchor, rec in book["pairs"].items():
        if not rec.get("entered") or rec.get("exited"):
            continue
        debit = quote_vertical_close(ib, qualify_fn, exp, rec["skew_call_short"], rec["skew_call_long"], "C")
        rec["exited"] = True
        rec["exit_debit_est"] = debit
        if rec.get("skew_call_credit") is not None and debit is not None:
            rec["pnl_shadow"] = round((rec["skew_call_credit"] - debit) * 100, 2)
        print(f"  [skew-shadow] {anchor}: closed, est debit {debit}, "
              f"shadow P&L {rec.get('pnl_shadow')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", help="parse-only on a past date (no IB connection)")
    ap.add_argument("--until", default=TIME_STOP, help="time-stop, CT HH:MM")
    a = ap.parse_args()
    date = a.dry or now_ct().strftime("%Y-%m-%d")

    plan = load_plan(date)
    if not plan:
        print(f"no gameplan for {date} -- nothing to shadow")
        return
    book = load_book(date)

    if a.dry:
        print(f"[dry] gameplan loaded for {date}: "
              f"{len([t for t in plan['triggers'] if t.get('setup') in ('eodic_p', 'openic_p') and t.get('fired')])} "
              f"of 2 put anchors fired. (No IB connection in --dry mode -- parse-only.)")
        return

    import ib_conn
    from options_trigger_daemon import qualify
    ib = ib_conn.connect()
    end = hhmm(a.until)
    try:
        while now_ct() < end:
            try:
                process(ib, qualify, date, plan, book)
            except Exception as e:
                print(f"  [skew-shadow] poll error: {type(e).__name__}: {e}")
            time.sleep(30)
        close_open(ib, qualify, plan["date"], book)
        save_book(date, book)
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
