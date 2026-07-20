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
import os
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

# --- execution policy defaults (A1/A2/A4; see docs/living/handoff.md S75S) -----
# These were all implicitly "no limit" until the 7/14–7/17 review, which cost
# the desk -$7,586 across 6 auto trades. Every number here is a POLICY choice,
# not a validated one — they are written to the plan so each day records the
# rules it ran under, and so a backtest can sweep them (item D1).
# A1 is DELIBERATELY OFF ("F" = accept every grade). The grade ladder has never
# been validated against outcomes, and on the only 16 trades we have, B is the
# WORST bucket (mean -$614) while B- is positive. Gating on a ladder that
# anti-correlates with P&L would just be a confident way to be wrong. Turn this
# back on only after the D1 backtest says the ladder predicts anything.
MIN_GRADE = "F"
# A4/A5 numbers below are NOT invented — they are the playbook's own documented
# entry rules for sell_0dte_gamma (§3), which existed the whole time and were
# never enforced by any code:
#   "require spot >= 40pts from the short strike AND net credit >= 0.80"
# On 2026-07-16 the desk fired one at 3pt for $9.90 and another at 3pt for $7.90.
# The rules were right; nothing read them.
MIN_CREDIT_ABS = 0.80   # A4: playbook §3 minimum net credit
MIN_OTM_PTS = 40        # A5: playbook §3 minimum distance from the short strike
# Below are STRUCTURAL, not tuned: SPXW strikes are 5pt apart, so "one strike
# away" is the smallest separation that can exist, and two orders on the SAME
# short strike are the same trade twice by definition. No number was chosen.
MIN_FADE_SEP = STRIKE_STEP  # a fade needs the level at least one strike away

# A3 — EXIT RULES. Before 2026-07-18 there were NONE: all 17 logged trades show
# close_reason blank/'expired'. Nothing was ever managed, so winners rode to
# expiry for pennies (+$32) and losers rode to expiry for the full width
# (-$1,513, -$1,713, -$2,471). A 0DTE position held to expiry has no exit policy,
# it has a coin flip. These are POLICY numbers awaiting the D1 backtest sweep.
#
# EXITS ARE THESIS-BASED, NOT P&L-BASED. We stay in while the reason for the
# trade is still true, and leave when it stops being true — full stop.
#
# This is not a preference, it is the only exit evidence we own. The playbook's
# §1 exit shootout (142 trades, scripts/mr_bps_exit_rules.py) tested this
# directly on the flagship:
#     signal exit (spot > SMA5) ... PF 1.74   +$14.7K   maxDD -$6.3K
#     hold to expiry .............. PF 0.95   (negative)
#     profit target at 50% ........ PF 0.97   (flat)
#     price stops ................. PF 0.71-0.84  (POISON — they sell the
#                                                  pre-bounce low)
# Its verdict: "NO price stops, NO expiry holds, NO profit targets — exit on the
# signal only." A price stop on a level trade exits precisely when the level is
# being TESTED, which is the thesis working, not failing.
#
# So: no profit target, no P&L stop. A position dies when its LEVEL fails, when
# its REGIME flips, or at the 0DTE clock — nothing else.
# Only ONE number below is a free choice, and it is marked. The rest are
# structural: the short strike IS the boundary the thesis lives on (beyond it the
# spread is in the money and "it stays OTM" is simply false), and HVL IS the
# regime boundary by definition. No distances were tuned.
EXITS = {
    "level_accept_mins": 10,     # ⚠ UNCALIBRATED — the only tuned number here.
                                 # Wick filter: how long spot must HOLD beyond the
                                 # short strike before we call it acceptance. Needs
                                 # intraday data we do not own; forward-test it.
    "regime_invalidation": True, # structural: pin structures need spot >= HVL
    "time_stop": "14:45",        # ⚠ CHOICE — before 15:00 CT settlement. Holding to
                                 # expiry is proven negative (PF 0.95), so SOME cutoff
                                 # is required; this particular minute is not proven.
}


