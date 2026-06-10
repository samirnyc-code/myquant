import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from data_loader import (load_sc_bars, load_nt_bars, get_market_holidays, TICK_SIZE,
                         parse_sc_ohlc_from_upload, parse_ohlc_from_upload)
from economic_calendar import get_economic_events, fred_key_configured, EVENT_COLOR

_DEFAULTS_FILE = Path(__file__).parent / "filter_defaults.json"

def _load_filter_defaults() -> dict:
    if _DEFAULTS_FILE.exists():
        try:
            return json.loads(_DEFAULTS_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_filter_defaults(d: dict):
    _DEFAULTS_FILE.write_text(json.dumps(d, indent=2))

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
    _keep = ["DateTime"] + ALL_FIELDS
    sc_m = sc[[c for c in _keep if c in sc.columns]].rename(
        columns={c: f"{c}_sc" for c in ALL_FIELDS}).set_index("DateTime")
    nt_m = nt[[c for c in _keep if c in nt.columns]].rename(
        columns={c: f"{c}_nt" for c in ALL_FIELDS}).set_index("DateTime")

    m = sc_m.join(nt_m, how="outer")
    matched = m["Open_sc"].notna() & m["Open_nt"].notna()

    m["Status"] = "Matched"
    m.loc[m["Open_sc"].notna() & m["Open_nt"].isna(), "Status"] = "SC only"
    m.loc[m["Open_sc"].isna() & m["Open_nt"].notna(), "Status"] = "NT only"

    for col in PRICE_FIELDS:
        m[f"Δ{col}"] = np.nan
        if matched.any():
            m.loc[matched, f"Δ{col}"] = (
                (m.loc[matched, f"{col}_nt"] - m.loc[matched, f"{col}_sc"]) / TICK_SIZE
            ).round(0)

    m["ΔVolume"] = np.nan
    if matched.any():
        m.loc[matched, "ΔVolume"] = (
            m.loc[matched, "Volume_nt"].astype(float) -
            m.loc[matched, "Volume_sc"].astype(float)
        )

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


# ── Commentary helpers ────────────────────────────────────────────────────────

def _info(text: str):
    st.info(text)


def _summary_commentary(n_matched, n_sc_only, n_nt_only, pct_ohlc, pct_ohlcv, n_ohlc_mm, excl_volume=False):
    if pct_ohlc >= 99:
        health = "🟢 **Strong agreement.** The two data sources are highly consistent on price."
    elif pct_ohlc >= 95:
        health = "🟡 **Good agreement with minor discrepancies.** Worth investigating but not alarming."
    else:
        health = "🔴 **Meaningful discrepancies detected.** Investigate the mismatch table before trusting either source."

    unmatched_note = ""
    if n_sc_only > 0 or n_nt_only > 0:
        unmatched_note = (
            f" Note: {n_sc_only} bar(s) exist only in SC and {n_nt_only} only in NT — "
            f"these are missing bars in one source and should be investigated separately."
        )

    vol_note = "" if excl_volume else (
        f" Volume exact match ({pct_ohlcv:.1f}%) is lower than OHLC match — "
        f"this is normal. Volume differences come from different data feed sources "
        f"counting ticks at bar boundaries differently. For a price-based strategy it does not affect signal generation."
    )

    _info(f"{health} {n_ohlc_mm:,} of {n_matched:,} bars have at least one OHLC field that differs.{vol_note}{unmatched_note}")


def _field_table_commentary(matched: pd.DataFrame, excl_volume: bool = False):
    if matched.empty:
        return
    open_mm  = int(matched["ΔOpen"].ne(0).sum())
    high_mm  = int(matched["ΔHigh"].ne(0).sum())
    low_mm   = int(matched["ΔLow"].ne(0).sum())
    close_mm = int(matched["ΔClose"].ne(0).sum())

    notes = []
    if open_mm > close_mm:
        notes.append(
            f"**Open ({open_mm} mismatches) > Close ({close_mm})** — typical. "
            "The opening bar is the most chaotic: both feeds race to capture the first print "
            "at 08:30 and may record different ticks depending on feed latency."
        )
    if high_mm <= 3 and low_mm <= 3:
        notes.append(
            f"**High and Low are nearly perfect ({high_mm} and {low_mm} mismatches)** — expected. "
            "Extreme prices are captured across the full bar window and are insensitive to boundary timing."
        )
    if not excl_volume:
        vol_mm = int(matched["ΔVolume"].ne(0).sum())
        if vol_mm > open_mm:
            notes.append(
                f"**Volume has the most mismatches ({vol_mm})** — normal and inconsequential for a price-based strategy. "
                "SC sums raw tick volumes; NT records feed-level volume. Different sources, different boundary counting."
            )

    for note in notes:
        _info(note)


def _time_of_day_commentary(tod: pd.DataFrame):
    if tod.empty:
        return
    worst = tod.loc[tod["OHLC_MM"].idxmax(), "BarTime"] if tod["OHLC_MM"].max() > 0 else None
    open_bar  = tod[tod["BarTime"] == "08:30"]["OHLC_MM"].sum()
    close_bars = tod[tod["BarTime"].isin(["14:45", "15:00", "15:05", "15:10"])]["OHLC_MM"].sum()
    mid_bars   = tod[(tod["BarTime"] > "09:00") & (tod["BarTime"] < "14:30")]["OHLC_MM"].sum()
    mid_total  = tod[(tod["BarTime"] > "09:00") & (tod["BarTime"] < "14:30")]["Total"].sum()
    mid_rate   = mid_bars / mid_total * 100 if mid_total > 0 else 0

    parts = []
    if open_bar > 0:
        parts.append(
            f"The **08:30 open bar** has {open_bar} mismatches — "
            "expected, as both feeds capture a different 'first print' of the session during the opening auction."
        )
    if close_bars > 0:
        parts.append(
            f"The **last 30 minutes** (14:45–15:10) show elevated mismatches ({int(close_bars)}) — "
            "end-of-session closing orders and settlement handling differ between feeds."
        )
    if mid_rate < 2:
        parts.append(
            f"The **mid-session** (09:00–14:30) is clean at {mid_rate:.1f}% mismatch rate — "
            "a healthy sign that both feeds are in sync during liquid hours."
        )
    if parts:
        _info(" ".join(parts))


def _by_date_commentary(by_date: pd.DataFrame):
    if by_date.empty:
        return
    days_with_mm = int((by_date["OHLC_MM"] > 0).sum())
    total_days   = len(by_date)
    worst_day    = by_date.loc[by_date["OHLC_MM"].idxmax()]
    worst_date   = pd.to_datetime(worst_day["Date"]).strftime("%b %d")
    worst_count  = int(worst_day["OHLC_MM"])
    clustered    = by_date["OHLC_MM"].max() > 5 * by_date["OHLC_MM"].median() + 1

    if clustered:
        _info(
            f"Mismatches are **not evenly distributed** — {worst_date} stands out with {worst_count} mismatches. "
            "A spike on one date typically indicates a data event: feed outage, rollover, or a day where "
            "the two sources had different session boundaries."
        )
    else:
        _info(
            f"Mismatches are **spread evenly** across {days_with_mm} of {total_days} trading days. "
            "No single day dominates, which suggests random boundary noise rather than a systematic data problem."
        )


def _delta_distribution_commentary(matched: pd.DataFrame):
    if matched.empty:
        return
    nonzero_deltas = pd.concat([
        matched[f"Δ{c}"].dropna() for c in PRICE_FIELDS
    ])
    nonzero_deltas = nonzero_deltas[nonzero_deltas.ne(0)]

    if len(nonzero_deltas) == 0:
        _info("All OHLC bars match exactly. No delta distribution to show.")
        return

    is_symmetric = abs(nonzero_deltas.mean()) < 0.5
    has_outliers  = nonzero_deltas.abs().max() > 4
    bias_dir      = "positive (NT > SC)" if nonzero_deltas.mean() > 0 else "negative (NT < SC)"

    parts = []
    if is_symmetric:
        parts.append(
            "The delta distribution is **roughly symmetric around zero** — no systematic bias between the two feeds. "
            "Mismatches are random boundary noise, not a consistent offset."
        )
    else:
        parts.append(
            f"The distribution shows a **{bias_dir} bias** (mean Δ = {nonzero_deltas.mean():.2f} ticks). "
            "This could indicate one feed is systematically recording a slightly different price at bar boundaries."
        )
    if has_outliers:
        n_outliers = int((nonzero_deltas.abs() > 4).sum())
        parts.append(
            f"{n_outliers} bar(s) show large deltas (> 4 ticks). "
            "These are likely caused by a data spike or session-boundary anomaly and are worth inspecting individually in the Mismatch Table."
        )
    _info(" ".join(parts))


def _show_gate_body(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_label: str,
    right_label: str,
    gate_key: str,
    excl_holidays: bool,
    show_commentary: bool,
    excl_volume: bool,
    show_excl_shading: bool,
    excl_first_n: int,
    excl_last_min: int,
    incl_days: tuple,
    event_types: tuple,
    event_filter_mode: str,
    event_window: int,
):
    left_dates  = left["DateTime"].dt.date
    right_dates = right["DateTime"].dt.date
    overlap_min = max(left_dates.min(), right_dates.min())
    overlap_max = min(left_dates.max(), right_dates.max())
    all_min     = min(left_dates.min(), right_dates.min())
    all_max     = max(left_dates.max(), right_dates.max())

    st.caption(f"**{left_label}** (left) vs **{right_label}** (right)  ·  Δ = right − left")

    dc1, dc2 = st.columns(2)
    date_from = dc1.date_input("From", value=overlap_min, min_value=all_min, max_value=all_max,
                                key=f"{gate_key}_date_from")
    date_to   = dc2.date_input("To",   value=overlap_max, min_value=all_min, max_value=all_max,
                                key=f"{gate_key}_date_to")

    left_f  = left[  (left_dates  >= date_from) & (left_dates  <= date_to)]
    right_f = right[ (right_dates >= date_from) & (right_dates <= date_to)]
    last_left_dt = left_f["DateTime"].max() if not left_f.empty else pd.Timestamp.max
    right_f = right_f[right_f["DateTime"] <= last_left_dt].copy()

    comp = build_comparison(left_f, right_f)

    holidays = get_market_holidays(str(date_from), str(date_to))
    n_holiday_bars = int((comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)).sum())
    if excl_holidays and holidays:
        comp = comp[~comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)].copy()

    matched_full = comp[comp["Status"] == "Matched"].copy()

    n_first_n_bars = 0
    if excl_first_n > 0:
        first_n_times = {
            f"{(8 * 60 + 30 + i * 5) // 60:02d}:{(8 * 60 + 30 + i * 5) % 60:02d}"
            for i in range(excl_first_n)
        }
        n_first_n_bars = int(comp["BarTime"].isin(first_n_times).sum())
        comp = comp[~comp["BarTime"].isin(first_n_times)].copy()

    n_last_min_bars = 0
    if excl_last_min > 0:
        cutoff_total = 15 * 60 + 15 - excl_last_min
        cutoff_str   = f"{cutoff_total // 60:02d}:{cutoff_total % 60:02d}"
        n_last_min_bars = int((comp["BarTime"] >= cutoff_str).sum())
        comp = comp[comp["BarTime"] < cutoff_str].copy()

    incl_mon, incl_tue, incl_wed, incl_thu, incl_fri = incl_days
    n_dow_bars = 0
    if not all(incl_days):
        dow_map = {0: incl_mon, 1: incl_tue, 2: incl_wed, 3: incl_thu, 4: incl_fri}
        keep    = comp["DateTime"].dt.dayofweek.map(dow_map).fillna(False)
        n_dow_bars = int((~keep).sum())
        comp = comp[keep].copy()

    events_df = get_economic_events(event_types, str(date_from), str(date_to)) \
        if event_types else pd.DataFrame(columns=["DateTime", "EventType", "Color"])

    n_event_bars = 0
    if not events_df.empty:
        if event_filter_mode == "Skip full day":
            event_dates = set(events_df["DateTime"].dt.date)
            mask = comp["DateTime"].dt.date.isin(event_dates)
            n_event_bars = int(mask.sum())
            comp = comp[~mask].copy()
        else:
            mask = pd.Series(False, index=comp.index)
            for _, ev in events_df.iterrows():
                ev_dt = ev["DateTime"]
                in_win = (
                    (comp["DateTime"] >= ev_dt - pd.Timedelta(minutes=event_window)) &
                    (comp["DateTime"] <= ev_dt + pd.Timedelta(minutes=event_window))
                )
                mask |= in_win
            n_event_bars = int(mask.sum())
            comp = comp[~mask].copy()

    matched    = comp[comp["Status"] == "Matched"]
    n_matched  = len(matched)
    n_lo       = int((comp["Status"] == "SC only").sum())
    n_ro       = int((comp["Status"] == "NT only").sum())
    n_ohlc_mm  = int((~matched["OHLC_match"]).sum()) if n_matched else 0
    n_vol_mm   = int(matched["ΔVolume"].ne(0).sum()) if n_matched else 0
    pct_ohlc   = (1 - n_ohlc_mm / n_matched) * 100  if n_matched else 0.0
    n_trading_days = matched["DateTime"].dt.date.nunique() if n_matched else 0

    if n_matched > 0:
        if pct_ohlc >= 99:
            st.success(f"✅ PASS — {pct_ohlc:.1f}% OHLC exact match  ·  {n_matched:,} bars  ·  {n_trading_days} days")
        elif pct_ohlc >= 95:
            st.warning(f"⚠️ MARGINAL — {pct_ohlc:.1f}% OHLC exact match  ·  {n_matched:,} bars  ·  {n_trading_days} days")
        else:
            st.error(f"❌ FAIL — {pct_ohlc:.1f}% OHLC exact match  ·  {n_matched:,} bars  ·  {n_trading_days} days")

    st.subheader("Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Matched Bars",       f"{n_matched:,}")
    m2.metric("Trading Days",       f"{n_trading_days:,}")
    m3.metric("OHLC Exact Match",   f"{pct_ohlc:.1f}%",
              help="Bars where ALL four OHLC fields match simultaneously.")
    m4.metric("Holiday Bars Excl.", f"{n_holiday_bars:,}" if excl_holidays and n_holiday_bars else "—")
    m5.metric("Event Bars Excl.",   f"{n_event_bars:,}"   if n_event_bars else "—")

    row2 = [(f"{left_label} Only", f"{n_lo:,}"), (f"{right_label} Only", f"{n_ro:,}")]
    if not excl_volume:
        row2.append(("Vol Mismatches",   f"{n_vol_mm:,}"))
    if n_first_n_bars:
        row2.append(("Open Bars Excl.",  f"{n_first_n_bars:,}"))
    if n_last_min_bars:
        row2.append(("Close Bars Excl.", f"{n_last_min_bars:,}"))
    if n_dow_bars:
        row2.append(("DOW Bars Excl.",   f"{n_dow_bars:,}"))
    cols2 = st.columns(len(row2))
    for col, (label, val) in zip(cols2, row2):
        col.metric(label, val)

    if show_commentary:
        _summary_commentary(n_matched, n_lo, n_ro, pct_ohlc, pct_ohlc, n_ohlc_mm, excl_volume)

    st.subheader("Mismatch by Field")
    if show_commentary:
        _info(
            "Each row shows how many bars matched exactly vs differed, and the range of the difference in ticks. "
            "A tick on ES = 0.25 points = $12.50. "
            "The OHLC Exact Match % above is ≤ all four individual field rates — a bar is a mismatch if *any* field differs."
        )
    _show_field_table(matched, excl_volume)
    if show_commentary:
        _field_table_commentary(matched, excl_volume)

    if "NullVol" in right_f.columns:
        null_vol = right_f[right_f["NullVol"]].copy()
        n_nv = len(null_vol)
        if n_nv > 0:
            null_vol["DateTime"] = null_vol["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            with st.expander(f"⚠️ {right_label} bars with null Volume — {n_nv} bar{'s' if n_nv > 1 else ''}"):
                st.caption("Volume was set to 0 for comparison purposes.")
                st.dataframe(null_vol[["DateTime", "Open", "High", "Low", "Close"]],
                             use_container_width=True, hide_index=True)

    if n_lo > 0 or n_ro > 0:
        with st.expander(f"Unmatched bars — {left_label} only: {n_lo}  |  {right_label} only: {n_ro}"):
            if show_commentary:
                _info("Bars that exist in one source but not the other. Common causes: session boundary differences, missing ticks, rollover gaps.")
            all_unmatched = set(comp[comp["Status"] != "Matched"]["DateTime"].dt.strftime("%Y-%m-%d"))
            hp = all_unmatched & holidays
            if hp:
                st.warning(f"📅 NYSE holiday bars in unmatched list: {', '.join(sorted(hp))}.")
            uc1, uc2 = st.columns(2)
            lo_df = comp[comp["Status"] == "SC only"][["DateTime","Open_sc","High_sc","Low_sc","Close_sc","Volume_sc"]].copy()
            ro_df = comp[comp["Status"] == "NT only"][["DateTime","Open_nt","High_nt","Low_nt","Close_nt","Volume_nt"]].copy()
            lo_df["DateTime"] = lo_df["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            ro_df["DateTime"] = ro_df["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            lo_df = lo_df.rename(columns={c: c.replace("_sc", "") for c in lo_df.columns if "_sc" in c})
            ro_df = ro_df.rename(columns={c: c.replace("_nt", "") for c in ro_df.columns if "_nt" in c})
            with uc1:
                st.caption(f"In {left_label}, missing from {right_label}")
                st.dataframe(lo_df, use_container_width=True, hide_index=True)
            with uc2:
                st.caption(f"In {right_label}, missing from {left_label}")
                st.dataframe(ro_df, use_container_width=True, hide_index=True)

    excl_dates: set = set()
    if show_excl_shading:
        if not all(incl_days):
            dow_excl = {i for i, inc in enumerate(incl_days) if not inc}
            excl_dates |= {d for d in matched_full["DateTime"].dt.date.unique()
                           if pd.Timestamp(d).dayofweek in dow_excl}
        if not events_df.empty and event_filter_mode == "Skip full day":
            excl_dates |= set(events_df["DateTime"].dt.date)

    t1, t2, t3, t4 = st.tabs([
        "🔎 Mismatch Table", "🕐 Time of Day", "📅 By Date", "📊 Delta Distribution",
    ])
    with t1:
        _show_mismatch_table(matched, excl_volume,
                              gate_key=gate_key, left_label=left_label, right_label=right_label)
    with t2:
        _show_time_of_day(matched_full, excl_first_n=excl_first_n, excl_last_min=excl_last_min,
                          show_shading=show_excl_shading, show_commentary=show_commentary)
    with t3:
        _show_by_date(matched_full, events_df,
                      excl_dates=excl_dates if show_excl_shading else None,
                      show_commentary=show_commentary)
    with t4:
        _show_delta_distribution(matched, excl_volume)


# ── Tab entry point ───────────────────────────────────────────────────────────

def show_validation_tab(sc_file: str = "", nt_file: str = ""):
    # ── Data Sources ──────────────────────────────────────────────────────────
    with st.expander("📁 Data Sources", expanded=True):
        uc1, uc2, uc3 = st.columns(3)

        py_bars = st.session_state.get("uploaded_sc_bars")
        if py_bars is not None:
            n_py   = py_bars["DateTime"].dt.date.nunique()
            py_lbl = st.session_state.get("scid_loaded_label", "loaded")
            uc1.success(f"**Python 5M**  ·  {py_lbl}  ·  {n_py} days")
        else:
            uc1.info("**Python 5M**\nLoad SCID quarters in Bar Analysis")

        sc5m_file = uc2.file_uploader(
            "SC 5M export (.csv/.txt)", type=["csv", "txt"], key="bv_sc5m_upload",
            help="SC: Analysis → Export Chart Data → 5-Min bars → CSV",
        )
        if sc5m_file:
            k = f"{sc5m_file.name}_{sc5m_file.size}"
            if st.session_state.get("bv_sc5m_key") != k:
                try:
                    parsed = parse_sc_ohlc_from_upload(sc5m_file)
                    st.session_state["bv_sc5m_bars"] = parsed
                    st.session_state["bv_sc5m_key"]  = k
                except Exception as e:
                    uc2.error(str(e))
            if "bv_sc5m_bars" in st.session_state:
                n = st.session_state["bv_sc5m_bars"]["DateTime"].dt.date.nunique()
                uc2.caption(f"✅ {sc5m_file.name}  ·  {n} days")
        else:
            st.session_state.pop("bv_sc5m_bars", None)
            st.session_state.pop("bv_sc5m_key",  None)

        nt5m_file = uc3.file_uploader(
            "NT8 5M export (.csv/.txt)", type=["csv", "txt"], key="bv_nt5m_upload",
            help="NT8 OHLCV bar export — semicolon-separated, bar close times",
        )
        if nt5m_file:
            k = f"{nt5m_file.name}_{nt5m_file.size}"
            if st.session_state.get("bv_nt5m_key") != k:
                try:
                    parsed = parse_ohlc_from_upload(nt5m_file)
                    st.session_state["bv_nt5m_bars"] = parsed
                    st.session_state["bv_nt5m_key"]  = k
                except Exception as e:
                    uc3.error(str(e))
            if "bv_nt5m_bars" in st.session_state:
                n = st.session_state["bv_nt5m_bars"]["DateTime"].dt.date.nunique()
                uc3.caption(f"✅ {nt5m_file.name}  ·  {n} days")
        else:
            st.session_state.pop("bv_nt5m_bars", None)
            st.session_state.pop("bv_nt5m_key",  None)

    # ── Gate availability ─────────────────────────────────────────────────────
    py_bars = st.session_state.get("uploaded_sc_bars")
    sc_bars = st.session_state.get("bv_sc5m_bars")
    nt_bars = st.session_state.get("bv_nt5m_bars")

    gate1_ok = py_bars is not None and sc_bars is not None
    gate2_ok = sc_bars is not None and nt_bars is not None

    if not gate1_ok and not gate2_ok:
        st.info(
            "**Gate 1** — Python 5M vs SC 5M: load SCID quarters (Bar Analysis) + upload SC 5M export above  \n"
            "**Gate 2** — SC 5M vs NT8 5M: upload SC 5M export + NT8 5M export above"
        )
        return

    # ── Shared filters ────────────────────────────────────────────────────────
    if "vt_initialized" not in st.session_state:
        for k, v in _load_filter_defaults().items():
            st.session_state.setdefault(k, v)
        st.session_state["vt_initialized"] = True

    with st.expander("⚙️ Filters", expanded=False):
        tc1, tc2 = st.columns(2)
        excl_holidays   = tc1.checkbox("Exclude NYSE holidays", key="f_excl_holidays",
                                        value=st.session_state.get("f_excl_holidays", True),
                                        help="Removes NYSE holiday sessions (Memorial Day etc.).")
        show_commentary = tc2.checkbox("Show commentary",        key="f_show_commentary",
                                        value=st.session_state.get("f_show_commentary", True))
        st.divider()
        st.markdown("**Display**")
        dc1, dc2 = st.columns(2)
        excl_volume       = dc1.checkbox("Ignore volume differences",      key="f_excl_volume",
                                          value=st.session_state.get("f_excl_volume", False))
        show_excl_shading = dc2.checkbox("Shade excluded zones on charts", key="f_show_excl_shading",
                                          value=st.session_state.get("f_show_excl_shading", True))
        st.divider()
        st.markdown("**Session Boundaries**")
        sb1, sb2 = st.columns(2)
        excl_first_n  = sb1.slider("Exclude first N bars",   0, 12,
                                    st.session_state.get("f_excl_first_n",  0), 1, key="f_excl_first_n")
        excl_last_min = sb2.slider("Exclude last N minutes", 0, 90,
                                    st.session_state.get("f_excl_last_min", 0), 5, key="f_excl_last_min")
        st.divider()
        st.markdown("**Day of Week**")
        st.caption("Include days:")
        dw1, dw2, dw3, dw4, dw5 = st.columns(5)
        incl_mon = dw1.checkbox("Mon", key="f_incl_mon", value=st.session_state.get("f_incl_mon", True))
        incl_tue = dw2.checkbox("Tue", key="f_incl_tue", value=st.session_state.get("f_incl_tue", True))
        incl_wed = dw3.checkbox("Wed", key="f_incl_wed", value=st.session_state.get("f_incl_wed", True))
        incl_thu = dw4.checkbox("Thu", key="f_incl_thu", value=st.session_state.get("f_incl_thu", True))
        incl_fri = dw5.checkbox("Fri", key="f_incl_fri", value=st.session_state.get("f_incl_fri", True))
        st.divider()
        st.markdown("**Economic Events**")
        if not fred_key_configured():
            st.info("FOMC dates built-in. For NFP/CPI add `FRED_API_KEY` to `.streamlit/secrets.toml`.")
        ea, eb, ec = st.columns(3)
        use_fomc = ea.checkbox("FOMC", key="f_use_fomc", value=st.session_state.get("f_use_fomc", False))
        use_nfp  = eb.checkbox("NFP",  key="f_use_nfp",  value=st.session_state.get("f_use_nfp",  False),
                                disabled=not fred_key_configured())
        use_cpi  = ec.checkbox("CPI",  key="f_use_cpi",  value=st.session_state.get("f_use_cpi",  False),
                                disabled=not fred_key_configured())
        event_types = tuple(
            e for e, on in [("FOMC", use_fomc), ("NFP", use_nfp), ("CPI", use_cpi)] if on
        )
        ef1, ef2 = st.columns([1, 2])
        _efm_default = st.session_state.get("f_event_filter_mode", "Skip full day")
        event_filter_mode = ef1.radio(
            "Filter mode", ["Skip full day", "Window ±N minutes"],
            index=["Skip full day", "Window ±N minutes"].index(_efm_default),
            key="f_event_filter_mode",
            help="**Skip full day:** removes all RTH bars on event dates.\n\n"
                 "**Window:** removes bars within N minutes of the announcement.",
        )
        event_window = 30
        if event_filter_mode == "Window ±N minutes":
            event_window = ef2.slider("Minutes before/after", 15, 180,
                                       st.session_state.get("f_event_window", 30), 15,
                                       key="f_event_window")
        st.divider()
        if st.button("💾 Save as Default"):
            _save_filter_defaults({
                "f_excl_holidays": excl_holidays, "f_show_commentary": show_commentary,
                "f_excl_volume": excl_volume, "f_show_excl_shading": show_excl_shading,
                "f_excl_first_n": excl_first_n, "f_excl_last_min": excl_last_min,
                "f_incl_mon": incl_mon, "f_incl_tue": incl_tue,
                "f_incl_wed": incl_wed, "f_incl_thu": incl_thu, "f_incl_fri": incl_fri,
                "f_use_fomc": use_fomc, "f_use_nfp": use_nfp, "f_use_cpi": use_cpi,
                "f_event_filter_mode": event_filter_mode, "f_event_window": event_window,
            })
            st.success("Defaults saved.", icon="✅")

    st.session_state["excl_first_n"]  = excl_first_n
    st.session_state["excl_last_min"] = excl_last_min

    # ── Gate tabs ─────────────────────────────────────────────────────────────
    filter_kwargs = dict(
        excl_holidays=excl_holidays, show_commentary=show_commentary,
        excl_volume=excl_volume, show_excl_shading=show_excl_shading,
        excl_first_n=excl_first_n, excl_last_min=excl_last_min,
        incl_days=(incl_mon, incl_tue, incl_wed, incl_thu, incl_fri),
        event_types=event_types, event_filter_mode=event_filter_mode, event_window=event_window,
    )

    gate_labels = []
    if gate1_ok:
        gate_labels.append("Gate 1 — Python vs SC")
    if gate2_ok:
        gate_labels.append("Gate 2 — SC vs NT8")

    gate_tabs = st.tabs(gate_labels)
    tab_idx = 0

    if gate1_ok:
        with gate_tabs[tab_idx]:
            _show_gate_body(py_bars, sc_bars,
                            left_label="Python 5M (SCID)", right_label="SC 5M",
                            gate_key="g1", **filter_kwargs)
        tab_idx += 1

    if gate2_ok:
        with gate_tabs[tab_idx]:
            _show_gate_body(sc_bars, nt_bars,
                            left_label="SC 5M", right_label="NT8 5M",
                            gate_key="g2", **filter_kwargs)


# ── Sub-view functions ────────────────────────────────────────────────────────

def _show_field_table(matched: pd.DataFrame, excl_volume: bool = False):
    if matched.empty:
        st.info("No matched bars in range.")
        return

    n = len(matched)
    rows = []
    for col in PRICE_FIELDS:
        d     = matched[f"Δ{col}"].dropna()
        wrong = d[d.ne(0)]
        rows.append({
            "Field":       col,
            "Unit":        "ticks",
            "Total":       n,
            "✓ Exact":    int(d.eq(0).sum()),
            "✗ Mismatch": int(len(wrong)),
            "Match %":    f"{d.eq(0).sum() / n * 100:.2f}%" if n else "—",
            "Min Δ":      f"{int(wrong.min()):+d}"          if len(wrong) else "—",
            "Max Δ":      f"{int(wrong.max()):+d}"          if len(wrong) else "—",
            "Mean |Δ|":   f"{wrong.abs().mean():.2f}"       if len(wrong) else "—",
        })
    if not excl_volume:
        d     = matched["ΔVolume"].dropna()
        wrong = d[d.ne(0)]
        rows.append({
            "Field":       "Volume",
            "Unit":        "contracts",
            "Total":       n,
            "✓ Exact":    int(d.eq(0).sum()),
            "✗ Mismatch": int(len(wrong)),
            "Match %":    f"{d.eq(0).sum() / n * 100:.2f}%" if n else "—",
            "Min Δ":      f"{int(wrong.min()):+,}"          if len(wrong) else "—",
            "Max Δ":      f"{int(wrong.max()):+,}"          if len(wrong) else "—",
            "Mean |Δ|":   f"{wrong.abs().mean():.0f}"       if len(wrong) else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _show_mismatch_table(matched: pd.DataFrame, excl_volume: bool = False,
                          gate_key: str = "g0",
                          left_label: str = "SC", right_label: str = "NT"):
    _info(
        f"Every bar where at least one OHLC field differs between {left_label} and {right_label}. "
        f"Δ is expressed in ticks ({right_label} − {left_label}). "
        f"🟠 = {right_label} higher, 🔴 = {right_label} lower. "
        "Toggle below to also show bars that match perfectly."
    )
    show_all = st.checkbox("Show all matched bars (not just mismatches)", value=False,
                            key=f"{gate_key}_show_all_mm")
    subset   = matched if show_all else matched[~matched["OHLC_match"]]

    if subset.empty:
        st.success("No OHLC mismatches in the selected range." if not show_all else "No matched bars.")
        return

    display_cols = ["DateTime"]
    for c in PRICE_FIELDS:
        display_cols += [f"{c}_sc", f"{c}_nt", f"Δ{c}"]
    if not excl_volume:
        display_cols += ["Volume_sc", "Volume_nt", "ΔVolume"]

    display = subset[display_cols].copy()
    display["DateTime"] = display["DateTime"].dt.strftime("%Y-%m-%d %H:%M")

    la = left_label.replace(" ", "")[:5]
    ra = right_label.replace(" ", "")[:5]
    rename = {f"{c}_sc": f"{c}_{la}" for c in PRICE_FIELDS}
    rename |= {f"{c}_nt": f"{c}_{ra}" for c in PRICE_FIELDS}
    if not excl_volume:
        rename["Volume_sc"] = f"Vol_{la}"
        rename["Volume_nt"] = f"Vol_{ra}"
    display = display.rename(columns=rename)

    def _color_delta(val):
        try:
            v = float(val)
            if v == 0: return ""
            return "color: #d62728" if v < 0 else "color: #ff9800"
        except (TypeError, ValueError):
            return ""

    price_fmt = {f"{c}_{la}": "{:.2f}" for c in PRICE_FIELDS}
    price_fmt |= {f"{c}_{ra}": "{:.2f}" for c in PRICE_FIELDS}
    delta_fmt  = {f"Δ{c}": "{:+.0f}" for c in PRICE_FIELDS}
    vol_fmt    = {"ΔVolume": "{:+.0f}", f"Vol_{la}": "{:.0f}", f"Vol_{ra}": "{:.0f}"}
    delta_cols = list(delta_fmt.keys()) + (["ΔVolume"] if not excl_volume else [])

    fmt = price_fmt | delta_fmt | (vol_fmt if not excl_volume else {})
    styled = display.style.map(_color_delta, subset=delta_cols).format(fmt)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)
    caption = f"Showing {len(subset):,} bars  |  Δ in ticks for OHLC"
    if not excl_volume:
        caption += "  |  Δ in contracts for Volume"
    st.caption(caption)


def _show_time_of_day(matched: pd.DataFrame,
                      excl_first_n: int = 0, excl_last_min: int = 0,
                      show_shading: bool = False, show_commentary: bool = True):
    if matched.empty:
        st.info("No matched bars.")
        return

    if show_commentary:
        _info(
            "Shows which 5-minute bar slots have the most OHLC mismatches across all trading days. "
            "The orange line is the mismatch rate (mismatches ÷ total bars at that slot). "
            "**What to look for:** spikes at 08:30 (opening bar) and 14:45–15:10 (close) are normal. "
            "A spike in the middle of the session would suggest a systematic data problem worth investigating."
        )

    tod = (
        matched.groupby("BarTime", sort=True)
        .agg(Total=("OHLC_match", "count"), OHLC_MM=("OHLC_match", lambda x: (~x).sum()))
        .reset_index()
    )
    tod["Rate%"] = (tod["OHLC_MM"] / tod["Total"] * 100).round(1)

    y_max   = max(int(tod["OHLC_MM"].max()), 1)
    y_range = y_max * 1.4

    fig = go.Figure()

    # Excluded zone shading — overlay bars clipped by explicit y range
    if show_shading and (excl_first_n > 0 or excl_last_min > 0):
        excl_times: set = set()
        if excl_first_n > 0:
            excl_times |= {f"{(8*60+30+i*5)//60:02d}:{(8*60+30+i*5)%60:02d}" for i in range(excl_first_n)}
        if excl_last_min > 0:
            cutoff = 15*60+15 - excl_last_min
            excl_times |= {f"{m//60:02d}:{m%60:02d}" for m in range(cutoff, 15*60+15, 5)}
        excl_in_tod = [t for t in tod["BarTime"] if t in excl_times]
        if excl_in_tod:
            fig.add_bar(
                x=excl_in_tod, y=[y_range * 20] * len(excl_in_tod),
                marker=dict(color="rgba(180,180,180,0.18)", line_width=0),
                name="Excluded", hoverinfo="skip", showlegend=True,
            )

    fig.add_bar(x=tod["BarTime"], y=tod["OHLC_MM"], name="OHLC Mismatches", marker_color="#ef5350")
    fig.add_scatter(
        x=tod["BarTime"], y=tod["Rate%"], name="Mismatch Rate %",
        mode="lines+markers", yaxis="y2",
        line=dict(color="#ff9800", width=2), marker=dict(size=4),
    )
    y2_max = max(tod["Rate%"].max() * 1.3, 5)
    fig.update_layout(
        barmode="overlay",
        title="OHLC Mismatches by Bar Time Slot",
        xaxis_title="Bar Open Time (CT)", yaxis_title="# Mismatches",
        yaxis=dict(range=[0, y_range]),
        yaxis2=dict(title="Mismatch Rate %", overlaying="y", side="right", range=[0, y2_max]),
        xaxis=dict(tickangle=-45, categoryorder="category ascending"),
        template="plotly_white", height=420,
        legend=dict(x=0.01, y=0.99),
    )
    st.plotly_chart(fig, use_container_width=True)

    if show_commentary:
        _time_of_day_commentary(tod)

    worst = tod[tod["OHLC_MM"] > 0].sort_values("Rate%", ascending=False)
    if not worst.empty:
        with st.expander(f"Detail table — {len(worst)} slots with at least one mismatch"):
            st.dataframe(
                worst.rename(columns={"BarTime": "Time (CT)", "Total": "Total Bars", "OHLC_MM": "Mismatches", "Rate%": "Rate %"}),
                use_container_width=True, hide_index=True,
            )


def _show_by_date(matched: pd.DataFrame, events_df: pd.DataFrame | None = None,
                  excl_dates: set | None = None, show_commentary: bool = True):
    if matched.empty:
        st.info("No matched bars.")
        return

    has_events = events_df is not None and not events_df.empty
    if show_commentary:
        _info(
            "Shows total OHLC mismatches per trading day. "
            "**What to look for:** a smooth low count across all days = random noise. "
            "A single day dominating = a data event (feed outage, rollover issue, or bad export). "
            "Percentage labels show mismatch rate for days with at least one mismatch."
            + (" Coloured vertical lines mark economic events."
               if has_events else "")
        )

    by_date = (
        matched.groupby("Date")
        .agg(Total=("OHLC_match", "count"), OHLC_MM=("OHLC_match", lambda x: (~x).sum()))
        .reset_index()
    )
    by_date["Rate%"] = (by_date["OHLC_MM"] / by_date["Total"] * 100).round(1)
    by_date["Date"]  = pd.to_datetime(by_date["Date"])

    y_max_d  = max(int(by_date["OHLC_MM"].max()), 1)
    y_range_d = y_max_d * 1.4

    fig = go.Figure()

    # Excluded date shading — overlay bars clipped by explicit y range
    if excl_dates:
        excl_ts = [pd.Timestamp(d) for d in sorted(excl_dates)]
        fig.add_bar(
            x=excl_ts, y=[y_range_d * 20] * len(excl_ts),
            marker=dict(color="rgba(180,180,180,0.18)", line_width=0),
            name="Excluded", hoverinfo="skip", showlegend=True,
        )

    fig.add_bar(
        x=by_date["Date"], y=by_date["OHLC_MM"],
        name="Mismatches", marker_color="#ef5350",
        text=by_date.apply(lambda r: f"{r['Rate%']:.0f}%" if r["OHLC_MM"] > 0 else "", axis=1),
        textposition="outside",
    )

    # Event markers — one vertical line per event, coloured by type
    if has_events:
        shown_labels = set()
        for _, ev in events_df.iterrows():
            ev_date = pd.Timestamp(ev["DateTime"].date())
            label   = ev["EventType"]
            fig.add_vline(
                x=ev_date.timestamp() * 1000,  # plotly expects ms epoch for date axes
                line_dash="dash",
                line_color=ev["Color"],
                line_width=1.5,
                annotation_text=label if label not in shown_labels else "",
                annotation_position="top",
                annotation_font_size=10,
            )
            shown_labels.add(label)

        # Legend entries for event types
        for etype, color in EVENT_COLOR.items():
            if etype in events_df["EventType"].values:
                fig.add_scatter(
                    x=[None], y=[None], mode="lines",
                    name=etype,
                    line=dict(color=color, dash="dash", width=1.5),
                )

    fig.update_layout(
        barmode="overlay",
        title="OHLC Mismatches per Trading Day",
        xaxis_title="Date", yaxis_title="# Mismatched Bars",
        yaxis=dict(range=[0, y_range_d]),
        template="plotly_white", height=440,
        xaxis=dict(tickformat="%b %d", tickangle=-45),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)

    if show_commentary:
        _by_date_commentary(by_date)

    worst = by_date[by_date["OHLC_MM"] > 0].sort_values("OHLC_MM", ascending=False)
    if not worst.empty:
        with st.expander(f"Detail table — {len(worst)} days with at least one mismatch"):
            st.dataframe(
                worst.assign(Date=worst["Date"].dt.strftime("%a %b %d, %Y"))
                     .rename(columns={"Total": "Bars", "OHLC_MM": "Mismatches", "Rate%": "Rate %"}),
                use_container_width=True, hide_index=True,
            )


def _show_delta_distribution(matched: pd.DataFrame, excl_volume: bool = False):
    if matched.empty:
        st.info("No matched bars.")
        return

    _info(
        "For every delta value observed, how many bars had that exact difference. "
        "Δ is in ticks for OHLC (1 tick = 0.25 pts), contracts for Volume. "
        "The field summary table at the top of this page has the match rates."
    )

    # ── Delta value counts (OHLC) ──────────────────────────────────────────────
    field_vc: dict = {}
    all_deltas: set = set()
    for col in PRICE_FIELDS:
        nz = matched[f"Δ{col}"].dropna()
        nz = nz[nz.ne(0)]
        vc = nz.value_counts().to_dict()
        field_vc[col] = vc
        all_deltas.update(vc.keys())

    if all_deltas:
        tbl_rows = []
        for delta in sorted(all_deltas):
            row = {"Δ (ticks)": f"{int(delta):+d}"}
            for col in PRICE_FIELDS:
                cnt = field_vc[col].get(delta, 0)
                row[col] = int(cnt) if cnt > 0 else "—"
            tbl_rows.append(row)
        st.caption("OHLC mismatch count by delta value (mismatched bars only)")
        st.dataframe(pd.DataFrame(tbl_rows), use_container_width=True, hide_index=True)
    else:
        st.success("All OHLC fields match exactly across every bar.")

    _delta_distribution_commentary(matched)

    # ── Volume delta value counts ──────────────────────────────────────────────
    if not excl_volume:
        vol_nz = matched["ΔVolume"].dropna()
        vol_nz = vol_nz[vol_nz.ne(0)]
        if len(vol_nz) > 0:
            vol_vc = vol_nz.value_counts().sort_index()
            vol_tbl = pd.DataFrame({
                "Δ Volume (contracts)": vol_vc.index.astype(int),
                "Count": vol_vc.values,
            })
            st.caption(f"Volume delta distribution — {len(vol_nz):,} mismatched bars")
            st.dataframe(vol_tbl, use_container_width=True, hide_index=True)
            _info(
                "Volume differences are expected and harmless for a price-based strategy. "
                "SC sums raw tick-level volumes; NT records broker-feed volume (Rithmic/CQG). "
                "The two feeds count trades at bar boundaries differently and may include/exclude spread legs."
            )
