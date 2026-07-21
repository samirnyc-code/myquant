# Explainer diagram: how a footprint ladder's Bid x Ask columns give (1) the
# delta-per-level view Samir sees, (2) the DIAGONAL imbalance comparison, and
# (3) what the Filter parameter tests. Uses the guide's own 71/19 = 274% example.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
from pathlib import Path

INK, MUT = "#20262e", "#68707c"
GRN, RED = "#2e7d4f", "#b03434"
GRNBG, REDBG = "#dcefe3", "#f6dedd"
HL = "#f5e6c4"

prices = ["7501.50", "7501.25", "7501.00", "7500.75", "7500.50", "7500.25"]
bid = [3, 12, 24, 19, 55, 41]
ask = [9, 30, 71, 33, 47, 8]

fig, ax = plt.subplots(figsize=(15, 8.5))
ax.set_xlim(0, 15); ax.set_ylim(-0.9, 8.5); ax.axis("off")

RH, Y0 = 0.85, 1.6
X_P, X_B, X_A, X_D = 1.0, 3.0, 4.6, 6.6
CW = 1.5

ax.text(X_P + 0.6, Y0 + 6 * RH + 0.45, "price", fontsize=13, color=MUT, ha="center")
ax.text(X_B + CW / 2, Y0 + 6 * RH + 0.45, "Bid\n(sellers hit)", fontsize=13, color=RED, ha="center")
ax.text(X_A + CW / 2, Y0 + 6 * RH + 0.45, "Ask\n(buyers lift)", fontsize=13, color=GRN, ha="center")
ax.text(X_D + CW / 2, Y0 + 6 * RH + 0.45, "Delta / level\n(what YOU see)", fontsize=13,
        color=INK, ha="center", fontweight="bold")

for i, (p, b, a) in enumerate(zip(prices, bid, ask)):
    y = Y0 + (5 - i) * RH
    hi_b = (p == "7500.75")
    hi_a = (p == "7501.00")
    ax.text(X_P + 0.6, y + RH / 2, p, fontsize=14, ha="center", va="center",
            color=INK, family="Consolas")
    for x, v, bg, hl in [(X_B, b, "#f3f3f0", hi_b), (X_A, a, "#f3f3f0", hi_a)]:
        ax.add_patch(Rectangle((x, y), CW, RH, facecolor=HL if hl else bg,
                               edgecolor="#c9c6bd", linewidth=1.2))
        ax.text(x + CW / 2, y + RH / 2, str(v), fontsize=15, ha="center", va="center",
                color=INK, family="Consolas", fontweight="bold" if hl else "normal")
    d = a - b
    ax.add_patch(Rectangle((X_D, y), CW, RH, facecolor=GRNBG if d > 0 else REDBG,
                           edgecolor="#c9c6bd", linewidth=1.2))
    ax.text(X_D + CW / 2, y + RH / 2, f"{d:+d}", fontsize=15, ha="center", va="center",
            color=GRN if d > 0 else RED, family="Consolas")

# vertical brace: delta compares SAME row
yv = Y0 + 3 * RH + RH / 2
ax.annotate("", xy=(X_D - 0.15, Y0 + 2 * RH + 0.12), xytext=(X_D - 0.15, Y0 + 4 * RH - 0.12),
            arrowprops=dict(arrowstyle="<->", color=MUT, lw=1.6))
ax.text(X_D + CW / 2, Y0 - 0.3, "delta = Ask − Bid\nSAME row (vertical)",
        fontsize=11.5, color=MUT, ha="center", va="top")

# diagonal arrow: Ask 71 @7501.00 vs Bid 19 @7500.75
y71 = Y0 + 3 * RH + RH / 2   # row index 2 -> (5-2)=3
y19 = Y0 + 2 * RH + RH / 2
ax.add_patch(FancyArrowPatch((X_A + CW / 2, y71), (X_B + CW / 2, y19),
                             arrowstyle="<->", mutation_scale=22, color="#a06a00", lw=3, zorder=6))
ax.text(2.2, -0.15, "IMBALANCE compares DIAGONALLY:\nAsk 71 @7501.00  vs  Bid 19 @7500.75\n"
        "(71/19 − 1) × 100 = 274%  →  ≥200% setting fires  =  BUY imbalance",
        fontsize=13.5, color="#a06a00", ha="left", va="center", fontweight="bold")

# Filter explanation box
ax.text(8.9, Y0 + 6 * RH + 0.45,
        "FILTER = minimum contracts\non the WINNING side only",
        fontsize=14.5, fontweight="bold", color=INK, ha="left", va="top")
ax.text(8.9, Y0 + 2.1 * RH,
        "Here the winning side is the 71 at Ask.\n\n"
        "Filter 40:  71 ≥ 40  → dot printed ✔\n"
        "Filter 100: 71 < 100 → NO dot ✘\n"
        "Filter 150: 71 < 150 → NO dot ✘\n\n"
        "It does NOT test 71+19, and NOT the whole\n"
        "level's 71+33... — only the 71.\n\n"
        "Why it exists: 12 vs 4 is also '3×' — but 12\n"
        "contracts is noise. The filter kills those dots.\n\n"
        "Your delta column can't show any of this:\n"
        "delta is vertical (same row), imbalance is\n"
        "diagonal (one row apart). Two different reads\n"
        "from the same Bid × Ask numbers.",
        fontsize=13, color=INK, ha="left", va="center", family="sans-serif",
        linespacing=1.45)

ax.text(1.0, 8.15, "One 5-minute bar's footprint — same numbers, three different reads",
        fontsize=16, fontweight="bold", color=INK)

out = str(Path(__file__).resolve().parents[4] / "scratchpad" / "imbalance_explainer.png")
fig.savefig(out, dpi=130, bbox_inches="tight", facecolor="#fcfcfa")
print("saved", out)
