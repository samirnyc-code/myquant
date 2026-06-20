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

from simulation_engine import simulate_trades, compute_summary, friction_ledger, INSTRUMENTS
from results_store import (
    create_run, save_fold, load_folds, load_all_oos_trades,
    load_fold_trades, guardrail_report, delete_run, list_runs, lock_oos,
    save_sweep, load_sweep,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_TRADING_DAYS_PER_YEAR = 252
_TRADING_DAYS_PER_QTR  = 63

# Multiplicative R steps (Kaufman rule — not linear)
_T_VALS  = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]   # T1 or T2 — clean 0.25 steps
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
    persist: bool = True,     # False = in-memory only (used by the window-anchor grid)
) -> list[dict]:
    """Run the full WFA. Returns list of fold result dicts.
    persist=True also writes folds, trade logs, sweep grids to the store and locks OOS."""
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
        # WFE = OOS ÷ IS is only meaningful when the IS edge is positive — it measures
        # how much of a *profitable* in-sample carried out-of-sample. If IS PnL ≤ 0 the
        # fold's optimization never produced an edge, so WFE is undefined (NaN), not a
        # huge negative number from dividing by a ~0/negative denominator.
        wfe = oos_ann / is_ann if is_ann > 0 else float("nan")

        # ── Persist ───────────────────────────────────────────────────────────
        is_start  = min(fold["is_dates"])
        is_end    = max(fold["is_dates"])
        oos_start = min(fold["oos_dates"])
        oos_end   = max(fold["oos_dates"])

        if persist:
            save_fold(
                run_id, setup_id, fold_id,
                is_start, is_end, oos_start, oos_end,
                param_sets, is_summary, oos_summary,
                is_results, oos_results,
                rob_pct, kurtosis, wfe,
            )
            save_sweep(run_id, setup_id, fold_id, sweep_df)
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


# ── Window-anchor grid (meta-validation: is the IS/OOS choice itself overfit?) ─

def _aggregate_grid_cell(folds: list[dict]) -> dict:
    """Collapse a full WFA's fold results into one window-grid cell's summary."""
    if not folds:
        return {"n_folds": 0, "mean_wfe": float("nan"), "total_oos_pnl": float("nan"),
                "mean_oos_prom": float("nan"), "pct_oos_prof": float("nan"),
                "oos_pf_median": float("nan"), "oos_maxdd_worst": float("nan")}
    wfe  = [f["wfe"] for f in folds if f["wfe"] is not None and not np.isnan(f["wfe"])]
    opnl = [f["oos_summary"].get("net_total", 0.0) for f in folds]
    opr  = [f["oos_summary"].get("prom", float("nan")) for f in folds]
    opr  = [v for v in opr if v is not None and not np.isnan(v)]
    # PF / Max DD are per-fold aggregates (median PF, worst single-fold DD) — the
    # store has no pooled gross win/loss or concatenated equity in grid mode. The
    # true concatenated-equity PF/DD live in the single-run 📊 Results tab.
    opf  = [f["oos_summary"].get("pf", float("nan")) for f in folds]
    opf  = [v for v in opf if v is not None and not np.isnan(v) and not np.isinf(v)]
    odd  = [f["oos_summary"].get("max_dd", float("nan")) for f in folds]
    odd  = [v for v in odd if v is not None and not np.isnan(v)]
    return {
        "n_folds":       len(folds),
        # Median (not mean) so a couple of undefined/extreme folds can't dominate.
        "mean_wfe":      float(np.median(wfe)) * 100 if wfe else float("nan"),
        "total_oos_pnl": float(np.sum(opnl)),
        "mean_oos_prom": float(np.mean(opr)) if opr else float("nan"),
        "pct_oos_prof":  float(np.mean([p > 0 for p in opnl]) * 100) if opnl else float("nan"),
        "oos_pf_median":   float(np.median(opf)) if opf else float("nan"),
        "oos_maxdd_worst": float(np.min(odd))    if odd else float("nan"),  # most negative
    }


def run_window_grid(
    signals: pd.DataFrame, ticks_by_date: dict, bars_by_date: dict,
    base_params: dict, mode: str,
    is_months_list: list[int], oos_months_list: list[int],
    n_param_sets: int = 3,
    pin_t1: float | None = None, pin_t2: float | None = None, pin_pb: float | None = None,
    progress_cb=None,
) -> pd.DataFrame:
    """Run a full (non-persisted) WFA for each (IS months × OOS months) pair and
    aggregate one cell per pair. Proves the 12m/3m window choice isn't itself overfit."""
    rows  = []
    total = len(is_months_list) * len(oos_months_list)
    k     = 0
    for im in is_months_list:
        for om in oos_months_list:
            k += 1
            if progress_cb:
                progress_cb(k, total, f"IS {im}m / OOS {om}m")
            isd  = int(im * _TRADING_DAYS_PER_YEAR / 12)
            oosd = int(om * _TRADING_DAYS_PER_YEAR / 12)
            folds = run_wfa(
                "__grid__", "__grid__", signals, ticks_by_date, bars_by_date,
                base_params, mode, is_days=isd, oos_days=oosd,
                n_param_sets=n_param_sets, pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb,
                persist=False,
            )
            cell = _aggregate_grid_cell(folds)
            cell.update({"is_months": im, "oos_months": om})
            rows.append(cell)
    return pd.DataFrame(rows)


# ── Multi-structure robustness (Phase 3a) ──────────────────────────────────────
# Run a FULL walk-forward at several IS/OOS window structures so the same setup +
# locked params can be judged under each, in sequence. A system that only works
# under one window structure is fragile (Pardo / setup_decision_manual Phase 3a).
def run_window_structures(
    signals: pd.DataFrame, ticks_by_date: dict, bars_by_date: dict,
    base_params: dict, mode: str,
    structures: list[tuple[int, int]],          # [(is_months, oos_months), …]
    n_param_sets: int = 3,
    pin_t1: float | None = None, pin_t2: float | None = None, pin_pb: float | None = None,
    progress_cb=None,
) -> list[dict]:
    """For each (IS months, OOS months) structure, run a full non-persisted WFA and
    return its fold dicts + aggregate. Feeds the on-one-page Robustness Report."""
    out   = []
    total = max(len(structures), 1)
    for k, (im, om) in enumerate(structures):
        if progress_cb:
            progress_cb(k, total, f"IS {im}m / OOS {om}m")
        isd  = int(im * _TRADING_DAYS_PER_YEAR / 12)
        oosd = int(om * _TRADING_DAYS_PER_YEAR / 12)
        folds = run_wfa(
            "__struct__", "__struct__", signals, ticks_by_date, bars_by_date,
            base_params, mode, is_days=isd, oos_days=oosd,
            n_param_sets=n_param_sets, pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb,
            persist=False,
        )
        agg = _aggregate_grid_cell(folds)
        agg.update({"is_months": im, "oos_months": om})
        out.append({"is_months": im, "oos_months": om, "folds": folds, "agg": agg})
    if progress_cb:
        progress_cb(total, total, "done")
    return out


# ── Streamlit UI ──────────────────────────────────────────────────────────────

def _fmt(v, fmt=".0f", fallback="—"):
    try:
        return f"{v:{fmt}}" if v is not None and not (isinstance(v, float) and np.isnan(v)) else fallback
    except Exception:
        return fallback


def _max_underwater_days(dates: pd.Series, underwater: pd.Series) -> int:
    """Longest run of calendar days spent below the prior equity peak.
    `underwater` is a per-trade bool (equity < running peak); `dates` aligns to it."""
    d  = pd.to_datetime(pd.Series(dates).reset_index(drop=True))
    uw = pd.Series(underwater).reset_index(drop=True).astype(bool)
    best = 0
    run_start = None
    for i in range(len(uw)):
        if uw.iloc[i]:
            if run_start is None:
                run_start = d.iloc[i]
            best = max(best, int((d.iloc[i] - run_start).days))
        else:
            run_start = None
    return best


def _dark_layout(fig: go.Figure, title: str, height: int = 300) -> go.Figure:
    fig.update_layout(
        title=title, height=height, margin=dict(l=40, r=20, t=40, b=40),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#e0e0e0"),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#2a2a2a", zeroline=True, zerolinecolor="#555"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def _window_heatmap(grid_df: pd.DataFrame, value_col: str, label: str,
                    zfmt: str = ".1f") -> go.Figure:
    """One Window-Anchor heatmap: IS (rows) × OOS (cols), coloured by value_col, each
    cell labelled with the value and (fold count). Higher = greener for every metric
    we plot — Max DD is stored negative, so 'less negative' is already the max → green."""
    piv  = grid_df.pivot(index="is_months", columns="oos_months", values=value_col)
    nfld = grid_df.pivot(index="is_months", columns="oos_months", values="n_folds")
    fig = go.Figure(go.Heatmap(
        z=piv.values,
        x=[f"{c}m" for c in piv.columns], y=[f"{r}m" for r in piv.index],
        text=nfld.values, texttemplate="%{z:" + zfmt + "}<br>(%{text} folds)",
        colorscale="RdYlGn", colorbar=dict(title=label),
        hovertemplate="IS=%{y} · OOS=%{x}<br>" + label + "=%{z:" + zfmt +
                      "}<br>folds=%{text}<extra></extra>",
    ))
    _dark_layout(fig, f"Window-Anchor Map — {label}", 360)
    fig.update_xaxes(title="OOS window")
    fig.update_yaxes(title="IS window")
    return fig


