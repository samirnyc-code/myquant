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
from options_gameplan import grade_ok  # single source of truth for the grade ladder

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")  # exchange time (Chicago / Central)
FEE = 1.30
POLL = 3        # seconds between spot evaluations
EXIT_POLL = 60  # seconds between open-position exit checks (each one quotes every leg)


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


def quote_legs(ib, exp, legs):
    """Price every leg WITHOUT placing anything; return (est_net, quoted).

    Split out of place_legs so the go/no-go gates (grade, credit floor, dedupe)
    run BEFORE any order exists. The old code placed all legs first and only then
    called is_broken() — so a "skipped" trade left real filled legs sitting in the
    account, unlogged and unmanaged. Quote first, decide, then execute.
    est_net > 0 = credit expected. Raises if any leg has no live quote.
    """
    ib.reqMarketDataType(1)
    est, quoted = 0.0, []
    for right, strike, action in legs:
        c = qualify(ib, exp, strike, right)
        q = ib.reqMktData(c, "", snapshot=False)
        ib.sleep(6)
        px = q.ask if action == "BUY" else q.bid
        ib.cancelMktData(c)
        if not (px == px and px > 0):
            raise RuntimeError(f"no live quote {strike}{right} — nothing placed")
        est += px if action == "SELL" else -px
        quoted.append((c, right, strike, action, px))
    return est, quoted


def place_legs(ib, exp, quoted, qty):
    """Execute already-quoted legs marketable, wings first (quoted preserves the
    BUY-first ordering from build_legs). Returns (net_per_contract, leg_dicts)."""
    net = 0.0
    filled = []
    for c, right, strike, action, px in quoted:
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
    if setup in ("cr0_fade", "ps0_fade"):
        # FADE grading (fixed): the short sits AT the level BY DESIGN, so
        # OTM-distance is meaningless here (the old code graded every fade D for
        # being at-the-money — a category error). A fade's ex-ante quality is
        # about REGIME (does the wall hold?) + credit richness. Positive gamma =
        # dealers mean-revert = wall likely holds = aligned fade. Negative gamma
        # = momentum = wall likely breaks = bad fade.
        width = st.get("width", 25)
        rich = net >= 0.25 * width
        if positive:
            return "B", (f"positive-gamma first-touch fade at the wall (trigger+regime+level "
                         f"aligned); credit {net:.2f}{' (rich)' if rich else ''}")
        if reg == "negative_gamma":
            return "D", f"NEG-gamma fade — fading into momentum, wall likely breaks; credit {net:.2f}"
        return "C", f"neutral-regime fade; credit {net:.2f}"
    if setup == "sell_0dte_gamma":
        # PREMIUM-SELL grading: here you WANT the short far OTM, so distance IS
        # the right axis (unlike a fade).
        short = st.get("short")
        dist = abs(spot - short) if short else 0
        if not positive:
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


CREDIT_SETUPS = ("sell_0dte_gamma", "cr0_fade", "ps0_fade")


def short_strike(trig):
    st = trig.get("structure", {})
    return st.get("short") if st.get("kind") == "vertical" else st.get("center")


