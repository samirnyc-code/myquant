import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

from data_loader import load_sc_bars, load_sc_ticks, get_market_holidays, TICK_SIZE, bar_num_from_dt
from economic_calendar import get_economic_events, fred_key_configured, EVENT_COLOR

_BA_DEFAULTS_FILE = Path(__file__).parent / "ba_filter_defaults.json"

INSTRUMENTS = {
    "ES":  {"tick_value": 12.50, "label": "ES  ($12.50/tick)"},
    "MES": {"tick_value":  1.25, "label": "MES ($1.25/tick)"},
}
RTH_END_MIN = 15 * 60 + 15  # 915


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
    incl_cc3: bool,
    incl_cc4: bool,
    first_trade_only: bool,
) -> pd.DataFrame:
    df = signals.copy()
    df["FilterStatus"] = "ok"

    # Date range
    df.loc[(df["Date"] < date_from) | (df["Date"] > date_to), "FilterStatus"] = "date_range"

    # Signal type
    for stype, incl in [("CC3", incl_cc3), ("CC4", incl_cc4)]:
        if not incl:
            df.loc[(df["FilterStatus"] == "ok") & (df["SignalType"] == stype),
                   "FilterStatus"] = "signal_type"

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

    # First trade of day (applied after all other signal filters)
    if first_trade_only:
        ok_first    = df[df["FilterStatus"] == "ok"].sort_values("SignalNum").groupby("Date").head(1).index
        non_first   = df[(df["FilterStatus"] == "ok") & ~df.index.isin(ok_first)].index
        df.loc[non_first, "FilterStatus"] = "first_trade_day"

    return df


# ── Trade simulation ──────────────────────────────────────────────────────────

# bar_num_from_dt imported from data_loader — shared with app.py


def _simulate_one(
    sig_dt, direction: str, signal_price: float, stop_csv: float,
    day_ticks: pd.DataFrame,
    target_r: float, entry_slip: int, exit_slip: int, stop_offset: int, tv: float,
) -> dict:
    ts      = TICK_SIZE
    is_long = direction == "Long"

    # Ticks strictly after signal bar close
    after = day_ticks[day_ticks["DateTime"] > sig_dt]
    if after.empty:
        return {"ok": False, "FilterStatus": "no_next_bar"}

    first_tick      = after.iloc[0]
    first_tick_px   = first_tick["Price"]

    # Fill condition: first tick must be at/through signal price (stop order)
    if is_long  and first_tick_px < signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}
    if not is_long and first_tick_px > signal_price:
        return {"ok": False, "FilterStatus": "no_fill"}

    # Actual entry = first tick price ± entry slippage
    actual_entry = first_tick_px + (entry_slip * ts if is_long else -entry_slip * ts)

    # Actual stop = CSV stop ± stop_offset ticks (one extra tick beyond level)
    actual_stop = (stop_csv - stop_offset * ts) if is_long else (stop_csv + stop_offset * ts)

    risk_pts = abs(actual_entry - actual_stop)
    if risk_pts < 0.001:
        return {"ok": False, "FilterStatus": "zero_risk"}

    target_price = actual_entry + (target_r * risk_pts if is_long else -target_r * risk_pts)
    entry_dt     = first_tick["DateTime"]
    entry_bar    = bar_num_from_dt(entry_dt)

    # Scan for exit + MAE/MFE
    prices = after["Price"].values
    times  = after["DateTime"].values

    exit_px_raw  = float(prices[-1])
    exit_dt_raw  = times[-1]
    exit_reason  = "Session"
    mae = mfe = 0.0

    for i, (p, t) in enumerate(zip(prices, times)):
        excursion = (p - actual_entry) if is_long else (actual_entry - p)
        mfe = max(mfe, excursion)
        mae = max(mae, -excursion)

        if i == 0:
            continue  # entry tick — no exit check on entry itself

        if is_long:
            if p >= target_price:
                exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                break
            if p <= actual_stop:
                exit_px_raw, exit_dt_raw, exit_reason = actual_stop, t, "Stop"
                break
        else:
            if p <= target_price:
                exit_px_raw, exit_dt_raw, exit_reason = target_price, t, "Target"
                break
            if p >= actual_stop:
                exit_px_raw, exit_dt_raw, exit_reason = actual_stop, t, "Stop"
                break

    # Exit fill = theoretical exit ± exit slippage (always adverse)
    actual_exit  = exit_px_raw + (-exit_slip * ts if is_long else exit_slip * ts)
    exit_dt_ts   = pd.Timestamp(exit_dt_raw)
    exit_bar     = bar_num_from_dt(exit_dt_ts)

    gross_pts = (actual_exit - actual_entry) if is_long else (actual_entry - actual_exit)
    gross_pnl = gross_pts / ts * tv
    r_achieved = gross_pts / risk_pts

    exit_label = "EOD" if exit_reason == "Session" else exit_reason

    return {
        "ok":          True,
        "SEPrice":     signal_price,          # stop-entry level (signal bar close)
        "FillPrice":   first_tick_px,         # first qualifying tick, pre-slippage
        "EntryTime":   pd.Timestamp(entry_dt),
        "EntryBarNum": entry_bar,
        "EntryPrice":  actual_entry,          # fill price ± entry slippage
        "ActualStop":  actual_stop,
        "Target":      target_price,
        "RiskPts":     risk_pts,
        "RiskDollar":  risk_pts / ts * tv,
        "ExitTime":    exit_dt_ts,
        "ExitBarNum":  exit_bar,
        "ExitPrice":   actual_exit,
        "ExitReason":  exit_label,
        "GrossPnLPts": gross_pts,
        "GrossPnL":    gross_pnl,
        "R_achieved":  r_achieved,
        "MAE_pts":     mae,
        "MAE_dollar":  mae / ts * tv,
        "MAE_R":       mae / risk_pts,
        "MFE_pts":     mfe,
        "MFE_dollar":  mfe / ts * tv,
        "MFE_R":       mfe / risk_pts,
    }


