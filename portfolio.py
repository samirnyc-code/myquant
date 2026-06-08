import json
import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

from bar_analysis import (
    simulate_trades,
    compute_summary,
    INSTRUMENTS,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_T_OPTS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
_T_LBLS = [f"{v:.2f}R" for v in _T_OPTS]

_PB_VALS = [0.0, -0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50, -2.0]
_PB_LBLS = ["None", "-0.25R", "-0.33R", "-0.50R", "-0.66R", "-0.75R",
            "-1.00R", "-1.25R", "-1.50R", "-2.00R"]

_SW_PB_LBLS = _PB_LBLS[1:]
_SW_PB_VALS = _PB_VALS[1:]

_COLORS = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
           "#1abc9c", "#e67e22", "#e91e63"]
_FILLS  = ["rgba(231,76,60,0.10)",  "rgba(52,152,219,0.10)", "rgba(46,204,113,0.10)",
           "rgba(243,156,18,0.10)", "rgba(155,89,182,0.10)", "rgba(26,188,156,0.10)",
           "rgba(230,126,34,0.10)", "rgba(233,30,99,0.10)"]

_DEFAULTS_FILE   = Path(__file__).parent / "pf_defaults.json"
_SAVED_RUNS_FILE = Path(__file__).parent / "pf_saved_runs.json"


# ── Color helpers ─────────────────────────────────────────────────────────────

def _cc_color(cc: str, cc_list: list) -> str:
    try:
        return _COLORS[cc_list.index(cc) % len(_COLORS)]
    except ValueError:
        return "#95a5a6"


def _cc_fill(cc: str, cc_list: list) -> str:
    try:
        return _FILLS[cc_list.index(cc) % len(_FILLS)]
    except ValueError:
        return "rgba(149,165,166,0.10)"


# ── Index helpers ─────────────────────────────────────────────────────────────

def _t_idx(val: float) -> int:
    try:
        return _T_OPTS.index(round(val, 2))
    except ValueError:
        return 2


def _pb_idx(val: float) -> int:
    try:
        return _PB_VALS.index(round(val, 2))
    except ValueError:
        return 3


def _t_range(min_lbl: str, max_lbl: str) -> list:
    i0, i1 = _T_LBLS.index(min_lbl), _T_LBLS.index(max_lbl)
    if i0 > i1:
        i0, i1 = i1, i0
    return _T_OPTS[i0: i1 + 1]


def _pb_range(sh_lbl: str, dp_lbl: str) -> list:
    i0, i1 = _SW_PB_LBLS.index(sh_lbl), _SW_PB_LBLS.index(dp_lbl)
    if i0 > i1:
        i0, i1 = i1, i0
    return _SW_PB_VALS[i0: i1 + 1]


# ── Persist helpers ───────────────────────────────────────────────────────────