def gate(trig, est_net, spot, plan):
    """A1/A2/A4 — every pre-order reason to stand down. (ok, code, why).

    The 7/14–7/17 review: the desk graded a trade D in its own output and took it
    anyway (-$1,513), fired the SAME 7555 short twice on one morning (-$3,225
    combined), and sold a 25pt spread for $0.35 — risking $2,465 to make $35.
    The execution policy at the time was, literally, "take all triggers regardless
    of grade". These gates are that policy's replacement.
    """
    ex = plan.get("execution", {})
    min_grade = ex.get("min_grade", "B-")
    min_cred = ex.get("min_credit_abs", 0.80)
    setup = trig["setup"]
    st = trig.get("structure", {})
    width = st.get("width", 25)

    # --- structurally broken (pre-existing checks, kept) ---
    if setup in CREDIT_SETUPS and est_net <= 0:
        return False, "broken", f"zero/negative credit ({est_net:.2f}) — wall already blown through"
    if setup == "fly_gw_0dte" and (-est_net) > 0.60 * width:
        return False, "broken", f"debit {-est_net:.2f} >60% of wing — no convexity edge"

    # --- A4: minimum credit floor ---
    if setup in CREDIT_SETUPS and est_net < min_cred:
        return False, "thin_credit", (
            f"credit {est_net:.2f} < playbook minimum {min_cred:.2f} — would risk "
            f"${(width - est_net) * 100:,.0f} to make ${est_net * 100:,.0f}")

    # --- A2: dedupe by SHORT STRIKE, not just by side ---
    mine = short_strike(trig)
    if mine is not None:
        for other in plan["triggers"]:
            if other is trig or other.get("status") != "fired":
                continue
            if other.get("structure", {}).get("right") != st.get("right"):
                continue
            theirs = short_strike(other)
            if theirs is not None and theirs == mine:
                return False, "duplicate_level", (
                    f"{other['id']} already fired a {st.get('right')} short at {theirs:.0f} — "
                    f"this is the same trade twice, doubled risk on one idea")

    # --- A1: grade gate, using the grade the REAL quote implies ---
    g, basis = grade_at_fill(trig, est_net, spot, plan)
    if not grade_ok(g, min_grade):
        return False, "below_grade", f"grade {g} < {min_grade} bar — {basis}"
    return True, "", ""


# ---------- exits (A3) ----------
# Until 2026-07-18 this daemon could only OPEN. Every position it created rode to
# expiry untouched, which is why the week's losers all show the full width and the
# winners show pennies. manage_open() below is the missing half.

DEFAULT_EXITS = {"level_accept_mins": 10, "regime_invalidation": True,
                 "time_stop": "14:45"}

# Which structures are a bet ON THE PIN (they need positive gamma to be true) vs
# a bet on the pin BREAKING. Crossing HVL invalidates one and confirms the other.
PIN_SETUPS = ("sell_0dte_gamma", "cr0_fade", "ps0_fade", "fly_gw_0dte", "condor_0dte")
ANTI_PIN_SETUPS = ("straddle_0dte",)


def thesis_level(trig):
    """The price the trade's thesis lives or dies on, and which side kills it.
    Returns (level, fatal_direction) where fatal_direction is 'above' or 'below'."""
    st = trig.get("structure", {})
    if st.get("kind") == "vertical":
        # A call spread sold at CR0 says "price stays BELOW CR0"; a put spread
        # sold at PS0 says "price stays ABOVE PS0".
        return st.get("short"), ("above" if st.get("right") == "C" else "below")
    if st.get("kind") == "butterfly":
        return st.get("center"), None      # a fly dies by regime/distance, not one side
    return None, None                       # straddle: regime is the thesis


