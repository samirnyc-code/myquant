"""MenthorQ gamma/blind-spot levels tab."""

from pathlib import Path
import re
import time
import json

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

CSV_PATH  = Path("data/menthorq/menthorq_levels.csv")
RAW_DIR   = Path("data/menthorq/raw")
BARS_PQ   = Path("data/bars/_continuous.parquet")
ROLLS_CSV = Path("data/nt_rollovers_export.csv")
CRED_FILE = Path.home() / ".menthorq" / "session.txt"
NONCE_FILE = Path.home() / ".menthorq" / "nonce.txt"

SLUGS = ["key_levels", "bl_levels", "levels_tv", "netgex"]
TICKER = "es1!"

AJAX_URL = "https://menthorq.com/wp-admin/admin-ajax.php"
HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://menthorq.com",
    "referer": "https://menthorq.com/account/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "x-requested-with": "XMLHttpRequest",
}

# ── colours ──────────────────────────────────────────────────────────────────
C_CALL     = "#2196F3"   # blue  — call resistance
C_PUT      = "#F44336"   # red   — put support
C_HVL      = "#FF9800"   # amber — HVL
C_BL       = "#9C27B0"   # purple — blind spots
C_GEX      = "#4CAF50"   # green — GEX strikes
C_1D       = "#607D8B"   # grey  — 1D max/min


# ── helpers ──────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _load_bars_parquet() -> pd.DataFrame | None:
    """Fallback bar source: back-adjusted continuous 5M parquet."""
    if not BARS_PQ.exists():
        return None
    b = pd.read_parquet(BARS_PQ)
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    return b


@st.cache_data(show_spinner=False)
def _front_offset(date_str: str) -> float:
    """Back-adjusted-continuous minus front-contract price on `date`.

    MQ levels are front-contract prices; the continuous parquet is back-adjusted
    to the CURRENT front, so bars on dates before a roll sit higher by the sum
    of all roll offsets after that date (e.g. ESH6 period +111.00, ESM6 +61.25).
    Subtract this from bars to plot them in MQ price space.
    """
    if not ROLLS_CSV.exists():
        return 0.0
    r = pd.read_csv(ROLLS_CSV, parse_dates=["rollover_date"])
    r = r[(r["instrument"] == "ES") & r["offset"].notna()]
    d = pd.Timestamp(date_str)
    return float(r.loc[r["rollover_date"] > d, "offset"].sum())


def _load_df() -> pd.DataFrame | None:
    if not CSV_PATH.exists():
        return None
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date")
    # coerce numeric columns
    num_skip = {"date", "contract", "gamma_condition", "distance_to_hvl_%",
                "total_gex", "net_gex", "expiring_gex", "total_dex", "net_dex"}
    for c in df.columns:
        if c not in num_skip:
            converted = pd.to_numeric(df[c], errors="coerce")
            if converted.notna().sum() > 0:
                df[c] = converted
    # parse M/B GEX strings to float
    for c in ["total_gex", "net_gex", "expiring_gex", "total_dex", "net_dex"]:
        if c in df.columns:
            df[c + "_num"] = (
                df[c].astype(str)
                .str.replace("M", "e6").str.replace("B", "e9")
                .apply(lambda x: float(x) if x not in ("nan", "") else float("nan"))
            )
    return df


def _load_cookies() -> dict:
    if not CRED_FILE.exists():
        return {}
    raw = CRED_FILE.read_text().strip()
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def _load_nonce() -> str:
    if NONCE_FILE.exists():
        return NONCE_FILE.read_text().strip()
    return "0e760b6ec4"


def _parse_row(d: str, results: dict) -> dict:
    row = {"date": d}
    kl_data = results["key_levels"]["data"]["resource"]["data"]
    for k, v in kl_data.items():
        col = k.lower().replace(" ", "_").replace(".", "").replace("/", "_")
        row[col] = v
    bl_txt = results["bl_levels"]["data"]["resource"]["text_data"]
    bls = dict(re.findall(r"BL (\d+), ([\d.]+)", bl_txt))
    for i in range(1, 11):
        row[f"bl_{i}"] = float(bls[str(i)]) if str(i) in bls else None
    tv_txt = results["levels_tv"]["data"]["resource"]["text_data"]
    tv_pairs = {k.strip(): v for k, v in re.findall(r"([A-Za-z0-9 /]+?),\s*([\d.]+)(?=,|$)", tv_txt)}
    row["hvl_0dte"]        = float(tv_pairs["HVL 0DTE"]) if "HVL 0DTE" in tv_pairs else None
    row["gamma_wall_0dte"] = float(tv_pairs["Gamma Wall 0DTE"]) if "Gamma Wall 0DTE" in tv_pairs else None
    for i in range(1, 11):
        key = f"GEX {i}"
        row[f"gex_{i}"] = float(tv_pairs[key]) if key in tv_pairs else None
    ng_data = results["netgex"]["data"]["resource"].get("data", {})
    strikes = ng_data.get("Top Net GEX Strikes", [])
    for i, s in enumerate(strikes[:3], 1):
        row[f"top_gex_strike_{i}"] = s
    return row


