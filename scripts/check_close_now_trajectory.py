"""One-shot diagnostic (S128): user watched the dashboard's 'day if closed now'
tile go from -$477 to +$1,033 in the ~5 minutes before today's close and
suspects a dashboard bug. Reconstruct the ACTUAL trajectory of that number
through the close, from the raw marks.csv (per-leg unrealized P&L, logged
every ~2-3 min) + notifications.log (realized closes), so we see exactly
when and why it moved -- instead of asserting a story that isn't checked
against the per-timestamp data.

Usage: .venv/Scripts/python.exe scripts/check_close_now_trajectory.py
Saves: data/options_sim/close_now_trajectory_<today>.csv
"""
import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log" / "notifications.log"
TODAY = "2026-10-05"


def realized_closes():
    """[(ts, trade_label, pnl)] for every TRADE CLOSED line today, in order."""
    out = []
    pat = re.compile(r"^(" + re.escape(TODAY) + r" \d\d:\d\d:\d\d)\tTRADE CLOSED . (\S+) \(\$(-?[\d,]+)\)")
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pat.match(line)
        if m:
            ts, label, pnl = m.groups()
            out.append((ts, label, float(pnl.replace(",", ""))))
    return out


def marks_by_ts():
    """{ts: {trade_id: unreal_pnl}} for today only, in file order."""
    by_ts = defaultdict(dict)
    with open(SIM / "marks.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["ts_et"].startswith(TODAY):
                by_ts[row["ts_et"]][row["trade_id"]] = float(row["unreal_pnl"])
    return dict(sorted(by_ts.items()))


def main():
    closes = realized_closes()
    marks = marks_by_ts()

    print("=== realized closes today (from notifications.log) ===")
    for ts, label, pnl in closes:
        print(f"  {ts}  {label:12s} {pnl:+.2f}")

    print("\n=== open-book unrealized total per marks.csv snapshot ===")
    out_rows = []
    for ts, legs in marks.items():
        realized_so_far = sum(p for cts, _, p in closes if cts <= ts)
        unreal = sum(legs.values())
        close_now = realized_so_far + unreal
        n_legs = len(legs)
        out_rows.append((ts, n_legs, unreal, realized_so_far, close_now))
        print(f"  {ts}  open_legs={n_legs:>2}  unreal={unreal:>8.2f}  "
              f"realized_so_far={realized_so_far:>8.2f}  close_now={close_now:>8.2f}")

    out = SIM / f"close_now_trajectory_{date.today():%Y%m%d}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ts", "open_legs", "unreal_pnl", "realized_so_far", "close_now"])
        w.writerows(out_rows)
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