def thesis_broken(trig, spot, plan, rules):
    """(broken, why) — is the REASON for this trade still true?

    Three ways a trade dies, none of them P&L:
      1. its level is ACCEPTED through (distance AND time, so wicks don't count)
      2. the REGIME it depends on flips (spot crosses HVL)
      3. the 0DTE clock runs out
    """
    hvl = plan.get("levels", {}).get("hvl")
    setup = trig["setup"]
    mins = rules.get("level_accept_mins", 10)

    # --- 3. clock ---
    ts = rules.get("time_stop", "14:45")
    if now_ct().time() >= dt.time(*map(int, ts.split(":"))):
        return True, f"time stop {ts} CT — flat before the 0DTE gamma cliff"

    # --- 2. regime invalidation ---
    if rules.get("regime_invalidation", True) and hvl is not None and spot is not None:
        reg = regime(spot, hvl)
        if setup in PIN_SETUPS and reg == "negative_gamma":
            return True, (f"regime flip: spot {spot:.0f} crossed BELOW HVL {hvl:.0f} — this "
                          f"structure needs the pin and the pin is gone")
        if setup in ANTI_PIN_SETUPS and reg == "positive_gamma":
            return True, (f"regime reclaim: spot {spot:.0f} back ABOVE HVL {hvl:.0f} — long vol "
                          f"wanted negative gamma; thesis over")

    # --- 1. level acceptance (distance + persistence) ---
    lvl, fatal = thesis_level(trig)
    if lvl is None or fatal is None or spot is None:
        return False, ""
    # The SHORT STRIKE is the boundary — beyond it the spread is ITM and the
    # thesis ("it stays OTM") is false. No arbitrary buffer is added.
    beyond = (spot > lvl) if fatal == "above" else (spot < lvl)
    if not beyond:
        trig.pop("beyond_since", None)     # came back inside — thesis intact, reset
        return False, ""
    first = trig.get("beyond_since")
    if first is None:
        trig["beyond_since"] = now_ct().isoformat()
        return False, ""
    held = (now_ct() - dt.datetime.fromisoformat(first)).total_seconds() / 60.0
    if held >= mins:
        return True, (f"level ACCEPTED: spot {spot:.0f} held {fatal} the {lvl:.0f} short strike "
                      f"for {held:.0f}min (>{mins}) — the wall we sold did not hold")
    return False, ""


def reverse(legs):
    """The closing side of an open position: buy back shorts, sell out longs.
    Shorts are bought FIRST so the position is never transiently naked."""
    out = [(l["right"], l["strike"], "BUY") for l in legs if l["side"] == "sell"]
    out += [(l["right"], l["strike"], "SELL") for l in legs if l["side"] == "buy"]
    return out


CLOSE_REQ = SIM / "close_requests.json"


def pending_manual_closes():
    """Trade IDs the user hit CLOSE on in the dashboard. The dashboard never
    places orders itself — it drops a request here and this daemon (the single
    process that owns the IB connection) executes it. One writer of orders."""
    if not CLOSE_REQ.exists():
        return {}
    try:
        return {r["trade_id"]: r for r in json.loads(CLOSE_REQ.read_text()).get("requests", [])
                if not r.get("done")}
    except Exception:
        return {}


def mark_manual_done(tid):
    try:
        d = json.loads(CLOSE_REQ.read_text())
        for r in d.get("requests", []):
            if r["trade_id"] == tid:
                r["done"] = True
                r["closed_at"] = now_ct().isoformat()
        CLOSE_REQ.write_text(json.dumps(d, indent=2))
    except Exception as e:
        print(f"  ! could not mark manual close done for {tid}: {e}")


def manage_open(ib, plan, spot, dry):
    """Close every open position whose THESIS is dead — or that the user closed
    by hand in the dashboard. Called on a throttle (EXIT_POLL); quoting is slow.

    Note the ordering: the thesis test is pure price/time/regime and costs
    nothing, so it runs BEFORE we spend ~6s/leg quoting. We only quote positions
    we have already decided to close.
    """
    rules = plan.get("execution", {}).get("exits", DEFAULT_EXITS)
    exp = plan["date"]
    manual = pending_manual_closes()
    for trig in plan["triggers"]:
        if trig.get("status") != "fired" or trig.get("exited"):
            continue
        tid, legs = trig.get("trade_id"), trig.get("filled_legs")
        entry_net = trig.get("fill", {}).get("net")
        if not (tid and legs and entry_net is not None):
            continue

        if tid in manual:
            go, why = True, ("MANUAL close from dashboard"
                             + (f": {manual[tid]['note']}" if manual[tid].get("note") else ""))
        else:
            go, why = thesis_broken(trig, spot, plan, rules)
        if not go:
            continue

        close_legs = reverse(legs)
        try:
            _, quoted = quote_legs(ib, exp, close_legs)
        except Exception as e:
            print(f"  ! exit quote failed {tid}: {e}")
            continue
        if dry:
            print(f"  [DRY] WOULD CLOSE {tid}: {why}")
            trig["exited"] = True
            continue
        try:
            net_out, _ = place_legs(ib, exp, quoted, plan["execution"]["size"])
        except Exception as e:
            print(f"  ! exit FAILED {tid}: {e}")
            continue
        cost = -net_out
        tlog.update_exit(tid, now_ct().strftime("%Y-%m-%d %H:%M"), cost, FEE,
                         close_reason=why)
        if tid in manual:
            mark_manual_done(tid)
        trig["exited"] = True
        trig["exit"] = {"cost": round(cost, 2), "at": now_ct().strftime("%H:%M:%S"), "why": why}
        pnl = (entry_net - cost) * 100 - FEE
        print(f"  CLOSED {tid} cost {cost:.2f} P&L ${pnl:,.0f} — {why}")
        notify(f"TRADE CLOSED · {trig['setup']} (${pnl:,.0f})", f"{trig['name']}: {why}")


