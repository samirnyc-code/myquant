"""General options metrics (S75) — P&L-at-expiry, POP, EV, P(max loss) for ANY
multi-leg structure (vertical / butterfly / straddle / calendar-ish), from the
trade's legs + entry net credit. Used by the live marker and the trade cards so
the numbers agree everywhere.

Distribution of the underlying at expiry: Normal(spot_now, σ), where σ = today's
MenthorQ 1-day expected-move half-range scaled to the trade's time-to-expiry
(√sessions). Approximate but consistent with the gameplan; labeled as such.
"""
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")


def intrinsic(right, strike, S):
    return max(0.0, S - strike) if right == "C" else max(0.0, strike - S)


def pnl_at(legs, credit, S):
    """Position P&L in $ at underlying S at expiry. credit = entry net (>0 credit
    received, <0 debit paid). Long legs add value, short legs subtract."""
    v = 0.0
    for l in legs:
        sign = 1 if l["side"] == "buy" else -1
        v += sign * intrinsic(l["right"], float(l["strike"]), S) * int(l.get("qty", 1))
    return (float(credit) + v) * 100.0


def _npdf(x, mu, s):
    return math.exp(-0.5 * ((x - mu) / s) ** 2) / (s * math.sqrt(2 * math.pi))


def metrics(legs, credit, spot, sigma, grid=500):
    """POP / EV / P(max loss) / max gain-loss for the structure, S~N(spot, sigma)."""
    lo, hi = spot - 4 * sigma, spot + 4 * sigma
    step = (hi - lo) / grid
    Ss = [lo + i * step for i in range(grid + 1)]
    pnls = [pnl_at(legs, credit, S) for S in Ss]
    minp, maxp = min(pnls), max(pnls)
    tol = abs(minp) * 0.02 + 1.0
    pop = ev = pml = z = 0.0
    for S, p in zip(Ss, pnls):
        w = _npdf(S, spot, sigma) * step
        z += w
        ev += p * w
        if p > 0:
            pop += w
        if p <= minp + tol:
            pml += w
    z = z or 1.0
    return dict(pop=pop / z, ev=ev / z, p_maxloss=pml / z,
                max_gain=round(maxp), max_loss=round(minp))


def daily_sigma(date):
    """Today's 1-day expected-move half-range from the gameplan (points)."""
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return None
    gp = json.loads(f.read_text(encoding="utf-8"))
    lo, hi = gp.get("d1_min"), gp.get("d1_max")
    return (hi - lo) / 2 if (lo and hi) else None


def sessions_to_expiry(expiry, now_ct):
    """Trading-session count from now to the expiry 15:00 CT close (fraction of
    today remaining + subsequent weekdays through expiry)."""
    exd = dt.datetime.strptime(expiry, "%Y%m%d").date()
    today = now_ct.date()
    op = now_ct.replace(hour=8, minute=30, second=0, microsecond=0)
    cl = now_ct.replace(hour=15, minute=0, second=0, microsecond=0)
    today_frac = 1.0 if now_ct <= op else 0.0 if now_ct >= cl else (cl - now_ct) / (cl - op)
    if exd <= today:
        return max(0.02, today_frac)
    full = sum(1 for i in range(1, (exd - today).days + 1)
               if (today + dt.timedelta(days=i)).weekday() < 5)
    return max(0.02, today_frac + full)


def sigma_to_expiry(date, expiry, now_ct):
    ds = daily_sigma(date)
    if not ds:
        return None
    return ds * math.sqrt(sessions_to_expiry(expiry, now_ct))


def live_metrics(legs, credit, spot, date, now_ct):
    """Convenience: metrics for a trade given its legs, entry credit, current spot,
    the gameplan date (for daily σ) and now. Returns None if σ unavailable."""
    expiry = max(l["expiry"] for l in legs)
    sig = sigma_to_expiry(date, expiry, now_ct)
    if not sig or not spot:
        return None
    m = metrics(legs, credit, spot, sig)
    m["sigma"] = round(sig, 1)
    return m
