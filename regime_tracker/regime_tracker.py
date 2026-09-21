"""Bull / Bear / Trading-range regime classifier -- Market Structure.pdf rules.

The document's word is "relevant", and what is relevant depends on the state.

  In a TREND, the relevant level in the trend's own direction is the EXTREME of
  the trend -- the highest high an uptrend has reached, the lowest low a
  downtrend has reached. It ratchets and never retreats, so a BOS only fires
  when the trend actually makes new ground. The relevant level on the other side
  is the pullback that came immediately before the last BOS: the higher low in
  an uptrend, the lower high in a downtrend. That is the ChoCh level.

  In a RANGE there is no trend and therefore no extreme, so the relevant levels
  are simply the last swing high and the last swing low.

      state   break above relevant high   break below relevant low
      -----   --------------------------  ------------------------
      Range   BOS    -> Bull*             BOS    -> Bear*
      Bull    BOS    -> stays Bull        ChoCh  -> Range
      Bear    ChoCh  -> Range             BOS    -> stays Bear

  * leaving a range needs BOTH halves of the structure, not just the break:
    upward also requires a higher low to already be in place, downward a lower
    high. Otherwise the range has merely widened. Without this a session could
    be called a downtrend on its second bar, off one low and no high at all.

BOS is a CONTINUATION signal -- taking out the last relevant high in an uptrend
confirms the trend is healthy, it does not end it. Only a ChoCh ends a trend,
and every ChoCh returns to a trading range, which a session also opens in.

Major pivots are the ones the structure is actually read from: each trend
extreme, and each pullback promoted to the relevant HL/LH by a BOS. Everything
else is a minor wiggle inside a leg -- plotted for context, never structural.

Breaks are measured against raw bar highs/lows, so a plain continuation bar that
never becomes a pivot itself still counts.
"""
import math

BULL, BEAR, RANGE = "Bull", "Bear", "Range"


class RegimeResult:
    def __init__(self, n):
        self.regime = [RANGE] * n
        # bar indices where the regime label actually changes (for chart annotation)
        self.change_points = []  # list of (index, new_regime)
        # every mywedge pivot, tagged -- majors carry the structure, minors are context
        self.pivot_lows = []   # list of (index, price, is_major)
        self.pivot_highs = []  # list of (index, price, is_major)
        # structural events, for annotating the chart / auditing a call
        self.events = []  # list of (index, "BOS"|"ChoCh", "up"|"down", level)


