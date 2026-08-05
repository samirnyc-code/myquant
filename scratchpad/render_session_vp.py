# Session volume profile from OUR footprint ladder:
#   chart A (7/13): current-session DEVELOPING VP (dVPOC/dVAH/dVAL evolving bar by bar)
#                   + end-of-session composite histogram on the left
#   chart B (7/14): PRIOR-session (7/13) profile carried forward (VPOC/VAH/VAL lines,
#                   naked-VPOC status) + 7/14 developing VP
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
TICK = 0.25

bars_all = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
fp = pd.read_csv(ROOT + r"\data\footprint\ES_footprint.csv", parse_dates=["BarTime"])
# same dedupe as footprint_metrics.py: exporter appends on rerun -> keep last
fp = fp.drop_duplicates(subset=["BarIdx", "BarTime", "Price"], keep="last")
fp["vol"] = fp.BidVol + fp.AskVol
marks_all = pd.read_csv(ROOT + r"\data\annotations\marks.csv", parse_dates=["bar_time"])
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")

def day_frames(day):
    b = bars_all[bars_all.BarTime.dt.strftime("%Y-%m-%d") == day].reset_index(drop=True)
    f = fp.merge(b[["BarIdx", "BarTime"]], on=["BarIdx", "BarTime"])  # drops junk partial bar
    b["x"] = np.arange(len(b))
    return b, f

def value_area(hist, pct=0.70):
    # hist: Series price->vol. Standard expand-around-POC.
    h = hist.sort_index()
    prices, vols = h.index.to_numpy(), h.to_numpy(dtype=float)
    ipoc = int(vols.argmax())
    total = vols.sum()
    need = total * pct
    lo = hi = ipoc
    acc = vols[ipoc]
    while acc < need and (lo > 0 or hi < len(vols) - 1):
        up = vols[hi + 1] if hi < len(vols) - 1 else -1
        dn = vols[lo - 1] if lo > 0 else -1
        if up >= dn:
            hi += 1; acc += vols[hi]
        else:
            lo -= 1; acc += vols[lo]
    return prices[ipoc], prices[hi], prices[lo]  # poc, vah, val

def developing(b, f):
    """per-bar developing POC/VAH/VAL using cumulative session histogram"""
    out = []
    hist = {}
    fg = dict(tuple(f.groupby("BarIdx")))
    for _, r in b.iterrows():
        g = fg.get(r.BarIdx)
        if g is not None:
            for p, v in zip(g.Price, g.vol):
                hist[p] = hist.get(p, 0) + v
        poc, vah, val = value_area(pd.Series(hist))
        out.append((r.x, poc, vah, val))
    return pd.DataFrame(out, columns=["x", "dpoc", "dvah", "dval"])

