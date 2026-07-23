"""Regime phase machine — trend / termination / seed / re-confirmation, drawn per session.

Usage:  python scratchpad/regime_phase_machine.py [YYYY-MM-DD]

Standalone: does NOT import or modify scripts/brooks_regime_layer.py. This is the working
model of the rules validated bar-by-bar with Samir on 2022-02-24 (2026-07-22), pending a port
into the engine once they hold up on other days.

BAR CLASSIFICATION
  An outside bar's range is always BIGGER than the prior bar's: one side may be equal, never
  both. So H==prior H AND L==prior L is a perfect INSIDE bar (no events), while higher-high-
  with-equal-low and lower-low-with-equal-high ARE outside bars (one-sided, so the extending
  side is the break by construction and no tick order is needed).

PHASES
  SEED  : the open-of-day rule, reused. The seeding bar marks BOTH an H and an L; each later
          bar carries the label on the side it breaks (OB carries both, IB/equal carries
          neither) until one side alone advances -> direction established. The first
          counter-move then ends the seed and makes the leading extreme the first pivot.
          The day OPENS in this phase, so the open is not a special case - it is seed #1.
  TREND : the event machine. A strict OB fires TWO events in tick order, so it can supply its
          own turn -> INTRABAR confirmation, displayed with an "i" (b23 -> 23i, b63 -> 63i).
          HH/LL are known at the turn; HL/LH at the new extreme.
          A bar trading below the standing MAJOR HL terminates the bull trend -> back to SEED.

MAJOR vs MINOR (this is the part that is easy to get wrong - see the handoff)
  ONE candidate per side at a time. Every pivot on that side enters the contest whatever its
  two-bar tag; a DEEPER low replaces the pending low and DEMOTES it to minor. The winner is
  promoted to major only when price exceeds the RUNNING DAY EXTREME that stood when it was
  set - NOT merely the prior swing pivot, which is a far lower bar and promotes all the chop.
  A promoted low is a major HL regardless of its tag, so a mechanically-tagged `ll` can be the
  major HL (b35, b56 on 2/24).
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
LO, HI = 1, n            # whole session
tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
tP = tk["Price"].values


def first_break(i):
    s = tP[tbar == i]
    up = np.nonzero(s > H[i-1])[0]; dn = np.nonzero(s < L[i-1])[0]
    tu = up[0] if len(up) else np.inf
    td = dn[0] if len(dn) else np.inf
    return "D" if td < tu else "U"


kind = {}; evs = {}; obdir = {}
for i in range(1, n):
    bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
    eqH = H[i] == H[i-1]; eqL = L[i] == L[i-1]
    if bt and bb:
        fb = first_break(i); obdir[i] = fb
        kind[i] = "OB " + fb + "-first"; evs[i] = ["D", "U"] if fb == "D" else ["U", "D"]
    elif bt and eqL: obdir[i] = "U"; kind[i] = "OB (high)"; evs[i] = ["U"]
    elif bb and eqH: obdir[i] = "D"; kind[i] = "OB (low)";  evs[i] = ["D"]
    elif bt:          kind[i] = "up";            evs[i] = ["U"]
    elif bb:          kind[i] = "down";          evs[i] = ["D"]
    elif eqH and eqL: kind[i] = "EQUAL = IB";    evs[i] = []
    else:             kind[i] = "inside";        evs[i] = []

# ---------------------------------------------------------------- phase machine
piv = []          # dicts: bar, side, tag, pivot_bar(confirm), intrabar, major_bar, in_seed
seed_marks = []   # (bar, "H"/"L")
seed_spans = []   # (start_bar, end_bar)
terms = []        # (hl_bar, hl_px, break_bar)
resumes = []      # (hh_bar, cont_bar)
log = []

prevH = prevL = 0
def tag_of(bar, side):
    global prevH, prevL
    if side == "H":
        t = "hh" if H[bar] > H[prevH] else ("lh" if H[bar] < H[prevH] else "dh"); prevH = bar
    else:
        t = "hl" if L[bar] > L[prevL] else ("ll" if L[bar] < L[prevL] else "dl"); prevL = bar
    return t

run_max_H = H[0]; run_max_H_bar = 0      # running DAY extremes - the promotion reference
run_min_L = L[0]; run_min_L_bar = 0


def add_pivot(bar, side, emit, in_seed=False):
    global awaiting
    t = tag_of(bar, side)
    p = dict(bar=bar, side=side, tag=t, conf=emit, intrabar=(emit == bar),
             major=None, majlab=None, in_seed=in_seed)
    piv.append(p)
    log.append((emit, "pivot %s on b%d (%s)%s" % (side, bar + 1, t,
                "  [intrabar]" if emit == bar else "")))
    # the first opposite-side pivot after a seed lead becomes its promotion partner
    if awaiting and awaiting["partner"] is None and side != awaiting["lead"]["side"]:
        awaiting["partner"] = p
    if in_seed:
        return p                       # seed leads promote with their partner, not on their own
    # A pullback pivot goes major only when price exceeds the RUNNING DAY EXTREME that stood
    # when it was set - the engine's own reference (run_max_H / run_min_L). Using the prior
    # SWING pivot instead is a far lower bar and wrongly promoted the whole chop (b18, b19,
    # b30, b37, b39, b41-46, b51, b52, b55...). An hh/ll is major only as the partner of a
    # promoted pullback, never on its own.
    # ONE candidate per side at a time. A DEEPER low replaces the pending low and DEMOTES it
    # to minor; a low that is not deeper is minor immediately and never competes. Same,
    # mirrored, for highs. Without this contest every pullback eventually promotes.
    # EVERY pivot on the side enters the contest, whatever its two-bar tag - the DEEPEST low
    # wins and becomes the major HL, so a mechanically-tagged `ll` can be the major HL (b35,
    # b56 on 2/24). Restricting the contest to `hl` was wrong.
    if side == "L":
        cur = next((r for r in pending_promo if r["need"] == "H"), None)
        if cur is None or L[bar] < L[cur["p"]["bar"]]:
            if cur is not None: pending_promo.remove(cur)      # demoted, stays minor
            pending_promo.append(dict(p=p, need="H", px=run_max_H, pk=run_max_H_bar))
    else:
        cur = next((r for r in pending_promo if r["need"] == "L"), None)
        if cur is None or H[bar] > H[cur["p"]["bar"]]:
            if cur is not None: pending_promo.remove(cur)
            pending_promo.append(dict(p=p, need="L", px=run_min_L, pk=run_min_L_bar))
    return p

# The day OPENS in the seed phase - b1 seeds both an H and an L. This is the same logic a
# termination resets into, so the open is not a special case, it is just the first seed.
mode = "seed"
st = {"d": None, "ext": 0}
standing_hl = None          # (bar, price)
seed = dict(sH=0, sL=0, dir=None, start=0)
seed_marks.append((0, "H")); seed_marks.append((0, "L"))
awaiting = None             # {lead, partner} pair awaiting major promotion
pending_promo = []          # hl/lh pivots awaiting their new-extreme confirmation

i = 1
while i < n:
    if mode == "trend":
        for ev in evs[i]:
            if ev == "U":
                if st["d"] == -1:
                    add_pivot(st["ext"], "L", i)
                    st["d"] = 1; st["ext"] = i
                else:
                    st["d"] = 1
                    st["ext"] = i if H[i] >= H[st["ext"]] else st["ext"]
            else:
                if st["d"] == 1:
                    add_pivot(st["ext"], "H", i)
                    st["d"] = -1; st["ext"] = i
                else:
                    st["d"] = -1
                    st["ext"] = i if L[i] <= L[st["ext"]] else st["ext"]
        # pullback pivots go major when price resumes past the prior swing extreme. ONLY a
        # MAJOR HL becomes the standing HL - a minor hl that price undercuts before it was
        # ever confirmed never was the trend's floor, and must not terminate anything.
        for pp in list(pending_promo):
            hit = (H[i] > pp["px"]) if pp["need"] == "H" else (L[i] < pp["px"])
            if hit:
                q = pp["p"]
                if q["major"] is None: q["major"] = i
                # the peak that stood when the pullback was set becomes the partner major
                # HH/LL - unless the confirming bar is itself a pivot on that side
                partner_bar = i if any(r["bar"] == i and r["side"] != q["side"] for r in piv) else pp["pk"]
                for r in piv:
                    if r["bar"] == partner_bar and r["side"] != q["side"] and r["major"] is None:
                        r["major"] = i; r["majlab"] = "HH" if r["side"] == "H" else "LL"
                q["majlab"] = "HL" if q["side"] == "L" else "LH"
                if q["side"] == "L":
                    standing_hl = (q["bar"], L[q["bar"]])
                    log.append((i, "standing HL -> b%d (major)" % (q["bar"] + 1)))
                pending_promo.remove(pp)
        # promotion of a post-seed pair: the seed's lead pivot and the pullback that follows
        # it go major together, at the moment price takes out the lead pivot's extreme
        if awaiting and awaiting["partner"] is not None:
            lead = awaiting["lead"]; part = awaiting["partner"]
            hit = (H[i] > H[lead["bar"]]) if lead["side"] == "H" else (L[i] < L[lead["bar"]])
            if hit:
                lead["major"] = i; part["major"] = i
                lead["majlab"] = "HH" if lead["side"] == "H" else "LL"
                part["majlab"] = "HL" if part["side"] == "L" else "LH"
                if part["tag"] == "hl":
                    standing_hl = (part["bar"], L[part["bar"]])
                resumes.append((lead["bar"], i, lead["side"]))
                log.append((i, "TREND RE-CONFIRMED: b%d -> major %s, b%d -> major %s"
                            % (lead["bar"] + 1, lead["tag"].upper(),
                               part["bar"] + 1, part["tag"].upper())))
                awaiting = None
        # termination test, after this bar's events
        if standing_hl and L[i] < standing_hl[1]:
            terms.append((standing_hl[0], standing_hl[1], i))
            log.append((i, "*** BULL TREND TERMINATED (breaks b%d HL) -> seed phase"
                        % (standing_hl[0] + 1)))
            mode = "seed"
            seed = dict(sH=i, sL=i, dir=None, start=i)
            seed_marks.append((i, "H")); seed_marks.append((i, "L"))
            standing_hl = None
        if H[i] > run_max_H: run_max_H = H[i]; run_max_H_bar = i
        if L[i] < run_min_L: run_min_L = L[i]; run_min_L_bar = i
        i += 1
        continue

    # ---- seed phase ----
    bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
    eqH = H[i] == H[i-1]; eqL = L[i] == L[i-1]
    ended = False
    if bt and bb:                                     # strict OB
        if seed["dir"] is None:
            seed["sH"] = i; seed["sL"] = i
            seed_marks.append((i, "H")); seed_marks.append((i, "L"))
        elif seed["dir"] == 1 and obdir[i] == "U":
            seed["sH"] = i; seed_marks.append((i, "H"))
            p = add_pivot(i, "H", i, in_seed=True)     # own turn -> intrabar first pivot
            awaiting = dict(lead=p, partner=None)
            st = {"d": -1, "ext": i}; ended = True
        elif seed["dir"] == -1 and obdir[i] == "D":
            seed["sL"] = i; seed_marks.append((i, "L"))
            p = add_pivot(i, "L", i, in_seed=True)
            awaiting = dict(lead=p, partner=None)
            st = {"d": 1, "ext": i}; ended = True
        else:                                          # OB breaks counter first
            side = "H" if seed["dir"] == 1 else "L"
            ref = seed["sH"] if side == "H" else seed["sL"]
            p = add_pivot(ref, side, i, in_seed=True)
            awaiting = dict(lead=p, partner=None)
            st = {"d": -1 if side == "H" else 1, "ext": i}; ended = True
    elif bt and not bb:                                # higher high only
        if seed["dir"] == -1:
            p = add_pivot(seed["sL"], "L", i, in_seed=True)
            awaiting = dict(lead=p, partner=None); st = {"d": 1, "ext": i}; ended = True
        else:
            seed["dir"] = 1; seed["sH"] = i; seed_marks.append((i, "H"))
    elif bb and not bt:                                # lower low only
        if seed["dir"] == 1:
            p = add_pivot(seed["sH"], "H", i, in_seed=True)
            awaiting = dict(lead=p, partner=None); st = {"d": -1, "ext": i}; ended = True
        else:
            seed["dir"] = -1; seed["sL"] = i; seed_marks.append((i, "L"))
    # IB / equal: nothing carries

    if ended:
        seed_spans.append((seed["start"], i))
        log.append((i, "seed phase ends -> first minor pivot"))
        mode = "trend"; seed = None
    if H[i] > run_max_H: run_max_H = H[i]; run_max_H_bar = i
    if L[i] < run_min_L: run_min_L = L[i]; run_min_L_bar = i
    i += 1

# NO terminal pivot. The running extreme at the close of the session was never confirmed by a
# turn (an HL needs a following higher high, an HH needs a following turn down) and the day
# simply ran out of bars. Labelling it would invent a pivot that price never made.
# (The original engine force-appends one here - same bug, carried over.)
unconfirmed = (st["ext"], "H" if st["d"] == 1 else "L") if st["d"] is not None else None

# ---------------------------------------------------------------- text output
print("=" * 96)
print("PHASE / EVENT LOG   (b%d-b%d)" % (LO, HI))
print("=" * 96)
for (bar, msg) in log:
    if LO - 1 <= bar <= HI - 1:
        print("  b%-3d  %s" % (bar + 1, msg))

print()
print("=" * 96)
print("PIVOTS")
print("=" * 96)
for p in piv:
    if not (LO - 3 <= p["bar"] <= HI - 1): continue
    cs = "b%d%s" % (p["conf"] + 1, "i" if p["intrabar"] else "")
    ms = "-" if p["major"] is None else "b%d" % (p["major"] + 1)
    print("  b%-3d %s  minor %-3s  pivot@%-6s  MAJOR %-3s @%-5s%s"
          % (p["bar"] + 1, p["side"], p["tag"], cs, p["tag"].upper(), ms,
             "   [seed phase]" if p["in_seed"] else ""))

print()
for (hlb, hlp, bb_) in terms:
    print("  TERMINATION: b%d HL broken by b%d" % (hlb + 1, bb_ + 1))
for (hb, cb, sd) in resumes:
    print("  RE-CONFIRMED: b%d high taken out by b%d" % (hb + 1, cb + 1))

# ---------------------------------------------------------------- chart
lo_i, hi_i = LO - 1, HI - 1
sub = range(lo_i, hi_i + 1)
vhi = max(H[k] for k in sub); vlo = min(L[k] for k in sub)
rng = vhi - vlo; off = rng * 0.026

fig, ax = plt.subplots(figsize=(36, 12), dpi=200)

for (s0, s1) in seed_spans:
    if s1 < lo_i or s0 > hi_i: continue          # keep out-of-window spans off the canvas
    ax.axvspan(max(s0, lo_i) - 0.45, min(s1, hi_i) + 0.45, color="#c9a227", alpha=0.10, zorder=0)
    ax.text((max(s0, lo_i) + min(s1, hi_i)) / 2.0, vhi + rng * 0.055, "SEED PHASE",
            ha="center", va="bottom", fontsize=12, color="#8a6a12", fontweight="bold",
            clip_on=False)

for k in sub:
    up = C[k] >= O[k]
    col = "#2e9e8f" if up else "#e0574a"
    ax.plot([k, k], [L[k], H[k]], color=col, lw=1.9, zorder=2)
    ax.add_patch(plt.Rectangle((k - 0.30, min(O[k], C[k])), 0.60,
                               max(abs(C[k] - O[k]), rng * 0.0012),
                               facecolor=col, edgecolor="black", lw=0.5, zorder=3))

for k in sub:
    if k in obdir and kind[k].startswith("OB"):
        s = obdir[k]
        yy = H[k] + off * 0.42 if s == "U" else L[k] - off * 0.42
        ax.plot(k, yy, "o", ms=9, color="gold", mec="black", mew=0.8, zorder=6)

# faded seed H/L trail
for (bar, side) in seed_marks:
    if not (lo_i <= bar <= hi_i): continue
    y = H[bar] + off * 0.95 if side == "H" else L[bar] - off * 0.95
    ax.text(bar, y, side, ha="center", va="bottom" if side == "H" else "top",
            fontsize=15, color="#8a6a12", fontweight="bold", alpha=0.85)

# pivots
last_side_bar = {}
for p in piv:
    bar = p["bar"]
    if not (lo_i <= bar <= hi_i): continue
    t = p["tag"]; bull = t in ("hh", "hl")
    mcol = "#1f7a3d" if bull else "#b23a2e"
    seedbump = off * 1.5 if any(b == bar for b, _ in seed_marks) else 0.0
    if p["side"] == "H":
        y1 = H[bar] + off * 0.95 + seedbump
        y2 = H[bar] + off * 3.15 + seedbump
        y3 = H[bar] + off * 5.15 + seedbump
        va = "bottom"
    else:
        y1 = L[bar] - off * 0.95 - seedbump
        y2 = L[bar] - off * 3.15 - seedbump
        y3 = L[bar] - off * 5.15 - seedbump
        va = "top"
    # adjacent same-side pivots would collide -> push the later one out one extra tier
    prev = last_side_bar.get(p["side"])
    if prev is not None and bar - prev <= 1:
        bump = off * 2.1
        y1 += bump if p["side"] == "H" else -bump
        y2 += bump if p["side"] == "H" else -bump
        y3 += bump if p["side"] == "H" else -bump
    last_side_bar[p["side"]] = bar
    ax.text(bar, y1, t, ha="center", va=va, fontsize=13.5,
            color=mcol, fontweight="bold")
    if p["major"] is not None:
        ml = p.get("majlab") or t.upper()
        mc2 = "#1f7a3d" if ml in ("HH", "HL") else "#b23a2e"
        ax.text(bar, y2, ml, ha="center", va="center", fontsize=14.5,
                color=mc2, fontweight="bold",
                bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec=mc2, lw=1.9))
    if p["major"] is not None:
        lab = "%d%s" % (p["conf"] + 1, "i" if p["intrabar"] else "")
        if p["major"] != p["conf"]: lab += "→%d" % (p["major"] + 1)
        ax.text(bar, y3, lab, ha="center", va=va, fontsize=13,
                color="#b8860b" if p["intrabar"] else "#444444", fontweight="bold")

# termination: standing HL carried into its break + the moment it breaks
for (hlb, hlp, bb_) in terms:
    if not (lo_i - 3 <= hlb <= hi_i): continue
    ax.plot([hlb, bb_], [hlp, hlp], ls=(0, (4, 3)), lw=2.3, color="#b23a2e", zorder=5)
    ax.plot(bb_, hlp, "x", ms=12, mew=2.8, color="#b23a2e", zorder=6)
    xv = bb_ + 0.5
    ax.axvline(xv, ls=(0, (3, 3)), lw=2.3, color="#b23a2e", zorder=5)
    ax.text(xv - 0.16, vlo + rng * 0.02, "BULL TREND TERMINATED", ha="right", va="bottom",
            fontsize=11.5, color="#b23a2e", fontweight="bold", rotation=90)

# resumption: the minor hh carried across to the bar that takes it out
for (hb, cb, sd) in resumes:
    if not (lo_i <= hb <= hi_i): continue
    ax.plot([hb, cb], [H[hb], H[hb]], ls=(0, (4, 3)), lw=2.3, color="#1f7a3d", zorder=5)
    ax.plot(cb, H[hb], "x", ms=12, mew=2.8, color="#1f7a3d", zorder=6)
    xv = cb + 0.5
    ax.axvline(xv, ls=(0, (3, 3)), lw=2.3, color="#1f7a3d", zorder=5)
    ax.text(xv + 0.16, vlo + rng * 0.02, "BULL TREND CONFIRMED", ha="left", va="bottom",
            fontsize=11.5, color="#1f7a3d", fontweight="bold", rotation=90)

ybar = vlo - rng * 0.075
for k in sub:
    ax.text(k, ybar, str(k + 1), ha="center", va="top", fontsize=13, color="#333333")
    kk = kind.get(k, "")
    kc = "#b8860b" if kk.startswith("OB") else ("#7a5aa0" if "IB" in kk or "inside" in kk else "#9aa4a8")
    ax.text(k, ybar - rng * 0.026, kk.replace(" ", "\n", 1), ha="center", va="top",
            fontsize=9.5, color=kc, linespacing=1.3,
            fontweight="bold" if (kk.startswith("OB") or "EQUAL" in kk) else "normal")

ax.set_xlim(lo_i - 0.9, hi_i + 1.1)
ax.set_ylim(vlo - rng * 0.24, vhi + rng * 0.13)
ax.set_title("2022-02-24  b%d–b%d  ·  trend → termination → seed phase → re-confirmation\n"
             "major = wins the deepest-low / highest-high contest AND is confirmed by a new DAY "
             "extreme · \"i\" = intrabar confirm · \"→\" = bar it was promoted to major"
             % (LO, HI), fontsize=14.5, fontweight="bold", pad=16, linespacing=1.7)
ax.grid(axis="y", color="#eceeed", lw=0.8)
ax.set_axisbelow(True)
for s in ("top", "right", "bottom"): ax.spines[s].set_visible(False)
ax.tick_params(axis="x", bottom=False, labelbottom=False)
fig.tight_layout()
out = OUTDIR + "/phase_machine_" + DAY.replace("-", "") + ".png"
fig.savefig(out, facecolor="white")
print("\nsaved", out)
