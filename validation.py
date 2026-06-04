import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data_loader import load_sc_bars, load_nt_bars, NT_FILE, TICK_SIZE

PRICE_FIELDS = ["Open", "High", "Low", "Close"]
ALL_FIELDS   = ["Open", "High", "Low", "Close", "Volume"]
FIELD_COLORS = {
    "Open":   "#1f77b4",
    "High":   "#2ca02c",
    "Low":    "#d62728",
    "Close":  "#9467bd",
    "Volume": "#ff7f0e",
}


# ── Comparison engine ─────────────────────────────────────────────────────────

def build_comparison(sc: pd.DataFrame, nt: pd.DataFrame) -> pd.DataFrame:
    sc_m = sc.rename(columns={c: f"{c}_sc" for c in ALL_FIELDS}).set_index("DateTime")
    nt_m = nt.rename(columns={c: f"{c}_nt" for c in ALL_FIELDS}).set_index("DateTime")

    m = sc_m.join(nt_m, how="outer")
    matched = m["Open_sc"].notna() & m["Open_nt"].notna()

    m["Status"] = "Matched"
    m.loc[m["Open_sc"].notna() & m["Open_nt"].isna(), "Status"] = "SC only"
    m.loc[m["Open_sc"].isna() & m["Open_nt"].notna(), "Status"] = "NT only"

    # Price deltas in ticks
    for col in PRICE_FIELDS:
        m[f"Δ{col}"] = np.nan
        if matched.any():
            m.loc[matched, f"Δ{col}"] = (
                (m.loc[matched, f"{col}_nt"] - m.loc[matched, f"{col}_sc"]) / TICK_SIZE
            ).round(0)

    # Volume delta in absolute contracts
    m["ΔVolume"] = np.nan
    if matched.any():
        m.loc[matched, "ΔVolume"] = (
            m.loc[matched, "Volume_nt"].astype(float) -
            m.loc[matched, "Volume_sc"].astype(float)
        )

    # Match flags (only meaningful for matched rows)
    m["OHLC_match"]  = False
    m["OHLCV_match"] = False
    if matched.any():
        ohlc_ok = m.loc[matched, [f"Δ{c}" for c in PRICE_FIELDS]].eq(0).all(axis=1)
        vol_ok  = m.loc[matched, "ΔVolume"].eq(0)
        m.loc[matched, "OHLC_match"]  = ohlc_ok
        m.loc[matched, "OHLCV_match"] = ohlc_ok & vol_ok

    m["Date"]    = m.index.normalize()
    m["BarTime"] = m.index.strftime("%H:%M")
    return m.reset_index()


# ── Tab entry point ───────────────────────────────────────────────────────────

def show_validation_tab():
    if not NT_FILE.exists():
        st.error(f"NT data file not found:\n`{NT_FILE}`")
        return

    sc = load_sc_bars()
    nt = load_nt_bars()

    sc_dates = sc["DateTime"].dt.date
    nt_dates = nt["DateTime"].dt.date
    overlap_min = max(sc_dates.min(), nt_dates.min())
    overlap_max = min(sc_dates.max(), nt_dates.max())
    all_min     = min(sc_dates.min(), nt_dates.min())
    all_max     = max(sc_dates.max(), nt_dates.max())

    c1, c2, _ = st.columns([1, 1, 2])
    date_from = c1.date_input("From", value=overlap_min, min_value=all_min, max_value=all_max)
    date_to   = c2.date_input("To",   value=overlap_max, min_value=all_min, max_value=all_max)

    sc_f = sc[(sc_dates >= date_from) & (sc_dates <= date_to)]
    nt_f = nt[(nt_dates >= date_from) & (nt_dates <= date_to)]

    comp    = build_comparison(sc_f, nt_f)
    matched = comp[comp["Status"] == "Matched"]

    n_matched  = len(matched)
    n_sc_only  = int((comp["Status"] == "SC only").sum())
    n_nt_only  = int((comp["Status"] == "NT only").sum())
    n_ohlc_mm  = int((~matched["OHLC_match"]).sum())   if n_matched else 0
    n_vol_mm   = int(matched["ΔVolume"].ne(0).sum())   if n_matched else 0
    n_ohlcv_mm = int((~matched["OHLCV_match"]).sum())  if n_matched else 0
    pct_ohlc   = (1 - n_ohlc_mm  / n_matched) * 100   if n_matched else 0.0
    pct_ohlcv  = (1 - n_ohlcv_mm / n_matched) * 100   if n_matched else 0.0

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.subheader("Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Matched Bars",      f"{n_matched:,}")
    m2.metric("SC Only",           f"{n_sc_only:,}")
    m3.metric("NT Only",           f"{n_nt_only:,}")
    m4.metric("OHLC Exact Match",  f"{pct_ohlc:.1f}%")
    m5.metric("OHLCV Exact Match", f"{pct_ohlcv:.1f}%")

    m6, m7, m8, _, _ = st.columns(5)
    m6.metric("OHLC Mismatches",  f"{n_ohlc_mm:,}")
    m7.metric("Vol Mismatches",   f"{n_vol_mm:,}")
    m8.metric("OHLCV Mismatches", f"{n_ohlcv_mm:,}")

    # ── Field breakdown table ──────────────────────────────────────────────────
    st.subheader("Mismatch by Field")
    _show_field_table(matched)

    # ── NT null-volume bars ────────────────────────────────────────────────────
    null_vol = nt_f[nt_f["NullVol"]].copy()
    n_null_vol = len(null_vol)
    if n_null_vol > 0:
        null_vol["DateTime"] = null_vol["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
        with st.expander(f"⚠️ NT bars with null Volume (filled as 0) — {n_null_vol} bar{'s' if n_null_vol > 1 else ''}"):
            st.caption("These bars existed in the NT file with no volume value. Volume was set to 0 for comparison purposes.")
            st.dataframe(
                null_vol[["DateTime", "Open", "High", "Low", "Close"]],
                use_container_width=True, hide_index=True,
            )

    # ── Unmatched bars ─────────────────────────────────────────────────────────
    if n_sc_only > 0 or n_nt_only > 0:
        with st.expander(f"Unmatched bars — SC only: {n_sc_only}  |  NT only: {n_nt_only}"):
            uc1, uc2 = st.columns(2)
            sc_only = comp[comp["Status"] == "SC only"][
                ["DateTime", "Open_sc", "High_sc", "Low_sc", "Close_sc", "Volume_sc"]
            ].copy()
            nt_only = comp[comp["Status"] == "NT only"][
                ["DateTime", "Open_nt", "High_nt", "Low_nt", "Close_nt", "Volume_nt"]
            ].copy()
            sc_only["DateTime"] = sc_only["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            nt_only["DateTime"] = nt_only["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            with uc1:
                st.caption("In SC, missing from NT")
                st.dataframe(sc_only, use_container_width=True, hide_index=True)
            with uc2:
                st.caption("In NT, missing from SC")
                st.dataframe(nt_only, use_container_width=True, hide_index=True)

    # ── Sub-views ──────────────────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs([
        "🔎 Mismatch Table",
        "🕐 Time of Day",
        "📅 By Date",
        "📊 Delta Distribution",
    ])
    with t1:
        _show_mismatch_table(matched)
    with t2:
        _show_time_of_day(matched)
    with t3:
        _show_by_date(matched)
    with t4:
        _show_delta_distribution(matched)


