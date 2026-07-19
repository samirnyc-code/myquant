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

Run after the close (Task Scheduler ~15:15 CT) or any time:
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
from options_build_cards import spx_close_on   # per-expiry SPX close for calendar settlement

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")  # exchange time (Chicago / Central)


FEE = 1.30  # $/contract, matches the sim/backtests


def settle_0dte(date, close):
    """Cash-settle any still-open trades whose legs ALL expire `date` (0DTE),
    to the SPX close. exit_cost = per-contract net intrinsic to close the spread
    (Σ short-leg intrinsic − Σ long-leg intrinsic). Lets the postmortem show real
    P&L instead of 'open/unsettled'."""
    if close is None:
        return []
    df = tlog.load()
    settled = []
    for _, r in df.iterrows():
        if pd.notna(r.exit_dt):
            continue
        try:
            legs = json.loads(r.legs)
        except Exception:
            continue
        exps = {l.get("expiry") for l in legs}
        if not legs or not exps or max(exps) > date:
            continue            # a leg is still live -> nothing to settle yet
        # S75V: this used to require {expiries} == {date}, i.e. every leg sharing ONE
        # expiry that is today. A CALENDAR never satisfies that, so multi-expiry
        # positions were flagged partial_expiry when the near leg went and then stayed
        # open forever - put_cal_wk_20260714_1221 sat "open" at a frozen mid for days,
        # and its card showed no payoff because no live legs remained. Now: settle once
        # the LAST leg has expired, valuing each leg at ITS OWN expiry-date SPX close.
        cost = 0.0
        for l in legs:
            k, q = float(l["strike"]), int(l.get("qty", 1))
            e = l.get("expiry")
            base = close if e == date else spx_close_on(f"{e[:4]}-{e[4:6]}-{e[6:]}")
            if base is None:
                base = close    # fall back to today's close if that day isn't cached
            intr = max(0.0, base - k) if l["right"] == "C" else max(0.0, k - base)
            cost += (intr * q) if l["side"] == "sell" else (-intr * q)
        fees = len(legs) * int(legs[0].get("qty", 1)) * FEE
        exit_dt = f"{date[:4]}-{date[4:6]}-{date[6:]} 16:00"
        # still open at settlement ⇒ we did NOT trade it to close ⇒ it EXPIRED.
        rr = tlog.update_exit(r.trade_id, exit_dt, round(cost, 2), fees,
                              fill_model="cash_settle", close_reason="expired")
        settled.append((r.trade_id, rr["pnl"]))
    return settled


def flag_partial_expiry(today):
    """Mark still-open trades that have SOME (not all) legs already expired — e.g. a
    calendar whose near leg settled. These can't be cleanly cash-settled (a live leg
    remains), so we flag them close_reason='partial_expiry' for a human decision
    rather than silently leaving them 'open'. Returns the flagged trade_ids."""
    df = tlog.load()
    flagged = []
    for _, r in df.iterrows():
        if pd.notna(r.exit_dt):
            continue
        try:
            exps = {l.get("expiry") for l in json.loads(r.legs)}
        except Exception:
            continue
        expired = {e for e in exps if e and e < today}
        if expired and expired != exps:            # some expired, some still live
            tlog.annotate(r.trade_id, close_reason="partial_expiry")
            flagged.append((r.trade_id, sorted(expired)))
    return flagged


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
    ap.add_argument("--date", help="YYYYMMDD (default today CT)")
    args = ap.parse_args()
    date = args.date or dt.datetime.now(CT).strftime("%Y%m%d")

    plan = load_plan(date)
    L = plan["levels"]
    tape = load_tape(date)
    ohlc = tape_ohlc(tape) if tape is not None else None

    # cash-settle 0DTE trades to the close BEFORE reading P&L
    settled = settle_0dte(date, ohlc["close"]) if ohlc else []
    flagged = flag_partial_expiry(date)
    if flagged:
        print(f"  flagged partial-expiry (needs decision): {[t for t, _ in flagged]}")

    trades = tlog.load()
    day_trades = trades[trades.entry_dt.astype(str).str.startswith(
        f"{date[:4]}-{date[4:6]}-{date[6:]}")] if len(trades) else trades

    report = {"date": date, "regime_preopen": plan.get("regime"),
              "spot_preopen": plan.get("spot_preopen"), "levels": L,
              "settled_0dte": [{"trade_id": t, "pnl": round(p)} for t, p in settled],
              "triggers": []}

    if ohlc is not None:
        report["ohlc"] = ohlc
        report["paths_materialized"] = classify_path(ohlc, L)
    else:
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
    if settled:
        print("  settled 0DTE at close: " + ", ".join(f"{t} ${p:+,.0f}" for t, p in settled))
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