def _fetch_today(nonce: str) -> dict | None:
    import datetime
    d = datetime.date.today().isoformat()
    cookies = _load_cookies()
    if not cookies:
        return None
    sess = requests.Session()
    sess.cookies.update(cookies)

    results = {}
    for slug in SLUGS:
        try:
            r = sess.post(AJAX_URL, headers=HEADERS, timeout=20, data={
                "action": "get_command", "security": nonce,
                "command_slug": slug, "date": d,
                "is_intraday": "false", "ticker": TICKER,
            })
            j = r.json()
            if not j.get("success"):
                return {"error": j.get("data", {}).get("message", "unknown"), "slug": slug}
            results[slug] = j
            time.sleep(0.6)
        except Exception as e:
            return {"error": str(e), "slug": slug}

    # ticker call
    try:
        r = sess.post(AJAX_URL, headers=HEADERS, timeout=20, data={
            "action": "get_ticker", "security": nonce,
            "ticker": TICKER, "date": d,
            "auto_fallback": "false", "mode": "eod",
        })
        j = r.json()
        if not j.get("success"):
            return {"error": j.get("data", {}).get("message", "unknown"), "slug": "ticker"}
        results["ticker"] = j
    except Exception as e:
        return {"error": str(e), "slug": "ticker"}

    # save raw
    day_dir = RAW_DIR / d
    day_dir.mkdir(parents=True, exist_ok=True)
    for slug, jdata in results.items():
        (day_dir / f"{slug}.json").write_text(json.dumps(jdata, indent=2))

    # parse + append to CSV
    td = results["ticker"]["data"]["ticker_data"]
    liq = td.get("liq_snapshot", {})
    qs  = td.get("qscore_data") or {}
    row = _parse_row(d, results)
    row["contract"]        = liq.get("Contract")
    row["pc_oi"]           = liq.get("P/C OI")
    row["gamma_condition"] = liq.get("Gamma Condition")
    exp = liq.get("1D Exp Move %", "")
    row["exp_move_1d_pct"] = re.sub(r"[^\d.]", "", exp) or None
    for part in ["option_score", "momentum_score", "volatility_score", "seasonality_score"]:
        sub = qs.get(part) or {}
        row[part] = sub.get(part)

    df_new = pd.DataFrame([row])
    if CSV_PATH.exists():
        df_old = pd.read_csv(CSV_PATH)
        df_old = df_old[df_old["date"] != d]
        df_combined = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_combined = df_new
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_combined.to_csv(CSV_PATH, index=False)
    return {"ok": True, "date": d}


# ── price ladder + candlestick chart ─────────────────────────────────────────

