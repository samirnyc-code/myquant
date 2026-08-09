"""Render N random ES days as a 2000-tick chart + Volume Profile + TPO/Market Profile.

Built for the PATs / auction-theory study: shows, per RTH session, the
2000-tick candles beside the volume profile (VP) and the time profile (TPO),
with POC / value-area / initial-balance marked. Source = data/ticks_continuous
(RTH-only ES ticks, DateTime/Price/Volume).

Outputs dated PNGs to data/profiles/charts/ and opens them in VSCode.

Usage:
  python scripts/pats_profile_charts.py            # 5 random days
  python scripts/pats_profile_charts.py --n 5 --ticks 2000 --seed 7
"""
import argparse
import glob
import os
import random
import string
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
TICKS = ROOT / "data" / "ticks_continuous"
OUT = ROOT / "data" / "profiles" / "charts"

# palette (dark, muted, trading-terminal)
BG, PANEL, INK, SOFT, GRID = "#0f1216", "#12171d", "#e8ecef", "#96a2ad", "#222a32"
UP, DN = "#4bbf8a", "#e0736b"
VPC, POCC, VAC, IBC = "#5ab6d0", "#e0873f", "#b98cd8", "#e0b45f"


def build_bars(df, ticks):
    """OHLCV bars of `ticks` trades each."""
    g = np.arange(len(df)) // ticks
    o = df.groupby(g).agg(t=("DateTime", "first"), O=("Price", "first"),
                          H=("Price", "max"), L=("Price", "min"),
                          C=("Price", "last"), V=("Volume", "sum"))
    return o.reset_index(drop=True)


def volume_profile(df, tick=0.25):
    """Volume-by-price series + POC (highest-volume price)."""
    row = (df["Price"] / tick).round() * tick
    vp = df.groupby(row)["Volume"].sum().sort_index()
    return vp, vp.idxmax()


def value_area(vp):
    """Dalton's volume value area (Mind Over Markets, Appendix 1).

    Start at the POC (highest-volume price). Compare the summed volume of the
    TWO prices directly above the current area to the TWO prices directly
    below; add the heavier *pair* to the value area. Repeat until 70% of total
    volume is enclosed. Volume-based (Dalton's primary method). Returns
    (val, poc, vah).
    """
    v = list(vp.values)
    prices = list(vp.index)
    n = len(v)
    poc = int(max(range(n), key=lambda k: v[k]))
    target = 0.70 * sum(v)
    lo = hi = poc
    acc = v[poc]
    while acc < target and (lo > 0 or hi < n - 1):
        up = (v[hi + 1] if hi + 1 < n else 0) + (v[hi + 2] if hi + 2 < n else 0)
        dn = (v[lo - 1] if lo - 1 >= 0 else 0) + (v[lo - 2] if lo - 2 >= 0 else 0)
        up_ok, dn_ok = hi < n - 1, lo > 0
        if up_ok and (up >= dn or not dn_ok):
            for _ in range(2):
                if hi < n - 1:
                    hi += 1; acc += v[hi]
        elif dn_ok:
            for _ in range(2):
                if lo > 0:
                    lo -= 1; acc += v[lo]
        else:
            break
    return prices[lo], prices[poc], prices[hi]


def developing_va(df, tick=0.25, bracket_min=30):
    """VAH/VAL of the *developing* value area at each 30-min bracket close."""
    t0 = df["DateTime"].iloc[0].floor("30min")
    out = []
    k = 1
    while True:
        te = t0 + pd.Timedelta(minutes=bracket_min * k)
        sub = df[df["DateTime"] <= te]
        if len(sub) < 50:
            k += 1
            if te > df["DateTime"].iloc[-1]:
                break
            continue
        vp, _ = volume_profile(sub, tick)
        val, _, vah = value_area(vp)
        out.append((te, val, vah))
        if te > df["DateTime"].iloc[-1]:
            break
        k += 1
    return out


