import re
from pathlib import Path
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import (CONTRACTS, bar_num_from_dt,
                         parse_ohlc_from_upload,
                         load_csv_cache, save_csv_cache,
                         load_csv_manifest, save_csv_manifest, clear_csv_cache,
                         apply_data_slot,
                         load_excluded_dates, save_excluded_dates)
import bar_analysis
import portfolio
import massive
import validation
import wfa as wfa_mod
import continuous_chart

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

    s1, s2, s3, s4 = st.columns(4)
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

    # Bar Analysis is the landing tab (first = default-active in st.tabs).
    tab3, tab_massive, tab0, tab1, tab_chart, tab4, tab_wfa = st.tabs([
        "📈 Bar Analysis", "📂 Massive", "🗂️ Data", "📊 Bar Viewer", "📈 Chart", "📊 Portfolio", "🔄 WFA",
    ])

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

        _signal_uploader("📊 MC Signals", "upload_signals", "ba_signals_mc")
        _signal_uploader("🔁 RevFTSignals", "upload_signals_revft", "ba_signals_revft")

        active_set = st.radio(
            "Active Signal Set", ["MC Signals", "RevFTSignals"],
            key="ba_active_signal_set", horizontal=True,
        )
        st.session_state["ba_signals"] = (
            st.session_state.get("ba_signals_mc") if active_set == "MC Signals"
            else st.session_state.get("ba_signals_revft")
        )

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)

    with tab4:
        portfolio.show_portfolio()

    with tab_wfa:
        wfa_mod.show_wfa_tab()

    # Render the status strip now that all tabs have populated session state.
    with status_ph:
        _render_status_strip()


main()
