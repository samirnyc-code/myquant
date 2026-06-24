"""🎯 QS Breakouts tab — Ali Moin-Afshari reproduction in-app.

Detector: WHITEPAPER (page 8-9 research defs: BO+FT, BigBO, Rev+FT) or PAINTBAR
(EL Ver5 code). Sim = the project tick engine (ESA-aware). Rich Quick View +
Year/Quarter/Month/Week breakdowns + full trade list. Results push to
st.session_state["ba_results"] so the Prop Sim tab + BA panels run on QS trades.

Default geometry = Ali WP: stop 1x signal-bar range, target 1x (symmetric),
entry bar 2 (BTC).  (His worksheet "a.Risk Dist" averaged ~4.74 pt = 1 bar range.)
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

import massive
import simulation_engine as _se_mod
import qs_setups as _qs_mod
from simulation_engine import simulate_trades, EXECUTION_PRESETS
from qs_setups import detect, detect_wp, QSConfig
import ui_controls as controls

_BARS = Path(__file__).parent / "data" / "bars" / "_continuous.parquet"
N_CHUNKS = 6


def _code_hash() -> str:
    h = hashlib.md5()
    for m in (_qs_mod, _se_mod):
        try:
            h.update(Path(m.__file__).read_bytes())
        except Exception:
            pass
    return h.hexdigest()[:10]


# ───────────────────────── metrics / period aggregation ──────────────────────

def _full_metrics(df: pd.DataFrame) -> dict:
    pnl = df["NetPnL"].to_numpy(float)
    r = (df["NetPnL"] / df["RiskDollar"].replace(0, np.nan)).to_numpy(float)
    n = len(pnl)
    if n == 0:
        return dict(n=0)
    wins = pnl > 0
    std = np.nanstd(r, ddof=1) if n > 1 else np.nan
    cum = np.cumsum(pnl); dd_dollar = float((cum - np.maximum.accumulate(cum)).min())
    cumr = np.cumsum(r); dd_r = float((cumr - np.maximum.accumulate(cumr)).min())
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    hold = (df["ExitBarNum"] - df["EntryBarNum"]) if "ExitBarNum" in df else pd.Series([np.nan])
    er = df.get("ExitReason", pd.Series([], dtype=object))
    return dict(
        n=n, win=float(wins.mean() * 100), expR=float(np.nanmean(r)),
        exp_dollar=float(pnl.mean()), net=float(pnl.sum()), totR=float(np.nansum(r)),
        PF=(float(gw / gl) if gl > 0 else np.inf),
        SQN=(float(np.nanmean(r) / std * np.sqrt(n)) if (n > 1 and std > 0) else np.nan),
        avgW_R=(float(r[wins].mean()) if wins.any() else np.nan),
        avgL_R=(float(r[~wins].mean()) if (~wins).any() else np.nan),
        payoff=(float(abs(r[wins].mean() / r[~wins].mean()))
                if (wins.any() and (~wins).any() and r[~wins].mean() != 0) else np.nan),
        maxDD_R=dd_r, maxDD_dollar=dd_dollar,
        MAR=(float(pnl.sum() / abs(dd_dollar)) if dd_dollar < 0 else np.inf),
        best=float(pnl.max()), worst=float(pnl.min()),
        avg_hold=float(hold.mean()) if len(hold) else np.nan,
        tgt_pct=float((er == "Target").mean() * 100) if len(er) else np.nan,
        stop_pct=float((er == "Stop").mean() * 100) if len(er) else np.nan,
        eod_pct=float((er == "EOD").mean() * 100) if len(er) else np.nan,
    )


def _by_period(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    dt = pd.to_datetime(df["DateTime"] if "DateTime" in df else df["EntryTime"])
    key = dt.dt.to_period(freq).astype(str)
    rows = []
    for p, g in df.groupby(key, sort=True):
        m = _full_metrics(g)
        rows.append({freq: p, "n": m["n"], "win%": round(m["win"], 1),
                     "expR": round(m["expR"], 3),
                     "PF": (round(m["PF"], 2) if m["PF"] != np.inf else np.inf),
                     "SQN": round(m["SQN"], 2) if not np.isnan(m["SQN"]) else np.nan,
                     "totR": round(m["totR"], 1), "net$": round(m["net"], 0),
                     "avgW_R": round(m["avgW_R"], 2), "avgL_R": round(m["avgL_R"], 2),
                     "maxDD_R": round(m["maxDD_R"], 1), "maxDD_$": round(m["maxDD_dollar"], 0)})
    return pd.DataFrame(rows).set_index(freq)


# ─────────────────────────────── run (cached) ────────────────────────────────

@st.cache_data(show_spinner=False)
def _run_qs(code_hash: str, cfg_items: tuple, detector: str, types: tuple,
            target_r: float, commission: float, entry_slip, exit_slip,
            calc_ms: int, wire_ms: int, ratchet_r: float, contracts: int) -> pd.DataFrame:
    bars = pd.read_parquet(_BARS)
    cfg = QSConfig(**dict(cfg_items))
    sig = detect_wp(bars, cfg) if detector == "wp" else detect(bars, cfg)
    if types:
        sig = sig[sig["SignalType"].isin(list(types))]
    sig = sig[sig["FilterStatus"] == "ok"].reset_index(drop=True)
    if sig.empty:
        return pd.DataFrame()
    sig["_date"] = pd.to_datetime(sig["DateTime"]).dt.date
    bars2 = bars.drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars2.groupby(bars2["DateTime"].dt.date)}
    dates = np.array(sorted(sig["_date"].unique()), object)

    base = dict(stop_offset=1, tick_value=12.5, contracts=int(contracts), multileg=False,
                threeleg=False, overrides=None, entry_model="market", target_r=target_r,
                commission=commission, entry_slip=entry_slip, exit_slip=exit_slip,
                calc_delay_ms=int(calc_ms), wire_delay_ms=int(wire_ms),
                ratchet_r=ratchet_r, ratchet_dest="BE", ratchet_lock_r=0.0, exec_seed=42)
    out = []
    prog = st.progress(0.0, text="Simulating QS trades…")
    chunks = np.array_split(dates, N_CHUNKS)
    for ci, chunk in enumerate(chunks):
        sub = sig[sig["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd, **base).reset_index(drop=True)
        for col in ["SignalType", "Direction", "DateTime", "BarNum"]:
            if col in sub.columns and col not in res.columns:
                res[col] = sub[col].values
        out.append(res[res["Filled"] == True].copy())
        prog.progress((ci + 1) / len(chunks), text=f"Simulating… {ci+1}/{len(chunks)}")
    prog.empty()
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# ─────────────────────────────── the tab ─────────────────────────────────────

_PB_PRESETS = {"paper (WP-ish)": QSConfig.paper, "EL Ver5 default": QSConfig,
               "research": QSConfig.research, "paintbar raw": QSConfig.paintbar_raw}

# geometry name -> (stop_basis, stop_dist_mult, target_r)
_GEOM = {
    "Ali WP (stop 1× range / tgt 1×)":        ("signal_range",   1.0, 1.0),
    "Wide / momentum (stop 2× comb / tgt 2×)": ("combined_range", 2.0, 1.0),
    "Ali combined (stop 2× comb / tgt 1×)":    ("combined_range", 2.0, 0.5),
    "Custom":                                  None,
}


def show_qs_tab():
    st.subheader("🎯 QS Breakouts — Ali reproduction")
    st.caption("Whitepaper (p.8-9) or PaintBar detector → tick-sim → metrics / "
               "breakdowns / trades. Results push to **Prop Sim** (`ba_results`).")

    with controls.expander("qs_config", "⚙️ Detector, signals & geometry", expanded=True):
        d1, d2, d3 = st.columns(3)
        detector_label = d1.radio("Detector", ["Whitepaper (p.8-9)", "PaintBar code"],
                                  index=0, key="qs_det")
        is_wp = detector_label.startswith("Whitepaper")
        contracts = d3.number_input("Contracts", value=1, min_value=1, step=1, key="qs_contracts")

        if is_wp:
            types = tuple(d2.multiselect("Signal types", ["BO+FT", "Rev+FT", "BigBO"],
                                         default=["BO+FT"], key="qs_types_wp"))
            preset_name = "wp"
        else:
            preset_name = d2.selectbox("PaintBar preset", list(_PB_PRESETS), index=0, key="qs_preset")
            subset = st.selectbox("Trade definition", ["FT-only", "BO-family", "All signals"],
                                  index=0, key="qs_subset")
            types = {"FT-only": ("BO+FT",), "BO-family": ("BO", "BO+FT", "BigBO"),
                     "All signals": ()}[subset]

        st.markdown("**Geometry**")
        gsel = st.selectbox("Geometry", list(_GEOM),
                            index=0 if is_wp else 1, key="qs_geom",
                            help="Ali WP = his worksheet's ~1-bar-range risk, symmetric 1R. "
                                 "Wide/momentum = the higher-$ hold-to-EOD version.")
        if _GEOM[gsel] is None:
            gg1, gg2, gg3 = st.columns(3)
            stop_basis = gg1.selectbox("Stop basis", ["signal_range", "combined_range"], key="qs_basis")
            stop_mult = gg2.number_input("Stop ×", value=1.0, step=0.5, key="qs_stopmult")
            target_r = gg3.number_input("Target (× R)", value=1.0, step=0.25, key="qs_tr")
        else:
            stop_basis, stop_mult, target_r = _GEOM[gsel]
            st.caption(f"→ stop **{stop_mult}× {stop_basis}**, target **{target_r}× R** — {gsel}")

        f1, f2, f3 = st.columns(3)
        ibs_on = f1.checkbox("IBS 69/31", value=True, key="qs_ibs")
        time_on = f2.checkbox("Time filter (10:10 ET)", value=True, key="qs_time")
        no3 = f3.checkbox("No 3rd consecutive", value=True, key="qs_no3")
        if not is_wp:
            h1, h2, h3 = st.columns(3)
            require_ft = h1.checkbox("Require FT", value=True, key="qs_ft")
            range_on = h2.checkbox("Range filter (ABR)", value=True, key="qs_range")
            use_obcx = h3.checkbox("Include OB+CX", value=True, key="qs_obcx")

    with controls.expander("qs_exec", "⚙️ Execution model (ESA) + BE", expanded=True):
        e1, e2, e3 = st.columns(3)
        esa = e1.selectbox("ESA preset", ["Custom", *EXECUTION_PRESETS.keys()], index=0, key="qs_esa")
        commission = e2.number_input("Commission $ (RT)", value=0.0, step=1.0, key="qs_comm")
        ratchet_r = e3.number_input("BE @ +R (0=off)", value=0.0, step=0.25, key="qs_be")
        if esa == "Custom":
            x1, x2, x3, x4 = st.columns(4)
            entry_slip = x1.number_input("Entry slip ticks", value=0, step=1, key="qs_eslip")
            exit_slip = x2.number_input("Exit slip ticks", value=0, step=1, key="qs_xslip")
            calc_ms = x3.number_input("Calc delay ms", value=0, step=10, key="qs_calc")
            wire_ms = x4.number_input("Wire delay ms", value=0, step=10, key="qs_wire")
        else:
            p = EXECUTION_PRESETS[esa]
            entry_slip, exit_slip = p["entry_slip"], p["exit_slip"]
            calc_ms, wire_ms = p["calc_delay_ms"], p["wire_delay_ms"]
            st.caption(f"**{esa}** → calc {calc_ms}ms · wire {wire_ms}ms · "
                       f"entry slip {entry_slip} · exit slip {exit_slip}")

    # ── build config ──
    if is_wp:
        cfg = QSConfig.wp()
        if not ibs_on:
            cfg.bull_bo_ibs = 0.0; cfg.bear_bo_ibs = 100.0
            cfg.bull_rev_ibs = 0.0; cfg.bear_rev_ibs = 100.0
    else:
        cfg = _PB_PRESETS[preset_name]()
        cfg.require_ft = require_ft
        cfg.range_filter_on = range_on
        cfg.use_ob = use_obcx; cfg.use_cx = use_obcx
        cfg.signal_ibs_bull = 69.0 if ibs_on else -1.0
        cfg.signal_ibs_bear = 31.0 if ibs_on else -1.0
        cfg.ft_ibs_bull = 69.0 if ibs_on else -1.0
        cfg.ft_ibs_bear = 31.0 if ibs_on else -1.0
    cfg.stop_basis = stop_basis
    cfg.stop_dist_mult = float(stop_mult)
    cfg.use_paper_istop_variants = False
    cfg.time_filter_on = time_on
    cfg.no_third_consecutive = no3

    rc1, rc2 = st.columns([1, 4])
    run_clicked = rc1.button("▶️ Run QS backtest", type="primary", key="qs_run")
    if rc2.button("🔄 Clear cached runs", key="qs_clear"):
        _run_qs.clear(); st.success("Cache cleared — press Run."); return
    if not run_clicked:
        st.info(f"Set config and press **Run**. First run replays ~5y of ticks "
                f"(~1–2 min); cached afterward. (code {_code_hash()})")
        return

    res = _run_qs(_code_hash(), tuple(sorted(cfg.to_dict().items())), preset_name if is_wp else "code",
                  types, float(target_r), float(commission), entry_slip, exit_slip,
                  int(calc_ms), int(wire_ms), float(ratchet_r), int(contracts))
    if res.empty:
        st.warning("No filled trades for this config."); return

    st.session_state["ba_results"] = res
    st.session_state["qs_results"] = res
    src = f"{'WP' if is_wp else 'PaintBar'} / {','.join(types) or 'all'} / {gsel} / {esa}"
    st.session_state["qs_results_source"] = src
    m = _full_metrics(res)
    st.success(f"✅ {m['n']:,} trades → pushed to **Prop Sim** (`ba_results`). Config: {src}")

    with controls.expander("qs_quickview", "📊 Quick View", expanded=True):
        r1 = st.columns(6)
        r1[0].metric("Trades", f"{m['n']:,}"); r1[1].metric("Win %", f"{m['win']:.1f}")
        r1[2].metric("Exp R", f"{m['expR']:+.3f}"); r1[3].metric("Exp $", f"${m['exp_dollar']:,.0f}")
        r1[4].metric("Net $", f"${m['net']:,.0f}"); r1[5].metric("Total R", f"{m['totR']:,.0f}")
        r2 = st.columns(6)
        r2[0].metric("PF", "inf" if m["PF"] == np.inf else f"{m['PF']:.2f}")
        r2[1].metric("SQN", f"{m['SQN']:.2f}"); r2[2].metric("Payoff W/L", f"{m['payoff']:.2f}")
        r2[3].metric("Avg W/L R", f"{m['avgW_R']:.2f}/{m['avgL_R']:.2f}")
        r2[4].metric("Max DD $", f"${m['maxDD_dollar']:,.0f}")
        r2[5].metric("MAR", "inf" if m["MAR"] == np.inf else f"{m['MAR']:.2f}")
        r3 = st.columns(6)
        r3[0].metric("Max DD R", f"{m['maxDD_R']:.1f}"); r3[1].metric("Avg hold", f"{m['avg_hold']:.1f}")
        r3[2].metric("Target %", f"{m['tgt_pct']:.1f}"); r3[3].metric("Stop %", f"{m['stop_pct']:.1f}")
        r3[4].metric("EOD %", f"{m['eod_pct']:.1f}")
        r3[5].metric("Best/Worst $", f"{m['best']:,.0f}/{m['worst']:,.0f}")

    with controls.expander("qs_breakdowns", "📅 Period breakdowns (Y/Q/M/W)", expanded=True):
        tabs = st.tabs(["Yearly", "Quarterly", "Monthly", "Weekly"])
        for tabobj, freq, name in zip(tabs, ["Y", "Q", "M", "W"], ["year", "quarter", "month", "week"]):
            with tabobj:
                tbl = _by_period(res, freq)
                st.dataframe(tbl, use_container_width=True)
                st.download_button(f"⬇️ {name} CSV", tbl.to_csv().encode("utf-8"),
                                   file_name=f"qs_{name}.csv", mime="text/csv", key=f"qs_dl_{freq}")

    with controls.expander("qs_trades", "📋 Complete trade list", expanded=False):
        cols = [c for c in ["DateTime", "Direction", "SignalType", "BarNum", "SignalPrice",
                            "EntryTime", "EntryBarNum", "EntryPrice", "ActualStop", "Target",
                            "ExitTime", "ExitPrice", "ExitReason", "RiskPts", "NetPnL", "MAE_R", "MFE_R"]
                if c in res.columns]
        view = res[cols].copy()
        view["R"] = (res["NetPnL"] / res["RiskDollar"].replace(0, np.nan)).round(3)
        st.caption(f"{len(view):,} filled trades")
        st.dataframe(view, use_container_width=True, height=420)
        st.download_button("⬇️ Full trade list CSV", res.to_csv(index=False).encode("utf-8"),
                           file_name="qs_trades_full.csv", mime="text/csv", key="qs_dl_trades")
