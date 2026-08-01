"""Render CURRENT ES 15m in David Halsey's style for Monday 08/03/26 on 24-HOUR (ETH)
data — matching his 24H chart. His 07-31 read: EMA 8 (white) / 21 (cyan), his measured
move anchored to the REAL leg (100% low 7,446.50 -> 0% high 7,517.75 @ 07-31 04:15) with
his level colors + upper fib. Levels transcribed from his 07-31 slide.

Data: eminiaddict/data/es_5m_24h.parquet (24H, built from the ETH tick export), resampled
to 15m close-labeled (NT convention). Output: figures/monday_es.png
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SRC = "../data/es_5m_24h.parquet"
OUT = "../figures/monday_es.png"
BARS = 320                       # ~3.3 days of 24H 15m bars
FS = 12 * float(os.environ.get("EA_FONT_SCALE", 1.2))

# his measured-move anchors + levels (transcribed from the 07-31 slide)
HI_P, LO_P = 7517.75, 7446.50    # 0% high / 100% low
HI_TIME = "2026-07-31 04:15:00"  # bar (close-labeled) where 7517.75 printed
FIBS = [
    (7517.75, "#bbbbbb", ":", "0% (high)  7,517.75"),
    (7534.57, "#26a65b", "-", "-23.6% TARGET  7,534.57"),
    (7490.53, "#e08a2b", "--", "38.2%  7,490.53"),
    (7482.13, "#e3b341", "-", "50% HWB (entry)  7,482.13"),
    (7473.72, "#e2453c", "-", "61.8% FAILURE  7,473.72"),
    (7446.50, "#bbbbbb", ":", "100% (low)  7,446.50"),
    (7547.88, "#e2453c", "-", "61.8% (upper)  7,547.88"),
    (7521.88, "#e3b341", "-", "50% (upper)  7,521.88"),
]


def main():
    df = pd.read_parquet(SRC)[["DateTime", "Open", "High", "Low", "Close"]]
    # 24H 15m, CLOSE-labeled (NT convention: bar time = bar close)
    d15 = (df.set_index("DateTime").resample("15min", closed="left", label="right")
           .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"})
           .dropna().reset_index()).tail(BARS).reset_index(drop=True)
    n = len(d15)

    # anchor bars: high = the 7517.75 bar; low = most recent bar at/below 7446.50 before it
    hi_ts = pd.Timestamp(HI_TIME)
    hi_idx = int((d15.DateTime - hi_ts).abs().idxmin())
    pre = d15[(d15.index < hi_idx) & (d15.Low <= LO_P + 0.25)]
    lo_idx = int(pre.index.max()) if len(pre) else 0

    c = d15["Close"]
    ema8 = c.ewm(span=8).mean()
    ema21 = c.ewm(span=21).mean()

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
    ax.plot([lo_idx, hi_idx], [LO_P, HI_P], color="#888", ls="--", lw=1.3, zorder=5)
    ax.scatter([lo_idx, hi_idx], [LO_P, HI_P], color="#ffd400", s=70, zorder=7,
               edgecolor="white", lw=.6)

    # fib levels drawn FROM the leg forward (right), his colors + de-collided labels
    x0 = lo_idx
    LINE_END = n - 0.5
    labels = []
    for y, color, ls, lab in FIBS:
        ax.plot([x0, LINE_END], [y, y], color=color, lw=1.7 if ls == "-" else 1.1, ls=ls, zorder=5)
        labels.append({"y": y, "c": color, "t": lab})
    last = d15.Close.iloc[-1]
    ax.plot([0, LINE_END], [last, last], color="#4aa3ff", lw=0.8, ls="--", alpha=.6, zorder=5)
    labels.append({"y": last, "c": "#4aa3ff", "t": f"last  {last:,.2f}"})

    lo = min(d15.Low.min(), min(x["y"] for x in labels))
    hi = max(d15.High.max(), max(x["y"] for x in labels))
    span = hi - lo
    ax.set_ylim(lo - .03 * span, hi + .05 * span)
    ymax = ax.get_ylim()[1]
    gap = .028 * span * (FS / 12)
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
        ax.plot([LINE_END, n + 0.4], [d["y"], d["ty"]], color=d["c"], lw=0.7, alpha=.6,
                zorder=4, clip_on=False)
        ax.text(n + 1.0, d["ty"], d["t"], color=d["c"], va="center", fontsize=FS,
                fontweight="bold", clip_on=False)

    d_lo = d15.DateTime[lo_idx].strftime("%m/%d %H:%M")
    d_hi = d15.DateTime[hi_idx].strftime("%m/%d %H:%M")
    ax.set_title(
        "ES 15m (24H/ETH) — Monday 08/03/26, David Halsey's read (his 07-31 slide)\n"
        f"EMA 8/21 · MM leg {d_lo} 7,446.50 -> {d_hi} 7,517.75 (his anchors) · "
        "HWB 7,482 · fail 7,473.72 · target 7,534.57",
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
    print("wrote", OUT, "| bars", d15.DateTime.iloc[0], "..", d15.DateTime.iloc[-1],
          "| leg low", d15.DateTime[lo_idx], "-> high", d15.DateTime[hi_idx])


if __name__ == "__main__":
    main()
