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
    try:
        body = urllib.request.urlopen(q, timeout=15).read().decode("utf-8", "replace")
    except Exception:
        return None
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) < 2 or lines[0].lstrip().startswith("<"):
        return None
    h = [x.strip().strip('"') for x in lines[0].split(",")]
    d = dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))
    b, a = fnum(d.get("bid")), fnum(d.get("ask"))
    return (b, a, d.get("timestamp")) if (b is not None and a is not None and a >= b >= 0) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    a = ap.parse_args()
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
        return tid, {"td_credit_exact": round(credit, 2) if ok else None, "ok": ok,
                     "et_time_used": et_time, "ib_fill_at_ct": t.get("ib_fill_at"),
                     "ib_credit": t.get("ib_credit"), "td_credit_live": t.get("td_credit"),
                     "detail": detail}

    with ThreadPoolExecutor(max_workers=4) as ex:
        res = dict(r for r in ex.map(work, book["trades"].items()) if r[1] is not None)

    out = SHADOW / f"reprice_{a.date}.json"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")

    print(f"{'order':10} {'IBfill(CT)':>10} {'ETsec':>9} {'IBcr':>6} {'liveTD':>7} {'exactTD':>8} {'exactD':>7}")
    for tid, r in sorted(res.items(), key=lambda kv: book["trades"][kv[0]].get("id", "")):
        idn = book["trades"][tid].get("id", "")
        ib = r["ib_credit"]; ex_ = r["td_credit_exact"]; lv = r["td_credit_live"]
        dd = round(ib - ex_, 2) if (ib is not None and ex_ is not None) else None
        print(f"  {idn:10} {str(r['ib_fill_at_ct']):>10} {str(r['et_time_used']):>9} "
              f"{str(ib):>6} {str(lv):>7} {str(ex_):>8} {str(dd):>7}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
