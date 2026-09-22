"""2E book, SINGLE-POSITION FLIP mode + MES contract-scaling on the prop account.

Difference from the stacking book (regime2e_fullhistory_realtick.py):
  - hold at most ONE position (size contracts, same dir). A same-direction 2E
    while in a trade is IGNORED (no pyramiding). An OPPOSITE 2E while in a trade
    REVERSES (close at the flip price, open opposite). Exits: stop (touch),
    reverse, or EOD (15:00 CT flat). Real trove ticks, trade-through limit fills.

Prop account (from memory prop_account_terms):
  - instrument MES = $5 / point (NOT ES $50). max 15 MES.
  - $4,500 trailing drawdown, EOD-measured, FREEZES at BE (start balance):
      floor = min(hwm_EOD, start + 4500) - 4500
      -> trails hwm-4500 until you've banked +4500, then locks at start forever.
      account is blown if EOD equity <= floor.
  - cost model: $5 RT + 1 MES tick ($1.25) slip = $6.25 / contract / trade.

Contract scaling: size = min(15, base + floor(banked_profit / step)), evaluated
on the PRIOR EOD equity (size can't change intraday). Sweeps step + base and
reports whether the single historical path survives, final equity, max EOD DD.

  python scripts/regime2e_flip_scale_sim.py [--limit N]
Output: reports/regime2e/flip_trades_<stamp>.csv + stdout.
"""
import sys
import time
from bisect import bisect_right
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

TICK = 0.25
MES_PT = 5.0                 # $ per point per MES contract
MES_COST = 6.25             # $5 RT + 1 tick ($1.25) slip, per contract per trade
DD = 4500.0
STOP_MULT = 0.30; STOP_FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
GOOD_HOURS = {9, 10, 11, 12, 13}
PB_T, FILL_T, CANCEL_BARS = 6, 7, 6      # config B fills (limit 6t, trade-through 7t)
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def signals_for_day(g, tP, tbar, sma20, adr10):
    """Gate-passing 2E entry candidates: (fill_tick, dir, entry_px)."""
    out = []
    trans = phase_transitions(g["High"].values, g["Low"].values, len(g), tP, tbar)
    tr_ix = [i for (i, _) in trans]; tr_md = [m for (_, m) in trans]
    hours = g["DateTime"].dt.hour.values
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
        if reg != ("BEAR" if short else "BULL") or not (trig > sma20):
            continue
        lim = trig + PB_T * TICK if short else trig - PB_T * TICK
        thru = trig + FILL_T * TICK if short else trig - FILL_T * TICK
        s0 = tP[jf:]
        jl = np.nonzero(s0 >= thru)[0] if short else np.nonzero(s0 <= thru)[0]
        if not len(jl):
            continue
        jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
        if fb2 - fb > CANCEL_BARS or int(hours[min(fb2, len(hours) - 1)]) not in GOOD_HOURS:
            continue
        out.append((jfl, dr, float(lim)))
    out.sort()
    return out


def flip_day(date, sigs, tP, stop_pts):
    """Single-position flip sim over the day's tick path. Returns closed trades (pts)."""
    trades = []; pos = None; i = 0; n = len(sigs)

    def stop_of(dr, epx):
        return epx + stop_pts if dr == "S" else epx - stop_pts

    def close(exit_px, outcome):
        pts = (pos["epx"] - exit_px) if pos["dir"] == "S" else (exit_px - pos["epx"])
        trades.append(dict(date=date, dir=pos["dir"], entry=pos["epx"],
                           exit=float(exit_px), pts=round(float(pts), 2), outcome=outcome))

    while i < n:
        ft, dr, epx = sigs[i]
        if pos is None:
            pos = dict(dir=dr, epx=epx, stop=stop_of(dr, epx), tick=ft); i += 1; continue
        seg = tP[pos["tick"]:ft + 1]
        js = np.nonzero(seg >= pos["stop"])[0] if pos["dir"] == "S" else np.nonzero(seg <= pos["stop"])[0]
        if len(js):                                   # stopped before this signal
            close(pos["stop"], "STOP"); pos = None; continue
        if dr == pos["dir"]:
            i += 1                                    # same dir -> ignore (single position)
        else:
            close(epx, "FLIP"); pos = dict(dir=dr, epx=epx, stop=stop_of(dr, epx), tick=ft); i += 1
    if pos is not None:
        seg = tP[pos["tick"]:]
        js = np.nonzero(seg >= pos["stop"])[0] if pos["dir"] == "S" else np.nonzero(seg <= pos["stop"])[0]
        if len(js):
            close(pos["stop"], "STOP")
        else:
            close(float(tP[-1]), "EOD")
    return trades


