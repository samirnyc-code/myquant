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


def set_book(name: str = "spx") -> None:
    """Point this process's trade log at a parallel book. Default 'spx' = the canonical
    trades.parquet (unchanged); 'xsp' = trades_xsp.parquet (the Mini-SPX mirror book).
    Per-process module state — the mirror daemon sets 'xsp'; the desk stays 'spx'."""
    global LOG
    LOG = ROOT / "data" / "options_log" / (
        "trades.parquet" if name in ("spx", "", None) else f"trades_{name}.parquet")

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
    # S99 (2026-08-08) — ENTRY INTEGRITY. A trade struck late or off a stale feed is
    # NOT a clean datapoint (08-05: an open-centered trade struck ~1h late polluted the
    # centering A/B). entry_valid=False ⇒ exclude from A/B tables; the others explain why.
    "entry_valid", "entry_lag_min", "feed_age_s", "entry_note",
]


def load():
    if LOG.exists():
        return pd.read_parquet(LOG)
    return pd.DataFrame(columns=COLUMNS)


def dedupe_mirrors(df):
    """Drop live-account mirror rows that duplicate a sim-book trade.

    A 'real_paper' row is the real IB leg of a trade also booked in the sim book
    (same strategy_id + entry day). For any DISPLAY/analytics view we count it
    once — never both — so collateral, P&L, grades and trade counts don't
    double-book (STMR sim+REAL pair). Non-destructive: only filters, never writes.
    """
    if df is None or not len(df) or "source" not in df.columns:
        return df
    ed = pd.to_datetime(df["entry_dt"], errors="coerce").dt.strftime("%Y-%m-%d")
    key = list(zip(df["strategy_id"].astype(str), ed.astype(str)))
    df = df.assign(_key=key)
    sib = set(df.loc[df["source"] != "real_paper", "_key"])
    dupe = (df["source"] == "real_paper") & df["_key"].isin(sib)
    return df[~dupe].drop(columns=["_key"])


def dedupe_duplicate_fires(df):
    """Drop re-fired copies of the same auto_trigger setup on the same day.

    2026-10-30 incident: a watchdog restart of options_trigger_daemon.py during
    a hang couldn't see what a prior (possibly still-alive) instance had already
    fired, and re-fired every trigger it still saw as unfired -> 2-3 real orders
    for the same strategy_id on one day. The daemon itself is now fixed
    (cross-process dedup via trades.parquet, see fire() in
    options_trigger_daemon.py) so this should not recur, but the historical book
    already has it on at least 2026-10-23 and 2026-10-30 (checked when this was
    added — both show the identical fingerprint: several `auto_trigger` setups
    with >1 row on the same entry day). For any DISPLAY/analytics view, keep only
    the EARLIEST entry for a given (entry day, strategy_id, auto_trigger) — the
    daemon always fires a legitimate trigger's one-and-only intended copy first;
    every later copy on the same day is the restart artifact, confirmed against
    the gameplan's own `time_at not_before` rule (the earliest fire is the one
    nearest the rule's intended time; later ones are strictly further from it).
    Non-destructive: only filters, never writes — the raw duplicate rows stay in
    trades.parquet as the incident's audit trail.
    """
    if df is None or not len(df) or "source" not in df.columns:
        return df
    is_auto = df["source"] == "auto_trigger"
    ed = pd.to_datetime(df["entry_dt"], errors="coerce")
    key = list(zip(df["strategy_id"].astype(str), ed.dt.strftime("%Y-%m-%d")))
    tmp = df.assign(_key=key, _entry_dt=ed)
    # rank ONLY among auto_trigger rows sharing the same (strategy_id, day) —
    # a manual/other-source row with the same strategy_id that day is untouched
    # and doesn't affect which auto_trigger copy counts as "first".
    auto_rank = tmp.loc[is_auto].groupby("_key")["_entry_dt"].rank(method="first")
    dupe = pd.Series(False, index=df.index)
    dupe.loc[auto_rank.index] = auto_rank > 1
    return df[~dupe]


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
