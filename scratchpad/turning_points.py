"""First-pass EXPLORATORY turning-point order-flow study (in-sample, hindsight —
hypothesis generation only). 5 days of ES footprint (7/13-7/17).

For each mechanically-detected swing high/low, characterize the flow into & at the
turn, and compare against non-turn control bars. Signatures (all from OUR pipeline):
  - turn_delta       : delta of the swing bar
  - approach_delta   : summed delta over the W bars before the turn
  - absorption (d/p) : |approach_delta| per point of price progress (H5 v2)
  - cvd_div          : effort-vs-result — did CVD make a NEW extreme with price?
                       (bearish turn: price HH but CVD not HH = buyers absorbed)
  - stacked_imb      : max diagonal-imbalance stack at the swing bar
  - unf              : unfinished auction at the extreme
  - dist_mq_ticks    : distance (ticks) to nearest MQ level that day
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
TICK = 0.25
W = 8            # swing window (bars each side)

bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
met = pd.read_csv(ROOT + r"\data\footprint\ES_metrics.csv", parse_dates=["BarTime"])
df = bars.merge(met[["BarIdx", "BarTime", "cvd", "buy_imb", "sell_imb", "poc", "vah", "val"]],
                on=["BarIdx", "BarTime"], how="inner")
df["day"] = df.BarTime.dt.strftime("%Y-%m-%d")
mq = pd.read_csv(ROOT + r"\data\menthorq\ES1!_mq_levels_history.csv")

LKEYS = ["cr", "ps", "hvl", "hvl0", "cr0", "ps0", "gw0", "gex_1", "gex_2", "gex_3", "gex_4", "gex_5"]
def mq_levels(day):
    r = mq[mq.session_date == day]
    if not len(r):
        return []
    r = r.iloc[0]
    return sorted({float(r[k]) for k in LKEYS if pd.notna(r.get(k))})

rows = []          # per-swing records
control = []       # non-swing control bars (delta/absorption baseline)
for day, g in df.groupby("day"):
    g = g.sort_values("BarIdx").reset_index(drop=True)
    hi, lo, cv, dl = g.High.values, g.Low.values, g.Low.values, g.cvd.values
    hi, lo = g.High.values, g.Low.values
    delta = g.Delta.values
    n = len(g)
    levels = mq_levels(day)
    swing_idx = set()
    for i in range(W, n - W):
        is_h = hi[i] == hi[i - W:i + W + 1].max() and hi[i] > hi[i - W:i].max()
        is_l = lo[i] == lo[i - W:i + W + 1].min() and lo[i] < lo[i - W:i].min()
        if not (is_h or is_l):
            continue
        swing_idx.add(i)
        kind = "HIGH" if is_h else "LOW"
        a0 = max(i - W, 0)
        appr = delta[a0:i + 1].sum()
        prog = (hi[i] - g.Low[a0]) if is_h else (g.High[a0] - lo[i])   # price traveled into turn
        prog = max(abs(prog), TICK)
        # cvd divergence: at a HIGH, is CVD below its own prior-window max? (buyers absorbed)
        cwin = g.cvd.values[a0:i + 1]
        if is_h:
            cvd_div = 1 if g.cvd[i] < cwin.max() - 1e-9 else 0
        else:
            cvd_div = 1 if g.cvd[i] > cwin.min() + 1e-9 else 0
        px = hi[i] if is_h else lo[i]
        dist = min((abs(px - L) for L in levels), default=np.nan) / TICK
        rows.append(dict(day=day, i=i, kind=kind, price=px,
                         turn_delta=delta[i], approach_delta=appr,
                         absorption=abs(appr) / prog,
                         cvd_div=cvd_div,
                         stacked_imb=max(g.buy_imb[i], g.sell_imb[i]),
                         unf=int((g.UnfHigh[i] > 0) or (g.UnfLow[i] > 0)),
                         dist_mq_ticks=dist))
    for i in range(W, n - W):
        if i in swing_idx:
            continue
        a0 = max(i - W, 0)
        appr = delta[a0:i + 1].sum()
        prog = max(abs(g.High[i] - g.Low[a0]), TICK)
        control.append(dict(absorption=abs(appr) / prog, stacked_imb=max(g.buy_imb[i], g.sell_imb[i]),
                            unf=int((g.UnfHigh[i] > 0) or (g.UnfLow[i] > 0)),
                            abs_delta=abs(delta[i])))

R = pd.DataFrame(rows)
C = pd.DataFrame(control)
print(f"days: {df.day.nunique()} | bars: {len(df)} | swings: {len(R)} "
      f"(highs {sum(R.kind=='HIGH')}, lows {sum(R.kind=='LOW')}) | controls: {len(C)}\n")

print("=== SIGNATURE: swings vs control bars (means) ===")
tbl = pd.DataFrame({
    "swing_HIGH": R[R.kind == "HIGH"][["absorption", "stacked_imb", "unf"]].mean(),
    "swing_LOW":  R[R.kind == "LOW"][["absorption", "stacked_imb", "unf"]].mean(),
    "control":    C[["absorption", "stacked_imb", "unf"]].mean(),
})
print(tbl.round(2).to_string())

print(f"\ncvd divergence present at swings: {R.cvd_div.mean()*100:.0f}% "
      f"(HIGH {R[R.kind=='HIGH'].cvd_div.mean()*100:.0f}% / LOW {R[R.kind=='LOW'].cvd_div.mean()*100:.0f}%)")
near = R.dist_mq_ticks <= 8
print(f"swings within 8 ticks (~2pt) of an MQ level: {near.mean()*100:.0f}%  "
      f"(median dist {R.dist_mq_ticks.median():.0f} ticks)")
print(f"absorption at swings vs control: {R.absorption.mean():.0f} vs {C.absorption.mean():.0f} "
      f"(ratio {R.absorption.mean()/max(C.absorption.mean(),1e-9):.2f}x)")

# ---- annotated chart: the day with the most swings ----
best = R.day.value_counts().idxmax()
g = df[df.day == best].sort_values("BarIdx").reset_index(drop=True)
g["x"] = np.arange(len(g))
sw = R[R.day == best]
UP, DN = "#2e9e4f", "#d64545"
fig, (axP, axC) = plt.subplots(2, 1, figsize=(22, 12), sharex=True,
                               gridspec_kw={"height_ratios": [2.5, 1], "hspace": 0.05})
for _, r in g.iterrows():
    c = UP if r.Close >= r.Open else DN
    axP.plot([r.x, r.x], [r.Low, r.High], color=c, lw=0.6, zorder=2)
    l, h = sorted([r.Open, r.Close])
    axP.add_patch(Rectangle((r.x - 0.38, l), 0.76, max(h - l, .05), facecolor=c, edgecolor=c, lw=.4, zorder=3))
for L in mq_levels(best):
    if g.Low.min() - 3 <= L <= g.High.max() + 3:
        axP.axhline(L, color="#9a7", lw=0.7, ls="--", alpha=.7, zorder=1)
        axP.text(len(g) + 1, L, f"{L:g}", va="center", fontsize=8, color="#9a7")
for _, s in sw.iterrows():
    x = s.i
    col = "#b02020" if s.kind == "HIGH" else "#0e7a3b"
    y = g.High[x] + 1.2 if s.kind == "HIGH" else g.Low[x] - 1.2
    mk = "v" if s.kind == "HIGH" else "^"
    axP.scatter([x], [y], marker=mk, s=90, color=col, edgecolor="black", lw=.5, zorder=6)
    tag = ("A" if s.cvd_div else "") + ("I" if s.stacked_imb >= 3 else "") + ("U" if s.unf else "")
    if tag:
        axP.text(x, y + (1.6 if s.kind == "HIGH" else -1.6), tag, ha="center", fontsize=9,
                 fontweight="bold", color=col)
axP.set_title(f"ES {best} — turning points (▲low ▼high) + flow tags  "
              f"[A=CVD divergence · I=stacked imbalance≥3 · U=unfinished auction] · exploratory/in-sample",
              fontsize=13)
axP.grid(alpha=.15)
axC.plot(g.x, g.cvd, color="#1f5fa8", lw=1.5)
axC.axhline(0, color="#666", lw=.8)
axC.set_ylabel("CVD"); axC.grid(alpha=.15)
for _, s in sw.iterrows():
    axC.scatter([s.i], [g.cvd[s.i]], s=28, color=("#b02020" if s.kind == "HIGH" else "#0e7a3b"), zorder=6)
ticks = g.x[:: max(len(g)//14, 1)]
axC.set_xticks(ticks); axC.set_xticklabels(g.BarTime.dt.strftime("%H:%M")[:: max(len(g)//14, 1)], fontsize=8)
out = ROOT + r"\scratchpad\turning_points.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print("\nsaved", out, "| charted day:", best, "with", len(sw), "swings")
