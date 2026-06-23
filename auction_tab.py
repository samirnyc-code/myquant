"""auction_tab.py — explorer for the per-session auction feature library.

Reads the in-app continuous 5M bars (data_sc_5m), builds the session feature
matrix (auction_features.build_session_features), and surfaces the three views
that matter first: day-type distribution, the yesterday→today transition matrix,
and the gap-bias study. The raw per-session table is downloadable for deeper
mining. Run-button gated; results cached in session_state.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import auction_features as af

_ETH_PATH = Path(__file__).parent / "data" / "eth_levels.parquet"


def show_auction_tab():
    st.subheader("🏛️ Auction Features")
    st.caption("Per-session market-profile feature library — day-type "
               "classification, transition probabilities, and gap-behavior base "
               "rates. Foundation for the pattern scanner.")

    bars = st.session_state.get("data_sc_5m")
    if bars is None or bars.empty:
        st.info("Build the continuous 5M series in the **📂 Massive** tab first.")
        return

    eth = None
    if _ETH_PATH.exists():
        try:
            eth = pd.read_parquet(_ETH_PATH)
        except Exception:
            eth = None

    if st.button("▶ Build Auction Features", key="auc_run", type="primary"):
        with st.spinner("Building session features…"):
            f = af.build_session_features(bars, eth)
        st.session_state["auc_features"] = f

    f = st.session_state.get("auc_features")
    if f is None or f.empty:
        st.info(f"**{bars['DateTime'].dt.normalize().nunique()} sessions** ready — "
                "click **▶ Build Auction Features**.")
        return

    st.success(f"{len(f)} sessions analyzed "
               f"({f['Date'].min():%Y-%m-%d} → {f['Date'].max():%Y-%m-%d})")

    # ── Day-type distribution ────────────────────────────────────────────────
    with st.expander("📊 Day-Type Distribution", expanded=True):
        vc = f["day_type"].value_counts()
        c1, c2 = st.columns([2, 3])
        with c1:
            tbl = vc.rename_axis("day_type").reset_index(name="count")
            tbl["pct"] = (tbl["count"] / tbl["count"].sum() * 100).round(1)
            st.dataframe(tbl, use_container_width=True, hide_index=True)
        with c2:
            st.plotly_chart(
                px.bar(vc.rename_axis("day_type").reset_index(name="count"),
                       x="day_type", y="count", color="day_type",
                       title="Sessions by day type"),
                use_container_width=True)
        st.caption("Dalton (*Mind Over Markets* Ch.2): Normal · Normal Variation · "
                   "Trend · Double Distribution · Neutral (Center/Extreme) · Nontrend. "
                   "Nontrend = the quiet rotational 'TR' day. Tunable in "
                   "`auction_features._classify_day_type`.")

    # ── Transition matrix ────────────────────────────────────────────────────
    with st.expander("🔁 Day-Type Transition (yesterday → today)", expanded=True):
        tm = af.day_type_transition_matrix(f)
        if tm.empty:
            st.info("Not enough data.")
        else:
            st.plotly_chart(
                go.Figure(go.Heatmap(
                    z=tm.values, x=list(tm.columns), y=list(tm.index),
                    colorscale="Blues", text=tm.values,
                    texttemplate="%{text:.0f}%", colorbar_title="%")
                ).update_layout(
                    title="P(today | yesterday) — row-normalized %",
                    xaxis_title="today", yaxis_title="yesterday", height=420),
                use_container_width=True)
            st.caption("Read across a row: given yesterday's type, the probability "
                       "of each type today. Diagonal = persistence.")

    # ── Gap study ────────────────────────────────────────────────────────────
    with st.expander("⛳ Gap Behavior (bias by size & direction)", expanded=True):
        gs = af.gap_outcome_study(f)
        if gs.empty:
            st.info("Not enough data.")
        else:
            st.dataframe(gs, use_container_width=True, hide_index=True)
            st.caption("**fill_rate** = % of gaps that traded back to the prior "
                       "close same session. **go_with_rate** = % that closed in the "
                       "gap direction. Note the small→large fill-rate collapse — the "
                       "'gap-and-go' threshold.")

    # ── Raw feature table ────────────────────────────────────────────────────
    with st.expander("🔬 Per-Session Features (raw)", expanded=False):
        type_filter = st.multiselect(
            "Filter day type", sorted(f["day_type"].dropna().unique()),
            key="auc_type_filter")
        view = f[f["day_type"].isin(type_filter)] if type_filter else f
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Download features CSV",
            f.to_csv(index=False).encode("utf-8"),
            "auction_features.csv", "text/csv", key="auc_dl")
