"""Per-trade LIVE metrics chart (S75) — how P&L, EV and POP evolve over the life of
a trade, from the marker's time series (data/options_sim/trade_metrics.csv).

Two stacked panels sharing a time axis (dual-axis is the #1 chart mistake, so $ and
% never share one axis):
  top  — unrealized P&L ($) + EV ($)
  bot  — POP (%) + P(max loss) (%)

  .venv/Scripts/python.exe scripts/trade_metrics_chart.py <trade_id>
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MET = ROOT / "data" / "options_sim" / "trade_metrics.csv"
CARDS = ROOT / "data" / "options_log" / "cards"

BG, SURF = "#0d0d0d", "#1a1a19"
INK, INK2, MUT, GRID = "#ffffff", "#c3c2b7", "#898781", "#2c2c2a"
PNL, EV, POP, PML = "#3987e5", "#eda100", "#0ca30c", "#d03b3b"


def render(trade_id):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    df = pd.read_csv(MET)
    d = df[df.trade_id == trade_id].copy()
    if not len(d):
        raise SystemExit(f"no metrics rows for {trade_id} yet (marker writes them each cycle)")
    d["t"] = pd.to_datetime(d.ts_et)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                        row_heights=[0.55, 0.45],
                        subplot_titles=("Unrealized P&L & EV ($)", "POP & P(max loss) (%)"))
    fig.add_trace(go.Scatter(x=d.t, y=d.unreal_pnl, name="P&L", mode="lines",
                             line=dict(color=PNL, width=2.4)), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.t, y=d.ev, name="EV", mode="lines",
                             line=dict(color=EV, width=2, dash="dot")), row=1, col=1)
    fig.add_hline(y=0, line=dict(color=MUT, width=1), row=1, col=1)
    fig.add_trace(go.Scatter(x=d.t, y=d["pop"] * 100, name="POP", mode="lines",
                             line=dict(color=POP, width=2.4)), row=2, col=1)
    fig.add_trace(go.Scatter(x=d.t, y=d.p_maxloss * 100, name="P(max loss)", mode="lines",
                             line=dict(color=PML, width=2, dash="dot")), row=2, col=1)

    last = d.iloc[-1]
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=SURF, height=560,
        title=dict(text=(f"<b>{trade_id}</b> — live trade metrics<br>"
                         f"<span style='font-size:12px;color:{INK2}'>latest: P&L "
                         f"${last.unreal_pnl:+,.0f} · POP {last["pop"]*100:.0f}% · EV "
                         f"${last.ev:+,.0f} · spot {last.spot:.0f} · σ {last.sigma:.0f}</span>"),
              font_color=INK),
        legend=dict(orientation="h", bgcolor=SURF, bordercolor=GRID, borderwidth=1),
        margin=dict(l=60, r=30, t=90, b=40))
    fig.update_xaxes(gridcolor=GRID, row=2, col=1, title="Exchange time (ET)")
    fig.update_xaxes(gridcolor=GRID, row=1, col=1)
    fig.update_yaxes(gridcolor=GRID, title="$", row=1, col=1)
    fig.update_yaxes(gridcolor=GRID, title="%", range=[0, 100], row=2, col=1)
    CARDS.mkdir(parents=True, exist_ok=True)
    out = CARDS / f"{trade_id}_metrics.html"
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"-> {out}  ({len(d)} points)")
    return out


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else "auto_20260716_090122")
