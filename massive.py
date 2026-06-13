import shutil
import streamlit as st
import pandas as pd
from data_loader import (
    fetch_massive_trades, fetch_massive_aggs,
    fetch_massive_contract_info, massive_ticker_to_nt_name,
    resample_ticks_to_bars, parse_ohlc_from_upload,
    MASSIVE_CACHE_DIR,
)
from validation import build_comparison

_PRICE_COLS = ["Open", "High", "Low", "Close"]


def _api_key() -> str:
    if st.session_state.get("mas_api_key"):
        return st.session_state["mas_api_key"]
    try:
        return st.secrets.get("MASSIVE_API_KEY", "")
    except Exception:
        return ""


def _status_box(bars: pd.DataFrame | None, label: str):
    if bars is not None:
        d = bars["DateTime"].dt.date
        st.success(f"✅ **{label}**  \n{d.nunique()} days · {d.min()} → {d.max()}")
    else:
        st.info(f"{label} — not loaded")


def _show_comparison(comp: pd.DataFrame, label_a: str, label_b: str):
    """Summary metrics + mismatch table for one build_comparison() result."""
    matched  = comp["Status"] == "Matched"
    n_match  = matched.sum()
    n_a_only = (comp["Status"] == "SC only").sum()
    n_b_only = (comp["Status"] == "NT only").sum()
    ohlc_pct  = comp.loc[matched, "OHLC_match"].mean()  * 100 if n_match else 0.0
    ohlcv_pct = comp.loc[matched, "OHLCV_match"].mean() * 100 if n_match else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Matched bars",       f"{n_match:,}")
    c2.metric(f"{label_a} only",    f"{n_a_only:,}")
    c3.metric(f"{label_b} only",    f"{n_b_only:,}")
    c4.metric("OHLC match",         f"{ohlc_pct:.1f}%")
    c5.metric("OHLCV match",        f"{ohlcv_pct:.1f}%")

    mismatches = comp[matched & ~comp["OHLC_match"]]
    if mismatches.empty:
        st.success("All matched bars have identical OHLC ✅")
        return

    with st.expander(f"Mismatch detail — {len(mismatches):,} bars", expanded=True):
        display = mismatches[[
            "DateTime", "BarTime",
            "Open_sc",  "Open_nt",  "ΔOpen",
            "High_sc",  "High_nt",  "ΔHigh",
            "Low_sc",   "Low_nt",   "ΔLow",
            "Close_sc", "Close_nt", "ΔClose",
        ]].copy()
        display.columns = [
            c.replace("_sc", f"_{label_a}").replace("_nt", f"_{label_b}")
            for c in display.columns
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Download CSV",
            display.to_csv(index=False, encoding="utf-8-sig"),
            f"mas_{label_a}_vs_{label_b}_mismatches.csv",
            "text/csv",
            key=f"dl_{label_a}_{label_b}",
        )


