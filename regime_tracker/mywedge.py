"""Python port of the MyWedge NinjaScript indicator (PriceActionIndicators.com).

Faithful bar-by-bar re-implementation of MyWedge.cs's OnBarUpdate logic, run as a
single forward pass over historical bars -- equivalent to NT8's Calculate.OnBarClose
backtest replay. SwingLow/SwingHigh/MC_Bull/MC_Bear entries can be retroactively
invalidated a few bars back by a later bar (mirrors the original's Series.Reset()
calls), so state lives in plain mutable arrays rather than a pure streaming
computation.

Deliberately NOT ported -- computed in the original but never read again there
either, confirmed by grepping the whole source file for each identifier:
  - Signal, BOdir, BOup, BOdn, HHdist, LLdist (Breakout/Climax BO Logics region)
  - Body, BodyPct, ZScore, ZScoreB, StatAvrg/RangeSTDev/RangeZ/BStatAvrg/BodySTDev/BodyZ
  - Draw.Line / RemoveDrawObject / bar coloring (chart-only, no state effect)
  - showLast200 (WedgeScalper's 10-arg MyWedge(...) overload never sets it)

Session boundaries (Bars.BarsSinceNewTradingDay / Bars.IsFirstBarOfSession) are
NT8 session-template specific and can't be inferred from OHLC alone -- pass them
in via `is_new_session`.
"""
import math
from datetime import timedelta
from zoneinfo import ZoneInfo


def _sma(values, i, period):
    lo = max(0, i - period + 1)
    window = values[lo:i + 1]
    return sum(window) / len(window)


def bars_since_new_session(is_new_session):
    """out[i] = 0 on the first bar of a session, incrementing each bar after."""
    out = [0] * len(is_new_session)
    count = 0
    for i, is_new in enumerate(is_new_session):
        if is_new:
            count = 0
        else:
            count += 1
        out[i] = count
    return out


def is_new_session_cme_eth(timestamps, session_start_hour=17, tz_name="America/Chicago"):
    """Session-boundary helper for NT8's stock "CME US Index Futures ETH" template:
    the session starting at `session_start_hour` (17:00 CT by default) on calendar
    day D is labeled trading day D+1 -- e.g. Sunday 5pm CT begins Monday's session.

    `timestamps` must be tz-aware datetimes (any timezone; converted to tz_name
    internally). Returns a bool list, True on the first bar of each new session.
    Confirm this matches your actual chart's session template before trusting it --
    a custom template with different cutover times will disagree with this.
    """
    tz = ZoneInfo(tz_name)
    session_dates = []
    for ts in timestamps:
        local = ts.astimezone(tz)
        d = local.date()
        if local.hour >= session_start_hour:
            d = d + timedelta(days=1)
        session_dates.append(d)
    out = [False] * len(session_dates)
    for i in range(len(session_dates)):
        if i == 0 or session_dates[i] != session_dates[i - 1]:
            out[i] = True
    return out


def _mro(valid_fn, i, occurrence, bars_back):
    """Port of NinjaScript's MRO(): bars-ago offset of the `occurrence`-th most
    recent True returned by valid_fn. NinjaTrader's MRO counts the CURRENT bar
    (barsAgo 0) as a possible occurrence -- e.g. MRO(() => Close[0]>Open[0], 1, n)
    returns 0 when the current bar matches -- so the scan must start at barsAgo 0,
    not 1. Returns 0 if not found within bars_back (callers guard with `> 0`)."""
    found = 0
    for bars_ago in range(0, bars_back + 1):
        idx = i - bars_ago
        if idx < 0:
            break
        if valid_fn(idx):
            found += 1
            if found == occurrence:
                return bars_ago
    return 0


class MyWedgeResult:
    def __init__(self, n):
        self.mc_bull = [math.nan] * n
        self.mc_bear = [math.nan] * n
        self.swing_low = [math.nan] * n
        self.swing_high = [math.nan] * n
        self.wedge_bl = [math.nan] * n
        self.wedge_br = [math.nan] * n
        self.wedge_bl_sb = [math.nan] * n
        self.wedge_br_sb = [math.nan] * n
        # exposed for debugging / validation against an NT8 export, not used
        # by anything downstream in this module
        self.bar_dir = [0] * n
        self.ob = [False] * n
        self.ib = [False] * n
        self.ibs = [0.0] * n
        self.atr50 = [0.0] * n


