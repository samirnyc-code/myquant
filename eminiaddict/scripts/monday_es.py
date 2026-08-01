"""ES 15m (24H) for Monday 08/03/26 — David Halsey's ACTUAL read from his 07-31 video
(transcribed), NOT a guessed traditional MM.

His read: the ES is going UP IN EXTENSIONS. The extension-failure level is right at the
gap fill and his bullish "LINE IN THE SAND" is 7473-75 ("everything above it is bullish").
Above it = extensions grind higher toward the upside targets; a break = the extension
fails -> swing high -> new series of shorts down into the larger downtrend. Gated by the
multi-market signals: stays bullish while VIX holds below 18.85 and DXY keeps falling in
extensions. Resistance levels are drawn from the mid-July highs->lows that price is running
into. Data: eminiaddict/data/es_5m_24h.parquet (24H), 15m close-labeled (NT convention).
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SRC = "../data/es_5m_24h.parquet"
OUT = "../figures/monday_es.png"
BARS = 320
FS = 12 * float(os.environ.get("EA_FONT_SCALE", 1.2))

SAND_LO, SAND_HI = 7473.0, 7475.0     # "line in the sand" zone (extension failure)
# horizontal levels he named / drew (price, color, style, label)
LEVELS = [
    (7547.88, "#e2453c", "-", "upper 61.8% / next resistance  7,547.88"),
    (7534.57, "#26a65b", "-", "extension target (-23.6%)  7,534.57"),
    (7521.88, "#e3b341", "--", "upper 50%  7,521.88"),
    (7517.75, "#bbbbbb", ":", "swing high (running into resistance)  7,517.75"),
    (7490.53, "#8a8f98", ":", "38.2%  7,490.53"),
]


def main():
    df = pd.read_parquet(SRC)[["DateTime", "Open", "High", "Low", "Close"]]
    d15 = (df.set_index("DateTime").resample("15min", closed="left", label="right")
           .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
           .dropna().reset_index()).tail(BARS).reset_index(drop=True)
    n = len(d15)
    c = d15["Close"]
    ema8, ema21 = c.ewm(span=8).mean(), c.ewm(span=21).mean()
    last = c.iloc[-1]

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

    # THE line in the sand (extension failure) — shaded zone, the centerpiece
    ax.axhspan(SAND_LO, SAND_HI, color="#e2453c", alpha=.28, zorder=3)
    ax.axhline(SAND_HI, color="#e2453c", lw=2.0, zorder=5)

    labels = [{"y": (SAND_LO + SAND_HI) / 2, "c": "#ff6a5e",
               "t": "LINE IN SAND 7,473-75 (ext fail)"}]
    for y, color, ls, lab in LEVELS:
        ax.plot([0, n - 0.5], [y, y], color=color, lw=1.6 if ls == "-" else 1.0, ls=ls, zorder=5)
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
        "ES 15m (24H) — Monday 08/03/26 · David Halsey's read (his 07-31 video)\n"
        "UP IN EXTENSIONS · above 7,473-75 = bullish, grind toward 7,534.57 / 7,547.88 · "
        "break = extension fails -> shorts · gate: VIX < 18.85, DXY falling",
        color="#eee", fontsize=FS, loc="left")
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
    print("wrote", OUT, "| last bar", d15.DateTime.iloc[-1], "close", last)


if __name__ == "__main__":
    main()
