# A) 7/13 TRADING chart (candles + MQ levels + user marks) with PRIOR session (7/10)
#    VAH/VAL/VPOC lines. 7/10 profile approximated from IB 1-min bars (volume spread
#    uniformly across each bar's range in 0.25 steps), RTH 08:30-15:00 CT, native ESU6.
# B) Divergence AT THE EXTREMES (retest style): swing B RETESTS swing A's price
#    (within tol) while CVD at B fails to confirm -> exhaustion divergence.
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
TICK = 0.25
DAY = "2026-07-13"

# ---------- prior-session (7/10) approx VP from IB 1-min ----------
m1 = pd.read_csv(ROOT + r"\scratchpad\es_1min_20260710_ib.csv", parse_dates=["t"])
m1["t"] = m1.t.dt.tz_localize(None)
rth = m1[(m1.t >= "2026-07-10 08:30") & (m1.t < "2026-07-10 15:00")]
hist = {}
for _, r in rth.iterrows():
    prices = np.arange(r.l, r.h + TICK / 2, TICK)
    v = r.v / len(prices)
    for p in prices:
        hist[round(p * 4) / 4] = hist.get(round(p * 4) / 4, 0) + v
hist = pd.Series(hist).sort_index()

def value_area(h, pct=0.70):
    prices, vols = h.index.to_numpy(), h.to_numpy(dtype=float)
    ipoc = int(vols.argmax()); need = vols.sum() * pct
    lo = hi = ipoc; acc = vols[ipoc]
    while acc < need and (lo > 0 or hi < len(vols) - 1):
        up = vols[hi + 1] if hi < len(vols) - 1 else -1
        dn = vols[lo - 1] if lo > 0 else -1
        if up >= dn: hi += 1; acc += vols[hi]
        else: lo -= 1; acc += vols[lo]
    return prices[ipoc], prices[hi], prices[lo]

ppoc, pvah, pval = value_area(hist)
print(f"7/10 prior (approx from 1-min, RTH): VPOC {ppoc} VAH {pvah} VAL {pval} "
      f"range {rth.l.min()}-{rth.h.max()}")

# ---------- 7/13 bars + cvd + marks + MQ ----------
bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
met = pd.read_csv(ROOT + r"\data\footprint\ES_metrics.csv", parse_dates=["BarTime"])
df = bars.merge(met[["BarIdx", "BarTime", "cvd"]], on=["BarIdx", "BarTime"])
df = df[df.BarTime.dt.strftime("%Y-%m-%d") == DAY].reset_index(drop=True)
df["x"] = np.arange(len(df))
marks = pd.read_csv(ROOT + r"\data\annotations\marks.csv", parse_dates=["bar_time"])
marks = marks[marks.day == DAY]
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")
mrow = mq[mq.session_date == DAY].iloc[0]

UP, DN = "#2e9e4f", "#d64545"
def candles(ax, b):
    for _, r in b.iterrows():
        c = UP if r.Close >= r.Open else DN
        ax.plot([r.x, r.x], [r.Low, r.High], color=c, linewidth=0.6, zorder=3)
        l, h = sorted([r.Open, r.Close])
        ax.add_patch(Rectangle((r.x - 0.38, l), 0.76, max(h - l, 0.05),
                               facecolor=c, edgecolor=c, linewidth=0.4, zorder=4))

def draw_marks(ax, b):
    for _, m in marks.iterrows():
        if not (0 <= m.bar_idx < len(b)): continue
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

# ---------- chart A ----------
fig, ax = plt.subplots(figsize=(24, 11))
candles(ax, df); draw_marks(ax, df)
n = len(df)
for k, col, ls in [("hvl0", "#4a7ebb", "-"), ("gex_1", "#999999", "--"), ("gex_3", "#999999", "--")]:
    v = float(mrow[k])
    ax.axhline(v, color=col, linewidth=0.9, linestyle=ls, alpha=0.8, zorder=1)
    ax.text(n + 3, v, f"{k} {v:g}", va="center", fontsize=9, color=col)
PC = "#a06a00"
ax.axhspan(pval, pvah, color="#e8d9b8", alpha=0.35, zorder=0)
for v, lab, lw, ls in [(ppoc, "prior VPOC", 1.8, "-"), (pvah, "prior VAH", 1.0, ":"),
                       (pval, "prior VAL", 1.0, ":")]:
    ax.axhline(v, color=PC, linewidth=lw, linestyle=ls, zorder=2)
    ax.text(n + 3, v, f"{lab} {v:g}", va="center", fontsize=9, color=PC, fontweight="bold")
