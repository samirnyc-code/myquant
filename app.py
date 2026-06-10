import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (load_sc_bars, CONTRACTS, bar_num_from_dt,
                         parse_sc_ticks_from_upload, parse_nt_ticks_from_upload,
                         parse_scid_ticks_from_upload,
                         resample_ticks_to_bars, resample_1s_ohlcv_to_5m,
                         parse_ohlc_from_upload, parse_sc_ohlc_from_upload,
                         load_csv_cache, save_csv_cache,
                         load_csv_manifest, save_csv_manifest, clear_csv_cache)
import validation
import bar_analysis
import portfolio

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

def _apply_data_slot(slot: str, df: pd.DataFrame, label: str, key: str) -> None:
    """Populate session state for a data slot and set all backward-compat aliases."""
    st.session_state[f"data_{slot}"]       = df
    st.session_state[f"data_{slot}_label"] = label
    st.session_state[f"data_{slot}_key"]   = key

    if slot == "sc_1s":
        py5m = resample_1s_ohlcv_to_5m(df)
        st.session_state["data_sc_py5m"]      = py5m
        st.session_state["uploaded_sc_bars"]  = py5m
        st.session_state["uploaded_sc_ticks"] = None
        st.session_state["uploaded_sc_key"]   = key
        st.session_state["scid_loaded_label"] = label
        st.session_state["bar_source"]        = "sc_upload"
    elif slot == "sc_5m":
        st.session_state["bv_sc5m_bars"] = df
        st.session_state["bv_sc5m_key"]  = key
    elif slot == "nt_5m":
        st.session_state["bv_nt5m_bars"]       = df
        st.session_state["bv_nt5m_key"]        = key
        st.session_state["uploaded_ohlc_bars"] = df
        st.session_state["uploaded_ohlc_key"]  = key


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str,
                     show_bar_nums: bool = False,
                     show_volume: bool = False,
                     excl_first_n: int = 0, excl_last_min: int = 0,
                     contract: str = "ES") -> go.Figure:
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
    return fig


# ── Bar Viewer tab ────────────────────────────────────────────────────────────

