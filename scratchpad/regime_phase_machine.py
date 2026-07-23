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
    if mode == "NEUTRAL":
        if side == "H":
            lsh = p
            if hi_p is None or H[bar] > H[hi_p["bar"]]: hi_p = p
            if t == "lh" or len(disp) == 1: has_lh = True; struct_lh = p
        else:
            lsl = p
            if lo_p is None or L[bar] < L[lo_p["bar"]]: lo_p = p
            if t == "hl" or len(disp) == 1: has_hl = True; struct_hl = p
    elif mode == "BULL" and side == "L":
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
    neutral_spans.append((neu_start, b))
    standing = None
    if partner is not None:
        standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
    run_b, run_px = b, px            # running extreme born at the breaking tick
    mode = "BULL" if up else "BEAR"; cand = None
    log.append((b, "*** %s TREND STARTS - b%d breaks the b%d pivot"
                % (side.upper(), b + 1, broken["bar"] + 1)))


def terminate(b):
    global mode, standing, run_b, run_px, cand, d, leg_px, leg_bar, neu_start
    global hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh, prevH, prevL
    terms.append((standing[0], standing[1], b, mode.lower()))
    log.append((b, "*** %s TREND TERMINATED - b%d breaks the b%d %s -> NEUTRAL"
                % (mode, b + 1, standing[0] + 1, "HL" if mode == "BULL" else "LH")))
    mode = "NEUTRAL"; neu_start = b
    cand = None; standing = None; run_b = run_px = None
    hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
    struct_hl = struct_lh = None
    prevH = b; prevL = b             # termination bar joins the comparison chain, never a pivot
    d = None; leg_px = leg_bar = None    # the open leg dies with the trend


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
                terminate(b)

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

# ============================== text output ==============================
print("=" * 96)
print("EVENT LOG  %s  (tick-driven)" % DAY)
print("=" * 96)
for (bar, msg) in log:
    print("  b%-3d  %s" % (bar + 1, msg))

print()
print("=" * 96)
print("PIVOTS  (bar | side | display tag | known-at | major label @ promoted-at)")
print("=" * 96)
for p in piv:
    cs = "b%d%s" % (p["conf"] + 1, "i" if p["intrabar"] else "")
    ms = "-" if p["major"] is None else "%s @b%d" % (p["majlab"], p["major"] + 1)
    print("  b%-3d %s  %-3s  known@%-6s  %s" % (p["bar"] + 1, p["side"], p["disp"], cs, ms))

print()
for (sb, sd, brk) in trend_starts:
    print("  %s TREND STARTS  b%d  (breaks the b%d pivot)" % (sd.upper(), sb + 1, brk + 1))
for (pb, px_, bb_, sd) in terms:
    print("  %s TREND TERMINATED b%d (breaks the b%d %s) -> NEUTRAL"
          % (sd.upper(), bb_ + 1, pb + 1, "HL" if sd == "bull" else "LH"))

# ============================== chart ==============================
vhi = H.max(); vlo = L.min(); rng = vhi - vlo; off = rng * 0.021
fig, ax = plt.subplots(figsize=(36, 12), dpi=200)

segs = []
bounds = sorted([(s_, "start", sd) for (s_, sd, _) in trend_starts] +
                [(b_, "term", None) for (_, _, b_, _) in terms])
cur = "neutral"; x0 = 0
for (xb, ktp, sd) in bounds:
    segs.append((x0, xb, cur)); x0 = xb
    cur = sd if ktp == "start" else "neutral"
segs.append((x0, n - 1, cur))
SHADE = {"neutral": ("#9aa0a6", 0.10), "bull": ("#1f7a3d", 0.06), "bear": ("#b23a2e", 0.06)}
for (a, b_, sdv) in segs:
    col, al = SHADE[sdv]
    ax.axvspan(a + 0.5 if a else -0.9, b_ + 0.5, color=col, alpha=al, zorder=0)
    if b_ - a >= 3:
        ax.text((a + b_) / 2.0, vhi + rng * 0.075, sdv.upper(), ha="center", va="bottom",
                fontsize=12, fontweight="bold",
                color={"neutral": "#0e7c86", "bull": "#1f7a3d", "bear": "#b23a2e"}[sdv])

for k in range(n):
    up_ = C[k] >= O[k]
    col = "#2e9e8f" if up_ else "#e0574a"
    ax.plot([k, k], [L[k], H[k]], color=col, lw=1.7, zorder=2)
    ax.add_patch(plt.Rectangle((k - 0.30, min(O[k], C[k])), 0.60,
                               max(abs(C[k] - O[k]), rng * 0.0010),
                               facecolor=col, edgecolor="black", lw=0.45, zorder=3))
    if k in obdir and kind[k].startswith("OB"):
        yy = H[k] + off * 0.40 if obdir[k] == "U" else L[k] - off * 0.40
        ax.plot(k, yy, "o", ms=8, color="gold", mec="black", mew=0.7, zorder=6)

for (bar, sdv) in seed_marks:
    y = H[bar] + off * 0.85 if sdv == "H" else L[bar] - off * 0.85
    ax.text(bar, y, sdv, ha="center", va="bottom" if sdv == "H" else "top",
            fontsize=13, color="#8a6a12", fontweight="bold", alpha=0.9)

