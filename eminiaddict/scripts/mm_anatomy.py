"""Render the FULL anatomy of Halsey measured-move sequences: every impulse leg
drawn as its own Fib (50 HWB / 61.8 fail / 123.6 target), classified by OUTCOME as
TRADITIONAL (hit target), EXTENSION (began beyond prior target), or FAILURE (pierced
61.8%, didn't work), plus the macro leg's ATWHWB and where price went after.

Batch (library): python mm_anatomy.py batch [5m|15m|1D] [years]  -> figures/sequences/
Single (debug):  python mm_anatomy.py [tf] [seq_index | start end]
"""
import json
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import find_mm_trades as F
import sequence_lib as S

OUTDIR = "../figures/sequences"
FONT_SCALE = float(os.environ.get("EA_FONT_SCALE", 1.15))
FS = 11 * FONT_SCALE
TYc = {"TRAD": "#4aa3ff", "EXT": "#c77dff", "FAIL": "#f85149", "WEAK": "#586070"}


def fib(lo, hi, up):
    R = hi - lo
    if up:
        return dict(start=lo, fail=lo + .382 * R, hwb=lo + .5 * R, d382=lo + .618 * R,
                    end=hi, tgt=hi + .236 * R, R=R)
    return dict(start=hi, fail=hi - .382 * R, hwb=hi - .5 * R, d382=hi - .618 * R,
                end=lo, tgt=lo - .236 * R, R=R)


