"""
WFA tab — Walk-Forward Analysis engine + Streamlit UI.

Architecture:
  IS window: 1 year (default, configurable)
  OOS window: 3 months (default, configurable)
  Step: OOS window length (rolling, not anchored)
  Optimizer: grid search over T1×T2×PB1 (2-leg) or T1 (single-leg)
  Objective: PROM (primary), PnL/DD and PF displayed alongside
  Guardrails: Kaufman (≥70% profitable, kurtosis ≤6, ≥30 trades, IR≤3.0)
              Pardo (no OOS reuse, forward risk = 2× IS risk)
"""

import itertools
import json
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from scipy import stats as scipy_stats

from simulation_engine import simulate_trades, compute_summary, INSTRUMENTS
from results_store import (
    create_run, save_fold, load_folds, load_all_oos_trades,
    load_fold_trades, guardrail_report, delete_run, list_runs, lock_oos,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_TRADING_DAYS_PER_YEAR = 252
_TRADING_DAYS_PER_QTR  = 63

# Multiplicative R steps (Kaufman rule — not linear)
_T_VALS  = [0.50, 0.625, 0.75, 1.00, 1.25, 1.50, 2.00]   # T1 or T2
_PB_VALS = [-0.25, -0.375, -0.50, -0.625, -0.75, -1.00]   # PB (negative R)


# ── Fold date slicer ──────────────────────────────────────────────────────────

def build_folds(
    all_dates: list,       # sorted list of unique trading dates in the dataset
    is_days: int = _TRADING_DAYS_PER_YEAR,
    oos_days: int = _TRADING_DAYS_PER_QTR,
) -> list[dict]:
    """Return list of {fold_id, is_dates, oos_dates} dicts.
    Step = oos_days (rolling window, not anchored)."""
    folds = []
    n     = len(all_dates)
    start = 0
    fold_id = 0

    while True:
        is_end   = start + is_days
        oos_end  = is_end + oos_days
        if oos_end > n:
            break
        folds.append({
            "fold_id":   fold_id,
            "is_dates":  all_dates[start:is_end],
            "oos_dates": all_dates[is_end:oos_end],
        })
        start   += oos_days
        fold_id += 1

    return folds


# ── IS grid sweep ─────────────────────────────────────────────────────────────

def _build_param_grid(
    mode: str,
    pin_t1: float | None = None,
    pin_t2: float | None = None,
    pin_pb: float | None = None,
) -> list[dict]:
    """Return all valid parameter combinations for the IS sweep.
    Pass a float to pin that parameter to a fixed value; None = sweep full range."""
    t1_vals = [pin_t1] if pin_t1 is not None else _T_VALS
    t2_vals = [pin_t2] if pin_t2 is not None else _T_VALS
    pb_vals = [pin_pb] if pin_pb is not None else _PB_VALS

    combos = []
    if mode == "singleleg":
        for t1 in t1_vals:
            combos.append({"target_r": t1})
    elif mode == "multileg":
        for t1, t2, pb in itertools.product(t1_vals, t2_vals, pb_vals):
            if t1 >= t2:
                continue  # T1 must be < T2
            combos.append({"t1_r": t1, "target_r": t2, "ml_pb_r": pb})
    elif mode == "3leg":
        for t1, t2, pb1 in itertools.product(t1_vals, t2_vals, pb_vals):
            if t1 >= t2:
                continue
            combos.append({"t1_r": t1, "t2_r": t1, "target_r": t2, "pb1_r": abs(pb1)})
    return combos


def run_is_sweep(
    signals_is: pd.DataFrame,
    ticks_by_date: dict,
    bars_by_date: dict,
    base_params: dict,        # fixed: entry_slip, exit_slip, stop_offset, tick_value, contracts, commission, etc.
    mode: str,
    pin_t1: float | None = None,
    pin_t2: float | None = None,
    pin_pb: float | None = None,
) -> pd.DataFrame:
    """Run all parameter combinations on IS data. Returns DataFrame with one row per combo."""
    grid   = _build_param_grid(mode, pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb)
    rows   = []

    multileg  = (mode == "multileg")
    threeleg  = (mode == "3leg")

    for combo in grid:
        call_params = {**base_params, **combo}
        call_params["multileg"]  = multileg
        call_params["threeleg"]  = threeleg
        call_params["overrides"] = None

        results = simulate_trades(
            signals   = signals_is,
            ticks_by_date = ticks_by_date,
            bars_by_date  = bars_by_date,
            **call_params,
        )
        if results.empty:
            continue

        summary = compute_summary(
            results,
            commission   = base_params["commission"],
            contracts    = base_params.get("contracts", 1),
            is_multileg  = multileg,
            contracts_t1 = base_params.get("contracts_t1", 1),
            contracts_t2 = base_params.get("contracts_t2", 1),
        )
        if not summary or summary.get("n_trades", 0) < 1:
            continue

        row = {**combo, **summary}
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ── Robustness checks (Kaufman) ───────────────────────────────────────────────

def compute_robustness(sweep_df: pd.DataFrame) -> tuple[float, float]:
    """Return (pct_profitable, kurtosis) for the IS sweep surface.
    pct_profitable: % of combos where net_total > 0.
    kurtosis: scipy excess kurtosis of the PROM distribution."""
    if sweep_df.empty:
        return 0.0, float("nan")

    pct = float((sweep_df["net_total"] > 0).mean() * 100)

    prom_vals = sweep_df["prom"].dropna().values
    kurt = float(scipy_stats.kurtosis(prom_vals, fisher=True)) if len(prom_vals) >= 4 else float("nan")

    return pct, kurt


def select_params(sweep_df: pd.DataFrame, n: int = 3) -> list[dict]:
    """Select the top-N param sets by PROM (IS objective function).
    Per Kaufman: trade the average of ≥3 sets, not the single best."""
    if sweep_df.empty:
        return []

    param_cols = [c for c in sweep_df.columns
                  if c in {"target_r", "t1_r", "t2_r", "ml_pb_r", "pb1_r"}]
    top = sweep_df.nlargest(n, "prom")[param_cols]
    return top.to_dict("records")


def average_params(param_sets: list[dict]) -> dict:
    """Average the parameter values across the chosen sets (Kaufman: trade the average)."""
    if not param_sets:
        return {}
    keys = param_sets[0].keys()
    return {k: float(np.mean([p[k] for p in param_sets])) for k in keys}


# ── WFA fold runner ───────────────────────────────────────────────────────────

def run_wfa(
    run_id: str,
    setup_id: str,
    signals: pd.DataFrame,
    ticks_by_date: dict,
    bars_by_date: dict,
    base_params: dict,
    mode: str,
    is_days: int = _TRADING_DAYS_PER_YEAR,
    oos_days: int = _TRADING_DAYS_PER_QTR,
    n_param_sets: int = 3,
    progress_cb=None,         # optional callable(fold_id, total_folds, msg)
    pin_t1: float | None = None,
    pin_t2: float | None = None,
    pin_pb: float | None = None,
) -> list[dict]:
    """Run the full WFA. Returns list of fold result dicts (also persisted to store)."""
    all_dates = sorted(signals["Date"].unique())
    folds     = build_folds(all_dates, is_days, oos_days)

    if not folds:
        return []

    fold_results = []

    for i, fold in enumerate(folds):
        fold_id   = fold["fold_id"]
        is_dates  = set(fold["is_dates"])
        oos_dates = set(fold["oos_dates"])

        if progress_cb:
            progress_cb(i, len(folds), f"Fold {fold_id+1}/{len(folds)} — IS sweep")

        signals_is  = signals[signals["Date"].isin(is_dates)].copy()
        signals_oos = signals[signals["Date"].isin(oos_dates)].copy()

        if signals_is.empty or signals_oos.empty:
            continue

        # ── IS sweep ──────────────────────────────────────────────────────────
        sweep_df = run_is_sweep(signals_is, ticks_by_date, bars_by_date, base_params, mode,
                                pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb)

        if sweep_df.empty:
            continue

        rob_pct, kurtosis = compute_robustness(sweep_df)
        param_sets        = select_params(sweep_df, n_param_sets)

        if not param_sets:
            continue

        avg_params = average_params(param_sets)

        # ── IS summary with averaged params ───────────────────────────────────
        is_call = {**base_params, **avg_params,
                   "multileg": mode == "multileg",
                   "threeleg": mode == "3leg",
                   "overrides": None}
        is_results = simulate_trades(
            signals=signals_is,
            ticks_by_date=ticks_by_date,
            bars_by_date=bars_by_date,
            **is_call,
        )
        is_summary = compute_summary(
            is_results, base_params["commission"],
            contracts    = base_params.get("contracts", 1),
            is_multileg  = (mode == "multileg"),
            contracts_t1 = base_params.get("contracts_t1", 1),
            contracts_t2 = base_params.get("contracts_t2", 1),
        )

        # ── OOS run (parameters locked from IS) ───────────────────────────────
        if progress_cb:
            progress_cb(i, len(folds), f"Fold {fold_id+1}/{len(folds)} — OOS")

        oos_call = {**base_params, **avg_params,
                    "multileg": mode == "multileg",
                    "threeleg": mode == "3leg",
                    "overrides": None}
        oos_results = simulate_trades(
            signals=signals_oos,
            ticks_by_date=ticks_by_date,
            bars_by_date=bars_by_date,
            **oos_call,
        )
        oos_summary = compute_summary(
            oos_results, base_params["commission"],
            contracts    = base_params.get("contracts", 1),
            is_multileg  = (mode == "multileg"),
            contracts_t1 = base_params.get("contracts_t1", 1),
            contracts_t2 = base_params.get("contracts_t2", 1),
        )

        # ── WFE ───────────────────────────────────────────────────────────────
        is_ann  = (is_summary.get("net_total",  0) / len(is_dates)  * _TRADING_DAYS_PER_YEAR
                   if len(is_dates)  > 0 else 0)
        oos_ann = (oos_summary.get("net_total", 0) / len(oos_dates) * _TRADING_DAYS_PER_YEAR
                   if len(oos_dates) > 0 else 0)
        wfe = oos_ann / is_ann if is_ann != 0 else float("nan")

        # ── Persist ───────────────────────────────────────────────────────────
        is_start  = min(fold["is_dates"])
        is_end    = max(fold["is_dates"])
        oos_start = min(fold["oos_dates"])
        oos_end   = max(fold["oos_dates"])

        save_fold(
            run_id, setup_id, fold_id,
            is_start, is_end, oos_start, oos_end,
            param_sets, is_summary, oos_summary,
            is_results, oos_results,
            rob_pct, kurtosis, wfe,
        )
        lock_oos(run_id, setup_id, fold_id)

        fold_results.append({
            "fold_id":    fold_id,
            "is_start":   is_start, "is_end":   is_end,
            "oos_start":  oos_start, "oos_end":  oos_end,
            "params":     param_sets,
            "avg_params": avg_params,
            "is_summary": is_summary,
            "oos_summary": oos_summary,
            "wfe":        wfe,
            "rob_pct":    rob_pct,
            "kurtosis":   kurtosis,
        })

    return fold_results


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def _fmt(v, fmt=".0f", fallback="—"):
    try:
        return f"{v:{fmt}}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else fallback
    except Exception:
        return fallback


def _equity_chart(oos_trades: pd.DataFrame, title: str = "Combined OOS Equity Curve") -> go.Figure:
    if oos_trades.empty or "NetPnL" not in oos_trades.columns:
        return go.Figure()

    df = oos_trades[oos_trades["Filled"] == True].copy()
    df = df.sort_values(["Date", "EntryTime"])
    df["Equity"] = df["NetPnL"].cumsum()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Date"].astype(str), y=df["Equity"],
        mode="lines", name="OOS Equity",
        line=dict(color="#00d4aa", width=2),
    ))
    fig.update_layout(
        title=title, height=360,
        margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#e0e0e0"),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
    )
    return fig


