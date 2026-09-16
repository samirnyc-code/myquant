"""wyckoff_ar.py — mark the Selling Climax + Automatic Rally range, comparing timeframes.

Answers "what does the AR range look like on 2k-tick vs 5M?" per the book (cites in
docs/research_notes/wyckoff_book_synthesis.md):
  - SC = climactic sell into the low; the extreme LOW = one range edge (p.78,84).
  - AR = "big move opposite the climax; volume high at start then declines" (p.83); its HIGH
    = the Creek/resistance edge (p.147).
  - Edges are ZONES "rather than a thin line" (p.154) — drawn wick→body: extreme→body cluster.

Data-driven per timeframe: build bars, Weis-wave zigzag, take the max-volume DOWN wave into
the session low as the SC and the UP wave that follows as the AR. Final marking is discretionary.

    python scripts/wyckoff_ar.py                                 # 2000t vs 5min, 9/15
    python scripts/wyckoff_ar.py --day 2026-09-15 --bars 2000t,5min --reversal 2.5
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
import tickdata as td
from weis_wave import zigzag, to_bars

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def hilo_bars(raw: pd.DataFrame, spec: str) -> pd.DataFrame:
    """to_bars gives close/high/low/vol; add open for candles (first price of each bar)."""
    b = to_bars(raw, spec).copy()
    r = raw.sort_values("DateTime").reset_index(drop=True)
    if spec.endswith("t"):
        n = int(spec[:-1])
        b["open"] = r.groupby(np.arange(len(r)) // n)["Price"].first().values[:len(b)]
    else:
        b["open"] = r.set_index("DateTime")["Price"].resample(spec).first().reindex(b.index).values
    return b


def analyze(bars: pd.DataFrame, reversal: float) -> dict:
    prices = bars["close"].to_numpy()
    piv = zigzag(prices, reversal)
    waves = []
    for s, e in zip(piv[:-1], piv[1:]):
        seg = bars.iloc[s:e + 1]
        waves.append(dict(s=s, e=e, up=prices[e] >= prices[s], vol=int(seg["vol"].sum()),
                          lo=float(seg["low"].min()), hi=float(seg["high"].max())))
    down = [w for w in waves if not w["up"]]
    # SC = the down-wave that reaches the session LOW — the climactic extreme that defines the
    # support edge (p.78,84). (The extreme, not the biggest wave, anchors the edge on any TF.)
    sc = min(down, key=lambda w: w["lo"])
    ar = next((w for w in waves if w["up"] and w["s"] >= sc["e"]), None)

    sc_seg = bars.iloc[sc["s"]:sc["e"] + 1]
    sc_body = float(sc_seg[["open", "close"]].min(axis=1).min())     # body cluster near the low
    out = dict(sc=sc, sc_low=sc["lo"], sc_body=sc_body, avg_dn=int(np.mean([w["vol"] for w in down])))
    if ar:
        ar_seg = bars.iloc[ar["s"]:ar["e"] + 1]
        half = max(1, len(ar_seg) // 2)
        out.update(ar=ar, ar_hi=ar["hi"],
                   ar_body=float(ar_seg[["open", "close"]].max(axis=1).max()),
                   ar_v1=int(ar_seg["vol"].iloc[:half].sum()), ar_v2=int(ar_seg["vol"].iloc[half:].sum()))
    return out


def render(ax, bars, a: dict, title: str):
    for i in range(len(bars)):
        r = bars.iloc[i]
        up = r["close"] >= r["open"]
        c = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [r["low"], r["high"]], color=c, lw=0.5, zorder=2)
        ax.add_patch(__import__("matplotlib").pyplot.Rectangle(
            (i - 0.4, min(r["open"], r["close"])), 0.8, max(abs(r["close"] - r["open"]), 0.01), color=c, zorder=3))
    ax.axhspan(a["sc_low"], a["sc_body"], color="#ef5350", alpha=0.13, zorder=1)
    ax.axhline(a["sc_low"], color="#c62828", lw=1.1, ls="--", label=f"SC low {a['sc_low']:.2f}")
    ax.axvspan(a["sc"]["s"], a["sc"]["e"], color="#ef5350", alpha=0.05, zorder=0)
    if "ar" in a:
        ax.axhspan(a["ar_body"], a["ar_hi"], color="#26a69a", alpha=0.13, zorder=1)
        ax.axhline(a["ar_hi"], color="#00897b", lw=1.1, ls="--", label=f"AR high {a['ar_hi']:.2f}")
        ax.axvspan(a["ar"]["s"], a["ar"]["e"], color="#26a69a", alpha=0.05, zorder=0)
    ax.set_title(title, fontsize=10); ax.legend(loc="upper right", fontsize=8); ax.grid(alpha=0.15)
    ax.set_xlabel("bar #"); ax.set_ylabel("price")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--bars", default="2000t,5min", help="comma list, e.g. 2000t,5min")
    ap.add_argument("--reversal", type=float, default=2.5)
    ap.add_argument("--eth", action="store_true")
    a = ap.parse_args()

    raw = td.load_eth(a.day) if a.eth else td.load_rth(a.day)
    specs = [s.strip() for s in a.bars.split(",")]

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, len(specs), figsize=(8 * len(specs), 8))
    if len(specs) == 1:
        axes = [axes]

    results = {}
    for spec, ax in zip(specs, axes):
        bars = hilo_bars(raw, spec)
        res = analyze(bars, a.reversal)
        results[spec] = (bars, res)
        render(ax, bars, res, f"{a.day} · {spec} · SC + AR")

    png = OUT / f"ar_compare_{a.day}_{'_'.join(specs)}.png"
    fig.suptitle(f"Selling Climax + Automatic Rally — {a.day} (reversal {a.reversal}pt)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97]); fig.savefig(png, dpi=110); plt.close(fig)

    # ---- inline comparison ----
    print(f"\n=== {a.day} · SC/AR range by timeframe (reversal {a.reversal}pt) ===\n")
    print(f"{'tf':<8}{'SC low':>9}{'SC body':>9}{'AR high':>9}{'AR body':>9}{'range':>8}"
          f"{'SC vol':>9}{'AR vol(1st/2nd)':>18}{'AR fades?':>11}")
    for spec in specs:
        bars, r = results[spec]
        if "ar" in r:
            fades = "yes" if r["ar_v1"] > r["ar_v2"] else "no"
            rng = r["ar_hi"] - r["sc_low"]
            arvol = f"{r['ar_v1']:,}/{r['ar_v2']:,}"
            print(f"{spec:<8}{r['sc_low']:>9.2f}{r['sc_body']:>9.2f}{r['ar_hi']:>9.2f}{r['ar_body']:>9.2f}"
                  f"{rng:>8.2f}{r['sc']['vol']:>9,}{arvol:>18}{fades:>11}")
        else:
            print(f"{spec:<8}{r['sc_low']:>9.2f}{r['sc_body']:>9.2f}{'—':>9}{'—':>9}{'—':>8}{r['sc']['vol']:>9,}")
    print("\nSUPPORT edge (SC low..body) and RESISTANCE edge (AR body..high) are drawn as ZONES "
          "(wick-to-body, book p.154), not thin lines.")
    print(f"\nchart: {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