def build_trades(limit=None):
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None
    all_tr = []; t0 = time.time()
    for i, d in enumerate(dates):
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
                stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)
                sigs = signals_for_day(g, tP, tbar, sma20, adr10)
                all_tr += flip_day(d, sigs, tP, stop_pts)
        prev_close, prev_range = day_cl, day_hi - day_lo
        if (i + 1) % 300 == 0:
            print(f"  ... {i+1}/{len(dates)} days, {time.time()-t0:.0f}s", flush=True)
    return pd.DataFrame(all_tr)


def account_sim(daily_pts, base, step, mult, sub_month=200.0):
    """EOD equity walk: contract scaling + trailing-DD-freeze-at-BE, EOD-measured.
    daily_pts = Series (date -> that day's total net POINTS, 1 contract).
    The $200/mo subscription is paid OUTSIDE the account (doesn't count vs the DD),
    so it reduces take-home but not the equity the DD watches. Returns both."""
    eq = 0.0; hwm = 0.0; size = base; peak = 0.0; maxdd = 0.0; blown = None
    sub_paid = 0.0; prev_month = None
    for d, pts in daily_pts.items():
        m = d[:7]
        if m != prev_month:
            sub_paid += sub_month; prev_month = m
        size = min(15, base + int(max(eq, 0) // step)) if step else base
        eq += pts * mult * size                          # ACCOUNT equity (DD basis)
        hwm = max(hwm, eq)
        floor = min(hwm, DD) - DD                        # trails until +4500 then locks at BE(0)
        peak = max(peak, eq); maxdd = min(maxdd, eq - peak)
        if blown is None and eq <= floor:
            blown = d
    return dict(final=eq, take=eq - sub_paid, sub=sub_paid,
                maxdd=maxdd, blown=blown, end_size=size)


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    df = build_trades(limit)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTDIR / f"flip_trades_{stamp}.csv", index=False)
    df["date"] = df["date"].astype(str)
    df["yr"] = df["date"].str[:4].astype(int)

    def pf(v):
        v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
        return gp / gl if gl else float("inf")

    print(f"\nFLIP MODE (single position) — {len(df)} trades, {df['date'].nunique()} days, "
          f"{df.yr.min()}-{df.yr.max()}")
    print(f"outcomes: {df.outcome.value_counts().to_dict()}")

    for inst, mult, cost in (("MES", 5.0, 6.25), ("ES", 50.0, 17.50)):
        cost_pts = cost / mult
        df["net_pts"] = df["pts"] - cost_pts
        daily = df.groupby("date")["net_pts"].sum()
        v = df.net_pts.values * mult
        print("\n" + "=" * 66)
        print(f"{inst}  (${mult:.0f}/pt, cost ${cost}/contract/trade, $200/mo sub OUTSIDE account)")
        print("=" * 66)
        print(f"1 {inst}: net ${v.sum():+,.0f}  PF {pf(df.net_pts.values):.2f}  win {100*(v>0).mean():.0f}%  "
              f"exp ${v.mean():+.0f}/tr  ~${v.sum()/5.1:+,.0f}/yr")
        dd1 = daily * mult
        print(f"worst single DAY at 1 {inst}: ${dd1.min():+,.0f} ({dd1.idxmin()})   best ${dd1.max():+,.0f}")
        print("  per-year:  " + "  ".join(f"{y}:${df[df.yr==y].net_pts.sum()*mult:+,.0f}" for y in sorted(df.yr.unique())))

        print(f"\n  FIXED SIZE (no scaling) vs $4,500 EOD trailing-DD-freeze-at-BE:")
        for base in (1, 2, 3, 5):
            r = account_sim(daily, base, 0, mult)
            st = f"BLOWN {r['blown']}" if r["blown"] else "SURVIVES"
            print(f"    {base:>2} {inst}: acct ${r['final']:+8,.0f}  take(after sub ${r['sub']:,.0f}) "
                  f"${r['take']:+8,.0f}  EODmaxDD ${r['maxdd']:+7,.0f}  -> {st}")

        print(f"\n  SCALING start 1 {inst}, +1c per $step banked (cap 15):")
        for step in (2000, 3000, 5000, 10000, 20000):
            r = account_sim(daily, 1, step, mult)
            st = f"BLOWN {r['blown']}" if r["blown"] else "SURVIVES"
            print(f"    +1c/${step:>6,}: acct ${r['final']:+8,.0f}  take ${r['take']:+8,.0f}  "
                  f"EODmaxDD ${r['maxdd']:+7,.0f}  end {r['end_size']:>2}c -> {st}")
    print(f"\ncsv: {OUTDIR / f'flip_trades_{stamp}.csv'}")


if __name__ == "__main__":
    main()
