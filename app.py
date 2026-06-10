import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (load_sc_bars, CONTRACTS, bar_num_from_dt,
                         parse_sc_ticks_from_upload, parse_nt_ticks_from_upload,
                         parse_scid_ticks_from_upload,
                         resample_ticks_to_bars, parse_ohlc_from_upload, parse_sc_ohlc_from_upload,
                         discover_scid_files, build_scid_quarter_map, load_scid_ticks_chunked,
                         save_scid_cache, save_last_selection, load_scid_cache, clear_scid_cache,
                         list_cached_quarters, load_quarters_from_cache, build_bars_from_cache)
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
    uploaded_sc   = st.session_state.get("uploaded_sc_bars")
    uploaded_ohlc = st.session_state.get("uploaded_ohlc_bars")
    bar_source    = st.session_state.get("bar_source", "none")

    if uploaded_sc is None and uploaded_ohlc is None:
        st.info("Upload data in the **📁 Upload Data** panel in Bar Analysis to begin.")
        return

    # bar_source only matters to pick between two loaded upload types
    if uploaded_sc is not None and (bar_source != "ohlc_upload" or uploaded_ohlc is None):
        bars = uploaded_sc
    elif uploaded_ohlc is not None:
        bars = uploaded_ohlc
    else:
        st.info("Upload data in the **📁 Upload Data** panel in Bar Analysis to begin.")
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


# ── App entry point ───────────────────────────────────────────────────────────

