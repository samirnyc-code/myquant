"""Prop Firm Simulator — sequential walk-through of BA trades with realistic
account rules: starting balance, contract scaling, daily loss cutoff, trailing
DD blow-up, max trades per day. Trades that violate limits are SKIPPED, so the
equity path reflects what would actually happen in a prop account."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Core simulator
# ─────────────────────────────────────────────────────────────────────────────

def _run_prop_sim(trades: pd.DataFrame, cfg: dict) -> dict:
    """Walk through trades chronologically, applying prop firm rules.

    Returns dict with:
      - trades_df: per-trade results with account state
      - daily_df:  per-day summary
      - blown: bool
      - blown_date: date or None
      - skipped_reasons: dict of reason → count
    """
    starting_bal   = cfg["starting_balance"]
    max_daily_loss = cfg["max_daily_loss"]
    max_trailing_dd = cfg["max_trailing_dd"]
    base_contracts = cfg["base_contracts"]
    scale_interval = cfg["scale_interval"]
    max_contracts  = cfg["max_contracts"]
    max_trades_day = cfg["max_trades_day"]
    count_per_dir  = cfg["count_per_dir"]
    tick_value     = cfg["tick_value"]
    commission_rt  = cfg["commission"]

    balance = starting_bal
    peak_balance = starting_bal
    blown = False
    blown_date = None

    # Per-session state
    current_date = None
    day_pnl = 0.0
    day_long_count = 0
    day_short_count = 0
    day_loss_breached = False

    rows = []
    skipped = {"daily_loss": 0, "max_trades": 0, "blown": 0, "zero_risk": 0}

    dir_map = {1: "Long", -1: "Short", "Long": "Long", "Short": "Short"}

    for _, t in trades.iterrows():
        trade_date = t["ExitTime"].date() if pd.notna(t.get("ExitTime")) else t["DateTime"].date()
        direction = dir_map.get(t.get("Direction"), "Unknown")

        # New day — reset daily state
        if trade_date != current_date:
            current_date = trade_date
            day_pnl = 0.0
            day_long_count = 0
            day_short_count = 0
            day_loss_breached = False

        # Account blown — skip everything
        if blown:
            skipped["blown"] += 1
            continue

        # Daily loss already breached — skip rest of day
        if day_loss_breached:
            skipped["daily_loss"] += 1
            continue

        # Max trades per day
        if max_trades_day > 0:
            if count_per_dir:
                if direction == "Long" and day_long_count >= max_trades_day:
                    skipped["max_trades"] += 1
                    continue
                if direction == "Short" and day_short_count >= max_trades_day:
                    skipped["max_trades"] += 1
                    continue
            else:
                if (day_long_count + day_short_count) >= max_trades_day:
                    skipped["max_trades"] += 1
                    continue

        # Determine contract count based on current balance
        profit_above_start = balance - starting_bal
        if scale_interval > 0 and profit_above_start > 0:
            extra = int(profit_above_start // scale_interval)
            contracts = min(base_contracts + extra, max_contracts)
        else:
            contracts = base_contracts
        contracts = max(1, contracts)

        # Compute P&L for this trade at the current contract count
        gross_pts = t.get("GrossPnLPts", 0)
        if pd.isna(gross_pts) or gross_pts == 0:
            r_ach = t.get("R_achieved", 0)
            risk_pts = t.get("RiskPts", 0)
            if pd.notna(r_ach) and pd.notna(risk_pts) and risk_pts > 0:
                gross_pts = r_ach * risk_pts
            else:
                skipped["zero_risk"] += 1
                continue

        ticks = gross_pts / 0.25
        gross_pnl = ticks * tick_value * contracts
        net_pnl = gross_pnl - commission_rt * contracts

        # Would this trade breach the daily loss limit?
        if max_daily_loss > 0 and (day_pnl + net_pnl) <= -max_daily_loss:
            # Take the trade (it happened in real life — you'd see the loss)
            # but mark the breach so no more trades today
            pass

        # Apply the trade
        balance += net_pnl
        day_pnl += net_pnl

        if direction == "Long":
            day_long_count += 1
        else:
            day_short_count += 1

        # Track peak and trailing DD
        peak_balance = max(peak_balance, balance)
        trailing_dd = balance - peak_balance

        # Check daily loss breach AFTER the trade
        if max_daily_loss > 0 and day_pnl <= -max_daily_loss:
            day_loss_breached = True

        # Check account blown
        if max_trailing_dd > 0 and trailing_dd <= -max_trailing_dd:
            blown = True
            blown_date = trade_date

        rows.append({
            "DateTime": t["DateTime"],
            "ExitTime": t["ExitTime"],
            "Date": trade_date,
            "Direction": direction,
            "SignalType": t.get("SignalType", ""),
            "Contracts": contracts,
            "GrossPnLPts": gross_pts,
            "GrossPnL": gross_pnl,
            "NetPnL": net_pnl,
            "Balance": balance,
            "Peak": peak_balance,
            "TrailingDD": trailing_dd,
            "DayPnL": day_pnl,
            "DayTradeNum": day_long_count + day_short_count,
            "DailyLossBreach": day_loss_breached,
            "AccountBlown": blown,
            "R_achieved": t.get("R_achieved", np.nan),
            "RiskPts": t.get("RiskPts", np.nan),
        })

    trades_df = pd.DataFrame(rows) if rows else pd.DataFrame()

    # Build daily summary
    daily_df = pd.DataFrame()
    if not trades_df.empty:
        daily_df = trades_df.groupby("Date").agg(
            trades=("NetPnL", "count"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            daily_pnl=("DayPnL", "last"),
            eod_balance=("Balance", "last"),
            eod_peak=("Peak", "last"),
            eod_trailing_dd=("TrailingDD", "last"),
            min_contracts=("Contracts", "min"),
            max_contracts=("Contracts", "max"),
            daily_loss_breach=("DailyLossBreach", "last"),
            account_blown=("AccountBlown", "last"),
        ).reset_index()
        daily_df["Win%"] = (100 * daily_df["wins"] / daily_df["trades"]).round(1)

        # Intraday worst DD
        intra_dd = trades_df.groupby("Date")["TrailingDD"].min().reset_index()
        intra_dd.columns = ["Date", "IntradayDD"]
        daily_df = daily_df.merge(intra_dd, on="Date", how="left")

    return {
        "trades_df": trades_df,
        "daily_df": daily_df,
        "blown": blown,
        "blown_date": blown_date,
        "skipped": skipped,
    }


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

def show_prop_sim_tab():
    st.header("🏢 Prop Firm Simulator")
    st.caption(
        "Sequential walk-through of BA trades with prop firm rules. "
        "Trades that violate limits are **skipped** — the equity path "
        "reflects what a real prop account would experience."
    )

    results = st.session_state.get("ba_results")
    if results is None or results.empty:
        st.info("Run a simulation in Bar Analysis first.")
        return

    filled = results[results["Filled"] == True].copy()
    if filled.empty or "ExitTime" not in filled.columns:
        st.info("No filled trades to simulate.")
        return

    filled = filled.sort_values("ExitTime").reset_index(drop=True)

    # ── Configuration ────────────────────────────────────────────────────────
    st.subheader("Account Rules")
    c1, c2, c3, c4 = st.columns(4)
    starting_balance = c1.number_input(
        "Starting balance ($)", value=50_000, step=5_000, key="ps_start_bal")
    max_daily_loss = c2.number_input(
        "Max daily loss ($)", value=2_000, step=250, key="ps_daily_loss",
        help="0 = no limit. After hitting this, no more trades that day.")
    max_trailing_dd = c3.number_input(
        "Max trailing DD ($)", value=3_000, step=250, key="ps_trailing_dd",
        help="0 = no limit. Account blown when trailing DD exceeds this.")
    max_trades_day = c4.number_input(
        "Max trades/day", value=0, step=1, key="ps_max_trades",
        help="0 = unlimited")

    st.subheader("Contract Scaling")
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    base_contracts = s1.number_input(
        "Base contracts", value=1, min_value=1, step=1, key="ps_base_c")
    scale_interval = s2.number_input(
        "Scale every $ profit", value=2_500, step=500, key="ps_scale_int",
        help="Add 1 contract per $X profit above start. 0 = no scaling.")
    max_contracts = s3.number_input(
        "Max contracts", value=10, min_value=1, step=1, key="ps_max_c")
    tick_value = s4.number_input(
        "Tick value ($)", value=12.50, step=1.25, key="ps_tv")
    commission = s5.number_input(
        "Commission RT ($/c)", value=4.36, step=0.50, key="ps_comm")
    count_per_dir = s6.checkbox(
        "Per direction", value=False, key="ps_per_dir",
        help="Max trades counted per direction (N longs + N shorts)")

    # ── Run button ───────────────────────────────────────────────────────────
    if st.button("▶ Run Prop Sim", key="ps_run", type="primary"):
        cfg = {
            "starting_balance": starting_balance,
            "max_daily_loss": max_daily_loss,
            "max_trailing_dd": max_trailing_dd,
            "base_contracts": base_contracts,
            "scale_interval": scale_interval,
            "max_contracts": max_contracts,
            "max_trades_day": max_trades_day,
            "count_per_dir": count_per_dir,
            "tick_value": tick_value,
            "commission": commission,
        }
        with st.spinner("Running prop sim..."):
            result = _run_prop_sim(filled, cfg)
        st.session_state["ps_result"] = result
        st.session_state["ps_cfg"] = cfg

    # ── Display results ──────────────────────────────────────────────────────
    result = st.session_state.get("ps_result")
    cfg = st.session_state.get("ps_cfg")
    if result is None:
        st.info("Configure settings above and click **Run Prop Sim**.")
        return

    trades_df = result["trades_df"]
    daily_df = result["daily_df"]
    blown = result["blown"]
    blown_date = result["blown_date"]
    skipped = result["skipped"]

    if trades_df.empty:
        st.warning("No trades survived the filters.")
        return

    starting_bal = cfg["starting_balance"]
    max_daily = cfg["max_daily_loss"]
    max_dd = cfg["max_trailing_dd"]

    # ── Headline ─────────────────────────────────────────────────────────────
    st.markdown("---")
    final_bal = trades_df["Balance"].iloc[-1]
    total_pnl = final_bal - starting_bal
    total_trades = len(trades_df)
    total_skipped = sum(skipped.values())
    worst_dd = trades_df["TrailingDD"].min()
    worst_day = daily_df["daily_pnl"].min() if not daily_df.empty else 0
    best_day = daily_df["daily_pnl"].max() if not daily_df.empty else 0
    max_c_reached = int(trades_df["Contracts"].max())
    n_breach_days = daily_df["daily_loss_breach"].sum() if not daily_df.empty else 0
    wins = (trades_df["NetPnL"] > 0).sum()

    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.metric("Final Balance", f"${final_bal:,.0f}", delta=f"${total_pnl:+,.0f}")
    h2.metric("Trades Taken", f"{total_trades}",
              delta=f"{total_skipped} skipped" if total_skipped else None)
    h3.metric("Win%", f"{100*wins/max(total_trades,1):.1f}%")
    h4.metric("Worst Trailing DD", f"${worst_dd:,.0f}")
    h5.metric("Worst Day", f"${worst_day:,.0f}")
    h6.metric("Max Contracts", f"{max_c_reached}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    if blown:
        st.error(
            f"💀 Account **BLOWN on {blown_date}** — trailing DD hit "
            f"${worst_dd:,.0f} (limit -${max_dd:,.0f}). "
            f"{total_trades} trades taken before blow-up, "
            f"{skipped['blown']} trades skipped after.")
    elif n_breach_days > 0:
        cushion = abs(max_dd) - abs(worst_dd) if max_dd > 0 else float("inf")
        st.warning(
            f"Account survives but hit daily loss limit on "
            f"**{int(n_breach_days)} day(s)**. Worst trailing DD: "
            f"${worst_dd:,.0f} (${cushion:,.0f} cushion).")
    else:
        cushion = abs(max_dd) - abs(worst_dd) if max_dd > 0 else float("inf")
        st.success(
            f"✅ Account **survives**. Net +${total_pnl:,.0f}, "
            f"worst DD ${worst_dd:,.0f} (${cushion:,.0f} cushion). "
            f"No daily loss breaches.")

    # ── Quick View ────────────────────────────────────────────────────────────
    with st.expander("📋 Quick View", expanded=True):
        losses = (trades_df["NetPnL"] <= 0).sum()
        avg_win = trades_df.loc[trades_df["NetPnL"] > 0, "NetPnL"].mean() if wins else 0
        avg_loss = trades_df.loc[trades_df["NetPnL"] <= 0, "NetPnL"].mean() if losses else 0
        exp_r = trades_df["R_achieved"].mean() if "R_achieved" in trades_df else 0
        trading_days = daily_df["Date"].nunique() if not daily_df.empty else 0
        equity = trades_df["NetPnL"].cumsum()
        peak_eq = equity.cummax()
        max_dd_eq = float((equity - peak_eq).min())

        r_vals = trades_df["R_achieved"].dropna().values
        r_std = float(np.std(r_vals, ddof=1)) if len(r_vals) > 1 else 0.0
        n_sqn = min(total_trades, 100)
        sqn = float(exp_r / r_std * np.sqrt(n_sqn)) if r_std > 0 else 0.0

        pos_pnl = trades_df.loc[trades_df["NetPnL"] > 0, "NetPnL"].sum()
        neg_pnl = trades_df.loc[trades_df["NetPnL"] <= 0, "NetPnL"].sum()
        pf = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else float("inf")
        pnl_dd = total_pnl / abs(max_dd_eq) if max_dd_eq < 0 else float("nan")

        q1, q2, q3, q4, q5, q6 = st.columns(6)
        q1.metric("Net PnL", f"${total_pnl:,.0f}")
        q2.metric("Win%", f"{100*wins/max(total_trades,1):.1f}%")
        q3.metric("PF", f"{pf:.2f}")
        q4.metric("Exp $", f"${total_pnl/max(total_trades,1):,.0f}")
        q5.metric("Max DD", f"${max_dd_eq:,.0f}")
        q6.metric("PnL/DD", f"{pnl_dd:.2f}" if not np.isnan(pnl_dd) else "—")

        q7, q8, q9, q10, q11, q12 = st.columns(6)
        q7.metric("Trades", f"{total_trades}")
        q8.metric("Avg Win", f"${avg_win:,.0f}")
        q9.metric("Avg Loss", f"${avg_loss:,.0f}")
        q10.metric("Exp R", f"{exp_r:.3f}")
        q11.metric("SQN", f"{sqn:.1f}")
        q12.metric("Days", f"{trading_days}")

    # ── Detail ───────────────────────────────────────────────────────────────
    with st.expander("📊 Detail", expanded=True):
        _tgt_mask = trades_df["NetPnL"] > 0
        _stop_mask = trades_df["NetPnL"] <= 0

        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown("**Breakdown**")
            _detail = {
                "Metric": [
                    "Gross Won", "Gross Lost", "Net Total",
                    "Avg Win", "Avg Loss", "W/L Ratio",
                    "Largest Win", "Largest Loss",
                    "Avg Contracts",
                ],
                "Value": [
                    f"${pos_pnl:,.0f}",
                    f"${neg_pnl:,.0f}",
                    f"${total_pnl:,.0f}",
                    f"${avg_win:,.0f}",
                    f"${avg_loss:,.0f}",
                    f"{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "∞",
                    f"${trades_df['NetPnL'].max():,.0f}",
                    f"${trades_df['NetPnL'].min():,.0f}",
                    f"{trades_df['Contracts'].mean():.1f}",
                ],
            }
            st.dataframe(pd.DataFrame(_detail), use_container_width=True, hide_index=True)

        with dc2:
            st.markdown("**Exit Reasons** (by scaled P&L)")
            if "R_achieved" in trades_df.columns:
                _r_pos = trades_df.loc[trades_df["R_achieved"] > 0]
                _r_neg = trades_df.loc[trades_df["R_achieved"] <= 0]
                _exit_detail = {
                    "": ["Winners", "Losers", "Total"],
                    "Count": [len(_r_pos), len(_r_neg), total_trades],
                    "Net $": [
                        f"${_r_pos['NetPnL'].sum():,.0f}",
                        f"${_r_neg['NetPnL'].sum():,.0f}",
                        f"${total_pnl:,.0f}",
                    ],
                    "Avg $": [
                        f"${_r_pos['NetPnL'].mean():,.0f}" if len(_r_pos) else "—",
                        f"${_r_neg['NetPnL'].mean():,.0f}" if len(_r_neg) else "—",
                        f"${total_pnl/max(total_trades,1):,.0f}",
                    ],
                }
                st.dataframe(pd.DataFrame(_exit_detail), use_container_width=True, hide_index=True)

    # ── Monthly Breakdown ────────────────────────────────────────────────────
    with st.expander("📅 Monthly Breakdown", expanded=True):
        trades_df["_month"] = pd.to_datetime(trades_df["ExitTime"]).dt.to_period("M")
        monthly = trades_df.groupby("_month").agg(
            trades=("NetPnL", "count"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            net_pnl=("NetPnL", "sum"),
            avg_contracts=("Contracts", "mean"),
        ).reset_index()
        monthly["Win%"] = (100 * monthly["wins"] / monthly["trades"]).round(1)
        monthly["Exp $"] = (monthly["net_pnl"] / monthly["trades"]).round(0)
        monthly["Month"] = monthly["_month"].astype(str)
        monthly["Cum PnL"] = monthly["net_pnl"].cumsum()

        # Color-coded monthly chart
        m_colors = ["#66bb6a" if v >= 0 else "#ef5350" for v in monthly["net_pnl"]]
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(
            x=monthly["Month"], y=monthly["net_pnl"],
            marker_color=m_colors, name="Monthly PnL",
        ))
        fig_m.add_trace(go.Scatter(
            x=monthly["Month"], y=monthly["Cum PnL"],
            mode="lines+markers", name="Cumulative",
            line=dict(color="#42A5F5", width=2),
            yaxis="y2",
        ))
        fig_m.update_layout(
            height=350, margin=dict(t=10, b=30),
            yaxis=dict(title="Monthly P&L ($)"),
            yaxis2=dict(title="Cumulative ($)", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.02),
        )
        st.plotly_chart(fig_m, use_container_width=True)

        # Monthly table
        display_monthly = monthly[["Month", "trades", "wins", "Win%",
                                    "net_pnl", "Exp $", "avg_contracts", "Cum PnL"]].copy()
        display_monthly.columns = ["Month", "Trades", "Wins", "Win%",
                                    "Net PnL", "Exp $", "Avg C", "Cum PnL"]
        st.dataframe(
            display_monthly.style.format({
                "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}",
                "Cum PnL": "${:,.0f}", "Avg C": "{:.1f}",
                "Win%": "{:.1f}%",
            }).applymap(
                lambda v: "color: #66bb6a" if isinstance(v, (int, float)) and v > 0
                else "color: #ef5350" if isinstance(v, (int, float)) and v < 0
                else "",
                subset=["Net PnL"]
            ),
            use_container_width=True, hide_index=True)

        trades_df.drop(columns=["_month"], inplace=True, errors="ignore")

    # ── Skip summary ─────────────────────────────────────────────────────────
    if total_skipped > 0:
        skip_parts = []
        if skipped["daily_loss"]:
            skip_parts.append(f"{skipped['daily_loss']} daily-loss cutoff")
        if skipped["max_trades"]:
            skip_parts.append(f"{skipped['max_trades']} max-trades limit")
        if skipped["blown"]:
            skip_parts.append(f"{skipped['blown']} post-blowup")
        if skipped["zero_risk"]:
            skip_parts.append(f"{skipped['zero_risk']} zero-risk (no data)")
        st.info(f"**Skipped trades:** {', '.join(skip_parts)}")

    # ── Charts ───────────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=[
            "Account Balance", "Daily P&L",
            "Trailing Drawdown (EOD + Intraday)", "Contracts"
        ],
        row_heights=[0.3, 0.25, 0.25, 0.2],
        shared_xaxes=True, vertical_spacing=0.05)

    dates = pd.to_datetime(daily_df["Date"])

    # Row 1: Balance
    fig.add_trace(go.Scatter(
        x=dates, y=daily_df["eod_balance"],
        mode="lines", line=dict(color="#4CAF50", width=2),
        showlegend=False,
    ), row=1, col=1)
    fig.add_hline(y=starting_bal, line_dash="dot", line_color="#666",
        annotation_text=f"Start ${starting_bal:,.0f}", row=1, col=1)
    if blown and blown_date:
        fig.add_vline(x=pd.Timestamp(blown_date), line_dash="dash",
            line_color="#ff1744", annotation_text="BLOWN", row=1, col=1)

    # Row 2: Daily P&L
    bar_colors = [
        "#c62828" if row["daily_loss_breach"] else
        "#ef5350" if row["daily_pnl"] < 0 else "#66bb6a"
        for _, row in daily_df.iterrows()
    ]
    fig.add_trace(go.Bar(
        x=dates, y=daily_df["daily_pnl"],
        marker_color=bar_colors, showlegend=False,
    ), row=2, col=1)
    if max_daily > 0:
        fig.add_hline(y=-max_daily, line_dash="dash", line_color="#ff5252",
            annotation_text=f"-${max_daily:,.0f}", row=2, col=1)

    # Row 3: Trailing DD
    fig.add_trace(go.Scatter(
        x=dates, y=daily_df["eod_trailing_dd"],
        fill="tozeroy", fillcolor="rgba(198,40,40,0.15)",
        line=dict(color="#ef5350", width=1.5),
        name="EOD DD", showlegend=False,
    ), row=3, col=1)
    if "IntradayDD" in daily_df.columns:
        fig.add_trace(go.Scatter(
            x=dates, y=daily_df["IntradayDD"],
            mode="lines", line=dict(color="#ff8a80", width=1, dash="dot"),
            name="Intraday DD", showlegend=False,
        ), row=3, col=1)
    if max_dd > 0:
        fig.add_hline(y=-max_dd, line_dash="dash", line_color="#ff5252",
            annotation_text=f"-${max_dd:,.0f}", row=3, col=1)

    # Row 4: Contracts
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(trades_df["ExitTime"]),
        y=trades_df["Contracts"],
        mode="lines", line=dict(color="#42A5F5", width=1.5),
        showlegend=False,
    ), row=4, col=1)
    fig.update_yaxes(title_text="Contracts", row=4, col=1)

    fig.update_layout(height=900, margin=dict(t=30, b=30))
    st.plotly_chart(fig, use_container_width=True)

    # ── Stats ────────────────────────────────────────────────────────────────
    st.subheader("Statistics")

    # Losing streaks
    streaks = []
    streak = 0
    for v in daily_df["daily_pnl"]:
        if v < 0:
            streak += 1
        else:
            if streak > 0:
                streaks.append(streak)
            streak = 0
    if streak > 0:
        streaks.append(streak)

    losing_days = (daily_df["daily_pnl"] < 0).sum()
    total_days = len(daily_df)

    st1, st2, st3, st4, st5, st6 = st.columns(6)
    st1.metric("Max losing streak", f"{max(streaks) if streaks else 0}d")
    st2.metric("Avg losing streak", f"{np.mean(streaks):.1f}d" if streaks else "0")
    st3.metric("Losing days", f"{losing_days}/{total_days}")
    st4.metric("Avg daily P&L", f"${daily_df['daily_pnl'].mean():,.0f}")
    st5.metric("Exp $/trade", f"${trades_df['NetPnL'].mean():,.0f}")
    st6.metric("Daily loss cutoffs", f"{int(n_breach_days)} days")

    # ── Scaling breakdown ────────────────────────────────────────────────────
    if cfg["scale_interval"] > 0 and trades_df["Contracts"].nunique() > 1:
        st.subheader("Scaling Breakdown")
        level_stats = trades_df.groupby("Contracts").agg(
            trades=("NetPnL", "count"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            net_pnl=("NetPnL", "sum"),
            avg_r=("R_achieved", "mean"),
            first_date=("ExitTime", "min"),
            last_date=("ExitTime", "max"),
        ).reset_index()
        level_stats["Win%"] = (100 * level_stats["wins"] / level_stats["trades"]).round(1)
        level_stats["Exp $"] = (level_stats["net_pnl"] / level_stats["trades"]).round(0)
        level_stats["First"] = level_stats["first_date"].dt.strftime("%Y-%m-%d")
        level_stats["Last"] = level_stats["last_date"].dt.strftime("%Y-%m-%d")
        display_cols = ["Contracts", "trades", "Win%", "net_pnl", "Exp $",
                        "avg_r", "First", "Last"]
        display_cols = [c for c in display_cols if c in level_stats.columns]
        st.dataframe(
            level_stats[display_cols].rename(columns={
                "trades": "Trades", "net_pnl": "Net PnL", "avg_r": "Avg R"
            }).style.format({
                "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}",
                "Avg R": "{:.3f}", "Win%": "{:.1f}%",
            }),
            use_container_width=True, hide_index=True)

    # ── Daily detail ─────────────────────────────────────────────────────────
    with st.expander("📋 Daily Detail", expanded=False):
        dd = daily_df[[
            "Date", "trades", "wins", "Win%", "daily_pnl",
            "eod_balance", "eod_trailing_dd", "min_contracts",
            "max_contracts", "daily_loss_breach",
        ]].copy()
        dd.columns = [
            "Date", "Trades", "Wins", "Win%", "Daily PnL",
            "EOD Balance", "Trailing DD", "Min C", "Max C", "Loss Breach",
        ]
        dd["Date"] = dd["Date"].astype(str)

        def _color(row):
            if row.get("Loss Breach"):
                return ["background-color: rgba(198,40,40,0.3)"] * len(row)
            if row["Daily PnL"] < 0:
                return ["background-color: rgba(198,40,40,0.1)"] * len(row)
            return [""] * len(row)

        styled = dd.style.apply(_color, axis=1).format({
            "Daily PnL": "${:,.0f}", "EOD Balance": "${:,.0f}",
            "Trailing DD": "${:,.0f}", "Win%": "{:.1f}%",
        })
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Trade detail ─────────────────────────────────────────────────────────
    with st.expander("📋 Trade Detail", expanded=False):
        td = trades_df[[
            "ExitTime", "Direction", "SignalType", "Contracts",
            "GrossPnLPts", "NetPnL", "Balance", "TrailingDD",
            "DayTradeNum", "R_achieved",
        ]].copy()
        td["ExitTime"] = td["ExitTime"].dt.strftime("%Y-%m-%d %H:%M")
        td.columns = [
            "Exit", "Dir", "Setup", "C",
            "Gross Pts", "Net $", "Balance", "Trail DD",
            "Day#", "R",
        ]
        st.dataframe(
            td.style.format({
                "Gross Pts": "{:.2f}", "Net $": "${:,.0f}",
                "Balance": "${:,.0f}", "Trail DD": "${:,.0f}",
                "R": "{:.3f}",
            }),
            use_container_width=True, hide_index=True)
