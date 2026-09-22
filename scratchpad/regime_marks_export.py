"""Regime phase machine v4 — TICK-DRIVEN (OnPriceChange emulation).

Usage:  python scratchpad/regime_phase_machine.py [YYYY-MM-DD]

Standalone: does NOT import or modify scripts/brooks_regime_layer.py. This emulates the
target live indicator: the machine's clock is EVERY PRICE CHANGE, exactly as an NT8
indicator running Calculate.OnPriceChange would see it. Bars exist only as bookkeeping
(pivots live on bars, labels reference bar numbers); all state transitions fire on ticks.

EVENTS (per Samir): each bar has at most two events — the FIRST tick above the prior bar's
high and the FIRST tick below the prior bar's low, registered in the order the ticks present
them. Each event applies the regime logic against live state, so an outside bar is simply
two consecutive steps that share a bar. Equal bars are perfect inside bars (no tick can
break an equal extreme — strict comparisons handle this for free).

STATES
  NEUTRAL : the day opens here and every termination returns here. Swing pivots keep
            forming (only a termination bar itself is excluded — its leg dies, though its
            extremes stay in the tag-comparison chain). The race: a tick above the latest
            swing-high pivot with an hl in the phase -> BULL; a tick below the latest
            swing-low pivot with an lh in the phase -> BEAR ("hl gets taken out in a
            neutral phase"). Day-first single-letter pivots count as compatible structure.
            At the start: broken pivot -> continuation major (HH/LL), the enabling hl/lh ->
            HL/LH, the phase's opposite extreme pivot -> its uppercased tag. The running
            trend extreme is born at the breaking tick.
  TREND   : a swing pivot that IS the trend's running extreme -> MAJOR continuation at its
            turn (every new running low of a bear is an LL — b17 on 04-12). Counter-trend
            pivots enter the ONE-candidate contest (deeper low / higher high replaces,
            replaced stays minor); the candidate promotes to major HL/LH when a tick
            exceeds the running extreme that stood when it was set, and becomes the
            STANDING level. A tick through the standing level TERMINATES the trend.
"""
import sys
from datetime import date
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
OUTDIR = str(Path(ROOT) / "docs" / "living")
sys.path.insert(0, ROOT)
import massive

DAY = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"

