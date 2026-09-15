"""tr_sr_prototype.py — CAUSAL / real-time prototype of trading-range + S/R + spring/upthrust
detection, so what it draws is exactly what TempoSpeedometer.cs could paint LIVE (no looking
to the right, no repainting).

Real-time rules:
  - Swing pivots CONFIRM with a p-bar delay: a high at bar k is only known at bar k+p (it must
    be the max of [k-p, k+p], all <= the current bar). We never use a pivot before it confirms.
  - A trading range becomes ACTIVE only once 2 confirmed highs (~equal = resistance) and 2
    confirmed lows (~equal = support) already exist to the LEFT. The box is drawn from that
    activation bar forward -- never back-filled.
  - Spring/upthrust fires on the CURRENT bar when it pokes beyond an already-established S/R and
    closes back inside (evaluated at bar close). Wyckoff type from depth+volume+range of that bar.
  - A close beyond S/R (by > tol) breaks the range (breakout/breakdown) and ends it.

    python tempo/scripts/tr_sr_prototype.py [YYYY-MM-DD] [pivot_strength] [maxwidth_mult]
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"


def tier_of(i, h, l, v, rng, up, lvl):
    avR = rng[max(0, i - 8):i].mean() if i > 0 else rng[i]
    avV = v[max(0, i - 8):i].mean() if i > 0 else v[i]
    pen = (h[i] - lvl) if up else (lvl - l[i])
    inten = ((pen / avR if avR > 0 else 1) + (v[i] / avV if avV > 0 else 1)
             + (rng[i] / avR if avR > 0 else 1)) / 3
    return 0 if inten <= 0.85 else (2 if inten >= 1.50 else 1)


def top_cluster(pivs, tol, take_high, min_sep):
    """from [(idx,price),...] return the level of the best cluster of >=2 pivots that are
    within tol in price AND at least min_sep bars apart in time (highest cluster if
    take_high else lowest), else None. The time-separation stops 2 adjacent wicks from
    faking a level."""
    if len(pivs) < 2:
        return None
    ordered = sorted(pivs, key=lambda pp: -pp[1] if take_high else pp[1])
    for a in range(len(ordered)):
        grp = [ordered[a]]
        for b in range(a + 1, len(ordered)):
            if abs(ordered[b][1] - ordered[a][1]) <= tol \
                    and all(abs(ordered[b][0] - m[0]) >= min_sep for m in grp):
                grp.append(ordered[b])
        if len(grp) >= 2:
            return float(np.mean([m[1] for m in grp]))
    return None


def causal_engine(o, h, l, c, v, p, max_width_mult, tol_mult=0.7, recent=150, min_sep=15):
    n = len(h); rng = h - l
    med = float(np.median(rng)); tol = tol_mult * med; max_width = max_width_mult * med
    conf_hi, conf_lo = [], []           # confirmed pivots (idx, price) -- all causal
    piv_hi, piv_lo = [], []
    ranges = []                         # (activation_bar, end_bar, S, R)
    events = []                         # (bar, is_up, tier, level)
    active = None                       # (act_bar, S, R)
    last_break = -1                     # a broken range can't re-form from pre-break pivots
    for t in range(n):
        k = t - p                       # candidate pivot bar, confirmable now
        if k - p >= 0:
            seg_h = h[k - p:t + 1]; seg_l = l[k - p:t + 1]   # window [k-p, k+p]=[k-p,t], all <= t
            if h[k] >= seg_h.max():
                conf_hi.append((k, h[k])); piv_hi.append(k)
            if l[k] <= seg_l.min():
                conf_lo.append((k, l[k])); piv_lo.append(k)
        if active is None:
            rh = [pp for pp in conf_hi if t - recent <= pp[0] and pp[0] > last_break]
            rl = [pp for pp in conf_lo if t - recent <= pp[0] and pp[0] > last_break]
            R = top_cluster(rh, tol, True, min_sep); S = top_cluster(rl, tol, False, min_sep)
            if R is not None and S is not None and 0 < R - S <= max_width:
                active = (t, S, R)
        else:
            act, S, R = active
            if c[t] > R + tol or c[t] < S - tol:     # breakout / breakdown -> range done
                ranges.append((act, t, S, R)); active = None; last_break = t
            else:
                if h[t] > R and c[t] <= R:           # upthrust: poke top, close back in
                    events.append((t, True, tier_of(t, h, l, v, rng, True, R), R))
                if l[t] < S and c[t] >= S:           # spring: poke bottom, close back in
                    events.append((t, False, tier_of(t, h, l, v, rng, False, S), S))
    if active is not None:
        ranges.append((active[0], n - 1, active[1], active[2]))
    return ranges, events, piv_hi, piv_lo, tol


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-11"
    p = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    mw = float(sys.argv[3]) if len(sys.argv) > 3 else 9.0
    df = pd.read_parquet(ENG); df = df[df.state >= 0]
    days = sorted(df.date.unique())
    prev = df[df.date == days[days.index(day) - 1]] if days.index(day) > 0 else None
    g = df[df.date == day].reset_index(drop=True)
    o, h, l, c = (g[x].to_numpy() for x in ("open", "high", "low", "close"))
    v = g["vol"].to_numpy(dtype=float)
    ranges, events, piv_hi, piv_lo, tol = causal_engine(o, h, l, c, v, p, mw)
    print(f"{day}: {len(ranges)} range(s), {len(events)} spring/upthrust event(s) "
          f"[real-time, {p}-bar pivot confirm delay]")

    fig, ax = plt.subplots(figsize=(17, 8.5), facecolor="#0d0d0d"); ax.set_facecolor("#0d0d0d")
    for i in range(len(g)):
        up = c[i] >= o[i]; col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.8, alpha=0.9, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.25,
                     facecolor=col, edgecolor=col, lw=0.3, zorder=3))
    if prev is not None:
        for lv, nm in ((prev.high.max(), "PDH"), (prev.low.min(), "PDL")):
            ax.axhline(lv, color="#6f8fb0", lw=0.9, ls=":", alpha=0.7, zorder=1)
            ax.annotate(nm, (len(g) - 1, lv), color="#6f8fb0", fontsize=8, family="monospace",
                        ha="right", va="bottom")
    for i in piv_hi:
        ax.plot(i, h[i], marker="v", color="#7a6fa0", ms=4, alpha=0.7, zorder=4)
    for i in piv_lo:
        ax.plot(i, l[i], marker="^", color="#7a6fa0", ms=4, alpha=0.7, zorder=4)
    # ranges drawn ONLY from activation forward (real-time)
    for (a, b, S, R) in ranges:
        ax.add_patch(Rectangle((a, S), b - a, R - S, facecolor="#ffd700", alpha=0.06,
                     edgecolor="none", zorder=1))
        for lv in (S, R):
            ax.plot([a, b], [lv, lv], color="#ffd700", lw=1.1, alpha=0.6, zorder=2)
        ax.annotate("TR active", (a, R), color="#ffd700", fontsize=7.5, family="monospace",
                    va="bottom", ha="left")
    spc = {0: "#4dd0a6", 1: "#ffd700", 2: "#ef5350"}; tl = {0: "3", 1: "2", 2: "1"}
    for (i, up, tr, lvl) in events:
        nm = ("UT" if up else "SP") + tl[tr]
        yv = h[i] if up else l[i]
        ax.annotate(nm, (i, yv), xytext=(0, 8 if up else -8), textcoords="offset points",
                    ha="center", va="bottom" if up else "top", color=spc[tr], fontsize=8,
                    fontweight="bold", family="monospace", zorder=7,
                    arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.1))
    ax.set_title(f"CAUSAL TR prototype  ·  {day}  ·  real-time, no look-ahead ({p}-bar pivot "
                 f"confirm)  ·  yellow=range from activation  ·  SP/UT=spring/upthrust",
                 color="#e8e6df", fontsize=10, family="monospace")
    ax.tick_params(colors="#8b877d")
    for s in ax.spines.values():
        s.set_color("#2c2c2a")
    ax.margins(x=0.01); ax.set_ylabel("ES price", color="#8b877d", family="monospace")
    fig.tight_layout()
    png = OUT / f"tr_sr_prototype_{day}.png"
    fig.savefig(png, dpi=110, facecolor="#0d0d0d"); print("wrote", png)


if __name__ == "__main__":
    main()
