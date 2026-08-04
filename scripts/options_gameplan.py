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
ENTRY_AT = "08:35"   # fire once, just after the 08:30 CT open
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


def _vert(tid, setup, name, right, short, note):
    long = short - WING if right == "P" else short + WING
    return {
        "id": tid, "setup": setup, "path": "—", "name": name,
        "arm": {"regime": "any"},
        "fire": {"type": "time_at", "not_before": ENTRY_AT},
        "window": ENTRY_WINDOW,
        "structure": {"kind": "vertical", "right": right, "short": short, "long": long, "width": WING},
        "projected_grade": "C", "grade_basis": note,
    }


def build_triggers(spot, vix):
    hw = em_halfwidth(spot, vix)
    sp1 = rnd(spot - hw)     # ~1sigma below
    sc1 = rnd(spot + hw)     # ~1sigma above
    atm = rnd(spot)
    band = f"±{hw:.0f}pt (VIX {vix:.1f})"
    T = [
        _vert("sell_bps", "sell_bps", f"0DTE Bull Put Spread @ {sp1:.0f} (~1σ)", "P", sp1,
              f"short put ~1σ below spot, {band}; condor put wing"),
        _vert("sell_bcs", "sell_bcs", f"0DTE Bear Call Spread @ {sc1:.0f} (~1σ)", "C", sc1,
              f"short call ~1σ above spot, {band}; condor call wing"),
        _vert("sell_bps_atm", "sell_bps_atm", f"0DTE Bull Put Spread @ {atm:.0f} (ATM)", "P", atm,
              "short put AT the money; iron-fly put wing"),
        _vert("sell_bcs_atm", "sell_bcs_atm", f"0DTE Bear Call Spread @ {atm:.0f} (ATM)", "C", atm,
              "short call AT the money; iron-fly call wing"),
    ]
    # STMR 15:59 bull put spread — the one validated edge; run by options_sim_daemon.
    T.append({
        "id": "bps_stmr_1559", "setup": "bps_stmr", "path": "—",
        "name": "STMR Bull Put Spread (15:59 signal)",
        "arm": {"regime": "any"},
        "fire": {"type": "signal_1559", "cond": "%K8<15 AND spot>SMA100"},
        "window": ["14:59", "14:59"],
        "structure": {"kind": "vertical", "right": "P", "short": "~30Δ", "width": 50, "dte": 14},
        "projected_grade": "A/B if signal fires",
        "grade_basis": "the only validated edge; executed by options_sim_daemon at 14:59 CT",
        "note": "run by options_sim_daemon.py, NOT the trigger daemon",
    })
    return T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (default today CT)")
    ap.add_argument("--spot", type=float, help="override pre-open spot")
    ap.add_argument("--vix", type=float, help="override VIX (default: latest close)")
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
        gx = gexlog_fetch()
    except Exception as e:
        gx = {"day_type": "unknown", "error": f"{type(e).__name__}: {e}"}

    triggers = build_triggers(spot, vix)
    for t in triggers:
        t.update(status="armed", fired=False, trade_id=None,
                 gexlog_day_type=gx.get("day_type", "unknown"))

    plan = {
        "date": date,
        "generated_at": now_ct().strftime("%Y-%m-%d %H:%M:%S CT"),
        "spot_preopen": spot, "spot_source": spot_src,
        "vix": vix, "vix_source": vix_src,
        "em_halfwidth": round(hw, 1),
        "em_low": round(spot - hw, 1), "em_high": round(spot + hw, 1),
        "regime": "n/a (premium-only, unconditional)",
        "gexlog": gx,            # morning brief: day_type (TREND/RANGE/CHOP), signal, regime, walls
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
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            had_fired = any(t.get("fired") for t in prev.get("triggers", []))
        except (ValueError, OSError):
            had_fired = False
        if had_fired and not args.restore:
            raise SystemExit(f"REFUSING to overwrite {out.name}: it has FIRED triggers (the day's "
                             f"executed record). Pass --restore only to rebuild a damaged record.")
        if not args.force:
            raise SystemExit(f"{out.name} exists. Use --force to regenerate (only before any fire).")
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    print(f"\nGAMEPLAN {date}  spot {spot:.0f} ({spot_src})  VIX {vix:.1f} ({vix_src})  "
          f"PREMIUM-SELLING ONLY")
    print(f"  EM band  {spot - hw:.0f} – {spot + hw:.0f}   (±{hw:.0f}pt, 1-day VIX move)")
    print(f"  GexLog day-type: {gx.get('day_type', 'unknown')}  "
          f"(forecast '{gx.get('forecast_type')}', signal {gx.get('signal')})"
          + (f"  [brief error: {gx['error']}]" if gx.get('error') else ""))
    print(f"\n  {'STATUS':7} {'SETUP':14} {'FIRE':10} STRUCTURE")
    print("  " + "-" * 78)
    for t in plan["triggers"]:
        st = t["structure"]
        desc = (f"{st['right']} short {st['short']} / long {st.get('long', '')}"
                if isinstance(st.get("short"), (int, float)) else st.get("short", ""))
        fire = t["fire"].get("not_before", t["fire"]["type"])
        print(f"  {t['status']:7} {t['setup']:14} {fire:10} {t['name']}  [{desc}]")
    print(f"\n  iron condor = sell_bps + sell_bcs   |   iron fly = sell_bps_atm + sell_bcs_atm")
    print(f"\nwrote {out}  ({len(plan['triggers'])} triggers armed)")
    return out


if __name__ == "__main__":
    main()
