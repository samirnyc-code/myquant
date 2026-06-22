import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


def show_extras_tab():
    st.header("Extras")

    # ── Signal Overlap & Account Allocation ──────────────────────────────────
    _show_signal_overlap()

    # ── Prop Firm Compliance ─────────────────────────────────────────────────
    _show_prop_firm()


def _show_signal_overlap():
    st.subheader("🏦 Signal Overlap & Account Allocation")

    results = st.session_state.get("ba_results")
    if results is None or results.empty:
        st.info("Run a simulation in Bar Analysis first — this tab reads those results.")
        return

    filled = results[results["Filled"] == True].copy()
    if filled.empty or "DateTime" not in filled.columns:
        st.info("No filled trades with DateTime to analyze.")
        return

    filled["Date"] = filled["DateTime"].dt.date
    _dir_map = {1: "Long", -1: "Short", "Long": "Long", "Short": "Short"}
    filled["Dir"] = filled["Direction"].map(_dir_map)

    # ── Headline metrics ─────────────────────────────────────────────────────
    spd = filled.groupby("Date").size()
    both_dirs = sum(
        1 for d in filled["Date"].unique()
        if filled[filled["Date"] == d]["Dir"].nunique() == 2
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Avg trades/day", f"{spd.mean():.1f}")
    mc2.metric("Median", f"{int(spd.median())}")
    mc3.metric("Max", f"{int(spd.max())}")
    mc4.metric("Days w/ both L+S",
               f"{both_dirs}/{spd.count()} "
               f"({100 * both_dirs / max(spd.count(), 1):.0f}%)")

    # ── Trades per day over time + distribution ──────────────────────────────
    daily = filled.groupby(["Date", "Dir"]).size().unstack(fill_value=0)
    for d in ("Long", "Short"):
        if d not in daily.columns:
            daily[d] = 0
    dates = pd.to_datetime(daily.index)

    fig1 = make_subplots(rows=1, cols=2,
        subplot_titles=["Trades per Day Over Time", "Distribution"],
        column_widths=[0.65, 0.35])
    fig1.add_trace(go.Bar(
        x=dates, y=daily["Long"], name="Long",
        marker_color="#2196F3", opacity=0.8), row=1, col=1)
    fig1.add_trace(go.Bar(
        x=dates, y=daily["Short"], name="Short",
        marker_color="#F44336", opacity=0.8), row=1, col=1)
    fig1.update_layout(barmode="stack", height=350, margin=dict(t=30, b=30))
    fig1.add_hline(y=spd.mean(), line_dash="dash", line_color="orange",
        annotation_text=f"Mean {spd.mean():.1f}/day", row=1, col=1)
    fig1.add_trace(go.Histogram(
        x=spd, name="Days", marker_color="#4CAF50", opacity=0.8,
        showlegend=False), row=1, col=2)
    fig1.update_xaxes(title_text="Trades per day", row=1, col=2)
    fig1.update_yaxes(title_text="Number of days", row=1, col=2)
    st.plotly_chart(fig1, use_container_width=True)

    # ── Gap between consecutive signals ──────────────────────────────────────
    sorted_f = filled.sort_values("DateTime")
    sorted_f["_prev_dt"] = sorted_f.groupby("Date")["DateTime"].shift(1)
    gaps = (
        (sorted_f["DateTime"] - sorted_f["_prev_dt"])
        .dt.total_seconds().div(60).dropna()
    )
    if not gaps.empty:
        st.markdown(
            f"**Gap between consecutive signals (same day):** "
            f"median {gaps.median():.0f} min, "
            f"mean {gaps.mean():.0f} min — "
            f"{(gaps < 30).sum()} ({100 * (gaps < 30).mean():.0f}%) "
            f"within 30 min"
        )

    # ── Concurrent position estimate ─────────────────────────────────────────
    st.subheader("Concurrent Positions (30-min window)")
    st.caption(
        "At each signal, how many other signals fired within ±30 minutes? "
        "This estimates how many positions would be open simultaneously."
    )
    conc_counts = []
    for _, grp in sorted_f.groupby("Date"):
        times = grp["DateTime"].sort_values().tolist()
        for t in times:
            n_conc = sum(
                1 for t2 in times
                if t2 != t and abs((t - t2).total_seconds()) <= 1800
            )
            conc_counts.append(n_conc + 1)
    cc_s = pd.Series(conc_counts)
    cc_vc = cc_s.value_counts().sort_index()
    cc_colors = ["#4CAF50", "#FFC107", "#FF9800", "#F44336", "#9C27B0", "#795548"]

    fig_cc = go.Figure(go.Bar(
        x=[str(k) for k in cc_vc.index],
        y=cc_vc.values,
        marker_color=[cc_colors[min(i, len(cc_colors) - 1)]
                      for i in range(len(cc_vc))],
        text=[f"{v}<br>({100 * v / cc_s.count():.0f}%)" for v in cc_vc.values],
        textposition="outside",
    ))
    fig_cc.update_layout(
        xaxis_title="Simultaneous positions",
        yaxis_title="Signal instances",
        height=300, margin=dict(t=10, b=30))
    st.plotly_chart(fig_cc, use_container_width=True)

    # ── Account allocation scenarios ─────────────────────────────────────────
    st.subheader("Account Allocation Scenarios")
    st.caption(
        "Each scenario keeps the first N filled trades per day per direction "
        "(sorted by signal time). Shows how many trades and what % of total "
        "P&L each scenario captures."
    )
    total_n = len(filled)
    total_pnl = filled["NetPnL"].sum()
    scenarios = {}

    for n_per in (1, 2, 3, 4, 5):
        sub = pd.concat([
            filled[filled["Dir"] == "Long"]
                .sort_values("DateTime").groupby("Date").head(n_per),
            filled[filled["Dir"] == "Short"]
                .sort_values("DateTime").groupby("Date").head(n_per),
        ])
        accts = n_per * 2
        sub_pnl = sub["NetPnL"].sum()
        scenarios[f"{n_per}L + {n_per}S ({accts} accts)"] = {
            "Accounts": accts,
            "Trades": len(sub),
            "% of Trades": f"{100 * len(sub) / max(total_n, 1):.1f}%",
            "Net PnL": f"${sub_pnl:,.0f}",
            "% of PnL": (
                f"{100 * sub_pnl / total_pnl:.1f}%"
                if total_pnl != 0 else "N/A"
            ),
            "Exp $/trade": f"${sub_pnl / max(len(sub), 1):,.0f}",
        }
    sc_df = pd.DataFrame(scenarios).T
    sc_df.index.name = "Scenario"
    st.dataframe(sc_df, use_container_width=True)

    # ── Per-account equity curves ────────────────────────────────────────────
    st.subheader("Per-Account Equity Curves")
    n_acct_per = st.slider(
        "Trades per direction per day",
        min_value=1, max_value=5, value=2,
        key="ext_ov_n_acct",
        help="e.g. 2 = accounts for 1st long, 2nd long, 1st short, 2nd short"
    )
    acct_traces = {}
    for dir_name in ("Long", "Short"):
        dir_trades = (filled[filled["Dir"] == dir_name]
                      .sort_values("DateTime").copy())
        dir_trades["_rank"] = dir_trades.groupby("Date").cumcount() + 1
        for slot in range(1, n_acct_per + 1):
            slot_trades = dir_trades[dir_trades["_rank"] == slot]
            label = f"Acct {slot} {dir_name}"
            acct_traces[label] = slot_trades

    fig_eq = go.Figure()
    eq_colors = {
        "Long": ["#1565C0", "#42A5F5", "#90CAF9", "#BBDEFB", "#E3F2FD"],
        "Short": ["#C62828", "#EF5350", "#EF9A9A", "#FFCDD2", "#FFEBEE"],
    }
    for label, trades in acct_traces.items():
        if trades.empty:
            continue
        sorted_trades = trades.sort_values("ExitTime")
        eq = sorted_trades["NetPnL"].cumsum()
        dir_key = "Long" if "Long" in label else "Short"
        slot_idx = int(label.split()[1]) - 1
        clr = eq_colors[dir_key][min(slot_idx, 4)]
        fig_eq.add_trace(go.Scatter(
            x=sorted_trades["ExitTime"],
            y=eq.values,
            mode="lines",
            name=f"{label} ({len(trades)} trades, ${eq.iloc[-1]:,.0f})",
            line=dict(color=clr, width=2),
        ))

    all_sorted = filled.sort_values("ExitTime")
    all_eq = all_sorted["NetPnL"].cumsum()
    fig_eq.add_trace(go.Scatter(
        x=all_sorted["ExitTime"],
        y=all_eq.values,
        mode="lines",
        name=f"ALL ({total_n} trades, ${total_pnl:,.0f})",
        line=dict(color="white", width=3, dash="dash"),
    ))
    fig_eq.update_layout(
        height=450,
        yaxis_title="Cumulative P&L ($)",
        xaxis_title="Date",
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="left", x=0),
        margin=dict(t=60, b=30),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

    # ── Per-account summary table ────────────────────────────────────────────
    acct_rows = []
    for label, trades in acct_traces.items():
        if trades.empty:
            continue
        pnl = trades["NetPnL"].sum()
        n = len(trades)
        wins = (trades["NetPnL"] > 0).sum()
        eq_curve = trades.sort_values("ExitTime")["NetPnL"].cumsum()
        dd = (eq_curve - eq_curve.cummax()).min()
        acct_rows.append({
            "Account": label,
            "Trades": n,
            "Net PnL": f"${pnl:,.0f}",
            "Exp $": f"${pnl / max(n, 1):,.0f}",
            "Win%": f"{100 * wins / max(n, 1):.1f}%",
            "Max DD": f"${dd:,.0f}",
            "PnL/DD": f"{pnl / abs(dd):.2f}" if dd < 0 else "∞",
        })
    if acct_rows:
        st.dataframe(
            pd.DataFrame(acct_rows),
            use_container_width=True, hide_index=True)

    st.caption(
        "**How to read:** Each 'account' receives the Nth trade of that "
        "direction each day. Acct 1 Long gets the first long signal of "
        "every day, Acct 2 Long gets the second, etc. The dashed white "
        "line is the combined portfolio (all trades). Individual account "
        "curves will diverge — the portfolio equity is NOT what any "
        "single account sees."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prop Firm Compliance & Contract Scaling
# ─────────────────────────────────────────────────────────────────────────────

def _simulate_scaled_equity(trades_sorted, tick_value, commission,
                            base_contracts, scale_interval, max_contracts,
                            starting_balance):
    """Re-simulate trade-by-trade P&L with dynamic contract scaling.

    At each trade, contracts = base + floor(balance / scale_interval).
    Clamped to [1, max_contracts]. Scales DOWN when balance drops.
    Returns a DataFrame with per-trade scaled results.
    """
    rows = []
    balance = starting_balance
    peak = balance

    for _, t in trades_sorted.iterrows():
        # Determine contracts for this trade
        profit_above_start = balance - starting_balance
        if scale_interval > 0 and profit_above_start > 0:
            extra = int(profit_above_start // scale_interval)
            contracts = min(base_contracts + extra, max_contracts)
        else:
            contracts = base_contracts
        contracts = max(1, contracts)

        # Recompute P&L for this contract count
        gross_pts = t.get("GrossPnLPts", 0)
        if pd.isna(gross_pts):
            gross_pts = 0
        gross_pnl = gross_pts / 0.25 * tick_value * contracts  # pts → $
        net_pnl = gross_pnl - commission * contracts

        balance += net_pnl
        peak = max(peak, balance)
        dd = balance - peak

        rows.append({
            "DateTime": t["DateTime"],
            "ExitTime": t["ExitTime"],
            "Date": t["ExitTime"].date() if pd.notna(t.get("ExitTime")) else t["DateTime"].date(),
            "Direction": t.get("Direction"),
            "SignalType": t.get("SignalType", ""),
            "Contracts": contracts,
            "GrossPnLPts": gross_pts,
            "GrossPnL": gross_pnl,
            "NetPnL": net_pnl,
            "Balance": balance,
            "Peak": peak,
            "TrailingDD": dd,
            "R_achieved": t.get("R_achieved", np.nan),
        })

    return pd.DataFrame(rows)


def _show_prop_firm():
    st.subheader("🏢 Prop Firm Compliance & Scaling")

    results = st.session_state.get("ba_results")
    if results is None or results.empty:
        st.info("Run a simulation in Bar Analysis first.")
        return

    filled = results[results["Filled"] == True].copy()
    if filled.empty or "ExitTime" not in filled.columns:
        st.info("No filled trades to analyze.")
        return

    filled = filled.sort_values("ExitTime")

    # ── Account Config ───────────────────────────────────────────────────────
    st.markdown("#### Account Rules")
    ac1, ac2, ac3 = st.columns(3)
    starting_balance = ac1.number_input(
        "Starting balance ($)", value=50_000, step=5_000,
        key="ext_pf_start_bal")
    max_daily_loss = ac2.number_input(
        "Max daily loss ($)", value=2_000, step=250,
        key="ext_pf_max_daily_loss")
    max_trailing_dd = ac3.number_input(
        "Max trailing DD ($)", value=3_000, step=250,
        key="ext_pf_max_trailing_dd")

    # ── Scaling Config ───────────────────────────────────────────────────────
    st.markdown("#### Contract Scaling")
    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
    base_contracts = sc1.number_input(
        "Base contracts", value=1, min_value=1, step=1,
        key="ext_pf_base_contracts")
    scale_interval = sc2.number_input(
        "Scale-up every $ profit", value=2_500, step=500,
        key="ext_pf_scale_interval",
        help="Add 1 contract for every $X above starting balance. "
             "Scales back down when balance drops.")
    max_contracts = sc3.number_input(
        "Max contracts", value=10, min_value=1, step=1,
        key="ext_pf_max_contracts")
    tick_value = sc4.number_input(
        "Tick value ($)", value=12.50, step=1.25,
        key="ext_pf_tick_value",
        help="ES = $12.50, MES = $1.25")
    commission = sc5.number_input(
        "Commission ($/contract RT)", value=4.36, step=0.50,
        key="ext_pf_commission")

    # ── Run the scaled simulation ────────────────────────────────────────────
    scaled = _simulate_scaled_equity(
        filled, tick_value, commission,
        base_contracts, scale_interval, max_contracts,
        starting_balance)

    if scaled.empty:
        st.warning("No trades to simulate.")
        return

    # ── Daily aggregation ────────────────────────────────────────────────────
    daily = scaled.groupby("Date").agg(
        trades=("NetPnL", "count"),
        wins=("NetPnL", lambda x: (x > 0).sum()),
        daily_pnl=("NetPnL", "sum"),
        eod_balance=("Balance", "last"),
        eod_peak=("Peak", "last"),
        eod_dd=("TrailingDD", "last"),
        min_contracts=("Contracts", "min"),
        max_contracts_day=("Contracts", "max"),
    ).reset_index()
    daily["Win%"] = (100 * daily["wins"] / daily["trades"]).round(1)

    # Intraday DD (worst point during the day, not just EOD)
    intra_dd = scaled.groupby("Date")["TrailingDD"].min().reset_index()
    intra_dd.columns = ["Date", "Intraday DD"]
    daily = daily.merge(intra_dd, on="Date", how="left")

    # Breach flags
    daily["Daily Loss Breach"] = daily["daily_pnl"] <= -max_daily_loss
    daily["DD Breach"] = daily["eod_dd"] <= -max_trailing_dd
    daily["Intraday DD Breach"] = daily["Intraday DD"] <= -max_trailing_dd

    n_daily_breach = daily["Daily Loss Breach"].sum()
    first_dd_breach = None
    if daily["Intraday DD Breach"].any():
        first_dd_breach = daily.loc[daily["Intraday DD Breach"].idxmax(), "Date"]

    # ── Headline metrics ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Results")
    final_balance = daily["eod_balance"].iloc[-1]
    total_pnl = final_balance - starting_balance
    worst_day = daily["daily_pnl"].min()
    best_day = daily["daily_pnl"].max()
    worst_dd = daily["Intraday DD"].min()
    losing_days = (daily["daily_pnl"] < 0).sum()
    total_days = len(daily)
    max_contracts_reached = int(scaled["Contracts"].max())

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Final Balance", f"${final_balance:,.0f}",
              delta=f"${total_pnl:+,.0f}")
    m2.metric("Worst Day", f"${worst_day:,.0f}",
              delta="BREACH" if worst_day <= -max_daily_loss else "OK",
              delta_color="inverse" if worst_day <= -max_daily_loss else "normal")
    m3.metric("Best Day", f"${best_day:,.0f}")
    m4.metric("Worst Trailing DD", f"${worst_dd:,.0f}",
              delta="BLOWN" if worst_dd <= -max_trailing_dd else "OK",
              delta_color="inverse" if worst_dd <= -max_trailing_dd else "normal")
    m5.metric("Daily Loss Breaches", f"{n_daily_breach}/{total_days}")
    m6.metric("Max Contracts", f"{max_contracts_reached}")

    # ── Survival verdict ─────────────────────────────────────────────────────
    if first_dd_breach:
        st.error(
            f"Account **blown on {first_dd_breach}** — trailing DD hit "
            f"${worst_dd:,.0f} (limit -${max_trailing_dd:,.0f}).")
    elif n_daily_breach > 0:
        st.warning(
            f"Account survives trailing DD but **hit daily loss limit on "
            f"{n_daily_breach} day(s)**. Worst day: ${worst_day:,.0f}.")
    else:
        cushion = abs(max_trailing_dd) - abs(worst_dd)
        st.success(
            f"Account survives. Worst trailing DD: ${worst_dd:,.0f} "
            f"(${cushion:,.0f} cushion). No daily loss breaches.")

    # ── Charts ───────────────────────────────────────────────────────────────
    dates = pd.to_datetime(daily["Date"])

    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=[
            "Account Balance (with scaling)",
            "Daily P&L",
            "EOD Trailing Drawdown",
            "Contracts per Trade",
        ],
        row_heights=[0.3, 0.25, 0.25, 0.2],
        shared_xaxes=True, vertical_spacing=0.05)

    # Row 1: Balance curve
    fig.add_trace(go.Scatter(
        x=dates, y=daily["eod_balance"],
        mode="lines", line=dict(color="#4CAF50", width=2),
        name="Balance", showlegend=False,
    ), row=1, col=1)
    fig.add_hline(y=starting_balance, line_dash="dot", line_color="#666",
        annotation_text="Starting balance", row=1, col=1)

    # Row 2: Daily P&L bars
    bar_colors = [
        "#c62828" if v <= -max_daily_loss else
        "#ef5350" if v < 0 else "#66bb6a"
        for v in daily["daily_pnl"]
    ]
    fig.add_trace(go.Bar(
        x=dates, y=daily["daily_pnl"],
        marker_color=bar_colors, showlegend=False,
    ), row=2, col=1)
    fig.add_hline(y=-max_daily_loss, line_dash="dash", line_color="#ff5252",
        annotation_text=f"-${max_daily_loss:,.0f}", row=2, col=1)

    # Row 3: EOD trailing DD
    fig.add_trace(go.Scatter(
        x=dates, y=daily["eod_dd"],
        fill="tozeroy", fillcolor="rgba(198,40,40,0.15)",
        line=dict(color="#ef5350", width=1.5),
        showlegend=False,
    ), row=3, col=1)
    # Also show intraday DD as a lighter area
    fig.add_trace(go.Scatter(
        x=dates, y=daily["Intraday DD"],
        mode="lines", line=dict(color="#ff8a80", width=1, dash="dot"),
        name="Intraday worst", showlegend=False,
    ), row=3, col=1)
    fig.add_hline(y=-max_trailing_dd, line_dash="dash", line_color="#ff5252",
        annotation_text=f"-${max_trailing_dd:,.0f}", row=3, col=1)

    # Row 4: Contracts per trade over time
    fig.add_trace(go.Scatter(
        x=pd.to_datetime(scaled["ExitTime"]),
        y=scaled["Contracts"],
        mode="lines", line=dict(color="#42A5F5", width=1.5),
        showlegend=False,
    ), row=4, col=1)
    fig.update_yaxes(title_text="Contracts", row=4, col=1)

    fig.update_layout(height=850, margin=dict(t=30, b=30))
    st.plotly_chart(fig, use_container_width=True)

    # ── Losing streaks ───────────────────────────────────────────────────────
    streaks = []
    streak = 0
    for v in daily["daily_pnl"]:
        if v < 0:
            streak += 1
        else:
            if streak > 0:
                streaks.append(streak)
            streak = 0
    if streak > 0:
        streaks.append(streak)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Max losing streak", f"{max(streaks) if streaks else 0} days")
    s2.metric("Avg losing streak", f"{np.mean(streaks):.1f} days" if streaks else "0")
    s3.metric("Losing days", f"{losing_days}/{total_days} "
              f"({100*losing_days/max(total_days,1):.0f}%)")
    s4.metric("Avg daily P&L", f"${daily['daily_pnl'].mean():,.0f}")

    # ── Scaling summary table ────────────────────────────────────────────────
    if scale_interval > 0:
        st.markdown("#### Scaling Steps")
        st.caption(
            f"Starting at {base_contracts} contract(s), adding 1 for every "
            f"${scale_interval:,.0f} in profit above ${starting_balance:,.0f}. "
            f"Max {max_contracts}. Scales back down if balance drops."
        )
        # Show when each contract level was first reached and total trades at each level
        level_stats = scaled.groupby("Contracts").agg(
            trades=("NetPnL", "count"),
            first_date=("ExitTime", "min"),
            last_date=("ExitTime", "max"),
            net_pnl=("NetPnL", "sum"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            avg_r=("R_achieved", "mean"),
        ).reset_index()
        level_stats["Win%"] = (100 * level_stats["wins"] / level_stats["trades"]).round(1)
        level_stats["Exp $"] = (level_stats["net_pnl"] / level_stats["trades"]).round(0)
        level_stats["First"] = level_stats["first_date"].dt.strftime("%Y-%m-%d")
        level_stats["Last"] = level_stats["last_date"].dt.strftime("%Y-%m-%d")
        level_stats = level_stats.rename(columns={
            "Contracts": "Contracts", "trades": "Trades",
            "net_pnl": "Net PnL", "avg_r": "Avg R",
        })
        display_cols = ["Contracts", "Trades", "Win%", "Net PnL", "Exp $",
                        "Avg R", "First", "Last"]
        display_cols = [c for c in display_cols if c in level_stats.columns]
        st.dataframe(
            level_stats[display_cols].style.format({
                "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}",
                "Avg R": "{:.3f}", "Win%": "{:.1f}%",
            }),
            use_container_width=True, hide_index=True)

    # ── Daily detail table ───────────────────────────────────────────────────
    with st.expander("📋 Daily P&L Detail", expanded=False):
        display = daily[[
            "Date", "trades", "wins", "Win%", "daily_pnl",
            "eod_balance", "eod_dd", "Intraday DD",
            "min_contracts", "max_contracts_day",
            "Daily Loss Breach",
        ]].copy()
        display.columns = [
            "Date", "Trades", "Wins", "Win%", "Daily PnL",
            "EOD Balance", "EOD DD", "Intraday DD",
            "Min Contracts", "Max Contracts",
            "Loss Breach",
        ]
        display["Date"] = display["Date"].astype(str)

        def _row_color(row):
            if row["Loss Breach"]:
                return ["background-color: rgba(198,40,40,0.3)"] * len(row)
            if row["Daily PnL"] < 0:
                return ["background-color: rgba(198,40,40,0.1)"] * len(row)
            return [""] * len(row)

        styled = display.style.apply(_row_color, axis=1).format({
            "Daily PnL": "${:,.0f}", "EOD Balance": "${:,.0f}",
            "EOD DD": "${:,.0f}", "Intraday DD": "${:,.0f}",
            "Win%": "{:.1f}%",
        })
        st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Per-trade detail ─────────────────────────────────────────────────────
    with st.expander("📋 Per-Trade Detail (with scaling)", expanded=False):
        trade_display = scaled[[
            "ExitTime", "Direction", "SignalType", "Contracts",
            "GrossPnLPts", "NetPnL", "Balance", "TrailingDD", "R_achieved",
        ]].copy()
        trade_display["ExitTime"] = trade_display["ExitTime"].dt.strftime(
            "%Y-%m-%d %H:%M")
        trade_display.columns = [
            "Exit Time", "Dir", "Setup", "Contracts",
            "Gross Pts", "Net PnL", "Balance", "Trailing DD", "R",
        ]
        st.dataframe(
            trade_display.style.format({
                "Gross Pts": "{:.2f}", "Net PnL": "${:,.0f}",
                "Balance": "${:,.0f}", "Trailing DD": "${:,.0f}",
                "R": "{:.3f}",
            }),
            use_container_width=True, hide_index=True)
