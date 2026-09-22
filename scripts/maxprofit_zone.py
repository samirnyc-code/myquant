"""maxprofit_zone.py — the 0DTE book's max-profit settlement zone.

ZONE = [highest short PUT strike, lowest short CALL strike] across the open book.
Every premium-book leg is a vertical, so INSIDE this band every short expires OTM
and the book keeps FULL credit — a true max-profit plateau (not a single pin).
Below the low edge the fattest short-put spread goes ITM first; above the high edge
the fattest short-call spread goes ITM first.

Two uses:
  * live: "where must SPX settle today for max profit" (+ are we currently in-zone).
  * SNAPSHOT: append a timestamped row to a dated CSV so the S114 sandbox can A/B
    zone-anchored EXIT strategies (bank at X% of max, exit on edge touch vs
    acceptance, delta-hedge at edge) against the current 10-min-acceptance rule.

Reads data/options_log/trades.parquet (SPX book) + data/options_sim/live.json (spot).
Read-only except --snapshot (append-only to a dated CSV). Library-usable: import
compute_zone(open_df).

CLI:
  .venv/Scripts/python.exe scripts/maxprofit_zone.py                 # today, open book
  .venv/Scripts/python.exe scripts/maxprofit_zone.py --date 20260908
  .venv/Scripts/python.exe scripts/maxprofit_zone.py --all-entries   # every entry that day
  .venv/Scripts/python.exe scripts/maxprofit_zone.py --snapshot      # + append dated CSV row
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
LIVE = ROOT / "data" / "options_sim" / "live.json"
OUT = ROOT / "data" / "options_sim"


def _legs(v):
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []
    return []


def short_legs(trades: pd.DataFrame):
    """[(right C/P, strike, strategy, credit)] for every SOLD leg in the frame."""
    out = []
    for _, r in trades.iterrows():
        for lg in _legs(r.get("legs")):
            if str(lg.get("side")) == "sell":
                out.append(((lg.get("right") or "").upper(), float(lg.get("strike")),
                            r.get("strategy_id"), r.get("credit")))
    return out


def compute_zone(trades: pd.DataFrame) -> dict:
    """Max-profit zone from a frame of positions (each row a vertical/structure)."""
    shorts = short_legs(trades)
    puts = [(k, s) for rt, k, s, c in shorts if rt == "P"]
    calls = [(k, s) for rt, k, s, c in shorts if rt == "C"]
    lo = max((k for k, s in puts), default=None)          # highest short put = downside edge
    hi = min((k for k, s in calls), default=None)         # lowest short call = upside edge
    total_credit = sum(float(c) for rt, k, s, c in shorts if c is not None)
    return {
        "n_positions": int(len(trades)),
        "n_short_puts": len(puts), "n_short_calls": len(calls),
        "zone_low": lo, "zone_high": hi,
        "zone_width": (hi - lo) if (lo is not None and hi is not None) else None,
        "low_edge_strategy": max(puts, default=(None, None))[1] if puts else None,
        "high_edge_strategy": min(calls, default=(None, None))[1] if calls else None,
        "total_credit": round(total_credit, 2),
        "put_shorts": sorted(puts, reverse=True),
        "call_shorts": sorted(calls),
    }


def live_spot():
    if not LIVE.exists():
        return None, None
    try:
        d = json.loads(LIVE.read_text())
        return d.get("spx"), d.get("ts_et")
    except Exception:
        return None, None


def _norm_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.replace("-", "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def main() -> int:
    ap = argparse.ArgumentParser(description="0DTE max-profit settlement zone")
    ap.add_argument("--date", help="trade date (YYYYMMDD or YYYY-MM-DD); default today (ET from live.json)")
    ap.add_argument("--all-entries", action="store_true",
                    help="use every entry that day, not just currently-open positions")
    ap.add_argument("--snapshot", action="store_true", help="append a timestamped row to the dated CSV")
    a = ap.parse_args()

    t = pd.read_parquet(TRADES)
    t["ed"] = t["entry_dt"].astype(str).str[:10]
    spx, ts_et = live_spot()
    date = _norm_date(a.date) or (ts_et and None)  # ts_et is time-only; fall back to max entry date
    if not date:
        date = t["ed"].max()
    day = t[t["ed"] == date]
    book = day if a.all_entries else day[day["exit_dt"].isna()]
    if not len(book):
        print(f"no {'entries' if a.all_entries else 'open positions'} for {date}")
        return 1

    z = compute_zone(book)
    lo, hi = z["zone_low"], z["zone_high"]
    scope = "all entries" if a.all_entries else "open positions"
    print(f"=== max-profit zone {date} ({z['n_positions']} {scope}) ===")
    for k, s in z["put_shorts"]:
        print(f"  short P {k:.0f}   ({s})")
    for k, s in z["call_shorts"]:
        print(f"  short C {k:.0f}   ({s})")
    if lo is None or hi is None:
        print("  incomplete: need at least one short put AND one short call for a two-sided zone.")
    else:
        status = "" if spx is None else (
            f"  |  SPX {spx:.1f} -> {'IN ZONE' if lo <= spx <= hi else 'OUTSIDE'}")
        print(f"\n>> ZONE {lo:.0f} - {hi:.0f}  (width {hi - lo:.0f}pt){status}")
        print(f"   downside edge {lo:.0f} ({z['low_edge_strategy']}) | upside edge {hi:.0f} ({z['high_edge_strategy']})")
        print(f"   max credit if it pins in-zone: {z['total_credit']} pts")

    if a.snapshot:
        f = OUT / f"maxprofit_zone_{date.replace('-', '')}.csv"
        new = not f.exists()
        with open(f, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["snapshot_ts_et", "date", "scope", "n_positions", "zone_low",
                            "zone_high", "zone_width", "spx", "in_zone", "total_credit",
                            "low_edge", "high_edge"])
            in_zone = None if (lo is None or hi is None or spx is None) else (lo <= spx <= hi)
            w.writerow([ts_et or "", date, scope, z["n_positions"], lo, hi, z["zone_width"],
                        spx, in_zone, z["total_credit"], z["low_edge_strategy"], z["high_edge_strategy"]])
        print(f"\nsnapshot appended -> {f.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
