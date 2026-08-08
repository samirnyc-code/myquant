"""Premarket options gameplan generator — PREMIUM-SELLING ONLY (S-gexlog rewrite).

MenthorQ is GONE. The old gameplan armed triggers off MenthorQ EOD gamma levels
(PS0/CR0/HVL/GW0) and a dealer-gamma regime; none of that survived our own
backtests, so it was purged 2026-08-04. This builder now arms ONLY defined-risk
premium-selling structures, placed off the VIX-implied expected-move band, and it
trades every available structure IN PARALLEL for a forward comparison.

Strike source: the 1-day expected move, EM = spot * VIX / sqrt(252) (VIX is the
prior close; this is the same formula GexLog and MenthorQ both use, and the only
range estimate that held up in testing). No level file, no regime gate.

Structures armed each day (0DTE, fire once near the open, hold to the time-stop):
  sell_bps       bull put spread,  short ~1sigma below spot
  sell_bcs       bear call spread, short ~1sigma above spot
  sell_bps_atm   bull put spread,  short AT the money
  sell_bcs_atm   bear call spread, short AT the money
Reconstructed structures (summed in analysis, no separate trade):
  iron condor = sell_bps + sell_bcs ;  iron fly = sell_bps_atm + sell_bcs_atm
Plus the STMR 15:59 bull put spread (the one validated edge; run by the sim daemon).

Everything is entered unconditionally (arm.regime = "any") — this is a
data-collection forward test, not a gated strategy. The daemon exits each vertical
on short-strike acceptance (its thesis_broken level rule) or the 14:45 time-stop.

Run premarket (Task Scheduler) or any time:
  .venv/Scripts/python.exe scripts/options_gameplan.py [--date YYYYMMDD] [--spot 5000] [--vix 16]
Writes data/options_sim/gameplan_YYYYMMDD.json and prints the plan.
"""
import argparse
import csv
import datetime as dt
import glob
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
VIX_FILE = ROOT / "data" / "vix_daily.csv"
CT = ZoneInfo("America/Chicago")

STRIKE_STEP = 5      # SPXW strikes are 5pt apart near ATM
WING = 25            # protective long distance (points) — defined risk = (WING - credit)
SQRT252 = 15.874507866387544
ENTRY_AT = "08:30"   # fire IMMEDIATELY at the 08:30 CT open — open-centered strikes
                     # are struck from the first live tick after the bell
ENTRY_WINDOW = ["08:30", "09:30"]

# Execution policy. Grade gate OFF (F): unconditional data collection. Credit floor
# low so ~16-delta 0DTE spreads are not disarmed for being cheap (we WANT the data).
MIN_GRADE = "F"
MIN_CREDIT_ABS = 0.10
EXITS = {
    "level_accept_mins": 10,      # spot must HOLD beyond the short strike this long to count as accepted
    "regime_invalidation": True,  # harmless here (premium setups are not PIN/ANTI-PIN)
    "time_stop": "14:45",         # flat before the 0DTE gamma cliff (hold-to-expiry is proven negative)
}


GRADE_RANK = {"A": 6, "B": 5, "B-": 4, "C+": 4, "C": 3, "C-": 2, "D": 1, "F": 0}


def grade_ok(grade, minimum=MIN_GRADE):
    """True if `grade` meets the bar. Unknown/non-letter grades pass (informational
    rows); the fill-time gate re-checks. Imported by options_trigger_daemon."""
    g = GRADE_RANK.get(str(grade).strip())
    return True if g is None else g >= GRADE_RANK[minimum]


def now_ct():
    return dt.datetime.now(CT)


