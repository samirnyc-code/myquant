import re
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from data_loader import (CONTRACTS, bar_num_from_dt,
                         parse_ohlc_from_upload,
                         load_csv_cache, save_csv_cache,
                         load_csv_manifest, save_csv_manifest, clear_csv_cache,
                         apply_data_slot,
                         load_excluded_dates, save_excluded_dates)
import bar_analysis
import ama_setups
import portfolio
import massive
import validation
import wfa as wfa_mod
import continuous_chart
import extras
import prop_sim
import auction_tab
import er_lookahead_tab

# ── Global display rule for st.dataframe (DISPLAY only — calc precision intact) ─
# One wrapper instead of editing ~35 call sites (and it catches future ones).
# Money/PnL columns → whole dollars (0 dp); ratios/percentages/everything else
# → max 2 dp. Uses Streamlit column_config for plain DataFrames (cheap, no Styler
# overhead on big trade-log tables) and Styler.format for already-styled tables.
# Columns that genuinely need 3 dp (R-grid values like 0.625) are passed as
# pre-formatted strings at their call site, so they're object dtype and untouched.
import re as _re
from pandas.io.formats.style import Styler as _Styler

_ORIG_DATAFRAME = st.dataframe
_MONEY_RE = _re.compile(r'(\$|net|gross|pnl|p&l|profit|loss|slippage|commission|dollar|cost|equity|drawdown|\bdd\b|margin)', _re.I)
_RATIO_RE = _re.compile(r'(/|ratio|factor|\bpf\b|prom|wfe|pct|%|kurt|sqn|win|\br\b)', _re.I)


def _col_dp(name) -> int:
    """0 dp for money/PnL columns, 2 dp for ratios/percentages/everything else."""
    n = str(name)
    if _RATIO_RE.search(n):
        return 2
    if _MONEY_RE.search(n):
        return 0
    return 2


def _dataframe_2dp(data=None, *args, **kwargs):
    try:
        if isinstance(data, _Styler):
            fmt = {c: ("{:,.0f}" if _col_dp(c) == 0 else "{:.2f}")
                   for c in data.data.select_dtypes(include="floating").columns}
            if fmt:
                data = data.format(fmt, na_rep="—")
        elif isinstance(data, pd.DataFrame):
            cfg = dict(kwargs.get("column_config") or {})
            for c in data.select_dtypes(include="floating").columns:
                if c in cfg:
                    continue
                cfg[c] = st.column_config.NumberColumn(
                    format="%.0f" if _col_dp(c) == 0 else "%.2f")
            if cfg:
                kwargs["column_config"] = cfg
    except Exception:
        pass
    return _ORIG_DATAFRAME(data, *args, **kwargs)


st.dataframe = _dataframe_2dp

st.set_page_config(
    page_title="ES Futures — 5-Min RTH Bars",
    page_icon="📈",
    layout="wide",
)
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Data slot helper ──────────────────────────────────────────────────────────

