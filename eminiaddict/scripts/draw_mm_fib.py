"""Draw an ES daily chart with a Halsey Measured-Move Fib on the dominant recent leg.

Halsey MM levels (Ch2 / Fig 6.1), for an UP leg from swing low L to swing high H
(range R = H - L):
    100%  = L            (start of move)
     61.8% = L + 0.382*R (FAILURE line - breach invalidates the MM)
     50%  = L + 0.500*R  (HWB / half-way-back = entry-continuation zone)
      0%  = H            (end of move)
    123.6% = H + 0.236*R (measured-move PROFIT TARGET; also seeds next swing)
Down leg is the mirror (100%=H, 0%=L, target below L).

Seed swing = last completed leg from a ZigZag pivot detector (proxy for Halsey's
"significant high-low that jumps off the page"). ZigZag threshold in %.
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PARQUET = "../../data/bars/_db_es_daily_24h.parquet"
OUT = "../figures/es_daily_mm_fib_{mode}.png"
WINDOW = 170          # bars to display
ZZ_PCT = 4.0          # ZigZag reversal threshold (%)
FONT_SCALE = 1.25     # global text scale (env EA_FONT_SCALE overrides)
FONT_SCALE = float(os.environ.get("EA_FONT_SCALE", FONT_SCALE))
LABEL_FS = 12.5 * FONT_SCALE   # right-margin level labels
TICK_FS = 10.5 * FONT_SCALE    # axis tick labels
TITLE_FS = 12.5 * FONT_SCALE   # title


def zigzag(highs, lows, pct):
    """Return list of (index, price, kind) pivots. kind='H' or 'L'."""
    thr = pct / 100.0
    piv = []
    # seed with first bar as tentative low and high
    last_ext_i = 0
    last_ext_p = lows[0]
    direction = 0  # +1 up (seeking high), -1 down (seeking low), 0 unknown
    ref_hi_i, ref_hi_p = 0, highs[0]
    ref_lo_i, ref_lo_p = 0, lows[0]
    for i in range(1, len(highs)):
        if highs[i] > ref_hi_p:
            ref_hi_p, ref_hi_i = highs[i], i
        if lows[i] < ref_lo_p:
            ref_lo_p, ref_lo_i = lows[i], i
        if direction >= 0:  # seeking a high; watch for reversal down
            if ref_hi_p - lows[i] >= thr * ref_hi_p and ref_hi_i != last_ext_i:
                piv.append((ref_hi_i, ref_hi_p, 'H'))
                direction = -1
                last_ext_i, last_ext_p = ref_hi_i, ref_hi_p
                ref_lo_p, ref_lo_i = lows[i], i
        if direction <= 0:  # seeking a low; watch for reversal up
            if highs[i] - ref_lo_p >= thr * ref_lo_p and ref_lo_i != last_ext_i:
                piv.append((ref_lo_i, ref_lo_p, 'L'))
                direction = 1
                last_ext_i, last_ext_p = ref_lo_i, ref_lo_p
                ref_hi_p, ref_hi_i = highs[i], i
    return piv


def main():
    df = pd.read_parquet(PARQUET).reset_index(drop=True)
    df = df.tail(WINDOW).reset_index(drop=True)
    highs = df["High"].values
    lows = df["Low"].values
    closes = df["Close"].values
    n = len(df)

    piv = zigzag(highs, lows, ZZ_PCT)
    if len(piv) < 2:
        raise SystemExit("not enough pivots; lower ZZ_PCT")

    mode = sys.argv[1] if len(sys.argv) > 1 else "last"
    if mode == "dominant":
        # seed = the completed pivot-to-pivot leg with the largest price range
        legs = [(piv[j], piv[j + 1]) for j in range(len(piv) - 1)]
        (a, b) = max(legs, key=lambda lg: abs(lg[1][1] - lg[0][1]))
        (i0, p0, k0), (i1, p1, k1) = a, b
    else:
        # seed swing = last completed leg (second-to-last pivot -> last pivot)
        (i0, p0, k0), (i1, p1, k1) = piv[-2], piv[-1]
    up = k1 == 'H'  # leg goes low->high
    # snap anchors to the TRUE extreme lows/highs within the leg span (+small pad)
    lo_i, hi_i = sorted((i0, i1))
    pad = 6
    a0, b0 = max(0, lo_i - pad), min(n - 1, hi_i + pad)
    seg = df.iloc[a0:b0 + 1]
    lo_idx = int(seg["Low"].idxmin())
    hi_idx = int(seg["High"].idxmax())
    if up:
        i0, p0 = lo_idx, df.Low[lo_idx]
        i1, p1 = hi_idx, df.High[hi_idx]
    else:
        i0, p0 = hi_idx, df.High[hi_idx]
        i1, p1 = lo_idx, df.Low[lo_idx]
    L, H = (p0, p1) if up else (p1, p0)
    R = H - L

    def lvl(frac_from_start):
        # frac measured as retracement fraction; price at that fib level
        if up:
            # 100%=L start, 0%=H end
            return L + (1 - frac_from_start) * R
        else:
            return H - (1 - frac_from_start) * R

    # explicit levels
    lv100 = L if up else H
    lv0 = H if up else L
    hwb = L + 0.5 * R if up else H - 0.5 * R
    fail = L + 0.382 * R if up else H - 0.382 * R
    tgt = H + 0.236 * R if up else L - 0.236 * R

    # ---- plot ----
    plt.rcParams.update({"font.size": 10})
    fig, ax = plt.subplots(figsize=(15, 9), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    up_c, dn_c = "#26a65b", "#e2453c"
    w = 0.6
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = up_c if c >= o else dn_c
        ax.plot([i, i], [l, h], color=col, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((i - w / 2, min(o, c)), w, abs(c - o) or 0.01,
                               facecolor=col, edgecolor=col, zorder=3))

    # EMAs (generic trend context, not Halsey's exact params)
    ema9 = pd.Series(closes).ewm(span=9).mean()
    ema20 = pd.Series(closes).ewm(span=20).mean()
    ax.plot(range(n), ema9, color="#4aa3ff", lw=1.0, alpha=.8, label="EMA 9")
    ax.plot(range(n), ema20, color="#dddddd", lw=1.0, alpha=.6, label="EMA 20")

    # swing anchor line
    ax.plot([i0, i1], [p0, p1], color="#888", ls="--", lw=1.2, zorder=4)
    ax.scatter([i0, i1], [p0, p1], color="#ffd400", s=60, zorder=6)

    # fib lines — STOP at the last bar (x=n) so nothing is drawn through the
    # right-margin labels. Lines start at the anchor bar i0.
    xr = n - 1
    LINE_END = n - 0.5   # right edge of the plotted lines; labels live beyond this
    for y, color, lw, ls in [
        (lv100, "#bbbbbb", 1.2, ":"), (fail, "#e2453c", 1.6, "-"),
        (hwb, "#ffd400", 1.6, "-"), (lv0, "#bbbbbb", 1.2, ":"),
        (tgt, "#26a65b", 2.0, "-"),
    ]:
        ax.plot([i0, LINE_END], [y, y], color=color, lw=lw, ls=ls, zorder=5)
    ax.plot([0, LINE_END], [closes[-1], closes[-1]], color="#4aa3ff", lw=0.8,
            ls="--", alpha=.5, zorder=5)

    # right-margin labels — bigger fonts + collision avoidance (never overlap)
    labels = [
        {"y": lv100, "c": "#bbbbbb", "t": f"100% (start)  {lv100:,.2f}"},
        {"y": fail, "c": "#e2453c", "t": f"61.8% FAILURE  {fail:,.2f}"},
        {"y": hwb, "c": "#ffd400", "t": f"50% HWB (entry)  {hwb:,.2f}"},
        {"y": lv0, "c": "#bbbbbb", "t": f"0% (end)  {lv0:,.2f}"},
        {"y": tgt, "c": "#26a65b", "t": f"123.6% TARGET  {tgt:,.2f}"},
        {"y": closes[-1], "c": "#4aa3ff", "t": f"last  {closes[-1]:,.2f}"},
    ]
    lo = min(lows.min(), min(d["y"] for d in labels))
    hi = max(highs.max(), max(d["y"] for d in labels))
    span = hi - lo
    ax.set_ylim(lo - 0.03 * span, hi + 0.06 * span)
    ymin_l, ymax_l = ax.get_ylim()
    gap = 0.046 * span * FONT_SCALE           # min vertical spacing between label texts
    labels.sort(key=lambda d: d["y"])
    for d in labels:
        d["ty"] = d["y"]
    for k in range(1, len(labels)):           # push up to enforce the gap
        if labels[k]["ty"] - labels[k - 1]["ty"] < gap:
            labels[k]["ty"] = labels[k - 1]["ty"] + gap
    over = labels[-1]["ty"] - (ymax_l - 0.01 * span)   # if stack overflows top, slide down
    if over > 0:
        for d in labels:
            d["ty"] -= over
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1]["ty"] - labels[k]["ty"] < gap:
                labels[k]["ty"] = labels[k + 1]["ty"] - gap
    for d in labels:                                    # leader from line-end to label
        ax.plot([LINE_END, n + 1.4], [d["y"], d["ty"]], color=d["c"], lw=0.7,
                alpha=.6, zorder=4, clip_on=False)
        ax.text(n + 2.2, d["ty"], d["t"], color=d["c"], va="center",
                fontsize=LABEL_FS, fontweight="bold", clip_on=False)

    dir_txt = "LONG (up leg, drawn low→high)" if up else "SHORT (down leg, drawn high→low)"
    d0 = df.DateTime[i0].strftime("%Y-%m-%d")
    d1 = df.DateTime[i1].strftime("%Y-%m-%d")
    ax.set_title(
        f"ES daily — Halsey Measured Move  |  seed swing {dir_txt}\n"
        f"{d0}  {p0:,.2f}  →  {d1}  {p1:,.2f}   (range {R:,.2f} pts,  ZigZag {ZZ_PCT}%)",
        color="#eee", fontsize=TITLE_FS, loc="left")

    # x ticks as dates
    step = max(1, n // 12)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([df.DateTime[i].strftime("%m/%d/%y") for i in range(0, n, step)],
                       color="#aaa", rotation=0, fontsize=TICK_FS)
    ax.tick_params(colors="#aaa", labelsize=TICK_FS)
    for s in ax.spines.values():
        s.set_color("#333")
    ax.set_xlim(-1, n + 30)
    ax.grid(True, color="#1c1c1c", lw=0.5)
    ax.legend(loc="upper left", facecolor="#111", edgecolor="#333", labelcolor="#ccc")
    fig.tight_layout()
    fig.savefig(OUT.format(mode=mode), dpi=130, facecolor=fig.get_facecolor())
    print("wrote", OUT.format(mode=mode))
    print(f"seed leg: {'UP' if up else 'DOWN'}  L={L:,.2f} H={H:,.2f} R={R:,.2f}")
    print(f"100%={lv100:,.2f} 61.8%(fail)={fail:,.2f} 50%(HWB)={hwb:,.2f} "
          f"0%={lv0:,.2f} 123.6%(target)={tgt:,.2f}  last={closes[-1]:,.2f}")


if __name__ == "__main__":
    main()
