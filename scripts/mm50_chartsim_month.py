#!/usr/bin/env python
"""mm50_chartsim_month.py — S92-EA: interactive 15M ES + NYSE-TICK for one month, with the
50% MM setups overlaid so each trade can be inspected (zoom/pan). Standalone Plotly HTML
(not the book_review canvas yet).

Top: 15M candles, swing H/L markers, and each MM 50% setup's entry(50%)/stop(61.8%)/target(123%)
     drawn from fill to exit + a fill marker labeled with the outcome.
Bottom: 15M NYSE TICK (high-low bar) with +/-800 and +/-1000 extreme lines.
X-axis skips non-session gaps (category axis) so bars are contiguous like a trading chart.

Usage: python scripts/mm50_chartsim_month.py [YYYY-MM=2026-06] [N=3]
"""
from __future__ import annotations

import sys
from pathlib import Path
import glob as _glob

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
OUT_DIR = ROOT / "eminiaddict" / "figures"
sys.path.insert(0, str(ROOT / "scripts"))
from halsey_mm50_engine import build_15m  # noqa: E402


def main():
    month = sys.argv[1] if len(sys.argv) > 1 else "2026-06"
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    g = build_15m().reset_index(drop=True)
    g["gi"] = g.index
    mask = g["dt"].dt.strftime("%Y-%m") == month
    gm = g[mask].reset_index(drop=True)
    if gm.empty:
        print(f"! no 15M bars in {month}"); return
    x = gm["dt"].dt.strftime("%m-%d %H:%M")   # category labels -> contiguous bars

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                        row_heights=[0.72, 0.28],
                        subplot_titles=(f"ES 15M — {month}   (50% MM setups overlaid)",
                                        "NYSE TICK (15M high-low)"))
    fig.add_trace(go.Candlestick(x=x, open=gm.O, high=gm.H, low=gm.L, close=gm.C,
                                 name="ES 15M", increasing_line_color="#26a65b",
                                 decreasing_line_color="#e2453c"), row=1, col=1)

    # TICK panel: real hi-lo bars (base=low, height=hi-low) — robust on a category axis
    base = gm.tkl.fillna(0)
    height = (gm.tkh - gm.tkl).fillna(0)
    colors = ["#e2453c" if (h >= 800 or l <= -800) else "#888"
              for h, l in zip(gm.tkh.fillna(0), gm.tkl.fillna(0))]
    fig.add_trace(go.Bar(x=x, y=height, base=base, marker_color=colors, width=0.7,
                         name="TICK hi-lo",
                         hovertext=[f"TICK {l:.0f}..{h:.0f}" for l, h in zip(gm.tkl, gm.tkh)],
                         hoverinfo="text"), row=2, col=1)
    for lv, dash in [(1000, "solid"), (800, "dash"), (-800, "dash"), (-1000, "solid")]:
        fig.add_hline(y=lv, line=dict(color="#e2453c", width=1, dash=dash), row=2, col=1)
    fig.update_yaxes(range=[-1300, 1300], row=2, col=1)

    # MM 50% setups overlay
    tr = pd.read_csv(sorted(_glob.glob(str(MASTER_DIR / "mm50_trades_*.csv")))[-1])
    tr = tr[tr.N == N].copy(); tr["dt"] = pd.to_datetime(tr["dt"])
    tr = tr[tr["dt"].dt.strftime("%Y-%m") == month]
    gi2x = {int(gi): xv for gi, xv in zip(gm["gi"], x)}
    for _, t in tr.iterrows():
        fk, ek = int(t.fill), int(t.exit)
        if fk not in gi2x:
            continue
        xf = gi2x[fk]; xe = gi2x.get(ek, xf)
        c = "#22d3ee" if t.why == "target" else ("#e2453c" if t.why == "stop" else "#f1c40f")
        # leg pivots (side-aware): long leg = low->high, short leg = high->low
        if t.side == 1:
            lo_i, lo_px, hi_i, hi_px = int(t.jL), g.loc[int(t.jL), "L"], int(t.jH), g.loc[int(t.jH), "H"]
        else:
            hi_i, hi_px, lo_i, lo_px = int(t.jL), g.loc[int(t.jL), "H"], int(t.jH), g.loc[int(t.jH), "L"]
        # MEASURED-MOVE dotted line: pivot1 -> pivot2 (the leg) -> 50% entry (the retrace)
        piv = sorted([(lo_i, lo_px), (hi_i, hi_px)], key=lambda p: p[0])
        path_i = [piv[0][0], piv[1][0], fk]
        path_y = [piv[0][1], piv[1][1], t.e50]
        if all(pi in gi2x for pi in path_i):
            fig.add_trace(go.Scatter(
                x=[gi2x[pi] for pi in path_i], y=path_y, mode="lines",
                line=dict(color="#ffffff", width=1.4, dash="dot"), showlegend=False,
                hovertext=["swing H/L -> 50%"] * 3, hoverinfo="text"), row=1, col=1)
        # 50 / 61.8 / 123 levels drawn from fill to exit
        for lv, col, dash in [(t.e50, "#ffd400", "solid"), (t.stop, "#e2453c", "dot"),
                              (t.tgt, "#22d3ee", "dash")]:
            fig.add_shape(type="line", x0=xf, x1=xe, y0=lv, y1=lv,
                          line=dict(color=col, width=1.2, dash=dash), row=1, col=1)
        # swing markers with labels (guard: pivot may be in a prior month -> off-view)
        if hi_i in gi2x:
            fig.add_trace(go.Scatter(x=[gi2x[hi_i]], y=[hi_px], mode="markers+text",
                          marker=dict(size=9, color="#ff5566", symbol="triangle-down"),
                          text=["H"], textposition="top center", textfont=dict(size=9, color="#ff5566"),
                          showlegend=False, hovertext=[f"swing H {hi_px:.2f}"], hoverinfo="text"),
                          row=1, col=1)
        if lo_i in gi2x:
            fig.add_trace(go.Scatter(x=[gi2x[lo_i]], y=[lo_px], mode="markers+text",
                          marker=dict(size=9, color="#33dd88", symbol="triangle-up"),
                          text=["L"], textposition="bottom center", textfont=dict(size=9, color="#33dd88"),
                          showlegend=False, hovertext=[f"swing L {lo_px:.2f}"], hoverinfo="text"),
                          row=1, col=1)
        # fill marker + outcome
        fig.add_trace(go.Scatter(
            x=[xf], y=[t.e50], mode="markers+text",
            marker=dict(size=12, color="white", symbol=("triangle-up" if t.side == 1
                                                        else "triangle-down"),
                        line=dict(color="black", width=1)),
            text=[f"{t.why} {t.R:+.1f}R"], textposition="middle right",
            textfont=dict(size=9, color=c),
            hovertext=[f"{'LONG' if t.side==1 else 'SHORT'} entry@50%={t.e50:.2f} "
                       f"stop(61.8%)={t.stop:.2f} tgt(123%)={t.tgt:.2f} -> {t.why} {t.R:+.2f}R"],
            hoverinfo="text", showlegend=False), row=1, col=1)

    fig.update_layout(template="plotly_dark", height=900, xaxis_rangeslider_visible=False,
                      margin=dict(l=40, r=20, t=50, b=40),
                      title=f"15M ES + NYSE TICK + 50% MM setups — {month} (N={N})")
    fig.update_xaxes(type="category", showticklabels=False, row=1, col=1)
    fig.update_xaxes(type="category", nticks=20, tickangle=45, row=2, col=1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"chartsim_15m_tick_{month.replace('-','')}_N{N}.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"wrote {out.relative_to(ROOT)}  | {len(gm)} bars, {len(tr)} MM setups overlaid")
    return out


if __name__ == "__main__":
    main()
