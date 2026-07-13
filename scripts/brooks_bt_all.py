"""Brooks A+ mechanizable setups — multi-timeframe backtest (5m / 10m / 15m), REGIME-FREE.

Trend context = 20-EMA only. No Brooks regime engine. One shared two-legged
attempt detector feeds three setups:
  H2L2   = with-trend High-2/Low-2 pullback (EMA rising->long, falling->short)
  REV    = second-entry reversal (2nd attempt AGAINST an extended move: price
           stretched > EXT*ABR beyond the EMA, counter to the EMA slope)
  BOPB   = breakout pullback (H2/L2 whose pullback began from a fresh N-bar breakout)

Every trade is scored at BOTH cost structures — MES @ $5 RT (the prop) and full
ES @ $5 RT — because the 5m finding was that the prop's fixed $5 dominates the edge.
"""
import sys, time, gc
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import massive
from brooks_bt_core import (load_bars, day_frame, resample_tf, compute,
                            fill_trade, TICK, PT_MES, PT_ES, COMM)

BOOKS = ("2R", "EOD", "BE2R", "TR1")
SETUPS = ("H2L2", "BOPB", "REV", "SPIKE", "AIFT", "TFO", "OREV", "SPCH")
TFS = {"5m": 1, "10m": 2, "15m": 3}
BO_LOOKBACK = 20      # bars for the "fresh breakout" test
EXT = 1.5             # ABR multiples beyond EMA to call a move "extended" (reversal)


def two_leg_events(f, slthr=0.03):
    """Emit every 2nd up-attempt and 2nd down-attempt (Brooks H2/L2 geometry) with
    context flags, regardless of trade decision. side='up' -> long candidate,
    'dn' -> short candidate. Flags: m2b, slow(agree), sbq, er, ext(ended), fresh_bo, slope_sign."""
    H, L, ema, slope, ABR, C = f["H"], f["L"], f["ema"], f["slope"], f["ABR"], f["C"]
    IBS, ER, slope_slow, n = f["IBS"], f["ER"], f["slope_slow"], f["n"]
    ev = []
    roll_hi = pd.Series(H).rolling(BO_LOOKBACK, min_periods=3).max().shift(1).values
    roll_lo = pd.Series(L).rolling(BO_LOOKBACK, min_periods=3).min().shift(1).values

    # up-attempts (longs)
    run_hi = H[0]; in_pb = False; attempt = 0; down_seen = False; bo_flag = False
    for i in range(1, n):
        if H[i] >= run_hi:
            run_hi = H[i]; in_pb = False; attempt = 0; down_seen = False
            bo_flag = bool(not np.isnan(roll_hi[i]) and H[i] > roll_hi[i])   # fresh breakout high
            continue
        if not in_pb:
            in_pb = True; attempt = 0; down_seen = False
        if H[i] > H[i - 1] + TICK / 2:
            if attempt == 0:
                attempt = 1
            elif attempt == 1 and down_seen:
                sb = i - 1
                ev.append(dict(i=i, sb=sb, side="up", trig=H[sb] + TICK,
                               m2b=bool(L[sb] <= ema[sb]), slow=bool(slope_slow[i] > 0),
                               sbq=float(IBS[sb]), er=float(ER[i]),
                               ext=bool(C[i] < ema[i] - EXT * ABR[i]),
                               fresh_bo=bo_flag, up=bool(slope[i] > slthr),
                               dn=bool(slope[i] < -slthr), tod=int(sb)))
                attempt = 2
        else:
            if L[i] < L[i - 1] - TICK / 2:
                down_seen = True

    # down-attempts (shorts)
    run_lo = L[0]; in_pb = False; attempt = 0; up_seen = False; bo_flag = False
    for i in range(1, n):
        if L[i] <= run_lo:
            run_lo = L[i]; in_pb = False; attempt = 0; up_seen = False
            bo_flag = bool(not np.isnan(roll_lo[i]) and L[i] < roll_lo[i])
            continue
        if not in_pb:
            in_pb = True; attempt = 0; up_seen = False
        if L[i] < L[i - 1] - TICK / 2:
            if attempt == 0:
                attempt = 1
            elif attempt == 1 and up_seen:
                sb = i - 1
                ev.append(dict(i=i, sb=sb, side="dn", trig=L[sb] - TICK,
                               m2b=bool(H[sb] >= ema[sb]), slow=bool(slope_slow[i] < 0),
                               sbq=float(100 - IBS[sb]), er=float(ER[i]),
                               ext=bool(C[i] > ema[i] + EXT * ABR[i]),
                               fresh_bo=bo_flag, up=bool(slope[i] > slthr),
                               dn=bool(slope[i] < -slthr), tod=int(sb)))
                attempt = 2
        else:
            if H[i] > H[i - 1] + TICK / 2:
                up_seen = True
    return ev


