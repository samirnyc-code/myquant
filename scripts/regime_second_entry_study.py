"""Regime x SECOND-ENTRY study — S83 (worktree branch regime/indep).

Combines three locked pieces, none re-invented:
  1) REGIME  — the tick-driven phase machine (scratchpad/regime_phase_machine.py v4,
     validated bar-by-bar on 2022-02-24 + 2022-04-12). Ported verbatim minus chart
     code; state transitions recorded per TICK -> BULL / NEUTRAL / BEAR at any tick.
  2) SETUPS  — the S61 Brooks entry engine (scripts/brooks_entry_sim.py, spec locked
     2026-07-08): strict legs (IB ignored, OB tick-resolved), direct-travel
     structure, neutral open + first-entry regime adoption + close-through flips,
     origin-reset entry counting. SECOND entries (2EL / 2ES) are the setups.
  3) FILLS   — the S61 sim: stop entry 1t beyond the break level (fill = trigger
     +1t slip), stop 1t beyond the signal bar's opposite extreme, targets 1R and 2R
     (separate books), EOD flat, $5 RT, 1 contract ES ($50/pt).

Every fired entry is labeled with the phase machine's regime state AT THE FILL TICK.
A hi-res chart is rendered PER DAY (regime shading, pivot labels, start/termination
lines, every traded entry marked with its T1/T2 PnL) + a browsable index.html.

Usage:
  python scripts/regime_second_entry_study.py                 # full run + charts
  python scripts/regime_second_entry_study.py --no-charts     # numbers only
  python scripts/regime_second_entry_study.py --validate DAY  # phase-machine events
  python scripts/regime_second_entry_study.py --day DAY       # one day + its chart

Bars/ticks are gitignored and live only in the MAIN repo -> read from
C:/Users/Admin/myquant/data (READ-ONLY). Outputs stay in THIS worktree:
  data/regime/second_entries_regime_20260723.csv        (every trade, both books)
  docs/living/regime_2e_charts/<date>.png + index.html  (gitignored, ~0.5GB)
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")          # main-repo data, read-only
OUT = WT_ROOT / "data" / "regime" / "second_entries_regime_20260723.csv"
CHARTS = WT_ROOT / "docs" / "living" / "regime_2e_charts"

BARS = DATA / "bars" / "_continuous.parquet"
TICKD = DATA / "ticks_continuous"


# ===================== 1. PHASE MACHINE (verbatim port of v4) =====================
def phase_transitions(H, L, n, tP, tbar, trace=None):
    """Tick-driven regime machine. Returns [(tick_idx, mode), ...] starting NEUTRAL.
    Logic identical to scratchpad/regime_phase_machine.py v4; chart/display code
    removed, state code unchanged."""
    piv = []
    trend_starts = []; terms = []; race_lines = []
    prevH = prevL = 0
    first_pivot_done = False
    mode = "NEUTRAL"
    standing = None
    run_b = None; run_px = None
    cand = None
    hi_p = None; lo_p = None
    lsh = None; lsl = None
    has_hl = False; has_lh = False
    struct_hl = None; struct_lh = None
    d = None; leg_px = None; leg_bar = None

    def add_pivot(bar, side, emit):
        nonlocal prevH, prevL, first_pivot_done, hi_p, lo_p, lsh, lsl
        nonlocal has_hl, has_lh, cand, struct_hl, struct_lh
        if side == "H":
            t = "hh" if H[bar] > H[prevH] else ("lh" if H[bar] < H[prevH] else "dh"); prevH = bar
        else:
            t = "hl" if L[bar] > L[prevL] else ("ll" if L[bar] < L[prevL] else "dl"); prevL = bar
        disp = side if not first_pivot_done else t
        first_pivot_done = True
        p = dict(bar=bar, side=side, tag=t, disp=disp, conf=emit,
                 intrabar=(emit == bar), major=None, majlab=None)
        piv.append(p)
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
            if cand is None or L[bar] < L[cand["p"]["bar"]]:
                cand = dict(p=p, ref_px=run_px)
        elif mode == "BEAR" and side == "H":
            if cand is None or H[bar] > H[cand["p"]["bar"]]:
                cand = dict(p=p, ref_px=run_px)
        if mode == "BULL" and side == "H" and bar == run_b:
            p["major"] = emit; p["majlab"] = "HH"
        elif mode == "BEAR" and side == "L" and bar == run_b:
            p["major"] = emit; p["majlab"] = "LL"
        return p

    def start_trend(up, b, px):
        nonlocal mode, standing, run_b, run_px, cand
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
        race_lines.append((broken["bar"], H[broken["bar"]] if up else L[broken["bar"]], b,
                           "bull" if up else "bear"))
        trend_starts.append((b, "bull" if up else "bear", broken["bar"]))
        standing = None
        if partner is not None:
            standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
        run_b, run_px = b, px
        mode = "BULL" if up else "BEAR"; cand = None

    def terminate(b):
        nonlocal mode, standing, run_b, run_px, cand, d, leg_px, leg_bar
        nonlocal hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh, prevH, prevL
        terms.append((standing[0], standing[1], b, mode.lower()))
        mode = "NEUTRAL"
        cand = None; standing = None; run_b = run_px = None
        hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
        struct_hl = struct_lh = None
        prevH = b; prevL = b
        d = None; leg_px = leg_bar = None

    transitions = [(0, "NEUTRAL")]
    cur_bar = -1
    up_done = dn_done = True
    for _t in range(len(tP)):
        b = int(tbar[_t])
        if b < 1 or b >= n:
            continue
        px = tP[_t]
        if b != cur_bar:
            cur_bar = b
            up_done = dn_done = False
        if d == 1 and (leg_px is None or px > leg_px): leg_px, leg_bar = px, b
        if d == -1 and (leg_px is None or px < leg_px): leg_px, leg_bar = px, b
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
                    cand = None
            if mode == "BULL" and px > run_px: run_b, run_px = b, px
            if mode == "BEAR" and px < run_px: run_b, run_px = b, px
            if standing is not None:
                if (mode == "BULL" and px < standing[1]) or (mode == "BEAR" and px > standing[1]):
                    terminate(b)
        if transitions[-1][1] != mode:
            transitions.append((_t, mode))
    if trace is not None:
        trace["starts"] = trend_starts; trace["terms"] = terms
        trace["piv"] = piv; trace["race"] = race_lines
    return transitions


# ============= 2+3. S61 ENTRY ENGINE + FILL SIM (verbatim from brooks_entry_sim) =============
def run_day(g, tP, tbar, transitions):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)

    def tick_slice(i):
        a = np.searchsorted(tbar, i, "left"); z = np.searchsorted(tbar, i, "right")
        return a, z

    def ob_cont_first(i, up):
        a, z = tick_slice(i); s = tP[a:z]
        if up:
            c_ = np.nonzero(s > H[i-1])[0]; k_ = np.nonzero(s < L[i-1])[0]
        else:
            c_ = np.nonzero(s < L[i-1])[0]; k_ = np.nonzero(s > H[i-1])[0]
        tc = c_[0] if len(c_) else np.inf
        tb = k_[0] if len(k_) else np.inf
        return tc < tb

    # legs
    piv = []
    d = 1 if H[1] >= H[0] else -1
    ext_i = 0; pj = 0
    for i in range(1, n):
        if H[i] < H[i-1] and L[i] > L[i-1]:
            continue
        if H[i] > H[i-1] and L[i] < L[i-1]:
            up = (d == 1); cf = ob_cont_first(i, up)
            if up:
                if cf:
                    if H[i] >= H[ext_i]: ext_i = i
                    piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
                else:
                    piv.append((ext_i, H[ext_i], "H")); piv.append((i, L[i], "L")); d = 1; ext_i = i
            else:
                if cf:
                    if L[i] <= L[ext_i]: ext_i = i
                    piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
                else:
                    piv.append((ext_i, L[ext_i], "L")); piv.append((i, H[i], "H")); d = -1; ext_i = i
            pj = i; continue
        if d == 1:
            if H[i] >= H[ext_i]: ext_i = i
            if L[i] < L[pj]:
                piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
        else:
            if L[i] <= L[ext_i]: ext_i = i
            if H[i] > H[pj]:
                piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
        pj = i
    piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L"))

    # structure vs last labeled extreme
    sw = [[idx, prc, typ, ""] for (idx, prc, typ) in piv]
    events = []
    refH = refL = None
    for k, (idx, prc, typ, _) in enumerate(sw):
        if typ == "L":
            if refL is None:
                refL = prc
            elif prc < refL:
                sw[k][3] = "LL"; refL = prc
                lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]
                j0 = lows[-1] if lows else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "H"]
                if seg:
                    lh = max(seg, key=lambda s: s[1])
                    if not lh[3] and (refH is None or lh[1] < refH):
                        lh[3] = "LH"; refH = lh[1]
                        events.append((idx, "LL", lh[0], lh[1]))
        else:
            if refH is None:
                refH = prc
            elif prc > refH:
                sw[k][3] = "HH"; refH = prc
                highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]
                j0 = highs[-1] if highs else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "L"]
                if seg:
                    hl = min(seg, key=lambda s: s[1])
                    if not hl[3] and (refL is None or hl[1] > refL):
                        hl[3] = "HL"; refL = hl[1]
                        events.append((idx, "HH", hl[0], hl[1]))
    ev_by_bar = {}
    for e in events:
        ev_by_bar.setdefault(e[0], []).append(e)

    # one pass: internal engine regime + entry trackers; collect fired entries
    entries = []   # (fire_bar, sig_bar, dir, count, trigger)
    regime = 0
    conf_LH = conf_HL = None
    ecS = 0; refS = None; refSb = None; orgS = None
    ecL = 0; refLo = None; refLb = None; orgL = None
    for i in range(n):
        for (ebar, kind, lb, lp) in ev_by_bar.get(i, []):
            if kind == "LL":
                conf_LH = (lb, lp)
                if regime == 0:
                    regime = -1; ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0
            else:
                conf_HL = (lb, lp)
                if regime == 0:
                    regime = 1; ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
        if i >= 1:
            is_ob = H[i] > H[i-1] and L[i] < L[i-1]
            if regime == 1:
                ecS = 0; refS = None; refSb = None; orgS = None
            else:
                if refS is not None and L[i] < refS - TICK/2:
                    ecS += 1
                    entries.append((i, refSb, "S", min(ecS, 3), refS - TICK))
                    if regime == 0:
                        regime = -1; ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0
                    refS = None; refSb = None
                    if is_ob and H[i] > H[i-1]:
                        refS = L[i]; refSb = i
                    if orgS is not None and L[i] < orgS - TICK/2:
                        ecS = 0; orgS = None
                elif orgS is not None and L[i] < orgS - TICK/2:
                    ecS = 0; orgS = None
                if regime <= 0:
                    if is_ob:
                        if orgS is None: orgS = L[i]
                        refS = L[i]; refSb = i
                    elif H[i] > H[i-1] or L[i] >= L[i-1] - TICK/2:
                        if refS is None and orgS is None: orgS = L[i-1]
                        refS = L[i]; refSb = i
            if regime == -1:
                ecL = 0; refLo = None; refLb = None; orgL = None
            else:
                if refLo is not None and H[i] > refLo + TICK/2:
                    ecL += 1
                    entries.append((i, refLb, "L", min(ecL, 3), refLo + TICK))
                    if regime == 0:
                        regime = 1; ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
                    refLo = None; refLb = None
                    if is_ob and L[i] < L[i-1]:
                        refLo = H[i]; refLb = i
                    if orgL is not None and H[i] > orgL + TICK/2:
                        ecL = 0; orgL = None
                elif orgL is not None and H[i] > orgL + TICK/2:
                    ecL = 0; orgL = None
                if regime >= 0:
                    if is_ob:
                        if orgL is None: orgL = H[i]
                        refLo = H[i]; refLb = i
                    elif L[i] < L[i-1] or H[i] <= H[i-1] + TICK/2:
                        if refLo is None and orgL is None: orgL = H[i-1]
                        refLo = H[i]; refLb = i
        if regime == -1 and conf_LH is not None and C[i] > conf_LH[1]:
            regime = 1; conf_LH = None
            ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
        elif regime == 1 and conf_HL is not None and C[i] < conf_HL[1]:
            regime = -1; conf_HL = None
            ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0

    # ---- trade the fired entries on ticks; label PHASE-MACHINE regime at the fill tick ----
    tr_ix = [t for (t, _) in transitions]
    tr_md = [m for (_, m) in transitions]
    out = []   # per-entry dicts (books nested)
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt >= 3:                       # do not trade 3rd+ entries
            continue
        short = dr == "S"
        a, z = tick_slice(fb)
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        pm_regime = tr_md[bisect_right(tr_ix, jf) - 1]
        fill = trig - TICK if short else trig + TICK        # 1t slip
        stop = H[sb] + TICK if short else L[sb] - TICK
        R = (stop - fill) if short else (fill - stop)
        if R <= 0:
            continue
        seg = tP[jf:]
        js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        js = js_[0] if len(js_) else np.inf
        books = {}
        for k, book in ((1.0, "T1"), (2.0, "T2")):
            tgt = fill - k * R if short else fill + k * R
            jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
            jt = jt_[0] if len(jt_) else np.inf
            if js <= jt:
                ex = stop
            elif np.isfinite(jt):
                ex = tgt
            else:
                ex = tP[-1]
            pnl = (fill - ex) if short else (ex - fill)
            books[book] = (pnl / R, pnl * PT - COMM)
        out.append(dict(dir=dr, cnt=cnt, fb=fb, sb=sb, fill=fill, stop=stop,
                        regime=pm_regime, R=R, books=books))
    return out


# ================================ chart ================================
SHADE = {"neutral": ("#9aa0a6", 0.10), "bull": ("#1f7a3d", 0.06), "bear": ("#b23a2e", 0.06)}
SCOL = {"neutral": "#0e7c86", "bull": "#1f7a3d", "bear": "#b23a2e"}


def render_chart(day, g, trace, day_entries, out_png):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    vhi = H.max(); vlo = L.min(); rng = vhi - vlo; off = rng * 0.021
    fig, ax = plt.subplots(figsize=(36, 12), dpi=150)

    # regime shading
    bounds = sorted([(s_, "start", sd) for (s_, sd, _) in trace["starts"]] +
                    [(b_, "term", None) for (_, _, b_, _) in trace["terms"]])
    cur = "neutral"; x0 = 0; segs = []
    for (xb, ktp, sd) in bounds:
        segs.append((x0, xb, cur)); x0 = xb
        cur = sd if ktp == "start" else "neutral"
    segs.append((x0, n - 1, cur))
    for (a, b_, sdv) in segs:
        col, al = SHADE[sdv]
        ax.axvspan(a + 0.5 if a else -0.9, b_ + 0.5, color=col, alpha=al, zorder=0)
        if b_ - a >= 3:
            ax.text((a + b_) / 2.0, vhi + rng * 0.075, sdv.upper(), ha="center", va="bottom",
                    fontsize=12, fontweight="bold", color=SCOL[sdv])

    # candles
    for k in range(n):
        up_ = C[k] >= O[k]
        col = "#2e9e8f" if up_ else "#e0574a"
        ax.plot([k, k], [L[k], H[k]], color=col, lw=1.7, zorder=2)
        ax.add_patch(plt.Rectangle((k - 0.30, min(O[k], C[k])), 0.60,
                                   max(abs(C[k] - O[k]), rng * 0.0010),
                                   facecolor=col, edgecolor="black", lw=0.45, zorder=3))

    # pivot labels (disp tag + circled major label, as in v4)
    last_side = {}
    for p in trace["piv"]:
        bar, side, t = p["bar"], p["side"], p["disp"]
        mcol = "#8a6a12" if len(t) == 1 else ("#1f7a3d" if t in ("hh", "hl") else "#b23a2e")
        sgn = 1 if side == "H" else -1
        base = (H[bar] + off * 0.85) if side == "H" else (L[bar] - off * 0.85)
        prev = last_side.get(side)
        if prev is not None and bar - prev <= 1: base += sgn * off * 1.9
        last_side[side] = bar
        va = "bottom" if side == "H" else "top"
        if len(t) == 1:
            ax.text(bar, base + sgn * off * 1.2, t, ha="center", va="center", fontsize=13,
                    color="#8a6a12", fontweight="bold",
                    bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec="#8a6a12", lw=1.7))
            continue
        ax.text(bar, base, t, ha="center", va=va, fontsize=11.5, color=mcol, fontweight="bold")
        if p["major"] is not None:
            ml = p["majlab"]
            mc2 = "#8a6a12" if len(ml) == 1 else ("#1f7a3d" if ml in ("HH", "HL") else "#b23a2e")
            ax.text(bar, base + sgn * off * 2.3, ml, ha="center", va="center", fontsize=13,
                    color=mc2, fontweight="bold",
                    bbox=dict(boxstyle="circle,pad=0.30", fc="white", ec=mc2, lw=1.7))

    # race / termination lines + verticals
    for (pb, px_, bb_, sdv) in trace["race"]:
        col = SCOL[sdv]
        ax.plot([pb, bb_], [px_, px_], ls=(0, (4, 3)), lw=2.2, color=col, zorder=5)
        ax.plot(bb_, px_, "x", ms=12, mew=2.6, color=col, zorder=6)
    for (pb, px_, bb_, sdv) in trace["terms"]:
        ax.plot([pb, bb_], [px_, px_], ls=(0, (4, 3)), lw=2.2, color="#33454d", zorder=5)
        ax.plot(bb_, px_, "x", ms=12, mew=2.6, color="#33454d", zorder=6)
    _evt = ([(bb_, "term", sdv) for (_, _, bb_, sdv) in trace["terms"]] +
            [(sb, "start", sdv) for (sb, sdv, _) in trace["starts"]])
    _evt.sort()
    for _k, (xb, ekind, sdv) in enumerate(_evt):
        col = SCOL["neutral"] if ekind == "term" else SCOL[sdv]
        txt = ("NEUTRAL  b%d" % (xb + 1)) if ekind == "term" else ("%s TREND  b%d" % (sdv.upper(), xb + 1))
        xv = xb + 0.5
        ax.axvline(xv, ls=(0, (3, 3)), lw=2.2, color=col, zorder=5)
        ytxt = vlo + rng * (0.015 if _k % 2 == 0 else 0.115)
        ax.text(xv - 0.14, ytxt, txt, ha="right", va="bottom", fontsize=10.5,
                color=col, fontweight="bold", rotation=90)

    # ---- entries: marker at fill + PnL annotation (2E bold, 1E faint) ----
    net2 = 0.0
    for e in day_entries:
        short = e["dir"] == "S"
        is2 = e["cnt"] == 2
        col = "#b23a2e" if short else "#1f7a3d"
        mk = "v" if short else "^"
        ax.plot(e["fb"], e["fill"], mk, ms=15 if is2 else 9, color=col,
                mec="black", mew=1.2, alpha=1.0 if is2 else 0.45, zorder=7)
        t1 = e["books"]["T1"][1]; t2 = e["books"]["T2"][1]
        lab = "%dE%s %s\nT1 %s\nT2 %s" % (e["cnt"], "S" if short else "L", e["regime"],
                                          "%+.0f" % t1, "%+.0f" % t2)
        yy = e["fill"] + (off * 2.2 if short else -off * 2.2)
        ax.text(e["fb"], yy, lab, ha="center", va="bottom" if short else "top",
                fontsize=9.5 if is2 else 7.5, color=col,
                fontweight="bold" if is2 else "normal",
                alpha=1.0 if is2 else 0.55, linespacing=1.2,
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=col,
                          lw=1.3 if is2 else 0.6, alpha=0.85))
        # stop line for 2E
        if is2:
            ax.plot([e["fb"] - 0.6, e["fb"] + 0.6], [e["stop"]] * 2, color=col,
                    lw=1.4, ls=":", zorder=6)
            net2 += t2
    # bar numbers
    ybar = vlo - rng * 0.075
    for k in range(n):
        ax.text(k, ybar, str(k + 1), ha="center", va="top", fontsize=10.5, color="#333333")

    n2 = sum(1 for e in day_entries if e["cnt"] == 2)
    ax.set_xlim(-1.0, n)
    ax.set_ylim(vlo - rng * 0.13, vhi + rng * 0.13)
    ax.set_title("%s  ·  phase-machine regime × S61 second entries   |   "
                 "2E trades: %d   2E net (T2 book): %+.0f$" % (day, n2, net2),
                 fontsize=15, fontweight="bold", pad=14)
    ax.grid(axis="y", color="#eceeed", lw=0.8); ax.set_axisbelow(True)
    for s_ in ("top", "right", "bottom"): ax.spines[s_].set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    fig.tight_layout()
    fig.savefig(out_png, facecolor="white")
    plt.close(fig)


def write_index(day_rows):
    """day_rows: list of (date, n2, net2_T1, net2_T2). Newest first, lazy-loaded imgs."""
    rows = sorted(day_rows, reverse=True)
    h = ["<!doctype html><meta charset='utf-8'><title>Regime × 2E charts</title>",
         "<style>body{font-family:Segoe UI,Arial;margin:18px;background:#fafafa}",
         "h2{margin:26px 0 6px} img{max-width:100%;border:1px solid #ddd;background:#fff}",
         ".pos{color:#1f7a3d}.neg{color:#b23a2e}</style>",
         "<h1>Regime × second entries — %d days</h1>" % len(rows),
         "<p>Marker = entry fill (▲ long ▼ short, big = 2E). Label = count/dir, regime at fill, T1/T2 net$.</p>"]
    for (dstr, n2, s1, s2) in rows:
        c1 = "pos" if s1 >= 0 else "neg"; c2 = "pos" if s2 >= 0 else "neg"
        h.append("<h2>%s — 2E: %d | T1 <span class=%s>%+.0f$</span> | T2 <span class=%s>%+.0f$</span></h2>"
                 % (dstr, n2, c1, s1, c2, s2))
        h.append("<a href='%s.png' target='_blank'><img loading='lazy' src='%s.png'></a>" % (dstr, dstr))
    (CHARTS / "index.html").write_text("\n".join(h), encoding="utf-8")


# ================================ driver ================================
def load_day(b, dstr):
    g = b[b["Date"] == dstr].sort_values("DateTime").reset_index(drop=True)
    p = TICKD / f"{dstr}.parquet"
    if len(g) < 30 or not p.exists():
        return None, None, None
    tk = pd.read_parquet(p).sort_values("DateTime")
    if tk.empty:
        return None, None, None
    tP = tk["Price"].values
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
    return g, tP, tbar


def flat_rows(dstr, day_entries):
    rows = []
    for e in day_entries:
        for book in ("T1", "T2"):
            r_, net_ = e["books"][book]
            rows.append((dstr, e["dir"], e["cnt"], book, e["regime"], e["fb"] + 1,
                         e["sb"] + 1, e["fill"], e["stop"], r_, net_, e["R"]))
    return rows


COLS = ["Date", "dir", "count", "book", "regime", "fire_bar", "sig_bar",
        "fill", "stop", "R", "net", "Rpts"]


def main():
    do_charts = "--no-charts" not in sys.argv
    b = pd.read_parquet(BARS)
    b["Date"] = b["DateTime"].dt.date.astype(str)

    if len(sys.argv) > 2 and sys.argv[1] == "--validate":
        dstr = sys.argv[2]
        g, tP, tbar = load_day(b, dstr)
        H, L = g["High"].values, g["Low"].values
        trace = {}
        phase_transitions(H, L, len(g), tP, tbar, trace=trace)
        print("PHASE MACHINE", dstr)
        for (sb, sd, brk) in trace["starts"]:
            print("  %s TREND STARTS  b%d  (breaks the b%d pivot)" % (sd.upper(), sb + 1, brk + 1))
        for (pb, px_, bb_, sd) in trace["terms"]:
            print("  %s TREND TERMINATED b%d (breaks the b%d %s) -> NEUTRAL"
                  % (sd.upper(), bb_ + 1, pb + 1, "HL" if sd == "bull" else "LH"))
        return

    if len(sys.argv) > 2 and sys.argv[1] == "--day":
        days = [sys.argv[2]]
    else:
        days = sorted(b["Date"].unique())

    CHARTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); rows = []; day_rows = []
    n_days = 0
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L = g["High"].values, g["Low"].values
        try:
            trace = {}
            transitions = phase_transitions(H, L, len(g), tP, tbar, trace=trace)
            de = run_day(g, tP, tbar, transitions)
            rows += flat_rows(dstr, de)
            e2 = [e for e in de if e["cnt"] == 2]
            day_rows.append((dstr, len(e2),
                             sum(e["books"]["T1"][1] for e in e2),
                             sum(e["books"]["T2"][1] for e in e2)))
            if do_charts:
                render_chart(dstr, g, trace, de, CHARTS / f"{dstr}.png")
            n_days += 1
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
        del tP, tbar; gc.collect()
        if (di + 1) % 50 == 0:
            print(f"[{di+1}/{len(days)}] trades={len(rows)//2} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=COLS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    if do_charts:
        write_index(day_rows)
    print(f"\nDONE {time.time()-t0:.0f}s  days={n_days}  rows={len(df)}  -> {OUT}")

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    for cnt_sel, tag in ((2, "SECOND ENTRIES (2E)"), (1, "first entries (reference)")):
        d1 = df[df["count"] == cnt_sel]
        print("\n" + "=" * 100)
        print(f"{tag}  n/book={len(d1)//2}")
        print("=" * 100)
        for book in ["T1", "T2"]:
            d2 = d1[d1.book == book]
            if not len(d2):
                continue
            print(f"\n-- target {book} ({'1R' if book=='T1' else '2R'}) --  n={len(d2)}  "
                  f"meanR {d2['R'].mean():+.3f}  win {(d2['R']>0).mean()*100:.1f}%  "
                  f"net ${d2['net'].sum():,.0f}  PF {pf(d2['net']):.2f}")
            t = d2.groupby(["regime", "dir"]).agg(
                n=("R", "size"), meanR=("R", "mean"),
                win=("R", lambda s: (s > 0).mean() * 100),
                net=("net", "sum"), PF=("net", pf)).round(3)
            print(t.to_string())


if __name__ == "__main__":
    main()
