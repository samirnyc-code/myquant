"""Intraday options trigger daemon (S75).

Reads today's premarket gameplan (options_gameplan.py), watches the live spot
feed (data/options_sim/live.json), and AUTO-EXECUTES each trigger the instant
its condition materializes — 1 lot, no concurrency cap, notify after each fill.
Takes every trigger regardless of grade (data collection); skips only
structurally-broken fills (zero/negative credit on a credit structure).

Fire conditions (from the gameplan's `fire` block):
  touch        — first cross of a level in a direction (fades)
  first_of     — price tags the wall  OR  a not_before time  (premium sells)
  time_at      — at/after a time, if the arm-regime holds (fly)
  regime_break — spot breaks a level in a direction (straddle arms on HVL break)
  signal_1559  — IGNORED here; run by options_sim_daemon.py

Each fire: build legs from the trigger's structure, place BUY-wings-first on the
paper account (real fills), stamp the FINAL grade from the realized credit, log
to the unified trade log, toast + log the notification, and persist fired=True
back into gameplan_YYYYMMDD.json (so a restart resumes, never double-fires).

Run (after Gateway login + spot_feed.py):
  .venv/Scripts/python.exe scripts/options_trigger_daemon.py [--dry-run] [--date YYYYMMDD]
--dry-run evaluates + logs what WOULD fire without placing any order.
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_trade_log as tlog
from ib_order_test import marketable
from ib_async import Option
from notify import notify

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")  # exchange time (Chicago / Central)
FEE = 1.30
POLL = 3  # seconds between spot evaluations


def now_ct():
    return dt.datetime.now(CT)


def hhmm(t):
    return now_ct().replace(hour=int(t[:2]), minute=int(t[3:]), second=0, microsecond=0)


# ---------- gameplan I/O ----------

def plan_path(date):
    return SIM / f"gameplan_{date}.json"


def load_plan(date):
    p = plan_path(date)
    if not p.exists():
        raise SystemExit(f"no gameplan for {date} — run options_gameplan.py first ({p}).")
    return json.loads(p.read_text(encoding="utf-8"))


def save_plan(plan):
    p = plan_path(plan["date"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    tmp.replace(p)


def read_live():
    f = SIM / "live.json"
    if f.exists():
        try:
            d = json.loads(f.read_text())
            if d.get("state") == "live" and d.get("spx"):
                return float(d["spx"])
        except Exception:
            pass
    return None


# ---------- condition evaluation ----------

def regime(spot, hvl):
    if spot is None or hvl is None:
        return "unknown"
    return "positive_gamma" if spot >= hvl else "negative_gamma"


def crossed(prev, cur, level, direction):
    """True if price crossed `level` between prev and cur in `direction`."""
    if prev is None or cur is None:
        return False
    if direction in ("from_below", "below"):   # crossing UP through / down to
        return prev < level <= cur if direction == "from_below" else prev >= level > cur
    if direction in ("from_above", "above"):
        return prev > level >= cur if direction == "from_above" else prev <= level < cur
    return False


def should_fire(trig, prev, spot, reg):
    """Return (fire: bool, reason: str). Assumes trigger is armed, in-window."""
    arm_reg = trig.get("arm", {}).get("regime", "any")
    if arm_reg != "any" and reg != arm_reg:
        return False, ""
    f = trig["fire"]
    ty = f["type"]
    if ty == "touch":
        if crossed(prev, spot, f["level"], f["dir"]):
            return True, f"touched {f['level']} {f['dir'].replace('from_','')}"
        return False, ""
    if ty == "regime_break":
        if crossed(prev, spot, f["level"], f["dir"]):
            return True, f"broke {f['dir']} {f['level']} (regime flip)"
        return False, ""
    if ty == "time_at":
        if now_ct() >= hhmm(f["not_before"]):
            return True, f"reached {f['not_before']}, regime {reg}"
        return False, ""
    if ty == "first_of":
        tc = f.get("touch")
        if tc and crossed(prev, spot, tc["level"], tc["dir"]):
            return True, f"tagged {tc['level']} {tc['dir'].replace('from_','')}"
        if now_ct() >= hhmm(f["not_before"]):
            return True, f"reached {f['not_before']} (no tag), regime {reg}"
        return False, ""
    return False, ""  # signal_1559 etc. handled elsewhere


# ---------- trade construction + execution ----------

def build_legs(struct, spot):
    """Return [(right, strike, action)] BUY-wings-first. Credit structures list
    the protective long first so it is placed before the naked short."""
    kind = struct["kind"]
    if kind == "vertical":
        r = struct["right"]
        return [(r, struct["long"], "BUY"), (r, struct["short"], "SELL")]
    if kind == "butterfly":
        r = struct["right"]
        return [(r, struct["lower"], "BUY"), (r, struct["upper"], "BUY"),
                (r, struct["center"], "SELL"), (r, struct["center"], "SELL")]
    if kind == "straddle":
        c = round(spot / 5) * 5
        return [("C", c, "BUY"), ("P", c, "BUY")]
    raise ValueError(f"unknown structure kind {kind}")


def qualify(ib, exp, strike, right):
    o = ib.qualifyContracts(Option("SPX", exp, strike, right, "SMART", tradingClass="SPXW"))
    if not o or not o[0].conId:
        o = ib.qualifyContracts(Option("SPX", exp, strike, right, "SMART", tradingClass="SPX"))
    if not o or not o[0].conId:
        raise RuntimeError(f"cannot qualify SPX {exp} {strike}{right}")
    return o[0]


def place_legs(ib, exp, legs, qty):
    """Place each leg marketable; return (net_per_contract, filled_leg_dicts).
    net > 0 = credit received. Raises on a leg that will not fill."""
    ib.reqMarketDataType(1)
    net = 0.0
    filled = []
    for right, strike, action in legs:
        c = qualify(ib, exp, strike, right)
        q = ib.reqMktData(c, "", snapshot=False)
        ib.sleep(6)
        px = q.ask if action == "BUY" else q.bid
        ib.cancelMktData(c)
        if not (px == px and px > 0):
            raise RuntimeError(f"no live quote {strike}{right} — aborting after {len(filled)} legs")
        tr = marketable(ib, c, action, qty, px)
        if tr.orderStatus.status != "Filled":
            raise RuntimeError(f"leg {action} {strike}{right} did not fill")
        fp = tr.orderStatus.avgFillPrice
        net += fp if action == "SELL" else -fp
        filled.append({"side": "sell" if action == "SELL" else "buy",
                       "right": right, "strike": float(strike), "expiry": exp, "qty": qty})
    return net, filled


# ---------- grading at fill (same ladders as the plan/dashboard) ----------

def grade_at_fill(trig, net, spot, plan):
    setup = trig["setup"]
    reg = regime(spot, plan["levels"].get("hvl"))
    positive = reg == "positive_gamma"
    st = trig["structure"]
    late = now_ct().time() > dt.time(10, 0)  # after 10:00 CT
    if setup in ("sell_0dte_gamma", "cr0_fade", "ps0_fade"):
        short = st.get("short")
        dist = abs(spot - short) if short else 0
        if not positive and setup == "sell_0dte_gamma":
            g = "C"
        elif dist >= 40 and net >= 0.80:
            g = "A"
        elif dist >= 40 and net >= 0.60:
            g = "B"
        elif dist >= 40:
            g = "B-"
        elif dist >= 25:
            g = "C"
        else:
            g = "D"
        if late and g in ("A", "B"):
            g = "B-" if g == "A" else "C"
        return g, f"{reg}, short ~{dist:.0f}pt OTM, credit {net:.2f}{' (late)' if late else ''}"
    if setup == "fly_gw_0dte":
        wing = st.get("width", 25)
        debit = -net
        if positive and debit <= 0.40 * wing:
            return "B", f"positive gamma, debit {debit:.2f} ≤40% wing"
        return ("C" if positive else "F"), f"{reg}, debit {debit:.2f}"
    if setup == "straddle_0dte":
        return ("B" if not positive else "F"), f"{reg} at fill (long vol wants neg gamma)"
    return "C", reg


def is_broken(trig, net):
    """Skip structurally-broken fills. Credit structures must yield credit."""
    setup = trig["setup"]
    if setup in ("sell_0dte_gamma", "cr0_fade", "ps0_fade") and net <= 0:
        return True, f"zero/negative credit ({net:.2f}) — wall already blown through"
    if setup == "fly_gw_0dte" and (-net) > 0.60 * trig["structure"].get("width", 25):
        return True, f"debit {-net:.2f} >60% of wing — too rich, no convexity edge"
    return False, ""


# ---------- firing ----------

def fire(ib, trig, spot, plan, reason, dry):
    exp = plan["date"]
    legs = build_legs(trig["structure"], spot)
    label = trig["name"]
    if dry:
        print(f"  [DRY] WOULD FIRE {trig['id']} ({label}) — {reason} — legs {legs}")
        trig["fired"], trig["status"] = True, "dry-fired"
        return
    try:
        net, filled = place_legs(ib, exp, legs, plan["execution"]["size"])
    except Exception as e:
        print(f"  ! {trig['id']} fire FAILED: {e}")
        trig["status"] = "error"
        trig["error"] = str(e)
        return
    broken, why = is_broken(trig, net)
    if broken:
        print(f"  SKIP {trig['id']}: {why} (net {net:.2f}) — NOT logged as a trade")
        trig["status"] = "skipped_broken"
        trig["fired"], trig["skip_reason"] = True, why
        notify(f"TRIGGER SKIPPED · {trig['setup']}", f"{label}: {why}")
        return
    grade, gbasis = grade_at_fill(trig, net, spot, plan)
    tid = f"auto_{now_ct():%Y%m%d_%H%M%S}"
    strikes = [l["strike"] for l in filled]
    width = (max(strikes) - min(strikes)) if len(strikes) > 1 else None
    kind = "credit" if net > 0 else "debit"
    coll = (width - net) * 100 if (width and net > 0) else abs(net) * 100
    struct_txt = trig["structure"]["kind"] + (f" {width:.0f}pt" if width else "")
    tlog.append_entry({
        "trade_id": tid, "strategy_id": trig["setup"], "source": "auto_trigger",
        "symbol": "SPXW", "entry_dt": now_ct().strftime("%Y-%m-%d %H:%M"),
        "dte": 0, "structure": struct_txt, "fill_model": "paper_fill",
        "legs": filled, "credit": net, "collateral": coll, "dow": now_ct().strftime("%a"),
        "grade": grade, "commentary": f"AUTO-TRIGGER [{trig['id']}] fired: {reason}. {gbasis}. "
                                      f"Projected {trig['projected_grade']} premarket. Path {trig.get('path','—')}.",
    })
    trig["fired"], trig["status"], trig["trade_id"] = True, "fired", tid
    trig["fill"] = {"net": round(net, 2), "grade": grade, "at": now_ct().strftime("%H:%M:%S")}
    print(f"  FIRED {trig['id']} -> {tid}: {struct_txt} net {kind} {abs(net):.2f} grade {grade}")
    notify(f"TRADE OPENED · {trig['setup']} ({grade})",
           f"{label}: {struct_txt}, net {kind} {abs(net):.2f}, coll ${coll:,.0f} — {reason}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (default today CT)")
    ap.add_argument("--dry-run", action="store_true", help="evaluate + log, place nothing")
    ap.add_argument("--until", default="15:00", help="stop time CT (default 15:00 = 16:00 ET)")
    args = ap.parse_args()
    date = args.date or now_ct().strftime("%Y%m%d")
    plan = load_plan(date)
    hvl = plan["levels"].get("hvl")
    end = hhmm(args.until)

    ib = None
    if not args.dry_run:
        ib = ib_conn.connect()
    mode = "DRY-RUN" if args.dry_run else "LIVE (auto-execute)"
    armed = [t for t in plan["triggers"] if t["fire"]["type"] != "signal_1559"]
    print(f"trigger daemon [{mode}] {date}: {len(armed)} triggers, watching until {args.until} CT")

    prev = None
    try:
        while now_ct() < end:
            spot = read_live()
            if spot is None:
                time.sleep(POLL)
                continue
            reg = regime(spot, hvl)
            dirty = False
            for trig in plan["triggers"]:
                if trig.get("fired") or trig["fire"]["type"] == "signal_1559":
                    continue
                w = trig.get("window")
                if w and not (hhmm(w[0]) <= now_ct() <= hhmm(w[1])):
                    if now_ct() > hhmm(w[1]) and trig["status"] != "expired":
                        trig["status"] = "expired"
                        dirty = True
                    continue
                go, reason = should_fire(trig, prev, spot, reg)
                if go:
                    fire(ib, trig, spot, plan, reason, args.dry_run)
                    dirty = True
            # Persist ONLY on a real status change (fire / expire). Do NOT write
            # the live spot here — that churned the file every tick and made the
            # dashboard full-reload (kicking the user off their tab). Live spot is
            # already on the page via live.json.
            if dirty:
                save_plan(plan)
            prev = spot
            time.sleep(POLL)
    finally:
        save_plan(plan)
        if ib:
            ib.disconnect()
        fired = [t for t in plan["triggers"] if t.get("fired")]
        print(f"\ndone. {len(fired)} triggers fired: "
              + ", ".join(f"{t['id']}({t.get('fill',{}).get('grade','?')})" for t in fired))


if __name__ == "__main__":
    main()
