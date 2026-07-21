"""Brooks A+ #1 — High 2 / Low 2 pullback (M2B/M2S) backtest, REGIME-FREE.

Trend context = 20-EMA ONLY (user directive). No Brooks regime engine.
Mechanical H2 (long) / L2 (short) definition:
  - Context: EMA20 bull (close>rising EMA20) for H2 longs; bear for L2 shorts.
  - A pullback begins when price trades below the running swing extreme.
  - Hn counting: a "higher-high bar" (H[i]>H[i-1]) is a leg marker; H1 is the
    first, and H2 is the next higher-high bar AFTER a new low below the H1-leg
    low has printed (i.e. a genuine two-legged A-B-C pullback), mirror for L2.
  - Signal bar = the pullback's second-leg low bar; entry = stop 1 tick beyond
    its high (H2 long) / low (L2 short); protective stop 1 tick the other side.
  - M2B/M2S filter (optional): the pullback low touched/penetrated the EMA20.
Reports base rates by year, net of $5 RT on MES, across management schemes and
with/without the EMA-touch (M2B) filter.
"""
import sys, time, gc
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import massive
from brooks_bt_core import (load_bars, day_frame, compute, ema20_context,
                            fill_trade, TICK)

BOOKS = ("1R", "2R", "4R", "EOD", "BE2R", "TR1")


def detect_h2_l2(f, ctx, slthr=0.03):
    """Brooks High-2 / Low-2 by up/down-ATTEMPT counting (the real rule).

    In a pullback within a bull (EMA20 rising):
      - High 1 = first bar whose high pokes above the prior bar's high (1st up-attempt).
      - The attempt then stalls (a down bar prints), i.e. a genuine 2nd leg down.
      - High 2 = the next bar whose high exceeds the prior bar's high (2nd up-attempt).
      - Signal bar = the bar right before that H2 up-bar; entry = 1 tick above it,
        stop = 1 tick below it. Mirror (Low 1/Low 2) for a bear (EMA20 falling).
    Direction gated by EMA20 slope (rising->H2 long, falling->L2 short). The
    pullback resets when price makes a new swing extreme. m2b = pullback reached EMA.
    """
    H, L, ema, slope, n = f["H"], f["L"], f["ema"], f["slope"], f["n"]
    sigs = []

    # ---- H2 longs (EMA20 rising) ----
    run_hi = H[0]; in_pb = False; attempt = 0; down_seen = False
    for i in range(1, n):
        if H[i] >= run_hi:                       # new swing high -> pullback over, reset
            run_hi = H[i]; in_pb = False; attempt = 0; down_seen = False; continue
        if not in_pb:                            # start of a pullback below the swing high
            in_pb = True; attempt = 0; down_seen = False
        up = H[i] > H[i - 1] + TICK / 2          # up-attempt bar
        if up:
            if attempt == 0:
                attempt = 1                      # High 1
            elif attempt == 1 and down_seen:
                sb = i - 1                        # signal bar = bar before the H2 up-bar
                if slope[i] > slthr:             # EMA20 rising => bull trend
                    sigs.append(dict(fb=i, sb=sb, dir="L", trig=H[sb] + TICK,
                                     m2b=bool(L[sb] <= ema[sb]), er=float(f["ER"][i]),
                                     slow=bool(f["slope_slow"][i] > 0),
                                     sbq=float(f["IBS"][sb]), tod=int(sb)))
                attempt = 2                       # one H2 per pullback (until new swing high)
        else:
            if L[i] < L[i - 1] - TICK / 2:        # a real down bar = 2nd leg forming
                down_seen = True

    # ---- L2 shorts (EMA20 falling) ----
    run_lo = L[0]; in_pb = False; attempt = 0; up_seen = False
    for i in range(1, n):
        if L[i] <= run_lo:
            run_lo = L[i]; in_pb = False; attempt = 0; up_seen = False; continue
        if not in_pb:
            in_pb = True; attempt = 0; up_seen = False
        dn = L[i] < L[i - 1] - TICK / 2           # down-attempt bar
        if dn:
            if attempt == 0:
                attempt = 1                       # Low 1
            elif attempt == 1 and up_seen:
                sb = i - 1
                if slope[i] < -slthr:             # EMA20 falling => bear trend
                    sigs.append(dict(fb=i, sb=sb, dir="S", trig=L[sb] - TICK,
                                     m2b=bool(H[sb] >= ema[sb]), er=float(f["ER"][i]),
                                     slow=bool(f["slope_slow"][i] < 0),
                                     sbq=float(100 - f["IBS"][sb]), tod=int(sb)))
                attempt = 2
        else:
            if H[i] > H[i - 1] + TICK / 2:
                up_seen = True
    return sigs