ymin, ymax = min(df.Low.min(), pval) - 5, max(df.High.max(), pvah) + 5
ax.set_ylim(ymin - 8, ymax + 10)
ax.set_xlim(-3, n + 34)
ax.set_title("ES 2026-07-13 — trading chart + PRIOR session (Fri 7/10) VAH/VAL/VPOC "
             "(approx from IB 1-min; native ESU6, RTH)", fontsize=14)
ax.grid(alpha=0.18)
ticks = df.x[:: max(n // 14, 1)]
ax.set_xticks(ticks); ax.set_xticklabels(df.BarTime.dt.strftime("%H:%M")[:: max(n // 14, 1)], fontsize=9)
outA = ROOT + r"\scratchpad\chart_prior_vp_20260713.png"
fig.savefig(outA, dpi=110, bbox_inches="tight"); print("saved", outA)

# ---------- B) divergence at the extremes (retest) ----------
W = 8          # swing = +/-8-bar extremum
TOL = 2.0      # retest tolerance in points (B within TOL of A, either side)
MAXGAP = 60    # bars between the two tests
hi, lo, cv = df.High.to_numpy(), df.Low.to_numpy(), df.cvd.to_numpy()
sw_h = [i for i in range(W, n - W) if hi[i] == hi[i-W:i+W+1].max() and hi[i] > hi[i-W:i].max()]
sw_l = [i for i in range(W, n - W) if lo[i] == lo[i-W:i+W+1].min() and lo[i] < lo[i-W:i].min()]

divs = []
for a_i, b_i in [(a, b) for a in sw_h for b in sw_h if a < b <= a + MAXGAP]:
    if abs(hi[b_i] - hi[a_i]) <= TOL and cv[b_i] < cv[a_i]:
        divs.append(("bearish", a_i, b_i))
for a_i, b_i in [(a, b) for a in sw_l for b in sw_l if a < b <= a + MAXGAP]:
    if abs(lo[b_i] - lo[a_i]) <= TOL and cv[b_i] > cv[a_i]:
        divs.append(("bullish", a_i, b_i))
# keep first (earliest B) per A to avoid chains
seen = set(); keep = []
for d in sorted(divs, key=lambda d: d[2]):
    if d[1] in seen: continue
    seen.add(d[1]); keep.append(d)
divs = keep
print(f"extreme-retest divergences: {len(divs)}")
for k, a, b in divs:
    p = hi if k == "bearish" else lo
    print(f"  {k}: test1 {df.BarTime[a]:%H:%M} p={p[a]:g} cvd={cv[a]:g} -> "
          f"retest {df.BarTime[b]:%H:%M} p={p[b]:g} cvd={cv[b]:g} dCVD={cv[b]-cv[a]:+g}")

fig, (axP, axC) = plt.subplots(2, 1, figsize=(24, 13), sharex=True,
                               gridspec_kw={"height_ratios": [2.4, 1], "hspace": 0.05})
candles(axP, df); draw_marks(axP, df)
axC.plot(df.x, df.cvd, color="#1f5fa8", linewidth=1.6)
axC.axhline(0, color="#666666", linewidth=0.8)
for k, a, b in divs:
    col = "#b02020" if k == "bearish" else "#0e7a3b"
    p = hi if k == "bearish" else lo
    off = 1.2 if k == "bearish" else -1.2
    axP.plot([a, b], [p[a] + off, p[b] + off], color=col, linewidth=2.4, zorder=6)
    axP.scatter([a, b], [p[a] + off, p[b] + off], s=26, color=col, zorder=7)
    axC.plot([a, b], [cv[a], cv[b]], color=col, linewidth=2.4, zorder=6)
    axP.annotate(f"{k} div (retest)\n{df.BarTime[b]:%H:%M}", xy=(b, p[b] + off),
                 xytext=(b + 5, p[b] + off * 6), fontsize=10, fontweight="bold", color=col,
                 arrowprops=dict(arrowstyle="->", color=col, lw=1.3))
axP.set_title(f"ES {DAY} — divergence AT THE EXTREMES: price retests a swing high/low "
              f"(±{TOL:g} pts, ≤{MAXGAP} bars) but CVD fails to confirm (ours)", fontsize=13)
axP.grid(alpha=0.18); axC.grid(alpha=0.18); axC.set_ylabel("CVD (session)")
axC.set_xticks(ticks)
axC.set_xticklabels(df.BarTime.dt.strftime("%H:%M")[:: max(n // 14, 1)], fontsize=9)
outB = ROOT + r"\scratchpad\cvd_divergence_extremes_20260713.png"
fig.savefig(outB, dpi=110, bbox_inches="tight"); print("saved", outB)
