"""Detect and render full Halsey measured-move SEQUENCES across ~5 years of ES.

A sequence = an initial (macro) leg + the series of with-trend traditional MMs that
ride it, the eventual 61.8% failure that flips the trend, the counter-trend MMs, and
the ATWHWB (all-the-way-half-way-back = 50% of the initial move) that price retraces
to after an extended trend breaks.

Renders one annotated chart per sequence into figures/sequences/ and writes a
manifest (figures/sequences/manifest.json) for the scrollable gallery.

Usage: python sequence_lib.py [15m|1D] [years]
"""
import json
import os
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import find_mm_trades as F

OUTDIR = "../figures/sequences"
FONT_SCALE = float(os.environ.get("EA_FONT_SCALE", 1.2))
LABEL_FS, TICK_FS, TITLE_FS = 12 * FONT_SCALE, 10 * FONT_SCALE, 12 * FONT_SCALE

CFG = {
    "5m":  {"tf": "5min",  "macro": 0.7, "micro": 0.3, "maxseq": 300, "cap": 30},
    "15m": {"tf": "15min", "macro": 1.2, "micro": 0.5, "maxseq": 220, "cap": 30},
    "1D":  {"tf": "1D",    "macro": 6.0, "micro": 2.0, "maxseq": 120, "cap": 24},
}


def load_tf(tf):
    if tf == "1D":
        return pd.read_parquet("../../data/bars/_db_es_daily_24h.parquet").reset_index(drop=True)
    df = pd.read_parquet("../../data/bars/_db_es_5m_rth.parquet")
    if tf == "5min":
        return df.reset_index(drop=True)
    return (df.set_index("DateTime").resample(tf)
            .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
            .dropna().reset_index())


def completed_mms(df, micro_pct):
    F.ZZ_PCT = micro_pct
    F.MAXFWD = 60
    return F.scan(df)


def detect(df, macro_pct, micro_pct, maxseq):
    H = df["High"].values; L = df["Low"].values
    piv = F.zigzag(H, L, macro_pct)
    mms = completed_mms(df, micro_pct)
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
        atwhwb = lo + 0.5 * R                       # 50% of the entire initial move
        # window: from the leg start until price retraces to ATWHWB (or a cap)
        end = min(len(df) - 1, i1 + maxseq)
        hit_atw = None
        for j in range(i1 + 1, end + 1):
            if (up and L[j] <= atwhwb) or ((not up) and H[j] >= atwhwb):
                hit_atw = j; break
        span_end = hit_atw if hit_atw is not None else end
        members = [m for m in mms if i0 <= m["i_entry"] <= span_end]
        withn = [m for m in members if m["up"] == up]
        counter = [m for m in members if m["up"] != up]
        if len(withn) < 2:                          # need a real series to be interesting
            continue
        seqs.append({
            "up": up, "i0": i0, "i1": i1, "span_end": span_end, "hit_atw": hit_atw,
            "lo": lo, "hi": hi, "R": R, "atwhwb": atwhwb,
            "dL": str(df.DateTime[i0].date()), "dH": str(df.DateTime[i1].date()),
            "members": members, "n_with": len(withn), "n_counter": len(counter),
        })
    return seqs


