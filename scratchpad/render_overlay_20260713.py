# Render 7/13 2000-lot volume bars with OUR footprint-derived indicator overlays:
# per-bar POC dots, VAH/VAL band, imbalance markers, unfinished-auction flags,
# delta panel (with min/max delta range), CVD panel. MQ levels + user's 6 marks kept.
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
DAY = "2026-07-13"

bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
met = pd.read_csv(ROOT + r"\data\footprint\ES_metrics.csv", parse_dates=["BarTime"])
marks = pd.read_csv(ROOT + r"\data\annotations\marks.csv", parse_dates=["bar_time"])

bars = bars[bars.BarTime.dt.strftime("%Y-%m-%d") == DAY].reset_index(drop=True)
met = met[met.BarTime.dt.strftime("%Y-%m-%d") == DAY].reset_index(drop=True)
marks = marks[marks.day == DAY]

df = bars.merge(met, on=["BarIdx", "BarTime"], how="left", validate="1:1")
df["x"] = np.arange(len(df))
print(f"bars={len(bars)} metrics={len(met)} joined={len(df)} cvd_nan={df.cvd.isna().sum()}")

# imbalance stats to pick a display threshold
print("buy_imb dist:", df.buy_imb.value_counts().sort_index().to_dict())
print("sell_imb dist:", df.sell_imb.value_counts().sort_index().to_dict())
print("unf:", int((df.UnfHigh > 0).sum()), int((df.UnfLow > 0).sum()))

LEVELS = {"hvl0 7585": (7585.0, "#4a7ebb"), "gex_3 7610": (7610.0, "#999999"),
          "gex_1 7550": (7550.0, "#999999"), "ps0 7540": (7540.0, "#999999"),
          "hvl 7545": (7545.0, "#999999")}

UP, DN = "#2e9e4f", "#d64545"

fig, (axP, axD, axC) = plt.subplots(
    3, 1, figsize=(24, 15), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1], "hspace": 0.04})

# ---- panel 1: price ----
# VAH/VAL band (our value area, per bar) drawn first so candles sit on top
axP.fill_between(df.x, df.val, df.vah, step="mid", color="#b8c7de", alpha=0.45,
                 linewidth=0, label="Value area (VAH–VAL, ours)")
for _, r in df.iterrows():
    c = UP if r.Close >= r.Open else DN
    axP.plot([r.x, r.x], [r.Low, r.High], color=c, linewidth=0.6, zorder=2)
    lo, hi = sorted([r.Open, r.Close])
    axP.add_patch(Rectangle((r.x - 0.38, lo), 0.76, max(hi - lo, 0.05),
                            facecolor=c, edgecolor=c, linewidth=0.4, zorder=3))
# POC dots
axP.scatter(df.x, df.poc, s=7, color="#1a1a5e", zorder=4, label="POC per bar (ours)")
# imbalance markers: >=3 stacked imbalances (>=2 fires on ~25% of bars — noise)
bi = df[df.buy_imb >= 3]
si = df[df.sell_imb >= 3]
axP.scatter(bi.x, bi.Low - 1.2, marker="^", s=30, color=UP, edgecolor="white",
            linewidth=0.4, zorder=5, label="buy imbalance ≥3 stacked (ours)")
axP.scatter(si.x, si.High + 1.2, marker="v", s=30, color=DN, edgecolor="white",
            linewidth=0.4, zorder=5, label="sell imbalance ≥3 stacked (ours)")
# NOTE: UnfHigh/UnfLow dropped from display — they fire on ~45% of 2000-lot volume
# bars (bar ends mid-auction by construction), so as drawn they carry no signal.

ymin, ymax = df.Low.min() - 4, df.High.max() + 4
for name, (lv, col) in LEVELS.items():
    if ymin <= lv <= ymax:
        axP.axhline(lv, color=col, linewidth=1.0 if "hvl0" in name else 0.8,
                    linestyle="-" if "hvl0" in name else "--", alpha=0.85, zorder=1)
        axP.text(len(df) + 3, lv, name, va="center", fontsize=9, color=col)

# user's marks
for _, m in marks.iterrows():
    # bar_idx in marks.csv is the day-relative bar index used by the marking tool
    if not (0 <= m.bar_idx < len(df)):
        continue
    row = df.iloc[[int(m.bar_idx)]]
    x = row.x.iloc[0]
    lab = {"fade2": "2nd-entry fade", "bopb": "BOPB", "other": "other"}.get(m.setup, m.setup)
    if m.direction == "long":
        axP.annotate(f"{lab} LONG\n{m.bar_time:%H:%M}", xy=(x, row.Low.iloc[0] - 1),
                     xytext=(x, row.Low.iloc[0] - 9), ha="center", fontsize=10,
                     fontweight="bold", color=UP,
                     arrowprops=dict(arrowstyle="->", color=UP, lw=1.6))
    else:
        axP.annotate(f"{lab} SHORT\n{m.bar_time:%H:%M}", xy=(x, row.High.iloc[0] + 1),
                     xytext=(x, row.High.iloc[0] + 9), ha="center", fontsize=10,
                     fontweight="bold", color=DN,
                     arrowprops=dict(arrowstyle="->", color=DN, lw=1.6))

axP.set_ylim(ymin - 10, ymax + 12)
axP.set_xlim(-3, len(df) + 26)
axP.set_title("ES 2026-07-13 — 2000-lot volume bars + OUR footprint-derived overlays "
              "(POC · value area · stacked imbalances · delta · CVD)", fontsize=14)
axP.legend(loc="lower left", fontsize=9, framealpha=0.9)
axP.grid(alpha=0.18)

# ---- panel 2: delta ----
cols = np.where(df.delta >= 0, UP, DN)
axD.vlines(df.x, df.MinDelta, df.MaxDelta, color="#b0b0b0", linewidth=0.7,
           label="min→max delta range (ours)")
axD.bar(df.x, df.delta, width=0.76, color=cols, label="bar delta (ours)")
axD.axhline(0, color="#666666", linewidth=0.8)
axD.set_ylabel("Delta")
axD.legend(loc="lower left", fontsize=9, framealpha=0.9)
axD.grid(alpha=0.18)

# ---- panel 3: CVD ----
axC.plot(df.x, df.cvd, color="#1f5fa8", linewidth=1.6)
axC.axhline(0, color="#666666", linewidth=0.8)
axC.set_ylabel("CVD (session)")
axC.grid(alpha=0.18)

ticks = df.x[:: max(len(df) // 16, 1)]
axC.set_xticks(ticks)
axC.set_xticklabels(df.BarTime.dt.strftime("%H:%M")[:: max(len(df) // 16, 1)], fontsize=9)

out = ROOT + r"\scratchpad\overlay_20260713.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)
