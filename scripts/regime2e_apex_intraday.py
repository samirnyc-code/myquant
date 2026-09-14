"""Funded-account survival under Apex's CONFIRMED legacy-FULL drawdown model:
INTRADAY trailing on PEAK UNREALIZED balance (from the Legacy Evaluation Rules page:
"the trailing threshold is based on the highest live value during trades").

Account equity = realized + open-trade unrealized, tick by tick. The trailing floor
ratchets to (running peak equity - threshold) in REAL TIME, locks at start+$100 once
peak >= start+threshold+$100. BLOW if equity ever touches the floor.

One-per-day book, real trove ticks. Runs the actual sequential 5-yr path at 1/2/3 ES
for each plan threshold, and reports blow date / deepest cushion / per-year, plus
a trade-level worst-case comparison to the EOD model I ran before.

  python scripts/regime2e_apex_intraday.py
"""
import sys
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5
STOP_MULT = 0.30; STOP_FLOOR_T = 8; GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
RETEST_T = 6; FILL_T = 7; CANCEL_BARS = 6; GOOD_HOURS = {9, 10, 11, 12, 13}
PLANS = [("150K", 5000.0), ("250K", 6500.0), ("300K", 7500.0)]
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime2e_flip_scale_sim import signals_for_day             # noqa: E402


def day_trades(g, tP, tbar, sma20, adr10):
    """one-per-day: first signal whose retest fills; exit at stop(touch) or EOD.
    Returns list with fill_tick, exit_tick, entry, sgn, pnl_pts (net of cost)."""
    stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)
    out = []
    for (jfl, dr, lim) in signals_for_day(g, tP, tbar, sma20, adr10):
        short = dr == "S"
        stop = lim + stop_pts if short else lim - stop_pts
        seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        if len(js):
            exit_off = int(js[0]); ex = stop
        else:
            exit_off = len(seg) - 1; ex = seg[-1]
        pts = (lim - ex) if short else (ex - lim)
        out.append(dict(fill=jfl, exit=jfl + exit_off, entry=lim,
                        sgn=(-1 if short else 1), pts=pts - COST / PT))
        break   # ONE per day
    return out


def extract_trades():
    """ONE tick pass: return per-trade (date, entry, sgn, seg prices, pnl_pts)."""
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None
    trades = []
    for d in dates:
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            continue
        day_hi, day_lo = float(np.max(tP)), float(np.min(tP))
        day_cl, day_op = float(tP[-1]), float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None
        tdy = (prev_range > TREND_MULT * adr_prior) if (adr_prior is not None and prev_range is not None) else None
        if prev_range is not None:
            ranges.append(prev_range)
        if prev_close is not None:
            closes.append(prev_close)
        sma20 = np.mean(closes) if len(closes) == SMA_N else None
        adr10 = np.mean(ranges) if len(ranges) == ADR_N else None
        if not (adr10 is None or sma20 is None or prev_close is None or tdy is None):
            if abs(day_op - prev_close) / prev_close * 100.0 <= GAP_MAX and not tdy:
                for t in day_trades(g, tP, tbar, sma20, adr10):
                    trades.append(dict(date=d, entry=t["entry"], sgn=t["sgn"],
                                       seg=np.asarray(tP[t["fill"]:t["exit"] + 1], float),
                                       pts=t["pts"]))
        prev_close, prev_range = day_cl, day_hi - day_lo
    return trades


def evaluate(trades, size, T):
    realized = 0.0; peak = 0.0; locked = False; blown = None
    min_cush = 1e12; yearly = {}
    for t in trades:
        if blown is not None:
            break
        u = t["sgn"] * (t["seg"] - t["entry"]) * PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        if not locked:
            floor = runpk - T
            lk = np.nonzero(runpk >= T + 100)[0]
            if len(lk):
                floor[lk[0]:] = 100.0
        else:
            floor = np.full(len(eq), 100.0)
        cush = eq - floor
        mc = float(cush.min())
        min_cush = min(min_cush, mc)
        if mc <= 0 and blown is None:
            blown = t["date"]
        peak = float(runpk[-1])
        if peak >= T + 100:
            locked = True
        realized += t["pts"] * PT * size
        yearly[t["date"][:4]] = yearly.get(t["date"][:4], 0.0) + t["pts"] * PT * size
    return dict(blown=blown, min_cush=min_cush, final=realized, yearly=yearly)


def main():
    trades = extract_trades()
    print(f"APEX LEGACY-FULL **INTRADAY** trailing DD (peak unrealized) — one_per_day, "
          f"{len(trades)} trades, real ticks\n")
    print(f"{'plan':>5} {'size':>4} | {'blew?':>18} {'deepest cushion':>16} {'net-to-blow/5yr':>14}")
    for name, T in PLANS:
        for size in (1, 2, 3):
            r = evaluate(trades, size, T)
            st = f"BLOWN {r['blown']}" if r["blown"] else "survives 5yr"
            print(f"{name:>5} {size:>4} | {st:>18} ${r['min_cush']:>+13,.0f} ${r['final']:>+12,.0f}")
        print()
    # detail for the headline case: 150K @ 1 ES
    r = evaluate(trades, 1, 5000.0)
    print("150K @ 1 ES per-year (until blow):")
    print("  " + "  ".join(f"{y}:${v:+,.0f}" for y, v in sorted(r["yearly"].items())))


if __name__ == "__main__":
    main()
