"""S75R — render each 1-minute bar as a full annotated explainer, b1-slide style.

Layout, left to right:
  * the real intrabar PRICE PATH (built from every print in the minute — this is
    actual data, not a sketch), with numbered markers
  * the candle
  * the BidAsk footprint ladder: coloured cells, price | bid | ask | delta
  * numbered callouts, each joined to its ladder row by a connector line and a DOT

Numbering runs in LADDER ORDER, top to bottom, so the marker column on the left and
the callout column on the right read in the identical sequence. (This is the same
lesson as the 5M b1 slide: mixing a chronological right column with a price-anchored
left column makes the numbers look wrong.)

Callouts are generated from the bar's own facts — the high, the dominant print, any
diagonal imbalance, the open/close rows, the low — so every number shown is real.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "footprint" / "ES_1m_20260717.json"
OUTDIR = ROOT / "docs" / "slides" / "flow-1m-20260717"

INK, MUT = "#20262e", "#68707c"
GRN, RED, BLU, AMB = "#2e9e4f", "#e05555", "#4a7ab5", "#c9922a"
DKG, DKR = "#1e7a3f", "#c23434"
BG = "#fcfcfa"
CIRC = "①②③④⑤⑥⑦⑧⑨"


def zigzag(path, th):
    """Turning points of the intrabar path, in TIME order, as indices into path."""
    # Track the running high AND low separately. The previous version kept one
    # `ext` with dirn starting at 0, so both update branches fired, dirn never left
    # 0, and no reversal was ever recorded — every bar came back with zero pivots.
    piv, dirn = [], 0
    hi = lo = path[0][1]
    hii = loi = 0
    for i, (_t, p) in enumerate(path):
        if p > hi:
            hi, hii = p, i
        if p < lo:
            lo, loi = p, i
        if dirn >= 0 and hi - p >= th:
            piv.append(hii)
            dirn, hi, lo, hii, loi = -1, p, p, i, i
        elif dirn <= 0 and p - lo >= th:
            piv.append(loi)
            dirn, hi, lo, hii, loi = 1, p, p, i, i
    return piv


def events(b):
    """The bar's story in the order PRICE ACTUALLY TRAVELLED IT.

    (1) is always the OPEN, (2) is wherever price went next, and so on to the
    close, derived from the real tick path. Numbering by ladder position instead
    put the open in the middle of the list, which is not how a bar forms or how
    anyone reads one.
    """
    lad = b["ladder"]
    idx = {round(p, 2): i for i, (p, *_) in enumerate(lad)}
    big = max(lad, key=lambda r: abs(r[3]))
    imb = set(b["buy_imb"]) | set(b["sell_imb"])
    path = b["path"]
    rng = max(b["h"] - b["l"], 0.25)

    # widen the turn threshold until the story fits in a readable number of steps
    piv = []
    for frac in (0.28, 0.38, 0.50, 0.65, 0.85):
        piv = zigzag(path, max(0.5, rng * frac))
        if len(piv) <= 4:
            break

    # (price, time-fraction) so the left-hand marker sits at the moment the step
    # happened, not merely at the first time that price ever traded
    cand = [(b["o"], 0.0)] + [(path[i][1], path[i][0]) for i in piv] + [(b["c"], 1.0)]
    steps = []
    for price, tf in cand:
        p = round(price, 2)
        if p in idx and (not steps or steps[-1][0] != p):
            steps.append((p, tf))
    steps = steps[:6]

    out, prev = [], None
    for k, (p, tf) in enumerate(steps):
        i = idx[p]
        _pp, bid, ask, d = lad[i]
        tags = []
        if p == round(big[0], 2):
            tags.append(f"dominant print — {abs(d) / max(abs(b['delta']), 1) * 100:.0f}% of net delta")
        if p in imb:
            tags.append("diagonal imbalance here")

        if k == 0:
            head, col, sub = f"OPEN {p:.2f}", INK, ["the minute starts here"]
        elif k == len(steps) - 1:
            head, col = f"CLOSE {p:.2f}", INK
            sub = [f"finishes at {b['close_loc'] * 100:.0f}% of the bar's range"]
        else:
            up = prev is not None and p > prev
            if p == round(b["h"], 2):
                head = f"UP TO THE HIGH {p:.2f}"
            elif p == round(b["l"], 2):
                head = f"DOWN TO THE LOW {p:.2f}"
            else:
                head = f"{'PUSH UP TO' if up else 'PULLS BACK TO'} {p:.2f}"
            col, sub = (DKG if up else DKR), []
        sub.append(f"{bid:,} bid x {ask:,} ask = {d:+,}")
        sub += tags
        out.append((i, head + "\n" + "\n".join("• " + s for s in sub), col, tf))
        prev = p
    return out


def context_panel(ax, b, bars, sr, n, x0=0.30, x1=4.30):
    """Every 1M bar UP TO THIS ONE, with the S/R that was knowable in advance.

    Y-scale is built from bars 1..i only — never the full window — so the panel
    cannot leak where price goes next. It rescales as the session develops, which
    is the honest behaviour even though a fixed scale would look steadier.
    """
    hist = [x for x in bars if x["i"] <= b["i"]]
    lo = min(x["l"] for x in hist)
    hi = max(x["h"] for x in hist)
    pad = max((hi - lo) * 0.15, 2.0)
    lo, hi = lo - pad, hi + pad

    def cy(p):                                   # price -> panel y
        return (p - lo) / (hi - lo) * (n - 1.0) + 0.5

    def cx(k):                                   # bar index -> panel x
        return x0 + 0.35 + (x1 - x0 - 0.5) * (k / max(len(bars) - 1, 1))

    ax.add_patch(Rectangle((x0, 0.2), x1 - x0, n - 0.4, facecolor="white",
                           edgecolor="#e3e3dd", lw=1.0, zorder=0))

    # S/R that falls inside the visible band
    for s in sr:
        if not (lo < s["price"] < hi):
            continue
        y = cy(s["price"])
        c = BLU if s["kind"] == "mq" else "#8a6d3b"
        ax.plot([x0 + 0.06, x1 - 0.06], [y, y], color=c, lw=1.1, ls="--",
                alpha=.85, zorder=1)
        ax.text(x0 + 0.10, y + 0.42, f"{s['label']} {s['price']:.2f}",
                fontsize=6.8, color=c, va="center", zorder=2)

    if b.get("vwap"):                            # session VWAP to this bar
        vy = cy(b["vwap"])
        if 0.4 < vy < n:
            ax.plot([x0 + 0.06, x1 - 0.06], [vy, vy], color="#9a6fb0", lw=1.2,
                    alpha=.9, zorder=1)
            ax.text(x1 - 0.10, vy + 0.42, f"VWAP {b['vwap']:.2f}", fontsize=6.8,
                    color="#9a6fb0", ha="right", va="center", zorder=2)

    w = (x1 - x0 - 0.5) / max(len(bars), 1) * 0.62
    for x in hist:
        k = x["i"] - 1
        xx = cx(k)
        cur = x["i"] == b["i"]
        col = GRN if x["c"] >= x["o"] else RED
        ax.plot([xx, xx], [cy(x["l"]), cy(x["h"])], color=col, lw=0.8,
                alpha=1.0 if cur else .75, zorder=3)
        y0, y1 = sorted((cy(x["o"]), cy(x["c"])))
        ax.add_patch(Rectangle((xx - w / 2, y0), w, max(y1 - y0, 0.12),
                               facecolor=col, edgecolor=INK if cur else "none",
                               lw=1.1 if cur else 0, alpha=1.0 if cur else .75,
                               zorder=3))
        if cur:                                  # mark where we are
            ax.annotate("", xy=(xx, cy(x["h"]) + 0.5), xytext=(xx, cy(x["h"]) + 2.1),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2), zorder=4)

    ax.text(x0, n + 0.5, f"PRICE ACTION SO FAR  ·  bars 1–{b['i']}  ·  "
                         f"{hist[0]['time']}→{b['time']}",
            fontsize=8.6, color=MUT, ha="left")


def render(b, bars, sr):
    lad = b["ladder"]
    n = len(lad)
    ev = events(b)
    # Give every callout at least ~3.8 ladder-rows of vertical room, then let the
    # canvas grow to fit. Sizing the page off `n` alone squashed the callouts on
    # narrow-range bars (12 rows, 5 callouts) and they overlapped.
    TOP = n + 4.7
    fig_h = max(4.6, 0.34 * TOP + 2.4)
    fig, ax = plt.subplots(figsize=(20.9, fig_h))
    ax.set_xlim(0, 22.0)
    ax.set_ylim(-3.4, TOP)
    ax.axis("off")
    fig.patch.set_facecolor(BG)

    context_panel(ax, b, bars, sr, n)

    top = lad[0][0]

    def y_of(p):
        return n - 1 - (top - p) / 0.25 + 0.5

    # ---- the real intrabar price path ---------------------------------------
    PX0, PW = 5.00, 1.95
    xs = [PX0 + t * PW for t, _ in b["path"]]
    ys = [y_of(p) for _, p in b["path"]]
    ax.plot(xs, ys, color=MUT, lw=1.5, alpha=.9, zorder=1)
    ax.annotate("", xy=(xs[-1], ys[-1]), xytext=(xs[-3], ys[-3]),
                arrowprops=dict(arrowstyle="->", color=MUT, lw=1.8))
    # sits below the OHLC line (TOP-1.25) — the two were overlapping
    ax.text(PX0, n + 0.5, "TIME →  path inside the minute",
            fontsize=9, color=MUT, ha="left")

    # numbered markers on the path, at each event's price
    for k, (i, _t, _c, tf) in enumerate(ev):
        p = lad[i][0]
        x = PX0 + tf * PW
        ax.text(x, y_of(p), CIRC[k], fontsize=12, color=INK, ha="center",
                va="center", fontweight="bold", zorder=4,
                bbox=dict(boxstyle="circle,pad=0.08", facecolor=BG, edgecolor="none"))

    # ---- candle --------------------------------------------------------------
    # Body spans from the CLOSE row to the OPEN row (whichever is lower is the
    # rectangle's origin). The previous version anchored at y_of(max(o,c)) - 0.5,
    # which put the body's bottom edge on the open row and grew it UPWARD — so on a
    # 1-tick body like bar 27 (O 7532.00 / C 7531.75) it covered 7532.25 and never
    # reached the close. The +-0.45 padding makes it span both cells fully.
    CX = 7.30
    ax.plot([CX, CX], [y_of(b["l"]) - .45, y_of(b["h"]) + .45], color=MUT, lw=2)
    up = b["c"] >= b["o"]
    ylo, yhi = sorted((y_of(b["o"]), y_of(b["c"])))
    ax.add_patch(Rectangle((CX - 0.30, ylo - 0.45), 0.60, (yhi - ylo) + 0.90,
                           facecolor=GRN if up else RED, edgecolor="none"))

    # ---- ladder --------------------------------------------------------------
    LX, LW = 9.65, 4.35
    X = {"price": LX + 0.95, "bid": LX + 2.15, "ask": LX + 3.15, "delta": LX + 4.22}
    for k, lab in (("price", "price"), ("bid", "bid"), ("ask", "ask"), ("delta", "Δ")):
        ax.text(X[k], n + 0.5, lab, ha="right", fontsize=9, color=MUT, family="Consolas")

    imb = set(b["buy_imb"]) | set(b["sell_imb"])
    big = max(lad, key=lambda r: abs(r[3]))
    vmax = max(r[1] + r[2] for r in lad)

    # ---- volume profile + POC -------------------------------------------------
    # The shape of the distribution is half of what a footprint tells you, and POC
    # was only ever stated in text. Drawn as a histogram so you can SEE whether
    # volume piled at the extreme (absorption / exhaustion) or in the middle
    # (balance), and where the bar's fair price actually sat.
    HW = 1.35
    poc_row = max(range(n), key=lambda k: lad[k][1] + lad[k][2])
    ax.text(LX - 0.06, n + 0.5, "volume", ha="right", fontsize=9, color=MUT,
            family="Consolas")
    for k, (p, bid, ask, _d) in enumerate(lad):
        y = n - 1 - k
        v = bid + ask
        w = HW * v / vmax
        ispoc = k == poc_row
        ax.add_patch(Rectangle((LX - 0.10 - w, y + 0.16), w, 0.62,
                               facecolor=AMB if ispoc else "#c9cdd4",
                               edgecolor="none", zorder=1))
    py = n - 1 - poc_row
    ax.text(LX - 0.10 - HW - 0.12, py + 0.47, "POC ▸", ha="right", va="center",
            fontsize=8.4, color=AMB, fontweight="bold")
    ax.plot([LX, LX + LW], [py + 0.47, py + 0.47], color=AMB, lw=0, zorder=0)
    for i, (p, bid, ask, d) in enumerate(lad):
        y = n - 1 - i
        even = abs(d) <= 2 and (bid + ask) >= 0.35 * vmax
        bg = BLU if even else (GRN if d > 0 else (RED if d < 0 else MUT))
        alpha = 0.62 + 0.38 * min(1.0, abs(d) / max(abs(big[3]), 1)) ** 0.55
        ax.add_patch(Rectangle((LX, y + 0.02), LW, 0.90, facecolor=bg,
                               edgecolor="white", lw=0.6, alpha=alpha, zorder=0))
        if p == big[0]:
            ax.add_patch(Rectangle((LX, y + 0.02), LW, 0.90, facecolor="none",
                                   edgecolor=AMB, lw=1.8, zorder=2))
        for k, v in (("price", f"{p:.2f}"), ("bid", f"{bid:,}"),
                     ("ask", f"{ask:,}"), ("delta", f"{d:+,}")):
            ax.text(X[k], y + 0.47, v, ha="right", fontsize=8.5, color="white",
                    family="Consolas", va="center", zorder=3,
                    fontweight="bold" if k == "delta" else "normal")
        if p in imb:
            # a DOT, colour-coded by side, rather than a text tag
            ax.plot([LX + LW + 0.17], [y + 0.47], marker="o", ms=7,
                    color=DKG if p in set(b["buy_imb"]) else DKR,
                    markeredgecolor="white", markeredgewidth=1.0, zorder=4)

    # Σ row + the delta arithmetic
    sa, sb = sum(r[2] for r in lad), sum(r[1] for r in lad)
    ax.plot([X["bid"] - 0.75, X["ask"]], [-0.30, -0.30], color=MUT, lw=1)
    ax.text(X["bid"], -0.95, f"{sb:,}", ha="right", fontsize=9.5, color=DKR,
            family="Consolas", fontweight="bold")
    ax.text(X["ask"], -0.95, f"{sa:,}", ha="right", fontsize=9.5, color=DKG,
            family="Consolas", fontweight="bold")
    ax.text(X["price"], -0.95, "Σ", ha="right", fontsize=9.5, color=MUT,
            family="Consolas")
    ax.annotate("", xy=(LX + LW + 0.85, -1.75), xytext=(X["ask"] - 0.2, -1.15),
                arrowprops=dict(arrowstyle="->", color=MUT, lw=1.5,
                                connectionstyle="arc3,rad=-0.28"))
    dc = DKG if b["delta"] > 0 else DKR
    ax.text(LX + LW + 1.0, -1.9,
            f"Σask {sa:,}  −  Σbid {sb:,}   =   Δ {b['delta']:+,}",
            fontsize=11.5, color=dc, fontweight="bold", va="center", family="Consolas")
    ax.text(LX + LW + 1.0, -2.65,
            f"{b['eff']:+.1f}% of {b['vol']:,} vol   ·   close at "
            f"{b['close_loc'] * 100:.0f}% of range   ·   POC {b['poc']:.2f}",
            fontsize=9, color=MUT, va="center")

    # ---- callouts, stacked in ladder order, with connector line + DOT --------
    # Callouts sit at the HEIGHT OF THE ROW THEY DESCRIBE. Stacking them in even
    # slots and running long connectors across the chart made the reader trace a
    # line to find out which price a note referred to; putting the text beside its
    # own row removes the question. Only collisions get nudged.
    # ---- imbalance: show WHICH TWO CELLS are being compared -------------------
    # An imbalance is DIAGONAL, not horizontal. A buyer lifting the offer at price P
    # is competing with the bid one tick BELOW, so the test is ask[P] vs bid[P-1].
    # On the early bars we draw the arrow between the exact two cells and spell the
    # arithmetic out, because "◀imb" on its own explains nothing.
    idxmap = {round(p, 2): i for i, (p, *_) in enumerate(lad)}
    EXPLAIN = b["i"] <= 6                                  # teach on the first six
    xb, xa = X["bid"] + 0.12, X["ask"] - 0.64

    def cellbox(xright, y, col, thin):
        ax.add_patch(Rectangle((xright - 0.62, y + 0.06), 0.68, 0.82,
                               facecolor="none", edgecolor=col, lw=1.3,
                               linestyle=":" if thin else "-", zorder=4))

    imb_blocks = []
    for q in b["imb"]:                       # EVERY imbalance, not just the biggest
        i = idxmap[round(q["price"], 2)]
        j = idxmap.get(round(q["other_price"], 2))
        if j is None:
            continue
        thin = q["thin"]
        col = (DKG if q["kind"] == "buy" else DKR)
        y_here, y_other = n - 1 - i + 0.47, n - 1 - j + 0.47
        # box BOTH cells that the test compares, so it is obvious what is measured
        if q["kind"] == "buy":
            cellbox(X["ask"], n - 1 - i, col, thin)      # ask here
            cellbox(X["bid"], n - 1 - j, col, thin)      # bid one tick down
            tail, head_ = (xb, y_other), (xa, y_here)
        else:
            cellbox(X["bid"], n - 1 - i, col, thin)      # bid here
            cellbox(X["ask"], n - 1 - j, col, thin)      # ask one tick up
            tail, head_ = (xa, y_other), (xb, y_here)
        ax.annotate("", xy=head_, xytext=tail,
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.5,
                                    alpha=0.35 if thin else 1.0,
                                    linestyle=":" if thin else "-",
                                    shrinkA=1, shrinkB=1), zorder=5)

    # explain only the best-quality one per side, else the text swamps the chart
    show = []
    for kind in ("buy", "sell"):
        c = [q for q in b["imb"] if q["kind"] == kind and not q["thin"]] or \
            [q for q in b["imb"] if q["kind"] == kind]
        if c:
            show.append(max(c, key=lambda q: q["ratio"] or 999))
    for q in show:
        kind, p, here, other = q["kind"], q["price"], q["here"], q["other"]
        i = idxmap[round(p, 2)]
        ratio, col = q["ratio"], (DKG if kind == "buy" else DKR)
        if EXPLAIN:
            # an empty opposite cell is the strongest form of the signal, but
            # "48 ÷ 0 = 48.0x" is nonsense — say what actually happened
            ratio_line = (f"• {here:,} ÷ {other:,} = {ratio:.1f}× — 3× or more, so it flags"
                          if other else
                          "• the other side is EMPTY (0) — the ratio is undefined")
            other_p = p - 0.25 if kind == "buy" else p + 0.25
            side = "ask" if kind == "buy" else "bid"
            oside = "bid" if kind == "buy" else "ask"
            dirn = "DOWN" if kind == "buy" else "UP"
            why = (f"a buyer lifting the offer at {p:.2f} is\n  competing with the "
                   f"bid just below, not the bid beside it" if kind == "buy" else
                   f"a seller hitting the bid at {p:.2f} is\n  competing with the "
                   f"offer just above")
            txt = (f"{kind.upper()} IMBALANCE at {p:.2f}\n"
                   f"• compares {side} {here:,} HERE ({p:.2f})\n"
                   f"  against {oside} {other:,} ONE TICK {dirn} ({other_p:.2f})\n"
                   f"{ratio_line}\n"
                   f"• why diagonal: {why}")
            # the two honesty caveats, stated on the chart rather than buried
            if q["thin"]:
                txt += (f"\n• BUT the {oside} side is only {other:,} lots — too thin for\n"
                        f"  the ratio to mean much. Weak signal (dotted box).")
            if (kind == "buy") != (q["row_delta"] > 0):
                txt += (f"\n• NOTE row delta is {q['row_delta']:+,} — the OPPOSITE side.\n"
                        f"  Diagonal and horizontal disagree; treat with suspicion.")
            imb_blocks.append((i, txt, col))

    NX = LX + LW + 0.55
    # One block per ROW, not per step: when the path revisits a price (common — a
    # pullback that tests the same tick twice) two identical callouts were drawn
    # stacked on each other. Merge them and carry both numerals.
    groups = {}
    for k, (i, text, col, _tf) in enumerate(ev):
        groups.setdefault(i, []).append((k, text, col))
    blocks = []
    for i, g in groups.items():
        nums = "".join(CIRC[k] for k, _, _ in g)
        head, *rest = g[0][1].split("\n")
        body = "\n".join(rest)
        if len(g) > 1:
            body += f"\n• price returns here at step {CIRC[g[-1][0]]}"
        blocks.append((i, f"{nums} {head}\n{body}", g[0][2]))
    blocks += imb_blocks          # imbalance explainers share the same column

    order = sorted(range(len(blocks)), key=lambda j: blocks[j][0])   # top row first
    heights = {j: (blocks[j][1].count("\n") + 1) * 0.92 + 0.55 for j in range(len(blocks))}
    ytxt, cursor = {}, TOP
    for j in order:                                   # push down off the ideal spot
        row_y = n - 1 - blocks[j][0] + 0.47
        y = min(row_y + heights[j] / 2, cursor)
        ytxt[j] = y
        cursor = y - heights[j]
    if order and ytxt[order[-1]] - heights[order[-1]] < -2.6:   # ran off the bottom
        cursor = -2.6
        for j in reversed(order):                     # then push back up
            y = max(ytxt[j], cursor + heights[j])
            ytxt[j] = y
            cursor = y

    for j, (i, text, col) in enumerate(blocks):
        row_y = n - 1 - i + 0.47
        ax.text(NX + 0.72, ytxt[j], text, fontsize=10.4, color=col,
                va="top", ha="left", linespacing=1.42)
        ax.plot([NX + 0.08, NX + 0.62], [row_y, ytxt[j] - 0.42], color=col,
                lw=1.1, alpha=.75)
        ax.plot([NX + 0.08], [row_y], marker="o", ms=4.5, color=col)

    ax.text(0.30, TOP - 0.35, f"BAR {b['i']}  ·  {b['time']}  ·  ES 1M  ·  Fri 7/17",
            fontsize=14, fontweight="bold", color=INK)
    ax.text(0.30, TOP - 1.25,
            f"O {b['o']:.2f}   H {b['h']:.2f}   L {b['l']:.2f}   C {b['c']:.2f}"
            f"   ·   {n} levels   ·   Δ {b['delta']:+,}",
            fontsize=9.5, color=MUT)

    # ---- internals strip ------------------------------------------------------
    parts = [f"IBS {b['ibs']:.2f}", f"body {b['body_pct']:.0f}%",
             f"wick {b['uw_pct']:.0f}%↑/{b['lw_pct']:.0f}%↓"]
    if b.get("rng_vs_abr"):
        parts.append(f"range {b['rng_vs_abr']}% of ABR(8)")
    if b.get("rvol8"):
        parts.append(f"RVOL {b['rvol8']:.2f}")
    parts += [f"POC at {b['poc_loc']*100:.0f}% of range",
              f"top/bot tick {b['tail_top']:.1f}%/{b['tail_bot']:.1f}% of vol",
              f"biggest print {b['dom_share']:.1f}% of vol"]
    if b["imb"]:
        parts.append(f"{len(b['imb'])} imb ({b['n_imb_thin']} thin)")
    ax.text(0.30, TOP - 2.15, "   ·   ".join(parts), fontsize=8.6, color=INK)

    if b.get("tags"):
        xt = 0.30
        for t in b["tags"]:
            c = (DKR if "absorption-high" in t or "climax" in t else
                 DKG if "absorption-low" in t else
                 AMB if "divergence" in t or "single-print" in t else MUT)
            ax.text(xt, TOP - 3.15, t, fontsize=8.2, color=c, va="center",
                    bbox=dict(boxstyle="round,pad=0.28", facecolor="white",
                              edgecolor=c, lw=0.9))
            xt += 0.16 * len(t) + 0.55

    # legend — what the dots mean and what the imbalance test actually computes
    if show:
        ax.plot([0.42], [-1.55], marker="o", ms=7, color=DKG,
                markeredgecolor="white", markeredgewidth=1.0)
        ax.text(0.62, -1.55, "buy imbalance:  ask[P] ÷ bid[P−1 tick] ≥ 3",
                fontsize=8.6, color=DKG, va="center")
        ax.plot([0.42], [-2.20], marker="o", ms=7, color=DKR,
                markeredgecolor="white", markeredgewidth=1.0)
        ax.text(0.62, -2.20, "sell imbalance:  bid[P] ÷ ask[P+1 tick] ≥ 3",
                fontsize=8.6, color=DKR, va="center")
        ax.text(0.62, -2.85, "boxes = the two cells compared · dotted = diagonal cell "
                             "under 20 lots, ratio unreliable",
                fontsize=8.2, color=MUT, va="center")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"bar_{b['i']:02d}_{b['time'].replace(':', '')}.png"
    fig.savefig(out, dpi=105, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    return out


def main():
    bars = json.loads(SRC.read_text(encoding="utf-8"))
    sr = json.loads((ROOT / "data" / "footprint" / "ES_1m_sr.json").read_text(encoding="utf-8"))
    only = None
    import sys
    if len(sys.argv) > 1:
        only = {int(x) for x in sys.argv[1].split(",")}
    for b in bars:
        if only and b["i"] not in only:
            continue
        render(b, bars, sr)
    print(f"rendered {len(bars)} bars -> {OUTDIR}")


if __name__ == "__main__":
    main()
