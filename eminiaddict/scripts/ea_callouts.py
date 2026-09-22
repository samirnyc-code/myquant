"""ea_callouts.py — overlay BIG readable fib labels on his settled ES frame. Robust placement:
OCR the right price-axis tags ($7547.86, $7521.88, ...) to get each level's exact y, then draw
color-coded callouts (red/yellow levels, green target) in the empty right zone with leaders to
the line. De-collided so nothing overlaps; marks where the 50% traded.

Usage: python ea_callouts.py <MMDDYY>   (uses the OCR-identified ES 4h frame + the ES ladder)
"""
import json
import os
import sys

import numpy as np
import pytesseract
from PIL import Image, ImageOps
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")
COL = {"red": "#f85149", "yellow": "#f5c518", "green": "#3fb950", "": "#e6edf3"}


def axis_prices(pil_img, W, H):
    """OCR the right price-axis strip -> list of (price_float, y_center_in_original_px)."""
    x0 = int(W * 0.945)
    strip = pil_img.convert("L").crop((x0, 0, W, H))
    scale = 3
    strip = strip.resize((strip.width * scale, strip.height * scale), Image.LANCZOS)
    strip = ImageOps.autocontrast(strip)
    data = pytesseract.image_to_data(strip, config="--psm 6",
                                     output_type=pytesseract.Output.DICT)
    out = []
    for i, txt in enumerate(data["text"]):
        t = txt.replace("$", "").replace(",", "").strip()
        try:
            v = float(t)
        except ValueError:
            continue
        if 5000 < v < 9000:
            y = (data["top"][i] + data["height"][i] / 2) / scale
            out.append((v, y))
    return out


def nearest_y(prices, target, tol=3.0):
    best, bd = None, 1e9
    for v, y in prices:
        if abs(v - target) < bd:
            bd, best = abs(v - target), y
    return best if bd <= tol else None


def annotate(mmddyy):
    d = os.path.join(DAILY, mmddyy)
    es = json.load(open(os.path.join(d, "report.json"), encoding="utf-8")).get("es", {})
    ladder = es.get("ladder", [])
    if not ladder:
        print(f"{mmddyy}: no ES ladder"); return
    frames = json.load(open(os.path.join(d, "frames", "frames.json"), encoding="utf-8"))
    fr = next((f for f in frames if f.get("instrument") == "ES" and f.get("tf") == "4h"), None)
    if not fr:
        print(f"{mmddyy}: no OCR-identified ES 4h frame"); return
    fp = os.path.join(d, "frames", fr["file"])
    pil = Image.open(fp)
    W, H = pil.size
    prices = axis_prices(pil, W, H)
    if len(prices) < 2:
        print(f"{mmddyy}: axis OCR found too few prices ({len(prices)})"); return

    im = mpimg.imread(fp)
    fig, ax = plt.subplots(figsize=(16, 9), facecolor="#0b0b0b")
    ax.imshow(im); ax.axis("off")
    lead_x = W * 0.94
    label_x = W * 0.78
    # linear fit price<->y from the axis tags (so any level the OCR misses is still placed)
    pv_list, y_list = [], []
    fit = None
    for pct, price, role, color, note in ladder:
        try:
            pv = float(str(price).replace(",", ""))
        except ValueError:
            continue
        y = nearest_y(prices, pv)
        if y is not None:
            pv_list.append(pv); y_list.append(y)
    if len(pv_list) >= 2:
        fit = np.polyfit(pv_list, y_list, 1)     # y = fit[0]*price + fit[1]
    # gather callouts (matched y, else fitted y)
    items = []
    for pct, price, role, color, note in ladder:
        try:
            pv = float(str(price).replace(",", ""))
        except ValueError:
            continue
        y = nearest_y(prices, pv)
        if y is None and fit is not None:
            y = float(np.polyval(fit, pv))
        if y is None:
            continue
        items.append((y, f"{pct}  {price}  {role}", COL.get(color, "#e6edf3")))
    if not items:
        print(f"{mmddyy}: no ladder prices matched the axis"); return
    items.sort(key=lambda t: t[0])
    min_gap = H * 0.05
    lys = []
    for ty, _, _ in items:
        lys.append(ty if not lys else max(ty, lys[-1] + min_gap))
    for (ty, txt, col), ly in zip(items, lys):
        ax.annotate(txt, (lead_x, ty), xytext=(label_x, ly), color=col, fontsize=15,
                    fontweight="bold", va="center", ha="right",
                    arrowprops=dict(arrowstyle="->", color=col, lw=2.2),
                    bbox=dict(boxstyle="round,pad=0.35", fc="#0b0f14", ec=col, lw=1.8))
    # mark where the 50% traded (candle touching the 50% y)
    y50 = nearest_y(prices, float(str(next((l[1] for l in ladder if l[0] == "50%"), "0"))
                                  .replace(",", "")))
    if y50:
        yy = int(y50)
        arr = im if im.max() > 1 else im
        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        rr, gg, bb = r[yy - 3:yy + 4], g[yy - 3:yy + 4], b[yy - 3:yy + 4]
        mx = 1.0 if arr.max() <= 1 else 255.0
        candle = ((rr > 0.45 * mx) & (gg < 0.5 * mx) & (bb < 0.5 * mx)) | \
                 ((gg > 0.45 * mx) & (rr < 0.5 * mx) & (bb < 0.5 * mx))
        xs = np.where(candle.any(axis=0)[:int(W * 0.72)])[0]
        xs = xs[xs > W * 0.05]
        if len(xs):
            xt = int(xs[-1])
            ax.annotate("50% traded here", (xt, yy), xytext=(xt, yy - H * 0.11),
                        color="#f5c518", fontsize=13, fontweight="bold", ha="center",
                        arrowprops=dict(arrowstyle="->", color="#f5c518", lw=2.4),
                        bbox=dict(boxstyle="round,pad=0.3", fc="#0b0f14", ec="#f5c518", lw=1.6))
    ax.set_title(f"ES {es.get('tf','4-hour')} — his fib, labeled", color="#eee", fontsize=13,
                 loc="left")
    out = os.path.join(d, "frames", os.path.splitext(fr["file"])[0] + "_annot.png")
    fig.tight_layout(); fig.savefig(out, dpi=120, facecolor="#0b0b0b"); plt.close(fig)
    print(f"{mmddyy}: wrote {os.path.relpath(out, ROOT)}  (axis prices matched: "
          f"{len(items)}/{len(ladder)})")


if __name__ == "__main__":
    for m in sys.argv[1:]:
        annotate(m)