def _fade_grade(positive, aligned):
    """Projected grade for a first-touch fade, mirroring grade_at_fill's fade
    branch in the trigger daemon (positive gamma = wall likely holds). These two
    ladders disagreed until 2026-07-18: the plan hardcoded PS0 fades to 'C' while
    the fill grader called the identical trade 'B'."""
    if not aligned:
        return "C", "spot is already at/through the level — no clean first touch"
    if positive:
        return "B", "positive-gamma first-touch fade (regime + level + trigger aligned)"
    return "D", "NEG-gamma fade — fading into momentum, the wall likely breaks"

GRADE_RANK = {"A": 6, "B": 5, "B-": 4, "C+": 4, "C": 3, "C-": 2, "D": 1, "F": 0}


def grade_ok(grade, minimum=MIN_GRADE):
    """True if `grade` meets the bar. Unknown/non-letter grades pass (they are
    informational rows like 'B if it fires'); the fill-time gate re-checks."""
    g = GRADE_RANK.get(str(grade).strip())
    return True if g is None else g >= GRADE_RANK[minimum]


def now_ct():
    return dt.datetime.now(CT)


def rnd(x, step=STRIKE_STEP):
    return None if x is None else round(x / step) * step


def load_levels():
    """Load today's MenthorQ levels, refusing to arm on levels MenthorQ never republished.

    S75V: mq_levels_fetch now records whether the SOURCE timestamp advanced since the last
    pull. If MenthorQ has not published yet, their endpoint returns yesterday's numbers
    quite happily — and this file would arm a full day of triggers off stale levels with
    nothing anywhere to flag it. A gameplan built on stale levels is worse than no
    gameplan: it looks committed and considered, and it is neither.
    """
    if not LEVELS_FILE.exists():
        raise SystemExit(f"no levels file at {LEVELS_FILE} — fill/paste MenthorQ EOD levels first.")
    d = json.loads(LEVELS_FILE.read_text(encoding="utf-8"))
    if d.get("_stale_warning"):
        print(f"  *** STALE LEVELS: {d['_stale_warning']}")
        if not os.environ.get("MYQUANT_ALLOW_STALE_LEVELS"):
            raise SystemExit(
                "REFUSING to build a gameplan on stale levels.\n"
                f"  source_ts {d.get('_source_ts')} did not advance (prev {d.get('_prev_source_ts')}).\n"
                "  Re-run scripts/mq_levels_fetch.py once MenthorQ has published, or set\n"
                "  MYQUANT_ALLOW_STALE_LEVELS=1 to override deliberately.")
    return d


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

