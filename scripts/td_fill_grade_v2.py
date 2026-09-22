"""Fill-grading v2 — grade each IB fill against its WHOLE 1-second NBBO window, not
one frozen quote (ThetaData suggestion #1, 2026-09-08).

IB exec time is to the second; 0DTE NBBO updates ~150-300x/sec, so grading a fill
against the single at_time quote produces false 'below-zero' / 'through-the-book'
outliers. Here we pull history/quote?interval=tick for [HH:MM:SS.000 .. .999] per fill
and grade against the best/worst touch IN that second:
  * a SELL is achievable if our price <= the HIGHEST bid in the second
  * a BUY  is achievable if our price >= the LOWEST  ask in the second
We compare v1 (single at_time quote) vs v2 (window) and count how many of the
~54 anomalies reclassify to achievable.

Input : data/thetadata/at_time_results_*.csv (518 fills, ET timestamps + IB fill px)
Output: data/thetadata/fill_grade_v2_<date>.csv + a reclassification summary.
"""
import argparse
import csv
import glob
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TD = ROOT / "data/thetadata"
BASE = "http://127.0.0.1:25503/v3"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def tick_window(expiry, strike, right, et_hms):
    """All NBBO ticks in the one-second window [et.000 .. et.999]. Returns dict of
    min/max bid/ask + n, or None."""
    r_ = "call" if str(right).upper().startswith("C") else "put"
    day = str(expiry)
    q = (f"{BASE}/option/history/quote?symbol=SPXW&expiration={day}"
         f"&strike={float(strike):.3f}&right={r_}"
         f"&start_date={day}&end_date={day}"
         f"&start_time={et_hms}.000&end_time={et_hms}.999&interval=tick&format=csv")
    try:
        body = urllib.request.urlopen(q, timeout=20).read().decode("utf-8", "replace")
    except Exception:
        return None
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) < 2 or lines[0].lstrip().startswith("<"):
        return None
    h = [x.strip().strip('"') for x in lines[0].split(",")]
    bi, ai = (h.index("bid") if "bid" in h else None), (h.index("ask") if "ask" in h else None)
    if bi is None or ai is None:
        return None
    bids, asks = [], []
    for ln in lines[1:]:
        v = [x.strip().strip('"') for x in ln.split(",")]
        b, a = fnum(v[bi]), fnum(v[ai])
        if b is not None and b > 0:
            bids.append(b)
        if a is not None and a > 0:
            asks.append(a)
    if not bids or not asks:
        return None
    return dict(min_bid=min(bids), max_bid=max(bids), min_ask=min(asks),
                max_ask=max(asks), n=len(lines) - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=None)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    src = a.src or sorted(glob.glob(str(TD / "at_time_results_*.csv")))[-1]
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    if a.limit:
        rows = rows[:a.limit]
    print(f"grading {len(rows)} fills from {Path(src).name} against their 1-second windows")

    def work(r):
        exp = str(r["expiry"]).replace("-", "")
        px = fnum(r["our_fill_price"])
        side = r["side_action"]        # SELL (receive) / BUY (pay)
        w = tick_window(exp, r["strike"], r["right"], r["time_of_day_et"])
        # v1: single at_time quote from the S113 pull
        b1, a1 = fnum(r.get("bid")), fnum(r.get("ask"))
        v1_anom = None
        if px is not None and b1 is not None and a1 is not None:
            v1_anom = (px < b1 - 1e-9) if side == "SELL" else (px > a1 + 1e-9)
        out = {**{k: r[k] for k in ("trade_id", "strategy", "event", "side_action",
                                    "expiry", "strike", "right", "time_of_day_et")},
               "fill": px, "v1_bid": b1, "v1_ask": a1, "v1_anomaly": v1_anom}
        if w:
            out.update(win_min_bid=w["min_bid"], win_max_bid=w["max_bid"],
                       win_min_ask=w["min_ask"], win_max_ask=w["max_ask"], win_n=w["n"])
            if px is not None:
                out["v2_achievable"] = (px <= w["max_bid"] + 1e-9) if side == "SELL" \
                    else (px >= w["min_ask"] - 1e-9)
        return out

    with ThreadPoolExecutor(max_workers=4) as ex:
        graded = list(ex.map(work, rows))

    out = TD / "fill_grade_v2.csv"
    cols = ["trade_id", "strategy", "event", "side_action", "expiry", "strike", "right",
            "time_of_day_et", "fill", "v1_bid", "v1_ask", "v1_anomaly",
            "win_min_bid", "win_max_bid", "win_min_ask", "win_max_ask", "win_n", "v2_achievable"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(graded)

    n = len(graded)
    win_ok = sum(1 for g in graded if g.get("win_n"))
    anom = [g for g in graded if g.get("v1_anomaly")]
    anom_fixed = [g for g in anom if g.get("v2_achievable")]
    still = [g for g in anom if g.get("v2_achievable") is False]
    v2_ach = sum(1 for g in graded if g.get("v2_achievable"))
    v2_ach_of = sum(1 for g in graded if g.get("v2_achievable") is not None)
    med_n = sorted(g["win_n"] for g in graded if g.get("win_n"))
    print(f"\nwindow pulled for {win_ok}/{n} fills; median quotes/second: "
          f"{med_n[len(med_n)//2] if med_n else '—'}")
    print(f"v1 anomalies (below-bid SELL / above-ask BUY vs single quote): {len(anom)}")
    print(f"  -> reclassified ACHIEVABLE against the 1s window: {len(anom_fixed)}/{len(anom)}")
    print(f"  -> still not achievable in the whole second: {len(still)}")
    if still:
        print("     residual (genuinely through the book):")
        for g in still[:10]:
            print(f"       {g['trade_id']} {g['strategy']} {g['side_action']} {g['strike']}{g['right']} "
                  f"fill {g['fill']} vs window bid[{g.get('win_min_bid')},{g.get('win_max_bid')}] "
                  f"ask[{g.get('win_min_ask')},{g.get('win_max_ask')}]")
    print(f"\noverall achievable-in-window: {v2_ach}/{v2_ach_of}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
