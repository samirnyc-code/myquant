"""Fetch today's MenthorQ gamma levels via the DIRECT API and write them to
scratchpad/mq_levels_today.json in the format the gameplan reads (S75).

Replaces the dead QUIN harvester (mq_quin_harvest.py). Same data source the
NQ Daily Brief uses: gamma-levels/{sym}/eod. Runs premarket (08:27 CT, just
before the 08:28 gameplan) so the plan always builds off fresh EOD walls.

Field map (API -> file):
  call_resistance -> cr        call_resistance_0dte -> cr0   gamma_wall_0dte -> gw0
  put_support     -> ps        put_support_0dte     -> ps0   hvl_0dte        -> hvl0
  hvl -> hvl   min_1d -> d1_min   max_1d -> d1_max   gex_1..10 -> gex[]

Run:
  .venv/Scripts/python.exe scripts/mq_levels_fetch.py
"""
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratchpad" / "mq_levels_today.json"
CT = ZoneInfo("America/Chicago")


def map_levels(lv):
    """MenthorQ gamma-levels/eod dict -> the compact {cr,ps,hvl,...} the gameplan uses."""
    def g(k):
        v = lv.get(k)
        return float(v) if isinstance(v, (int, float)) else None
    gex = [g(f"gex_{i}") for i in range(1, 11)]
    return {
        "cr": g("call_resistance"), "ps": g("put_support"), "hvl": g("hvl"),
        "cr0": g("call_resistance_0dte"), "ps0": g("put_support_0dte"),
        "gw0": g("gamma_wall_0dte"), "hvl0": g("hvl_0dte"),
        "d1_min": g("min_1d"), "d1_max": g("max_1d"),
        "gex": [x for x in gex if x is not None],
    }


def main():
    mq = MQ()
    spx_raw = mq.levels("SPX")
    out = map_levels(spx_raw)
    out["_comment"] = "AUTO-FILLED by mq_levels_fetch.py (direct MenthorQ API, NOT QUIN)"
    out["_source_ts"] = spx_raw.get("timestamp")
    out["_fetched_ct"] = dt.datetime.now(CT).strftime("%Y-%m-%d %H:%M:%S CT")
    # ES levels too (the file historically carries an `es` block; gameplan uses SPX)
    try:
        es = map_levels(mq.levels("ES1!"))
        es["_comment"] = "MenthorQ ES1! EOD (direct API)"
        out["es"] = es
    except Exception as e:
        out["es"] = {"_error": str(e)[:80]}

    # ---- FRESHNESS GATE (S75V) ------------------------------------------------
    # MenthorQ publishes EOD levels on their own schedule. If they have not published
    # yet, this endpoint happily returns YESTERDAY'S numbers and everything downstream
    # arms triggers off stale levels with nothing to flag it. The old check in
    # options_healthcheck was tautological - it tested `_fetched_ct startswith today`,
    # which is true by construction because the fetch runs today.
    #
    # The honest test is whether the SOURCE timestamp covers today's session: it must be
    # from the PREVIOUS TRADING DAY's EOD or later. "Did it advance since last fetch" was
    # the first cut, but it false-alarms every Monday: a weekend fetch records Friday's
    # ts, then Monday's fetch sees the same (correct, freshest-possible) Friday ts and
    # refuses the gameplan. MenthorQ does not publish on weekends/holidays — Friday EOD
    # IS the right data for Monday. (2026-07-20 incident.)
    prev_src = None
    if OUT.exists():
        try:
            prev_src = json.loads(OUT.read_text(encoding="utf-8")).get("_source_ts")
        except Exception:
            pass
    src = out.get("_source_ts")
    out["_prev_source_ts"] = prev_src
    out["_source_advanced"] = bool(src and prev_src and str(src) > str(prev_src)) or prev_src is None
    if src:
        try:
            from market_calendar import is_trading_day
            src_date = dt.date.fromisoformat(str(src)[:10])
            prev_td = dt.datetime.now(CT).date() - dt.timedelta(days=1)
            while not is_trading_day(prev_td):
                prev_td -= dt.timedelta(days=1)
            if src_date < prev_td:
                out["_stale_warning"] = (
                    f"source_ts {src} is older than the previous trading day ({prev_td}) - "
                    "MenthorQ has not published levels for the last session")
        except Exception as e:
            # calendar unavailable: fall back to the advance check rather than go blind
            if prev_src and str(src) <= str(prev_src):
                out["_stale_warning"] = (f"source_ts did NOT advance: {src} (previous "
                                         f"{prev_src}) [calendar check failed: {e}]")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
    if out.get("_stale_warning"):
        print(f"  *** STALE: {out['_stale_warning']}")
    print(f"  SPX  CR {out['cr']}  CR0 {out['cr0']}  GW0 {out['gw0']}  "
          f"HVL {out['hvl']}  PS0 {out['ps0']}  PS {out['ps']}")
    print(f"  1-day range {out['d1_min']} - {out['d1_max']}  ·  source {out['_source_ts']}")
    # sanity: all core levels present + ordered (ps <= hvl <= cr)
    core = [out["ps"], out["hvl"], out["cr"]]
    if any(x is None for x in core):
        print("  WARNING: missing core levels (ps/hvl/cr) — check API auth")
    elif not (out["ps"] <= out["hvl"] <= out["cr"]):
        print(f"  WARNING: levels not ordered ps<=hvl<=cr ({core}) — verify")
    return out


if __name__ == "__main__":
    main()