B = pd.read_parquet(ROOT + "/data/bars/_continuous.parquet")
B["Date"] = B["DateTime"].dt.date.astype(str)
g = B[B["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
n = len(g)
tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
tP = tk["Price"].values

# ---- bar classification (display strip + gold OB dots only; the machine reads ticks) ----
kind = {}; obdir = {}
for i in range(1, n):
    bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
    eqH = H[i] == H[i-1]; eqL = L[i] == L[i-1]
    if bt and bb:
        s_ = tP[tbar == i]
        up = np.nonzero(s_ > H[i-1])[0]; dn = np.nonzero(s_ < L[i-1])[0]
        fb = "D" if (dn[0] if len(dn) else np.inf) < (up[0] if len(up) else np.inf) else "U"
        obdir[i] = fb; kind[i] = "OB " + fb + "-first"
    elif bt and eqL: obdir[i] = "U"; kind[i] = "OB (high)"
    elif bb and eqH: obdir[i] = "D"; kind[i] = "OB (low)"
    elif bt:          kind[i] = "up"
    elif bb:          kind[i] = "down"
    elif eqH and eqL: kind[i] = "EQUAL = IB"
    else:             kind[i] = "inside"

# ============================== state ==============================
piv = []           # bar, side, tag, disp, conf, intrabar, major, majlab
log = []
trend_starts = []  # (bar, "bull"|"bear", broken_pivot_bar)
terms = []         # (standing_bar, standing_px, break_bar, "bull"|"bear")
race_lines = []    # (pivot_bar, px, break_bar, "bull"|"bear")
neutral_spans = [] # (start_bar, end_bar)
transitions = []   # (bar, "start"|"term", side) in TRUE firing order - same-bar events can
                    # go either way: term-then-start on an immediate flip (terminate() calls
                    # start_trend()), or start-then-term when a wide/OB bar ticks through a
                    # fresh trigger and then straight through its own brand-new standing
                    # level (04-10 b78: starts bull, dies bull, same bar). A bar-number sort
                    # can't tell these apart; only insertion order can.

prevH = prevL = 0
first_pivot_done = False
mode = "NEUTRAL"
standing = None              # (bar, px): major HL floor (bull) / major LH ceiling (bear)
run_b = None; run_px = None  # running trend extreme — born at trend start, tick-accurate
cand = None                  # {p, ref_px}: pending pullback candidate
neu_start = 0
hi_p = None; lo_p = None     # EXTREME pivots since reset (promoted when the race resolves)
lsh = None; lsl = None       # LATEST pivots since reset — the race break levels
has_hl = False; has_lh = False
struct_hl = None; struct_lh = None   # the hl / lh pivot enabling a start (the partner)


def add_pivot(bar, side, emit):
    global prevH, prevL, first_pivot_done, hi_p, lo_p, lsh, lsl
    global has_hl, has_lh, cand, struct_hl, struct_lh
    if side == "H":
        t = "hh" if H[bar] > H[prevH] else ("lh" if H[bar] < H[prevH] else "dh"); prevH = bar
    else:
        t = "hl" if L[bar] > L[prevL] else ("ll" if L[bar] < L[prevL] else "dl"); prevL = bar
    disp = side if not first_pivot_done else t     # day's first pivot: single letter
    first_pivot_done = True
    p = dict(bar=bar, side=side, tag=t, disp=disp, conf=emit, intrabar=(emit == bar),
             major=None, majlab=None)
    piv.append(p)
    log.append((emit, "pivot %s on b%d (%s)%s" % (side, bar + 1, disp,
                "  [intrabar]" if emit == bar else "")))
    # Latest-pivot / structure trackers run in EVERY mode, not just NEUTRAL - reset at every
    # mode transition (start_trend / terminate), accumulated continuously in between. In
    # NEUTRAL they drive the entry race; in TREND they capture the counter-trend minor
    # structure forming INSIDE the trend (e.g. a bear's own minor hh + hl), which the next
    # termination checks for an IMMEDIATE flip straight to the opposite trend (08-20: b53
    # minor hh + b55 minor hl -> b56 breaks the bear's LH and fires bull on the same tick,
    # no neutral pause) instead of always parking in neutral to wait for fresh pivots.
    if side == "H":
        lsh = p
        if hi_p is None or H[bar] > H[hi_p["bar"]]: hi_p = p
        if t == "lh" or len(disp) == 1: has_lh = True; struct_lh = p
    else:
        lsl = p
        if lo_p is None or L[bar] < L[lo_p["bar"]]: lo_p = p
        if t == "hl" or len(disp) == 1: has_hl = True; struct_hl = p
    if mode == "BULL" and side == "L":
        # ONE candidate: a DEEPER low replaces it (old stays minor); otherwise minor forever
        if cand is None or L[bar] < L[cand["p"]["bar"]]:
            cand = dict(p=p, ref_px=run_px)
    elif mode == "BEAR" and side == "H":
        if cand is None or H[bar] > H[cand["p"]["bar"]]:
            cand = dict(p=p, ref_px=run_px)
    # TREND-EXTREME CONTINUATION (b17 on 04-12): a swing pivot that IS the trend's running
    # extreme is a major continuation pivot at its turn. Equal extremes are not new (b19 dl).
    # identity test, not price: an EQUAL low is a dl, not a new extreme (b19 on 04-12) —
    # strict < in the tick loop keeps run_b on the FIRST bar that made the level
    if mode == "BULL" and side == "H" and bar == run_b:
        p["major"] = emit; p["majlab"] = "HH"
    elif mode == "BEAR" and side == "L" and bar == run_b:
        p["major"] = emit; p["majlab"] = "LL"
    return p


def start_trend(up, b, px):
    global mode, standing, run_b, run_px, cand
    global hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh
    side = "bull" if up else "bear"
    broken = lsh if up else lsl
    partner = struct_hl if up else struct_lh
    opp = lo_p if up else hi_p
    broken["major"] = b
    broken["majlab"] = "HH" if up else "LL"
    if partner is not None and partner["major"] is None:
        partner["major"] = b
        partner["majlab"] = (partner["disp"] if len(partner["disp"]) == 1
                             else ("HL" if up else "LH"))
    if opp is not None and opp is not partner and opp["major"] is None:
        opp["major"] = b
        opp["majlab"] = (opp["disp"] if len(opp["disp"]) == 1 else opp["tag"].upper())
    race_lines.append((broken["bar"], H[broken["bar"]] if up else L[broken["bar"]], b, side))
    trend_starts.append((b, side, broken["bar"]))
    transitions.append((b, "start", side))
    neutral_spans.append((neu_start, b))
    standing = None
    if partner is not None:
        standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
    run_b, run_px = b, px            # running extreme born at the breaking tick
    mode = "BULL" if up else "BEAR"; cand = None
    hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False   # fresh scope for the new trend
    struct_hl = struct_lh = None
    log.append((b, "*** %s TREND STARTS - b%d breaks the b%d pivot"
                % (side.upper(), b + 1, broken["bar"] + 1)))


def terminate(b, px):
    global mode, standing, run_b, run_px, cand, d, leg_px, leg_bar, neu_start
    global hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh, prevH, prevL
    was_bull = (mode == "BULL")
    terms.append((standing[0], standing[1], b, mode.lower()))
    transitions.append((b, "term", mode.lower()))
    # IMMEDIATE FLIP: the counter-trend minor structure already formed INSIDE the dying
    # trend (lsh/has_hl or lsl/has_lh, tracked continuously - see add_pivot) may already
    # satisfy the OPPOSITE race at this same tick. If so, skip neutral and start the new
    # trend right away (08-20 b56: bear's own minor hh@53 + hl@55 -> bull fires on the
    # break, not after a fresh seed forms).
    # the enabling partner must have formed AFTER the candidate (hh THEN hl, b53 then b55 -
    # not some stale lh from back near the trend's own start) or this fires on ANY leftover
    # structure, which spuriously flipped the validated b71/b74 terminations in testing
    flip_up = (not was_bull) and lsh is not None and px > H[lsh["bar"]] and has_hl \
              and struct_hl is not None and struct_hl["bar"] > lsh["bar"]
    flip_dn = was_bull and lsl is not None and px < L[lsl["bar"]] and has_lh \
              and struct_lh is not None and struct_lh["bar"] > lsl["bar"]
    log.append((b, "*** %s TREND TERMINATED - b%d breaks the b%d %s%s"
                % (mode, b + 1, standing[0] + 1, "HL" if was_bull else "LH",
                   "" if (flip_up or flip_dn) else " -> NEUTRAL")))
    mode = "NEUTRAL"; neu_start = b
    cand = None; standing = None; run_b = run_px = None
    # prevH/prevL are NOT touched here at all - termination is purely a REGIME-state event.
    # An earlier version forced the termination bar onto the comparison chain (on the side
    # that broke), which fixed 04-10's b25 (correctly reading lh vs b14, not the b21
    # termination bar) - but it broke the moment the termination bar ITSELF later turns out
    # to be a genuine pivot (2023-04-12 b12: comparing L[12] to a prevL that had JUST been
    # set to b12 is a self-reference, producing dl instead of the real ll vs b10). Leaving
    # prevH/prevL untouched resolves both: whatever pivot forms next - on the termination
    # bar itself or later - naturally compares against the real last prior pivot, because
    # the tag chain was never interrupted in the first place.
    # The LEG ITSELF does NOT reset at termination - it keeps running exactly as it would
    # have anyway. Killing it here was an unvalidated guess that broke real structure
    # (2023-04-12: the down-leg from b11 was running through b12 when the bull terminated
    # AT b12; resetting the leg discarded that leg entirely, so b13's up-tick opened a
    # brand-new leg instead of closing the real one, and b12 never got to be the pivot it
    # should be - "b13 triggers above b12, which makes b12 a minor ll"). Only the REGIME
    # state (mode/standing/cand/race trackers) belongs to the trend and resets with it.
    if flip_up or flip_dn:
        log.append((b, "    counter-trend structure already satisfies the race -> immediate flip"))
        start_trend(flip_up, b, px)  # uses the still-populated lsh/lsl/struct_*/hi_p/lo_p
    else:
        hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
        struct_hl = struct_lh = None


# ============================ TICK LOOP — OnPriceChange emulation ============================
d = None                 # leg direction
leg_px = None; leg_bar = None
cur_bar = -1
up_done = dn_done = True

for _t in range(len(tP)):
    b = int(tbar[_t])
    if b < 1 or b >= n:
        continue
    px = tP[_t]
    if b != cur_bar:
        cur_bar = b
        up_done = dn_done = False    # both breakout events armed against the prior bar
    # ---- leg extreme carries tick by tick ----
    if d == 1 and (leg_px is None or px > leg_px): leg_px, leg_bar = px, b
    if d == -1 and (leg_px is None or px < leg_px): leg_px, leg_bar = px, b
    # ---- the two per-bar breakout events, in tick order ----
    if not up_done and px > H[b - 1]:
        up_done = True
        if d == -1:
            add_pivot(leg_bar, "L", b)
            d = 1; leg_px, leg_bar = px, b
        elif d is None:
            d = 1; leg_px, leg_bar = px, b
    if not dn_done and px < L[b - 1]:
        dn_done = True
        if d == 1:
            add_pivot(leg_bar, "H", b)
            d = -1; leg_px, leg_bar = px, b
        elif d is None:
            d = -1; leg_px, leg_bar = px, b
    # ---- regime checks on every price change ----
    if mode == "NEUTRAL":
        if lsh is not None and px > H[lsh["bar"]] and has_hl:
            start_trend(True, b, px)
        elif lsl is not None and px < L[lsl["bar"]] and has_lh:
            start_trend(False, b, px)
    else:
        if cand is not None and cand["ref_px"] is not None:
            hit = px > cand["ref_px"] if mode == "BULL" else px < cand["ref_px"]
            if hit:
                q = cand["p"]; q["major"] = b
                q["majlab"] = "HL" if mode == "BULL" else "LH"
                standing = (q["bar"], L[q["bar"]] if mode == "BULL" else H[q["bar"]])
                log.append((b, "major %s on b%d -> standing level" % (q["majlab"], q["bar"] + 1)))
                cand = None
        if mode == "BULL" and px > run_px: run_b, run_px = b, px
        if mode == "BEAR" and px < run_px: run_b, run_px = b, px
        if standing is not None:
            if (mode == "BULL" and px < standing[1]) or (mode == "BEAR" and px > standing[1]):
                terminate(b, px)

if mode == "NEUTRAL":
    neutral_spans.append((neu_start, n - 1))

# ---- open pre-phase carry trail (display only, validated on 02-24) ----
first_piv_bar = piv[0]["bar"] if piv else n - 1
first_piv_side = piv[0]["side"] if piv else None
seed_marks = [(0, "H"), (0, "L")]
for i in range(1, first_piv_bar + 1):
    bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
    if bt and bb: seed_marks += [(i, "H"), (i, "L")]
    elif bt: seed_marks.append((i, "H"))
    elif bb: seed_marks.append((i, "L"))
# the first pivot's own label replaces its trail mark
seed_marks = [(b_, s_) for (b_, s_) in seed_marks
              if not (b_ == first_piv_bar and s_ == first_piv_side)]

# ===================== MARKS CSV EXPORT (added) =====================
import csv as _csv
from pathlib import Path as _P
def _pr(bar, is_h): return round(float(H[bar] if is_h else L[bar]), 2)
COLS = ["date","bar","event","side","minor_tag","disp","is_major","major_lab",
        "promoted_at","confirm_bar","confirm_i","is_ob","ob_kind","ob_dir","ref_bar","price"]
def _row(**k):
    r = {c: "" for c in COLS}; r["date"] = DAY; r.update(k); return r
rows = []
for (b_, s_) in seed_marks:
    rows.append(_row(bar=b_+1, event="seed", side=s_, price=_pr(b_, s_=="H")))
for p in piv:
    k_ = kind.get(p["bar"], ""); isob = k_.startswith("OB")
    rows.append(_row(bar=p["bar"]+1, event="pivot", side=p["side"], minor_tag=p["tag"],
        disp=p["disp"], is_major=int(p["major"] is not None), major_lab=p["majlab"] or "",
        promoted_at=(p["major"]+1 if p["major"] is not None else ""),
        confirm_bar=p["conf"]+1, confirm_i=("i" if p["intrabar"] else ""),
        is_ob=int(isob), ob_kind=k_, ob_dir=obdir.get(p["bar"], ""),
        price=_pr(p["bar"], p["side"]=="H")))
for (sb, sd, brk) in trend_starts:
    rows.append(_row(bar=sb+1, event="start", side=sd, ref_bar=brk+1, price=_pr(brk, sd=="bull")))
for (pb, px_, bb_, sd) in terms:
    rows.append(_row(bar=bb_+1, event="term", side=sd, ref_bar=pb+1, price=round(float(px_),2)))
_ord = {"seed":0,"pivot":1,"start":2,"term":3}
rows.sort(key=lambda r: (r["bar"], _ord.get(r["event"],9), r["side"]))
outp = _P("scratchpad") / ("marks_py_" + DAY + ".csv")
with open(outp, "w", newline="", encoding="utf-8") as f:
    w = _csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
print("wrote", outp, "rows=", len(rows), "pivots=", len(piv))