def compute_mywedge(
    open_, high, low, close, tick_size, is_new_session,
    lookback=12, show_w2l=False, wedge_symmetry=4, ol_sensitivity=1,
    ctsb_ignore=True, ib_ignore=True, show_wedge_sb=True,
    signal_bar_ibs=66.0, continue_mc=False, continue_on_gap=False,
    warmup_floor=4,
):
    """Ports MyWedge.cs's OnBarUpdate. Defaults here match MyWedge.cs's own
    State.SetDefaults (NOT the stale copies in WedgeScalper.cs's SetDefaults --
    CTSB_Ignore/IB_Ignore in particular differ between the two: MyWedge.cs
    defaults both to True, WedgeScalper.cs's had them at False).

    warmup_floor: the hard minimum for `start` below (default 4, matching the
    original port -- do not change it for anything using the wedge/signal-bar
    outputs, only swing_low/swing_high are safe to warm up faster, since every
    H(k)/L(k) lookback already guards negative indices to NaN/False)."""
    n = len(open_)
    if not (len(high) == len(low) == len(close) == len(is_new_session) == n):
        raise ValueError("open/high/low/close/is_new_session must be same length")

    bsntd = bars_since_new_session(is_new_session)
    res = MyWedgeResult(n)

    bar_range = [high[i] - low[i] for i in range(n)]
    avg_range = [_sma(bar_range, i, 8) for i in range(n)]

    true_range = [0.0] * n
    for i in range(n):
        if i == 0:
            true_range[i] = bar_range[i]
        else:
            true_range[i] = max(
                bar_range[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])
            )
    atr50 = [_sma(true_range, i, 50) for i in range(n)]
    res.atr50 = atr50

    # C# `60 / OLSensitivity` is INTEGER division (both operands int) before
    # widening to double -- e.g. OLSensitivity=7 gives OLDiv=8, not 8.571.
    ol_div = float(60 // ol_sensitivity)
    sym_fact = float(wedge_symmetry)
    sym_fact_dist = float(wedge_symmetry)

    continue_from_y = False
    start = max(int(1.5 * lookback), warmup_floor)

    for i in range(start, n):
        def L(k):
            idx = i - k
            return low[idx] if idx >= 0 else math.nan

        def H(k):
            idx = i - k
            return high[idx] if idx >= 0 else math.nan

        def O(k):
            idx = i - k
            return open_[idx] if idx >= 0 else math.nan

        def C(k):
            idx = i - k
            return close[idx] if idx >= 0 else math.nan

        def BR(k):
            idx = i - k
            return bar_range[idx] if idx >= 0 else math.nan

        def OBf(k):
            idx = i - k
            return res.ob[idx] if idx >= 0 else False

        def IBf(k):
            idx = i - k
            return res.ib[idx] if idx >= 0 else False

        def BD(k):
            idx = i - k
            return res.bar_dir[idx] if idx >= 0 else 0

        def SL(k):
            idx = i - k
            return res.swing_low[idx] if idx >= 0 else math.nan

        def SL_set(k, v):
            res.swing_low[i - k] = v

        def SL_reset(k):
            idx = i - k
            if idx >= 0:
                res.swing_low[idx] = math.nan

        def SH(k):
            idx = i - k
            return res.swing_high[idx] if idx >= 0 else math.nan

        def SH_set(k, v):
            res.swing_high[i - k] = v

        def SH_reset(k):
            idx = i - k
            if idx >= 0:
                res.swing_high[idx] = math.nan

        def MC_BULL_VALID(k):
            idx = i - k
            return idx >= 0 and not math.isnan(res.mc_bull[idx])

        def MC_BEAR_VALID(k):
            idx = i - k
            return idx >= 0 and not math.isnan(res.mc_bear[idx])

        offset_swing = max(atr50[i] / 7.0, 3 * tick_size)

        # ---- Outside bar / inside bar / IBS / bar direction ----
        ob0 = H(0) > H(1) and L(0) < L(1)
        res.ob[i] = ob0

        if H(0) < H(1) and L(0) > L(1):
            ib0 = True
        elif H(0) < H(1) and L(0) == L(1):
            ib0 = True
        elif H(0) == H(1) and L(0) > L(1):
            ib0 = True
        elif H(0) == H(1) and L(0) == L(1):
            ib0 = True
        else:
            ib0 = False
        res.ib[i] = ib0

        ibs0 = 0.0
        if BR(0) != 0:
            ibs0 = (C(0) - L(0)) / BR(0) * 100
        res.ibs[i] = ibs0

        if C(0) > O(0) and ibs0 >= 50:
            bd0 = 1
        elif C(0) < O(0) and ibs0 <= 50:
            bd0 = -1
        elif C(0) == O(0) and ibs0 > 50:
            bd0 = 1
        elif C(0) == O(0) and ibs0 < 50:
            bd0 = -1
        elif C(0) == O(0) and ibs0 == 50:
            bd0 = BD(1)
        elif C(0) < O(0) and ibs0 > 50:
            bd0 = 1
        elif C(0) > O(0) and ibs0 < 50:
            bd0 = -1
        elif ibs0 == 50:
            bd0 = BD(1)
        else:
            bd0 = BD(1)
        res.bar_dir[i] = bd0

        # ---- Gap / continuation ----
        is_new = is_new_session[i]
        if is_new:
            continue_from_y = False
        if is_new and continue_mc and not (L(1) > H(0) or H(1) < L(0)):
            continue_from_y = True

        # ---- Micro channel ----
        if bsntd[i] > 0 or continue_mc or continue_on_gap:
            if L(1) <= L(0):
                res.mc_bull[i] = (res.mc_bull[i - 1] + 1) if MC_BULL_VALID(1) else 2
            if H(1) >= H(0):
                res.mc_bear[i] = (res.mc_bear[i - 1] + 1) if MC_BEAR_VALID(1) else 2

        # ==== Swing Low ====

        # -- Outside Bar --
        if ob0 or bsntd[i] == 0:
            SL_set(0, L(0) - offset_swing)

            cond_a = (ob0 and BD(0) == 1) or (H(1) < H(0) and L(1) == L(0))
            cond_b = not (
                OBf(1)
                or (BD(1) == -1 and BD(0) == -1)
                or (H(2) < H(1) and L(2) == L(1) and BD(1) == 1)
                or (BD(1) == 1 and L(2) > L(1))
            )
            if cond_a and cond_b:
                SL_reset(1)
            elif ob0 and BD(1) == -1 and BD(0) == -1 and O(0) < C(0):
                SL_reset(1)
            elif OBf(1) and ob0 and BD(1) == -1 and BD(0) == 1:
                SL_reset(1)

            if (
                H(1) < H(0) and L(1) == L(0)
                and not (BD(1) == 1)
                and not (OBf(1) and BD(1) == 1)
                and not (BD(1) == -1 and BD(0) == -1)
                and not (H(2) < H(1) and L(2) == L(1) and BD(1) == 1)
            ):
                SL_reset(1)

            if ob0 and BD(0) == 1 and BD(1) == 1 and O(1) > C(1) and L(2) > C(1):
                SL_reset(1)

            if H(1) < H(0) and L(1) == L(0) and L(2) <= L(1) and BD(0) == -1 and not IBf(1):
                SL_reset(0)

            if H(1) < H(0) and L(1) == L(0) and BD(1) == 1 and L(2) > L(1):
                SL_reset(0)

        # -- Bear CH start --
        if H(1) >= H(0):
            if L(1) > L(0):
                SL_set(0, L(0) - offset_swing)

            cond_a = (
                L(1) <= L(0)
                or (L(1) - BR(0) / ol_div <= L(0) and BD(0) == -1)
                or BD(0) == 1
            )
            cond_b = (
                L(2) > L(1)
                or (BD(1) == -1 and O(1) >= C(1))
                or (BD(1) == 1 and BD(0) == -1 and IBf(0) and L(2) > L(1))
                or bsntd[i] == 1
            )
            if cond_a and cond_b:
                if not (IBf(1) and IBf(0)) and not (L(3) >= L(2) and L(2) <= L(1) and IBf(0)):
                    SL_set(1, L(1) - offset_swing)

                if BD(1) == -1 and bsntd[i] > 1 and not MC_BEAR_VALID(1) and not OBf(1) and not IBf(0):
                    SL_reset(1)

                if L(2) <= L(1) and H(2) <= L(0) and bsntd[i] > 1:
                    SL_reset(1)
                    SL_set(0, L(0) - offset_swing)
            elif L(1) <= L(0) and BD(0) == 1 and not OBf(1):
                SL_set(0, L(0) - offset_swing)

            if L(1) <= L(0) and BD(1) == 1:
                SL_set(0, L(0) - offset_swing)

            if not ib_ignore and O(1) >= C(1) and H(2) < H(1) and H(2) > C(1) and L(2) <= L(1) and IBf(0):
                SL_set(1, L(1) - offset_swing)
                SL_reset(0)

            if H(2) < H(1) and L(2) == L(1) and L(1) > L(0) and BD(0) == -1:
                SL_reset(1)

        # -- Bear CH progression --
        if H(1) >= H(0) and (MC_BEAR_VALID(1) or OBf(1) or bsntd[i] == 1):
            if L(1) > L(0):
                SL_set(0, L(0) - offset_swing)

                cond_c = (
                    L(1) - BR(0) / ol_div > L(0)
                    or BD(0) == 1
                    or (L(1) - BR(0) / ol_div <= L(0) and O(0) < C(0))
                )
                cond_d = not (
                    BD(1) == 1
                    or (O(1) < C(1) and OBf(1))
                    or (L(2) - BR(1) / ol_div <= L(1) and O(1) < C(1))
                )
                cond_e = not (
                    BD(0) == 1 and not OBf(1) and res.ibs[i - 1] > 20
                    and BR(1) / 2 > abs(C(1) - O(1))
                    and L(3) > L(2) and L(2) > L(1)
                    and L(3) - BR(2) / ol_div <= L(2)
                    and L(2) - BR(1) / ol_div <= L(1)
                )
                if cond_c and cond_d and cond_e:
                    SL_reset(1)

                if IBf(1) and res.ibs[i - 1] < 50 and L(1) - BR(0) / ol_div <= L(0):
                    SL_reset(1)

                if IBf(1) and L(2) < L(1):
                    SL_reset(1)

                if bsntd[i] == 1:
                    SL_reset(1)

            if IBf(1) and IBf(0):
                SL_reset(0)

        # ==== Swing High (mirror of Swing Low) ====

        # -- Outside Bar --
        if ob0 or bsntd[i] == 0:
            SH_set(0, H(0) + offset_swing)

            cond_a = (ob0 and BD(0) == -1) or (H(1) == H(0) and L(1) > L(0))
            cond_b = not (
                OBf(1)
                or (BD(1) == 1 and BD(0) == 1)
                or (H(2) == H(1) and L(2) > L(1) and BD(1) == -1)
                or (BD(1) == -1 and H(2) < H(1))
            )
            if cond_a and cond_b:
                SH_reset(1)
            elif ob0 and BD(1) == 1 and BD(0) == 1 and O(0) > C(0):
                SH_reset(1)
            elif OBf(1) and ob0 and BD(1) == 1 and BD(0) == -1:
                SH_reset(1)

            if (
                H(1) == H(0) and L(1) > L(0)
                and not (BD(1) == -1)
                and not (OBf(1) and BD(1) == -1)
                and not (BD(1) == 1 and BD(0) == 1)
                and not (H(2) == H(1) and L(2) > L(1) and BD(1) == -1)
            ):
                SH_reset(1)

            if ob0 and BD(0) == -1 and BD(1) == -1 and O(1) < C(1) and H(2) < C(1):
                SH_reset(1)

            if H(1) == H(0) and L(1) > L(0) and H(2) >= H(1) and BD(0) == 1 and not IBf(1):
                SH_reset(0)

            if H(1) == H(0) and L(1) > L(0) and BD(1) == -1 and H(2) < H(1):
                SH_reset(0)

        # -- Bull CH start --
        if L(1) <= L(0):
            if H(1) < H(0):
                SH_set(0, H(0) + offset_swing)

            cond_a = (
                H(1) >= H(0)
                or (H(1) + BR(0) / ol_div >= H(0) and BD(0) == 1)
                or BD(0) == -1
            )
            cond_b = (
                H(2) < H(1)
                or (BD(1) == 1 and O(1) <= C(1))
                or (BD(1) == -1 and BD(0) == 1 and IBf(0) and H(2) < H(1))
                or bsntd[i] == 1
            )
            if cond_a and cond_b:
                if not (IBf(1) and IBf(0)) and not (H(3) <= H(2) and H(2) >= H(1) and IBf(0)):
                    SH_set(1, H(1) + offset_swing)

                if BD(1) == 1 and bsntd[i] > 1 and not MC_BULL_VALID(1) and not OBf(1) and not IBf(0):
                    SH_reset(1)

                if H(2) >= H(1) and L(2) >= H(0) and bsntd[i] > 1:
                    SH_reset(1)
                    SH_set(0, H(0) + offset_swing)
            elif H(1) >= H(0) and BD(0) == -1 and not OBf(1):
                SH_set(0, H(0) + offset_swing)

            if H(1) >= H(0) and BD(1) == -1:
                SH_set(0, H(0) + offset_swing)

            if not ib_ignore and O(1) <= C(1) and L(2) > L(1) and L(2) < C(1) and H(2) >= H(1) and IBf(0):
                SH_set(1, H(1) + offset_swing)
                SH_reset(0)

            if L(2) > L(1) and H(2) == H(1) and H(1) < H(0) and BD(0) == 1:
                SH_reset(1)

        # -- Bull CH progression --
        if L(1) <= L(0) and (MC_BULL_VALID(1) or OBf(1) or bsntd[i] == 1):
            if H(1) < H(0):
                SH_set(0, H(0) + offset_swing)

                cond_c = (
                    H(1) + BR(0) / ol_div < H(0)
                    or BD(0) == -1
                    or (H(1) + BR(0) / ol_div >= H(0) and O(0) > C(0))
                )
                cond_d = not (
                    BD(1) == -1
                    or (O(1) > C(1) and OBf(1))
                    or (H(2) + BR(1) / ol_div >= H(1) and O(1) > C(1))
                )
                cond_e = not (
                    BD(0) == -1 and not OBf(1) and res.ibs[i - 1] < 80
                    and BR(1) / 2 > abs(C(1) - O(1))
                    and H(3) < H(2) and H(2) < H(1)
                    and H(3) + BR(2) / ol_div >= H(2)
                    and H(2) + BR(1) / ol_div >= H(1)
                )
                if cond_c and cond_d and cond_e:
                    SH_reset(1)

                if IBf(1) and res.ibs[i - 1] > 50 and H(1) + BR(0) / ol_div >= H(0):
                    SH_reset(1)

                if IBf(1) and H(2) > H(1):
                    SH_reset(1)

                if bsntd[i] == 1:
                    SH_reset(1)

            if IBf(1) and IBf(0):
                SH_reset(0)

        # ---- Remove CT SBs (untriggered only) ----
        if ctsb_ignore and SL(1) > 0 and BD(1) == 1 and not IBf(1) and not OBf(1) and L(1) > L(0) and not (ob0 and BD(0) == -1):
            SL_reset(1)
        if ctsb_ignore and SH(1) > 0 and BD(1) == -1 and not IBf(1) and not OBf(1) and H(1) < H(0) and not (ob0 and BD(0) == 1):
            SH_reset(1)

        # ---- Remove IBs (untriggered only) ----
        if ib_ignore and IBf(1) and SL(1) > 0:
            SL_reset(1)
        if ib_ignore and IBf(1) and SH(1) > 0:
            SH_reset(1)
        if ib_ignore and IBf(1) and SL(2) > 0 and L(3) <= L(2) and bsntd[i] > 2:
            SL_reset(2)
        if ib_ignore and IBf(1) and SH(2) > 0 and H(3) >= H(2) and bsntd[i] > 2:
            SH_reset(2)

        # ==== Wedge ====

        def sl_valid(idx):
            return not math.isnan(res.swing_low[idx])

        def sh_valid(idx):
            return not math.isnan(res.swing_high[idx])

        SL0 = 0
        SL1 = _mro(sl_valid, i, 2, lookback)
        SL2 = _mro(sl_valid, i, 3, lookback)

        if (
            SL2 > 0 and SL1 > 0
            and (SL2 <= bsntd[i] or continue_from_y or continue_on_gap)
            and L(1) > L(0) and L(SL2) > L(SL1) and L(SL1) > L(SL0)
            and not (
                (L(SL2) - L(SL1) > sym_fact * (L(SL1) - L(SL0)) and L(SL2) - L(SL1) > avg_range[i])
                or (L(SL1) - L(SL0) > sym_fact * (L(SL2) - L(SL1)) and L(SL1) - L(SL0) > avg_range[i])
            )
            and not (
                (SL2 - SL1 > sym_fact_dist * (SL1 - SL0))
                or ((SL2 - SL1) * sym_fact_dist < SL1 - SL0)
            )
        ):
            res.wedge_bl[i] = L(0)

        SH0 = 0
        SH1 = _mro(sh_valid, i, 2, lookback)
        SH2 = _mro(sh_valid, i, 3, lookback)

        if (
            SH2 > 0 and SH1 > 0
            and (SH2 <= bsntd[i] or continue_from_y or continue_on_gap)
            and H(1) < H(0) and H(SH2) < H(SH1) and H(SH1) < H(SH0)
            and not (
                (H(SH1) - H(SH2) > sym_fact * (H(SH0) - H(SH1)) and H(SH1) - H(SH2) > avg_range[i])
                or (H(SH0) - H(SH1) > sym_fact * (H(SH1) - H(SH2)) and H(SH0) - H(SH1) > avg_range[i])
            )
            and not (
                (SH2 - SH1 > sym_fact_dist * (SH1 - SH0))
                or ((SH2 - SH1) * sym_fact_dist < SH1 - SH0)
            )
        ):
            res.wedge_br[i] = H(0)

        if show_w2l:
            SL0_2L = 0
            SL1_2L = _mro(sl_valid, i, 2, lookback)
            SL2_2L = _mro(sl_valid, i, 3, lookback)
            SL3_2L = _mro(sl_valid, i, 4, lookback)

            if (
                SL3_2L > 0 and SL2_2L > 0 and SL1_2L > 0
                and (SL3_2L <= bsntd[i] or continue_from_y or continue_on_gap)
                and L(1) > L(0)
                and L(SL3_2L) > L(SL2_2L) and L(SL2_2L) > L(SL0_2L) and L(SL2_2L) <= L(SL1_2L)
                and not (
                    (L(SL3_2L) - L(SL2_2L) > sym_fact * (L(SL2_2L) - L(SL0_2L)) and L(SL3_2L) - L(SL2_2L) > avg_range[i])
                    or (L(SL2_2L) - L(SL0_2L) > sym_fact * (L(SL3_2L) - L(SL2_2L)) and L(SL2_2L) - L(SL0_2L) > avg_range[i])
                )
                and not (
                    (SL3_2L - SL2_2L > sym_fact_dist * (SL2_2L - SL0_2L))
                    or ((SL3_2L - SL2_2L) * sym_fact_dist < SL2_2L - SL0_2L)
                )
            ):
                res.wedge_bl[i] = L(0)

            SH0_2L = 0
            SH1_2L = _mro(sh_valid, i, 2, lookback)
            SH2_2L = _mro(sh_valid, i, 3, lookback)
            SH3_2L = _mro(sh_valid, i, 4, lookback)

            if (
                SH3_2L > 0 and SH2_2L > 0 and SH1_2L > 0
                and (SH3_2L <= bsntd[i] or continue_from_y or continue_on_gap)
                and H(1) < H(0)
                and H(SH3_2L) < H(SH2_2L) and H(SH2_2L) < H(SH0_2L) and H(SH2_2L) >= H(SH1_2L)
                and not (
                    (H(SH2_2L) - H(SH3_2L) > sym_fact * (H(SH0_2L) - H(SH2_2L)) and H(SH2_2L) - H(SH3_2L) > avg_range[i])
                    or (H(SH0_2L) - H(SH2_2L) > sym_fact * (H(SH2_2L) - H(SH3_2L)) and H(SH0_2L) - H(SH2_2L) > avg_range[i])
                )
                and not (
                    (SH3_2L - SH2_2L > sym_fact_dist * (SH2_2L - SH0_2L))
                    or ((SH3_2L - SH2_2L) * sym_fact_dist < SH2_2L - SH0_2L)
                )
            ):
                res.wedge_br[i] = H(0)

        # ==== Wedge Signal Bars (latest 3-region SB: Trap/OB + 2BR + Inside Bar) ====
        if show_wedge_sb:
            median0 = (H(0) + L(0)) / 2.0
            ibs0 = res.ibs[i]
            def wv(arr, k):                       # WedgeBL/BR[k] > 0, and that wedge bar is within
                idx = i - k                       # the current session (mirrors the wedge's own
                return idx >= 0 and k <= bsntd[i] and not math.isnan(arr[idx]) and arr[idx] > 0  # SL2<=bsntd gate)
            def sb_set(arr, k):                   # WedgeBLSB/BRSB[k] already fired
                idx = i - k
                return idx >= 0 and not math.isnan(arr[idx])
            def mc_lt7(arr, k):                   # MC_Bear/Bull[k] < 7 (unset = allowed)
                idx = i - k
                return idx < 0 or math.isnan(arr[idx]) or arr[idx] < 7

            # -- Trap / OB --  (current bar traps below the prior 2 bars)
            if (wv(res.wedge_bl, 0) or wv(res.wedge_bl, 1) or wv(res.wedge_bl, 2)) and ibs0 >= signal_bar_ibs \
               and min(L(1), L(2)) > L(0) and H(1) > median0:
                res.wedge_bl_sb[i] = L(0) - 2 * tick_size
            if (wv(res.wedge_br, 0) or wv(res.wedge_br, 1) or wv(res.wedge_br, 2)) and ibs0 <= (100 - signal_bar_ibs) \
               and max(H(1), H(2)) < H(0) and L(1) < median0:
                res.wedge_br_sb[i] = H(0) + 2 * tick_size

            # -- 2BR --  (prior bar traps; current bar does not push lower)
            # NB: Thomas's source guards these with `WedgeBLSB[1]<0.1` / `WedgeBRSB[1]<0.1`
            # (skip a 2BR right after another signal). But his EXPORT fires the 2BR on bars
            # immediately after a signal (validated: 3 consecutive-short cases the guard would
            # wrongly block), so NT does not actually block here. Guard dropped to match the
            # indicator's output exactly (0 new extras over 170 days). CONFIRM WITH THOMAS.
            if ((wv(res.wedge_bl, 1) or wv(res.wedge_bl, 2)) and ibs0 >= signal_bar_ibs
                    and min(L(2), L(3)) > L(1) and L(1) <= L(0) and H(1) + BR(0) / 4 > H(0) and O(1) <= C(0)
                    and O(1) > C(1) and L(2) > C(1) and mc_lt7(res.mc_bear, 1)):
                res.wedge_bl_sb[i] = L(0) - 2 * tick_size
            if ((wv(res.wedge_br, 1) or wv(res.wedge_br, 2)) and ibs0 <= (100 - signal_bar_ibs)
                    and max(H(2), H(3)) < H(1) and H(1) >= H(0) and L(1) - BR(0) / 4 < L(0) and O(1) >= C(0)
                    and O(1) < C(1) and H(2) < C(1) and mc_lt7(res.mc_bull, 1)):
                res.wedge_br_sb[i] = H(0) + 2 * tick_size

            # -- Inside Bar --  (current is an IB; prior bar trapped)
            if (wv(res.wedge_bl, 1) or wv(res.wedge_bl, 2)) and ibs0 >= signal_bar_ibs and res.ib[i] and min(L(2), L(3)) > L(1):
                res.wedge_bl_sb[i] = L(0) - 2 * tick_size
            if (wv(res.wedge_br, 1) or wv(res.wedge_br, 2)) and ibs0 <= (100 - signal_bar_ibs) and res.ib[i] and max(H(2), H(3)) < H(1):
                res.wedge_br_sb[i] = H(0) + 2 * tick_size

    return res


if __name__ == "__main__":
    import random

    random.seed(0)
    n = 500
    px = 4500.0
    o, h, l, c = [], [], [], []
    for _ in range(n):
        move = random.uniform(-2, 2)
        op = px
        cl = px + move
        hi = max(op, cl) + random.uniform(0, 1)
        lo = min(op, cl) - random.uniform(0, 1)
        o.append(op); h.append(hi); l.append(lo); c.append(cl)
        px = cl
    is_new = [False] * n
    for k in range(0, n, 100):
        is_new[k] = True

    result = compute_mywedge(o, h, l, c, tick_size=0.25, is_new_session=is_new)
    longs = sum(1 for v in result.wedge_bl_sb if not math.isnan(v))
    shorts = sum(1 for v in result.wedge_br_sb if not math.isnan(v))
    print(f"smoke test ok: {n} bars, {longs} WedgeBLSB, {shorts} WedgeBRSB signals")
