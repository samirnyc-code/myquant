"""Premarket options gameplan generator (S75).

Turns the EOD MenthorQ gamma levels + a pre-open spot snapshot into a committed
plan of ARMED TRIGGERS for the day — one per setup/scenario, spanning every
grade tier — so the desk is prepared before the bell. The intraday trigger
daemon (`options_trigger_daemon.py`) then watches the live feed and fires each
trigger when its condition is met (auto-execute, 1 lot, notify after).

Design principles:
  * Deterministic — same levels + same pre-open spot => same plan, every day.
    The *only* judgment encoded is the playbook's setup->level->grade mapping,
    which is exactly the hypothesis we are collecting data to validate.
  * Causal / no lookahead — triggers fire on live price as it happens; the
    daemon places REAL paper orders (real fills, per the fill-realism rule).
  * Grade at plan-time is PROJECTED from regime + distance-to-level. The FINAL
    grade is stamped at fill when the real credit/debit is known.
  * Take everything that triggers regardless of grade (data collection). The
    daemon skips only structurally-broken fills (zero/negative credit).

Regime (dealer gamma, NOT the Brooks engine): spot >= HVL => positive gamma
(pin / fade-the-extremes); spot < HVL => negative gamma (moves amplify).

Run premarket (Task Scheduler ~08:25 CT) or any time to (re)generate:
  .venv/Scripts/python.exe scripts/options_gameplan.py [--date YYYYMMDD] [--spot 7543]
Writes data/options_sim/gameplan_YYYYMMDD.json and prints the plan.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # Windows console defaults to cp1252 — the plan text uses ≥ – → Δ − etc.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LEVELS_FILE = ROOT / "scratchpad" / "mq_levels_today.json"
CT = ZoneInfo("America/Chicago")  # exchange time (Chicago / Central); market opens 08:30 CT

STRIKE_STEP = 5  # SPXW strikes are 5pt apart near ATM


def now_ct():
    return dt.datetime.now(CT)


def rnd(x, step=STRIKE_STEP):
    return None if x is None else round(x / step) * step


def load_levels():
    if not LEVELS_FILE.exists():
        raise SystemExit(f"no levels file at {LEVELS_FILE} — fill/paste MenthorQ EOD levels first.")
    return json.loads(LEVELS_FILE.read_text(encoding="utf-8"))


def preopen_spot():
    """Best available spot before/around the open: live feed if ticking, else
    the last underlying tape tick, else None."""
    live = SIM / "live.json"
    if live.exists():
        try:
            d = json.loads(live.read_text())
            if d.get("state") == "live" and d.get("spx"):
                return float(d["spx"]), f"{d.get('ts_et','')[:5]} live"
        except Exception:
            pass
    import glob
    for f in reversed(sorted(glob.glob(str(SIM / "underlying_*.csv")))):
        import csv
        with open(f, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if rows:
            return float(rows[-1]["und"]), f"{rows[-1]['ts_et'][-8:-3]} tape"
    return None, None


def regime(spot, hvl):
    if spot is None or hvl is None:
        return "unknown", "need spot + HVL"
    if spot >= hvl:
        return "positive_gamma", f"spot {spot:.0f} ≥ HVL {hvl:.0f} — dealers long gamma; pin / fade extremes"
    return "negative_gamma", f"spot {spot:.0f} < HVL {hvl:.0f} — dealers short gamma; moves amplify"


# ---------------------------------------------------------------------------
# Price-path scenarios — the premarket "what may play out" map. Descriptive;
# each trigger below references the path(s) it belongs to.
# ---------------------------------------------------------------------------

def scenarios(spot, L):
    ps0, hvl, gw0, cr0, cr, ps = (L[k] for k in ("ps0", "hvl", "gw0", "cr0", "cr", "ps"))
    return [
        {"id": "A", "name": "Grind up to the wall",
         "path": f"spot {spot:.0f} → {cr0:.0f}" if spot else "→ CR0/GW0",
         "means": "tags CR0/GW0 resistance",
         "acts": "CR0 touch-fade (short call spread); fly @ GW0 if it pins there"},
        {"id": "B", "name": "Fade to support",
         "path": f"spot {spot:.0f} → {hvl:.0f} → {ps0:.0f}" if spot else "→ HVL → PS0",
         "means": "tests HVL then PS0",
         "acts": "PS0 touch-fade (short put spread); regime still + while HVL holds"},
        {"id": "C", "name": "Pin / chop (base case, +gamma)",
         "path": f"chop {hvl:.0f}–{cr0:.0f}" if hvl and cr0 else "range-bound",
         "means": "the pin — positive gamma pins price",
         "acts": "both premium-sells decay; fly @ GW0 ideal"},
        {"id": "D", "name": "Break below HVL",
         "path": f"spot < {hvl:.0f}" if hvl else "< HVL",
         "means": "regime tips toward negative gamma",
         "acts": f"premium-sells STAND DOWN; straddle arms; PS {ps:.0f} next magnet" if ps else "straddle arms"},
    ]


# ---------------------------------------------------------------------------
# Trigger builders. Condition-driven (not clock-driven). Grade is PROJECTED;
# the final grade is stamped at fill by the daemon from the realized credit.
# Fire schema understood by options_trigger_daemon.py:
#   {"type":"touch","level":L,"dir":"from_below"|"from_above","first_only":true}
#   {"type":"first_of","touch":{...},"not_before":"HH:MM"}   # touch OR time
#   {"type":"time_at","not_before":"HH:MM"}
#   {"type":"regime_break","level":L,"dir":"below"}
#   {"type":"signal_1559"}                                    # informational
# arm.regime gates whether the trigger is eligible; window bounds validity.
# ---------------------------------------------------------------------------

def _dist_grade(dist, positive):
    if not positive:
        return "C", "off primary regime (premium-sell wants positive gamma)"
    if dist >= 40:
        return "B", f"positive gamma, short ~{dist:.0f}pt OTM (≥40pt cushion); A+ if credit ≥0.80 at fill"
    if dist >= 25:
        return "C", f"positive gamma but short only ~{dist:.0f}pt OTM (25–40pt band)"
    return "D", f"short <25pt OTM (~{dist:.0f}pt) — thin cushion"


def build_triggers(spot, lv, reg):
    positive = reg == "positive_gamma"
    L = {k: lv.get(k) for k in ("ps", "ps0", "hvl", "gw0", "cr0", "cr")}
    T = []

    # 1. Put credit spread @ PS0 — first of {price tags PS0 from above, or 09:00
    #    regime-confirmation}, within 08:45–10:00. Condition-driven with a
    #    theta-capture backstop so we don't miss the day if price never tags.
    if L["ps0"]:
        short = rnd(L["ps0"])
        dist = abs(spot - short) if spot else None
        g, basis = _dist_grade(dist, positive) if dist is not None else ("?", "")
        T.append({
            "id": "sell_0dte_put", "setup": "sell_0dte_gamma", "path": "B/C",
            "name": "0DTE Put Credit Spread @ PS0",
            "arm": {"regime": "positive_gamma"},
            "fire": {"type": "first_of", "touch": {"level": short, "dir": "from_above"},
                     "not_before": "09:00"},
            "window": ["08:45", "10:00"],
            "structure": {"kind": "vertical", "right": "P", "short": short, "long": short - 25, "width": 25},
            "projected_grade": g, "grade_basis": basis,
        })

    # 2. Call credit spread @ CR0 — first of {price tags CR0 from below, or 09:00}.
    if L["cr0"]:
        short = rnd(L["cr0"])
        dist = abs(spot - short) if spot else None
        g, basis = _dist_grade(dist, positive) if dist is not None else ("?", "")
        T.append({
            "id": "sell_0dte_call", "setup": "sell_0dte_gamma", "path": "A/C",
            "name": "0DTE Call Credit Spread @ CR0",
            "arm": {"regime": "positive_gamma"},
            "fire": {"type": "first_of", "touch": {"level": short, "dir": "from_below"},
                     "not_before": "09:00"},
            "window": ["08:45", "10:00"],
            "structure": {"kind": "vertical", "right": "C", "short": short, "long": short + 25, "width": 25},
            "projected_grade": g, "grade_basis": basis,
        })

    # NB: the 0DTE iron condor is DEDUPED — at these strikes it is exactly the
    # put-spread + call-spread above, so we take the two one-sided spreads
    # instead (finer per-side data, no doubled correlated risk). See handoff.

    # 3. Butterfly at the Gamma Wall — theta/convexity play; confirm at 10:00 if
    #    positive gamma holds. (No natural touch trigger — it wants price NEAR
    #    the wall, which the pin base-case delivers.)
    if L["gw0"]:
        c = rnd(L["gw0"])
        g = "B" if positive else "F"
        basis = ("positive gamma settles near GW0; convex into the pin"
                 if positive else "no pin on a negative-gamma/trend day — the wall won't hold")
        T.append({
            "id": "fly_gw_0dte", "setup": "fly_gw_0dte", "path": "A/C",
            "name": "0DTE Call Butterfly @ GW0",
            "arm": {"regime": "positive_gamma"},
            "fire": {"type": "time_at", "not_before": "09:00"},
            "window": ["09:00", "11:00"],
            "structure": {"kind": "butterfly", "right": "C", "center": c,
                          "lower": c - 25, "upper": c + 25, "width": 25},
            "projected_grade": g, "grade_basis": basis,
        })

    # 4. CR0 first-touch-from-below fade  (S73-night survivor candidate)
    if L["cr0"]:
        short = rnd(L["cr0"])
        below = spot is not None and spot < L["cr0"]
        T.append({
            "id": "cr0_touch_fade", "setup": "cr0_fade", "path": "A",
            "name": "CR0 first-touch fade (short call spread)",
            "arm": {"regime": "any", "spot_side": {"level": short, "side": "below"}},
            "fire": {"type": "touch", "level": short, "dir": "from_below", "first_only": True},
            "window": ["08:45", "14:30"],
            "structure": {"kind": "vertical", "right": "C", "short": short, "long": short + 25, "width": 25},
            "projected_grade": "B" if below else "C",
            "grade_basis": ("armed: spot below CR0, waiting for first touch from below"
                            if below else "spot already at/above CR0 — no clean from-below touch"),
        })

    # 5. PS0 first-touch-from-above fade
    if L["ps0"]:
        short = rnd(L["ps0"])
        above = spot is not None and spot > L["ps0"]
        T.append({
            "id": "ps0_touch_fade", "setup": "ps0_fade", "path": "B",
            "name": "PS0 first-touch fade (short put spread)",
            "arm": {"regime": "any", "spot_side": {"level": short, "side": "above"}},
            "fire": {"type": "touch", "level": short, "dir": "from_above", "first_only": True},
            "window": ["08:45", "14:30"],
            "structure": {"kind": "vertical", "right": "P", "short": short, "long": short - 25, "width": 25},
            "projected_grade": "C",
            "grade_basis": ("armed: spot above PS0, waiting for first touch from above"
                            if above else "spot already at/below PS0"),
        })

    # 6. Long ATM straddle — arms only if price BREAKS BELOW HVL intraday
    #    (regime flips to negative gamma) or on an event day. On a pin day it
    #    stays dormant, waiting for path D. Center re-struck at fire time.
    if L["hvl"]:
        T.append({
            "id": "straddle_0dte", "setup": "straddle_0dte", "path": "D",
            "name": "Long ATM Straddle (0DTE)",
            "arm": {"regime": "any"},
            "fire": {"type": "regime_break", "level": rnd(L["hvl"]), "dir": "below"},
            "window": ["08:45", "13:00"],
            "structure": {"kind": "straddle", "center": "atm"},
            "projected_grade": "B if it fires",
            "grade_basis": ("dormant on a positive-gamma pin day; ARMS if spot breaks below "
                            f"HVL {L['hvl']:.0f} (regime flip → long vol makes sense)"),
        })

    # 7. 15:59 STMR Bull Put Spread — informational; executed by options_sim_daemon
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
    args = ap.parse_args()

    date = args.date or now_ct().strftime("%Y%m%d")
    lv = load_levels()
    if args.spot is not None:
        spot, spot_src = args.spot, "manual"
    else:
        spot, spot_src = preopen_spot()
    reg, reg_detail = regime(spot, lv.get("hvl"))
    L = {k: lv.get(k) for k in ("ps", "ps0", "hvl", "gw0", "cr0", "cr")}
    triggers = build_triggers(spot, lv, reg)
    paths = scenarios(spot, L) if spot else []

    plan = {
        "date": date,
        "generated_at": now_ct().strftime("%Y-%m-%d %H:%M:%S CT"),
        "spot_preopen": spot, "spot_source": spot_src,
        "regime": reg, "regime_detail": reg_detail,
        "levels": L, "d1_min": lv.get("d1_min"), "d1_max": lv.get("d1_max"),
        "execution": {"mode": "auto", "size": 1, "concurrency_cap": None,
                      "policy": "take all triggers regardless of grade; dedupe (two sides, no condor); "
                                "skip only broken fills"},
        "scenarios": paths,
        "triggers": [dict(t, status="armed", fired=False, trade_id=None) for t in triggers],
    }
    out = SIM / f"gameplan_{date}.json"
    out.write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def fire_str(fire):
        ty = fire["type"]
        if ty == "touch":
            return f"touch {fire['level']} {fire['dir'].replace('from_','')}"
        if ty == "first_of":
            return f"tag {fire['touch']['level']} or {fire['not_before']}"
        if ty == "time_at":
            return f"at {fire['not_before']}"
        if ty == "regime_break":
            return f"break {fire['dir']} {fire['level']}"
        if ty == "signal_1559":
            return "15:59 signal"
        return ty

    print(f"\nGAMEPLAN {date}   spot {spot} ({spot_src})   regime: {reg.upper()}")
    print(f"  {reg_detail}")
    print("  levels  " + "  ".join(f"{k.upper()} {v:.0f}" for k, v in L.items() if v))
    if plan["d1_min"] and plan["d1_max"]:
        print(f"  1-day range {plan['d1_min']:.0f} – {plan['d1_max']:.0f}")
    if paths:
        print("\n  PRICE PATHS (what may play out):")
        for p in paths:
            print(f"    {p['id']}. {p['name']:22} {p['path']:22} → {p['acts']}")
    print(f"\n  {'GRADE':7} {'PATH':5} {'FIRE WHEN':22} SETUP")
    print("  " + "-" * 82)
    for t in plan["triggers"]:
        print(f"  {str(t['projected_grade']):7} {t.get('path','—'):5} {fire_str(t['fire']):22} {t['name']}")
        print(f"  {'':7} {'':5} {'':22} → {t['grade_basis']}")
    print(f"\nwrote {out}  ({len(plan['triggers'])} triggers armed)")
    return out


if __name__ == "__main__":
    main()
