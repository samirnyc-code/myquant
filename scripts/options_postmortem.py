"""Daily options postmortem (S75) — compare the premarket gameplan to how the
day actually played out, so we can LEARN without changing the rules daily.

For a given date it reconciles three things:
  1. the morning gameplan (options_gameplan.py)      — what we intended
  2. the day's spot tape (underlying_YYYYMMDD.csv)    — what actually happened
  3. the trades taken (trades.parquet, auto_trigger)  — what we did

and reports, per trigger:
  * FIRED   — projected grade vs final grade vs P&L (P&L once settled/marked)
  * NOT FIRED — counterfactual: did its condition occur on the tape? (would it
    have fired?). NOTE: we do NOT reconstruct option P&L for unfired triggers —
    we have no intraday option-price history, so the counterfactual is
    STRUCTURAL (condition reached y/n), stated honestly, not a fake P&L.

It also classifies which price path (A/B/C/D) materialized and writes a
narrative. This job only OBSERVES — it never edits the criteria. Rule changes
are proposed weekly (options_weekly_review.py) and require sign-off. That
separation is the anti-overfitting guardrail.

Run after the close (Task Scheduler ~16:15 ET) or any time:
  .venv/Scripts/python.exe scripts/options_postmortem.py [--date YYYYMMDD]
Writes data/options_sim/postmortem_YYYYMMDD.json and prints the report.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
ET = ZoneInfo("America/New_York")


def load_plan(date):
    p = SIM / f"gameplan_{date}.json"
    if not p.exists():
        raise SystemExit(f"no gameplan for {date} ({p}).")
    return json.loads(p.read_text(encoding="utf-8"))


def load_tape(date):
    f = SIM / f"underlying_{date}.csv"
    if not f.exists():
        return None
    df = pd.read_csv(f)
    return df if len(df) else None


def tape_ohlc(df):
    u = df.und.astype(float)
    return {"open": float(u.iloc[0]), "high": float(u.max()),
            "low": float(u.min()), "close": float(u.iloc[-1])}


def touched(df, level, direction):
    """Did the tape reach `level` in `direction` at any point during the day?
    Approximate (day hi/lo) — enough to answer 'would this trigger have fired?'."""
    u = df.und.astype(float)
    hi, lo = float(u.max()), float(u.min())
    if direction in ("from_below", "above"):
        return hi >= level   # price rose to/through the level
    if direction in ("from_above", "below"):
        return lo <= level   # price fell to/through the level
    return False


def classify_path(ohlc, L):
    hvl, ps0, cr0, gw0 = L.get("hvl"), L.get("ps0"), L.get("cr0"), L.get("gw0")
    notes = []
    if hvl and ohlc["close"] < hvl:
        notes.append(("D", f"closed {ohlc['close']:.0f} below HVL {hvl:.0f} — regime tipped negative"))
    if cr0 and ohlc["high"] >= cr0:
        notes.append(("A", f"high {ohlc['high']:.0f} tagged CR0/GW0 {cr0:.0f}"))
    if ps0 and ohlc["low"] <= ps0:
        notes.append(("B", f"low {ohlc['low']:.0f} tagged PS0 {ps0:.0f}"))
    if hvl and cr0 and ohlc["low"] >= hvl and ohlc["high"] <= cr0:
        notes.append(("C", f"ranged {ohlc['low']:.0f}–{ohlc['high']:.0f} inside HVL/CR0 — pin held"))
    if not notes:
        notes.append(("C/—", f"ranged {ohlc['low']:.0f}–{ohlc['high']:.0f}"))
    return notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (default today ET)")
    args = ap.parse_args()
    date = args.date or dt.datetime.now(ET).strftime("%Y%m%d")

    plan = load_plan(date)
    L = plan["levels"]
    tape = load_tape(date)
    trades = tlog.load()
    day_trades = trades[trades.entry_dt.astype(str).str.startswith(
        f"{date[:4]}-{date[4:6]}-{date[6:]}")] if len(trades) else trades

    report = {"date": date, "regime_preopen": plan.get("regime"),
              "spot_preopen": plan.get("spot_preopen"), "levels": L, "triggers": []}

    if tape is not None:
        ohlc = tape_ohlc(tape)
        report["ohlc"] = ohlc
        report["paths_materialized"] = classify_path(ohlc, L)
    else:
        ohlc = None
        report["ohlc"] = None
        report["paths_materialized"] = [("?", "no tape for this date")]

    for t in plan["triggers"]:
        row = {"id": t["id"], "setup": t["setup"], "name": t["name"],
               "projected_grade": t["projected_grade"], "status": t.get("status"),
               "fired": bool(t.get("fired"))}
        if t.get("fired") and t.get("trade_id"):
            tr = day_trades[day_trades.trade_id == t["trade_id"]]
            if len(tr):
                r = tr.iloc[0]
                row["final_grade"] = r.grade
                row["credit"] = None if pd.isna(r.credit) else round(float(r.credit), 2)
                row["pnl"] = None if pd.isna(r.pnl) else round(float(r.pnl))
                row["outcome"] = ("open/unsettled" if pd.isna(r.pnl)
                                  else "WIN" if float(r.pnl) > 0 else "LOSS")
        elif t.get("status") == "skipped_broken":
            row["outcome"] = "skipped (broken fill): " + t.get("skip_reason", "")
        elif tape is not None and t["fire"]["type"] in ("touch", "first_of", "regime_break"):
            f = t["fire"]
            tc = f.get("touch", f)  # first_of nests the touch
            lvl, d = tc.get("level"), tc.get("dir")
            if lvl and d:
                reached = touched(tape, lvl, d)
                row["counterfactual"] = (f"condition {'DID' if reached else 'did NOT'} occur "
                                         f"(price {'reached' if reached else 'never reached'} {lvl} {d.replace('from_','')})")
        report["triggers"].append(row)

    out = SIM / f"postmortem_{date}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ---- readable ----
    print(f"\nPOSTMORTEM {date}   preopen {report['spot_preopen']} ({report['regime_preopen']})")
    if ohlc:
        print(f"  day  O {ohlc['open']:.0f}  H {ohlc['high']:.0f}  L {ohlc['low']:.0f}  C {ohlc['close']:.0f}")
    print("  path(s) materialized:")
    for pid, why in report["paths_materialized"]:
        print(f"    {pid}: {why}")
    print("\n  TRIGGER OUTCOMES:")
    for row in report["triggers"]:
        if row["fired"] and "pnl" in row:
            pnl = row["pnl"]
            pstr = "—" if pnl is None else (f"{'+' if pnl >= 0 else '−'}${abs(pnl):,}")
            print(f"    FIRED   {row['name']}: proj {row['projected_grade']} → "
                  f"final {row.get('final_grade','?')} · {row.get('outcome','?')} {pstr}")
        elif "counterfactual" in row:
            print(f"    unfired {row['name']} [{row['status']}]: {row['counterfactual']}")
        elif "outcome" in row:
            print(f"    {row['name']}: {row['outcome']}")
        else:
            print(f"    {row['name']} [{row['status']}]")
    n_fired = sum(1 for r in report["triggers"] if r["fired"])
    print(f"\n  {n_fired} fired · learning is OBSERVE-ONLY here; rule changes go through "
          f"the weekly review (sign-off required).")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