_apply_data_slot = apply_data_slot  # alias — shared implementation lives in data_loader.py


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str,
                     show_bar_nums: bool = False,
                     show_volume: bool = False,
                     excl_first_n: int = 0, excl_last_min: int = 0,
                     contract: str = "ES",
                     signals: "pd.DataFrame | None" = None) -> go.Figure:
    candle = go.Candlestick(
        x=df["DateTime"],
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name=contract,
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
    )

    if show_volume:
        from plotly.subplots import make_subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.75, 0.25],
            vertical_spacing=0.02,
        )
        fig.add_trace(candle, row=1, col=1)
        vol_colors = [
            "#26a69a" if c >= o else "#ef5350"
            for o, c in zip(df["Open"], df["Close"])
        ]
        fig.add_trace(
            go.Bar(x=df["DateTime"], y=df["Volume"],
                   marker_color=vol_colors, showlegend=False, name="Volume"),
            row=2, col=1,
        )
        fig.update_layout(
            title=f"{contract} — 5-Min RTH Bars  ({date_str})",
            xaxis_rangeslider_visible=False,
            xaxis2=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
            yaxis=dict(autorange=True, title="Price"),
            yaxis2=dict(tickformat=",d", title="Vol"),
            height=640,
            margin=dict(l=50, r=20, t=60, b=60),
            template="plotly_white",
        )
    else:
        fig = go.Figure(candle)
        fig.update_layout(
            title=f"{contract} — 5-Min RTH Bars  ({date_str})",
            xaxis_title="Time (CT)",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False,
            xaxis=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
            yaxis=dict(autorange=True),
            height=520,
            margin=dict(l=50, r=20, t=60, b=60),
            template="plotly_white",
        )

    half  = pd.Timedelta(minutes=2, seconds=30)
    shade = dict(fillcolor="rgba(180,180,180,0.15)", line_width=0, layer="below")
    if excl_first_n > 0 and excl_first_n <= len(df):
        fig.add_vrect(x0=df.iloc[0]["DateTime"] - half,
                      x1=df.iloc[min(excl_first_n, len(df)) - 1]["DateTime"] + half, **shade)
    if excl_last_min > 0:
        cutoff_total = 15 * 60 + 15 - excl_last_min
        cutoff_str   = f"{cutoff_total // 60:02d}:{cutoff_total % 60:02d}"
        cutoff_bars  = df[df["DateTime"].dt.strftime("%H:%M") >= cutoff_str]
        if not cutoff_bars.empty:
            fig.add_vrect(x0=cutoff_bars.iloc[0]["DateTime"] - half,
                          x1=df.iloc[-1]["DateTime"] + half, **shade)
    if show_bar_nums:
        labeled = sorted(set(range(0, len(df), 3)) | {len(df) - 1})
        for i in labeled:
            fig.add_annotation(
                x=df.iloc[i]["DateTime"], xref="x",
                y=df.iloc[i]["Low"], yref="y",
                yshift=-6,
                text=str(bar_num_from_dt(df.iloc[i]["DateTime"])),
                showarrow=False,
                font=dict(size=12),
                xanchor="center",
                yanchor="top",
            )

    if signals is not None and not signals.empty:
        bar_hi = df.set_index("DateTime")["High"]
        bar_lo = df.set_index("DateTime")["Low"]
        offset = df["High"].max() * 0.0003
        row_kw = {"row": 1, "col": 1} if show_volume else {}

        df_day = df.copy()
        df_day["DateTime"] = pd.to_datetime(df_day["DateTime"])
        df_day = df_day.sort_values("DateTime").reset_index(drop=True)

        wins = losses = 0
        net_pts = 0.0
        type_stats: dict = {}   # {SignalType: {"w": int, "l": int, "pts": float}}

        for _, s in signals.iterrows():
            sig_dt      = pd.to_datetime(s["SignalDateTime"])   # FT bar open
            bo_start    = sig_dt - pd.Timedelta(minutes=5)      # BO bar open
            setup_end   = sig_dt + pd.Timedelta(minutes=5)      # FT bar closes = entry bar open
            entry_dt    = setup_end
            is_long     = s["Direction"] == "Long"
            dir_color   = "#00c853" if is_long else "#d50000"   # triangle only
            symbol      = "triangle-up" if is_long else "triangle-down"
            stop_px     = s["StopPrice"]
            tgt_px      = (s["SignalPrice"] + s["TargetPoints"] if is_long
                           else s["SignalPrice"] - s["TargetPoints"])
            target_mode = s.get("TargetMode", "BarRange")

            # Triangle marker at FT bar
            ref_px = bar_lo.get(sig_dt, s["SignalPrice"]) if is_long else bar_hi.get(sig_dt, s["SignalPrice"])
            y_pos  = ref_px - offset if is_long else ref_px + offset
            label  = s["SignalType"]
            hover  = (f"{label} {s['Direction']}<br>"
                      f"Entry: {s['SignalPrice']:.2f}<br>"
                      f"Stop: {stop_px:.2f}<br>"
                      f"Target: +{s['TargetPoints']:.2f} pts")
            fig.add_trace(go.Scatter(
                x=[sig_dt], y=[y_pos],
                mode="markers+text",
                marker=dict(symbol=symbol, size=8, color=dir_color,
                            line=dict(color="white", width=1)),
                text=[label],
                textposition="bottom center" if is_long else "top center",
                textfont=dict(size=9, color=dir_color),
                hovertext=[hover], hoverinfo="text",
                showlegend=False, name=label,
            ), **row_kw)

            # Walk forward from entry bar to find exit (stop or target hit)
            fwd = df_day[df_day["DateTime"] >= entry_dt].reset_index(drop=True)
            entry_px = fwd.iloc[0]["Open"] if not fwd.empty else s["SignalPrice"]
            exit_dt = exit_px = result = None

            for _, bar in fwd.iterrows():
                hit_tgt  = bar["High"] >= tgt_px  if is_long else bar["Low"]  <= tgt_px
                hit_stop = bar["Low"]  <= stop_px if is_long else bar["High"] >= stop_px
                if hit_stop and hit_tgt:
                    exit_dt = bar["DateTime"]
                    exit_px = stop_px
                    result  = stop_px - entry_px if is_long else entry_px - stop_px
                    break
                elif hit_tgt:
                    exit_dt = bar["DateTime"]
                    exit_px = tgt_px
                    result  = tgt_px - entry_px if is_long else entry_px - tgt_px
                    break
                elif hit_stop:
                    exit_dt = bar["DateTime"]
                    exit_px = stop_px
                    result  = stop_px - entry_px if is_long else entry_px - stop_px
                    break

            if exit_dt is None and not fwd.empty:
                last    = fwd.iloc[-1]
                exit_dt = last["DateTime"]
                exit_px = last["Close"]
                result  = (exit_px - entry_px) if is_long else (entry_px - exit_px)
            elif exit_dt is None:
                exit_dt = sig_dt + pd.Timedelta(minutes=10)
                exit_px = s["SignalPrice"]
                result  = 0.0

            # Stop line (always red): BO bar → exit bar
            fig.add_shape(type="line",
                x0=bo_start, x1=exit_dt,
                y0=stop_px, y1=stop_px,
                line=dict(color="#d50000", width=1, dash="dot"),
                opacity=0.7, **row_kw)

            # Target line (always green): BO bar → exit bar
            fig.add_shape(type="line",
                x0=bo_start, x1=exit_dt,
                y0=tgt_px, y1=tgt_px,
                line=dict(color="#00c853", width=1, dash="dot"),
                opacity=0.7, **row_kw)

            # Price path: direct dotted line entry → exit (yellow)
            fig.add_shape(type="line",
                x0=entry_dt, x1=exit_dt,
                y0=entry_px, y1=exit_px,
                line=dict(color="#FFD600", width=1.0, dash="dot"),
                opacity=0.8, **row_kw)

            # Setup range lines across the 2 setup bars (BO + FT)
            bo_row = df_day[df_day["DateTime"] == bo_start]
            ft_row = df_day[df_day["DateTime"] == sig_dt]
            if not bo_row.empty and not ft_row.empty:
                bo_r = bo_row.iloc[0]
                ft_r = ft_row.iloc[0]
                # BarRange: H and L of combined setup bars
                for y in (max(bo_r["High"], ft_r["High"]),
                          min(bo_r["Low"],  ft_r["Low"])):
                    fig.add_shape(type="line",
                        x0=bo_start, x1=setup_end,
                        y0=y, y1=y,
                        line=dict(color="#00c853", width=1, dash="dot"),
                        opacity=0.4, **row_kw)
                if target_mode == "BodyRange":
                    # Additional lines for combined body extents
                    for y in (max(bo_r["Open"], bo_r["Close"],
                                  ft_r["Open"], ft_r["Close"]),
                              min(bo_r["Open"], bo_r["Close"],
                                  ft_r["Open"], ft_r["Close"])):
                        fig.add_shape(type="line",
                            x0=bo_start, x1=setup_end,
                            y0=y, y1=y,
                            line=dict(color="#00c853", width=1, dash="dot"),
                            opacity=0.25, **row_kw)

            # Accumulate day stats
            if result is not None:
                stype = s["SignalType"]
                if stype not in type_stats:
                    type_stats[stype] = {"w": 0, "l": 0, "pts": 0.0}
                if result > 0:
                    wins += 1
                    type_stats[stype]["w"] += 1
                else:
                    losses += 1
                    type_stats[stype]["l"] += 1
                net_pts += result
                type_stats[stype]["pts"] += result

            # Result annotation at exit bar
            if result is not None:
                sign      = "+" if result > 0 else ""
                ann_color = "#00c853" if result > 0 else "#d50000"
                fig.add_annotation(
                    x=exit_dt, y=exit_px,
                    text=f"{sign}{result:.2f}",
                    showarrow=False,
                    font=dict(size=9, color=ann_color, family="monospace"),
                    xanchor="left",
                    yanchor="bottom" if is_long else "top",
                    **row_kw,
                )

        # Combined info + stats box — top left, stacked
        s0   = signals.iloc[0]
        tm   = s0.get("TargetMode", "BarRange")
        tmul = float(s0.get("TargetMult", 1.0))
        sm   = s0.get("StopMode",   "BarExtreme")
        soff = s0.get("StopOffset", 1)
        lime = "#00ff00"

        def _fmt(pts: float, pnl: float) -> str:
            p = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"
            d = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
            return f"{p}pts  {d}"

        box_lines = [f"Tgt: {tm} ×{tmul:.2f}  |  Stop: {sm} +{int(soff)}t"]
        for stype, st in sorted(type_stats.items()):
            if st["w"] + st["l"] == 0:
                continue
            box_lines.append(f"{stype}  {st['w']}W-{st['l']}L  {_fmt(st['pts'], st['pts']*50)}")
        net_pnl = net_pts * 50
        box_lines.append(f"Total  {wins}W-{losses}L  {_fmt(net_pts, net_pnl)}")

        fig.add_annotation(
            x=0.99, y=0.99,
            xref="paper", yref="paper",
            text="<br> <br>".join(box_lines),
            showarrow=False,
            bgcolor="rgba(15,15,15,0.8)",
            bordercolor="#00ff00",
            borderwidth=1,
            font=dict(size=11, color=lime, family="monospace"),
            align="left",
            xanchor="right",
            yanchor="top",
        )

    return fig


