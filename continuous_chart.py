"""
Continuous Chart tab — a scrollable, windowed candlestick over the full
back-adjusted continuous series, with indicator overlays.

Design (v1 — price + indicators):
  • Data: the continuous 5M series already in session (`data_sc_5m` / `mas_continuous`).
  • Windowed render: a date-range control slices the series so each draw stays light
    (~99k bars over 5yr render slowly all at once; Plotly candlesticks aren't WebGL).
  • Indicators computed on the FULL series, then sliced — so EMAs/VWAP are correct at
    the window's left edge (no warm-up truncation).
  • RTH-only series → rangebreaks suppress overnight/weekend gaps for a continuous look.

Trade overlays (entries/exits/price-paths) are a deliberate second pass — not here yet.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from indicators import session_vwap_bands, prior_period_levels

# Value-area timeframes offered on the chart: label → (period arg, colour).
_VA_TIMEFRAMES = {
    "Session":   ("session",   "#9e9e9e"),
    "Weekly":    ("weekly",    "#42a5f5"),
    "Monthly":   ("monthly",   "#ab47bc"),
    "Quarterly": ("quarterly", "#ffa726"),
    "Yearly":    ("yearly",    "#ef5350"),
}


# ── Indicator helpers ───────────────────────────────────────────────────────

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _break_last_of_group(y: pd.Series, grp: pd.Series) -> pd.Series:
    """Null the last bar of each contiguous group so the line does not connect
    across boundaries — no diagonal/vertical connector. Used to stop VWAP at the
    session edge and hold value-area levels flat (horizontal) within a period.
    With connectgaps=False the next group simply starts fresh."""
    is_last = grp.ne(grp.shift(-1)).to_numpy(copy=True)
    is_last[-1] = False                       # keep the final visible bar
    return y.mask(is_last)


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP — resets each trading day."""
    tp  = (df["High"] + df["Low"] + df["Close"]) / 3.0
    pv  = tp * df["Volume"]
    day = df["DateTime"].dt.date
    cum_pv  = pv.groupby(day).cumsum()
    cum_vol = df["Volume"].groupby(day).cumsum()
    return cum_pv / cum_vol.replace(0, np.nan)


def _daily_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    """Resample the intraday continuous series to one row per trading day."""
    g = df.groupby(df["DateTime"].dt.date)
    d = pd.DataFrame({
        "Open":  g["Open"].first(),
        "High":  g["High"].max(),
        "Low":   g["Low"].min(),
        "Close": g["Close"].last(),
    })
    d.index.name = "Date"
    return d.reset_index()


def _wilder_atr(daily: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    prev_c  = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def _wilder_adx(daily: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = daily["High"], daily["Low"], daily["Close"]
    up   = h.diff()
    down = -l.diff()
    plus_dm  = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    prev_c   = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False).mean()
    plus_di  = 100 * pd.Series(plus_dm,  index=daily.index).ewm(alpha=1.0 / n, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=daily.index).ewm(alpha=1.0 / n, adjust=False).mean() / atr.replace(0, np.nan)
    dx  = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1.0 / n, adjust=False).mean()


def _map_daily_to_intraday(df: pd.DataFrame, daily_val: pd.Series, daily: pd.DataFrame) -> pd.Series:
    """Forward-map a per-day indicator value onto each intraday bar by its Date."""
    lut = pd.Series(daily_val.values, index=daily["Date"].values)
    return df["DateTime"].dt.date.map(lut)


# ── Tab ─────────────────────────────────────────────────────────────────────

_RTH_BREAKS = [
    dict(bounds=["sat", "mon"]),               # weekends
    dict(bounds=[15.25, 8.5], pattern="hour"), # overnight (after 15:15 CT, before 08:30)
]