def _is_surface_section(run_id: str, setup: str, fold_id: int, mode: str,
                        chosen: list[dict]) -> None:
    """Render the stored IS optimization surface for one fold so you can SEE whether
    the chosen params sit on a robust plateau or an isolated spike."""
    sweep = load_sweep(run_id, setup, fold_id)
    if sweep.empty:
        st.caption("No stored IS surface for this fold — re-run the WFA (older runs didn't "
                   "persist the optimization grid).")
        return

    metric_opts = {"PROM": "prom", "Net PnL": "net_total", "Profit Factor": "pf"}
    metric_opts = {k: v for k, v in metric_opts.items() if v in sweep.columns}
    mlabel = st.selectbox("Colour surface by", list(metric_opts), key=f"wfa_surf_metric_{fold_id}")
    mcol   = metric_opts[mlabel]

    # 1D case (singleleg): metric vs Target R
    if mode == "singleleg" or "ml_pb_r" not in sweep.columns or "t1_r" not in sweep.columns:
        s = sweep.sort_values("target_r")
        bar_c = ["#00d4aa" if v == s[mcol].max() else "#4a6fa5" for v in s[mcol]]
        fig = go.Figure(go.Bar(x=[f"{r:.3f}" for r in s["target_r"]], y=s[mcol],
                               marker_color=bar_c, text=s[mcol].round(2), textposition="outside"))
        _dark_layout(fig, f"IS {mlabel} vs Target R (best highlighted)", 320)
        fig.update_xaxes(title="Target R")
        st.plotly_chart(fig, use_container_width=True)
        pct = (sweep["net_total"] > 0).mean() * 100 if "net_total" in sweep else float("nan")
        st.caption(f"{len(sweep)} combos · {pct:.0f}% profitable. A broad cluster of similar bars = "
                   "robust; one spike towering over its neighbours = brittle/curve-fit.")
        return

    # 2D case (multileg/3leg): PB (Y) × T2 (X), sliced by T1
    t1_vals = sorted(sweep["t1_r"].dropna().unique())
    t1_sel  = (st.select_slider("T1 slice", options=[round(v, 3) for v in t1_vals],
                                value=round(t1_vals[0], 3), key=f"wfa_surf_t1_{fold_id}")
               if len(t1_vals) > 1 else t1_vals[0])
    sub = sweep[np.isclose(sweep["t1_r"], t1_sel)]
    if sub.empty:
        st.caption("No combos at this T1 slice.")
        return

    piv = sub.pivot_table(index="ml_pb_r", columns="target_r", values=mcol, aggfunc="mean")
    fig = go.Figure(go.Heatmap(
        z=piv.values,
        x=[f"{c:.3f}" for c in piv.columns], y=[f"{r:.3f}" for r in piv.index],
        colorscale="RdYlGn", colorbar=dict(title=mlabel),
        hovertemplate="T2=%{x}<br>PB=%{y}<br>" + mlabel + "=%{z:.2f}<extra></extra>",
    ))
    # Mark the chosen param sets that fall in this T1 slice
    cx, cy = [], []
    for p in chosen or []:
        if np.isclose(p.get("t1_r", np.nan), t1_sel):
            cx.append(f"{p.get('target_r', np.nan):.3f}")
            cy.append(f"{p.get('ml_pb_r', np.nan):.3f}")
    if cx:
        fig.add_trace(go.Scatter(x=cx, y=cy, mode="markers", name="chosen",
                                 marker=dict(symbol="x", size=14, color="#000000",
                                             line=dict(width=2, color="#ffffff"))))
    _dark_layout(fig, f"IS {mlabel} surface — PB × T2  (T1 = {t1_sel:.3f})", 400)
    fig.update_xaxes(title="T2 (Target R)")
    fig.update_yaxes(title="PB R")
    st.plotly_chart(fig, use_container_width=True)
    pct = (sweep["net_total"] > 0).mean() * 100 if "net_total" in sweep else float("nan")
    st.caption(f"{len(sweep)} combos across all T1 · {pct:.0f}% profitable. ✕ marks the chosen set(s) "
               "in this slice. A warm plateau around the ✕ = robust; an isolated hot cell = curve-fit risk.")


def _pain_index(equity: pd.Series) -> tuple[float, float]:
    """Pain Index — mean depth of drawdown across the equity path.
    Returns (dollars, pct_of_peak). Trade-step averaged (each filled trade = one step)."""
    if equity.empty:
        return 0.0, 0.0
    peak = equity.cummax()
    dd   = (equity - peak)               # ≤ 0
    pain_usd = float((-dd).mean())
    denom    = float(peak.replace(0, np.nan).abs().mean())
    pain_pct = (pain_usd / denom * 100) if denom and not np.isnan(denom) else 0.0
    return pain_usd, pain_pct


def _windsorized_mean_wfe(wfe: pd.Series) -> float:
    """Trimmed mean WFE: drop the single highest and lowest fold, average the rest.
    Reveals whether headline Mean WFE is outlier-driven (one windfall window)."""
    w = pd.Series(wfe).dropna().sort_values()
    if len(w) <= 2:
        return float(w.mean()) if len(w) else float("nan")
    return float(w.iloc[1:-1].mean())


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


def _flag(v) -> str:
    """NaN-safe boolean → ✓/✗/—. Robust to int64 1/0, bool, or NaN."""
    if pd.isna(v):
        return "—"
    return "✓" if bool(v) else "✗"


def _fold_table(folds_df: pd.DataFrame) -> None:
    if folds_df.empty:
        st.info("No fold results found.")
        return

    src = folds_df.copy()
    display = pd.DataFrame({
        "Fold":       src["fold_id"],
        "IS Start":   src["is_start"],
        "IS End":     src["is_end"],
        "OOS Start":  src["oos_start"],
        "OOS End":    src["oos_end"],
        "IS Trades":  src["is_n_trades"],
        "IS Net $":   src["is_net_pnl"].round(0),
        "IS PROM":    src["is_prom"].round(2),
        "IS PnL/DD":  src["is_pnl_dd"].round(2),
        "OOS Trades": src["oos_n_trades"],
        "OOS Net $":  src["oos_net_pnl"].round(0),
        "OOS PROM":   src["oos_prom"].round(2),
        "OOS PnL/DD": src["oos_pnl_dd"].round(2),
        "WFE %":      (src["wfe"] * 100).round(1),
        "IS Rob %":   src["is_rob_pct"].round(1),
        "Rob ✓":      src["rob_passed"].map(_flag),
        "Kurt ✓":     src["kurtosis_ok"].map(_flag),
    })

    def _color_wfe(val):
        if pd.isna(val): return ""
        if val >= 50:  return "background-color: #1a3a1a"
        if val >= 25:  return "background-color: #3a3a1a"
        return "background-color: #3a1a1a"

    st.dataframe(
        display.style.map(_color_wfe, subset=["WFE %"]),
        use_container_width=True, hide_index=True,
    )