def level_warnings(spot, L):
    """A5 — sanity-check the level stack BEFORE it becomes a plan.

    On 2026-07-16 the builder emitted PS0 7555 against a 7557.75 pre-open spot:
    a 'support' level 3pt BELOW price. It graded the resulting trade D in its own
    output and fired it anyway for a full -$1,513 loss, and the scenario text read
    'spot 7558 -> 7535 -> 7555' (down to HVL, then back UP to support). Nothing in
    the code objected. Each check below returns (code, human_text, disarm_ids).
    """
    W = []
    if spot is None:
        return W
    ps0, hvl, cr0, cr, ps = (L.get(k) for k in ("ps0", "hvl", "cr0", "cr", "ps"))

    # 1. Sides must be on the correct side of spot to mean what their name says.
    if ps0 is not None and ps0 >= spot:
        W.append(("ps0_above_spot",
                  f"PS0 {ps0:.0f} is AT/ABOVE spot {spot:.0f} — that is not support. "
                  f"Put premium-sell + PS0 fade disarmed.",
                  ["sell_0dte_put", "ps0_touch_fade"]))
    if cr0 is not None and cr0 <= spot:
        W.append(("cr0_below_spot",
                  f"CR0 {cr0:.0f} is AT/BELOW spot {spot:.0f} — that is not resistance. "
                  f"Call premium-sell + CR0 fade disarmed.",
                  ["sell_0dte_call", "cr0_touch_fade"]))

    # 2. Premium-sells need real cushion. A fade sits AT its level by design and
    #    is exempt (see grade_at_fill's fade branch — distance is the wrong axis).
    if ps0 is not None and 0 < (spot - ps0) < MIN_OTM_PTS:
        W.append(("ps0_too_close",
                  f"PS0 {ps0:.0f} is only {spot - ps0:.0f}pt below spot (<{MIN_OTM_PTS}pt) — "
                  f"put premium-sell disarmed (fade may still arm).",
                  ["sell_0dte_put"]))
    if cr0 is not None and 0 < (cr0 - spot) < MIN_OTM_PTS:
        W.append(("cr0_too_close",
                  f"CR0 {cr0:.0f} is only {cr0 - spot:.0f}pt above spot (<{MIN_OTM_PTS}pt) — "
                  f"call premium-sell disarmed (fade may still arm).",
                  ["sell_0dte_call"]))

    # 2b. A first-touch fade needs the level to be a DESTINATION. If spot already
    #     sits on it, "first touch" fires on the next random tick — which is
    #     exactly what happened on 2026-07-16: PS0 was 3pt away at the open and
    #     ps0_fade fired at 09:06 for a full -$1,713 loss. Distance is the wrong
    #     axis for grading a fade, but it is the right axis for arming one.
    for name, lvl, ids in (("PS0", ps0, ["ps0_touch_fade"]), ("CR0", cr0, ["cr0_touch_fade"])):
        if lvl is not None and abs(spot - lvl) < MIN_FADE_SEP:
            W.append((f"{name.lower()}_no_approach",
                      f"{name} {lvl:.0f} is {abs(spot - lvl):.0f}pt from spot {spot:.0f} "
                      f"(<{MIN_FADE_SEP}pt) — no room for a clean approach, so 'first touch' is "
                      f"noise. Fade disarmed.", ids))

    # 3. Stack ordering. Not fatal on its own, but it means the day's map is
    #    incoherent and the scenario paths will read as nonsense.
    stack = [("PS", ps), ("PS0", ps0), ("HVL", hvl), ("CR0", cr0), ("CR", cr)]
    known = [(n, v) for n, v in stack if v is not None]
    inverted = [f"{known[i][0]}>{known[i+1][0]}" for i in range(len(known) - 1)
                if known[i][1] > known[i + 1][1]]
    if inverted:
        W.append(("stack_inverted",
                  "level stack out of order (" + ", ".join(inverted) +
                  ") — the scenario map is unreliable today.", []))
    return W


