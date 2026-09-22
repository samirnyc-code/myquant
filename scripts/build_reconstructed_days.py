"""build_reconstructed_days.py — assemble data/options_sim/reconstructed_days.json from the
per-day replay outputs, for the dashboard calendar's reconstructed-day overlay (the '*' days).

A reconstructed day is a session the live desk MISSED (gateway/NT down at the open) that we
rebuilt from ThetaData per-leg NBBO: entry at the open, live exit rules replayed
(10-min level-accept + 14:45 CT stop), realistic worst-touch fills. It is shown on the
calendar with an asterisk and is DELIBERATELY kept OUT of trades.parquet, so the real
performance tiles (PF/win/expectancy/maxDD) are never polluted by reconstructed fills.

Reads (per date):  data/options_log/replay_<date>_exits.json      (per-trade + total)
                   data/options_log/replay_<date>_dd_breaker.json (intraday DD + breakers)
Writes:            data/options_sim/reconstructed_days.json        (dict keyed by YYYY-MM-DD)

    python scripts/build_reconstructed_days.py --date 20260921
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "options_log"
OUT = ROOT / "data" / "options_sim" / "reconstructed_days.json"


def iso(d8: str) -> str:
    return f"{d8[:4]}-{d8[4:6]}-{d8[6:8]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260921")
    a = ap.parse_args()

    ex = json.loads((LOG / f"replay_{a.date}_exits.json").read_text())
    dd = json.loads((LOG / f"replay_{a.date}_dd_breaker.json").read_text())

    taken = [v for v in ex["verticals"] if v.get("taken")]
    rec = {
        "pnl": round(ex["total_pnl"]),
        "n": len(taken),
        "dd": round(dd["intraday_trough"]),
        "dd_p2t": round(dd["intraday_dd_peak_to_trough"]),
        "breaker_2k": round(dd["breaker_2k"]["pnl"]),
        "breaker_2k_hit": bool(dd["breaker_2k"]["triggered"]),
        "breaker_3k": round(dd["breaker_3k"]["pnl"]),
        "breaker_3k_hit": bool(dd["breaker_3k"]["triggered"]),
        "spot_open": dd.get("spot_open"),
        "spot_close": dd.get("spot_close"),
        "note": ("Reconstructed from ThetaData NBBO (desk was down at the open). Entry at the "
                 "08:31 CT open; live exits replayed (10-min level-acceptance + 14:45 CT stop); "
                 "realistic worst-touch fills. NOT a booked day — excluded from all stat tiles."),
        "trades": [{"strategy": v["id"], "structure": v["struct"], "entry_cr": v["entry_cr"],
                    "exit_et": v["exit_et"], "reason": v["reason"], "pnl": round(v["pnl"])}
                   for v in taken],
    }

    allrec = {}
    if OUT.exists():
        try:
            allrec = json.loads(OUT.read_text())
        except Exception:
            allrec = {}
    allrec[iso(a.date)] = rec
    OUT.write_text(json.dumps(allrec, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  {iso(a.date)}: pnl {rec['pnl']:+,} | n {rec['n']} | intraday DD {rec['dd']:+,} | "
          f"2k {'HIT' if rec['breaker_2k_hit'] else 'no'} {rec['breaker_2k']:+,} | "
          f"3k {'HIT' if rec['breaker_3k_hit'] else 'no'} {rec['breaker_3k']:+,}")


if __name__ == "__main__":
    main()
