#!/usr/bin/env python3
"""MentorQ gamma-level tracker — ingestion CLI.

Capture path is "screenshot -> parse": you save the Backtest-panel screenshot to
screenshots/, an assistant (or you) transcribes it into a small JSON file, and
this script validates + decomposes + writes it into gamma.db. Keeping a JSON of
record makes every ingest reviewable before it hits the DB.

Subcommands
-----------
  init                              create gamma.db from schema.sql
  morning  <records.json>          upsert the pre-RTH panel numbers
  evening  <outcomes.json>         fill the post-close outcome fields
  show     [--date YYYY-MM-DD]     dump rows + decomposition for a date

JSON shapes
-----------
morning:  {"date": "2026-07-11", "levels": [
             {"level_name": "1D Max", "level_price": 7602.02,
              "regime_hold_rate_pct": 89.07, "positive_outcomes": 348,
              "broke_at_close_pct": 10.9, "comeback_rate_pct": 43,
              "avg_move_intraday": 22.01, "worst_move_intraday": 108.70,
              "median_close_beyond": 19.74, "avg_close_beyond": 23.29,
              "worst_close_beyond": 86.53, "regime_label": null}, ...]}

evening:  {"date": "2026-07-11",
           "session_high": ..., "session_low": ..., "session_close": ...,
           "levels": [
             {"level_name": "1D Max", "touched": 1, "broke_intraday": 0,
              "max_excursion_beyond": 0, "closed_beyond": 0,
              "dist_beyond_at_close": -14.5, "held": 1, "notes": ""}, ...]}
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = HERE / "gamma.db"
SCHEMA = HERE / "schema.sql"

# Fields we accept from a morning JSON (everything except the primary key parts).
MORNING_FIELDS = [
    "level_price", "regime_label", "regime_hold_rate_pct", "positive_outcomes",
    "broke_at_close_pct", "comeback_rate_pct", "avg_move_intraday",
    "worst_move_intraday", "median_close_beyond", "avg_close_beyond",
    "worst_close_beyond",
]
EVENING_LEVEL_FIELDS = [
    "touched", "broke_intraday", "max_excursion_beyond", "closed_beyond",
    "dist_beyond_at_close", "held", "notes",
]
EVENING_SESSION_FIELDS = ["session_high", "session_low", "session_close"]


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def cmd_init(_args) -> None:
    con = connect()
    con.executescript(SCHEMA.read_text())
    con.commit()
    con.close()
    print(f"Initialized {DB_PATH}")


def _decompose(H_pct, P, Bc_pct, Cr_pct):
    """Back out the never-reached / comeback / closed-beyond split.

    Returns None if any input is missing. Mirrors the v_decomposition view so
    the ingest confirmation and the SQL report agree.
    """
    if None in (H_pct, P, Bc_pct, Cr_pct) or H_pct == 0:
        return None
    H, Bc, Cr = H_pct / 100.0, Bc_pct / 100.0, Cr_pct / 100.0
    if Cr >= 1.0:
        return None
    N = P / H
    closed_beyond = N * Bc
    comeback = closed_beyond * Cr / (1 - Cr)
    broke_intraday = comeback + closed_beyond
    never = N - broke_intraday
    return {
        "N": round(N), "never_reached": round(never),
        "comeback": round(comeback), "closed_beyond": round(closed_beyond),
        "check": round(never + comeback),  # should equal P
    }


def cmd_morning(args) -> None:
    payload = json.loads(Path(args.json).read_text())
    date = payload["date"]
    levels = payload["levels"]
    con = connect()
    for lv in levels:
        name = lv["level_name"]
        cols = ["date", "level_name"] + [f for f in MORNING_FIELDS if f in lv]
        vals = [date, name] + [lv[f] for f in MORNING_FIELDS if f in lv]
        placeholders = ",".join("?" * len(cols))
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("date", "level_name"))
        con.execute(
            f"INSERT INTO daily_levels ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(date, level_name) DO UPDATE SET {updates}",
            vals,
        )
    con.commit()

    print(f"\nMorning ingest for {date} - {len(levels)} levels\n")
    print(f"{'Level':<16}{'Hold%':>7}{'Pos':>6}{'Bc%':>6}{'Cr%':>6}   decomposition")
    print("-" * 74)
    for lv in levels:
        d = _decompose(lv.get("regime_hold_rate_pct"), lv.get("positive_outcomes"),
                       lv.get("broke_at_close_pct"), lv.get("comeback_rate_pct"))
        tail = ""
        if d:
            ok = "OK" if d["check"] == lv.get("positive_outcomes") else f"!= {lv.get('positive_outcomes')}"
            tail = (f"N={d['N']}  never={d['never_reached']}  "
                    f"comeback={d['comeback']}  closed={d['closed_beyond']}  [{ok}]")
        print(f"{lv['level_name']:<16}"
              f"{_fmt(lv.get('regime_hold_rate_pct')):>7}"
              f"{_fmt(lv.get('positive_outcomes')):>6}"
              f"{_fmt(lv.get('broke_at_close_pct')):>6}"
              f"{_fmt(lv.get('comeback_rate_pct')):>6}   {tail}")
    con.close()


def cmd_evening(args) -> None:
    payload = json.loads(Path(args.json).read_text())
    date = payload["date"]
    con = connect()
    # session-wide fields go on every row for the date
    sess = {f: payload[f] for f in EVENING_SESSION_FIELDS if f in payload}
    for lv in payload["levels"]:
        name = lv["level_name"]
        fields = {**sess, **{f: lv[f] for f in EVENING_LEVEL_FIELDS if f in lv}}
        if not fields:
            continue
        sets = ",".join(f"{c}=?" for c in fields)
        con.execute(
            f"UPDATE daily_levels SET {sets} WHERE date=? AND level_name=?",
            list(fields.values()) + [date, name],
        )
    con.commit()
    con.close()
    print(f"Evening outcomes written for {date} ({len(payload['levels'])} levels)")


def cmd_show(args) -> None:
    con = connect()
    where = "WHERE date=?" if args.date else ""
    params = (args.date,) if args.date else ()
    rows = con.execute(
        f"SELECT * FROM v_decomposition {where} ORDER BY date, level_name", params
    ).fetchall()
    if not rows:
        print("No decomposable rows yet.")
        return
    print(f"{'Date':<12}{'Level':<16}{'N':>6}{'never':>7}{'comeback':>10}{'closed':>8}")
    print("-" * 59)
    for r in rows:
        print(f"{r['date']:<12}{r['level_name']:<16}"
              f"{_fmt(r['est_total_days']):>6}{_fmt(r['est_never_reached']):>7}"
              f"{_fmt(r['est_comeback_days']):>10}{_fmt(r['est_closed_beyond']):>8}")
    con.close()


def _fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def main() -> None:
    p = argparse.ArgumentParser(description="MentorQ gamma-level tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    m = sub.add_parser("morning"); m.add_argument("json"); m.set_defaults(func=cmd_morning)
    e = sub.add_parser("evening"); e.add_argument("json"); e.set_defaults(func=cmd_evening)
    s = sub.add_parser("show"); s.add_argument("--date"); s.set_defaults(func=cmd_show)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
