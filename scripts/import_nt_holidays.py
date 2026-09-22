"""Import US market holidays from NinjaTrader's Trading Hours template.

Source of truth: NT8 'CBOE US Index Futures RTH.xml' (the SPX/XSP cash-session
calendar). Extracts full closures + early-close (partial) days into a JSON the
options sim can consult for a holiday guard.

This ONLY writes a data file (data/options_sim/market_holidays.json). It does NOT
touch any strategy/daemon. Re-run any time the NT template is updated.

  .venv/Scripts/python.exe scripts/import_nt_holidays.py
"""
from __future__ import annotations
import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NT_TH = Path.home() / "Documents" / "NinjaTrader 8" / "templates" / "TradingHours"
SRC = NT_TH / "CBOE US Index Futures RTH.xml"
OUT = ROOT / "data" / "options_sim" / "market_holidays.json"


def _date(node: ET.Element) -> str | None:
    d = node.findtext("Date")
    return d.split("T")[0] if d else None


def main() -> int:
    if not SRC.exists():
        print(f"NT template not found: {SRC}")
        return 1
    tree = ET.parse(SRC)
    root = tree.getroot()

    full, early = [], []
    for h in root.iter("Holiday"):
        d = _date(h)
        if d:
            full.append({"date": d, "desc": (h.findtext("Description") or "").strip()})
    for p in root.iter("PartialHoliday"):
        d = _date(p)
        if d:
            early.append({
                "date": d,
                "desc": (p.findtext("Description") or "").strip(),
                "early_end": (p.findtext("IsEarlyEnd") or "").strip().lower() == "true",
                "late_begin": (p.findtext("IsLateBegin") or "").strip().lower() == "true",
            })
    full.sort(key=lambda x: x["date"])
    early.sort(key=lambda x: x["date"])

    payload = {
        "source": "NT8 templates/TradingHours/CBOE US Index Futures RTH.xml",
        "imported_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "note": "US index cash-session calendar (SPX/XSP). full_close = market closed; "
                "early_close = shortened session (13:00 ET typical).",
        "full_close": [h["date"] for h in full],
        "early_close": [e["date"] for e in early],
        "full_close_detail": full,
        "early_close_detail": early,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    yrs = sorted({d[:4] for d in payload["full_close"]})
    print(f"source : {SRC.name}")
    print(f"written: {OUT.relative_to(ROOT)}")
    print(f"full closures : {len(full)}  ({yrs[0]}..{yrs[-1]})")
    print(f"early closes  : {len(early)}")
    today = dt.date.today().isoformat()
    upcoming = [h for h in full if h["date"] >= today][:6]
    print(f"\ntoday = {today}  -> full-closure today? "
          f"{'YES' if today in payload['full_close'] else 'no'}")
    print("next full closures:")
    for h in upcoming:
        print(f"  {h['date']}  {h['desc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
