"""flip_chart_render.py — render the flip setup from ticks, exact deployed indicator (S119).

Reproduces TempoSpeedometer.SimFlipSession (SE entry, SeOrderLifeBars, 3R target,
SAR, EB opposite-IBS scratch on the signal bar, min SB body, doji guard) on the 2000t
engine bars and draws a candlestick chart with the setup overlay, so it can be put
next to the live NT chart.

    python tempo/scripts/flip_chart_render.py 2026-09-14 09:45 10:25
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
MINBODY = 4
LIFE = 1
RRT = 3          # chart renders a 3R target


def bardir(o, h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    x = (c[i] - l[i]) / rg
    return 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)


def flipdir(o, h, l, c, cx, i):
    if i < 1 or not cx[i] or not cx[i - 1]:
        return 0
    if abs(c[i - 1] - o[i - 1]) < TICK / 2:            # bar1 doji
        return 0
    if abs(c[i] - o[i]) < MINBODY * TICK - TICK / 2:   # SB body
        return 0
    d1 = 1 if c[i - 1] >= o[i - 1] else -1
    d2 = bardir(o, h, l, c, i)
    if d2 == 0 or d1 == d2:
        return 0
    return 1 if d1 == 1 else 2                          # 1 short, 2 long


def sim(o, h, l, c, cx, n):
    """port of SimFlipSession (SE, life, 3R, SAR, EB scratch on signal bar).
    returns list of dicts describing each signal + outcome for rendering."""
    out = []
    pi = -1; pSig = -1; pSh = False; en = st = rk = tg = 0.0
    qSig = -1; qSh = False; qEn = qSt = 0.0
    for i in range(1, n):
        if pi >= 0:
            hs = (h[i] >= st) if pSh else (l[i] <= st)
            ht = (l[i] <= tg) if pSh else (h[i] >= tg)
            if hs:
                out.append({"sig": pSig, "sh": pSh, "res": "Xstop", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
            elif ht:
                out.append({"sig": pSig, "sh": pSh, "res": "OK 3R", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
            elif i == pi + 1:
                d = bardir(o, h, l, c, i)
                if (not cx[i]) and ((pSh and d == 1) or (not pSh and d == -1)):
                    out.append({"sig": pSig, "sh": pSh, "res": "eb-scr", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
        if qSig >= 0 and pi < 0:
            if i > qSig + LIFE:
                out.append({"sig": qSig, "sh": qSh, "res": "no-fill", "end": i - 1, "en": qEn, "st": qSt, "tg": None, "fill": -1}); qSig = -1
            else:
                inval = (h[i] >= qSt) if qSh else (l[i] <= qSt)
                trig = (l[i] <= qEn - TICK) if qSh else (h[i] >= qEn + TICK)
                if trig:
                    pi = i; pSig = qSig; pSh = qSh; en = qEn; st = qSt; rk = abs(en - st)
                    sg = -1 if pSh else 1
                    tg = en + sg * RRT * rk; qSig = -1
                    if inval:
                        out.append({"sig": pSig, "sh": pSh, "res": "Xstop", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
                    else:
                        ht0 = (l[i] <= tg) if pSh else (h[i] >= tg)
                        if ht0:
                            out.append({"sig": pSig, "sh": pSh, "res": "OK 3R", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
                elif inval:
                    out.append({"sig": qSig, "sh": qSh, "res": "canc", "end": i, "en": qEn, "st": qSt, "tg": None, "fill": -1}); qSig = -1
                elif i == qSig + 1:
                    d = bardir(o, h, l, c, i)
                    if (not cx[i]) and ((qSh and d == 1) or (not qSh and d == -1)):
                        out.append({"sig": qSig, "sh": qSh, "res": "eb-canc", "end": i, "en": qEn, "st": qSt, "tg": None, "fill": -1}); qSig = -1
        fd = flipdir(o, h, l, c, cx, i)
        if fd == 0:
            continue
        sh = fd == 1
        if pi >= 0:
            if sh != pSh:
                out.append({"sig": pSig, "sh": pSh, "res": "rev", "end": i, "en": en, "st": st, "tg": tg, "fill": pi}); pi = -1
            else:
                continue
        if qSig >= 0:
            out.append({"sig": qSig, "sh": qSh, "res": "no-fill", "end": i, "en": qEn, "st": qSt, "tg": None, "fill": -1}); qSig = -1
        h2 = max(h[i - 1], h[i]); l2 = min(l[i - 1], l[i])
        e2 = (l[i] - TICK) if sh else (h[i] + TICK)
        s2 = (h2 + TICK) if sh else (l2 - TICK)
        if abs(e2 - s2) < TICK:
            continue
        qSig = i; qSh = sh; qEn = e2; qSt = s2
    if pi >= 0:
        out.append({"sig": pSig, "sh": pSh, "res": "open", "end": n - 1, "en": en, "st": st, "tg": tg, "fill": pi})
    if qSig >= 0:
        out.append({"sig": qSig, "sh": qSh, "res": "no-fill", "end": n - 1, "en": qEn, "st": qSt, "tg": None, "fill": -1})
    return out


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-09-14"
    t0 = sys.argv[2] if len(sys.argv) > 2 else "09:45"
    t1 = sys.argv[3] if len(sys.argv) > 3 else "10:25"
    # price offset to display RAW contract prices (trove is back-adjusted continuous;
    # ESZ6 spliced -67.75 vs the ESU6 anchor, so raw 12-26 = continuous + 67.75)
    off = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    df = pd.read_parquet(ENG)
    d = df[df["date"] == date].sort_values("bar").reset_index(drop=True)
    d["hhmm"] = pd.to_datetime(d["start"]).dt.strftime("%H:%M:%S")
    o = d["open"].to_numpy() + off; h = d["high"].to_numpy() + off
    l = d["low"].to_numpy() + off; c = d["close"].to_numpy() + off
    cx = d["climax"].to_numpy().astype(bool)
    tp = d["tpct"].to_numpy()
    sigs = sim(o, h, l, c, cx, len(d))

    lo = d.index[d["hhmm"] >= t0].min()
    hi = d.index[d["hhmm"] <= t1 + ":99"].max()
    lo = 0 if pd.isna(lo) else int(lo); hi = len(d) - 1 if pd.isna(hi) else int(hi)

    fig, ax = plt.subplots(figsize=(15, 8))
    for i in range(lo, hi + 1):
        up = c[i] >= o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=1, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), TICK / 2),
                               facecolor=col, edgecolor=col, zorder=3))
        if cx[i]:
            ax.add_patch(Rectangle((i - 0.36, l[i]), 0.72, h[i] - l[i], fill=False,
                                   edgecolor="gold", lw=1.8, zorder=4))
        ax.text(i, l[i] - (h.max() - l.min()) * 0.012, f"{tp[i]:.0f}", ha="center",
                va="top", fontsize=6, color="gold" if cx[i] else "#888")

    for s in sigs:
        sig = s["sig"]
        if sig < lo - 1 or sig > hi + 1:
            continue
        box_l = min(l[sig - 1], l[sig]); box_h = max(h[sig - 1], h[sig])
        ax.add_patch(Rectangle((sig - 1 - 0.42, box_l), 1.84, box_h - box_l, fill=False,
                               edgecolor="#e8c000", lw=1.3, ls="--", zorder=5))
        side = "SHORT" if s["sh"] else "LONG"
        endx = min(s["end"], hi)
        ax.hlines(s["en"], sig - 0.4, endx + 0.4, color="#dddddd", lw=1.3, zorder=6)
        ax.hlines(s["st"], sig - 0.4, endx + 0.4, color="#ef5350", lw=1.2, zorder=6)
        if s["tg"] is not None:
            ax.hlines(s["tg"], sig - 0.4, endx + 0.4, color="#26a69a", lw=1.2, ls=":", zorder=6)
        tagcol = {"OK 3R": "#26a69a", "Xstop": "#ef5350", "rev": "#6fa8ff",
                  "eb-scr": "#6fa8ff", "no-fill": "#999", "canc": "#999",
                  "eb-canc": "#999", "open": "#dddddd"}.get(s["res"], "#dddddd")
        ax.text(sig + 0.5, s["en"], f" {side} {s['res']}"
                + ("" if s["fill"] < 0 else f" @{s['en']:.2f}"),
                color=tagcol, fontsize=9, va="bottom", zorder=7, weight="bold")

    ax.set_xlim(lo - 1, hi + 2)
    ys = l[lo:hi + 1].min(); yl = h[lo:hi + 1].max(); pad = (yl - ys) * 0.08
    ax.set_ylim(ys - pad, yl + pad)
    step = max(1, (hi - lo) // 18)
    ax.set_xticks(range(lo, hi + 1, step))
    ax.set_xticklabels([d["hhmm"].iloc[i][:5] for i in range(lo, hi + 1, step)], rotation=0, fontsize=8)
    ax.set_title(f"ES 2000t — {date}  {t0}-{t1}  (python port of deployed flip indicator: "
                 f"SE entry, life {LIFE}, 3R, SAR, EB-scr; gold=climax, num=tempo pct)", fontsize=10)
    ax.set_facecolor("#0e0e12"); fig.patch.set_facecolor("#0e0e12")
    ax.tick_params(colors="#aaa"); ax.title.set_color("#ddd")
    for sp in ax.spines.values():
        sp.set_color("#333")
    fig.tight_layout()
    p = OUT / f"flip_chart_{date}_{t0.replace(':','')}_{t1.replace(':','')}.png"
    fig.savefig(p, dpi=130, facecolor=fig.get_facecolor())
    print("saved", p)
    # print the setups in-window for the reply
    print(f"\nsetups touching {t0}-{t1}:")
    for s in sigs:
        if lo - 1 <= s["sig"] <= hi + 1:
            st = d["hhmm"].iloc[s["sig"]]
            fillt = "" if s["fill"] < 0 else f" fill@{d['hhmm'].iloc[s['fill']]} {s['en']:.2f}"
            print(f"  SB {st}  {'SHORT' if s['sh'] else 'LONG'}  {s['res']}"
                  f"  stop {s['st']:.2f}{fillt}")


if __name__ == "__main__":
    main()