def event_gate(gx):
    """#20 gamma-regime event gate (VALIDATED 2026-08-08 on 82 archive days,
    scripts/gexlog_event_gate_validate.py). ADVISORY ONLY — the desk trades every
    structure every day for the parallel comparison, so this records a posture, it
    does not disarm triggers. It tells us which event days to actually stand aside on
    once real money is on: EM-held by cell was POS+event 83%, NEG+event 65% (worst).
    """
    if not bool(gx.get("event_day")):
        return {"event_day": False, "gamma": gx.get("gamma_regime", "?"),
                "verdict": "NORMAL", "advisory": False,
                "note": "no high-impact scheduled macro print today"}
    gm = gx.get("gamma_regime", "?")
    titles = ", ".join(gx.get("event_titles") or []) or "scheduled print"
    if gm == "NEG":
        return {"event_day": True, "gamma": "NEG", "verdict": "STAND_ASIDE", "advisory": True,
                "note": f"NEG-gamma event day ({titles}) — archive EM-held only 65% "
                        "(worst cell; breaks are TREND-strong). Real-money posture: "
                        "size down / widen wings / go directional. Paper still trades all for the record."}
    if gm == "POS":
        return {"event_day": True, "gamma": "POS", "verdict": "TRADE_NORMAL", "advisory": True,
                "note": f"POS-gamma event day ({titles}) — archive EM-held 83% (~= non-event). "
                        "Positive gamma dampens the print (08-07 NFP +$1,367). Trade normal, "
                        "but damper≠wall (06-05 POS-NFP still broke) — never naked."}
    return {"event_day": True, "gamma": "?", "verdict": "CAUTION", "advisory": True,
            "note": f"event day ({titles}) with UNKNOWN gamma regime — treat as caution."}


def rnd(x, step=STRIKE_STEP):
    return None if x is None else round(x / step) * step


def latest_vix():
    """Prior VIX close from data/vix_daily.csv (date, [open, high, low,] close)."""
    if not VIX_FILE.exists():
        raise SystemExit(f"no VIX file at {VIX_FILE} — cannot size the EM band.")
    rows = list(csv.DictReader(open(VIX_FILE)))
    if not rows:
        raise SystemExit("VIX file is empty.")
    last = rows[-1]
    return float(last["close"]), str(last["date"])


def em_halfwidth(spot, vix):
    """1-day expected move in index points: spot * (VIX/100) / sqrt(252)."""
    return spot * (vix / 100.0) / math.sqrt(252.0)


