import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from data_loader import load_sc_bars, load_nt_bars, get_market_holidays, NT_FILE, TICK_SIZE
from economic_calendar import get_economic_events, fred_key_configured, EVENT_COLOR

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
    sc_m = sc.rename(columns={c: f"{c}_sc" for c in ALL_FIELDS}).set_index("DateTime")
    nt_m = nt.rename(columns={c: f"{c}_nt" for c in ALL_FIELDS}).set_index("DateTime")

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


# ── Tab entry point ───────────────────────────────────────────────────────────

def show_validation_tab():
    if not NT_FILE.exists():
        st.error(f"NT data file not found:\n`{NT_FILE}`")
        return

    sc = load_sc_bars()
    nt = load_nt_bars()

    sc_dates = sc["DateTime"].dt.date
    nt_dates = nt["DateTime"].dt.date
    overlap_min = max(sc_dates.min(), nt_dates.min())
    overlap_max = min(sc_dates.max(), nt_dates.max())
    all_min     = min(sc_dates.min(), nt_dates.min())
    all_max     = max(sc_dates.max(), nt_dates.max())

    # ── Date range ────────────────────────────────────────────────────────────
    dc1, dc2 = st.columns(2)
    date_from = dc1.date_input("From", value=overlap_min, min_value=all_min, max_value=all_max)
    date_to   = dc2.date_input("To",   value=overlap_max, min_value=all_min, max_value=all_max)

    # ── Filter toggles ────────────────────────────────────────────────────────
    st.markdown("**Filters**")
    fc1, fc2, fc3, fc4 = st.columns(4)
    excl_holidays  = fc1.checkbox(
        "Exclude NYSE holidays", value=True,
        help="Removes days like Memorial Day where there is no proper RTH session "
             "(NYSE calendar via exchange-calendars)."
    )
    excl_first_bar = fc2.checkbox(
        "Exclude first bar (08:30)", value=False,
        help="The opening bar has the highest mismatch rate due to opening auction noise. "
             "Toggle off to see clean mid-session agreement."
    )
    excl_late      = fc3.checkbox(
        "Exclude last 45 min (14:30–15:15)", value=False,
        help="Closing bars have elevated mismatches from end-of-session order flow and "
             "settlement handling differences between feeds."
    )
    excl_volume    = fc4.checkbox(
        "Ignore volume differences", value=False,
        help="Hides volume from all stats and tables. Useful when you've already confirmed "
             "volume differences are expected and want to focus on OHLC only."
    )

    sc_f = sc[(sc_dates >= date_from) & (sc_dates <= date_to)]
    nt_f = nt[(nt_dates >= date_from) & (nt_dates <= date_to)]

    # Cut NT at the last SC bar: SC was downloaded mid-session, NT after close.
    last_sc_dt = sc_f["DateTime"].max()
    nt_f = nt_f[nt_f["DateTime"] <= last_sc_dt].copy()

    comp = build_comparison(sc_f, nt_f)

    # ── Existing filters ───────────────────────────────────────────────────────
    holidays = get_market_holidays(str(date_from), str(date_to))
    n_holiday_bars = int((comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)).sum())
    if excl_holidays and holidays:
        comp = comp[~comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)].copy()
    if excl_first_bar:
        comp = comp[comp["BarTime"] != "08:30"].copy()
    if excl_late:
        comp = comp[comp["BarTime"] < "14:30"].copy()

    # ── Economic event filters ─────────────────────────────────────────────────
    with st.expander("📅 Economic Event Filters", expanded=False):
        if not fred_key_configured():
            st.info(
                "FOMC dates are built-in. For NFP and CPI, add your free FRED API key to "
                "`.streamlit/secrets.toml`: `FRED_API_KEY = 'your_key'`  "
                "([Register free at fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html))"
            )
        ea, eb, ec = st.columns(3)
        use_fomc = ea.checkbox("FOMC",  value=False)
        use_nfp  = eb.checkbox("NFP",   value=False, disabled=not fred_key_configured())
        use_cpi  = ec.checkbox("CPI",   value=False, disabled=not fred_key_configured())

        event_types = tuple(
            e for e, on in [("FOMC", use_fomc), ("NFP", use_nfp), ("CPI", use_cpi)] if on
        )

        ef1, ef2 = st.columns([1, 2])
        event_filter_mode = ef1.radio(
            "Filter mode",
            ["Skip full day", "Window ±N minutes"],
            index=0,
            help=(
                "**Skip full day:** removes all RTH bars on event dates.\n\n"
                "**Window:** removes bars within N minutes of announcement time.\n\n"
                "⚠️ NFP/CPI are released at 7:30 CT — before RTH opens at 8:30 CT. "
                "A window < 60 min has no effect on RTH bars. Use 'Skip full day' for those."
            ),
        )
        event_window = 30
        if event_filter_mode == "Window ±N minutes":
            event_window = ef2.slider("Minutes before/after", 15, 180, 30, 15)

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

    matched = comp[comp["Status"] == "Matched"]

    n_matched  = len(matched)
    n_sc_only  = int((comp["Status"] == "SC only").sum())
    n_nt_only  = int((comp["Status"] == "NT only").sum())
    n_ohlc_mm  = int((~matched["OHLC_match"]).sum())  if n_matched else 0
    n_vol_mm   = int(matched["ΔVolume"].ne(0).sum())  if n_matched else 0
    pct_ohlc   = (1 - n_ohlc_mm / n_matched) * 100   if n_matched else 0.0

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.subheader("Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Matched Bars",     f"{n_matched:,}")
    m2.metric("SC Only",          f"{n_sc_only:,}")
    m3.metric("NT Only",          f"{n_nt_only:,}")
    m4.metric("OHLC Exact Match", f"{pct_ohlc:.1f}%",
              help="Bars where ALL four OHLC fields match simultaneously. "
                   "Lower than per-field rates in the table below because one wrong field "
                   "makes the whole bar a mismatch.")
    m5.metric("OHLC Mismatches",  f"{n_ohlc_mm:,}")

    secondary = []
    if not excl_volume:
        secondary.append(("Vol Mismatches",       f"{n_vol_mm:,}"))
    if excl_holidays and n_holiday_bars:
        secondary.append(("Holiday Bars Excl.",   f"{n_holiday_bars:,}"))
    if n_event_bars:
        secondary.append(("Event Bars Excl.",     f"{n_event_bars:,}"))
    if secondary:
        cols = st.columns(5)
        for i, (label, val) in enumerate(secondary[:5]):
            cols[i].metric(label, val)

    _summary_commentary(n_matched, n_sc_only, n_nt_only, pct_ohlc, pct_ohlc, n_ohlc_mm, excl_volume)

    # ── Field breakdown ────────────────────────────────────────────────────────
    st.subheader("Mismatch by Field")
    _info(
        "Each row shows how many bars matched exactly vs differed, and the range of the difference in ticks "
        "(OHLC) or contracts (Volume). A tick on ES = 0.25 points = $12.50. "
        "**Note:** the OHLC Exact Match % above is lower than all four individual field rates — "
        "that is correct. The summary counts a bar as a mismatch if *any* of the four fields differ, "
        "so it is always ≤ the lowest individual field rate."
    )
    _show_field_table(matched, excl_volume)
    _field_table_commentary(matched, excl_volume)

    # ── Unmatched bars ─────────────────────────────────────────────────────────
    null_vol = nt_f[nt_f["NullVol"]].copy()
    n_null_vol = len(null_vol)
    if n_null_vol > 0:
        null_vol["DateTime"] = null_vol["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
        with st.expander(f"⚠️ NT bars with null Volume (filled as 0) — {n_null_vol} bar{'s' if n_null_vol > 1 else ''}"):
            st.caption("These bars existed in the NT file with no volume value. Volume was set to 0 for comparison purposes.")
            st.dataframe(null_vol[["DateTime", "Open", "High", "Low", "Close"]], use_container_width=True, hide_index=True)

    if n_sc_only > 0 or n_nt_only > 0:
        with st.expander(f"Unmatched bars — SC only: {n_sc_only}  |  NT only: {n_nt_only}"):
            _info(
                "Bars that exist in one source but not the other. Common causes: different session start/end handling, "
                "one feed missing ticks on a particular day, or a rollover gap."
            )
            # Flag NYSE holidays still present (only visible when checkbox is off)
            all_unmatched_dates = set(
                comp[comp["Status"] != "Matched"]["DateTime"].dt.strftime("%Y-%m-%d")
            )
            holiday_dates_present = all_unmatched_dates & holidays
            if holiday_dates_present:
                st.warning(
                    f"📅 NYSE holiday bars present in unmatched list: "
                    f"{', '.join(sorted(holiday_dates_present))}. "
                    f"Enable 'Exclude NYSE market holidays' above to remove them."
                )

            uc1, uc2 = st.columns(2)
            sc_only = comp[comp["Status"] == "SC only"][["DateTime","Open_sc","High_sc","Low_sc","Close_sc","Volume_sc"]].copy()
            nt_only = comp[comp["Status"] == "NT only"][["DateTime","Open_nt","High_nt","Low_nt","Close_nt","Volume_nt"]].copy()
            sc_only["DateTime"] = sc_only["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            nt_only["DateTime"] = nt_only["DateTime"].dt.strftime("%Y-%m-%d %H:%M")
            with uc1:
                st.caption("In SC, missing from NT")
                st.dataframe(sc_only, use_container_width=True, hide_index=True)
            with uc2:
                st.caption("In NT, missing from SC")
                st.dataframe(nt_only, use_container_width=True, hide_index=True)

    # ── Sub-views ──────────────────────────────────────────────────────────────
    t1, t2, t3, t4 = st.tabs([
        "🔎 Mismatch Table",
        "🕐 Time of Day",
        "📅 By Date",
        "📊 Delta Distribution",
    ])
    with t1:
        _show_mismatch_table(matched, excl_volume)
    with t2:
        _show_time_of_day(matched)
    with t3:
        _show_by_date(matched, events_df)
    with t4:
        _show_delta_distribution(matched, excl_volume)


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


def _show_mismatch_table(matched: pd.DataFrame, excl_volume: bool = False):
    _info(
        "Every bar where at least one OHLC field differs between SC and NT. "
        "Δ is expressed in ticks (NT − SC). 🟠 = NT higher, 🔴 = NT lower. "
        "Toggle below to also show bars that match perfectly."
    )
    show_all = st.checkbox("Show all matched bars (not just mismatches)", value=False)
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

    def _color_delta(val):
        try:
            v = float(val)
            if v == 0: return ""
            return "color: #d62728" if v < 0 else "color: #ff9800"
        except (TypeError, ValueError):
            return ""

    price_fmt  = {f"{c}_{s}": "{:.2f}" for c in PRICE_FIELDS for s in ("sc", "nt")}
    delta_fmt  = {f"Δ{c}": "{:+.0f}" for c in PRICE_FIELDS}
    vol_fmt    = {"ΔVolume": "{:+.0f}", "Volume_sc": "{:.0f}", "Volume_nt": "{:.0f}"}
    delta_cols = list(delta_fmt.keys()) + (["ΔVolume"] if not excl_volume else [])

    fmt = price_fmt | delta_fmt | (vol_fmt if not excl_volume else {})
    styled = display.style.map(_color_delta, subset=delta_cols).format(fmt)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)
    caption = f"Showing {len(subset):,} bars  |  Δ in ticks for OHLC"
    if not excl_volume:
        caption += "  |  Δ in contracts for Volume"
    st.caption(caption)


def _show_time_of_day(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

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

    fig = go.Figure()
    fig.add_bar(x=tod["BarTime"], y=tod["OHLC_MM"], name="OHLC Mismatches", marker_color="#ef5350")
    fig.add_scatter(
        x=tod["BarTime"], y=tod["Rate%"], name="Mismatch Rate %",
        mode="lines+markers", yaxis="y2",
        line=dict(color="#ff9800", width=2), marker=dict(size=4),
    )
    y2_max = max(tod["Rate%"].max() * 1.3, 5)
    fig.update_layout(
        title="OHLC Mismatches by Bar Time Slot",
        xaxis_title="Bar Open Time (CT)", yaxis_title="# Mismatches",
        yaxis2=dict(title="Mismatch Rate %", overlaying="y", side="right", range=[0, y2_max]),
        xaxis=dict(tickangle=-45),
        template="plotly_white", height=420,
        legend=dict(x=0.01, y=0.99),
    )
    st.plotly_chart(fig, use_container_width=True)

    _time_of_day_commentary(tod)

    worst = tod[tod["OHLC_MM"] > 0].sort_values("Rate%", ascending=False)
    if not worst.empty:
        with st.expander(f"Detail table — {len(worst)} slots with at least one mismatch"):
            st.dataframe(
                worst.rename(columns={"BarTime": "Time (CT)", "Total": "Total Bars", "OHLC_MM": "Mismatches", "Rate%": "Rate %"}),
                use_container_width=True, hide_index=True,
            )


def _show_by_date(matched: pd.DataFrame, events_df: pd.DataFrame | None = None):
    if matched.empty:
        st.info("No matched bars.")
        return

    has_events = events_df is not None and not events_df.empty
    _info(
        "Shows total OHLC mismatches per trading day. "
        "**What to look for:** a smooth low count across all days = random noise. "
        "A single day dominating = a data event (feed outage, rollover issue, or bad export). "
        "Percentage labels show mismatch rate for days with at least one mismatch."
        + (" Coloured vertical lines mark economic events (use the Economic Event Filters expander above)."
           if has_events else "")
    )

    by_date = (
        matched.groupby("Date")
        .agg(Total=("OHLC_match", "count"), OHLC_MM=("OHLC_match", lambda x: (~x).sum()))
        .reset_index()
    )
    by_date["Rate%"] = (by_date["OHLC_MM"] / by_date["Total"] * 100).round(1)
    by_date["Date"]  = pd.to_datetime(by_date["Date"])

    fig = go.Figure()
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
        title="OHLC Mismatches per Trading Day",
        xaxis_title="Date", yaxis_title="# Mismatched Bars",
        template="plotly_white", height=440,
        xaxis=dict(tickformat="%b %d", tickangle=-45),
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig, use_container_width=True)

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