def run():
    b = load_bars()
    days = sorted(b["Date"].unique())
    rows = []
    t0 = time.time()
    for di, d in enumerate(days):
        g = day_frame(b, d)
        if len(g) < 30:
            continue
        tk = massive.load_continuous_ticks(date.fromisoformat(d))
        if tk.empty:
            continue
        tk = tk.sort_values("DateTime")
        tP = tk["Price"].values
        tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
        f = compute(g)
        ctx = ema20_context(f)
        for sg in detect_h2_l2(f, ctx):
            trades = fill_trade(f, tP, tbar, sg["fb"], sg["sb"], sg["dir"], sg["trig"], BOOKS)
            for tr in trades:
                tr.update(Date=d, m2b=sg["m2b"], year=d[:4], fb=sg["fb"], er=sg["er"],
                          slow=sg["slow"], sbq=sg["sbq"], tod=sg["tod"])
                rows.append(tr)
        del tk, tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    out = ROOT / "docs" / "living" / "brooks_bt_h2_trades.parquet"
    df.to_parquet(out)
    print(f"\nDONE {time.time()-t0:.0f}s  trades(per-book rows)={len(df)}  file={out}")
    report(df)


def report(df):
    def blk(sub, label):
        if not len(sub):
            print(f"  {label:22s} n=0"); return
        R = sub["Rmult"]
        ci = 1.96 * R.std() / np.sqrt(len(sub))
        pf_w = sub.loc[sub.pnl_pts > 0, "net_mes"].sum()
        pf_l = -sub.loc[sub.pnl_pts <= 0, "net_mes"].sum()
        pf = pf_w / pf_l if pf_l > 0 else float("inf")
        print(f"  {label:22s} n={len(sub):5d}  avgR {R.mean():+.3f}±{ci:.3f}  "
              f"win {(R>0).mean()*100:4.1f}%  PF {pf:4.2f}  "
              f"net/lot(MES) ${sub['net_mes'].sum():>8,.0f}  perTrade ${sub['net_mes'].mean():+6.1f}")

    n_entries = len(df[df.book == "1R"])
    print(f"\n===== H2/L2 — {n_entries} entries (2021-06..2026-07), net $5 RT on MES =====")
    # headline management comparison on the M2B subset (the only live lead)
    print("\n##### M2B subset — management comparison #####")
    for book in BOOKS:
        blk(df[(df.book == book) & (df.m2b)], f"M2B {book}")

    print("\n##### edge-lever cuts (book=TR1 trailing) #####")
    d2 = df[df.book == "TR1"]
    blk(d2[d2.m2b], "M2B")
    blk(d2[d2.m2b & d2.slow], "M2B & slowEMA-agree")
    blk(d2[d2.m2b & (d2.sbq >= 60)], "M2B & strong signal-bar")
    blk(d2[d2.m2b & d2.slow & (d2.sbq >= 60)], "M2B & slow & strong-SB")
    blk(d2[d2.m2b & (d2.tod >= 6) & (d2.tod <= 60)], "M2B & 09:00-13:30 only")
    blk(d2[d2.m2b & d2.slow & (d2.tod <= 60)], "M2B & slow & not-late")

    print("\n##### best combo by year (TR1, M2B & slowEMA-agree) #####")
    dd = df[(df.book == "TR1") & (df.m2b) & (df.slow)]
    for y in sorted(dd.year.unique()):
        blk(dd[dd.year == y], y)
    print("\n##### by year — M2B all (TR1) for comparison #####")
    dd2 = df[(df.book == "TR1") & (df.m2b)]
    for y in sorted(dd2.year.unique()):
        blk(dd2[dd2.year == y], y)


if __name__ == "__main__":
    run()
