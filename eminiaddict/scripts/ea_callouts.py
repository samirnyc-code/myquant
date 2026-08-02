"""ea_callouts.py — annotate his settled ES chart frame with smart callouts: label each fib
level (color-matched) with a leader to the line, and mark WHERE the 50% traded — placed in the
empty right/left zones so nothing overlaps the candles or his own labels.

Calibration: detect his YELLOW (50%) and GREEN (-23.6% target) horizontal lines (both unique,
known prices from the report's ES ladder) -> linear price<->y map -> place every level exactly.

Usage: python ea_callouts.py <MMDDYY>   (reads report ES ladder + the ES-tf2 settled frame)
Output: frames/<orig>_annot.png  (referenced by the page generator)
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")
COL = {"red": "#f85149", "yellow": "#e3b341", "green": "#3fb950", "": "#c9d1d9"}


def _rows(mask, thr):
    frac = mask.mean(axis=1)
    ys = np.where(frac > thr)[0]
    return int(ys.mean()) if len(ys) else None


def annotate(mmddyy):
    d = os.path.join(DAILY, mmddyy)
    rep = json.load(open(os.path.join(d, "report.json"), encoding="utf-8"))
    es = rep.get("es", {})
    ladder = es.get("ladder", [])
    anchors = es.get("anchors", [])
    if not ladder:
        print(f"{mmddyy}: no ES ladder"); return
    # pick the ES 4h settled frame (topic ES-tf2, else ES)
    frames = json.load(open(os.path.join(d, "frames", "frames.json"), encoding="utf-8"))
    pick = next((f for f in frames if f["topic"] == "ES-tf2"), None) or \
        next((f for f in frames if f["topic"] == "ES"), None)
    if not pick:
        print(f"{mmddyy}: no ES frame"); return
    fp = os.path.join(d, "frames", pick["file"])
    im = mpimg.imread(fp)
    if im.max() > 1:
        im = im / 255.0
    H, W = im.shape[:2]
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    xr = int(W * 0.55)      # fib lines live in the right portion of the chart only
    ry, gy, by = r[:, xr:], g[:, xr:], b[:, xr:]
    y_yellow = _rows((ry > 0.6) & (gy > 0.5) & (by < 0.45), 0.25)
    y_green = _rows((gy > 0.5) & (ry < 0.55) & (by < 0.55), 0.05)
    # prices for calibration from the ladder
    pr = {p[0]: float(str(p[1]).replace(",", "")) for p in ladder}
    p_yellow = pr.get("50%"); p_green = pr.get("-23.6%")
    if not (y_yellow and y_green and p_yellow and p_green):
        print(f"{mmddyy}: calibration lines not found (yellow={y_yellow}, green={y_green})"); return
    # linear price(y): price = a*y + c
    a = (p_green - p_yellow) / (y_green - y_yellow)
    c = p_yellow - a * y_yellow

    def y_of(price):
        return (price - c) / a

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="#0b0b0b")
    ax.imshow(im); ax.axis("off")
    lead_x = W * 0.955       # his level lines run to the right edge
    label_x = W * 0.80       # labels sit in the empty future zone (right of the last candle)
    # collect ladder items by true y, then de-collide the label y-positions
    items = []
    for pct, price, role, color, note in ladder:
        try:
            pv = float(str(price).replace(",", ""))
        except ValueError:
            continue
        items.append((y_of(pv), f"{pct}  {price}  {role}", COL.get(color, "#c9d1d9")))
    items.sort(key=lambda t: t[0])
    min_gap = H * 0.045
    lys = []
    for ty, _, _ in items:
        ly = ty if not lys else max(ty, lys[-1] + min_gap)
        lys.append(ly)
    for (ty, txt, col), ly in zip(items, lys):
        ax.annotate(txt, (lead_x, ty), xytext=(label_x, ly),
                    color=col, fontsize=12.5, fontweight="bold", va="center", ha="right",
                    arrowprops=dict(arrowstyle="->", color=col, lw=1.7,
                                    connectionstyle="arc3,rad=0.0"),
                    bbox=dict(boxstyle="round,pad=0.3", fc="#0b0f14", ec=col, lw=1.4))
    # anchors (100% / 0%) as smaller tags on the left empty band
    for pct, price, note in anchors:
        try:
            pv = float(str(price).replace(",", ""))
        except ValueError:
            continue
        y = y_of(pv)
        ax.annotate(f"{pct} anchor {price}", (W * 0.02, y), color="#c9d1d9", fontsize=10,
                    va="center", ha="left",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#0b0f14", ec="#484f58", lw=1))
    # mark where the 50% traded: rightmost candle column touching y_yellow
    yy = int(y_yellow)
    rr, gg, bb = r[yy - 3:yy + 4], g[yy - 3:yy + 4], b[yy - 3:yy + 4]
    candle = ((rr > 0.45) & (gg < 0.5) & (bb < 0.5)) | ((gg > 0.45) & (rr < 0.5) & (bb < 0.5))
    band = candle.any(axis=0)
    xs = np.where(band[:int(W * 0.78)])[0]
    xs = xs[xs > W * 0.05]
    if len(xs):
        xt = int(xs[-1])
        ax.annotate("50% traded here", (xt, yy), xytext=(xt, yy - H * 0.10),
                    color="#e3b341", fontsize=11, fontweight="bold", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#e3b341", lw=2),
                    bbox=dict(boxstyle="round,pad=0.3", fc="#0b0f14", ec="#e3b341", lw=1.4))
    ax.set_title(f"ES {es.get('tf','')} — his settled fib (callouts added)", color="#eee",
                 fontsize=13, loc="left")
    out = os.path.join(d, "frames", os.path.splitext(pick["file"])[0] + "_annot.png")
    fig.tight_layout(); fig.savefig(out, dpi=120, facecolor="#0b0b0b"); plt.close(fig)
    print(f"{mmddyy}: wrote {os.path.relpath(out, ROOT)}  (yellow y={y_yellow}, green y={y_green})")


if __name__ == "__main__":
    for m in sys.argv[1:]:
        annotate(m)