def scenarios(spot, L, reg):
    """A8 — the price-path map, written for the regime that actually holds.

    Until 2026-07-18 this emitted the positive-gamma template unconditionally, so
    the 7/17 plan (spot 7479 < HVL 7540, negative gamma) told the reader the base
    case was 'Pin / chop (base case, +gamma)' and that path D was 'break below
    HVL' — a break that had ALREADY happened before the open.
    """
    ps0, hvl, gw0, cr0, cr, ps = (L[k] for k in ("ps0", "hvl", "gw0", "cr0", "cr", "ps"))
    s = f"{spot:.0f}" if spot else "spot"

    if reg == "negative_gamma":
        return [
            {"id": "A", "name": "Reclaim HVL",
             "path": f"spot {s} → {hvl:.0f}" if hvl else "→ HVL",
             "means": "regime flips back to positive gamma; the pin returns",
             "acts": "premium-sells RE-ARM above HVL; until then they stay down"},
            {"id": "B", "name": "Amplified slide",
             "path": f"spot {s} → {ps0:.0f} → {ps:.0f}" if (ps0 and ps) else "→ PS0 → PS",
             "means": "dealers short gamma sell into weakness — moves extend",
             "acts": "long vol works; do NOT fade support into momentum"},
            {"id": "C", "name": "Trend / expansion (base case, −gamma)",
             "path": f"range expands beyond {ps0:.0f}–{hvl:.0f}" if (ps0 and hvl) else "range expands",
             "means": "no pin — this is the regime that makes range, not chop",
             "acts": "straddle is the structure; premium-sells STAND DOWN"},
            {"id": "D", "name": "Capitulation through PS",
             "path": f"spot < {ps:.0f}" if ps else "< PS",
             "means": "below the last gamma support — nothing structural beneath",
             "acts": "stay long vol; no fades, no premium sales"},
        ]

    return [
        {"id": "A", "name": "Grind up to the wall",
         "path": f"spot {s} → {cr0:.0f}" if (spot and cr0) else "→ CR0/GW0",
         "means": "tags CR0/GW0 resistance",
         "acts": "CR0 touch-fade (short call spread); fly @ GW0 if it pins there"},
        {"id": "B", "name": "Fade to support",
         "path": f"spot {s} → {hvl:.0f} → {ps0:.0f}" if (spot and hvl and ps0) else "→ HVL → PS0",
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
        g, basis = _fade_grade(positive, below)
        T.append({
            "id": "cr0_touch_fade", "setup": "cr0_fade", "path": "A",
            "name": "CR0 first-touch fade (short call spread)",
            "arm": {"regime": "any", "spot_side": {"level": short, "side": "below"}},
            "fire": {"type": "touch", "level": short, "dir": "from_below", "first_only": True},
            "window": ["08:45", "14:30"],
            "structure": {"kind": "vertical", "right": "C", "short": short, "long": short + 25, "width": 25},
            "projected_grade": g, "grade_basis": basis,
        })

    # 5. PS0 first-touch-from-above fade
    if L["ps0"]:
        short = rnd(L["ps0"])
        above = spot is not None and spot > L["ps0"]
        g, basis = _fade_grade(positive, above)
        T.append({
            "id": "ps0_touch_fade", "setup": "ps0_fade", "path": "B",
            "name": "PS0 first-touch fade (short put spread)",
            "arm": {"regime": "any", "spot_side": {"level": short, "side": "above"}},
            "fire": {"type": "touch", "level": short, "dir": "from_above", "first_only": True},
            "window": ["08:45", "14:30"],
            "structure": {"kind": "vertical", "right": "P", "short": short, "long": short - 25, "width": 25},
            "projected_grade": g, "grade_basis": basis,
        })

    # 6. Long ATM straddle — arms only if price BREAKS BELOW HVL intraday
    #    (regime flips to negative gamma) or on an event day. On a pin day it
    #    stays dormant, waiting for path D. Center re-struck at fire time.
    if L["hvl"]:
        hvl_r = rnd(L["hvl"])
        # A7 — GAP-AWARE ARMING. A cross-trigger whose cross has ALREADY happened
        # before the open is mechanically unfireable: on 2026-07-17 spot opened at
        # 7478.6 with HVL 7540, so "break below 7540" was consumed pre-open and the
        # straddle — scenario D's designated structure on a day that WAS scenario D
        # — could never fire. The desk took 0 trades on the one day the thesis was
        # right. A satisfied cross becomes a STATE condition, never a dead trigger.
        gapped = spot is not None and spot < hvl_r
        if gapped:
            T.append({
                "id": "straddle_0dte", "setup": "straddle_0dte", "path": "D",
                "name": "Long ATM Straddle (0DTE) — gap-armed",
                "arm": {"regime": "negative_gamma"},
                "fire": {"type": "time_at", "not_before": "09:00"},
                "window": ["09:00", "13:00"],
                "structure": {"kind": "straddle", "center": "atm"},
                "gap_armed": True,
                "projected_grade": "B",
                "grade_basis": (f"GAP-ARMED: spot {spot:.0f} opened already BELOW HVL {hvl_r:.0f} — "
                                f"the break was consumed pre-open, so the cross-trigger is dead. "
                                f"Converted to a state condition: fire at 09:00 while regime is "
                                f"still negative gamma (the condition the straddle wanted is "
                                f"already TRUE)."),
            })
        else:
            T.append({
                "id": "straddle_0dte", "setup": "straddle_0dte", "path": "D",
                "name": "Long ATM Straddle (0DTE)",
                "arm": {"regime": "any"},
                "fire": {"type": "regime_break", "level": hvl_r, "dir": "below"},
                "window": ["08:45", "13:00"],
                "structure": {"kind": "straddle", "center": "atm"},
                "gap_armed": False,
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
    ap.add_argument("--force", action="store_true",
                    help="overwrite even if the day's plan already has fired triggers")
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
    paths = scenarios(spot, L, reg) if spot else []

    # A5 — disarm anything the level stack invalidates, and A1 — disarm anything
    # already below the grade bar at plan time. Both record WHY on the trigger, so
    # the day's JSON explains its own stand-downs.
    warns = level_warnings(spot, L)
    disarm = {tid: text for _, text, ids in warns for tid in ids}
    plan_triggers = []
    for t in triggers:
        t = dict(t, status="armed", fired=False, trade_id=None)
        if t["id"] in disarm:
            t["status"], t["disarmed_reason"] = "disarmed", disarm[t["id"]]
        elif not grade_ok(t["projected_grade"]):
            t["status"] = "disarmed"
            t["disarmed_reason"] = (f"projected grade {t['projected_grade']} is below the "
                                    f"{MIN_GRADE} bar — {t['grade_basis']}")
        plan_triggers.append(t)

    plan = {
        "date": date,
        "generated_at": now_ct().strftime("%Y-%m-%d %H:%M:%S CT"),
        "spot_preopen": spot, "spot_source": spot_src,
        "regime": reg, "regime_detail": reg_detail,
        "levels": L, "d1_min": lv.get("d1_min"), "d1_max": lv.get("d1_max"),
        "warnings": [{"code": c, "text": txt} for c, txt, _ in warns],
        "execution": {"mode": "auto", "size": 1, "concurrency_cap": None,
                      "min_grade": MIN_GRADE, "min_credit_abs": MIN_CREDIT_ABS,
                      "exits": EXITS,
                      "policy": f"all grades taken (ladder unvalidated); credit >= {MIN_CREDIT_ABS:.2f} "
                                f"and short >= {MIN_OTM_PTS}pt OTM per playbook §3; dedupe by short "
                                f"strike (exact match); THESIS-based exits; all gates PRE-ORDER"},
        "scenarios": paths,
        "triggers": plan_triggers,
    }
    out = SIM / f"gameplan_{date}.json"
    if out.exists() and not args.force:
        try:
            prev = json.loads(out.read_text(encoding="utf-8"))
            if any(t.get("fired") for t in prev.get("triggers", [])):
                raise SystemExit(
                    f"REFUSING to overwrite {out.name}: it already has fired triggers "
                    f"(would wipe the day's live record). Use --force only if you mean it.")
        except (ValueError, OSError):
            pass
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
    if plan["warnings"]:
        print("\n  ⚠ LEVEL-STACK WARNINGS:")
        for w in plan["warnings"]:
            print(f"    [{w['code']}] {w['text']}")
    if paths:
        print("\n  PRICE PATHS (what may play out):")
        for p in paths:
            print(f"    {p['id']}. {p['name']:22} {p['path']:22} → {p['acts']}")
    print(f"\n  {'GRADE':7} {'STATUS':9} {'PATH':5} {'FIRE WHEN':22} SETUP")
    print("  " + "-" * 92)
    for t in plan["triggers"]:
        print(f"  {str(t['projected_grade']):7} {t['status']:9} {t.get('path','—'):5} "
              f"{fire_str(t['fire']):22} {t['name']}")
        print(f"  {'':7} {'':9} {'':5} {'':22} → {t.get('disarmed_reason') or t['grade_basis']}")
    n_armed = sum(1 for t in plan["triggers"] if t["status"] == "armed")
    n_off = len(plan["triggers"]) - n_armed
    print(f"\nwrote {out}  ({n_armed} armed, {n_off} disarmed)")
    # daily reasoning charts (one per path + per trade) -> gameplan_charts/YYYYMMDD/,
    # browsable by day in Mission Control /playbook. Detached: a render must never
    # fail or delay the gameplan itself.
    try:
        import subprocess
        subprocess.Popen([sys.executable, str(ROOT / "scripts" / "gameplan_charts.py"),
                          "--date", date, "--no-open"],
                         cwd=str(ROOT), creationflags=0x08000008,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"  (chart render not started: {type(e).__name__})")
    return out


if __name__ == "__main__":
    main()