def draw_price(ax, b, marks, levels, title):
    UP, DN = "#2e9e4f", "#d64545"
    for _, r in b.iterrows():
        c = UP if r.Close >= r.Open else DN
        ax.plot([r.x, r.x], [r.Low, r.High], color=c, linewidth=0.6, zorder=3)
        lo, hi = sorted([r.Open, r.Close])
        ax.add_patch(Rectangle((r.x - 0.38, lo), 0.76, max(hi - lo, 0.05),
                               facecolor=c, edgecolor=c, linewidth=0.4, zorder=4))
    ymin, ymax = b.Low.min() - 4, b.High.max() + 4
    for name, lv, col, ls in levels:
        if ymin - 6 <= lv <= ymax + 6:
            ax.axhline(lv, color=col, linewidth=0.8, linestyle=ls, alpha=0.8, zorder=1)
            ax.text(len(b) + 3, lv, name, va="center", fontsize=9, color=col)
    for _, m in marks.iterrows():
        if not (0 <= m.bar_idx < len(b)):
            continue
        r = b.iloc[int(m.bar_idx)]
        lab = {"fade2": "2nd-entry fade", "bopb": "BOPB"}.get(m.setup, m.setup)
        if m.direction == "long":
            ax.annotate(f"{lab} LONG\n{m.bar_time:%H:%M}", xy=(r.x, r.Low - 1),
                        xytext=(r.x, r.Low - 9), ha="center", fontsize=10, fontweight="bold",
                        color=UP, arrowprops=dict(arrowstyle="->", color=UP, lw=1.6))
        else:
            ax.annotate(f"{lab} SHORT\n{m.bar_time:%H:%M}", xy=(r.x, r.High + 1),
                        xytext=(r.x, r.High + 9), ha="center", fontsize=10, fontweight="bold",
                        color=DN, arrowprops=dict(arrowstyle="->", color=DN, lw=1.6))
    ax.set_ylim(ymin - 10, ymax + 12)
    ax.set_xlim(-3, len(b) + 30)
    ax.set_title(title, fontsize=14)
    ax.grid(alpha=0.18)
    ticks = b.x[:: max(len(b) // 14, 1)]
    ax.set_xticks(ticks)
    ax.set_xticklabels(b.BarTime.dt.strftime("%H:%M")[:: max(len(b) // 14, 1)], fontsize=9)

def mq_levels(day):
    row = mq[mq.session_date == day].iloc[0]
    out = []
    for k, col, ls in [("hvl0", "#4a7ebb", "-"), ("gex_1", "#999999", "--"),
                       ("gex_3", "#999999", "--"), ("ps0", "#999999", "--")]:
        v = row.get(k)
        if pd.notna(v):
            out.append((f"{k} {float(v):g}", float(v), col, ls))
    return out

# ---------- chart A: 7/13 developing VP ----------
b13, f13 = day_frames("2026-07-13")
dev13 = developing(b13, f13)
sess13 = f13.groupby("Price").vol.sum()

fig, ax = plt.subplots(figsize=(24, 11))
draw_price(ax, b13, marks_all[marks_all.day == "2026-07-13"], mq_levels("2026-07-13"),
           "ES 2026-07-13 — DEVELOPING session VP from our ladder "
           "(dVPOC line, dVAH/dVAL band) + composite profile at left")
ax.fill_between(dev13.x, dev13.dval, dev13.dvah, step="mid", color="#9db9dc", alpha=0.30,
                linewidth=0, zorder=2, label="developing value area 70% (ours)")
ax.step(dev13.x, dev13.dpoc, where="mid", color="#1a1a5e", linewidth=1.8, zorder=5,
        label="developing VPOC (ours)")
ax.step(dev13.x, dev13.dvah, where="mid", color="#5b7fb5", linewidth=1.0, zorder=5)
ax.step(dev13.x, dev13.dval, where="mid", color="#5b7fb5", linewidth=1.0, zorder=5)
# composite histogram on the left margin
w = sess13 / sess13.max() * 34
ax.barh(sess13.index, -w, left=-3, height=TICK, color="#7f95b5", alpha=0.55, zorder=2,
        label="session profile (ours)")
ax.set_xlim(-40, len(b13) + 30)
ax.legend(loc="lower left", fontsize=10, framealpha=0.9)
outA = ROOT + r"\scratchpad\vp_developing_20260713.png"
fig.savefig(outA, dpi=110, bbox_inches="tight")
print("saved", outA)
fpoc, fvah, fval = value_area(sess13)
print(f"7/13 final: VPOC {fpoc} VAH {fvah} VAL {fval}")

# ---------- chart B: 7/14 with prior-session (7/13) profile ----------
b14, f14 = day_frames("2026-07-14")
dev14 = developing(b14, f14)
ppoc, pvah, pval = value_area(sess13)
naked = not ((b14.Low <= ppoc) & (b14.High >= ppoc)).any()

fig, ax = plt.subplots(figsize=(24, 11))
draw_price(ax, b14, marks_all[marks_all.day == "2026-07-14"], mq_levels("2026-07-14"),
           "ES 2026-07-14 — PRIOR-session (7/13) profile carried forward + 7/14 developing VP (ours)")
# prior-session profile as histogram on left + carried lines
w = sess13 / sess13.max() * 34
ax.barh(sess13.index, -w, left=-3, height=TICK, color="#c4a468", alpha=0.5, zorder=2,
        label="PRIOR session (7/13) profile")
ax.axhline(ppoc, color="#a06a00", linewidth=1.8, linestyle="-", zorder=5)
ax.text(len(b14) + 3, ppoc, f"prior VPOC {ppoc:g}" + (" (NAKED)" if naked else " (touched)"),
        va="center", fontsize=9, color="#a06a00", fontweight="bold")
for v, lab in [(pvah, "prior VAH"), (pval, "prior VAL")]:
    ax.axhline(v, color="#a06a00", linewidth=0.9, linestyle=":", zorder=5)
    ax.text(len(b14) + 3, v, f"{lab} {v:g}", va="center", fontsize=9, color="#a06a00")
ax.fill_between(dev14.x, dev14.dval, dev14.dvah, step="mid", color="#9db9dc", alpha=0.30,
                linewidth=0, zorder=2, label="7/14 developing value area (ours)")
ax.step(dev14.x, dev14.dpoc, where="mid", color="#1a1a5e", linewidth=1.8, zorder=5,
        label="7/14 developing VPOC (ours)")
ax.set_xlim(-40, len(b14) + 30)
ax.legend(loc="lower left", fontsize=10, framealpha=0.9)
outB = ROOT + r"\scratchpad\vp_prior_20260714.png"
fig.savefig(outB, dpi=110, bbox_inches="tight")
print("saved", outB)
print(f"prior VPOC {ppoc} naked={naked}; 7/14 bars={len(b14)}")