_EMPTY_TRADE = {
    "Filled": False,
    "SEPrice": np.nan, "FillPrice": np.nan,
    "EntryTime": pd.NaT, "EntryBarNum": np.nan,
    "EntryPrice": np.nan, "ActualStop": np.nan, "Target": np.nan,
    "RiskPts": np.nan, "RiskDollar": np.nan,
    "ExitTime": pd.NaT, "ExitBarNum": np.nan,
    "ExitPrice": np.nan, "ExitReason": "",
    "GrossPnLPts": np.nan, "GrossPnL": np.nan, "NetPnL": np.nan,
    "R_achieved": np.nan,
    "MAE_pts": np.nan, "MAE_dollar": np.nan, "MAE_R": np.nan,
    "MFE_pts": np.nan, "MFE_dollar": np.nan, "MFE_R": np.nan,
    "CumPF": np.nan,
}


def simulate_trades(
    signals: pd.DataFrame,
    ticks_by_date: dict,
    target_r: float,
    entry_slip: int,
    exit_slip: int,
    stop_offset: int,
    tick_value: float,
    contracts: int,
    commission: float,
) -> pd.DataFrame:
    tv   = tick_value * contracts
    rows = []

    for _, sig in signals.iterrows():
        base = sig.to_dict()
        base["TargetR"] = target_r
        base.update(_EMPTY_TRADE)
        base["FilterStatus"] = sig.get("FilterStatus", "ok")  # restore after update

        if base["FilterStatus"] != "ok":
            rows.append(base)
            continue

        day_ticks = ticks_by_date.get(base["Date"])
        if day_ticks is None or day_ticks.empty:
            base["FilterStatus"] = "no_tick_data"
            rows.append(base)
            continue

        res = _simulate_one(
            base["DateTime"], base["Direction"], base["SignalPrice"], base["StopPrice"],
            day_ticks, target_r, entry_slip, exit_slip, stop_offset, tv,
        )

        if not res.get("ok", False):
            base["FilterStatus"] = res.get("FilterStatus", "no_fill")
            rows.append(base)
            continue

        # Merge simulation result into base row
        for k, v in res.items():
            if k != "ok":
                base[k] = v
        base["Filled"]  = True
        base["NetPnL"]  = base["GrossPnL"] - commission
        rows.append(base)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Cumulative PF column (over filled trades sorted by date/time)
    filled_mask = df["Filled"] == True
    df["CumPF"]  = np.nan
    if filled_mask.any():
        g_pnl     = df.loc[filled_mask, "GrossPnL"]
        cum_wins  = g_pnl.clip(lower=0).cumsum()
        cum_loss  = g_pnl.clip(upper=0).cumsum().abs()
        df.loc[filled_mask, "CumPF"] = (cum_wins / cum_loss.replace(0, np.nan)).values

    return df


# ── Summary metrics ───────────────────────────────────────────────────────────

