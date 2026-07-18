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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
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