def _build_chart(
    row: pd.Series,
    bars: pd.DataFrame | None,
    show_call: bool,
    show_call_0dte: bool,
    show_hvl: bool,
    show_hvl_0dte: bool,
    show_put: bool,
    show_put_0dte: bool,
    show_1d: bool,
    show_bl: bool,
    show_gex: bool,
    show_gamma_wall: bool,
) -> go.Figure:

    fig = go.Figure()

    # ── candlestick bars for the selected date ────────────────────────────────
    if bars is not None and not bars.empty:
        fig.add_trace(go.Candlestick(
            x=bars["DateTime"],
            open=bars["Open"], high=bars["High"],
            low=bars["Low"],   close=bars["Close"],
            name="ES 5M",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
            increasing_fillcolor="#26a69a",
            decreasing_fillcolor="#ef5350",
            line_width=1,
        ))
        use_time_axis = True
        x0_line, x1_line = bars["DateTime"].iloc[0], bars["DateTime"].iloc[-1]
        xref = "x"
        x_annot = bars["DateTime"].iloc[-1]
    else:
        use_time_axis = False
        x0_line, x1_line = 0, 1
        xref = "paper"
        x_annot = 1.0

    # ── level definitions ─────────────────────────────────────────────────────
    level_groups = []

    if show_call:
        level_groups.append(("Call Res",    row.get("call_resistance"),      C_CALL, "solid", 2))
    if show_call_0dte:
        level_groups.append(("Call Res 0DTE", row.get("call_resistance_0dte"), C_CALL, "dot", 1))
    if show_gamma_wall:
        level_groups.append(("Gamma Wall 0DTE", row.get("gamma_wall_0dte"),  C_CALL, "dash", 1))
    if show_hvl:
        level_groups.append(("HVL",         row.get("high_vol_level"),       C_HVL,  "solid", 2))
    if show_hvl_0dte:
        level_groups.append(("HVL 0DTE",    row.get("hvl_0dte"),             C_HVL,  "dot", 1))
    if show_put:
        level_groups.append(("Put Support", row.get("put_support"),          C_PUT,  "solid", 2))
    if show_put_0dte:
        level_groups.append(("Put Sup 0DTE", row.get("put_support_0dte"),    C_PUT,  "dot", 1))
    if show_1d:
        level_groups.append(("1D Max",      row.get("1d_max"),               C_1D,   "dash", 1))
        level_groups.append(("1D Min",      row.get("1d_min"),               C_1D,   "dash", 1))
    if show_bl:
        for i in range(1, 11):
            level_groups.append((f"BL {i}", row.get(f"bl_{i}"),             C_BL,   "dot", 1))
    if show_gex:
        for i in range(1, 11):
            level_groups.append((f"GEX {i}", row.get(f"gex_{i}"),           C_GEX,  "dot", 1))

    # draw levels
    all_level_prices = []
    for label, val, color, dash, width in level_groups:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        price = float(val)
        all_level_prices.append(price)
        fig.add_shape(
            type="line",
            x0=x0_line, x1=x1_line, y0=price, y1=price,
            line=dict(color=color, dash=dash, width=width),
            xref=xref, yref="y",
        )
        fig.add_annotation(
            x=x_annot, y=price,
            xref=xref, yref="y",
            text=f"<b>{label}</b> {price:.2f}",
            showarrow=False,
            font=dict(size=10, color=color),
            xanchor="left", yanchor="middle",
            xshift=8,
        )

    # ── y-axis range: union of bars and levels ────────────────────────────────
    all_prices = list(all_level_prices)
    if bars is not None and not bars.empty:
        all_prices += [bars["Low"].min(), bars["High"].max()]
    if all_prices:
        y_min = min(all_prices) - 20
        y_max = max(all_prices) + 20
    else:
        y_min, y_max = 0, 1

    fig.update_layout(
        height=700,
        margin=dict(l=20, r=180, t=30, b=20),
        yaxis=dict(range=[y_min, y_max], showgrid=True, gridcolor="#2a2a2a"),
        xaxis=dict(
            rangeslider_visible=False,
            showgrid=True, gridcolor="#2a2a2a",
            type="date" if use_time_axis else "linear",
        ),
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        showlegend=False,
    )
    return fig


# ── QScore badge ─────────────────────────────────────────────────────────────

