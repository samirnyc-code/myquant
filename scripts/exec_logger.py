"""exec_logger.py — persist IB's OWN execution record for every fill, forever.

WHY (S112): orders.csv logs `ts_et` = our MACHINE wall-clock at the moment we processed
the fill callback (client-side, +latency, 1s granularity) — NOT the exchange execution
time.  IB carries the real fill time on every `Fill` (`fill.time`, a tz-aware datetime) and
the actual commission on `fill.commissionReport`, but the desk never wrote them, so for past
trades reqExecutions (current session only) can't get them back.  This closes that gap going
forward: one row per fill appended to data/options_log/ib_executions.csv, joinable to
orders.csv on order_id.

Authoritative timestamp = `fill.time` (IB execution time, UTC).  This is what a ThetaData /
OPRA tick alignment should key on — never our ts_et.

Design: DEAD SAFE.  Every call is wrapped so a logging failure can NEVER propagate into the
order-placement path.  Additive: a brand-new file with its own schema; touches nothing else.

Called from the two live fill paths:
  * ib_order_test.marketable -> _audit            (per-leg placement)
  * options_trigger_daemon.place_combo/close_combo (atomic BAG placement)
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_log" / "ib_executions.csv"

HEADER = [
    "logged_utc", "source", "order_id", "perm_id", "exec_id", "local_symbol",
    "side", "shares", "price", "ib_exec_time_utc", "ib_exec_time_raw",
    "exchange", "last_liquidity", "cum_qty", "avg_price",
    "commission", "currency", "realized_pnl",
]


def _iso(t) -> str:
    """fill.time is a tz-aware datetime in ib_async; be tolerant of anything else."""
    if t is None:
        return ""
    if isinstance(t, dt.datetime):
        return t.isoformat()
    return str(t)


def log_fills(trade, source: str = "") -> int:
    """Append every fill on `trade` to ib_executions.csv. Returns rows written.

    NEVER raises — any error is swallowed with a stderr note so order flow is unaffected.
    """
    try:
        fills = list(getattr(trade, "fills", None) or [])
        if not fills:
            return 0
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        rows = []
        for f in fills:
            ex = getattr(f, "execution", None)
            cr = getattr(f, "commissionReport", None)
            con = getattr(f, "contract", None)
            rows.append([
                now, source,
                getattr(ex, "orderId", ""),
                getattr(ex, "permId", ""),
                getattr(ex, "execId", ""),
                getattr(con, "localSymbol", ""),
                getattr(ex, "side", ""),                 # BOT / SLD
                getattr(ex, "shares", ""),
                getattr(ex, "price", ""),
                _iso(getattr(f, "time", None)),          # <- authoritative fill time (UTC)
                getattr(ex, "time", ""),                 # raw IB string (exchange/acct tz)
                getattr(ex, "exchange", ""),
                getattr(ex, "lastLiquidity", ""),
                getattr(ex, "cumQty", ""),
                getattr(ex, "avgPrice", ""),
                getattr(cr, "commission", "") if cr else "",
                getattr(cr, "currency", "") if cr else "",
                getattr(cr, "realizedPNL", "") if cr else "",
            ])
        new = not OUT.exists()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with open(OUT, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(HEADER)
            w.writerows(rows)
        return len(rows)
    except Exception as e:                               # never break the order path
        try:
            import sys
            print(f"  [exec_logger] non-fatal: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        except Exception:
            pass
        return 0
