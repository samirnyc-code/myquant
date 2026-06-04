import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from data_loader import load_sc_bars, load_nt_bars, get_market_holidays, NT_FILE, TICK_SIZE

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


def _summary_commentary(n_matched, n_sc_only, n_nt_only, pct_ohlc, pct_ohlcv, n_ohlc_mm):
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

    vol_note = (
        f" Volume exact match ({pct_ohlcv:.1f}%) is lower than OHLC match — "
        f"this is normal. Volume differences come from different data feed sources "
        f"counting ticks at bar boundaries differently. For a price-based strategy it does not affect signal generation."
    )

    _info(f"{health} {n_ohlc_mm:,} of {n_matched:,} bars have at least one OHLC field that differs.{vol_note}{unmatched_note}")


def _field_table_commentary(matched: pd.DataFrame):
    if matched.empty:
        return
    open_mm  = int(matched["ΔOpen"].ne(0).sum())
    high_mm  = int(matched["ΔHigh"].ne(0).sum())
    low_mm   = int(matched["ΔLow"].ne(0).sum())
    close_mm = int(matched["ΔClose"].ne(0).sum())
    vol_mm   = int(matched["ΔVolume"].ne(0).sum())

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

    c1, c2, c3 = st.columns([1, 1, 2])
    date_from      = c1.date_input("From", value=overlap_min, min_value=all_min, max_value=all_max)
    date_to        = c2.date_input("To",   value=overlap_max, min_value=all_min, max_value=all_max)
    exclude_holidays = c3.checkbox(
        "Exclude NYSE market holidays",
        value=True,
        help="Uses the NYSE calendar (exchange-calendars). Removes days like Memorial Day where "
             "there is no proper RTH session even though CME Globex may have thin trading."
    )

    sc_f = sc[(sc_dates >= date_from) & (sc_dates <= date_to)]
    nt_f = nt[(nt_dates >= date_from) & (nt_dates <= date_to)]

    # Cut NT at the last SC bar: SC was downloaded mid-session, NT after close.
    last_sc_dt = sc_f["DateTime"].max()
    nt_f = nt_f[nt_f["DateTime"] <= last_sc_dt].copy()

    comp    = build_comparison(sc_f, nt_f)

    # Holiday exclusion — applied after merge so unmatched holiday bars are visible
    # when the checkbox is off, but excluded from all stats when on.
    holidays = get_market_holidays(str(date_from), str(date_to))
    n_holiday_bars = int((comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)).sum())
    if exclude_holidays and holidays:
        comp = comp[~comp["DateTime"].dt.strftime("%Y-%m-%d").isin(holidays)].copy()

    matched = comp[comp["Status"] == "Matched"]

    n_matched  = len(matched)
    n_sc_only  = int((comp["Status"] == "SC only").sum())
    n_nt_only  = int((comp["Status"] == "NT only").sum())
    n_ohlc_mm  = int((~matched["OHLC_match"]).sum())   if n_matched else 0
    n_vol_mm   = int(matched["ΔVolume"].ne(0).sum())   if n_matched else 0
    n_ohlcv_mm = int((~matched["OHLCV_match"]).sum())  if n_matched else 0
    pct_ohlc   = (1 - n_ohlc_mm  / n_matched) * 100   if n_matched else 0.0
    pct_ohlcv  = (1 - n_ohlcv_mm / n_matched) * 100   if n_matched else 0.0

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.subheader("Summary")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Matched Bars",      f"{n_matched:,}")
    m2.metric("SC Only",           f"{n_sc_only:,}")
    m3.metric("NT Only",           f"{n_nt_only:,}")
    m4.metric("OHLC Exact Match",  f"{pct_ohlc:.1f}%")
    m5.metric("OHLCV Exact Match", f"{pct_ohlcv:.1f}%")

    m6, m7, m8, m9, _ = st.columns(5)
    m6.metric("OHLC Mismatches",  f"{n_ohlc_mm:,}")
    m7.metric("Vol Mismatches",   f"{n_vol_mm:,}")
    m8.metric("OHLCV Mismatches", f"{n_ohlcv_mm:,}")
    if exclude_holidays:
        m9.metric("Holiday Bars Excluded", f"{n_holiday_bars:,}")

    _summary_commentary(n_matched, n_sc_only, n_nt_only, pct_ohlc, pct_ohlcv, n_ohlc_mm)

    # ── Field breakdown ────────────────────────────────────────────────────────
    st.subheader("Mismatch by Field")
    _info(
        "Each row shows how many bars matched exactly vs differed, and the range of the difference in ticks "
        "(OHLC) or contracts (Volume). A tick on ES = 0.25 points = $12.50."
    )
    _show_field_table(matched)
    _field_table_commentary(matched)

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
        _show_mismatch_table(matched)
    with t2:
        _show_time_of_day(matched)
    with t3:
        _show_by_date(matched)
    with t4:
        _show_delta_distribution(matched)


