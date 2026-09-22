"""Position-management MODE sweep for the 2E book on the $4,500 EOD prop account.

Same signals / same real-tick path as regime2e_flip_scale_sim.py; only the
in-position rule differs. Signals are computed ONCE per day (the expensive part)
then all modes are simulated on them.

MODES (all single-position, no pyramiding):
  flip        : opposite 2E -> reverse (close + open opposite)              [current]
  ignore      : hold the first trade to stop/EOD, ignore ALL further signals;
                after a stop you may take the next signal (multiple non-overlap/day)
  close_reenter: opposite 2E -> close (do NOT take it); flat, re-enterable later
  close_done  : opposite 2E -> close and STOP trading for the day
  one_per_day : take only the FIRST signal; hold to stop/EOD; no re-entry ever

For each mode x instrument (MES $5/pt, ES $50/pt), reports 1-contract net/PF/win,
worst day, EOD maxDD, and SURVIVE/BLOW vs the $4,500 EOD trailing-DD-freeze-at-BE.

  python scripts/regime2e_mode_sweep.py [--limit N]
Output: reports/regime2e/mode_sweep_<stamp>.csv (per-trade, all modes) + stdout.
"""
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

TICK = 0.25; DD = 4500.0; SUB = 200.0
STOP_MULT = 0.30; STOP_FLOOR_T = 8
GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
MODES = ["flip", "ignore", "close_reenter", "close_done", "one_per_day"]
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime2e_flip_scale_sim import signals_for_day             # noqa: E402


def sim_day(date, sigs, tP, stop_pts, mode):
    trades = []; pos = None; i = 0; n = len(sigs); done = False

    def stop_of(dr, epx):
        return epx + stop_pts if dr == "S" else epx - stop_pts

    def close(exit_px, outcome):
        pts = (pos["epx"] - exit_px) if pos["dir"] == "S" else (exit_px - pos["epx"])
        trades.append(dict(date=date, dir=pos["dir"], pts=round(float(pts), 2), outcome=outcome))

    while i < n and not done:
        ft, dr, epx = sigs[i]
        if pos is None:
            pos = dict(dir=dr, epx=epx, stop=stop_of(dr, epx), tick=ft); i += 1; continue
        seg = tP[pos["tick"]:ft + 1]
        js = np.nonzero(seg >= pos["stop"])[0] if pos["dir"] == "S" else np.nonzero(seg <= pos["stop"])[0]
        if len(js):
            close(pos["stop"], "STOP"); pos = None
            if mode == "one_per_day":
                done = True
            continue
        if dr == pos["dir"]:
            i += 1                                   # same dir: ignore in every mode
        elif mode == "flip":
            close(epx, "FLIP"); pos = dict(dir=dr, epx=epx, stop=stop_of(dr, epx), tick=ft); i += 1
        elif mode in ("ignore", "one_per_day"):
            i += 1                                   # hold original, ignore opposite
        else:                                        # close_reenter / close_done
            close(epx, "CLOSE"); pos = None; i += 1
            if mode == "close_done":
                done = True
    if pos is not None:
        seg = tP[pos["tick"]:]
        js = np.nonzero(seg >= pos["stop"])[0] if pos["dir"] == "S" else np.nonzero(seg <= pos["stop"])[0]
        close(pos["stop"], "STOP") if len(js) else close(float(tP[-1]), "EOD")
    return trades


def build_all(limit=None):
    dates = sorted(p.stem for p in TICKD.glob("2*.parquet"))
    if limit:
        dates = dates[-limit:]
    ranges = deque(maxlen=ADR_N); closes = deque(maxlen=SMA_N)
    prev_close = prev_range = None
    out = {m: [] for m in MODES}; t0 = time.time()
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
                sigs = signals_for_day(g, tP, tbar, sma20, adr10)      # computed ONCE
                if sigs:
                    for m in MODES:
                        out[m] += sim_day(d, sigs, tP, stop_pts, m)
        prev_close, prev_range = day_cl, day_hi - day_lo
        if (i + 1) % 300 == 0:
            print(f"  ... {i+1}/{len(dates)} days, {time.time()-t0:.0f}s", flush=True)
    return out


def account(daily, mult, base=1, step=0):
    eq = hwm = peak = 0.0; maxdd = 0.0; size = base; blown = None; sub = 0.0; pm = None
    for d, pnl1 in daily.items():
        m = d[:7]
        if m != pm:
            sub += SUB; pm = m
        size = min(15, base + int(max(eq, 0) // step)) if step else base
        eq += pnl1 * size
        hwm = max(hwm, eq); floor = min(hwm, DD) - DD
        peak = max(peak, eq); maxdd = min(maxdd, eq - peak)
        if blown is None and eq <= floor:
            blown = d
    return eq, eq - sub, maxdd, blown


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    out = build_all(limit)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    allrows = []
    for m in MODES:
        for r in out[m]:
            allrows.append({**r, "mode": m})
    pd.DataFrame(allrows).to_csv(OUTDIR / f"mode_sweep_{stamp}.csv", index=False)

    for inst, mult, cost in (("MES", 5.0, 6.25), ("ES", 50.0, 17.50)):
        print("\n" + "=" * 92)
        print(f"{inst} (${mult:.0f}/pt, ${cost}/c/trade, $200/mo sub) — 1 contract, $4,500 EOD trailing-DD")
        print("=" * 92)
        print(f"{'mode':14} {'n':>4} {'net$':>9} {'PF':>5} {'win%':>4} {'exp$':>5} "
              f"{'worstDay':>8} {'EODmaxDD':>9} {'take$':>9}  survive?")
        for m in MODES:
            df = pd.DataFrame(out[m])
            if df.empty:
                continue
            df["net_pts"] = df["pts"] - cost / mult
            v = df["net_pts"].values * mult
            daily = df.groupby("date")["net_pts"].sum() * mult
            eq, take, maxdd, blown = account(daily, 1.0)
            st = f"BLOWN {blown}" if blown else "SURVIVES"
            print(f"{m:14} {len(df):>4} {v.sum():>+9,.0f} {pf(df.net_pts.values):>5.2f} "
                  f"{100*(v>0).mean():>4.0f} {v.mean():>+5.0f} {daily.min():>+8,.0f} "
                  f"{maxdd:>+9,.0f} {take:>+9,.0f}  {st}")
    print(f"\ncsv: {OUTDIR / f'mode_sweep_{stamp}.csv'}")


if __name__ == "__main__":
    main()
