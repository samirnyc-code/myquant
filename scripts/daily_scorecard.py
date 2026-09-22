"""daily_scorecard.py — snapshot each day's process pass/fail into a permanent record.

#3 (2026-07-20): a visual history of the days so you can see, weeks later, WHICH
processes failed on WHICH day. The live timeline only shows NOW; this freezes the day.

Runs once near the end of the day (after the halt jobs), reads the live timeline, and
writes one immutable row-per-process file:  data/_catalog/scorecard/YYYY-MM-DD.json
Mission Control /scorecard renders these as a process × day grid (green ✓ / red ✗ / grey).

    python scripts/daily_scorecard.py            # snapshot today
    python scripts/daily_scorecard.py --date 2026-07-20
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "_catalog" / "scorecard"


def snapshot(date: str) -> dict:
    """Read the live timeline and reduce each process to pass/fail for the day."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8590/timeline.json", timeout=15) as r:
            tl = json.loads(r.read())
    except Exception as e:
        return {"date": date, "error": f"timeline unreachable: {type(e).__name__}", "items": []}
    items = []
    for ph in tl.get("phases", []):
        for it in ph.get("items", []):
            items.append({
                "id": it["id"], "title": it["title"], "phase": ph["key"],
                "ct": it.get("ct", ""),
                "ok": it.get("ok_today"),          # True / False / None (didn't run)
                "state": it.get("state"),
                "detail": (it.get("detail") or "")[:160],
                "paused": bool(it.get("paused")),
            })
    n_ok = sum(1 for i in items if i["ok"] is True)
    n_bad = sum(1 for i in items if i["ok"] is False)
    return {"date": date, "captured_at": dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M CT"),
            "n_ok": n_ok, "n_bad": n_bad, "n_total": len(items), "items": items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today CT)")
    a = ap.parse_args()
    date = a.date or dt.datetime.now(ZoneInfo("America/Chicago")).date().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    snap = snapshot(date)
    (OUT / f"{date}.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")
    print(f"scorecard {date}: {snap.get('n_ok','?')} ok / {snap.get('n_bad','?')} failed "
          f"/ {snap.get('n_total','?')} total -> {OUT / (date + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
