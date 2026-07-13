"""Brooks A+ backtest core — REGIME-FREE.

Reuses ONLY the trustworthy, regime-independent primitives (per the S69 engine
capability map): 5m bars + per-day tick cache, EMA20 context (user directive),
bar-count leg structure, and a tick-accurate fill/stop/target engine.

⚠️ Does NOT use the broken Brooks regime/always-in state machine or its
1ES/2ES entry-count tier. Trend context = the 20-EMA, full stop.

Provides:
  load_bars()                      -> full 5m ES continuous df with Date col
  day_frame(b, date_str)           -> one day's bars, sorted
  compute(g)                       -> dict of per-bar arrays (EMA20, slope, ABR, ER, IBS, ...)
  ema20_context(g, feats)          -> per-bar trend context {+1 bull, -1 bear, 0 range}
  fill_trade(g, tP, tbar, fb, sb, direction, trig, books) -> list of trade dicts
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25
PT_ES = 50.0        # $/pt full ES
PT_MES = 5.0        # $/pt micro ES (user's instrument)
COMM = 5.0          # $ round-turn (user's real prop cost on MES)
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT))


def load_bars():
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    return b


def day_frame(b, date_str):
    g = b[b["Date"] == date_str].sort_values("DateTime").reset_index(drop=True)
    return g


def resample_tf(g, k):
    """Aggregate a day's 5-minute bars into k*5-minute bars (k=1->5m, 2->10m, 3->15m),
    aligned to the session start. Bucket DateTime = its first 5m bar's start (left label),
    so tick->bar mapping via searchsorted on DateTime stays correct."""
    if k == 1:
        return g.reset_index(drop=True)
    idx = np.arange(len(g)) // k
    agg = g.groupby(idx).agg(
        DateTime=("DateTime", "first"), Open=("Open", "first"), High=("High", "max"),
        Low=("Low", "min"), Close=("Close", "last"), Volume=("Volume", "sum"),
    ).reset_index(drop=True)
    agg["Date"] = g["Date"].iloc[0]
    return agg


def compute(g):
    O = g["Open"].values.astype(float)
    H = g["High"].values.astype(float)
    L = g["Low"].values.astype(float)
    C = g["Close"].values.astype(float)
    n = len(g)
    rng = (H - L)
    IBS = np.where(rng > 0, (C - L) / np.maximum(rng, 1e-9) * 100.0, 50.0)
    # ABR10 = trailing mean of prior 10 bar ranges (the engine's ATR surrogate)
    ABR = np.array([rng[max(0, i - 10):i].mean() if i > 0 else rng[0] for i in range(n)])
    # EMA20 on close, seeded at close[0] (Brooks/Mack 20-EMA)
    ema = np.empty(n)
    a = 2.0 / (20 + 1)
    ema[0] = C[0]
    for i in range(1, n):
        ema[i] = a * C[i] + (1 - a) * ema[i - 1]
    # slower EMA (~higher-timeframe proxy on 5m) for larger-trend agreement
    ema_slow = np.empty(n)
    a2 = 2.0 / (60 + 1)
    ema_slow[0] = C[0]
    for i in range(1, n):
        ema_slow[i] = a2 * C[i] + (1 - a2) * ema_slow[i - 1]
    slope_slow = np.zeros(n)
    for i in range(5, n):
        slope_slow[i] = (ema_slow[i] - ema_slow[i - 5]) / 5.0 / max(rng[max(0, i-10):i].mean() if i > 0 else rng[0], TICK)
    # EMA slope over 3 bars, normalised by ABR (per-bar, in ABR units)
    slope = np.zeros(n)
    for i in range(3, n):
        slope[i] = (ema[i] - ema[i - 3]) / 3.0 / max(ABR[i], TICK)
    # ER12 (Kaufman efficiency ratio)
    K = 12
    ER = np.zeros(n)
    for i in range(n):
        if i >= K:
            den = np.abs(np.diff(C[i - K:i + 1])).sum()
            ER[i] = abs(C[i] - C[i - K]) / den if den > 0 else 0.0
    return dict(O=O, H=H, L=L, C=C, n=n, rng=rng, IBS=IBS, ABR=ABR, ema=ema, slope=slope,
                ER=ER, ema_slow=ema_slow, slope_slow=slope_slow)


def ema20_context(f, slope_thr=0.03):
    """Per-bar trend context from the 20-EMA ONLY.
    +1 bull  = close above a RISING ema20
    -1 bear  = close below a FALLING ema20
     0 range = otherwise (flat ema20 / mixed)
    slope_thr is in ABR units/bar (small dead-band so a flat EMA => range).
    """
    C, ema, slope, n = f["C"], f["ema"], f["slope"], f["n"]
    ctx = np.zeros(n, dtype=int)
    for i in range(n):
        if C[i] > ema[i] and slope[i] > slope_thr:
            ctx[i] = 1
        elif C[i] < ema[i] and slope[i] < -slope_thr:
            ctx[i] = -1
    return ctx


def fill_trade(f, tP, tbar, fb, sb, direction, trig, books=("1R", "2R", "4R", "EOD", "BE2R"),
               cancel_bars=4):
    """Tick-accurate fill + management. Returns one dict per book (management scheme).
    fb = trigger bar index (entry armed on/after this bar)
    sb = signal bar index (defines the protective stop)
    direction = 'L' or 'S'; trig = stop-entry trigger price.
    cancel_bars = the resting stop-entry is cancelled if not hit within this many
      bars after fb (Brooks cancels a stale entry). Stop = 1 tick beyond signal-bar
      extreme. Books: 1R/2R/4R fixed R; EOD hold to last tick; BE2R = 2R target but
      move stop to breakeven once +1R is reached (runner with BE).
    """
    H, L = f["H"], f["L"]
    short = direction == "S"
    a = np.searchsorted(tbar, fb, "left")
    z = len(tP)
    # entry must trigger within cancel_bars bars of fb
    ze = np.searchsorted(tbar, fb + cancel_bars, "right")
    s = tP[a:ze]
    if not len(s):
        return []
    hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
    if not len(hit):
        return []
    jf = a + int(hit[0])
    fill = trig - TICK if short else trig + TICK
    stop = H[sb] + TICK if short else L[sb] - TICK
    R = (stop - fill) if short else (fill - stop)
    if R <= 0:
        return []
    seg = tP[jf:]
    # index of stop hit
    js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
    js = js_[0] if len(js_) else np.inf
    out = []
    for book in books:
        if book == "EOD":
            ex = stop if np.isfinite(js) else seg[-1]
            pnl = (fill - ex) if short else (ex - fill)
            out.append(_row(direction, book, pnl, R, fill, stop))
            continue
        if book == "TR1":
            # chandelier trail: once +1R reached, trail stop 1R behind the best price
            best = fill
            cur_stop = stop
            armed = False
            ex = None
            for px in seg:
                if short:
                    if px < best:
                        best = px
                    if not armed and (fill - best) >= R:
                        armed = True
                    if armed:
                        cur_stop = min(cur_stop, best + R)
                    if px >= cur_stop:
                        ex = cur_stop; break
                else:
                    if px > best:
                        best = px
                    if not armed and (best - fill) >= R:
                        armed = True
                    if armed:
                        cur_stop = max(cur_stop, best - R)
                    if px <= cur_stop:
                        ex = cur_stop; break
            if ex is None:
                ex = seg[-1]
            pnl = (fill - ex) if short else (ex - fill)
            out.append(_row(direction, book, pnl, R, fill, stop))
            continue
        if book == "BE2R":
            # move to BE once +1R reached, target 2R
            one = fill - 1 * R if short else fill + 1 * R
            tgt = fill - 2 * R if short else fill + 2 * R
            j1_ = np.nonzero(seg <= one)[0] if short else np.nonzero(seg >= one)[0]
            j1 = j1_[0] if len(j1_) else np.inf
            jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
            jt = jt_[0] if len(jt_) else np.inf
            if js < j1 and js < jt:                 # stopped before +1R
                ex = stop
            else:
                # BE active after j1; stop becomes fill
                jbe_ = np.nonzero(seg[int(j1) if np.isfinite(j1) else 0:] >= fill)[0] if short \
                    else np.nonzero(seg[int(j1) if np.isfinite(j1) else 0:] <= fill)[0]
                jbe = (int(j1) + jbe_[0]) if (np.isfinite(j1) and len(jbe_)) else np.inf
                if np.isfinite(jt) and (not np.isfinite(jbe) or jt <= jbe):
                    ex = tgt
                elif np.isfinite(jbe):
                    ex = fill                        # breakeven
                else:
                    ex = seg[-1]
            pnl = (fill - ex) if short else (ex - fill)
            out.append(_row(direction, book, pnl, R, fill, stop))
            continue
        k = {"1R": 1.0, "2R": 2.0, "4R": 4.0}[book]
        tgt = fill - k * R if short else fill + k * R
        jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
        jt = jt_[0] if len(jt_) else np.inf
        if js <= jt:
            ex = stop
        elif np.isfinite(jt):
            ex = tgt
        else:
            ex = seg[-1]
        pnl = (fill - ex) if short else (ex - fill)
        out.append(_row(direction, book, pnl, R, fill, stop))
    return out


def _row(direction, book, pnl, R, fill, stop):
    return dict(dir=direction, book=book, Rpts=R, pnl_pts=pnl, Rmult=pnl / R,
                net_mes=pnl * PT_MES - COMM, net_es=pnl * PT_ES - COMM, fill=fill, stop=stop)