def _score_color(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "#888"
    if v <= 1:  return "#F44336"
    if v <= 2:  return "#FF9800"
    if v == 3:  return "#FFC107"
    if v == 4:  return "#8BC34A"
    return "#4CAF50"


def _gamma_badge(gc: str) -> str:
    color = "#4CAF50" if str(gc).lower() == "positive" else "#F44336"
    return f'<span style="background:{color};padding:2px 10px;border-radius:4px;font-weight:bold">{gc}</span>'


# ── main tab ─────────────────────────────────────────────────────────────────

def show_menthorq_tab():
    st.header("MenthorQ — ES1! Gamma & Blind Spot Levels")

    df = _load_df()

    if df is None or df.empty:
        st.warning("No data found. Run `scripts/menthorq_backfill.py` first.")
        return

    # ── refresh button ────────────────────────────────────────────────────────
    col_btn, col_status = st.columns([1, 4])
    with col_btn:
        if st.button("Refresh Today's Data", type="primary"):
            nonce = _load_nonce()
            with st.spinner("Fetching today from MenthorQ..."):
                result = _fetch_today(nonce)
            if result is None:
                st.error("No session cookie found at ~/.menthorq/session.txt")
            elif "error" in result:
                st.error(f"Fetch failed on {result['slug']}: {result['error']}")
                st.info("Your session cookie may have expired. Re-paste a fresh cURL from DevTools and update ~/.menthorq/session.txt")
            else:
                st.success(f"Added {result['date']} to dataset.")
                st.rerun()
    with col_status:
        latest = df["date"].max()
        import datetime
        days_old = (pd.Timestamp(datetime.date.today()) - latest).days
        if days_old == 0:
            st.success(f"Data is current through today ({latest.date()})")
        elif days_old == 1:
            st.info(f"Data through {latest.date()} — missing today")
        else:
            st.warning(f"Data through {latest.date()} — {days_old} days behind")

    st.divider()

    # ── date picker ───────────────────────────────────────────────────────────
    dates = df["date"].dt.date.tolist()
    selected_date = st.select_slider(
        "Date", options=dates, value=dates[-1],
        format_func=lambda d: d.strftime("%b %d, %Y"),
    )
    row = df[df["date"].dt.date == selected_date].iloc[0]

    # ── headline strip ────────────────────────────────────────────────────────
    gc = row.get("gamma_condition", "")
    st.markdown(
        f"**{selected_date.strftime('%A, %B %d %Y')}** &nbsp;|&nbsp; "
        f"Gamma Condition: {_gamma_badge(gc)} &nbsp;|&nbsp; "
        f"Contract: **{row.get('contract','')}** &nbsp;|&nbsp; "
        f"P/C OI: **{row.get('pc_oi','')}** &nbsp;|&nbsp; "
        f"IV30: **{row.get('implied_vol_30d','')}%** &nbsp;|&nbsp; "
        f"Exp Move: **±{row.get('exp_move_1d_pct','')}%**",
        unsafe_allow_html=True,
    )

    # QScore badges
    q_cols = st.columns(4)
    for col, (label, key) in zip(q_cols, [
        ("Option", "option_score"), ("Momentum", "momentum_score"),
        ("Volatility", "volatility_score"), ("Seasonality", "seasonality_score"),
    ]):
        v = row.get(key)
        color = _score_color(v)
        col.markdown(
            f'<div style="text-align:center;padding:8px;background:#1e1e2e;border-radius:6px">'
            f'<div style="font-size:11px;color:#aaa">{label}</div>'
            f'<div style="font-size:28px;font-weight:bold;color:{color}">{v if pd.notna(v) else "—"}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── level toggles ─────────────────────────────────────────────────────────
    st.subheader("Level Toggles")
    t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.columns(9)
    show_call       = t1.checkbox("Call Res",     value=True,  key="mq_call")
    show_call_0dte  = t2.checkbox("Call 0DTE",    value=False, key="mq_call0")
    show_hvl        = t3.checkbox("HVL",          value=True,  key="mq_hvl")
    show_hvl_0dte   = t4.checkbox("HVL 0DTE",     value=False, key="mq_hvl0")
    show_put        = t5.checkbox("Put Sup",      value=True,  key="mq_put")
    show_put_0dte   = t6.checkbox("Put 0DTE",     value=False, key="mq_put0")
    show_1d         = t7.checkbox("1D Max/Min",   value=True,  key="mq_1d")
    show_bl         = t8.checkbox("Blind Spots",  value=True,  key="mq_bl")
    show_gex        = t9.checkbox("GEX Strikes",  value=True,  key="mq_gex")
    show_gamma_wall = st.checkbox("Gamma Wall 0DTE", value=False, key="mq_gwall")

    # ── load 5M bars for the selected date ───────────────────────────────────
    bars_day = None
    _bar_status = ""
    try:
        from data_loader import load_csv_cache, load_csv_manifest
        mf = load_csv_manifest()

        # priority: SC 5M upload → NT 5M upload → nt_cont manifest cache
        bars_all = (
            st.session_state.get("data_sc_5m")
            or st.session_state.get("data_nt_5m")
        )
        _bar_source = "session"
        if bars_all is None:
            for slot in ("nt_cont", "sc_5m", "nt_5m"):
                if slot in mf:
                    info = mf[slot]
                    bars_all = load_csv_cache(slot, info["name"], info["size"])
                    _bar_source = f"cache:{slot}"
                    if bars_all is not None:
                        break

        _roll_adjust = False
        if bars_all is None:
            # final fallback: repo continuous parquet (back-adjusted -> needs
            # roll-offset correction into MQ front-contract price space)
            bars_all = _load_bars_parquet()
            if bars_all is not None:
                _bar_source = "parquet:_continuous"
                _roll_adjust = True

        if bars_all is not None:
            # ensure DateTime column exists
            dt_col = next((c for c in bars_all.columns if "datetime" in c.lower() or c.lower() == "time"), None)
            if dt_col and dt_col != "DateTime":
                bars_all = bars_all.rename(columns={dt_col: "DateTime"})
            bars_all["DateTime"] = pd.to_datetime(bars_all["DateTime"])

            d_start = pd.Timestamp(selected_date)
            d_end   = d_start + pd.Timedelta(days=1)
            bars_day = bars_all[
                (bars_all["DateTime"] >= d_start) &
                (bars_all["DateTime"] <  d_end)
            ].copy()
            if bars_day.empty:
                _bar_status = f"No bars for {selected_date} in {_bar_source} (data spans {bars_all['DateTime'].min().date()} – {bars_all['DateTime'].max().date()})"
                bars_day = None
            elif _roll_adjust:
                off = _front_offset(str(selected_date))
                if off:
                    for c in ("Open", "High", "Low", "Close"):
                        bars_day[c] = bars_day[c] - off
                    _bar_status = f"bars from {_bar_source}, roll-adjusted −{off:g} pts to front-contract (MQ) prices"
                else:
                    _bar_status = f"bars from {_bar_source} (current front, no adjustment)"
        else:
            _bar_status = "No bar data found in session state or manifest cache"
    except Exception as e:
        _bar_status = f"Bar load error: {e}"
        bars_day = None

    # ── chart + tables ────────────────────────────────────────────────────────
    col_chart, col_tables = st.columns([2, 1])

    with col_chart:
        title = "5M Bars + Gamma Levels" if bars_day is not None else "Gamma Level Ladder"
        st.subheader(title)
        if bars_day is None and _bar_status:
            st.caption(f"Bars not shown — {_bar_status}")
        elif bars_day is not None and _bar_status:
            st.caption(_bar_status)
        fig = _build_chart(
            row, bars_day,
            show_call, show_call_0dte,
            show_hvl, show_hvl_0dte,
            show_put, show_put_0dte,
            show_1d, show_bl, show_gex, show_gamma_wall,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_tables:
        st.subheader("Key Levels")
        kl_data = {
            "Call Resistance":    row.get("call_resistance"),
            "Call Res 0DTE":      row.get("call_resistance_0dte"),
            "Gamma Wall 0DTE":    row.get("gamma_wall_0dte"),
            "HVL":                row.get("high_vol_level"),
            "HVL 0DTE":           row.get("hvl_0dte"),
            "Put Support":        row.get("put_support"),
            "Put Support 0DTE":   row.get("put_support_0dte"),
            "1D Max":             row.get("1d_max"),
            "1D Min":             row.get("1d_min"),
            "Net GEX":            row.get("net_gex"),
            "Total GEX":          row.get("total_gex"),
        }
        st.dataframe(
            pd.DataFrame(list(kl_data.items()), columns=["Level", "Value"]),
            hide_index=True, use_container_width=True,
        )

        st.subheader("Blind Spots")
        bl_rows = [(f"BL {i}", row.get(f"bl_{i}")) for i in range(1, 11)]
        st.dataframe(
            pd.DataFrame(bl_rows, columns=["Level", "Price"]),
            hide_index=True, use_container_width=True,
        )

        st.subheader("Top GEX Strikes")
        gex_rows = [(f"GEX {i}", row.get(f"gex_{i}")) for i in range(1, 11)]
        st.dataframe(
            pd.DataFrame(gex_rows, columns=["Rank", "Strike"]),
            hide_index=True, use_container_width=True,
        )

    st.divider()

    # ── historical table ──────────────────────────────────────────────────────
    with st.expander("Full Historical Table", expanded=False):
        display_cols = [
            "date", "gamma_condition", "call_resistance", "high_vol_level",
            "put_support", "net_gex", "bl_1", "bl_2", "bl_3",
            "gex_1", "gex_2", "gex_3",
            "option_score", "momentum_score", "volatility_score", "seasonality_score",
        ]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[display_cols].sort_values("date", ascending=False).reset_index(drop=True),
            use_container_width=True,
        )

    # ── regime chart ──────────────────────────────────────────────────────────
    with st.expander("Gamma Regime History", expanded=False):
        df2 = df.copy()
        df2["regime_num"] = df2["gamma_condition"].map({"Positive": 1, "Negative": -1}).fillna(0)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=df2["date"], y=df2["regime_num"],
            marker_color=df2["regime_num"].map({1: C_GEX, -1: C_PUT, 0: "#888"}),
            name="Gamma Condition",
        ))
        fig2.add_trace(go.Scatter(
            x=df2["date"], y=df2["volatility_score"],
            mode="lines", name="Vol Score", yaxis="y2",
            line=dict(color=C_HVL, width=2),
        ))
        fig2.update_layout(
            height=300,
            yaxis=dict(tickvals=[-1, 1], ticktext=["Negative", "Positive"]),
            yaxis2=dict(overlaying="y", side="right", range=[0, 5], title="Vol Score"),
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            margin=dict(l=20, r=60, t=20, b=20),
            legend=dict(orientation="h"),
        )
        st.plotly_chart(fig2, use_container_width=True)
