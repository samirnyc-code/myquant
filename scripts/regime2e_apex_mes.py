"""MES-sizing sweep on the Apex legacy 150K (intraday trailing $5,000) — the right
way to fit a trailing DD: size in micros BELOW 1-ES-equiv so the $ drawdown fits.

Official Apex Rithmic fees: MES $1.02 RT, ES $3.98 RT. All-in per MES/trade =
$1.02 comm + 1 MES tick ($1.25) slip = ~$2.27.

Caches the extracted trades (one 6-min tick pass) so sweeps are instant afterwards.
Runs BOTH the legacy INTRADAY $5,000 model and the EOD $4,000 model.

  python scripts/regime2e_apex_mes.py
"""
import pickle
from collections import deque
from pathlib import Path
import numpy as np

TICK = 0.25; PT_ES = 50.0; MES_PT = 5.0
MES_FEE = 1.02 + 1.25          # RT commission + 1 MES-tick slip, per contract per trade
STOP_MULT = 0.30; STOP_FLOOR_T = 8; GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
RETEST_T = 6; FILL_T = 7; CANCEL_BARS = 6; GOOD_HOURS = {9, 10, 11, 12, 13}
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
CACHE = REPO / "reports" / "regime2e" / "apex_mes_trades.pkl"
import sys
sys.path.insert(0, str(REPO / "scripts")); sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime2e_flip_scale_sim import signals_for_day             # noqa: E402


def extract():
    if CACHE.exists():
        return pickle.load(open(CACHE, "rb"))
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None; trades = []
    for d in dates:
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            continue
        day_hi, day_lo = float(np.max(tP)), float(np.min(tP))
        day_cl, day_op = float(tP[-1]), float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None
        tdy = (prev_range > TREND_MULT * adr_prior) if (adr_prior is not None and prev_range is not None) else None
        if prev_range is not None: ranges.append(prev_range)
        if prev_close is not None: closes.append(prev_close)
        sma20 = np.mean(closes) if len(closes) == SMA_N else None
        adr10 = np.mean(ranges) if len(ranges) == ADR_N else None
        if not (adr10 is None or sma20 is None or prev_close is None or tdy is None):
            if abs(day_op - prev_close) / prev_close * 100.0 <= GAP_MAX and not tdy:
                stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)
                for (jfl, dr, lim) in signals_for_day(g, tP, tbar, sma20, adr10):
                    short = dr == "S"; stop = lim + stop_pts if short else lim - stop_pts
                    seg = tP[jfl:]
                    js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                    exit_off = int(js[0]) if len(js) else len(seg) - 1
                    ex = stop if len(js) else seg[-1]
                    trades.append(dict(date=d, entry=lim, sgn=(-1 if short else 1),
                                       seg=np.asarray(seg[:exit_off + 1], float),
                                       gross_pts=float((lim - ex) if short else (ex - lim))))
                    break   # one per day
        prev_close, prev_range = day_cl, day_hi - day_lo
    CACHE.parent.mkdir(parents=True, exist_ok=True); pickle.dump(trades, open(CACHE, "wb"))
    return trades


def sim(trades, mes, T, model):
    """mes contracts ($5/pt). model='intraday' (peak-unrealized ratchet) or 'eod'
    (floor set at each close, fixed intraday, ratchets only at close). Both lock at +T+100."""
    realized = 0.0; peak = 0.0; eod_peak = 0.0; locked = False; blown = None; min_c = 1e12
    prev_date = None
    for t in trades:
        if blown is not None: break
        if model == "eod" and t["date"] != prev_date:
            eod_peak = max(eod_peak, realized)            # yesterday's close set the floor
            prev_date = t["date"]
        u = t["sgn"] * (t["seg"] - t["entry"]) * MES_PT * mes
        eq = realized + u
        if model == "intraday":
            runpk = np.maximum(peak, np.maximum.accumulate(eq))
            floor = np.where(runpk >= T + 100, 100.0, runpk - T)
            peak = float(runpk[-1]); locked = locked or peak >= T + 100
        else:  # eod: floor from highest prior close, fixed through the day
            base = 100.0 if (eod_peak >= T + 100) else (eod_peak - T)
            floor = np.full(len(eq), base)
        cush = float((eq - floor).min()); min_c = min(min_c, cush)
        if cush <= 0: blown = t["date"]
        realized += t["gross_pts"] * MES_PT * mes - MES_FEE * mes
    return blown, min_c, realized


def main():
    trades = extract()
    ds = sorted({t["date"] for t in trades})
    from datetime import date
    y0 = date(*map(int, ds[0].split("-"))); y1 = date(*map(int, ds[-1].split("-")))
    yrs = max((y1 - y0).days, 1) / 365.25       # calendar span, not trade-day count
    print(f"MES sizing on Apex legacy 150K — {len(trades)} trades, MES fee ${MES_FEE:.2f}/c/trade, ~{yrs:.1f}yr\n")
    for model, T, cap, label in [("intraday", 5000.0, 170, "LEGACY 150K intraday $5,000 (max 170 MES)"),
                                 ("eod", 4000.0, 100, "EOD 150K $4,000 (max 100 MES)")]:
        print(f"=== {label} ===")
        print(f"  {'MES':>4} {'=ES':>5} | {'result':>16} {'deepest cush':>13} {'net/yr':>9} {'net 5yr':>10}")
        for mes in [5, 8, 10, 12, 15, 20, 25, 30, 40, 50]:
            if mes > cap: continue
            blown, minc, net = sim(trades, mes, T, model)
            st = f"BLOWN {blown[:7]}" if blown else "survives"
            print(f"  {mes:>4} {mes/10:>5.1f} | {st:>16} ${minc:>+11,.0f} ${net/ (yrs if not blown else 1):>+8,.0f} ${net:>+9,.0f}")
        print()


if __name__ == "__main__":
    main()