def signals_for(setup, ev, f):
    """Turn events / bar features into (direction, sig) for a given setup."""
    out = []
    # ---- two-legged-event setups ----
    if setup in ("H2L2", "BOPB", "REV"):
        for e in ev:
            d = "L" if e["side"] == "up" else "S"
            if setup == "H2L2":
                if (e["side"] == "up" and e["up"]) or (e["side"] == "dn" and e["dn"]):
                    out.append((d, e))
            elif setup == "BOPB":
                if e["fresh_bo"] and ((e["side"] == "up" and e["up"]) or (e["side"] == "dn" and e["dn"])):
                    out.append((d, e))
            elif setup == "REV":
                if e["side"] == "up" and e["dn"] and e["ext"]:
                    out.append(("L", e))
                elif e["side"] == "dn" and e["up"] and e["ext"]:
                    out.append(("S", e))
        return out
    # ---- bar-feature setups ----
    if setup == "SPIKE":
        return detect_spike(f)
    if setup == "AIFT":
        return detect_aift(f)
    if setup == "TFO":
        return detect_tfo(f)
    if setup == "OREV":
        return detect_orev(f)
    if setup == "SPCH":
        return detect_spch(f)
    return out


def _mk(f, i, sb, d):
    """Build a sig dict from a signal bar sb and trigger bar i, direction d."""
    H, L, ema, ABR, IBS, ER, C = f["H"], f["L"], f["ema"], f["ABR"], f["IBS"], f["ER"], f["C"]
    trig = (H[sb] + TICK) if d == "L" else (L[sb] - TICK)
    m2b = bool(L[sb] <= ema[sb]) if d == "L" else bool(H[sb] >= ema[sb])
    return (d, dict(i=i, sb=sb, side="up" if d == "L" else "dn", trig=trig, m2b=m2b,
                    slow=bool(f["slope_slow"][i] > 0) if d == "L" else bool(f["slope_slow"][i] < 0),
                    sbq=float(IBS[sb]) if d == "L" else float(100 - IBS[sb]),
                    er=float(ER[i]), ext=False, fresh_bo=False, tod=int(sb)))


def _strong(f, i, d):
    """Is bar i a strong trend bar in direction d (big body, close near extreme)?"""
    rng, ABR, IBS = f["rng"], f["ABR"], f["IBS"]
    big = rng[i] > ABR[i]
    return big and (IBS[i] >= 65 if d == "L" else IBS[i] <= 35)


def detect_spike(f):
    """Strong breakout / spike entry: >=3 consecutive strong trend bars; buy the
    continuation 1 tick beyond the last spike bar (stop below the spike base)."""
    n, H, L, slope = f["n"], f["H"], f["L"], f["slope"]
    out = []
    i = 2
    while i < n - 1:
        for d in ("L", "S"):
            if _strong(f, i, d) and _strong(f, i - 1, d) and _strong(f, i - 2, d):
                if (d == "L" and slope[i] > 0) or (d == "S" and slope[i] < 0):
                    base = i - 2
                    sb = base                      # stop beyond the spike base
                    dd, sig = _mk(f, i, i, d)      # entry 1 tick beyond spike bar i
                    sig["trig"] = (H[i] + TICK) if d == "L" else (L[i] - TICK)
                    # widen stop to spike base
                    sig["sb"] = base
                    out.append((d, sig))
                    i += 2
                    break
        i += 1
    return out