def _fold_table(folds_df: pd.DataFrame) -> None:
    if folds_df.empty:
        st.info("No fold results found.")
        return

    display = folds_df[[
        "fold_id", "is_start", "is_end", "oos_start", "oos_end",
        "is_n_trades", "is_net_pnl", "is_prom", "is_pnl_dd",
        "oos_n_trades", "oos_net_pnl", "oos_prom", "oos_pnl_dd",
        "wfe", "is_rob_pct", "rob_passed", "kurtosis_ok",
    ]].copy()

    display["wfe_pct"]    = (display["wfe"]    * 100).round(1)
    display["is_net_pnl"] = display["is_net_pnl"].round(0)
    display["oos_net_pnl"] = display["oos_net_pnl"].round(0)
    display["is_prom"]    = display["is_prom"].round(3)
    display["oos_prom"]   = display["oos_prom"].round(3)

    def _color_wfe(val):
        if pd.isna(val): return ""
        if val >= 50:  return "background-color: #1a3a1a"
        if val >= 25:  return "background-color: #3a3a1a"
        return "background-color: #3a1a1a"

    st.dataframe(
        display.style.applymap(_color_wfe, subset=["wfe_pct"]),
        use_container_width=True, hide_index=True,
    )


def _guardrail_badges(report: dict) -> None:
    n = report.get("total_folds", 0)
    if not n:
        return

    cols = st.columns(6)
    metrics = [
        ("Rob ≥70%",    f"{report['rob_passed']}/{n}",        report['rob_passed'] == n),
        ("Kurt ≤6",     f"{report['kurtosis_ok']}/{n}",       report['kurtosis_ok'] == n),
        ("Min trades",  f"{report['min_trades_ok']}/{n}",     report['min_trades_ok'] == n),
        ("OOS profit%", f"{report['pct_oos_profitable']}%",   report['pct_oos_profitable'] >= 60),
        ("Mean WFE",    f"{report['mean_wfe']}%",             report['mean_wfe'] >= 50),
        ("PROM decay",  f"{report.get('mean_prom_decay','—')}", True),
    ]
    for col, (label, val, ok) in zip(cols, metrics):
        color = "#00d4aa" if ok else "#ff6b6b"
        col.markdown(
            f"<div style='text-align:center;padding:8px;border:1px solid {color};"
            f"border-radius:6px'><div style='color:{color};font-size:18px;font-weight:bold'>"
            f"{val}</div><div style='color:#aaa;font-size:12px'>{label}</div></div>",
            unsafe_allow_html=True,
        )


