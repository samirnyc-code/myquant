"""market_calendar.py — US market holidays and session state, computed not hardcoded.

Every holiday here is DERIVED from its rule (nth weekday of the month, Easter-relative,
weekend-observance shifts), so the calendar never expires. A hardcoded list is a silent
time bomb: it works until the year it doesn't, and then every session check is wrong on
exactly the days that matter most.

Covers CME equity-index futures (ES) and Cboe index options (SPX/SPXW):
  * full closures       — no trading at all
  * early closes        — 12:00 CT for futures, 12:15 CT for SPX options
  * the daily halt      — 16:00-17:00 CT
  * the Sunday reopen   — 17:00 CT

    python scripts/market_calendar.py            # this year's calendar
    python scripts/market_calendar.py 2027
"""
from __future__ import annotations

import datetime as dt
import sys


# ---------------------------------------------------------------- holiday rules
def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th `weekday` (Mon=0) of month; n=-1 means the LAST one."""
    if n > 0:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    nxt = dt.date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year: int) -> dt.date:
    """Anonymous Gregorian algorithm — Good Friday is Easter minus two days."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def _observed(d: dt.date) -> dt.date:
    """Fixed-date holidays shift: Saturday -> Friday before, Sunday -> Monday after."""
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


def holidays(year: int) -> dict[dt.date, str]:
    """Full closures for US equity/index markets."""
    h = {
        _observed(dt.date(year, 1, 1)): "New Year's Day",
        _nth_weekday(year, 1, 0, 3): "Martin Luther King Jr. Day",
        _nth_weekday(year, 2, 0, 3): "Presidents' Day",
        _easter(year) - dt.timedelta(days=2): "Good Friday",
        _nth_weekday(year, 5, 0, -1): "Memorial Day",
        _observed(dt.date(year, 6, 19)): "Juneteenth",
        _observed(dt.date(year, 7, 4)): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        _nth_weekday(year, 11, 3, 4): "Thanksgiving",
        _observed(dt.date(year, 12, 25)): "Christmas Day",
    }
    return h


def early_closes(year: int) -> dict[dt.date, str]:
    """Half days — futures close 12:00 CT, SPX options 12:15 CT.

    These matter more than they look: an early close means the desk's 15:00 CT flat-by
    rule and the 15:15/15:20 postmortem+EOD jobs are all running AFTER the market shut,
    and the sim daemon's 14:59 rule never fires at all.
    """
    out = {}
    jul4 = _observed(dt.date(year, 7, 4))
    if jul4.weekday() < 5 and jul4.day == 4:          # only when the 4th itself is a weekday
        prev = jul4 - dt.timedelta(days=1)
        if prev.weekday() < 5:
            out[prev] = "July 3rd (half day)"
    tg = _nth_weekday(year, 11, 3, 4)
    out[tg + dt.timedelta(days=1)] = "Day after Thanksgiving (half day)"
    xmas = dt.date(year, 12, 24)
    if xmas.weekday() < 5:
        out[xmas] = "Christmas Eve (half day)"
    return out


def day_type(d: dt.date) -> tuple[str, str]:
    """('holiday'|'early'|'weekend'|'normal', label)"""
    if d.weekday() >= 5:
        return "weekend", d.strftime("%A")
    h = holidays(d.year)
    if d in h:
        return "holiday", h[d]
    e = early_closes(d.year)
    if d in e:
        return "early", e[d]
    return "normal", ""


def is_trading_day(d: dt.date) -> bool:
    return day_type(d)[0] in ("normal", "early")


def prev_trading_day(d: dt.date) -> dt.date:
    x = d - dt.timedelta(days=1)
    while not is_trading_day(x):
        x -= dt.timedelta(days=1)
    return x


def next_trading_day(d: dt.date) -> dt.date:
    x = d + dt.timedelta(days=1)
    while not is_trading_day(x):
        x += dt.timedelta(days=1)
    return x


# ---------------------------------------------------------------- session state
def futures_state(now: dt.datetime) -> tuple[str, str]:
    """('open'|'halt'|'closed', reason) for ES on Globex, in CHICAGO time.

    Globex runs Sun 17:00 -> Fri 16:00 CT with a 16:00-17:00 daily halt. A holiday
    closes the CASH session; the overnight session into a holiday still trades, so the
    honest test is on the session's own date.
    """
    d, t = now.date(), now.time()
    kind, label = day_type(d)

    if kind == "holiday":
        return "closed", label
    if t >= dt.time(17, 0):                    # evening: session for the NEXT day
        nxt = d + dt.timedelta(days=1)
        k2, l2 = day_type(nxt)
        if k2 == "holiday":
            return "closed", f"eve of {l2}"
        if nxt.weekday() == 5:                 # Friday evening -> weekend
            return "closed", "weekend"
        return "open", "ETH"
    if kind == "weekend":
        return "closed", label
    if kind == "early" and t >= dt.time(12, 0):
        return "closed", label
    if dt.time(16, 0) <= t < dt.time(17, 0):
        return "halt", "daily maintenance halt"
    if d.weekday() == 4 and t >= dt.time(16, 0):
        return "closed", "weekend"
    return "open", "RTH" if dt.time(8, 30) <= t < dt.time(15, 15) else "ETH"


def options_state(now: dt.datetime) -> tuple[str, str]:
    """('RTH'|'GTH'|'closed', reason) for SPX/SPXW, CHICAGO time.
    RTH 08:30-15:00 (15 min before ES), GTH 19:00-08:15."""
    d, t = now.date(), now.time()
    kind, label = day_type(d)
    if kind == "holiday":
        return "closed", label
    close = dt.time(12, 15) if kind == "early" else dt.time(15, 0)
    if kind != "weekend" and dt.time(8, 30) <= t < close:
        return "RTH", label or "regular"
    if t >= dt.time(19, 0):
        nxt = d + dt.timedelta(days=1)
        if is_trading_day(nxt):
            return "GTH", "overnight"
        return "closed", "no session tomorrow"
    if t < dt.time(8, 15) and is_trading_day(d):
        return "GTH", "overnight"
    return "closed", label or "outside session"


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else dt.date.today().year
    print(f"\nUS market calendar {year}\n" + "=" * 46)
    print("\nFULL CLOSURES")
    for d, name in sorted(holidays(year).items()):
        print(f"  {d}  {d:%a}  {name}")
    print("\nEARLY CLOSES (futures 12:00 CT · SPX options 12:15 CT)")
    for d, name in sorted(early_closes(year).items()):
        print(f"  {d}  {d:%a}  {name}")
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        now = dt.datetime.utcnow() - dt.timedelta(hours=5)
    fs, fr = futures_state(now)
    os_, orr = options_state(now)
    print(f"\nNOW  {now:%Y-%m-%d %H:%M} CT ({now:%A})")
    print(f"  day      : {day_type(now.date())[0]} {day_type(now.date())[1]}")
    print(f"  futures  : {fs}  ({fr})")
    print(f"  options  : {os_}  ({orr})")
    print(f"  next trading day: {next_trading_day(now.date())}\n")


if __name__ == "__main__":
    main()