# ── Bar Viewer tab ────────────────────────────────────────────────────────────

def show_bar_viewer(sc_file: str = "", contract: str = "ES"):
    bars = st.session_state.get("data_sc_5m")

    if bars is None:
        st.info("Build the continuous series in the **📂 Massive** tab to begin.")
        return

    bars["Date"] = bars["DateTime"].dt.date
    dates = sorted(bars["Date"].unique())

    if "bar_viewer_idx" not in st.session_state:
        st.session_state.bar_viewer_idx = len(dates) - 1
    st.session_state.bar_viewer_idx = max(0, min(st.session_state.bar_viewer_idx, len(dates) - 1))

    c_prev, c_next, c_sel = st.columns([1, 1, 14])
    if c_prev.button("‹", help="Previous date"):
        st.session_state.bar_viewer_idx = max(0, st.session_state.bar_viewer_idx - 1)
    if c_next.button("›", help="Next date"):
        st.session_state.bar_viewer_idx = min(len(dates) - 1, st.session_state.bar_viewer_idx + 1)

    selected_date = c_sel.selectbox(
        "Trading Date",
        options=dates,
        index=st.session_state.bar_viewer_idx,
        format_func=lambda d: d.strftime("%A %b %d, %Y"),
    )
    st.session_state.bar_viewer_idx = dates.index(selected_date)

    day = bars[bars["Date"] == selected_date].drop(columns="Date").reset_index(drop=True)
    if day.empty:
        st.warning("No RTH data found for this date.")
        return

    day_open  = day.iloc[0]["Open"]
    day_close = day.iloc[-1]["Close"]
    day_high  = day["High"].max()
    day_low   = day["Low"].min()
    day_vol   = day["Volume"].sum()
    chg       = day_close - day_open
    chg_pct   = chg / day_open * 100

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Open",         f"{day_open:.2f}")
    m2.metric("High",         f"{day_high:.2f}")
    m3.metric("Low",          f"{day_low:.2f}")
    m4.metric("Close",        f"{day_close:.2f}")
    m5.metric("Change",       f"{chg:+.2f}", f"{chg_pct:+.2f}%")
    m6.metric("Total Volume", f"{day_vol:,.0f}")

    cb1, cb2 = st.columns(2)
    show_bar_nums = cb1.checkbox("Show bar numbers", value=False,
                                  help="Labels every 3rd bar (1, 4, 7…) below the x-axis.")
    show_volume   = cb2.checkbox("Show volume", value=False,
                                  help="Adds a colour-coded volume panel below the price chart.")
    excl_first_n  = st.session_state.get("excl_first_n",  0)
    excl_last_min = st.session_state.get("excl_last_min", 0)

    # Collect any active signal sets to overlay
    _day_signals = []
    for _sig_key in ("ba_signals_ama", "ba_signals_mc", "ba_signals_revft"):
        _sigs = st.session_state.get(_sig_key)
        if _sigs is not None and not _sigs.empty:
            _day = _sigs[pd.to_datetime(_sigs["SignalDateTime"]).dt.date == selected_date]
            if not _day.empty:
                _day_signals.append(_day)
    _overlay = pd.concat(_day_signals, ignore_index=True) if _day_signals else None

    st.plotly_chart(
        make_candlestick(day, selected_date.strftime("%B %d, %Y"),
                         show_bar_nums=show_bar_nums,
                         show_volume=show_volume,
                         excl_first_n=excl_first_n, excl_last_min=excl_last_min,
                         contract=contract,
                         signals=_overlay),
        use_container_width=True,
    )

    with st.expander("5-Minute Bar Table", expanded=False):
        display = day.copy()
        display["Time"] = display["DateTime"].dt.strftime("%H:%M")
        display = display[["Time", "Open", "High", "Low", "Close", "Volume"]]
        st.dataframe(
            display.style.format({
                "Open": "{:.2f}", "High": "{:.2f}",
                "Low":  "{:.2f}", "Close": "{:.2f}",
                "Volume": "{:,.0f}",
            }),
            use_container_width=True,
            hide_index=True,
            height=min(35 * len(display) + 38, 600),
        )


