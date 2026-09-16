"""wyckoff_phases.py — mark the whole Trading Range + Phases A-E on one session.

Builds on wyckoff_ar.py: once the SC (support edge) and AR (resistance edge) are found, the
range is set and the session partitions into the book's phases (p.134-144):
  A = stopping action  (PS · SC · AR · ST) — ends at the ST
  B = building cause   (oscillation inside the range; UA/upthrust-action; ST-as-SOW)
  C = the test         (Spring/UTAD = false break of an edge that MUST reverse) — may be ABSENT
  D = trend in range   (SOS/SOW + LPS/LPSY after Phase C)
  E = out of range     (markup/markdown beyond the edge)

Events are derived from the Weis-wave structure (transparent, not hand-placed); the drawing is
a discretionary aid, not gospel (book p.169/250 — read dynamics, don't robot-label).

    python scripts/wyckoff_phases.py --day 2026-09-15 --bar 5min --reversal 2.5
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
from weis_wave import zigzag
from wyckoff_ar import hilo_bars

OUT = ROOT / "data" / "l1_tape" / "_analysis"


def build_waves(bars, reversal):
    prices = bars["close"].to_numpy()
    piv = zigzag(prices, reversal)
    W = []
    for s, e in zip(piv[:-1], piv[1:]):
        seg = bars.iloc[s:e + 1]
        lo_bar = s + int(np.argmin(seg["low"].to_numpy()))    # EXACT bar of the intrabar low
        hi_bar = s + int(np.argmax(seg["high"].to_numpy()))    # EXACT bar of the intrabar high
        W.append(dict(s=s, e=e, up=prices[e] >= prices[s], vol=int(seg["vol"].sum()),
                      lo=float(seg["low"].min()), hi=float(seg["high"].max()),
                      lo_bar=lo_bar, hi_bar=hi_bar, p0=float(prices[s]), p1=float(prices[e])))
    return W


def derive(bars, W, reversal):
    """Return the key events + phase boundaries, derived from the waves."""
    downs = [w for w in W if not w["up"]]
    sc = min(downs, key=lambda w: w["lo"])                      # climax = lowest low
    sc_low = sc["lo"]
    ar = next((w for w in W if w["up"] and w["s"] >= sc["e"]), None)   # first rally after SC
    ev = {"SC": sc, "AR": ar}

    # PS (preliminary support) = the last notable UP wave BEFORE the SC (a bounce in the fall)
    ups_before = [w for w in W if w["up"] and w["e"] <= sc["s"]]
    ev["PS"] = ups_before[-1] if ups_before else None

    ar_hi = ar["hi"] if ar else sc_low
    after_ar = [w for w in W if w["s"] >= (ar["e"] if ar else sc["e"])]
    # ST = first DOWN wave after the AR that holds above the SC low on volume < SC
    ev["ST"] = next((w for w in after_ar if not w["up"] and w["lo"] > sc_low + 0.01
                     and w["vol"] < sc["vol"]), None)
    # SOS = the highest-volume UP wave after the AR that closes above the AR high (breakout up)
    up_after = [w for w in after_ar if w["up"] and w["p1"] > ar_hi]
    ev["SOS"] = max(up_after, key=lambda w: w["vol"]) if up_after else None
    # LPS = the last DOWN wave (higher low) right before the SOS
    if ev["SOS"]:
        pre = [w for w in W if not w["up"] and w["e"] <= ev["SOS"]["s"] and w["lo"] > sc_low]
        ev["LPS"] = pre[-1] if pre else None
    else:
        ev["LPS"] = None
    # Spring (Phase C) = any wave that breaks BELOW the SC low then price reclaims. Check.
    ev["SPRING"] = next((w for w in after_ar if w["lo"] < sc_low - 0.01), None)

    # range top = AR high extended by Phase B highs (Creek, p.147), capped before the SOS
    b_end = ev["SOS"]["s"] if ev["SOS"] else len(bars) - 1
    phaseB_hi = max([w["hi"] for w in W if (ar["e"] if ar else sc["e"]) <= w["s"] < b_end] or [ar_hi])
    ev["range_low"] = sc_low
    ev["range_top_ar"] = ar_hi
    ev["range_top_ext"] = phaseB_hi

    # ALL tests of support (not just one ST): a real test PROBES DOWN toward support — it must
    # reach the LOWER THIRD of the range (book classifies tests by the third they end in, p.90).
    # A dip that only reaches mid-range is a range rotation, not a test of the low. Real trading
    # never has a single clean ST — the low gets probed repeatedly (that IS Phase B).
    lower_third = sc_low + (phaseB_hi - sc_low) / 3.0
    start_b = ar["e"] if ar else sc["e"]
    stop_b = ev["SOS"]["s"] if ev["SOS"] else len(bars)
    tests = [w for w in W if (not w["up"]) and start_b <= w["s"] < stop_b and w["lo"] <= lower_third]
    ev["tests"] = tests
    ev["lower_third"] = lower_third
    return ev


def ext_bar(w, key):
    """Exact bar index of the labelled extreme (fixes the close-pivot off-by-one)."""
    return w["lo_bar"] if key == "lo" else w["hi_bar"] if key == "hi" else (w["e"] if key == "p1" else w["s"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-15")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--reversal", type=float, default=2.5)
    ap.add_argument("--eth", action="store_true")
    a = ap.parse_args()

    raw = td.load_eth(a.day) if a.eth else td.load_rth(a.day)
    bars = hilo_bars(raw, a.bar)
    W = build_waves(bars, a.reversal)
    ev = derive(bars, W, a.reversal)

    def bx(w, which="e"):
        return None if w is None else w[which]

    # phase boundaries (bar indices)
    scb, arb = ev["SC"]["e"], bx(ev["AR"]) or ev["SC"]["e"]
    stb = bx(ev["ST"]) or arb
    sosb = ev["SOS"]["s"] if ev["SOS"] else len(bars) - 1
    n = len(bars)
    phases = [("A", 0, stb, "#90a4ae"), ("B", stb, sosb, "#b0bec5"),
              ("D", sosb, n - 1, "#a5d6a7"), ("E", n - 1, n - 1, "#66bb6a")]

    # ---- inline report ----
    print(f"\n=== {a.day} · {a.bar} · Trading Range + Phases (reversal {a.reversal}pt) ===")
    print(f"TR support (SC low)          {ev['range_low']:.2f}")
    print(f"TR resistance (AR high)      {ev['range_top_ar']:.2f}   extended by Phase B to {ev['range_top_ext']:.2f}")
    def show(tag, w, price_key):
        if w is None:
            print(f"  {tag:<5} —  (not present)"); return
        t = bars.index[w["e"] if price_key == "p1" else w["s"]]
        print(f"  {tag:<5} {w[price_key]:.2f}  @ {pd.Timestamp(t):%H:%M}  vol {w['vol']:,}")
    show("PS", ev["PS"], "p1")
    show("SC", ev["SC"], "lo") if False else print(f"  {'SC':<5} {ev['SC']['lo']:.2f}  @ {pd.Timestamp(bars.index[ev['SC']['e']]):%H:%M}  vol {ev['SC']['vol']:,}  (CLIMAX)")
    show("AR", ev["AR"], "hi")
    show("ST", ev["ST"], "lo")
    print(f"  {'C':<5} " + ("SPRING at %.2f" % ev["SPRING"]["lo"] if ev["SPRING"] else "NO spring - price never broke the SC low; Phase C effectively absent (went straight B->D via LPS)"))
    show("LPS?", ev["LPS"], "lo")
    print("        ^ 'LPS' is RETROACTIVE only — in real time it is just another test; it is not")
    print("          knowable as the LAST one until the SOS confirms and price does not return.")
    show("SOS", ev["SOS"], "p1")
    print(f"  close {float(bars['close'].iloc[-1]):.2f}  ({'ABOVE range top = Phase E markup' if float(bars['close'].iloc[-1])>ev['range_top_ext'] else 'inside/at range'})")

    # every test of the low, in sequence, with volume — this is what you actually watch live
    print(f"\nTESTS of the low (the range's lower half) — {len(ev['tests'])} of them, not one ST:")
    print(f"  {'#':<4}{'time':>7}{'low':>10}{'vol':>10}   volume vs prior test")
    prev = None
    for k, w in enumerate(ev["tests"], 1):
        ts = pd.Timestamp(bars.index[ext_bar(w, 'lo')]).strftime("%H:%M")
        trend = "" if prev is None else ("lighter (absorption)" if w["vol"] < prev else "heavier (supply)")
        print(f"  t{k:<3}{ts:>7}{w['lo']:>10.2f}{w['vol']:>10,}   {trend}")
        prev = w["vol"]

    # ---- annotated chart ----
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(16, 8))
    for i in range(n):
        r = bars.iloc[i]; up = r["close"] >= r["open"]; c = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [r["low"], r["high"]], color=c, lw=0.6, zorder=3)
        ax.add_patch(plt.Rectangle((i - 0.4, min(r["open"], r["close"])), 0.8,
                                   max(abs(r["close"] - r["open"]), 0.01), color=c, zorder=4))
    # TR box
    ax.axhspan(ev["range_low"], ev["range_top_ext"], color="#42a5f5", alpha=0.06, zorder=0)
    ax.axhline(ev["range_low"], color="#c62828", lw=1.3, ls="--", zorder=2)
    ax.axhline(ev["range_top_ar"], color="#00897b", lw=1.1, ls="--", zorder=2)
    ax.axhline(ev["range_top_ext"], color="#00897b", lw=0.9, ls=":", zorder=2)
    ax.text(1, ev["range_low"], " SC low / support %.2f" % ev["range_low"], color="#c62828", fontsize=8, va="bottom")
    ax.text(1, ev["range_top_ar"], " AR high %.2f" % ev["range_top_ar"], color="#00897b", fontsize=8, va="bottom")
    ax.text(1, ev["range_top_ext"], " Creek (Phase-B high) %.2f" % ev["range_top_ext"], color="#00897b", fontsize=8, va="bottom")
    # phase bands
    for tag, x0, x1, col in phases:
        if x1 <= x0:
            continue
        ax.axvspan(x0, x1, color=col, alpha=0.10, zorder=0)
        ax.text((x0 + x1) / 2, ax.get_ylim()[1], f"Phase {tag}", ha="center", va="top",
                fontsize=11, color="#37474f", fontweight="bold")
    # all tests of the low (t1..tn) drawn small; the labelled ST / LPS are just two of them
    for k, w in enumerate(ev["tests"], 1):
        ax.annotate(f"t{k}", (ext_bar(w, "lo"), w["lo"]), fontsize=7, color="#5d4037",
                    xytext=(ext_bar(w, "lo"), w["lo"] - 1.5), ha="center")

    # event markers — placed at the EXACT extreme bar (not the close pivot)
    def mark(tag, w, key, dy):
        if w is None:
            return
        i = ext_bar(w, key); price = w[key]
        ax.annotate(tag, (i, price), fontsize=9, fontweight="bold", color="#263238",
                    xytext=(i, price + dy), ha="center",
                    arrowprops=dict(arrowstyle="->", color="#263238", lw=0.8))
    mark("PS", ev["PS"], "p1", 3)
    mark("SC", ev["SC"], "lo", -4)
    mark("AR", ev["AR"], "hi", 3)
    mark("ST(t1)", ev["ST"], "lo", -3)
    mark("LPS?", ev["LPS"], "lo", -3)      # only confirmed retroactively — hence the "?"
    mark("SOS", ev["SOS"], "p1", 3)
    ax.set_title(f"{a.day} · {a.bar} · Wyckoff TR + Phases A-E  (reversal {a.reversal}pt)", fontsize=12)
    ax.set_ylabel("price"); ax.set_xlabel(f"{a.bar} bar #"); ax.grid(alpha=0.15)
    png = OUT / f"phases_{a.day}_{'eth' if a.eth else 'rth'}_{a.bar}.png"
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    print(f"\nchart: {png}")
    try:
        subprocess.Popen(["code", "-r", str(png)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
