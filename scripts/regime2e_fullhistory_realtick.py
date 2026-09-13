"""FULL-HISTORY real-tick run of the Regime2ESetups indicator spec (v1.1 book).

Replicates the NT8 indicator's mechanics 1:1 in python over the ENTIRE tick
trove (data/ticks_continuous, 2021-06-18 ->), so the 3-month NT sample can be
judged against all available data on the SAME basis:

  signal : detect_entries_causal cnt==2 (S61 second entry), verbatim import
  regime : phase_transitions v4 at the trigger-touch tick (BULL->L / BEAR->S)
  gates  : entry trigger > SMA20 of prior session closes (both sides)
           | skip day after trend day (prior range > 1.6 x prior ADR10)
           | skip |gap| > 0.54% (first tick vs prior session last tick)
           | fill window 09:00-13:59 trove clock
  entry  : retest LIMIT trigger -/+ 6t, must fill within 6 bars of the fire bar
  exit   : stop 0.30 x ADR10 (floor 8t) from entry, else EOD last tick
  costs  : reported GROSS and NET ($5 RT + 1t slip = $17.50/trade, book model)

Same bar/tick construction as regime2e_nt_diff.py (imported). Overlapping
entries all taken (indicator behavior; book pyramids overlapping 2Es).

  python scripts/regime2e_fullhistory_realtick.py [--limit N]
Output: reports/regime2e/fullhistory_trades_<stamp>.csv + stdout metrics.
"""
import sys
import time
from bisect import bisect_right
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5
RETEST_T = 6; CANCEL_BARS = 6; STOP_MULT = 0.30; STOP_FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
GOOD_HOURS = {9, 10, 11, 12, 13}
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def run_day(date, g, tP, tbar, sma20, adr10, skip_day):
    trades = []
    stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)
    trans = phase_transitions(g["High"].values, g["Low"].values, len(g), tP, tbar)
    tr_ix = [i for (i, _) in trans]; tr_md = [m for (_, m) in trans]
    hours = g["DateTime"].dt.hour.values                          # bar END hour
    for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
        if cnt != 2:
            continue
        short = dr == "S"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        reg = tr_md[bisect_right(tr_ix, jf) - 1] if tr_ix else "NEUTRAL"
        if reg != ("BEAR" if short else "BULL"):
            continue
        if not (trig > sma20) or skip_day:
            continue
        lim = trig + RETEST_T * TICK if short else trig - RETEST_T * TICK
        s0 = tP[jf:]
        jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > CANCEL_BARS:
            continue
        # fill-bar clock hour: bar END hour of the fill bar (bar k ends at 08:30+(k+1)*5m)
        fill_hour = int(hours[min(fb2, len(hours) - 1)])
        if fill_hour not in GOOD_HOURS:
            continue
        stop = lim + stop_pts if short else lim - stop_pts
        seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        if len(js):
            ex, outcome = stop, "STOP"
        else:
            ex, outcome = seg[-1], "EOD"
        pts = (lim - ex) if short else (ex - lim)
        trades.append(dict(date=date, yr=int(date[:4]), dir=dr, trig=float(trig),
                           entry=float(lim), exit=float(ex), outcome=outcome,
                           pts=round(float(pts), 2), stop_pts=float(stop_pts)))
    return trades


def metrics(df, label, cost):
    v = df["pts"].values * PT - cost
    w = v[v > 0]; l = v[v <= 0]
    pf = w.sum() / -l.sum() if len(l) and l.sum() < 0 else float("inf")
    eq = pd.Series(v).cumsum(); mdd = float((eq - eq.cummax()).min())
    daily = pd.DataFrame({"d": df["date"].values, "v": v}).groupby("d")["v"].sum()
    sharpe = daily.mean() / daily.std() * (252 ** 0.5) if daily.std() > 0 else float("nan")
    yrs = max((pd.to_datetime(df["date"]).max() - pd.to_datetime(df["date"]).min()).days, 1) / 365.25
    print(f"\n===== {label}  (n={len(v)}, {df['date'].nunique()} days, {yrs:.1f}yr) =====")
    print(f"  net            ${v.sum():+,.0f}   (${v.sum() / yrs:+,.0f}/yr, 1 ES)")
    print(f"  PF             {pf:.2f}")
    print(f"  win rate       {100 * (v > 0).mean():.1f}%   ({len(w)}W / {len(l)}L)")
    print(f"  avg win        ${w.mean():+,.0f}    avg loss ${l.mean():+,.0f}    payoff {abs(w.mean() / l.mean()):.2f}")
    print(f"  expectancy     ${v.mean():+,.0f}/trade")
    print(f"  max drawdown   ${mdd:+,.0f} (trade-equity)")
    print(f"  daily Sharpe   {sharpe:.2f}    trades/yr {len(v) / yrs:.0f}")
    for d_ in ("L", "S"):
        x = v[(df["dir"] == d_).values]
        if len(x):
            pfx = x[x > 0].sum() / -x[x <= 0].sum() if (x <= 0).any() and x[x <= 0].sum() < 0 else float("inf")
            print(f"  {'2EL' if d_ == 'L' else '2ES'}:  n={len(x)}  PF {pfx:.2f}  net ${x.sum():+,.0f}")
    print("  per-year:")
    for y, x in pd.DataFrame({"yr": df["yr"].values, "v": v}).groupby("yr"):
        vv = x["v"].values
        pfy = vv[vv > 0].sum() / -vv[vv <= 0].sum() if (vv <= 0).any() and vv[vv <= 0].sum() < 0 else float("inf")
        print(f"    {int(y)}: ${vv.sum():+9,.0f}  PF {pfy:4.2f}  n={len(vv):4d}  win {100 * (vv > 0).mean():3.0f}%")


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = None; prev_range = None
    all_trades = []; skipped = {"warm": 0, "gap": 0, "tdy": 0, "thin": 0}
    t0 = time.time()
    for i, d in enumerate(dates):
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            skipped["thin"] += 1
            continue
        day_hi = float(np.max(tP)); day_lo = float(np.min(tP))
        day_cl = float(tP[-1]); day_op = float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None      # ADR before prior day added
        if adr_prior is not None and prev_range is not None:
            tdy = prev_range > TREND_MULT * adr_prior
        else:
            tdy = None
        # roll the deques with the PRIOR day before judging today (indicator order)
        if prev_range is not None:
            ranges.append(prev_range)
        if prev_close is not None:
            closes.append(prev_close)
        sma20 = np.mean(closes) if len(closes) == SMA_N else None
        adr10 = np.mean(ranges) if len(ranges) == ADR_N else None
        if adr10 is None or sma20 is None or prev_close is None or tdy is None:
            skipped["warm"] += 1
        else:
            gap = abs(day_op - prev_close) / prev_close * 100.0
            if gap > GAP_MAX:
                skipped["gap"] += 1
            elif tdy:
                skipped["tdy"] += 1
            else:
                all_trades += run_day(d, g, tP, tbar, sma20, adr10, False)
        prev_close = day_cl; prev_range = day_hi - day_lo
        if (i + 1) % 100 == 0:
            print(f"  ... {i + 1}/{len(dates)} days, {len(all_trades)} trades, {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(all_trades)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"fullhistory_trades_{stamp}.csv"
    df.to_csv(out, index=False)
    print(f"\ndays: {len(dates)}  skipped: {skipped}  trades: {len(df)}")
    if len(df):
        metrics(df, "GROSS (no costs)", 0.0)
        metrics(df, "NET ($17.50/trade)", COST)
    print(f"\ntrades csv: {out}")


if __name__ == "__main__":
    main()
