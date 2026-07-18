# b1 RTH 2026-07-17 (08:30-08:35 CT), ES 5M — annotated ladder using OUR BidAsk
# footprint export (matches the chart now that calc mode = BidAsk).
# Stacked, numbered, one-at-a-time callouts.
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

fp = pd.read_csv(r"c:\Users\Admin\myquant\data\footprint\ES_footprint.csv",
                 parse_dates=["BarTime"])
bars = pd.read_csv(r"c:\Users\Admin\myquant\data\footprint\ES_bars.csv",
                   parse_dates=["BarTime"])
b = bars[bars.BarTime == "2026-07-17 08:35:00"].iloc[0]
g = fp[fp.BarIdx == b.BarIdx].sort_values("Price", ascending=False).reset_index(drop=True)
n = len(g)

INK, MUT = "#20262e", "#68707c"
GRNBG, REDBG, BLU = "#2e9e4f", "#e05555", "#4a7ab5"

fig, ax = plt.subplots(figsize=(14, 19))
ax.set_xlim(0, 14); ax.set_ylim(-7.6, n + 4); ax.axis("off")
X0, CW = 4.9, 2.3

# candle sketch (real OHLC)
def y_of(price):  # ladder row center for a price
    return n - 1 - (g.Price.iloc[0] - price) / 0.25 + 0.5
ax.plot([3.6, 3.6], [y_of(b.Low) - 0.5, y_of(b.High) + 0.5], color=REDBG, lw=2.5)
ax.add_patch(Rectangle((2.9, y_of(b.Close) - 0.5), 1.4,
                       y_of(b.Open) - y_of(b.Close), facecolor=REDBG, edgecolor=REDBG))
ax.text(3.6, n + 1.3, "the candle", ha="center", fontsize=12, color=MUT)

# ---- the price path: how the bar FORMED, anchored to PRICE ------------------
# Vertical = price on BOTH sides. The markers sit at the true price rows, so ① (the
# 7485.00 open) is mid-ladder where the bar actually started, ② is up at the high,
# and the path shows the rally-then-selloff. The callouts on the right are stacked
# in the SAME ladder order (see NOTES sort below), so the two number columns read
# identically top-to-bottom: ②③④①⑤⑥⑦⑧⑨.
import numpy as np
yo, yh, yl, yc = y_of(b.Open), y_of(b.High), y_of(b.Low), y_of(b.Close)
xs = [1.55, 1.75, 2.05, 1.75, 1.55, 1.75, 2.0]
ys = [yo, (yo + yh) / 2, yh, y_of(7484.5), y_of(7480), yl, yc]
t = np.linspace(0, 1, 200)
xi = np.interp(t, np.linspace(0, 1, len(xs)), xs)
yi = np.interp(t, np.linspace(0, 1, len(ys)), ys)
ax.plot(xi, yi, color=MUT, lw=2, alpha=0.85)
ax.annotate("", xy=(2.0, yc), xytext=(1.9, yc + 1.5),
            arrowprops=dict(arrowstyle="->", color=MUT, lw=2))
ax.text(0.3, yh - 2.2, "TIME →\nhow the bar\nformed", fontsize=11, color=MUT,
        ha="left", va="top")

for i, r in g.iterrows():
    y = n - 1 - i
    d = r.AskVol - r.BidVol
    bg = BLU if abs(d) <= 2 and r.BidVol + r.AskVol > 800 else (GRNBG if d > 0 else REDBG)
    ax.add_patch(Rectangle((X0, y), CW, 0.92, facecolor=bg, edgecolor="white", lw=0.5))
    ax.text(X0 + 0.08, y + 0.45, f"{r.Price:.2f}", fontsize=7.5, color="white",
            va="center", family="Consolas")
    ax.text(X0 + CW - 0.08, y + 0.45, f"{r.BidVol:.0f}x{r.AskVol:.0f}  {d:+.0f}",
            fontsize=8, color="white", va="center", ha="right",
            family="Consolas", fontweight="bold")
ax.text(X0 + CW / 2, n + 1.3, "price   bid x ask   delta", ha="center", fontsize=12, color=MUT)
ax.text(X0 + CW / 2, -1.3, f"{b.Delta:+.0f}", ha="center", fontsize=17,
        color="#c23434", fontweight="bold")
ax.text(X0 + CW / 2, -2.1, f"bar delta  ({b.Delta / (g.BidVol.sum()+g.AskVol.sum()) * 100:+.1f}% of {g.BidVol.sum()+g.AskVol.sum():,.0f} vol)",
        ha="center", fontsize=10.5, color=MUT)

# open/close markers
for price, lab in [(b.Open, "OPEN 7485.00"), (b.Close, "CLOSE 7475.25")]:
    y = y_of(price)
    ax.annotate(lab, xy=(X0 - 0.05, y), xytext=(X0 - 1.15, y), fontsize=10,
                fontweight="bold", color=INK, va="center", ha="right",
                arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))