def compute_summary(results: pd.DataFrame, commission: float) -> dict:
    if results.empty:
        return {}
    filled = results[results["Filled"] == True]
    if filled.empty:
        return {}

    n_total    = len(results)
    n_filtered = int((results["FilterStatus"] != "ok").sum())
    n_no_fill  = int(results["FilterStatus"].isin(
        ["no_fill", "no_next_bar", "no_tick_data", "zero_risk"]).sum())
    n_trades   = len(filled)

    wins   = filled[filled["ExitReason"] == "Target"]
    stops  = filled[filled["ExitReason"] == "Stop"]
    sess   = filled[filled["ExitReason"] == "Session"]
    n_wins = len(wins)
    n_stop = len(stops)
    n_sess = len(sess)
    win_pct = n_wins / n_trades * 100 if n_trades else 0

    gross_total = filled["GrossPnL"].sum()
    net_total   = filled["NetPnL"].sum()

    # PF based on all outcomes (positive / |negative|)
    pos_pnl = filled.loc[filled["GrossPnL"] > 0, "GrossPnL"].sum()
    neg_pnl = filled.loc[filled["GrossPnL"] < 0, "GrossPnL"].sum()
    pf = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else (float("inf") if pos_pnl > 0 else 0)

    exp_dollar = filled["NetPnL"].mean()
    exp_r      = filled["R_achieved"].mean()
    avg_win    = wins["NetPnL"].mean()   if n_wins else 0
    avg_loss   = stops["NetPnL"].mean()  if n_stop else 0
    wl_ratio   = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

    return dict(
        n_total=n_total, n_filtered=n_filtered, n_no_fill=n_no_fill,
        n_trades=n_trades, n_wins=n_wins, n_stop=n_stop, n_sess=n_sess,
        win_pct=win_pct, gross_total=gross_total, net_total=net_total,
        pf=pf, exp_dollar=exp_dollar, exp_r=exp_r,
        avg_win=avg_win, avg_loss=avg_loss, wl_ratio=wl_ratio,
        avg_mae_pts=filled["MAE_pts"].mean(), avg_mfe_pts=filled["MFE_pts"].mean(),
        avg_mae_R=filled["MAE_R"].mean(),     avg_mfe_R=filled["MFE_R"].mean(),
        largest_win=wins["NetPnL"].max()    if n_wins else 0,
        largest_loss=stops["NetPnL"].min()  if n_stop else 0,
        commission_total=n_trades * commission,
    )


# ── Chart ─────────────────────────────────────────────────────────────────────

def _outcome_color(exit_reason: str) -> str:
    return {"Target": "#26a69a", "Stop": "#ef5350"}.get(exit_reason, "#9e9e9e")


