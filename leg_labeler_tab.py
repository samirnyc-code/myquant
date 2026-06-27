"""
leg_labeler_tab.py — Streamlit tab for manual leg labeling.

Workflow
--------
1. Load bar data (continuous parquet or uploaded file).
2. Run ATR-swing decomposition to auto-segment legs.
3. Chart shows candlesticks with colored leg segments (draft labels).
4. User picks a leg from a table or clicks on the chart.
5. User assigns a label from the taxonomy dropdown.
6. Save → writes to ground_truth_labels.parquet.

Lookahead discipline: the labeler works with full hindsight (this is
the ground-truth store). The live-call-log is NEVER written here.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import leg_decomp
import leg_label_store as lls

DATA_DIR = Path(__file__).parent / "data"

# Colour map for leg states
_STATE_COLORS = {
    "IMPULSE_L1":  "#00CC66",   # bright green
    "IMPULSE_LN":  "#66FFAA",   # light green
    "PB_L1":       "#FF8C00",   # dark orange
    "PB_L2":       "#FF4444",   # red
    "PB_L3":       "#CC0000",   # dark red
    "REVERSAL":    "#AA00FF",   # purple
    "UNLABELED":   "#888888",   # grey
}

_DIR_LABEL = {1: "Up", -1: "Down"}


# ── Chart ─────────────────────────────────────────────────────────────────────

def _make_chart(
    bars: pd.DataFrame,
    labels: pd.DataFrame,
    legs: pd.DataFrame,
    gt_labels: pd.DataFrame,
    selected_lid: int | None,
    threshold: float,
) -> go.Figure:
    """Build the Plotly candlestick chart with leg segment overlays."""
    fig = go.Figure()

    # ── Candlesticks ──────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=bars["DateTime"],
        open=bars["Open"],
        high=bars["High"],
        low=bars["Low"],
        close=bars["Close"],
        name="ES 5M",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        increasing_fillcolor="#26a69a",
        decreasing_fillcolor="#ef5350",
        line_width=1,
        whiskerwidth=0,
    ))

    # ── Leg overlays ─────────────────────────────────────────────────────────
    # Build a quick lookup: leg_id → assigned label
    gt_map = {}
    if not gt_labels.empty:
        for _, row in gt_labels.iterrows():
            gt_map[int(row["leg_id"])] = str(row["leg_state"])

    seen_states: set[str] = set()

    for _, leg in legs.iterrows():
        lid       = int(leg["leg_id"])
        state     = gt_map.get(lid, "UNLABELED")
        color     = _STATE_COLORS.get(state, "#888888")
        is_sel    = lid == selected_lid
        opacity   = 1.0 if is_sel else 0.45
        line_w    = 3   if is_sel else 1.5

        start_dt  = leg["start_dt"]
        end_dt    = leg["end_dt"]
        direction = int(leg["direction"])
        s_price   = float(leg["start_price"])
        e_price   = float(leg["end_price"])

        show_legend = state not in seen_states
        seen_states.add(state)

        # Shaded background for selected leg
        if is_sel:
            fig.add_vrect(
                x0=start_dt, x1=end_dt,
                fillcolor=color, opacity=0.12,
                layer="below", line_width=0,
            )

        # Diagonal line: start_price → end_price
        fig.add_trace(go.Scatter(
            x=[start_dt, end_dt],
            y=[s_price, e_price],
            mode="lines",
            line=dict(color=color, width=line_w, dash="solid"),
            opacity=opacity,
            name=state if show_legend else None,
            showlegend=show_legend,
            hovertemplate=(
                f"Leg {lid} | {state}<br>"
                f"Dir: {_DIR_LABEL.get(direction,'?')}<br>"
                f"{int(leg['length_bars'])} bars | {int(leg['length_ticks'])} ticks"
                "<extra></extra>"
            ),
        ))

    # ── ATR threshold annotation ───────────────────────────────────────────────
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.01, y=0.99,
        text=f"ATR threshold: {threshold:.2f}",
        showarrow=False,
        font=dict(size=11, color="#aaa"),
        align="left",
    )

    fig.update_layout(
        height=580,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#e0e0e0"),
        xaxis=dict(
            rangeslider=dict(visible=False),
            showgrid=True, gridcolor="#2a2a2a",
            type="date",
        ),
        yaxis=dict(showgrid=True, gridcolor="#2a2a2a"),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01,
            xanchor="left", x=0,
            font=dict(size=10),
        ),
        margin=dict(l=60, r=20, t=30, b=30),
    )
    return fig


# ── Tab body ──────────────────────────────────────────────────────────────────

def show_labeler_tab() -> None:
    st.subheader("Leg Labeler")
    st.caption(
        "ATR-swing decomposition → manual label assignment → ground_truth_labels.parquet. "
        "This is the hindsight label store. Never modifies the live call log."
    )

    # ── Data source ───────────────────────────────────────────────────────────
    cont = st.session_state.get("mas_continuous")
    sc   = st.session_state.get("data_sc_5m")
    bars_raw = cont if (cont is not None and not cont.empty) else sc

    if bars_raw is None or bars_raw.empty:
        st.info("Load bar data first (Data tab or Massive tab).")
        return

    # ── Controls ──────────────────────────────────────────────────────────────
    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])

    # Date range
    min_date = pd.to_datetime(bars_raw["DateTime"]).dt.date.min()
    max_date = pd.to_datetime(bars_raw["DateTime"]).dt.date.max()
    date_sel = ctrl1.date_input(
        "Date range",
        value=(max_date - pd.Timedelta(days=5), max_date),
        min_value=min_date,
        max_value=max_date,
        key="lbl_date_range",
    )
    if isinstance(date_sel, tuple) and len(date_sel) == 2:
        d_start, d_end = date_sel
    else:
        d_start = d_end = max_date

    # ATR threshold
    threshold = ctrl2.number_input(
        "ATR threshold",
        min_value=0.5, max_value=5.0, value=1.5, step=0.1, format="%.1f",
        key="lbl_threshold",
        help="ATR multiples to confirm a leg reversal. Lock this BEFORE labeling.",
    )

    # ATR period
    atr_period = ctrl3.number_input(
        "ATR period",
        min_value=5, max_value=50, value=14, step=1,
        key="lbl_atr_period",
    )

    # ── Filter bars to selected date range ────────────────────────────────────
    bars = bars_raw.copy()
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    mask  = (bars["DateTime"].dt.date >= d_start) & (bars["DateTime"].dt.date <= d_end)
    bars  = bars.loc[mask].reset_index(drop=True)

    if bars.empty:
        st.warning("No bars in selected date range.")
        return

    # ── Run decomposition ─────────────────────────────────────────────────────
    @st.cache_data(show_spinner="Running ATR-swing decomposition…")
    def _run_decomp(bars_key: str, thr: float, atr_p: int) -> tuple:
        # bars_key is just for cache invalidation
        return leg_decomp.decompose(bars, threshold=thr, atr_period=atr_p)

    cache_key = f"{d_start}_{d_end}_{len(bars)}"
    try:
        labels, legs = _run_decomp(cache_key, float(threshold), int(atr_period))
    except Exception as e:
        st.error(f"Decomposition error: {e}")
        return

    if legs.empty:
        st.warning("No legs detected — try lowering the ATR threshold.")
        return

    # ── Load existing labels ──────────────────────────────────────────────────
    gt_labels = lls.load_ground_truth()
    gt_map    = dict(zip(gt_labels["leg_id"].astype(int), gt_labels["leg_state"]))

    # ── Metrics strip ─────────────────────────────────────────────────────────
    n_legs      = len(legs)
    n_labeled   = sum(1 for lid in legs["leg_id"].astype(int) if gt_map.get(lid, "UNLABELED") != "UNLABELED")
    n_confirmed = int((legs["phase"] == "confirmed").sum())

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Legs detected",   n_legs)
    m2.metric("Confirmed",       n_confirmed)
    m3.metric("Labeled (GT)",    n_labeled)
    m4.metric("Unlabeled",       n_legs - n_labeled)

    # ── Selected leg state ────────────────────────────────────────────────────
    selected_lid = st.session_state.get("lbl_selected_lid")

    # ── Chart ─────────────────────────────────────────────────────────────────
    chart_fig = _make_chart(bars, labels, legs, gt_labels, selected_lid, threshold)
    st.plotly_chart(chart_fig, use_container_width=True, key="lbl_chart")

    st.divider()

    # ── Leg table + labeling panel ─────────────────────────────────────────────
    col_tbl, col_lbl = st.columns([3, 2])

    with col_tbl:
        st.markdown("**Legs in view**")

        # Build display table
        display = legs[[
            "leg_id", "direction", "phase", "start_dt", "end_dt",
            "length_bars", "length_ticks", "avg_atr",
        ]].copy()
        display["leg_state"] = display["leg_id"].astype(int).map(
            lambda lid: gt_map.get(lid, "UNLABELED")
        )
        display["dir"] = display["direction"].map({1: "↑ Up", -1: "↓ Down"})
        display["start_dt"] = pd.to_datetime(display["start_dt"]).dt.strftime("%m/%d %H:%M")
        display["end_dt"]   = pd.to_datetime(display["end_dt"]).dt.strftime("%H:%M")
        display["avg_atr"]  = display["avg_atr"].round(2)

        show_cols = ["leg_id", "dir", "phase", "start_dt", "end_dt",
                     "length_bars", "length_ticks", "avg_atr", "leg_state"]
        display = display[show_cols].rename(columns={
            "leg_id": "ID", "dir": "Dir", "phase": "Phase",
            "start_dt": "Start", "end_dt": "End",
            "length_bars": "Bars", "length_ticks": "Ticks",
            "avg_atr": "ATR", "leg_state": "Label",
        })

        sel_df = st.dataframe(
            display,
            use_container_width=True,
            height=320,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="lbl_leg_table",
        )

        # Update selected_lid from table click
        sel_rows = sel_df.selection.rows if hasattr(sel_df, "selection") else []
        if sel_rows:
            row_idx = sel_rows[0]
            clicked_lid = int(legs.iloc[row_idx]["leg_id"])
            if clicked_lid != st.session_state.get("lbl_selected_lid"):
                st.session_state["lbl_selected_lid"] = clicked_lid
                st.rerun()

    with col_lbl:
        st.markdown("**Assign label**")

        lid_options = ["(none)"] + [str(int(x)) for x in legs["leg_id"].tolist()]
        current_sel = str(selected_lid) if selected_lid is not None else "(none)"
        if current_sel not in lid_options:
            current_sel = "(none)"

        # Manual leg ID picker
        sel_str = st.selectbox(
            "Leg ID",
            options=lid_options,
            index=lid_options.index(current_sel),
            key="lbl_leg_picker",
        )
        if sel_str != "(none)":
            st.session_state["lbl_selected_lid"] = int(sel_str)
            selected_lid = int(sel_str)

        if selected_lid is not None:
            sel_leg = legs[legs["leg_id"] == selected_lid]
            if not sel_leg.empty:
                sl = sel_leg.iloc[0]
                st.caption(
                    f"Leg {selected_lid} | {_DIR_LABEL.get(int(sl['direction']), '?')} | "
                    f"{int(sl['length_bars'])} bars | {int(sl['length_ticks'])} ticks | "
                    f"{sl['phase']}"
                )

            current_state = gt_map.get(selected_lid, "UNLABELED")
            new_state = st.selectbox(
                "Leg state",
                options=lls.LEG_STATES,
                index=lls.LEG_STATES.index(current_state),
                key="lbl_state_picker",
            )

            notes = st.text_area(
                "Notes (optional)",
                value=gt_labels.loc[gt_labels["leg_id"] == selected_lid, "notes"].values[0]
                      if selected_lid in gt_labels["leg_id"].values else "",
                height=60,
                key="lbl_notes",
            )

            labeler = st.text_input("Labeler tag", value="manual", key="lbl_labeler_tag")

            if st.button("Save label", type="primary", key="lbl_save_btn"):
                if not sel_leg.empty:
                    sl = sel_leg.iloc[0]
                    lls.upsert_ground_truth(
                        rows=[{
                            "leg_id":    selected_lid,
                            "start_dt":  sl["start_dt"],
                            "end_dt":    sl["end_dt"],
                            "direction": int(sl["direction"]),
                            "leg_state": new_state,
                            "notes":     notes,
                            "labeler":   labeler,
                        }],
                        session=f"lbl_{d_start}_{d_end}",
                    )
                    st.success(f"Leg {selected_lid} → {new_state}")
                    st.rerun()

        st.divider()

        # ── Bulk draft import ──────────────────────────────────────────────────
        with st.expander("Bulk: import draft labels for all legs in view"):
            st.caption(
                "Creates UNLABELED placeholder rows for all detected legs. "
                "Existing labels are NOT overwritten."
            )
            if st.button("Import drafts", key="lbl_draft_import"):
                draft = lls.draft_from_decomp(legs)
                # Only import legs not already labeled
                already = set(gt_labels["leg_id"].astype(int).tolist()) if not gt_labels.empty else set()
                to_import = draft[~draft["leg_id"].isin(already)]
                if to_import.empty:
                    st.info("All legs already have label rows.")
                else:
                    lls.upsert_ground_truth(
                        rows=to_import.to_dict(orient="records"),
                        session=f"draft_{d_start}_{d_end}",
                    )
                    st.success(f"Imported {len(to_import)} draft rows.")
                    st.rerun()

        # ── Edge summary ───────────────────────────────────────────────────────
        with st.expander("GT vs Live call edge"):
            edge = lls.compute_edge()
            if edge.empty:
                st.info("No live calls logged yet.")
            else:
                total   = len(edge)
                correct = int(edge["correct"].sum())
                st.metric("Accuracy", f"{correct/total:.1%}", f"{correct}/{total} legs")
                st.dataframe(edge.head(50), use_container_width=True, hide_index=True)

        # ── Label distribution ─────────────────────────────────────────────────
        if not gt_labels.empty:
            with st.expander("Label distribution (all GT labels)"):
                dist = gt_labels["leg_state"].value_counts().reset_index()
                dist.columns = ["State", "Count"]
                st.dataframe(dist, use_container_width=True, hide_index=True)