def show_bar_viewer(sc_file: str = "", contract: str = "ES"):
    bars = st.session_state.get("data_sc_py5m")

    if bars is None:
        st.info("Upload SC 1s data in the **📂 Data** tab to begin.")
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
    st.plotly_chart(
        make_candlestick(day, selected_date.strftime("%B %d, %Y"),
                         show_bar_nums=show_bar_nums,
                         show_volume=show_volume,
                         excl_first_n=excl_first_n, excl_last_min=excl_last_min,
                         contract=contract),
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
    st.markdown("### Data Sources")
    st.caption(
        "Upload SC and NT exports once — each file is cached to Parquet and reloaded "
        "automatically on next session. Export from the continuous **ESM26-CME [CB]** chart."
    )

    col_sc, col_nt = st.columns(2)

    # ── SC column ─────────────────────────────────────────────────────────────
    with col_sc:
        st.markdown("**Sierra Chart**")

        # SC 1s status
        _sc1s = st.session_state.get("data_sc_1s")
        if _sc1s is not None:
            _lbl  = st.session_state.get("data_sc_1s_label", "")
            _days = _sc1s["DateTime"].dt.date.nunique()
            _min  = _sc1s["DateTime"].dt.date.min()
            _max  = _sc1s["DateTime"].dt.date.max()
            st.success(f"✅ **SC 1s** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
        else:
            st.info("SC 1s — not loaded")

        sc_1s_file = st.file_uploader(
            "Upload SC 1s BarData (.txt / .csv)", type=["txt", "csv"], key="dt_sc1s",
            help="SC → Analysis → Export Chart Data → 1-Second bars (ESM26-CME [CB] chart)",
        )
        if sc_1s_file:
            _key = f"{sc_1s_file.name}_{sc_1s_file.size}"
            if st.session_state.get("data_sc_1s_key") != _key:
                _cached = load_csv_cache("sc_1s", sc_1s_file.name, sc_1s_file.size)
                if _cached is not None:
                    _df = _cached
                else:
                    with st.spinner("Parsing SC 1s data…"):
                        _df = parse_sc_ohlc_from_upload(sc_1s_file)
                    save_csv_cache(_df, "sc_1s", sc_1s_file.name, sc_1s_file.size)
                    _mf = load_csv_manifest()
                    _mf["sc_1s"] = {"name": sc_1s_file.name, "size": sc_1s_file.size}
                    save_csv_manifest(_mf)
                _apply_data_slot("sc_1s", _df, sc_1s_file.name, _key)
                st.rerun()

        st.divider()

        # SC 5M status
        _sc5m = st.session_state.get("data_sc_5m")
        if _sc5m is not None:
            _lbl  = st.session_state.get("data_sc_5m_label", "")
            _days = _sc5m["DateTime"].dt.date.nunique()
            _min  = _sc5m["DateTime"].dt.date.min()
            _max  = _sc5m["DateTime"].dt.date.max()
            st.success(f"✅ **SC 5M** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
        else:
            st.info("SC 5M — not loaded  *(required for Gate 1 validation)*")

        sc_5m_file = st.file_uploader(
            "Upload SC 5M BarData (.txt / .csv)", type=["txt", "csv"], key="dt_sc5m",
            help="SC → Analysis → Export Chart Data → 5-Minute bars (ESM26-CME [CB] chart)",
        )
        if sc_5m_file:
            _key = f"{sc_5m_file.name}_{sc_5m_file.size}"
            if st.session_state.get("data_sc_5m_key") != _key:
                _cached = load_csv_cache("sc_5m", sc_5m_file.name, sc_5m_file.size)
                if _cached is not None:
                    _df = _cached
                else:
                    with st.spinner("Parsing SC 5M data…"):
                        _df = parse_sc_ohlc_from_upload(sc_5m_file)
                    save_csv_cache(_df, "sc_5m", sc_5m_file.name, sc_5m_file.size)
                    _mf = load_csv_manifest()
                    _mf["sc_5m"] = {"name": sc_5m_file.name, "size": sc_5m_file.size}
                    save_csv_manifest(_mf)
                _apply_data_slot("sc_5m", _df, sc_5m_file.name, _key)
                st.rerun()

    # ── NT column ─────────────────────────────────────────────────────────────
    with col_nt:
        st.markdown("**NinjaTrader** *(optional)*")

        # NT 1s status
        _nt1s = st.session_state.get("data_nt_1s")
        if _nt1s is not None:
            _lbl  = st.session_state.get("data_nt_1s_label", "")
            _days = _nt1s["DateTime"].dt.date.nunique()
            _min  = _nt1s["DateTime"].dt.date.min()
            _max  = _nt1s["DateTime"].dt.date.max()
            st.success(f"✅ **NT 1s** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
        else:
            st.info("NT 1s — not loaded")

        nt_1s_file = st.file_uploader(
            "Upload NT 1s data (.txt / .csv)", type=["txt", "csv"], key="dt_nt1s",
            help="NinjaTrader 1-second OHLCV bar export",
        )
        if nt_1s_file:
            _key = f"{nt_1s_file.name}_{nt_1s_file.size}"
            if st.session_state.get("data_nt_1s_key") != _key:
                _cached = load_csv_cache("nt_1s", nt_1s_file.name, nt_1s_file.size)
                if _cached is not None:
                    _df = _cached
                else:
                    with st.spinner("Parsing NT 1s data…"):
                        _df = parse_ohlc_from_upload(nt_1s_file)
                    save_csv_cache(_df, "nt_1s", nt_1s_file.name, nt_1s_file.size)
                    _mf = load_csv_manifest()
                    _mf["nt_1s"] = {"name": nt_1s_file.name, "size": nt_1s_file.size}
                    save_csv_manifest(_mf)
                _apply_data_slot("nt_1s", _df, nt_1s_file.name, _key)
                st.rerun()

        st.divider()

        # NT 5M status
        _nt5m = st.session_state.get("data_nt_5m")
        if _nt5m is not None:
            _lbl  = st.session_state.get("data_nt_5m_label", "")
            _days = _nt5m["DateTime"].dt.date.nunique()
            _min  = _nt5m["DateTime"].dt.date.min()
            _max  = _nt5m["DateTime"].dt.date.max()
            st.success(f"✅ **NT 5M** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
        else:
            st.info("NT 5M — not loaded  *(required for Gate 2 validation)*")

        nt_5m_file = st.file_uploader(
            "Upload NT 5M data (.txt / .csv)", type=["txt", "csv"], key="dt_nt5m",
            help="NinjaTrader 5-minute OHLCV bar export (semicolon-delimited, bar close times)",
        )
        if nt_5m_file:
            _key = f"{nt_5m_file.name}_{nt_5m_file.size}"
            if st.session_state.get("data_nt_5m_key") != _key:
                _cached = load_csv_cache("nt_5m", nt_5m_file.name, nt_5m_file.size)
                if _cached is not None:
                    _df = _cached
                else:
                    with st.spinner("Parsing NT 5M data…"):
                        _df = parse_ohlc_from_upload(nt_5m_file)
                    if _df.empty:
                        st.error(
                            f"**{nt_5m_file.name}** parsed to 0 RTH bars.  \n"
                            "Expected format: comma-separated CSV with header "
                            "`DateTime,Open,High,Low,Close,Volume` and CT open times "
                            "(e.g. `2025-01-02 08:30:00`), OR semicolon-delimited TXT "
                            "with CT/Berlin close times.  \n"
                            f"First 200 chars of file: `{nt_5m_file.read(200)}`"
                        )
                        st.stop()
                    save_csv_cache(_df, "nt_5m", nt_5m_file.name, nt_5m_file.size)
                    _mf = load_csv_manifest()
                    _mf["nt_5m"] = {"name": nt_5m_file.name, "size": nt_5m_file.size}
                    save_csv_manifest(_mf)
                _apply_data_slot("nt_5m", _df, nt_5m_file.name, _key)
                st.rerun()

    # ── Cache management ──────────────────────────────────────────────────────
    st.divider()
    if st.button("🗑️ Clear all cached data", help="Deletes Parquet cache files and resets session."):
        clear_csv_cache()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_sc_key",
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
                "scid_loaded_label", "bar_source",
            ):
                st.session_state.pop(k, None)
        st.rerun()


# ── App entry point ───────────────────────────────────────────────────────────

def main():
    # ── Auto-load from CSV Parquet cache on first run ─────────────────────────
    if "data_sc_1s" not in st.session_state and "data_sc_5m" not in st.session_state:
        _mf = load_csv_manifest()
        for _slot in ("sc_1s", "sc_5m", "nt_1s", "nt_5m"):
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

    _rl_col, _ = st.columns([1, 10])
    if _rl_col.button("🔄 Reload", help="Clears session data (cache files are preserved)."):
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_sc_key",
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
                "ba_signals", "ba_signals_key", "scid_loaded_label",
                "bar_source", "bar_source_radio",
            ):
                st.session_state.pop(k, None)
        st.rerun()

    # Ensure bar_source is always set
    if "bar_source" not in st.session_state:
        st.session_state["bar_source"] = (
            "sc_upload" if st.session_state.get("data_sc_1s") is not None else "none"
        )

    tab0, tab1, tab2, tab3, tab4 = st.tabs([
        "📂 Data", "📊 Bar Viewer", "🔍 Bar Validation", "📈 Bar Analysis", "📊 Portfolio",
    ])

    contract_label = selected_key.split(" — ")[0] if selected_key else "ES"

    with tab0:
        show_data_tab()

    with tab1:
        show_bar_viewer(sc_file, contract=contract_label)

    with tab2:
        validation.show_validation_tab(sc_file=sc_file, nt_file=nt_file)

    with tab3:
        # Signals upload lives here (price data is in the Data tab)
        with st.expander("📊 MC Signals", expanded=False):
            sig_file = st.file_uploader(
                "MC Signals (.txt/.csv)", type=["txt", "csv"], key="upload_signals",
                help="Space-delimited: Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop",
            )
            if sig_file is not None:
                sig_key = f"{sig_file.name}_{sig_file.size}"
                if st.session_state.get("ba_signals_key") != sig_key:
                    raw    = sig_file.read().decode("utf-8", errors="replace")
                    parsed = bar_analysis.parse_signals(raw)
                    if parsed is None or parsed.empty:
                        st.error("Could not parse signals.")
                    else:
                        st.session_state["ba_signals"]     = parsed
                        st.session_state["ba_signals_key"] = sig_key
                if st.session_state.get("ba_signals") is not None:
                    n_sig = len(st.session_state["ba_signals"])
                    st.caption(f"✅ {sig_file.name}  |  {n_sig} signals")
            else:
                for k in ("ba_signals", "ba_signals_key"):
                    st.session_state.pop(k, None)

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)

    with tab4:
        portfolio.show_portfolio()


main()
