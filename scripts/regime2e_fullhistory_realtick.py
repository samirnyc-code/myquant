"""FULL-HISTORY real-tick run of the Regime2ESetups indicator spec (v1.1 book).

Replicates the NT8 indicator's mechanics over the ENTIRE tick trove
(data/ticks_continuous, 2021-06-18 ->), with REALISTIC limit fills:

  signal : detect_entries_causal cnt==2 (S61 second entry), verbatim import
  regime : phase_transitions v4 at the trigger-touch tick (BULL->L / BEAR->S)
  gates  : entry trigger > SMA20 of prior session closes (both sides)
           | skip day after trend day (prior range > 1.6 x prior ADR10)
           | skip |gap| > 0.54%  | fill window 09:00-13:59 trove clock
  ENTRY (fill realism - NO touch-fills on limits):
           a resting retest LIMIT only fills when price TRADES THROUGH it by 1t.
           Two configs are run:
             A) pb=5t : limit at trig-/+5t, filled only when trig-/+6t is reached
             B) pb=6t : limit at trig-/+6t, filled only when trig-/+7t is reached
           entry price = the limit price (you get your limit once traded through).
           unfilled after 6 bars = no trade.
  STOP   : 0.30 x ADR10 (8t floor) from entry, fills ON TOUCH (conservative).
  EXIT   : else EOD last tick.
  costs  : reported GROSS and NET ($5 RT + 1t slip = $17.50/trade).

  python scripts/regime2e_fullhistory_realtick.py [--limit N]
Output: reports/regime2e/fullhistory_<cfg>_<stamp>.csv + stdout metrics per config.
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
CANCEL_BARS = 6; STOP_MULT = 0.30; STOP_FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
GOOD_HOURS = {9, 10, 11, 12, 13}
# (name, pb ticks = limit distance, fill ticks = trade-through level required)
CONFIGS = [("A_pb5_through6", 5, 6), ("B_pb6_through7", 6, 7)]
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def run_day(date, g, tP, tbar, sma20, adr10, pb_t, fill_t):
    """One day, one fill-config. Limit fills only on trade-through; stops on touch."""
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
        if not (trig > sma20):
            continue
        # limit placement (pb_t back) and the trade-THROUGH level that confirms a fill
        lim = trig + pb_t * TICK if short else trig - pb_t * TICK
        thru = trig + fill_t * TICK if short else trig - fill_t * TICK
        s0 = tP[jf:]
        jl = np.nonzero(s0 >= thru)[0] if short else np.nonzero(s0 <= thru)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > CANCEL_BARS:
            continue
        fill_hour = int(hours[min(fb2, len(hours) - 1)])
        if fill_hour not in GOOD_HOURS:
            continue
        stop = lim + stop_pts if short else lim - stop_pts
        seg = tP[jfl:]
        js = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]  # touch
        if len(js):
            exit_off = int(js[0]); ex, outcome = stop, "STOP"
        else:
            exit_off = len(seg) - 1; ex, outcome = seg[-1], "EOD"
        pts = (lim - ex) if short else (ex - lim)
        held = seg[:exit_off + 1]
        mae = float(lim - held.min()) if not short else float(held.max() - lim)
        trades.append(dict(date=date, yr=int(date[:4]), dir=dr, trig=float(trig),
                           entry=float(lim), exit=float(ex), outcome=outcome,
                           pts=round(float(pts), 2), mae_pts=round(mae, 2),
                           stop_pts=float(stop_pts),
                           fill_tick=int(jfl), exit_tick=int(jfl + exit_off),
                           sgn=(-1 if short else 1)))
    intraday = intraday_path(trades, tP)
    return trades, intraday


def intraday_path(trades, tP):
    """Piecewise equity extremes (pts, relative to day start) with overlaps marked."""
    intraday = [0.0]
    if not trades:
        return intraday
    ev_at = {}
    for k, t in enumerate(trades):
        ev_at.setdefault(t["fill_tick"], []).append((1, k))
        ev_at.setdefault(t["exit_tick"], []).append((0, k))
    bounds = sorted(ev_at)
    realized = 0.0; openset = {}
    for bi, tk in enumerate(bounds):
        for kind, k in ev_at[tk]:
            if kind == 1:
                openset[k] = trades[k]
            else:
                t = openset.pop(k, None)
                if t is not None:
                    realized += t["pts"]
        nxt = bounds[bi + 1] if bi + 1 < len(bounds) else len(tP)
        if not openset or nxt <= tk:
            intraday.append(realized); continue
        net = sum(t["sgn"] for t in openset.values())
        const = sum(t["sgn"] * t["entry"] for t in openset.values())
        pr = tP[tk:nxt]
        e_lo = realized + net * float(pr.min()) - const
        e_hi = realized + net * float(pr.max()) - const
        intraday.append(min(e_lo, e_hi)); intraday.append(max(e_lo, e_hi))
    return intraday


def metrics(df, eq_series, label, cost):
    v = df["pts"].values * PT - cost
    w = v[v > 0]; l = v[v <= 0]
    pf = w.sum() / -l.sum() if len(l) and l.sum() < 0 else float("inf")
    eq = pd.Series(v).cumsum(); mdd = float((eq - eq.cummax()).min())
    daily = pd.DataFrame({"d": df["date"].values, "v": v}).groupby("d")["v"].sum()
    sharpe = daily.mean() / daily.std() * (252 ** 0.5) if daily.std() > 0 else float("nan")
    yrs = max((pd.to_datetime(df["date"]).max() - pd.to_datetime(df["date"]).min()).days, 1) / 365.25
    print(f"\n----- {label}  (n={len(v)}, {df['date'].nunique()} days, {yrs:.1f}yr) -----")
    print(f"  net            ${v.sum():+,.0f}   (${v.sum() / yrs:+,.0f}/yr, 1 ES)")
    print(f"  PF             {pf:.2f}")
    print(f"  win rate       {100 * (v > 0).mean():.1f}%   ({len(w)}W / {len(l)}L)")
    print(f"  avg win        ${w.mean():+,.0f}    avg loss ${l.mean():+,.0f}    payoff {abs(w.mean() / l.mean()):.2f}")
    print(f"  expectancy     ${v.mean():+,.0f}/trade")
    print(f"  closed-eq maxDD${mdd:+,.0f}")
    if eq_series is not None:
        es = np.array(eq_series) - cost / PT * 0  # eq_series is gross pts*PT; show gross intraday
        es = np.array(eq_series)
        idd = float((es - np.maximum.accumulate(es)).min())
        print(f"  intraday maxDD ${idd:+,.0f}  (open positions marked, GROSS)")
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


def mae_block(df):
    mae = df["mae_pts"].values * PT
    winmae = df.loc[df.pts > 0, "mae_pts"].values * PT
    print(f"  per-trade MAE  avg ${mae.mean():,.0f}  median ${np.median(mae):,.0f}  worst ${mae.max():,.0f}")
    print(f"  MAE on WINNERS avg ${winmae.mean():,.0f}  worst ${winmae.max():,.0f}")


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = None; prev_range = None
    acc = {name: {"trades": [], "eq": [0.0], "eqv": 0.0} for name, _, _ in CONFIGS}
    skipped = {"warm": 0, "gap": 0, "tdy": 0, "thin": 0}
    t0 = time.time()
    for i, d in enumerate(dates):
        g, tP, tbar = day_frames(d)
        if g is None or len(g) < 30:
            skipped["thin"] += 1
            continue
        day_hi = float(np.max(tP)); day_lo = float(np.min(tP))
        day_cl = float(tP[-1]); day_op = float(tP[0])
        adr_prior = np.mean(ranges) if len(ranges) == ADR_N else None
        tdy = (prev_range > TREND_MULT * adr_prior) if (adr_prior is not None and prev_range is not None) else None
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
                for name, pb_t, fill_t in CONFIGS:
                    daytr, intraday = run_day(d, g, tP, tbar, sma20, adr10, pb_t, fill_t)
                    A = acc[name]
                    A["trades"] += daytr
                    base = A["eqv"]
                    for vv in intraday:
                        A["eq"].append(base + vv * PT)
                    A["eqv"] += sum(t["pts"] for t in daytr) * PT
        prev_close = day_cl; prev_range = day_hi - day_lo
        if (i + 1) % 200 == 0:
            print(f"  ... {i + 1}/{len(dates)} days, {time.time() - t0:.0f}s", flush=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"\ndays: {len(dates)}  skipped: {skipped}")
    for name, pb_t, fill_t in CONFIGS:
        A = acc[name]
        df = pd.DataFrame(A["trades"])
        df.to_csv(OUTDIR / f"fullhistory_{name}_{stamp}.csv", index=False)
        print("\n" + "=" * 70)
        print(f"CONFIG {name}:  limit {pb_t}t back from trigger, fills only when "
              f"price trades through to {fill_t}t (stops on touch)")
        print("=" * 70)
        if not len(df):
            print("  no trades"); continue
        metrics(df, A["eq"], "GROSS (no costs)", 0.0)
        metrics(df, A["eq"], "NET ($17.50/trade)", COST)
        print("\n  --- intraday risk ---")
        mae_block(df)
        print(f"  max concurrent open trades: {_max_concurrent(df)}")
    print(f"\ncsvs in {OUTDIR}")


def _max_concurrent(df):
    evs = []
    for t in df.itertuples():
        evs.append((t.date, t.fill_tick, 1)); evs.append((t.date, t.exit_tick, -1))
    evs.sort()
    cur = mx = 0
    for _, _, delta in evs:
        cur += delta; mx = max(mx, cur)
    return mx


if __name__ == "__main__":
    main()