def show_continuous_chart_tab() -> None:
    st.header("📈 Continuous Chart")

    bars = st.session_state.get("data_sc_5m")
    if bars is None or bars.empty:
        bars = st.session_state.get("mas_continuous")
        if bars is not None:
            bars = bars.drop(columns=["Contract"], errors="ignore")
    if bars is None or bars.empty:
        st.info("Build the continuous series in the **📂 Massive** tab first.")
        return

    bars = bars.sort_values("DateTime").reset_index(drop=True)
    dmin = bars["DateTime"].min()
    dmax = bars["DateTime"].max()
    st.caption(f"{len(bars):,} bars  ·  {dmin.date()} → {dmax.date()}  "
               f"({bars['DateTime'].dt.date.nunique():,} trading days)")

    # ── Window controls — Date-range OR scroll one session at a time ──────────
    trading_days = sorted(bars["DateTime"].dt.date.unique())

    cc1, cc2, cc3 = st.columns([1.2, 1.4, 2])
    view_mode = cc1.radio("View", ["Date range", "Single session"],
                          horizontal=True, key="cc_view_mode")

    if view_mode == "Single session":
        if "cc_sess_idx" not in st.session_state:
            st.session_state["cc_sess_idx"] = len(trading_days) - 1
        nav_prev, nav_pick, nav_next = cc2.columns([1, 3, 1])
        if nav_prev.button("◀", key="cc_prev", use_container_width=True):
            st.session_state["cc_sess_idx"] = max(0, st.session_state["cc_sess_idx"] - 1)
        if nav_next.button("▶", key="cc_next", use_container_width=True):
            st.session_state["cc_sess_idx"] = min(len(trading_days) - 1,
                                                   st.session_state["cc_sess_idx"] + 1)
        # selectbox WITHOUT a key → recreated each run honouring our index (no state clash)
        sess_date = nav_pick.selectbox("Session", trading_days,
                                       index=st.session_state["cc_sess_idx"])
        st.session_state["cc_sess_idx"] = trading_days.index(sess_date)
        start_ts = pd.Timestamp(sess_date)
        end_ts   = start_ts + pd.Timedelta(days=1)
    else:
        span = cc2.selectbox("Window", ["1M", "3M", "6M", "1Y", "2Y", "All"],
                             index=1, key="cc_span")
        end_date = cc2.date_input("Window end", value=dmax.date(),
                                  min_value=dmin.date(), max_value=dmax.date(), key="cc_end")
        _span_days = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "2Y": 731, "All": None}[span]
        end_ts   = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        start_ts = dmin if _span_days is None else (end_ts - pd.Timedelta(days=_span_days))

    with cc3:
        ic1, ic2 = st.columns(2)
        ema_lens = ic1.multiselect("EMAs (on chart TF)", [9, 20, 50, 100, 200],
                                   default=[20], key="cc_emas")
        show_vwap   = ic1.checkbox("Session VWAP", value=False, key="cc_vwap")
        show_d200   = ic1.checkbox("Daily 200-EMA (macro trend)", value=True, key="cc_d200")
        show_vol    = ic2.checkbox("Volume", value=True, key="cc_vol")
        show_atr    = ic2.checkbox("Daily ATR(14)", value=False, key="cc_atr")
        show_adx    = ic2.checkbox("Daily ADX(14)", value=False, key="cc_adx")

    # ── VWAP σ-bands + Value-Area overlays (grouped legend → toggle in-chart) ──
    vc1, vc2, vc3 = st.columns([1, 1.8, 1.4])
    sigma_bands = vc1.multiselect("VWAP σ-bands", [1, 2, 3], default=[],
                                  key="cc_vwap_sigma",
                                  help="Standard-deviation bands around session VWAP "
                                       "(±1/±2/±3σ). Toggle each band in the legend.")
    va_periods  = vc2.multiselect("Value Areas (prior-period POC/VAH/VAL)",
                                  list(_VA_TIMEFRAMES.keys()), default=[],
                                  key="cc_value_areas",
                                  help="Prior period's value area projected across the "
                                       "current period — the reference levels the entry "
                                       "filter keys off. Toggle each timeframe in the legend.")
    shade_va    = vc3.checkbox("Shade value areas", value=True, key="cc_va_shade")
    va_opacity  = vc3.slider("VA opacity", 0.0, 0.40, 0.12, 0.02, key="cc_va_opacity")
    chart_h     = vc3.slider("Chart height (px)", 480, 1200, 760, 40, key="cc_height")

    # ── Indicators on FULL series (correct at window edge), then slice ────────
    work = bars.copy()
    for n in ema_lens:
        work[f"EMA{n}"] = _ema(work["Close"], n)
    if show_vwap or sigma_bands:
        vb = session_vwap_bands(bars)
        work["VWAP"]       = vb["VWAP"].values
        work["VWAP_sigma"] = vb["VWAP_sigma"].values
    for label in va_periods:
        period, _ = _VA_TIMEFRAMES[label]
        lv = prior_period_levels(bars, work["DateTime"], period)
        work[f"{label}_POC"] = lv["POC"].values
        work[f"{label}_VAH"] = lv["VAH"].values
        work[f"{label}_VAL"] = lv["VAL"].values

    daily = _daily_ohlc(bars)
    if show_d200:
        d200 = _ema(daily["Close"], 200)
        work["D200"] = _map_daily_to_intraday(work, d200, daily)
    if show_atr:
        atr = _wilder_atr(daily, 14)
        work["ATR"] = _map_daily_to_intraday(work, atr, daily)
    if show_adx:
        adx = _wilder_adx(daily, 14)
        work["ADX"] = _map_daily_to_intraday(work, adx, daily)

    view = work[(work["DateTime"] >= start_ts) & (work["DateTime"] < end_ts)].copy()
    if view.empty:
        st.warning("No bars in the selected window.")
        return

    n_view = len(view)
    if n_view > 25000:
        st.warning(f"{n_view:,} bars in view — Plotly candlesticks get sluggish above ~25k. "
                   "Narrow the window for smooth pan/zoom (price-path drill-in comes later).")

    # ── Build figure (dynamic subplots) ──────────────────────────────────────
    sub_rows  = [("price", 0.62)]
    if show_vol: sub_rows.append(("vol", 0.13))
    if show_atr: sub_rows.append(("atr", 0.13))
    if show_adx: sub_rows.append(("adx", 0.12))
    heights = [h for _, h in sub_rows]
    heights = [h / sum(heights) for h in heights]
    titles  = {"price": "", "vol": "Volume", "atr": "Daily ATR(14)", "adx": "Daily ADX(14)"}
    row_idx = {name: i + 1 for i, (name, _) in enumerate(sub_rows)}

    fig = make_subplots(rows=len(sub_rows), cols=1, shared_xaxes=True,
                        vertical_spacing=0.02, row_heights=heights,
                        subplot_titles=[titles[n] for n, _ in sub_rows])

    fig.add_trace(go.Candlestick(
        x=view["DateTime"], open=view["Open"], high=view["High"],
        low=view["Low"], close=view["Close"], name="ES",
        increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
    ), row=1, col=1)

    _ema_colors = {9: "#f6c453", 20: "#42a5f5", 50: "#ab47bc", 100: "#ffa726", 200: "#ef5350"}
    for n in ema_lens:
        fig.add_trace(go.Scatter(x=view["DateTime"], y=view[f"EMA{n}"], mode="lines",
                                 name=f"EMA{n}", line=dict(width=1, color=_ema_colors.get(n, "#888"))),
                      row=1, col=1)
    # ── VWAP group (center + ±kσ bands) — broken at each session edge ─────────
    if show_vwap or sigma_bands:
        sess = view["DateTime"].dt.date
        vwap_b = _break_last_of_group(view["VWAP"], sess)
        fig.add_trace(go.Scatter(x=view["DateTime"], y=vwap_b, mode="lines",
                                 name="VWAP", legendgroup="VWAP",
                                 legendgrouptitle_text="VWAP", connectgaps=False,
                                 line=dict(width=1.2, color="#26c6da", dash="dot")),
                      row=1, col=1)
        _sigma_color = {1: "#80deea", 2: "#4dd0e1", 3: "#26c6da"}
        for k in sorted(sigma_bands):
            col = _sigma_color.get(k, "#26c6da")
            for sign, lab in ((1, f"+{k}σ"), (-1, f"−{k}σ")):
                band = _break_last_of_group(view["VWAP"] + sign * k * view["VWAP_sigma"], sess)
                fig.add_trace(go.Scatter(
                    x=view["DateTime"], y=band, mode="lines", name=lab,
                    legendgroup="VWAP", connectgaps=False,
                    line=dict(width=1, color=col, dash="dash"),
                    hovertemplate=lab + ": %{y:.2f}<extra></extra>",
                ), row=1, col=1)

    # ── Value-Area groups (prior-period levels) — flat horizontal per period ──
    for label in va_periods:
        _, col = _VA_TIMEFRAMES[label]
        grp = f"{label} VA"
        # break each level where it changes → clean horizontal segments, no risers
        vah = _break_last_of_group(view[f"{label}_VAH"], view[f"{label}_VAH"])
        val = _break_last_of_group(view[f"{label}_VAL"], view[f"{label}_VAL"])
        poc = _break_last_of_group(view[f"{label}_POC"], view[f"{label}_POC"])
        if shade_va and va_opacity > 0:
            fig.add_trace(go.Scatter(x=view["DateTime"], y=val, mode="lines",
                                     legendgroup=grp, showlegend=False,
                                     line=dict(width=0, color=col), connectgaps=False,
                                     hoverinfo="skip"), row=1, col=1)
            fig.add_trace(go.Scatter(x=view["DateTime"], y=vah, mode="lines",
                                     name=f"{label} band", legendgroup=grp,
                                     legendgrouptitle_text=grp, fill="tonexty",
                                     fillcolor=_rgba(col, va_opacity),
                                     line=dict(width=0, color=col), connectgaps=False,
                                     hoverinfo="skip"), row=1, col=1)
        for lvl, series, dash, w in (("VAH", vah, "solid", 1),
                                     ("POC", poc, "dash", 1.4),
                                     ("VAL", val, "solid", 1)):
            fig.add_trace(go.Scatter(
                x=view["DateTime"], y=series, mode="lines",
                name=f"{label[0]}-{lvl}", legendgroup=grp, legendgrouptitle_text=grp,
                line=dict(width=w, color=col, dash=dash), connectgaps=False,
                hovertemplate=f"{label} {lvl}: " + "%{y:.2f}<extra></extra>",
            ), row=1, col=1)

    if show_d200:
        fig.add_trace(go.Scatter(x=view["DateTime"], y=view["D200"], mode="lines",
                                 name="Daily 200-EMA", line=dict(width=1.5, color="#e0e0e0")),
                      row=1, col=1)

    if show_vol:
        vc = ["#26a69a" if c >= o else "#ef5350" for o, c in zip(view["Open"], view["Close"])]
        fig.add_trace(go.Bar(x=view["DateTime"], y=view["Volume"], marker_color=vc,
                             showlegend=False, name="Vol"), row=row_idx["vol"], col=1)
    if show_atr:
        fig.add_trace(go.Scatter(x=view["DateTime"], y=view["ATR"], mode="lines",
                                 line=dict(color="#ffa726", width=1), showlegend=False),
                      row=row_idx["atr"], col=1)
    if show_adx:
        fig.add_trace(go.Scatter(x=view["DateTime"], y=view["ADX"], mode="lines",
                                 line=dict(color="#42a5f5", width=1), showlegend=False),
                      row=row_idx["adx"], col=1)
        for lvl, col in [(25, "#26a69a"), (15, "#888")]:
            fig.add_hline(y=lvl, line_dash="dot", line_color=col, line_width=1,
                          row=row_idx["adx"], col=1)

    fig.update_layout(
        height=chart_h + 130 * (len(sub_rows) - 1),
        margin=dict(l=50, r=20, t=30, b=30),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#e0e0e0"),
        xaxis_rangeslider_visible=False, dragmode="pan",
        legend=dict(orientation="h", y=1.02, yanchor="bottom", bgcolor="rgba(0,0,0,0)",
                    groupclick="togglegroup"),
    )
    fig.update_xaxes(rangebreaks=_RTH_BREAKS, showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#2a2a2a")
    st.plotly_chart(fig, use_container_width=True,
                    config={"scrollZoom": True, "displayModeBar": True})
    st.caption("Drag to pan · scroll to zoom · double-click to reset. "
               "Indicators are computed on the full series, so EMAs/VWAP are correct at the window's left edge.")
