"""ER10 look-ahead comparison tab.

Runs the SAME single-leg simulation twice and shows every metric side by side:

  • Current  — ER10 gate uses ER_intra_2 as the live pipeline merges it
               (merge_asof backward on sig_dt → the bar labeled sig_dt, which is
               the ENTRY bar; its close isn't known until sig_dt + 1 bar).
  • Causal   — ER10 gate uses ER_intra_2 of the actual SIGNAL bar (one bar
               earlier), i.e. the value fully known at the moment the signal fires.

This is additive/diagnostic only — it imports the production engine functions and
reuses the tick/bar artifacts AND the resolved ESA execution config (`ba_sim_params`)
that the Bar Analysis tab publishes to session_state. It does NOT modify any existing
code path or the live ER10 behavior; the only knob is the ER10 gate being tested.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import indicators as ind
from simulation_engine import simulate_trades, compute_summary

GATE_DEFAULT = 0.30


# ── ER10 tagging: current (look-ahead) vs causal ─────────────────────────────
def _er10_both_modes(signals: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Return signals (sorted) with two columns: ER10_current, ER10_causal.

    ER10_current == the PRE-FIX look-ahead value (raw backward merge → entry bar).
                    The live pipeline no longer uses this; kept here to show the
                    historical impact of the bug.
    ER10_causal  == the ER of the signal's OWN bar (what tag_signals now uses).
    """
    b = bars.copy()
    b["DateTime"] = b["DateTime"].astype("datetime64[ns]")
    b = b.sort_values("DateTime").reset_index(drop=True)

    eri = ind.bar_kaufman_er(b, spans=(2,)).sort_values("DateTime").reset_index(drop=True)
    eri = eri[["DateTime", "ER_intra_2"]].rename(columns={"ER_intra_2": "ER10_current"})

    eri_causal = eri.copy()
    eri_causal["ER10_causal"] = eri_causal["ER10_current"].shift(1)
    eri_causal = eri_causal[["DateTime", "ER10_causal"]]

    s = signals.copy()
    s["DateTime"] = s["DateTime"].astype("datetime64[ns]")
    s = s.sort_values("DateTime")
    s = pd.merge_asof(s, eri, on="DateTime", direction="backward")
    s = pd.merge_asof(s, eri_causal, on="DateTime", direction="backward")
    return s


def _apply_gate(signals: pd.DataFrame, er_col: str, gate: float) -> pd.DataFrame:
    """Mark FilterStatus per the ER10 gate. NaN fails (matches the live gate)."""
    out = signals.copy()
    out["FilterStatus"] = "ok"
    bad = ~(out[er_col] >= gate)   # NaN -> True -> excluded
    out.loc[bad, "FilterStatus"] = "low_er10"
    return out


# ── Metric presentation ──────────────────────────────────────────────────────
# (key, label, formatter, higher_is_better) — None h_i_b = neutral (no delta arrow)
_FMT_INT   = lambda v: f"{v:,.0f}"
_FMT_USD   = lambda v: f"${v:,.0f}"
_FMT_USD2  = lambda v: f"${v:,.2f}"
_FMT_PCT   = lambda v: f"{v:.1f}%"
_FMT_2     = lambda v: f"{v:.2f}"
_FMT_3     = lambda v: f"{v:.3f}"

_METRICS = [
    ("n_total",        "Signals (total)",        _FMT_INT,  None),
    ("n_filtered",     "Filtered out (gate)",    _FMT_INT,  None),
    ("n_trades",       "Trades (filled)",        _FMT_INT,  None),
    ("n_wins",         "Wins",                   _FMT_INT,  True),
    ("n_stop",         "Stops",                  _FMT_INT,  False),
    ("win_pct",        "Win %",                  _FMT_PCT,  True),
    ("net_total",      "Net P&L",                _FMT_USD,  True),
    ("exp_dollar",     "Expectancy $",           _FMT_USD2, True),
    ("exp_r",          "Expectancy R",           _FMT_3,    True),
    ("pf",             "Profit Factor",          _FMT_2,    True),
    ("sqn",            "SQN",                    _FMT_2,    True),
    ("prom",           "PROM",                   _FMT_2,    True),
    ("prom_tgt",       "PROM (target-hit)",      _FMT_2,    True),
    ("max_dd",         "Max Drawdown",           _FMT_USD,  True),   # less negative is better
    ("pnl_dd",         "Net / |MaxDD|",          _FMT_2,    True),
    ("avg_win",        "Avg Win $",              _FMT_USD2, True),
    ("avg_loss",       "Avg Loss $",             _FMT_USD2, None),
    ("wl_ratio",       "Win/Loss ratio",         _FMT_2,    True),
    ("avg_mae_R",      "Avg MAE (R)",            _FMT_3,    None),
    ("avg_mfe_R",      "Avg MFE (R)",            _FMT_3,    None),
    ("sharpe",         "Sharpe (notional)",      _FMT_2,    True),
    ("cagr",           "CAGR (notional)",        _FMT_PCT,  True),
    ("trading_days",   "Trading days",           _FMT_INT,  None),
    ("commission_total","Commission $",          _FMT_USD,  None),
    ("slippage_total", "Slippage $",             _FMT_USD,  None),
]


