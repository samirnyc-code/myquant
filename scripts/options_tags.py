"""Trade tagging helpers (S75) — derive the analytic dimensions we slice P&L by.

`bias` (bullish / bearish / neutral) is fully derivable from the strategy + legs,
so we compute it on the fly (no schema migration). `gamma_regime` is NOT derivable
after the fact (needs spot-vs-HVL at entry) — the daemon records it at fill; older
trades are backfilled.
"""


def derive_bias(strategy_id, legs=None):
    """Directional lean of the position at entry."""
    s = (strategy_id or "").lower()
    if "bear" in s:
        return "bearish"
    if "bull" in s or "bps" in s or s.startswith("stmr"):
        return "bullish"
    if "cr" in s and "fade" in s:            # fade Call Resistance = bet price falls
        return "bearish"
    if "ps" in s and "fade" in s:            # fade Put Support = bet price holds/bounces
        return "bullish"
    if "straddle" in s or "strangle" in s:   # long vol — non-directional
        return "neutral"
    if "condor" in s or "fly" in s or "butterfly" in s or "cal" in s:
        return "neutral"                     # range / pin / calendar
    if "sell_0dte" in s or "gamma" in s:     # credit spread — side decides lean
        rights = {l.get("right") for l in legs} if legs else set()
        if rights == {"P"}:
            return "bullish"                 # put credit spread: want price up/stable
        if rights == {"C"}:
            return "bearish"                 # call credit spread: want price down/stable
        return "neutral"
    return "neutral"


def bias_of_row(row):
    """From a trades.parquet row (handles legs stored as JSON text)."""
    import json
    legs = None
    lg = row.get("legs") if hasattr(row, "get") else row["legs"]
    if isinstance(lg, str):
        try:
            legs = json.loads(lg)
        except Exception:
            legs = None
    elif isinstance(lg, list):
        legs = lg
    sid = row.get("strategy_id") if hasattr(row, "get") else row["strategy_id"]
    return derive_bias(sid, legs)
