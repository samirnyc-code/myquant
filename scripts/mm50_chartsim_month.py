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

    # TICK panel: high-low bars via a filled scatter per bar is heavy; use error-bar style
    fig.add_trace(go.Scatter(
        x=x, y=gm.tkh, mode="markers", marker=dict(size=2, color="#888"),
        name="TICK high", hovertemplate="TICK hi %{y}<extra></extra>"), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=x, y=gm.tkl, mode="markers", marker=dict(size=2, color="#888"),
        name="TICK low", hovertemplate="TICK lo %{y}<extra></extra>"), row=2, col=1)
    # vertical TICK range segments
    for i in range(len(gm)):
        if np.isnan(gm.tkh[i]):
            continue
        fig.add_shape(type="line", x0=x[i], x1=x[i], y0=gm.tkl[i], y1=gm.tkh[i],
                      line=dict(color="#666", width=1), row=2, col=1)
    for lv, dash in [(1000, "solid"), (800, "dash"), (-800, "dash"), (-1000, "solid")]:
        fig.add_hline(y=lv, line=dict(color="#e2453c", width=1, dash=dash), row=2, col=1)

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
        for lv, col, dash in [(t.e50, "#ffd400", "solid"), (t.stop, "#e2453c", "dot"),
                              (t.tgt, "#22d3ee", "dash")]:
            fig.add_shape(type="line", x0=xf, x1=xe, y0=lv, y1=lv,
                          line=dict(color=col, width=1.3, dash=dash), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=[xf], y=[t.e50], mode="markers+text",
            marker=dict(size=11, color="white", symbol=("triangle-up" if t.side == 1
                                                        else "triangle-down"),
                        line=dict(color="black", width=1)),
            text=[f"{t.why} {t.R:+.1f}R"], textposition="top center",
            textfont=dict(size=9, color=c),
            hovertext=[f"{'LONG' if t.side==1 else 'SHORT'} 50%={t.e50:.2f} "
                       f"stop={t.stop:.2f} tgt={t.tgt:.2f} -> {t.why} {t.R:+.2f}R"],
            hoverinfo="text", showlegend=False), row=1, col=1)
        # swing markers
        for gi_, sym, col in [(int(t.jL), "circle", "#33dd88"), (int(t.jH), "circle", "#ff5566")]:
            if gi_ in gi2x:
                yy = g.loc[gi_, "L"] if col == "#33dd88" else g.loc[gi_, "H"]
                fig.add_trace(go.Scatter(x=[gi2x[gi_]], y=[yy], mode="markers",
                              marker=dict(size=7, color=col), showlegend=False,
                              hovertext=["swing"], hoverinfo="text"), row=1, col=1)

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