def draw(df, s, tf, path):
    a = max(0, s["i0"] - 6)
    b = min(len(df) - 1, s["span_end"] + 6)
    win = df.iloc[a:b + 1].reset_index(drop=True)
    n = len(win)
    gi = lambda idx: idx - a
    up = s["up"]
    lo, hi, R, atw = s["lo"], s["hi"], s["R"], s["atwhwb"]

    fig, ax = plt.subplots(figsize=(15, 8), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    up_c, dn_c = "#26a65b", "#e2453c"
    for i in range(n):
        o, h, l, c = win.Open[i], win.High[i], win.Low[i], win.Close[i]
        col = up_c if c >= o else dn_c
        ax.plot([i, i], [l, h], color=col, lw=0.7, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, c)), .6, abs(c - o) or 0.02,
                               facecolor=col, edgecolor=col, zorder=3))

    # macro leg + its key levels
    ax.plot([gi(s["i0"]), gi(s["i1"])], [lo if up else hi, hi if up else lo],
            color="#888", ls="--", lw=1.1, zorder=4)
    LINE_END = n - 0.5
    fib = [(hi if up else lo, "#bbbbbb", "0% (leg end)", 1.0, ":"),
           ((hi + 0.236 * R) if up else (lo - 0.236 * R), "#26a65b", "123.6% target", 1.6, "-"),
           (atw, "#4aa3ff", "ATWHWB (50% of leg)", 2.0, "-"),
           (lo if up else hi, "#bbbbbb", "100% (leg start)", 1.0, ":")]
    labels = []
    for y, c, t, lw, ls in fib:
        ax.plot([gi(s["i0"]), LINE_END], [y, y], color=c, lw=lw, ls=ls, zorder=5)
        labels.append({"y": y, "c": c, "t": f"{t}  {y:,.2f}"})

    # member MMs: each drawn as entry (small triangle) -> target (dot), colored by dir
    for m in s["members"]:
        mc = "#26d07c" if m["up"] else "#ff7a6b"
        ax.scatter([gi(m["i_entry"])], [m["hwb"]], marker="^" if m["up"] else "v",
                   s=42, color=mc, edgecolor="white", lw=0.4, zorder=7)
        ax.scatter([gi(m["i_tgt"])], [m["tgt"]], marker="*", s=70, color=mc,
                   edgecolor="none", zorder=7)
        ax.plot([gi(m["i_entry"]), gi(m["i_tgt"])], [m["hwb"], m["tgt"]],
                color=mc, lw=0.6, alpha=.5, zorder=6)

    # de-collide the macro labels
    lo_ = min(win.Low.min(), min(d["y"] for d in labels))
    hi_ = max(win.High.max(), max(d["y"] for d in labels))
    span = hi_ - lo_
    ax.set_ylim(lo_ - 0.04 * span, hi_ + 0.05 * span)
    ymax_l = ax.get_ylim()[1]
    gap = 0.05 * span * FONT_SCALE
    labels.sort(key=lambda d: d["y"])
    for d in labels:
        d["ty"] = d["y"]
    for k in range(1, len(labels)):
        if labels[k]["ty"] - labels[k - 1]["ty"] < gap:
            labels[k]["ty"] = labels[k - 1]["ty"] + gap
    over = labels[-1]["ty"] - (ymax_l - 0.01 * span)
    if over > 0:
        for d in labels:
            d["ty"] -= over
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1]["ty"] - labels[k]["ty"] < gap:
                labels[k]["ty"] = labels[k + 1]["ty"] - gap
    for d in labels:
        ax.plot([LINE_END, n + 0.4], [d["y"], d["ty"]], color=d["c"], lw=0.6, alpha=.6,
                zorder=4, clip_on=False)
        ax.text(n + 1.0, d["ty"], d["t"], color=d["c"], va="center", fontsize=LABEL_FS,
                fontweight="bold", clip_on=False)

    atw_txt = f"ATWHWB hit {df.DateTime[s['hit_atw']].date()}" if s["hit_atw"] else "ATWHWB not reached in window"
    dirtxt = "UP" if up else "DOWN"
    ax.set_title(
        f"ES {tf} — MM SEQUENCE ({dirtxt})   {s['n_with']} with-trend MMs, {s['n_counter']} counter   {atw_txt}\n"
        f"initial leg {s['dL']} {lo if up else hi:,.2f} → {s['dH']} {hi if up else lo:,.2f}  (R {R:,.1f})",
        color="#eee", fontsize=TITLE_FS, loc="left")
    step = max(1, n // 10)
    ax.set_xticks(range(0, n, step))
    fmt = "%m/%d %H:%M" if tf in ("5m", "15m") else "%m/%d/%y"
    ax.set_xticklabels([win.DateTime[i].strftime(fmt) for i in range(0, n, step)],
                       color="#aaa", rotation=0, fontsize=TICK_FS)
    ax.tick_params(colors="#aaa", labelsize=TICK_FS)
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.set_xlim(-1, n + 12)
    ax.grid(True, color="#161616", lw=0.5)
    fig.tight_layout()
    fig.savefig(path, dpi=105, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    tf = sys.argv[1] if len(sys.argv) > 1 else "15m"
    years = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    c = CFG[tf]
    df = load_tf(c["tf"])
    cutoff = df.DateTime.max() - pd.Timedelta(days=365 * years)
    df = df[df.DateTime >= cutoff].reset_index(drop=True)
    print(f"{tf}: {len(df)} bars {df.DateTime.iloc[0].date()}..{df.DateTime.iloc[-1].date()}")
    seqs = detect(df, c["macro"], c["micro"], c["maxseq"])
    seqs.sort(key=lambda s: -s["i1"])           # recent first
    seqs = seqs[:c["cap"]]
    os.makedirs(OUTDIR, exist_ok=True)
    manifest = []
    for idx, s in enumerate(seqs):
        name = f"seq_{tf}_{idx:02d}_{s['dL']}.png"
        draw(df, s, tf, f"{OUTDIR}/{name}")
        manifest.append({"tf": tf, "png": name, "dir": "UP" if s["up"] else "DOWN",
                         "leg": f"{s['dL']} → {s['dH']}", "n_with": s["n_with"],
                         "n_counter": s["n_counter"], "atw": bool(s["hit_atw"]),
                         "R": round(s["R"], 1)})
        print(f"  {name}  {s['n_with']}+{s['n_counter']} MMs  atw={bool(s['hit_atw'])}")
    # merge into existing manifest (keep other TF)
    mpath = f"{OUTDIR}/manifest.json"
    existing = []
    if os.path.exists(mpath):
        existing = [m for m in json.load(open(mpath)) if m["tf"] != tf]
    json.dump(existing + manifest, open(mpath, "w"), indent=1)
    print(f"wrote {len(manifest)} {tf} sequences -> {mpath}")


if __name__ == "__main__":
    main()