def _load_defaults() -> dict:
    if _DEFAULTS_FILE.exists():
        try:
            return json.loads(_DEFAULTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_defaults(configs: dict):
    out = {}
    for cc, cfg in configs.items():
        out[cc] = {k: v for k, v in cfg.items()}
    _DEFAULTS_FILE.write_text(json.dumps(out, indent=2))


def _load_saved_runs() -> list:
    if _SAVED_RUNS_FILE.exists():
        try:
            return json.loads(_SAVED_RUNS_FILE.read_text())
        except Exception:
            pass
    return []


def _save_run(name: str, summary: dict, configs: dict, starting_cap: float,
              date_from, date_to):
    runs = _load_saved_runs()
    _dd  = abs(summary["max_dd"]) if summary["max_dd"] != 0 else None
    entry = {
        "name":       name,
        "timestamp":  datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date_from":  str(date_from),
        "date_to":    str(date_to),
        "net_pnl":    round(summary["net_total"], 0),
        "win_pct":    round(summary["win_pct"], 1),
        "pf":         round(min(summary["pf"], 99.0), 2),
        "pnl_dd":     round(summary["net_total"] / _dd, 2) if _dd else None,
        "max_dd":     round(summary["max_dd"], 0),
        "trades":     summary["n_trades"],
        "exp_r":      round(summary["exp_r"], 3),
        "return_pct": round(summary["net_total"] / starting_cap * 100, 1) if starting_cap > 0 else None,
        "starting_cap": starting_cap,
        "setups": {
            cc: {
                "t1": cfg.get("t1_r"), "pb": cfg.get("pb_r"),
                "t2": cfg.get("t2_r"),
                "c_t1": cfg.get("contracts_t1"), "c_t2": cfg.get("contracts_t2"),
            }
            for cc, cfg in configs.items() if cfg.get("enabled")
        },
    }
    runs.append(entry)
    _SAVED_RUNS_FILE.write_text(json.dumps(runs, indent=2))


# ── Config apply helper ───────────────────────────────────────────────────────
# T1/PB/T2 selectboxes use versioned keys (e.g. pf_t1_CC2_v3).
# Incrementing the version counter creates brand-new keys that don't exist in
# session state yet, so index= takes effect on the next render.
# This avoids both the "duplicate auto-ID" error (unique keys per CC) and the
# "cannot modify after instantiation" error (new version = new key = fresh init).

def _apply_to_config(cc: str, t1_raw: float, pb_raw: float, t2_raw: float):
    _sk = f"pf_cfg_{cc}"
    _cfg = dict(st.session_state.get(_sk, {}))
    _cfg["t1_idx"] = _t_idx(t1_raw)
    _cfg["pb_idx"] = _pb_idx(pb_raw)
    _cfg["t2_idx"] = _t_idx(t2_raw)
    st.session_state[_sk] = _cfg
    st.session_state["pf_cfg_ver"] = st.session_state.get("pf_cfg_ver", 0) + 1


def _flush_pending_cfg():
    pass  # no longer needed — kept for call-site compatibility


# ── Print CSS (injected once per render) ─────────────────────────────────────

_PRINT_CSS = """
<style>
@media print {
    /* Hide all Streamlit chrome */
    header[data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stSidebar"],
    [data-testid="stStatusWidget"],
    footer,
    .stButton,
    [data-testid="stFileUploadDropzone"] { display: none !important; }

    /* Expand every expander */
    details[data-testid="stExpander"] { display: block !important; }
    details[data-testid="stExpander"] > div,
    details[data-testid="stExpander"] > section { display: block !important; }

    /* Full-width layout */
    .block-container { max-width: 100% !important; padding: 0.5rem !important; }

    /* Plotly charts: force tall */
    .js-plotly-plot, .plotly, .plot-container {
        height: 580px !important;
        min-height: 580px !important;
    }
    .js-plotly-plot .svg-container { height: 580px !important; }

    @page { size: landscape; margin: 1.2cm; }
}
</style>
"""


# ── PDF export ────────────────────────────────────────────────────────────────

def _pdf_button(key: str):
    """Opens browser print dialog. Counter forces re-render on every click.

    Print behaviour:
    - Does NOT open or close any expanders — page prints exactly as it looks now.
    - The Equity Curves chart (already expanded) is enlarged to ~full page via
      Plotly.relayout() triggered by the browser's beforeprint event.
    - After printing, the chart is restored to its original height.
    """
    if st.button("📄 Export PDF", key=key, use_container_width=True,
                 help="Prints the current view as-is. "
                      "Close expanders you don't need first. "
                      "File goes to browser Downloads."):
        _n = st.session_state.get("_pdf_n", 0) + 1
        st.session_state["_pdf_n"] = _n
        components.html(
            f"""<script>
(function(){{
    var w = window.parent;
    var _equityPlot = null;
    var _origHeight = 420;

    // Find the Equity Curves plotly chart (inside the open <details> whose
    // summary contains "Equity Curves")
    function findEquityChart() {{
        var found = null;
        w.document.querySelectorAll('details').forEach(function(d) {{
            if (!d.open) return;
            var s = d.querySelector('summary');
            if (s && s.textContent.indexOf('Equity Curves') >= 0) {{
                found = d.querySelector('.js-plotly-plot');
            }}
        }});
        return found;
    }}

    function beforePrint() {{
        _equityPlot = findEquityChart();
        if (_equityPlot && w.Plotly) {{
            _origHeight = _equityPlot.clientHeight || 420;
            w.Plotly.relayout(_equityPlot, {{height: 680}});
        }}
    }}

    function afterPrint() {{
        if (_equityPlot && w.Plotly) {{
            w.Plotly.relayout(_equityPlot, {{height: _origHeight}});
        }}
    }}

    // matchMedia fires reliably in Chrome/Safari before the dialog opens
    var mql = w.matchMedia('print');
    mql.addEventListener('change', function(e) {{
        if (e.matches) {{ beforePrint(); }} else {{ afterPrint(); }}
    }});

    // onbeforeprint / onafterprint for Firefox + fallback
    w.addEventListener('beforeprint', beforePrint);
    w.addEventListener('afterprint',  afterPrint);

    setTimeout(function(){{ w.print(); }}, 150);
}})(); // {_n}
</script>""",
            height=0,
        )


# ── Summary strips ────────────────────────────────────────────────────────────

def _summary_strip(summary: dict, pnl_dd, pf_str, exp_r_help, starting_cap: float = 0.0):
    with st.expander("📋 Quick View", expanded=True):
        r1 = st.columns(6)
        r1[0].metric("Net PnL",  f"${summary['net_total']:,.0f}")
        r1[1].metric("Win %",    f"{summary['win_pct']:.1f}%",
                     help=f"W{summary['n_wins']} / L{summary['n_stop']} / BE{summary['n_sess']}")
        r1[2].metric("Exp R",    f"{summary['exp_r']:+.2f}", help=exp_r_help)
        r1[3].metric("PnL/DD",   f"{pnl_dd:.2f}" if pnl_dd is not None else "—")
        r1[4].metric("PF",       pf_str)
        r1[5].metric("Max DD",   f"${summary['max_dd']:,.0f}")

        r2 = st.columns(6)
        r2[0].metric("Trades",   f"{summary['n_trades']}")
        r2[1].metric("Avg Win",  f"${summary['avg_win']:+.0f}")
        r2[2].metric("Avg Loss", f"${summary['avg_loss']:+.0f}")
        r2[3].metric("Median W", f"${summary['median_win']:+.0f}")
        r2[4].metric("Median L", f"${summary['median_loss']:+.0f}")
        if starting_cap > 0:
            ret_pct = summary["net_total"] / starting_cap * 100
            r2[5].metric("Return %", f"{ret_pct:.1f}%")
        else:
            r2[5].metric("Days", f"{summary['trading_days']}")


def _detail_strip(summary: dict, pf_str, starting_cap: float = 0.0):
    with st.expander("📊 Detail", expanded=False):
        _actual_comm = summary["gross_total"] - summary["net_total"]
        _slip_usd    = summary.get("slippage_total", 0.0)
        _total_cost  = _slip_usd + _actual_comm
        _wl_str      = f"{summary['wl_ratio']:.2f}" if summary["wl_ratio"] < 99 else "∞"

        r1 = st.columns(6)
        r1[0].metric("Gross PnL",     f"${summary['gross_total']:,.0f}")
        r1[1].metric("Profit Factor", pf_str)
        r1[2].metric("W/L Ratio",     _wl_str)
        r1[3].metric("Exp $",         f"${summary['exp_dollar']:+.0f}")
        r1[4].metric("Std R",         f"{summary['r_std']:.3f}")
        r1[5].metric("Trading Days",  f"{summary['trading_days']}")

        r2 = st.columns(6)
        r2[0].metric("Slippage",    f"${_slip_usd:.0f}")
        r2[1].metric("Commission",  f"${_actual_comm:.0f}")
        r2[2].metric("Total Cost",  f"${_total_cost:.0f}")
        r2[3].metric("Max Risk $",  f"${summary['max_risk_dollar']:,.0f}")
        r2[4].metric("Avg Risk $",  f"${summary['avg_risk_dollar']:,.0f}")
        if starting_cap > 0:
            r2[5].metric("Capital", f"${starting_cap:,.0f}")
        else:
            r2[5].metric("Trades",  f"{summary['n_trades']}")


# ── Sweep helpers ─────────────────────────────────────────────────────────────

def _run_sweep_for_cc(cc_sig, ticks_by_date, bars_by_date,
                      t1_vals, pb_vals, t2_vals,
                      entry_slip, exit_slip, stop_offset,
                      tick_value, commission,
                      contracts_t1, contracts_t2,
                      min_trades: int) -> pd.DataFrame:
    rows = []
    for t1 in t1_vals:
        for pb in pb_vals:
            for t2 in t2_vals:
                res = simulate_trades(
                    cc_sig, ticks_by_date, t2,
                    entry_slip, exit_slip, stop_offset,
                    tick_value, contracts_t1, commission,
                    bars_by_date=bars_by_date,
                    multileg=True,
                    t1_r=t1, t1_action="exit",
                    contracts_t1=contracts_t1,
                    contracts_t2=contracts_t2,
                    ml_pb_r=pb,
                )
                s = compute_summary(res, commission,
                                    contracts=contracts_t1, is_multileg=True,
                                    contracts_t1=contracts_t1, contracts_t2=contracts_t2)
                if not s or s["n_trades"] < min_trades:
                    continue
                _dd  = abs(s["max_dd"]) if s["max_dd"] != 0 else None
                rows.append({
                    "t1_raw": t1, "pb_raw": pb, "t2_raw": t2,
                    "Trades":  s["n_trades"],
                    "Win %":   round(s["win_pct"], 1),
                    "PF":      round(min(s["pf"], 99.0), 2),
                    "Net PnL": round(s["net_total"], 0),
                    "PnL/DD":  round(s["net_total"] / _dd, 2) if _dd else np.nan,
                    "Exp $":   round(s["exp_dollar"], 1),
                })
    return pd.DataFrame(rows)


def _format_sweep_df(df: pd.DataFrame, rank_col: str) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.sort_values(rank_col, ascending=False).head(20).copy()
    out.insert(0, "T1", out["t1_raw"].apply(lambda x: f"{x:.2f}R"))
    out.insert(1, "PB", out["pb_raw"].apply(lambda x: f"{x:.2f}R"))
    out.insert(2, "T2", out["t2_raw"].apply(lambda x: f"{x:.2f}R"))
    out["Net PnL"] = out["Net PnL"].apply(lambda x: f"${x:,.0f}")
    out["Exp $"]   = out["Exp $"].apply(lambda x: f"${x:+.0f}")
    return out[["T1", "PB", "T2", "Trades", "Win %", "PF", "Net PnL", "PnL/DD", "Exp $"]]


# ── Main ──────────────────────────────────────────────────────────────────────

def show_portfolio():
    st.markdown(_PRINT_CSS, unsafe_allow_html=True)

    signals_raw   = st.session_state.get("ba_signals")
    ticks_by_date = st.session_state.get("pf_ticks_by_date", {})
    bars_by_date  = st.session_state.get("pf_bars_by_date",  {})

    if signals_raw is None or signals_raw.empty:
        st.info("Upload signals in the **📁 Upload Data** section of Bar Analysis first.")
        return
    if not ticks_by_date and not bars_by_date:
        st.info("Open the **📈 Bar Analysis** tab once to load price data, then return here.")
        return

    cc_types = sorted(signals_raw["SignalType"].unique())

    # ── Global settings ───────────────────────────────────────────────────────
    with st.expander("⚙️ Global Settings", expanded=False):
        g1, g2, g3, g4, g5, g6 = st.columns(6)
        instrument   = g1.selectbox("Instrument", list(INSTRUMENTS.keys()),
                                    index=0, key="pf_instrument")
        tick_value   = INSTRUMENTS[instrument]["tick_value"]
        def_comm     = INSTRUMENTS[instrument]["default_commission"]
        entry_slip   = g2.number_input("Entry Slip (ticks)", 0.0, 5.0,
                                       value=float(st.session_state.get("pf_entry_slip", 0.5)),
                                       step=0.5, key="pf_entry_slip")
        exit_slip    = g3.number_input("Exit Slip (ticks)",  0.0, 5.0,
                                       value=float(st.session_state.get("pf_exit_slip",  0.5)),
                                       step=0.5, key="pf_exit_slip")
        commission   = g4.number_input("Commission ($/contract)", 0.0, 20.0,
                                       value=float(st.session_state.get("pf_commission", def_comm)),
                                       step=0.5, key="pf_commission")
        stop_offset  = g5.number_input("Stop Offset (ticks)", 0, 10,
                                       value=int(st.session_state.get("pf_stop_offset", 0)),
                                       step=1, key="pf_stop_offset")
        starting_cap = g6.number_input("Starting Capital ($)", 0, 500_000,
                                       value=int(st.session_state.get("pf_starting_cap", 25_000)),
                                       step=5_000, key="pf_starting_cap")

    # ── Date range ────────────────────────────────────────────────────────────
    _sig_min = signals_raw["Date"].min()
    _sig_max = signals_raw["Date"].max()
    dc1, dc2, _, pdf_col = st.columns([3, 3, 4, 2])
    date_from = dc1.date_input("From", value=_sig_min, key="pf_date_from")
    date_to   = dc2.date_input("To",   value=_sig_max, key="pf_date_to")
    with pdf_col:
        _pdf_button("pf_pdf_btn")

    signals = signals_raw[
        (signals_raw["Date"] >= date_from) &
        (signals_raw["Date"] <= date_to)
    ].copy()

    # ── Per-setup 2-leg config ────────────────────────────────────────────────
    _flush_pending_cfg()
    _cfg_ver        = st.session_state.get("pf_cfg_ver", 0)
    _saved_defaults = _load_defaults()

    with st.expander("⚙️ Setup Parameters (2-Leg Scale-In)", expanded=True):
        hdr = st.columns([0.6, 1.2, 1.5, 2.5, 2.5, 1.5, 2.5, 1.2])
        for col, lbl in zip(hdr, ["Run", "Setup", "E1 Contr.", "T1", "PB", "E2 Contr.", "T2", "Sigs"]):
            col.markdown(f"<small>**{lbl}**</small>", unsafe_allow_html=True)

        configs = {}
        for cc in cc_types:
            n_sigs   = int((signals["SignalType"] == cc).sum())
            _sk      = f"pf_cfg_{cc}"
            # Build default — prefer saved file defaults, then hardcoded
            _file_def = _saved_defaults.get(cc, {})
            _default  = {
                "enabled": _file_def.get("enabled", cc != "CC1"),
                "c_t1":    _file_def.get("c_t1", 1),
                "t1_idx":  _file_def.get("t1_idx", _t_idx(1.00)),
                "pb_idx":  _file_def.get("pb_idx", _pb_idx(-0.50)),
                "c_t2":    _file_def.get("c_t2", 1),
                "t2_idx":  _file_def.get("t2_idx", _t_idx(2.00)),
            }
            _stored = st.session_state.get(_sk, {})
            if not all(k in _stored for k in _default):
                _stored = _default
                st.session_state[_sk] = _stored
            _cfg = _stored

            rc = st.columns([0.6, 1.2, 1.5, 2.5, 2.5, 1.5, 2.5, 1.2])
            enabled = rc[0].checkbox("", value=_cfg["enabled"],
                                     key=f"pf_en_{cc}", label_visibility="collapsed")
            rc[1].markdown(f"**{cc}**")
            c_t1    = rc[2].number_input("", 1, 10, value=int(_cfg["c_t1"]),
                                         key=f"pf_ct1_{cc}", label_visibility="collapsed",
                                         disabled=not enabled)
            t1_lbl  = rc[3].selectbox("", _T_LBLS, index=_cfg["t1_idx"],
                                       key=f"pf_t1_{cc}_v{_cfg_ver}",
                                       label_visibility="collapsed",
                                       disabled=not enabled)
            pb_lbl  = rc[4].selectbox("", _PB_LBLS, index=_cfg["pb_idx"],
                                       key=f"pf_pb_{cc}_v{_cfg_ver}",
                                       label_visibility="collapsed",
                                       disabled=not enabled)
            c_t2    = rc[5].number_input("", 1, 10, value=int(_cfg["c_t2"]),
                                         key=f"pf_ct2_{cc}", label_visibility="collapsed",
                                         disabled=not enabled)
            t2_lbl  = rc[6].selectbox("", _T_LBLS, index=_cfg["t2_idx"],
                                       key=f"pf_t2_{cc}_v{_cfg_ver}",
                                       label_visibility="collapsed",
                                       disabled=not enabled)
            rc[7].caption(f"{n_sigs}")

            st.session_state[_sk] = {
                "enabled": enabled,
                "c_t1":    c_t1,
                "t1_idx":  _T_LBLS.index(t1_lbl),
                "pb_idx":  _PB_LBLS.index(pb_lbl),
                "c_t2":    c_t2,
                "t2_idx":  _T_LBLS.index(t2_lbl),
            }
            configs[cc] = {
                "enabled":      enabled,
                "contracts_t1": c_t1,
                "t1_r":         _T_OPTS[_T_LBLS.index(t1_lbl)],
                "pb_r":         _PB_VALS[_PB_LBLS.index(pb_lbl)],
                "contracts_t2": c_t2,
                "t2_r":         _T_OPTS[_T_LBLS.index(t2_lbl)],
            }

        # Save as Defaults button
        st.markdown("")
        if st.button("💾 Save as Defaults", key="pf_save_defaults"):
            _save_defaults({cc: st.session_state[f"pf_cfg_{cc}"]
                            for cc in cc_types if f"pf_cfg_{cc}" in st.session_state})
            st.success("Saved as defaults — will load on next app start.")

    enabled_ccs = [cc for cc, cfg in configs.items() if cfg["enabled"]]

    # ── Per-Setup Sweep ───────────────────────────────────────────────────────
    with st.expander("🔍 Per-Setup Sweep", expanded=False):
        sw1, sw2, sw3, sw4 = st.columns(4)

        with sw1:
            st.caption("**T1 range**")
            _sw_t1_min = st.selectbox("T1 Min", _T_LBLS, index=0, key="pf_sw_t1_min")
            _sw_t1_max = st.selectbox("T1 Max", _T_LBLS, index=_t_idx(2.0), key="pf_sw_t1_max")
        with sw2:
            st.caption("**PB range**")
            _sw_pb_sh  = st.selectbox("Shallowest", _SW_PB_LBLS, index=0, key="pf_sw_pb_sh")
            _sw_pb_dp  = st.selectbox("Deepest",    _SW_PB_LBLS, index=5, key="pf_sw_pb_dp")
        with sw3:
            st.caption("**T2 range**")
            _sw_t2_min = st.selectbox("T2 Min", _T_LBLS, index=0, key="pf_sw_t2_min")
            _sw_t2_max = st.selectbox("T2 Max", _T_LBLS, index=_t_idx(3.0), key="pf_sw_t2_max")
        with sw4:
            st.caption("**Options**")
            _rank_by    = st.radio("Rank by", ["PnL/DD", "Net PnL", "PF"],
                                   index=0, key="pf_sw_rank_by")
            _min_trades = st.number_input("Min trades", 5, 200, value=10,
                                          step=5, key="pf_sw_min_trades")

        _t1_vals  = _t_range(_sw_t1_min, _sw_t1_max)
        _pb_vals  = _pb_range(_sw_pb_sh, _sw_pb_dp)
        _t2_vals  = _t_range(_sw_t2_min, _sw_t2_max)
        _n_combos = len(_t1_vals) * len(_pb_vals) * len(_t2_vals)

        sw_btn_col, sw_cap_col = st.columns([2, 8])
        _sw_run = sw_btn_col.button(
            "▶ Run Sweep", type="primary",
            disabled=not enabled_ccs or _n_combos == 0,
            key="pf_sw_run_btn",
        )
        sw_cap_col.caption(
            f"{len(_t1_vals)} T1 × {len(_pb_vals)} PB × {len(_t2_vals)} T2 = "
            f"**{_n_combos} combos** × {len(enabled_ccs)} setups = "
            f"{_n_combos * len(enabled_ccs)} simulations"
        )

        if _sw_run:
            _sw_res = {}
            _sw_prog = st.progress(0)
            for _i, _cc in enumerate(enabled_ccs):
                _cc_sig = signals[signals["SignalType"] == _cc].copy()
                _cfg_cc = configs[_cc]
                _sw_res[_cc] = _run_sweep_for_cc(
                    _cc_sig, ticks_by_date, bars_by_date,
                    _t1_vals, _pb_vals, _t2_vals,
                    entry_slip, exit_slip, stop_offset,
                    tick_value, commission,
                    _cfg_cc["contracts_t1"], _cfg_cc["contracts_t2"],
                    int(_min_trades),
                )
                _sw_prog.progress((_i + 1) / len(enabled_ccs))
            _sw_prog.empty()
            st.session_state["pf_sweep_results"] = _sw_res
            st.session_state["pf_sweep_rank"]    = _rank_by
            st.rerun()

        # ── Sweep results ─────────────────────────────────────────────────────
        _sw_data  = st.session_state.get("pf_sweep_results")
        _rank_col = st.session_state.get("pf_sweep_rank", "PnL/DD")
        if _sw_data:
            _ccs = list(_sw_data.keys())
            for _i in range(0, len(_ccs), 2):
                _pair = _ccs[_i: _i + 2]
                _tcols = st.columns(len(_pair))
                for _tcol, _cc in zip(_tcols, _pair):
                    with _tcol:
                        _raw_df = _sw_data[_cc]
                        _color  = _cc_color(_cc, cc_types)
                        st.markdown(
                            f"<span style='color:{_color}'>**{_cc}**</span>"
                            f" — top 20 by {_rank_col}",
                            unsafe_allow_html=True,
                        )
                        if _raw_df.empty:
                            st.caption("No combos met the min-trades filter.")
                            continue

                        _sorted_raw = _raw_df.sort_values(_rank_col, ascending=False).head(20).reset_index(drop=True)
                        _disp_df    = _format_sweep_df(_raw_df, _rank_col)

                        _sel = st.dataframe(
                            _disp_df,
                            use_container_width=True, hide_index=True,
                            height=380, key=f"pf_sw_sel_{_cc}",
                            on_select="rerun", selection_mode="single-row",
                        )
                        _rows = _sel.selection.rows if hasattr(_sel, "selection") else []
                        if _rows:
                            _r  = _sorted_raw.iloc[_rows[0]]
                            _t1_lbl = f"{_r['t1_raw']:.2f}R"
                            _pb_lbl = f"{_r['pb_raw']:.2f}R"
                            _t2_lbl = f"{_r['t2_raw']:.2f}R"
                            if st.button(
                                f"Apply  T1={_t1_lbl}  PB={_pb_lbl}  T2={_t2_lbl}  → {_cc}",
                                key=f"pf_sw_apply_row_{_cc}",
                            ):
                                _apply_to_config(_cc, _r["t1_raw"], _r["pb_raw"], _r["t2_raw"])
                                st.rerun()

            # Apply all-best button
            st.markdown("---")
            _ap_col, _ap_cap = st.columns([2, 8])
            if _ap_col.button("✅ Apply All Best to Config", key="pf_sw_apply_all"):
                for _cc, _df in _sw_data.items():
                    if _df.empty or _rank_col not in _df.columns:
                        continue
                    _best = _df.sort_values(_rank_col, ascending=False).iloc[0]
                    _apply_to_config(_cc, _best["t1_raw"], _best["pb_raw"], _best["t2_raw"])
                st.rerun()
            _ap_cap.caption(
                f"Sets each setup to the #1 combo by {_rank_col}. "
                "Or click a row above to apply one setup at a time."
            )

    # ── Run Portfolio button ──────────────────────────────────────────────────
    btn_col, cap_col = st.columns([2, 8])
    run_clicked = btn_col.button(
        "▶ Run Portfolio", type="primary", disabled=not enabled_ccs,
    )
    cap_col.caption(
        f"{len(enabled_ccs)} setups · {len(signals)} signals in range"
        + ("" if enabled_ccs else " — enable at least one setup")
    )

    if run_clicked:
        _pf_res = {}
        prog = st.progress(0)
        for i, cc in enumerate(enabled_ccs):
            cfg    = configs[cc]
            cc_sig = signals[signals["SignalType"] == cc].copy()
            res    = simulate_trades(
                cc_sig, ticks_by_date, cfg["t2_r"],
                entry_slip, exit_slip, stop_offset,
                tick_value, cfg["contracts_t1"], commission,
                bars_by_date=bars_by_date,
                multileg=True,
                t1_r=cfg["t1_r"], t1_action="exit",
                contracts_t1=cfg["contracts_t1"],
                contracts_t2=cfg["contracts_t2"],
                ml_pb_r=cfg["pb_r"],
            )
            _pf_res[cc] = res
            prog.progress((i + 1) / len(enabled_ccs))
        prog.empty()
        _combined = (
            pd.concat(list(_pf_res.values()))
            .sort_values(["Date", "EntryTime"])
            .reset_index(drop=True)
        )
        st.session_state["pf_results"]  = _pf_res
        st.session_state["pf_combined"] = _combined
        st.session_state["pf_configs"]  = configs
        st.rerun()

    # ── Results ───────────────────────────────────────────────────────────────
    pf_results  = st.session_state.get("pf_results")
    combined    = st.session_state.get("pf_combined")
    run_configs = st.session_state.get("pf_configs", configs)

    if not pf_results or combined is None or combined.empty:
        return

    comb_filled = (
        combined[combined["Filled"] == True]
        .sort_values(["Date", "EntryTime"])
    )

    summary = compute_summary(combined, commission,
                              contracts=1, is_multileg=True,
                              contracts_t1=1, contracts_t2=1)
    if not summary:
        st.warning("No filled trades in portfolio.")
        return

    _dd_abs     = abs(summary["max_dd"]) if summary["max_dd"] != 0 else None
    _pnl_dd     = summary["net_total"] / _dd_abs if _dd_abs else None
    _pf_str     = f"{summary['pf']:.2f}" if summary["pf"] < 99 else "∞"
    _ci_lo      = summary.get("exp_r_ci_lo", np.nan)
    _ci_hi      = summary.get("exp_r_ci_hi", np.nan)
    _ci_known   = not (np.isnan(_ci_lo) or np.isnan(_ci_hi))
    _exp_r_help = f"95% CI  [{_ci_lo:+.2f}, {_ci_hi:+.2f}]" if _ci_known else None

    st.markdown("---")
    _summary_strip(summary, _pnl_dd, _pf_str, _exp_r_help, starting_cap=float(starting_cap))
    _detail_strip(summary, _pf_str, starting_cap=float(starting_cap))

    # ── Equity curves ─────────────────────────────────────────────────────────
    with st.expander("📈 Equity Curves", expanded=True):
        fig = go.Figure()
        for cc, res in pf_results.items():
            filled = res[res["Filled"] == True].sort_values(["Date", "EntryTime"])
            if filled.empty:
                continue
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(filled["Date"].astype(str)),
                y=filled["NetPnL"].cumsum().values,
                name=cc, mode="lines",
                line=dict(color=_cc_color(cc, cc_types), width=1.5),
                hovertemplate=f"{cc}<br>%{{x}}<br>$%{{y:,.0f}}<extra></extra>",
            ))
        if not comb_filled.empty:
            fig.add_trace(go.Scatter(
                x=pd.to_datetime(comb_filled["Date"].astype(str)),
                y=comb_filled["NetPnL"].cumsum().values,
                name="Portfolio", mode="lines",
                line=dict(color="white", width=2.5, dash="dot"),
                hovertemplate="Portfolio<br>%{x}<br>$%{y:,.0f}<extra></extra>",
            ))
        fig.update_layout(
            height=420, margin=dict(l=50, r=20, t=30, b=40),
            xaxis_title="Date", yaxis_title="Cumulative Net PnL ($)",
            legend=dict(orientation="h", y=1.1),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)",
                       zeroline=True, zerolinecolor="rgba(255,255,255,0.25)"),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Per-setup breakdown ───────────────────────────────────────────────────
    with st.expander("📊 Per-Setup Breakdown", expanded=True):
        rows = []
        for cc, res in pf_results.items():
            cfg  = run_configs.get(cc, {})
            ct1  = cfg.get("contracts_t1", 1)
            ct2  = cfg.get("contracts_t2", 1)
            s    = compute_summary(res, commission, contracts=ct1, is_multileg=True,
                                   contracts_t1=ct1, contracts_t2=ct2)
            if not s:
                continue
            _dd  = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            _pd  = round(s["net_total"] / _dd, 2) if _dd else None
            _ret = f"{s['net_total'] / starting_cap * 100:.1f}%" if starting_cap > 0 else "—"
            pb_v = cfg.get("pb_r", 0.0)
            rows.append({
                "Setup":   cc,
                "T1":      f"{cfg.get('t1_r', 1.0):.2f}R",
                "PB":      f"{pb_v:.2f}R" if pb_v != 0 else "None",
                "T2":      f"{cfg.get('t2_r', 2.0):.2f}R",
                "E1×E2":   f"{ct1}×{ct2}",
                "Trades":  s["n_trades"],
                "Win %":   f"{s['win_pct']:.1f}%",
                "PF":      f"{s['pf']:.2f}" if s["pf"] < 99 else "∞",
                "Net PnL": f"${s['net_total']:,.0f}",
                "Return":  _ret,
                "Max DD":  f"${s['max_dd']:,.0f}",
                "PnL/DD":  f"{_pd:.2f}" if _pd else "—",
                "Exp $":   f"${s['exp_dollar']:+.0f}",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Drawdown by setup ─────────────────────────────────────────────────────
    with st.expander("📉 Drawdown by Setup", expanded=False):
        fig_dd = go.Figure()
        for cc, res in pf_results.items():
            filled = res[res["Filled"] == True].sort_values(["Date", "EntryTime"])
            if filled.empty:
                continue
            eq = filled["NetPnL"].cumsum()
            dd = eq - eq.cummax()
            fig_dd.add_trace(go.Scatter(
                x=pd.to_datetime(filled["Date"].astype(str)),
                y=dd.values,
                name=cc, mode="lines",
                line=dict(color=_cc_color(cc, cc_types), width=1.2),
                fill="tozeroy", fillcolor=_cc_fill(cc, cc_types),
            ))
        if not comb_filled.empty:
            comb_eq = comb_filled["NetPnL"].cumsum()
            comb_dd = comb_eq - comb_eq.cummax()
            fig_dd.add_trace(go.Scatter(
                x=pd.to_datetime(comb_filled["Date"].astype(str)),
                y=comb_dd.values,
                name="Portfolio", mode="lines",
                line=dict(color="white", width=2, dash="dot"),
            ))
        fig_dd.update_layout(
            height=300, margin=dict(l=50, r=20, t=20, b=40),
            xaxis_title="Date", yaxis_title="Drawdown ($)",
            legend=dict(orientation="h", y=1.12),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig_dd, use_container_width=True)

    # ── Save this run ─────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("💾 Save This Run", expanded=False):
        st.caption(
            "Convention: **`{scope} | {period} | {description}`**  "
            "e.g. `IS | 2026-01→2026-06 | CC2-5 sweep-opt PB-0.5`"
        )
        _sv1, _sv2, _sv3 = st.columns([1.5, 2, 3])
        _scope = _sv1.selectbox(
            "Scope", ["IS", "OOS", "Full", "WF-IS", "WF-OOS", "Backtest"],
            key="pf_save_scope",
        )
        _period = _sv2.text_input(
            "Period",
            value=f"{date_from.strftime('%Y-%m')}→{date_to.strftime('%Y-%m')}",
            key="pf_save_period",
        )
        _desc = _sv3.text_input(
            "Description",
            value="", placeholder="CC2-5 sweep-opt | 1x1 contracts",
            key="pf_save_desc",
        )
        _run_name = f"{_scope} | {_period} | {_desc}".strip(" |")
        st.caption(f"Will save as: **{_run_name}**")

        if st.button("💾 Save", key="pf_save_btn",
                     disabled=not _desc.strip()):
            _save_run(_run_name, summary, run_configs,
                      float(starting_cap), date_from, date_to)
            st.success(f"Saved: '{_run_name}'")

    # ── Compare saved runs ────────────────────────────────────────────────────
    _saved = _load_saved_runs()
    if _saved:
        with st.expander(f"📊 Compare Saved Runs  ({len(_saved)})", expanded=False):
            _metrics = [
                ("Net PnL",  lambda r: f"${r['net_pnl']:,.0f}"),
                ("Return %", lambda r: f"{r['return_pct']:.1f}%" if r.get("return_pct") else "—"),
                ("Win %",    lambda r: f"{r['win_pct']:.1f}%"),
                ("PF",       lambda r: f"{r['pf']:.2f}"),
                ("PnL/DD",   lambda r: f"{r['pnl_dd']:.2f}" if r.get("pnl_dd") else "—"),
                ("Max DD",   lambda r: f"${r['max_dd']:,.0f}"),
                ("Exp R",    lambda r: f"{r['exp_r']:+.3f}"),
                ("Trades",   lambda r: str(r["trades"])),
                ("Period",   lambda r: f"{r['date_from']} → {r['date_to']}"),
                ("Saved",    lambda r: r["timestamp"]),
            ]

            _col_names = [r["name"] for r in _saved]
            _tbl = {"Metric": [m[0] for m in _metrics]}
            for run in _saved:
                _tbl[run["name"]] = [fmt(run) for _, fmt in _metrics]

            st.dataframe(pd.DataFrame(_tbl).set_index("Metric"),
                         use_container_width=True)

            # Delete a run
            _del_name = st.selectbox("Delete run", ["—"] + _col_names, key="pf_del_sel")
            if st.button("🗑 Delete", key="pf_del_btn", disabled=_del_name == "—"):
                _remaining = [r for r in _saved if r["name"] != _del_name]
                _SAVED_RUNS_FILE.write_text(json.dumps(_remaining, indent=2))
                st.rerun()
