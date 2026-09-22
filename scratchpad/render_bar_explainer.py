# Annotated walkthrough of the user's screenshot bar (7/17 15:00 5M ES, red candle,
# delta/level view, bar delta +852 shown green under the bar). Numbers transcribed
# from the screenshot top->bottom; zones annotated in plain language.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

vals = [6, 161, 77, 257, 69, 133, -241, 41, 87, 239, 150, 77, 59, -70, 203, -212,
        -87, -51, -200, 17, -38, -4, 133, -23, 104, 70, -96, 0, 168, -124, -48, 32,
        278, 359, -212, -264, -19, -68, -40, -39, 5, -69, -32, -45, 9, -43, 57, -80,
        -62, 39, -39, 19, -41, 22, 14, 109, 204, -50, -51]
n = len(vals)
GRN, RED, INK, MUT = "#1e7a3f", "#c23434", "#20262e", "#68707c"
GRNBG, REDBG = "#2e9e4f", "#e05555"

fig, ax = plt.subplots(figsize=(13, 16))
ax.set_xlim(0, 13); ax.set_ylim(-2.5, n + 4); ax.axis("off")
X0, CW, RH = 4.6, 1.7, 1.0

# candle sketch: open at row of the blue 0 (idx 27), close near row 53
open_i, close_i = n - 1 - 27, n - 1 - 53   # y coords (0=bottom)
ax.plot([3.4, 3.4], [0.5, n - 0.5], color=RED, lw=2)                       # wick
ax.add_patch(Rectangle((2.75, close_i), 1.3, open_i - close_i, facecolor=RED,
                       edgecolor=RED))                                     # body
ax.text(3.4, n + 1.2, "the candle\n(what price did)", ha="center", fontsize=12,
        color=MUT)

for i, v in enumerate(vals):
    y = n - 1 - i
    bg = GRNBG if v > 0 else (REDBG if v < 0 else "#4a7ab5")
    ax.add_patch(Rectangle((X0, y), CW, RH * 0.94, facecolor=bg,
                           edgecolor="white", linewidth=0.6))
    ax.text(X0 + CW / 2, y + 0.47, str(v), ha="center", va="center",
            fontsize=9.5, color="white", family="Consolas", fontweight="bold")
ax.text(X0 + CW / 2, n + 1.2, "delta per price level\n(who was aggressive)",
        ha="center", fontsize=12, color=MUT)
ax.text(X0 + CW / 2, -1.6, "852", ha="center", fontsize=17, color=GRN,
        fontweight="bold")
ax.text(X0 + CW / 2, -2.3, "bar delta = sum of all rows", ha="center", fontsize=10.5,
        color=MUT)

def note(y, text, color=INK):
    ax.annotate(text, xy=(X0 + CW + 0.15, y), xytext=(X0 + CW + 0.75, y),
                fontsize=11.5, color=color, va="center", ha="left",
                arrowprops=dict(arrowstyle="-", color=color, lw=1.3),
                linespacing=1.35)

note(n - 2.5, "① THE TOP — tiny 6 at the very high,\nbig green 161/257 just below:\n"
     "buyers were still LIFTING at the highs...", GRN)
note(n - 7.5, "② ...and got slapped: −241 one tick\nunder the probe = sellers answered\n"
     "the breakout attempt", RED)
note(n - 16, "③ upper-third red cluster (−212, −200):\nsellers took over; price left the\n"
     "highs — this whole zone is the\nupper WICK (rejected prices)", RED)
note(n - 28.5, "④ blue 0 row ≈ the OPEN. Zero delta\ncan still be huge two-way volume —\n"
     "'silent' absorption looks like this", "#4a7ab5")
note(n - 34.5, "⑤ 278 and 359 — the HEAVIEST buying\nof the bar... and price still fell\n"
     "through it. That buying was eaten\nby passive sellers = ABSORPTION", GRN)
note(n - 40.5, "⑥ −264/−212 right below the failed\nbuying: absorbed buyers give up,\nsellers press on", RED)
note(n - 56.5, "⑦ THE BOTTOM — green 109/204 one-two\nticks off the low: responsive buyers\n"
     "stepping in; tiny −50/−51 at the very\nlow = selling dried up at the extreme", GRN)

ax.text(0.3, -1.2,
        "THE HEADLINE: red candle (price fell 8 points)\n"
        "but delta is +852 (buyers were MORE aggressive).\n"
        "Aggressive buying that loses = someone big sold\n"
        "passively into every lift. Effort up, result down.\n"
        "This is the absorption signature — the same shape\n"
        "as your 08:35 and 09:15 marks from 7/13.",
        fontsize=12.5, color=INK, va="top", ha="left", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f5e6c4", edgecolor="#a06a00"))

ax.text(0.3, n + 3.2, "Your bar, decoded — ES 5M, Fri 7/17 15:00 (the afternoon flush)",
        fontsize=15, fontweight="bold", color=INK)
out = r"c:\Users\Admin\myquant\scratchpad\bar_explainer_20260717_1500.png"
fig.savefig(out, dpi=120, bbox_inches="tight", facecolor="#fcfcfa")
print("saved", out)
EOF_MARKER_NOT_NEEDED = True
