"""ui_controls.py — the "🎛️ Master" tab: a central visibility control center.

Lets the user show/hide whole tabs (via an on/off switch) and individual
top-level expanders inside each tab (via checkboxes), all from one place.

Design notes / Streamlit constraints
------------------------------------
* `st.tabs` always renders every tab button — a tab can't be "collapsed". The
  only way to hide a tab is to omit it from the label list passed to
  `st.tabs([...])`. So `app.py` builds that list from `tab_visible()`.
* You can't put a widget inside an expander header, so each Master row is laid
  out as ``[toggle] [expander]`` via columns — the toggle stays visible while
  the row's expander is collapsed.
* `controlled_expander()` is a drop-in for `st.expander`. When a panel is hidden
  it renders the body into a throwaway slot and clears it, so call sites only
  need a one-line swap (no body re-indent). Tradeoff: a hidden panel's body
  still *executes* (just isn't shown) — acceptable for a declutter feature.

State is keyed in ``st.session_state`` (``ui_tab_<k>`` / ``ui_exp_<slug>``),
defaults to visible, and is persisted to ``saved_signals/ui_visibility.json``.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import streamlit as st

_STATE_PATH = Path(__file__).parent / "saved_signals" / "ui_visibility.json"

# ── Tab registry ────────────────────────────────────────────────────────────
# Order here drives the tab bar. "master" is always first and never hideable.
TAB_ORDER = [
    "master", "massive", "data", "bar_analysis", "wfa", "bar_viewer",
    "chart", "portfolio", "extras", "prop", "auction", "erc", "qs",
]

TAB_LABELS = {
    "master":       "🎛️ Master",
    "massive":      "📂 Massive",
    "data":         "🗂️ Data",
    "bar_analysis": "📈 Bar Analysis",
    "wfa":          "🔄 WFA",
    "bar_viewer":   "📊 Bar Viewer",
    "chart":        "📈 Chart",
    "portfolio":    "📊 Portfolio",
    "extras":       "🧩 Extras",
    "prop":         "🏢 Prop Sim",
    "auction":      "🏛️ Auction",
    "erc":          "🔬 ER10 Look-ahead",
    "qs":           "🎯 QS Breakouts",
}

# ── Expander catalog ──────────────────────────────────────────────────────────
# {tab_key: [(exp_slug, display_label, help_text), ...]}  — only the TOP-LEVEL
# expanders visible in each tab; nested sub-expanders are intentionally omitted.
EXPANDER_CATALOG: dict[str, list[tuple[str, str, str]]] = {
    "data": [
        ("data_bartable", "5-Minute Bar Table", "Raw 5-minute OHLCV table for the loaded session data."),
        ("data_excluded", "Manually Excluded Dates", "Dates you've manually excluded from all analysis."),
    ],
    "bar_analysis": [
        ("ba_signals_mc",       "MC Signals (upload)",       "Upload / auto-load the MC signal set (.txt/.csv)."),
        ("ba_signals_revft",    "RevFTSignals (upload)",     "Upload / auto-load the RevFT signal set."),
        ("ba_zlo",              "ZLO Overlay",               "Optional ZeroLag oscillator overlay export (NT)."),
        ("ba_alwaysin",         "Always In State",           "Optional NT AlwaysIn flip-state overlay."),
        ("ba_filters",          "Filters",                   "Date / session / setup filters applied to the signal set."),
        ("ba_signals_panel",    "Signals",                   "Active signal-set summary and selection."),
        ("ba_trading_params",   "Trading Parameters",        "Stop / target / scale-in parameters for the backtest."),
        ("ba_exec_model",       "Execution model (ESA)",     "Calc delay / wire / entry-fill execution model preset."),
        ("ba_quick_view",       "Quick View",                "Headline performance metrics."),
        ("ba_exp_stability",    "Expectancy Stability (R)",  "Rolling expectancy stability over time."),
        ("ba_detail",           "Detail",                    "Detailed performance breakdown."),
        ("ba_exec_audit",       "Execution Audit",           "Verify simulated fills against tick data."),
        ("ba_assumption_ledger","Assumption Ledger",         "Frictionless → net cost assumption ledger."),
        ("ba_esa",              "Execution Sensitivity (ESA)","How much edge survives realistic fills/slippage."),
        ("ba_edge_analysis",    "Edge Analysis",             "Edge decomposition diagnostics."),
        ("ba_daily_chart",      "Daily Chart",               "Per-day price chart with trades overlaid."),
        ("ba_mismatch",         "Bar Data Mismatch Analysis","SC vs NT bar-data mismatch diagnostics."),
        ("ba_stop_sweep",       "Stop Multiplier Sweep",     "Sweep the stop multiplier."),
        ("ba_stop_target_sweep","2-D Stop × Target Sweep",   "Joint stop × target grid sweep."),
        ("ba_monthly",          "Monthly Breakdown",         "Performance by month."),
        ("ba_setup_analysis",   "Setup Analysis",            "Per-setup performance breakdown."),
        ("ba_tod_dow",          "Time-of-Day / Day-of-Week", "Performance by time-of-day and weekday."),
        ("ba_regime_exp",       "Regime / Indicator Expectancy","Expectancy by regime / indicator bucket."),
        ("ba_entry_zoom",       "Entry Zoom",                "Tick-level view around trade entry."),
    ],
    "wfa": [
        ("wfa_regime",          "Regime Filter",             "Optional multi-slice regime filter (off by default)."),
        ("wfa_compare",         "Compare Two Runs",          "Side-by-side OOS metrics of two persisted runs."),
        ("wfa_guardrails",      "Kaufman / Pardo Guardrails","Overfitting guardrail summary."),
        ("wfa_oos_equity",      "Combined OOS Equity Curve", "Stitched out-of-sample equity curve."),
        ("wfa_fold_summary",    "Fold Summary Table",        "Per-fold IS/OOS summary table."),
        ("wfa_per_fold_charts", "Per-Fold Charts",           "Per-fold equity / metric charts."),
        ("wfa_oos_dist",        "OOS Trade Distribution",    "Distribution of OOS trade outcomes."),
        ("wfa_friction",        "Friction & Robustness",     "Friction and robustness diagnostics."),
        ("wfa_glossary",        "Metric Glossary",           "Definitions of the WFA metrics."),
        ("wfa_drilldown",       "Per-Fold Drill-Down",       "Inspect a single fold's IS/OOS trades."),
        ("wfa_delete",          "Delete Run",                "Delete a persisted WFA run."),
    ],
    "portfolio": [
        ("pf_quick",            "Quick View",                "Headline portfolio metrics."),
        ("pf_detail",           "Detail",                    "Detailed portfolio breakdown."),
        ("pf_global",           "Global Settings",           "Account-level / global portfolio settings."),
        ("pf_setup_params",     "Setup Parameters",          "Per-setup 2-leg scale-in parameters."),
        ("pf_sweep",            "Per-Setup Sweep",           "Parameter sweep for an individual setup."),
        ("pf_equity",           "Equity Curves",             "Combined and per-setup equity curves."),
        ("pf_setup_breakdown",  "Per-Setup Breakdown",       "Performance broken out by setup."),
        ("pf_drawdown",         "Drawdown by Setup",         "Drawdown attribution by setup."),
        ("pf_save",             "Save This Run",             "Persist the current portfolio run."),
    ],
    "prop": [
        ("prop_payouts",        "Payouts, Costs & Conservatism","Payout / cost / conservatism assumptions."),
        ("prop_quick",          "Quick View",                "Headline prop-account metrics."),
        ("prop_metrics",        "Prop Metrics",              "Prop-firm-specific metrics."),
        ("prop_detail",         "Detail",                    "Detailed prop breakdown."),
        ("prop_monthly",        "Monthly Breakdown",         "Prop performance by month."),
        ("prop_daily",          "Daily Detail",              "Per-day prop detail table."),
        ("prop_trades",         "Trade Detail",              "Per-trade prop detail table."),
    ],
    "extras": [
        ("ex_daily",            "Daily P&L Detail",          "Per-day P&L detail table."),
        ("ex_trades",           "Per-Trade Detail",          "Per-trade detail with scaling."),
    ],
    "qs": [
        ("qs_config",           "Detection & trade config",  "QS PaintBar detection + trade-definition controls."),
        ("qs_exec",             "Execution (costs / BE)",    "Commission, slippage, breakeven-stop trigger."),
        ("qs_breakdowns",       "Period breakdowns",         "Year / Quarter / Month / Week metric tables."),
        ("qs_export",           "Export trades (CSV)",       "Download the filled-trade results table."),
    ],
    "auction": [
        ("auc_daytype",         "Day-Type Distribution",     "Distribution of Dalton day types."),
        ("auc_transition",      "Day-Type Transition",       "Yesterday → today day-type transition matrix."),
        ("auc_gap",             "Gap Behavior",              "Gap bias base rates by size & direction."),
        ("auc_features",        "Per-Session Features (raw)","Raw per-session auction feature table."),
    ],
    "massive": [
        ("mas_roll",            "Roll Schedule & Downloads", "Contract roll schedule and downloads."),
        ("mas_nt_files",        "NT Import Files",           "NinjaTrader import files ready to use."),
        ("mas_series_vs_nt",    "Continuous Series vs NT",   "Continuous series compared to NT @ES."),
        ("mas_tick_series",     "Continuous Tick Series",    "Cached continuous tick series."),
        ("mas_config",          "Config",                    "Massive pipeline configuration."),
    ],
}


# ── Persistence ──────────────────────────────────────────────────────────────
def _all_exp_slugs() -> list[str]:
    return [slug for items in EXPANDER_CATALOG.values() for slug, _, _ in items]


def load_state() -> None:
    """Seed session_state from disk once per session (defaults to visible)."""
    if st.session_state.get("ui_loaded"):
        return
    data = {}
    try:
        if _STATE_PATH.exists():
            data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    tabs = data.get("tabs", {})
    exps = data.get("exps", {})
    for k in TAB_ORDER:
        if k == "master":
            continue
        st.session_state.setdefault(f"ui_tab_{k}", bool(tabs.get(k, True)))
    for slug in _all_exp_slugs():
        st.session_state.setdefault(f"ui_exp_{slug}", bool(exps.get(slug, True)))
    st.session_state.setdefault("ui_profiles", data.get("profiles", {}))
    st.session_state["ui_loaded"] = True


def save_state() -> None:
    tabs = {k: bool(st.session_state.get(f"ui_tab_{k}", True))
            for k in TAB_ORDER if k != "master"}
    exps = {slug: bool(st.session_state.get(f"ui_exp_{slug}", True))
            for slug in _all_exp_slugs()}
    payload = {"tabs": tabs, "exps": exps,
               "profiles": st.session_state.get("ui_profiles", {})}
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


# ── Visibility readers ────────────────────────────────────────────────────────
def tab_visible(tab_key: str) -> bool:
    if tab_key == "master":
        return True
    return bool(st.session_state.get(f"ui_tab_{tab_key}", True))


def expander_visible(exp_slug: str) -> bool:
    return bool(st.session_state.get(f"ui_exp_{exp_slug}", True))


@contextmanager
def controlled_expander(exp_slug: str, label: str, **kwargs):
    """Drop-in for ``st.expander`` that honors the Master-tab visibility toggle.

    When hidden, the body is rendered into a throwaway slot and immediately
    cleared, so it never shows but call sites stay one-liners.
    """
    if expander_visible(exp_slug):
        with st.expander(label, **kwargs) as e:
            yield e
    else:
        ph = st.empty()
        with ph.container():
            yield None
        ph.empty()


# convenience alias matching `st.expander(` call shape after the slug
expander = controlled_expander


@contextmanager
def tab_ctx(tab_map: dict, tab_key: str):
    """Context for a tab body. If the tab is visible, yields its real tab
    container; if hidden, yields a throwaway container that is cleared after —
    so the body still runs (keeping cross-tab session_state consistent) but
    renders nowhere. Lets ``app.py`` swap ``with tabX:`` → ``with tab_ctx(...)``
    with no body re-indentation."""
    obj = tab_map.get(tab_key)
    if obj is not None:
        with obj:
            yield obj
    else:
        ph = st.empty()
        with ph.container():
            yield None
        ph.empty()


# ── Master tab UI ──────────────────────────────────────────────────────────────
def _set_all_exps(value: bool) -> None:
    for slug in _all_exp_slugs():
        st.session_state[f"ui_exp_{slug}"] = value


def _apply_profile(prof: dict) -> None:
    for k, v in prof.get("tabs", {}).items():
        st.session_state[f"ui_tab_{k}"] = bool(v)
    for slug, v in prof.get("exps", {}).items():
        st.session_state[f"ui_exp_{slug}"] = bool(v)


def render_master_tab() -> None:
    st.subheader("🎛️ Master — Tab & Panel Visibility")
    st.caption(
        "Hide clutter you're not using. Each tab has an **on/off switch** "
        "(turn it off to remove the tab entirely) and, inside its row, "
        "**checkboxes** for the panels in that tab. Hover the ⓘ on any checkbox "
        "for what it does. Everything is on by default and your choices persist."
    )

    # ── hidden-count badge ──────────────────────────────────────────────────
    n_tabs_hidden = sum(1 for k in TAB_ORDER if k != "master" and not tab_visible(k))
    n_exps_hidden = sum(1 for slug in _all_exp_slugs() if not expander_visible(slug))
    if n_tabs_hidden or n_exps_hidden:
        st.info(f"Currently hidden: **{n_tabs_hidden}** tab(s), **{n_exps_hidden}** panel(s).")
    else:
        st.success("Everything is visible.")

    # ── bulk actions ────────────────────────────────────────────────────────
    b1, b2, b3, b4 = st.columns(4)
    if b1.button("✅ Show all panels", use_container_width=True):
        _set_all_exps(True); save_state(); st.rerun()
    if b2.button("◻ Hide all panels", use_container_width=True):
        _set_all_exps(False); save_state(); st.rerun()
    if b3.button("↺ Reset to defaults", use_container_width=True,
                 help="Show every tab and every panel."):
        for k in TAB_ORDER:
            if k != "master":
                st.session_state[f"ui_tab_{k}"] = True
        _set_all_exps(True); save_state(); st.rerun()
    show_empty = b4.toggle("Show empty tabs", value=True, key="ui_show_empty",
                           help="Also list tabs that have no controllable panels.")

    # ── presets / profiles ───────────────────────────────────────────────────
    profiles: dict = st.session_state.get("ui_profiles", {})
    with st.expander("💾 Layout presets", expanded=False):
        st.caption("Save the current show/hide layout under a name, then re-apply it later.")
        pc1, pc2 = st.columns([3, 1])
        new_name = pc1.text_input("Preset name", key="ui_prof_name",
                                  placeholder="e.g. Research / Execution audit / Minimal")
        if pc2.button("Save preset", use_container_width=True) and new_name.strip():
            profiles[new_name.strip()] = {
                "tabs": {k: tab_visible(k) for k in TAB_ORDER if k != "master"},
                "exps": {slug: expander_visible(slug) for slug in _all_exp_slugs()},
            }
            st.session_state["ui_profiles"] = profiles
            save_state(); st.rerun()
        if profiles:
            ac1, ac2, ac3 = st.columns([3, 1, 1])
            sel = ac1.selectbox("Saved presets", sorted(profiles), key="ui_prof_sel")
            if ac2.button("Apply", use_container_width=True):
                _apply_profile(profiles[sel]); save_state(); st.rerun()
            if ac3.button("Delete", use_container_width=True):
                profiles.pop(sel, None)
                st.session_state["ui_profiles"] = profiles
                save_state(); st.rerun()

    # ── search filter ─────────────────────────────────────────────────────────
    query = st.text_input("🔎 Filter panels", key="ui_search",
                          placeholder="Type to filter panels by name…").strip().lower()

    st.divider()

    # ── per-tab rows ───────────────────────────────────────────────────────────
    for k in TAB_ORDER:
        if k == "master":
            continue
        items = EXPANDER_CATALOG.get(k, [])
        if query:
            items = [it for it in items if query in it[1].lower()]
            if not items:
                continue  # hide whole row when nothing matches the filter
        elif not items and not show_empty:
            continue

        c1, c2 = st.columns([1, 9])
        with c1:
            # No value= : the key is seeded in session_state by load_state(),
            # so the widget reads/writes that directly (avoids the Streamlit
            # "value set via both default and Session State" warning).
            on = st.toggle(TAB_LABELS[k], key=f"ui_tab_{k}",
                           label_visibility="collapsed",
                           help=f"Show/hide the {TAB_LABELS[k]} tab")
        with c2:
            dot = "🟢" if on else "⚪"
            with st.expander(f"{dot} {TAB_LABELS[k]}", expanded=bool(query)):
                if not items:
                    st.caption("No controllable panels in this tab.")
                for slug, disp, helptext in items:
                    mark = "✅" if expander_visible(slug) else "◻"
                    st.checkbox(f"{mark} {disp}", key=f"ui_exp_{slug}", help=helptext)

    # The keyed widgets above mutate session_state directly, so persist the
    # current state on every render (this tab's body runs on every script run).
    save_state()