def compute_regime(swing_low, swing_high, low, high, bar_dir=None):
    """swing_low/swing_high: compute_mywedge()'s output arrays (NaN except at
    pivot bars). low/high: the same bars' raw OHLC low/high, used both for pivot
    prices and for break detection (the swing arrays hold an offset stop level,
    not the pivot price itself).

    bar_dir: mywedge's res.bar_dir (1 bullish, -1 bearish), consulted to order
    the two extremes within a bar -- a bullish bar is taken to have made its low
    first, a bearish one its high first."""
    n = len(swing_low)
    if not (len(swing_high) == len(low) == len(high) == n):
        raise ValueError("swing_low/swing_high/low/high must be same length")
    if bar_dir is None:
        bar_dir = [1] * n

    res = RegimeResult(n)

    trend = RANGE
    zz = []                       # alternating swing sequence (index, kind, price)
    major_low, major_high = set(), set()

    # The relevant level in the trend's direction is the top of the last
    # COMPLETED leg. After a BOS the trend is mid-leg and has no relevant level
    # yet (`bos_level` is None); the leg's extreme is tracked in `leg`, and the
    # pullback that ends the leg is what promotes it. So exactly one BOS fires
    # per leg, and because each leg tops beyond the last, it is the trend extreme.
    bos_level = None
    leg = leg_i = None            # extreme of the leg in progress
    counter = counter_i = None    # relevant HL (Bull) / LH (Bear): the ChoCh level
    cand = cand_i = None          # pullback extreme since the last BOS

    def tips(kind, count=2):
        out = []
        for idx, k, price in reversed(zz):
            if k == kind:
                out.append((idx, price))
                if len(out) == count:
                    break
        return out

    def ref(kind):
        t = tips(kind, 1)
        return t[0][1] if t else None

    def higher_low():
        t = tips("L")
        return len(t) == 2 and t[0][1] > t[1][1]

    def lower_high():
        t = tips("H")
        return len(t) == 2 and t[0][1] < t[1][1]

    def set_trend(i, new_trend):
        nonlocal trend
        if new_trend != trend:
            trend = new_trend
            res.change_points.append((i, new_trend))

    def push(i, kind, price):
        """Fold a pivot into the swing sequence. A same-kind pivot does not
        extend it -- the leg simply ran further, so the tip moves to the more
        extreme point and the other is a minor wiggle inside that leg."""
        if zz and zz[-1][1] == kind:
            if (price > zz[-1][2]) if kind == "H" else (price < zz[-1][2]):
                zz[-1] = (i, kind, price)
        else:
            zz.append((i, kind, price))

    def enter(i, new_trend, level):
        """Leave the range: the swing on the far side is the relevant HL/LH."""
        nonlocal bos_level, leg, leg_i, counter, counter_i, cand, cand_i
        t = tips("L" if new_trend is BULL else "H", 1)
        if t:
            counter_i, counter = t[0]
            (major_low if new_trend is BULL else major_high).add(counter_i)
        bos_level = None            # mid-leg: nothing relevant to break yet
        leg, leg_i = level, i
        cand = cand_i = None
        set_trend(i, new_trend)

    def bos(i, direction, level):
        """Trend continuation: the pullback that came before this break becomes
        the new relevant HL/LH, and a fresh leg starts."""
        nonlocal bos_level, leg, leg_i, counter, counter_i, cand, cand_i
        res.events.append((i, "BOS", direction, bos_level))
        if cand_i is not None:
            counter, counter_i = cand, cand_i
            (major_low if direction == "up" else major_high).add(cand_i)
        bos_level = None
        leg, leg_i = level, i
        cand = cand_i = None

    for i in range(n):
        lp, hp = low[i], high[i]
        is_low = not math.isnan(swing_low[i])
        is_high = not math.isnan(swing_high[i])
        low_first = bar_dir[i] >= 0
        sides = ["L", "H"] if low_first else ["H", "L"]

        # --- 1. breaks, on raw price, against the relevant levels as they stand
        #        before this bar's own pivots can move them ---
        for side in sides:
            if trend == RANGE:
                # The pullback has to be there before the break can mean
                # anything: to turn up, the last completed swing must be the
                # LOW that will serve as the higher low, and the break clears
                # the high standing before it. If the last swing is still a
                # high, the leg is simply running -- no new structure yet.
                tip = zz[-1][1] if zz else None
                rh, rl = ref("H"), ref("L")
                if side == "H" and tip == "L" and rh is not None and hp > rh:
                    res.events.append((i, "BOS", "up", rh))
                    if higher_low():
                        enter(i, BULL, hp)
                elif side == "L" and tip == "H" and rl is not None and lp < rl:
                    res.events.append((i, "BOS", "down", rl))
                    if lower_high():
                        enter(i, BEAR, lp)
            elif trend == BULL:
                if side == "L" and counter is not None and lp < counter:
                    res.events.append((i, "ChoCh", "down", counter))
                    bos_level = None
                    set_trend(i, RANGE)
                elif side == "H" and bos_level is not None and hp > bos_level:
                    bos(i, "up", hp)
            elif trend == BEAR:
                if side == "H" and counter is not None and hp > counter:
                    res.events.append((i, "ChoCh", "up", counter))
                    bos_level = None
                    set_trend(i, RANGE)
                elif side == "L" and bos_level is not None and lp < bos_level:
                    bos(i, "down", lp)

        # while a leg is still running, its extreme keeps moving
        if leg is not None and bos_level is None:
            if trend == BULL and hp > leg:
                leg, leg_i = hp, i
            elif trend == BEAR and lp < leg:
                leg, leg_i = lp, i

        # --- 2. fold this bar's pivots in, and keep the pullback candidate ---
        order = []
        if is_low and is_high:
            order = [("L", lp), ("H", hp)] if low_first else [("H", hp), ("L", lp)]
        elif is_low:
            order = [("L", lp)]
        elif is_high:
            order = [("H", hp)]
        for kind, price in order:
            push(i, kind, price)
            if kind == "L":
                if trend == BULL:
                    # the pullback ends the leg: its top is now the relevant high
                    if bos_level is None and leg is not None:
                        bos_level = leg
                        major_high.add(leg_i)
                    if cand is None or price < cand:
                        cand, cand_i = price, i
            else:
                if trend == BEAR:
                    if bos_level is None and leg is not None:
                        bos_level = leg
                        major_low.add(leg_i)
                    if cand is None or price > cand:
                        cand, cand_i = price, i

    for i in range(n):
        if not math.isnan(swing_low[i]):
            res.pivot_lows.append((i, low[i], i in major_low))
        if not math.isnan(swing_high[i]):
            res.pivot_highs.append((i, high[i], i in major_high))

    state = RANGE
    changes = dict(res.change_points)
    for i in range(n):
        if i in changes:
            state = changes[i]
        res.regime[i] = state

    return res