def detect_aift(f):
    """Always-in follow-through (EMA20 proxy): 2 consecutive strong trend bars that
    agree with EMA20 slope; enter continuation beyond the 2nd bar."""
    n, slope, H, L = f["n"], f["slope"], f["H"], f["L"]
    out = []
    for i in range(2, n - 1):
        for d in ("L", "S"):
            agree = (d == "L" and slope[i] > 0.03) or (d == "S" and slope[i] < -0.03)
            if agree and _strong(f, i, d) and _strong(f, i - 1, d):
                dd, sig = _mk(f, i, i, d)
                sig["trig"] = (H[i] + TICK) if d == "L" else (L[i] - TICK)
                sig["sb"] = i - 1
                out.append((d, sig))
    return out


def detect_tfo(f, or_bars=6):
    """Trend from the open: after the first `or_bars` (opening range), take the
    breakout in the EMA20 direction; one entry/day, held (EOD favored)."""
    n, H, L, slope = f["n"], f["H"], f["L"], f["slope"]
    if n <= or_bars + 2:
        return []
    orh = H[:or_bars].max(); orl = L[:or_bars].min()
    for i in range(or_bars, min(n - 1, or_bars + 18)):
        if H[i] > orh + TICK and slope[i] > 0:
            d, sig = _mk(f, i, i, "L"); sig["trig"] = orh + TICK; sig["sb"] = i
            return [(d, sig)]
        if L[i] < orl - TICK and slope[i] < 0:
            d, sig = _mk(f, i, i, "S"); sig["trig"] = orl - TICK; sig["sb"] = i
            return [(d, sig)]
    return []


def detect_orev(f, or_bars=6):
    """Opening reversal: in the first ~hour, a reversal bar at the opening-range
    extreme against the initial thrust; fade back toward the day's middle."""
    n, H, L, IBS = f["n"], f["H"], f["L"], f["IBS"]
    if n <= or_bars + 2:
        return []
    out = []
    orh = H[:or_bars].max(); orl = L[:or_bars].min()
    for i in range(or_bars, min(n - 1, 24)):
        # poke above OR high then a bear reversal bar -> short (fade)
        if H[i] >= orh and IBS[i] <= 35:
            d, sig = _mk(f, i, i, "S"); out.append((d, sig));
        elif L[i] <= orl and IBS[i] >= 65:
            d, sig = _mk(f, i, i, "L"); out.append((d, sig))
    return out[:1]


def detect_spch(f):
    """Spike and channel: detect an opening spike (>=3 strong bars), then buy the
    first pullback that resumes inside the channel (EMA-direction only)."""
    n, slope = f["n"], f["slope"]
    sp = detect_spike(f)
    if not sp:
        return []
    d0, s0 = sp[0]
    start = s0["i"] + 1
    H, L = f["H"], f["L"]
    for i in range(start + 1, min(n - 1, start + 30)):
        if d0 == "L" and H[i] > H[i - 1] + TICK and L[i - 1] <= f["ema"][i - 1] and slope[i] > 0:
            d, sig = _mk(f, i, i - 1, "L"); return [(d, sig)]
        if d0 == "S" and L[i] < L[i - 1] - TICK and H[i - 1] >= f["ema"][i - 1] and slope[i] < 0:
            d, sig = _mk(f, i, i - 1, "S"); return [(d, sig)]
    return []


