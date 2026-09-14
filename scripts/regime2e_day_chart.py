"""Render one day as the Regime2E strategy sees it: 5-min candles + TREND (regime)
shading + SMA20 gate + every 2E signal with its gate decision + valid entries/stops.

  python scripts/regime2e_day_chart.py 2026-05-19
Output: reports/regime2e/day_<date>.png
"""
import sys
from bisect import bisect_right
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

TICK = 0.25; RETEST_T = 6; FILL_T = 7; CANCEL_BARS = 6
STOP_MULT = 0.30; STOP_FLOOR_T = 8; GAP_MAX = 0.54; SMA_N = 20; ADR_N = 10; TREND_MULT = 1.6
GOOD_HOURS = {9, 10, 11, 12, 13}
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "reports" / "regime2e"
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, r"C:\Users\Admin\myquant-regime\scripts")
from regime2e_nt_diff import day_frames                          # noqa: E402
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def context(date):
    b = pd.read_parquet(REPO / "data" / "bars" / "_db_es_5m_rth.parquet")
    b["d"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("d").agg(C=("Close", "last"), H=("High", "max"), L=("L" if False else "Low", "min")).reset_index().sort_values("d").reset_index(drop=True)
    g["rng"] = g.H - g.L
    g["sma20"] = g.C.rolling(SMA_N).mean().shift(1)
    g["adr10"] = g.rng.rolling(ADR_N).mean().shift(1)
    g["adr_before_prev"] = g.adr10.shift(1)
    i = g.index[g.d == date][0]
    row = g.loc[i]; prev = g.loc[i - 1]
    trend_day = prev.rng > TREND_MULT * g.loc[i, "adr_before_prev"] if pd.notna(g.loc[i, "adr_before_prev"]) else False
    return float(row.sma20), float(row.adr10), float(prev.C), bool(trend_day)


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-05-19"
    g, tP, tbar = day_frames(date)
    if g is None:
        sys.exit("no ticks for " + date)
    sma20, adr10, prev_close, trend_day = context(date)
    day_op = float(tP[0])
    gap = abs(day_op - prev_close) / prev_close * 100.0
    gap_skip = gap > GAP_MAX
    stop_pts = max(round(STOP_MULT * adr10 / TICK) * TICK, STOP_FLOOR_T * TICK)

    trans = phase_transitions(g["High"].values, g["Low"].values, len(g), tP, tbar)
    tr_ix = [i for (i, _) in trans]; tr_md = [m for (_, m) in trans]
    # regime per bar = mode active at that bar's last tick
    n = len(g); reg_bar = []
    for b in range(n):
        z = np.searchsorted(tbar, b, "right") - 1
        reg_bar.append(tr_md[bisect_right(tr_ix, max(z, 0)) - 1] if tr_ix else "NEUTRAL")

    hours = g["DateTime"].dt.hour.values
    sigs = []
    day_taken = False
    for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
        if cnt != 2:
            continue
        short = dr == "S"
        a = np.searchsorted(tbar, fb, "left"); zc = np.searchsorted(tbar, fb, "right")
        s = tP[a:zc]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        reg = tr_md[bisect_right(tr_ix, jf) - 1] if tr_ix else "NEUTRAL"
        # gate reason
        reason = "OK"
        if reg != ("BEAR" if short else "BULL"):
            reason = "REG"
        elif not (trig > sma20):
            reason = "SMA"
        elif gap_skip:
            reason = "GAP"
        elif trend_day:
            reason = "TDY"
        # fill + window
        lim = trig + RETEST_T * TICK if short else trig - RETEST_T * TICK
        thru = trig + FILL_T * TICK if short else trig - FILL_T * TICK
        s0 = tP[jf:]
        jl = np.nonzero(s0 >= thru)[0] if short else np.nonzero(s0 <= thru)[0]
        fillbar = None
        if len(jl):
            jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
            if fb2 - fb <= CANCEL_BARS:
                fillbar = fb2
                if int(hours[min(fb2, n - 1)]) not in GOOD_HOURS:
                    if reason == "OK":
                        reason = "WIN"
        elif reason == "OK":
            reason = "NOFILL"
        taken = False
        if reason == "OK" and fillbar is not None and not day_taken:
            taken = True; day_taken = True   # OnePerDay: first valid fill
        sigs.append(dict(sb=int(sb) if sb is not None else int(fb), fb=int(fb), fill=fillbar,
                         dir=dr, trig=trig, lim=lim, reason=reason, taken=taken))

    # ---- plot ----
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    fig, ax = plt.subplots(figsize=(16, 8))
    for b in range(n):
        col = {"BULL": "#2e7d32", "BEAR": "#c62828"}.get(reg_bar[b])
        if col:
            ax.axvspan(b - 0.5, b + 0.5, color=col, alpha=0.07, lw=0)
    for b in range(n):
        up = C[b] >= O[b]; cc = "#26a69a" if up else "#ef5350"
        ax.plot([b, b], [L[b], H[b]], color=cc, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((b - 0.3, min(O[b], C[b])), 0.6, max(abs(C[b] - O[b]), 0.01),
                               facecolor=cc, edgecolor=cc, zorder=3))
    ax.axhline(sma20, color="#888", ls="--", lw=1, label=f"SMA20d {sma20:.1f} (gate)")
    for s in sigs:
        short = s["dir"] == "S"
        bx = s["fb"]
        y = L[bx] - 6 * TICK if not short else H[bx] + 6 * TICK
        if s["taken"]:
            ax.annotate("▲2EL TAKEN" if not short else "▼2ES TAKEN", (bx, y),
                        color="#000", fontsize=9, weight="bold", ha="center",
                        va="top" if short else "bottom",
                        bbox=dict(boxstyle="round", fc="#ffd54f", ec="k"))
            # retest limit + stop
            stop = s["lim"] + stop_pts if short else s["lim"] - stop_pts
            fb2 = s["fill"] if s["fill"] is not None else bx
            ax.plot([bx, n - 1], [s["lim"], s["lim"]], color="#1565c0", lw=1, ls=":")
            ax.plot([fb2, n - 1], [stop, stop], color="red", lw=1.5)
            ax.annotate(f"entry {s['lim']:.2f}", (n - 1, s["lim"]), fontsize=7, color="#1565c0", ha="right")
            ax.annotate(f"stop {stop:.2f}", (n - 1, stop), fontsize=7, color="red", ha="right", va="top")
        else:
            mk = "v" if short else "^"
            ax.scatter([bx], [y], marker=mk, s=40, color="gray", zorder=4)
            ax.annotate(s["reason"], (bx, y), color="gray", fontsize=7, ha="center",
                        va="top" if short else "bottom")
    ax.set_xlim(-1, n)
    times = g["DateTime"].dt.strftime("%H:%M").values
    step = max(1, n // 14)
    ax.set_xticks(range(0, n, step)); ax.set_xticklabels(times[::step], rotation=45, fontsize=8)
    skip = "GAP-SKIP" if gap_skip else ("TREND-DAY-SKIP" if trend_day else "tradeable")
    ntaken = sum(s["taken"] for s in sigs)
    ax.set_title(f"REGIME-2E — {date}  |  {skip}  |  gap {gap:.2f}%  ADR {adr10:.1f}  stop {stop_pts:.2f}pt"
                 f"  |  {len(sigs)} signals, {ntaken} taken (OnePerDay)", fontsize=12)
    ax.legend(loc="upper left", fontsize=8); ax.set_ylabel("ES price")
    fig.tight_layout()
    out = OUTDIR / f"day_{date}.png"
    fig.savefig(out, dpi=120)
    print(f"chart: {out}")
    print(f"{date}: regime lanes BULL/BEAR/NEUTRAL shaded; {len(sigs)} 2E signals:")
    for s in sigs:
        print(f"  bar {s['fb']:>3} {s['dir']} trig {s['trig']:.2f} -> {s['reason']}" + ("  [TAKEN]" if s['taken'] else ""))


if __name__ == "__main__":
    main()
