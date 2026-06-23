"""Prop Firm Simulator — sequential walk-through of BA trades with realistic
account rules: starting balance, contract scaling, daily loss cutoff, trailing
DD blow-up, max trades per day, periodic 80/20 payouts, subscription/reset costs.

Trades that violate limits are SKIPPED, so the equity path reflects what a real
prop account would experience.

Key modelling choices (deliberately conservative):
  • Trailing DD is measured on TRADING EQUITY (start + cumulative net P&L).
    Withdrawals are a separate cash flow and do NOT trigger the DD — otherwise a
    payout would phantom-blow the account.
  • Contract scaling keys off ACCOUNT BALANCE (start + net − withdrawn), so once
    you cash out your excess you automatically size back down.
  • Daily loss limit: the trade that trips it is taken (it filled in real life),
    then the rest of the day is locked out.
  • Live-vs-backtest haircut is ASYMMETRIC: winners ×(1−x), losers ×(1+x) — it
    must worsen drawdowns, not flatter them.
  • Payout buffer = Monte-Carlo 99th-pct dollar drawdown at max contracts; we
    never withdraw the account below start + buffer.
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

INSTRUMENTS = {
    "ES":  {"tick_value": 12.50, "margin": 500.0},
    "MES": {"tick_value": 1.25,  "margin": 50.0},
}

DIR_MAP = {1: "Long", -1: "Short", "Long": "Long", "Short": "Short"}


def _trade_pts(t) -> float:
    """Per-trade gross P&L in points at 1 contract (with the same fallback the
    old engine used: derive from R × RiskPts when GrossPnLPts is missing)."""
    g = t.get("GrossPnLPts", 0)
    if pd.isna(g) or g == 0:
        r = t.get("R_achieved", np.nan)
        rk = t.get("RiskPts", np.nan)
        if pd.notna(r) and pd.notna(rk) and rk > 0:
            return float(r * rk)
        return np.nan
    return float(g)


def _haircut_gross(gross: np.ndarray, haircut: float) -> np.ndarray:
    """Asymmetric live haircut: shrink wins, deepen losses. Conservative."""
    if haircut <= 0:
        return gross
    return np.where(gross >= 0, gross * (1.0 - haircut), gross * (1.0 + haircut))


def _net_dollars(pts: np.ndarray, contracts, cfg) -> np.ndarray:
    """Vectorised per-trade net $ for a given (scalar or array) contract count."""
    ticks = np.asarray(pts, dtype=float) / 0.25
    gross = ticks * cfg["tick_value"] * contracts
    gross = _haircut_gross(gross, cfg["haircut"])
    return gross - cfg["commission"] * contracts


# ─────────────────────────────────────────────────────────────────────────────
# Monte-Carlo: payout buffer, suggested scale interval, blow-up probability
# ─────────────────────────────────────────────────────────────────────────────

def _mc_analysis(pts: np.ndarray, cfg: dict) -> dict | None:
    """Moving-block bootstrap of the trade sequence.

    Returns the dollar drawdown distribution at 1 contract and at max contracts,
    from which we derive:
      • buffer            — 99th-pct (configurable) worst $ DD at max contracts
      • per_contract_dd   — same percentile $ DD at 1 contract
      • suggested_interval— per_contract_dd × safety_mult (rounded to $250)
      • blowup_prob       — P(trailing DD breach) at max contracts from start
    """
    pts = pts[~np.isnan(pts)]
    n = len(pts)
    if n < 20:
        return None

    rng = np.random.default_rng(42)
    block = max(1, int(cfg["mc_block"]))
    n_iter = max(100, int(cfg["mc_iter"]))
    maxc = cfg["max_contracts"]
    start = cfg["starting_balance"]
    tdd = cfg["max_trailing_dd"]
    dd_lock = cfg["dd_lock_at_start"]

    net1 = _net_dollars(pts, 1, cfg)
    netmax = _net_dollars(pts, maxc, cfg)

    shock_d = cfg.get("shock_dollars_1c", 0.0)
    shock_p = cfg.get("shock_prob", 0.0)

    n_blocks = int(math.ceil(n / block))
    offsets = np.arange(block)

    dd1 = np.empty(n_iter)
    ddmax = np.empty(n_iter)
    blow = 0

    for i in range(n_iter):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + offsets[None, :]).ravel() % n
        idx = idx[:n]

        s1 = net1[idx]
        sm = netmax[idx]

        # Inject shock events (adverse gap beyond stop) at the chosen frequency
        if shock_p > 0 and shock_d > 0:
            shk = rng.random(n) < shock_p
            s1 = s1 - shk * shock_d
            sm = sm - shk * shock_d * maxc

        eq1 = np.cumsum(s1)
        dd1[i] = float((eq1 - np.maximum.accumulate(eq1)).min())

        eqm = np.cumsum(sm)
        ddmax[i] = float((eqm - np.maximum.accumulate(eqm)).min())

        # Blow-up check at max contracts, no withdrawals, from start
        equity = start + eqm
        peak = np.maximum.accumulate(equity)
        if dd_lock and tdd > 0:
            peak = np.minimum(peak, start + tdd)
        trail = equity - peak
        if tdd > 0 and trail.min() <= -tdd:
            blow += 1

    q = 100.0 - cfg["buffer_pct"]            # e.g. 99th-pct worst → 1st percentile of signed DD
    buffer = float(-np.percentile(ddmax, q))
    per_contract_dd = float(-np.percentile(dd1, q))
    raw_int = per_contract_dd * cfg["scale_safety_mult"]
    suggested_interval = int(math.ceil(raw_int / 250.0) * 250) if raw_int > 0 else 0

    # Worst-ever single-trade loss at 1 contract (after haircut + commission) — the
    # unit the floor de-risk sizes against. Use the empirical max for never-blow.
    worst_trade_1c = float(-net1.min()) if net1.min() < 0 else 0.0

    return {
        "buffer": max(0.0, buffer),
        "per_contract_dd": per_contract_dd,
        "suggested_interval": suggested_interval,
        "blowup_prob": blow / n_iter,
        "dd_samples_max": ddmax,
        "worst_trade_1c": worst_trade_1c,
    }


def _mc_blowup_derisk(pts: np.ndarray, cfg: dict, buffer: float) -> float:
    """Blow-up probability with the floor de-risk rule + contract scaling + shock
    injection applied per trade (sequential). The realistic 'will I ever blow'
    figure, vs the vectorised flat-max-contracts worst-case bound."""
    pts = pts[~np.isnan(pts)]
    n = len(pts)
    if n < 20:
        return 0.0

    rng = np.random.default_rng(123)
    block = max(1, int(cfg["mc_block"]))
    n_iter = max(100, int(cfg["mc_iter"]))
    start = cfg["starting_balance"]
    tdd = cfg["max_trailing_dd"]
    dd_lock = cfg["dd_lock_at_start"]
    maxc = cfg["max_contracts"]
    base_c = cfg["base_contracts"]
    scale_int = cfg["scale_interval"]
    margin = cfg["margin"]
    unit = cfg.get("worst_trade_1c", 0.0)
    cover_n = cfg["derisk_cover_n"]
    shock_d = cfg.get("shock_dollars_1c", 0.0)
    shock_p = cfg.get("shock_prob", 0.0)

    net1 = _net_dollars(pts, 1, cfg)
    n_blocks = int(math.ceil(n / block))
    offsets = np.arange(block)
    blow = 0

    for _ in range(n_iter):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + offsets[None, :]).ravel() % n
        idx = idx[:n]
        seq = net1[idx]
        shk = (rng.random(n) < shock_p) if shock_p > 0 else np.zeros(n, dtype=bool)

        cum = 0.0
        peak = start
        blew = False
        for j in range(n):
            equity = start + cum
            pa = cum
            c = base_c + int(pa // scale_int) if (scale_int > 0 and pa > 0) else base_c
            c = max(base_c, min(c, maxc))
            if margin > 0:
                c = min(c, int(equity // margin))
            if tdd > 0 and unit > 0:
                headroom = equity - (peak - tdd)
                denom = unit * cover_n
                ms = int(headroom // denom) if denom > 0 else c
                if ms < 1:
                    continue          # too close to floor → skip, stay flat
                if ms < c:
                    c = ms
            c = max(1, c)
            pnl = seq[j] * c - (shock_d * c if shk[j] else 0.0)
            cum += pnl
            equity = start + cum
            peak = max(peak, equity)
            if dd_lock and tdd > 0:
                peak = min(peak, start + tdd)
            if tdd > 0 and (equity - peak) <= -tdd:
                blew = True
                break
        if blew:
            blow += 1

    return blow / n_iter


# ─────────────────────────────────────────────────────────────────────────────
# Core sequential simulator
# ─────────────────────────────────────────────────────────────────────────────

def _run_prop_sim(trades: pd.DataFrame, cfg: dict, buffer: float) -> dict:
    """Walk trades chronologically applying all prop rules + monthly payouts."""
    start = cfg["starting_balance"]
    max_daily_loss = cfg["max_daily_loss"]
    tdd = cfg["max_trailing_dd"]
    dd_lock = cfg["dd_lock_at_start"]
    base_c = cfg["base_contracts"]
    scale_int = cfg["scale_interval"]
    max_c = cfg["max_contracts"]
    max_trades_day = cfg["max_trades_day"]
    count_per_dir = cfg["count_per_dir"]
    margin = cfg["margin"]
    split = cfg["profit_split"]
    min_days = cfg["min_trading_days"]
    min_payout = cfg["min_payout"]
    consistency = cfg["consistency_pct"]
    sub_fee = cfg["subscription_fee"]
    reset_fee = cfg["reset_fee"]
    restart = cfg["restart_after_blowup"]
    floor = start + max(0.0, buffer)

    cum_net = 0.0
    withdrawn = 0.0
    peak_equity = start
    blown = False
    blown_date = None
    reset_count = 0

    # Daily state
    current_date = None
    current_month = None
    day_pnl = 0.0
    day_long = 0
    day_short = 0
    day_breached = False

    # Payout / cost state
    take_home = 0.0
    firm_cut = 0.0
    sub_total = 0.0
    reset_total = 0.0
    trading_days = 0
    period_day_pnls = []          # day P&Ls accrued since last settle
    first_payout_done = False
    payouts = []

    # Worst-DD tracking
    worst_trail = 0.0
    worst_trail_date = None
    worst_trail_tradeidx = 0
    derisk_capped = 0

    rows = []
    skipped = {"daily_loss": 0, "max_trades": 0, "blown": 0,
               "zero_risk": 0, "margin": 0, "direction": 0, "derisk": 0}

    def settle_month(label):
        """Pay subscription, then attempt a payout for the just-completed month."""
        nonlocal cum_net, withdrawn, take_home, firm_cut, sub_total
        nonlocal first_payout_done
        sub_total += sub_fee
        period_profit = sum(period_day_pnls)
        violation = (
            consistency > 0 and period_profit > 0 and period_day_pnls
            and max(period_day_pnls) > (consistency / 100.0) * period_profit
        )
        eligible = trading_days >= min_days
        acct = start + cum_net - withdrawn
        withdrawable = max(0.0, acct - floor)
        paid = 0.0
        deferred = None
        if not eligible:
            deferred = "min-days"
        elif violation:
            deferred = "consistency"
        elif withdrawable < min_payout or withdrawable <= 0:
            deferred = "below-min" if withdrawable > 0 else None
        else:
            paid = withdrawable
            withdrawn += paid
            take_home += split * paid
            firm_cut += (1.0 - split) * paid
            first_payout_done = True
        payouts.append({
            "Month": label,
            "AcctBefore": acct,
            "Withdrawable": withdrawable,
            "Paid": paid,
            "TakeHome": split * paid,
            "AcctAfter": start + cum_net - withdrawn,
            "Deferred": deferred or "",
            "ConsistencyOK": not violation,
        })
        period_day_pnls.clear()

    for ti, (_, t) in enumerate(trades.iterrows()):
        trade_date = (t["ExitTime"].date() if pd.notna(t.get("ExitTime"))
                      else t["DateTime"].date())
        direction = DIR_MAP.get(t.get("Direction"), "Unknown")
        month = (trade_date.year, trade_date.month)

        # Month rollover → settle the previous month
        if current_month is not None and month != current_month:
            settle_month(f"{current_month[0]}-{current_month[1]:02d}")
        current_month = month

        # New day
        if trade_date != current_date:
            if current_date is not None:
                period_day_pnls.append(day_pnl)
            current_date = trade_date
            trading_days += 1
            day_pnl = 0.0
            day_long = 0
            day_short = 0
            day_breached = False

        # Direction filter
        if cfg["direction_filter"] != "Both" and direction != cfg["direction_filter"]:
            skipped["direction"] += 1
            continue

        if blown:
            skipped["blown"] += 1
            continue

        if day_breached:
            skipped["daily_loss"] += 1
            continue

        # Max trades / day
        if max_trades_day > 0:
            if count_per_dir:
                if direction == "Long" and day_long >= max_trades_day:
                    skipped["max_trades"] += 1
                    continue
                if direction == "Short" and day_short >= max_trades_day:
                    skipped["max_trades"] += 1
                    continue
            elif (day_long + day_short) >= max_trades_day:
                skipped["max_trades"] += 1
                continue

        # Contracts: profit-scaled (on account balance), capped, margin-limited
        acct = start + cum_net - withdrawn
        profit_above = acct - start
        if scale_int > 0 and profit_above > 0:
            contracts = base_c + int(profit_above // scale_int)
        else:
            contracts = base_c
        contracts = max(base_c, min(contracts, max_c))
        if margin > 0:
            affordable = int(acct // margin)
            if affordable < 1:
                skipped["margin"] += 1
                continue
            contracts = min(contracts, affordable)

        # ── Floor de-risk (never-blow sizing) ───────────────────────────────
        # Cap size so N worst-ever single-trade losses still fit inside the
        # headroom between current trading equity and the blow level. May size
        # below base near the floor; skips the trade if even 1 contract is unsafe.
        if cfg.get("derisk_floor") and tdd > 0 and cfg.get("worst_trade_1c", 0) > 0:
            trade_equity_pre = start + cum_net
            blow_level = peak_equity - tdd
            headroom = trade_equity_pre - blow_level
            unit = cfg["worst_trade_1c"] * cfg["derisk_cover_n"]
            max_safe = int(headroom // unit) if unit > 0 else contracts
            if max_safe < 1:
                skipped["derisk"] += 1
                continue
            if max_safe < contracts:
                contracts = max_safe
                derisk_capped += 1

        contracts = max(1, contracts)

        # P&L
        pts = t["pts"] if "pts" in t else _trade_pts(t)
        if pd.isna(pts):
            skipped["zero_risk"] += 1
            continue
        net_pnl = float(_net_dollars(np.array([pts]), contracts, cfg)[0])

        # Apply
        cum_net += net_pnl
        day_pnl += net_pnl
        if direction == "Long":
            day_long += 1
        else:
            day_short += 1

        trade_equity = start + cum_net
        account_balance = trade_equity - withdrawn
        peak_equity = max(peak_equity, trade_equity)
        if dd_lock and tdd > 0:
            peak_equity = min(peak_equity, start + tdd)
        trailing_dd = trade_equity - peak_equity

        if trailing_dd < worst_trail:
            worst_trail = trailing_dd
            worst_trail_date = trade_date
            worst_trail_tradeidx = len(rows) + 1

        if max_daily_loss > 0 and day_pnl <= -max_daily_loss:
            day_breached = True

        if tdd > 0 and trailing_dd <= -tdd:
            blown = True
            blown_date = trade_date
            reset_count += 1
            reset_total += reset_fee
            if restart:
                # Fresh account; keep accumulating costs/payouts history
                period_day_pnls.append(day_pnl)
                cum_net = 0.0
                withdrawn = 0.0
                peak_equity = start
                blown = False
                day_breached = True   # no more trades this day after a reset

        rows.append({
            "DateTime": t["DateTime"],
            "ExitTime": t["ExitTime"],
            "Date": trade_date,
            "Direction": direction,
            "SignalType": t.get("SignalType", ""),
            "Contracts": contracts,
            "GrossPnLPts": pts,
            "NetPnL": net_pnl,
            "Equity": trade_equity,
            "Balance": account_balance,
            "Peak": peak_equity,
            "TrailingDD": trailing_dd,
            "DayPnL": day_pnl,
            "DayTradeNum": day_long + day_short,
            "DailyLossBreach": day_breached,
            "AccountBlown": blown,
            "Withdrawn": withdrawn,
            "R_achieved": t.get("R_achieved", np.nan),
            "RiskPts": t.get("RiskPts", np.nan),
        })

    # Final settle (last partial month)
    if current_date is not None:
        period_day_pnls.append(day_pnl)
    if current_month is not None:
        settle_month(f"{current_month[0]}-{current_month[1]:02d}")

    trades_df = pd.DataFrame(rows) if rows else pd.DataFrame()

    daily_df = pd.DataFrame()
    if not trades_df.empty:
        daily_df = trades_df.groupby("Date").agg(
            trades=("NetPnL", "count"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            daily_pnl=("DayPnL", "last"),
            eod_balance=("Balance", "last"),
            eod_equity=("Equity", "last"),
            eod_peak=("Peak", "last"),
            eod_trailing_dd=("TrailingDD", "last"),
            min_contracts=("Contracts", "min"),
            max_contracts=("Contracts", "max"),
            daily_loss_breach=("DailyLossBreach", "last"),
            account_blown=("AccountBlown", "last"),
        ).reset_index()
        daily_df["Win%"] = (100 * daily_df["wins"] / daily_df["trades"]).round(1)
        intra = trades_df.groupby("Date")["TrailingDD"].min().reset_index()
        intra.columns = ["Date", "IntradayDD"]
        daily_df = daily_df.merge(intra, on="Date", how="left")

    acct_final = start + cum_net - withdrawn
    unrealized = split * max(0.0, acct_final - start)
    net_to_trader = take_home + unrealized - sub_total - reset_total

    return {
        "trades_df": trades_df,
        "daily_df": daily_df,
        "blown": blown,
        "blown_date": blown_date,
        "skipped": skipped,
        "payouts": pd.DataFrame(payouts) if payouts else pd.DataFrame(),
        "take_home": take_home,
        "firm_cut": firm_cut,
        "sub_total": sub_total,
        "reset_total": reset_total,
        "reset_count": reset_count,
        "withdrawn": withdrawn,
        "unrealized": unrealized,
        "net_to_trader": net_to_trader,
        "acct_final": acct_final,
        "worst_trail": worst_trail,
        "worst_trail_date": worst_trail_date,
        "worst_trail_tradeidx": worst_trail_tradeidx,
        "derisk_capped": derisk_capped,
        "buffer": buffer,
        "floor": floor,
    }


def _start_date_sensitivity(trades: pd.DataFrame, cfg: dict, buffer: float) -> pd.DataFrame:
    """Re-run the deterministic sim starting from each calendar month; show how
    much the outcome depends on where you happened to begin."""
    months = sorted(trades["_startm"].unique())
    rows = []
    for m in months:
        sub = trades[trades["_startm"] >= m]
        if len(sub) < 30:
            continue
        r = _run_prop_sim(sub, cfg, buffer)
        rows.append({
            "Start": str(m),
            "Trades": len(r["trades_df"]),
            "Blown": "Yes" if r["blown"] else "No",
            "Net to Trader": r["net_to_trader"],
            "Take-Home": r["take_home"],
            "Worst DD": r["worst_trail"],
        })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────────────────

def show_prop_sim_tab():
    st.header("🏢 Prop Firm Simulator")
    st.caption(
        "Sequential walk-through of BA trades with prop firm rules, monthly "
        "80/20 payouts, and Monte-Carlo risk sizing. Trades that violate limits "
        "are **skipped** — the path reflects a real prop account."
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
    filled["pts"] = filled.apply(_trade_pts, axis=1)
    filled["_startm"] = pd.to_datetime(filled["ExitTime"]).dt.to_period("M")

    # ── Configuration ────────────────────────────────────────────────────────
    st.subheader("Account Rules")
    c1, c2, c3, c4, c5 = st.columns(5)
    instrument = c1.selectbox("Instrument", ["ES", "MES"], key="ps_instr",
                              help="Sets tick value + per-contract day margin.")
    inst = INSTRUMENTS[instrument]
    starting_balance = c2.number_input(
        "Starting balance ($)", value=50_000, step=5_000, key="ps_start_bal")
    max_daily_loss = c3.number_input(
        "Max daily loss ($)", value=2_000, step=250, key="ps_daily_loss",
        help="0 = no limit. The trade that trips it is taken, then the day locks out.")
    max_trailing_dd = c4.number_input(
        "Max trailing DD ($)", value=3_000, step=250, key="ps_trailing_dd",
        help="0 = no limit. Account blown when trailing DD (on trading equity) exceeds this.")
    max_trades_day = c5.number_input(
        "Max trades/day", value=0, step=1, key="ps_max_trades", help="0 = unlimited")

    cc1, cc2, cc3 = st.columns(3)
    direction_filter = cc1.radio("Direction", ["Both", "Long", "Short"],
                                 horizontal=True, key="ps_dir")
    dd_lock_at_start = cc2.checkbox(
        "Lock DD at starting balance", value=True, key="ps_dd_lock",
        help="Trailing DD stops trailing once the threshold reaches the starting "
             "balance, then locks there. Off = trails indefinitely.")
    count_per_dir = cc3.checkbox(
        "Max trades per direction", value=False, key="ps_per_dir",
        help="Max trades counted per direction (N longs + N shorts).")

    st.subheader("Contract Scaling")
    s1, s2, s3, s4 = st.columns(4)
    base_contracts = s1.number_input(
        "Base contracts", value=1, min_value=1, step=1, key="ps_base_c")
    scale_interval = s2.number_input(
        "Scale every $ profit", value=2_500, step=500, key="ps_scale_int",
        help="Add 1 contract per $X profit above start. 0 = no scaling. "
             "See the suggested interval after a run.")
    max_contracts = s3.number_input(
        "Max contracts", value=10, min_value=1, step=1, key="ps_max_c")
    commission = s4.number_input(
        "Commission RT ($/c)", value=4.36, step=0.50, key="ps_comm")

    with st.expander("💸 Payouts, Costs & Conservatism", expanded=False):
        p1, p2, p3, p4 = st.columns(4)
        profit_split = p1.number_input(
            "Your split (%)", value=80, min_value=0, max_value=100, step=5,
            key="ps_split", help="Your share of each withdrawal. Firm keeps the rest.")
        min_trading_days = p2.number_input(
            "Min trading days before payout", value=10, step=1, key="ps_min_days")
        min_payout = p3.number_input(
            "Min payout ($)", value=500, step=100, key="ps_min_payout")
        consistency_pct = p4.number_input(
            "Consistency rule (% of profit)", value=0, step=5, key="ps_consistency",
            help="Defer a payout if any single day exceeds this % of the period's "
                 "profit. 0 = off.")

        h1, h2, h3, h4 = st.columns(4)
        haircut_pct = h1.number_input(
            "Live haircut (%)", value=0.0, step=1.0, key="ps_haircut",
            help="Models live worse than backtest. Asymmetric: shrinks wins, "
                 "deepens losses. Keep small/0 if BA already ran under ESA.")
        subscription_fee = h2.number_input(
            "Monthly subscription ($)", value=0, step=10, key="ps_sub")
        reset_fee = h3.number_input(
            "Reset fee on blow-up ($)", value=0, step=50, key="ps_reset_fee")
        restart_after_blowup = h4.checkbox(
            "Restart after blow-up", value=False, key="ps_restart",
            help="Reset to start (charging the reset fee) and keep trading. "
                 "Off = stop at first blow-up.")

        m1, m2, m3, m4 = st.columns(4)
        buffer_pct = m1.number_input(
            "Buffer percentile", value=99, min_value=50, max_value=100, step=1,
            key="ps_buf_pct", help="Withdrawal floor = start + this percentile of "
                                    "the MC drawdown distribution at max contracts.")
        scale_safety_mult = m2.number_input(
            "Scale safety ×", value=1.0, min_value=0.5, step=0.25, key="ps_scale_mult",
            help="Multiplier on per-contract MC DD for the suggested scale interval.")
        mc_iter = m3.number_input(
            "MC iterations", value=2000, min_value=200, step=500, key="ps_mc_iter")
        mc_block = m4.number_input(
            "MC block size (trades)", value=10, min_value=1, step=1, key="ps_mc_block",
            help="Moving-block bootstrap block — preserves streak clustering.")

        d1, d2 = st.columns(2)
        derisk_floor = d1.checkbox(
            "🛡️ De-risk near floor (never-blow sizing)", value=False, key="ps_derisk",
            help="Cap contracts so N worst-ever single-trade losses still fit between "
                 "current equity and the blow level. Sizes below base near the floor; "
                 "skips a trade if even 1 contract is unsafe. Asymmetric: cuts fast on "
                 "the way down, scales up only on the normal profit interval.")
        derisk_cover_n = d2.number_input(
            "Cover N worst trades", value=3, min_value=1, step=1, key="ps_derisk_n",
            help="Headroom to the blow level must cover this many worst-ever single-trade "
                 "losses at the current contract size.")

        sh1, sh2 = st.columns(2)
        shock_pts = sh1.number_input(
            "Shock size (points)", value=0.0, step=5.0, key="ps_shock_pts",
            help="Assumed worst-case adverse gap beyond your stop, in points "
                 f"(ES: 1pt=${INSTRUMENTS['ES']['tick_value']/0.25:.0f}/c, "
                 f"MES: 1pt=${INSTRUMENTS['MES']['tick_value']/0.25:.0f}/c). "
                 "Feeds the de-risk unit AND is injected into the Monte-Carlo. 0 = off.")
        shock_freq_n = sh2.number_input(
            "Shock once per N trading days", value=500, min_value=1, step=50,
            key="ps_shock_freq",
            help="How often such a shock occurs. 500 ≈ once per ~2 years. Sets the "
                 "per-trade injection probability for the MC buffer + blow-up %.")

    # ── Run ──────────────────────────────────────────────────────────────────
    if st.button("▶ Run Prop Sim", key="ps_run", type="primary"):
        cfg = {
            "starting_balance": starting_balance,
            "max_daily_loss": max_daily_loss,
            "max_trailing_dd": max_trailing_dd,
            "dd_lock_at_start": dd_lock_at_start,
            "base_contracts": base_contracts,
            "scale_interval": scale_interval,
            "max_contracts": max_contracts,
            "max_trades_day": max_trades_day,
            "count_per_dir": count_per_dir,
            "tick_value": inst["tick_value"],
            "margin": inst["margin"],
            "instrument": instrument,
            "commission": commission,
            "direction_filter": direction_filter,
            "profit_split": profit_split / 100.0,
            "min_trading_days": min_trading_days,
            "min_payout": min_payout,
            "consistency_pct": consistency_pct,
            "haircut": haircut_pct / 100.0,
            "subscription_fee": subscription_fee,
            "reset_fee": reset_fee,
            "restart_after_blowup": restart_after_blowup,
            "buffer_pct": buffer_pct,
            "scale_safety_mult": scale_safety_mult,
            "mc_iter": mc_iter,
            "mc_block": mc_block,
            "derisk_floor": derisk_floor,
            "derisk_cover_n": derisk_cover_n,
            "shock_freq_n": shock_freq_n,
        }
        with st.spinner("Monte-Carlo sizing + walk-through..."):
            sub = filled
            if direction_filter != "Both":
                sub = filled[filled["Direction"].map(DIR_MAP) == direction_filter]
            pts_arr = sub["pts"].values.astype(float)
            valid = pts_arr[~np.isnan(pts_arr)]
            n_days = pd.to_datetime(sub["ExitTime"]).dt.date.nunique()
            avg_tpd = len(valid) / max(n_days, 1)

            cfg["shock_pts"] = shock_pts
            cfg["shock_dollars_1c"] = shock_pts * cfg["tick_value"] / 0.25
            cfg["shock_prob"] = (1.0 / (avg_tpd * shock_freq_n)
                                 if (shock_pts > 0 and shock_freq_n > 0 and avg_tpd > 0)
                                 else 0.0)

            mc = _mc_analysis(pts_arr, cfg)
            buffer = mc["buffer"] if mc else 0.0
            hist_worst = mc["worst_trade_1c"] if mc else 0.0
            cfg["hist_worst_1c"] = hist_worst
            cfg["worst_trade_1c"] = max(hist_worst, cfg["shock_dollars_1c"])

            if cfg["derisk_floor"] and mc:
                mc = dict(mc)
                mc["blowup_prob_derisk"] = _mc_blowup_derisk(pts_arr, cfg, buffer)

            result = _run_prop_sim(filled, cfg, buffer)
            sens = _start_date_sensitivity(filled, cfg, buffer)
        st.session_state["ps_result"] = result
        st.session_state["ps_cfg"] = cfg
        st.session_state["ps_mc"] = mc
        st.session_state["ps_sens"] = sens

    result = st.session_state.get("ps_result")
    cfg = st.session_state.get("ps_cfg")
    mc = st.session_state.get("ps_mc")
    sens = st.session_state.get("ps_sens")
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

    start = cfg["starting_balance"]
    max_daily = cfg["max_daily_loss"]
    max_dd = cfg["max_trailing_dd"]

    # ── Headline ─────────────────────────────────────────────────────────────
    st.markdown("---")
    total_trades = len(trades_df)
    total_skipped = sum(skipped.values())
    worst_dd = result["worst_trail"]
    worst_day = daily_df["daily_pnl"].min() if not daily_df.empty else 0
    max_c_reached = int(trades_df["Contracts"].max())
    n_breach_days = daily_df["daily_loss_breach"].sum() if not daily_df.empty else 0
    wins = (trades_df["NetPnL"] > 0).sum()

    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.metric("Net to Trader", f"${result['net_to_trader']:,.0f}",
              help="Take-home payouts + unrealized 80% − subscription − reset costs.")
    h2.metric("Take-Home (paid)", f"${result['take_home']:,.0f}",
              delta=f"{len(result['payouts'][result['payouts']['Paid'] > 0]) if not result['payouts'].empty else 0} payouts")
    h3.metric("Account Equity", f"${result['acct_final']:,.0f}",
              delta=f"${result['acct_final'] - start:+,.0f}")
    h4.metric("Trades Taken", f"{total_trades}",
              delta=f"{total_skipped} skipped" if total_skipped else None)
    h5.metric("Worst Trailing DD", f"${worst_dd:,.0f}")
    h6.metric("Max Contracts", f"{max_c_reached}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    if blown:
        st.error(
            f"💀 Account **BLOWN on {blown_date}** — trailing DD hit ${worst_dd:,.0f} "
            f"(limit -${max_dd:,.0f}). {result['reset_count']} blow-up(s).")
    elif n_breach_days > 0:
        cushion = abs(max_dd) - abs(worst_dd) if max_dd > 0 else float("inf")
        st.warning(
            f"Account survives but hit the daily loss limit on **{int(n_breach_days)} "
            f"day(s)**. Worst trailing DD ${worst_dd:,.0f} (${cushion:,.0f} cushion).")
    else:
        cushion = abs(max_dd) - abs(worst_dd) if max_dd > 0 else float("inf")
        st.success(
            f"✅ Account **survives**. Net to trader +${result['net_to_trader']:,.0f}, "
            f"worst DD ${worst_dd:,.0f} (${cushion:,.0f} cushion).")

    if mc:
        parts = [f"flat max contracts **{100*mc['blowup_prob']:.1f}%**"]
        if "blowup_prob_derisk" in mc:
            parts.append(f"with de-risk **{100*mc['blowup_prob_derisk']:.1f}%**")
        shock_note = ""
        if cfg.get("shock_prob", 0) > 0:
            shock_note = (f" · shock {cfg['shock_pts']:.0f}pt "
                          f"(${cfg['shock_dollars_1c']:,.0f}/c) once/{cfg['shock_freq_n']}d injected")
        st.caption(
            f"🎲 MC blow-up probability — {', '.join(parts)} "
            f"({cfg['mc_iter']:,} paths, block {cfg['mc_block']}).{shock_note}")

    # Engine equity (no withdrawals) for strategy-level stats
    equity = trades_df["NetPnL"].cumsum()
    peak_eq = equity.cummax()
    dd_series = equity - peak_eq
    max_dd_eq = float(dd_series.min())
    total_pnl = float(equity.iloc[-1])

    # ── Quick View (richer) ───────────────────────────────────────────────────
    with st.expander("📋 Quick View", expanded=True):
        losses = (trades_df["NetPnL"] <= 0).sum()
        avg_win = trades_df.loc[trades_df["NetPnL"] > 0, "NetPnL"].mean() if wins else 0
        avg_loss = trades_df.loc[trades_df["NetPnL"] <= 0, "NetPnL"].mean() if losses else 0
        exp_r = trades_df["R_achieved"].mean() if "R_achieved" in trades_df else 0
        trading_days = daily_df["Date"].nunique() if not daily_df.empty else 0

        r_vals = trades_df["R_achieved"].dropna().values
        r_std = float(np.std(r_vals, ddof=1)) if len(r_vals) > 1 else 0.0
        n_sqn = min(total_trades, 100)
        sqn = float(exp_r / r_std * np.sqrt(n_sqn)) if r_std > 0 else 0.0

        pos_pnl = trades_df.loc[trades_df["NetPnL"] > 0, "NetPnL"].sum()
        neg_pnl = trades_df.loc[trades_df["NetPnL"] <= 0, "NetPnL"].sum()
        pf = abs(pos_pnl / neg_pnl) if neg_pnl < 0 else float("inf")
        pnl_dd = total_pnl / abs(max_dd_eq) if max_dd_eq < 0 else float("nan")
        payoff = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")

        # CAGR / Sharpe / MAR on engine equity (gross of withdrawals)
        span_days = max(1, (pd.to_datetime(trades_df["ExitTime"]).iloc[-1]
                            - pd.to_datetime(trades_df["ExitTime"]).iloc[0]).days)
        years = span_days / 365.25
        gross_growth = (start + total_pnl) / start if start > 0 else np.nan
        cagr = (gross_growth ** (1 / years) - 1) if years > 0 and gross_growth > 0 else np.nan
        dly = daily_df["daily_pnl"]
        sharpe = (dly.mean() / dly.std() * np.sqrt(252)) if dly.std() > 0 else np.nan
        mdd_pct = abs(max_dd_eq) / start if start > 0 else np.nan
        mar = (cagr / mdd_pct) if mdd_pct and not np.isnan(cagr) and mdd_pct > 0 else np.nan

        q1, q2, q3, q4, q5, q6 = st.columns(6)
        q1.metric("Strategy Net PnL", f"${total_pnl:,.0f}")
        q2.metric("Win%", f"{100*wins/max(total_trades,1):.1f}%")
        q3.metric("PF", f"{pf:.2f}")
        q4.metric("Exp $", f"${total_pnl/max(total_trades,1):,.0f}")
        q5.metric("Max DD", f"${max_dd_eq:,.0f}")
        q6.metric("PnL/DD", f"{pnl_dd:.2f}" if not np.isnan(pnl_dd) else "—")

        q7, q8, q9, q10, q11, q12 = st.columns(6)
        q7.metric("CAGR", f"{100*cagr:.1f}%" if not np.isnan(cagr) else "—")
        q8.metric("Sharpe", f"{sharpe:.2f}" if not np.isnan(sharpe) else "—")
        q9.metric("MAR", f"{mar:.2f}" if mar and not np.isnan(mar) else "—")
        q10.metric("Payoff", f"{payoff:.2f}" if payoff != float('inf') else "∞")
        q11.metric("Exp R", f"{exp_r:.3f}")
        q12.metric("SQN", f"{sqn:.1f}")

        q13, q14, q15, q16, q17, q18 = st.columns(6)
        q13.metric("Trades", f"{total_trades}")
        q14.metric("Avg Win", f"${avg_win:,.0f}")
        q15.metric("Avg Loss", f"${avg_loss:,.0f}")
        q16.metric("Largest Win", f"${trades_df['NetPnL'].max():,.0f}")
        q17.metric("Largest Loss", f"${trades_df['NetPnL'].min():,.0f}")
        q18.metric("Days", f"{trading_days}")

    # ── Prop-specific metrics ─────────────────────────────────────────────────
    with st.expander("🏦 Prop Metrics", expanded=True):
        pay_df = result["payouts"]
        n_paid = len(pay_df[pay_df["Paid"] > 0]) if not pay_df.empty else 0
        avg_payout = pay_df.loc[pay_df["Paid"] > 0, "Paid"].mean() if n_paid else 0
        margin_at_max = cfg["margin"] * max_c_reached
        worst_idx = result["worst_trail_tradeidx"]
        worst_dt = result["worst_trail_date"]

        pm = {
            "Metric": [
                "Instrument", "Per-contract margin", "Margin at max contracts",
                "Withdrawal floor (start + buffer)", "MC buffer (99-pct DD)",
                "Suggested scale interval", "Current scale interval",
                "MC blow-up probability",
                "Total withdrawn (gross)", "Your take-home (80%)",
                "Firm cut (20%)", "Unrealized take-home",
                "# payouts", "Avg payout", "Subscription paid", "Reset cost",
                "# blow-ups", "Max trailing DD", "Max DD at trade #", "Max DD date",
                "Floor de-risk", "Shock assumption", "Shock $ / contract",
                "Hist. worst trade (1c)", "Effective de-risk unit (1c)",
                "Blow-up % (de-risk)", "Trades de-risked",
            ],
            "Value": [
                cfg["instrument"],
                f"${cfg['margin']:,.0f}",
                f"${margin_at_max:,.0f}",
                f"${result['floor']:,.0f}",
                f"${result['buffer']:,.0f}",
                f"${mc['suggested_interval']:,.0f}" if mc else "—",
                f"${cfg['scale_interval']:,.0f}",
                f"{100*mc['blowup_prob']:.1f}%" if mc else "—",
                f"${result['withdrawn']:,.0f}",
                f"${result['take_home']:,.0f}",
                f"${result['firm_cut']:,.0f}",
                f"${result['unrealized']:,.0f}",
                f"{n_paid}",
                f"${avg_payout:,.0f}",
                f"${result['sub_total']:,.0f}",
                f"${result['reset_total']:,.0f}",
                f"{result['reset_count']}",
                f"${result['worst_trail']:,.0f}",
                f"{worst_idx}",
                f"{worst_dt}",
                "ON" if cfg.get("derisk_floor") else "off",
                (f"{cfg.get('shock_pts', 0):.0f} pt, once/{cfg.get('shock_freq_n', 0)}d"
                 if cfg.get("shock_pts", 0) > 0 else "none"),
                f"${cfg.get('shock_dollars_1c', 0):,.0f}",
                f"${cfg.get('hist_worst_1c', 0):,.0f}",
                f"${cfg.get('worst_trade_1c', 0):,.0f}",
                (f"{100*mc['blowup_prob_derisk']:.1f}%"
                 if mc and "blowup_prob_derisk" in mc else "—"),
                f"{result['derisk_capped']} capped, {skipped['derisk']} skipped",
            ],
        }
        st.dataframe(pd.DataFrame(pm), use_container_width=True, hide_index=True)

        if mc and cfg["scale_interval"] > 0 and mc["suggested_interval"] > cfg["scale_interval"]:
            st.warning(
                f"⚠️ Your scale interval (${cfg['scale_interval']:,.0f}) is below the "
                f"suggested ${mc['suggested_interval']:,.0f} — you may be adding contracts "
                f"faster than your cushion can absorb a bad streak.")

        if not pay_df.empty:
            st.markdown("**Payout log**")
            show = pay_df.copy()
            st.dataframe(
                show.style.format({
                    "AcctBefore": "${:,.0f}", "Withdrawable": "${:,.0f}",
                    "Paid": "${:,.0f}", "TakeHome": "${:,.0f}", "AcctAfter": "${:,.0f}",
                }),
                use_container_width=True, hide_index=True)

    # ── Detail ───────────────────────────────────────────────────────────────
    with st.expander("📊 Detail", expanded=False):
        dc1, dc2 = st.columns(2)
        with dc1:
            st.markdown("**Breakdown**")
            _detail = {
                "Metric": ["Gross Won", "Gross Lost", "Net Total", "Avg Win",
                           "Avg Loss", "W/L Ratio", "Largest Win", "Largest Loss",
                           "Avg Contracts"],
                "Value": [
                    f"${trades_df.loc[trades_df['NetPnL'] > 0, 'NetPnL'].sum():,.0f}",
                    f"${trades_df.loc[trades_df['NetPnL'] <= 0, 'NetPnL'].sum():,.0f}",
                    f"${total_pnl:,.0f}",
                    f"${trades_df.loc[trades_df['NetPnL'] > 0, 'NetPnL'].mean() if wins else 0:,.0f}",
                    f"${trades_df.loc[trades_df['NetPnL'] <= 0, 'NetPnL'].mean() if (trades_df['NetPnL'] <= 0).any() else 0:,.0f}",
                    f"{trades_df['NetPnL'].max() / abs(trades_df['NetPnL'].min()):.2f}" if trades_df['NetPnL'].min() < 0 else "∞",
                    f"${trades_df['NetPnL'].max():,.0f}",
                    f"${trades_df['NetPnL'].min():,.0f}",
                    f"{trades_df['Contracts'].mean():.1f}",
                ],
            }
            st.dataframe(pd.DataFrame(_detail), use_container_width=True, hide_index=True)
        with dc2:
            st.markdown("**Winners vs Losers**")
            _rp = trades_df.loc[trades_df["NetPnL"] > 0]
            _rn = trades_df.loc[trades_df["NetPnL"] <= 0]
            _ed = {
                "": ["Winners", "Losers", "Total"],
                "Count": [len(_rp), len(_rn), total_trades],
                "Net $": [f"${_rp['NetPnL'].sum():,.0f}", f"${_rn['NetPnL'].sum():,.0f}",
                          f"${total_pnl:,.0f}"],
                "Avg $": [f"${_rp['NetPnL'].mean():,.0f}" if len(_rp) else "—",
                          f"${_rn['NetPnL'].mean():,.0f}" if len(_rn) else "—",
                          f"${total_pnl/max(total_trades,1):,.0f}"],
            }
            st.dataframe(pd.DataFrame(_ed), use_container_width=True, hide_index=True)

    # ── Setup breakdown ───────────────────────────────────────────────────────
    if "SignalType" in trades_df.columns and trades_df["SignalType"].nunique() > 1:
        with st.expander("🎯 Setup Breakdown", expanded=False):
            setup = trades_df.groupby("SignalType").agg(
                trades=("NetPnL", "count"),
                wins=("NetPnL", lambda x: (x > 0).sum()),
                net_pnl=("NetPnL", "sum"),
                avg_r=("R_achieved", "mean"),
            ).reset_index()
            setup["Win%"] = (100 * setup["wins"] / setup["trades"]).round(1)
            setup["Exp $"] = (setup["net_pnl"] / setup["trades"]).round(0)
            setup["% of Profit"] = (100 * setup["net_pnl"] / total_pnl).round(1) if total_pnl != 0 else 0
            disp = setup[["SignalType", "trades", "Win%", "net_pnl", "Exp $",
                          "avg_r", "% of Profit"]].rename(columns={
                "SignalType": "Setup", "trades": "Trades", "net_pnl": "Net PnL",
                "avg_r": "Avg R"})
            st.dataframe(
                disp.style.format({
                    "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}", "Avg R": "{:.3f}",
                    "Win%": "{:.1f}%", "% of Profit": "{:.1f}%"}),
                use_container_width=True, hide_index=True)

    # ── Monthly Breakdown ─────────────────────────────────────────────────────
    with st.expander("📅 Monthly Breakdown", expanded=False):
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
        pct_profitable = 100 * (monthly["net_pnl"] > 0).sum() / max(len(monthly), 1)
        st.caption(f"Profitable months: {pct_profitable:.0f}%")

        m_colors = ["#66bb6a" if v >= 0 else "#ef5350" for v in monthly["net_pnl"]]
        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(x=monthly["Month"], y=monthly["net_pnl"],
                               marker_color=m_colors, name="Monthly PnL"))
        fig_m.add_trace(go.Scatter(x=monthly["Month"], y=monthly["Cum PnL"],
                                   mode="lines+markers", name="Cumulative",
                                   line=dict(color="#42A5F5", width=2), yaxis="y2"))
        fig_m.update_layout(height=350, margin=dict(t=10, b=30),
                            yaxis=dict(title="Monthly P&L ($)"),
                            yaxis2=dict(title="Cumulative ($)", overlaying="y", side="right"),
                            legend=dict(orientation="h", y=1.02))
        st.plotly_chart(fig_m, use_container_width=True)

        disp_m = monthly[["Month", "trades", "wins", "Win%", "net_pnl",
                          "Exp $", "avg_contracts", "Cum PnL"]].copy()
        disp_m.columns = ["Month", "Trades", "Wins", "Win%", "Net PnL",
                          "Exp $", "Avg C", "Cum PnL"]
        st.dataframe(
            disp_m.style.format({
                "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}", "Cum PnL": "${:,.0f}",
                "Avg C": "{:.1f}", "Win%": "{:.1f}%"}).map(
                lambda v: "color: #66bb6a" if isinstance(v, (int, float)) and v > 0
                else "color: #ef5350" if isinstance(v, (int, float)) and v < 0 else "",
                subset=["Net PnL"]),
            use_container_width=True, hide_index=True)
        trades_df.drop(columns=["_month"], inplace=True, errors="ignore")

    # ── Start-date sensitivity ────────────────────────────────────────────────
    if sens is not None and not sens.empty:
        with st.expander("📆 Start-Date Sensitivity", expanded=False):
            n_blown = (sens["Blown"] == "Yes").sum()
            st.caption(
                f"Ran from {len(sens)} different start months. "
                f"Blown in **{n_blown}/{len(sens)}**. "
                f"Net-to-trader range: ${sens['Net to Trader'].min():,.0f} → "
                f"${sens['Net to Trader'].max():,.0f} "
                f"(median ${sens['Net to Trader'].median():,.0f}).")
            st.dataframe(
                sens.style.format({
                    "Net to Trader": "${:,.0f}", "Take-Home": "${:,.0f}",
                    "Worst DD": "${:,.0f}"}),
                use_container_width=True, hide_index=True)

    # ── MC drawdown distribution ──────────────────────────────────────────────
    if mc is not None:
        with st.expander("🎲 Monte-Carlo DD Distribution", expanded=False):
            dd = -mc["dd_samples_max"]
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Histogram(x=dd, nbinsx=50, marker_color="#ef5350"))
            fig_dd.add_vline(x=mc["buffer"], line_dash="dash", line_color="#42A5F5",
                             annotation_text=f"Buffer ${mc['buffer']:,.0f}")
            if max_dd > 0:
                fig_dd.add_vline(x=max_dd, line_dash="dot", line_color="#ff1744",
                                 annotation_text=f"DD limit ${max_dd:,.0f}")
            fig_dd.update_layout(height=300, margin=dict(t=10, b=30),
                                 xaxis_title="Worst drawdown ($, max contracts)",
                                 yaxis_title="Paths")
            st.plotly_chart(fig_dd, use_container_width=True)

    # ── Skip summary ──────────────────────────────────────────────────────────
    if total_skipped > 0:
        parts = []
        labels = {"daily_loss": "daily-loss cutoff", "max_trades": "max-trades limit",
                  "blown": "post-blowup", "zero_risk": "zero-risk (no data)",
                  "margin": "insufficient margin", "direction": "direction filter",
                  "derisk": "too close to floor (de-risk)"}
        for k, lbl in labels.items():
            if skipped.get(k):
                parts.append(f"{skipped[k]} {lbl}")
        st.info(f"**Skipped trades:** {', '.join(parts)}")

    # ── Charts ────────────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=4, cols=1,
        subplot_titles=["Account Balance + Cumulative Take-Home", "Daily P&L",
                        "Trailing Drawdown (EOD + Intraday)", "Contracts"],
        row_heights=[0.3, 0.25, 0.25, 0.2], shared_xaxes=True, vertical_spacing=0.05,
        specs=[[{"secondary_y": True}], [{}], [{}], [{}]])

    dates = pd.to_datetime(daily_df["Date"])

    fig.add_trace(go.Scatter(x=dates, y=daily_df["eod_balance"], mode="lines",
                             line=dict(color="#4CAF50", width=2), name="Balance"),
                  row=1, col=1, secondary_y=False)
    fig.add_hline(y=start, line_dash="dot", line_color="#666",
                  annotation_text=f"Start ${start:,.0f}", row=1, col=1)
    fig.add_hline(y=result["floor"], line_dash="dot", line_color="#42A5F5",
                  annotation_text=f"Floor ${result['floor']:,.0f}", row=1, col=1)
    # cumulative take-home (step at payouts)
    pay_df = result["payouts"]
    if not pay_df.empty and (pay_df["Paid"] > 0).any():
        cum_th = pay_df.copy()
        cum_th["cum"] = (cfg["profit_split"] * cum_th["Paid"]).cumsum()
        cum_th = cum_th[cum_th["Paid"] > 0]
        cum_th["dt"] = pd.to_datetime(cum_th["Month"] + "-28", format="%Y-%m-%d", errors="coerce")
        fig.add_trace(go.Scatter(x=cum_th["dt"], y=cum_th["cum"], mode="lines+markers",
                                 line=dict(color="#FFD54F", width=1.5), name="Cum Take-Home"),
                      row=1, col=1, secondary_y=True)
    if blown and blown_date:
        fig.add_vline(x=pd.Timestamp(blown_date), line_dash="dash",
                      line_color="#ff1744", annotation_text="BLOWN", row=1, col=1)

    bar_colors = ["#c62828" if r["daily_loss_breach"] else
                  "#ef5350" if r["daily_pnl"] < 0 else "#66bb6a"
                  for _, r in daily_df.iterrows()]
    fig.add_trace(go.Bar(x=dates, y=daily_df["daily_pnl"], marker_color=bar_colors,
                         showlegend=False), row=2, col=1)
    if max_daily > 0:
        fig.add_hline(y=-max_daily, line_dash="dash", line_color="#ff5252",
                      annotation_text=f"-${max_daily:,.0f}", row=2, col=1)

    fig.add_trace(go.Scatter(x=dates, y=daily_df["eod_trailing_dd"], fill="tozeroy",
                             fillcolor="rgba(198,40,40,0.15)",
                             line=dict(color="#ef5350", width=1.5),
                             name="EOD DD", showlegend=False), row=3, col=1)
    if "IntradayDD" in daily_df.columns:
        fig.add_trace(go.Scatter(x=dates, y=daily_df["IntradayDD"], mode="lines",
                                 line=dict(color="#ff8a80", width=1, dash="dot"),
                                 name="Intraday DD", showlegend=False), row=3, col=1)
    if max_dd > 0:
        fig.add_hline(y=-max_dd, line_dash="dash", line_color="#ff5252",
                      annotation_text=f"-${max_dd:,.0f}", row=3, col=1)

    fig.add_trace(go.Scatter(x=pd.to_datetime(trades_df["ExitTime"]),
                             y=trades_df["Contracts"], mode="lines",
                             line=dict(color="#42A5F5", width=1.5), showlegend=False),
                  row=4, col=1)
    fig.update_yaxes(title_text="Contracts", row=4, col=1)
    fig.update_layout(height=950, margin=dict(t=30, b=30),
                      legend=dict(orientation="h", y=1.04))
    st.plotly_chart(fig, use_container_width=True)

    # ── Statistics ────────────────────────────────────────────────────────────
    st.subheader("Statistics")
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

    # ── Scaling breakdown ──────────────────────────────────────────────────────
    if cfg["scale_interval"] > 0 and trades_df["Contracts"].nunique() > 1:
        st.subheader("Scaling Breakdown")
        if mc:
            st.caption(
                f"Suggested scale interval ${mc['suggested_interval']:,.0f} "
                f"(per-contract 99-pct MC DD ${mc['per_contract_dd']:,.0f} × "
                f"{cfg['scale_safety_mult']}). Current: ${cfg['scale_interval']:,.0f}.")
        level = trades_df.groupby("Contracts").agg(
            trades=("NetPnL", "count"),
            wins=("NetPnL", lambda x: (x > 0).sum()),
            net_pnl=("NetPnL", "sum"),
            avg_r=("R_achieved", "mean"),
            first_date=("ExitTime", "min"),
            last_date=("ExitTime", "max"),
        ).reset_index()
        level["Win%"] = (100 * level["wins"] / level["trades"]).round(1)
        level["Exp $"] = (level["net_pnl"] / level["trades"]).round(0)
        level["First"] = level["first_date"].dt.strftime("%Y-%m-%d")
        level["Last"] = level["last_date"].dt.strftime("%Y-%m-%d")
        cols = ["Contracts", "trades", "Win%", "net_pnl", "Exp $", "avg_r", "First", "Last"]
        st.dataframe(
            level[cols].rename(columns={"trades": "Trades", "net_pnl": "Net PnL",
                                        "avg_r": "Avg R"}).style.format({
                "Net PnL": "${:,.0f}", "Exp $": "${:,.0f}", "Avg R": "{:.3f}",
                "Win%": "{:.1f}%"}),
            use_container_width=True, hide_index=True)

    # ── Daily detail ────────────────────────────────────────────────────────────
    with st.expander("📋 Daily Detail", expanded=False):
        dd = daily_df[["Date", "trades", "wins", "Win%", "daily_pnl", "eod_balance",
                       "eod_trailing_dd", "min_contracts", "max_contracts",
                       "daily_loss_breach"]].copy()
        dd.columns = ["Date", "Trades", "Wins", "Win%", "Daily PnL", "EOD Balance",
                      "Trailing DD", "Min C", "Max C", "Loss Breach"]
        dd["Date"] = dd["Date"].astype(str)

        def _color(row):
            if row.get("Loss Breach"):
                return ["background-color: rgba(198,40,40,0.3)"] * len(row)
            if row["Daily PnL"] < 0:
                return ["background-color: rgba(198,40,40,0.1)"] * len(row)
            return [""] * len(row)

        st.dataframe(
            dd.style.apply(_color, axis=1).format({
                "Daily PnL": "${:,.0f}", "EOD Balance": "${:,.0f}",
                "Trailing DD": "${:,.0f}", "Win%": "{:.1f}%"}),
            use_container_width=True, hide_index=True)

    # ── Trade detail ─────────────────────────────────────────────────────────────
    with st.expander("📋 Trade Detail", expanded=False):
        td = trades_df[["ExitTime", "Direction", "SignalType", "Contracts",
                        "GrossPnLPts", "NetPnL", "Balance", "TrailingDD",
                        "DayTradeNum", "R_achieved"]].copy()
        td["ExitTime"] = td["ExitTime"].dt.strftime("%Y-%m-%d %H:%M")
        td.columns = ["Exit", "Dir", "Setup", "C", "Gross Pts", "Net $", "Balance",
                      "Trail DD", "Day#", "R"]
        st.dataframe(
            td.style.format({"Gross Pts": "{:.2f}", "Net $": "${:,.0f}",
                             "Balance": "${:,.0f}", "Trail DD": "${:,.0f}",
                             "R": "{:.3f}"}),
            use_container_width=True, hide_index=True)