def show_wfa_tab() -> None:
    st.header("🔄 Walk-Forward Analysis")

    mas_cont    = st.session_state.get("mas_continuous")
    _ba_sig     = st.session_state.get("ba_signals")
    _rev_sig    = st.session_state.get("rev_signals")
    signals_raw = (_ba_sig  if _ba_sig  is not None and not (hasattr(_ba_sig,  "empty") and _ba_sig.empty)
                   else _rev_sig if _rev_sig is not None and not (hasattr(_rev_sig, "empty") and _rev_sig.empty)
                   else None)

    # ── Data availability check ───────────────────────────────────────────────
    if mas_cont is None or mas_cont.empty:
        st.warning("Build the continuous series in the 📂 Massive tab first.")
        return

    if signals_raw is None:
        st.info("Upload a signals file (MC Signals or RevFT Signals) in the 📈 Bar Analysis tab first.")
        return

    bars = mas_cont.drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: grp.reset_index(drop=True)
                    for d, grp in bars.groupby(bars["DateTime"].dt.date)}

    # ── Tabs: Configure / Results ─────────────────────────────────────────────
    tab_cfg, tab_res = st.tabs(["⚙️ Configure & Run", "📊 Results"])

    # ═══════════════════════════════════════════════════════════════════════════
    with tab_cfg:
        st.subheader("Setup")
        c1, c2, c3 = st.columns(3)
        setup_id   = c1.text_input("Setup ID", value="CC2", key="wfa_setup_id")
        instrument = c2.selectbox("Instrument", list(INSTRUMENTS.keys()), key="wfa_instrument")
        mode       = c3.selectbox("Trade Mode", ["multileg", "singleleg", "3leg"], key="wfa_mode")

        tick_value  = INSTRUMENTS[instrument]["tick_value"]
        def_comm    = INSTRUMENTS[instrument]["default_commission"]

        st.subheader("Window Parameters")
        wc1, wc2, wc3 = st.columns(3)
        is_months  = wc1.number_input("IS window (months)", min_value=3, max_value=24, value=12, step=3, key="wfa_is_mo")
        oos_months = wc2.number_input("OOS window (months)", min_value=1, max_value=6,  value=3,  step=1, key="wfa_oos_mo")
        n_sets     = wc3.number_input("Param sets (Kaufman avg)", min_value=1, max_value=10, value=3, key="wfa_n_sets")

        is_days  = int(is_months  * _TRADING_DAYS_PER_YEAR / 12)
        oos_days = int(oos_months * _TRADING_DAYS_PER_YEAR / 12)

        all_dates  = sorted(signals_raw["Date"].unique())
        folds_preview = build_folds(all_dates, is_days, oos_days)
        st.caption(
            f"Dataset: {len(all_dates)} trading days "
            f"({all_dates[0]} → {all_dates[-1]})  |  "
            f"**{len(folds_preview)} folds** with IS={is_days}d / OOS={oos_days}d"
        )

        if len(folds_preview) < 10:
            st.warning(f"Only {len(folds_preview)} folds. Pardo minimum is 10. "
                       "Consider a shorter IS or OOS window.")

        st.subheader("Execution Parameters")
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        entry_slip  = ec1.number_input("Entry slip (ticks)", 0.0, 5.0, 1.0, 0.5, key="wfa_eslip")
        exit_slip   = ec2.number_input("Exit slip (ticks)",  0.0, 5.0, 1.0, 0.5, key="wfa_xslip")
        stop_offset = ec3.number_input("Stop offset (ticks)",0, 5, 1, key="wfa_soff")
        contracts_t1= ec4.number_input("Contracts E1",       1, 10, 1, key="wfa_ct1")
        contracts_t2= ec5.number_input("Contracts E2",       0, 10, 1, key="wfa_ct2")
        commission  = st.number_input("Commission ($/contract/side)", 0.0, 10.0, float(def_comm), 0.5, key="wfa_comm")

        base_params = dict(
            entry_slip   = entry_slip,
            exit_slip    = exit_slip,
            stop_offset  = int(stop_offset),
            tick_value   = tick_value,
            contracts    = contracts_t1,
            contracts_t1 = contracts_t1,
            contracts_t2 = contracts_t2,
            commission   = commission,
            ratchet_r    = 0.0,   # sweeps always run without ratchet (Kaufman)
        )

        # ── Target / Pullback pin controls ────────────────────────────────────
        st.subheader("Target & Pullback Parameters")
        st.caption(
            "Leave 'Pin?' unchecked to sweep the full grid. "
            "Check to fix a value and reduce the search space."
        )
        tp1, tp2, tp3 = st.columns(3)
        _T_OPTS = [0.50, 0.625, 0.75, 1.00, 1.25, 1.50, 2.00]
        _PB_OPTS = [-0.25, -0.375, -0.50, -0.625, -0.75, -1.00]

        pin_t1_chk = tp1.checkbox("Pin T1?", value=False, key="wfa_pin_t1_chk")
        pin_t1 = (
            tp1.selectbox("T1 value (R)", _T_OPTS, index=3, key="wfa_pin_t1_val")
            if pin_t1_chk else None
        )

        pin_t2_chk = tp2.checkbox("Pin T2?", value=False, key="wfa_pin_t2_chk")
        pin_t2 = (
            tp2.selectbox("T2 value (R)", _T_OPTS, index=3, key="wfa_pin_t2_val")
            if pin_t2_chk else None
        )

        pin_pb_chk = tp3.checkbox("Pin PB?", value=False, key="wfa_pin_pb_chk")
        pin_pb = (
            tp3.selectbox("PB value (R)", _PB_OPTS, index=2, key="wfa_pin_pb_val")
            if pin_pb_chk else None
        )

        _pinned = sum(v is not None for v in (pin_t1, pin_t2, pin_pb))
        _combos = len(_T_OPTS) ** (2 - sum(v is not None for v in (pin_t1, pin_t2))) * len(_PB_OPTS) ** (1 - pin_pb_chk)
        st.caption(
            f"Grid size (multileg): **{_combos} combos** per IS fold  "
            f"({'full sweep' if _pinned == 0 else f'{_pinned} param(s) pinned'})"
        )

        # Signal CC filter
        cc_col = None
        for col in ["CCCount", "CC", "SetupCC", "cc_count"]:
            if col in signals_raw.columns:
                cc_col = col
                break

        if cc_col:
            cc_vals = sorted(signals_raw[cc_col].dropna().unique())
            sel_cc  = st.multiselect(f"Filter by {cc_col}", cc_vals, default=cc_vals, key="wfa_cc_filter")
            signals_filtered = signals_raw[signals_raw[cc_col].isin(sel_cc)].copy() if sel_cc else signals_raw.copy()
        else:
            signals_filtered = signals_raw.copy()

        st.caption(f"{len(signals_filtered)} signals after filter")

        # ── Run button ────────────────────────────────────────────────────────
        st.divider()
        run_id_input = st.text_input("Run ID (leave blank to auto-generate)", value="", key="wfa_run_id_input")
        notes_input  = st.text_input("Notes (optional)", value="", key="wfa_notes")

        run_btn = st.button("▶ Run WFA", type="primary", key="wfa_run_btn")

        if run_btn:
            run_id = run_id_input.strip() or f"run_{uuid.uuid4().hex[:8]}"
            create_run(run_id, setup_id, mode, base_params, notes_input)

            progress_bar = st.progress(0.0)
            status_text  = st.empty()

            # Load tick cache now (only on run, not on every render)
            import massive as _massive_mod
            sig_dates  = sorted(signals_filtered["Date"].unique())
            _ticks_key = f"wfa_ticks__{hash(tuple(sig_dates))}"
            if _ticks_key not in st.session_state:
                status_text.text("Loading tick cache…")
                tbd = {}
                for d in sig_dates:
                    dt = _massive_mod.load_continuous_ticks(d)
                    if not dt.empty:
                        tbd[d] = dt
                st.session_state[_ticks_key] = tbd
            ticks_by_date = st.session_state[_ticks_key]

            def _cb(i, total, msg):
                progress_bar.progress((i + 0.5) / total)
                status_text.text(msg)

            with st.spinner("Running WFA…"):
                fold_results = run_wfa(
                    run_id, setup_id,
                    signals_filtered, ticks_by_date, bars_by_date,
                    base_params, mode,
                    is_days=is_days, oos_days=oos_days,
                    n_param_sets=int(n_sets),
                    progress_cb=_cb,
                    pin_t1=pin_t1,
                    pin_t2=pin_t2,
                    pin_pb=pin_pb,
                )

            progress_bar.progress(1.0)
            status_text.text(f"Done — {len(fold_results)} folds completed.")
            st.session_state["wfa_last_run_id"]    = run_id
            st.session_state["wfa_last_setup_id"]  = setup_id
            st.success(f"Run **{run_id}** complete — {len(fold_results)} folds. View results in the 📊 Results tab.")

    # ═══════════════════════════════════════════════════════════════════════════
    with tab_res:
        st.subheader("Results")

        # ── Run selector ──────────────────────────────────────────────────────
        all_runs = list_runs()
        if all_runs.empty:
            st.info("No runs found. Run a WFA in the ⚙️ Configure & Run tab.")
            return

        run_labels = [
            f"{r['run_id']}  [{r['setup_id']} / {r['mode']}]  {r['created_at'][:16]}"
            for _, r in all_runs.iterrows()
        ]
        default_idx = 0
        last_id = st.session_state.get("wfa_last_run_id")
        if last_id:
            for i, r in enumerate(all_runs.itertuples()):
                if r.run_id == last_id:
                    default_idx = i
                    break

        sel_label  = st.selectbox("Select run", run_labels, index=default_idx, key="wfa_sel_run")
        sel_run_id = all_runs.iloc[run_labels.index(sel_label)]["run_id"]
        sel_setup  = all_runs.iloc[run_labels.index(sel_label)]["setup_id"]

        folds_df = load_folds(sel_run_id, sel_setup)

        if folds_df.empty:
            st.info("No fold data for this run.")
            return

        # ── Guardrail summary ─────────────────────────────────────────────────
        with st.expander("🔒 Kaufman / Pardo Guardrails", expanded=True):
            report = guardrail_report(folds_df)
            _guardrail_badges(report)

            forward_risk_warning = """
            ⚠️ **Pardo forward risk rule:** Expected live risk = **2× IS max drawdown**.
            IS results are NOT your live expectation.
            """
            st.warning(forward_risk_warning)

        # ── OOS equity curve ──────────────────────────────────────────────────
        with st.expander("📈 Combined OOS Equity Curve", expanded=True):
            oos_trades = load_all_oos_trades(sel_run_id, sel_setup)
            if not oos_trades.empty:
                fig = _equity_chart(oos_trades, f"OOS Equity — {sel_setup} / {sel_run_id}")
                st.plotly_chart(fig, use_container_width=True)

                filled_oos = oos_trades[oos_trades["Filled"] == True]
                if not filled_oos.empty:
                    eq  = filled_oos.sort_values(["Date", "EntryTime"])["NetPnL"].cumsum()
                    pk  = eq.cummax()
                    dd  = float((eq - pk).min())
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    mc1.metric("OOS Net PnL",   f"${filled_oos['NetPnL'].sum():,.0f}")
                    mc2.metric("OOS Trades",    len(filled_oos))
                    mc3.metric("OOS Win%",       f"{(filled_oos['NetPnL']>0).mean()*100:.1f}%")
                    mc4.metric("OOS Max DD",    f"${dd:,.0f}")
            else:
                st.info("No OOS trade data found.")

        # ── Fold summary table ────────────────────────────────────────────────
        with st.expander("📋 Fold Summary Table", expanded=True):
            _fold_table(folds_df)

        # ── Per-fold drill-down ───────────────────────────────────────────────
        with st.expander("🔍 Per-Fold Drill-Down"):
            fold_ids = folds_df["fold_id"].tolist()
            sel_fold = st.selectbox("Select fold", fold_ids, key="wfa_sel_fold")

            fold_row = folds_df[folds_df["fold_id"] == sel_fold].iloc[0]
            dc1, dc2 = st.columns(2)

            with dc1:
                st.markdown("**IS Period**")
                st.caption(f"{fold_row['is_start']} → {fold_row['is_end']}")
                is_metrics = {
                    "Trades": fold_row["is_n_trades"],
                    "Net PnL": f"${fold_row['is_net_pnl']:,.0f}",
                    "Win%": f"{fold_row['is_win_pct']:.1f}%",
                    "PF": f"{fold_row['is_pf']:.2f}",
                    "PROM": f"{fold_row['is_prom']:.3f}",
                    "PnL/DD": f"{fold_row['is_pnl_dd']:.2f}",
                    "Max DD": f"${fold_row['is_max_dd']:,.0f}",
                    "Robustness": f"{fold_row['is_rob_pct']:.1f}%",
                    "Kurtosis": f"{fold_row['is_kurtosis']:.2f}",
                }
                for k, v in is_metrics.items():
                    st.text(f"  {k:<14} {v}")

            with dc2:
                st.markdown("**OOS Period**")
                st.caption(f"{fold_row['oos_start']} → {fold_row['oos_end']}")
                oos_metrics = {
                    "Trades": fold_row["oos_n_trades"],
                    "Net PnL": f"${fold_row['oos_net_pnl']:,.0f}",
                    "Win%": f"{fold_row['oos_win_pct']:.1f}%",
                    "PF": f"{fold_row['oos_pf']:.2f}",
                    "PROM": f"{fold_row['oos_prom']:.3f}",
                    "PnL/DD": f"{fold_row['oos_pnl_dd']:.2f}",
                    "Max DD": f"${fold_row['oos_max_dd']:,.0f}",
                    "WFE": f"{fold_row['wfe']*100:.1f}%",
                }
                for k, v in oos_metrics.items():
                    st.text(f"  {k:<14} {v}")

            params_chosen = fold_row.get("params_chosen", [])
            if params_chosen:
                st.markdown("**Chosen parameter sets (IS)**")
                st.dataframe(pd.DataFrame(params_chosen), use_container_width=True, hide_index=True)

            is_tr  = load_fold_trades(sel_run_id, sel_setup, sel_fold, "is")
            oos_tr = load_fold_trades(sel_run_id, sel_setup, sel_fold, "oos")

            if not is_tr.empty:
                with st.expander(f"IS trades ({len(is_tr[is_tr.get('Filled', False) == True] if 'Filled' in is_tr.columns else is_tr)} filled)"):
                    st.dataframe(is_tr, use_container_width=True, hide_index=True)
            if not oos_tr.empty:
                with st.expander(f"OOS trades ({len(oos_tr[oos_tr.get('Filled', False) == True] if 'Filled' in oos_tr.columns else oos_tr)} filled)"):
                    st.dataframe(oos_tr, use_container_width=True, hide_index=True)

        # ── Delete run ────────────────────────────────────────────────────────
        with st.expander("🗑️ Delete Run"):
            st.warning(f"This permanently deletes run **{sel_run_id}** and all its trade logs.")
            if st.button("Delete this run", key="wfa_delete_run"):
                delete_run(sel_run_id)
                st.session_state.pop("wfa_last_run_id", None)
                st.rerun()