def preopen_spot():
    """Best spot before/around the open: live feed if ticking, else last tape tick."""
    live = SIM / "live.json"
    if live.exists():
        try:
            d = json.loads(live.read_text())
            if d.get("state") == "live" and d.get("spx"):
                return float(d["spx"]), f"{d.get('ts_et', '')[:5]} live"
        except Exception:
            pass
    for f in reversed(sorted(glob.glob(str(SIM / "underlying_*.csv")))):
        with open(f, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            return float(rows[-1]["und"]), f"{rows[-1]['ts_et'][-8:-3]} tape"
    return None, None


def _vert(tid, setup, name, right, short, stream, note):
    long = short - WING if right == "P" else short + WING
    return {
        "id": tid, "setup": setup, "stream": stream, "path": "—", "name": name,
        "arm": {"regime": "any"},
        "fire": {"type": "time_at", "not_before": ENTRY_AT},
        "window": ENTRY_WINDOW,
        "structure": {"kind": "vertical", "right": right, "short": short, "long": long, "width": WING},
        "projected_grade": "C", "grade_basis": note,
    }


def _vert_dyn(tid, setup, name, right, offset, stream, note):
    """Strikes resolved AT FIRE from the live (open) spot: short = round(spot+offset).
    The daemon converts kind 'vertical_dynamic' -> 'vertical' before building legs."""
    return {
        "id": tid, "setup": setup, "stream": stream, "path": "—", "name": name,
        "arm": {"regime": "any"},
        "fire": {"type": "time_at", "not_before": ENTRY_AT},
        "window": ENTRY_WINDOW,
        "structure": {"kind": "vertical_dynamic", "right": right, "offset": offset, "width": WING},
        "projected_grade": "C", "grade_basis": note,
    }


def build_triggers(spot, vix, gx):
    """Premium-selling structures in parallel, separate P&L streams:
       eod    — iron condor centered on the PRIOR CLOSE ± expected move (gexlog band)
       open   — iron condor centered on the OPEN ± the SAME move (struck at 08:35)
       fly    — ATM iron fly, struck at the open
       gexlog — iron condor at gexlog's putWall / callWall
       stmr   — the 15:59 validated bull put spread
    eod vs open share the same ± width; only the CENTER differs — a clean A/B on
    anchoring the range to the prior close vs the actual open."""
    hw = em_halfwidth(spot, vix)
    # STALENESS GUARD: only trust the brief if it was generated TODAY. A late/stale
    # brief is anchored to the WRONG prior close (e.g. 08-03 morning band was 186pt
    # below the 08-03 close) — building on it would misplace every EOD strike.
    today_et = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    fresh = (str(gx.get("generated_at") or "").startswith(today_et)
             or bool(gx.get("_trusted_test_brief")))
    if not fresh:
        gx = dict(gx, emLower=None, emUpper=None, expectedMove=None,
                  current=None, putWall=None, callWall=None)
    move = gx.get("expectedMove") or hw
    prior_close = gx.get("current") or spot   # stale/no brief -> last tape ≈ prior close
    em_lo = gx.get("emLower") if gx.get("emLower") else prior_close - move
    em_hi = gx.get("emUpper") if gx.get("emUpper") else prior_close + move
    band_src = ("gexlog brief" if gx.get("emLower")
                else f"computed VIX {vix:.1f}" + ("" if fresh else " (brief STALE — gx condor skipped)"))
    lo, hi, pc = rnd(em_lo), rnd(em_hi), rnd(prior_close)

    # EVERY centered strategy is traded in BOTH versions each day — EOD-centered
    # (prior close) and OPEN-centered (struck at 08:35). Same strategy, only the
    # center differs, so P&L splits cleanly by EOD vs Open.
    T = [
        # ===== EOD-centered (prior close) — fixed premarket =====
        _vert("eodic_p", "eodic_p", f"[EOD] Bull Put @ {lo:.0f}", "P", lo,
              "eod", f"EOD condor put — prior-close EM low ({band_src})"),
        _vert("eodic_c", "eodic_c", f"[EOD] Bear Call @ {hi:.0f}", "C", hi,
              "eod", f"EOD condor call — prior-close EM high ({band_src})"),
        _vert("eodfly_p", "eodfly_p", f"[EOD] Bull Put @ {pc:.0f} (ATM)", "P", pc,
              "eod", "EOD fly put — ATM = prior close"),
        _vert("eodfly_c", "eodfly_c", f"[EOD] Bear Call @ {pc:.0f} (ATM)", "C", pc,
              "eod", "EOD fly call — ATM = prior close"),
        # ===== OPEN-centered — strikes struck at fire (08:35) =====
        _vert_dyn("openic_p", "openic_p", f"[Open] Bull Put @ open-{move:.0f}", "P", -move,
                  "open", f"Open condor put — {move:.0f}pt below the open"),
        _vert_dyn("openic_c", "openic_c", f"[Open] Bear Call @ open+{move:.0f}", "C", move,
                  "open", f"Open condor call — {move:.0f}pt above the open"),
        _vert_dyn("openfly_p", "openfly_p", "[Open] Bull Put @ ATM(open)", "P", 0,
                  "open", "Open fly put — ATM = open"),
        _vert_dyn("openfly_c", "openfly_c", "[Open] Bear Call @ ATM(open)", "C", 0,
                  "open", "Open fly call — ATM = open"),
    ]
    # GexLog's own suggested condor — at its gamma walls (its own stream)
    pw, cw = gx.get("putWall"), gx.get("callWall")
    if pw and cw:
        T += [
            _vert("gx_bps", "gx_bps", f"[GexLog] Bull Put @ putWall {pw:.0f}", "P", rnd(pw),
                  "gexlog", "gexlog suggested: short put at its Put Wall"),
            _vert("gx_bcs", "gx_bcs", f"[GexLog] Bear Call @ callWall {cw:.0f}", "C", rnd(cw),
                  "gexlog", "gexlog suggested: short call at its Call Wall"),
        ]
    # STMR 15:59 bull put spread — the one validated edge; run by options_sim_daemon.
    T.append({
        "id": "bps_stmr_1559", "setup": "bps_stmr", "stream": "stmr", "path": "—",
        "name": "STMR Bull Put Spread (15:59 signal)",
        "arm": {"regime": "any"},
        "fire": {"type": "signal_1559", "cond": "%K8<15 AND spot>SMA100"},
        "window": ["14:59", "14:59"],
        "structure": {"kind": "vertical", "right": "P", "short": "~30Δ", "width": 50, "dte": 14},
        "projected_grade": "A/B if signal fires",
        "grade_basis": "the only validated edge; executed by options_sim_daemon at 14:59 CT",
        "note": "run by options_sim_daemon.py, NOT the trigger daemon",
    })
    # structure GROUP (one tile per structure) + CENTER (eod/open P&L split)
    GROUPS = {"eodic_p": "[EOD] Iron Condor", "eodic_c": "[EOD] Iron Condor",
              "eodfly_p": "[EOD] Iron Fly", "eodfly_c": "[EOD] Iron Fly",
              "openic_p": "[Open] Iron Condor", "openic_c": "[Open] Iron Condor",
              "openfly_p": "[Open] Iron Fly", "openfly_c": "[Open] Iron Fly",
              "gx_bps": "[GexLog] Iron Condor", "gx_bcs": "[GexLog] Iron Condor",
              "bps_stmr": "STMR Bull Put Spread"}
    for t in T:
        t["group"] = GROUPS.get(t["id"], t.get("name"))
        t["center"] = t.get("stream")   # eod | open | gexlog | stmr
    # BRIEF-DRIVEN WAIT (2026-08-04, user decision): when the playbook says WAIT
    # for an event (all scenarios "WAIT for JOLTs..."), shift EVERY entry to
    # 09:05 CT — after the 09:00 CT / 10:00 ET data. Deterministic from the brief,
    # so the scheduled --force rebuild reproduces it. The OPEN is still captured
    # at 08:30 by the daemon; dynamic strikes are struck from the 09:05 spot.
    # (revised 08-04: EOD strategies keep the 08:30 open entry — their strikes are
    # premarket-fixed; only the entry-spot-dependent streams (open, gexlog) wait.)
    # SAFE DEFAULT (2026-08-07, NFP-blind lesson): if the brief is missing/blocked/
    # stale we CANNOT see a WAIT instruction — so assume one. Trading blind at the
    # bell on an unread event day is the aggressive choice; blind days take the
    # conservative posture instead.
    brief_blind = bool(gx.get("error")) or not fresh
    if brief_blind:
        gx["playbook_wait"] = True
    if gx.get("playbook_wait"):
        for t in T:
            if t["fire"].get("type") == "time_at" and t.get("stream") in ("open", "gexlog"):
                t["fire"]["not_before"] = "09:05"
                t["window"] = ["09:05", "10:00"]
                t["grade_basis"] = (t.get("grade_basis", "") +
                                    " [WAIT day: entry 09:05 CT post-event per brief]")
    return T, band_src, round(em_lo, 1), round(em_hi, 1), round(move, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (default today CT)")
    ap.add_argument("--spot", type=float, help="override pre-open spot")
    ap.add_argument("--vix", type=float, help="override VIX (default: latest close)")
    ap.add_argument("--brief-date", help="TEST: use the archived GexLog brief from this date "
                                         "(YYYY-MM-DD) and trust it even though it is not today's")
    ap.add_argument("--restore", action="store_true", help="rebuild a damaged record with fired triggers")
    ap.add_argument("--force", action="store_true", help="overwrite the morning plan (before any fire)")
    args = ap.parse_args()

    date = args.date or now_ct().strftime("%Y%m%d")
    spot, spot_src = (args.spot, "manual") if args.spot is not None else preopen_spot()
    if spot is None:
        raise SystemExit("no pre-open spot available (no live feed, no tape) — pass --spot.")
    if args.vix is not None:
        vix, vix_src = args.vix, "manual"
    else:
        vix, vix_src = latest_vix()

    hw = em_halfwidth(spot, vix)

    # GexLog morning brief (published ~06:20 ET) — tag the day's FORECAST type so
    # P&L can be bucketed TREND/RANGE/CHOP later. Never fatal: on any failure the
    # day is tagged "unknown" and premium is still sold.
    try:
        from gexlog_brief import fetch as gexlog_fetch
        gx = gexlog_fetch(date=args.brief_date) if args.brief_date else gexlog_fetch()
        if args.brief_date:
            gx["_trusted_test_brief"] = True
    except Exception as e:
        gx = {"day_type": "unknown", "error": f"{type(e).__name__}: {e}"}

    triggers, band_src, em_lo, em_hi, move = build_triggers(spot, vix, gx)
    for t in triggers:
        t.update(status="armed", fired=False, trade_id=None,
                 gexlog_signal=gx.get("signal_bucket", "unknown"),
                 gexlog_day_type=gx.get("day_type", "unknown"))

    plan = {
        "date": date,
        "generated_at": now_ct().strftime("%Y-%m-%d %H:%M:%S CT"),
        "spot_preopen": spot, "spot_source": spot_src,
        "vix": vix, "vix_source": vix_src,
        "em_halfwidth": move, "em_source": band_src,
        "em_low": em_lo, "em_high": em_hi,
        "regime": "n/a (premium-only, unconditional)",
        "gexlog": gx,            # morning brief: day_type (TREND/RANGE/CHOP), signal, regime, walls
        "event_gate": event_gate(gx),   # #20 gamma-regime event posture (advisory; validated 08-08)
        "levels": {},            # kept as an empty dict so the daemon's plan["levels"].get(...) is safe
        "warnings": [],
        "execution": {"mode": "auto", "size": 1, "concurrency_cap": None,
                      "min_grade": MIN_GRADE, "min_credit_abs": MIN_CREDIT_ABS,
                      "exits": EXITS,
                      "policy": "PREMIUM-SELLING ONLY, unconditional (data collection). Four "
                                "0DTE verticals fired at the open off the VIX EM band; iron "
                                "condor = bps+bcs, iron fly = atm bps+bcs (summed in analysis). "
                                "No MenthorQ, no regime gate. Exits: short-strike acceptance or "
                                f"{EXITS['time_stop']} time-stop."},
        "scenarios": [],
        "triggers": triggers,
    }

    out = SIM / f"gameplan_{date}.json"
    if out.exists():
        prev = {}
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            had_fired = any(t.get("fired") for t in prev.get("triggers", []))
        except (ValueError, OSError):
            had_fired = False
        if had_fired and not args.restore:
            raise SystemExit(f"REFUSING to overwrite {out.name}: it has FIRED triggers (the day's "
                             f"executed record). Pass --restore only to rebuild a damaged record.")
        # S99 BLIND-CLOBBER GUARD: a LATE scheduled run (e.g. 08:28) with a blocked/
        # errored brief must NOT overwrite an EARLIER plan built off a GOOD brief. On
        # 08-07 a blind 08:28 regen replaced the morning plan and fired blind at the
        # bell. Keep the good early plan; the blind run is a no-op.
        prev_gx = (prev.get("gexlog") or {})
        prev_good = bool(prev_gx.get("generated_at")) and not prev_gx.get("error")
        if prev_good and gx.get("error") and not args.restore:
            raise SystemExit(f"KEEPING {out.name}: existing plan has a GOOD brief; this run's brief "
                             f"is blind ({gx['error']}). Refusing to clobber good with blind (S99 guard).")
        if not args.force:
            raise SystemExit(f"{out.name} exists. Use --force to regenerate (only before any fire).")
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"\nGAMEPLAN {date}  spot {spot:.0f} ({spot_src})  VIX {vix:.1f} ({vix_src})  "
          f"PREMIUM-SELLING ONLY")
    print(f"  EM band  {plan['em_low']:.0f} – {plan['em_high']:.0f}   (source: {band_src})")
    print(f"  GexLog signal: {gx.get('signal_bucket', 'unknown')} (P&L bucket)  "
          f"[day-type {gx.get('day_type', 'unknown')}, forecast '{gx.get('forecast_type')}']"
          + (f"  [brief error: {gx['error']}]" if gx.get('error') else ""))
    eg = plan["event_gate"]
    print(f"  Event gate: {eg['verdict']} (gamma {eg['gamma']}, event_day {eg['event_day']}) — {eg['note']}")
    print(f"\n  {'STREAM':7} {'SETUP':14} {'FIRE':10} STRUCTURE")
    print("  " + "-" * 78)
    for t in plan["triggers"]:
        st = t["structure"]
        desc = (f"{st['right']} short {st['short']} / long {st.get('long', '')}"
                if isinstance(st.get("short"), (int, float)) else st.get("short", ""))
        fire = t["fire"].get("not_before", t["fire"]["type"])
        print(f"  {t.get('stream', '—'):7} {t['setup']:14} {fire:10} {t['name']}  [{desc}]")
    print(f"\n  streams: eod (prior-close ±{move:.0f}) · open (open ±{move:.0f}, struck at {ENTRY_AT}) · "
          f"fly (ATM) · gexlog (walls) · stmr")

    # push the day's plan to Telegram — HTML, stacked per structure, no link preview
    try:
        from notify_telegram import send
        cats = gx.get("catalysts_today") or []
        hi = gx.get("high_impact_today") or 0
        sig = gx.get("signal_bucket", "?")
        sig_ico = {"GO": "🟢", "CAUTION": "🟡", "WAIT": "🔴"}.get(sig, "⚪")
        dt_ico = {"RANGE": "🟢", "CHOP": "🟡", "TREND": "🔴", "HIVOL": "🟠"}.get(gx.get("day_type"), "⚪")

        def sk(tid):
            st = next((t["structure"] for t in plan["triggers"] if t["id"] == tid), None)
            if not st:
                return None
            if st.get("kind") == "vertical_dynamic":
                off = st["offset"]
                return "ATM(open)" if off == 0 else f"open{off:+.0f}"
            return f"{st.get('short'):.0f}" if isinstance(st.get("short"), (int, float)) else str(st.get("short"))

        L = [f"📋 <b>GAMEPLAN {date}</b>",
             f"{sig_ico} <b>{sig}</b> · {dt_ico} {gx.get('day_type', '?')} · conf {gx.get('confidence', '?')}%",
             "",
             f"📍 EOD <b>{(gx.get('current') or spot):.0f}</b> · EM ±<b>{move:.0f}</b> · VIX {vix:.2f}",
             f"🛡 band <b>{em_lo:.0f}–{em_hi:.0f}</b> · walls <b>{gx.get('putWall') or '—'} / {gx.get('callWall') or '—'}</b>"]
        if gx.get("gap_note"):
            L.append(f"↗️ gap <b>{gx['gap_note']}</b>"
                     + (f" · ES premkt {gx['es_premarket']:.0f}" if gx.get("es_premarket") else ""))
        if gx.get("calendar_note"):
            L.append(f"📅 calendar <b>{gx['calendar_note']}</b>")
        if gx.get("playbook_wait"):
            L.append("⏳ <b>WAIT day: ALL entries 09:05 CT (post-event, per brief)</b>")
        eg = plan["event_gate"]
        if eg.get("advisory"):
            eg_ico = {"STAND_ASIDE": "🛑", "TRADE_NORMAL": "✅", "CAUTION": "⚠️"}.get(eg["verdict"], "•")
            L.append(f"{eg_ico} <b>Event gate: {eg['verdict']}</b> (gamma {eg['gamma']}) "
                     f"— {', '.join(gx.get('event_titles') or []) or 'scheduled print'}")
        if gx.get("stale_risk"):
            L.append("⚠️ their caveat: quote-derived close (pivots approximate)")
        L.append("")
        pairs = [("🔵 <b>EOD Condor</b>", sk("eodic_p"), sk("eodic_c")),
                 ("🔵 <b>EOD Fly</b>", sk("eodfly_p"), sk("eodfly_c")),
                 ("⚪ <b>Open Condor</b>", sk("openic_p"), sk("openic_c")),
                 ("⚪ <b>Open Fly</b>", sk("openfly_p"), sk("openfly_c")),
                 ("🟣 <b>GexLog Walls</b>", sk("gx_bps"), sk("gx_bcs"))]
        for name, p, c in pairs:
            if p and c:
                L.append(f"{name}\n      <code>P {p}  ·  C {c}</code>")
        L.append("🟢 <b>STMR 15:59</b>\n      <code>P ~30Δ (only if signal fires)</code>")
        L.append("")
        if cats:
            head_c = f"📅 catalysts {len(cats)}" + (f" · <b>{hi} HIGH</b> ⚠️" if hi else "")
            L.append(head_c)
            for c in cats:
                imp = " ⚠️" if c.get("impact") == "high" else ""
                L.append(f"      {c.get('time')}  {c.get('title')}{imp}")
        L.append("")
        L.append("🔗 <a href='https://gexlog.com/dashboard/'>morning brief</a> · "
                 "<a href='https://gexlog.com/dashboard/history/'>archive</a>")
        send("\n".join(L), level="info", html=True, no_preview=True)
        print("  → pushed to Telegram")
    except Exception as e:
        print(f"  (telegram push skipped: {type(e).__name__})")
    print(f"\nwrote {out}  ({len(plan['triggers'])} triggers armed)")
    return out


if __name__ == "__main__":
    main()