def run():
    b = load_bars()
    days = sorted(b["Date"].unique())
    rows = []
    t0 = time.time()
    for di, d in enumerate(days):
        g5 = day_frame(b, d)
        if len(g5) < 30:
            continue
        tk = massive.load_continuous_ticks(date.fromisoformat(d))
        if tk.empty:
            continue
        tk = tk.sort_values("DateTime"); tP = tk["Price"].values
        tdt = tk["DateTime"].values
        for tf, k in TFS.items():
            g = resample_tf(g5, k)
            if len(g) < 12:
                continue
            tbar = np.searchsorted(g["DateTime"].values, tdt, side="right") - 1
            f = compute(g)
            ev = two_leg_events(f)
            for setup in SETUPS:
                for dirn, e in signals_for(setup, ev, f):
                    trades = fill_trade(f, tP, tbar, e["i"], e["sb"], dirn, e["trig"], BOOKS)
                    for tr in trades:
                        tr.update(Date=d, year=d[:4], setup=setup, tf=tf, dirn=dirn,
                                  m2b=e["m2b"], slow=e["slow"], sbq=e["sbq"], er=e["er"],
                                  ext=e["ext"], fresh_bo=e["fresh_bo"])
                        rows.append(tr)
        del tk, tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    out = ROOT / "docs" / "living" / "brooks_bt_all_trades.parquet"
    df.to_parquet(out)
    print(f"\nDONE {time.time()-t0:.0f}s  rows={len(df)}  file={out}")
    report(df)


def _line(sub, label):
    if not len(sub):
        print(f"    {label:26s} n=0"); return
    R = sub["Rmult"]
    mes = sub["pnl_pts"] * PT_MES - COMM
    es = sub["pnl_pts"] * PT_ES - COMM
    pf = (R[R > 0].sum() / -R[R <= 0].sum()) if (R <= 0).any() else float("inf")
    print(f"    {label:26s} n={len(sub):5d}  avgR{R.mean():+.3f}  win{(R>0).mean()*100:4.0f}%  "
          f"PF{pf:4.2f}  MES/t${mes.mean():+5.1f} (${mes.sum():+8,.0f})  "
          f"ES/t${es.mean():+6.1f} (${es.sum():+9,.0f})")


def report(df):
    print("\n================= BROOKS A+ SETUPS x TIMEFRAME (net $5 RT) =================")
    for setup in SETUPS:
        print(f"\n############ {setup} ############")
        for tf in TFS:
            d0 = df[(df.setup == setup) & (df.tf == tf)]
            if not len(d0):
                continue
            print(f"  ---- {tf} ----")
            for book in ("EOD", "TR1"):
                d2 = d0[d0.book == book]
                _line(d2, f"{book} ALL")
                if d2.m2b.any():
                    _line(d2[d2.m2b], f"{book} M2B")
    # best-of table: for each setup, best TF by ES$, EOD, by year
    print("\n================= YEAR ROBUSTNESS (best cut per setup, EOD, ES $5) =================")
    for setup in SETUPS:
        best = None
        for tf in TFS:
            for m2bonly in (True, False):
                d2 = df[(df.setup == setup) & (df.tf == tf) & (df.book == "EOD")]
                if m2bonly:
                    d2 = d2[d2.m2b]
                if len(d2) < 25:
                    continue
                tot = (d2.pnl_pts * PT_ES - COMM).sum()
                posyrs = sum(1 for y in d2.year.unique()
                             if (d2[d2.year == y].pnl_pts * PT_ES - COMM).sum() > 0)
                if best is None or tot > best[0]:
                    best = (tot, tf, m2bonly, d2, posyrs)
        if best is None:
            print(f"  {setup:5s} -- too few trades"); continue
        tot, tf, m2bonly, d2, posyrs = best
        yrs = " ".join(f"{y}:{(d2[d2.year==y].pnl_pts*PT_ES-COMM).sum():+,.0f}"
                       for y in sorted(d2.year.unique()))
        tag = "M2B" if m2bonly else "ALL"
        print(f"  {setup:5s} {tf:3s} {tag:3s} n={len(d2):4d} +yrs={posyrs}/{d2.year.nunique()} ES5yr${tot:+8,.0f}  {yrs}")


if __name__ == "__main__":
    run()