def _guardrail_badges(report: dict) -> None:
    n = report.get("total_folds", 0)
    if not n:
        return

    cols = st.columns(6)
    _kn = report.get("kurtosis_n", n)
    _kurt_val = f"{report['kurtosis_ok']}/{_kn}" if _kn else "N/A"
    _kurt_ok  = (_kn == 0) or (report["kurtosis_ok"] == _kn)   # N/A is neutral, not red
    metrics = [
        ("Rob ≥70%",    f"{report['rob_passed']}/{n}",        report['rob_passed'] == n),
        ("Kurt ≤6",     _kurt_val,                            _kurt_ok),
        ("Min trades",  f"{report['min_trades_ok']}/{n}",     report['min_trades_ok'] == n),
        ("OOS profit%", f"{report['pct_oos_profitable']}%",   report['pct_oos_profitable'] >= 60),
        ("Median WFE",  f"{report['mean_wfe']}%",             report['mean_wfe'] >= 50),
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


# ── Metric tooltips (hover help) ──────────────────────────────────────────────

_METRIC_HELP = {
    "prom": "PROM — Pessimistic Return on Margin (Pardo). Net profit haircut by "
            "1/√N on wins and penalised by 1/√N on losses, divided by |max drawdown|. "
            "Rewards edges with many trades and shallow drawdowns; nan when DD=0.",
    "pnl_dd": "PnL / |Max Drawdown| — net profit per dollar of worst peak-to-trough loss. "
              "Higher is better; a pure return-to-risk ratio.",
    "pf": "Profit Factor — gross wins ÷ gross losses. >1 is profitable; "
          "1.3–1.5+ is generally considered robust intraday.",
    "win_pct": "Win rate — % of filled trades with NetPnL > 0.",
    "max_dd": "Max Drawdown — largest peak-to-trough drop in cumulative NetPnL over the window.",
    "wfe": "Walk-Forward Efficiency — annualised OOS return ÷ annualised IS return. "
           "~100% means OOS held up to IS; <50% flags decay; >>100% usually means a "
           "regime shift amplified the edge OOS (not necessarily good — check stability).",
    "rob_pct": "IS Robustness — % of parameter combos in the IS grid that were profitable. "
               "Kaufman wants ≥70%: a profitable plateau, not an isolated spike.",
    "kurtosis": "Kurtosis of the IS PROM surface (Fisher/excess). Kaufman wants ≤6: "
                "a low, flat surface means the chosen params aren't on a brittle cliff.",
    "n_trades": "Number of filled trades in the window. Kaufman floor is ≥30 IS trades "
                "for the optimisation to be statistically meaningful.",
    "is_window": "In-Sample window length (trading days). Parameters are optimised here.",
    "oos_window": "Out-of-Sample window length (trading days). Locked params are validated here; "
                  "never optimised. Step size = OOS length (rolling, non-anchored).",
    "n_sets": "Kaufman rule — trade the AVERAGE of the top-N IS param sets by PROM, "
              "never the single best, to avoid sitting on an overfit peak.",
}


def _guardrail_breakdown(folds_df: pd.DataFrame) -> None:
    """Per-fold pass/fail table for each guardrail — surfaces WHICH folds failed."""
    if folds_df.empty:
        return

    bd = pd.DataFrame({
        "Fold":        folds_df["fold_id"],
        "OOS Start":   folds_df["oos_start"],
        "Rob ≥70%":    folds_df["rob_passed"].map(_flag),
        "IS Rob %":    pd.to_numeric(folds_df["is_rob_pct"], errors="coerce").round(1),
        "Kurt ≤6":     folds_df["kurtosis_ok"].map(_flag),
        "Kurtosis":    pd.to_numeric(folds_df["is_kurtosis"], errors="coerce").round(2),
        "≥30 trades":  folds_df["min_trades_ok"].map(_flag),
        "IS Trades":   folds_df["is_n_trades"],
        "OOS Profit":  (folds_df["oos_net_pnl"] > 0).map(_flag),
        "OOS Net $":   pd.to_numeric(folds_df["oos_net_pnl"], errors="coerce").round(0),
        "WFE %":       (pd.to_numeric(folds_df["wfe"], errors="coerce") * 100).round(1),
    })

    def _mark(val):
        if val == "✓": return "color: #00d4aa"
        if val == "✗": return "color: #ff6b6b"
        return ""

    st.markdown("**Per-fold guardrail breakdown**")
    st.dataframe(
        bd.style.map(_mark, subset=["Rob ≥70%", "Kurt ≤6", "≥30 trades", "OOS Profit"]),
        use_container_width=True, hide_index=True,
    )

    # Roll-up of which folds failed each rail
    fails = []
    for label, col, good in [
        ("Robustness <70%", "rob_passed", True),
        ("IS trades <30",   "min_trades_ok", True),
    ]:
        failed = folds_df.loc[folds_df[col].astype(bool) != good, "fold_id"].tolist()
        if failed:
            fails.append(f"- **{label}:** fold(s) {', '.join(map(str, failed))}")
    # Kurtosis handled separately: only DEFINED folds (>6) are real failures; NaN = N/A.
    _kd = pd.to_numeric(folds_df["is_kurtosis"], errors="coerce")
    _kfail = folds_df.loc[_kd > 6.0, "fold_id"].tolist()
    if _kfail:
        fails.append(f"- **Kurtosis >6:** fold(s) {', '.join(map(str, _kfail))}")
    oos_neg = folds_df.loc[folds_df["oos_net_pnl"] <= 0, "fold_id"].tolist()
    if oos_neg:
        fails.append(f"- **OOS unprofitable:** fold(s) {', '.join(map(str, oos_neg))}")
    if fails:
        st.caption("Guardrail failures by fold:")
        st.markdown("\n".join(fails))
    else:
        st.caption("✓ All folds passed every guardrail.")

    _kna = folds_df.loc[_kd.isna(), "fold_id"].tolist()
    if _kna:
        st.caption(
            f"ℹ️ Kurtosis & robustness are **N/A** for fold(s) {', '.join(map(str, _kna))} — "
            "the IS sweep had too few combos (parameters pinned) to form a surface. "
            "These guardrails only apply when WFA is choosing among multiple parameter sets; "
            "unpin params to make them meaningful.")


# ── Robustness Report (one scrollable page: each window in sequence + verdict) ──
# Acceptance rails per window structure — Pardo / setup_decision_manual Phase 3a/3b.
# Fixed in advance; the report NEVER tunes them to the result.
_WIN_MIN_FOLDS   = 6      # too few folds = low confidence (Pardo prefers ≥10)
_WIN_MIN_WFE     = 50.0   # Median WFE ≥ 50%
_WIN_MIN_PROFPCT = 50.0   # ≥ 50% of OOS windows profitable


def _window_robustness_tests(cell: dict) -> list[tuple[str, bool]]:
    """The independent pass/fail robustness tests for one IS/OOS architecture (grid
    cell). Thresholds are fixed in advance (Pardo / handoff: WFE≥50%, ≥60% OOS green).
    Profit is ONE test among several — the score rewards surviving the most tests, not
    making the most money. Returns [(test_name, passed), …]."""
    n   = cell.get("n_folds", 0)
    pnl = cell.get("total_oos_pnl", float("nan"))
    wfe = cell.get("mean_wfe", float("nan"))       # already median × 100
    pp  = cell.get("pct_oos_prof", float("nan"))
    pf  = cell.get("oos_pf_median", float("nan"))
    pr  = cell.get("mean_oos_prom", float("nan"))
    dd  = cell.get("oos_maxdd_worst", float("nan"))
    _ok = lambda v, cond: bool(v is not None and not np.isnan(v) and cond)
    rr  = (pnl / abs(dd)) if (_ok(pnl, True) and _ok(dd, dd < 0)) else float("nan")
    return [
        ("≥8 folds",          n >= 8),
        ("OOS PnL > 0",       _ok(pnl, pnl > 0)),
        ("Median WFE ≥ 50%",  _ok(wfe, wfe >= 50)),
        ("≥60% OOS green",    _ok(pp,  pp >= 60)),
        ("Median PF ≥ 1.2",   _ok(pf,  pf >= 1.2)),
        ("Mean PROM > 0",     _ok(pr,  pr > 0)),
        ("Return ≥ Max DD",   _ok(rr,  rr >= 1.0)),
    ]


_WIN_N_TESTS = len(_window_robustness_tests({}))   # total tests (for "x/N" labels)


def _window_robustness_score(cell: dict) -> int:
    """How many robustness tests this IS/OOS architecture survives (0–_WIN_N_TESTS)."""
    return sum(1 for _, ok in _window_robustness_tests(cell) if ok)


def _window_pass(agg: dict) -> tuple[bool, list[str]]:
    """Does one window structure clear the acceptance rails? → (passed, reasons-failed)."""
    fails = []
    n   = agg.get("n_folds", 0)
    wfe = agg.get("mean_wfe", float("nan"))      # already median × 100
    pnl = agg.get("total_oos_pnl", float("nan"))
    pp  = agg.get("pct_oos_prof", float("nan"))
    if n < _WIN_MIN_FOLDS:
        fails.append(f"only {n} folds (<{_WIN_MIN_FOLDS})")
    if not (pnl > 0):
        fails.append("OOS PnL ≤ 0")
    if np.isnan(wfe) or wfe < _WIN_MIN_WFE:
        fails.append(f"Median WFE {_fmt(wfe, '.0f')}% (<{_WIN_MIN_WFE:.0f}%)")
    if np.isnan(pp) or pp < _WIN_MIN_PROFPCT:
        fails.append(f"{_fmt(pp, '.0f')}% OOS profitable (<{_WIN_MIN_PROFPCT:.0f}%)")
    return (len(fails) == 0, fails)


def _robustness_report(results: list[dict]) -> None:
    """One scrollable narrative: each window structure in sequence, then a combined,
    actionable ROBUST / FRAGILE / FAIL verdict. Answers 'does the edge survive
    different walk-forward structures?' — the Phase 3a robustness question."""
    if not results:
        st.info("No window structures to report.")
        return

    st.markdown("## 🧭 Robustness Report — does the edge survive different window structures?")
    st.caption(
        "Same setup, same locked parameters, validated under several IS/OOS walk-forward "
        "structures **in sequence**. Read top to bottom: each window below is one full "
        "walk-forward; the final verdict combines all of them. An edge that only holds under "
        "one structure is fragile (Pardo)."
    )

    passes = []
    for idx, res in enumerate(results, 1):
        agg   = res["agg"]
        folds = res["folds"]
        ok, fails = _window_pass(agg)
        passes.append(ok)

        st.divider()
        _tag = "✅ holds" if ok else "❌ does not hold"
        st.markdown(f"### Window {idx} — IS {res['is_months']}m / OOS {res['oos_months']}m  ·  {_tag}")

        if not folds:
            st.warning("This structure produced **0 folds** (window too long for the data span) — "
                       "the edge cannot be judged here. Shorten IS+OOS or widen the date range.")
            continue

        n   = agg["n_folds"]
        wfe = agg["mean_wfe"]; pnl = agg["total_oos_pnl"]; pp = agg["pct_oos_prof"]
        st.write(
            f"Rolled **{n}** walk-forward folds. In each, parameters were optimised in-sample and "
            f"locked, then traded on untouched out-of-sample data. Across those {n} OOS segments the "
            f"edge produced **${pnl:,.0f}** total, kept **{_fmt(wfe, '.0f')}%** of its in-sample "
            f"efficiency (median WFE), and was profitable in **{_fmt(pp, '.0f')}%** of windows."
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Folds", n)
        m2.metric("Total OOS PnL", f"${pnl:,.0f}")
        m3.metric("Median WFE", _fmt(wfe, ".0f") + "%")
        m4.metric("% OOS profitable", _fmt(pp, ".0f") + "%")

        # The sequence itself: per-fold OOS PnL (bars) + cumulative (line), both in $.
        _f   = sorted(folds, key=lambda f: f["fold_id"])
        xs   = [f"F{f['fold_id'] + 1}" for f in _f]
        opnl = [f["oos_summary"].get("net_total", 0.0) for f in _f]
        cum  = list(np.cumsum(opnl))
        fig  = go.Figure()
        fig.add_trace(go.Bar(x=xs, y=opnl, name="OOS PnL / fold",
                             marker_color=["#00d4aa" if v >= 0 else "#ff6b6b" for v in opnl]))
        fig.add_trace(go.Scatter(x=xs, y=cum, name="Cumulative OOS PnL",
                                 mode="lines+markers", line=dict(color="#e0e0e0")))
        _dark_layout(fig, "OOS result in sequence (fold by fold)", 300)
        st.plotly_chart(fig, use_container_width=True, key=f"rob_seq_{idx}")

        if not ok:
            st.caption("⚠️ Fails: " + "; ".join(fails) + ".")

    # ── Combined verdict ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("## 🏁 Verdict — combining all windows")

    n_win  = len(results)
    n_pass = sum(passes)

    rows = []
    for res in results:
        a = res["agg"]
        ok, _ = _window_pass(a)
        rows.append({
            "Window":           f"IS {res['is_months']}m / OOS {res['oos_months']}m",
            "Folds":            a["n_folds"],
            "Total OOS PnL":    round(a["total_oos_pnl"], 0) if not np.isnan(a["total_oos_pnl"]) else None,
            "Median WFE %":     round(a["mean_wfe"], 0)      if not np.isnan(a["mean_wfe"]) else None,
            "% OOS profitable": round(a["pct_oos_prof"], 0)  if not np.isnan(a["pct_oos_prof"]) else None,
            "Mean OOS PROM":    round(a["mean_oos_prom"], 2) if not np.isnan(a["mean_oos_prom"]) else None,
            "Holds?":           "✅" if ok else "❌",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if n_win and n_pass == n_win:
        verdict, color, msg = ("ROBUST", "#00d4aa",
            "The edge held under **every** window structure tested — the strongest walk-forward "
            "evidence available here. Next: Monte Carlo on the OOS trades, then portfolio sizing.")
    elif n_pass >= max(1, n_win // 2):
        verdict, color, msg = ("FRAGILE", "#d4a000",
            f"The edge held under **{n_pass} of {n_win}** structures — it is structure-dependent. "
            "Treat as provisional; find out which windows fail and why before risking capital.")
    else:
        verdict, color, msg = ("FAIL", "#ff6b6b",
            f"The edge held under only **{n_pass} of {n_win}** structures — it does not generalise "
            "across walk-forward structures. Do NOT trade this configuration as-is.")

    st.markdown(
        f"<div style='padding:14px 18px;border-radius:8px;background:{color}22;"
        f"border-left:5px solid {color};'>"
        f"<span style='font-size:1.5rem;font-weight:700;color:{color};'>{verdict}</span>"
        f"<span style='margin-left:10px;'>— {n_pass} of {n_win} window structures held.</span>"
        f"<div style='margin-top:6px;'>{msg}</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Pass rails per window (fixed in advance): Median WFE ≥ {_WIN_MIN_WFE:.0f}%, "
        f"≥ {_WIN_MIN_PROFPCT:.0f}% of OOS windows profitable, total OOS PnL > 0, "
        f"≥ {_WIN_MIN_FOLDS} folds. The report never tunes these to the result."
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

    # ── Tabs: Configure / Results / Window Map ────────────────────────────────
    tab_cfg, tab_res, tab_map = st.tabs(["⚙️ Configure & Run", "📊 Results", "🗺️ Window Map"])

    # ═══════════════════════════════════════════════════════════════════════════
    with tab_cfg:
        st.subheader("Setup")

        # ── Setup selection via per-SignalType checkboxes (mirrors Bar Analysis) ──
        # Built dynamically from the loaded signals' own types so it adapts to
        # MC (CC2/CC3/…), RevFT (OB/IB/Trap), or any future set. Selected types
        # both filter the signals AND derive the stored setup_id label.
        _all_types = (sorted(signals_raw["SignalType"].dropna().unique())
                      if "SignalType" in signals_raw.columns and not signals_raw.empty
                      else [])
        selected_types = []
        if _all_types:
            st.caption("**Setup (SignalType)** — check the setups to run. Each run stores under "
                       "the combined label below.")
            _tcols = st.columns(min(len(_all_types), 6))
            for _i, _stype in enumerate(_all_types):
                _tk = f"wfa_incl_{_stype}"
                if _tcols[_i % len(_tcols)].checkbox(
                        str(_stype), key=_tk, value=st.session_state.get(_tk, True)):
                    selected_types.append(_stype)
            signals_typed = (signals_raw[signals_raw["SignalType"].isin(selected_types)].copy()
                             if selected_types else signals_raw.iloc[0:0].copy())
            _derived_id = ("ALL" if len(selected_types) == len(_all_types)
                           else "+".join(map(str, selected_types)) or "NONE")
        else:
            st.caption("Loaded signals have no SignalType column — running all signals as one setup.")
            signals_typed = signals_raw.copy()
            _derived_id   = "ALL"

        c1, c2, c3 = st.columns(3)
        setup_id   = c1.text_input("Setup ID (storage label)", value=_derived_id, key="wfa_setup_id",
                                   help="Auto-derived from the checked SignalTypes; edit to relabel the "
                                        "stored run. This is the key results are saved/loaded under.")
        instrument = c2.selectbox("Instrument", list(INSTRUMENTS.keys()), key="wfa_instrument")
        mode       = c3.selectbox("Trade Mode", ["multileg", "singleleg", "3leg"], key="wfa_mode",
                                  help="multileg = 2-leg PB scale-in (E1+E2). singleleg = E1 only. "
                                       "3leg = two scale-ins. Sweep grid adapts to the mode.")
        st.caption(f"{len(signals_typed)} signals across {len(selected_types) or len(_all_types) or 1} "
                   f"selected setup type(s).")

        tick_value  = INSTRUMENTS[instrument]["tick_value"]
        def_comm    = INSTRUMENTS[instrument]["default_commission"]

        st.subheader("Window Parameters")
        wc1, wc2, wc3 = st.columns(3)
        is_months  = wc1.number_input("IS window (months)", min_value=3, max_value=24, value=12, step=3,
                                      key="wfa_is_mo", help=_METRIC_HELP["is_window"])
        oos_months = wc2.number_input("OOS window (months)", min_value=1, max_value=6,  value=3,  step=1,
                                      key="wfa_oos_mo", help=_METRIC_HELP["oos_window"])
        n_sets     = wc3.number_input("Param sets (Kaufman avg)", min_value=1, max_value=10, value=3,
                                      key="wfa_n_sets", help=_METRIC_HELP["n_sets"])

        is_days  = int(is_months  * _TRADING_DAYS_PER_YEAR / 12)
        oos_days = int(oos_months * _TRADING_DAYS_PER_YEAR / 12)

        all_dates  = sorted(signals_typed["Date"].unique()) if not signals_typed.empty else []
        folds_preview = build_folds(all_dates, is_days, oos_days) if all_dates else []
        if not all_dates:
            st.warning("No signals selected — check at least one SignalType above.")
        else:
            st.caption(
                f"Dataset: {len(all_dates)} trading days "
                f"({all_dates[0]} → {all_dates[-1]})  |  "
                f"**{len(folds_preview)} folds** with IS={is_days}d / OOS={oos_days}d"
            )

        if all_dates and len(folds_preview) < 10:
            st.warning(f"Only {len(folds_preview)} folds. Pardo minimum is 10. "
                       "Consider a shorter IS or OOS window.")

        st.subheader("Execution Parameters")
        ec1, ec2, ec3, ec4, ec5 = st.columns(5)
        entry_slip  = ec1.number_input("Entry slip (ticks)", 0.0, 5.0, 1.0, 0.5, key="wfa_eslip")
        exit_slip   = ec2.number_input("Exit slip (ticks)",  0.0, 5.0, 1.0, 0.5, key="wfa_xslip")
        stop_offset = ec3.number_input("Stop offset (ticks)",0, 5, 1, key="wfa_soff")
        contracts_t1= ec4.number_input("Contracts E1",       1, 10, 1, key="wfa_ct1")
        contracts_t2= ec5.number_input("Contracts E2",       0, 10, 1, key="wfa_ct2")
        commission  = st.number_input("Commission ($/contract, round-trip)", 0.0, 10.0, float(def_comm), 0.5,
                                      key="wfa_comm",
                                      help="Round-trip commission per contract, charged once per trade per "
                                           "contract (entry+exit combined — NOT per side). ES default $3.00 is r/t.")

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
            pb_round     = "nearest",  # realistic tick-snap of PB & targets (execution accuracy)
        )

        # ── Target / Pullback pin controls ────────────────────────────────────
        st.subheader("Target & Pullback Parameters")
        st.caption(
            "Leave 'Pin?' unchecked to sweep the full grid. "
            "Check to fix a value and reduce the search space."
        )
        tp1, tp2, tp3 = st.columns(3)
        _T_OPTS = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]
        _PB_OPTS = [-0.25, -0.375, -0.50, -0.625, -0.75, -1.00]

        pin_t1_chk = tp1.checkbox("Pin T1?", value=False, key="wfa_pin_t1_chk")
        pin_t1 = (
            tp1.selectbox("T1 value (R)", _T_OPTS, index=2, key="wfa_pin_t1_val")
            if pin_t1_chk else None
        )

        pin_t2_chk = tp2.checkbox("Pin T2?", value=False, key="wfa_pin_t2_chk")
        pin_t2 = (
            tp2.selectbox("T2 value (R)", _T_OPTS, index=2, key="wfa_pin_t2_val")
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

        # Signal CC filter (applied on top of the SignalType selection)
        cc_col = None
        for col in ["CCCount", "CC", "SetupCC", "cc_count"]:
            if col in signals_typed.columns:
                cc_col = col
                break

        if cc_col and not signals_typed.empty:
            cc_vals = sorted(signals_typed[cc_col].dropna().unique())
            sel_cc  = st.multiselect(f"Filter by {cc_col}", cc_vals, default=cc_vals, key="wfa_cc_filter")
            signals_filtered = signals_typed[signals_typed[cc_col].isin(sel_cc)].copy() if sel_cc else signals_typed.copy()
        else:
            signals_filtered = signals_typed.copy()

        st.caption(f"{len(signals_filtered)} signals after filter")

        # ── 🧭 Multi-slice regime filter (optional; validated via WFA) ─────────
        # Research the buckets in Bar Analysis → Regime/Indicator Expectancy,
        # pre-commit a small hypothesis-driven set HERE, then let WFA validate it.
        # WFA optimizes ONLY T1/T2/PB — these buckets are NEVER swept (S20 rails).
        # "Locked" = fixed before the run & not optimized by WFA; it is NOT an
        # on/off state. The master toggle below is the on/off control.
        import regime_filter as _rf
        locked_spec: dict = {}
        with st.expander("🧭 Regime Filter (optional — off by default)", expanded=False):
            _rf_on = st.checkbox(
                "Enable regime filter", value=False, key="wfa_rf_enable",
                help="OFF = every signal passes through (default). ON = keep only "
                     "signals whose regime buckets you select below. Once enabled, the "
                     "selection is LOCKED for the run — WFA never optimizes it (only "
                     "T1/T2/PB). To turn a single indicator off, leave ALL its buckets "
                     "selected.",
            )
            st.caption(
                "**Discipline (handoff S20):** pre-commit a *small* hypothesis-driven "
                "set, prefer open-ended tails over interior bands, and never re-tune "
                "against OOS results. Each kept bucket needs a structural *why*. "
                "Counts shown are on the current signal set."
            )

            if not _rf_on:
                st.caption("Filter OFF — all signals pass to WFA.")
            elif signals_filtered.empty:
                st.info("No signals to filter.")
            else:
                # Tag once and memoize across reruns (tag_signals runs market
                # structure over the full bar series — too heavy to redo per widget).
                _rf_fp = (len(signals_filtered),
                          int(pd.util.hash_pandas_object(
                              signals_filtered["DateTime"], index=False).sum()
                              & 0xFFFFFFFF),
                          str(bars["DateTime"].iloc[-1]), len(bars))
                if st.session_state.get("_wfa_rf_fp") != _rf_fp:
                    try:
                        _tagged, _bcols = _rf.tag_and_bucket(signals_filtered, bars)
                    except Exception as _e:                      # pragma: no cover
                        _tagged, _bcols = None, {}
                        st.warning(f"Could not tag signals for regime filtering: {_e}")
                    st.session_state["_wfa_rf_fp"]     = _rf_fp
                    st.session_state["_wfa_rf_tagged"] = _tagged
                    st.session_state["_wfa_rf_bcols"]  = _bcols
                else:
                    _tagged = st.session_state["_wfa_rf_tagged"]
                    _bcols  = st.session_state["_wfa_rf_bcols"]

                if _bcols:
                    for ind in _rf.SHORTLIST:
                        if ind.key not in _bcols:
                            continue
                        _bcol    = _bcols[ind.key]
                        _present = _rf.present_buckets(_tagged, ind, _bcol)
                        if not _present:
                            continue
                        _counts = _tagged[_bcol].value_counts()
                        _sel = st.multiselect(
                            f"{ind.label}  ·  *{ind.factor}*",
                            _present, default=_present, key=f"wfa_rf_{ind.key}",
                            format_func=lambda b, c=_counts: f"{b}  ({int(c.get(b, 0))})",
                            help="Keep signals whose value falls in the selected "
                                 "bucket(s). Leave ALL selected = this indicator is off.",
                        )
                        if _sel and set(_sel) < set(_present):
                            locked_spec[ind.key] = _sel
                            if ind.ordered and not _rf.is_open_ended(ind, _sel):
                                st.caption(f"⚠️ {ind.label}: interior band selected — "
                                           "prefer an open-ended tail (rail #3).")

                    if locked_spec:
                        _mask = _rf.filter_mask(_tagged, _bcols, locked_spec)
                        _kept = set(_tagged.loc[_mask, "_rf_id"].tolist())
                        _sig2 = signals_filtered.copy()
                        _sig2["_rf_id"] = np.arange(len(_sig2))
                        signals_filtered = (_sig2[_sig2["_rf_id"].isin(_kept)]
                                            .drop(columns="_rf_id").copy())
                        st.success(
                            f"Regime filter ACTIVE — **{len(signals_filtered)} of "
                            f"{len(_sig2)}** signals kept.")
                        st.caption(f"🔒 Locked: {_rf.describe_spec(locked_spec)}")
                        if len(signals_filtered):
                            _em, _sh, _cm = _rf.time_concentration(signals_filtered["DateTime"])
                            st.caption(f"Time spread of kept signals: {_em} {_cm} "
                                       "(🔴 = single-regime windfall risk — a filter that "
                                       "only 'works' in one window is not durable).")
                    else:
                        st.caption("Enabled, but every indicator has all buckets "
                                   "selected — no constraint active, all signals pass.")
                elif _tagged is not None:
                    st.info("Regime indicators unavailable on this signal set "
                            "(missing Direction / price / indicator columns).")

        # Fold-feasibility guard: surface WHY a run might yield 0 folds.
        _n_into = len(signals_filtered)
        _n_days = signals_filtered["Date"].nunique() if _n_into else 0
        _need_days = int(is_days + oos_days)
        st.caption(f"{_n_into} signals into WFA across {_n_days} signal-days "
                   f"(need ≥ ~{_need_days} trading-days of span to form 1 fold).")
        if _n_into and _n_days < _need_days:
            st.warning(
                f"Only {_n_days} signal-days remain — fewer than the ~{_need_days} "
                f"(IS {is_days} + OOS {oos_days}) needed for a single fold, so the run "
                "will produce **0 folds**. Disable/loosen the regime filter or widen the "
                "date range / shorten the IS+OOS windows.")

        # ── Run button ────────────────────────────────────────────────────────
        st.divider()
        run_id_input = st.text_input("Run ID (leave blank to auto-generate)", value="", key="wfa_run_id_input")
        notes_input  = st.text_input("Notes (optional)", value="", key="wfa_notes")

        run_btn = st.button("▶ Run WFA", type="primary", key="wfa_run_btn",
                            disabled=signals_filtered.empty)

        if run_btn and not signals_filtered.empty:
            run_id = run_id_input.strip() or f"run_{uuid.uuid4().hex[:8]}"
            # Permanently record the locked regime filter with the run (rail #1:
            # the filter is LOCKED before the run — the run notes prove what it was).
            _notes_full = notes_input
            if locked_spec:
                _rf_desc = _rf.describe_spec(locked_spec)
                _notes_full = (f"{notes_input} | " if notes_input else "") + \
                              f"regime_filter[LOCKED]: {_rf_desc}"
            create_run(run_id, setup_id, mode, base_params, _notes_full)

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

        sel_label   = st.selectbox("Select run", run_labels, index=default_idx, key="wfa_sel_run")
        sel_run_row = all_runs.iloc[run_labels.index(sel_label)]
        sel_run_id  = sel_run_row["run_id"]
        sel_setup   = sel_run_row["setup_id"]
        try:
            _run_cfg = json.loads(sel_run_row.get("params_json") or "{}")
        except Exception:
            _run_cfg = {}
        _base_slip_ticks = float(_run_cfg.get("entry_slip", 0)) + float(_run_cfg.get("exit_slip", 0))

        folds_df = load_folds(sel_run_id, sel_setup)

        if folds_df.empty:
            st.info("No fold data for this run.")
            return

        # ── Guardrail summary ─────────────────────────────────────────────────
        with st.expander("🔒 Kaufman / Pardo Guardrails", expanded=False):
            report = guardrail_report(folds_df)
            _guardrail_badges(report)
            _guardrail_breakdown(folds_df)

        # ── OOS equity curve ──────────────────────────────────────────────────
        with st.expander("📈 Combined OOS Equity Curve", expanded=False):
            oos_trades = load_all_oos_trades(sel_run_id, sel_setup)
            if not oos_trades.empty:
                fig = _equity_chart(oos_trades, f"OOS Equity — {sel_setup} / {sel_run_id}")
                st.plotly_chart(fig, use_container_width=True)

                filled_oos = oos_trades[oos_trades["Filled"] == True]
                if not filled_oos.empty:
                    _sorted = filled_oos.sort_values(["Date", "EntryTime"])
                    eq  = _sorted["NetPnL"].cumsum()
                    pk  = eq.cummax()
                    dd  = float((eq - pk).min())
                    pnl = filled_oos["NetPnL"].sum()
                    pf  = (filled_oos.loc[filled_oos["NetPnL"] > 0, "NetPnL"].sum() /
                           abs(filled_oos.loc[filled_oos["NetPnL"] < 0, "NetPnL"].sum())
                           if (filled_oos["NetPnL"] < 0).any() else float("nan"))
                    # Max calendar days underwater (Time Underwater) — pure result, no params.
                    underwater = eq < pk
                    tuw_days   = _max_underwater_days(_sorted["Date"], underwater)

                    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
                    mc1.metric("OOS Net PnL", f"${pnl:,.0f}",
                               help="Sum of NetPnL across all filled OOS trades (friction already baked in).")
                    mc2.metric("OOS Trades", len(filled_oos),
                               help=_METRIC_HELP["n_trades"])
                    mc3.metric("OOS Win%", f"{(filled_oos['NetPnL']>0).mean()*100:.1f}%",
                               help=_METRIC_HELP["win_pct"])
                    mc4.metric("OOS PF", _fmt(pf, ".2f"),
                               help=_METRIC_HELP["pf"])
                    mc5.metric("OOS Max DD", f"${dd:,.0f}",
                               help=_METRIC_HELP["max_dd"])
                    mc6.metric("Max Time U/W", f"{tuw_days}d",
                               help="Max Time Underwater — longest stretch of calendar days the OOS equity "
                                    "curve spent below its prior peak. A long flat/underwater stretch is the "
                                    "main psychological-risk metric even when the dollar drawdown is small.")
            else:
                st.info("No OOS trade data found.")

        # ── Fold summary table ────────────────────────────────────────────────
        with st.expander("📋 Fold Summary Table", expanded=False):
            _fold_table(folds_df)

        # ── Per-fold charts (describes the run — no new strategy params) ───────
        with st.expander("📊 Per-Fold Charts", expanded=False):
            _f      = folds_df.sort_values("fold_id")
            _fx     = _f["fold_id"].astype(str)
            wfe_pct = (_f["wfe"] * 100)
            _wcol   = ["#00d4aa" if v >= 50 else "#d4a000" if v >= 25 else "#ff6b6b"
                       for v in wfe_pct.fillna(0)]
            fig_wfe = go.Figure(go.Bar(x=_fx, y=wfe_pct, marker_color=_wcol,
                                       text=wfe_pct.round(0), textposition="outside"))
            fig_wfe.add_hline(y=100, line_dash="dot", line_color="#888")
            _dark_layout(fig_wfe, "Walk-Forward Efficiency by fold (OOS ÷ IS, %)", 300)
            st.plotly_chart(fig_wfe, use_container_width=True)

            fig_pnl = go.Figure()
            fig_pnl.add_trace(go.Bar(x=_fx, y=_f["is_net_pnl"],  name="IS",  marker_color="#4a6fa5"))
            fig_pnl.add_trace(go.Bar(x=_fx, y=_f["oos_net_pnl"], name="OOS", marker_color="#00d4aa"))
            _dark_layout(fig_pnl, "IS vs OOS Net PnL by fold", 300)
            fig_pnl.update_layout(barmode="group")
            st.plotly_chart(fig_pnl, use_container_width=True)
            st.caption("WFE ~100% = OOS held up to IS. >>100% usually means a regime shift amplified the "
                       "edge OOS (not necessarily durable). Watch for a few folds carrying the whole result.")

        # ── OOS trade distribution ─────────────────────────────────────────────
        with st.expander("📉 OOS Trade Distribution", expanded=False):
            _ft = oos_trades[oos_trades["Filled"] == True] if not oos_trades.empty else pd.DataFrame()
            if _ft.empty:
                st.info("No OOS trades to plot.")
            else:
                pnl_s = _ft["NetPnL"]
                fig_h = go.Figure(go.Histogram(x=pnl_s, nbinsx=60, marker_color="#00d4aa"))
                fig_h.add_vline(x=0, line_color="#888", line_dash="dot")
                _dark_layout(fig_h, "Per-trade OOS NetPnL distribution", 320)
                st.plotly_chart(fig_h, use_container_width=True)
                hc1, hc2, hc3, hc4 = st.columns(4)
                hc1.metric("Mean / trade",   f"${pnl_s.mean():,.1f}")
                hc2.metric("Median / trade", f"${pnl_s.median():,.1f}")
                hc3.metric("Std dev",        f"${pnl_s.std():,.0f}")
                hc4.metric("Skew",           f"{pnl_s.skew():.2f}",
                           help="Distribution skew. Strong positive skew = a few big winners carry the edge; "
                                "negative = fat-tailed losses.")

        # ── Friction & robustness diagnostics (Pardo-safe; adds no strategy params) ─
        with st.expander("🧪 Friction & Robustness Diagnostics", expanded=False):
            _ft = oos_trades[oos_trades["Filled"] == True] if not oos_trades.empty else pd.DataFrame()
            if _ft.empty:
                st.info("No OOS trades to analyse.")
            else:
                net        = float(_ft["NetPnL"].sum())
                has_slip   = "SlippageDollar" in _ft.columns
                total_slip = float(_ft["SlippageDollar"].sum()) if has_slip else float("nan")
                total_comm = float((_ft["GrossPnL"] - _ft["NetPnL"]).sum())
                eq         = _ft.sort_values(["Date", "EntryTime"])["NetPnL"].cumsum()
                pain_usd, pain_pct = _pain_index(eq)
                _wfe_defined = pd.to_numeric(folds_df["wfe"], errors="coerce").dropna()
                _n_undef     = len(folds_df) - len(_wfe_defined)
                median_wfe   = _wfe_defined.median() * 100 if len(_wfe_defined) else float("nan")
                wwfe         = _windsorized_mean_wfe(folds_df["wfe"]) * 100

                d1, d2, d3 = st.columns(3)
                d1.metric("Median WFE", _fmt(median_wfe, ".1f") + "%",
                          help=_METRIC_HELP["wfe"] +
                               (f" · {_n_undef} fold(s) N/A (IS not profitable)" if _n_undef else ""))
                d2.metric("Windsorized WFE", _fmt(wwfe, ".1f") + "%",
                          help="Mean WFE after dropping the single best and worst folds. If this is far below "
                               "the raw Mean WFE, the headline is outlier-driven (one windfall window), not "
                               "structural adaptability.")
                d3.metric("Pain Index", f"${pain_usd:,.0f}",
                          help="Average depth of drawdown across the whole OOS equity path (not just the max). "
                               "Captures the 'drag' of long shallow underwater stretches.")

                d4, d5, d6 = st.columns(3)
                fpr = ((total_slip + total_comm) / net) if (net and not np.isnan(total_slip)) else float("nan")
                d4.metric("Total Commission", f"${total_comm:,.0f}",
                          help="Σ(GrossPnL − NetPnL) over filled OOS trades — round-trip commission charged.")
                d5.metric("Total Slippage", f"${total_slip:,.0f}" if has_slip else "—",
                          help="Σ SlippageDollar over filled OOS trades (modelled fill cost).")
                d6.metric("Friction-to-Profit", _fmt(fpr * 100, ".1f") + "%" if not np.isnan(fpr) else "—",
                          help="(Total slippage + commission) ÷ net profit. High values mean the edge mostly "
                               "feeds execution costs — fragile if fills worsen or volume thins.")

                # ── Assumption / friction ledger (make stacked conservatism visible) ──
                _led = friction_ledger(_ft)
                if _led:
                    st.markdown("**Assumption ledger** — frictionless gross → net, so the stacked "
                                "execution conservatism is visible, not hidden.")
                    ledger = pd.DataFrame([
                        {"Step": "Frictionless gross", "Amount $": _led["frictionless_gross"]},
                        {"Step": "− Slippage",          "Amount $": -_led["slippage"]},
                        {"Step": "− Commission",        "Amount $": -_led["commission"]},
                        {"Step": "= Net (modeled)",     "Amount $": _led["net"]},
                    ])
                    lc1, lc2 = st.columns([2, 1])
                    lc1.dataframe(ledger, use_container_width=True, hide_index=True)
                    lc2.metric("Friction / trade", f"${_led['per_trade_friction']:,.0f}",
                               help="Total slippage+commission ÷ trades. Sanity-check vs real-world "
                                    "execution (e.g. ES ≈ $15.50/trade). If the model's haircut is much "
                                    "larger than reality, you may be under-optimizing.")
                    lc2.metric("Net / trade", f"${_led['per_trade_net']:,.0f}")
                    st.caption("Slippage is embedded in fills, so frictionless = GrossPnL + slippage. "
                               "Tick-snap & same-bar priority are baked into the fills too (bounded ~½ tick) — "
                               "isolating them needs a counterfactual re-run; the SEC slider below probes slippage.")

                # ── Slippage Elasticity (SEC) ─────────────────────────────────
                st.markdown("**Slippage Elasticity (SEC)** — how OOS net profit responds to worse fills.")
                if not has_slip:
                    st.caption("Trade log has no SlippageDollar column — SEC unavailable for this run.")
                else:
                    m = st.slider("Slippage multiplier (× modelled fill cost)", 0.0, 3.0, 1.0, 0.25,
                                  key="wfa_sec_mult",
                                  help="Scales the modelled slippage. 1.0× = as run. Slippage is linear in "
                                       "ticks, so this is an exact re-pricing of the existing OOS trades.")
                    adj_net = net - total_slip * (m - 1.0)
                    sc1, sc2 = st.columns(2)
                    sc1.metric(f"OOS Net PnL @ {m:.2f}×", f"${adj_net:,.0f}",
                               delta=f"${adj_net - net:,.0f}")
                    if _base_slip_ticks > 0:
                        sec_half = -total_slip / _base_slip_ticks * 0.5
                        sc2.metric("SEC (per +0.5 tick)", f"${sec_half:,.0f}",
                                   help=f"Run modelled {_base_slip_ticks:.1f} slip ticks round-trip. Each extra "
                                        "0.5 tick costs this much across all OOS trades.")
                    mults = np.arange(0.0, 3.01, 0.25)
                    curve = net - total_slip * (mults - 1.0)
                    fig_sec = go.Figure(go.Scatter(x=mults, y=curve, mode="lines+markers",
                                                   line=dict(color="#00d4aa")))
                    fig_sec.add_hline(y=0, line_dash="dot", line_color="#ff6b6b")
                    fig_sec.add_vline(x=1.0, line_dash="dot", line_color="#888")
                    _dark_layout(fig_sec, "OOS Net PnL vs slippage multiplier", 300)
                    st.plotly_chart(fig_sec, use_container_width=True)
                    _be = net / total_slip + 1.0 if total_slip else float("nan")
                    if not np.isnan(_be) and _be > 0:
                        st.caption(f"Edge reaches break-even at **{_be:.2f}×** modelled slippage "
                                   f"({_be * _base_slip_ticks:.1f} round-trip ticks)." if _base_slip_ticks > 0
                                   else f"Edge reaches break-even at **{_be:.2f}×** modelled slippage.")

        # ── Metric glossary ────────────────────────────────────────────────────
        with st.expander("ℹ️ Metric Glossary"):
            _glabels = {
                "prom": "PROM", "pnl_dd": "PnL / DD", "pf": "Profit Factor",
                "win_pct": "Win %", "max_dd": "Max Drawdown", "wfe": "Walk-Forward Efficiency",
                "rob_pct": "IS Robustness", "kurtosis": "Kurtosis", "n_trades": "Trade count",
                "is_window": "IS window", "oos_window": "OOS window", "n_sets": "Param sets (Kaufman avg)",
            }
            for _k, _lbl in _glabels.items():
                st.markdown(f"**{_lbl}** — {_METRIC_HELP[_k]}")

        # ── Per-fold drill-down ───────────────────────────────────────────────
        with st.expander("🔍 Per-Fold Drill-Down"):
            fold_ids = folds_df["fold_id"].tolist()
            sel_fold = st.selectbox("Select fold", fold_ids, key="wfa_sel_fold")

            fold_row = folds_df[folds_df["fold_id"] == sel_fold].iloc[0]
            dc1, dc2 = st.columns(2)

            def _sf(v, fmt, prefix="", suffix=""):
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return "—"
                return f"{prefix}{v:{fmt}}{suffix}"

            with dc1:
                st.markdown("**IS Period**")
                st.caption(f"{fold_row['is_start']} → {fold_row['is_end']}")
                is_metrics = {
                    "Trades": fold_row["is_n_trades"],
                    "Net PnL": _sf(fold_row['is_net_pnl'], ",.0f", "$"),
                    "Win%": _sf(fold_row['is_win_pct'], ".1f", suffix="%"),
                    "PF": _sf(fold_row['is_pf'], ".2f"),
                    "PROM": _sf(fold_row['is_prom'], ".2f"),
                    "PnL/DD": _sf(fold_row['is_pnl_dd'], ".2f"),
                    "Max DD": _sf(fold_row['is_max_dd'], ",.0f", "$"),
                    "Robustness": _sf(fold_row['is_rob_pct'], ".1f", suffix="%"),
                    "Kurtosis": _sf(fold_row['is_kurtosis'], ".2f"),
                }
                for k, v in is_metrics.items():
                    st.text(f"  {k:<14} {v}")

            with dc2:
                st.markdown("**OOS Period**")
                st.caption(f"{fold_row['oos_start']} → {fold_row['oos_end']}")
                _wfe = fold_row['wfe']
                oos_metrics = {
                    "Trades": fold_row["oos_n_trades"],
                    "Net PnL": _sf(fold_row['oos_net_pnl'], ",.0f", "$"),
                    "Win%": _sf(fold_row['oos_win_pct'], ".1f", suffix="%"),
                    "PF": _sf(fold_row['oos_pf'], ".2f"),
                    "PROM": _sf(fold_row['oos_prom'], ".2f"),
                    "PnL/DD": _sf(fold_row['oos_pnl_dd'], ".2f"),
                    "Max DD": _sf(fold_row['oos_max_dd'], ",.0f", "$"),
                    "WFE": _sf(_wfe * 100 if _wfe is not None else None, ".1f", suffix="%"),
                }
                for k, v in oos_metrics.items():
                    st.text(f"  {k:<14} {v}")

            params_chosen = fold_row.get("params_chosen", [])
            if params_chosen:
                _plabels = {
                    "target_r": "Target R", "t1_r": "T1 R", "t2_r": "T2 R",
                    "ml_pb_r": "PB R", "pb1_r": "PB1 R",
                }
                _pdf = pd.DataFrame(params_chosen).rename(columns=_plabels)
                # R-grid values (0.625 / 0.375) need 3 dp — render as strings so the
                # global 2-dp display rule leaves them intact.
                for _c in _pdf.columns:
                    _pdf[_c] = _pdf[_c].map(lambda v: f"{v:.3f}")
                _pdf.insert(0, "Rank (by IS PROM)", range(1, len(_pdf) + 1))
                st.markdown("**Top-N IS parameter sets** — the best combos by PROM in the IS sweep. "
                            "These are **averaged** to produce the single locked param set traded OOS "
                            "(Kaufman rule — never trade the single best).")
                st.dataframe(_pdf, use_container_width=True, hide_index=True)
                _avg = {_plabels.get(k, k): round(float(np.mean([p[k] for p in params_chosen])), 3)
                        for k in params_chosen[0].keys()}
                st.caption("Averaged (locked) params traded OOS:  " +
                           "  ·  ".join(f"**{k}** {v}" for k, v in _avg.items()))

            st.markdown("**🗺️ IS optimization surface** — is the chosen set on a plateau or a spike?")
            _surf_mode = sel_run_row.get("mode", "multileg")
            _is_surface_section(sel_run_id, sel_setup, int(sel_fold), _surf_mode, params_chosen)

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

    # ═══════════════════════════════════════════════════════════════════════════
    with tab_map:
        st.subheader("Window-Anchor Heatmap")
        st.caption(
            "Meta-validation (Pardo-safe): runs a full WFA for each IS×OOS window pair and "
            "colours each cell by an aggregate metric. A **contiguous warm cluster** around your "
            "chosen 12m/3m means the window choice isn't itself overfit; a lone hot cell means it is. "
            "Uses the **same setup/mode/pins/filters** configured in ⚙️ Configure & Run. "
            "Nothing is persisted — this never touches your stored runs or the OOS lock."
        )

        if signals_filtered.empty:
            st.info("Select at least one SignalType in ⚙️ Configure & Run first.")
        else:
            mg1, mg2 = st.columns(2)
            is_grid  = mg1.multiselect("IS windows (months)", [3, 6, 9, 12, 18, 24],
                                       default=[3, 6, 12, 18, 24], key="wfa_map_is")
            oos_grid = mg2.multiselect("OOS windows (months)", [1, 2, 3, 4, 6],
                                       default=[1, 2, 3, 4, 6], key="wfa_map_oos")
            st.caption("All metrics (PnL, WFE, PF, Max DD, % profitable) are computed in one pass "
                       "when you build the map and shown together below — no metric dropdown.")

            n_cells = len(is_grid) * len(oos_grid)
            st.caption(f"**{n_cells} cells** — each is a full WFA "
                       f"({'singleleg ~7' if mode == 'singleleg' else 'multileg grid'} combos × folds). "
                       "Heavier modes/grids can take minutes; pin params in Configure to shrink it.")

            if st.button("▶ Build Window Map", type="primary", key="wfa_map_run",
                         disabled=(n_cells == 0)):
                import massive as _massive_mod
                sig_dates  = sorted(signals_filtered["Date"].unique())
                _ticks_key = f"wfa_ticks__{hash(tuple(sig_dates))}"
                if _ticks_key not in st.session_state:
                    with st.spinner("Loading tick cache…"):
                        tbd = {}
                        for d in sig_dates:
                            dt = _massive_mod.load_continuous_ticks(d)
                            if not dt.empty:
                                tbd[d] = dt
                        st.session_state[_ticks_key] = tbd
                ticks_by_date = st.session_state[_ticks_key]

                pbar = st.progress(0.0)
                stat = st.empty()

                def _mcb(k, total, msg):
                    pbar.progress(k / total)
                    stat.text(f"{k}/{total} — {msg}")

                with st.spinner("Running window grid…"):
                    grid_df = run_window_grid(
                        signals_filtered, ticks_by_date, bars_by_date,
                        base_params, mode, is_grid, oos_grid,
                        n_param_sets=int(n_sets),
                        pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb,
                        progress_cb=_mcb,
                    )
                pbar.progress(1.0)
                stat.text("Done.")
                st.session_state["wfa_map_df"] = grid_df

            grid_df = st.session_state.get("wfa_map_df")
            if grid_df is not None and not grid_df.empty:
                grid_df = grid_df.copy()
                # Window Robustness Score — count how many fixed pass/fail tests each
                # architecture survives (NOT a profit-weighted blend; profit is only
                # one of the tests). Rank by tests survived → "which window structure
                # is most robust", not "which made the most money".
                grid_df["robust_score"] = grid_df.apply(
                    lambda r: _window_robustness_score(r.to_dict()), axis=1)

                # ── Robustness-score heatmap (the headline) ───────────────────
                st.markdown("#### 🛡️ Window Robustness Score — tests survived (0–"
                            f"{_WIN_N_TESTS})")
                st.plotly_chart(
                    _window_heatmap(grid_df, "robust_score", "Tests survived", ".0f"),
                    use_container_width=True)
                st.caption(
                    f"Each cell = how many of {_WIN_N_TESTS} independent robustness tests that "
                    "IS/OOS architecture passes (PnL>0, WFE≥50%, ≥60% OOS green, PF≥1.2, PROM>0, "
                    "return≥Max DD, ≥8 folds). Thresholds are fixed in advance — not tuned to the "
                    "result. **Pick a structure from a high-scoring *cluster*, not the single top "
                    "cell** (one peak cell is meta-overfitting; a warm neighbourhood is durable)."
                )

                # ── Ranked architecture table ─────────────────────────────────
                _rank = grid_df.copy()
                _rank["Window"] = ("IS " + _rank["is_months"].astype(str) + "m / OOS "
                                   + _rank["oos_months"].astype(str) + "m")
                _rank["Tests"]  = _rank["robust_score"].astype(str) + f"/{_WIN_N_TESTS}"
                _rank = _rank.sort_values(["robust_score", "mean_wfe", "mean_oos_prom"],
                                          ascending=False)
                _show = _rank[["Window", "Tests", "n_folds", "total_oos_pnl", "oos_pf_median",
                               "mean_wfe", "pct_oos_prof", "mean_oos_prom", "oos_maxdd_worst"]].copy()
                _show.columns = ["Window", "Tests survived", "Folds", "Total OOS PnL", "Median OOS PF",
                                 "Median WFE %", "% OOS green", "Mean PROM", "Worst-fold Max DD"]
                for _c, _r in {"Total OOS PnL": 0, "Median OOS PF": 2, "Median WFE %": 0,
                               "% OOS green": 0, "Mean PROM": 2, "Worst-fold Max DD": 0}.items():
                    _show[_c] = _show[_c].map(lambda v, _r=_r: round(v, _r) if pd.notna(v) else None)
                st.markdown("**Architectures ranked by robustness** (tests survived, then WFE, then PROM):")
                st.dataframe(_show, use_container_width=True, hide_index=True)

                # ── The four component heatmaps (the evidence behind the score) ─
                st.markdown("#### Component metrics (the evidence behind the score)")
                st.plotly_chart(_window_heatmap(grid_df, "total_oos_pnl", "Total OOS PnL", ",.0f"),
                                use_container_width=True)
                st.plotly_chart(_window_heatmap(grid_df, "mean_wfe", "Median WFE %", ".0f"),
                                use_container_width=True)
                st.plotly_chart(_window_heatmap(grid_df, "oos_pf_median", "Median OOS PF", ".2f"),
                                use_container_width=True)
                st.plotly_chart(_window_heatmap(grid_df, "oos_maxdd_worst", "Worst-fold OOS Max DD", ",.0f"),
                                use_container_width=True)
                st.caption("Each cell label: metric value and (fold count). Few folds = low confidence — "
                           "large IS + large OOS leaves fewer rolling windows in a 5-yr dataset. PF and Max "
                           "DD are per-fold aggregates (median PF, worst single-fold DD); the concatenated-"
                           "equity PF/DD for one chosen window live in the 📊 Results tab.")

            # ── 🧭 4-Window Robustness Report (full WFAs in sequence + verdict) ──
            st.divider()
            st.markdown("### 🧭 Robustness Report — validate across 4 window structures")
            st.caption(
                "Beyond the heatmap: runs a **full walk-forward for each of the 4 structures below**, "
                "shows them in sequence on this page, and ends with one actionable verdict "
                "(ROBUST / FRAGILE / FAIL). Same setup, params, pins and filters as ⚙️ Configure & Run. "
                "Heavier than the heatmap (4 full WFAs); nothing is persisted."
            )
            _def_struct = [(12, 3), (12, 1), (6, 3), (6, 1)]
            _scols = st.columns(4)
            structures = []
            for _i, (_dim, _dom) in enumerate(_def_struct):
                _im = _scols[_i].number_input(f"W{_i + 1} IS (mo)", 3, 24, _dim, 3, key=f"wfa_rob_is_{_i}")
                _om = _scols[_i].number_input(f"W{_i + 1} OOS (mo)", 1, 6, _dom, 1, key=f"wfa_rob_oos_{_i}")
                structures.append((int(_im), int(_om)))

            if st.button("▶ Build 4-Window Robustness Report", type="primary",
                         key="wfa_rob_run", disabled=signals_filtered.empty):
                import massive as _massive_mod
                sig_dates  = sorted(signals_filtered["Date"].unique())
                _ticks_key = f"wfa_ticks__{hash(tuple(sig_dates))}"
                if _ticks_key not in st.session_state:
                    with st.spinner("Loading tick cache…"):
                        tbd = {}
                        for d in sig_dates:
                            dt = _massive_mod.load_continuous_ticks(d)
                            if not dt.empty:
                                tbd[d] = dt
                        st.session_state[_ticks_key] = tbd
                ticks_by_date = st.session_state[_ticks_key]

                rbar = st.progress(0.0)
                rstat = st.empty()

                def _rcb(k, total, msg):
                    rbar.progress(min(k / total, 1.0))
                    rstat.text(f"{k}/{total} — {msg}")

                with st.spinner("Running 4 walk-forward structures…"):
                    rob_results = run_window_structures(
                        signals_filtered, ticks_by_date, bars_by_date,
                        base_params, mode, structures,
                        n_param_sets=int(n_sets),
                        pin_t1=pin_t1, pin_t2=pin_t2, pin_pb=pin_pb,
                        progress_cb=_rcb,
                    )
                rbar.progress(1.0)
                rstat.text("Done.")
                st.session_state["wfa_rob_results"] = rob_results

            rob_results = st.session_state.get("wfa_rob_results")
            if rob_results:
                _robustness_report(rob_results)