# ── Data tab ──────────────────────────────────────────────────────────────────

def show_data_tab():
    st.caption(
        "Set once here — these same filters (holidays, day-of-week, session boundaries, "
        "economic events) automatically apply to the Massive continuous-series comparison "
        "and to Bar Analysis. No need to set them twice."
    )
    validation.render_filters("shared")

    st.divider()
    st.markdown("### Data Sources")
    st.caption(
        "Massive bars/ticks (built in the 📂 Massive tab) drive Bar Viewer and all trade analysis. "
        "NT is only used as a continuous-contract upload in the Massive tab, for matching — "
        "it doesn't need anything here. This panel is a manual override if you ever need to "
        "load a different ES_MAS 5M export by hand."
    )

    _sc5m = st.session_state.get("data_sc_5m")
    if _sc5m is not None:
        _lbl  = st.session_state.get("data_sc_5m_label", "")
        _days = _sc5m["DateTime"].dt.date.nunique()
        _min  = _sc5m["DateTime"].dt.date.min()
        _max  = _sc5m["DateTime"].dt.date.max()
        st.success(f"✅ **ES_MAS 5M** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
    else:
        st.info("ES_MAS 5M — not loaded")

    sc_5m_file = st.file_uploader(
        "Upload ES_MAS 5M bars (.txt / .csv) — overrides the Massive continuous series",
        type=["txt", "csv"], key="dt_sc5m",
        help="OHLCExporter TXT from the ES_MAS chart in NT",
    )
    if sc_5m_file:
        _key = f"{sc_5m_file.name}_{sc_5m_file.size}"
        if st.session_state.get("data_sc_5m_key") != _key:
            _cached = load_csv_cache("sc_5m", sc_5m_file.name, sc_5m_file.size)
            if _cached is not None:
                _df = _cached
            else:
                with st.spinner("Parsing ES_MAS 5M data…"):
                    _df = parse_ohlc_from_upload(sc_5m_file)
                save_csv_cache(_df, "sc_5m", sc_5m_file.name, sc_5m_file.size)
                _mf = load_csv_manifest()
                _mf["sc_5m"] = {"name": sc_5m_file.name, "size": sc_5m_file.size}
                save_csv_manifest(_mf)
            _apply_data_slot("sc_5m", _df, sc_5m_file.name, _key)
            st.rerun()

    # ── Manually excluded dates ───────────────────────────────────────────────
    st.divider()
    with st.expander("🚫 Manually Excluded Dates", expanded=False):
        st.caption(
            "Dates flagged here are dropped everywhere in the app — comparisons, Bar Viewer, "
            "and trade simulation/WFA — because the underlying data for that day is known to be bad "
            "(feed gap, capture artifact, etc), not a real price discrepancy."
        )
        excluded = load_excluded_dates()

        ec1, ec2, ec3 = st.columns([2, 3, 1])
        new_date   = ec1.date_input("Date", key="excl_date_input")
        new_reason = ec2.text_input("Reason", key="excl_reason_input", placeholder="e.g. NT capture gap")
        if ec3.button("Add", key="excl_date_add"):
            excluded[str(new_date)] = new_reason or "—"
            save_excluded_dates(excluded)
            st.rerun()

        if excluded:
            for d in sorted(excluded):
                rc1, rc2, rc3 = st.columns([2, 5, 1])
                rc1.write(d)
                rc2.write(excluded[d])
                if rc3.button("🗑️", key=f"excl_remove_{d}"):
                    excluded.pop(d, None)
                    save_excluded_dates(excluded)
                    st.rerun()
        else:
            st.info("No dates excluded.")

    # ── Cache management ──────────────────────────────────────────────────────
    st.divider()
    if st.button("🗑️ Clear all cached data", help="Deletes Parquet cache files and resets session."):
        clear_csv_cache()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
            ):
                st.session_state.pop(k, None)
        st.rerun()


