import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (load_sc_bars, CONTRACTS, bar_num_from_dt,
                         parse_sc_ticks_from_upload, parse_nt_ticks_from_upload,
                         resample_ticks_to_bars, parse_ohlc_from_upload)
import validation
import bar_analysis

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
</style>
""", unsafe_allow_html=True)


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str,
                     show_bar_nums: bool = False,
                     excl_first_n: int = 0, excl_last_min: int = 0,
                     contract: str = "ES") -> go.Figure:
    fig = go.Figure(
        go.Candlestick(
            x=df["DateTime"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=contract,
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        )
    )
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
    bar_source    = st.session_state.get("bar_source", "sc_disk")
    uploaded_sc   = st.session_state.get("uploaded_sc_bars")
    uploaded_ohlc = st.session_state.get("uploaded_ohlc_bars")

    if bar_source == "sc_upload" and uploaded_sc is not None:
        bars = uploaded_sc
    elif bar_source == "ohlc_upload" and uploaded_ohlc is not None:
        bars = uploaded_ohlc
    elif sc_file:
        bars = load_sc_bars(sc_file)
    else:
        bars = load_sc_bars()

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

    if len(day) < 81:
        first_bar_time = day.iloc[0]["DateTime"].strftime("%H:%M")
        st.warning(f"Incomplete data: {len(day)} bars, starts at {first_bar_time} (not 08:30). "
                   "Bar numbers are correct — they reflect position from 08:30.")

    show_bar_nums = st.checkbox("Show bar numbers", value=False,
                                help="Labels every 3rd bar (1, 4, 7…) below the x-axis.")
    excl_first_n  = st.session_state.get("excl_first_n",  0)
    excl_last_min = st.session_state.get("excl_last_min", 0)
    st.plotly_chart(
        make_candlestick(day, selected_date.strftime("%B %d, %Y"),
                         show_bar_nums=show_bar_nums,
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
    st.title("ES Futures — 5-Minute RTH Bars")

    hdr_l, hdr_r = st.columns([8, 2])
    hdr_l.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    from pathlib import Path
    contract_keys = [k for k, v in CONTRACTS.items() if Path(v["sc_file"]).exists()]
    if not contract_keys:
        st.error("No SC data files found in data/raw/. Add at least one contract file.")
        st.stop()

    selected_key = hdr_r.selectbox(
        "Contract", contract_keys,
        index=0, key="active_contract", label_visibility="collapsed",
    )

    sc_file = str(CONTRACTS[selected_key]["sc_file"])
    nt_file = str(CONTRACTS[selected_key]["nt_file"])

    reload_col = st.columns([11, 1])[1]
    if reload_col.button("🔄 Reload", help="Clears all cached data and reloads from disk."):
        st.cache_data.clear()
        for k in ("uploaded_sc_bars", "uploaded_sc_ticks", "uploaded_ohlc_bars",
                  "uploaded_sc_key", "uploaded_ohlc_key", "ba_signals", "ba_signals_key"):
            st.session_state.pop(k, None)
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["📊 Bar Viewer", "🔍 Bar Validation", "📈 Bar Analysis"])

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
                "Tick Data (.txt)", type=["txt", "csv"], key="upload_tick",
                help="SC BarData or NT8 tick export — auto-detected",
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
                    peek = tick_file.read(200)
                    if isinstance(peek, bytes):
                        peek = peek.decode("utf-8", errors="replace")
                    first_line = peek.split("\n")[0].strip()
                    tick_file.seek(0)
                    is_nt = bool(re.match(r"^\d{8} \d{6} \d+;", first_line))
                    st.caption(f"Parsing {'NT8' if is_nt else 'SC'} tick file ({tick_file.size / 1e6:.0f} MB)…")
                    pbar = st.progress(0)
                    ticks = parse_nt_ticks_from_upload(tick_file, progress=pbar.progress) if is_nt \
                            else parse_sc_ticks_from_upload(tick_file)
                    pbar.progress(1.0)
                    st.session_state["uploaded_sc_ticks"] = ticks
                    st.session_state["uploaded_sc_bars"]  = resample_ticks_to_bars(ticks)
                    st.session_state["uploaded_sc_key"]   = tick_key
                n_days = st.session_state["uploaded_sc_bars"]["DateTime"].dt.date.nunique()
                up_l.caption(f"✅ {tick_file.name}  |  {n_days} days")
            else:
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

        # ── Bar data source selector ──────────────────────────────────────────
        _sc_on_disk      = bool(sc_file and Path(sc_file).exists())
        _has_sc_upload   = st.session_state.get("uploaded_sc_bars")  is not None
        _has_ohlc_upload = st.session_state.get("uploaded_ohlc_bars") is not None

        _source_opts: list[tuple[str, str]] = []
        if _has_sc_upload:
            _source_opts.append(("SC Ticks (upload)", "sc_upload"))
        if _has_ohlc_upload:
            _source_opts.append(("OHLC (upload)", "ohlc_upload"))
        if _sc_on_disk:
            _source_opts.append(("SC Ticks (disk)", "sc_disk"))

        if len(_source_opts) > 1:
            _src_labels = [s[0] for s in _source_opts]
            _src_keys   = [s[1] for s in _source_opts]
            _prev     = st.session_state.get("bar_source", _src_keys[0])
            _prev_idx = _src_keys.index(_prev) if _prev in _src_keys else 0
            with st.expander("📡 Bar data source", expanded=False):
                _chosen = st.radio(
                    "Source", _src_labels,
                    index=_prev_idx, horizontal=True, key="bar_source_radio",
                    label_visibility="collapsed",
                )
            st.session_state["bar_source"] = _src_keys[_src_labels.index(_chosen)]
        elif _source_opts:
            st.session_state["bar_source"] = _source_opts[0][1]
        else:
            st.session_state["bar_source"] = "sc_disk"

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)


main()