def show_massive_tab():
    st.markdown("### Massive.io — Tick Import & Three-Way Validation")
    st.caption(
        "Fetch ES ticks from Massive.io API, build 5M bars, compare against "
        "Massive agg bars and NT ES_MAS bars (imported from the same ticks)."
    )

    # ── API Config ───────────────────────────────────────────────────────────
    with st.expander("⚙️ Config", expanded=not _api_key()):
        col_key, col_ticker = st.columns([3, 1])

        raw_key = col_key.text_input(
            "Massive.io API Key",
            value=st.session_state.get("mas_api_key", ""),
            type="password",
            placeholder="Paste key here — stored in session only, not on disk",
        )
        if raw_key:
            st.session_state["mas_api_key"] = raw_key

        ticker = col_ticker.text_input(
            "Ticker",
            value=st.session_state.get("mas_ticker", "ESM6"),
            help="Massive.io contract ticker e.g. ESM6, ESZ5",
        )
        st.session_state["mas_ticker"] = ticker

        col_d1, col_d2 = st.columns(2)
        date_start = col_d1.text_input(
            "Start Date (YYYY-MM-DD)",
            value=st.session_state.get("mas_date_start", "2026-03-17"),
        )
        date_end = col_d2.text_input(
            "End Date (YYYY-MM-DD)",
            value=st.session_state.get("mas_date_end", "2026-06-20"),
        )
        st.session_state["mas_date_start"] = date_start
        st.session_state["mas_date_end"]   = date_end

        if st.button("🔎 Look up contract info", disabled=not _api_key()):
            try:
                info = fetch_massive_contract_info(_api_key(), ticker)
                nt_name = massive_ticker_to_nt_name(ticker, info["first_trade_date"])
                st.info(
                    f"**{ticker}** · {info['first_trade_date']} → {info['last_trade_date']}  \n"
                    f"NT name: `{nt_name}.Last.txt`  |  tick size: {info.get('tick_size', '—')}"
                )
            except Exception as e:
                st.error(f"Lookup failed: {e}")

    api_key = _api_key()

    # ── Data Status & Fetch ──────────────────────────────────────────────────
    st.markdown("#### Data")
    col_t, col_a, col_n = st.columns(3)

    tick_bars = st.session_state.get("mas_tick_bars")
    agg_bars  = st.session_state.get("mas_agg_bars")
    nt_bars   = st.session_state.get("mas_nt_bars")

    with col_t:
        _status_box(tick_bars, "Tick-built bars")
        if st.button("📥 Fetch Ticks → Build Bars", disabled=not api_key,
                     help="Fetches raw ticks, caches to parquet, resamples to 5M RTH bars."):
            try:
                with st.spinner(f"Fetching {ticker} ticks…"):
                    ticks = fetch_massive_trades(api_key, ticker, date_start, date_end)
                bars = resample_ticks_to_bars(ticks)
                st.session_state["mas_tick_bars"]  = bars
                st.session_state["mas_tick_ticks"] = ticks
                st.rerun()
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    with col_a:
        _status_box(agg_bars, "Massive agg bars")
        if st.button("📊 Fetch Agg Bars", disabled=not api_key,
                     help="Fetches Massive.io pre-built 5M bars as a reference."):
            try:
                with st.spinner(f"Fetching {ticker} agg bars…"):
                    bars = fetch_massive_aggs(api_key, ticker, date_start, date_end)
                st.session_state["mas_agg_bars"] = bars
                st.rerun()
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    with col_n:
        _status_box(nt_bars, "NT ES_MAS bars")
        nt_file = st.file_uploader(
            "Upload NT ES_MAS 5M export (.txt/.csv)",
            type=["txt", "csv"],
            key="mas_nt_upload",
            help="Run OHLCExporter on the ES_MAS chart in NT after importing ticks.",
        )
        if nt_file:
            _key = f"{nt_file.name}_{nt_file.size}"
            if st.session_state.get("mas_nt_key") != _key:
                with st.spinner("Parsing…"):
                    df = parse_ohlc_from_upload(nt_file)
                st.session_state["mas_nt_bars"] = df
                st.session_state["mas_nt_key"]  = _key
                st.rerun()

    # ── Cache ────────────────────────────────────────────────────────────────
    if st.button("🗑️ Clear Massive cache", help="Deletes parquet cache — next fetch re-downloads from API."):
        if MASSIVE_CACHE_DIR.exists():
            shutil.rmtree(MASSIVE_CACHE_DIR)
        for k in ("mas_tick_bars", "mas_tick_ticks", "mas_agg_bars",
                  "mas_nt_bars", "mas_nt_key"):
            st.session_state.pop(k, None)
        st.rerun()

    st.divider()

    # ── Comparison 1: Tick-built vs Massive Agg ──────────────────────────────
    st.markdown("#### Comparison 1 — Tick-Built Bars vs Massive Agg Bars")
    st.caption("Both sourced from Massive.io — should be identical if bar builder is correct.")

    if tick_bars is not None and agg_bars is not None:
        _show_comparison(build_comparison(tick_bars, agg_bars), "Tick", "Agg")
    else:
        missing = [l for l, d in [("Tick-built bars", tick_bars), ("Massive agg bars", agg_bars)] if d is None]
        st.info(f"Needs: {', '.join(missing)}")

    st.divider()

    # ── Comparison 2: Tick-built vs NT ES_MAS ────────────────────────────────
    st.markdown("#### Comparison 2 — Tick-Built Bars vs NT ES_MAS Bars")
    st.caption("Validates the full round-trip: Massive ticks → NT import → OHLCExporter → bars.")

    if tick_bars is not None and nt_bars is not None:
        _show_comparison(build_comparison(tick_bars, nt_bars), "Tick", "NT")
    else:
        missing = [l for l, d in [("Tick-built bars", tick_bars), ("NT ES_MAS bars", nt_bars)] if d is None]
        st.info(f"Needs: {', '.join(missing)}")
