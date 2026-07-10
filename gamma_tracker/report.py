#!/usr/bin/env python3
"""MentorQ gamma-level tracker — analysis reports.

  drift    [--level NAME]   positive-outcomes & hold-rate over time per level
  decomp   [--date DATE]    the never-reached / comeback / closed split per row
  calib    [--level NAME]   MentorQ's advertised hold rate vs. your logged reality

'drift' is the tell for whether MentorQ's 3-year window is rolling and whether
the regime filter changes daily: if positive_outcomes wanders (348 -> 351 -> 349)
the sample is not fixed. 'calib' only has data once you've logged evening
outcomes (the `held` column) for enough days.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "gamma.db"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def cmd_drift(args) -> None:
    con = connect()
    where = "WHERE level_name=?" if args.level else ""
    params = (args.level,) if args.level else ()
    rows = con.execute(
        f"SELECT date, level_name, regime_hold_rate_pct, positive_outcomes "
        f"FROM daily_levels {where} "
        f"ORDER BY level_name, date", params).fetchall()
    if not rows:
        print("No rows logged yet.")
        return

    by_level: dict[str, list] = {}
    for r in rows:
        by_level.setdefault(r["level_name"], []).append(r)

    for level, series in by_level.items():
        print(f"\n== {level} ==")
        print(f"{'Date':<12}{'Hold%':>8}{'Pos':>7}{'dPos':>7}")
        prev = None
        for r in series:
            p = r["positive_outcomes"]
            dp = "" if prev is None or p is None else f"{p - prev:+d}"
            print(f"{r['date']:<12}{_fmt(r['regime_hold_rate_pct']):>8}"
                  f"{_fmt(p):>7}{dp:>7}")
            if p is not None:
                prev = p
        counts = [r["positive_outcomes"] for r in series if r["positive_outcomes"] is not None]
        if len(counts) > 1:
            span = max(counts) - min(counts)
            verdict = "ROLLING/variable window" if span else "fixed so far"
            print(f"  range over {len(counts)} days: {min(counts)}..{max(counts)} "
                  f"(span {span}) -> {verdict}")
    con.close()


def cmd_decomp(args) -> None:
    con = connect()
    where = "WHERE date=?" if args.date else ""
    params = (args.date,) if args.date else ()
    rows = con.execute(
        f"SELECT * FROM v_decomposition {where} ORDER BY date, level_name", params).fetchall()
    if not rows:
        print("No decomposable rows yet (need hold rate, positive count, "
              "broke-at-close, comeback rate).")
        return
    print(f"{'Date':<12}{'Level':<16}{'N':>6}{'never':>7}{'comeback':>10}{'closed':>8}")
    print("-" * 59)
    for r in rows:
        print(f"{r['date']:<12}{r['level_name']:<16}"
              f"{_fmt(r['est_total_days']):>6}{_fmt(r['est_never_reached']):>7}"
              f"{_fmt(r['est_comeback_days']):>10}{_fmt(r['est_closed_beyond']):>8}")
    con.close()


def cmd_calib(args) -> None:
    con = connect()
    where = "AND level_name=?" if args.level else ""
    params = (args.level,) if args.level else ()
    rows = con.execute(
        f"SELECT level_name, "
        f"       AVG(regime_hold_rate_pct) AS advertised, "
        f"       AVG(held)*100.0           AS realized, "
        f"       COUNT(held)               AS n_outcomes "
        f"FROM daily_levels "
        f"WHERE held IS NOT NULL {where} "
        f"GROUP BY level_name ORDER BY level_name", params).fetchall()
    if not rows:
        print("No logged outcomes yet — fill the evening `held` field for a few "
              "weeks, then calibration becomes meaningful.")
        return
    print(f"{'Level':<16}{'Advert%':>9}{'Real%':>8}{'Gap':>7}{'n':>5}")
    print("-" * 45)
    for r in rows:
        gap = (r["realized"] - r["advertised"]) if r["realized"] is not None else None
        print(f"{r['level_name']:<16}{_fmt(r['advertised']):>9}"
              f"{_fmt(r['realized']):>8}{_fmt(gap):>7}{r['n_outcomes']:>5}")
    print("\n(small n — treat as directional until you have 30+ outcomes per level)")
    con.close()


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def main() -> None:
    p = argparse.ArgumentParser(description="MentorQ tracker reports")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("drift"); d.add_argument("--level"); d.set_defaults(func=cmd_drift)
    c = sub.add_parser("decomp"); c.add_argument("--date"); c.set_defaults(func=cmd_decomp)
    k = sub.add_parser("calib"); k.add_argument("--level"); k.set_defaults(func=cmd_calib)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