def build_mms(win, micro_pct):
    H = win["High"].values; L = win["Low"].values
    piv = F.zigzag(H, L, micro_pct)
    if len(piv) < 3:
        return None
    up_trend = win.Close.iloc[len(win) // 2:].mean() >= win.Close.iloc[:len(win) // 2].mean()
    mms, prev_tgt = [], None
    for k in range(len(piv) - 1):
        (a, pa, ka), (b, pb, kb) = piv[k], piv[k + 1]
        up = (ka == 'L' and kb == 'H')
        if up != up_trend:
            continue
        lo, hi = (pa, pb) if up else (pb, pa)
        fb = fib(lo, hi, up)
        pull = piv[k + 2][1] if k + 2 < len(piv) else None
        seg = win.iloc[b:min(len(win), b + 40)]
        reached = ((up and seg.High.max() >= fb["tgt"]) or
                   ((not up) and seg.Low.min() <= fb["tgt"])) if len(seg) else False
        pierced = pull is not None and (
            (up and pull < fb["fail"]) or ((not up) and pull > fb["fail"]))
        typ = "TRAD" if reached else ("FAIL" if pierced else "WEAK")
        if typ == "TRAD" and prev_tgt is not None:
            if (up and lo >= prev_tgt - 0.05 * fb["R"]) or \
               ((not up) and hi <= prev_tgt + 0.05 * fb["R"]):
                typ = "EXT"
        mms.append({"a": a, "b": b, "next": (piv[k + 2][0] if k + 2 < len(piv) else b + 6),
                    "up": up, "typ": typ, "reached": reached, **fb})
        prev_tgt = fb["tgt"]
    return {"up_trend": up_trend, "mms": mms}


def render_anatomy(df, a, b, macro, tf, micro, path):
    win = df.iloc[a:b + 1].reset_index(drop=True)
    n = len(win)
    info = build_mms(win, micro)
    if not info:
        return None
    fig, ax = plt.subplots(figsize=(16, 8.5), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for i in range(n):
        o, h, l, cl = win.Open[i], win.High[i], win.Low[i], win.Close[i]
        col = "#2a7d54" if cl >= o else "#8f3b34"
        ax.plot([i, i], [l, h], color=col, lw=0.7, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, cl)), .6, abs(cl - o) or .02,
                               facecolor=col, edgecolor=col, zorder=2))
    tnum = {"TRAD": 0, "EXT": 0, "FAIL": 0, "WEAK": 0}
    for m in info["mms"]:
        x0, x1 = m["b"], min(n - 1, m["next"] + 2)
        col = TYc[m["typ"]]; tnum[m["typ"]] += 1
        weak = m["typ"] == "WEAK"
        keys = [("hwb", "-"), ("fail", ":"), ("tgt", "--")] if not weak else [("hwb", "-")]
        for key, style in keys:
            ax.plot([x0, x1], [m[key], m[key]], color=col,
                    lw=1.5 if key == "hwb" and not weak else 0.9, ls=style,
                    alpha=.3 if weak else (.9 if key == "hwb" else .6), zorder=5)
        ax.plot([m["a"], m["b"]], [m["start"], m["end"]], color=col, lw=0.9,
                alpha=.25 if weak else .5, zorder=4)
        if not weak:
            tag = {"TRAD": "Trad", "EXT": "Ext", "FAIL": "FAIL"}[m["typ"]] + str(tnum[m["typ"]])
            tag += " ✓" if m["typ"] != "FAIL" else ""
            ax.text(m["b"] + 0.4, m["tgt"], tag, color=col, fontsize=FS * .8,
                    fontweight="bold", va="center", zorder=8)
        if m["typ"] == "FAIL":
            ax.scatter([x0], [m["fail"]], marker="x", s=85, color="#f85149", zorder=9)

    atw_hit = False
    if macro:
        atw = macro["atwhwb"]
        ax.axhline(atw, color="#ffd400", lw=2.0, zorder=6)
        ax.text(n + 0.6, atw, f"ATWHWB (50% of leg)  {atw:,.2f}", color="#ffd400",
                fontsize=FS, fontweight="bold", va="center", clip_on=False)
        if macro.get("hit_atw"):
            gi = macro["hit_atw"] - a
            if 0 <= gi < n:
                ax.scatter([gi], [atw], marker="o", s=90, color="#ffd400",
                           edgecolor="white", lw=.8, zorder=9); atw_hit = True

    dirn = "UP" if info["up_trend"] else "DOWN"
    ax.set_title(
        f"ES {tf} — MM SEQUENCE ANATOMY ({dirn} trend)   "
        f"{tnum['TRAD']} traditionals · {tnum['EXT']} extensions · {tnum['FAIL']} failures  (grey=minor)\n"
        f"blue=Trad ✓ (hit 123.6% target)  purple=Ext  red=Fail (✗ pierced 61.8%)   "
        f"each ladder = its 50(HWB)/61.8(fail)/123.6(target)",
        color="#eee", fontsize=FS * 1.05, loc="left")
    step = max(1, n // 12)
    fmt = "%m/%d %H:%M" if tf in ("5m", "15m") else "%m/%d/%y"
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([win.DateTime[i].strftime(fmt) for i in range(0, n, step)],
                       color="#aaa", rotation=0, fontsize=FS * .8)
    ax.tick_params(colors="#aaa")
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.set_xlim(-1, n + 16)
    ax.grid(True, color="#141414", lw=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=112, facecolor=fig.get_facecolor())
    plt.close(fig)
    return {"dir": dirn, "n_trad": tnum["TRAD"], "n_ext": tnum["EXT"],
            "n_fail": tnum["FAIL"], "atw": atw_hit,
            "leg": f"{win.DateTime.iloc[0].strftime('%Y-%m-%d')} → {win.DateTime.iloc[-1].strftime('%Y-%m-%d')}"}


def batch(tf, years):
    c = S.CFG[tf]
    df = S.load_tf(c["tf"])
    df = df[df.DateTime >= df.DateTime.max() - pd.Timedelta(days=365 * years)].reset_index(drop=True)
    H = df["High"].values; L = df["Low"].values
    piv = F.zigzag(H, L, c["macro"])
    os.makedirs(OUTDIR, exist_ok=True)
    seqs = []
    for k in range(len(piv) - 1):
        (i0, p0, k0), (i1, p1, k1) = piv[k], piv[k + 1]
        up = (k0 == 'L' and k1 == 'H')
        if not (up or (k0 == 'H' and k1 == 'L')):
            continue
        lo, hi = (p0, p1) if up else (p1, p0)
        R = hi - lo
        if R <= 0:
            continue
        atw = lo + 0.5 * R
        end = min(len(df) - 1, i1 + c["maxseq"])
        hit = None
        for j in range(i1 + 1, end + 1):
            if (up and L[j] <= atw) or ((not up) and H[j] >= atw):
                hit = j; break
        span_end = hit if hit is not None else end
        if not (40 <= (span_end - i0) <= c["maxseq"]):
            continue
        seqs.append({"up": up, "i0": i0, "i1": i1, "span_end": span_end,
                     "hit_atw": hit, "atwhwb": atw, "R": R})
    seqs.sort(key=lambda s: -s["i1"])
    manifest, kept = [], 0
    for s in seqs:
        if kept >= c["cap"]:
            break
        a = max(0, s["i0"] - 6); b = min(len(df) - 1, s["span_end"] + 6)
        name = f"anat_{tf}_{kept:02d}_{df.DateTime[s['i0']].strftime('%Y%m%d')}.png"
        st = render_anatomy(df, a, b, s, tf, c["micro"], f"{OUTDIR}/{name}")
        if not st or (st["n_trad"] + st["n_ext"] + st["n_fail"]) < 3:
            continue
        manifest.append({"tf": tf, "png": name, "R": round(s["R"], 1), **st})
        kept += 1
        print(f"  {name}  {st['n_trad']}T {st['n_ext']}E {st['n_fail']}F atw={st['atw']}")
    mpath = f"{OUTDIR}/manifest.json"
    existing = [m for m in json.load(open(mpath)) if m["tf"] != tf] if os.path.exists(mpath) else []
    json.dump(existing + manifest, open(mpath, "w"), indent=1)
    print(f"wrote {len(manifest)} {tf} anatomy sequences")


def single():
    tf = sys.argv[1] if len(sys.argv) > 1 else "15m"
    c = S.CFG[tf]
    df = S.load_tf(c["tf"])
    df = df[df.DateTime >= df.DateTime.max() - pd.Timedelta(days=365 * 5)].reset_index(drop=True)
    seqs = S.detect(df, c["macro"], c["micro"], c["maxseq"])
    good = [s for s in seqs if s["hit_atw"] and 40 <= (s["span_end"] - s["i0"]) <= 150]
    good.sort(key=lambda s: -(s["n_with"] + s["n_counter"]))
    s = (good or seqs)[0]
    a, b = max(0, s["i0"] - 6), min(len(df) - 1, s["span_end"] + 6)
    print(render_anatomy(df, a, b, s, tf, c["micro"], "../figures/mm_anatomy.png"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        batch(sys.argv[2] if len(sys.argv) > 2 else "15m",
              int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    else:
        single()