last_side = {}
for p in piv:
    bar, side, t = p["bar"], p["side"], p["disp"]
    mcol = "#8a6a12" if len(t) == 1 else ("#1f7a3d" if t in ("hh", "hl") else "#b23a2e")
    seedbump = off * 1.4 if any(b_ == bar for b_, _ in seed_marks) else 0.0
    sgn = 1 if side == "H" else -1
    base = (H[bar] + off * 0.85 + seedbump) if side == "H" else (L[bar] - off * 0.85 - seedbump)
    prev = last_side.get(side)
    if prev is not None and bar - prev <= 1: base += sgn * off * 1.9
    last_side[side] = bar
    va = "bottom" if side == "H" else "top"
    if len(t) == 1:
        # the day's first pivot: one gold circled letter + its number — no extra layers
        ax.text(bar, base + sgn * off * 1.2, t, ha="center", va="center", fontsize=14.5,
                color="#8a6a12", fontweight="bold",
                bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec="#8a6a12", lw=1.9))
        lab = "%d%s" % (p["conf"] + 1, "i" if p["intrabar"] else "")
        if p["major"] is not None and p["major"] != p["conf"]:
            lab += "→%d" % (p["major"] + 1)
        ax.text(bar, base + sgn * off * 3.0, lab, ha="center", va=va, fontsize=12.5,
                color="#b8860b" if p["intrabar"] else "#444444", fontweight="bold")
        continue
    ax.text(bar, base, t, ha="center", va=va, fontsize=12.5, color=mcol, fontweight="bold")
    if p["major"] is not None:
        ml = p["majlab"]
        mc2 = "#8a6a12" if len(ml) == 1 else ("#1f7a3d" if ml in ("HH", "HL") else "#b23a2e")
        ax.text(bar, base + sgn * off * 2.3, ml, ha="center", va="center", fontsize=14.5,
                color=mc2, fontweight="bold",
                bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec=mc2, lw=1.9))
        lab = "%d%s" % (p["conf"] + 1, "i" if p["intrabar"] else "")
        if p["major"] != p["conf"]: lab += "→%d" % (p["major"] + 1)
        ax.text(bar, base + sgn * off * 4.1, lab, ha="center", va=va, fontsize=12.5,
                color="#b8860b" if p["intrabar"] else "#444444", fontweight="bold")

for (pb, px_, bb_, sdv) in race_lines:
    col = "#1f7a3d" if sdv == "bull" else "#b23a2e"
    ax.plot([pb, bb_], [px_, px_], ls=(0, (4, 3)), lw=2.2, color=col, zorder=5)
    ax.plot(bb_, px_, "x", ms=12, mew=2.6, color=col, zorder=6)
for (pb, px_, bb_, sdv) in terms:
    ax.plot([pb, bb_], [px_, px_], ls=(0, (4, 3)), lw=2.2, color="#33454d", zorder=5)
    ax.plot(bb_, px_, "x", ms=12, mew=2.6, color="#33454d", zorder=6)

_evt = ([(bb_, "term", sdv) for (_, _, bb_, sdv) in terms] +
        [(sb, "start", sdv) for (sb, sdv, _) in trend_starts])
_evt.sort()
for _k, (xb, ekind, sdv) in enumerate(_evt):
    if ekind == "term":
        col = "#0e7c86"; txt = "NEUTRAL  b%d" % (xb + 1)
    else:
        col = "#1f7a3d" if sdv == "bull" else "#b23a2e"
        txt = "%s TREND  b%d" % (sdv.upper(), xb + 1)
    xv = xb + 0.5
    ax.axvline(xv, ls=(0, (3, 3)), lw=2.2, color=col, zorder=5)
    ytxt = vlo + rng * (0.015 if _k % 2 == 0 else 0.115)
    ax.text(xv - 0.14, ytxt, txt, ha="right", va="bottom", fontsize=10.5,
            color=col, fontweight="bold", rotation=90)

ybar = vlo - rng * 0.075
for k in range(n):
    ax.text(k, ybar, str(k + 1), ha="center", va="top", fontsize=11.5, color="#333333")
    kk = kind.get(k, "")
    kc = "#b8860b" if kk.startswith("OB") else ("#7a5aa0" if ("IB" in kk or "inside" in kk) else "#9aa4a8")
    ax.text(k, ybar - rng * 0.020, kk.replace(" ", "\n", 1), ha="center", va="top",
            fontsize=8.5, color=kc, linespacing=1.25,
            fontweight="bold" if (kk.startswith("OB") or "EQUAL" in kk) else "normal")

ax.set_xlim(-1.0, n)
ax.set_ylim(vlo - rng * 0.19, vhi + rng * 0.13)
ax.set_title("%s  ·  TICK-DRIVEN phase machine (OnPriceChange emulation)\n"
             "every price change advances the state · per-bar breakout events in tick order · "
             "hl/lh takeout = trend start · standing major HL/LH broken = termination"
             % DAY, fontsize=14.5, fontweight="bold", pad=16, linespacing=1.7)
ax.grid(axis="y", color="#eceeed", lw=0.8); ax.set_axisbelow(True)
for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
ax.tick_params(axis="x", bottom=False, labelbottom=False)
fig.tight_layout()
out = OUTDIR + "/phase_machine_" + DAY.replace("-", "") + ".png"
fig.savefig(out, facecolor="white")
print("\nsaved", out)