# ── App entry point ───────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Detecting AMA signals…")
def _run_ama(
    bars: pd.DataFrame,
    stop_offset: int,
    target_mode: str,
    target_mult: float,
    types_key: str,
    ob_requires_ft: bool,
    # AMAConfig knobs (all cacheable scalars)
    bl_signal_ibs: int,
    br_signal_ibs: int,
    bl_ft_ibs: int,
    br_ft_ibs: int,
    range_filter: float,
    range_lookback: int,
    ft_must_close_beyond: int,
    show_bigbo: int,
    big_bo_range_factor: float,
    show_cx: int,
    strict_ob: int,
) -> pd.DataFrame:
    """Run AMA detect + to_signal_rows on `bars`. Cached by all params."""
    cfg = ama_setups.AMAConfig(
        bl_signal_ibs=bl_signal_ibs,
        br_signal_ibs=br_signal_ibs,
        bl_ft_bar_ibs=bl_ft_ibs,
        br_ft_bar_ibs=br_ft_ibs,
        range_filter=range_filter,
        range_lookback=range_lookback,
        ft_bar_must_close_beyond=ft_must_close_beyond,
        show_bigbo=show_bigbo,
        big_bo_range_factor=big_bo_range_factor,
        show_cx=show_cx,
        strict_ob=strict_ob,
    )
    tp = ama_setups.AMATradeParams(
        stop_offset_ticks=stop_offset,
        target_mode=target_mode,
        target_mult=target_mult,
    )
    types_set  = set(types_key.split(","))
    include_ft = "BO" in types_set or "FT" in types_set
    codes: list[int] = []
    if "BO" in types_set or "FT" in types_set: codes += [1, -1]
    if "OB"    in types_set: codes += [3, -3, 4]
    if "BigBO" in types_set: codes += [5, -5]
    bars = bars.drop(columns=["Contract"], errors="ignore")
    detected = ama_setups.detect(bars, cfg)
    return ama_setups.to_signal_rows(
        detected, bars, tp,
        signal_types=tuple(set(codes)),
        include_ft=include_ft,
        ob_requires_ft=ob_requires_ft,
        include_flip=False,
    )


def _render_status_strip():
    """A compact load-status row: price, continuous series, and signal sets.
    Checkmarks reflect current session state (continuous self-corrects on the
    next rerun after the Massive tab builds it)."""
    def _has(x):
        return x is not None and not getattr(x, "empty", False)

    def _chk(ok):
        return "✅" if ok else "⬜"

    price = st.session_state.get("data_sc_5m")
    cont  = st.session_state.get("mas_continuous")
    mc    = st.session_state.get("ba_signals_mc")
    rev   = st.session_state.get("ba_signals_revft")
    ama   = st.session_state.get("ba_signals_ama")

    s1, s2, s3, s4, s5 = st.columns(5)
    if _has(price):
        d0, d1 = price["DateTime"].min().date(), price["DateTime"].max().date()
        s1.markdown(f"{_chk(True)} **Price** · {len(price):,} bars · {d0} → {d1}")
    else:
        s1.markdown(f"{_chk(False)} **Price** — none loaded")
    s2.markdown(f"{_chk(_has(cont))} **Continuous** "
                + (f"· {len(cont):,} bars" if _has(cont) else "— not built"))
    s3.markdown(f"{_chk(_has(mc))} **MC signals** "
                + (f"· {len(mc)}" if _has(mc) else "— none"))
    s4.markdown(f"{_chk(_has(rev))} **RevFT signals** "
                + (f"· {len(rev)}" if _has(rev) else "— none"))
    s5.markdown(f"{_chk(_has(ama))} **AMA signals** "
                + (f"· {len(ama)}" if _has(ama) else "— none"))