# ── Sub-view functions ────────────────────────────────────────────────────────

def _show_field_table(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars in range.")
        return

    rows = []
    for col in PRICE_FIELDS:
        d     = matched[f"Δ{col}"].dropna()
        wrong = d[d.ne(0)]
        rows.append({
            "Field":       col,
            "Unit":        "ticks",
            "✓ Correct":  int(d.eq(0).sum()),
            "✗ Mismatch": int(len(wrong)),
            "Min Δ":      f"{wrong.min():.0f}"       if len(wrong) else "—",
            "Max Δ":      f"{wrong.max():.0f}"       if len(wrong) else "—",
            "Mean |Δ|":   f"{wrong.abs().mean():.2f}" if len(wrong) else "—",
        })
    d     = matched["ΔVolume"].dropna()
    wrong = d[d.ne(0)]
    rows.append({
        "Field":       "Volume",
        "Unit":        "contracts",
        "✓ Correct":  int(d.eq(0).sum()),
        "✗ Mismatch": int(len(wrong)),
        "Min Δ":      f"{wrong.min():.0f}"       if len(wrong) else "—",
        "Max Δ":      f"{wrong.max():.0f}"       if len(wrong) else "—",
        "Mean |Δ|":   f"{wrong.abs().mean():.0f}" if len(wrong) else "—",
    })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _show_mismatch_table(matched: pd.DataFrame):
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

    price_fmt = {f"{c}_{s}": "{:.2f}" for c in PRICE_FIELDS for s in ("sc", "nt")}
    delta_fmt = {f"Δ{c}": "{:+.0f}" for c in PRICE_FIELDS}
    delta_cols = list(delta_fmt.keys()) + ["ΔVolume"]

    styled = (
        display.style
        .map(_color_delta, subset=delta_cols)
        .format(price_fmt | delta_fmt | {"ΔVolume": "{:+.0f}", "Volume_sc": "{:.0f}", "Volume_nt": "{:.0f}"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=420)
    st.caption(f"Showing {len(subset):,} bars  |  Δ in ticks for OHLC  |  Δ in contracts for Volume")


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


def _show_by_date(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    _info(
        "Shows total OHLC mismatches per trading day. "
        "**What to look for:** a smooth low count across all days = random noise. "
        "A single day dominating = a data event (feed outage, rollover issue, or bad export). "
        "Percentage labels show mismatch rate for days with at least one mismatch."
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
    fig.update_layout(
        title="OHLC Mismatches per Trading Day",
        xaxis_title="Date", yaxis_title="# Mismatched Bars",
        template="plotly_white", height=420,
        xaxis=dict(tickformat="%b %d", tickangle=-45),
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


def _show_delta_distribution(matched: pd.DataFrame):
    if matched.empty:
        st.info("No matched bars.")
        return

    _info(
        "Each panel shows the distribution of NT − SC differences for bars where that field mismatched. "
        "Every field has its own independent scale so a field with 2 mismatches is just as readable as one with 135. "
        "The exact count table below shows precise numbers for every delta value observed."
    )

    # ── 1. Stacked bar: match vs mismatch count per field ─────────────────────
    zero_counts    = {c: int(matched[f"Δ{c}"].dropna().eq(0).sum()) for c in PRICE_FIELDS}
    nonzero_counts = {c: int(matched[f"Δ{c}"].dropna().ne(0).sum()) for c in PRICE_FIELDS}

    fig0 = go.Figure()
    fig0.add_bar(x=PRICE_FIELDS, y=[zero_counts[c]    for c in PRICE_FIELDS],
                 name="Δ = 0 (exact match)", marker_color="#26a69a")
    fig0.add_bar(x=PRICE_FIELDS, y=[nonzero_counts[c] for c in PRICE_FIELDS],
                 name="Δ ≠ 0 (mismatch)",   marker_color="#ef5350")
    fig0.update_layout(
        barmode="stack", title="Exact Match vs Mismatch Count per Field",
        xaxis_title="Field", yaxis_title="# Bars",
        template="plotly_white", height=280,
        legend=dict(orientation="h", y=1.15),
    )
    st.plotly_chart(fig0, use_container_width=True)

    # ── 2. 2×2 subplot grid — one panel per field, independent y-axes ─────────
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=[
            f"{c}  ({nonzero_counts[c]} mismatches)" for c in PRICE_FIELDS
        ],
        horizontal_spacing=0.14,
        vertical_spacing=0.24,
    )
    for i, col in enumerate(PRICE_FIELDS):
        r, c_idx = divmod(i, 2)
        vals    = matched[f"Δ{col}"].dropna()
        nonzero = vals[vals.ne(0)]
        if len(nonzero) > 0:
            counts = nonzero.value_counts().sort_index()
            fig.add_bar(
                x=counts.index.astype(int),
                y=counts.values,
                name=col,
                marker_color=FIELD_COLORS[col],
                showlegend=False,
                row=r + 1, col=c_idx + 1,
            )
        else:
            # empty panel — add invisible point so axes render
            fig.add_scatter(
                x=[0], y=[0], mode="markers",
                marker=dict(opacity=0, size=1),
                showlegend=False,
                row=r + 1, col=c_idx + 1,
            )
        fig.update_xaxes(title_text="NT − SC (ticks)", tickformat="+d",
                         dtick=1, row=r + 1, col=c_idx + 1)
        fig.update_yaxes(title_text="Count", row=r + 1, col=c_idx + 1)

    fig.update_layout(
        title="OHLC Delta Distribution — Mismatched Bars Only (independent scales)",
        template="plotly_white",
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── 3. Exact value-counts table ────────────────────────────────────────────
    field_vc = {}
    all_deltas: set = set()
    for col in PRICE_FIELDS:
        nonzero = matched[f"Δ{col}"].dropna()
        nonzero = nonzero[nonzero.ne(0)]
        vc = nonzero.value_counts().to_dict()
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
        st.caption("Exact mismatch count per delta value per field")
        st.dataframe(pd.DataFrame(tbl_rows), use_container_width=True, hide_index=True)

    _delta_distribution_commentary(matched)

    # ── 4. Volume ──────────────────────────────────────────────────────────────
    vol_nz = matched["ΔVolume"].dropna()
    vol_nz = vol_nz[vol_nz.ne(0)]
    if len(vol_nz) > 0:
        fig2 = go.Figure()
        fig2.add_histogram(x=vol_nz, name="Volume",
                           marker_color=FIELD_COLORS["Volume"], nbinsx=50)
        fig2.update_layout(
            title=f"Volume Delta — {len(vol_nz):,} mismatched bars (NT − SC, contracts)",
            xaxis_title="NT − SC (contracts)", yaxis_title="Count",
            template="plotly_white", height=300,
        )
        st.plotly_chart(fig2, use_container_width=True)
        _info(
            "Volume differences are expected and harmless for a price-based strategy. "
            "SC sums raw tick-level volumes; NT records broker-feed volume (Rithmic/CQG). "
            "The two feeds count trades at bar boundaries differently and may include/exclude spread legs."
        )
