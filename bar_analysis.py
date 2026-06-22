import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from pathlib import Path

from data_loader import load_sc_bars, load_sc_ticks, get_market_holidays, TICK_SIZE, bar_num_from_dt
from economic_calendar import get_economic_events, fred_key_configured, EVENT_COLOR
import indicators as ind
from simulation_engine import (
    INSTRUMENTS, RTH_END_MIN, _EMPTY_TRADE,
    simulate_trades, compute_summary, friction_ledger,
    _simulate_one, _simulate_one_bars,
    _simulate_one_multileg, _simulate_one_bars_multileg,
    _simulate_one_3leg, _simulate_one_bars_3leg,
    _resimulate_bars, _snap_level,
)

_BA_DEFAULTS_FILE = Path(__file__).parent / "ba_filter_defaults.json"


def _load_ba_defaults() -> dict:
    if _BA_DEFAULTS_FILE.exists():
        try:
            return json.loads(_BA_DEFAULTS_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_ba_defaults(d: dict):
    _BA_DEFAULTS_FILE.write_text(json.dumps(d, indent=2))


# ── CSV parser ────────────────────────────────────────────────────────────────

def parse_signals(raw: str) -> pd.DataFrame | None:
    """Parse MC signals text.
    Format: Num  Type  Dir  DD/MM/YYYY  HH:MM:SS  BarNum  Price  Stop
    """
    rows = []
    for line in raw.strip().splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            rows.append({
                "SignalNum":   int(parts[0]),
                "SignalType":  parts[1],
                "Direction":   parts[2],
                "DateTime":    pd.to_datetime(f"{parts[3]} {parts[4]}", dayfirst=True),
                "BarNum":      int(parts[5]),
                "SignalPrice": float(parts[6].replace(",", "")),
                "StopPrice":   float(parts[7].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["Date"] = df["DateTime"].dt.date
    return df.sort_values("SignalNum").reset_index(drop=True)


# ── Filter logic ──────────────────────────────────────────────────────────────

def apply_signal_filters(
    signals: pd.DataFrame,
    date_from, date_to,
    excl_holidays: bool,
    incl_dow: list,          # [mon, tue, wed, thu, fri]
    excl_first_n: int,
    excl_last_min: int,
    event_types: tuple,
    event_filter_mode: str,
    event_window: int,
    excluded_types: set,     # SignalType values to filter out (unchecked in UI)
    direction: str,          # "Both", "Long", "Short"
) -> pd.DataFrame:
    df = signals.copy()
    df["FilterStatus"] = "ok"

    # Date range
    df.loc[(df["Date"] < date_from) | (df["Date"] > date_to), "FilterStatus"] = "date_range"

    # Signal type
    if excluded_types:
        df.loc[(df["FilterStatus"] == "ok") & (df["SignalType"].isin(excluded_types)),
               "FilterStatus"] = "signal_type"

    # Direction
    if direction != "Both":
        df.loc[(df["FilterStatus"] == "ok") & (df["Direction"] != direction),
               "FilterStatus"] = "direction"

    # NYSE holidays
    if excl_holidays:
        hols = get_market_holidays(str(date_from), str(date_to))
        hol_mask = df["DateTime"].dt.strftime("%Y-%m-%d").isin(hols)
        df.loc[(df["FilterStatus"] == "ok") & hol_mask, "FilterStatus"] = "holiday"

    # Day of week
    dow_map  = {i: v for i, v in enumerate(incl_dow)}
    excl_dow = ~df["DateTime"].dt.dayofweek.map(dow_map).fillna(False)
    df.loc[(df["FilterStatus"] == "ok") & excl_dow, "FilterStatus"] = "dow"

    # Session: first N bars  (BarNum is 1-indexed session bar; signal time = bar close)
    if excl_first_n > 0:
        df.loc[(df["FilterStatus"] == "ok") & (df["BarNum"] <= excl_first_n),
               "FilterStatus"] = "first_bars"

    # Session: last N minutes
    if excl_last_min > 0:
        cutoff_min  = RTH_END_MIN - excl_last_min
        cutoff_time = pd.Timestamp(f"{cutoff_min // 60:02d}:{cutoff_min % 60:02d}:00").time()
        late_mask   = df["DateTime"].dt.time >= cutoff_time
        df.loc[(df["FilterStatus"] == "ok") & late_mask, "FilterStatus"] = "last_bars"

    # Economic events
    if event_types:
        events_df = get_economic_events(event_types, str(date_from), str(date_to))
        if not events_df.empty:
            if event_filter_mode == "Skip full day":
                ev_dates = set(events_df["DateTime"].dt.date)
                df.loc[(df["FilterStatus"] == "ok") & df["Date"].isin(ev_dates),
                       "FilterStatus"] = "event"
            else:
                ev_mask = pd.Series(False, index=df.index)
                for _, ev in events_df.iterrows():
                    dt = ev["DateTime"]
                    ev_mask |= (
                        (df["DateTime"] >= dt - pd.Timedelta(minutes=event_window)) &
                        (df["DateTime"] <= dt + pd.Timedelta(minutes=event_window))
                    )
                df.loc[(df["FilterStatus"] == "ok") & ev_mask, "FilterStatus"] = "event"

    return df


def apply_regime_population_filters(
    df: pd.DataFrame,
    tags: pd.DataFrame,
    want_er: bool,
    er_min: float,
    want_balance: bool,
    want_inside: bool,
    skip_trend: bool,
    want_er10: bool = False,
    er10_min: float = 0.30,
) -> pd.DataFrame:
    """Mark FilterStatus for rows excluded by the regime population gates.

    `tags` carries the look-ahead-safe columns ER_intra_2 / ER_intra_6 /
    balance_state / prior_inside_day / prior_adr_ext (from indicators.tag_signals),
    aligned to `df.index`. Only rows currently "ok" can be excluded — these stack
    AFTER the session/event filters, like every other status. NaN readings fail the
    keep gates (conservative, matching the research's fillna(0) on ER) and are NOT
    treated as trend days for the skip. ER gates run first (primary chop filters;
    balance/inside are secondary boosters on top).
    """
    if not (want_er or want_er10 or want_balance or want_inside or skip_trend):
        return df
    t = tags.reindex(df.index)
    if want_er:
        bad = (df["FilterStatus"] == "ok") & ~(t["ER_intra_6"] >= er_min)
        df.loc[bad, "FilterStatus"] = "low_er"
    if want_er10:
        bad = (df["FilterStatus"] == "ok") & ~(t["ER_intra_2"] >= er10_min)
        df.loc[bad, "FilterStatus"] = "low_er10"
    if want_balance:
        bad = (df["FilterStatus"] == "ok") & ~t["balance_state"].fillna(False)
        df.loc[bad, "FilterStatus"] = "not_balance"
    if want_inside:
        bad = (df["FilterStatus"] == "ok") & ~t["prior_inside_day"].fillna(False)
        df.loc[bad, "FilterStatus"] = "not_inside"
    if skip_trend:
        bad = (df["FilterStatus"] == "ok") & t["prior_adr_ext"].fillna(False)
        df.loc[bad, "FilterStatus"] = "prior_trend"
    return df


# ── Trade simulation ──────────────────────────────────────────────────────────

# bar_num_from_dt imported from data_loader — shared with app.py


# ── Ratchet/BE-Stop bar-ambiguity diagnostic ──────────────────────────────────

def diagnose_ratchet_bar_ambiguities(
    results_df: pd.DataFrame,
    ticks_by_date: dict,
    bars_by_date: dict | None,
    ratchet_r: float,
    target_r: float,
    tick_value: float,
    entry_slip: float,
    exit_slip: float,
    stop_offset: int,
    commission: float,
    contracts: int,
) -> pd.DataFrame:
    """Identify AIAO trades that stopped at ~BE after ratchet, then re-simulate as
    BE Stop to show whether the same trade would have continued and hit the target.
    Returns a comparison DataFrame showing the PnL delta per trade."""
    ts = TICK_SIZE
    tv = tick_value * contracts
    tol = (exit_slip + 1.5) * ts   # price tolerance for "exit ≈ entry"

    filled = results_df[results_df["Filled"] == True].copy()
    # Candidate trades: Stop exit priced within tol of entry (ratcheted BE stop)
    be_stops = filled[
        (filled["ExitReason"] == "Stop") &
        (abs(filled["ExitPrice"] - filled["EntryPrice"]) <= tol)
    ].copy()

    rows = []
    for _, row in be_stops.iterrows():
        date       = row["Date"]
        sig_dt     = row["DateTime"]
        direction  = row["Direction"]
        is_long    = direction == "Long"
        entry_px   = float(row["EntryPrice"])
        actual_stop = float(row["ActualStop"])
        risk_pts   = float(row["RiskPts"])
        sig_price  = float(row.get("SignalPrice", entry_px))
        stop_price = float(row.get("StopPrice",  actual_stop))
        t1_level   = entry_px + (ratchet_r * risk_pts if is_long else -ratchet_r * risk_pts)

        # ── Find the exit bar to verify the Hi/Lo pattern ─────────────────────
        bar_hi = bar_lo = None
        is_ambiguous = False
        day_bars = (bars_by_date or {}).get(date)
        exit_time = row.get("ExitTime")

        if day_bars is not None and exit_time is not None:
            exit_ts = pd.Timestamp(exit_time)
            candidates = day_bars[day_bars["DateTime"] <= exit_ts]
            if not candidates.empty:
                eb = candidates.iloc[-1]
                bar_hi = float(eb["High"])
                bar_lo = float(eb["Low"])
                if is_long:
                    is_ambiguous = (
                        bar_hi >= t1_level - 0.001 and
                        bar_lo <= entry_px + 0.001 and
                        bar_lo > actual_stop - 0.001
                    )
                else:
                    is_ambiguous = (
                        bar_lo <= t1_level + 0.001 and
                        bar_hi >= entry_px - 0.001 and
                        bar_hi < actual_stop + 0.001
                    )

        # ── Re-simulate as BE Stop (same T1 level, full position continues) ───
        be_exit_reason = be_exit_px = be_net_pnl = None
        day_ticks = ticks_by_date.get(date)
        no_ticks  = day_ticks is None or day_ticks.empty

        try:
            if not no_ticks:
                res = _simulate_one_multileg(
                    sig_dt, direction, sig_price, stop_price,
                    day_ticks, target_r, ratchet_r, "be_only",
                    entry_slip, exit_slip, stop_offset,
                    tv1=0.0, tv2=tv,
                )
            elif day_bars is not None:
                res = _simulate_one_bars_multileg(
                    sig_dt, direction, sig_price, stop_price,
                    day_bars, target_r, ratchet_r, "be_only",
                    entry_slip, exit_slip, stop_offset,
                    tv1=0.0, tv2=tv,
                )
            else:
                res = {"ok": False}

            if res.get("ok"):
                be_exit_reason = res["ExitReason"]
                be_exit_px     = round(float(res["ExitPrice"]), 2)
                be_net_pnl     = round(float(res["GrossPnL"]) - commission * contracts, 2)
        except Exception:
            pass

        pnl_diff = round(be_net_pnl - float(row["NetPnL"]), 2) if be_net_pnl is not None else None

        rows.append({
            "Date":          str(date),
            "Dir":           direction,
            "Entry":         round(entry_px, 2),
            "Stop":          round(actual_stop, 2),
            "T1_Level":      round(t1_level, 2),
            "Bar_Hi":        round(bar_hi, 2) if bar_hi else None,
            "Bar_Lo":        round(bar_lo, 2) if bar_lo else None,
            "Ambiguous_Bar": is_ambiguous,
            "AIAO_Exit":     row["ExitReason"],
            "AIAO_Px":       round(float(row["ExitPrice"]), 2),
            "AIAO_Net":      round(float(row["NetPnL"]), 2),
            "BEStop_Exit":   be_exit_reason,
            "BEStop_Px":     be_exit_px,
            "BEStop_Net":    be_net_pnl,
            "PnL_Delta":     pnl_diff,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Date").reset_index(drop=True)
    return df


# ── Chart ─────────────────────────────────────────────────────────────────────

def _outcome_color(exit_reason: str) -> str:
    if "Target" in exit_reason:
        return "#26a69a"   # green — full or partial win
    if exit_reason == "Stop":
        return "#ef5350"   # red — full stop
    if exit_reason in ("T1+BE", "T1+EOD"):
        return "#ff9800"   # orange — partial profit
    return "#9e9e9e"       # grey — EOD, session


def make_analysis_chart(
    day_bars: pd.DataFrame,
    day_results: pd.DataFrame,
    date_str: str,
    show_bar_nums: bool = False,
    excl_first_n: int = 0,
    excl_last_min: int = 0,
    contract: str = "ES",
    show_hover: bool = True,
) -> go.Figure:
    df = day_bars
    fig = go.Figure(
        go.Candlestick(
            x=df["DateTime"], open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"], name=contract,
            increasing_line_color="#26a69a", decreasing_line_color="#ef5350",
        )
    )

    half  = pd.Timedelta(minutes=2, seconds=30)
    shade = dict(fillcolor="rgba(180,180,180,0.15)", line_width=0, layer="below")
    if excl_first_n > 0 and excl_first_n <= len(df):
        fig.add_vrect(x0=df.iloc[0]["DateTime"] - half,
                      x1=df.iloc[min(excl_first_n, len(df)) - 1]["DateTime"] + half, **shade)
    if excl_last_min > 0:
        ct = 15 * 60 + 15 - excl_last_min
        cs = f"{ct // 60:02d}:{ct % 60:02d}"
        cb = df[df["DateTime"].dt.strftime("%H:%M") >= cs]
        if not cb.empty:
            fig.add_vrect(x0=cb.iloc[0]["DateTime"] - half,
                          x1=df.iloc[-1]["DateTime"] + half, **shade)

    if show_bar_nums:
        labeled = sorted(set(range(0, len(df), 3)) | {len(df) - 1})
        for i in labeled:
            fig.add_annotation(
                x=df.iloc[i]["DateTime"], y=df.iloc[i]["Low"],
                yshift=-6, text=str(bar_num_from_dt(df.iloc[i]["DateTime"])),
                showarrow=False, font=dict(size=12),
                xanchor="center", yanchor="top",
            )

    # Collect all relevant prices for Y-range calculation
    y_prices = list(df["Low"].values) + list(df["High"].values)

    # Pre-compute chart y-range for hover rectangles (extend well beyond bars)
    y_lo_pre = df["Low"].min()
    y_hi_pre = df["High"].max()
    h_pad    = (y_hi_pre - y_lo_pre) * 0.30

    if not day_results.empty:
        day_range = df["High"].max() - df["Low"].min()
        marker_offset = day_range * 0.003

        for _, row in day_results.iterrows():
            sig_dt   = row["DateTime"]
            is_long  = row["Direction"] == "Long"
            filtered = row["FilterStatus"] != "ok"

            # Signal bar open = sig_dt - 5min (bars use label="left")
            bar_open = sig_dt - pd.Timedelta(minutes=5)
            bar_rows = df[df["DateTime"] == bar_open]
            if bar_rows.empty:
                continue
            bar_row = bar_rows.iloc[0]

            if filtered:
                rect_color   = "rgba(160,160,160,0.10)"
                border_color = "rgba(160,160,160,0.30)"
                dot_color    = "#aaaaaa"
            elif is_long:
                rect_color   = "rgba(0,230,118,0.18)"
                border_color = "rgba(0,230,118,0.70)"
                dot_color    = "#00e676"
            else:
                rect_color   = "rgba(255,80,80,0.18)"
                border_color = "rgba(255,80,80,0.70)"
                dot_color    = "#ff5252"

            fig.add_vrect(
                x0=bar_open - half, x1=bar_open + half,
                fillcolor=rect_color,
                line=dict(color=border_color, width=1.0),
                layer="below",
            )

            htxt = (
                f"Signal #{int(row['SignalNum'])} {row['SignalType']} {row['Direction']}<br>"
                f"Date: {row['Date']}  Bar: {int(row['BarNum'])} | {sig_dt.strftime('%H:%M')}<br>"
                f"Signal Price: {row['SignalPrice']:.2f} | Stop: {row['StopPrice']:.2f}<br>"
                f"Status: {row['FilterStatus']}"
            )
            if show_hover:
                fig.add_trace(go.Scatter(
                    x=[bar_open],
                    y=[(float(bar_row["High"]) + float(bar_row["Low"])) / 2],
                    mode="markers",
                    marker=dict(size=20, color=dot_color, opacity=0.001),
                    hovertemplate=htxt + "<extra></extra>",
                    showlegend=False, name="",
                ))

            if not row["Filled"]:
                continue

            entry_dt  = row["EntryTime"]
            entry_px  = row["EntryPrice"]
            stop_px   = row["ActualStop"]
            target_px = row["Target"]
            exit_dt   = row["ExitTime"]
            exit_px   = row["ExitPrice"]
            reason    = row["ExitReason"]
            oc        = _outcome_color(reason)
            net_pnl   = row["NetPnL"]
            gross_pts = row["GrossPnLPts"]
            sign      = "+" if net_pnl >= 0 else ""

            _t1_px_yrange = row.get("Target1", np.nan)
            for p in [entry_px, stop_px, target_px, _t1_px_yrange, exit_px]:
                if pd.notna(p):
                    y_prices.append(p)

            entry_ts = pd.Timestamp(entry_dt)
            exit_ts  = pd.Timestamp(exit_dt)

            entry_htxt = (
                f"ENTRY #{int(row['SignalNum'])}<br>"
                f"Date: {entry_ts.strftime('%Y-%m-%d')}  Bar {int(row['EntryBarNum'])} | {entry_ts.strftime('%H:%M:%S')}<br>"
                f"Price: {entry_px:.2f}<br>"
                f"Stop: {stop_px:.2f} | Target: {target_px:.2f}<br>"
                f"Risk: {row['RiskPts']:.2f} pts (${row['RiskDollar']:.0f})"
            )
            # Entry marker — hover directly on the circle
            _ekw = {"hovertemplate": entry_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
            fig.add_trace(go.Scatter(
                x=[entry_ts], y=[entry_px], mode="markers",
                marker=dict(symbol="circle-open", size=9, color=oc, line=dict(width=2)),
                showlegend=False, name="", **_ekw,
            ))

            exit_htxt = (
                f"EXIT #{int(row['SignalNum'])}  ({reason})<br>"
                f"Date: {exit_ts.strftime('%Y-%m-%d')}  Bar {int(row['ExitBarNum'])} | {exit_ts.strftime('%H:%M:%S')}<br>"
                f"Price: {exit_px:.2f}<br>"
                f"Gross: {sign}{gross_pts:.2f} pts | Net: {sign}${net_pnl:.0f}<br>"
                f"R: {row['R_achieved']:+.2f}<br>"
                f"MAE: {row['MAE_pts']:.2f} pts | MFE: {row['MFE_pts']:.2f} pts"
            )
            # Exit marker — hover directly on the x marker
            _xkw = {"hovertemplate": exit_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
            fig.add_trace(go.Scatter(
                x=[exit_ts], y=[exit_px], mode="markers",
                marker=dict(symbol="x", size=9, color=oc, line=dict(width=2)),
                showlegend=False, name="", **_xkw,
            ))

            xref, yref = "x", "y"

            # Stop line — extends from signal bar left edge to exit
            fig.add_shape(type="line",
                x0=bar_open, x1=exit_ts,
                y0=stop_px, y1=stop_px,
                line=dict(color="#ef5350", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # T1 line (dotted teal, shown when multileg)
            target1_px = row.get("Target1", np.nan)
            risk_pts   = row.get("RiskPts",  np.nan)
            _has_t1    = pd.notna(target1_px) and pd.notna(risk_pts) and risk_pts > 0.001
            if _has_t1:
                t1_r_disp = abs(float(target1_px) - entry_px) / risk_pts
                fig.add_shape(type="line",
                    x0=entry_ts, x1=exit_ts,
                    y0=float(target1_px), y1=float(target1_px),
                    line=dict(color="#26a69a", width=1.0, dash="dot"),
                    xref=xref, yref=yref)
                fig.add_annotation(
                    x=exit_ts, y=float(target1_px),
                    xshift=6, yshift=0,
                    text=f"T1 {t1_r_disp:.2f}R",
                    showarrow=False, xanchor="left",
                    font=dict(size=10, color="#26a69a"),
                )

            # PB level line + E2 fill circle (scale-in model)
            pb_level_px  = row.get("PBLevel",    np.nan)
            e2_fill_px   = row.get("E2FillPrice", np.nan)
            e2_fill_time = row.get("E2FillTime",  pd.NaT)
            if pd.notna(pb_level_px):
                y_prices.append(pb_level_px)
                e2_end_ts = pd.Timestamp(e2_fill_time) if pd.notna(e2_fill_time) else exit_ts
                fig.add_shape(type="line",
                    x0=entry_ts, x1=e2_end_ts,
                    y0=pb_level_px, y1=pb_level_px,
                    line=dict(color="#ffa726", width=1.2, dash="dashdot"),
                    xref=xref, yref=yref)
                fig.add_annotation(
                    x=entry_ts, y=pb_level_px,
                    xshift=-4, yshift=0,
                    text="PB", showarrow=False, xanchor="right",
                    font=dict(size=9, color="#ffa726"),
                )
                if pd.notna(e2_fill_px) and pd.notna(e2_fill_time):
                    e2_htxt = (
                        f"E2 FILL (scale-in)<br>"
                        f"Time: {e2_end_ts.strftime('%H:%M')}<br>"
                        f"Fill price: {e2_fill_px:.2f}"
                    )
                    _e2kw = {"hovertemplate": e2_htxt + "<extra></extra>"} if show_hover else {"hoverinfo": "skip"}
                    fig.add_trace(go.Scatter(
                        x=[e2_end_ts], y=[e2_fill_px], mode="markers",
                        marker=dict(symbol="circle", size=9, color="#ffa726",
                                    line=dict(color="#ffa726", width=2)),
                        showlegend=False, name="", **_e2kw,
                    ))

            # T2 / Target line (dashed teal)
            t2_label = f"T2 {row['TargetR']:.2f}R" if _has_t1 else f"<b>{row['TargetR']:.2f}R</b>"
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=target_px, y1=target_px,
                line=dict(color="#26a69a", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # R label — right end of target line
            fig.add_annotation(
                x=exit_ts, y=target_px,
                xshift=6, yshift=0,
                text=t2_label,
                showarrow=False, xanchor="left",
                font=dict(size=11, color="#26a69a"),
            )

            # BE line (orange) = entry price
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=entry_px, y1=entry_px,
                line=dict(color="#ff9800", width=1.0),
                xref=xref, yref=yref)

            # Dotted diagonal: entry price → exit price
            fig.add_shape(type="line",
                x0=entry_ts, x1=exit_ts,
                y0=entry_px, y1=exit_px,
                line=dict(color=oc, width=1.5, dash="dot"),
                xref=xref, yref=yref)

    # Y-range with padding
    if y_prices:
        y_lo, y_hi = min(y_prices), max(y_prices)
        pad = (y_hi - y_lo) * 0.06
        fig.update_layout(yaxis=dict(range=[y_lo - pad, y_hi + pad]))

    # x-axis: bar DateTimes are open times; label ticks as close time (+5 min)
    _tick_vals = [t for t in df["DateTime"] if t.minute % 15 == 0]
    _tick_text = [(t + pd.Timedelta(minutes=5)).strftime("%H:%M") for t in _tick_vals]
    spike = dict(showspikes=True, spikethickness=1, spikedash="dot",
                 spikecolor="rgba(128,128,128,0.40)", spikesnap="cursor")
    fig.update_layout(
        title=f"{contract} — Bar Analysis  ({date_str})",
        xaxis_title="Time (CT)", yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis=dict(tickvals=_tick_vals, ticktext=_tick_text, tickangle=-45, **spike),
        yaxis=dict(**spike),
        height=560,
        margin=dict(l=50, r=20, t=60, b=60),
        template="plotly_white",
        hovermode="closest" if show_hover else False,
        hoverlabel=dict(font_size=15, bgcolor="rgba(30,30,30,0.90)", font_color="white"),
        spikedistance=200,
    )
    return fig


# ── Signal table ──────────────────────────────────────────────────────────────

_STATUS_LABELS = {
    "ok":             "Filtered",    # shouldn't appear if not filled
    "date_range":     "Date range",
    "signal_type":    "Signal type",
    "direction":      "Direction",
    "holiday":        "Holiday",
    "dow":            "Day of week",
    "first_bars":     "Open excl.",
    "last_bars":      "Close excl.",
    "event":          "Econ event",
    "first_trade_day":"2nd+ trade",
    "no_fill":        "No fill",
    "no_next_bar":    "Session end",
    "no_tick_data":   "No tick data",
    "zero_risk":      "Zero risk",
}


def _show_signal_table(results: pd.DataFrame, key_suffix: str = ""):
    if results.empty:
        st.info("No signals to display.")
        return

    _has_multileg = (
        "Leg1ExitReason" in results.columns and
        results["Leg1ExitReason"].notna().any()
    )
    _group_opts = ["Core", "Entry/Exit", "P&L", "Risk & R", "MAE/MFE"]
    if _has_multileg:
        _group_opts.append("Multileg")

    col_groups = st.multiselect(
        "Column groups",
        _group_opts,
        default=["Core", "Entry/Exit", "P&L", "Risk & R"],
        key=f"ba_col_groups{key_suffix}",
    )

    cols = []
    if "Core" in col_groups:
        cols += ["#", "Type", "Dir", "Date", "Sig Time", "Sig Bar", "Status", "ER10"]
    if "Entry/Exit" in col_groups:
        cols += ["SB Close", "SE Px", "Bar Open", "Entry Time", "Entry Bar", "Entry Px", "Stop", "Target",
                 "Exit Time", "Exit Bar", "Exit Px", "Exit Type"]
    if "P&L" in col_groups:
        cols += ["Gross$", "Net$", "Cum PF"]
    if "Risk & R" in col_groups:
        cols += ["Risk$", "Target R", "R"]
    if "MAE/MFE" in col_groups:
        cols += ["MAE pts", "MAE$", "MAE R", "MFE pts", "MFE$", "MFE R"]
    if "Multileg" in col_groups and _has_multileg:
        cols += ["T1 R", "T2 R", "T1", "L1 Exit", "L1 Px", "L1 $",
                 "PB R", "PB Exact", "PB Lvl", "E2 Fill", "E2 Time", "Blend", "L2 Exit", "L2 Px", "L2 $"]

    if not cols:
        st.info("Select at least one column group above.")
        return

    def fmt_time(t):
        try:
            ts = pd.Timestamp(t)
            if not pd.notna(ts):
                return "—"
            base = ts.strftime("%H:%M:%S")
            ms = ts.microsecond // 1000
            return f"{base}.{ms:03d}" if ms else base
        except Exception:
            return "—"

    def fmt_f(v, decimals=2):
        return f"{v:.{decimals}f}" if pd.notna(v) else "—"

    def fmt_pf(v):
        if pd.isna(v):
            return "—"
        return "∞" if v > 99 else f"{v:.2f}"

    def fmt_status(s):
        return _STATUS_LABELS.get(s, s)

    disp = pd.DataFrame()
    disp["#"]          = results["SignalNum"]
    disp["Type"]       = results["SignalType"]
    disp["Dir"]        = results["Direction"]
    disp["Date"]       = results["Date"].astype(str)
    disp["Sig Time"]   = results["DateTime"].dt.strftime("%H:%M")
    disp["Sig Bar"]    = results["BarNum"]
    disp["Status"]     = results.apply(
        lambda r: "✓ Filled" if r["Filled"] else fmt_status(r["FilterStatus"]), axis=1
    )
    disp["ER10"]       = results["ER10"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—") if "ER10" in results.columns else "—"
    disp["SB Close"]   = results["SBClose"].apply(fmt_f)   # signal bar close (diagnostic)
    disp["Entry Ref"]  = results["SEPrice"].apply(fmt_f)   # SEPrice = post-delay entry reference
    disp["Bar Open"]   = results["FillPrice"].apply(fmt_f) # raw fill (pre-slip)
    disp["Entry Time"] = results["EntryTime"].apply(fmt_time)
    disp["Entry Bar"]  = results["EntryBarNum"].apply(lambda v: int(v) if pd.notna(v) else "—")
    disp["Entry Px"]   = results["EntryPrice"].apply(fmt_f)
    disp["Stop"]       = results["ActualStop"].apply(fmt_f)
    disp["Target"]     = results["Target"].apply(fmt_f)
    disp["Exit Time"]  = results["ExitTime"].apply(fmt_time)
    disp["Exit Bar"]   = results["ExitBarNum"].apply(lambda v: int(v) if pd.notna(v) else "—")
    disp["Exit Px"]    = results["ExitPrice"].apply(fmt_f)
    disp["Exit Type"]  = results["ExitReason"].replace("", "—")
    disp["Gross$"]     = results["GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
    disp["Net$"]       = results["NetPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
    disp["Cum PF"]     = results["CumPF"].apply(fmt_pf)
    disp["Risk$"]      = results["RiskDollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["ConcRisk$"]  = results["ConcurrentRiskDollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—") if "ConcurrentRiskDollar" in results.columns else "—"
    disp["Target R"]   = results["TargetR"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    disp["R"]          = results["R_achieved"].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
    disp["MAE pts"]    = results["MAE_pts"].apply(fmt_f)
    disp["MAE$"]       = results["MAE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MAE R"]      = results["MAE_R"].apply(fmt_f)
    disp["MFE pts"]    = results["MFE_pts"].apply(fmt_f)
    disp["MFE$"]       = results["MFE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MFE R"]      = results["MFE_R"].apply(fmt_f)
    if _has_multileg:
        disp["T1 R"]   = results["T1_R"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
        disp["T2 R"]   = results["TargetR"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
        disp["T1"]     = results["Target1"].apply(fmt_f)
        disp["L1 Exit"]= results["Leg1ExitReason"].fillna("—")
        disp["L1 Px"]  = results["Leg1ExitPrice"].apply(fmt_f)
        disp["L1 $"]   = results["Leg1GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        disp["L2 Exit"]= results["Leg2ExitReason"].fillna("—")
        disp["L2 Px"]  = results["Leg2ExitPrice"].apply(fmt_f)
        disp["L2 $"]   = results["Leg2GrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        if "PBLevel" in results.columns:
            disp["PB R"]     = results["PB_R"].apply(lambda v: f"{v:.2f}R" if pd.notna(v) else "—")
            disp["PB Lvl"]   = results["PBLevel"].apply(fmt_f)
            disp["PB Exact"] = results["PBLevelRaw"].apply(lambda v: f"{v:.4f}" if pd.notna(v) else "—")
            disp["E2 Fill"]= results["E2FillPrice"].apply(fmt_f)
            disp["E2 Time"]= results["E2FillTime"].apply(
                lambda t: pd.Timestamp(t).strftime("%H:%M") if pd.notna(t) else "—"
            )
            disp["Blend"]  = results["BlendedEntry"].apply(fmt_f)

    # Filter to selected column groups
    visible = [c for c in cols if c in disp.columns]
    disp    = disp[visible]

    st.dataframe(disp, use_container_width=True, hide_index=True,
                 height=min(35 * len(disp) + 38, 600))
    st.caption(f"{len(results)} signals  |  {int(results['Filled'].sum())} filled trades")


# ── Entry Zoom chart ──────────────────────────────────────────────────────────

def _show_entry_zoom(
    sig_row: pd.Series,
    ticks_by_date: dict,
) -> None:
    """Full tick-level view from signal bar close through fill + a few ticks beyond.
    Annotates every ESA event: SBClose, SEPrice, OrderLive, Retrace, TickThrough/Fill."""
    date      = sig_row["Date"]
    sig_dt    = pd.Timestamp(sig_row["DateTime"])
    day_ticks = ticks_by_date.get(date)

    if day_ticks is None or day_ticks.empty:
        st.warning("No tick data for this date.")
        return

    entry_price = float(sig_row["EntryPrice"])
    stop_price  = float(sig_row["ActualStop"])
    sb_close_px = float(sig_row["SBClose"]) if pd.notna(sig_row.get("SBClose")) else None
    se_price    = float(sig_row["SEPrice"]) if pd.notna(sig_row.get("SEPrice")) else None
    raw_fill    = float(sig_row["RawFillPrice"]) if pd.notna(sig_row.get("RawFillPrice")) else None
    target_px   = float(sig_row["Target"]) if pd.notna(sig_row.get("Target")) else None
    is_long     = sig_row["Direction"] == "Long"
    entry_type  = sig_row.get("EntryType", "market")

    # ESA timestamps
    _get_ts = lambda col: pd.Timestamp(sig_row[col]) if col in sig_row.index and pd.notna(sig_row.get(col)) else pd.NaT
    ref_ts   = _get_ts("ReferenceTime")
    live_ts  = _get_ts("OrderLiveTime")
    retr_ts  = _get_ts("RetraceTime")
    thru_ts  = _get_ts("FirstThroughTime")
    entry_ts = _get_ts("EntryTime")
    exit_ts  = _get_ts("ExitTriggerTime")

    # Determine the fill timestamp (tick-through for stop, or entry time for market)
    fill_ts = thru_ts if (entry_type == "stop" and pd.notna(thru_ts)) else entry_ts

    # Window: tight around the action — 3 ticks before signal, through fill + 5 ticks after
    before = day_ticks[day_ticks["DateTime"] <= sig_dt]
    after  = day_ticks[day_ticks["DateTime"] > sig_dt]
    if before.empty or after.empty:
        st.warning("Not enough ticks around this signal.")
        return

    pre = before.iloc[-3:]
    if pd.notna(fill_ts):
        fill_after = after[after["DateTime"] >= fill_ts]
        post_fill_count = min(5, len(fill_after))
        end_idx = after.index.get_loc(fill_after.index[post_fill_count - 1]) + 1 if post_fill_count > 0 else len(after)
        post = after.iloc[:end_idx]
    else:
        post = after.iloc[:20]

    zoom = pd.concat([pre, post]).reset_index(drop=True)
    if zoom.empty:
        st.warning("No ticks in zoom window.")
        return

    def ts_label(t):
        ts = pd.Timestamp(t)
        ms = ts.microsecond // 1000
        return ts.strftime("%H:%M:%S") + (f".{ms:03d}" if ms else "")

    fig = go.Figure()

    # Price line — all ticks
    fig.add_trace(go.Scatter(
        x=zoom["DateTime"], y=zoom["Price"],
        mode="lines", line=dict(color="#555", width=1.2),
        showlegend=False, hoverinfo="skip",
    ))

    # Tick dots with hover
    fig.add_trace(go.Scatter(
        x=zoom["DateTime"], y=zoom["Price"],
        mode="markers",
        marker=dict(size=4, color="#888"),
        name="Ticks",
        hovertemplate="%{x|%H:%M:%S.%L}<br>%{y:.2f}<extra></extra>",
    ))

    # ── Annotated ESA event markers ──
    # Arrow annotations from nearby text boxes to exact event ticks.
    # Each event gets a pre-assigned pixel offset direction so boxes don't overlap.

    def _resolve_event(ts_val):
        ts_val = pd.Timestamp(ts_val)
        mask = zoom["DateTime"] == ts_val
        if not mask.any():
            nearest_idx = (zoom["DateTime"] - ts_val).abs().idxmin()
            return zoom.loc[nearest_idx, "DateTime"], float(zoom.loc[nearest_idx, "Price"])
        return ts_val, float(zoom.loc[mask, "Price"].iloc[0])

    # Pre-assigned pixel offsets (ax, ay) per event — spread to both sides,
    # early cluster (SB/SE/Live) goes left, later events (Retrace/Fill) go right.
    _event_offsets = {
        "SB Close":            (-80, -30),
        "SEPrice":             (-80,  30),
        "Order Live":          (-80,  75),
        "Retrace":             ( 0,  -45),
        "Tick-Through (Fill)": ( 0,   45),
        "Fill":                ( 0,   45),
    }

    _event_defs = []
    def _queue(ts_val, label, color):
        if pd.notna(ts_val):
            _event_defs.append((ts_val, label, color))

    _queue(sig_dt, "SB Close", "orange")
    _queue(ref_ts, "SEPrice", "#00bfff")
    _queue(live_ts, "Order Live", "#22cc22")
    if entry_type == "stop":
        _queue(retr_ts, "Retrace", "#ffcc00")
        _queue(thru_ts, "Tick-Through (Fill)", "#ff3366")
    else:
        _queue(entry_ts, "Fill", "#ff3366")

    for ts_val, label, color in _event_defs:
        tx, px = _resolve_event(ts_val)
        ax_px, ay_px = _event_offsets.get(label, (0, -45))

        fig.add_annotation(
            x=tx, y=px,
            text=f"<b>{label}</b><br>{ts_label(tx)}<br>{px:.2f}",
            showarrow=True, arrowhead=2, arrowsize=0.8, arrowwidth=1.2,
            arrowcolor=color, ax=ax_px, ay=ay_px,
            font=dict(size=10, color=color),
            align="center", bgcolor="rgba(26,26,26,0.85)",
            bordercolor=color, borderwidth=0.5, borderpad=3,
        )

    # ── Vertical line at signal bar close ──
    fig.add_vline(
        x=sig_dt.value / 1e6,
        line=dict(color="orange", width=2, dash="solid"),
    )

    # ── Horizontal price levels ──
    # No SBClose label on the axis — it's already marked by the event annotation.
    # SEPrice and Entry (slipped) drawn finer. Stagger right-side labels when close.
    tick = 0.25
    _hline_annots = []
    def _queue_hline(px, label, color, dash="dash", width=1.5):
        if px is not None and not (isinstance(px, float) and np.isnan(px)):
            _hline_annots.append((float(px), label, color, dash, width))

    _queue_hline(se_price, "SEPrice", "#00bfff", "dot", 0.8)
    _queue_hline(entry_price, "Entry (slipped)", "#00ff88", "dash", 0.8)
    _queue_hline(stop_price, "Stop", "#ff4444", "dash", 1.5)
    if target_px and not np.isnan(target_px):
        _queue_hline(target_px, "Target", "#44aaff", "dash", 1.5)
    # SBClose hline drawn but no right-side label
    if sb_close_px is not None and not np.isnan(sb_close_px):
        fig.add_hline(y=sb_close_px, line=dict(color="orange", width=0.8, dash="dot"))

    _hline_annots.sort(key=lambda h: h[0])
    _label_y_offsets = {}
    for i, (px_i, *_rest) in enumerate(_hline_annots):
        y_off = 0
        for j in range(i):
            if abs(px_i - _hline_annots[j][0]) < 2 * tick:
                y_off += 15
        _label_y_offsets[i] = y_off

    for i, (px, label, color, dash, width) in enumerate(_hline_annots):
        fig.add_hline(y=px, line=dict(color=color, width=width, dash=dash))
        fig.add_annotation(
            x=1.0, xref="paper", xanchor="left",
            y=px, yshift=-_label_y_offsets[i],
            text=f"{label}  {px:.2f}",
            font=dict(color=color, size=10),
            showarrow=False, bgcolor="rgba(26,26,26,0.8)", borderpad=2,
        )

    dir_label = "LONG" if is_long else "SHORT"
    fill_time_ms = sig_row.get("SigToFill_ms", 0)
    fill_time_str = f"{fill_time_ms/1000:.1f}s" if fill_time_ms < 60000 else f"{fill_time_ms/60000:.1f}min"
    exit_reason = sig_row.get("ExitReason", "")
    r_achieved = sig_row.get("R_achieved", 0)

    fig.update_layout(
        title=dict(
            text=(f"🔬 {dir_label} {sig_row.get('SignalType','')}  ·  {date}  "
                  f"·  Entry {entry_type}  ·  Fill in {fill_time_str}  "
                  f"·  {exit_reason} {r_achieved:+.2f}R  ·  ${sig_row.get('NetPnL',0):+,.0f}"),
            font=dict(size=12),
        ),
        xaxis=dict(title="", type="date", tickformat="%H:%M:%S.%L",
                   showgrid=True, gridcolor="#333",
                   range=[zoom["DateTime"].min() - pd.Timedelta(seconds=2),
                          zoom["DateTime"].max() + pd.Timedelta(seconds=2)]),
        yaxis=dict(title="Price", showgrid=True, gridcolor="#333",
                   tickformat=".2f", dtick=0.25,
                   range=[float(zoom["Price"].min()) - 0.75,
                          float(zoom["Price"].max()) + 0.75]),
        height=600,
        showlegend=False,
        margin=dict(r=160, t=60, b=60, l=70),
        plot_bgcolor="#1a1a1a", paper_bgcolor="#1a1a1a",
        font=dict(color="#ddd"),
    )

    # ── Delay shading on chart (when delay or wire > 0) ──
    calc_ms = sig_row.get("ActualCalcMs", 0) or 0
    wire_ms  = sig_row.get("WireDelayMs", 0) or 0
    if calc_ms > 0 and pd.notna(ref_ts):
        fig.add_vrect(
            x0=sig_dt.value / 1e6, x1=ref_ts.value / 1e6,
            fillcolor="orange", opacity=0.10, line_width=0,
            annotation_text=f"Calc {calc_ms:.0f}ms",
            annotation_position="top left",
            annotation_font=dict(size=9, color="orange"),
        )
    if wire_ms > 0 and pd.notna(ref_ts) and pd.notna(live_ts):
        fig.add_vrect(
            x0=ref_ts.value / 1e6, x1=live_ts.value / 1e6,
            fillcolor="#22cc22", opacity=0.10, line_width=0,
            annotation_text=f"Wire {wire_ms:.0f}ms",
            annotation_position="top left",
            annotation_font=dict(size=9, color="#22cc22"),
        )

    st.plotly_chart(fig, use_container_width=True)

    # ── Compute intervals from timestamps ──
    def _interval_ms(t_start, t_end):
        if pd.notna(t_start) and pd.notna(t_end):
            return (pd.Timestamp(t_end) - pd.Timestamp(t_start)).total_seconds() * 1000
        return None

    def _fmt_interval(ms):
        if ms is None:
            return "—"
        if abs(ms) < 1000:
            return f"{ms:.0f} ms"
        if abs(ms) < 60000:
            return f"{ms/1000:.1f} s"
        return f"{ms/60000:.1f} min"

    sig_to_ref   = _interval_ms(sig_dt, ref_ts)
    ref_to_live  = _interval_ms(ref_ts, live_ts)
    live_to_fill = _interval_ms(live_ts, fill_ts)
    sig_to_fill  = _interval_ms(sig_dt, fill_ts)

    # ── Key metrics strip ──
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("SBClose", f"{sb_close_px:.2f}" if sb_close_px else "—")
    c2.metric("SEPrice", f"{se_price:.2f}" if se_price else "—")
    c3.metric("Entry (slipped)", f"{entry_price:.2f}",
              delta=f"{entry_price - (raw_fill or entry_price):+.2f} slip")
    c4.metric("Stop", f"{stop_price:.2f}",
              delta=f"{abs(entry_price - stop_price):.2f} risk pts")
    c5.metric("Fill time", _fmt_interval(sig_to_fill))

    # ── Timestamp trail ──
    _ts_fmt = lambda t: ts_label(t) if pd.notna(t) else "—"
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Signal", sig_dt.strftime("%H:%M:%S"))
    t2.metric("SEPrice tick", _ts_fmt(ref_ts))
    t3.metric("Order live", _ts_fmt(live_ts))
    t4.metric("Retrace" if entry_type == "stop" else "—", _ts_fmt(retr_ts))
    t5.metric("Fill", _ts_fmt(fill_ts))

    # ── Interval strip ──
    i1, i2, i3, i4, i5 = st.columns(5)
    i1.metric("Sig → SEPrice", _fmt_interval(sig_to_ref),
              delta=f"calc {calc_ms:.0f}ms" if calc_ms > 0 else None)
    i2.metric("SEPrice → Live", _fmt_interval(ref_to_live),
              delta=f"wire {wire_ms:.0f}ms" if wire_ms > 0 else None)
    i3.metric("Live → Fill", _fmt_interval(live_to_fill))
    i4.metric("Sig → Fill (total)", _fmt_interval(sig_to_fill))
    if entry_type == "stop":
        retr_to_fill = _interval_ms(retr_ts, thru_ts)
        i5.metric("Retrace → Fill", _fmt_interval(retr_to_fill))
    else:
        i5.metric("—", "—")


def _show_entry_zoom_section(results: pd.DataFrame, ticks_by_date: dict) -> None:
    """Expander that lets the user pick a filled trade and view the tick entry zoom."""
    filled = results[results["Filled"] == True]
    if filled.empty or not ticks_by_date:
        return

    with st.expander("🔍 Entry Zoom — tick-level view around trade entry", expanded=False):
        sig_opts = {
            f"#{int(r['SignalNum'])}  {r['Date']} {r['Direction']} "
            f"@ {pd.Timestamp(r['DateTime']).strftime('%H:%M')} "
            f"→ EB Open {float(r['FillPrice']):.2f}  Entry {float(r['EntryPrice']):.2f}"
            : idx
            for idx, r in filled.iterrows()
        }
        chosen_label = st.selectbox("Select trade", list(sig_opts.keys()),
                                    key="ba_entry_zoom_sel")
        if chosen_label:
            row_idx = sig_opts[chosen_label]
            _show_entry_zoom(results.loc[row_idx], ticks_by_date)


# ── Optimal R sweep ───────────────────────────────────────────────────────────

def _apply_day_trade_filters(
    results: pd.DataFrame,
    first_trade_only: bool,
    first_2_filled_only: bool,
) -> pd.DataFrame:
    """Apply post-simulation per-day trade count filters (mirrors main sim path)."""
    if results.empty:
        return results
    if first_trade_only:
        _fm = results["Filled"] == True
        _keep = results[_fm].sort_values(["Date", "SignalNum"]).groupby("Date").head(1).index
        results = results.drop(results[_fm & ~results.index.isin(_keep)].index).reset_index(drop=True)
    if first_2_filled_only and not results.empty:
        _fm = results["Filled"] == True
        _keep = results[_fm].sort_values(["Date", "SignalNum"]).groupby("Date").head(2).index
        results = results.drop(results[_fm & ~results.index.isin(_keep)].index).reset_index(drop=True)
    return results


def _win_breakdown(res: pd.DataFrame):
    """Decompose filled trades into target hits vs EOD-only wins, using the exact
    same buckets as compute_summary(). Returns (tgt_pct, eod_win_pct, eod_win_avg_r).
    By construction Win % == tgt_pct + eod_win_pct (to within independent rounding)."""
    f = res[res["Filled"] == True]
    n = len(f)
    if not n:
        return 0.0, 0.0, 0.0
    tgt  = (f["ExitReason"].str.contains("Target", na=False) |
            f["ExitReason"].isin(["T1+BE", "T1_only"]))
    stp  = f["ExitReason"].isin(["Stop", "E1E2+Stop"])
    eodw = (~tgt & ~stp) & (f["NetPnL"] > 0)
    tgt_pct  = round(float(tgt.mean())  * 100, 1)
    eodw_pct = round(float(eodw.mean()) * 100, 1)
    eodw_r   = round(float(f.loc[eodw, "R_achieved"].mean()), 2) if bool(eodw.any()) else 0.0
    return tgt_pct, eodw_pct, eodw_r


def _run_r_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    max_r: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    _n_steps = max(1, round(max_r / 0.25))
    r_values = [round(r * 0.25, 2) for r in range(2, _n_steps + 1)]  # 0.50 – max_r
    rows = []
    for r in r_values:
        res = simulate_trades(signals, ticks_by_date, r,
                               entry_slip, exit_slip, stop_offset,
                               tick_value, contracts, commission,
                               bars_by_date=bars_by_date,
                               multileg=multileg, t1_r=t1_r,
                               t1_action=t1_action, contracts_t1=contracts_t1,
                               contracts_t2=contracts_t2)
        res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
        s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                            t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        if not s or s["n_trades"] == 0:
            continue
        _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None

        # Decompose Win % into target hits vs EOD-only wins.
        tgt_pct, eodw_pct, eodw_r = _win_breakdown(res)

        rows.append({
            "R":       r,
            "Win %":   round(s["win_pct"], 1),
            "Tgt %":     tgt_pct,
            "EOD Win %": eodw_pct,
            "EOD Win R": eodw_r,
            "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
            "Net PnL": round(s["net_total"], 0),
            "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
            "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
            "Exp $":   round(s["exp_dollar"], 0),
        })
    return pd.DataFrame(rows)


def _run_t1t2_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    max_t1: float = 3.0, max_t2: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Grid sweep over all valid (T1, T2) pairs for 2-leg / BE-stop mode."""
    _n_t1 = max(1, round(max_t1 / 0.25))
    _n_t2 = max(1, round(max_t2 / 0.25))
    t1_vals = [round(r * 0.25, 2) for r in range(1, _n_t1 + 1)]
    t2_vals = [round(r * 0.25, 2) for r in range(2, _n_t2 + 1)]
    rows = []
    for t1 in t1_vals:
        for t2 in t2_vals:
            if t1 >= t2:
                continue
            res = simulate_trades(
                signals, ticks_by_date, t2,
                entry_slip, exit_slip, stop_offset,
                tick_value, contracts, commission,
                bars_by_date=bars_by_date,
                multileg=True, t1_r=t1,
                t1_action=t1_action,
                contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            s = compute_summary(
                res, commission, contracts=contracts, is_multileg=True,
                t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "T1":      t1,
                "T2":      t2,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


def _run_ml_scalein_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    contracts_t1: int, contracts_t2: int,
    bars_by_date: dict | None = None,
    pb_vals: list | None = None,
    t1_vals: list | None = None,
    t2_vals: list | None = None,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
    scale_in_style: str = "e2",
    pb_round: str = "nearest",
    progress_bar=None,
) -> pd.DataFrame:
    """FAST scale-in sweep (PB_R × T1_R × T2_R for 2-leg PB scale-in, ratchet off).

    Identical results to the engine reference (`_run_ml_scalein_sweep_engine` →
    simulate_trades + compute_summary), but seconds instead of minutes. How:

      * Per signal, the entry slice + running-max / running-min are precomputed ONCE
        (combo-independent). Those arrays are monotonic, so each combo's first PB /
        T1 / stop hit is an O(log n) np.searchsorted instead of an O(n) scan over
        ~100k ticks. Phase-2 (after PB fills) is a C-level numpy scan of just the
        post-PB suffix, only for signals that actually scaled in.
      * The exit sequencing mirrors the engine's vectorized PB path EXACTLY
        (PB fills before stop and continues; pre-PB only T1 can fire; post-PB stop
        beats T2 on a tie). floor/ceil PB rounding and all slip/round arithmetic are
        copied verbatim from simulation_engine._simulate_one_multileg.

    Verified byte-identical to the reference across the full default grid by
    scripts/validate_scalein_sweep.py — run it after ANY change here.
    """
    if pb_vals is None:
        pb_vals = [-0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50]
    if t1_vals is None:
        t1_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    if t2_vals is None:
        t2_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

    ts      = TICK_SIZE
    tv1     = tick_value * contracts_t1
    tv2     = tick_value * contracts_t2
    tv_tot  = tv1 + tv2
    comm1   = commission * contracts_t1                 # leg-1-only commission
    comm12  = commission * (contracts_t1 + contracts_t2)  # both-legs commission

    # ── Per-signal cache (combo-independent). A signal is "filled" exactly when the
    #    engine fills it: FilterStatus ok + tick data + ≥1 tick after signal + risk≥
    #    0.001. That set never changes across combos, so build it once. ──
    _ok = signals[signals.get("FilterStatus", pd.Series("ok", index=signals.index)) == "ok"]
    cache = []
    for _, row in _ok.iterrows():
        date = row["Date"]
        df   = ticks_by_date.get(date)
        if df is None or df.empty:
            continue
        dt_arr = df["DateTime"].values
        start  = int(np.searchsorted(dt_arr, np.datetime64(pd.Timestamp(row["DateTime"])), side="right"))
        if start >= len(dt_arr):
            continue
        prices  = df["Price"].values[start:].astype(np.float64)
        is_long = row["Direction"] == "Long"
        sgn     = 1.0 if is_long else -1.0
        entry   = float(prices[0]) + sgn * entry_slip * ts
        stop    = float(row["StopPrice"]) - sgn * stop_offset * ts
        risk    = abs(entry - stop)
        if risk < 0.001:
            continue
        cache.append({
            "is_long": is_long, "sgn": sgn,
            "prices": prices,
            "rmax": np.maximum.accumulate(prices),
            "neg_rmin": -np.minimum.accumulate(prices),
            "entry": entry, "stop": stop, "risk": risk,
            "last_px": float(prices[-1]), "n": len(prices),
            "entry_time": dt_arr[start], "date": date,
            "signum": row.get("SignalNum", -1),
        })

    if not cache:
        return pd.DataFrame()

    # Day-trade filters: keep first N filled per day by (Date, SignalNum), preserving
    # original signal order (matches _apply_day_trade_filters' drop+reset semantics).
    if first_trade_only or first_2_filled_only:
        keep_n = 1 if first_trade_only else 2
        cnt, keep = {}, set()
        for i in sorted(range(len(cache)), key=lambda j: (str(cache[j]["date"]), cache[j]["signum"])):
            d = cache[i]["date"]
            if cnt.get(d, 0) < keep_n:
                keep.add(i); cnt[d] = cnt.get(d, 0) + 1
        cache = [cache[i] for i in range(len(cache)) if i in keep]
        if not cache:
            return pd.DataFrame()

    n_sigs = len(cache)
    # DD equity order: by (Date, EntryTime), stable on original order — matches
    # compute_summary's sort_values(["Date","EntryTime"]).
    dd_idx = np.array(sorted(range(n_sigs), key=lambda j: (str(cache[j]["date"]), cache[j]["entry_time"])))
    e1_risk_dollar = np.array([c["risk"] / ts * tv1 for c in cache])

    # exit-reason codes
    T1, STOP, EOD, E2TGT, E2EOD, E2STOP = 0, 1, 2, 3, 4, 5

    total = len(pb_vals) * len(t1_vals) * len(t2_vals)
    done  = 0
    rows  = []

    for pb_r in pb_vals:
        for t1_r in t1_vals:
            for t2_r in t2_vals:
                done += 1
                if progress_bar is not None and (done % 5 == 0 or done == total):
                    progress_bar.progress(done / total,
                                          text=f"Scale-in sweep: {done} / {total}  "
                                               f"(PB={pb_r}R  T1={t1_r}R  T2={t2_r}R)")

                gross = np.empty(n_sigs)
                net   = np.empty(n_sigs)
                rach  = np.empty(n_sigs)
                codes = np.empty(n_sigs, dtype=np.int8)

                for i, c in enumerate(cache):
                    is_long = c["is_long"]; sgn = c["sgn"]
                    prices  = c["prices"]; rmax = c["rmax"]; neg_rmin = c["neg_rmin"]
                    entry   = c["entry"]; stop = c["stop"]; risk = c["risk"]; n = c["n"]

                    t1_price = _snap_level(entry + sgn * t1_r * risk, ts, entry, pb_round)
                    pb_raw   = entry + sgn * pb_r * risk    # ml_pb_ticks = 0
                    if is_long:
                        pb_trigger = (round(round(pb_raw / ts) * ts, 10) if pb_round == "nearest"
                                      else round(float(np.floor(pb_raw / ts)) * ts, 10))
                        pb_i   = int(np.searchsorted(neg_rmin, -pb_trigger, side="right"))
                        t1_i   = int(np.searchsorted(rmax, t1_price, side="right"))
                        stop_i = int(np.searchsorted(neg_rmin, -stop, side="left"))
                    else:
                        pb_trigger = (round(round(pb_raw / ts) * ts, 10) if pb_round == "nearest"
                                      else round(float(np.ceil(pb_raw / ts)) * ts, 10))
                        pb_i   = int(np.searchsorted(rmax, pb_trigger, side="right"))
                        t1_i   = int(np.searchsorted(neg_rmin, -t1_price, side="right"))
                        stop_i = int(np.searchsorted(rmax, stop, side="left"))

                    if pb_i >= n:                                   # PB never fills
                        if t1_i >= n and stop_i >= n:
                            exit_px = c["last_px"] - sgn * exit_slip * ts; codes[i] = EOD
                        elif t1_i < n and (stop_i >= n or t1_i < stop_i):
                            exit_px = t1_price - sgn * exit_slip * ts;     codes[i] = T1
                        else:
                            exit_px = stop - sgn * exit_slip * ts;         codes[i] = STOP
                        g = sgn * (exit_px - entry) / ts * tv1
                        gross[i] = g; net[i] = g - comm1
                        rach[i] = g / e1_risk_dollar[i] if e1_risk_dollar[i] > 0 else 0.0
                        continue

                    if t1_i < pb_i:                                 # T1 before PB → no scale-in
                        exit_px = t1_price - sgn * exit_slip * ts
                        g = sgn * (exit_px - entry) / ts * tv1
                        gross[i] = g; net[i] = g - comm1; codes[i] = T1
                        rach[i] = g / e1_risk_dollar[i] if e1_risk_dollar[i] > 0 else 0.0
                        continue

                    # PB fills at pb_i — limit add fills AT the trigger (tick-snapped); no adverse slip
                    e2        = pb_trigger
                    blended   = (entry * tv1 + e2 * tv2) / tv_tot
                    if scale_in_style == "blended":
                        _ref, _rr = blended, abs(blended - stop)
                    else:
                        _ref, _rr = e2, abs(e2 - stop)
                    t2_price  = _snap_level(_ref + sgn * t2_r * _rr, ts, _ref, pb_round)

                    suffix = prices[pb_i + 1:]                      # ticks strictly after PB
                    if suffix.size:
                        if is_long:
                            sm = suffix <= stop; tm = suffix > t2_price
                        else:
                            sm = suffix >= stop; tm = suffix < t2_price
                        has_s = bool(sm.any()); has_t = bool(tm.any())
                        s_rel = int(np.argmax(sm)) if has_s else n
                        t_rel = int(np.argmax(tm)) if has_t else n
                    else:
                        has_s = has_t = False; s_rel = t_rel = n

                    if not has_s and not has_t:
                        exit_px = c["last_px"] - sgn * exit_slip * ts; codes[i] = E2EOD
                    elif has_t and (not has_s or t_rel < s_rel):
                        exit_px = t2_price - sgn * exit_slip * ts;     codes[i] = E2TGT
                    else:
                        exit_px = stop - sgn * exit_slip * ts;         codes[i] = E2STOP
                    l1 = sgn * (exit_px - entry) / ts * tv1
                    l2 = sgn * (exit_px - e2) / ts * tv2
                    g  = l1 + l2
                    gross[i] = g; net[i] = g - comm12
                    rach[i] = g / e1_risk_dollar[i] if e1_risk_dollar[i] > 0 else 0.0

                # ── Aggregate (mirrors compute_summary buckets exactly) ──
                tgt  = (codes == T1) | (codes == E2TGT)
                stp  = (codes == STOP) | (codes == E2STOP)
                eod  = ~tgt & ~stp
                eodw = eod & (net > 0)
                n_wins = int((tgt | eodw).sum())

                pos = float(gross[gross > 0].sum())
                neg = float(gross[gross < 0].sum())
                pf  = abs(pos / neg) if neg < 0 else (float("inf") if pos > 0 else 0.0)

                net_total  = float(net.sum())
                exp_dollar = float(net.mean())
                eq   = np.cumsum(net[dd_idx])
                dd   = float((eq - np.maximum.accumulate(eq)).min())
                _dd  = abs(dd) if dd != 0 else None

                rows.append({
                    "PB_R":      pb_r,
                    "T1_R":      t1_r,
                    "T2_R":      t2_r,
                    "T1 %":      round(float((codes == T1).mean()) * 100, 1),
                    "T2 %":      round(float((codes == E2TGT).mean()) * 100, 1),
                    "Tgt %":     round(float(tgt.mean()) * 100, 1),
                    "EOD Win %": round(float(eodw.mean()) * 100, 1),
                    "EOD Win R": round(float(rach[eodw].mean()), 2) if bool(eodw.any()) else 0.0,
                    "Win %":     round(n_wins / n_sigs * 100, 1),
                    "PF":        round(pf, 2) if pf < 99 else 99.9,
                    "Net PnL":   round(net_total, 0),
                    "DD $":      round(_dd, 0) if _dd else 0.0,
                    "PnL/DD":    round(net_total / _dd, 2) if _dd else 0.0,
                    "Exp $":     round(exp_dollar, 0),
                })

    return pd.DataFrame(rows)


def _run_ml_scalein_sweep_engine(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    contracts_t1: int, contracts_t2: int,
    bars_by_date: dict | None = None,
    pb_vals: list | None = None,
    t1_vals: list | None = None,
    t2_vals: list | None = None,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
    scale_in_style: str = "e2",
    pb_round: str = "nearest",
    progress_bar=None,
) -> pd.DataFrame:
    """REFERENCE (slow, ~2s/combo) scale-in sweep: each combo is a full run through
    simulate_trades(multileg + PB) + compute_summary — i.e. literally the main-sim
    path. The app uses the fast `_run_ml_scalein_sweep` instead; this stays as the
    ground-truth oracle that scripts/validate_scalein_sweep.py checks the fast path
    against across the whole grid (so the fast path can never silently drift)."""
    if pb_vals is None:
        pb_vals = [-0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50]
    if t1_vals is None:
        t1_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    if t2_vals is None:
        t2_vals = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]

    total = len(pb_vals) * len(t1_vals) * len(t2_vals)
    done  = 0
    rows  = []

    for pb_r in pb_vals:
        for t1_r in t1_vals:
            for t2_r in t2_vals:
                done += 1
                if progress_bar is not None and (done % 5 == 0 or done == total):
                    progress_bar.progress(done / total,
                                          text=f"Scale-in sweep: {done} / {total}  "
                                               f"(PB={pb_r}R  T1={t1_r}R  T2={t2_r}R)")

                res = simulate_trades(
                    signals, ticks_by_date, t2_r,
                    entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission,
                    bars_by_date=bars_by_date,
                    multileg=True, t1_r=t1_r, t1_action="exit",
                    contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    ml_pb_r=pb_r, scale_in_style=scale_in_style, pb_round=pb_round,
                )
                res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
                s = compute_summary(
                    res, commission, contracts=contracts, is_multileg=True,
                    t1_action="exit", contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                )
                if not s or s["n_trades"] == 0:
                    continue

                filled  = res[res["Filled"] == True]
                t1_pct  = round(float((filled["ExitReason"] == "T1_only").mean()) * 100, 1)
                t2_pct  = round(float((filled["ExitReason"] == "E1E2+Target").mean()) * 100, 1)
                tgt_pct, eodw_pct, eodw_r = _win_breakdown(res)
                _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None

                rows.append({
                    "PB_R":      pb_r,
                    "T1_R":      t1_r,
                    "T2_R":      t2_r,
                    "T1 %":      t1_pct,
                    "T2 %":      t2_pct,
                    "Tgt %":     tgt_pct,
                    "EOD Win %": eodw_pct,
                    "EOD Win R": eodw_r,
                    "Win %":     round(s["win_pct"], 1),
                    "PF":        round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                    "Net PnL":   round(s["net_total"], 0),
                    "DD $":      round(_dd_abs, 0) if _dd_abs else 0.0,
                    "PnL/DD":    round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                    "Exp $":     round(s["exp_dollar"], 0),
                })

    return pd.DataFrame(rows)


def _run_pb_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, commission: float,
    target_r: float, t1_r: float, t2_r: float, t1_action: str,
    tv_e1: float, tv_e2: float, tv_e3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_ticks: int, pb2_ticks: int,
    ratchet_r: float, ratchet_dest: str, ratchet_lock_r: float,
    bars_by_date: dict | None = None,
    max_pb1: float = 1.5, max_pb2: float = 2.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Grid sweep over PB1_R × PB2_R for 3-leg mode (tick offsets and targets held fixed)."""
    _step = 0.25
    pb1_vals = [round(r * _step, 2) for r in range(1, max(1, round(max_pb1 / _step)) + 1)]
    pb2_vals = [round(r * _step, 2) for r in range(2, max(2, round(max_pb2 / _step)) + 1)]
    rows = []
    for pb1 in pb1_vals:
        for pb2 in pb2_vals:
            if pb2 <= pb1:
                continue
            res = simulate_trades(
                signals, ticks_by_date, target_r,
                entry_slip, exit_slip, stop_offset,
                tick_value, e1c, commission,
                bars_by_date=bars_by_date,
                threeleg=True, t1_r=t1_r, t2_r=t2_r, t1_action=t1_action,
                contracts_e1=e1c, contracts_e2=e2c, contracts_e3=e3c,
                pb1_r=pb1, pb1_ticks=pb1_ticks,
                pb2_r=pb2, pb2_ticks=pb2_ticks,
                ratchet_r=0.0,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            total_c = e1c + e2c + e3c
            s = compute_summary(res, commission, contracts=total_c,
                                is_multileg=False)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "PB1": pb1, "PB2": pb2,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


def _run_t1t2_sweep_3leg(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, commission: float,
    t2_r_fixed: float, t1_action: str,
    tv_e1: float, tv_e2: float, tv_e3: float,
    e1c: int, e2c: int, e3c: int,
    pb1_r: float, pb1_ticks: int,
    pb2_r: float, pb2_ticks: int,
    bars_by_date: dict | None = None,
    max_t1: float = 3.0, max_t3: float = 5.0,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
) -> pd.DataFrame:
    """Sweep T1 (E1 target) × T3 (E3 target) with T2 (E2 target) held fixed."""
    _step   = 0.25
    t1_vals = [round(r * _step, 2) for r in range(1, max(1, round(max_t1 / _step)) + 1)]
    t3_vals = [round(r * _step, 2) for r in range(2, max(2, round(max_t3 / _step)) + 1)]
    rows = []
    for t1 in t1_vals:
        for t3 in t3_vals:
            if t1 >= t2_r_fixed or t2_r_fixed >= t3:
                continue
            res = simulate_trades(
                signals, ticks_by_date, t3,
                entry_slip, exit_slip, stop_offset,
                tick_value, e1c, commission,
                bars_by_date=bars_by_date,
                threeleg=True, t1_r=t1, t2_r=t2_r_fixed, t1_action=t1_action,
                contracts_e1=e1c, contracts_e2=e2c, contracts_e3=e3c,
                pb1_r=pb1_r, pb1_ticks=pb1_ticks,
                pb2_r=pb2_r, pb2_ticks=pb2_ticks,
                ratchet_r=0.0,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            total_c = e1c + e2c + e3c
            s = compute_summary(res, commission, contracts=total_c, is_multileg=False)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            rows.append({
                "T1":      t1,
                "T3":      t3,
                "Win %":   round(s["win_pct"], 1),
                "PF":      round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL": round(s["net_total"], 0),
                "DD $":    round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":  round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":   round(s["exp_dollar"], 0),
            })
    return pd.DataFrame(rows)


_SWEEP_GREEN   = "#1a9850"  # heatmap RdYlGn max color
_STOP_MULTS    = [0.25, 0.33, 0.50, 0.66, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]


def _apply_stop_mult(signals: pd.DataFrame, mult: float) -> pd.DataFrame:
    """Return a copy of signals with StopPrice scaled by mult relative to SignalPrice."""
    sigs = signals.copy()
    long_mask  = sigs["Direction"] == "Long"
    short_mask = ~long_mask
    dist_long  = sigs.loc[long_mask,  "SignalPrice"] - sigs.loc[long_mask,  "StopPrice"]
    dist_short = sigs.loc[short_mask, "StopPrice"]   - sigs.loc[short_mask, "SignalPrice"]
    sigs.loc[long_mask,  "StopPrice"] = sigs.loc[long_mask,  "SignalPrice"] - dist_long  * mult
    sigs.loc[short_mask, "StopPrice"] = sigs.loc[short_mask, "SignalPrice"] + dist_short * mult
    return sigs


def _run_stop_mult_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    target_r: float, bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
    progress_cb=None, mults: list | None = None,
) -> pd.DataFrame:
    """Sweep stop multipliers at the current target R."""
    if mults is None:
        mults = _STOP_MULTS
    rows = []
    total = len(mults)
    for i, mult in enumerate(mults):
        if progress_cb:
            progress_cb((i + 1) / total, f"Stop {mult:.2f}× ({i+1}/{total})")
        sigs = _apply_stop_mult(signals, mult)
        res  = simulate_trades(sigs, ticks_by_date, target_r,
                               entry_slip, exit_slip, stop_offset,
                               tick_value, contracts, commission,
                               bars_by_date=bars_by_date,
                               multileg=multileg, t1_r=t1_r,
                               t1_action=t1_action,
                               contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
        s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                            t1_action=t1_action,
                            contracts_t1=contracts_t1, contracts_t2=contracts_t2)
        if not s or s["n_trades"] == 0:
            continue
        _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
        rows.append({
            "Stop Mult": f"{mult:.2f}×",
            "Win %":     round(s["win_pct"], 1),
            "PF":        round(s["pf"], 2) if s["pf"] < 99 else 99.9,
            "Net PnL":   round(s["net_total"], 0),
            "DD $":      round(_dd_abs, 0) if _dd_abs else 0.0,
            "PnL/DD":    round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
            "Exp $":     round(s["exp_dollar"], 0),
        })
    return pd.DataFrame(rows)


def _run_stop_target_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    stop_mults: list | None = None,
    target_rs:  list | None = None,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
    progress_cb=None,
) -> pd.DataFrame:
    """2-D grid sweep over (stop_mult × target_r), single-leg by default.

    R is measured in stop units, so the stop axis also moves the *absolute*
    target — the two parameters interact and the joint optimum can differ from
    chaining the two 1-D sweeps. This crosses both axes so the real surface is
    visible. Reuses _apply_stop_mult (stop scaling), simulate_trades +
    _apply_day_trade_filters + compute_summary (exact engine path), and
    _win_breakdown (Tgt%/EOD decomposition). Descriptive only — never a WFA input.

    Built-in cross-check: the stop_mult = 1.00× column reproduces the 1-D R
    sweep exactly, and the row at any given target_r reproduces the 1-D stop
    sweep at that target.
    """
    if stop_mults is None:
        stop_mults = _STOP_MULTS
    if target_rs is None:
        target_rs = [round(r * 0.25, 2) for r in range(2, 21)]   # 0.50 – 5.00

    rows = []
    total = len(stop_mults) * len(target_rs)
    i = 0
    for mult in stop_mults:
        sigs = _apply_stop_mult(signals, mult)          # scale stop ONCE per column
        for tr in target_rs:
            i += 1
            if progress_cb:
                progress_cb(i / total, f"Stop {mult:.2f}× · T {tr:.2f}R ({i}/{total})")
            res = simulate_trades(
                sigs, ticks_by_date, tr,
                entry_slip, exit_slip, stop_offset,
                tick_value, contracts, commission,
                bars_by_date=bars_by_date,
                multileg=multileg, t1_r=t1_r, t1_action=t1_action,
                contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                                t1_action=t1_action,
                                contracts_t1=contracts_t1, contracts_t2=contracts_t2)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            tgt_pct, eodw_pct, eodw_r = _win_breakdown(res)
            rows.append({
                "Stop Mult": f"{mult:.2f}×",
                "R":         tr,
                "Win %":     round(s["win_pct"], 1),
                "Tgt %":     tgt_pct,
                "EOD Win %": eodw_pct,
                "PF":        round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL":   round(s["net_total"], 0),
                "DD $":      round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":    round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":     round(s["exp_dollar"], 0),
                "Trades":    int(s["n_trades"]),
            })
    return pd.DataFrame(rows)


def _show_stop_sweep(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                     tick_value, contracts, commission, target_r, bars_by_date=None,
                     multileg: bool = False, t1_r: float = 1.0,
                     t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
                     first_trade_only: bool = False, first_2_filled_only: bool = False):
    _METRIC_COLS = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS  = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}
    with st.expander("🔍 Stop Multiplier Sweep", expanded=False):
        st.caption(
            "Runs simulation at multiple stop sizes "
            f"(multiplier of the original signal stop) at the current target R = {target_r:.2f}. "
            "1.00× is the baseline (original stop). Target scales proportionally with the stop."
        )
        _sc1, _sc2 = st.columns(2)
        _sm_min = _sc1.select_slider("Min stop mult", options=_STOP_MULTS,
                                     value=0.75, key="ba_stop_min")
        _sm_max = _sc2.select_slider("Max stop mult", options=_STOP_MULTS,
                                     value=1.50, key="ba_stop_max")
        _sel_mults = [m for m in _STOP_MULTS if _sm_min <= m <= _sm_max]
        st.caption(f"**{len(_sel_mults)}** stop sizes: "
                   f"{', '.join(f'{m:.2f}×' for m in _sel_mults)}")

        if st.button("Run Stop Sweep", key="ba_run_stop_sweep"):
            _prog = st.progress(0.0)
            _stat = st.empty()
            def _stop_cb(pct, msg):
                _prog.progress(pct)
                _stat.caption(msg)
            with st.spinner("Running stop sweep…"):
                stop_df = _run_stop_mult_sweep(
                    signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission, target_r,
                    bars_by_date=bars_by_date, multileg=multileg, t1_r=t1_r,
                    t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    progress_cb=_stop_cb, mults=_sel_mults,
                )
            _prog.empty()
            _stat.empty()
            if stop_df.empty:
                st.warning("No results.")
                return
            st.session_state["ba_stop_sweep_df"] = stop_df

        stop_df = st.session_state.get("ba_stop_sweep_df")
        if stop_df is None or stop_df.empty:
            return

        fmt_map = {"Win %": "{:.1f}", "PF": "{:.2f}", "PnL/DD": "{:.2f}"}
        fmt_map.update({"Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"})
        styled = _apply_best_green(stop_df, stop_df.style.format(fmt_map),
                                   _METRIC_COLS, _THRESHOLDS)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        fig = go.Figure()
        fig.add_scatter(x=stop_df["Stop Mult"], y=stop_df["Net PnL"],
                        name="Net PnL ($)", mode="lines+markers",
                        line=dict(color="#26a69a", width=2))
        fig.add_scatter(x=stop_df["Stop Mult"], y=stop_df["PF"],
                        name="Profit Factor", mode="lines+markers",
                        yaxis="y2", line=dict(color="#ff9800", width=2))
        fig.update_layout(
            xaxis_title="Stop Multiplier",
            yaxis=dict(title="Net PnL ($)"),
            yaxis2=dict(title="PF", overlaying="y", side="right"),
            height=300, template="plotly_white",
            legend=dict(x=0.01, y=0.99),
        )
        st.plotly_chart(fig, use_container_width=True)


def _stop_target_plateau(df: pd.DataFrame):
    """Neighbor-stability of the best PnL/DD cell on the stop×target grid.

    Returns (best_val, stop_lbl, r_val, n_within, n_tot, tgt_pct, trades) where
    n_within of n_tot of the 8 grid neighbors are within 10% of the best cell.
    This is the anti-overfit guardrail: a lone spike whose neighbors fall away is
    in-sample luck; a stable plateau is a robust region.
    """
    piv = df.pivot(index="Stop Mult", columns="R", values="PnL/DD")
    row_order = sorted(piv.index, key=lambda s: float(str(s).rstrip("×")))
    piv = piv.reindex(row_order)
    arr = piv.values
    if not np.isfinite(arr).any():
        return None
    bi, bj = np.unravel_index(np.nanargmax(arr), arr.shape)
    best = arr[bi, bj]
    n_within = n_tot = 0
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            ii, jj = bi + di, bj + dj
            if 0 <= ii < arr.shape[0] and 0 <= jj < arr.shape[1]:
                v = arr[ii, jj]
                if np.isfinite(v):
                    n_tot += 1
                    if best != 0 and abs(v - best) <= 0.10 * abs(best):
                        n_within += 1
    stop_lbl = row_order[bi]
    r_val    = piv.columns[bj]
    cell = df[(df["Stop Mult"] == stop_lbl) & (df["R"] == r_val)]
    tgt_pct = float(cell["Tgt %"].iloc[0]) if not cell.empty else float("nan")
    trades  = int(cell["Trades"].iloc[0]) if not cell.empty else 0
    return best, stop_lbl, r_val, n_within, n_tot, tgt_pct, trades


def _show_stop_target_sweep(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                            tick_value, contracts, commission, bars_by_date=None,
                            multileg=False, t1_r=1.0, t1_action="exit",
                            contracts_t1=1, contracts_t2=1,
                            first_trade_only=False, first_2_filled_only=False):
    _METRIC_COLS = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS  = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}
    with st.expander("🔍 2-D Stop × Target Sweep", expanded=False):
        st.caption(
            "Crosses stop size (× baseline stop) with target R. Because R is measured "
            "in stop units, these two interact — the joint optimum can differ from "
            "chaining the two 1-D sweeps. Read the surface for a stable PLATEAU, not a "
            "lone peak. Descriptive only: this never feeds the WFA optimizer."
        )

        _c1, _c2, _c3 = st.columns(3)
        with _c1:
            st.caption("**Stop range** (× baseline)")
            _sm_min = st.select_slider("Min stop mult", options=_STOP_MULTS,
                                       value=0.50, key="ba_st_stop_min")
            _sm_max = st.select_slider("Max stop mult", options=_STOP_MULTS,
                                       value=1.25, key="ba_st_stop_max")
        with _c2:
            st.caption("**Target range** (R)")
            _r_min = st.number_input("Min R", min_value=0.50, max_value=10.0,
                                     value=0.50, step=0.25, key="ba_st_r_min")
            _r_max = st.number_input("Max R", min_value=0.50, max_value=10.0,
                                     value=3.00, step=0.25, key="ba_st_r_max")
        _sel_mults = [m for m in _STOP_MULTS if _sm_min <= m <= _sm_max]
        _lo, _hi = sorted((_r_min, _r_max))
        _target_rs = [round(r * 0.25, 2) for r in
                      range(max(2, round(_lo / 0.25)), round(_hi / 0.25) + 1)]

        # filter-aware signal count (mirrors the scale-in expander)
        _st_ok = signals[signals.get("FilterStatus", pd.Series("ok", index=signals.index)) == "ok"]
        _st_sig = len(_st_ok)
        if first_2_filled_only:
            _st_sig = len(_st_ok.sort_values(["Date", "SignalNum"]).groupby("Date").head(2))
        elif first_trade_only:
            _st_sig = len(_st_ok.sort_values(["Date", "SignalNum"]).groupby("Date").head(1))

        _n_combos = len(_sel_mults) * len(_target_rs)
        with _c3:
            st.caption("**Grid size**")
            st.markdown(f"{len(_sel_mults)} stops × {len(_target_rs)} targets = "
                        f"**{_n_combos} combos**")
            st.caption(f"{_st_sig} signals")
        if _n_combos > 200:
            st.warning(f"{_n_combos} combos — each is a full engine simulation; this "
                       "will be slow. Narrow a range to reduce it.")
        if not _sel_mults or not _target_rs:
            st.info("Pick a non-empty stop and target range.")
            return

        if st.button("Run 2-D Sweep", key="ba_run_st_sweep"):
            _prog = st.progress(0.0)
            _stat = st.empty()
            def _st_cb(pct, msg):
                _prog.progress(pct)
                _stat.caption(msg)
            with st.spinner(f"Running 2-D stop×target sweep ({_n_combos} combos)…"):
                st_df = _run_stop_target_sweep(
                    signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission,
                    bars_by_date=bars_by_date, multileg=multileg, t1_r=t1_r,
                    t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    stop_mults=_sel_mults, target_rs=_target_rs,
                    first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    progress_cb=_st_cb,
                )
            _prog.empty()
            _stat.empty()
            if st_df.empty:
                st.warning("No results.")
                return
            st.session_state["ba_st_sweep_df"] = st_df

        st_df = st.session_state.get("ba_st_sweep_df")
        if st_df is None or st_df.empty:
            return

        _metric = st.selectbox(
            "Color heatmap by", ["PnL/DD", "Net PnL", "PF", "Exp $", "Win %"],
            key="ba_st_metric",
        )

        # ── Heatmap (Stop Mult × Target R) ───────────────────────────────────
        _pivot = st_df.pivot(index="Stop Mult", columns="R", values=_metric)
        _row_order = sorted(_pivot.index, key=lambda s: float(str(s).rstrip("×")))
        _pivot = _pivot.reindex(_row_order)
        _x_labels = [f"{v:.2f}" for v in _pivot.columns]
        _hover = "Stop: %{y}<br>Target R: %{x}<br>" + _metric + ": %{z}<extra></extra>"
        _hfig = go.Figure(go.Heatmap(
            x=_x_labels, y=list(_pivot.index),
            z=_pivot.values.tolist(),
            colorscale="RdYlGn",
            hovertemplate=_hover,
            colorbar=dict(title=_metric, thickness=14),
        ))
        _hfig.update_layout(
            xaxis_title="Target (R)", yaxis_title="Stop Mult",
            height=420, template="plotly_white",
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(_hfig, use_container_width=True)

        # ── Plateau caption (anti-overfit guardrail) ─────────────────────────
        _pl = _stop_target_plateau(st_df)
        if _pl:
            _best, _slbl, _rval, _nw, _nt, _tgt, _trd = _pl
            _stable = _nt > 0 and _nw >= max(1, round(0.5 * _nt))
            _verdict = ("stable plateau" if _stable
                        else "isolated peak — treat as overfit")
            _emoji = "🟢" if _stable else "🔴"
            st.markdown(
                f"{_emoji} **Best PnL/DD {_best:.2f} at {_slbl}/{_rval:.2f}R — "
                f"{_nw}/{_nt} neighbors within 10% ({_verdict}).** "
                f"That cell: {_trd} trades, Tgt% {_tgt:.1f}."
            )
            if _tgt < 30:
                st.caption("⚠️ Low Tgt% at the winner — profit is mostly EOD closes, "
                           "not target hits; this isn't really a stop/target edge.")
            if _trd < 30:
                st.caption("⚠️ Thin trade count at the winner — unreliable regardless "
                           "of metric.")

        # ── Ranked top-20 table ──────────────────────────────────────────────
        st.caption(f"Top 20 cells by **{_metric}**")
        _ranked = st_df.sort_values(_metric, ascending=False).head(20).reset_index(drop=True)
        _ranked.index = _ranked.index + 1
        _fmt = {"R": "{:.2f}", "Win %": "{:.1f}", "Tgt %": "{:.1f}", "EOD Win %": "{:.1f}",
                "PF": "{:.2f}", "PnL/DD": "{:.2f}", "Trades": "{:.0f}",
                "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
        _styled = _apply_best_green(
            _ranked, _ranked.style.format(_fmt), _METRIC_COLS, _THRESHOLDS
        )
        st.dataframe(_styled, use_container_width=True)


def _apply_best_green(sweep_df: pd.DataFrame, styled, metric_cols: list[str],
                      thresholds: dict | None = None):
    """Highlight only the single best value per column in heatmap-green.
    threshold dict: {col: min_value_to_qualify} — no highlight if best < threshold."""
    thresholds = thresholds or {}

    def _hl_max(s, thr=0):
        best = s.max()
        if best <= thr:
            return [""] * len(s)
        return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                if v == best else "" for v in s]

    def _hl_min(s):
        best = s.min()
        return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                if v == best else "" for v in s]

    for col in metric_cols:
        if col not in sweep_df.columns:
            continue
        if col == "DD $":
            styled = styled.apply(_hl_min, subset=[col])
        else:
            thr = thresholds.get(col, 0)
            styled = styled.apply(_hl_max, thr=thr, subset=[col])
    return styled


def _show_optimal_r(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission, bars_by_date=None,
                    multileg: bool = False, t1_r: float = 1.0,
                    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
                    threeleg: bool = False,
                    tv_e1: float = 0.0, tv_e2: float = 0.0, tv_e3: float = 0.0,
                    e1c: int = 1, e2c: int = 1, e3c: int = 1,
                    pb1_ticks: int = 0, pb2_ticks: int = 0,
                    t2_r: float = 0.0,
                    ratchet_r: float = 0.0, ratchet_dest: str = "BE", ratchet_lock_r: float = 0.0,
                    scale_in_style: str = "e2", pb_round: str = "nearest",
                    first_trade_only: bool = False, first_2_filled_only: bool = False):

    _METRIC_COLS  = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS   = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}

    if threeleg:
        # ── 2D PB1×PB2 grid sweep ─────────────────────────────────────────────
        with st.expander("🔍 PB1×PB2 Sweep", expanded=False):
            st.caption(
                "Sweeps pullback entry levels (as R distance back from E1) with tick offsets held fixed. "
                "Ratchet is disabled during sweep for clean robustness testing."
            )
            _rc1, _rc2 = st.columns(2)
            _max_pb1 = _rc1.number_input(
                "Max PB1 (R back)", min_value=0.25, max_value=3.0,
                value=float(st.session_state.get("ba_sweep_max_pb1", 1.5)),
                step=0.25, format="%.2f", key="ba_sweep_max_pb1",
            )
            _max_pb2 = _rc2.number_input(
                "Max PB2 (R back)", min_value=0.5, max_value=4.0,
                value=float(st.session_state.get("ba_sweep_max_pb2", 2.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_pb2",
            )
            _n_pb1 = max(1, round(_max_pb1 / 0.25))
            _n_pb2 = max(2, round(_max_pb2 / 0.25))
            _n_combos = sum(1 for p1 in range(1, _n_pb1 + 1)
                              for p2 in range(2, _n_pb2 + 1)
                              if p2 > p1)
            st.caption(f"PB1: 0.25–{_max_pb1:.2f}R × PB2: 0.50–{_max_pb2:.2f}R — {_n_combos} combinations")

            if st.button("Run PB1×PB2 Sweep", key="ba_run_pb_sweep"):
                with st.spinner(f"Running PB1×PB2 sweep ({_n_combos} combinations)…"):
                    _pb_df = _run_pb_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                        tick_value, commission,
                        target_r=float(st.session_state.get("ba_target_r_3l", 3.0)),
                        t1_r=t1_r, t2_r=t2_r, t1_action=t1_action,
                        tv_e1=tv_e1, tv_e2=tv_e2, tv_e3=tv_e3,
                        e1c=e1c, e2c=e2c, e3c=e3c,
                        pb1_ticks=pb1_ticks, pb2_ticks=pb2_ticks,
                        ratchet_r=0.0, ratchet_dest="BE", ratchet_lock_r=0.0,
                        bars_by_date=bars_by_date,
                        max_pb1=_max_pb1, max_pb2=_max_pb2,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _pb_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_pb_sweep_df"] = _pb_df

            sweep_df = st.session_state.get("ba_pb_sweep_df")
            if sweep_df is None or sweep_df.empty:
                return

            _metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
            _metric = st.selectbox("Color heatmap by", _metric_opts, key="ba_pb_metric")

            _pivot = sweep_df.pivot(index="PB1", columns="PB2", values=_metric)
            _pb1_labels = [f"{v:.2f}" for v in _pivot.index]
            _pb2_labels = [f"{v:.2f}" for v in _pivot.columns]
            _hover = "PB1: %{y}R back<br>PB2: %{x}R back<br>" + _metric + ": %{z}<extra></extra>"
            _hfig = go.Figure(go.Heatmap(
                x=_pb2_labels, y=_pb1_labels, z=_pivot.values.tolist(),
                colorscale="RdYlGn", hovertemplate=_hover,
                colorbar=dict(title=_metric, thickness=14),
            ))
            _hfig.update_layout(
                xaxis_title="PB2 (R back)", yaxis_title="PB1 (R back)",
                height=400, template="plotly_white",
                margin=dict(l=60, r=20, t=30, b=60),
            )
            st.plotly_chart(_hfig, use_container_width=True)

            st.caption(f"Top 20 combinations by **{_metric}**")
            _ranked = sweep_df.sort_values(_metric, ascending=False).head(20).reset_index(drop=True)
            _ranked.index = _ranked.index + 1
            _fmt = {"PB1": "{:.2f}", "PB2": "{:.2f}", "Win %": "{:.1f}",
                    "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                    "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
            _styled = _apply_best_green(_ranked, _ranked.style.format(_fmt), _METRIC_COLS, _THRESHOLDS)
            st.dataframe(_styled, use_container_width=True)

        # ── T1×T3 sweep for 3-leg (T2 held fixed at current value) ───────────
        with st.expander("🔍 T1×T3 Sweep (3-Leg)", expanded=False):
            _t2_fixed = t2_r if t2_r > 0 else float(st.session_state.get("ba_t2_r_3l", 2.0))
            st.caption(
                f"Sweeps T1 (E1 target) × T3 (E3 target) with T2={_t2_fixed:.2f}R (E2 target) held fixed. "
                "PB levels and ratchet disabled."
            )
            _t3c1, _t3c2 = st.columns(2)
            _max_t1_3l = _t3c1.number_input(
                "Max T1 (R)", min_value=0.25, max_value=5.0,
                value=float(st.session_state.get("ba_sweep_max_t1_3l", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t1_3l",
            )
            _max_t3_3l = _t3c2.number_input(
                "Max T3 (R)", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_t3_3l", 5.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t3_3l",
            )
            _n_t1_3l = max(1, round(_max_t1_3l / 0.25))
            _n_t3_3l = max(2, round(_max_t3_3l / 0.25))
            _n_combos_t = sum(1 for t1i in range(1, _n_t1_3l + 1)
                               for t3i in range(2, _n_t3_3l + 1)
                               if t1i < _t2_fixed / 0.25 and _t2_fixed / 0.25 < t3i)
            st.caption(f"T1: 0.25–{_max_t1_3l:.2f}R × T3: 0.50–{_max_t3_3l:.2f}R — {_n_combos_t} combinations")

            if st.button("Run T1×T3 Sweep", key="ba_run_t1t2_3l"):
                _pb1_cur = float(st.session_state.get("ba_pb1_r_3l", 0.33))
                _pb2_cur = float(st.session_state.get("ba_pb2_r_3l", 0.66))
                with st.spinner(f"Running T1×T3 sweep ({_n_combos_t} combinations)…"):
                    _t1t2_3l_df = _run_t1t2_sweep_3leg(
                        signals, ticks_by_date,
                        entry_slip, exit_slip, stop_offset,
                        tick_value, commission,
                        t2_r_fixed=_t2_fixed, t1_action=t1_action,
                        tv_e1=tv_e1, tv_e2=tv_e2, tv_e3=tv_e3,
                        e1c=e1c, e2c=e2c, e3c=e3c,
                        pb1_r=_pb1_cur, pb1_ticks=pb1_ticks,
                        pb2_r=_pb2_cur, pb2_ticks=pb2_ticks,
                        bars_by_date=bars_by_date,
                        max_t1=_max_t1_3l, max_t3=_max_t3_3l,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _t1t2_3l_df.empty:
                    st.warning("No results.")
                else:
                    st.session_state["ba_t1t2_3l_df"] = _t1t2_3l_df

            _t1t2_3l_res = st.session_state.get("ba_t1t2_3l_df")
            if _t1t2_3l_res is not None and not _t1t2_3l_res.empty:
                _t3_metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _t3_metric = st.selectbox("Color heatmap by", _t3_metric_opts, key="ba_t1t2_3l_metric")

                _pivot_t = _t1t2_3l_res.pivot(index="T1", columns="T3", values=_t3_metric)
                _t1_labels = [f"{v:.2f}" for v in _pivot_t.index]
                _t2_labels = [f"{v:.2f}" for v in _pivot_t.columns]
                _hover_t = "T1: %{y}R<br>T3: %{x}R<br>" + _t3_metric + ": %{z}<extra></extra>"
                _tfig = go.Figure(go.Heatmap(
                    x=_t2_labels, y=_t1_labels, z=_pivot_t.values.tolist(),
                    colorscale="RdYlGn", hovertemplate=_hover_t,
                    colorbar=dict(title=_t3_metric, thickness=14),
                ))
                _tfig.update_layout(
                    xaxis_title="T2 (R)", yaxis_title="T1 (R)",
                    height=400, template="plotly_white",
                    margin=dict(l=60, r=20, t=30, b=60),
                )
                st.plotly_chart(_tfig, use_container_width=True)

                st.caption(f"Top 20 combinations by **{_t3_metric}**")
                _t_ranked = _t1t2_3l_res.sort_values(_t3_metric, ascending=False).head(20).reset_index(drop=True)
                _t_ranked.index = _t_ranked.index + 1
                _t_fmt = {"T1": "{:.2f}", "T3": "{:.2f}", "Win %": "{:.1f}",
                          "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                          "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _t_styled = _apply_best_green(_t_ranked, _t_ranked.style.format(_t_fmt), _METRIC_COLS, _THRESHOLDS)
                st.dataframe(_t_styled, use_container_width=True)

    elif multileg:
        # ── 2D T1×T2 grid sweep ───────────────────────────────────────────────
        with st.expander("🔍 T1×T2 Sweep", expanded=False):
            _rc1, _rc2 = st.columns(2)
            _max_t1 = _rc1.number_input(
                "Max T1 (R)", min_value=0.5, max_value=5.0,
                value=float(st.session_state.get("ba_sweep_max_t1", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t1",
            )
            _max_t2 = _rc2.number_input(
                "Max T2 (R)", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_t2", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_t2",
            )
            _n_t1 = max(1, round(_max_t1 / 0.25))
            _n_t2 = max(1, round(_max_t2 / 0.25))
            _n_combos = sum(1 for t1i in range(1, _n_t1 + 1)
                              for t2i in range(2, _n_t2 + 1)
                              if t1i < t2i)
            st.caption(f"T1: 0.25–{_max_t1:.2f} × T2: 0.50–{_max_t2:.2f} — {_n_combos} combinations")

            if st.button("Run T1×T2 Sweep", key="ba_run_sweep"):
                with st.spinner(f"Running T1×T2 sweep ({_n_combos} combinations)…"):
                    _t1t2_df = _run_t1t2_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                        tick_value, contracts, commission,
                        bars_by_date=bars_by_date, t1_action=t1_action,
                        contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                        max_t1=_max_t1, max_t2=_max_t2,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if _t1t2_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_t1t2_df"] = _t1t2_df

            sweep_df = st.session_state.get("ba_t1t2_df")
            if sweep_df is not None and not sweep_df.empty:
                _metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _metric = st.selectbox(
                    "Color heatmap by", _metric_opts,
                    key="ba_t1t2_metric",
                )

                # ── Heatmap ───────────────────────────────────────────────────
                _pivot = sweep_df.pivot(index="T1", columns="T2", values=_metric)
                _t1_labels = [f"{v:.2f}" for v in _pivot.index]
                _t2_labels = [f"{v:.2f}" for v in _pivot.columns]

                _hover = "T1: %{y}<br>T2: %{x}<br>" + _metric + ": %{z}<extra></extra>"
                _hfig = go.Figure(go.Heatmap(
                    x=_t2_labels, y=_t1_labels,
                    z=_pivot.values.tolist(),
                    colorscale="RdYlGn",
                    hovertemplate=_hover,
                    colorbar=dict(title=_metric, thickness=14),
                ))
                _hfig.update_layout(
                    xaxis_title="T2 (R)", yaxis_title="T1 (R)",
                    height=420, template="plotly_white",
                    margin=dict(l=60, r=20, t=30, b=60),
                )
                st.plotly_chart(_hfig, use_container_width=True)

                # ── Ranked table ──────────────────────────────────────────────
                st.caption(f"Top 20 combinations by **{_metric}**")
                _ranked = sweep_df.sort_values(_metric, ascending=False).head(20).reset_index(drop=True)
                _ranked.index = _ranked.index + 1

                _fmt = {"T1": "{:.2f}", "T2": "{:.2f}", "Win %": "{:.1f}",
                        "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                        "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _styled = _apply_best_green(
                    _ranked, _ranked.style.format(_fmt), _METRIC_COLS, _THRESHOLDS
                )
                def _hl_rank1_t1t2(s):
                    return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                            if i == s.index[0] else "" for i in s.index]
                for _tc in ("T1", "T2"):
                    if _tc in _ranked.columns:
                        _styled = _styled.apply(_hl_rank1_t1t2, subset=[_tc])
                st.dataframe(_styled, use_container_width=True)

        # ── Scale-In sweep: PB × T1 × T2 ─────────────────────────────────────
        with st.expander("🔍 Scale-In Sweep (PB × T1 × T2)", expanded=False):
            _all_pb = [-0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50]
            _all_t1 = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
            _all_t2 = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
            _pb_lbl = [f"{v:.2f}R" for v in _all_pb]
            _t1_lbl = [f"{v:.2f}R" for v in _all_t1]
            _t2_lbl = [f"{v:.2f}R" for v in _all_t2]

            _sc1, _sc2, _sc3 = st.columns(3)
            with _sc1:
                st.caption("**PB range**")
                _pb_from_sel = st.selectbox("Shallowest", _pb_lbl, index=0, key="ba_si_pb_from")
                _pb_to_sel   = st.selectbox("Deepest",    _pb_lbl, index=3, key="ba_si_pb_to")
            with _sc2:
                st.caption("**T1 range**")
                _t1_from_sel = st.selectbox("Min T1", _t1_lbl, index=0, key="ba_si_t1_from")
                _t1_to_sel   = st.selectbox("Max T1", _t1_lbl, index=5, key="ba_si_t1_to")
            with _sc3:
                st.caption("**T2 range**")
                _t2_from_sel = st.selectbox("Min T2", _t2_lbl, index=0, key="ba_si_t2_from")
                _t2_to_sel   = st.selectbox("Max T2", _t2_lbl, index=6, key="ba_si_t2_to")

            _pb_from_i = _pb_lbl.index(_pb_from_sel)
            _pb_to_i   = _pb_lbl.index(_pb_to_sel)
            _t1_from_i = _t1_lbl.index(_t1_from_sel)
            _t1_to_i   = _t1_lbl.index(_t1_to_sel)
            _t2_from_i = _t2_lbl.index(_t2_from_sel)
            _t2_to_i   = _t2_lbl.index(_t2_to_sel)

            _sweep_pb = _all_pb[min(_pb_from_i, _pb_to_i) : max(_pb_from_i, _pb_to_i) + 1]
            _sweep_t1 = _all_t1[min(_t1_from_i, _t1_to_i) : max(_t1_from_i, _t1_to_i) + 1]
            _sweep_t2 = _all_t2[min(_t2_from_i, _t2_to_i) : max(_t2_from_i, _t2_to_i) + 1]
            _si_n = len(_sweep_pb) * len(_sweep_t1) * len(_sweep_t2)
            _use_t1_cap = st.checkbox("Apply data-driven T1 ceiling", value=False, key="ba_si_use_t1_cap",
                                      help="Runs a pre-sweep simulation to find the 95th-pct MFE and prunes T1 values above it. Useful when sweeping a wide T1 range; skip it if your Max T1 is already conservative (≤ 2–3R).")
            _cap_suffix = " (T1 auto-capped at run time)" if _use_t1_cap else ""
            _si_ok = signals[signals.get("FilterStatus", pd.Series("ok", index=signals.index)) == "ok"]
            _si_sig_count = len(_si_ok)
            if first_2_filled_only:
                _si_sig_count = len(_si_ok.sort_values(["Date", "SignalNum"]).groupby("Date").head(2))
            elif first_trade_only:
                _si_sig_count = len(_si_ok.sort_values(["Date", "SignalNum"]).groupby("Date").head(1))
            st.caption(f"PB: {len(_sweep_pb)} values · T1: {len(_sweep_t1)} values · T2: {len(_sweep_t2)} values — **{_si_n} combinations**{_cap_suffix} · **{_si_sig_count} signals**")

            if st.button("Run Scale-In Sweep", key="ba_run_si_sweep"):
                if _use_t1_cap:
                    with st.spinner("Computing T1 ceiling from data…"):
                        _bl_res  = simulate_trades(
                            signals, ticks_by_date, 999.0,
                            entry_slip, exit_slip, stop_offset,
                            tick_value, contracts_t1, commission,
                            bars_by_date=bars_by_date, multileg=False,
                        )
                        _bl_res  = _apply_day_trade_filters(_bl_res, first_trade_only, first_2_filled_only)
                        _mfe_ser = _bl_res[_bl_res["Filled"] == True]["MFE_R"]
                        _t1_cap  = float(round(_mfe_ser.quantile(0.95) * 4) / 4) if not _mfe_ser.empty else 10.0
                        st.session_state["ba_si_t1_cap"] = _t1_cap
                    _sweep_t1_capped = [v for v in _sweep_t1 if v <= _t1_cap] or [_sweep_t1[0]]
                else:
                    _t1_cap = None
                    _sweep_t1_capped = _sweep_t1
                _si_n_actual = len(_sweep_pb) * len(_sweep_t1_capped) * len(_sweep_t2)
                _cap_str = f", T1 ≤ {_t1_cap:.2f}R" if _t1_cap is not None else ""
                _si_prog = st.progress(0.0, text=f"Scale-in sweep: 0 / {_si_n_actual}")
                _si_df = _run_ml_scalein_sweep(
                    signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission,
                    contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                    bars_by_date=bars_by_date,
                    pb_vals=_sweep_pb, t1_vals=_sweep_t1_capped, t2_vals=_sweep_t2,
                    first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    scale_in_style=scale_in_style, pb_round=pb_round,
                    progress_bar=_si_prog,
                )
                _si_prog.empty()
                if _si_df.empty:
                    st.warning("No scale-in results.")
                else:
                    st.session_state["ba_si_sweep_df"] = _si_df

            _si_res = st.session_state.get("ba_si_sweep_df")
            if _si_res is not None and "T1_R" not in _si_res.columns:
                # stale result from old 2-param sweep — discard it
                st.session_state.pop("ba_si_sweep_df", None)
                _si_res = None
            if _si_res is not None and not _si_res.empty:
                _si_metric_opts = ["Net PnL", "PF", "Win %", "PnL/DD", "Exp $"]
                _si_c1, _si_c2 = st.columns(2)
                _si_metric  = _si_c1.selectbox("Color heatmap by", _si_metric_opts, key="ba_si_metric")
                _si_t1_vals = sorted(_si_res["T1_R"].unique())
                _si_t1_lbls = [f"{v:.2f}R" for v in _si_t1_vals]
                _si_t1_sel  = _si_c2.selectbox("T1 slice (heatmap)", _si_t1_lbls, key="ba_si_t1_slice")
                _si_t1_val  = _si_t1_vals[_si_t1_lbls.index(_si_t1_sel)]

                _si_slice = _si_res[_si_res["T1_R"] == _si_t1_val]
                if not _si_slice.empty:
                    _si_pivot  = _si_slice.pivot(index="PB_R", columns="T2_R", values=_si_metric)
                    _pb_lbls_h = [f"{v:.2f}" for v in _si_pivot.index]
                    _t2_lbls_h = [f"{v:.2f}" for v in _si_pivot.columns]
                    _si_hover  = f"T1={_si_t1_val:.2f}R<br>PB: %{{y}}R<br>T2: %{{x}}R<br>{_si_metric}: %{{z}}<extra></extra>"
                    _si_fig = go.Figure(go.Heatmap(
                        x=_t2_lbls_h, y=_pb_lbls_h,
                        z=_si_pivot.values.tolist(),
                        colorscale="RdYlGn",
                        hovertemplate=_si_hover,
                        colorbar=dict(title=_si_metric, thickness=14),
                    ))
                    _si_fig.update_layout(
                        title=f"PB × T2  (T1 = {_si_t1_val:.2f}R)",
                        xaxis_title="T2 (R from blended entry)",
                        yaxis_title="E2 Pullback (R from entry)",
                        height=380, template="plotly_white",
                        margin=dict(l=80, r=20, t=40, b=60),
                    )
                    st.plotly_chart(_si_fig, use_container_width=True)

                _t1_cap_shown = st.session_state.get("ba_si_t1_cap")
                if _t1_cap_shown:
                    st.info(
                        f"**T1 ceiling applied: {_t1_cap_shown:.2f}R** — "
                        f"computed as the 95th percentile of unconstrained MFE across all filled signals "
                        f"(single-leg sim, target = 999R). "
                        f"T1 values above {_t1_cap_shown:.2f}R would produce a ~0% T1-only rate and were excluded from the sweep.",
                        icon="📐",
                    )
                st.caption(f"Top 20 combinations (all T1) by **{_si_metric}**")
                _si_ranked = _si_res.sort_values(_si_metric, ascending=False).head(20).reset_index(drop=True)
                _si_ranked.index = _si_ranked.index + 1
                _si_fmt = {"PB_R": "{:.2f}", "T1_R": "{:.2f}", "T2_R": "{:.2f}",
                           "T1 %": "{:.1f}", "T2 %": "{:.1f}",
                           "Tgt %": "{:.1f}", "EOD Win %": "{:.1f}", "EOD Win R": "{:.2f}",
                           "Win %": "{:.1f}",
                           "PF": "{:.2f}", "PnL/DD": "{:.2f}",
                           "Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"}
                _si_styled = _apply_best_green(
                    _si_ranked, _si_ranked.style.format(_si_fmt), _METRIC_COLS, _THRESHOLDS
                )
                def _hl_rank1_si(s):
                    return [f"background-color: {_SWEEP_GREEN}; color: white; font-weight: bold"
                            if i == s.index[0] else "" for i in s.index]
                for _sc in ("PB_R", "T1_R", "T2_R"):
                    if _sc in _si_ranked.columns:
                        _si_styled = _si_styled.apply(_hl_rank1_si, subset=[_sc])
                st.dataframe(_si_styled, use_container_width=True)

    else:
        # ── 1D R sweep (single-leg) ───────────────────────────────────────────
        with st.expander("🔍 Optimal R Sweep", expanded=False):
            _max_r = st.number_input(
                "Max R", min_value=0.5, max_value=10.0,
                value=float(st.session_state.get("ba_sweep_max_r", 3.0)),
                step=0.25, format="%.2f", key="ba_sweep_max_r",
            )
            _n_r = max(1, round(_max_r / 0.25)) - 1  # steps from 0.50
            st.caption(f"R: 0.50–{_max_r:.2f} in 0.25 steps — {_n_r} values")

            if st.button("Run R Sweep", key="ba_run_sweep"):
                with st.spinner(f"Running sweep ({_n_r} values)…"):
                    sweep_df = _run_r_sweep(
                        signals, ticks_by_date, entry_slip, exit_slip,
                        stop_offset, tick_value, contracts, commission,
                        bars_by_date=bars_by_date,
                        multileg=False, t1_r=t1_r, t1_action=t1_action,
                        contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                        max_r=_max_r,
                        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
                    )
                if sweep_df.empty:
                    st.warning("No results.")
                    return
                st.session_state["ba_sweep_df"] = sweep_df

            sweep_df = st.session_state.get("ba_sweep_df")
            if sweep_df is None or sweep_df.empty:
                return

            fmt_map = {"R": "{:.2f}", "Win %": "{:.1f}", "PF": "{:.2f}", "PnL/DD": "{:.2f}"}
            fmt_map.update({"Tgt %": "{:.1f}", "EOD Win %": "{:.1f}", "EOD Win R": "{:.2f}"})
            fmt_map.update({"Net PnL": "${:.0f}", "DD $": "${:.0f}", "Exp $": "${:.0f}"})
            styled = _apply_best_green(
                sweep_df, sweep_df.style.format(fmt_map), _METRIC_COLS, _THRESHOLDS
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

            fig = go.Figure()
            fig.add_scatter(x=sweep_df["R"], y=sweep_df["Net PnL"],
                            name="Net PnL ($)", mode="lines+markers",
                            line=dict(color="#26a69a", width=2))
            fig.add_scatter(x=sweep_df["R"], y=sweep_df["PF"],
                            name="Profit Factor", mode="lines+markers",
                            yaxis="y2", line=dict(color="#ff9800", width=2))
            fig.update_layout(
                xaxis_title="Target R",
                yaxis=dict(title="Net PnL ($)"),
                yaxis2=dict(title="PF", overlaying="y", side="right"),
                height=320, template="plotly_white",
                legend=dict(x=0.01, y=0.99),
            )
            st.plotly_chart(fig, use_container_width=True)


# ── Unfilled signals table ────────────────────────────────────────────────────

_FILTER_LABELS = {
    "no_fill":        "Price never crossed signal level",
    "no_next_bar":    "No ticks after signal bar close",
    "no_tick_data":   "No tick data for this date",
    "zero_risk":      "Stop distance is zero",
    "holiday":        "NYSE holiday",
    "dow":            "Day-of-week excluded",
    "event":          "Economic event window",
    "first_bars":     "Within excluded opening bars",
    "last_bars":      "Within excluded closing window",
    "signal_type":    "Signal type excluded",
    "direction":      "Direction excluded",
    "date_range":     "Outside selected date range",
    "first_trade_day":"Non-first trade of day",
    "manual_override":"Manual fill override ✓",
    "low_er":         "Intraday ER 30m below gate (chop)",
    "low_er10":       "Intraday ER 10m below gate (chop)",
    "not_balance":    "Not a balance-state day (S25)",
    "not_inside":     "Prior day not an inside day (S25)",
    "prior_trend":    "Prior day a trend day >1.6×ADR (S25)",
}

_EXECUTION_STATUSES = {"no_fill", "no_next_bar", "no_tick_data", "zero_risk"}


def _on_first_trade_change():
    if st.session_state.get("ba_first_trade"):
        st.session_state["ba_first_2_filled"] = False

def _on_first_2_change():
    if st.session_state.get("ba_first_2_filled"):
        st.session_state["ba_first_trade"] = False


def _missed_by_ticks(sig_row, ticks_by_date: dict):
    """For a no_fill signal, how many ticks did price miss the signal level by?"""
    day_ticks = ticks_by_date.get(sig_row["Date"])
    if day_ticks is None:
        return None
    after = day_ticks[day_ticks["DateTime"] > sig_row["DateTime"]]
    if after.empty:
        return None
    sp = sig_row["SignalPrice"]
    prices = after["Price"]
    if sig_row["Direction"] == "Long":
        closest = prices.max()
        return None if closest >= sp else int(round((sp - closest) / TICK_SIZE))
    else:
        closest = prices.min()
        return None if closest <= sp else int(round((closest - sp) / TICK_SIZE))


_SETUP_COLORS = ["#ffa726", "#ab47bc", "#29b6f6", "#66bb6a", "#ec407a", "#ef5350"]


def _show_monthly_breakdown(results: pd.DataFrame, commission: float):
    filled = results[results["Filled"]].copy()
    if filled.empty:
        return

    filled = filled.sort_values(["Date", "EntryTime"]).reset_index(drop=True)
    filled["Month"] = pd.to_datetime(filled["Date"]).dt.to_period("M")
    signal_types = sorted(filled["SignalType"].unique())

    # ── Shared stats helper ───────────────────────────────────────────────────
    def _group_stats(g, setup_pcts: bool = False) -> pd.Series:
        n       = len(g)
        _tgt    = g["ExitReason"].str.contains("Target", na=False) | g["ExitReason"].isin(["T1+BE", "T1_only"])
        _stp    = g["ExitReason"].isin(["Stop", "E1E2+Stop"])
        _eod_w  = ~_tgt & ~_stp & (g["NetPnL"] > 0)
        _eod_l  = ~_tgt & ~_stp & (g["NetPnL"] < 0)
        wins    = g[_tgt | _eod_w]
        stops   = g[_stp | _eod_l]
        pos_pnl = g.loc[g["GrossPnL"] > 0, "GrossPnL"].sum()
        neg_pnl = g.loc[g["GrossPnL"] < 0, "GrossPnL"].sum()
        pf      = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else (float("inf") if pos_pnl > 0 else 0)
        row = {
            "Trades":  n,
            "Win%":    round(len(wins) / n * 100, 1) if n else 0.0,
            "PF":      round(min(pf, 99.9), 2),
            "Net PnL": round(g["NetPnL"].sum(), 0),
            "Avg R":   round(g["R_achieved"].mean(), 2),
            "MAE R":   round(g["MAE_R"].mean(), 2),
            "MFE R":   round(g["MFE_R"].mean(), 2),
            "Best":    round(wins["NetPnL"].max(), 0) if len(wins) else 0.0,
            "Worst":   round(stops["NetPnL"].min(), 0) if len(stops) else 0.0,
        }
        if setup_pcts:
            for stype in signal_types:
                row[f"{stype}%"] = round(int((g["SignalType"] == stype).sum()) / n * 100, 1) if n else 0.0
        return pd.Series(row)

    # ── Per-month ─────────────────────────────────────────────────────────────
    monthly = (
        filled.groupby("Month", sort=True)
        .apply(lambda g: _group_stats(g, setup_pcts=True))
        .reset_index()
    )
    monthly["Month"] = monthly["Month"].astype(str)

    # ── Per-setup ─────────────────────────────────────────────────────────────
    setup_df = (
        filled.groupby("SignalType", sort=True)
        .apply(lambda g: _group_stats(g, setup_pcts=False))
        .reset_index()
    )

    # ── Equity / DD / trend ───────────────────────────────────────────────────
    equity     = filled["NetPnL"].cumsum().values
    peak       = pd.Series(equity).cummax().values
    dd_vals    = equity - peak
    trade_nums = list(range(1, len(filled) + 1))
    tn_arr     = np.array(trade_nums, dtype=float)
    coeffs     = np.polyfit(tn_arr, equity, 1)
    trend_y    = np.polyval(coeffs, tn_arr)

    stype_pct_cols = [f"{s}%" for s in signal_types]

    def _fmt(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["Net PnL"] = df["Net PnL"].apply(lambda v: f"${v:+,.0f}")
        d["Best"]    = df["Best"].apply(lambda v: f"${v:+,.0f}" if v != 0 else "—")
        d["Worst"]   = df["Worst"].apply(lambda v: f"${v:+,.0f}" if v != 0 else "—")
        d["Win%"]    = df["Win%"].apply(lambda v: f"{v:.1f}%")
        d["PF"]      = df["PF"].apply(lambda v: f"{v:.2f}")
        d["Avg R"]   = df["Avg R"].apply(lambda v: f"{v:.2f}")
        d["MAE R"]   = df["MAE R"].apply(lambda v: f"{v:.2f}")
        d["MFE R"]   = df["MFE R"].apply(lambda v: f"{v:.2f}")
        return d

    base_cols = ["Trades", "Win%", "PF", "Net PnL", "Avg R", "MAE R", "MFE R", "Best", "Worst"]

    # ── Monthly breakdown expander ────────────────────────────────────────────
    with st.expander("📅 Monthly Breakdown", expanded=False):
        disp = _fmt(monthly)
        for col in stype_pct_cols:
            if col in monthly.columns:
                disp[col] = monthly[col].apply(lambda v: f"{v:.1f}%")
        st.dataframe(
            disp[["Month"] + base_cols + stype_pct_cols],
            use_container_width=True, hide_index=True,
        )

        chart_l, chart_r = st.columns([3, 2])

        with chart_l:
            fig_eq = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                row_heights=[0.65, 0.35], vertical_spacing=0.04,
                subplot_titles=("Equity Curve", "Drawdown ($)"),
            )
            fig_eq.add_trace(go.Scatter(
                x=trade_nums, y=equity.tolist(),
                mode="lines", name="Equity",
                line=dict(color="#26a69a", width=2),
                fill="tozeroy", fillcolor="rgba(38,166,154,0.12)",
                hovertemplate="Trade %{x}<br>Equity: $%{y:,.0f}<extra></extra>",
            ), row=1, col=1)
            fig_eq.add_trace(go.Scatter(
                x=[trade_nums[0], trade_nums[-1]],
                y=[float(trend_y[0]), float(trend_y[-1])],
                mode="lines", name="Trend",
                line=dict(color="rgba(255,167,38,0.85)", width=1.5, dash="dash"),
                hoverinfo="skip",
            ), row=1, col=1)
            fig_eq.add_trace(go.Bar(
                x=trade_nums, y=dd_vals.tolist(),
                name="DD", marker_color="rgba(239,83,80,0.65)",
                hovertemplate="Trade %{x}<br>DD: $%{y:,.0f}<extra></extra>",
            ), row=2, col=1)
            fig_eq.update_layout(
                height=400, showlegend=False, template="plotly_white",
                margin=dict(l=55, r=15, t=40, b=40),
                hovermode="x unified",
            )
            fig_eq.update_yaxes(tickprefix="$", row=1, col=1)
            fig_eq.update_yaxes(tickprefix="$", row=2, col=1)
            fig_eq.update_xaxes(title_text="Trade #", row=2, col=1)
            st.plotly_chart(fig_eq, use_container_width=True)

        with chart_r:
            bar_colors = ["#26a69a" if v >= 0 else "#ef5350" for v in monthly["Net PnL"]]
            fig_cc = go.Figure()
            fig_cc.add_trace(go.Bar(
                x=monthly["Month"], y=monthly["Net PnL"],
                name="Net PnL", marker_color=bar_colors, yaxis="y",
                hovertemplate="%{x}<br>Net PnL: $%{y:+,.0f}<extra></extra>",
            ))
            for i, stype in enumerate(signal_types):
                col = f"{stype}%"
                if col not in monthly.columns:
                    continue
                fig_cc.add_trace(go.Scatter(
                    x=monthly["Month"], y=monthly[col],
                    name=stype, mode="lines+markers",
                    line=dict(color=_SETUP_COLORS[i % len(_SETUP_COLORS)], width=2),
                    marker=dict(size=7), yaxis="y2",
                    hovertemplate=f"%{{x}}<br>{stype}%%: %{{y:.1f}}%%<extra></extra>",
                ))
            setup_label = "/".join(signal_types) + "% vs Net PnL" if signal_types else "Setup% vs Net PnL"
            fig_cc.update_layout(
                height=400, template="plotly_white",
                title=dict(text=setup_label, font=dict(size=13)),
                margin=dict(l=55, r=65, t=45, b=60),
                legend=dict(orientation="h", y=1.10, x=0),
                yaxis=dict(title="Net PnL ($)", tickprefix="$"),
                yaxis2=dict(title="Setup %", overlaying="y", side="right",
                            range=[0, 100], ticksuffix="%"),
                xaxis=dict(tickangle=-45),
                hovermode="x unified",
            )
            st.plotly_chart(fig_cc, use_container_width=True)

    # ── Setup analysis expander ───────────────────────────────────────────────
    with st.expander("📊 Setup Analysis", expanded=False):
        sdisp = _fmt(setup_df)
        st.dataframe(
            sdisp[["SignalType"] + base_cols],
            use_container_width=True, hide_index=True,
        )


# Session phases (CT), keyed by trade EntryTime. Right-open intervals.
# Open 08:30–11:30 · Mid 11:30–13:00 · Late 13:00–14:45 · Close 14:45–15:15
_SESSION_PHASES = [
    ("Open",  8 * 60 + 30, 11 * 60 + 30),
    ("Mid",  11 * 60 + 30, 13 * 60 +  0),
    ("Late", 13 * 60 +  0, 14 * 60 + 45),
    ("Close", 14 * 60 + 45, 15 * 60 + 15),
]
_PHASE_ORDER = [p[0] for p in _SESSION_PHASES]
_DOW_ORDER   = ["Mon", "Tue", "Wed", "Thu", "Fri"]


def _phase_of(ts) -> str:
    """Map an entry timestamp to its session phase by minute-of-day (CT)."""
    m = ts.hour * 60 + ts.minute
    for name, lo, hi in _SESSION_PHASES:
        if lo <= m < hi:
            return name
    return "Other"  # outside RTH phases (rare; e.g. last-bar edge)


def _expectancy_stats(g: pd.DataFrame) -> pd.Series:
    """Read-only per-group expectancy. Same definitions as the Monthly
    breakdown's _group_stats (Trades/Win%/PF/Net PnL/Avg R/MAE R/MFE R)."""
    n      = len(g)
    _tgt   = g["ExitReason"].str.contains("Target", na=False) | g["ExitReason"].isin(["T1+BE", "T1_only"])
    _stp   = g["ExitReason"].isin(["Stop", "E1E2+Stop"])
    _eod_w = ~_tgt & ~_stp & (g["NetPnL"] > 0)
    wins   = g[_tgt | _eod_w]
    pos    = g.loc[g["GrossPnL"] > 0, "GrossPnL"].sum()
    neg    = g.loc[g["GrossPnL"] < 0, "GrossPnL"].sum()
    pf     = abs(pos / neg) if neg < 0 else (float("inf") if pos > 0 else 0.0)
    return pd.Series({
        "Trades":  n,
        "Win%":    round(len(wins) / n * 100, 1) if n else 0.0,
        "PF":      round(min(pf, 99.9), 2),
        "Net PnL": round(g["NetPnL"].sum(), 0),
        "Avg R":   round(g["R_achieved"].mean(), 2),
        "MAE R":   round(g["MAE_R"].mean(), 2),
        "MFE R":   round(g["MFE_R"].mean(), 2),
    })


def _show_tod_dow_breakdown(results: pd.DataFrame):
    """Read-only Time-of-Day / Day-of-Week expectancy matrix.

    DESCRIPTION ONLY — no optimization, no sweep, no WFA coupling. Surfaces
    structural patterns for hypothesis-forming; locking a filter is a separate,
    deliberate step that lives in the shared engine layer (NEVER co-swept in WFA).
    """
    filled = results[results["Filled"]].copy()
    if filled.empty:
        return

    filled["Phase"] = filled["EntryTime"].apply(_phase_of)
    filled["DoW"]   = filled["EntryTime"].dt.dayofweek.map(
        {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"})
    filled = filled[filled["DoW"].notna()]

    base_cols = ["Trades", "Win%", "PF", "Net PnL", "Avg R", "MAE R", "MFE R"]

    def _fmt(df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        d["Net PnL"] = df["Net PnL"].apply(lambda v: f"${v:+,.0f}")
        d["Win%"]    = df["Win%"].apply(lambda v: f"{v:.1f}%")
        d["PF"]      = df["PF"].apply(lambda v: f"{v:.2f}")
        for c in ("Avg R", "MAE R", "MFE R"):
            d[c] = df[c].apply(lambda v: f"{v:.2f}")
        return d

    def _ordered(df: pd.DataFrame, key: str, order: list) -> pd.DataFrame:
        df = df[df[key].isin(order)].copy()
        df[key] = pd.Categorical(df[key], categories=order, ordered=True)
        return df.sort_values(key)

    with st.expander("🕐 Time-of-Day / Day-of-Week Breakdown", expanded=False):
        st.caption(
            "Descriptive only — read this to form a *structural* hypothesis, not to "
            "pick the best cell. Thin cells (low Trades) are noise. Any filter you "
            "lock from this lives in the shared engine layer; it is never co-swept in WFA."
        )

        # ── Day-of-Week table ──────────────────────────────────────────────────
        st.markdown("**By Day of Week**")
        dow_df = _ordered(
            filled.groupby("DoW", sort=False).apply(_expectancy_stats).reset_index(),
            "DoW", _DOW_ORDER)
        st.dataframe(_fmt(dow_df)[["DoW"] + base_cols],
                     use_container_width=True, hide_index=True)

        # ── Session-phase table ────────────────────────────────────────────────
        st.markdown("**By Session Phase**  (Open 08:30–11:30 · Mid 11:30–13:00 · "
                    "Late 13:00–14:45 · Close 14:45–15:15 CT)")
        ph_df = _ordered(
            filled.groupby("Phase", sort=False).apply(_expectancy_stats).reset_index(),
            "Phase", _PHASE_ORDER)
        st.dataframe(_fmt(ph_df)[["Phase"] + base_cols],
                     use_container_width=True, hide_index=True)

        # ── Weekday × phase heatmap ─────────────────────────────────────────────
        st.markdown("**Weekday × Phase Heatmap**")
        metric = st.radio(
            "Colour by", ["Avg R", "Net PnL", "Win%", "PF"],
            horizontal=True, key="ba_tod_metric",
        )
        cell = (filled.groupby(["Phase", "DoW"], sort=False)
                      .apply(_expectancy_stats).reset_index())
        cell = cell[cell["DoW"].isin(_DOW_ORDER) & cell["Phase"].isin(_PHASE_ORDER)]

        z   = cell.pivot(index="Phase", columns="DoW", values=metric).reindex(
                  index=_PHASE_ORDER, columns=_DOW_ORDER)
        cnt = cell.pivot(index="Phase", columns="DoW", values="Trades").reindex(
                  index=_PHASE_ORDER, columns=_DOW_ORDER)

        # annotate each cell with "value (n=trades)"; blank where no trades
        txt = []
        for ph in _PHASE_ORDER:
            row = []
            for d in _DOW_ORDER:
                v, n = z.loc[ph, d], cnt.loc[ph, d]
                if pd.isna(n) or n == 0:
                    row.append("")
                elif metric == "Net PnL":
                    row.append(f"${v:+,.0f}<br>n={int(n)}")
                elif metric == "Win%":
                    row.append(f"{v:.0f}%<br>n={int(n)}")
                else:
                    row.append(f"{v:.2f}<br>n={int(n)}")
            txt.append(row)

        # diverging scale centred at 0 for Avg R / Net PnL; sequential otherwise
        diverging = metric in ("Avg R", "Net PnL")
        fig = go.Figure(go.Heatmap(
            z=z.values, x=_DOW_ORDER, y=_PHASE_ORDER,
            text=txt, texttemplate="%{text}", textfont={"size": 11},
            colorscale="RdYlGn" if diverging else "Blues",
            zmid=0 if diverging else None,
            hovertemplate="%{y} · %{x}<br>" + metric + ": %{z}<extra></extra>",
            colorbar=dict(title=metric),
        ))
        fig.update_layout(
            height=320, template="plotly_white",
            margin=dict(l=60, r=15, t=10, b=40),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Cell annotation: metric value with trade count (n). "
                   "Treat any n below ~15–20 as too sparse to interpret.")


# ── Regime bucket constants ──────────────────────────────────────────────────
_PCT_EDGES   = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
_PCT_LABELS  = ["0–20", "20–40", "40–60", "60–80", "80–100"]
_VWAP_EDGES  = ([-4.5 + i * 0.5 for i in range(19)]   # −4.5 to +4.5 in 0.5 steps
                + [np.inf])
_VWAP_EDGES[0] = -np.inf
_VWAP_LABELS = ([f"{_VWAP_EDGES[i]:+.1f}..{_VWAP_EDGES[i+1]:+.1f}σ"
                 for i in range(len(_VWAP_EDGES) - 1)])
_VWAP_LABELS[0]  = "≤ −4.0σ"
_VWAP_LABELS[-1] = "≥ +4.0σ"
_TERCILE     = [0.0, 1 / 3, 2 / 3, 1.0]
_RANGE_ATR_EDGES  = [0.0, 0.6, 0.8, 1.0, 1.2, np.inf]
_RANGE_ATR_LABELS = ["<0.6", "0.6–0.8", "0.8–1.0", "1.0–1.2", ">1.2"]
# Intraday Kaufman ER is already 0–1; 0.02-step bins for threshold-finding.
_ERI_EDGES   = [round(i * 0.02, 2) for i in range(51)]          # 0.00 .. 1.00
_ERI_LABELS  = [f"{round(i*0.02,2):.2f}–{round((i+1)*0.02,2):.2f}"
                for i in range(50)]


@st.cache_data(show_spinner="Tagging trades with regime indicators…")
def _tag_trades_cached(fp: int, _filled: pd.DataFrame, _bars: pd.DataFrame) -> pd.DataFrame:
    """Join look-ahead-safe indicator tags onto each filled trade by EntryTime.
    `fp` is the cache key; `_filled`/`_bars` are not hashed (underscore prefix)."""
    base = pd.DataFrame({
        "_idx": range(len(_filled)),
        "DateTime": pd.to_datetime(_filled["EntryTime"]).values,
        "Price": _filled["EntryPrice"].astype(float).values,
    })
    if "Direction" in _filled.columns:
        base["Direction"] = _filled["Direction"].values
    tags = ind.tag_signals(base, _bars, periods=("session", "weekly", "monthly"))
    tags = tags.set_index("_idx").sort_index()
    cols = [c for c in tags.columns if c not in ("_idx", "DateTime", "Price", "Direction")]
    return tags[cols].reset_index(drop=True)


@st.cache_data(show_spinner="Tagging regime state…")
def _regime_tags_cached(fp: int, _signals: pd.DataFrame, _bars: pd.DataFrame) -> pd.DataFrame:
    """Look-ahead-safe regime-gate columns for the whole signal population.

    Returns ER_intra_6 (intraday 30m Kaufman ER — the deployed chop gate) plus the
    S25 balance columns balance_state / prior_inside_day / prior_adr_ext, aligned
    to `_signals.index`. `fp` is the cache key; frames are unhashed (underscore
    prefix). periods=("session",) skips the weekly/monthly value-area work these
    gates don't need."""
    base = _signals.copy()
    base["_bid"] = np.arange(len(base))
    tagged = ind.tag_signals(base, _bars, periods=("session",))
    cols = ["ER_intra_2", "ER_intra_6", "balance_state", "prior_inside_day", "prior_adr_ext"]
    out = tagged.set_index("_bid").sort_index()[cols]
    out.index = _signals.index
    return out


def _compute_ric(bucket_df: pd.DataFrame, total_exp: float) -> float:
    """Regime Information Coefficient (normalized): sample-weighted MAD of bucket
    expectancy from the baseline, divided by |baseline|.
    0% = uniform performance across buckets, 100%+ = strongly polarized."""
    n = bucket_df["Trades"].values.astype(float)
    total = n.sum()
    if total == 0 or total_exp == 0:
        return 0.0
    exp = bucket_df["Net PnL"].values / np.where(n > 0, n, 1.0)
    raw = float(np.sum((n / total) * np.abs(exp - total_exp)))
    return raw / abs(total_exp) * 100.0


def _auto_hypothesis(category: str, indicator: str, bucket: str,
                     positive: bool) -> str:
    """Generate a default structural hypothesis for a notable regime slice."""
    edge = "higher" if positive else "lower"
    anti = "lower" if positive else "higher"

    _hyp = {
        # Volatility
        ("Volatility", "ATR percentile"): {
            True: {
                "80–100": "High-volatility regimes produce wider swings — breakout/expansion signals get larger follow-through and R-multiples are bigger in point terms.",
                "0–20": "Very low volatility compresses ranges — breakouts from compression can be clean and directional, but targets may need to be tighter.",
            },
            False: {
                "0–20": "Low-volatility regimes lack the range for targets to be hit intraday — trades stall and exit EOD or at small losses.",
                "80–100": "Extreme volatility overruns stops before expansion can develop cleanly — whipsaws dominate.",
            },
        },
        ("Volatility", "Prior-day Range/ATR"): {
            True: {
                "<0.6": "Compressed prior day (range < 0.6× ATR) precedes expansion — signals at the start of a new move tend to be higher quality.",
                ">1.2": "Extended prior day may trigger profit-taking / reversion the next session — breakout entries may face exhaustion.",
            },
            False: {
                ">1.2": "After an extended day, continuation pressure can overrun stops before reversion occurs.",
                "<0.6": "After compression, breakout direction is uncertain — signals may be false starts.",
            },
        },
        # Trend
        ("Trend", "ADX percentile"): {
            True: {
                "0–20": "Low ADX = no dominant trend = range-bound market — breakout signals may lack follow-through without directional momentum.",
                "80–100": "Strong trend provides directional conviction — breakout entries align with the dominant momentum.",
            },
            False: {
                "80–100": "Strong trends in the wrong direction overpower breakout signals — counter-trend entries get steamrolled.",
                "0–20": "Choppy with no direction — signals lack the initial expansion quality needed for clean follow-through.",
            },
        },
        ("Trend", "Kaufman ER percentile"): {
            True: {
                "0–20": "Low efficiency = choppy path — breakout signals may whipsaw as price oscillates without direction.",
                "80–100": "High efficiency = clean directional move — breakout entries ride sustained momentum with minimal noise.",
            },
            False: {
                "80–100": "Highly efficient trends in the wrong direction trap counter-trend breakout entries.",
                "0–20": "Ultra-choppy conditions produce noisy signals with poor follow-through in either direction.",
            },
        },
    }

    # Market Structure
    _mss_hyp = {
        ("Market Structure", "Structural Trend"): {
            True: {
                "Bullish": "Breakout signals firing with bullish market structure — HH/HL sequence supports expansion entries.",
                "Bearish": "Breakout signals fire during bearish structure — short-side entries align with LL/LH sequence.",
            },
            False: {
                "Bullish": "Long breakouts underperform in bullish structure — may be buying late into established moves.",
                "Bearish": "Short breakouts underperform in bearish structure — may be selling into established declines.",
            },
        },
        ("Market Structure", "Deep Pullback (liquidity sweep)"): {
            True: {
                "Yes": "Liquidity sweep (wick pierce without close) — smart money absorbed the stop hunt, expansion follows.",
                "No": "No liquidity sweep — clean structural trend, breakout signals fire in orderly market.",
            },
            False: {
                "Yes": "Liquidity sweep destabilizes — the stop hunt creates noise that degrades signal quality.",
                "No": "No sweep but still underperforms — breakout signal fires in ambiguous structure.",
            },
        },
    }

    # check MSS keys
    key = (category, indicator)
    if key in _mss_hyp and positive in _mss_hyp[key]:
        for pattern, text in _mss_hyp[key][positive].items():
            if pattern in bucket:
                return text

    # Directional indicators
    _dir_hyp = {
        "Above/Below 20 EMA (directional)": {
            "Aligned": "Trading in the direction of the short-term trend (20 EMA) — breakout momentum and EMA bias are aligned.",
            "Misaligned": "Counter-trend to the 20 EMA — the breakout signal fights the prevailing short-term momentum.",
        },
        "Above/Below VWAP (directional)": {
            "Aligned": "Trading in the direction of institutional flow (VWAP) — institutional volume supports the trade direction.",
            "Misaligned": "Counter to VWAP positioning — fighting the volume-weighted fair value of the session.",
        },
        "Above/Below Open of Day (directional)": {
            "Aligned": "Price above open for longs / below for shorts — session bias confirms trade direction.",
            "Misaligned": "Trading against the session's opening bias — early session direction is a weak but real signal.",
        },
        "vs Prior-Day High/Low": {
            "Above HOY": "Price above yesterday's high — breakout/extension territory. Expansion signals align with the directional move.",
            "Below LOY": "Price below yesterday's low — breakdown zone. Short-side breakout signals align with selling pressure.",
            "Between": "Price within yesterday's range — no extreme displacement. Breakout signals may lack follow-through without a level break.",
        },
        "vs 60-min Opening Range": {
            "Above OR": "Above the 60-min opening range — directional bias established. Breakout longs ride session momentum.",
            "Below OR": "Below the 60-min opening range — bearish bias. Breakout shorts align with session direction.",
            "Inside OR": "Inside the opening range — no directional bias yet. Signals are in a balance zone.",
        },
    }

    # VWAP sigma
    if "VWAP" in indicator and "σ" in indicator:
        if "−" in bucket or bucket.startswith("≤"):
            if positive:
                return "Price well below session VWAP — breakout signals fire at displacement from institutional fair value, expansion room is larger."
            return "Deep below VWAP may indicate persistent selling pressure — long-side breakouts fight the institutional flow."
        if "+" in bucket or bucket.startswith("≥"):
            if positive:
                return "Price well above session VWAP — breakout signals fire at displacement from fair value, momentum has room to expand."
            return "Extended above VWAP may indicate strong buying exhaustion — short-side breakouts fight the flow."
        if positive:
            return "Near-VWAP signals trade in the acceptance zone — breakouts from fair value may lack the displacement for follow-through."
        return "Near VWAP = low displacement — targets may not be reached before EOD."

    # Value areas
    if "value-area" in indicator:
        va_hyp = {
            "above": ("Price above prior value area — displaced from acceptance, breakout/expansion signals have room to run.",
                      "Price above value area in a strong trend — continuation may exhaust before targets are reached."),
            "below": ("Price below prior value area — displaced below acceptance, breakout shorts align with rejection.",
                      "Below value = breakdown territory — long-side breakouts fight selling pressure."),
            "inside": ("Inside prior value area — high-volume acceptance zone, breakout signals may lack displacement for follow-through.",
                       "Inside value = no edge — trades perform at baseline because there's no displacement to exploit."),
        }
        if bucket in va_hyp:
            return va_hyp[bucket][0 if positive else 1]

    # Directional indicators
    for ind_name, buckets in _dir_hyp.items():
        if ind_name in indicator and bucket in buckets:
            return buckets[bucket]

    # Percentile-based lookups
    key = (category, indicator)
    if key in _hyp and positive in _hyp[key]:
        for pattern, text in _hyp[key][positive].items():
            if pattern in bucket:
                return text

    # Generic fallback
    if positive:
        return f"This regime slice shows {edge} expectancy — investigate the structural market reason before using as a filter."
    return f"This regime slice shows {anti} expectancy — understand why before excluding these trades."


_RTH_RANGEBREAKS = [
    dict(bounds=["sat", "mon"]),
    dict(bounds=[15.25, 8.5], pattern="hour"),
]


def _time_concentration(entry_times) -> tuple:
    """How concentrated in calendar time is a slice's trades?

    Returns (emoji, top6mo_share, comment). A slice whose edge is bunched into
    one 6-month window is a single-regime artifact, not a persistent filter.
    🟢 well-spread (<40% in any 6mo) · 🟡 moderate (40–65%) · 🔴 concentrated (>65%).
    """
    ts = pd.to_datetime(pd.Series(list(entry_times))).dropna().sort_values()
    if len(ts) < 3:
        return "•", 1.0, "too few trades to assess time spread"
    months = ts.dt.to_period("M")
    full = pd.period_range(months.min(), months.max(), freq="M")
    counts = months.value_counts().reindex(full, fill_value=0).sort_index()
    if len(counts) <= 6:
        share = 1.0
        win = f"{full.min().strftime('%b %Y')}–{full.max().strftime('%b %Y')}"
    else:
        roll = counts.rolling(6).sum()
        share = float(roll.max()) / len(ts)
        end_i = int(np.nanargmax(roll.values))
        start_i = max(0, end_i - 5)
        win = f"{full[start_i].strftime('%b %Y')}–{full[end_i].strftime('%b %Y')}"
    emoji = "🟢" if share < 0.40 else ("🟡" if share < 0.65 else "🔴")
    return emoji, share, f"{share:.0%} of these trades fall in {win}"


def _plot_slice_inspector(d: pd.DataFrame, bars: pd.DataFrame, bucket_defs: list):
    """Plot the trades that fall in a chosen indicator/bucket on the continuous
    price series. Read-only — purely for eyeballing where a slice's trades live."""
    # indicators whose per-trade bucket column is present on the trade frame
    opts = {}
    for cat, name, col, order, ric, bdf in bucket_defs:
        if col in d.columns:
            opts[f"{name}"] = (col, [str(o) for o in order])
    if not opts:
        st.info("No tagged bucket columns available to inspect.")
        return

    c1, c2, c3 = st.columns([2, 1.6, 1.4])
    ind_name = c1.selectbox("Indicator", list(opts), key="ba_si_ind")
    col, order = opts[ind_name]

    present = [str(b) for b in d[col].dropna().astype(str).unique()]
    ordered = [b for b in order if b in present] + [b for b in present if b not in order]
    if not ordered:
        st.info("No trades tagged for this indicator.")
        return
    # Composite key: switching Indicator gives a fresh Bucket widget, so a stale
    # bucket label from a different indicator can't crash the selectbox.
    bucket = c2.selectbox("Bucket", ordered, key=f"ba_si_bucket::{ind_name}")

    sub = d[d[col].astype(str) == str(bucket)].copy()
    sub = sub[sub["EntryTime"].notna() & sub["EntryPrice"].notna()]
    if sub.empty:
        st.info("No trades in this slice.")
        return

    # focus control: whole range, or zoom to a single trade (±5 trading days).
    # Per-trade list only for reasonably small slices; big buckets stay "All".
    _FOCUS_CAP = 300
    if len(sub) <= _FOCUS_CAP:
        focus_opts = ["All trades"] + [
            f"{i+1}. {pd.to_datetime(t).strftime('%Y-%m-%d %H:%M')} "
            f"{dir_} ({pnl:+,.0f})"
            for i, (t, dir_, pnl) in enumerate(zip(
                sub["EntryTime"], sub.get("Direction", pd.Series("", index=sub.index)),
                sub["NetPnL"]))
        ]
    else:
        focus_opts = ["All trades"]
    # Key depends on indicator+bucket so changing the slice resets Focus to "All".
    focus = c3.selectbox("Focus", focus_opts, key=f"ba_si_focus::{ind_name}::{bucket}")
    if len(sub) > _FOCUS_CAP:
        c3.caption(f"{len(sub)} trades — too many to list; zoom manually.")

    n_win = int((sub["NetPnL"] > 0).sum())
    n_los = int((sub["NetPnL"] <= 0).sum())
    exp = float(sub["NetPnL"].mean())
    st.caption(f"**{ind_name} → {bucket}** · {len(sub)} trades "
               f"({n_win}W / {n_los}L) · Exp ${exp:+,.0f}/trade · "
               f"Net ${sub['NetPnL'].sum():+,.0f}")

    # price line over the full series (downsample so the line stays light)
    b = bars.sort_values("DateTime")
    step = max(1, len(b) // 12000)
    line = b.iloc[::step]

    is_long = sub.get("Direction", pd.Series("", index=sub.index)) \
                 .astype(str).str.upper().str.startswith("L")
    win = sub["NetPnL"] > 0

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=line["DateTime"], y=line["Close"], mode="lines",
        line=dict(width=0.8, color="#5a6472"), name="ES (continuous)",
        hoverinfo="skip"))

    for lbl, m_dir, sym in [("Long", is_long, "triangle-up"),
                            ("Short", ~is_long, "triangle-down")]:
        for wlbl, m_win, color in [("win", win, "#26a69a"),
                                   ("loss", ~win, "#ef5350")]:
            mk = sub[m_dir & m_win]
            if mk.empty:
                continue
            fig.add_trace(go.Scatter(
                x=mk["EntryTime"], y=mk["EntryPrice"], mode="markers",
                marker=dict(symbol=sym, size=10, color=color,
                            line=dict(width=0.5, color="#0e1117")),
                name=f"{lbl} {wlbl}",
                customdata=np.c_[mk["NetPnL"].values],
                hovertemplate=("%{x|%Y-%m-%d %H:%M}<br>" + lbl +
                               " @ %{y:.2f}<br>PnL $%{customdata[0]:+,.0f}"
                               "<extra></extra>")))

    layout = dict(
        height=520, margin=dict(l=50, r=20, t=20, b=30),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font=dict(color="#e0e0e0"),
        dragmode="pan", xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, yanchor="bottom",
                    bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(rangebreaks=_RTH_RANGEBREAKS, showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="#2a2a2a")

    if focus != "All trades":
        idx = focus_opts.index(focus) - 1
        ft = pd.to_datetime(sub["EntryTime"].iloc[idx])
        x0, x1 = ft - pd.Timedelta(days=5), ft + pd.Timedelta(days=5)
        win_bars = b[(b["DateTime"] >= x0) & (b["DateTime"] <= x1)]
        layout["xaxis"] = dict(range=[x0, x1])
        if not win_bars.empty:
            pad = (win_bars["High"].max() - win_bars["Low"].min()) * 0.1 or 5
            layout["yaxis"] = dict(range=[win_bars["Low"].min() - pad,
                                          win_bars["High"].max() + pad])

    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True,
                    config={"scrollZoom": True, "displayModeBar": True})
    st.caption("Continuous back-adjusted price. Drag to pan · scroll to zoom · "
               "use **Focus** to jump to one trade (±5 days). For full indicator "
               "overlays use the 📈 Continuous Chart tab.")


# Latent factor each indicator proxies → use the best 1 per factor, not all of
# them (correlated filters double-count the same edge and shrink the sample).
_FACTOR_MAP = {
    "VWAP deviation (0.5σ)":               "Displacement from value",
    "Above/Below VWAP (directional)":      "Displacement from value",
    "Session value-area location":         "Displacement from value",
    "Weekly value-area location":          "Displacement from value",
    "Monthly value-area location":         "Displacement from value",
    "vs Prior-Day High/Low":               "Displacement from value",
    "vs 60-min Opening Range":             "Displacement from value",
    "Prior-day Range/ATR":                 "Volatility regime",
    "ATR percentile":                      "Volatility regime",
    "ADX percentile":                      "Trend strength",
    "Kaufman ER percentile":               "Trend strength",
    "Intraday ER 30m":                     "Intraday efficiency",
    "Intraday ER 60m":                     "Intraday efficiency",
    "Intraday ER 120m":                    "Intraday efficiency",
    "Above/Below 20 EMA (directional)":    "Directional alignment",
    "Above/Below Open of Day (directional)": "Directional alignment",
    "Structural Trend":                    "Market structure",
    "Deep Pullback (liquidity sweep)":     "Market structure",
}
_FACTOR_ORDER = ["Displacement from value", "Volatility regime", "Trend strength",
                 "Intraday efficiency", "Directional alignment", "Market structure"]
_RIC_FLOOR = 35.0   # below this, an indicator differentiates too little to filter on


def _show_factor_groups(d: pd.DataFrame, bucket_defs: list):
    """Group indicators by the latent factor they proxy, recommend the best one
    per factor (avoid redundant filters), and show an empirical Spearman
    correlation matrix so the conceptual grouping can be confirmed on the data."""
    st.markdown("---")
    st.markdown("### Factor Groups & Redundancy — pick ~1 per group")
    st.caption("Indicators that measure the *same underlying thing* are redundant — "
               "stacking them double-counts one edge and shrinks your sample. "
               "Use the highest-RIC indicator in each factor (✅), confirm with the "
               "correlation matrix below.")

    ric_by_name = {name: ric for _, name, _, _, ric, _ in bucket_defs}

    rows, shortlist = [], []
    for factor in _FACTOR_ORDER:
        members = [(n, ric_by_name[n]) for n in ric_by_name
                   if _FACTOR_MAP.get(n) == factor]
        if not members:
            continue
        members.sort(key=lambda x: x[1], reverse=True)
        best_name, best_ric = members[0]
        for j, (n, ric) in enumerate(members):
            if j == 0 and best_ric >= _RIC_FLOOR:
                pick = "✅ use this"
                shortlist.append((n, ric))
            elif j == 0:
                pick = f"⚠️ best in group but RIC < {_RIC_FLOOR:.0f}% — weak"
            else:
                pick = "redundant proxy"
            rows.append({"Factor": factor, "Indicator": n,
                         "RIC %": f"{ric:.0f}%", "Use?": pick})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if shortlist:
        chips = " · ".join(f"**{n}** ({r:.0f}%)" for n, r in shortlist)
        st.success(f"Suggested orthogonal shortlist: {chips}")
    else:
        st.warning(f"No factor has an indicator above the {_RIC_FLOOR:.0f}% RIC floor "
                   "on this trade set — nothing here is filter-worthy yet.")

    # ── empirical Spearman correlation of the underlying numeric values ──────
    num = {}
    if "VWAP_dev" in d.columns:      num["VWAP σ"]     = d["VWAP_dev"]
    if "prior_RangeATR" in d.columns: num["Range/ATR"] = d["prior_RangeATR"]
    if "prior_ATR_pct" in d.columns:  num["ATR %ile"]  = d["prior_ATR_pct"]
    if "prior_ADX_pct" in d.columns:  num["ADX %ile"]  = d["prior_ADX_pct"]
    if "prior_ER_pct" in d.columns:   num["Kaufman ER"] = d["prior_ER_pct"]
    if "ER_intra_12" in d.columns:    num["Intra ER 60m"] = d["ER_intra_12"]
    if {"EntryPrice", "EMA_20"} <= set(d.columns):
        num["Px−EMA20"] = d["EntryPrice"].astype(float) - d["EMA_20"].astype(float)
    if {"EntryPrice", "OOD"} <= set(d.columns):
        num["Px−OOD"] = d["EntryPrice"].astype(float) - d["OOD"].astype(float)
    if {"EntryPrice", "VWAP"} <= set(d.columns):
        num["Px−VWAP"] = d["EntryPrice"].astype(float) - d["VWAP"].astype(float)
    if "structural_trend" in d.columns:
        num["Struct Trend"] = pd.to_numeric(d["structural_trend"], errors="coerce")
    if "is_deep_pullback" in d.columns:
        num["Deep PB"] = d["is_deep_pullback"].astype(float)

    nf = pd.DataFrame(num)
    if nf.shape[1] >= 2:
        corr = nf.corr(method="spearman")
        labels = list(corr.columns)
        txt = [[f"{corr.iloc[i, j]:+.2f}" for j in range(len(labels))]
               for i in range(len(labels))]
        fig = go.Figure(go.Heatmap(
            z=corr.values, x=labels, y=labels, text=txt, texttemplate="%{text}",
            textfont={"size": 10}, colorscale="RdBu", zmid=0, zmin=-1, zmax=1,
            colorbar=dict(title="ρ")))
        fig.update_layout(height=max(300, 36 * len(labels) + 120),
                          template="plotly_white",
                          margin=dict(l=90, r=15, t=10, b=90))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Spearman ρ on the underlying values. **|ρ| > 0.6 ≈ redundant** — "
                   "two such indicators carry the same information; keep only one.")


def _show_regime_expectancy(results: pd.DataFrame):
    """Read-only regime / indicator expectancy tables for the CURRENT trade set.

    DESCRIPTION ONLY — measures where expectancy already exists by regime.
    No optimization, no filtering. Trade counts are shown everywhere.
    """
    bars = st.session_state.get("data_sc_5m")
    if bars is None or getattr(bars, "empty", True):
        bars = st.session_state.get("mas_continuous")
        if bars is not None:
            bars = bars.drop(columns=["Contract"], errors="ignore")

    filled = results[results["Filled"]].reset_index(drop=True)
    if filled.empty:
        return

    with st.expander("🌡️ Regime / Indicator Expectancy", expanded=False):
        if bars is None or bars.empty:
            st.info("Build the continuous series in the **📂 Massive** tab to tag trades "
                    "with regime indicators.")
            return
        st.caption("Descriptive only — where does the current trade set already have "
                   "expectancy, by regime? **Watch n (Trades): thin buckets are noise.** "
                   "In-sample exploration; lock nothing from here.")

        fp = hash((len(filled),
                   int(pd.to_datetime(filled["EntryTime"]).astype("int64").sum()),
                   round(float(filled["EntryPrice"].sum()), 2),
                   len(bars), str(bars["DateTime"].iloc[-1])))
        d = pd.concat([filled, _tag_trades_cached(fp, filled, bars)], axis=1)

        has_dir = "Direction" in d.columns

        # ── total baseline expectancy ────────────────────────────────────────
        total_exp = float(d["NetPnL"].sum() / len(d)) if len(d) > 0 else 0.0

        # ── helpers ──────────────────────────────────────────────────────────
        def _bucket(df, col, order):
            g = (df[df[col].notna()].groupby(col, sort=False, observed=True)
                 .apply(_expectancy_stats).reset_index())
            g[col] = pd.Categorical(g[col], categories=order, ordered=True)
            g = g.sort_values(col)
            g["Exp $"] = (g["Net PnL"] / g["Trades"]).round(0)
            return g

        def _fmt(df, key):
            o = df[[key, "Trades", "Win%", "PF", "Net PnL", "Exp $"]].copy()
            o["Win%"]    = o["Win%"].map(lambda v: f"{v:.1f}%")
            o["PF"]      = o["PF"].map(lambda v: f"{v:.2f}")
            o["Net PnL"] = o["Net PnL"].map(lambda v: f"${v:+,.0f}")
            o["Exp $"]   = o["Exp $"].map(lambda v: f"${v:+,.0f}")
            return o

        def _dir_bucket(df, level_col, label):
            """Directional bucket: Aligned/Misaligned based on Direction vs price
            relative to a level (above=long aligned, below=short aligned).
            Persists the per-trade label on `df[label]` so the Slice Inspector
            can re-select the same trades."""
            mask = df[level_col].notna() & df["EntryPrice"].notna()
            if not mask.any():
                return pd.DataFrame()
            px = df["EntryPrice"].astype(float)
            lv = df[level_col].astype(float)
            above = px > lv
            is_long = df["Direction"].str.upper().str.startswith("L")
            aligned = (above & is_long) | (~above & ~is_long)
            lab = pd.Series(np.where(aligned, "Aligned", "Misaligned"),
                            index=df.index).where(mask)
            df[label] = pd.Categorical(lab, categories=["Aligned", "Misaligned"])
            return _bucket(df, label, ["Aligned", "Misaligned"])

        # ── build all bucket tables + RIC scores ─────────────────────────────
        bucket_defs = []   # (category, name, bucket_col, order, ric, df)

        # --- Category: Volatility ---
        d["ATR%"] = pd.cut(d["prior_ATR_pct"], _PCT_EDGES, labels=_PCT_LABELS,
                           include_lowest=True)
        b = _bucket(d, "ATR%", _PCT_LABELS)
        ric = _compute_ric(b, total_exp)
        bucket_defs.append(("Volatility", "ATR percentile", "ATR%", _PCT_LABELS, ric, b))

        d["RangeATR"] = pd.cut(d["prior_RangeATR"], _RANGE_ATR_EDGES,
                               labels=_RANGE_ATR_LABELS, include_lowest=True)
        b = _bucket(d, "RangeATR", _RANGE_ATR_LABELS)
        ric = _compute_ric(b, total_exp)
        bucket_defs.append(("Volatility", "Prior-day Range/ATR", "RangeATR",
                            _RANGE_ATR_LABELS, ric, b))

        # --- Category: Trend ---
        d["ADX%"] = pd.cut(d["prior_ADX_pct"], _PCT_EDGES, labels=_PCT_LABELS,
                           include_lowest=True)
        b = _bucket(d, "ADX%", _PCT_LABELS)
        ric = _compute_ric(b, total_exp)
        bucket_defs.append(("Trend", "ADX percentile", "ADX%", _PCT_LABELS, ric, b))

        d["ER%"] = pd.cut(d["prior_ER_pct"], _PCT_EDGES, labels=_PCT_LABELS,
                          include_lowest=True)
        b = _bucket(d, "ER%", _PCT_LABELS)
        ric = _compute_ric(b, total_exp)
        bucket_defs.append(("Trend", "Kaufman ER percentile", "ER%", _PCT_LABELS, ric, b))

        # --- Category: Intraday Efficiency (developing ER, 30/60/120m) ───────
        # Fixed 0–1 bins (ER is already normalized) — no percentile window needed.
        # The trio is a ROBUSTNESS set: a real edge should appear at a similar
        # RIC across all three lookbacks, not just one.
        for n_bars, lbl in [(6, "30m"), (12, "60m"), (24, "120m")]:
            src = f"ER_intra_{n_bars}"
            if src not in d.columns:
                continue
            bcol = f"ERi {lbl}"
            d[bcol] = pd.cut(d[src], _ERI_EDGES, labels=_ERI_LABELS,
                             include_lowest=True)
            b = _bucket(d, bcol, _ERI_LABELS)
            ric = _compute_ric(b, total_exp)
            bucket_defs.append(("Intraday Efficiency",
                                f"Intraday ER {lbl}", bcol, _ERI_LABELS, ric, b))

        # --- Category: VWAP ---
        d["VWAPσ"] = pd.cut(d["VWAP_dev"], _VWAP_EDGES, labels=_VWAP_LABELS)
        b = _bucket(d, "VWAPσ", _VWAP_LABELS)
        ric = _compute_ric(b, total_exp)
        bucket_defs.append(("VWAP", "VWAP deviation (0.5σ)", "VWAPσ", _VWAP_LABELS, ric, b))

        if has_dir and "VWAP" in d.columns:
            b = _dir_bucket(d, "VWAP", "vs VWAP")
            if not b.empty:
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("VWAP", "Above/Below VWAP (directional)",
                                    "vs VWAP", ["Aligned", "Misaligned"], ric, b))

        # --- Category: EMA ---
        if has_dir and "EMA_20" in d.columns:
            b = _dir_bucket(d, "EMA_20", "vs EMA20")
            if not b.empty:
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("EMA", "Above/Below 20 EMA (directional)",
                                    "vs EMA20", ["Aligned", "Misaligned"], ric, b))

        # --- Category: Session Levels ---
        if has_dir and "OOD" in d.columns:
            b = _dir_bucket(d, "OOD", "vs OOD")
            if not b.empty:
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Session Levels",
                                    "Above/Below Open of Day (directional)",
                                    "vs OOD", ["Aligned", "Misaligned"], ric, b))

        if has_dir and "HOY" in d.columns:
            m = d["HOY"].notna() & d["LOY"].notna() & d["EntryPrice"].notna()
            if m.any():
                px = d["EntryPrice"].astype(float)
                above_hoy = px > d["HOY"].astype(float)
                below_loy = px < d["LOY"].astype(float)
                order_hl = ["Above HOY", "Between", "Below LOY"]
                lab = pd.Series(np.select([above_hoy, below_loy],
                                          ["Above HOY", "Below LOY"],
                                          default="Between"),
                                index=d.index).where(m)
                d["vs HOY/LOY"] = pd.Categorical(lab, categories=order_hl, ordered=True)
                b = _bucket(d, "vs HOY/LOY", order_hl)
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Session Levels", "vs Prior-Day High/Low",
                                    "vs HOY/LOY", order_hl, ric, b))

        if has_dir and "OR60_High" in d.columns:
            m = d["OR60_High"].notna() & d["OR60_Low"].notna() & d["EntryPrice"].notna()
            if m.any():
                px = d["EntryPrice"].astype(float)
                above_or = px > d["OR60_High"].astype(float)
                below_or = px < d["OR60_Low"].astype(float)
                order_or = ["Above OR", "Inside OR", "Below OR"]
                lab = pd.Series(np.select([above_or, below_or],
                                          ["Above OR", "Below OR"],
                                          default="Inside OR"),
                                index=d.index).where(m)
                d["vs 60m OR"] = pd.Categorical(lab, categories=order_or, ordered=True)
                b = _bucket(d, "vs 60m OR", order_or)
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Session Levels", "vs 60-min Opening Range",
                                    "vs 60m OR", order_or, ric, b))

        # --- Category: Value Areas ---
        for tf, loc_col in [("Session", "vaD_loc"), ("Weekly", "vaW_loc"),
                            ("Monthly", "vaM_loc")]:
            d[f"VA {tf}"] = d.get(loc_col)
            if d[f"VA {tf}"] is not None:
                order_va = ["below", "inside", "above"]
                b = _bucket(d, f"VA {tf}", order_va)
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Value Areas", f"{tf} value-area location",
                                    f"VA {tf}", order_va, ric, b))

        # --- Category: Market Structure ---
        if "structural_trend" in d.columns:
            mask_st = d["structural_trend"].notna()
            if mask_st.any():
                sub_st = d[mask_st].copy()
                sub_st["Struct Trend"] = sub_st["structural_trend"].map(
                    {1: "Bullish", -1: "Bearish"}).fillna("Unknown")
                order_st = ["Bullish", "Bearish"]
                b = _bucket(sub_st, "Struct Trend", order_st)
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Market Structure", "Structural Trend",
                                    "Struct Trend", order_st, ric, b))
                d["Struct Trend"] = sub_st["Struct Trend"]

        if "is_deep_pullback" in d.columns:
            mask_dp = d["is_deep_pullback"].notna()
            if mask_dp.any():
                sub_dp = d[mask_dp].copy()
                sub_dp["Deep PB"] = sub_dp["is_deep_pullback"].map(
                    {True: "Yes", False: "No", 1: "Yes", 0: "No"}).fillna("No")
                order_dp = ["Yes", "No"]
                b = _bucket(sub_dp, "Deep PB", order_dp)
                ric = _compute_ric(b, total_exp)
                bucket_defs.append(("Market Structure",
                                    "Deep Pullback (liquidity sweep)",
                                    "Deep PB", order_dp, ric, b))
                d["Deep PB"] = sub_dp["Deep PB"]

        # ── RIC ranking table (the high-value summary) ───────────────────────
        n_tag = int(d["prior_ATR_pct"].notna().sum())
        st.caption(f"{n_tag} of {len(filled)} filled trades tagged "
                   f"(baseline Exp $: ${total_exp:+,.0f}/trade).")

        st.markdown("### RIC Ranking — Regime Information Coefficient")
        st.caption("Higher RIC = this indicator differentiates performance more. "
                   "Low RIC = uniform expectancy across buckets (no regime utility).")
        ric_rows = [{"Category": cat, "Indicator": name, "RIC %": f"{ric:.0f}%",
                     "Buckets": len(bdf), "RIC_raw": ric}
                    for cat, name, _, _, ric, bdf in bucket_defs]
        ric_df = pd.DataFrame(ric_rows).sort_values("RIC_raw", ascending=False)
        st.dataframe(ric_df[["Category", "Indicator", "RIC %", "Buckets"]],
                     use_container_width=True, hide_index=True)

        # ── factor groups & redundancy ───────────────────────────────────────
        _show_factor_groups(d, bucket_defs)

        # ── notable slices (potential filter candidates) ────────────────────
        st.markdown("---")
        st.markdown("### Notable Slices — Potential Filter Candidates")
        st.caption("Buckets where per-trade expectancy deviates >50% from baseline "
                   "AND has n ≥ 20 trades. Edit the hypothesis — a slice without a "
                   "structural *why* is curve-fit, not edge.")
        notable_items = []
        for cat, name, col, order, ric, bdf in bucket_defs:
            for _, row in bdf.iterrows():
                n_trades = int(row["Trades"])
                if n_trades < 20:
                    continue
                bucket_exp = float(row["Net PnL"]) / n_trades
                if total_exp == 0:
                    continue
                pct_dev = (bucket_exp - total_exp) / abs(total_exp) * 100
                if abs(pct_dev) < 50:
                    continue
                direction = "+" if pct_dev > 0 else ""
                slice_ts = d.loc[d[col].astype(str) == str(row[col]), "EntryTime"] \
                    if col in d.columns else []
                tc_emoji, tc_share, tc_comment = _time_concentration(slice_ts)
                notable_items.append({
                    "Category": cat,
                    "Indicator": name,
                    "Bucket": str(row[col]),
                    "Trades": n_trades,
                    "Exp $": f"${bucket_exp:+,.0f}",
                    "vs Baseline": f"{direction}{pct_dev:.0f}%",
                    "Time Spread": f"{tc_emoji} {tc_share:.0%}",
                    "PF": f"{row['PF']:.2f}",
                    "Win%": f"{row['Win%']:.1f}%",
                    "_dev": abs(pct_dev),
                    "_positive": pct_dev > 0,
                    "_col": col,
                    "_tc": tc_comment,
                    "_tc_emoji": tc_emoji,
                })
        if notable_items:
            notable_items.sort(key=lambda x: x["_dev"], reverse=True)
            notable_df = pd.DataFrame(notable_items)
            st.dataframe(
                notable_df.drop(columns=["_dev", "_positive", "_col", "_tc", "_tc_emoji"]),
                use_container_width=True, hide_index=True,
                column_config={"Time Spread": st.column_config.TextColumn(
                    "Time Spread",
                    help="Share of this slice's trades in its busiest 6-month window. "
                         "🟢 <40% well-spread · 🟡 40–65% · 🔴 >65% concentrated "
                         "(edge may be a single-regime artifact, not a durable filter).")})

            st.markdown("#### Hypotheses")
            st.caption("Auto-generated structural reasons + time-spread note. "
                       "Edit to refine or reject.")
            hyp_store = st.session_state.setdefault("ba_regime_hypotheses", {})
            for i, item in enumerate(notable_items):
                key = f"{item['Indicator']}|{item['Bucket']}"
                default = _auto_hypothesis(
                    item["Category"], item["Indicator"], item["Bucket"],
                    item["_positive"])
                current = hyp_store.get(key, default)
                edge = "outperforms" if item["_positive"] else "underperforms"
                label = (f"**{item['Indicator']}** → {item['Bucket']} "
                         f"({edge}, {item['vs Baseline']}, n={item['Trades']})")
                st.markdown(label)
                st.caption(f"{item['_tc_emoji']} Time concentration: {item['_tc']}.")
                new_val = st.text_area(
                    "Hypothesis", value=current, key=f"ba_hyp_{i}",
                    height=68, label_visibility="collapsed")
                hyp_store[key] = new_val
        else:
            st.info("No buckets meet the threshold (>50% deviation, n ≥ 20).")

        # ── slice inspector — plot the trades of one slice on price ──────────
        st.markdown("---")
        st.markdown("### 🔍 Slice Inspector — see the trades on a chart")
        st.caption("Pick any indicator/bucket and plot exactly those entries on the "
                   "continuous price series. Green = winner, red = loser; ▲ long, ▼ short.")
        _plot_slice_inspector(d, bars, bucket_defs)

        # ── all bucket tables (scrollable, one per row) ──────────────────────
        st.markdown("---")
        st.markdown("### All Bucket Tables")
        current_cat = None
        for cat, name, col, order, ric, bdf in bucket_defs:
            if cat != current_cat:
                st.markdown(f"#### {cat}")
                current_cat = cat
            st.markdown(f"**{name}** · RIC: {ric:.0f}%")
            st.dataframe(_fmt(bdf, col), use_container_width=True, hide_index=True,
                         height=min(35 * (len(bdf) + 1) + 10, 600))

        # ── custom heatmap builder ───────────────────────────────────────────
        st.markdown("---")
        st.markdown("### Custom Heatmap Builder")
        st.caption("Pick any two bucket dimensions as axes. Cell metric is selectable.")

        # tercile versions for matrix axes
        d["ATR3"] = pd.cut(d["prior_ATR_pct"], _TERCILE,
                           labels=["Low ATR", "Mid ATR", "High ATR"], include_lowest=True)
        d["ADX3"] = pd.cut(d["prior_ADX_pct"], _TERCILE,
                           labels=["Low ADX", "Mid ADX", "High ADX"], include_lowest=True)
        d["ER3"]  = pd.cut(d["prior_ER_pct"], _TERCILE,
                           labels=["Low ER", "Mid ER", "High ER"], include_lowest=True)

        heatmap_axes = {}
        for cat, name, col, order, _, bdf in bucket_defs:
            if len(order) >= 2:
                heatmap_axes[f"{name}"] = (col, order)
        heatmap_axes["ATR tercile"]  = ("ATR3",  ["Low ATR", "Mid ATR", "High ATR"])
        heatmap_axes["ADX tercile"]  = ("ADX3",  ["Low ADX", "Mid ADX", "High ADX"])
        heatmap_axes["ER tercile"]   = ("ER3",   ["Low ER",  "Mid ER",  "High ER"])
        if "Struct Trend" in d.columns and d["Struct Trend"].notna().any():
            heatmap_axes["Structural Trend"] = ("Struct Trend", ["Bullish", "Bearish"])
        if "Deep PB" in d.columns and d["Deep PB"].notna().any():
            heatmap_axes["Deep Pullback"] = ("Deep PB", ["Yes", "No"])

        axis_names = list(heatmap_axes.keys())
        hc1, hc2, hc3 = st.columns(3)
        y_name = hc1.selectbox("Y axis", axis_names, index=0, key="ba_hm_y")
        x_name = hc2.selectbox("X axis", axis_names,
                               index=min(1, len(axis_names) - 1), key="ba_hm_x")
        metric = hc3.selectbox("Metric", ["Exp $", "PF", "Win%"],
                               key="ba_hm_metric")

        y_col, y_order = heatmap_axes[y_name]
        x_col, x_order = heatmap_axes[x_name]

        valid = d[d[y_col].notna() & d[x_col].notna()]
        if valid.empty:
            st.warning("No trades with both dimensions tagged.")
        else:
            cell = (valid.groupby([y_col, x_col], sort=False, observed=True)
                    .apply(_expectancy_stats).reset_index())
            cell["Exp $"] = cell["Net PnL"] / cell["Trades"]

            z   = cell.pivot(index=y_col, columns=x_col, values=metric
                             ).reindex(index=y_order, columns=x_order)
            nt  = cell.pivot(index=y_col, columns=x_col, values="Trades"
                             ).reindex(index=y_order, columns=x_order)
            pf  = cell.pivot(index=y_col, columns=x_col, values="PF"
                             ).reindex(index=y_order, columns=x_order)

            txt = []
            for r in y_order:
                row = []
                for cc in x_order:
                    try:
                        v, n, p = z.loc[r, cc], nt.loc[r, cc], pf.loc[r, cc]
                    except KeyError:
                        row.append("")
                        continue
                    if pd.isna(n) or n == 0:
                        row.append("")
                    elif metric == "Exp $":
                        row.append(f"${v:+,.0f}<br>PF {p:.2f}<br>n={int(n)}")
                    elif metric == "Win%":
                        row.append(f"{v:.0f}%<br>n={int(n)}")
                    else:
                        row.append(f"{v:.2f}<br>n={int(n)}")
                txt.append(row)

            diverging = metric in ("Exp $",)
            fig = go.Figure(go.Heatmap(
                z=z.values, x=x_order, y=y_order, text=txt,
                texttemplate="%{text}", textfont={"size": 11},
                colorscale="RdYlGn" if diverging else "Blues",
                zmid=0 if diverging else None,
                hovertemplate="%{y} · %{x}<br>" + metric + ": %{z}<extra></extra>",
                colorbar=dict(title=metric)))
            fig.update_layout(
                height=max(250, 50 * len(y_order)),
                template="plotly_white",
                margin=dict(l=100, r=15, t=10, b=50),
                xaxis_title=x_name, yaxis_title=y_name)
            st.plotly_chart(fig, use_container_width=True)

        st.caption("Spec discipline: this finds *where* edge exists — it is not a filter "
                   "and not optimization. A bucket is only interesting if it has a real "
                   "sample (n) and a structural reason, and survives OOS/WFA validation.")


def _show_unfilled_table(results: pd.DataFrame, ticks_by_date: dict):
    st.markdown("---")

    # ── Signals that passed filters but didn't execute ────────────────────────
    exec_failed = results[results["FilterStatus"].isin(_EXECUTION_STATUSES)].copy()

    with st.expander(f"Execution failures — {len(exec_failed)} signals", expanded=False):
        if exec_failed.empty:
            st.success("All filter-passing signals were filled.")
        else:
            exec_failed["Reason"] = exec_failed["FilterStatus"].map(_FILTER_LABELS)
            exec_failed["Missed by (ticks)"] = exec_failed.apply(
                lambda r: _missed_by_ticks(r, ticks_by_date)
                          if r["FilterStatus"] == "no_fill" else None,
                axis=1,
            )
            disp = pd.DataFrame({
                "Date":      exec_failed["Date"].astype(str),
                "Bar":       exec_failed["BarNum"].astype(int),
                "Dir":       exec_failed["Direction"],
                "Signal Px": exec_failed["SignalPrice"].apply(lambda v: f"{v:.2f}"),
                "Stop Px":   exec_failed["StopPrice"].apply(lambda v: f"{v:.2f}"),
                "Reason":    exec_failed["Reason"],
                "Missed by": exec_failed["Missed by (ticks)"].apply(
                    lambda v: f"{v} tks" if pd.notna(v) else "—"
                ),
            })
            st.dataframe(disp, use_container_width=True, hide_index=True)

        # ── Manual fill override form ─────────────────────────────────────────
        st.markdown("**Manual Fill Override**")
        overrides = st.session_state.get("ba_manual_overrides", {})

        fillable = results[results["FilterStatus"].isin({"no_fill", "no_next_bar"})].copy()
        if not fillable.empty:
            ov_cols = st.columns([2, 2, 2, 1])
            sig_opts = {
                f"#{int(r['SignalNum'])} — {r['Date']} Bar {int(r['BarNum'])} {r['Direction']} @ {r['SignalPrice']:.2f}": int(r["SignalNum"])
                for _, r in fillable.iterrows()
            }
            sel_label = ov_cols[0].selectbox("Signal", list(sig_opts.keys()),
                                              key="ov_sig_sel", label_visibility="collapsed")
            sel_num   = sig_opts[sel_label]
            sel_sig   = fillable[fillable["SignalNum"] == sel_num].iloc[0]
            fill_px   = ov_cols[1].number_input("Fill Price", value=float(sel_sig["SignalPrice"]),
                                                 step=0.25, format="%.2f", key="ov_fill_px",
                                                 label_visibility="collapsed")
            fill_bar  = ov_cols[2].number_input("Entry Bar #", value=min(int(sel_sig["BarNum"]) + 1, 81),
                                                 min_value=1, max_value=81, step=1,
                                                 key="ov_fill_bar", label_visibility="collapsed")
            if ov_cols[3].button("Add", use_container_width=True):
                overrides[sel_num] = {"fill_price": fill_px, "fill_bar": int(fill_bar)}
                st.session_state["ba_manual_overrides"] = overrides
                st.rerun()
        else:
            st.caption("No fillable signals to override.")

        # Active overrides
        if overrides:
            st.caption("Active overrides:")
            for sig_num, ov in list(overrides.items()):
                r1, r2 = st.columns([6, 1])
                r1.caption(f"Signal #{sig_num} — fill @ {ov['fill_price']:.2f}  bar {ov['fill_bar']}")
                if r2.button("✕", key=f"rm_ov_{sig_num}"):
                    del overrides[sig_num]
                    st.session_state["ba_manual_overrides"] = overrides
                    st.rerun()

    # ── Signals filtered by user settings ────────────────────────────────────
    filtered = results[~results["FilterStatus"].isin(_EXECUTION_STATUSES | {"ok", "manual_override"})].copy()
    with st.expander(f"Filtered by settings — {len(filtered)} signals", expanded=False):
        if filtered.empty:
            st.info("No signals filtered by current settings.")
        else:
            filtered["Reason"] = filtered["FilterStatus"].map(_FILTER_LABELS).fillna(filtered["FilterStatus"])
            disp = pd.DataFrame({
                "Date":      filtered["Date"].astype(str),
                "Bar":       filtered["BarNum"].astype(int),
                "Dir":       filtered["Direction"],
                "Signal Px": filtered["SignalPrice"].apply(lambda v: f"{v:.2f}"),
                "Reason":    filtered["Reason"],
            })
            st.dataframe(disp, use_container_width=True, hide_index=True)


def compute_alt_path_outcomes(results: pd.DataFrame, sc_bars: pd.DataFrame, nt_bars: pd.DataFrame,
                               mode: str, params: dict) -> pd.DataFrame:
    """Flag filled trades where NT and Massive would have produced a different outcome.

    Gate: only check trades whose NT signal bar's Close differs from Massive's Close for
    that same bar (signal_price *is* that NT close, by construction — see _simulate_one_bars
    docstring). If they agree, Massive-based simulation is already faithful to what NT showed
    and there's nothing to re-derive.

    For gated trades, re-run the same entry/pullback/target logic using NT's 5M bars (the only
    NT granularity available) instead of Massive's, holding signal_price/stop_csv fixed (they
    come from the external signals file, not from either bar source). Only rows where the
    re-derived outcome actually differs (fill/no-fill, exit reason, or PnL) get the Alt* columns
    populated — most gated trades will re-derive to the same outcome and aren't flagged.
    """
    from validation import build_comparison

    out = results.copy()
    out["AltChecked"]    = False
    out["AltDiffers"]    = False
    out["AltExitReason"] = pd.NA
    out["AltGrossPnL"]   = np.nan
    out["AltEntryPrice"] = np.nan
    out["AltExitPrice"]  = np.nan

    if nt_bars is None or nt_bars.empty or "Filled" not in out.columns:
        return out

    filled = out[out["Filled"] == True]
    if filled.empty:
        return out

    comp = build_comparison(sc_bars, nt_bars)
    comp_close_delta = comp.set_index("DateTime")["ΔClose"]
    nt_by_date = {d: g for d, g in nt_bars.groupby(nt_bars["DateTime"].dt.date)}

    for idx, row in filled.iterrows():
        sig_bar_dt = row["DateTime"] - pd.Timedelta(minutes=5)
        d_close = comp_close_delta.get(sig_bar_dt)
        if d_close is None or pd.isna(d_close) or d_close == 0:
            continue  # NT close at the signal bar matches Massive — nothing to re-check

        out.at[idx, "AltChecked"] = True
        day_bars_nt = nt_by_date.get(row["Date"])
        if day_bars_nt is None or day_bars_nt.empty:
            continue

        alt = _resimulate_bars(mode, row["DateTime"], row["Direction"],
                                row["SignalPrice"], row["StopPrice"], day_bars_nt, params)

        alt_ok   = bool(alt.get("ok", False))
        alt_exit = alt.get("ExitReason") if alt_ok else "NoFill"
        alt_pnl  = alt.get("GrossPnL", 0.0) if alt_ok else 0.0

        differs = (
            alt_ok != True
            or alt_exit != row.get("ExitReason")
            or abs(alt_pnl - row.get("GrossPnL", 0.0)) > 0.01
        )
        if differs:
            out.at[idx, "AltDiffers"]    = True
            out.at[idx, "AltExitReason"] = alt_exit
            out.at[idx, "AltGrossPnL"]   = alt_pnl
            out.at[idx, "AltEntryPrice"] = alt.get("EntryPrice")
            out.at[idx, "AltExitPrice"]  = alt.get("ExitPrice")

    return out


def _show_mismatch_analysis(results: pd.DataFrame, sc_bars: pd.DataFrame, nt_bars: pd.DataFrame):
    from validation import build_comparison

    comp = build_comparison(sc_bars, nt_bars)
    # Index comparison by bar open DateTime for fast join
    comp_idx = comp.set_index("DateTime")[["OHLC_match", "ΔOpen", "ΔHigh", "ΔLow", "ΔClose"]].copy()

    filled = results[results["Filled"] == True].copy()
    if filled.empty:
        st.info("No filled trades to analyse.")
        return

    # Signal bar open = signal fire time (bar close) − 5 min
    filled["_SigBarDT"] = filled["DateTime"] - pd.Timedelta(minutes=5)
    filled = filled.join(comp_idx, on="_SigBarDT", how="left")

    # Impact: does the mismatch help or hurt the trade direction?
    # Δ = NT − SC  →  ΔHigh > 0 means NT showed higher high than SC (SC had less upside)
    # LONG favored by:  ΔHigh ≤ 0 (SC high ≥ NT high)  AND  ΔLow ≤ 0 (SC low ≥ NT low)
    # SHORT favored by: ΔHigh ≥ 0 (SC high ≤ NT high)  AND  ΔLow ≥ 0 (SC low ≤ NT low)
    def _impact(row):
        if pd.isna(row.get("ΔHigh")):
            return "No data"
        dh, dl = row["ΔHigh"], row["ΔLow"]
        net = -(dh + dl) if row["Direction"] == "Long" else (dh + dl)
        if net > 0:
            return "Favorable"
        elif net < 0:
            return "Unfavorable"
        return "Neutral"

    filled["Impact"] = filled.apply(_impact, axis=1)

    n_total    = len(filled)
    mism_mask  = filled["OHLC_match"] == False
    n_mismatch = int(mism_mask.sum())

    filled["_Won"] = filled["NetPnL"] > 0
    wr_matched  = filled.loc[~mism_mask, "_Won"].mean()
    wr_mismatch = filled.loc[mism_mask,  "_Won"].mean()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Signals on Mismatch Bars", n_mismatch)
    c2.metric("% of Filled Signals",
              f"{n_mismatch / n_total * 100:.1f}%" if n_total else "—")
    c3.metric("Win Rate — Matched",
              f"{wr_matched  * 100:.1f}%" if not pd.isna(wr_matched)  else "—")
    c4.metric("Win Rate — Mismatched",
              f"{wr_mismatch * 100:.1f}%" if not pd.isna(wr_mismatch) else "—")
    delta_wr = (wr_mismatch - wr_matched) if not (pd.isna(wr_mismatch) or pd.isna(wr_matched)) else None
    c5.metric("Win Rate Δ",
              f"{delta_wr * 100:+.1f}%" if delta_wr is not None else "—",
              delta_color="normal" if delta_wr is None else ("normal" if delta_wr >= 0 else "inverse"))

    if n_mismatch == 0:
        st.success("No filled signals fell on mismatched bars.")
        return

    mismatched = filled[mism_mask].copy()

    # Breakdown: favorable vs unfavorable
    impact_counts = mismatched["Impact"].value_counts()
    b1, b2, b3 = st.columns(3)
    b1.metric("Favorable",   int(impact_counts.get("Favorable",   0)), delta_color="off")
    b2.metric("Unfavorable", int(impact_counts.get("Unfavorable", 0)), delta_color="off")
    b3.metric("Neutral",     int(impact_counts.get("Neutral",     0)), delta_color="off")

    IMPACT_STYLE = {
        "Favorable":   "color:#26a69a; font-weight:bold",
        "Unfavorable": "color:#ef5350; font-weight:bold",
        "Neutral":     "color:#888",
        "No data":     "color:#555",
    }

    with st.expander(f"Mismatched signals — detail ({n_mismatch})", expanded=False):
        disp = pd.DataFrame()
        disp["Date"]      = mismatched["Date"].astype(str)
        disp["Bar"]       = mismatched["BarNum"].astype(int)
        disp["Dir"]       = mismatched["Direction"]
        disp["Sig Px"]    = mismatched["SignalPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        disp["Entry Px"]  = mismatched["EntryPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
        disp["Exit"]      = mismatched["ExitReason"].replace("", "—")
        disp["Net $"]     = mismatched["NetPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
        disp["R"]         = mismatched["R_achieved"].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
        disp["ΔOpen"]     = mismatched["ΔOpen"].round(0).astype("Int64")
        disp["ΔHigh"]     = mismatched["ΔHigh"].round(0).astype("Int64")
        disp["ΔLow"]      = mismatched["ΔLow"].round(0).astype("Int64")
        disp["ΔClose"]    = mismatched["ΔClose"].round(0).astype("Int64")
        disp["Impact"]    = mismatched["Impact"].values

        def _style_impact(s):
            return [IMPACT_STYLE.get(v, "") for v in s]

        def _style_delta(s):
            out = []
            for v in s:
                if pd.isna(v) or v == 0:
                    out.append("color:#888")
                elif v > 0:
                    out.append("color:#26a69a")
                else:
                    out.append("color:#ef5350")
            return out

        styled = (
            disp.style
            .apply(_style_impact, subset=["Impact"])
            .apply(_style_delta,  subset=["ΔOpen", "ΔHigh", "ΔLow", "ΔClose"])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Alt-path outcomes: trades whose NT signal bar Close differs AND the ──
    # ── re-derived NT-bar outcome actually changes the result ───────────────
    if "AltChecked" in results.columns:
        n_checked = int(results["AltChecked"].sum())
        n_differs = int(results["AltDiffers"].sum())
        st.markdown("---")
        st.caption(
            f"**Signal-bar Close gate**: {n_checked} filled trade(s) had an NT signal-bar Close "
            f"that differs from Massive's — re-derived using NT's 5M bars. "
            f"**{n_differs}** actually changed outcome."
        )
        if n_differs == 0:
            st.success("No trades changed outcome when re-derived with NT bars.")
        else:
            alt = results[results["AltDiffers"] == True].copy()
            disp2 = pd.DataFrame()
            disp2["Date"]         = alt["Date"].astype(str)
            disp2["Bar"]          = alt["BarNum"].astype(int)
            disp2["Dir"]          = alt["Direction"]
            disp2["Exit (SC)"]    = alt["ExitReason"].replace("", "—")
            disp2["Net $ (SC)"]   = alt["NetPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
            disp2["Exit (NT)"]    = alt["AltExitReason"].fillna("NoFill")
            disp2["Gross $ (NT)"] = alt["AltGrossPnL"].apply(lambda v: f"{v:+.0f}" if pd.notna(v) else "—")
            disp2["Entry (NT)"]   = alt["AltEntryPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
            disp2["Exit Px (NT)"] = alt["AltExitPrice"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
            st.dataframe(disp2, use_container_width=True, hide_index=True)


# ── Main tab ──────────────────────────────────────────────────────────────────

def show_bar_analysis(sc_file: str = "", contract: str = "ES", nt_file: str = ""):
    from data_loader import filter_excluded_dates

    signals_raw = st.session_state.get("ba_signals")
    if signals_raw is None:
        st.info("Upload a signals file in the **📊 MC Signals** panel above to begin.")
        return
    signals_raw = filter_excluded_dates(signals_raw)

    # ── Load data — Massive continuous is the analysis source; NT is matching-only ──
    from pathlib import Path
    uploaded_ohlc = st.session_state.get("uploaded_ohlc_bars")   # legacy fallback only
    mas_cont      = st.session_state.get("mas_continuous")

    if mas_cont is not None and not mas_cont.empty:
        bars        = mas_cont.drop(columns=["Contract"], errors="ignore")
        _bar_source = "massive_continuous"
    elif uploaded_ohlc is not None:
        bars        = uploaded_ohlc
        _bar_source = "ohlc_upload"
    else:
        st.error(
            "No bar data available. Build the continuous series in the 📂 Massive tab, "
            "or upload an OHLC bar export in the 🗂️ Data tab."
        )
        return
    bars = filter_excluded_dates(bars)

    # Continuous ticks: built lazily, only for the dates that actually have signals —
    # never the full multi-year history (the per-day Parquet cache from the Massive
    # tab makes each individual day-read fast regardless of total history size).
    import massive as _massive_mod
    _sig_dates = sorted(signals_raw["Date"].unique())
    _ticks_cache_key = f"ba_cont_ticks__{hash(tuple(_sig_dates))}"
    if _ticks_cache_key not in st.session_state:
        _tbd = {}
        _tick_prog = st.progress(0.0, text="Loading tick cache…")
        for _i, d in enumerate(_sig_dates):
            day_ticks = _massive_mod.load_continuous_ticks(d)
            if not day_ticks.empty:
                _tbd[d] = day_ticks
            _tick_prog.progress((_i + 1) / len(_sig_dates),
                                text=f"Loading tick cache… {_i+1}/{len(_sig_dates)}")
        _tick_prog.empty()
        st.session_state[_ticks_cache_key] = _tbd
    ticks_by_date = st.session_state[_ticks_cache_key]
    _tick_source  = "massive_continuous" if ticks_by_date else "none"

    _bar_sim_mode  = _tick_source == "none"
    _has_1s_bars   = st.session_state.get("data_sc_1s") is not None
    if _bar_sim_mode and not _has_1s_bars:
        st.warning(
            "No continuous tick cache for these signal dates — running **bar-level simulation** "
            "(5-min OHLC H/L checks). Build the tick cache in the 📂 Massive tab for tick-level fills. "
            "Conservative assumption: when both stop and target are reachable within the same bar, "
            "stop is filled first.",
            icon="⚠️",
        )
    elif _bar_sim_mode and _has_1s_bars:
        st.caption("📊 Simulation mode: 1s OHLCV bar-level (near-tick accuracy)")
    if _bar_source == "ohlc_upload":
        st.caption("📊 Bar data: uploaded OHLC bar_export (Massive continuous series not built yet)")

    # NT bars for the signal-bar Close matching gate only — never used for fills/exits.
    # NT @ES continuous (Massive tab upload) wins over the legacy single-contract upload.
    _nt_bars_for_mismatch = st.session_state.get("nt_cont_bars")
    if _nt_bars_for_mismatch is None or (hasattr(_nt_bars_for_mismatch, "empty") and _nt_bars_for_mismatch.empty):
        _nt_bars_for_mismatch = uploaded_ohlc
    if _nt_bars_for_mismatch is None and nt_file and Path(nt_file).exists():
        from data_loader import load_nt_bars
        _nt_bars_for_mismatch = load_nt_bars(nt_file)
    nt_bars = filter_excluded_dates(_nt_bars_for_mismatch) if _nt_bars_for_mismatch is not None else None

    # Bar groupby for simulation — use 1s bars when available (near-tick accuracy)
    _sim_src = st.session_state.get("data_sc_1s") if _has_1s_bars else None
    _sim_df  = _sim_src if _sim_src is not None else bars
    bars_by_date_sim = {
        d: grp.reset_index(drop=True)
        for d, grp in _sim_df.groupby(_sim_df["DateTime"].dt.date)
    }

    # Expose to Portfolio tab via session state
    st.session_state["pf_ticks_by_date"] = ticks_by_date
    st.session_state["pf_bars_by_date"]  = bars_by_date_sim

    # Signal bar close = the signal price (which IS the NT bar close by construction)
    signals_raw["SBClose"] = signals_raw["SignalPrice"]

    bars["Date"] = bars["DateTime"].dt.date
    bar_dates    = sorted(bars["Date"].unique())
    sig_min      = signals_raw["Date"].min()
    sig_max      = signals_raw["Date"].max()
    data_min     = bars["Date"].min()
    data_max     = bars["Date"].max()

    # ── Detect data change (contract switch OR new upload) — reset stale date state ──
    _active_key = f"{_bar_source}|{len(bars)}|{data_min}|{data_max}|{st.session_state.get('uploaded_ohlc_key', '')}"
    if st.session_state.get("ba_active_data_key") != _active_key:
        for k in ("ba_date_from", "ba_date_to", "ba_chart_idx", "ba_initialized"):
            st.session_state.pop(k, None)
        st.session_state["ba_active_data_key"] = _active_key

    # ── Initialize defaults ───────────────────────────────────────────────────
    if "ba_initialized" not in st.session_state:
        for k, v in _load_ba_defaults().items():
            st.session_state.setdefault(k, v)
        st.session_state["ba_initialized"] = True

    # ── Date range ────────────────────────────────────────────────────────────
    dc1, dc2 = st.columns(2)
    # Clamp defaults to [data_min, data_max] — handles signals from a different year than bars
    _from_default = min(max(sig_min, data_min), data_max)
    _to_default   = max(min(sig_max, data_max), data_min)
    date_from = dc1.date_input("From", value=_from_default,
                                min_value=data_min, max_value=data_max, key="ba_date_from")
    date_to   = dc2.date_input("To",   value=_to_default,
                                min_value=data_min, max_value=data_max, key="ba_date_to")

    # ── Filters expander ──────────────────────────────────────────────────────
    with st.expander("⚙️ Filters", expanded=False):
        st.markdown("**Session Filters**")
        sf1, sf2, sf3 = st.columns(3)
        excl_holidays = sf1.checkbox("Exclude NYSE holidays", key="ba_excl_holidays",
                                      value=st.session_state.get("ba_excl_holidays", True))
        st.markdown("")  # spacer

        st.markdown("**Day of Week**")
        dw1, dw2, dw3, dw4, dw5 = st.columns(5)
        incl_mon = dw1.checkbox("Mon", key="ba_mon", value=st.session_state.get("ba_mon", True))
        incl_tue = dw2.checkbox("Tue", key="ba_tue", value=st.session_state.get("ba_tue", True))
        incl_wed = dw3.checkbox("Wed", key="ba_wed", value=st.session_state.get("ba_wed", True))
        incl_thu = dw4.checkbox("Thu", key="ba_thu", value=st.session_state.get("ba_thu", True))
        incl_fri = dw5.checkbox("Fri", key="ba_fri", value=st.session_state.get("ba_fri", True))

        st.markdown("**Session Boundaries**")
        sb1, sb2 = st.columns(2)
        excl_first_n  = sb1.slider("Exclude first N bars",   0, 12,
                                    st.session_state.get("ba_excl_first_n", 0), 1,
                                    key="ba_excl_first_n")
        excl_last_min = sb2.slider("Exclude last N minutes", 0, 90,
                                    st.session_state.get("ba_excl_last_min", 45), 5,
                                    key="ba_excl_last_min")

        st.divider()
        st.markdown("**Economic Events**")
        if not fred_key_configured():
            st.info("FOMC built-in. Add FRED_API_KEY to .streamlit/secrets.toml for NFP/CPI.")
        ea, eb, ec = st.columns(3)
        use_fomc = ea.checkbox("FOMC", key="ba_fomc", value=st.session_state.get("ba_fomc", True))
        use_nfp  = eb.checkbox("NFP",  key="ba_nfp",  value=st.session_state.get("ba_nfp",  False),
                                disabled=not fred_key_configured())
        use_cpi  = ec.checkbox("CPI",  key="ba_cpi",  value=st.session_state.get("ba_cpi",  False),
                                disabled=not fred_key_configured())
        event_types = tuple(e for e, on in [("FOMC", use_fomc), ("NFP", use_nfp), ("CPI", use_cpi)] if on)

        ef1, ef2 = st.columns([1, 2])
        _EFM_OPTS = ["Skip full day", "Window ±N minutes"]
        _efm_raw  = st.session_state.get("ba_event_mode", _EFM_OPTS[1])
        # Normalise: stored value may have plain ± while code had mojibake, or vice versa
        _efm_default = _EFM_OPTS[1] if ("±" in _efm_raw or "±" in _efm_raw) else _EFM_OPTS[0]
        event_filter_mode = ef1.radio(
            "Filter mode", _EFM_OPTS,
            index=_EFM_OPTS.index(_efm_default),
            key="ba_event_mode",
        )
        event_window = 30
        if event_filter_mode == _EFM_OPTS[1]:
            event_window = ef2.slider("Minutes before/after", 15, 180,
                                       st.session_state.get("ba_event_window", 15), 15,
                                       key="ba_event_window")

        st.divider()
        st.markdown("**Regime Gates**")
        eg1, eg2, eg3, eg4 = st.columns([2, 2, 2, 2])
        flt_er30 = eg1.checkbox(
            "ER 30m ≥ gate", key="ba_flt_er30",
            value=st.session_state.get("ba_flt_er30", False),
            help="Chop gate on 30-minute Kaufman ER (ER_intra_6). "
                 "Below 0.30 everything loses.")
        er_min = eg2.number_input(
            "ER30 gate", 0.0, 1.0,
            float(st.session_state.get("ba_flt_er_min", 0.30)),
            step=0.02, format="%.2f", key="ba_flt_er_min",
            help="ER30 threshold (default 0.30).")
        flt_er10 = eg3.checkbox(
            "ER 10m ≥ gate", key="ba_flt_er10",
            value=st.session_state.get("ba_flt_er10", False),
            help="Chop gate on 10-minute Kaufman ER (ER_intra_2, 2-bar). "
                 "S26 research: $116 exp, PF 1.40, 15/15 OOS folds green at 0.30.")
        er10_min = eg4.number_input(
            "ER10 gate", 0.0, 1.0,
            float(st.session_state.get("ba_flt_er10_min", 0.30)),
            step=0.02, format="%.2f", key="ba_flt_er10_min",
            help="ER10 threshold (default 0.30).")

        st.markdown("**Balance State (S25, secondary boosters on top of ER)**")
        rb1, rb2, rb3 = st.columns(3)
        flt_balance = rb1.checkbox(
            "Balance state only", key="ba_flt_balance",
            value=st.session_state.get("ba_flt_balance", False),
            help="Keep only signals on a balance day: opened INSIDE the prior "
                 "RTH range AND still rotating inside it at signal time (no "
                 "discovery yet). Look-ahead-safe.")
        flt_inside = rb2.checkbox(
            "Prior inside day only", key="ba_flt_inside",
            value=st.session_state.get("ba_flt_inside", False),
            help="Keep only signals whose PRIOR day's range fell inside the "
                 "day-before's range (compression → expansion).")
        flt_skip_trend = rb3.checkbox(
            "Skip prior trend day", key="ba_flt_skip_trend",
            value=st.session_state.get("ba_flt_skip_trend", False),
            help="Drop signals whose prior day was a trend day (range > 1.6×ADR) "
                 "— the S25 clean hard-skip (breakout edge ≈ dead after a trend day).")

    # ── Signals ───────────────────────────────────────────────────────────────
    with st.expander("📶 Signals", expanded=False):
        # Signal-type filter — built dynamically from the loaded signals' own types,
        # so it adapts to MC (CC2/CC3/…), RevFT (OB/IB/Trap), or any future set.
        _all_types = (sorted(signals_raw["SignalType"].dropna().unique())
                      if not signals_raw.empty else [])
        excluded_types = set()
        if _all_types:
            _cc_cols = st.columns(min(len(_all_types), 6))
            for _i, _stype in enumerate(_all_types):
                _tk = f"ba_incl_{_stype}"
                if not _cc_cols[_i % len(_cc_cols)].checkbox(
                        str(_stype), key=_tk, value=st.session_state.get(_tk, True)):
                    excluded_types.add(_stype)
        else:
            st.caption("No signals loaded.")
        _sf_cols = st.columns([2, 2, 3])
        first_trade_only = _sf_cols[0].checkbox("First trade of day only", key="ba_first_trade",
                                                 value=st.session_state.get("ba_first_trade", False),
                                                 on_change=_on_first_trade_change)
        first_2_filled_only = _sf_cols[1].checkbox("First 2 of day", key="ba_first_2_filled",
                                                    value=st.session_state.get("ba_first_2_filled", False),
                                                    on_change=_on_first_2_change)
        _dir_opts = ["Both", "Long", "Short"]
        direction_filter = _sf_cols[2].radio(
            "Direction", _dir_opts, horizontal=True, key="ba_direction_filter",
            index=_dir_opts.index(st.session_state.get("ba_direction_filter", "Both")),
        )

    # ── Trading Parameters expander ───────────────────────────────────────────
    with st.expander("⚙️ Trading Parameters", expanded=False):
        # 3-Leg hidden until tick data is available.
        _mode_opts = ["Single Leg", "2-Leg"]
        _saved_mode = st.session_state.get("ba_trade_mode", "Single Leg")
        if _saved_mode not in _mode_opts:
            _saved_mode = "Single Leg"
        _trade_mode = st.radio(
            "Trade Mode", _mode_opts,
            index=_mode_opts.index(_saved_mode),
            horizontal=True, key="ba_trade_mode_radio",
            label_visibility="collapsed",
        )
        st.session_state["ba_trade_mode"] = _trade_mode
        _is_sl = (_trade_mode == "Single Leg")
        _is_ml = (_trade_mode == "2-Leg")
        _is_3l = False

        _col_sl, _col_ml, _col_3l = st.columns(3)
        _ml_invalid = False

        # -- Single Leg --
        with _col_sl:
            if _is_sl:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_sl",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_sl",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )
                # BE Stop and Stop Ratchet modes hidden — require tick data for
                # accurate bar-level simulation (dynamic stop movement creates
                # intrabar sequence ambiguity).
                _sl_be = False
                st.session_state["ba_sl_mode"] = "AIAO"
                st.number_input(
                    "Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_sl",
                        st.session_state.get("ba_contracts", 1))),
                    key="ba_contracts_sl",
                )
                st.number_input(
                    "Target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_target_r_sl",
                          st.session_state.get("ba_target_r", 2.0))),
                    step=0.25, format="%.2f", key="ba_target_r_sl",
                )
                st.number_input(
                    "Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_sl",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_sl",
                )
                st.number_input(
                    "Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_sl",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_sl",
                )
                st.number_input(
                    "Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_sl",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_sl",
                )
                _def_comm_sl = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_sl", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input(
                    "Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_sl", _def_comm_sl)),
                    step=0.5, format="%.2f", key="ba_commission_sl",
                )
                _sl_c    = int(st.session_state.get("ba_contracts_sl", 1))
                _sl_comm = float(st.session_state.get("ba_commission_sl", _def_comm_sl))
                st.caption(f"{_sl_c}c × ${_sl_comm:.2f} = ${_sl_c * _sl_comm:.2f}/trade")
                st.caption("**Stop Ratchet (trail to BE)**")
                _sl_ratchet = st.checkbox("Enable", value=bool(st.session_state.get("ba_ratchet_sl", False)), key="ba_ratchet_sl")
                if _sl_ratchet:
                    st.number_input("Trigger (R from entry)", 0.25, 10.0,
                        float(st.session_state.get("ba_ratchet_r_sl", 1.0)),
                        step=0.25, format="%.2f", key="ba_ratchet_r_sl")
                    _sl_rdest = st.selectbox("Move stop to",
                        ["BE (entry)", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_sl")
                    if _sl_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_sl", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_sl")

        # -- 2-Leg --
        with _col_ml:
            if _is_ml:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_ml",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_ml",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )
                _r_opts  = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
                _r_lbls  = [f"{v:.2f}R" for v in _r_opts]

                st.caption("**Leg 1 (E1)**")
                contracts_t1 = st.number_input(
                    "E1 Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_t1", 1)),
                    key="ba_contracts_t1",
                )
                _saved_t1_lbl = st.session_state.get("ba_t1_r_sel", "1.00R")
                _t1_idx    = _r_lbls.index(_saved_t1_lbl) if _saved_t1_lbl in _r_lbls else 2
                _t1_sel    = st.selectbox(
                    "T1 (E1 target, R from entry)", _r_lbls, index=_t1_idx,
                    key="ba_t1_r_sel",
                    help="If price hits T1 before PB fills → trade over, E1 profits.",
                )
                t1_r      = _r_opts[_r_lbls.index(_t1_sel)]
                t1_action = "exit"  # scale-in model always exits E1 at T1

                st.caption("**Leg 2 (E2 scale-in)**")
                contracts_t2 = st.number_input(
                    "E2 Contracts", 1, 100,
                    int(st.session_state.get("ba_contracts_t2", 1)),
                    key="ba_contracts_t2",
                )
                _pb_vals = [0.0, -0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50, -2.0]
                _pb_lbls = ["None (immediate)", "-0.25R", "-0.33R", "-0.50R",
                            "-0.66R", "-0.75R", "-1.0R", "-1.25R", "-1.50R", "-2.0R"]
                _saved_pb = float(st.session_state.get("ba_ml_pb_r", -0.50))
                _pb_idx   = _pb_vals.index(_saved_pb) if _saved_pb in _pb_vals else 3
                _pb_sel   = st.selectbox(
                    "E2 Pullback (R from entry)", _pb_lbls, index=_pb_idx,
                    key="ba_ml_pb_sel",
                    help="How far price must retrace from E1 entry before E2 fills. "
                         "-0.5R = half-R below E1 entry (for longs).",
                )
                ml_pb_r_v = _pb_vals[_pb_lbls.index(_pb_sel)]

                _saved_t2_lbl = st.session_state.get("ba_t2_r_sel", "2.00R")
                _t2_idx    = _r_lbls.index(_saved_t2_lbl) if _saved_t2_lbl in _r_lbls else 4
                _t2_sel    = st.selectbox(
                    "T2 (R after E2)", _r_lbls, index=_t2_idx,
                    key="ba_t2_r_sel",
                    help="Target for the position after E2 fills. Reference + risk unit "
                         "depend on the scale-in style below.",
                )
                target_r_ml = _r_opts[_r_lbls.index(_t2_sel)]

                _si_style_lbls = ["E1 break-even (E2-based)", "Blended position"]
                _si_style_map  = {"E1 break-even (E2-based)": "e2", "Blended position": "blended"}
                _si_style_idx  = _si_style_lbls.index(
                    st.session_state.get("ba_scale_in_style", _si_style_lbls[0]))
                _si_style_sel  = st.selectbox(
                    "Scale-in style", _si_style_lbls, index=_si_style_idx,
                    key="ba_scale_in_style",
                    help="E1 break-even: T2 = E2 entry + R × E2's own risk. At a 50% PB both "
                         "legs exit at E1 entry (E1 scratches at BE, E2 banks R). "
                         "Blended: T2 = blended entry + R × blended risk (manage as one averaged position).",
                )
                scale_in_style_v = _si_style_map[_si_style_sel]

                _pbr_lbls = ["Round to nearest", "Floor/Ceil (conservative)"]
                st.selectbox(
                    "Price rounding (PB & targets)", _pbr_lbls,
                    index=_pbr_lbls.index(st.session_state.get("ba_pb_round", _pbr_lbls[0]))
                          if st.session_state.get("ba_pb_round", _pbr_lbls[0]) in _pbr_lbls else 0,
                    key="ba_pb_round",
                    help="Snaps all computed price levels (PB triggers AND profit targets) to a tradeable "
                         "tick. Round-to-nearest (default) = realistic closest-tick fill. Floor/Ceil snaps "
                         "AWAY from entry (conservative — targets land further/harder to fill, PB deeper).",
                )

                st.caption("**Execution**")
                st.number_input(
                    "Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_ml",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_ml",
                )
                st.number_input(
                    "Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_ml",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_ml",
                )
                st.number_input(
                    "Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_ml",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_ml",
                )
                _def_comm_ml = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_ml", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input(
                    "Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_ml", _def_comm_ml)),
                    step=0.5, format="%.2f", key="ba_commission_ml",
                )

                _ml_c    = contracts_t1 + contracts_t2
                _ml_comm = float(st.session_state.get("ba_commission_ml", _def_comm_ml))
                st.caption(f"{_ml_c}c × ${_ml_comm:.2f} = ${_ml_c * _ml_comm:.2f}/trade")
                st.caption("**Stop Ratchet**")
                _ml_ratchet = st.checkbox("Enable", value=bool(st.session_state.get("ba_ratchet_ml", False)), key="ba_ratchet_ml")
                if _ml_ratchet:
                    st.number_input("Trigger (R from entry)", 0.25, 10.0,
                        float(st.session_state.get("ba_ratchet_r_ml", 1.0)),
                        step=0.25, format="%.2f", key="ba_ratchet_r_ml")
                    _ml_rdest = st.selectbox("Move stop to",
                        ["BE (entry)", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_ml")
                    if _ml_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_ml", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_ml")

        # -- 3-Leg --
        with _col_3l:
            if _is_3l:
                st.selectbox(
                    "Instrument", list(INSTRUMENTS.keys()),
                    index=list(INSTRUMENTS.keys()).index(
                        st.session_state.get("ba_instrument_3l",
                        st.session_state.get("ba_instrument", "ES"))),
                    key="ba_instrument_3l",
                    format_func=lambda k: INSTRUMENTS[k]["label"],
                )

                # ── E1 ────────────────────────────────────────────────────────
                st.markdown("**E1 — Initial entry at signal**")
                e1c_3l = st.number_input("E1 Contracts", 1, 100,
                    int(st.session_state.get("ba_e1c_3l", 1)), key="ba_e1c_3l")
                t1_r_3l = st.number_input("T1 — E1 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_t1_r_3l", 1.0)),
                    step=0.25, format="%.2f", key="ba_t1_r_3l")
                _t1_lbl_3l = st.radio("At T1", ["Exit E1", "BE stop only"],
                    index=0 if st.session_state.get("ba_t1_action_3l", "exit") == "exit" else 1,
                    key="ba_t1_action_3l_radio", horizontal=True)
                t1_action_3l = "exit" if _t1_lbl_3l == "Exit E1" else "be_only"

                st.divider()

                # ── E2 ────────────────────────────────────────────────────────
                st.markdown("**E2 — Pullback entry 1**")
                e2c_3l = st.number_input("E2 Contracts (0 = disabled)", 0, 100,
                    int(st.session_state.get("ba_e2c_3l", 1)), key="ba_e2c_3l")
                _pb1c1, _pb1c2 = st.columns(2)
                _pb1c1.number_input("PB1 (R back)", 0.01, 4.0,
                    float(st.session_state.get("ba_pb1_r_3l", 0.33)),
                    step=0.01, format="%.2f", key="ba_pb1_r_3l",
                    help="How far back from E1 entry (in R) to place the PB1 limit order")
                _pb1c2.number_input("PB1 tick offset", -20, 20,
                    int(st.session_state.get("ba_pb1_ticks_3l", 0)), key="ba_pb1_ticks_3l",
                    help="+= shallower (closer to entry), –= deeper")
                t2_r_3l = st.number_input("T2 — E2 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_t2_r_3l", 2.0)),
                    step=0.25, format="%.2f", key="ba_t2_r_3l")

                st.divider()

                # ── E3 ────────────────────────────────────────────────────────
                st.markdown("**E3 — Pullback entry 2**")
                e3c_3l = st.number_input("E3 Contracts (0 = disabled)", 0, 100,
                    int(st.session_state.get("ba_e3c_3l", 1)), key="ba_e3c_3l")
                _pb2c1, _pb2c2 = st.columns(2)
                _pb2c1.number_input("PB2 (R back)", 0.01, 5.0,
                    float(st.session_state.get("ba_pb2_r_3l", 0.66)),
                    step=0.01, format="%.2f", key="ba_pb2_r_3l",
                    help="Must be deeper than PB1")
                _pb2c2.number_input("PB2 tick offset", -20, 20,
                    int(st.session_state.get("ba_pb2_ticks_3l", 0)), key="ba_pb2_ticks_3l",
                    help="+= shallower, –= deeper")
                target_r_3l = st.number_input("T3 — E3 target (R)", 0.25, 10.0,
                    float(st.session_state.get("ba_target_r_3l", 3.0)),
                    step=0.25, format="%.2f", key="ba_target_r_3l")

                # Validation
                _pb1_r_v = float(st.session_state.get("ba_pb1_r_3l", 0.33))
                _pb2_r_v = float(st.session_state.get("ba_pb2_r_3l", 0.66))
                _t2_r_v  = float(st.session_state.get("ba_t2_r_3l", 2.0))
                if _pb2_r_v <= _pb1_r_v:
                    st.warning(f"PB2 ({_pb2_r_v:.2f}R) must be > PB1 ({_pb1_r_v:.2f}R).")
                if not (t1_r_3l < _t2_r_v < target_r_3l):
                    st.warning(f"Targets must satisfy T1 ({t1_r_3l}R) < T2 ({_t2_r_v}R) < T3 ({target_r_3l}R).")

                st.divider()

                # ── Execution ─────────────────────────────────────────────────
                st.markdown("**Execution**")
                st.number_input("Entry slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_entry_slip_3l",
                          st.session_state.get("ba_entry_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_entry_slip_3l")
                st.number_input("Exit slip (ticks)", 0.0, 10.0,
                    float(st.session_state.get("ba_exit_slip_3l",
                          st.session_state.get("ba_exit_slip", 0.0))),
                    step=0.5, format="%.1f", key="ba_exit_slip_3l")
                st.number_input("Stop offset (ticks)", 0, 10,
                    int(st.session_state.get("ba_stop_offset_3l",
                        st.session_state.get("ba_stop_offset", 1))),
                    key="ba_stop_offset_3l")
                _def_comm_3l = INSTRUMENTS.get(
                    st.session_state.get("ba_instrument_3l", "ES"), {}
                ).get("default_commission", 3.0)
                st.number_input("Commission ($/contract)", min_value=0.0,
                    value=float(st.session_state.get("ba_commission_3l", _def_comm_3l)),
                    step=0.5, format="%.2f", key="ba_commission_3l")
                _3l_c_tot = e1c_3l + e2c_3l + e3c_3l
                st.caption(f"E1:{e1c_3l} · E2:{e2c_3l} · E3:{e3c_3l} "
                           f"× ${float(st.session_state.get('ba_commission_3l', _def_comm_3l)):.2f} "
                           f"= ${_3l_c_tot * float(st.session_state.get('ba_commission_3l', _def_comm_3l)):.2f} max/trade")

                st.divider()

                # ── Stop Ratchet ──────────────────────────────────────────────
                st.markdown("**Stop Ratchet**")
                _3l_ratchet = st.checkbox("Enable", value=bool(st.session_state.get("ba_ratchet_3l", False)), key="ba_ratchet_3l")
                if _3l_ratchet:
                    st.number_input("Trigger (R from blended entry)", 0.25, 10.0,
                        float(st.session_state.get("ba_ratchet_r_3l", 1.0)),
                        step=0.25, format="%.2f", key="ba_ratchet_r_3l")
                    _3l_rdest = st.selectbox("Move stop to",
                        ["BE (blended)", "E1 entry", "Lock-in R"], index=0,
                        key="ba_ratchet_dest_3l")
                    if _3l_rdest == "Lock-in R":
                        st.number_input("Lock-in (R)", 0.0, 5.0,
                            float(st.session_state.get("ba_ratchet_lock_r_3l", 0.5)),
                            step=0.25, format="%.2f", key="ba_ratchet_lock_r_3l")

        # ── Derive active parameters ──────────────────────────────────────────
        _sl_be_deriv  = _is_sl and st.session_state.get("ba_sl_mode", "AIAO") == "BE Stop"
        _3l_pb_ok  = float(st.session_state.get("ba_pb2_r_3l", 0.66)) > float(st.session_state.get("ba_pb1_r_3l", 0.33))
        _3l_tgt_ok = (float(st.session_state.get("ba_t1_r_3l", 1.0))
                      < float(st.session_state.get("ba_t2_r_3l", 2.0))
                      < float(st.session_state.get("ba_target_r_3l", 3.0)))
        _3l_valid  = _is_3l and _3l_pb_ok and _3l_tgt_ok

        # Ratchet params (resolved per active mode)
        def _resolve_ratchet(prefix):
            if not st.session_state.get(f"ba_ratchet_{prefix}", False):
                return 0.0, "BE", 0.0
            r_r   = float(st.session_state.get(f"ba_ratchet_r_{prefix}", 1.0))
            dest_raw = st.session_state.get(f"ba_ratchet_dest_{prefix}", "BE (entry)")
            if dest_raw == "Lock-in R":
                dest = "Lock-in"
                lock = float(st.session_state.get(f"ba_ratchet_lock_r_{prefix}", 0.5))
            elif dest_raw == "E1 entry":
                dest, lock = "E1", 0.0
            else:
                dest, lock = "BE", 0.0
            return r_r, dest, lock

        ml_pb_r_v = 0.0  # default; overridden in 2-leg block below
        scale_in_style_v = "e2"  # default; overridden in 2-leg block below
        pb_round_v = "nearest"  # default; overridden in 2-leg block below

        if _is_3l and _3l_valid:
            use_threeleg = True
            use_multileg = False
            instrument  = st.session_state.get("ba_instrument_3l", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            target_r    = float(st.session_state.get("ba_target_r_3l", 3.0))
            t1_r        = float(st.session_state.get("ba_t1_r_3l", 1.0))
            t2_r_val    = float(st.session_state.get("ba_t2_r_3l", 2.0))
            t1_action   = t1_action_3l  # defined in _col_3l block
            entry_slip  = float(st.session_state.get("ba_entry_slip_3l", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_3l", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_3l", 1))
            commission  = float(st.session_state.get("ba_commission_3l", 4.0))
            contracts   = e1c_3l
            contracts_t1 = e1c_3l; contracts_t2 = e2c_3l + e3c_3l
            pb1_r_val   = float(st.session_state.get("ba_pb1_r_3l", 0.33))
            pb2_r_val   = float(st.session_state.get("ba_pb2_r_3l", 0.66))
            pb1_ticks_v = int(st.session_state.get("ba_pb1_ticks_3l", 0))
            pb2_ticks_v = int(st.session_state.get("ba_pb2_ticks_3l", 0))
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("3l")
        elif _is_ml and not _ml_invalid:
            use_threeleg = False
            use_multileg = True
            instrument  = st.session_state.get("ba_instrument_ml", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            # T2: read from selectbox label → float
            _t2_r_opts  = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
            _t2_r_lbls  = [f"{v:.2f}R" for v in _t2_r_opts]
            _t2_sel_ss  = st.session_state.get("ba_t2_r_sel", "2.00R")
            target_r    = _t2_r_opts[_t2_r_lbls.index(_t2_sel_ss)] if _t2_sel_ss in _t2_r_lbls else 2.0
            entry_slip  = float(st.session_state.get("ba_entry_slip_ml", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_ml", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_ml", 1))
            commission  = float(st.session_state.get("ba_commission_ml", 4.0))
            contracts   = 1
            # PB level: read from selectbox label → float
            _pb_vals_ss = [0.0, -0.25, -0.33, -0.50, -0.66, -0.75, -1.0, -1.25, -1.50, -2.0]
            _pb_lbls_ss = ["None (immediate)", "-0.25R", "-0.33R", "-0.50R",
                           "-0.66R", "-0.75R", "-1.0R", "-1.25R", "-1.50R", "-2.0R"]
            _pb_sel_ss  = st.session_state.get("ba_ml_pb_sel", "-0.50R")
            ml_pb_r_v   = _pb_vals_ss[_pb_lbls_ss.index(_pb_sel_ss)] if _pb_sel_ss in _pb_lbls_ss else -0.50
            scale_in_style_v = ("blended"
                if str(st.session_state.get("ba_scale_in_style", "")).startswith("Blended")
                else "e2")
            pb_round_v = ("nearest"
                if str(st.session_state.get("ba_pb_round", "")).startswith("Round")
                else "floor_ceil")
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("ml")
            # t1_r, t1_action, contracts_t1, contracts_t2 defined in _col_ml block
        elif _sl_be_deriv:
            use_threeleg = False
            use_multileg = True
            instrument   = st.session_state.get("ba_instrument_sl", "ES")
            tick_value   = INSTRUMENTS[instrument]["tick_value"]
            target_r     = float(st.session_state.get("ba_target_r_sl", 2.0))
            t1_r         = float(st.session_state.get("ba_t1_r_sl", 1.0))
            t1_action    = "be_only"
            contracts_t1 = 0
            contracts_t2 = int(st.session_state.get("ba_contracts_sl", 1))
            entry_slip   = float(st.session_state.get("ba_entry_slip_sl", 0.0))
            exit_slip    = float(st.session_state.get("ba_exit_slip_sl", 0.0))
            stop_offset  = int(st.session_state.get("ba_stop_offset_sl", 1))
            commission   = float(st.session_state.get("ba_commission_sl", 4.0))
            contracts    = 1
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("sl")
        else:
            use_threeleg = False
            use_multileg = False
            instrument  = st.session_state.get("ba_instrument_sl", "ES")
            tick_value  = INSTRUMENTS[instrument]["tick_value"]
            target_r    = float(st.session_state.get("ba_target_r_sl", 2.0))
            entry_slip  = float(st.session_state.get("ba_entry_slip_sl", 0.0))
            exit_slip   = float(st.session_state.get("ba_exit_slip_sl", 0.0))
            stop_offset = int(st.session_state.get("ba_stop_offset_sl", 1))
            commission  = float(st.session_state.get("ba_commission_sl", 4.0))
            contracts   = int(st.session_state.get("ba_contracts_sl", 1))
            t1_r        = 1.0; t1_action = "exit"
            contracts_t1 = 0;  contracts_t2 = 0
            pb1_r_val = pb2_r_val = pb1_ticks_v = pb2_ticks_v = 0
            t2_r_val = 0.0
            e1c_3l = e2c_3l = e3c_3l = 1
            ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v = _resolve_ratchet("sl")

        # Ensure 3-leg locals always exist (used by sweep calls even in other modes)
        if not _is_3l:
            e1c_3l = e2c_3l = e3c_3l = 1
            pb1_r_val = 0.33; pb2_r_val = 0.66
            pb1_ticks_v = pb2_ticks_v = 0
            t1_action_3l = "exit"
            target_r_3l = 3.0; t1_r_3l = 1.0; t2_r_val = 2.0; _t2_r_v = 2.0

        st.divider()
        if st.button("💾 Save as Default", key="ba_save_defaults"):
            _save_ba_defaults({
                **{f"ba_incl_{t}": (t not in excluded_types) for t in _all_types},
                "ba_first_trade": first_trade_only,
                "ba_first_2_filled": first_2_filled_only,
                "ba_direction_filter": direction_filter,
                "ba_excl_holidays": excl_holidays,
                "ba_mon": incl_mon, "ba_tue": incl_tue, "ba_wed": incl_wed,
                "ba_thu": incl_thu, "ba_fri": incl_fri,
                "ba_excl_first_n": excl_first_n, "ba_excl_last_min": excl_last_min,
                "ba_fomc": use_fomc, "ba_nfp": use_nfp, "ba_cpi": use_cpi,
                "ba_event_mode": event_filter_mode, "ba_event_window": event_window,
                "ba_flt_er30": flt_er30, "ba_flt_er_min": float(er_min),
                "ba_flt_er10": flt_er10, "ba_flt_er10_min": float(er10_min),
                "ba_flt_balance": flt_balance, "ba_flt_inside": flt_inside,
                "ba_flt_skip_trend": flt_skip_trend,
                "ba_trade_mode": st.session_state.get("ba_trade_mode", "Single Leg"),
                # Single-leg
                "ba_instrument_sl": st.session_state.get("ba_instrument_sl", "ES"),
                "ba_sl_mode": st.session_state.get("ba_sl_mode", "AIAO"),
                "ba_contracts_sl": int(st.session_state.get("ba_contracts_sl", 1)),
                "ba_t1_r_sl": float(st.session_state.get("ba_t1_r_sl", 1.0)),
                "ba_target_r_sl": float(st.session_state.get("ba_target_r_sl", 2.0)),
                "ba_entry_slip_sl": float(st.session_state.get("ba_entry_slip_sl", 0.0)),
                "ba_exit_slip_sl": float(st.session_state.get("ba_exit_slip_sl", 0.0)),
                "ba_stop_offset_sl": int(st.session_state.get("ba_stop_offset_sl", 1)),
                "ba_commission_sl": float(st.session_state.get("ba_commission_sl", 4.0)),
                "ba_ratchet_sl": bool(st.session_state.get("ba_ratchet_sl", False)),
                "ba_ratchet_r_sl": float(st.session_state.get("ba_ratchet_r_sl", 1.0)),
                "ba_ratchet_dest_sl": st.session_state.get("ba_ratchet_dest_sl", "BE (entry)"),
                "ba_ratchet_lock_r_sl": float(st.session_state.get("ba_ratchet_lock_r_sl", 0.5)),
                # 2-leg
                "ba_instrument_ml": st.session_state.get("ba_instrument_ml", "ES"),
                "ba_contracts_t1": int(st.session_state.get("ba_contracts_t1", 1)),
                "ba_t1_r": float(st.session_state.get("ba_t1_r", 1.0)),
                "ba_t1_action": t1_action,
                "ba_contracts_t2": int(st.session_state.get("ba_contracts_t2", 1)),
                "ba_target_r_ml": float(st.session_state.get("ba_target_r_ml", 2.0)),
                "ba_entry_slip_ml": float(st.session_state.get("ba_entry_slip_ml", 0.0)),
                "ba_exit_slip_ml": float(st.session_state.get("ba_exit_slip_ml", 0.0)),
                "ba_stop_offset_ml": int(st.session_state.get("ba_stop_offset_ml", 1)),
                "ba_commission_ml": float(st.session_state.get("ba_commission_ml", 4.0)),
                "ba_ratchet_ml": bool(st.session_state.get("ba_ratchet_ml", False)),
                "ba_ratchet_r_ml": float(st.session_state.get("ba_ratchet_r_ml", 1.0)),
                "ba_ratchet_dest_ml": st.session_state.get("ba_ratchet_dest_ml", "BE (entry)"),
                "ba_ratchet_lock_r_ml": float(st.session_state.get("ba_ratchet_lock_r_ml", 0.5)),
                # 3-leg
                "ba_instrument_3l": st.session_state.get("ba_instrument_3l", "ES"),
                "ba_e1c_3l": int(st.session_state.get("ba_e1c_3l", 1)),
                "ba_e2c_3l": int(st.session_state.get("ba_e2c_3l", 1)),
                "ba_e3c_3l": int(st.session_state.get("ba_e3c_3l", 1)),
                "ba_pb1_r_3l": float(st.session_state.get("ba_pb1_r_3l", 0.5)),
                "ba_pb1_ticks_3l": int(st.session_state.get("ba_pb1_ticks_3l", 0)),
                "ba_pb2_r_3l": float(st.session_state.get("ba_pb2_r_3l", 1.0)),
                "ba_pb2_ticks_3l": int(st.session_state.get("ba_pb2_ticks_3l", 0)),
                "ba_t1_r_3l": float(st.session_state.get("ba_t1_r_3l", 1.0)),
                "ba_t1_action_3l": t1_action_3l,
                "ba_target_r_3l": float(st.session_state.get("ba_target_r_3l", 2.0)),
                "ba_entry_slip_3l": float(st.session_state.get("ba_entry_slip_3l", 0.0)),
                "ba_exit_slip_3l": float(st.session_state.get("ba_exit_slip_3l", 0.0)),
                "ba_stop_offset_3l": int(st.session_state.get("ba_stop_offset_3l", 1)),
                "ba_commission_3l": float(st.session_state.get("ba_commission_3l", 4.0)),
                "ba_ratchet_3l": bool(st.session_state.get("ba_ratchet_3l", False)),
                "ba_ratchet_r_3l": float(st.session_state.get("ba_ratchet_r_3l", 1.0)),
                "ba_ratchet_dest_3l": st.session_state.get("ba_ratchet_dest_3l", "BE (blended)"),
                "ba_ratchet_lock_r_3l": float(st.session_state.get("ba_ratchet_lock_r_3l", 0.5)),
            })
            st.success("Defaults saved.", icon="✅")

    # ── Execution model (ESA) ──────────────────────────────────────────────────
    # Single-run execution controls (delay / entry model / preset). The full
    # preset-comparison ESA expander is separate; this just drives ONE main run so
    # the engine can be tested on real data. Defaults (Custom / market / 0 ms) keep
    # the run byte-identical to the pre-ESA baseline.
    from simulation_engine import EXECUTION_PRESETS as _ESA_PRESETS
    with st.expander("⚙️ Execution model (ESA) — calc delay / wire / entry / preset", expanded=False):
        _ex = st.columns(3)
        _exec_preset = _ex[0].selectbox(
            "Execution preset", ["Custom", *_ESA_PRESETS.keys()], key="ba_exec_preset",
            help="Custom = use Entry/Exit slip from Trading Parameters + the delays below. "
                 "Named presets (Optimistic…Brutal) override slip + delays per the ESA spec.")
        exec_entry_model = _ex[1].radio(
            "Entry model", ["market", "stop"], horizontal=True, key="ba_exec_entry_model",
            help="market = fill at first tick after calc + wire delay. "
                 "stop = retrace ≥1 tick beyond SEPrice then tick-through ≥1 tick "
                 "the other side, else no fill.")
        _exec_calc_in = _ex[2].number_input(
            "Calc delay (ms)", 0, 1000, value=0, step=10, key="ba_exec_calc_ms",
            help="Indicator computation time (ER10 filter etc.) after first tick of "
                 "new bar. Used in Custom mode (named presets carry their own value).")
        if _exec_preset == "Custom":
            exec_entry_slip, exec_exit_slip = entry_slip, exit_slip
            exec_calc_ms = int(_exec_calc_in)
            exec_wire_ms = 0
        else:
            _pp = _ESA_PRESETS[_exec_preset]
            exec_entry_slip, exec_exit_slip = _pp["entry_slip"], _pp["exit_slip"]
            exec_calc_ms = int(_pp["calc_delay_ms"])
            exec_wire_ms = int(_pp.get("wire_delay_ms", 0))
            st.caption(f"**{_exec_preset}** → calc {exec_calc_ms} ms · wire {exec_wire_ms} ms · "
                       f"entry slip {exec_entry_slip} · exit slip {exec_exit_slip} ticks (overrides Trading Params slip)")
        exec_seed = 42
        exec_max_fill_min = st.number_input(
            "Max fill time (min)", 0, 120, value=0, step=5, key="ba_exec_max_fill_min",
            help="Cancel the entry if not filled within this many minutes of the signal bar close. "
                 "0 = no timeout. Data shows fills >30 min are net losers.")
        exec_max_fill_ms = int(exec_max_fill_min * 60000)

    # ── Date whitelist (optional CSV/TXT upload) ─────────────────────────
    from datetime import datetime as _dt_cls
    _ba_date_files = st.file_uploader(
        "Date whitelist (optional — upload YYYYMMDD files to restrict days)",
        type=["csv", "txt"], accept_multiple_files=True,
        key="ba_date_whitelist")
    _ba_wl_dates = None
    if _ba_date_files:
        _ba_wl_dates = set()
        for _f in _ba_date_files:
            for _line in _f.read().decode("utf-8", errors="ignore").splitlines():
                _line = _line.strip()
                if _line and _line.isdigit() and len(_line) == 8:
                    try:
                        _ba_wl_dates.add(_dt_cls.strptime(_line, "%Y%m%d").date())
                    except ValueError:
                        pass
        if _ba_wl_dates:
            st.caption(f"Date whitelist active: **{len(_ba_wl_dates)}** dates from "
                       f"{len(_ba_date_files)} file{'s' if len(_ba_date_files) > 1 else ''}")
        else:
            st.warning("No valid YYYYMMDD dates found in uploaded files.")
            _ba_wl_dates = None

    # ── Run button ────────────────────────────────────────────────────────────
    st.divider()
    _rb_col, _ = st.columns([2, 5])
    run_btn = _rb_col.button("▶ Run Simulation", key="ba_run_btn", type="primary",
                             use_container_width=True)

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered_signals = apply_signal_filters(
        signals_raw, date_from, date_to, excl_holidays,
        [incl_mon, incl_tue, incl_wed, incl_thu, incl_fri],
        excl_first_n, excl_last_min,
        event_types, event_filter_mode, event_window,
        excluded_types,
        direction_filter,
    )

    # Apply date whitelist if uploaded
    if _ba_wl_dates is not None:
        _before_wl = (filtered_signals["FilterStatus"] == "ok").sum()
        filtered_signals.loc[
            (filtered_signals["FilterStatus"] == "ok") &
            ~filtered_signals["Date"].isin(_ba_wl_dates),
            "FilterStatus"
        ] = "date_whitelist"
        _after_wl = (filtered_signals["FilterStatus"] == "ok").sum()
        st.caption(f"Date whitelist: **{_after_wl}** of {_before_wl} filtered signals on whitelisted dates")

    # Regime population gates (ER chop + S25 balance) — tag only when at least one
    # is active (the tag is cached, so it computes once per signal/bar set).
    if flt_er30 or flt_er10 or flt_balance or flt_inside or flt_skip_trend:
        _reg_fp = hash((
            len(signals_raw),
            int(signals_raw["SignalNum"].sum()) if not signals_raw.empty else 0,
            len(bars),
        ))
        _reg_tags = _regime_tags_cached(_reg_fp, signals_raw, bars)
        filtered_signals = apply_regime_population_filters(
            filtered_signals, _reg_tags, flt_er30, er_min,
            flt_balance, flt_inside, flt_skip_trend,
            want_er10=flt_er10, er10_min=er10_min)

    _sim_fp = hash((
        len(filtered_signals),
        int(filtered_signals["SignalNum"].sum()) if not filtered_signals.empty else 0,
        target_r, entry_slip, exit_slip, stop_offset,
        commission, contracts, use_multileg, use_threeleg,
        t1_r, t1_action, contracts_t1, contracts_t2, ml_pb_r_v,
        e1c_3l, e2c_3l, e3c_3l, pb1_r_val, pb2_r_val, pb1_ticks_v, pb2_ticks_v,
        t2_r_val, ratchet_r_v, ratchet_dest_v, ratchet_lock_r_v, scale_in_style_v, pb_round_v,
        str(st.session_state.get("ba_manual_overrides", {})),
        first_trade_only, first_2_filled_only,
        flt_er30, round(er_min, 4), flt_er10, round(er10_min, 4),
        flt_balance, flt_inside, flt_skip_trend,
        exec_entry_model, exec_calc_ms, exec_wire_ms, exec_max_fill_ms, str(exec_entry_slip), str(exec_exit_slip), exec_seed,
    ))
    _has_results = (st.session_state.get("ba_results_fp") == _sim_fp
                    and st.session_state.get("ba_results") is not None)

    if not run_btn and not _has_results:
        if filtered_signals.empty:
            st.warning("No signals match the current filters.")
        else:
            st.info(f"**{len(filtered_signals)} signals** ready — click **▶ Run Simulation**.")
        return

    if run_btn or not _has_results:
        with st.spinner("Running simulation…"):
            results = simulate_trades(
                filtered_signals, ticks_by_date, target_r,
                exec_entry_slip, exec_exit_slip, stop_offset,
                tick_value, contracts, commission,
                overrides=st.session_state.get("ba_manual_overrides"),
                bars_by_date=bars_by_date_sim,
                multileg=use_multileg, t1_r=t1_r,
                t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
                ratchet_r=ratchet_r_v, ratchet_dest=ratchet_dest_v, ratchet_lock_r=ratchet_lock_r_v,
                ml_pb_r=ml_pb_r_v, scale_in_style=scale_in_style_v, pb_round=pb_round_v,
                threeleg=use_threeleg,
                contracts_e1=e1c_3l, contracts_e2=e2c_3l, contracts_e3=e3c_3l,
                pb1_r=pb1_r_val, pb1_ticks=pb1_ticks_v,
                pb2_r=pb2_r_val, pb2_ticks=pb2_ticks_v,
                t2_r=t2_r_val,
                entry_model=exec_entry_model, calc_delay_ms=exec_calc_ms,
                wire_delay_ms=exec_wire_ms, max_fill_ms=exec_max_fill_ms,
                exec_seed=exec_seed,
            )

            if nt_bars is not None and not nt_bars.empty:
                _alt_mode = "3leg" if use_threeleg else ("multileg" if use_multileg else "single")
                _alt_params = dict(
                    target_r=target_r, entry_slip=entry_slip, exit_slip=exit_slip, stop_offset=stop_offset,
                    tv=tick_value * contracts,
                    ratchet_r=ratchet_r_v, ratchet_dest=ratchet_dest_v, ratchet_lock_r=ratchet_lock_r_v,
                    t1_r=t1_r, t1_action=t1_action,
                    tv1=tick_value * contracts_t1, tv2=tick_value * contracts_t2,
                    ml_pb_r=ml_pb_r_v, ml_pb_ticks=0,
                    t2_r=(t2_r_val if t2_r_val > 0 else target_r),
                    tv_e1=tick_value * e1c_3l, tv_e2=tick_value * e2c_3l, tv_e3=tick_value * e3c_3l,
                    contracts_e1=e1c_3l, contracts_e2=e2c_3l, contracts_e3=e3c_3l,
                    pb1_r=pb1_r_val, pb1_ticks=pb1_ticks_v, pb2_r=pb2_r_val, pb2_ticks=pb2_ticks_v,
                )
                results = compute_alt_path_outcomes(results, bars, nt_bars, _alt_mode, _alt_params)

            if first_trade_only and not results.empty:
                _filled_mask = results["Filled"] == True
                _filled_sorted = results[_filled_mask].sort_values(["Date", "SignalNum"])
                _keep_idx = _filled_sorted.groupby("Date").head(1).index
                _beyond_idx = results[_filled_mask & ~results.index.isin(_keep_idx)].index
                results = results.drop(_beyond_idx).reset_index(drop=True)

            if first_2_filled_only and not results.empty:
                _filled_mask = results["Filled"] == True
                _filled_sorted = results[_filled_mask].sort_values(["Date", "SignalNum"])
                _keep_idx = _filled_sorted.groupby("Date").head(2).index
                _beyond_idx = results[_filled_mask & ~results.index.isin(_keep_idx)].index
                results = results.drop(_beyond_idx).reset_index(drop=True)

            _summary_contracts = e1c_3l + e2c_3l + e3c_3l if use_threeleg else contracts
            summary = compute_summary(results, commission,
                                      contracts=_summary_contracts,
                                      is_multileg=(use_multileg or use_threeleg),
                                      t1_action=t1_action,
                                      contracts_t1=contracts_t1, contracts_t2=contracts_t2)

        # Attach ER10 (ER_intra_2) to results — use the EXACT same values
        # the regime gate uses so filter and display always agree.
        if not results.empty:
            _er_fp = hash((len(signals_raw),
                           int(signals_raw["SignalNum"].sum()) if not signals_raw.empty else 0,
                           len(bars)))
            _er_tags = _regime_tags_cached(_er_fp, signals_raw, bars)
            if "ER_intra_2" in _er_tags.columns:
                # _er_tags is indexed identically to signals_raw (set in the cached fn)
                signals_raw_copy = signals_raw.copy()
                signals_raw_copy["_ER10"] = _er_tags["ER_intra_2"].values
                _er_map = signals_raw_copy.set_index("SignalNum")["_ER10"]
                results["ER10"] = results["SignalNum"].map(_er_map)

        st.session_state["ba_results"]    = results
        st.session_state["ba_summary"]    = summary
        st.session_state["ba_results_fp"] = _sim_fp
    else:
        results = st.session_state["ba_results"]
        summary = st.session_state["ba_summary"]

    # ── Param echo — exactly what the sim consumed (stale-result guard) ───────
    _mode_str = "3-leg" if use_threeleg else ("2-leg" if use_multileg else "single-leg")
    if ratchet_r_v > 0:
        _rdest = (f"Lock-in +{ratchet_lock_r_v:.2f}R" if ratchet_dest_v == "Lock-in"
                  else ratchet_dest_v)
        _rat_str = f"ratchet {ratchet_r_v:.2f}R→{_rdest}"
    else:
        _rat_str = "ratchet off"
    if use_multileg:
        _spec = (f"T1 {t1_r:.2f}R · PB {ml_pb_r_v:.2f}R · T2 {target_r:.2f}R · "
                 f"style {scale_in_style_v} · PBround {pb_round_v}")
    elif use_threeleg:
        _spec = f"T1 {t1_r:.2f}R · PB1 {pb1_r_val:.2f}R · PB2 {pb2_r_val:.2f}R · T2 {t2_r_val:.2f}R"
    else:
        _spec = f"target {target_r:.2f}R"
    _n_filled = int((results["Filled"] == True).sum()) if not results.empty else 0
    st.caption(
        f"🧾 ran: **{_mode_str}** · {_spec} · {_rat_str} · "
        f"{_n_filled}/{len(results)} filled · slip {entry_slip:.0f}/{exit_slip:.0f} · "
        f"comm ${commission:.2f}"
    )

    # ── Assumption ledger — frictionless gross → net (stacked conservatism visible) ─
    _led = friction_ledger(results) if not results.empty else {}
    if _led:
        with st.expander("🧮 Assumption Ledger (frictionless → net)", expanded=False):
            _ldf = pd.DataFrame([
                {"Step": "Frictionless gross", "Amount $": _led["frictionless_gross"]},
                {"Step": "− Slippage",          "Amount $": -_led["slippage"]},
                {"Step": "− Commission",        "Amount $": -_led["commission"]},
                {"Step": "= Net (modeled)",     "Amount $": _led["net"]},
            ])
            _lc1, _lc2 = st.columns([2, 1])
            _lc1.dataframe(_ldf, use_container_width=True, hide_index=True)
            _lc2.metric("Friction / trade", f"${_led['per_trade_friction']:,.0f}",
                        help="Slippage+commission ÷ trades. Sanity-check vs real execution "
                             "(ES ≈ $15.50/trade). A model haircut far above reality = under-optimizing.")
            _lc2.metric("Net / trade", f"${_led['per_trade_net']:,.0f}")
            st.caption("Slippage is embedded in fills, so frictionless = GrossPnL + slippage. "
                       "Tick-snap & same-bar priority are baked into fills (bounded ~½ tick) and would "
                       "need a counterfactual re-run to isolate.")

    # ── Summary — pre-compute shared derived values ───────────────────────────
    if summary:
        _pf_str    = f"{summary['pf']:.2f}" if summary['pf'] < 99 else "∞"
        _wl_str    = f"{summary['wl_ratio']:.2f}" if summary['wl_ratio'] < 99 else "∞"
        _slip_usd  = summary.get("slippage_total", 0.0)
        if use_multileg:
            _slip_tks = int(round(_slip_usd / tick_value)) if tick_value > 0 else 0
        else:
            _slip_tks = int((entry_slip + exit_slip) * summary["n_trades"] * contracts)
        _slip_str      = f"{_slip_tks} tks  /  ${_slip_usd:.0f}"
        # Actual commission = gross − net (slippage already embedded in gross prices)
        _actual_comm   = summary["gross_total"] - summary["net_total"]
        _total_cost    = _slip_usd + _actual_comm
        _dd_abs        = abs(summary["max_dd"]) if summary["max_dd"] != 0 else None
        _pnl_dd        = summary["net_total"] / _dd_abs if _dd_abs else None
        _ci_lo         = summary.get("exp_r_ci_lo", np.nan)
        _ci_hi         = summary.get("exp_r_ci_hi", np.nan)
        _ci_known      = not (np.isnan(_ci_lo) or np.isnan(_ci_hi))
        _exp_r_help    = (f"95 % CI  [{_ci_lo:+.2f}, {_ci_hi:+.2f}]") if _ci_known else None

    # ── PDF export ───────────────────────────────────────────────────────────
    st.markdown("""
<style>
@media print {
    header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
    [data-testid="stSidebar"],[data-testid="stStatusWidget"],footer,.stButton,
    [data-testid="stFileUploadDropzone"] { display: none !important; }
    details[data-testid="stExpander"] { display: block !important; }
    details[data-testid="stExpander"] > div,
    details[data-testid="stExpander"] > section { display: block !important; }
    .block-container { max-width: 100% !important; padding: 0.5rem !important; }
    .js-plotly-plot, .plotly, .plot-container { height: 580px !important; min-height: 580px !important; }
    .js-plotly-plot .svg-container { height: 580px !important; }
    @page { size: landscape; margin: 1.2cm; }
}
</style>""", unsafe_allow_html=True)
    _pdf_col = st.columns([10, 2])[1]
    if _pdf_col.button("📄 Export PDF", key="ba_pdf_btn", use_container_width=True,
                       help="Opens browser print dialog — choose 'Save as PDF', check Downloads."):
        import streamlit.components.v1 as _cmp
        _pn = st.session_state.get("_ba_pdf_n", 0) + 1
        st.session_state["_ba_pdf_n"] = _pn
        _cmp.html(
            f"""<script>
(function(){{
    var w = window.parent;
    // Print the page exactly as it currently looks — no expander changes.
    // The Daily Chart (already expanded) gets relayout to ~full page height.
    var _plot = null;
    var _orig = 520;
    function findChart() {{
        var found = null;
        w.document.querySelectorAll('details').forEach(function(d) {{
            if (!d.open) return;
            var s = d.querySelector('summary');
            if (s && s.textContent.indexOf('Daily Chart') >= 0) {{
                found = d.querySelector('.js-plotly-plot');
            }}
        }});
        return found;
    }}
    function bp() {{ _plot = findChart(); if (_plot && w.Plotly) {{ _orig = _plot.clientHeight || 520; w.Plotly.relayout(_plot, {{height: 680}}); }} }}
    function ap() {{ if (_plot && w.Plotly) w.Plotly.relayout(_plot, {{height: _orig}}); }}
    w.matchMedia('print').addEventListener('change', function(e) {{ if (e.matches) bp(); else ap(); }});
    w.addEventListener('beforeprint', bp);
    w.addEventListener('afterprint',  ap);
    setTimeout(function(){{ w.print(); }}, 150);
}})(); // {_pn}
</script>""",
            height=0,
        )

    # ── Quick View (expanded by default) ─────────────────────────────────────
    with st.expander("📋 Quick View", expanded=False):
        if summary:
            r1 = st.columns(6)
            r1[0].metric("Net PnL",   f"${summary['net_total']:,.0f}")
            r1[1].metric("Win %",     f"{summary['win_pct']:.1f}%",
                         help=f"W{summary['n_wins']} / L{summary['n_stop']} / S{summary['n_sess']}")
            r1[2].metric("Exp R",     f"{summary['exp_r']:+.2f}", help=_exp_r_help)
            r1[3].metric("PnL/DD",    f"{_pnl_dd:.2f}" if _pnl_dd is not None else "—")
            # SQN is unreliable for multi-leg (high R variance by design) — show PF instead
            if use_multileg or use_threeleg:
                r1[4].metric("PF",    _pf_str)
            else:
                r1[4].metric("SQN",   f"{summary['sqn']:+.2f}")
            r1[5].metric("Max DD",    f"${summary['max_dd']:,.0f}")

            r2 = st.columns(6)
            r2[0].metric("Trades",    f"{summary['n_trades']}")
            r2[1].metric("Avg Win",   f"${summary['avg_win']:+.0f}")
            r2[2].metric("Avg Loss",  f"${summary['avg_loss']:+.0f}")
            r2[3].metric("Median W",  f"${summary['median_win']:+.0f}")
            r2[4].metric("Median L",  f"${summary['median_loss']:+.0f}")
            r2[5].metric("Days",      f"{summary['trading_days']}")
        else:
            st.info("No filled trades in the selected range.")

    # ── Expectancy Stability (rolling R + per-period) ─────────────────────────
    with st.expander("📈 Expectancy Stability (R)", expanded=False):
        _fr = (results[results["Filled"] == True].copy()
               if results is not None and "Filled" in results.columns else pd.DataFrame())
        if _fr.empty or "R_achieved" not in _fr.columns:
            st.info("No filled trades to analyze.")
        else:
            _fr = _fr.sort_values("DateTime").reset_index(drop=True)
            _fr["_n"] = np.arange(1, len(_fr) + 1)
            _R = _fr["R_achieved"].astype(float)
            _dt = pd.to_datetime(_fr["DateTime"])
            _overall = float(_R.mean())

            _cc = st.columns([1, 1, 2])
            _wa = _cc[0].number_input("Rolling window A", 20, 1000,
                                      int(st.session_state.get("ba_exprw_a", 100)), 10, key="ba_exprw_a")
            _wb = _cc[1].number_input("Rolling window B", 20, 1000,
                                      int(st.session_state.get("ba_exprw_b", 200)), 10, key="ba_exprw_b")
            _grain = _cc[2].radio("Period grain", ["Year", "Half-year", "Quarter"],
                                  horizontal=True, key="ba_exprw_grain")

            _rA, _rB = _R.rolling(_wa).mean(), _R.rolling(_wb).mean()
            _ymax = float(np.nanmax([_rA.max(), _rB.max(), _overall]))

            _fig = go.Figure()
            _fig.add_trace(go.Scatter(x=_fr["_n"], y=_rA, name=f"Rolling {_wa}",
                                      line=dict(color="#1f77b4", width=1.2)))
            _fig.add_trace(go.Scatter(x=_fr["_n"], y=_rB, name=f"Rolling {_wb}",
                                      line=dict(color="#d62728", width=2)))
            _fig.add_hline(y=0, line=dict(color="black", width=1))
            _fig.add_hline(y=_overall, line=dict(color="green", dash="dash", width=1),
                           annotation_text=f"overall {_overall:+.3f}R")
            for _yr in sorted(_dt.dt.year.unique()):
                _x0 = int(_fr.loc[_dt.dt.year == _yr, "_n"].iloc[0])
                _fig.add_vline(x=_x0, line=dict(color="lightgray", width=1))
                _fig.add_annotation(x=_x0, y=_ymax, text=str(_yr), showarrow=False,
                                    yshift=8, font=dict(size=10, color="gray"))
            _fig.update_layout(template="plotly_white", height=420,
                               title=f"Rolling Expectancy (R) — {len(_fr)} trades, overall {_overall:+.3f}R",
                               xaxis_title="Trade # (chronological)", yaxis_title="Exp R",
                               legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"))
            st.plotly_chart(_fig, use_container_width=True)

            if _grain == "Year":
                _key = _dt.dt.year.astype(str)
            elif _grain == "Half-year":
                _key = _dt.dt.year.astype(str) + "-H" + ((_dt.dt.quarter > 2).astype(int) + 1).astype(str)
            else:
                _key = _dt.dt.year.astype(str) + "-Q" + _dt.dt.quarter.astype(str)
            _per = (pd.DataFrame({"R": _R.values, "k": _key.values})
                    .groupby("k")["R"].agg(["count", "mean"]))
            _per.columns = ["Trades", "Exp R"]

            _bar = go.Figure(go.Bar(
                x=_per.index, y=_per["Exp R"],
                marker_color=np.where(_per["Exp R"] >= 0, "#2ca02c", "#d62728"),
                text=[f"{v:+.2f}" for v in _per["Exp R"]], textposition="outside"))
            _bar.add_hline(y=_overall, line=dict(color="green", dash="dash", width=1))
            _bar.update_layout(template="plotly_white", height=320, margin=dict(t=40),
                               title=f"Exp R by {_grain.lower()}", yaxis_title="Exp R")
            st.plotly_chart(_bar, use_container_width=True)

            _disp = _per.copy()
            _disp["Exp R"] = _disp["Exp R"].map(lambda v: f"{v:+.3f}")
            st.dataframe(_disp, use_container_width=True)
            _green = int((_per["Exp R"] >= 0).sum())
            st.caption(f"**{_green}/{len(_per)} {_grain.lower()} periods positive.** "
                       f"Overall {_overall:+.3f}R over {len(_fr)} trades. "
                       f"R is contract-independent — identical for 1c, 2c or MES.")

    # ── Detail (collapsed) ────────────────────────────────────────────────────
    with st.expander("📊 Detail", expanded=False):
        if summary:
            r1 = st.columns(6)
            r1[0].metric("Signals",       f"{summary['n_total']}")
            r1[1].metric("Filtered Out",  f"{summary['n_filtered']}")
            r1[2].metric("Gross PnL",     f"${summary['gross_total']:,.0f}")
            r1[3].metric("Profit Factor", _pf_str)
            r1[4].metric("W/L Ratio",     _wl_str)
            r1[5].metric("Exp $",         f"${summary['exp_dollar']:+.0f}")

            r2 = st.columns(6)
            r2[0].metric("Slippage",      _slip_str)
            r2[1].metric("Commission",    f"${_actual_comm:.0f}")
            r2[2].metric("Total Cost",    f"${_total_cost:.0f}")
            r2[3].metric("Max Risk $",    f"${summary['max_risk_dollar']:,.0f}", help="Largest single-trade risk")
            r2[4].metric("Max Conc Risk", f"${summary.get('max_concurrent_risk_dollar', 0):,.0f}", help="Peak total $ at risk across all simultaneously open trades")
            r2[5].metric("Avg Risk $",    f"${summary['avg_risk_dollar']:,.0f}")

            r3 = st.columns(6)
            r3[0].metric("Avg MAE",       f"{summary['avg_mae_pts']:.2f} pts")
            r3[1].metric("Avg MFE",       f"{summary['avg_mfe_pts']:.2f} pts")
            r3[2].metric("MAE R",         f"{summary['avg_mae_R']:.2f}")
            r3[3].metric("MFE R",         f"{summary['avg_mfe_R']:.2f}")
            r3[4].metric("Largest Win",   f"${summary['largest_win']:+.0f}")
            r3[5].metric("Largest Loss",  f"${summary['largest_loss']:+.0f}")
        else:
            st.info("No filled trades in the selected range.")

    # ── Execution Audit (main run) ───────────────────────────────────────────
    with st.expander("🔍 Execution Audit — verify fills against tick data", expanded=False):
      try:
        if summary and not results.empty:
            _au = results[results["Filled"] == True].copy()
            if _au.empty:
                st.info("No filled trades to audit.")
            else:
                _ts_sz = 0.25
                _sig_dt = pd.to_datetime(_au["DateTime"])

                # ── Computed delay columns (ms) for eyeball verification ──
                _ref_t = pd.to_datetime(_au.get("ReferenceTime"))
                _live_t = pd.to_datetime(_au.get("OrderLiveTime"))
                _retr_t = pd.to_datetime(_au.get("RetraceTime"))
                _thru_t = pd.to_datetime(_au.get("FirstThroughTime"))
                _entry_t = pd.to_datetime(_au.get("EntryTime"))

                # Actual elapsed ms from signal bar close to each event
                _au["SigToRef_ms"] = ((_ref_t - _sig_dt).dt.total_seconds() * 1000).round(0)
                _au["SigToLive_ms"] = ((_live_t - _sig_dt).dt.total_seconds() * 1000).round(0)
                _au["SigToFill_ms"] = ((_entry_t - _sig_dt).dt.total_seconds() * 1000).round(0)
                _au["LiveToFill_ms"] = ((_entry_t - _live_t).dt.total_seconds() * 1000).round(0)

                _expected_delay = _au.get("ActualCalcMs", 0).fillna(0).astype(float)
                _expected_wire = _au.get("WireDelayMs", 0).fillna(0).astype(float)
                _expected_total = _expected_delay + _expected_wire

                # ── Y/N verification columns ──

                # 1. SEPrice = first tick price (always, ESA v2)
                _au["SEPrice_OK"] = "?"
                if "SEPrice" in _au.columns and "ReferenceTime" in _au.columns:
                    _au["SEPrice_OK"] = np.where(
                        _ref_t.notna() & (_au["SigToRef_ms"] >= 0), "Y", "N")

                # 2. ReferenceTime >= DateTime (SEPrice tick is after signal bar close)
                _au["Ref≥SigDt"] = np.where(
                    _ref_t.notna() & (_ref_t >= _sig_dt), "Y", "N")

                # 3. OrderLiveTime >= DateTime + delay + wire
                _au["Live≥Delay"] = "N/A"
                if _live_t is not None:
                    _live_valid = _live_t.notna()
                    _au.loc[_live_valid, "Live≥Delay"] = np.where(
                        _au.loc[_live_valid, "SigToLive_ms"] >= _expected_total[_live_valid] - 1,
                        "Y", "N")
                    _au.loc[_expected_total == 0, "Live≥Delay"] = np.where(
                        _au.loc[_expected_total == 0, "SigToLive_ms"] >= 0, "Y", "N")

                # 4. Fill happens after order is live
                _au["Fill≥Live"] = "N/A"
                if _entry_t is not None and _live_t is not None:
                    _both_valid = _entry_t.notna() & _live_t.notna()
                    _au.loc[_both_valid, "Fill≥Live"] = np.where(
                        _entry_t[_both_valid] >= _live_t[_both_valid], "Y", "N")

                # 5. Stop entry: retrace after order live
                _is_stop = _au.get("EntryType", "") == "stop"
                _stop_mask = _is_stop if isinstance(_is_stop, pd.Series) else pd.Series(False, index=_au.index)

                _au["Retr≥Live"] = "N/A"
                if _retr_t is not None and _live_t is not None:
                    _sm_valid = _stop_mask & _retr_t.notna() & _live_t.notna()
                    _au.loc[_sm_valid, "Retr≥Live"] = np.where(
                        _retr_t[_sm_valid] >= _live_t[_sm_valid], "Y", "N")

                # 6. Stop entry: tick-through after retrace (sequence)
                _au["Thru>Retr"] = "N/A"
                if _retr_t is not None and _thru_t is not None:
                    _sm_both = _stop_mask & _retr_t.notna() & _thru_t.notna()
                    _au.loc[_sm_both, "Thru>Retr"] = np.where(
                        _thru_t[_sm_both] >= _retr_t[_sm_both], "Y", "N")

                # 7. Slip applied correctly (|EntryPrice - RawFillPrice| == slip_ticks * tick_size)
                _au["SlipOK"] = "?"
                if "RawFillPrice" in _au.columns and "EntrySlipTicks" in _au.columns:
                    _slip_diff = (_au["EntryPrice"] - _au["RawFillPrice"]).abs()
                    _slip_exp = _au["EntrySlipTicks"].abs() * _ts_sz
                    _au["SlipOK"] = np.where(
                        (_slip_diff - _slip_exp).abs() <= 0.001, "Y", "N")

                # 8. Stop fill price = SEPrice ± 1 tick (for stop entries)
                _au["StopFillOK"] = "N/A"
                if _stop_mask.any() and "RawFillPrice" in _au.columns:
                    _is_long = _au["Direction"] == "Long"
                    _exp_stop_fill_long = _au["SEPrice"] + _ts_sz
                    _exp_stop_fill_short = _au["SEPrice"] - _ts_sz
                    _exp_fill = np.where(_is_long, _exp_stop_fill_long, _exp_stop_fill_short)
                    _au.loc[_stop_mask, "StopFillOK"] = np.where(
                        ((_au.loc[_stop_mask, "RawFillPrice"] - _exp_fill[_stop_mask]).abs() < 0.001),
                        "Y", "N")

                # ── Summary banner ──
                _n_au = len(_au)
                _checks = ["Ref≥SigDt", "Live≥Delay", "Fill≥Live", "SlipOK"]
                _stop_checks = ["Retr≥Live", "Thru>Retr", "StopFillOK"]
                _fails = {}
                for _ck in _checks + _stop_checks:
                    if _ck in _au.columns:
                        _n_fail = int((_au[_ck] == "N").sum())
                        if _n_fail > 0:
                            _fails[_ck] = _n_fail
                if _fails:
                    st.error(f"**{sum(_fails.values())} verification failures:** " +
                             ", ".join(f"{k}={v}" for k, v in _fails.items()))
                else:
                    st.success(f"**All {_n_au} trades pass verification checks.**")

                # ── Display table ──
                _au_cols = [
                    "Date", "SignalType", "Direction", "DateTime",
                    "SBClose", "SEPrice", "RawFillPrice", "EntryPrice",
                    "EntryType", "EntryTime",
                    "EntrySlipTicks", "ExitSlipTicks",
                    "ActualCalcMs", "WireDelayMs",
                    "ReferenceTime", "OrderLiveTime",
                    "RetraceTime", "FirstThroughTime",
                    "ExitTriggerTime",
                    "SigToRef_ms", "SigToLive_ms", "SigToFill_ms", "LiveToFill_ms",
                    "ExitPrice", "ExitReason",
                    "GrossPnL", "NetPnL", "R_achieved",
                    "Ref≥SigDt", "Live≥Delay", "Fill≥Live",
                    "SlipOK", "Retr≥Live", "Thru>Retr", "StopFillOK",
                ]
                _au_cols = [c for c in _au_cols if c in _au.columns]
                st.dataframe(_au[_au_cols].reset_index(drop=True),
                             use_container_width=True, height=500)

                # ── Filter to failures only ──
                _fail_rows = _au[_au_cols].copy()
                _any_fail = pd.Series(False, index=_fail_rows.index)
                for _ck in _checks + _stop_checks:
                    if _ck in _fail_rows.columns:
                        _any_fail = _any_fail | (_fail_rows[_ck] == "N")
                if _any_fail.any():
                    with st.expander(f"⚠️ Show only failed checks ({int(_any_fail.sum())} trades)",
                                     expanded=False):
                        st.dataframe(_fail_rows[_any_fail].reset_index(drop=True),
                                     use_container_width=True, height=400)

                # ── Fill time distribution table ──
                st.subheader("Signal-to-Fill Time Distribution")
                _fill_min = _au["SigToFill_ms"] / 60000.0
                _buckets = [
                    ("< 30 sec", 0, 0.5),
                    ("30s – 1 min", 0.5, 1),
                    ("1–5 min (within bar)", 1, 5),
                    ("5–15 min (1–3 bars)", 5, 15),
                    ("15–30 min (3–6 bars)", 15, 30),
                    ("30–60 min (6–12 bars)", 30, 60),
                    ("> 60 min (12+ bars)", 60, 999999),
                ]
                _ft_rows = []
                for _bl, _blo, _bhi in _buckets:
                    _bm = (_fill_min >= _blo) & (_fill_min < _bhi)
                    _bn = int(_bm.sum())
                    _bpct = _bn / len(_au) * 100 if len(_au) else 0
                    _bsub = _au[_bm]
                    _br = float(_bsub["R_achieved"].mean()) if _bn > 0 else 0
                    _bw = float((_bsub["R_achieved"] > 0).mean() * 100) if _bn > 0 else 0
                    _bnet = float(_bsub["NetPnL"].sum()) if _bn > 0 else 0
                    _ft_rows.append({
                        "Bucket": _bl, "Trades": _bn,
                        "Pct": f"{_bpct:.1f}%", "Avg R": f"{_br:+.3f}",
                        "Win%": f"{_bw:.1f}%", "Net $": f"${_bnet:+,.0f}",
                    })
                st.dataframe(pd.DataFrame(_ft_rows).set_index("Bucket"),
                             use_container_width=True)
                st.caption("Trades filling after 30 min are typically net losers. "
                           "Use **Max fill time** in the ESA expander to cap stale fills.")
        else:
            st.info("Run the simulation first.")
      except Exception as _audit_err:
        st.error(f"Execution Audit error: {_audit_err}")
        import traceback
        st.code(traceback.format_exc())

    # ── ESA Phase B — Execution Sensitivity Comparison ──────────────────────
    with st.expander("🔬 Execution Sensitivity Analysis (ESA)", expanded=False):
        if summary and not results.empty:
            _esa_all_presets = list(_ESA_PRESETS.keys())
            _esa_selected = st.multiselect(
                "Presets to compare", _esa_all_presets,
                default=_esa_all_presets, key="ba_esa_presets")

            _esa_run = st.button("▶ Run ESA Comparison", key="ba_esa_run_btn",
                                 type="secondary", use_container_width=False)

            _esa_cache_key = "ba_esa_cache"
            _esa_fp_key = "ba_esa_fp"
            _esa_fp = hash((
                _sim_fp,
                tuple(sorted(_esa_selected)),
            ))
            _esa_cached = (st.session_state.get(_esa_fp_key) == _esa_fp
                           and st.session_state.get(_esa_cache_key) is not None)

            if _esa_run or _esa_cached:
                if _esa_run or not _esa_cached:
                    if not _esa_selected:
                        st.warning("Select at least one preset.")
                    else:
                        _esa_results = {}
                        _prog = st.progress(0, text="Running ESA presets…")
                        for _pi, _pname in enumerate(_esa_selected):
                            _prog.progress((_pi) / len(_esa_selected),
                                           text=f"Running **{_pname}**…")
                            _pp = _ESA_PRESETS[_pname]
                            _p_eslip = _pp["entry_slip"]
                            _p_xslip = _pp["exit_slip"]
                            _p_delay = int(_pp["calc_delay_ms"])
                            _p_wire = int(_pp.get("wire_delay_ms", 0))
                            _p_res = simulate_trades(
                                filtered_signals, ticks_by_date, target_r,
                                _p_eslip, _p_xslip, stop_offset,
                                tick_value, contracts, commission,
                                overrides=st.session_state.get("ba_manual_overrides"),
                                bars_by_date=bars_by_date_sim,
                                multileg=use_multileg, t1_r=t1_r,
                                t1_action=t1_action, contracts_t1=contracts_t1,
                                contracts_t2=contracts_t2,
                                ratchet_r=ratchet_r_v, ratchet_dest=ratchet_dest_v,
                                ratchet_lock_r=ratchet_lock_r_v,
                                ml_pb_r=ml_pb_r_v, scale_in_style=scale_in_style_v,
                                pb_round=pb_round_v,
                                threeleg=use_threeleg,
                                contracts_e1=e1c_3l, contracts_e2=e2c_3l,
                                contracts_e3=e3c_3l,
                                pb1_r=pb1_r_val, pb1_ticks=pb1_ticks_v,
                                pb2_r=pb2_r_val, pb2_ticks=pb2_ticks_v,
                                t2_r=t2_r_val,
                                entry_model=exec_entry_model,
                                calc_delay_ms=_p_delay, wire_delay_ms=_p_wire,
                                max_fill_ms=exec_max_fill_ms, exec_seed=exec_seed,
                            )
                            if first_trade_only and not _p_res.empty:
                                _fm = _p_res["Filled"] == True
                                _fs = _p_res[_fm].sort_values(["Date", "SignalNum"])
                                _ki = _fs.groupby("Date").head(1).index
                                _p_res = _p_res.drop(
                                    _p_res[_fm & ~_p_res.index.isin(_ki)].index
                                ).reset_index(drop=True)
                            if first_2_filled_only and not _p_res.empty:
                                _fm = _p_res["Filled"] == True
                                _fs = _p_res[_fm].sort_values(["Date", "SignalNum"])
                                _ki = _fs.groupby("Date").head(2).index
                                _p_res = _p_res.drop(
                                    _p_res[_fm & ~_p_res.index.isin(_ki)].index
                                ).reset_index(drop=True)
                            _sc = e1c_3l + e2c_3l + e3c_3l if use_threeleg else contracts
                            _p_sum = compute_summary(
                                _p_res, commission, contracts=_sc,
                                is_multileg=(use_multileg or use_threeleg),
                                t1_action=t1_action,
                                contracts_t1=contracts_t1,
                                contracts_t2=contracts_t2)
                            _esa_results[_pname] = {"results": _p_res, "summary": _p_sum}
                        _prog.empty()
                        st.session_state[_esa_cache_key] = _esa_results
                        st.session_state[_esa_fp_key] = _esa_fp

                _esa_data = st.session_state.get(_esa_cache_key, {})
                if _esa_data:
                    _esa_metrics = []
                    for _pn in _esa_all_presets:
                        if _pn not in _esa_data:
                            continue
                        _s = _esa_data[_pn]["summary"]
                        if not _s:
                            continue
                        _esa_metrics.append({
                            "Preset": _pn,
                            "Trades": _s.get("n_trades", 0),
                            "Win%": _s.get("win_pct", 0),
                            "PF": _s.get("pf", 0),
                            "Exp $": _s.get("exp_dollar", 0),
                            "Exp R": _s.get("exp_r", 0),
                            "Net $": _s.get("net_total", 0),
                            "MaxDD": _s.get("max_dd", 0),
                            "CAGR": _s.get("cagr", 0),
                            "Sharpe": _s.get("sharpe", 0),
                            "SQN": _s.get("sqn", 0),
                        })

                    if _esa_metrics:
                        _esa_df = pd.DataFrame(_esa_metrics).set_index("Preset")

                        # ── Comparison table ──
                        st.subheader("Comparison")
                        _disp = _esa_df.copy()
                        _disp["Trades"] = _disp["Trades"].astype(int)
                        _disp["Win%"] = _disp["Win%"].map(lambda v: f"{v:.1f}%")
                        _disp["PF"] = _disp["PF"].map(lambda v: f"{v:.2f}")
                        _disp["Exp $"] = _disp["Exp $"].map(lambda v: f"${v:+,.0f}")
                        _disp["Exp R"] = _disp["Exp R"].map(lambda v: f"{v:+.3f}")
                        _disp["Net $"] = _disp["Net $"].map(lambda v: f"${v:+,.0f}")
                        _disp["MaxDD"] = _disp["MaxDD"].map(lambda v: f"${v:,.0f}")
                        _disp["CAGR"] = _disp["CAGR"].map(
                            lambda v: f"{v:.1%}" if not np.isnan(v) else "N/A")
                        _disp["Sharpe"] = _disp["Sharpe"].map(lambda v: f"{v:.2f}")
                        _disp["SQN"] = _disp["SQN"].map(lambda v: f"{v:.1f}")
                        st.dataframe(_disp, use_container_width=True)

                        # ── Degradation vs Optimistic (lightest preset) ──
                        _base_name = "Optimistic"
                        if _base_name in _esa_df.index and len(_esa_df) > 1:
                            st.subheader(f"Degradation vs {_base_name}")
                            _ideal = _esa_df.loc[_base_name]
                            _deg_rows = []
                            for _pn in _esa_df.index:
                                if _pn == _base_name:
                                    continue
                                _row = _esa_df.loc[_pn]
                                _dr = {"Preset": _pn}
                                for _col in ["Trades", "Win%", "PF", "Exp $",
                                             "Exp R", "Net $", "CAGR", "Sharpe", "SQN"]:
                                    _iv = _ideal[_col]
                                    _rv = _row[_col]
                                    _delta = _rv - _iv
                                    if _col == "Trades":
                                        _dr[f"Δ {_col}"] = f"{int(_delta):+d}"
                                    elif _col in ("Win%",):
                                        _dr[f"Δ {_col}"] = f"{_delta:+.1f}pp"
                                    elif _col in ("Exp $", "Net $"):
                                        _dr[f"Δ {_col}"] = f"${_delta:+,.0f}"
                                    elif _col == "CAGR":
                                        if np.isnan(_iv) or np.isnan(_rv):
                                            _dr[f"Δ {_col}"] = "N/A"
                                        else:
                                            _dr[f"Δ {_col}"] = f"{_delta:+.1%}"
                                    else:
                                        _dr[f"Δ {_col}"] = f"{_delta:+.3f}"
                                _deg_rows.append(_dr)
                            _deg_df = pd.DataFrame(_deg_rows).set_index("Preset")
                            st.dataframe(_deg_df, use_container_width=True)

                        # ── Execution Robustness Score ──
                        st.subheader("Execution Robustness Score")
                        _cons_name = "Conservative"
                        _base_rob = "Optimistic"
                        if _base_rob in _esa_df.index and _cons_name in _esa_df.index:
                            _base_expr = _esa_df.loc[_base_rob, "Exp R"]
                            _cons_expr = _esa_df.loc[_cons_name, "Exp R"]
                            if abs(_base_expr) < 0.005:
                                st.warning(f"{_base_rob} Exp R ≈ 0 — robustness score "
                                           "undefined (no edge to degrade).")
                                _rob_score = float("nan")
                            elif _base_expr < 0:
                                st.warning(f"{_base_rob} Exp R < 0 — no positive edge "
                                           "at baseline.")
                                _rob_score = float("nan")
                            else:
                                _rob_score = _cons_expr / _base_expr

                            if not np.isnan(_rob_score):
                                if _rob_score >= 0.80:
                                    _band, _color = "Strong", "🟢"
                                elif _rob_score >= 0.60:
                                    _band, _color = "Adequate", "🟡"
                                elif _rob_score >= 0.40:
                                    _band, _color = "Weak", "🟠"
                                else:
                                    _band, _color = "Fragile", "🔴"
                                st.metric(
                                    f"ExpR Robustness (Conservative / {_base_rob})",
                                    f"{_rob_score:.1%}",
                                    delta=f"{_band}",
                                    delta_color="off",
                                )
                                st.caption(
                                    f"{_color} **{_band}** — Conservative Exp R "
                                    f"({_cons_expr:+.3f}) retains "
                                    f"**{_rob_score:.0%}** of {_base_rob} ({_base_expr:+.3f}). "
                                    f"Bands: ≥80% Strong · ≥60% Adequate · ≥40% Weak · <40% Fragile.")
                        else:
                            _missing = []
                            if _ideal_name not in _esa_df.index:
                                _missing.append(_ideal_name)
                            if _cons_name not in _esa_df.index:
                                _missing.append(_cons_name)
                            st.info(f"Select **{' + '.join(_missing)}** to compute "
                                    f"the robustness score.")

                        # ── Equity overlay chart ──
                        st.subheader("OOS Equity Overlay")
                        _eq_fig = go.Figure()
                        _preset_colors = {
                            "Optimistic": "#2ca02c", "Realistic": "#1f77b4",
                            "Conservative": "#ff7f0e", "Brutal": "#d62728",
                        }
                        for _pn in _esa_all_presets:
                            if _pn not in _esa_data:
                                continue
                            _pr = _esa_data[_pn]["results"]
                            _pf_filled = _pr[_pr["Filled"] == True].sort_values(
                                ["Date", "EntryTime"])
                            if _pf_filled.empty:
                                continue
                            _eq = _pf_filled["NetPnL"].cumsum()
                            _eq_fig.add_trace(go.Scatter(
                                x=list(range(len(_eq))), y=_eq.values,
                                name=_pn, mode="lines",
                                line=dict(
                                    color=_preset_colors.get(_pn, "#999"),
                                    width=2 if _pn in ("Optimistic", "Conservative") else 1.2,
                                ),
                            ))
                        _eq_fig.update_layout(
                            template="plotly_white", height=400,
                            title="Cumulative Net PnL by Execution Preset",
                            xaxis_title="Trade #", yaxis_title="Cumulative Net $",
                            legend=dict(orientation="h", y=1.02, x=0.5,
                                        xanchor="center"),
                        )
                        st.plotly_chart(_eq_fig, use_container_width=True)

                        # ── Audit drill-down ──
                        with st.expander("🔍 Execution Audit — per-trade detail",
                                         expanded=False):
                            _audit_preset = st.selectbox(
                                "Preset", [p for p in _esa_all_presets
                                           if p in _esa_data],
                                key="ba_esa_audit_preset")
                            if _audit_preset and _audit_preset in _esa_data:
                                _ar = _esa_data[_audit_preset]["results"]
                                _af = _ar[_ar["Filled"] == True].copy()

                                _ts_size = 0.25
                                _is_long = _af["Direction"] == "Long"

                                # Y/N: delay applied correctly
                                if "ActualCalcMs" in _af.columns:
                                    _pp_ad = _ESA_PRESETS.get(_audit_preset, {})
                                    _exp_delay = int(_pp_ad.get("calc_delay_ms", 0))
                                    _af["DelayOK"] = np.where(
                                        _af["ActualCalcMs"] == _exp_delay, "Y", "N")
                                else:
                                    _af["DelayOK"] = "?"

                                # Y/N: SEPrice after SBClose + delay
                                if "ReferenceTime" in _af.columns and "EntryTime" in _af.columns:
                                    _ref_valid = _af["ReferenceTime"].notna()
                                    _af["RefAfterSB"] = np.where(
                                        _ref_valid & (_af["ReferenceTime"] >= _af["EntryTime"].shift(0)),
                                        "Y", "?")
                                    _af.loc[_ref_valid, "RefAfterSB"] = "Y"
                                    _af.loc[~_ref_valid, "RefAfterSB"] = "?"

                                # Y/N: for stop entry — retrace happened
                                if "RetraceTime" in _af.columns:
                                    _is_stop = _af.get("EntryType", "") == "stop"
                                    _af["RetraceOK"] = "N/A"
                                    _stop_mask = _is_stop if isinstance(_is_stop, pd.Series) else pd.Series(False, index=_af.index)
                                    _af.loc[_stop_mask, "RetraceOK"] = np.where(
                                        _af.loc[_stop_mask, "RetraceTime"].notna(), "Y", "N")

                                # Y/N: for stop entry — tick-through happened
                                if "FirstThroughTime" in _af.columns:
                                    _af["ThruOK"] = "N/A"
                                    if isinstance(_is_stop, pd.Series):
                                        _af.loc[_stop_mask, "ThruOK"] = np.where(
                                            _af.loc[_stop_mask, "FirstThroughTime"].notna(), "Y", "N")

                                # Y/N: retrace before tick-through (sequence check)
                                if "RetraceTime" in _af.columns and "FirstThroughTime" in _af.columns:
                                    _af["SeqOK"] = "N/A"
                                    if isinstance(_is_stop, pd.Series):
                                        _both = _stop_mask & _af["RetraceTime"].notna() & _af["FirstThroughTime"].notna()
                                        _af.loc[_both, "SeqOK"] = np.where(
                                            _af.loc[_both, "RetraceTime"] <= _af.loc[_both, "FirstThroughTime"],
                                            "Y", "N")

                                # Y/N: slip applied correctly
                                _af["SlipOK"] = np.where(
                                    (_af["EntryPrice"] - _af["RawFillPrice"]).abs() <=
                                    _af["EntrySlipTicks"] * _ts_size + 0.001,
                                    "Y", "N") if "RawFillPrice" in _af.columns else "?"

                                _audit_cols = [
                                    "Date", "SignalType", "Direction",
                                    "SBClose", "SEPrice", "RawFillPrice",
                                    "EntryPrice", "EntryType",
                                    "EntrySlipTicks", "ExitSlipTicks",
                                    "ActualCalcMs", "WireDelayMs", "ExecCostTicks",
                                    "ReferenceTime", "OrderLiveTime",
                                    "RetraceTime",
                                    "FirstThroughTime", "ExitTriggerTime",
                                    "ExitPrice", "ExitReason",
                                    "GrossPnL", "NetPnL", "R_achieved",
                                    "DelayOK", "SlipOK",
                                    "RetraceOK", "ThruOK", "SeqOK",
                                ]
                                _audit_cols = [c for c in _audit_cols
                                               if c in _af.columns]
                                st.dataframe(
                                    _af[_audit_cols].reset_index(drop=True),
                                    use_container_width=True, height=400)
                    else:
                        st.info("No filled trades — nothing to compare.")
        else:
            st.info("Run the simulation first to enable ESA comparison.")

    # ── Edge Analysis ─────────────────────────────────────────────────────────
    with st.expander("📊 Edge Analysis", expanded=False):
        if summary and not results.empty:
            _ea_filled = results[results["Filled"] == True].copy()
            _ea_wins   = _ea_filled[
                _ea_filled["ExitReason"].str.contains("Target", na=False) |
                _ea_filled["ExitReason"].isin(["T1+BE", "T1_only"])
            ]
            _ea_losses = _ea_filled[_ea_filled["ExitReason"].isin(["Stop", "E1E2+Stop"])]

            # ── R-multiple histogram ──────────────────────────────────────────
            _r_vals = _ea_filled["R_achieved"].dropna()
            if not _r_vals.empty:
                _exp_r  = float(_r_vals.mean())
                _r_pos  = _r_vals[_r_vals >= 0]
                _r_neg  = _r_vals[_r_vals < 0]
                _fig_r  = go.Figure()
                _bin_sz = 0.1
                if not _r_pos.empty:
                    _fig_r.add_trace(go.Histogram(
                        x=_r_pos, name="Positive R", xbins=dict(size=_bin_sz),
                        marker_color="rgba(46,204,113,0.75)", marker_line_width=0,
                    ))
                if not _r_neg.empty:
                    _fig_r.add_trace(go.Histogram(
                        x=_r_neg, name="Negative R", xbins=dict(size=_bin_sz),
                        marker_color="rgba(231,76,60,0.75)", marker_line_width=0,
                    ))
                _ci_lo_ea = summary.get("exp_r_ci_lo", np.nan)
                _ci_hi_ea = summary.get("exp_r_ci_hi", np.nan)
                if not (np.isnan(_ci_lo_ea) or np.isnan(_ci_hi_ea)):
                    _fig_r.add_vrect(x0=_ci_lo_ea, x1=_ci_hi_ea,
                                     fillcolor="rgba(243,156,18,0.25)", line_width=0)
                    _fig_r.add_annotation(
                        x=_ci_lo_ea, y=1, yref="paper", xanchor="right",
                        text=f"95% CI [{_ci_lo_ea:+.2f}, {_ci_hi_ea:+.2f}]",
                        showarrow=False, font=dict(color="#f39c12", size=11),
                        bgcolor="rgba(0,0,0,0.4)",
                    )
                _fig_r.add_vline(x=0, line_color="rgba(255,255,255,0.4)", line_dash="dot")
                _fig_r.add_vline(x=_exp_r, line_color="#f39c12", line_dash="dash",
                                 annotation_text=f"Exp R {_exp_r:+.2f}",
                                 annotation_position="top left")
                _fig_r.update_layout(
                    barmode="overlay", height=300, margin=dict(l=40, r=20, t=30, b=40),
                    legend=dict(orientation="h", y=1.08),
                    xaxis_title="R multiple (E1 basis)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_r, use_container_width=True)

            # ── MAE / MFE by outcome ──────────────────────────────────────────
            _mae_col = "MAE_R"
            _mfe_col = "MFE_R"
            _col_l, _col_r = st.columns(2)

            with _col_l:
                st.caption("**MAE R — how far price moved against you** (winners blue, losers red)")
                _mae_w = _ea_wins[_mae_col].dropna()
                _mae_l = _ea_losses[_mae_col].dropna()
                _fig_mae = go.Figure()
                if not _mae_w.empty:
                    _fig_mae.add_trace(go.Histogram(
                        x=_mae_w, name="Winners", xbins=dict(size=0.05),
                        marker_color="rgba(52,152,219,0.7)", marker_line_width=0,
                    ))
                if not _mae_l.empty:
                    _fig_mae.add_trace(go.Histogram(
                        x=_mae_l, name="Losers", xbins=dict(size=0.05),
                        marker_color="rgba(231,76,60,0.7)", marker_line_width=0,
                    ))
                _fig_mae.update_layout(
                    barmode="overlay", height=260, margin=dict(l=40, r=10, t=20, b=40),
                    legend=dict(orientation="h", y=1.1),
                    xaxis_title="MAE (R)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_mae, use_container_width=True)

            with _col_r:
                st.caption("**MFE R — best price reached before exit** (winners blue, losers red)")
                _mfe_w = _ea_wins[_mfe_col].dropna()
                _mfe_l = _ea_losses[_mfe_col].dropna()
                _fig_mfe = go.Figure()
                if not _mfe_w.empty:
                    _fig_mfe.add_trace(go.Histogram(
                        x=_mfe_w, name="Winners", xbins=dict(size=0.05),
                        marker_color="rgba(52,152,219,0.7)", marker_line_width=0,
                    ))
                if not _mfe_l.empty:
                    _fig_mfe.add_trace(go.Histogram(
                        x=_mfe_l, name="Losers", xbins=dict(size=0.05),
                        marker_color="rgba(231,76,60,0.7)", marker_line_width=0,
                    ))
                _fig_mfe.update_layout(
                    barmode="overlay", height=260, margin=dict(l=10, r=10, t=20, b=40),
                    legend=dict(orientation="h", y=1.1),
                    xaxis_title="MFE (R)", yaxis_title="Count",
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                )
                st.plotly_chart(_fig_mfe, use_container_width=True)

            # ── Drawdown events table ─────────────────────────────────────────
            st.markdown("**Drawdown periods**")
            _dd_sorted  = _ea_filled.sort_values(["Date", "EntryTime"]).reset_index(drop=True)
            _dd_pnl     = _dd_sorted["NetPnL"].values
            _dd_dates   = _dd_sorted["Date"].values
            _n_dd       = len(_dd_pnl)
            _dd_equity  = np.zeros(_n_dd + 1)
            for _i in range(_n_dd):
                _dd_equity[_i + 1] = _dd_equity[_i] + _dd_pnl[_i]

            _dd_events = []
            _pk        = 0.0
            _pk_date   = None
            _in_dd     = False
            _tr_val    = 0.0
            _tr_date   = None

            for _i in range(1, _n_dd + 1):
                _v = _dd_equity[_i]
                _d = _dd_dates[_i - 1]
                if _v >= _pk:
                    if _in_dd:
                        _dd_events.append({
                            "Start":    str(_pk_date),
                            "Trough":   str(_tr_date),
                            "Recovery": str(_d),
                            "DD $":     f"${_tr_val - _pk:,.0f}",
                            "Days":     (pd.Timestamp(_d) - pd.Timestamp(_pk_date)).days,
                        })
                        _in_dd = False
                    _pk      = _v
                    _pk_date = _d
                else:
                    if not _in_dd:
                        _in_dd   = True
                        _tr_val  = _v
                        _tr_date = _d
                    elif _v < _tr_val:
                        _tr_val  = _v
                        _tr_date = _d

            if _in_dd:
                _dd_events.append({
                    "Start":    str(_pk_date),
                    "Trough":   str(_tr_date),
                    "Recovery": "—",
                    "DD $":     f"${_tr_val - _pk:,.0f}",
                    "Days":     (pd.Timestamp(_dd_dates[-1]) - pd.Timestamp(_pk_date)).days,
                })

            if _dd_events:
                _dd_df = pd.DataFrame(_dd_events).sort_values("DD $")
                st.dataframe(_dd_df, use_container_width=True, hide_index=True)
            else:
                st.success("No drawdown periods — equity curve is monotonically increasing.")
        else:
            st.info("Run a simulation first.")

    # ── Ratchet bar-ambiguity diagnostic (AIAO+ratchet mode only) ────────────
    _is_aiao_ratchet = (not use_multileg and not use_threeleg and ratchet_r_v > 0)
    if _is_aiao_ratchet:
        with st.expander("🔬 Ratchet BE-Stop Diagnostic", expanded=False):
            st.caption(
                "Finds AIAO trades that stopped at ~BE after ratchet fired, "
                "then re-simulates each as BE Stop to show what the outcome "
                "would have been. Isolates the bar-level intrabar ambiguity."
            )
            if st.button("Run Diagnostic", key="ba_run_ratchet_diag"):
                with st.spinner("Re-simulating…"):
                    diag_df = diagnose_ratchet_bar_ambiguities(
                        results,
                        ticks_by_date,
                        bars_by_date_sim,
                        ratchet_r=ratchet_r_v,
                        target_r=target_r,
                        tick_value=tick_value,
                        entry_slip=entry_slip,
                        exit_slip=exit_slip,
                        stop_offset=stop_offset,
                        commission=commission,
                        contracts=contracts,
                    )
                st.session_state["ba_diag_df"] = diag_df

            diag_df = st.session_state.get("ba_diag_df")
            if diag_df is not None and not diag_df.empty:
                n_amb   = int(diag_df["Ambiguous_Bar"].sum())
                n_total_be = len(diag_df)
                delta_sum  = diag_df["PnL_Delta"].sum()
                amb_delta  = diag_df.loc[diag_df["Ambiguous_Bar"], "PnL_Delta"].sum() if n_amb else 0

                mc = st.columns(4)
                mc[0].metric("BE-stop trades found",   n_total_be)
                mc[1].metric("Confirmed ambiguous bars", n_amb)
                mc[2].metric("Total PnL delta (all)",  f"${delta_sum:+,.0f}")
                mc[3].metric("PnL delta (ambiguous bars only)", f"${amb_delta:+,.0f}")

                show_all = st.checkbox("Show all BE-stop trades (uncheck = ambiguous only)",
                                       value=False, key="ba_diag_all")
                display_df = (diag_df if show_all else diag_df[diag_df["Ambiguous_Bar"]]).copy()
                # Convert bool to readable label before display
                display_df["Ambiguous_Bar"] = display_df["Ambiguous_Bar"].map(
                    {True: "YES — same bar", False: "no"}
                )
                # Colour-code BEStop_Exit column
                def _be_color(v):
                    if isinstance(v, str):
                        if "Target" in v:  return "color:#26a69a;font-weight:bold"
                        if v == "T1+BE":   return "color:#ff9800"
                    return ""
                st.dataframe(
                    display_df.style.format({
                        "Entry": "{:.2f}", "Stop": "{:.2f}", "T1_Level": "{:.2f}",
                        "Bar_Hi": "{:.2f}", "Bar_Lo": "{:.2f}",
                        "AIAO_Px": "{:.2f}", "AIAO_Net": "${:,.0f}",
                        "BEStop_Px": "{:.2f}", "BEStop_Net": "${:,.0f}",
                        "PnL_Delta": "${:+,.0f}",
                    }).map(
                        lambda v: "background-color:#1a3a1a" if v == "YES — same bar" else "",
                        subset=["Ambiguous_Bar"]
                    ).map(_be_color, subset=["BEStop_Exit"]),
                    use_container_width=True,
                )
                st.caption(
                    "**Ambiguous_Bar = YES** — the exit bar's Hi crossed T1_Level AND its Lo "
                    "crossed Entry on the same bar. AIAO stopped out; BE Stop let it live.  "
                    "**BEStop_Exit: T1+Target** (green) = real money left on table. "
                    "**T1+BE** (orange) = same exit price, only classification differs.  "
                    f"Sum across all {n_total_be} trades: **${delta_sum:+,.0f}**."
                )
            elif diag_df is not None:
                st.success("No ratchet-triggered BE stops found in this result set.")

    # ── Same-Bar Conflict diagnostic ─────────────────────────────────────────
    _sbc_df = results[results["SameBarConflict"] == True].copy() \
        if "SameBarConflict" in results.columns else pd.DataFrame()
    with st.expander(
        f"⚠️ Same-Bar Conflicts  ({len(_sbc_df)} trades)" if not _sbc_df.empty
        else "⚠️ Same-Bar Conflicts  (none found)",
        expanded=not _sbc_df.empty,
    ):
        if _sbc_df.empty:
            st.success(
                "No same-bar conflicts found: no trade's stop AND target "
                "were both reachable in the same bar."
            )
        else:
            st.caption(
                "These trades had both their **stop AND target reachable in the same bar**. "
                "The conservative bar rule applied: stop wins. "
                "The outcome may have been different with tick-level data."
            )
            _ts = TICK_SIZE
            # Derive $ per tick per trade from existing GrossPnL / GrossPnLPts
            # Works for single-leg; for 2-leg it gives blended TV (good enough for direction).
            _sbc_df["_tv"] = _sbc_df.apply(
                lambda r: r["GrossPnL"] / (r["GrossPnLPts"] / _ts)
                if abs(r.get("GrossPnLPts", 0)) > 1e-6 else np.nan,
                axis=1,
            )
            # For single-leg, hypothetical: target wins instead of stop
            # Delta = (Target - ActualStop) * sign(direction) / ts * tv
            def _if_target_won(r):
                tv = r["_tv"]
                if np.isnan(tv):
                    return np.nan
                if r["Direction"] == "Long":
                    delta_pts = r["Target"] - r["ActualStop"]
                else:
                    delta_pts = r["ActualStop"] - r["Target"]
                return r["NetPnL"] + delta_pts / _ts * tv

            _sbc_df["IfTargetWon"] = _sbc_df.apply(_if_target_won, axis=1)
            _sbc_df["PnL_Delta"]   = _sbc_df["IfTargetWon"] - _sbc_df["NetPnL"]
            total_delta = _sbc_df["PnL_Delta"].sum()

            _mc = st.columns(3)
            _mc[0].metric("Trades affected", len(_sbc_df))
            _mc[1].metric("PnL delta if targets won", f"${total_delta:+,.0f}")
            _mc[2].metric("Avg delta / trade", f"${total_delta / len(_sbc_df):+,.0f}")

            _disp = _sbc_df[[
                "Date", "Direction", "EntryPrice", "ActualStop", "Target",
                "ExitReason", "NetPnL", "IfTargetWon", "PnL_Delta",
            ]].rename(columns={
                "Direction": "Dir", "EntryPrice": "Entry",
                "ActualStop": "Stop", "ExitReason": "ExitResult",
                "IfTargetWon": "IfTgtWon_Net",
            }).copy()

            st.dataframe(
                _disp.style.format({
                    "Entry": "{:.2f}", "Stop": "{:.2f}", "Target": "{:.2f}",
                    "NetPnL": "${:,.0f}", "IfTgtWon_Net": "${:,.0f}",
                    "PnL_Delta": "${:+,.0f}",
                }).map(
                    lambda v: "color:#ef5350" if isinstance(v, (int, float)) and v < 0 else
                              "color:#26a69a" if isinstance(v, (int, float)) and v > 0 else "",
                    subset=["PnL_Delta"],
                ),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "**IfTgtWon_Net** — hypothetical net P&L if the target had been reached "
                "before the stop (tick-level outcome unknown). "
                "For 2-Leg Phase-2 BE conflicts the delta is computed as if T2 had won over BE stop."
            )

    # ── Optimal R / PB sweep ─────────────────────────────────────────────────
    _show_optimal_r(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        threeleg=use_threeleg,
        tv_e1=tick_value * e1c_3l, tv_e2=tick_value * e2c_3l, tv_e3=tick_value * e3c_3l,
        e1c=e1c_3l, e2c=e2c_3l, e3c=e3c_3l,
        pb1_ticks=pb1_ticks_v, pb2_ticks=pb2_ticks_v,
        t2_r=t2_r_val,
        scale_in_style=scale_in_style_v, pb_round=pb_round_v,
        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
    )

    # ── Stop multiplier sweep ─────────────────────────────────────────────────
    _show_stop_sweep(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        target_r=target_r,
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
    )

    # ── 2-D Stop × Target sweep (descriptive; never a WFA input) ──────────────
    # target is an AXIS here, not a fixed input — so no target_r is passed.
    _show_stop_target_sweep(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
        bars_by_date=bars_by_date_sim,
        multileg=use_multileg, t1_r=t1_r,
        t1_action=t1_action, contracts_t1=contracts_t1, contracts_t2=contracts_t2,
        first_trade_only=first_trade_only, first_2_filled_only=first_2_filled_only,
    )

    # ── Monthly breakdown ──────────────────────────────────────────────────────
    _show_monthly_breakdown(results, commission)

    # ── Time-of-Day / Day-of-Week breakdown (read-only, Pardo-safe) ────────────
    _show_tod_dow_breakdown(results)

    # ── Regime / indicator expectancy (read-only, descriptive) ─────────────────
    _show_regime_expectancy(results)

    # ── Unfilled signals ──────────────────────────────────────────────────────
    _show_unfilled_table(results, ticks_by_date)

    # ── Missing tick-data days ────────────────────────────────────────────────
    in_range_pre = results[(results["Date"] >= date_from) & (results["Date"] <= date_to)]
    _missing = (
        in_range_pre[in_range_pre["FilterStatus"] == "no_tick_data"]["Date"]
        .drop_duplicates()
        .sort_values()
    )
    if not _missing.empty:
        st.warning(
            f"⚠️ **{len(_missing)} trading day(s)** in the selected range have no tick data — "
            f"all signals on those days were excluded from the analysis."
        )
        with st.expander(f"Missing tick-data days ({len(_missing)})", expanded=False):
            st.dataframe(
                pd.DataFrame({"Date": _missing.values,
                              "Weekday": [pd.Timestamp(d).strftime("%A") for d in _missing.values]}),
                hide_index=True, use_container_width=True,
            )

    # ── Per-day chart ─────────────────────────────────────────────────────────
    in_range   = results[(results["Date"] >= date_from) & (results["Date"] <= date_to)]
    filled_all = in_range[in_range["Filled"]]

    with st.expander("📈 Daily Chart", expanded=False):
        _trade_filter = st.radio(
            "Show dates with:", ["All signals", "Winners only", "Losers only"],
            horizontal=True, key="ba_trade_filter",
        )

        if _trade_filter == "Winners only":
            _win_dates   = set(filled_all.loc[filled_all["ExitReason"] == "Target", "Date"])
            signal_dates = sorted(d for d in in_range["Date"].unique() if d in _win_dates)
        elif _trade_filter == "Losers only":
            _loss_dates  = set(filled_all.loc[filled_all["ExitReason"] == "Stop", "Date"])
            signal_dates = sorted(d for d in in_range["Date"].unique() if d in _loss_dates)
        else:
            signal_dates = sorted(in_range["Date"].unique())

        if not signal_dates:
            label = "winners" if _trade_filter == "Winners only" else "losers"
            st.info(f"No dates with {label} in the selected range.")
            return

        if st.session_state.get("_last_trade_filter") != _trade_filter:
            st.session_state["ba_chart_idx"] = len(signal_dates) - 1
            st.session_state["_last_trade_filter"] = _trade_filter

        if "ba_chart_idx" not in st.session_state:
            st.session_state["ba_chart_idx"] = len(signal_dates) - 1
        st.session_state["ba_chart_idx"] = min(st.session_state["ba_chart_idx"], len(signal_dates) - 1)

        cc1, cc2, cc3 = st.columns([1, 1, 14])
        if cc1.button("‹", key="ba_prev"):
            st.session_state["ba_chart_idx"] = max(0, st.session_state["ba_chart_idx"] - 1)
        if cc2.button("›", key="ba_next"):
            st.session_state["ba_chart_idx"] = min(len(signal_dates) - 1, st.session_state["ba_chart_idx"] + 1)

        selected_date = cc3.selectbox(
            "Date", options=signal_dates,
            index=st.session_state["ba_chart_idx"],
            format_func=lambda d: pd.Timestamp(d).strftime("%A %b %d, %Y"),
        )
        st.session_state["ba_chart_idx"] = list(signal_dates).index(selected_date)

        day_bars    = bars[bars["Date"] == selected_date].drop(columns="Date").reset_index(drop=True)
        day_results = results[results["Date"] == selected_date]

        if len(day_bars) < 81:
            first_bar_time = day_bars.iloc[0]["DateTime"].strftime("%H:%M") if not day_bars.empty else "?"
            st.warning(f"Incomplete data: {len(day_bars)} bars, starts {first_bar_time} (not 08:30). "
                       "Bar numbers reflect position from 08:30.")

        ctrl_l, ctrl_r = st.columns(2)
        show_bar_nums = ctrl_l.checkbox("Show bar numbers", value=False, key="ba_show_bar_nums")
        show_hover    = ctrl_r.checkbox("Show hover labels", value=True, key="ba_show_hover")

        if not day_bars.empty:
            fig = make_analysis_chart(
                day_bars, day_results,
                pd.Timestamp(selected_date).strftime("%B %d, %Y"),
                show_bar_nums=show_bar_nums,
                excl_first_n=excl_first_n,
                excl_last_min=excl_last_min,
                contract=contract,
                show_hover=show_hover,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No bar data for this date.")

    # ── Signal table for selected day ─────────────────────────────────────────
    with st.expander(f"Signal Table — {pd.Timestamp(selected_date).strftime('%b %d, %Y')}"
                     f"  ({len(day_results)} signals)", expanded=False):
        _show_signal_table(day_results.reset_index(drop=True), key_suffix="_day")

    # ── Full-range signal table ───────────────────────────────────────────────
    with st.expander(f"All Signals — {date_from} to {date_to}  ({len(in_range)} signals)", expanded=False):
        _show_signal_table(in_range.reset_index(drop=True), key_suffix="_all")

    # ── ER10 distribution ─────────────────────────────────────────────────────
    if "ER10" in results.columns:
        _filled = results[results["Filled"] == True]
        _er_vals = _filled["ER10"].dropna()
        if not _er_vals.empty:
            _n_nan = int(_filled["ER10"].isna().sum())
            _title = f"ER10 Distribution — {len(_er_vals)}/{len(_filled)} filled trades"
            if _n_nan > 0:
                _title += f" ({_n_nan} missing ER10)"
            with st.expander(_title, expanded=False):
                _bins = np.arange(0, 1.101, 0.10)
                _er_cut = pd.cut(_er_vals, bins=_bins, right=False)
                _counts = _er_cut.value_counts().sort_index()

                # Per-bucket performance
                _filled_er = _filled.dropna(subset=["ER10"]).copy()
                _filled_er["ER10_bin"] = pd.cut(_filled_er["ER10"], bins=_bins, right=False)
                _bkt = _filled_er.groupby("ER10_bin", observed=True).agg(
                    Trades=("NetPnL", "size"),
                    Net=("NetPnL", "sum"),
                    WinPct=("NetPnL", lambda x: (x > 0).mean() * 100),
                    AvgR=("R_achieved", "mean"),
                ).reset_index()
                _bkt["Exp"] = _bkt["Net"] / _bkt["Trades"]
                _bkt["ER10_bin"] = _bkt["ER10_bin"].astype(str)

                # Histogram colored by avg R (green = positive, red = negative)
                _colors = ["#22cc44" if r >= 0 else "#dd3344" for r in _bkt["AvgR"]]
                _hist_fig = go.Figure()
                _hist_fig.add_trace(go.Bar(
                    x=_bkt["ER10_bin"], y=_bkt["Trades"],
                    marker_color=_colors,
                    hovertemplate=(
                        "<b>%{x}</b><br>Trades: %{y}<br>"
                        "Exp: $%{customdata[0]:,.0f}<br>"
                        "Win: %{customdata[1]:.0f}%<br>"
                        "Avg R: %{customdata[2]:+.2f}<extra></extra>"
                    ),
                    customdata=np.column_stack([_bkt["Exp"], _bkt["WinPct"], _bkt["AvgR"]]),
                ))
                _hist_fig.update_layout(
                    template="plotly_dark", height=350,
                    title="ER10 at Signal — Filled Trade Distribution",
                    xaxis_title="ER10 Bucket", yaxis_title="Trade Count",
                    xaxis=dict(tickangle=-45),
                    margin=dict(t=40, b=80),
                )
                st.plotly_chart(_hist_fig, use_container_width=True)

                # Summary stats
                _sc1, _sc2, _sc3, _sc4 = st.columns(4)
                _sc1.metric("Median ER10", f"{_er_vals.median():.2f}")
                _sc2.metric("Mean ER10", f"{_er_vals.mean():.2f}")
                _sc3.metric("< 0.30", f"{(_er_vals < 0.30).sum()} ({(_er_vals < 0.30).mean()*100:.0f}%)")
                _sc4.metric("> 0.70", f"{(_er_vals > 0.70).sum()} ({(_er_vals > 0.70).mean()*100:.0f}%)")

                # Bucket table
                _bkt_disp = _bkt.copy()
                _bkt_disp.columns = ["ER10 Bucket", "Trades", "Net $", "Win %", "Avg R", "Exp $"]
                _bkt_disp["Net $"] = _bkt_disp["Net $"].map(lambda v: f"${v:+,.0f}")
                _bkt_disp["Win %"] = _bkt_disp["Win %"].map(lambda v: f"{v:.0f}%")
                _bkt_disp["Avg R"] = _bkt_disp["Avg R"].map(lambda v: f"{v:+.3f}")
                _bkt_disp["Exp $"] = _bkt_disp["Exp $"].map(lambda v: f"${v:+,.0f}")
                st.dataframe(_bkt_disp, use_container_width=True, hide_index=True)

                # Cumulative threshold table — "if ER10 >= X, what do you get?"
                st.subheader("ER10 Threshold Analysis")
                _thresholds = np.arange(0, 1.01, 0.10)
                _thresh_rows = []
                for _t in _thresholds:
                    _sub = _filled_er[_filled_er["ER10"] >= _t]
                    if _sub.empty:
                        continue
                    _n = len(_sub)
                    _net = _sub["NetPnL"].sum()
                    _win = (_sub["NetPnL"] > 0).mean() * 100
                    _gross_w = _sub.loc[_sub["GrossPnL"] > 0, "GrossPnL"].sum()
                    _gross_l = abs(_sub.loc[_sub["GrossPnL"] <= 0, "GrossPnL"].sum())
                    _pf = _gross_w / _gross_l if _gross_l > 0 else float("inf")
                    _expr = _sub["R_achieved"].mean()
                    _eq = _sub["NetPnL"].cumsum()
                    _dd = (_eq - _eq.cummax()).min()
                    _thresh_rows.append({
                        "ER10 ≥": f"{_t:.1f}",
                        "Trades": _n,
                        "Win %": f"{_win:.1f}%",
                        "PF": f"{_pf:.2f}" if _pf < 99 else "∞",
                        "Exp R": f"{_expr:+.3f}",
                        "Net $": f"${_net:+,.0f}",
                        "Max DD": f"${_dd:+,.0f}",
                    })
                if _thresh_rows:
                    st.dataframe(pd.DataFrame(_thresh_rows), use_container_width=True, hide_index=True)

    # ── Entry zoom ────────────────────────────────────────────────────────────
    _show_entry_zoom_section(results, ticks_by_date)

    # ── Bar data mismatch analysis ────────────────────────────────────────────
    if nt_bars is not None and not nt_bars.empty:
        st.markdown("---")
        with st.expander("🔍 Bar Data Mismatch Analysis", expanded=False):
            _show_mismatch_analysis(results, bars, nt_bars)
