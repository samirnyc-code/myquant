"""Re-price the shadow's entries at each trade's EXACT fill second (fixes the
timing drift from mid-session restarts). Reads the live shadow book for the legs
and IB's fill time, pulls TD's NBBO at that exact ET second (at_time), recomputes
the marketable-touch credit, and writes a SEPARATE file the dashboard merges
(never touches the live book -> no write race).

IB fill time (plan `fill.at`) is CT; options data is ET -> +1h.

  python scripts/td_shadow_reprice.py [--date YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADOW = ROOT / "data/options_sim/shadow_td"
BASE = "http://127.0.0.1:25503/v3"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ct_to_et(hms):
    """desk logs fill.at in CT; ThetaData is ET (+1h)."""
    try:
        t = dt.datetime.strptime(hms, "%H:%M:%S")
        return (t + dt.timedelta(hours=1)).strftime("%H:%M:%S")
    except Exception:
        return None


def nbbo_at(expiry, strike, right, et_day, et_time):
    r_ = "call" if str(right).upper().startswith("C") else "put"
    q = (f"{BASE}/option/at_time/quote?symbol=SPXW&expiration={et_day}&strike={float(strike):.3f}"
         f"&right={r_}&start_date={et_day}&end_date={et_day}&time_of_day={et_time}&format=csv")
    body = None
    for attempt in range(5):
        try:
            body = urllib.request.urlopen(q, timeout=15).read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:                     # terminal rate limit: back off, retry
                import time
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            return None
    if body is None:
        return None
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) < 2 or lines[0].lstrip().startswith("<"):
        return None
    h = [x.strip().strip('"') for x in lines[0].split(",")]
    d = dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))
    b, a = fnum(d.get("bid")), fnum(d.get("ask"))
    return (b, a, d.get("timestamp")) if (b is not None and a is not None and a >= b >= 0) else None


_FC = {}


def _final_close():
    """final SPX close for the reprice date (cached); None until published."""
    if "v" in _FC:
        return _FC["v"]
    day = _FC.get("day")
    u = f"{BASE}/index/history/eod?symbol=SPX&start_date={day}&end_date={day}&format=csv"
    try:
        body = urllib.request.urlopen(u, timeout=15).read().decode("utf-8", "replace")
        lines = [l for l in body.splitlines() if l.strip()]
        h = [x.strip().strip('"') for x in lines[0].split(",")]
        r = [x.strip().strip('"') for x in lines[-1].split(",")]
        v = dict(zip(h, r)).get("close")
        val = float(v) if v not in (None, "", "0.00", "0") else None
    except Exception:
        val = None
    if val is None:
        # TD publishes the index EOD row late evening; until then settle at the
        # SAME close the desk book settles at (options_postmortem.official_close:
        # daily cache -> live Yahoo chart API) so both sides of the compare use
        # one number. yahoo_spx() is wrong here — it drops TODAY's row by design.
        try:
            import sys as _s
            _s.path.insert(0, str(Path(__file__).resolve().parent))
            from options_postmortem import official_close
            val = official_close(day)
        except Exception:
            pass
    if val is not None:
        _FC["v"] = val          # only cache success (429s must not poison the day)
    return val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    _FC["day"] = a.date.replace("-", "")
    book = json.loads((SHADOW / f"shadow_book_{a.date}.json").read_text(encoding="utf-8"))

    def work(item):
        tid, t = item
        legs = t.get("legs") or []
        et_time = ct_to_et(str(t.get("ib_fill_at") or ""))
        if not et_time or not legs:
            return tid, None
        exp = str(legs[0]["expiry"]).replace("-", "")
        credit, ok, detail = 0.0, True, []
        for lg in legs:
            q = nbbo_at(exp, lg["strike"], lg["right"], exp, et_time)
            if q is None:
                ok = False
                detail.append({"strike": lg["strike"], "right": lg["right"], "td": None})
                continue
            b, a_, ts = q
            px = b if lg["side"] == "sell" else a_       # touch: sell@bid, buy@ask
            credit += (px if lg["side"] == "sell" else -px) * lg.get("qty", 1)
            detail.append({"side": lg["side"], "strike": lg["strike"], "right": lg["right"],
                           "bid": b, "ask": a_, "px": px, "quote_ts": ts})
        rec = {"td_credit_exact": round(credit, 2) if ok else None, "ok": ok,
               "et_time_used": et_time, "ib_fill_at_ct": t.get("ib_fill_at"),
               "ib_credit": t.get("ib_credit"), "td_credit_live": t.get("td_credit"),
               "detail": detail}
        # EXPIRY settle: trade never exited and the session is over -> settle each
        # leg at intrinsic vs the FINAL SPX close (same rule as the backtest engine).
        if not t.get("exited") and _final_close() is not None:
            fc = _final_close()
            val = 0.0
            for lg in legs:
                itm = max(0.0, lg["strike"] - fc) if lg["right"] == "P" else max(0.0, fc - lg["strike"])
                val += (itm if lg["side"] == "sell" else -itm) * lg.get("qty", 1)
            rec["td_exit_debit_exact"] = round(val, 2)
            rec["et_exit_time_used"] = "settle"
            if ok:
                ncon = sum(l.get("qty", 1) for l in legs)
                rec["td_pnl_exact"] = round((credit - val) * 100 - ncon * 1.63, 2)
                ibc = t.get("ib_credit")
                rec["ib_pnl"] = round((ibc - val) * 100 - ncon * 1.63, 2) if ibc is not None else None
        # EXIT reprice: at the exact close time, marketable-touch to CLOSE the spread
        # (buy back the short @ask, sell the long @bid) — the way the backtest prices a stop.
        if t.get("exited") and t.get("ib_exit_at"):
            xet = ct_to_et(str(t.get("ib_exit_at")))
            debit, xok = 0.0, True
            for lg in legs:
                q = nbbo_at(exp, lg["strike"], lg["right"], exp, xet)
                if q is None:
                    xok = False; continue
                b, a_, _ = q
                px = a_ if lg["side"] == "sell" else b   # buy back short @ask, sell long @bid
                debit += (px if lg["side"] == "sell" else -px) * lg.get("qty", 1)
            rec["td_exit_debit_exact"] = round(debit, 2) if xok else None
            rec["et_exit_time_used"] = xet
            rec["ib_exit_cost"] = t.get("ib_exit_cost")
            if ok and xok:
                nleg = len(legs)
                rec["td_pnl_exact"] = round((credit - debit) * 100 - 2 * nleg * 1.63, 2)
                ibc, ibx = t.get("ib_credit"), t.get("ib_exit_cost")
                rec["ib_pnl"] = round((ibc - ibx) * 100 - 2 * nleg * 1.63, 2) if (ibc is not None and ibx is not None) else None
        return tid, rec

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = dict(r for r in ex.map(work, book["trades"].items()) if r[1] is not None)

    out = SHADOW / f"reprice_{a.date}.json"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print("ENTRY (exact fill second):")
    print(f"  {'order':10} {'IBcr':>6} {'exactTD':>8} {'d':>6}")
    for tid, r in sorted(res.items(), key=lambda kv: book["trades"][kv[0]].get("id", "")):
        idn = book["trades"][tid].get("id", "")
        ib = r["ib_credit"]; ex_ = r["td_credit_exact"]
        dd = round(ib - ex_, 2) if (ib is not None and ex_ is not None) else None
        print(f"  {idn:10} {str(ib):>6} {str(ex_):>8} {str(dd):>6}")
    print("\nEXIT + P&L (exact close second) — CLOSED trades:")
    print(f"  {'order':10} {'IBexit':>7} {'exactTDexit':>12} {'IB_PnL':>8} {'exactTD_PnL':>12}")
    for tid, r in sorted(res.items(), key=lambda kv: book["trades"][kv[0]].get("id", "")):
        if "td_exit_debit_exact" not in r:
            continue
        idn = book["trades"][tid].get("id", "")
        print(f"  {idn:10} {str(r.get('ib_exit_cost')):>7} {str(r.get('td_exit_debit_exact')):>12} "
              f"{str(r.get('ib_pnl')):>8} {str(r.get('td_pnl_exact')):>12}")
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
