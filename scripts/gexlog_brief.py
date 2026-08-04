"""Fetch today's GexLog morning brief and normalize it to a day-type tag.

GexLog publishes the morning report ~06:20 AM ET (prior-EOD basis, forecasts the
day). We pull it premarket (~08:00 CT, 30 min before the open) and tag the
gameplan with its FORECAST day-type so P&L can later be bucketed TREND/RANGE/CHOP.
No auth; plain HTTP + a Referer header. Never fatal to the gameplan — on any
failure returns a dict with day_type "unknown".

Endpoints (see the gexlog repo docs/API.md):
  report.php?type=morning                          today's live report
  archive.php?action=report&type=morning&date=D    fallback by date
"""
from __future__ import annotations
import requests

BASE = "https://gexlog.com/dashboard/api"
_H = {"User-Agent": "Mozilla/5.0 (myquant)", "Referer": "https://gexlog.com/dashboard/",
      "Accept": "application/json"}


def _norm_day_type(raw: str) -> str:
    s = (raw or "").lower()
    if "trend" in s:
        return "TREND"
    if "range" in s:
        return "RANGE"
    if "chop" in s or "mixed" in s or "balance" in s:
        return "CHOP"
    return "unknown"


def _norm_signal(raw: str) -> str:
    """GexLog's go/no-go call -> GO / CAUTION / WAIT (the 3 P&L buckets)."""
    s = (raw or "").strip().upper()
    if s.startswith("GO"):
        return "GO"
    if s.startswith("CAUT"):
        return "CAUTION"
    if s.startswith("WAIT"):
        return "WAIT"
    return "unknown"


def _g(d, *path, default=None):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return default
    return d


def fetch(date: str | None = None, timeout: int = 15) -> dict:
    """Return a normalized dict; day_type in {TREND, RANGE, CHOP, unknown}."""
    out = {"signal_bucket": "unknown", "signal": None, "day_type": "unknown",
           "forecast_type": None, "regime": None, "net_gex": None, "gex_flip": None,
           "putWall": None, "callWall": None, "expectedMove": None,
           "generated_at": None, "source": None, "error": None}
    try:
        s = requests.Session()
        s.headers.update(_H)
        if date:
            r = s.get(f"{BASE}/archive.php", params={"action": "report", "type": "morning", "date": date}, timeout=timeout)
        else:
            r = s.get(f"{BASE}/report.php", params={"type": "morning"}, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        if not isinstance(d, dict) or "error" in d:
            out["error"] = "no report"
            return out
        ft = _g(d, "forecast", "type") or _g(d, "forecast", "regime_streak", "day_type")
        sig = _g(d, "guidance", "signal")
        out.update(
            forecast_type=ft, day_type=_norm_day_type(ft),
            signal=sig, signal_bucket=_norm_signal(sig),
            regime=_g(d, "forecast", "factors", "gamma", "value"),
            net_gex=_g(d, "forecast", "factors", "gamma", "net_gex"),
            gex_flip=_g(d, "forecast", "factors", "gamma", "gex_flip"),
            putWall=_g(d, "levels", "putWall"), callWall=_g(d, "levels", "callWall"),
            expectedMove=_g(d, "levels", "expectedMove"),
            generated_at=_g(d, "meta", "generatedAt"),
            source="report.php" if not date else "archive.php")
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:120]
    return out


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(fetch(sys.argv[1] if len(sys.argv) > 1 else None), indent=2))
