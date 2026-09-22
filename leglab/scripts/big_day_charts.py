"""
Interactive chart: each BIG ES day (last 12 months) + the NEXT session, in 5M
candles, with fib retracement levels drawn on the big-day move so the pullback
can be measured. Plotly draw tools enabled (draw your own lines/fibs, erase).

Big day = daily RTH range >= K x ABR8 (K default 2.5). Fib anchored to the big
day's HIGH (100%) and LOW (0%); the next-day pullback is measured against it
(Tim: enter ~50% pullback against the big-day direction, stop beyond the bar).

Output: leglab/outputs/big_day_charts_lastyear.html  (opened in the browser)
"""
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "data" / "bars" / "_db_es_5m_rth.parquet"
OUTDIR = ROOT / "leglab" / "outputs"
K = 2.5
FIBS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.66, 0.786, 1.0]
FIB_COLOR = {0.5: "#d62728", 0.618: "#ff7f0e", 0.66: "#ff7f0e"}


def main():
    df = pd.read_parquet(BARS)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["date"] = df["DateTime"].dt.date
    dates = sorted(df["date"].unique())
    nxt = {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}

    d = df.groupby("date").agg(o=("Open", "first"), c=("Close", "last"),
                               h=("High", "max"), l=("Low", "min"))
    d["range"] = d["h"] - d["l"]
    d["abr8"] = d["range"].shift(1).rolling(8).mean()
    d["rng_x"] = d["range"] / d["abr8"]
    d.index = pd.to_datetime(d.index)
    last = d[d.index >= d.index.max() - pd.Timedelta(days=365)]
    bigs = last[last["rng_x"] >= K].copy()
    big_dates = [ts.date() for ts in bigs.index]
    print(f"big days (K>={K}) last 12 months: {len(big_dates)}")

    n = len(big_dates)
    titles = []
    for bd in big_dates:
        row = d.loc[pd.Timestamp(bd)]
        direction = "UP" if row["c"] >= row["o"] else "DOWN"
        titles.append(f"{bd}  —  {row['rng_x']:.2f}× ABR8  ({direction} day, range {row['range']:.1f} pts)  + next session")

    fig = make_subplots(rows=n, cols=1, subplot_titles=titles, vertical_spacing=0.06)

    for i, bd in enumerate(big_dates, start=1):
        nd = nxt.get(bd)
        days = [bd] + ([nd] if nd else [])
        seg = df[df["date"].isin(days)].sort_values("DateTime").reset_index(drop=True)
        xcat = seg["DateTime"].dt.strftime("%m-%d %H:%M").tolist()
        fig.add_trace(go.Candlestick(
            x=xcat, open=seg["Open"], high=seg["High"], low=seg["Low"], close=seg["Close"],
            name=str(bd), showlegend=False,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        ), row=i, col=1)

        # day divider between big day and next session
        big_n = int((seg["date"] == bd).sum())
        if nd:
            fig.add_vline(x=big_n - 0.5, line=dict(color="#888", width=1, dash="dot"), row=i, col=1)

        # fib lines from the big day's high/low
        row = d.loc[pd.Timestamp(bd)]
        hi, lo = row["h"], row["l"]
        xr = f"x{'' if i == 1 else i}"
        yr = f"y{'' if i == 1 else i}"
        for f in FIBS:
            price = lo + f * (hi - lo)
            col = FIB_COLOR.get(f, "#9e9e9e")
            wid = 2 if f in (0.5, 0.618, 0.66) else 1
            fig.add_shape(type="line", xref=xr, yref=yr,
                          x0=xcat[0], x1=xcat[-1], y0=price, y1=price,
                          line=dict(color=col, width=wid,
                                    dash="solid" if f in (0.0, 1.0) else "dash"),
                          layer="below")
            fig.add_annotation(xref=xr, yref=yr, x=xcat[-1], y=price,
                               text=f"{int(f*100)}%  {price:.1f}", showarrow=False,
                               xanchor="left", font=dict(size=9, color=col))
        fig.update_xaxes(type="category", showticklabels=(i == n),
                         tickangle=45, nticks=20, row=i, col=1)
        fig.update_yaxes(title_text="ES", row=i, col=1)

    fig.update_layout(
        title=f"LegLab — Big ES days (K≥{K}) + next session, last 12 months.  "
              f"Fib on the big-day range. Use the toolbar ✎ to draw your own.",
        height=430 * n, xaxis_rangeslider_visible=False,
        dragmode="drawline", newshape=dict(line=dict(color="#1f77b4", width=1.5)),
        template="plotly_white", margin=dict(l=60, r=90, t=90, b=40),
    )
    for ax in fig.layout:
        if ax.startswith("xaxis"):
            fig.layout[ax].rangeslider = dict(visible=False)

    out = OUTDIR / "big_day_charts_lastyear.html"
    config = {"modeBarButtonsToAdd": ["drawline", "drawopenpath", "drawrect", "eraseshape"],
              "scrollZoom": True, "displaylogo": False}
    fig.write_html(out, config=config, include_plotlyjs="cdn")
    print(f"html -> {out}")


if __name__ == "__main__":
    main()
