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
        wfe = oos_ann / is_ann if is_ann != 0 else float("nan")

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
                "mean_oos_prom": float("nan"), "pct_oos_prof": float("nan")}
    wfe  = [f["wfe"] for f in folds if f["wfe"] is not None and not np.isnan(f["wfe"])]
    opnl = [f["oos_summary"].get("net_total", 0.0) for f in folds]
    opr  = [f["oos_summary"].get("prom", float("nan")) for f in folds]
    opr  = [v for v in opr if v is not None and not np.isnan(v)]
    return {
        "n_folds":       len(folds),
        "mean_wfe":      float(np.mean(wfe)) * 100 if wfe else float("nan"),
        "total_oos_pnl": float(np.sum(opnl)),
        "mean_oos_prom": float(np.mean(opr)) if opr else float("nan"),
        "pct_oos_prof":  float(np.mean([p > 0 for p in opnl]) * 100) if opnl else float("nan"),
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
        "IS Rob %":    folds_df["is_rob_pct"].round(1),
        "Kurt ≤6":     folds_df["kurtosis_ok"].map(_flag),
        "Kurtosis":    folds_df["is_kurtosis"].round(2),
        "≥30 trades":  folds_df["min_trades_ok"].map(_flag),
        "IS Trades":   folds_df["is_n_trades"],
        "OOS Profit":  (folds_df["oos_net_pnl"] > 0).map(_flag),
        "OOS Net $":   folds_df["oos_net_pnl"].round(0),
        "WFE %":       (folds_df["wfe"] * 100).round(1),
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
        ("Kurtosis >6",     "kurtosis_ok", True),
        ("IS trades <30",   "min_trades_ok", True),
    ]:
        failed = folds_df.loc[folds_df[col].astype(bool) != good, "fold_id"].tolist()
        if failed:
            fails.append(f"- **{label}:** fold(s) {', '.join(map(str, failed))}")
    oos_neg = folds_df.loc[folds_df["oos_net_pnl"] <= 0, "fold_id"].tolist()
    if oos_neg:
        fails.append(f"- **OOS unprofitable:** fold(s) {', '.join(map(str, oos_neg))}")
    if fails:
        st.caption("Guardrail failures by fold:")
        st.markdown("\n".join(fails))
    else:
        st.caption("✓ All folds passed every guardrail.")


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

        # ── Run button ────────────────────────────────────────────────────────
        st.divider()
        run_id_input = st.text_input("Run ID (leave blank to auto-generate)", value="", key="wfa_run_id_input")
        notes_input  = st.text_input("Notes (optional)", value="", key="wfa_notes")

        run_btn = st.button("▶ Run WFA", type="primary", key="wfa_run_btn",
                            disabled=signals_filtered.empty)

        if run_btn and not signals_filtered.empty:
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
        with st.expander("🔒 Kaufman / Pardo Guardrails", expanded=True):
            report = guardrail_report(folds_df)
            _guardrail_badges(report)
            _guardrail_breakdown(folds_df)

        # ── OOS equity curve ──────────────────────────────────────────────────
        with st.expander("📈 Combined OOS Equity Curve", expanded=True):
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
        with st.expander("📋 Fold Summary Table", expanded=True):
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
                mean_wfe   = folds_df["wfe"].mean() * 100
                wwfe       = _windsorized_mean_wfe(folds_df["wfe"]) * 100

                d1, d2, d3 = st.columns(3)
                d1.metric("Mean WFE", _fmt(mean_wfe, ".1f") + "%",
                          help=_METRIC_HELP["wfe"])
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

            with dc1:
                st.markdown("**IS Period**")
                st.caption(f"{fold_row['is_start']} → {fold_row['is_end']}")
                is_metrics = {
                    "Trades": fold_row["is_n_trades"],
                    "Net PnL": f"${fold_row['is_net_pnl']:,.0f}",
                    "Win%": f"{fold_row['is_win_pct']:.1f}%",
                    "PF": f"{fold_row['is_pf']:.2f}",
                    "PROM": f"{fold_row['is_prom']:.2f}",
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
                    "PROM": f"{fold_row['oos_prom']:.2f}",
                    "PnL/DD": f"{fold_row['oos_pnl_dd']:.2f}",
                    "Max DD": f"${fold_row['oos_max_dd']:,.0f}",
                    "WFE": f"{fold_row['wfe']*100:.1f}%",
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
            mg1, mg2, mg3 = st.columns(3)
            is_grid  = mg1.multiselect("IS windows (months)", [6, 9, 12, 18, 24],
                                       default=[6, 12, 18, 24], key="wfa_map_is")
            oos_grid = mg2.multiselect("OOS windows (months)", [1, 2, 3, 4, 6],
                                       default=[1, 3, 6], key="wfa_map_oos")
            metric_lbl = mg3.selectbox("Cell metric", ["Mean WFE %", "Total OOS PnL",
                                                       "Mean OOS PROM", "% OOS folds profitable"],
                                       key="wfa_map_metric")
            _metric_col = {"Mean WFE %": "mean_wfe", "Total OOS PnL": "total_oos_pnl",
                           "Mean OOS PROM": "mean_oos_prom", "% OOS folds profitable": "pct_oos_prof"}[metric_lbl]

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
                st.session_state["wfa_map_df"]     = grid_df
                st.session_state["wfa_map_metric_col"] = _metric_col
                st.session_state["wfa_map_metric_lbl"] = metric_lbl

            grid_df = st.session_state.get("wfa_map_df")
            if grid_df is not None and not grid_df.empty:
                _mc  = st.session_state.get("wfa_map_metric_col", _metric_col)
                _ml  = st.session_state.get("wfa_map_metric_lbl", metric_lbl)
                piv  = grid_df.pivot(index="is_months", columns="oos_months", values=_mc)
                nfld = grid_df.pivot(index="is_months", columns="oos_months", values="n_folds")
                cscale = "RdYlGn" if _mc != "total_oos_pnl" else "RdYlGn"
                fig = go.Figure(go.Heatmap(
                    z=piv.values,
                    x=[f"{c}m" for c in piv.columns], y=[f"{r}m" for r in piv.index],
                    text=nfld.values, texttemplate="%{z:.1f}<br>(%{text} folds)",
                    colorscale=cscale, colorbar=dict(title=_ml),
                    hovertemplate="IS=%{y} · OOS=%{x}<br>" + _ml + "=%{z:.2f}<br>folds=%{text}<extra></extra>",
                ))
                _dark_layout(fig, f"Window-Anchor Map — {_ml}", 420)
                fig.update_xaxes(title="OOS window")
                fig.update_yaxes(title="IS window")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Each cell label: metric value and (fold count). Few folds = low confidence — "
                           "large IS + large OOS leaves fewer rolling windows in a 5-yr dataset.")
