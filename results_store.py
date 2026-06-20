"""
Persistent storage for WFA fold results.

SQLite (wfa_results.db):
  - table: folds — one row per (run_id, setup_id, fold_id); all scalar metadata + metrics
  - table: runs  — one row per run_id; run-level config

Parquet (wfa_trades/):
  - {run_id}/{setup_id}/fold_{fold_id}_is.parquet  — IS trade log
  - {run_id}/{setup_id}/fold_{fold_id}_oos.parquet — OOS trade log
"""

import json
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import date

_STORE_DIR  = Path(__file__).parent / "data" / "wfa_store"
_DB_PATH    = _STORE_DIR / "wfa_results.db"
_TRADES_DIR = _STORE_DIR / "trades"
_SWEEP_DIR  = _STORE_DIR / "sweeps"

_STORE_DIR.mkdir(parents=True, exist_ok=True)
_TRADES_DIR.mkdir(parents=True, exist_ok=True)
_SWEEP_DIR.mkdir(parents=True, exist_ok=True)


# ── Database init ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id       TEXT PRIMARY KEY,
                created_at   TEXT NOT NULL,
                setup_id     TEXT NOT NULL,
                mode         TEXT NOT NULL,   -- 'singleleg' | 'multileg' | '3leg'
                params_json  TEXT NOT NULL,   -- fixed params (slip, commission, etc.)
                notes        TEXT
            );

            CREATE TABLE IF NOT EXISTS folds (
                run_id          TEXT NOT NULL,
                setup_id        TEXT NOT NULL,
                fold_id         INTEGER NOT NULL,
                is_start        TEXT NOT NULL,
                is_end          TEXT NOT NULL,
                oos_start       TEXT NOT NULL,
                oos_end         TEXT NOT NULL,
                -- selected params
                params_json     TEXT NOT NULL,   -- the ≥3 param sets chosen in IS
                -- IS metrics
                is_n_trades     INTEGER,
                is_net_pnl      REAL,
                is_win_pct      REAL,
                is_pf           REAL,
                is_prom         REAL,
                is_pnl_dd       REAL,
                is_max_dd       REAL,
                is_sqn          REAL,
                is_rob_pct      REAL,    -- % of IS param combos profitable (robustness)
                is_kurtosis     REAL,    -- kurtosis of IS optimization surface
                -- OOS metrics
                oos_n_trades    INTEGER,
                oos_net_pnl     REAL,
                oos_win_pct     REAL,
                oos_pf          REAL,
                oos_prom        REAL,
                oos_pnl_dd      REAL,
                oos_max_dd      REAL,
                oos_sqn         REAL,
                -- derived
                wfe             REAL,    -- WFE = oos_net_pnl_ann / is_net_pnl_ann
                prom_decay      REAL,    -- oos_prom / is_prom
                -- guardrails
                rob_passed      INTEGER, -- 1 if is_rob_pct >= 70%
                kurtosis_ok     INTEGER, -- 1 if is_kurtosis <= 6
                min_trades_ok   INTEGER, -- 1 if is_n_trades >= 30
                oos_used        INTEGER DEFAULT 0,  -- 1 = OOS locked (no-feedback flag)
                PRIMARY KEY (run_id, setup_id, fold_id)
            );
        """)


# ── Run management ────────────────────────────────────────────────────────────

def create_run(run_id: str, setup_id: str, mode: str,
               params: dict, notes: str = "") -> None:
    init_db()
    from datetime import datetime
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
            (run_id, datetime.now().isoformat(), setup_id, mode,
             json.dumps(params), notes)
        )


def list_runs(setup_id: str | None = None) -> pd.DataFrame:
    init_db()
    with _get_conn() as conn:
        if setup_id:
            rows = conn.execute(
                "SELECT * FROM runs WHERE setup_id=? ORDER BY created_at DESC", (setup_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


def delete_run(run_id: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM folds WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM runs  WHERE run_id=?", (run_id,))
    import shutil
    for base in (_TRADES_DIR, _SWEEP_DIR):
        run_dir = base / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)


# ── Fold storage ──────────────────────────────────────────────────────────────

def save_fold(
    run_id: str,
    setup_id: str,
    fold_id: int,
    is_start: date, is_end: date,
    oos_start: date, oos_end: date,
    params_chosen: list[dict],     # ≥3 param dicts chosen from IS sweep
    is_summary: dict,
    oos_summary: dict,
    is_trades: pd.DataFrame,
    oos_trades: pd.DataFrame,
    is_rob_pct: float,
    is_kurtosis: float,
    wfe: float,
) -> None:
    init_db()

    prom_decay = (oos_summary.get("prom", float("nan")) / is_summary.get("prom", float("nan"))
                  if is_summary.get("prom") and is_summary["prom"] != 0
                  else float("nan"))

    rob_passed     = 1 if is_rob_pct >= 70.0 else 0
    # Kurtosis is undefined when the IS sweep has <4 combos (e.g. all params pinned):
    # there is no surface to measure. Store NULL (→ "N/A") rather than a false fail.
    kurtosis_ok    = None if pd.isna(is_kurtosis) else (1 if is_kurtosis <= 6.0 else 0)
    min_trades_ok  = 1 if is_summary.get("n_trades", 0) >= 30 else 0

    values = (
        run_id, setup_id, fold_id,
        str(is_start), str(is_end), str(oos_start), str(oos_end),
        json.dumps(params_chosen),
        is_summary.get("n_trades"),  is_summary.get("net_total"),
        is_summary.get("win_pct"),   is_summary.get("pf"),
        is_summary.get("prom"),      is_summary.get("pnl_dd"),
        is_summary.get("max_dd"),    is_summary.get("sqn"),
        is_rob_pct, is_kurtosis,
        oos_summary.get("n_trades"), oos_summary.get("net_total"),
        oos_summary.get("win_pct"),  oos_summary.get("pf"),
        oos_summary.get("prom"),     oos_summary.get("pnl_dd"),
        oos_summary.get("max_dd"),   oos_summary.get("sqn"),
        wfe, prom_decay,
        rob_passed, kurtosis_ok, min_trades_ok,
        0,  # oos_used = 0 until locked
    )
    with _get_conn() as conn:
        # Placeholders generated from the tuple so count can't drift from the schema.
        conn.execute(
            f"INSERT OR REPLACE INTO folds VALUES ({','.join('?' * len(values))})",
            values,
        )

    # Parquet trade logs
    trade_dir = _TRADES_DIR / run_id / setup_id
    trade_dir.mkdir(parents=True, exist_ok=True)
    if not is_trades.empty:
        is_trades.to_parquet(trade_dir / f"fold_{fold_id}_is.parquet", index=False)
    if not oos_trades.empty:
        oos_trades.to_parquet(trade_dir / f"fold_{fold_id}_oos.parquet", index=False)


def lock_oos(run_id: str, setup_id: str, fold_id: int) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE folds SET oos_used=1 WHERE run_id=? AND setup_id=? AND fold_id=?",
            (run_id, setup_id, fold_id)
        )


# ── Fold retrieval ────────────────────────────────────────────────────────────

def load_folds(run_id: str, setup_id: str | None = None) -> pd.DataFrame:
    init_db()
    with _get_conn() as conn:
        if setup_id:
            rows = conn.execute(
                "SELECT * FROM folds WHERE run_id=? AND setup_id=? ORDER BY fold_id",
                (run_id, setup_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM folds WHERE run_id=? ORDER BY setup_id, fold_id",
                (run_id,)
            ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["params_chosen"] = df["params_json"].apply(json.loads)
    return df


def load_fold_trades(run_id: str, setup_id: str, fold_id: int,
                     period: str = "oos") -> pd.DataFrame:
    path = _TRADES_DIR / run_id / setup_id / f"fold_{fold_id}_{period}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def save_sweep(run_id: str, setup_id: str, fold_id: int, sweep_df: pd.DataFrame) -> None:
    """Persist the full IS optimization-surface grid for one fold (for heatmaps)."""
    if sweep_df is None or sweep_df.empty:
        return
    d = _SWEEP_DIR / run_id / setup_id
    d.mkdir(parents=True, exist_ok=True)
    sweep_df.to_parquet(d / f"fold_{fold_id}.parquet", index=False)


def load_sweep(run_id: str, setup_id: str, fold_id: int) -> pd.DataFrame:
    """Load the IS optimization-surface grid for one fold (empty if not stored)."""
    path = _SWEEP_DIR / run_id / setup_id / f"fold_{fold_id}.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_all_oos_trades(run_id: str, setup_id: str) -> pd.DataFrame:
    """Concatenate all OOS trade logs for a setup — used to build the combined OOS equity curve."""
    folds_df = load_folds(run_id, setup_id)
    if folds_df.empty:
        return pd.DataFrame()
    parts = []
    for fold_id in folds_df["fold_id"]:
        df = load_fold_trades(run_id, setup_id, fold_id, "oos")
        if not df.empty:
            df["fold_id"] = fold_id
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(["Date", "EntryTime"])


# ── Cross-setup portfolio OOS curve ──────────────────────────────────────────

def load_portfolio_oos_trades(run_ids: dict[str, str]) -> pd.DataFrame:
    """Load OOS trades for multiple setups and tag each row with setup_id.
    run_ids: {setup_id: run_id}
    Returns combined DataFrame suitable for equity curve construction."""
    parts = []
    for setup_id, run_id in run_ids.items():
        df = load_all_oos_trades(run_id, setup_id)
        if not df.empty:
            df["setup_id"] = setup_id
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values(["Date", "EntryTime"])


# ── Guardrail summary ─────────────────────────────────────────────────────────

def guardrail_report(folds_df: pd.DataFrame) -> dict:
    """Return counts of passed/failed guardrails across all folds."""
    if folds_df.empty:
        return {}
    n = len(folds_df)
    # Kurtosis pass/denominator derived from is_kurtosis directly (NaN = N/A, not a
    # fail) — works for older runs that stored kurtosis_ok=0 for degenerate grids too.
    _kurt    = pd.to_numeric(folds_df["is_kurtosis"], errors="coerce")
    _kurt_n  = int(_kurt.notna().sum())
    _kurt_ok = int((_kurt <= 6.0).sum())
    return {
        "total_folds":       n,
        "rob_passed":        int(folds_df["rob_passed"].sum()),
        "kurtosis_ok":       _kurt_ok,
        "kurtosis_n":        _kurt_n,
        "min_trades_ok":     int(folds_df["min_trades_ok"].sum()),
        "oos_profitable":    int((folds_df["oos_net_pnl"] > 0).sum()),
        "pct_oos_profitable": round((folds_df["oos_net_pnl"] > 0).mean() * 100, 1),
        "mean_wfe":          round(pd.to_numeric(folds_df["wfe"], errors="coerce").median() * 100, 1),
        "mean_prom_decay":   round(folds_df["prom_decay"].dropna().mean(), 3),
    }
