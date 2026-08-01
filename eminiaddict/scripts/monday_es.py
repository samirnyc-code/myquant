"""ES 15m (24H) for Monday 08/03/26 — David Halsey's PRIMARY measured move, read straight
off his 07-31 video (his Fibonacci tool popup gives the exact anchors):
    Start 7324 @ 2026-07-29 16:22 (100% low)  ->  End 7446.50 @ 2026-07-30 10:22 (0% high)
Complete level set (his exact numbers, read off his axis):
    100% 7324 · 61.8% 7370.80 · 50% 7385.25 · 38.2% 7399.71 · 0% 7446.50 · -23.6% 7475.41
Price extended ABOVE the -23.6% (7475.41) -> that is his "line in the sand" / extension
trigger; above it the ES grinds up in extensions (gated by VIX < 18.85, DXY falling).

Fib is drawn ANCHORED to the actual bars (diagonal leg + all levels), not floated.
Data: eminiaddict/data/es_5m_24h.parquet (24H), 15m close-labeled (NT convention).
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SRC = "../data/es_5m_24h.parquet"
OUT = "../figures/monday_es.png"
FS = 12 * float(os.environ.get("EA_FONT_SCALE", 1.2))

# his exact anchors (from the fib-tool popup in the video)
LO_P, LO_T = 7324.0, "2026-07-29 16:22:00"     # 100%
HI_P, HI_T = 7446.5, "2026-07-30 10:22:00"     # 0%
# complete level set (price, color, style, label) — his colors
FIB = [
    (7324.00, "#cfcfcf", ":", "100%  7,324.00"),
    (7370.80, "#e2453c", "-", "61.8%  7,370.80"),
    (7385.25, "#e3b341", "-", "50%  7,385.25"),
    (7399.71, "#8a8f98", ":", "38.2%  7,399.71"),
    (7446.50, "#cfcfcf", ":", "0%  7,446.50"),
    (7475.41, "#26d07c", (0, (1, 1)), "-23.6% = LINE IN SAND  7,475.41"),
]


def main():
    df = pd.read_parquet(SRC)[["DateTime", "Open", "High", "Low", "Close"]]
    d15 = (df.set_index("DateTime").resample("15min", closed="left", label="right")
           .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
           .dropna().reset_index())
    # window: from a bit before the low anchor to the end
    a = d15.index[d15.DateTime >= pd.Timestamp(LO_T) - pd.Timedelta(hours=12)][0]
    d15 = d15.iloc[a:].reset_index(drop=True)
    n = len(d15)
    c = d15["Close"]
    ema8, ema21 = c.ewm(span=8).mean(), c.ewm(span=21).mean()
    last = c.iloc[-1]

    def bar_at(ts):
        return int((d15.DateTime - pd.Timestamp(ts)).abs().idxmin())
    lo_i, hi_i = bar_at(LO_T), bar_at(HI_T)

    fig, ax = plt.subplots(figsize=(16, 9), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for i in range(n):
        o, h, l, cl = d15.Open[i], d15.High[i], d15.Low[i], d15.Close[i]
        col = "#26a65b" if cl >= o else "#e2453c"
        ax.plot([i, i], [l, h], color=col, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, cl)), .6, abs(cl - o) or .02,
                               facecolor=col, edgecolor=col, zorder=3))
    ax.plot(range(n), ema8, color="#ededed", lw=1.3, zorder=4, label="EMA 8")
    ax.plot(range(n), ema21, color="#38c6d9", lw=1.3, zorder=4, label="EMA 21")

    # the measured-move LEG (anchors) + markers
    ax.plot([lo_i, hi_i], [LO_P, HI_P], color="#888", ls="--", lw=1.4, zorder=5)
    ax.scatter([lo_i, hi_i], [LO_P, HI_P], color="#ffd400", s=80, zorder=8,
               edgecolor="white", lw=.7)

    # complete fib level set, drawn FROM the leg forward
    labels = []
    for y, color, ls, lab in FIB:
        ax.plot([lo_i, n - 0.5], [y, y], color=color, lw=1.9 if "SAND" in lab else 1.5,
                ls=ls, zorder=6 if "SAND" in lab else 5)
        labels.append({"y": y, "c": color, "t": lab})
    ax.plot([0, n - 0.5], [last, last], color="#4aa3ff", lw=0.8, ls="--", alpha=.6, zorder=5)
    labels.append({"y": last, "c": "#4aa3ff", "t": f"last  {last:,.2f}"})

    lo = min(d15.Low.min(), min(x["y"] for x in labels))
    hi = max(d15.High.max(), max(x["y"] for x in labels))
    span = hi - lo
    ax.set_ylim(lo - .03 * span, hi + .05 * span)
    ymax = ax.get_ylim()[1]
    gap = .03 * span * (FS / 12)
    labels.sort(key=lambda d: d["y"])
    for d in labels:
        d["ty"] = d["y"]
    for k in range(1, len(labels)):
        if labels[k]["ty"] - labels[k - 1]["ty"] < gap:
            labels[k]["ty"] = labels[k - 1]["ty"] + gap
    over = labels[-1]["ty"] - (ymax - .01 * span)
    if over > 0:
        for d in labels:
            d["ty"] -= over
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1]["ty"] - labels[k]["ty"] < gap:
                labels[k]["ty"] = labels[k + 1]["ty"] - gap
    for d in labels:
        ax.plot([n - 0.5, n + 0.4], [d["y"], d["ty"]], color=d["c"], lw=0.7, alpha=.6,
                zorder=4, clip_on=False)
        ax.text(n + 1.0, d["ty"], d["t"], color=d["c"], va="center", fontsize=FS * .92,
                fontweight="bold", clip_on=False)

    ax.set_title(
        "ES 15m (24H) — Monday 08/03/26 · David Halsey's primary MM (exact from his 07-31 video)\n"
        f"leg 7,324 ({d15.DateTime[lo_i]:%m/%d %H:%M}) -> 7,446.50 ({d15.DateTime[hi_i]:%m/%d %H:%M}) · "
        "extended above -23.6% 7,475.41 = UP IN EXTENSIONS · above 7,475 bullish (VIX<18.85)",
        color="#eee", fontsize=FS * .95, loc="left")
    step = max(1, n // 12)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([d15.DateTime[i].strftime("%m/%d %H:%M") for i in range(0, n, step)],
                       color="#aaa", rotation=0, fontsize=FS * .72)
    ax.tick_params(colors="#aaa")
    for s in ax.spines.values():
        s.set_color("#333")
    ax.set_xlim(-1, n + 12)
    ax.grid(True, color="#141414", lw=0.5)
    ax.legend(loc="upper left", facecolor="#111", edgecolor="#333", labelcolor="#ccc")
    fig.tight_layout()
    fig.savefig(OUT, dpi=120, facecolor=fig.get_facecolor())
    print("wrote", OUT, "| leg", d15.DateTime[lo_i], LO_P, "->", d15.DateTime[hi_i], HI_P,
          "| last", last)


if __name__ == "__main__":
    main()