# (ladder row index, label, text, colour). Numbers stay CHRONOLOGICAL — ① is the
# open — but the list is sorted by ladder row before stacking, so the callouts
# appear in price order and match the left markers one-for-one.
NOTES = [
    (25, "①", "① 08:30 — THE OPEN, 7485.00\n"
              "• bar starts here (black arrow on the ladder)\n"
              "• first move is UP: delta path hits +244\n"
              "  before it ever goes negative", "#20262e"),
    (4, "②", "② THE PROBE UP (7489–7491.25)\n"
             "• buyers lift: +91, +103, +123\n"
             "• but only 23 lots trade at the very top\n"
             "• the push upward dies quietly", "#1e7a3f"),
    (13, "③", "③ REJECTION — FIRST PUNCH AT 7488.00\n"
              "• on the way back down: 1237 sell x 1036 buy\n"
              "  = −201, three points (12 ticks) above the open\n"
              "• the top is now the upper wick", "#c23434"),
    (19, "④", "④ BACK THROUGH THE OPEN (7487.25→7485)\n"
              "• every level red: −107, −126, −172, −170\n"
              "• sellers press straight through 7485\n"
              "• bar turns red and stays red", "#c23434"),
    (28, "⑤", "⑤ ONE BATTLE, ONE COUNTERPUNCH\n"
              "• 7484.50: 710 x 709 — dead even, huge traffic\n"
              "• 7484.25: buyers answer +166\n"
              "• their only real stand of the bar — it fails", "#4a7ab5"),
    (36, "⑥", "⑥ THE TRAPDOOR (7483.25→7481.25)\n"
              "• −216, −134 … then the ask column collapses\n"
              "  DOWN the ladder: 21, 13, 4 … 3\n"
              "  (one 92 blip at 7481.50 — the lone bid)\n"
              "• selling into a vacuum = price falls fast", "#c23434"),
    (45, "⑦", "⑦ STILL PRESSING — 7480.00\n"
              "• 345 x 167 = −178\n"
              "• round number, no defense", "#c23434"),
    (55, "⑧", "⑧ WEAK PUSHBACK (7478.25–7477.50)\n"
              "• down the ladder: +40 then +123 — buyers probe\n"
              "• too small vs the flow above; no traction", "#1e7a3f"),
    (65, "⑨", "⑨ 08:35 — THE LOW AND THE CLOSE\n"
              "• 7475.00: 160 sells x ZERO buys — nobody lifts\n"
              "• one-sided extreme, selling not exhausted\n"
              "• closes 7475.25, one tick off the low", "#c23434"),
]
NOTES.sort(key=lambda r: r[0])          # price order -> matches the left column
# left markers, at their true price rows, in one column clear of the OPEN/CLOSE
# labels (those right-align at x=3.75 and run back to ~2.5)
for idx, lab, _t, _c in NOTES:
    ax.text(1.3, n - 1 - idx + 0.5, lab, fontsize=13, color=INK,
            ha="center", va="center", fontweight="bold")
# fixed stacked slots (chronological top->bottom), connector to the actual row
slot_h = (n + 2) / len(NOTES)
for si, (idx, _lab, text, color) in enumerate(NOTES):
    ys = n + 0.5 - si * slot_h            # slot top
    ax.text(X0 + CW + 1.05, ys, text, fontsize=11.8, color=color, va="top",
            ha="left", linespacing=1.42)
    ax.plot([X0 + CW + 0.12, X0 + CW + 0.95], [n - 1 - idx + 0.5, ys - 1.0],
            color=color, lw=1.2, alpha=0.75)
    ax.plot([X0 + CW + 0.12], [n - 1 - idx + 0.5], marker="o", ms=4, color=color)

ax.text(0.35, -5.4,
        "VERDICT: no absorption story here — sellers attacked from the open,\n"
        "won every fight but one, and the low finished one-sided. Plain initiative selling.",
        fontsize=13, color=INK, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f6dedd", edgecolor="#c23434"))
ax.text(0.35, n + 3.0,
        "b1 of RTH — ES 5M, Fri 7/17 08:30–08:35 CT  (BidAsk numbers)",
        fontsize=16, fontweight="bold", color=INK)
ax.text(0.35, n + 1.9,
        f"O {b.Open}  H {b.High}  L {b.Low}  C {b.Close}   ·   66 price levels   ·   delta −2339",
        fontsize=12, color=MUT)

# write straight into the slide library — the old scratchpad path meant re-running
# this script silently left docs/slides/ showing the stale PNG.
out = (r"c:\Users\Admin\myquant\docs\slides\footprint-reading"
       r"\02_b1_rth_20260717_ladder_read.png")
fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="#fcfcfa")
print("saved", out)
