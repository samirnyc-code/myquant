"""l1_footprint_rth.py — RTH footprint + delta + CVD study from the L1 tape, with
auto-marked price/delta divergences and areas-of-interest (absorption, imbalance stacks).

Reads the aggressor-tagged L1 tape (A = buy lifting ask, B = sell hitting bid) and builds,
for a given RTH date:
  * 5M candles + per-bar footprint (volume-at-price split bid/ask) and bar POC
  * a footprint DELTA heatmap (price x time, net delta per cell) = where buying/selling stacked
  * per-bar delta panel  + cumulative delta (CVD) panel overlaid on price
  * AOIs marked on the chart:
      - ABSORPTION (effort-vs-result): large |bar delta| but price closes the OTHER way
      - CVD DIVERGENCE at swing pivots: price HH / CVD LH (bearish) or price LL / CVD HL (bullish)
      - stacked diagonal imbalances (3+ consecutive buy/sell imbalances in a bar)
  * a zoomed NUMERIC footprint (bid x ask per price) on the most active window

    python scripts/l1_footprint_rth.py --day 2026-09-16 --bar 5min
    python scripts/l1_footprint_rth.py --day 2026-09-16 --zoom 14:00 15:00

Outputs (dated) into data/l1_tape/_analysis/:
  footprint_rth_<day>_<bar>.png            (4-panel overview)
  footprint_rth_<day>_zoom.png             (numeric footprint on the AOI window)
  footprint_rth_<day>_bars.csv             (per-bar OHLC/buy/sell/delta/cvd/poc + flags)
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
L1 = ROOT / "data" / "l1_tape"
OUT = L1 / "_analysis"
TICK = 0.25
RTH_START = dt.time(8, 30)
RTH_END = dt.time(15, 15)


def load_rth(day: str) -> pd.DataFrame:
    # prefer parquet, else csv; front-month 12-26
    cand = list(L1.glob(f"ES_*_l1_{day}.parquet")) + list(L1.glob(f"ES_*_l1_{day}.csv"))
    if not cand:
        raise SystemExit(f"no L1 file for {day} in {L1}")
    # front-month = the file with the real tape (largest by size), not the pre-roll leg stub
    path = max(cand, key=lambda p: p.stat().st_size)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(
        path, low_memory=False, usecols=["Time", "Ev", "Price", "Size", "Aggr"])
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    t = df[df["Ev"] == "T"].dropna(subset=["Time"]).copy()
    t = t[(t["Time"].dt.time >= RTH_START) & (t["Time"].dt.time <= RTH_END)]
    t["Size"] = pd.to_numeric(t["Size"], errors="coerce").fillna(0).astype(int)
    t["Price"] = pd.to_numeric(t["Price"], errors="coerce")
    t = t.dropna(subset=["Price"])
    t["buy"] = np.where(t["Aggr"].astype(str) == "A", t["Size"], 0)   # aggressive buy @ ask
    t["sell"] = np.where(t["Aggr"].astype(str) == "B", t["Size"], 0)  # aggressive sell @ bid
    print(f"[load] {path.name}  RTH trades={len(t):,}  vol={t.Size.sum():,}  "
          f"range {t.Price.min():.2f}-{t.Price.max():.2f}")
    return t


def build_bars(t: pd.DataFrame, bar: str):
    t = t.copy()
    t["bar"] = t["Time"].dt.floor(bar)
    g = t.groupby("bar", sort=True)
    bars = pd.DataFrame({
        "open": g["Price"].first(), "high": g["Price"].max(),
        "low": g["Price"].min(), "close": g["Price"].last(),
        "vol": g["Size"].sum(), "buy": g["buy"].sum(), "sell": g["sell"].sum(),
    })
    bars["delta"] = bars["buy"] - bars["sell"]
    bars["cvd"] = bars["delta"].cumsum()
    # per-bar POC (price with max total vol), snapped to tick
    t["plevel"] = (t["Price"] / TICK).round() * TICK
    poc = t.groupby(["bar", "plevel"])["Size"].sum().reset_index()
    poc = poc.loc[poc.groupby("bar")["Size"].idxmax()].set_index("bar")["plevel"]
    bars["poc"] = poc
    bars = bars.reset_index()
    return bars, t


def swing_pivots(y: np.ndarray, k: int = 2):
    """indices of local highs/lows over +/-k bars."""
    hi, lo = [], []
    for i in range(k, len(y) - k):
        w = y[i - k:i + k + 1]
        if y[i] == w.max() and (w.argmax() == k):
            hi.append(i)
        if y[i] == w.min() and (w.argmin() == k):
            lo.append(i)
    return hi, lo


def detect_aois(bars: pd.DataFrame):
    aois = []
    body = bars["close"] - bars["open"]
    dmed = bars["delta"].abs().median()
    vmed = bars["vol"].median()
    # 1) ABSORPTION: strong delta but price result opposes it (effort vs result)
    for i, r in bars.iterrows():
        if r["vol"] < vmed:
            continue
        strong = abs(r["delta"]) > 1.3 * dmed
        if strong and r["delta"] > 0 and body[i] <= 0:      # buyers absorbed -> bearish
            aois.append((i, "absorption", "sellers absorb buying", r["high"]))
        elif strong and r["delta"] < 0 and body[i] >= 0:    # sellers absorbed -> bullish
            aois.append((i, "absorption", "buyers absorb selling", r["low"]))
    # 2) CVD divergence at swing pivots
    px = bars["close"].to_numpy(); cvd = bars["cvd"].to_numpy()
    hi, lo = swing_pivots(px, 2)
    for a, b in zip(hi, hi[1:]):
        if px[b] > px[a] and cvd[b] < cvd[a]:
            aois.append((b, "divergence", "price HH / CVD LH (bearish)", px[b]))
    for a, b in zip(lo, lo[1:]):
        if px[b] < px[a] and cvd[b] > cvd[a]:
            aois.append((b, "divergence", "price LL / CVD HL (bullish)", px[b]))
    return aois


def render_overview(bars, day, bar, aois, png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    n = len(bars)
    fig = plt.figure(figsize=(max(16, n * 0.34), 15))
    gs = GridSpec(4, 1, height_ratios=[3.2, 1.5, 1.1, 1.6], hspace=0.12)
    x = np.arange(n)
    axc = fig.add_subplot(gs[0]); axh = fig.add_subplot(gs[1], sharex=axc)
    axd = fig.add_subplot(gs[2], sharex=axc); axv = fig.add_subplot(gs[3], sharex=axc)

    # --- candles + POC + AOIs
    for i, r in bars.iterrows():
        up = r["close"] >= r["open"]; c = "#26a69a" if up else "#ef5350"
        axc.plot([i, i], [r["low"], r["high"]], color=c, lw=.8, zorder=3)
        axc.add_patch(plt.Rectangle((i - .3, min(r.open, r.close)), .6,
                      max(abs(r.close - r.open), TICK / 2), color=c, zorder=4))
        axc.plot(i, r["poc"], "o", ms=3, color="#f9a825", zorder=6)  # POC
    for i, kind, label, ypx in aois:
        col = "#8e24aa" if kind == "divergence" else "#1565c0"
        off = 8 if "bear" in label or "sellers" in label else -8
        axc.annotate(label, (i, ypx), xytext=(i, ypx + off), fontsize=7.5,
                     ha="center", color=col, fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=col, lw=1))
    axc.set_title(f"ES 12-26 · {day} RTH · {bar} footprint study  "
                  f"(POC=gold · absorption=blue · divergence=purple)", fontsize=12)
    axc.set_ylabel("price"); axc.grid(alpha=.15)

    # --- footprint DELTA heatmap (price 1pt buckets x bar), net delta per cell
    axh.set_ylabel("delta@price (1pt)")
    axh.text(.005, .92, "footprint delta heatmap — green=net buy, red=net sell at that price",
             transform=axh.transAxes, fontsize=8, color="#555")

    # --- per-bar delta
    axd.bar(x, bars["delta"], color=np.where(bars["delta"] >= 0, "#26a69a", "#ef5350"), width=.7)
    axd.axhline(0, color="#888", lw=.6); axd.set_ylabel("bar delta"); axd.grid(alpha=.15)

    # --- CVD + price overlay
    axv.plot(x, bars["cvd"], color="#3949ab", lw=1.6, label="CVD")
    axv.set_ylabel("CVD", color="#3949ab"); axv.grid(alpha=.15)
    axp = axv.twinx(); axp.plot(x, bars["close"], color="#455a64", lw=1, ls="--", label="close")
    axp.set_ylabel("price", color="#455a64")
    # label x with times
    ticks = list(range(0, n, max(1, n // 14)))
    axv.set_xticks(ticks)
    axv.set_xticklabels([pd.Timestamp(bars["bar"].iloc[i]).strftime("%H:%M") for i in ticks],
                        rotation=0, fontsize=8)
    axv.set_xlabel("time (CT)")
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)


def render_heatmap_into(bars, tape, day, bar, png):
    """Full render incl. the delta heatmap cells (done in one pass over tape)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    from matplotlib.colors import TwoSlopeNorm
    n = len(bars)
    barlist = list(bars["bar"])
    bar_ix = {b: i for i, b in enumerate(barlist)}
    tape = tape.copy()
    tape["p1"] = np.floor(tape["Price"]).astype(int)  # 1pt bucket
    fp = tape.groupby(["bar", "p1"]).agg(buy=("buy", "sum"), sell=("sell", "sum")).reset_index()
    fp["d"] = fp["buy"] - fp["sell"]
    pmin, pmax = int(tape["p1"].min()), int(tape["p1"].max())
    rows = pmax - pmin + 1
    grid = np.full((rows, n), np.nan)
    for _, r in fp.iterrows():
        grid[int(r["p1"]) - pmin, bar_ix[r["bar"]]] = r["d"]

    fig = plt.figure(figsize=(max(16, n * 0.34), 16))
    gs = GridSpec(4, 1, height_ratios=[3.0, 2.2, 1.0, 1.5], hspace=0.14)
    x = np.arange(n)
    axc = fig.add_subplot(gs[0]); axh = fig.add_subplot(gs[1], sharex=axc)
    axd = fig.add_subplot(gs[2], sharex=axc); axv = fig.add_subplot(gs[3], sharex=axc)

    aois = detect_aois(bars)
    for i, r in bars.iterrows():
        up = r["close"] >= r["open"]; c = "#26a69a" if up else "#ef5350"
        axc.plot([i, i], [r["low"], r["high"]], color=c, lw=.8, zorder=3)
        axc.add_patch(plt.Rectangle((i - .3, min(r.open, r.close)), .6,
                      max(abs(r.close - r.open), TICK / 2), color=c, zorder=4))
        axc.plot(i, r["poc"], "o", ms=3, color="#f9a825", zorder=6)
    for i, kind, label, ypx in aois:
        col = "#8e24aa" if kind == "divergence" else "#1565c0"
        off = (r["high"] - r["low"]); off = 6
        axc.annotate(label, (i, ypx), xytext=(i, ypx + (off if ("bear" in label or "sellers" in label) else -off)),
                     fontsize=7, ha="center", color=col, fontweight="bold",
                     arrowprops=dict(arrowstyle="->", color=col, lw=1), zorder=8)
    axc.set_ylabel("price"); axc.grid(alpha=.15)
    axc.set_title(f"ES 12-26 · {day} RTH · {bar} footprint study "
                  f"(POC=gold · absorption=blue · CVD-divergence=purple)", fontsize=12)

    vmax = np.nanpercentile(np.abs(grid), 98) or 1
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)
    im = axh.imshow(grid, aspect="auto", origin="lower", cmap="RdYlGn", norm=norm,
                    extent=[-.5, n - .5, pmin, pmax + 1], interpolation="nearest")
    axh.set_ylabel("delta @ price (1pt)")
    axh.text(.004, .96, "footprint delta heatmap — green=net buying / red=net selling stacked at that price",
             transform=axh.transAxes, fontsize=8, color="#333", va="top")
    fig.colorbar(im, ax=axh, pad=.005, fraction=.02, label="net delta")

    axd.bar(x, bars["delta"], color=np.where(bars["delta"] >= 0, "#26a69a", "#ef5350"), width=.7)
    axd.axhline(0, color="#888", lw=.6); axd.set_ylabel("bar delta"); axd.grid(alpha=.15)

    axv.plot(x, bars["cvd"], color="#3949ab", lw=1.7, label="CVD")
    axv.set_ylabel("CVD", color="#3949ab"); axv.grid(alpha=.15)
    axp = axv.twinx(); axp.plot(x, bars["close"], color="#455a64", lw=1.1, ls="--")
    axp.set_ylabel("price", color="#455a64")
    ticks = list(range(0, n, max(1, n // 14)))
    axv.set_xticks(ticks)
    axv.set_xticklabels([pd.Timestamp(barlist[i]).strftime("%H:%M") for i in ticks], fontsize=8)
    axv.set_xlabel("time (CT)")
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)
    return aois


def render_zoom(tape, bars, day, z0, z1, png):
    """numeric footprint (bid x ask per tick) for the [z0,z1) window."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = pd.Timestamp(f"{day} ")
    t0 = pd.Timestamp(f"{day} {z0}"); t1 = pd.Timestamp(f"{day} {z1}")
    ZB = 1.0  # bucket footprint to 1pt for a legible numeric grid over a trend window
    w = tape[(tape["Time"] >= t0) & (tape["Time"] < t1)].copy()
    w["lvl"] = np.floor(w["Price"] / ZB) * ZB
    barlist = sorted(w["bar"].unique())
    fp = w.groupby(["bar", "lvl"]).agg(buy=("buy", "sum"), sell=("sell", "sum")).reset_index()
    pmin, pmax = w["lvl"].min(), w["lvl"].max()
    levels = np.round(np.arange(pmin, pmax + ZB, ZB), 2)
    nb = len(barlist)
    fig, ax = plt.subplots(figsize=(max(12, nb * 1.5), max(8, len(levels) * 0.22)))
    bx = {b: i for i, b in enumerate(barlist)}
    # per-bar totals for POC + delta
    for b in barlist:
        i = bx[b]
        sub = fp[fp["bar"] == b]
        poc = sub.loc[(sub["buy"] + sub["sell"]).idxmax(), "lvl"] if len(sub) else None
        for _, r in sub.iterrows():
            y = r["lvl"]; d_ = r["buy"] - r["sell"]
            imb = ""
            # diagonal imbalance vs the opposing side one bucket away (buy@y vs sell@y-1pt)
            selldn = sub.loc[sub["lvl"] == round(y - ZB, 2), "sell"]
            buyup = sub.loc[sub["lvl"] == round(y + ZB, 2), "buy"]
            if len(selldn) and r["buy"] >= 3 * max(selldn.iloc[0], 1):
                imb = "b"
            if len(buyup) and r["sell"] >= 3 * max(buyup.iloc[0], 1):
                imb = "s"
            bg = "#e0f2e9" if d_ > 0 else "#fae1e4" if d_ < 0 else "#f0f0f0"
            if y == poc:
                bg = "#fff3c4"
            ax.add_patch(plt.Rectangle((i - .48, y - ZB / 2), .96, ZB, color=bg, zorder=1))
            txt = f"{int(r['sell'])}×{int(r['buy'])}"
            col = "#1b7a4b" if imb == "b" else "#b3283a" if imb == "s" else "#333"
            fw = "bold" if imb else "normal"
            ax.text(i, y, txt, ha="center", va="center", fontsize=6.5, color=col,
                    fontweight=fw, zorder=3)
    ax.set_xlim(-.6, nb - .4); ax.set_ylim(pmin - ZB, pmax + ZB)
    ax.set_xticks(range(nb))
    ax.set_xticklabels([pd.Timestamp(b).strftime("%H:%M") for b in barlist])
    ax.set_ylabel("price"); ax.set_xlabel("time (CT)  —  cells = sell×buy volume")
    ax.set_title(f"ES 12-26 · {day} · numeric footprint {z0}-{z1} CT  "
                 f"(gold=bar POC · bold green=buy-imbalance · bold red=sell-imbalance)", fontsize=11)
    ax.grid(axis="x", alpha=.1)
    fig.savefig(png, dpi=110, bbox_inches="tight"); plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-16")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--zoom", nargs=2, default=["13:30", "15:00"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    t = load_rth(a.day)
    bars, tape = build_bars(t, a.bar)

    over = OUT / f"footprint_rth_{a.day}_{a.bar}.png"
    aois = render_heatmap_into(bars, tape, a.day, a.bar, over)
    zoom = OUT / f"footprint_rth_{a.day}_zoom.png"
    render_zoom(tape, bars, a.day, a.zoom[0], a.zoom[1], zoom)

    # flag bars + save
    flags = {i: [] for i in range(len(bars))}
    for i, kind, label, _ in aois:
        flags[i].append(f"{kind}:{label}")
    bars["aoi"] = [" | ".join(flags[i]) for i in range(len(bars))]
    csv = OUT / f"footprint_rth_{a.day}_bars.csv"
    bars.to_csv(csv, index=False)

    print("\n=== AOIs detected ===")
    for i, kind, label, ypx in aois:
        print(f"  {pd.Timestamp(bars['bar'].iloc[i]).strftime('%H:%M')}  {kind:11s} {label}  @~{ypx:.2f}")
    print(f"\ncharts: {over}\n        {zoom}\n bars:  {csv}")
    for p in (over, zoom):
        try:
            subprocess.Popen(["code", "-r", str(p)], shell=True)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