def main():
    # ── Auto-load from CSV Parquet cache on first run ─────────────────────────
    if "data_sc_5m" not in st.session_state and "data_nt_5m" not in st.session_state:
        _mf = load_csv_manifest()
        for _slot in ("sc_5m", "nt_5m"):
            _info = _mf.get(_slot)
            if _info:
                _df = load_csv_cache(_slot, _info["name"], _info["size"])
                if _df is not None:
                    _apply_data_slot(
                        _slot, _df, _info["name"],
                        f"{_info['name']}_{_info['size']}",
                    )

    st.title("ES Futures — 5-Minute RTH Bars")

    hdr_l, hdr_r = st.columns([8, 2])
    hdr_l.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    # Positioned here but filled at the END of main(), so it reflects state that
    # the tab blocks populate later (continuous series, signals, sc_5m bridge).
    status_ph = st.container()

    from pathlib import Path
    contract_keys = [k for k, v in CONTRACTS.items() if Path(v["sc_file"]).exists()]

    if len(contract_keys) > 1:
        selected_key = hdr_r.selectbox(
            "Contract", contract_keys,
            index=0, key="active_contract", label_visibility="collapsed",
        )
    elif len(contract_keys) == 1:
        selected_key = contract_keys[0]
    else:
        selected_key = None

    sc_file = str(CONTRACTS[selected_key]["sc_file"]) if selected_key else ""
    nt_file = str(CONTRACTS[selected_key]["nt_file"]) if selected_key else ""

    _rl_col, _fr_col, _ = st.columns([1, 1.6, 9])
    if _rl_col.button("🔄 Reload", help="Clears session data (cache files are preserved)."):
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
                "ba_signals", "ba_signals_key",
            ):
                st.session_state.pop(k, None)
        st.rerun()
    if _fr_col.button(
        "♻️ Full Restart",
        help="Resets ALL session state + caches and re-derives everything from disk "
             "(continuous series, defaults, widgets). The in-app equivalent of relaunching — "
             "use after code changes. Cache files on disk are preserved.",
    ):
        st.cache_data.clear()
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.session_state.clear()
        st.rerun()

    # Tab order: Bar Viewer first, Bar Analysis right after it (restored). st.tabs
    # always opens tab 0, so a one-time JS click below makes Bar Analysis the
    # default-active tab while keeping it in second position.
    tab_massive, tab0, tab3, tab_wfa, tab1, tab_chart, tab4, tab_extras, tab_prop, tab_auction, tab_erc = st.tabs([
        "📂 Massive", "🗂️ Data", "📈 Bar Analysis", "🔄 WFA", "📊 Bar Viewer", "📈 Chart", "📊 Portfolio", "🧩 Extras", "🏢 Prop Sim", "🏛️ Auction", "🔬 ER10 Look-ahead",
    ])

    # Auto-select Bar Analysis (index 1) once per browser session — guarded so it
    # does NOT re-fire on every rerun and yank you off a tab you navigated to.
    components.html(
        """
        <script>
        (function () {
          if (window.sessionStorage.getItem('ba_default_done')) return;
          const doc = window.parent.document;
          const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
          if (tabs.length > 1) {
            tabs[1].click();
            window.sessionStorage.setItem('ba_default_done', '1');
          }
        })();
        </script>
        """,
        height=0,
    )

    contract_label = selected_key.split(" — ")[0] if selected_key else "ES"

    with tab_massive:
        massive.show_massive_tab()

    if st.session_state.get("data_sc_5m") is None and st.session_state.get("mas_continuous") is not None:
        mas_cont = st.session_state["mas_continuous"]
        apply_data_slot("sc_5m", mas_cont.drop(columns=["Contract"], errors="ignore"),
                         "Massive Continuous (auto)", "mas_continuous_auto")

    with tab0:
        show_data_tab()

    with tab1:
        show_bar_viewer(sc_file, contract=contract_label)

    with tab_chart:
        continuous_chart.show_continuous_chart_tab()

    with tab3:
        # Signals upload lives here (price data is in the Data tab)
        _SIGNALS_DIR = Path(__file__).parent / "saved_signals"
        _SIGNALS_DIR.mkdir(exist_ok=True)

        def _signal_uploader(label: str, upload_key: str, state_prefix: str):
            _disk_path = _SIGNALS_DIR / f"{state_prefix}.parquet"
            with st.expander(label, expanded=False):
                sig_file = st.file_uploader(
                    "Signals (.txt/.csv)", type=["txt", "csv"], key=upload_key,
                    help="Space-delimited: Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop",
                )
                if sig_file is not None:
                    sig_key = f"{sig_file.name}_{sig_file.size}"
                    if st.session_state.get(f"{state_prefix}_key") != sig_key:
                        raw    = sig_file.read().decode("utf-8", errors="replace")
                        parsed = bar_analysis.parse_signals(raw)
                        if parsed is None or parsed.empty:
                            st.error("Could not parse signals.")
                        else:
                            st.session_state[state_prefix]           = parsed
                            st.session_state[f"{state_prefix}_key"]  = sig_key
                            parsed.to_parquet(_disk_path, index=False)
                    if st.session_state.get(state_prefix) is not None:
                        n_sig = len(st.session_state[state_prefix])
                        st.caption(f"✅ {sig_file.name}  |  {n_sig} signals")
                else:
                    if state_prefix not in st.session_state and _disk_path.exists():
                        st.session_state[state_prefix] = pd.read_parquet(_disk_path)
                    if st.session_state.get(state_prefix) is not None:
                        n_sig = len(st.session_state[state_prefix])
                        st.caption(f"✅ (auto-loaded from disk)  |  {n_sig} signals")

        _signal_uploader("📊 MC Signals",   "upload_signals",       "ba_signals_mc")
        _signal_uploader("🔁 RevFT Signals", "upload_signals_revft", "ba_signals_revft")

        # AMA Signals — generated directly from loaded bar data, no upload needed
        with st.expander("🔶 AMA Breakouts Signals", expanded=False):
            _cont = st.session_state.get("mas_continuous")
            _sc   = st.session_state.get("data_sc_5m")
            _ama_bars = _cont if (_cont is not None and not _cont.empty) else _sc
            if _ama_bars is None:
                st.info("Load bar data first (Data tab or Massive tab).")
            else:
                # ── 01. Signal types ──────────────────────────────────────────
                st.markdown("**Signal types**")
                _tc1, _tc2, _tc3 = st.columns(3)
                _inc_boft  = _tc1.checkbox("BO+FT",  value=True,  key="ama_inc_boft")
                _inc_ob    = _tc2.checkbox("OB+FT",  value=True,  key="ama_inc_ob")
                _inc_bigbo = _tc3.checkbox("BigBO",  value=False, key="ama_inc_bigbo")
                _selected_types = ",".join(t for t, on in [
                    ("BO", _inc_boft), ("OB", _inc_ob), ("BigBO", _inc_bigbo),
                ] if on)

                # ── 02. Trade geometry ────────────────────────────────────────
                st.markdown("**Trade geometry**")
                _ag1, _ag2, _ag3 = st.columns(3)
                _ama_stop_off = _ag1.number_input("Stop offset (ticks)", min_value=0,
                                                   max_value=10, value=1, step=1,
                                                   key="ama_stop_offset")
                _ama_tgt_mode = _ag2.selectbox("Target mode", ["BarRange", "BodyRange"],
                                                key="ama_target_mode")
                _ama_tgt_mult = _ag3.number_input("Target mult", min_value=0.1,
                                                   max_value=5.0, value=1.0, step=0.1,
                                                   format="%.1f", key="ama_target_mult")

                # ── 03. IBS Filters (–1 = off) ────────────────────────────────
                st.markdown("**IBS filters** (−1 = off)")
                _ib1, _ib2, _ib3, _ib4 = st.columns(4)
                _bl_ibs  = _ib1.number_input("Bull BO min IBS",  min_value=-1, max_value=100,
                                              value=60, step=1, key="ama_bl_ibs")
                _br_ibs  = _ib2.number_input("Bear BO max IBS",  min_value=-1, max_value=100,
                                              value=40, step=1, key="ama_br_ibs")
                _bl_ft   = _ib3.number_input("Bull FT min IBS",  min_value=-1, max_value=100,
                                              value=40, step=1, key="ama_bl_ft_ibs")
                _br_ft   = _ib4.number_input("Bear FT max IBS",  min_value=-1, max_value=100,
                                              value=60, step=1, key="ama_br_ft_ibs")

                # ── 04. FT settings ───────────────────────────────────────────
                st.markdown("**Follow-through**")
                _ft1, _ft2, _ft3 = st.columns(3)
                _ft_close = _ft1.selectbox("FT must close beyond", [1, 0],
                                            format_func=lambda x: "Yes" if x else "No",
                                            key="ama_ft_close_beyond")
                _ob_ft    = _ft2.checkbox("OB requires FT", value=True, key="ama_ob_req_ft")
                _strict   = _ft3.checkbox("Strict OB",      value=True, key="ama_strict_ob")

                # ── 05. Range filter ──────────────────────────────────────────
                st.markdown("**Range filter** (0 = off)")
                _rf1, _rf2 = st.columns(2)
                _rng_filt = _rf1.number_input("Range filter mult", min_value=0.0,
                                               max_value=3.0, value=0.0, step=0.1,
                                               format="%.1f", key="ama_range_filter")
                _rng_lb   = _rf2.number_input("Range lookback",    min_value=2,
                                               max_value=50, value=8, step=1,
                                               key="ama_range_lookback")

                # ── 06. BigBO / CX ────────────────────────────────────────────
                st.markdown("**BigBO / CX**")
                _bx1, _bx2, _bx3 = st.columns(3)
                _show_bbo  = _bx1.checkbox("Show BigBO", value=False, key="ama_show_bigbo")
                _bbo_fact  = _bx2.number_input("BigBO range factor", min_value=0.5,
                                                max_value=5.0, value=1.05, step=0.05,
                                                format="%.2f", key="ama_bbo_factor")
                _show_cx   = _bx3.checkbox("Show CX",   value=False, key="ama_show_cx")

                st.divider()
                if st.button("Generate AMA Signals", key="ama_generate"):
                    if not _selected_types:
                        st.warning("Select at least one signal type.")
                    else:
                        _ama_sig = _run_ama(
                            _ama_bars,
                            int(_ama_stop_off),
                            _ama_tgt_mode,
                            float(_ama_tgt_mult),
                            _selected_types,
                            ob_requires_ft=bool(_ob_ft),
                            bl_signal_ibs=int(_bl_ibs),
                            br_signal_ibs=int(_br_ibs),
                            bl_ft_ibs=int(_bl_ft),
                            br_ft_ibs=int(_br_ft),
                            range_filter=float(_rng_filt),
                            range_lookback=int(_rng_lb),
                            ft_must_close_beyond=int(_ft_close),
                            show_bigbo=int(_show_bbo),
                            big_bo_range_factor=float(_bbo_fact),
                            show_cx=int(_show_cx),
                            strict_ob=int(_strict),
                        )
                        st.session_state["ba_signals_ama"] = _ama_sig
                        st.success(f"Generated {len(_ama_sig):,} AMA signals.")

                if st.session_state.get("ba_signals_ama") is not None:
                    _n = len(st.session_state["ba_signals_ama"])
                    st.caption(f"✅ {_n:,} signals ready  "
                               f"({_ama_stop_off}t offset · {_ama_tgt_mode} ×{_ama_tgt_mult:.1f})")

        # ZLO overlay data
        _ZLO_DISK = _SIGNALS_DIR / "ba_zlo_overlay.parquet"
        with st.expander("📈 ZLO Overlay (optional)", expanded=False):
            zlo_file = st.file_uploader(
                "ZLO Export (.csv)", type=["csv"], key="upload_zlo",
                help="CSV from NT ZerolagExporter: DateTime,Open,High,Low,Close,Oscillator,BaseTrend,TrendState,signals…",
            )
            if zlo_file is not None:
                zlo_key = f"{zlo_file.name}_{zlo_file.size}"
                if st.session_state.get("ba_zlo_key") != zlo_key:
                    zlo_df = pd.read_csv(zlo_file, parse_dates=["DateTime"])
                    st.session_state["ba_zlo"] = zlo_df
                    st.session_state["ba_zlo_key"] = zlo_key
                    zlo_df.to_parquet(_ZLO_DISK, index=False)
                if st.session_state.get("ba_zlo") is not None:
                    st.caption(f"✅ {zlo_file.name}  |  {len(st.session_state['ba_zlo'])} bars")
            else:
                if "ba_zlo" not in st.session_state and _ZLO_DISK.exists():
                    st.session_state["ba_zlo"] = pd.read_parquet(_ZLO_DISK)
                if st.session_state.get("ba_zlo") is not None:
                    st.caption(f"✅ (auto-loaded from disk)  |  {len(st.session_state['ba_zlo'])} bars")

        # Always In (AID) flip-state overlay
        _AI_DISK = _SIGNALS_DIR / "ba_alwaysin_overlay.parquet"
        with st.expander("🧭 Always In State (optional)", expanded=False):
            ai_file = st.file_uploader(
                "AlwaysIn flips (.csv)", type=["csv"], key="upload_alwaysin",
                help="CSV from the NT AlwaysIn indicator: Event,BarTime,BarNum,NewDir,…  (flip rows)",
            )
            if ai_file is not None:
                ai_key = f"{ai_file.name}_{ai_file.size}"
                if st.session_state.get("ba_alwaysin_key") != ai_key:
                    ai_df = pd.read_csv(ai_file, parse_dates=["BarTime"])
                    st.session_state["ba_alwaysin"] = ai_df
                    st.session_state["ba_alwaysin_key"] = ai_key
                    ai_df.to_parquet(_AI_DISK, index=False)
                if st.session_state.get("ba_alwaysin") is not None:
                    st.caption(f"✅ {ai_file.name}  |  {len(st.session_state['ba_alwaysin'])} flips")
            else:
                if "ba_alwaysin" not in st.session_state and _AI_DISK.exists():
                    st.session_state["ba_alwaysin"] = pd.read_parquet(_AI_DISK)
                if st.session_state.get("ba_alwaysin") is not None:
                    st.caption(f"✅ (auto-loaded from disk)  |  {len(st.session_state['ba_alwaysin'])} flips")

        active_set = st.radio(
            "Active Signal Set",
            ["MC Signals", "RevFT Signals", "AMA Signals"],
            key="ba_active_signal_set",
            horizontal=True,
        )
        st.session_state["ba_signals"] = {
            "MC Signals":   st.session_state.get("ba_signals_mc"),
            "RevFT Signals": st.session_state.get("ba_signals_revft"),
            "AMA Signals":  st.session_state.get("ba_signals_ama"),
        }.get(active_set)

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)

    with tab4:
        portfolio.show_portfolio()

    with tab_wfa:
        wfa_mod.show_wfa_tab()

    with tab_extras:
        extras.show_extras_tab()

    with tab_prop:
        prop_sim.show_prop_sim_tab()

    with tab_auction:
        auction_tab.show_auction_tab()

    with tab_erc:
        er_lookahead_tab.show_er_lookahead_tab()

    # Render the status strip now that all tabs have populated session state.
    with status_ph:
        _render_status_strip()


main()