def _fmt(v, formatter):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else "∞"
    try:
        return formatter(v)
    except (TypeError, ValueError):
        return str(v)


def _build_table(cur: dict, cau: dict) -> pd.DataFrame:
    rows = []
    for key, label, fmt, hib in _METRICS:
        cv = cur.get(key)
        kv = cau.get(key)
        # delta + direction arrow (causal minus current)
        if (isinstance(cv, (int, float)) and isinstance(kv, (int, float))
                and not any(isinstance(x, float) and (np.isnan(x) or np.isinf(x)) for x in (cv, kv))):
            d = kv - cv
            if hib is None or d == 0:
                arrow = ""
            elif (d > 0) == hib:
                arrow = " ▲"   # causal is better
            else:
                arrow = " ▼"   # causal is worse
            dstr = f"{_fmt(d, fmt)}{arrow}" if d != 0 else "0"
        else:
            dstr = "—"
        rows.append({
            "Metric": label,
            "Pre-fix (look-ahead)": _fmt(cv, fmt),
            "Causal (now live)": _fmt(kv, fmt),
            "Δ (causal − pre-fix)": dstr,
        })
    return pd.DataFrame(rows)


# ── Main tab ─────────────────────────────────────────────────────────────────
def show_er_lookahead_tab():
    st.header("🔬 ER10 Look-ahead Comparison")
    st.success(
        "✅ The look-ahead bug is **fixed** in the live pipeline — `tag_signals` now uses the "
        "signal bar's own ER (causal). This tab is kept as a **historical-impact / regression "
        "view**: it runs the same sim twice with your Bar Analysis ESA settings — once with the "
        "old pre-fix look-ahead ER10 (entry bar's close = future data), once with the causal "
        "value the pipeline now uses.",
        icon="✅",
    )

    signals_raw = st.session_state.get("ba_signals")
    bars        = st.session_state.get("mas_continuous")
    ticks_by_date = st.session_state.get("pf_ticks_by_date")
    bars_by_date  = st.session_state.get("pf_bars_by_date")

    if signals_raw is None or signals_raw.empty:
        st.info("Upload a signals file in the **🗂️ Data → 📊 MC Signals** panel first.")
        return
    if bars is None or bars.empty:
        st.info("Build the Massive continuous series first (📂 Massive tab).")
        return
    if not ticks_by_date or not bars_by_date:
        st.warning(
            "Tick/bar simulation cache is empty. Open the **📈 Bar Analysis** tab once "
            "(it builds the tick cache for your signal dates), then come back here."
        )
        return

    params = st.session_state.get("ba_sim_params")
    if not params:
        st.warning(
            "No execution config found. Open the **📈 Bar Analysis** tab once (with signals "
            "loaded) so it publishes its ESA settings, then come back here."
        )
        return

    try:
        from data_loader import filter_excluded_dates
        signals_raw = filter_excluded_dates(signals_raw)
        bars = filter_excluded_dates(bars.drop(columns=["Contract"], errors="ignore"))
    except Exception:
        bars = bars.drop(columns=["Contract"], errors="ignore")

    # ── Inherited ESA configuration (read-only — set it in Bar Analysis) ──────
    st.subheader("Execution configuration (inherited from Bar Analysis)")
    st.caption(
        "This runs the **exact ESA settings** you configured on the 📈 Bar Analysis tab — "
        "preset, entry model, slippage, delays and leg structure. Change them there and they "
        "update here automatically. The only knob below is the ER10 gate being tested."
    )
    _disp = params.get("display", {})
    if _disp:
        _items = list(_disp.items())
        _cols = st.columns(4)
        for _i, (_k, _v) in enumerate(_items):
            _cols[_i % 4].metric(_k, _v)

    gate = st.number_input(
        "ER10 gate ≥ (tested in both modes)", 0.0, 1.0,
        float(params.get("er10_min", GATE_DEFAULT)), 0.02, "%.2f", key="erc_gate",
        help="Defaults to the ER10 gate set in Bar Analysis. The comparison applies this same "
             "threshold to the look-ahead ER10 and the causal ER10.")

    run = st.button("▶ Run comparison", type="primary", key="erc_run")

    sim_kwargs = params["sim_kwargs"]
    summary_kwargs = params["summary_kwargs"]
    commission = params["commission"]

    fp = hash((len(signals_raw), int(signals_raw["SignalNum"].sum()), len(bars),
               round(gate, 4), repr(sorted(sim_kwargs.items())),
               repr(sorted(summary_kwargs.items())), round(commission, 4)))
    have = st.session_state.get("erc_result_fp") == fp and st.session_state.get("erc_result") is not None

    if not run and not have:
        st.info(f"**{len(signals_raw)} signals** loaded — click **▶ Run comparison**.")
        return

    if run or not have:
        with st.spinner("Tagging ER10 (both modes) and running two sims…"):
            tagged = _er10_both_modes(signals_raw, bars)

            sim_kw = dict(ticks_by_date=ticks_by_date, bars_by_date=bars_by_date, **sim_kwargs)

            res_cur = simulate_trades(_apply_gate(tagged, "ER10_current", gate), **sim_kw)
            res_cau = simulate_trades(_apply_gate(tagged, "ER10_causal", gate), **sim_kw)
            sum_cur = compute_summary(res_cur, commission, **summary_kwargs)
            sum_cau = compute_summary(res_cau, commission, **summary_kwargs)

            # Gate-flip diagnostics on the population with a defined causal value
            valid = tagged.dropna(subset=["ER10_causal"]).copy()
            cur_pass = valid["ER10_current"] >= gate
            cau_pass = valid["ER10_causal"] >= gate
            diag = {
                "n": int(len(valid)),
                "pass_cur": int(cur_pass.sum()),
                "pass_cau": int(cau_pass.sum()),
                "flips": int((cur_pass != cau_pass).sum()),
                "phantom_pass": int((cur_pass & ~cau_pass).sum()),
                "phantom_block": int((~cur_pass & cau_pass).sum()),
                "er_differs": int((~np.isclose(valid["ER10_current"].fillna(-9),
                                               valid["ER10_causal"].fillna(-9))).sum()),
            }

        st.session_state["erc_result"] = (sum_cur, sum_cau, diag)
        st.session_state["erc_result_fp"] = fp

    sum_cur, sum_cau, diag = st.session_state["erc_result"]

    if not sum_cur or not sum_cau:
        st.error("One of the runs produced no filled trades — loosen the gate or check the data.")
        return

    # ── Gate-flip diagnostics ────────────────────────────────────────────────
    st.subheader("Gate decision impact")
    d1, d2, d3, d4 = st.columns(4)
    pct = lambda x: f"{x/diag['n']*100:.1f}%" if diag["n"] else "—"
    d1.metric("Gate decisions FLIPPED", f"{diag['flips']:,}", pct(diag["flips"]))
    d2.metric("ER10 value differs", f"{diag['er_differs']:,}", pct(diag["er_differs"]))
    d3.metric("Phantom PASS (chop snuck in)", f"{diag['phantom_pass']:,}",
              "current trades it, causal skips", delta_color="inverse")
    d4.metric("Phantom BLOCK (good signal tossed)", f"{diag['phantom_block']:,}",
              "current skips, causal trades", delta_color="inverse")
    st.caption(
        f"Of **{diag['n']:,}** signals with a defined causal ER10: current gate passes "
        f"**{diag['pass_cur']:,}**, causal gate passes **{diag['pass_cau']:,}**. "
        "A flip means the look-ahead changed whether the signal was traded."
    )

    # ── Side-by-side metrics ─────────────────────────────────────────────────
    st.subheader("All metrics — Pre-fix (look-ahead) vs Causal (now live)")
    table = _build_table(sum_cur, sum_cau)
    st.dataframe(table, use_container_width=True, hide_index=True,
                 height=min(40 + 35 * len(table), 1000))

    # Headline deltas
    net_d = sum_cau.get("net_total", 0) - sum_cur.get("net_total", 0)
    exp_d = sum_cau.get("exp_dollar", 0) - sum_cur.get("exp_dollar", 0)
    st.caption(
        f"**Net P&L:** causal − pre-fix = **${net_d:,.0f}**  |  "
        f"**Expectancy/trade:** **${exp_d:,.2f}**.  "
        "Where pre-fix (look-ahead) was better than causal, the old ER10 gate was flattering "
        "results with data it couldn't have known — that inflation is now removed from the live pipeline."
    )
    st.caption(
        "▲ = causal is better on that metric, ▼ = causal is worse. Δ is causal − pre-fix."
    )
