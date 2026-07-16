"""Unified options trade log — the §B schema from docs/living/options_playbook.md (S73).

ONE schema for backtest, forward-sim, and paper trades so results are comparable.
File: data/options_log/trades.parquet — one row per trade. Open trades have
exit_dt = None; close them with update_exit().

slippage = (mid-model credit − executed credit) × 100 per spread in $ at the SAME
timestamp — i.e. the half-spread cost actually paid, one component of fill-drift.
The full 16:00-mark-vs-real-fill drift is measured from the quote CSVs the sim
daemon writes alongside each trade.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "options_log" / "trades.parquet"

COLUMNS = [
    "trade_id", "strategy_id", "source", "symbol", "entry_dt", "exit_dt", "dte",
    "structure", "legs", "credit", "exit_cost", "fill_model", "slippage",
    "pnl", "roc", "collateral", "hold_days", "win",
    "vix", "vix_rank", "er10", "adx", "gex_regime", "hvl_side", "dow", "event",
    # S73 additions — per-trade thesis & risk metrics
    "commentary", "grade", "max_gain", "max_loss", "pop",
    # S75 — how the trade closed: "expired" (held to cash-settlement) |
    # "traded_to_close" (we placed offsetting orders) | "partial_expiry" (some legs
    # expired, position residual — needs attention). Tracked as an outcome stat.
    "close_reason",
]


def load():
    if LOG.exists():
        return pd.read_parquet(LOG)
    return pd.DataFrame(columns=COLUMNS)


def _save(df):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(LOG, index=False)


def open_trades(strategy_id=None):
    df = load()
    df = df[df.exit_dt.isna()]
    if strategy_id:
        df = df[df.strategy_id == strategy_id]
    return df


def append_entry(row):
    """row: dict with at least trade_id/strategy_id/source/symbol/entry_dt/legs/credit.
    legs may be a list of dicts — stored as JSON text."""
    if isinstance(row.get("legs"), (list, dict)):
        row = {**row, "legs": json.dumps(row["legs"])}
    df = load()
    if (df.trade_id == row["trade_id"]).any():
        raise ValueError(f"trade_id {row['trade_id']} already exists")
    full = {c: row.get(c) for c in COLUMNS}
    df = pd.concat([df, pd.DataFrame([full])], ignore_index=True)
    _save(df)
    return full


def update_exit(trade_id, exit_dt, exit_cost, fees_total, **extra):
    """Close a trade: computes pnl/roc/hold_days/win from the stored entry row."""
    df = load()
    m = df.trade_id == trade_id
    if not m.any():
        raise ValueError(f"trade_id {trade_id} not found")
    i = df.index[m][0]
    credit = float(df.at[i, "credit"])
    coll = float(df.at[i, "collateral"]) if pd.notna(df.at[i, "collateral"]) else None
    pnl = (credit - float(exit_cost)) * 100 - float(fees_total)
    df.at[i, "exit_dt"] = exit_dt
    df.at[i, "exit_cost"] = float(exit_cost)
    df.at[i, "pnl"] = pnl
    df.at[i, "win"] = pnl > 0
    if coll:
        df.at[i, "roc"] = pnl / coll
    df.at[i, "hold_days"] = (pd.to_datetime(exit_dt) - pd.to_datetime(df.at[i, "entry_dt"])).days
    for k, v in extra.items():
        if k in COLUMNS:
            df.at[i, k] = v
    _save(df)
    return df.loc[i].to_dict()


def annotate(trade_id, **fields):
    """Set arbitrary columns on a trade WITHOUT closing it (e.g. a close_reason flag
    on a still-open partial-expiry trade). Only writes keys that exist in COLUMNS."""
    df = load()
    m = df.trade_id == trade_id
    if not m.any():
        raise ValueError(f"trade_id {trade_id} not found")
    i = df.index[m][0]
    for k, v in fields.items():
        if k in COLUMNS:
            df.at[i, k] = v
    _save(df)
    return df.loc[i].to_dict()


def summary(strategy_id=None):
    df = load()
    if strategy_id:
        df = df[df.strategy_id == strategy_id]
    closed = df[df.exit_dt.notna()]
    if closed.empty:
        return f"{len(df)} trades, none closed yet"
    p = closed.pnl.astype(float)
    pf = p[p > 0].sum() / -p[p < 0].sum() if (p < 0).any() else float("inf")
    return (f"{len(closed)} closed ({len(df) - len(closed)} open)  win {(p > 0).mean() * 100:.0f}%  "
            f"PF {pf:.2f}  total ${p.sum():+,.0f}  avg ${p.mean():+.0f}")


if __name__ == "__main__":
    df = load()
    print(f"{LOG}\n{len(df)} rows")
    if len(df):
        print(df.to_string())
        print(summary())
