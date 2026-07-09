"""Thomas/Cadaver trendlines on the S63 pivot engine (deterministic, anchored hull).

Bull TL = from the lowest low, the line that keeps ALL subsequent lows on one side
(= anchored LOWER convex hull of swing lows). Shallowest = first hull edge; later
(steeper) hull edges = 'accelerated' TLs. Break = a bar CLOSES beyond the shallowest
line. Mirror for bear (upper hull of swing highs).
"""
import sys
from pathlib import Path
from datetime import date
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT)); import massive

B = pd.read_parquet(ROOT/"data"/"bars"/"_continuous.parquet"); B["Date"] = B["DateTime"].dt.date.astype(str)


def pivots(DAY):
    g = B[B["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
    O, H, L, C = (g[c].values.astype(float) for c in ["Open", "High", "Low", "Close"]); n = len(g)
    tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1; tP = tk["Price"].values
    def fbk(i):
        s = tP[tbar == i]; up = np.nonzero(s > H[i-1])[0]; dn = np.nonzero(s < L[i-1])[0]
        if not len(up) and not len(dn): up = np.nonzero(s >= H[i-1])[0]; dn = np.nonzero(s <= L[i-1])[0]
        return "D" if (dn[0] if len(dn) else np.inf) < (up[0] if len(up) else np.inf) else "U"
    evs = {}
    for i in range(1, n):
        bt = H[i] > H[i-1]; bb = L[i] < L[i-1]; eq = (H[i] == H[i-1]) and (L[i] == L[i-1])
        evs[i] = (["D", "U"] if fbk(i) == "D" else ["U", "D"]) if ((bt and bb) or eq) else (["U"] if bt else (["D"] if bb else []))
    st = {"d": None, "ext": 0}; piv = []   # (pivot_bar, type, confirmation_bar)
    def proc(ev, i):
        if ev == "U":
            if st["d"] == -1: piv.append((st["ext"], "L", i)); st["d"] = 1; st["ext"] = i
            else: st["d"] = 1; st["ext"] = i if H[i] >= H[st["ext"]] else st["ext"]
        else:
            if st["d"] == 1: piv.append((st["ext"], "H", i)); st["d"] = -1; st["ext"] = i
            else: st["d"] = -1; st["ext"] = i if L[i] <= L[st["ext"]] else st["ext"]
    for i in range(1, n):
        for ev in evs[i]: proc(ev, i)
    piv.append((st["ext"], "H" if st["d"] == 1 else "L", n-1))
    return g, O, H, L, C, n, piv


def lower_hull(pts):
    """pts = [(x, y)] sorted by x. Returns lower-hull vertices (all pts on/above)."""
    h = []
    for p in pts:
        while len(h) >= 2 and (h[-1][0]-h[-2][0])*(p[1]-h[-2][1]) - (h[-1][1]-h[-2][1])*(p[0]-h[-2][0]) <= 0:
            h.pop()
        h.append(p)
    return h


def upper_hull(pts):
    h = []
    for p in pts:
        while len(h) >= 2 and (h[-1][0]-h[-2][0])*(p[1]-h[-2][1]) - (h[-1][1]-h[-2][1])*(p[0]-h[-2][0]) >= 0:
            h.pop()
        h.append(p)
    return h


TICK = 0.25; POKE = 2*TICK

def _shallow(pts, bull):
    """anchored-hull first edge from the extreme; returns (x0,y0,slope) valid over pts."""
    if len(pts) < 2: return None
    o = min(range(len(pts)), key=lambda k: pts[k][1] if bull else -pts[k][1])
    p = pts[o:]
    if len(p) < 2: return None
    b0 = p[0]; best = None
    for q in p[1:]:
        if q[0] == b0[0]: continue
        m = (q[1]-b0[1])/(q[0]-b0[0])
        if best is None or (m < best if bull else m > best): best = m
    return None if best is None else (b0[0], b0[1], best)


def _regime(seq):
    """OPEN-adoption regime (from brooks_entry_engine): adopt direction from the FIRST
    structural read off the open (first HH -> bull, first LL -> bear); once a regime
    exists it flips only on the opposite confirmation. We do NOT wait for 2 swings."""
    reg = 0
    for (b, t, lab) in seq:
        if reg == 0:
            if lab == "HH": reg = 1
            elif lab == "LL": reg = -1
        elif reg == 1 and lab == "LL": reg = -1
        elif reg == -1 and lab == "HH": reg = 1
    return "bull" if reg == 1 else ("bear" if reg == -1 else "neutral")


def build(DAY):
    g, O, H, L, C, n, piv = pivots(DAY)      # piv: (bar, type, confirmation_bar)
    # causal HH/HL/LH/LL labels for the user's pivots
    tagged = []; pHp = pLp = None
    for (b, t, c) in piv:
        if t == "H": lab = "HH" if (pHp is None or H[b] > pHp) else ("LH" if H[b] < pHp else "DH"); pHp = H[b]
        else: lab = "HL" if (pLp is None or L[b] > pLp) else ("LL" if L[b] < pLp else "DL"); pLp = L[b]
        tagged.append((b, t, lab, c))
    buys = []; sells = []; breaks = []
    tl_snaps = []; mtl_snaps = []            # (bar, x0,y0,m) active TL / mTL as known at bar
    state_at = {}; tl_at = {}; acc_at = {}
    mtlL_at = {}; mtlH_at = {}               # mTL on bar LOWS / bar HIGHS, every bar from b1
    moL = 0; moH = 0                         # micro origins (re-anchor on micro close-break)
    for i in range(n):
        known = [(b, t) for (b, t, c) in piv if c <= i]      # only swings CONFIRMED by bar i
        state = _regime([(b, t, lab) for (b, t, lab, c) in tagged if c <= i]); state_at[i] = state
        # --- mTL EVERY BAR from the open (b1L-b2L to start), independent of regime ---
        if i >= 1:
            mt = _shallow([(j, L[j]) for j in range(moL, i+1)], True)   # bull mTL on bar lows
            if mt:
                ln = mt[1] + mt[2]*(i-mt[0])
                if C[i] < ln-1e-9 and i > mt[0]: moL = i               # micro break -> re-anchor
                else: mtlL_at[i] = mt
            mt = _shallow([(j, H[j]) for j in range(moH, i+1)], False)  # bear mTL on bar highs
            if mt:
                ln = mt[1] + mt[2]*(i-mt[0])
                if C[i] > ln+1e-9 and i > mt[0]: moH = i
                else: mtlH_at[i] = mt
        if len(known) < 1: continue
        if state == "bull":
            klows = [(b, L[b]) for (b, t) in known if t == "L"]
            tl = _shallow(klows, True)
            if tl and tl[2] > 0:
                x0, y0, m = tl; line = y0 + m*(i-x0)
                tl_snaps.append((i, x0, y0, m)); tl_at[i] = (x0, y0, m)
                if i > x0:
                    if C[i] < line-1e-9: breaks.append((i, "bull"))
                    elif line-4*TICK <= L[i] <= line+POKE and C[i] > line: buys.append((i, x0, y0, m))
                # accelerated TL = steepest (last) lower-hull edge from a later low
                hull = lower_hull(klows)
                if len(hull) >= 3:
                    ax0, ay0 = hull[-2]; ax1, ay1 = hull[-1]; am = (ay1-ay0)/(ax1-ax0) if ax1 != ax0 else 0
                    if am > 0:
                        acc_at[i] = (ax0, ay0, am); la = ay0 + am*(i-ax0)
                        if i > ax1 and la-4*TICK <= L[i] <= la+POKE and C[i] > la: buys.append((i, ax0, ay0, am))
        elif state == "bear":
            khighs = [(b, H[b]) for (b, t) in known if t == "H"]
            tl = _shallow(khighs, False)
            if tl and tl[2] < 0:
                x0, y0, m = tl; line = y0 + m*(i-x0)
                tl_snaps.append((i, x0, y0, m)); tl_at[i] = (x0, y0, m)
                if i > x0:
                    if C[i] > line+1e-9: breaks.append((i, "bear"))
                    elif line-4*TICK <= H[i] <= line+POKE and C[i] < line: sells.append((i, x0, y0, m))
                hull = upper_hull(khighs)
                if len(hull) >= 3:
                    ax0, ay0 = hull[-2]; ax1, ay1 = hull[-1]; am = (ay1-ay0)/(ax1-ax0) if ax1 != ax0 else 0
                    if am < 0:
                        acc_at[i] = (ax0, ay0, am); la = ay0 + am*(i-ax0)
                        if i > ax1 and la-POKE <= H[i] <= la+4*TICK and C[i] < la: sells.append((i, ax0, ay0, am))

    # ---- bar-by-bar replay: one PDF page per bar, drawn ONLY with info known at bar i ----
    from matplotlib.backends.backend_pdf import PdfPages
    buy_bars = {b: (x0, y0, m) for (b, x0, y0, m) in buys}
    sell_bars = {b: (x0, y0, m) for (b, x0, y0, m) in sells}
    break_bars = {b: k for (b, k) in breaks}
    out = ROOT/"docs"/"living"/(f"tl_replay_{DAY.replace('-','')}.pdf")
    with PdfPages(out) as pdf:
        for i in range(n):
            fig, ax = plt.subplots(figsize=(16, 8))
            lo = L[:i+1].min(); hi = H[:i+1].max(); off = 0.014*(hi-lo+1e-9)
            for j in range(i+1):
                col = "#26a69a" if C[j] >= O[j] else "#ef5350"
                ax.plot([j, j], [L[j], H[j]], color=col, lw=1.6, zorder=2)
                ax.add_patch(plt.Rectangle((j-0.34, min(O[j], C[j])), 0.68, max(abs(C[j]-O[j]), .02), facecolor=col, edgecolor="black", lw=0.4, zorder=3))
            ax.axvspan(i-0.5, i+0.5, color="gold", alpha=0.18, zorder=0)   # current bar
            # user's pivots (HH/HL/LH/LL) confirmed by bar i
            for (b, t, lab, c) in tagged:
                if c > i: continue
                yy = H[b] if t == "H" else L[b]; cc = "darkgreen" if lab in ("HH", "HL") else ("darkred" if lab in ("LH", "LL") else "gray")
                ax.plot(b, yy, "o", ms=4, color=cc, zorder=6)
                ax.text(b, yy + (off*0.9 if t == "H" else -off*0.9), lab, ha="center", va="bottom" if t == "H" else "top", fontsize=7, color=cc, fontweight="bold", zorder=6)
            # mTL on bar lows & highs from b1 (gray), TL shallowest (red/purple), accelerated (orange)
            if i in mtlL_at:
                x0, y0, m = mtlL_at[i]; ax.plot([x0, i], [y0, y0+m*(i-x0)], color="dimgray", lw=1.2, ls="--", alpha=0.8, zorder=6, label="mTL (bar lows)")
            if i in mtlH_at:
                x0, y0, m = mtlH_at[i]; ax.plot([x0, i], [y0, y0+m*(i-x0)], color="silver", lw=1.2, ls="--", alpha=0.8, zorder=6, label="mTL (bar highs)")
            if i in tl_at:
                x0, y0, m = tl_at[i]; ax.plot([x0, i], [y0, y0+m*(i-x0)], color="red" if m > 0 else "purple", lw=2.6, zorder=7, label="TL shallowest")
            if i in acc_at:
                x0, y0, m = acc_at[i]; ax.plot([x0, i], [y0, y0+m*(i-x0)], color="orange", lw=2.0, ls="--", zorder=7, label="TL accelerated")
            # entries / breaks that have occurred by bar i
            for b in [x for x in buy_bars if x <= i]:
                ax.annotate("", xy=(b, L[b]-off*0.3), xytext=(b, L[b]-off*1.5), arrowprops=dict(arrowstyle="-|>", color="green", lw=2.4), zorder=9)
                ax.text(b, L[b]-off*1.6, "buy", ha="center", va="top", fontsize=8, color="green", fontweight="bold", zorder=9)
            for b in [x for x in sell_bars if x <= i]:
                ax.annotate("", xy=(b, H[b]+off*0.3), xytext=(b, H[b]+off*1.5), arrowprops=dict(arrowstyle="-|>", color="red", lw=2.4), zorder=9)
                ax.text(b, H[b]+off*1.6, "sell", ha="center", va="bottom", fontsize=8, color="red", fontweight="bold", zorder=9)
            for b in [x for x in break_bars if x <= i]:
                ax.plot(b, C[b], "x", ms=10, mew=2.6, color="black", zorder=10)
            stt = state_at.get(i, "neutral")
            ax.set_xlim(-1, max(10, i+2)); ax.set_ylim(lo-off*3, hi+off*3)
            ax.set_xticks(range(0, i+1, 2)); ax.set_xticklabels([str(k+1) for k in range(0, i+1, 2)], fontsize=7); ax.grid(alpha=0.25, lw=0.5)
            if i in mtlL_at or i in mtlH_at or i in tl_at: ax.legend(loc="upper left", fontsize=9)
            ax.set_title(f"{DAY}  bar {i+1}/{n}   state={stt.upper()}   (only info known through bar {i+1})", fontsize=12, fontweight="bold")
            fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
    print("saved", out, f"| pages={n} buys={len(buys)} sells={len(sells)} breaks={len(breaks)}")
    return str(out)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "2022-02-24")
