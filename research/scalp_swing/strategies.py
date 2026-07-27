"""Signal generators. Each returns a per-bar DataFrame with columns:
   side, entry, stop, target, etype, expiry   (see engine.run docstring).

Causal breakout arming: at the last opening-range bar we arm a STOP order on the
side that breaks FIRST (scanning forward only to pick side == an OCO bracket;
the engine still fills at the real break bar, never earlier). If both sides break
in the same bar we skip (ambiguous without ticks) -> resolved on ticks for finals.
"""
import numpy as np
import pandas as pd

TICK = 0.25


def _empty(day):
    return pd.DataFrame(dict(side=0, entry=np.nan, stop=np.nan, target=np.nan,
                             etype="", expiry=0), index=range(len(day)))


def range_breakout(day, or_bars, risk_pts, rr=2.0, buf_ticks=1,
                   cutoff_bar=None, max_entry_bar=None):
    """Opening/Initial range breakout. Fixed-point risk, target = rr*risk (>=2)."""
    n = len(day)
    sig = _empty(day)
    if n < or_bars + 3:
        return sig
    H, L = day.High.values, day.Low.values
    hi = H[:or_bars].max(); lo = L[:or_bars].min()
    buf = buf_ticks * TICK
    hi_lvl = hi + buf; lo_lvl = lo - buf
    last = n if max_entry_bar is None else min(n, max_entry_bar)
    side = 0; brk_bar = None
    for j in range(or_bars, last):
        up = H[j] >= hi_lvl; dn = L[j] <= lo_lvl
        if up and dn:
            side = 0; brk_bar = j; break   # ambiguous
        if up:
            side = +1; brk_bar = j; break
        if dn:
            side = -1; brk_bar = j; break
    if side == 0:
        return sig
    arm = or_bars - 1
    ep = hi_lvl if side > 0 else lo_lvl
    sp = ep - side * risk_pts
    tp = ep + side * rr * risk_pts
    expiry = brk_bar - arm + 1
    sig.loc[arm, ["side", "entry", "stop", "target", "etype", "expiry"]] = [side, ep, sp, tp, "stop", expiry]
    return sig


def make_range(or_bars, risk_pts, rr=2.0, buf_ticks=1, max_entry_bar=None):
    def f(day):
        return range_breakout(day, or_bars, risk_pts, rr, buf_ticks, max_entry_bar=max_entry_bar)
    f.__name__ = f"rb_or{or_bars}_r{risk_pts}_rr{rr}_me{max_entry_bar}"
    return f


# ---- momentum / donchian scalp ----
def donchian(day, lookback, risk_pts, rr=2.0, buf_ticks=1, start_bar=3, max_entry_bar=None):
    """Buy stop above rolling-N high, sell stop below rolling-N low. Emits the
    FIRST trigger per day (single position anyway). Causal: arm at bar i, level
    from bars [i-lookback, i]."""
    n = len(day); sig = _empty(day)
    if n < lookback + 3:
        return sig
    H, L = day.High.values, day.Low.values
    last = n if max_entry_bar is None else min(n, max_entry_bar)
    for i in range(max(start_bar, lookback), last - 1):
        hh = H[i - lookback:i + 1].max(); ll = L[i - lookback:i + 1].min()
        buf = buf_ticks * TICK
        # decide which side breaks first on the NEXT bar path -> arm both, engine fills first
        # arm long-biased: pick side by which level nearer? We arm the side whose
        # trigger occurs first scanning forward one bar (i+1). Simplify: arm long if
        # next bar breaks up first else short.
        up_lvl = hh + buf; dn_lvl = ll - buf
        j = i + 1
        up = H[j] >= up_lvl; dn = L[j] <= dn_lvl
        if up and not dn:
            side = +1; ep = up_lvl
        elif dn and not up:
            side = -1; ep = dn_lvl
        else:
            continue
        sp = ep - side * risk_pts; tp = ep + side * rr * risk_pts
        sig.loc[i, ["side", "entry", "stop", "target", "etype", "expiry"]] = [side, ep, sp, tp, "stop", 2]
        break  # one entry attempt per day for the scan
    return sig


def make_donchian(lookback, risk_pts, rr=2.0, buf_ticks=1, max_entry_bar=None):
    def f(day):
        return donchian(day, lookback, risk_pts, rr, buf_ticks, max_entry_bar=max_entry_bar)
    f.__name__ = f"dc_lb{lookback}_r{risk_pts}_rr{rr}"
    return f


def _ema(x, span):
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x, dtype=float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _atr(H, L, C, span):
    pc = np.concatenate([[C[0]], C[:-1]])
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    return _ema(tr, span)


def trend_pullback(day, ema_span, atr_span, stop_atr, rr=2.0,
                   start_bar=6, max_entry_bar=None, one_per_day=False):
    """Continuation: in an EMA uptrend, buy a stop-entry above the prior bar high
    after a pullback that TAGS the EMA (price low <= EMA). Mirror for downtrend.
    Stop = stop_atr*ATR below entry; target = rr*risk. Causal (all arrays to bar i)."""
    n = len(day); sig = _empty(day)
    need = max(ema_span, atr_span) + 2
    if n < need + 3:
        return sig
    H, L, C = day.High.values, day.Low.values, day.Close.values
    ema = _ema(C, ema_span); atr = _atr(H, L, C, atr_span)
    last = n if max_entry_bar is None else min(n, max_entry_bar)
    fired = False
    for i in range(max(start_bar, need), last - 1):
        up = C[i] > ema[i] and ema[i] > ema[i - 3]
        dn = C[i] < ema[i] and ema[i] < ema[i - 3]
        tag_up = L[i] <= ema[i] or L[i - 1] <= ema[i - 1]
        tag_dn = H[i] >= ema[i] or H[i - 1] >= ema[i - 1]
        risk = stop_atr * atr[i]
        if risk <= 0:
            continue
        if up and tag_up:
            ep = H[i] + TICK; sp = ep - risk; tp = ep + rr * risk; s = 1
        elif dn and tag_dn:
            ep = L[i] - TICK; sp = ep + risk; tp = ep - rr * risk; s = -1
        else:
            continue
        sig.loc[i, ["side", "entry", "stop", "target", "etype", "expiry"]] = [s, ep, sp, tp, "stop", 2]
        if one_per_day:
            break
    return sig


def make_pullback(ema_span, atr_span, stop_atr, rr=2.0, max_entry_bar=None, one_per_day=False):
    def f(day):
        return trend_pullback(day, ema_span, atr_span, stop_atr, rr,
                              max_entry_bar=max_entry_bar, one_per_day=one_per_day)
    f.__name__ = f"pb_e{ema_span}_a{atr_span}_s{stop_atr}_rr{rr}"
    return f
