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
           "emLower": None, "emUpper": None, "current": None,
           "risk_level": None, "confidence": None, "flip_proximity": None,
           "borderline_regime": None, "streak_label": None,
           "catalysts_today": [], "high_impact_today": 0,
           "playbook_wait": False, "playbook": {}, "pivots": {},
           "gap_pct": None, "gap_note": None, "calendar_note": None,
           "stale_risk": None, "es_premarket": None, "rsi_14": None,
           "corr_putWall": None, "corr_callWall": None,
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
            emLower=_g(d, "levels", "emLower"), emUpper=_g(d, "levels", "emUpper"),
            current=_g(d, "levels", "current"),
            risk_level=_g(d, "risk", "level"),
            confidence=_g(d, "forecast", "confidence"),
            flip_proximity=_g(d, "forecast", "factors", "gamma", "flip_proximity"),
            borderline_regime=_g(d, "forecast", "factors", "gamma", "borderline_regime"),
            streak_label=_g(d, "forecast", "regime_streak", "label"),
            catalysts_today=[c for c in (_g(d, "catalysts", "today", default=[]) or [])
                             if isinstance(c, dict)][:8],
            high_impact_today=sum(1 for c in (_g(d, "catalysts", "today", default=[]) or [])
                                  if isinstance(c, dict) and c.get("impact") == "high"),
            playbook_wait=any("wait" in ((p.get("trigger") or "") + (p.get("bias") or "")).lower()
                              for p in (d.get("playbook") or {}).values() if isinstance(p, dict)),
            playbook={k: {"scenario": p.get("scenario"), "trigger": p.get("trigger"),
                          "bias": (p.get("bias") or "")[:300]}
                      for k, p in (d.get("playbook") or {}).items() if isinstance(p, dict)},
            pivots={k: _g(d, "levels", k) for k in ("r2", "r1", "s1", "s2")},
            gap_pct=_g(d, "forecast", "factors", "gap", "percent"),
            gap_note=_g(d, "forecast", "factors", "gap", "value"),
            calendar_note=_g(d, "forecast", "factors", "calendar", "value"),
            stale_risk=_g(d, "regime_caveat", "stale_risk"),
            es_premarket=_g(d, "market", "es", "price"),
            rsi_14=_g(d, "market_context", "technical", "rsi_14"),
            generated_at=_g(d, "meta", "generatedAt"),
            source="report.php" if not date else "archive.php")
        # corrected walls from the per-strike profile (net-GEX method — the fix we
        # proved on 08-03 when the published put wall degenerated to spot):
        prof = _g(d, "forecast", "factors", "gamma", "gex_profile", default=[]) or []
        spot0 = out.get("current")
        if prof and spot0:
            below = [s for s in prof if s.get("strike", 0) < spot0 and s.get("net_gex") is not None]
            above = [s for s in prof if s.get("strike", 0) > spot0 and s.get("net_gex") is not None]
            if below:
                out["corr_putWall"] = min(below, key=lambda s: s["net_gex"])["strike"]
            if above:
                out["corr_callWall"] = max(above, key=lambda s: s["net_gex"])["strike"]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:120]
    return out


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(fetch(sys.argv[1] if len(sys.argv) > 1 else None), indent=2))