def tpo(df, rowh=1.0, bracket_min=30):
    """Return {price_row: [bracket_indices...]} and letters count."""
    t0 = df["DateTime"].iloc[0].floor("30min")
    br = ((df["DateTime"] - t0).dt.total_seconds() // (bracket_min * 60)).astype(int)
    prow = np.floor(df["Price"] / rowh) * rowh
    seen = {}
    for b, p in zip(br.values, prow.values):
        seen.setdefault(p, set()).add(int(b))
    rows = {p: sorted(bs) for p, bs in seen.items()}
    nbr = int(br.max()) + 1
    return rows, nbr


def draw(day, df, ticks, rowh, prior=None):
    bars = build_bars(df, ticks)
    vp, poc = volume_profile(df)
    val, _, vah = value_area(vp)          # Dalton volume value area
    dev = developing_va(df)               # [(time, val, vah), ...]
    trows, nbr = tpo(df, rowh)
    # initial balance = first two 30-min brackets
    t0 = df["DateTime"].iloc[0].floor("30min")
    ib = df[df["DateTime"] < t0 + pd.Timedelta(minutes=60)]
    ibh, ibl = ib["Price"].max(), ib["Price"].min()
    lo, hi = df["Price"].min(), df["Price"].max()
    if prior:
        lo = min(lo, prior["val"]); hi = max(hi, prior["vah"])
    pad = (hi - lo) * 0.03

    fig = plt.figure(figsize=(15, 8.4), facecolor=BG)
    gs = fig.add_gridspec(1, 3, width_ratios=[6.2, 1.7, 2.4], wspace=0.04)
    axc = fig.add_subplot(gs[0]); axv = fig.add_subplot(gs[1], sharey=axc)
    axt = fig.add_subplot(gs[2], sharey=axc)
    for a in (axc, axv, axt):
        a.set_facecolor(PANEL)
        for s in a.spines.values():
            s.set_color(GRID)
        a.tick_params(colors=SOFT, labelsize=8)
    axc.set_ylim(lo - pad, hi + pad)

    # PRIOR-session value area = the reference zone you trade FROM (shaded)
    PRC, PRSH = "#a9c1dc", "#4d6f97"
    if prior:
        for a in (axc, axv, axt):
            a.axhspan(prior["val"], prior["vah"], color=PRSH, alpha=0.16, zorder=0)
        axc.axhline(prior["poc"], color=PRC, lw=1.1, ls="-", alpha=0.85, zorder=1)
        for lvl, lab, va_ in [(prior["vah"], "pVAH", "bottom"),
                              (prior["poc"], "pPOC", "center"),
                              (prior["val"], "pVAL", "top")]:
            axc.annotate(f"{lab} {lvl:g}", (0.6, lvl), color=PRC, fontsize=7.5,
                         va=va_, fontweight="bold", zorder=6)
    else:  # first day in archive: fall back to shading current VA
        for a in (axc, axv, axt):
            a.axhspan(val, vah, color=VAC, alpha=0.10, zorder=0)

    # current-day POC (orange) — the day's most-traded price
    for a in (axc, axv, axt):
        a.axhline(poc, color=POCC, lw=1.0, ls="-", alpha=0.8, zorder=1)
    # initial balance
    axc.axhline(ibh, color=IBC, lw=0.8, ls="--", alpha=0.5)
    axc.axhline(ibl, color=IBC, lw=0.8, ls="--", alpha=0.5)

    # CURRENT-day developing value area (dashed) — builds through the session
    bt = bars["t"].values
    xs = [min(max(int(np.searchsorted(bt, np.datetime64(te))), 0), len(bars) - 1)
          for te, _, _ in dev]
    if xs:
        axc.step(xs, [d[2] for d in dev], where="post", color=VAC, lw=1.35,
                 ls=(0, (5, 2)), alpha=0.95, zorder=4)
        axc.step(xs, [d[1] for d in dev], where="post", color=VAC, lw=1.35,
                 ls=(0, (5, 2)), alpha=0.95, zorder=4)

    # candles
    w = 0.34
    for i, r in bars.iterrows():
        c = UP if r.C >= r.O else DN
        axc.plot([i, i], [r.L, r.H], color=c, lw=0.6, zorder=2)
        axc.add_patch(Rectangle((i - w, min(r.O, r.C)), 2 * w, abs(r.C - r.O) or 0.05,
                                facecolor=c, edgecolor=c, lw=0.4, zorder=3))
    axc.set_xlim(-1, len(bars))
    # time x-ticks
    idx = np.linspace(0, len(bars) - 1, 7).astype(int)
    axc.set_xticks(idx)
    axc.set_xticklabels([bars.t.iloc[j].strftime("%H:%M") for j in idx])
    axc.set_title(f"{day}   ·   2000-tick candles   ·   {len(bars)} bars   ·   "
                  f"vol {int(df.Volume.sum()):,}", color=INK, fontsize=11,
                  loc="left", fontweight="bold", pad=10)
    axc.set_ylabel("ES price", color=SOFT, fontsize=9)
    axc.grid(True, color=GRID, lw=0.4, alpha=0.5)

    # volume profile (horizontal)
    prices = vp.index.values
    axv.barh(prices, vp.values, height=0.22, color=VPC, alpha=0.85,
             edgecolor="none")
    axv.barh([poc], [vp.max()], height=0.22, color=POCC)  # POC row
    axv.set_title("Volume Profile", color=INK, fontsize=10, loc="left")
    axv.tick_params(labelleft=False)
    axv.set_xticks([])
    axv.grid(True, axis="y", color=GRID, lw=0.3, alpha=0.4)

    # TPO profile (colored blocks per bracket)
    cmap = plt.cm.turbo(np.linspace(0.05, 0.95, nbr))
    maxlen = max(len(v) for v in trows.values())
    for p, bs in trows.items():
        for k, b in enumerate(bs):
            axt.add_patch(Rectangle((k, p - rowh / 2), 0.92, rowh * 0.92,
                          facecolor=cmap[b], edgecolor="none"))
    axt.set_xlim(0, maxlen + 1)
    axt.set_title("TPO / Market Profile", color=INK, fontsize=10, loc="left")
    axt.tick_params(labelleft=False)
    axt.set_xticks([])
    # labels for POC / VA / IB
    axt.annotate(f"POC {poc:g}", (maxlen + 0.6, poc), color=POCC, fontsize=8,
                 va="center", fontweight="bold")
    axt.annotate(f"VAH {vah:g}", (maxlen + 0.6, vah), color=VAC, fontsize=7.5, va="center")
    axt.annotate(f"VAL {val:g}", (maxlen + 0.6, val), color=VAC, fontsize=7.5, va="center")

    # legend line
    fig.text(0.012, 0.015,
             "PRIOR value area = trade-from zone (steel shaded) + pPOC · current POC "
             "(orange) · current developing VA (violet dashed, builds through the day) · "
             "initial balance (gold dash) · TPO by 30-min bracket (blue→red = early→late)",
             color=SOFT, fontsize=7.5)
    fig.subplots_adjust(left=0.05, right=0.925, top=0.92, bottom=0.07)
    OUT.mkdir(parents=True, exist_ok=True)
    fp = OUT / f"{day}_2kVP_TPO.png"
    fig.savefig(fp, dpi=130, facecolor=BG)
    plt.close(fig)
    return fp, dict(poc=float(poc), vah=float(vah), val=float(val),
                    ibh=float(ibh), ibl=float(ibl), bars=len(bars))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--rowh", type=float, default=1.0, help="TPO row height (points)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--days", nargs="*", help="explicit YYYY-MM-DD dates instead of random")
    args = ap.parse_args()
    files = sorted(glob.glob(str(TICKS / "*.parquet")))
    if args.days:
        picks = [str(TICKS / f"{d}.parquet") for d in args.days]
    else:
        if args.seed is not None:
            random.seed(args.seed)
        # only full sessions (>150k trades) so profiles are meaningful
        big = [f for f in files if os.path.getsize(f) > 1_500_000]
        picks = random.sample(big or files, min(args.n, len(big or files)))
    fidx = {f: i for i, f in enumerate(files)}

    def prior_levels(f):
        i = fidx.get(f, 0)
        if i == 0:
            return None
        pf = files[i - 1]
        pdf = pd.read_parquet(pf)
        vp, _ = volume_profile(pdf)
        val, poc, vah = value_area(vp)
        return {"val": val, "poc": poc, "vah": vah,
                "day": os.path.basename(pf).replace(".parquet", "")}

    made = []
    for f in sorted(picks):
        day = os.path.basename(f).replace(".parquet", "")
        df = pd.read_parquet(f).sort_values("DateTime").reset_index(drop=True)
        fp, stats = draw(day, df, args.ticks, args.rowh, prior=prior_levels(f))
        made.append((day, fp, stats))
        print(f"{day}: {stats['bars']} bars · POC {stats['poc']:g} · "
              f"VA {stats['val']:g}-{stats['vah']:g} · IB {stats['ibl']:g}-{stats['ibh']:g} "
              f"-> {fp}")
    print("\nPNGs:")
    for _, fp, _ in made:
        print(fp)


if __name__ == "__main__":
    main()