# ---------- firing ----------

def fire(ib, trig, spot, plan, reason, dry):
    exp = plan["date"]
    legs = build_legs(trig["structure"], spot)
    label = trig["name"]
    if dry:
        print(f"  [DRY] WOULD FIRE {trig['id']} ({label}) — {reason} — legs {legs}")
        trig["fired"], trig["status"] = True, "dry-fired"
        return
    # 1. QUOTE — no order exists yet, so every gate below is free to say no.
    try:
        est_net, quoted = quote_legs(ib, exp, legs)
    except Exception as e:
        print(f"  ! {trig['id']} quote FAILED: {e}")
        trig["status"] = "error"
        trig["error"] = str(e)
        return

    # 2. GATE — A1 grade / A2 level dedupe / A4 credit floor. Nothing was placed.
    ok, code, why = gate(trig, est_net, spot, plan)
    if not ok:
        print(f"  STAND DOWN {trig['id']} [{code}]: {why} (est net {est_net:.2f}) — no order placed")
        trig["status"] = f"stood_down_{code}"
        trig["fired"], trig["skip_reason"] = True, why
        trig["est_net"] = round(est_net, 2)
        notify(f"STOOD DOWN · {trig['setup']} [{code}]", f"{label}: {why}")
        return

    # 3. EXECUTE — only now do real orders hit the account.
    try:
        net, filled = place_legs(ib, exp, quoted, plan["execution"]["size"])
    except Exception as e:
        print(f"  ! {trig['id']} fire FAILED after gates passed: {e}")
        trig["status"] = "error"
        trig["error"] = str(e)
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
        "gex_regime": regime(spot, plan["levels"].get("hvl")),  # for analytics slicing
        "grade": grade, "commentary": f"AUTO-TRIGGER [{trig['id']}] fired: {reason}. {gbasis}. "
                                      f"Projected {trig['projected_grade']} premarket. Path {trig.get('path','—')}.",
    })
    trig["fired"], trig["status"], trig["trade_id"] = True, "fired", tid
    trig["fill"] = {"net": round(net, 2), "grade": grade, "at": now_ct().strftime("%H:%M:%S")}
    trig["filled_legs"] = filled   # A3: the exit manager reverses these
    trig["exited"] = False
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
    last_exit_check = 0.0
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
                if trig.get("status") == "disarmed":
                    continue  # A5/A1 stood it down premarket; reason is on the trigger
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
            # A3: manage open positions on a slower cadence than the fire loop —
            # each check quotes every leg of every open position (~6s per leg).
            if any(t.get("status") == "fired" and not t.get("exited") for t in plan["triggers"]):
                # A manual CLOSE from the dashboard is acted on next poll (~3s),
                # not on the 60s exit cadence — when the user hits the button they
                # mean now.
                if pending_manual_closes() or time.monotonic() - last_exit_check >= EXIT_POLL:
                    manage_open(ib, plan, spot, args.dry_run)
                    last_exit_check = time.monotonic()
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