def main():
    # ── Auto-load Parquet cache on first run of the session ───────────────────
    if "uploaded_sc_bars" not in st.session_state:
        _cached_ticks, _cache_meta = load_scid_cache()
        if _cached_ticks is not None:
            _cached_bars = resample_ticks_to_bars(_cached_ticks)
            st.session_state["uploaded_sc_ticks"]  = _cached_ticks
            st.session_state["uploaded_sc_bars"]   = _cached_bars
            st.session_state["uploaded_sc_key"]    = f"scid_{','.join(_cache_meta['quarters'])}"
            st.session_state["scid_loaded_label"]  = (
                f"{_cache_meta['quarters'][0]}–{_cache_meta['quarters'][-1]}"
                if len(_cache_meta["quarters"]) > 1 else _cache_meta["quarters"][0]
            )
            st.session_state["bar_source"] = "sc_upload"
            st.session_state.pop("bar_source_radio", None)

    st.title("ES Futures — 5-Minute RTH Bars")

    hdr_l, hdr_r = st.columns([8, 2])
    hdr_l.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    from pathlib import Path
    contract_keys = [k for k, v in CONTRACTS.items() if Path(v["sc_file"]).exists()]
    if not contract_keys:
        st.error("No SC data files found in data/raw/. Add at least one contract file.")
        st.stop()

    if len(contract_keys) > 1:
        selected_key = hdr_r.selectbox(
            "Contract", contract_keys,
            index=0, key="active_contract", label_visibility="collapsed",
        )
    else:
        selected_key = contract_keys[0]

    sc_file = str(CONTRACTS[selected_key]["sc_file"])
    nt_file = str(CONTRACTS[selected_key]["nt_file"])

    _rl_col, _src_col = st.columns([1, 10])
    if _rl_col.button("🔄 Reload", help="Clears all uploaded data from session."):
        st.cache_data.clear()
        for k in ("uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_ohlc_bars",
                  "uploaded_sc_key", "uploaded_ohlc_key", "ba_signals", "ba_signals_key",
                  "scid_load_summary", "scid_loaded_label", "scid_quarter_map",
                  "bar_source", "bar_source_radio"):
            st.session_state.pop(k, None)
        st.rerun()

    # ── Source selector — runs BEFORE tabs so bar_source is current on every render ──
    _sc_on_disk      = bool(sc_file and Path(sc_file).exists())
    _has_sc_upload   = st.session_state.get("uploaded_sc_bars")  is not None
    _has_ohlc_upload = st.session_state.get("uploaded_ohlc_bars") is not None

    _source_opts: list[tuple[str, str]] = []
    if _has_sc_upload:
        _source_opts.append(("SC Ticks / SCID", "sc_upload"))
    if _has_ohlc_upload:
        _source_opts.append(("OHLC bar export", "ohlc_upload"))

    if len(_source_opts) > 1:
        _src_labels = [s[0] for s in _source_opts]
        _src_keys   = [s[1] for s in _source_opts]
        _prev     = st.session_state.get("bar_source", "sc_upload")
        _prev_idx = _src_keys.index(_prev) if _prev in _src_keys else 0
        _chosen = _src_col.radio(
            "Bar data source", _src_labels,
            index=_prev_idx, horizontal=True, key="bar_source_radio",
            label_visibility="collapsed",
        )
        st.session_state["bar_source"] = _src_keys[_src_labels.index(_chosen)]
    elif _has_sc_upload:
        st.session_state["bar_source"] = "sc_upload"
    elif _has_ohlc_upload:
        st.session_state["bar_source"] = "ohlc_upload"
    else:
        st.session_state["bar_source"] = "none"

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Bar Viewer", "🔍 Bar Validation", "📈 Bar Analysis", "📊 Portfolio"])

    contract_label = selected_key.split(" — ")[0]

    with tab1:
        show_bar_viewer(sc_file, contract=contract_label)

    with tab2:
        validation.show_validation_tab(sc_file=sc_file, nt_file=nt_file)

    with tab3:
        # ── Upload expander ───────────────────────────────────────────────────
        with st.expander("📁 Upload Data", expanded=False):
            up_l, up_m, up_r = st.columns(3)

            tick_file = up_l.file_uploader(
                "Tick Data (.txt / .scid)", type=["txt", "csv", "scid"], key="upload_tick",
                help="SC BarData (.txt), NT8 tick export (.txt), or Sierra Chart binary (.scid) — auto-detected",
            )
            ohlc_file = up_m.file_uploader(
                "OHLC 5M bar_export (.txt/.csv)", type=["txt", "csv"], key="upload_ohlc",
                help="MM/DD/YYYY HH:MM:SS;O;H;L;C;V — Berlin close times",
            )
            sig_file = up_r.file_uploader(
                "MC Signals (.txt/.csv)", type=["txt", "csv"], key="upload_signals",
                help="Space-delimited: Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop",
            )

            # Tick upload
            if tick_file is not None:
                tick_key = f"{tick_file.name}_{tick_file.size}"
                if st.session_state.get("uploaded_sc_key") != tick_key:
                    tick_file.seek(0)
                    magic = tick_file.read(4)
                    is_scid = magic == b"SCID"
                    tick_file.seek(0)

                    if is_scid:
                        fmt_label = "SCID"
                        is_nt = False
                    else:
                        peek = magic + tick_file.read(196)
                        if isinstance(peek, bytes):
                            peek = peek.decode("utf-8", errors="replace")
                        first_line = peek.split("\n")[0].strip()
                        tick_file.seek(0)
                        is_nt = bool(re.match(r"^\d{8} \d{6} \d+;", first_line))
                        fmt_label = "NT8" if is_nt else "SC"

                    st.caption(f"Parsing {fmt_label} tick file ({tick_file.size / 1e6:.0f} MB)…")
                    pbar = st.progress(0)
                    if is_scid:
                        ticks = parse_scid_ticks_from_upload(tick_file)
                        pbar.progress(1.0)
                    elif is_nt:
                        ticks = parse_nt_ticks_from_upload(tick_file, progress=pbar.progress)
                        pbar.progress(1.0)
                    else:
                        ticks = parse_sc_ticks_from_upload(tick_file)
                        pbar.progress(1.0)
                    st.session_state["uploaded_sc_ticks"] = ticks
                    st.session_state["uploaded_sc_bars"]  = resample_ticks_to_bars(ticks)
                    st.session_state["uploaded_sc_key"]   = tick_key
                n_days = st.session_state["uploaded_sc_bars"]["DateTime"].dt.date.nunique()
                up_l.caption(f"✅ {tick_file.name}  |  {n_days} days")
            else:
                # Only wipe if data came from the uploader — preserve disk-loaded SCID data
                if not st.session_state.get("uploaded_sc_key", "").startswith("scid_"):
                    for k in ("uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_sc_key"):
                        st.session_state.pop(k, None)

            # OHLC upload
            if ohlc_file is not None:
                ohlc_key = f"{ohlc_file.name}_{ohlc_file.size}"
                if st.session_state.get("uploaded_ohlc_key") != ohlc_key:
                    with st.spinner("Parsing OHLC data…"):
                        st.session_state["uploaded_ohlc_bars"] = parse_ohlc_from_upload(ohlc_file)
                    st.session_state["uploaded_ohlc_key"] = ohlc_key
                n_days = st.session_state["uploaded_ohlc_bars"]["DateTime"].dt.date.nunique()
                up_m.caption(f"✅ {ohlc_file.name}  |  {n_days} days")
            else:
                for k in ("uploaded_ohlc_bars", "uploaded_ohlc_key"):
                    st.session_state.pop(k, None)

            # Signals upload
            if sig_file is not None:
                sig_key = f"{sig_file.name}_{sig_file.size}"
                if st.session_state.get("ba_signals_key") != sig_key:
                    raw = sig_file.read().decode("utf-8", errors="replace")
                    parsed = bar_analysis.parse_signals(raw)
                    if parsed is None or parsed.empty:
                        up_r.error("Could not parse signals.")
                    else:
                        st.session_state["ba_signals"]     = parsed
                        st.session_state["ba_signals_key"] = sig_key
                if st.session_state.get("ba_signals") is not None:
                    n_sig = len(st.session_state["ba_signals"])
                    up_r.caption(f"✅ {sig_file.name}  |  {n_sig} signals")
            else:
                for k in ("ba_signals", "ba_signals_key"):
                    st.session_state.pop(k, None)

        # ── SCID disk loader ─────────────────────────────────────────────────
        if discover_scid_files():
            with st.expander("📂 Load SCID from Disk", expanded=False):
                # Build quarter→file map once per session
                if "scid_quarter_map" not in st.session_state:
                    with st.spinner("Scanning all SCID files for available quarters…"):
                        st.session_state["scid_quarter_map"] = build_scid_quarter_map()
                _q_map = st.session_state["scid_quarter_map"]

                if _q_map:
                    _all_q = list(_q_map.keys())
                    # Apply "Select all" flag before the widget is instantiated
                    if st.session_state.pop("_scid_select_all", False):
                        st.session_state["scid_sel_quarters"] = _all_q
                    _n_cached = sum(1 for q in _all_q if q in set(list_cached_quarters()))
                    st.caption(
                        f"{len(_all_q)} quarters available across "
                        f"{len(set(_q_map.values()))} contract files  "
                        f"({_all_q[0]} – {_all_q[-1]})  ·  "
                        f"{_n_cached} cached (instant load)"
                    )
                    ca, cb = st.columns([3, 1])
                    _sel_q = ca.multiselect(
                        "Select quarters to load", _all_q,
                        default=_all_q, key="scid_sel_quarters",
                        label_visibility="collapsed",
                    )
                    if cb.button("Select all", key="scid_sel_all"):
                        st.session_state["_scid_select_all"] = True
                        st.rerun()

                    if st.button("Load selected quarters", key="scid_load_btn",
                                 disabled=not _sel_q):
                        _cached_q_set = set(list_cached_quarters())
                        _need_scid    = [q for q in _sel_q if q not in _cached_q_set]

                        # ── Parse from raw SCID only for quarters not yet cached ──
                        if _need_scid:
                            _by_file: dict[Path, set[str]] = {}
                            for q in _need_scid:
                                _by_file.setdefault(_q_map[q], set()).add(q)

                            all_new = []
                            pbar    = st.progress(0)
                            _status = st.empty()
                            for i, (fpath, fquarters) in enumerate(_by_file.items()):
                                _status.caption(f"Reading {fpath.stem}… ({i+1}/{len(_by_file)})")
                                frac_start = i / len(_by_file)
                                frac_end   = (i + 1) / len(_by_file)
                                def _prog(x, s=frac_start, e=frac_end):
                                    pbar.progress(s + x * (e - s))
                                ticks = load_scid_ticks_chunked(fpath, set(fquarters), progress=_prog)
                                if not ticks.empty:
                                    all_new.append(ticks)
                            _status.empty()
                            pbar.empty()

                            if all_new:
                                new_ticks = (pd.concat(all_new, ignore_index=True)
                                               .sort_values("DateTime").reset_index(drop=True))
                                with st.spinner("Saving to Parquet cache…"):
                                    save_scid_cache(new_ticks, _need_scid)
                            elif not (_cached_q_set & set(_sel_q)):
                                st.error("No RTH ticks found for the selected quarters.")
                                st.stop()

                        # ── Load from Parquet cache ──
                        # >16 quarters: build bars one quarter at a time to avoid OOM.
                        # ≤16 quarters: load full ticks (needed for tick-level simulation).
                        _TICK_Q_LIMIT = 16
                        if len(_sel_q) > _TICK_Q_LIMIT:
                            with st.spinner(f"Building 5-min bars from {len(_sel_q)} quarters…"):
                                bars = build_bars_from_cache(_sel_q)
                            combined = pd.DataFrame(columns=["DateTime", "Price", "Volume"])
                        else:
                            with st.spinner(f"Loading {len(_sel_q)} quarters from cache…"):
                                combined, _meta = load_quarters_from_cache(_sel_q)
                            if combined is None or combined.empty:
                                st.error("No ticks found — check Parquet cache.")
                                st.stop()
                            with st.spinner("Building 5-min bars…"):
                                bars = resample_ticks_to_bars(combined)
                        if bars.empty:
                            st.error("No bars produced — check Parquet cache.")
                            st.stop()
                        st.session_state["uploaded_sc_ticks"] = combined
                        st.session_state["uploaded_sc_bars"]  = bars
                        st.session_state["uploaded_sc_key"]   = f"scid_{','.join(_sel_q)}"
                        st.session_state["scid_loaded_label"] = (
                            f"{_sel_q[0]}–{_sel_q[-1]}" if len(_sel_q) > 1 else _sel_q[0]
                        )
                        st.session_state["bar_source"] = "sc_upload"
                        st.session_state.pop("bar_source_radio", None)
                        n_days = bars["DateTime"].dt.date.nunique()
                        st.session_state["scid_load_summary"] = (
                            f"{n_days} trading days  |  {len(_sel_q)} quarters  "
                            f"({_sel_q[0]}–{_sel_q[-1]})"
                        )
                        save_last_selection(_sel_q)
                        st.rerun()

                    # Persistent status line + cache controls
                    _summary = st.session_state.get("scid_load_summary")
                    if _summary:
                        _s_col, _c_col = st.columns([8, 2])
                        _s_col.success(f"✅ Loaded — {_summary}  |  Go to **Bar Viewer** or **Bar Validation** tabs.")
                        if _c_col.button("⏏️ Unload", key="scid_clear_cache",
                                         help="Clears loaded data from this session. Parquet cache on disk is kept."):
                            for k in ("uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_sc_key",
                                      "scid_load_summary", "scid_loaded_label"):
                                st.session_state.pop(k, None)
                            st.session_state["bar_source"] = "none"
                            st.rerun()
                else:
                    st.warning("No SCID files found in the Sierra Chart data folder.")

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)

    with tab4:
        portfolio.show_portfolio()


main()