def make_analysis_chart(
    day_bars: pd.DataFrame,
    day_results: pd.DataFrame,
    date_str: str,
    show_bar_nums: bool = False,
    excl_first_n: int = 0,
    excl_last_min: int = 0,
    contract: str = "ES",
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

            marker_y = (bar_row["Low"] - marker_offset) if is_long else (bar_row["High"] + marker_offset)
            msym     = "triangle-up" if is_long else "triangle-down"
            mcolor   = "#26a69a" if (is_long and not filtered) else ("#ef5350" if (not is_long and not filtered) else "#bdbdbd")

            htxt = (
                f"Signal #{int(row['SignalNum'])} {row['SignalType']} {row['Direction']}<br>"
                f"Bar: {int(row['BarNum'])} | {sig_dt.strftime('%H:%M')}<br>"
                f"Signal Price: {row['SignalPrice']:.2f} | Stop: {row['StopPrice']:.2f}<br>"
                f"Status: {row['FilterStatus']}"
            )
            fig.add_trace(go.Scatter(
                x=[bar_open], y=[marker_y], mode="markers",
                marker=dict(symbol=msym, size=12, color=mcolor,
                            line=dict(width=1, color="white")),
                hovertext=htxt, hoverinfo="text", showlegend=False,
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

            for p in [entry_px, stop_px, target_px, exit_px]:
                if pd.notna(p):
                    y_prices.append(p)

            # Entry hover marker
            entry_htxt = (
                f"ENTRY #{int(row['SignalNum'])}<br>"
                f"Time: {pd.Timestamp(entry_dt).strftime('%H:%M:%S')} | Bar {int(row['EntryBarNum'])}<br>"
                f"Price: {entry_px:.2f}<br>"
                f"Stop: {stop_px:.2f} | Target: {target_px:.2f}<br>"
                f"Risk: {row['RiskPts']:.2f} pts (${row['RiskDollar']:.0f})"
            )
            fig.add_trace(go.Scatter(
                x=[pd.Timestamp(entry_dt)], y=[entry_px], mode="markers",
                marker=dict(symbol="circle-open", size=9, color=oc, line=dict(width=2)),
                hovertext=entry_htxt, hoverinfo="text", showlegend=False,
            ))

            # Exit hover marker
            exit_htxt = (
                f"EXIT #{int(row['SignalNum'])}  ({reason})<br>"
                f"Time: {pd.Timestamp(exit_dt).strftime('%H:%M:%S')} | Bar {int(row['ExitBarNum'])}<br>"
                f"Price: {exit_px:.2f}<br>"
                f"Gross: {sign}{gross_pts:.2f} pts | Net: {sign}${net_pnl:.0f}<br>"
                f"R: {row['R_achieved']:+.2f}<br>"
                f"MAE: {row['MAE_pts']:.2f} pts | MFE: {row['MFE_pts']:.2f} pts"
            )
            fig.add_trace(go.Scatter(
                x=[pd.Timestamp(exit_dt)], y=[exit_px], mode="markers",
                marker=dict(symbol="x", size=9, color=oc, line=dict(width=2)),
                hovertext=exit_htxt, hoverinfo="text", showlegend=False,
            ))

            xref, yref = "x", "y"

            # Stop line (dashed red)
            fig.add_shape(type="line",
                x0=pd.Timestamp(entry_dt), x1=pd.Timestamp(exit_dt),
                y0=stop_px, y1=stop_px,
                line=dict(color="#ef5350", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # Target line (dashed teal)
            fig.add_shape(type="line",
                x0=pd.Timestamp(entry_dt), x1=pd.Timestamp(exit_dt),
                y0=target_px, y1=target_px,
                line=dict(color="#26a69a", width=1.2, dash="dash"),
                xref=xref, yref=yref)

            # BE line (orange) = entry price
            fig.add_shape(type="line",
                x0=pd.Timestamp(entry_dt), x1=pd.Timestamp(exit_dt),
                y0=entry_px, y1=entry_px,
                line=dict(color="#ff9800", width=1.0),
                xref=xref, yref=yref)

            # Dotted diagonal: entry price → exit price
            fig.add_shape(type="line",
                x0=pd.Timestamp(entry_dt), x1=pd.Timestamp(exit_dt),
                y0=entry_px, y1=exit_px,
                line=dict(color=oc, width=1.5, dash="dot"),
                xref=xref, yref=yref)

            # PnL annotation at exit point — offset above/below, larger font
            day_range = df["High"].max() - df["Low"].min()
            y_offset  = day_range * 0.012 * (1 if is_long else -1)
            fig.add_annotation(
                x=pd.Timestamp(exit_dt), y=exit_px + y_offset,
                xshift=10, yshift=0,
                text=f"<b>#{int(row['SignalNum'])} {sign}{gross_pts:.2f}pt | {sign}${net_pnl:.0f}</b>",
                showarrow=True, arrowhead=0, arrowcolor=oc, arrowwidth=1,
                ax=20, ay=-30 if is_long else 30,
                xanchor="left",
                font=dict(size=12, color=oc),
                bgcolor="rgba(30,30,30,0.80)",
                bordercolor=oc, borderwidth=1, borderpad=4,
            )

    # Y-range with padding
    if y_prices:
        y_lo, y_hi = min(y_prices), max(y_prices)
        pad = (y_hi - y_lo) * 0.06
        fig.update_layout(yaxis=dict(range=[y_lo - pad, y_hi + pad]))

    fig.update_layout(
        title=f"{contract} — Bar Analysis  ({date_str})",
        xaxis_title="Time (CT)", yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
        height=560,
        margin=dict(l=50, r=20, t=60, b=60),
        template="plotly_white",
    )
    return fig


# ── Signal table ──────────────────────────────────────────────────────────────

_STATUS_LABELS = {
    "ok":             "Filtered",    # shouldn't appear if not filled
    "date_range":     "Date range",
    "signal_type":    "Signal type",
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

    col_groups = st.multiselect(
        "Column groups",
        ["Core", "Entry/Exit", "P&L", "Risk & R", "MAE/MFE"],
        default=["Core", "Entry/Exit", "P&L", "Risk & R"],
        key=f"ba_col_groups{key_suffix}",
    )

    cols = []
    if "Core" in col_groups:
        cols += ["#", "Type", "Dir", "Date", "Sig Time", "Sig Bar", "Status"]
    if "Entry/Exit" in col_groups:
        cols += ["SE Px", "Fill Px", "Entry Time", "Entry Bar", "Entry Px", "Stop", "Target",
                 "Exit Time", "Exit Bar", "Exit Px", "Exit Type"]
    if "P&L" in col_groups:
        cols += ["Gross$", "Net$", "Cum PF"]
    if "Risk & R" in col_groups:
        cols += ["Risk$", "Target R", "R"]
    if "MAE/MFE" in col_groups:
        cols += ["MAE pts", "MAE$", "MAE R", "MFE pts", "MFE$", "MFE R"]

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
    disp["SE Px"]      = results["SEPrice"].apply(fmt_f)
    disp["Fill Px"]    = results["FillPrice"].apply(fmt_f)
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
    disp["Target R"]   = results["TargetR"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    disp["R"]          = results["R_achieved"].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")
    disp["MAE pts"]    = results["MAE_pts"].apply(fmt_f)
    disp["MAE$"]       = results["MAE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MAE R"]      = results["MAE_R"].apply(fmt_f)
    disp["MFE pts"]    = results["MFE_pts"].apply(fmt_f)
    disp["MFE$"]       = results["MFE_dollar"].apply(lambda v: f"${v:.0f}" if pd.notna(v) else "—")
    disp["MFE R"]      = results["MFE_R"].apply(fmt_f)

    # Filter to selected column groups
    visible = [c for c in cols if c in disp.columns]
    disp    = disp[visible]

    st.dataframe(disp, use_container_width=True, hide_index=True,
                 height=min(35 * len(disp) + 38, 600))
    st.caption(f"{len(results)} signals  |  {int(results['Filled'].sum())} filled trades")


# ── Optimal R sweep ───────────────────────────────────────────────────────────

def _run_r_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: int, exit_slip: int, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
) -> pd.DataFrame:
    r_values = [round(r * 0.25, 2) for r in range(2, 21)]  # 0.50 – 5.00
    rows = []
    for r in r_values:
        res = simulate_trades(signals, ticks_by_date, r,
                               entry_slip, exit_slip, stop_offset,
                               tick_value, contracts, commission)
        s = compute_summary(res, commission)
        if not s or s["n_trades"] == 0:
            continue
        rows.append({
            "R":        r,
            "Trades":   s["n_trades"],
            "Win %":    round(s["win_pct"], 1),
            "PF":       round(s["pf"], 2) if s["pf"] < 99 else 99.9,
            "Exp $":    round(s["exp_dollar"], 0),
            "Exp R":    round(s["exp_r"], 3),
            "Net PnL":  round(s["net_total"], 0),
            "Avg Win":  round(s["avg_win"], 0),
            "Avg Loss": round(s["avg_loss"], 0),
        })
    return pd.DataFrame(rows)


def _show_optimal_r(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                    tick_value, contracts, commission):
    with st.expander("🔍 Optimal R Sweep (0.50 – 5.00)"):
        st.caption("Runs simulation at every R from 0.50 to 5.00 in 0.25 steps. "
                   "Highlights best value per metric.")
        if st.button("Run R Sweep", key="ba_run_sweep"):
            with st.spinner("Running sweep…"):
                sweep_df = _run_r_sweep(signals, ticks_by_date, entry_slip, exit_slip,
                                         stop_offset, tick_value, contracts, commission)
            if sweep_df.empty:
                st.warning("No results.")
                return
            st.session_state["ba_sweep_df"] = sweep_df

        sweep_df = st.session_state.get("ba_sweep_df")
        if sweep_df is None or sweep_df.empty:
            return

        # Highlight max per metric column (except R, Trades)
        metric_cols = ["Win %", "PF", "Exp $", "Exp R", "Net PnL", "Avg Win"]

        def highlight_max(s):
            is_max = s == s.max()
            return ["font-weight: bold; color: #ffd700; border: 1px solid #ffd700"
                    if v else "" for v in is_max]

        fmt_map = {c: "{:.2f}" for c in ["Win %", "PF", "Exp R"]}
        fmt_map.update({c: "{:.0f}" for c in ["Exp $", "Net PnL", "Avg Win", "Avg Loss"]})
        styled = sweep_df.style.apply(highlight_max, subset=metric_cols).format(fmt_map)
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Line chart: Net PnL and PF vs R
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


# ── Mismatch analysis ─────────────────────────────────────────────────────────

def _show_mismatch_analysis(results: pd.DataFrame, sc_bars: pd.DataFrame, nt_bars: pd.DataFrame):
    from validation import build_comparison

    st.markdown("---")
    st.subheader("🔍 Bar Data Mismatch Analysis")

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

    with st.expander(f"Mismatched signals — detail ({n_mismatch})", expanded=True):
        disp = pd.DataFrame()
        disp["Date"]      = mismatched["Date"].astype(str)
        disp["Bar"]       = mismatched["BarNum"].astype(int)
        disp["Dir"]       = mismatched["Direction"]
        disp["Sig Px"]    = mismatched["SignalPrice"].round(2)
        disp["Entry Px"]  = mismatched["EntryPrice"].round(2)
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


# ── Main tab ──────────────────────────────────────────────────────────────────

def show_bar_analysis(sc_file: str = "", contract: str = "ES", nt_file: str = ""):
    # ── CSV Upload ────────────────────────────────────────────────────────────
    uploaded = st.file_uploader(
        "Upload MC Signals CSV", type=["txt", "csv"],
        help="Space-delimited: Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop",
        key="ba_file",
    )
    if uploaded is not None:
        raw = uploaded.read().decode("utf-8", errors="replace")
        signals_parsed = parse_signals(raw)
        if signals_parsed is None or signals_parsed.empty:
            st.error("Could not parse signals from uploaded file.")
            return
        st.session_state["ba_signals"] = signals_parsed
        st.success(f"Loaded {len(signals_parsed)} signals.", icon="✅")

    signals_raw = st.session_state.get("ba_signals")
    if signals_raw is None:
        st.info("Upload a signals file above to begin.")
        return

    # ── Load data (prefer uploaded files) ────────────────────────────────────
    uploaded_bars  = st.session_state.get("uploaded_sc_bars")
    uploaded_ticks = st.session_state.get("uploaded_sc_ticks")

    bars  = uploaded_bars  if uploaded_bars  is not None else (load_sc_bars(sc_file)  if sc_file else load_sc_bars())
    ticks = uploaded_ticks if uploaded_ticks is not None else (load_sc_ticks(sc_file) if sc_file else load_sc_ticks())

    # NT bars for mismatch analysis (uploaded OHLC wins over disk file)
    _uploaded_ohlc = st.session_state.get("uploaded_ohlc_bars")
    if _uploaded_ohlc is not None:
        nt_bars = _uploaded_ohlc
    elif nt_file:
        from data_loader import load_nt_bars
        nt_bars = load_nt_bars(nt_file)
    else:
        nt_bars = None

    # Cache key: uploaded data uses upload-key suffix so switching files busts the cache
    _up_key = st.session_state.get("uploaded_sc_key", "")
    tbd_key = (f"ba_ticks_by_date__up_{_up_key}"
               if uploaded_ticks is not None
               else f"ba_ticks_by_date_{sc_file}")
    if tbd_key not in st.session_state:
        st.session_state[tbd_key] = {
            d: grp.reset_index(drop=True)
            for d, grp in ticks.groupby(ticks["DateTime"].dt.date)
        }
    ticks_by_date = st.session_state[tbd_key]

    bars["Date"] = bars["DateTime"].dt.date
    bar_dates    = sorted(bars["Date"].unique())
    sig_min      = signals_raw["Date"].min()
    sig_max      = signals_raw["Date"].max()
    data_min     = bars["Date"].min()
    data_max     = bars["Date"].max()

    # ── Detect data change (contract switch OR new upload) — reset stale date state ──
    _active_key = f"{sc_file}|{st.session_state.get('uploaded_sc_key', '')}"
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
    date_from = dc1.date_input("From", value=max(sig_min, data_min),
                                min_value=data_min, max_value=data_max, key="ba_date_from")
    date_to   = dc2.date_input("To",   value=min(sig_max, data_max),
                                min_value=data_min, max_value=data_max, key="ba_date_to")

    # ── Filters expander ──────────────────────────────────────────────────────
    with st.expander("⚙️ Filters & Trading Parameters", expanded=False):
        st.markdown("**Signals**")
        sc1, sc2, sc3 = st.columns(3)
        incl_cc3 = sc1.checkbox("CC3", key="ba_incl_cc3",
                                  value=st.session_state.get("ba_incl_cc3", True))
        incl_cc4 = sc2.checkbox("CC4", key="ba_incl_cc4",
                                  value=st.session_state.get("ba_incl_cc4", True))
        first_trade_only = sc3.checkbox("First trade of day only", key="ba_first_trade",
                                         value=st.session_state.get("ba_first_trade", False))

        st.divider()
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
                                    st.session_state.get("ba_excl_last_min", 0), 5,
                                    key="ba_excl_last_min")

        st.divider()
        st.markdown("**Economic Events**")
        if not fred_key_configured():
            st.info("FOMC built-in. Add FRED_API_KEY to .streamlit/secrets.toml for NFP/CPI.")
        ea, eb, ec = st.columns(3)
        use_fomc = ea.checkbox("FOMC", key="ba_fomc", value=st.session_state.get("ba_fomc", False))
        use_nfp  = eb.checkbox("NFP",  key="ba_nfp",  value=st.session_state.get("ba_nfp",  False),
                                disabled=not fred_key_configured())
        use_cpi  = ec.checkbox("CPI",  key="ba_cpi",  value=st.session_state.get("ba_cpi",  False),
                                disabled=not fred_key_configured())
        event_types = tuple(e for e, on in [("FOMC", use_fomc), ("NFP", use_nfp), ("CPI", use_cpi)] if on)

        ef1, ef2 = st.columns([1, 2])
        _efm_default = st.session_state.get("ba_event_mode", "Skip full day")
        event_filter_mode = ef1.radio(
            "Filter mode", ["Skip full day", "Window ±N minutes"],
            index=["Skip full day", "Window ±N minutes"].index(_efm_default),
            key="ba_event_mode",
        )
        event_window = 30
        if event_filter_mode == "Window ±N minutes":
            event_window = ef2.slider("Minutes before/after", 15, 180,
                                       st.session_state.get("ba_event_window", 30), 15,
                                       key="ba_event_window")

        st.divider()
        st.markdown("**Instrument & Sizing**")
        ia, ib, ic = st.columns(3)
        instrument  = ia.selectbox("Instrument", list(INSTRUMENTS.keys()),
                                    index=list(INSTRUMENTS.keys()).index(
                                        st.session_state.get("ba_instrument", "ES")),
                                    key="ba_instrument",
                                    format_func=lambda k: INSTRUMENTS[k]["label"])
        contracts   = ib.number_input("Contracts", min_value=1, max_value=100,
                                       value=int(st.session_state.get("ba_contracts", 1)),
                                       key="ba_contracts")
        commission  = ic.number_input("Round-trip commission ($)", min_value=0.0,
                                       value=float(st.session_state.get("ba_commission", 4.0)),
                                       step=0.5, format="%.2f", key="ba_commission")

        tick_value = INSTRUMENTS[instrument]["tick_value"]

        st.markdown("**Execution Parameters**")
        ep1, ep2, ep3, ep4 = st.columns(4)
        entry_slip  = ep1.number_input("Entry slip (ticks)",  0, 10,
                                        int(st.session_state.get("ba_entry_slip", 0)),
                                        key="ba_entry_slip")
        exit_slip   = ep2.number_input("Exit slip (ticks)",   0, 10,
                                        int(st.session_state.get("ba_exit_slip",  0)),
                                        key="ba_exit_slip")
        stop_offset = ep3.number_input("Stop offset (ticks)", 0, 10,
                                        int(st.session_state.get("ba_stop_offset", 1)),
                                        key="ba_stop_offset")
        target_r    = ep4.number_input("Target R", 0.25, 10.0,
                                        float(st.session_state.get("ba_target_r", 2.0)),
                                        step=0.25, format="%.2f", key="ba_target_r")

        st.divider()
        if st.button("💾 Save as Default", key="ba_save_defaults"):
            _save_ba_defaults({
                "ba_incl_cc3": incl_cc3, "ba_incl_cc4": incl_cc4,
                "ba_first_trade": first_trade_only,
                "ba_excl_holidays": excl_holidays,
                "ba_mon": incl_mon, "ba_tue": incl_tue, "ba_wed": incl_wed,
                "ba_thu": incl_thu, "ba_fri": incl_fri,
                "ba_excl_first_n": excl_first_n, "ba_excl_last_min": excl_last_min,
                "ba_fomc": use_fomc, "ba_nfp": use_nfp, "ba_cpi": use_cpi,
                "ba_event_mode": event_filter_mode, "ba_event_window": event_window,
                "ba_instrument": instrument, "ba_contracts": contracts,
                "ba_commission": commission, "ba_entry_slip": entry_slip,
                "ba_exit_slip": exit_slip, "ba_stop_offset": stop_offset,
                "ba_target_r": target_r,
            })
            st.success("Defaults saved.", icon="✅")

    # ── Apply filters & simulate ──────────────────────────────────────────────
    filtered_signals = apply_signal_filters(
        signals_raw, date_from, date_to, excl_holidays,
        [incl_mon, incl_tue, incl_wed, incl_thu, incl_fri],
        excl_first_n, excl_last_min,
        event_types, event_filter_mode, event_window,
        incl_cc3, incl_cc4, first_trade_only,
    )

    results = simulate_trades(
        filtered_signals, ticks_by_date, target_r,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
    )

    # When first_trade_only is active, drop non-first-trade signals from all display/metrics
    if first_trade_only:
        results = results[results["FilterStatus"] != "first_trade_day"].reset_index(drop=True)

    summary = compute_summary(results, commission)

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.subheader("Summary")
    if summary:
        r1 = st.columns(6)
        r1[0].metric("Signals",      f"{summary['n_total']}")
        r1[1].metric("Filtered Out", f"{summary['n_filtered']}")
        r1[2].metric("Trades Taken", f"{summary['n_trades']}")
        r1[3].metric("Win %",        f"{summary['win_pct']:.1f}%",
                     help=f"W{summary['n_wins']} / L{summary['n_stop']} / S{summary['n_sess']}")
        r1[4].metric("Gross PnL",    f"${summary['gross_total']:,.0f}")
        r1[5].metric("Net PnL",      f"${summary['net_total']:,.0f}")

        r2 = st.columns(6)
        pf_str = f"{summary['pf']:.2f}" if summary['pf'] < 99 else "∞"
        r2[0].metric("Profit Factor", pf_str)
        r2[1].metric("Exp $",         f"${summary['exp_dollar']:+.0f}")
        r2[2].metric("Exp R",         f"{summary['exp_r']:+.3f}")
        r2[3].metric("Avg Win",       f"${summary['avg_win']:+.0f}")
        r2[4].metric("Avg Loss",      f"${summary['avg_loss']:+.0f}")
        r2[5].metric("W/L Ratio",
                     f"{summary['wl_ratio']:.2f}" if summary['wl_ratio'] < 99 else "∞")

        r3 = st.columns(6)
        r3[0].metric("Avg MAE",      f"{summary['avg_mae_pts']:.2f} pts")
        r3[1].metric("Avg MFE",      f"{summary['avg_mfe_pts']:.2f} pts")
        r3[2].metric("MAE R",        f"{summary['avg_mae_R']:.2f}")
        r3[3].metric("MFE R",        f"{summary['avg_mfe_R']:.2f}")
        r3[4].metric("Largest Win",  f"${summary['largest_win']:+.0f}")
        r3[5].metric("Largest Loss", f"${summary['largest_loss']:+.0f}")
    else:
        st.info("No filled trades in the selected range.")

    # ── Per-day chart ─────────────────────────────────────────────────────────
    st.subheader("Daily Chart")

    # Date selector — dates with at least one signal in range
    in_range = results[(results["Date"] >= date_from) & (results["Date"] <= date_to)]
    signal_dates = sorted(in_range["Date"].unique())

    if not signal_dates:
        st.info("No signals in selected date range.")
        return

    if "ba_chart_idx" not in st.session_state:
        st.session_state["ba_chart_idx"] = len(signal_dates) - 1
    st.session_state["ba_chart_idx"] = min(st.session_state["ba_chart_idx"], len(signal_dates) - 1)

    cc1, cc2, cc3 = st.columns([1, 1, 14])
    if cc1.button("‹", key="ba_prev"):
        st.session_state["ba_chart_idx"] = max(0, st.session_state["ba_chart_idx"] - 1)
    if cc2.button("›", key="ba_next"):
        st.session_state["ba_chart_idx"] = min(len(signal_dates) - 1, st.session_state["ba_chart_idx"] + 1)

    # No key on the selectbox — index parameter drives it; buttons update ba_chart_idx
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

    show_bar_nums = st.checkbox("Show bar numbers", value=False, key="ba_show_bar_nums")

    if not day_bars.empty:
        fig = make_analysis_chart(
            day_bars, day_results,
            pd.Timestamp(selected_date).strftime("%B %d, %Y"),
            show_bar_nums=show_bar_nums,
            excl_first_n=excl_first_n,
            excl_last_min=excl_last_min,
            contract=contract,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No bar data for this date.")

    # ── Signal table for selected day ─────────────────────────────────────────
    with st.expander(f"Signal Table — {pd.Timestamp(selected_date).strftime('%b %d, %Y')}"
                     f"  ({len(day_results)} signals)", expanded=True):
        _show_signal_table(day_results.reset_index(drop=True), key_suffix="_day")

    # ── Full-range signal table ───────────────────────────────────────────────
    with st.expander(f"All Signals — full range  ({len(results)} signals)", expanded=False):
        _show_signal_table(results.reset_index(drop=True), key_suffix="_all")

    # ── Optimal R sweep ───────────────────────────────────────────────────────
    _show_optimal_r(
        filtered_signals, ticks_by_date,
        entry_slip, exit_slip, stop_offset,
        tick_value, contracts, commission,
    )

    # ── Bar data mismatch analysis ────────────────────────────────────────────
    if nt_bars is not None and not nt_bars.empty:
        _show_mismatch_analysis(results, bars, nt_bars)