# ── Sub-view functions ────────────────────────────────────────────────────────

def _show_field_table(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars in range.")
        return

    rows = []
    for col in PRICE_FIELDS:
        d     = matched[f"Δ{col}"].dropna()
        wrong = d[d.ne(0)]
        rows.append({
            "Field":          col,
            "Unit":           "ticks",
            "✓ Correct":     int(d.eq(0).sum()),
            "✗ Mismatch":    int(len(wrong)),
            "Min Δ":         f"{wrong.min():.0f}"      if len(wrong) else "—",
            "Max Δ":         f"{wrong.max():.0f}"      if len(wrong) else "—",
            "Mean |Δ|":      f"{wrong.abs().mean():.2f}" if len(wrong) else "—",
        })
    d     = matched["ΔVolume"].dropna()
    wrong = d[d.ne(0)]
    rows.append({
        "Field":       "Volume",
        "Unit":        "contracts",
        "✓ Correct":  int(d.eq(0).sum()),
        "✗ Mismatch": int(len(wrong)),
        "Min Δ":      f"{wrong.min():.0f}"       if len(wrong) else "—",
        "Max Δ":      f"{wrong.max():.0f}"       if len(wrong) else "—",
        "Mean |Δ|":   f"{wrong.abs().mean():.0f}" if len(wrong) else "—",
    })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _show_mismatch_table(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    show_all = st.checkbox("Show all matched bars (not just mismatches)", value=False)
    subset   = matched if show_all else matched[~matched["OHLC_match"]]

    if subset.empty:
        st.success("No OHLC mismatches in the selected range." if not show_all else "No matched bars.")
        return

    # Column order: per-field grouping for easy reading
    display_cols = ["DateTime"]
    for c in PRICE_FIELDS:
        display_cols += [f"{c}_sc", f"{c}_nt", f"Δ{c}"]
    display_cols += ["Volume_sc", "Volume_nt", "ΔVolume"]

    display = subset[display_cols].copy()
    display["DateTime"] = display["DateTime"].dt.strftime("%Y-%m-%d %H:%M")

    def _color_delta(val):
        try:
            v = float(val)
            if v == 0: return ""
            return "color: #d62728" if v < 0 else "color: #ff9800"
        except (TypeError, ValueError):
            return ""

    price_fmt  = {f"{c}_{s}": "{:.2f}" for c in PRICE_FIELDS for s in ("sc", "nt")}
    delta_fmt  = {f"Δ{c}": "{:+.0f}" for c in PRICE_FIELDS}
    delta_cols = list(delta_fmt.keys()) + ["ΔVolume"]

    styled = (
        display.style
        .map(_color_delta, subset=delta_cols)
        .format(price_fmt | delta_fmt | {"ΔVolume": "{:+.0f}", "Volume_sc": "{:.0f}", "Volume_nt": "{:.0f}"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)
    st.caption(
        f"Showing {len(subset):,} bars  |  "
        f"Δ in ticks for OHLC  |  Δ in contracts for Volume  |  "
        f"🟠 NT > SC  🔴 NT < SC"
    )


def _show_time_of_day(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    tod = (
        matched.groupby("BarTime", sort=True)
        .agg(
            Total=("OHLC_match", "count"),
            OHLC_MM=("OHLC_match", lambda x: (~x).sum()),
        )
        .reset_index()
    )
    tod["Rate%"] = (tod["OHLC_MM"] / tod["Total"] * 100).round(1)

    fig = go.Figure()
    fig.add_bar(
        x=tod["BarTime"], y=tod["OHLC_MM"],
        name="OHLC Mismatches", marker_color="#ef5350",
    )
    fig.add_scatter(
        x=tod["BarTime"], y=tod["Rate%"],
        name="Mismatch Rate %", mode="lines+markers",
        yaxis="y2", line=dict(color="#ff9800", width=2),
        marker=dict(size=5),
    )
    y2_max = max(tod["Rate%"].max() * 1.3, 5)
    fig.update_layout(
        title="OHLC Mismatches by Bar Time Slot",
        xaxis_title="Bar Open Time (CT)",
        yaxis_title="# Mismatches",
        yaxis2=dict(title="Mismatch Rate %", overlaying="y", side="right", range=[0, y2_max]),
        xaxis=dict(tickangle=-45),
        template="plotly_white", height=420,
        legend=dict(x=0.01, y=0.99),
    )
    st.plotly_chart(fig, use_container_width=True)

    worst = tod[tod["OHLC_MM"] > 0].sort_values("Rate%", ascending=False)
    if not worst.empty:
        st.caption(f"Bar slots with at least one mismatch: {len(worst)} of {len(tod)}")
        st.dataframe(
            worst.rename(columns={
                "BarTime": "Time (CT)", "Total": "Total Bars",
                "OHLC_MM": "Mismatches", "Rate%": "Rate %",
            }),
            use_container_width=True, hide_index=True,
        )


def _show_by_date(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    by_date = (
        matched.groupby("Date")
        .agg(
            Total=("OHLC_match", "count"),
            OHLC_MM=("OHLC_match", lambda x: (~x).sum()),
        )
        .reset_index()
    )
    by_date["Rate%"] = (by_date["OHLC_MM"] / by_date["Total"] * 100).round(1)
    by_date["Date"]  = pd.to_datetime(by_date["Date"])

    fig = go.Figure()
    fig.add_bar(
        x=by_date["Date"], y=by_date["OHLC_MM"],
        name="Mismatches", marker_color="#ef5350",
        text=by_date["Rate%"].apply(lambda v: f"{v:.0f}%" if v > 0 else ""),
        textposition="outside",
    )
    fig.update_layout(
        title="OHLC Mismatches per Trading Day",
        xaxis_title="Date", yaxis_title="# Mismatched Bars",
        template="plotly_white", height=420,
        xaxis=dict(tickformat="%b %d", tickangle=-45),
        uniformtext_minsize=8, uniformtext_mode="hide",
    )
    st.plotly_chart(fig, use_container_width=True)

    worst = by_date[by_date["OHLC_MM"] > 0].sort_values("OHLC_MM", ascending=False)
    if not worst.empty:
        st.caption(f"Days with at least one mismatch: {len(worst)} of {len(by_date)}")
        st.dataframe(
            worst.assign(Date=worst["Date"].dt.strftime("%a %b %d, %Y"))
                 .rename(columns={"Total": "Bars", "OHLC_MM": "Mismatches", "Rate%": "Rate %"}),
            use_container_width=True, hide_index=True,
        )


def _show_delta_distribution(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    nonzero_only = st.checkbox("Exclude Δ = 0 bars", value=False)

    # OHLC histograms
    fig = go.Figure()
    for col in PRICE_FIELDS:
        vals = matched[f"Δ{col}"].dropna()
        if nonzero_only:
            vals = vals[vals.ne(0)]
        if len(vals):
            fig.add_histogram(
                x=vals, name=col, opacity=0.7,
                marker_color=FIELD_COLORS[col], xbins=dict(size=1),
            )
    fig.update_layout(
        barmode="overlay",
        title="OHLC Delta Distribution (ticks)",
        xaxis_title="NT − SC (ticks)", yaxis_title="Count",
        template="plotly_white", height=380,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Volume histogram
    vol = matched["ΔVolume"].dropna()
    if nonzero_only:
        vol = vol[vol.ne(0)]
    if len(vol):
        fig2 = go.Figure()
        fig2.add_histogram(
            x=vol, name="Volume",
            marker_color=FIELD_COLORS["Volume"], nbinsx=60,
        )
        fig2.update_layout(
            title="Volume Delta Distribution (contracts)",
            xaxis_title="NT − SC (contracts)", yaxis_title="Count",
            template="plotly_white", height=320,
        )
        st.plotly_chart(fig2, use_container_width=True)
