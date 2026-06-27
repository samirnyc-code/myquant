"""
leg_label_store.py — Separate persistent stores for ground-truth labels and live call log.

Two stores that MUST remain separate (spec §4.4 — collapsing them is the
most common way these projects fool themselves):

  ground_truth_labels.parquet  — per-bar leg state with full hindsight.
                                  May be corrected retrospectively. Always
                                  reflects what actually happened.

  live_call_log.parquet        — what the real-time indicator called at bar
                                  close, frozen and never altered. This is
                                  the historical prediction record.

  The gap between these two stores is the measured edge.

Label taxonomy (spec §2.2)
--------------------------
  IMPULSE_L1   — first push of a new directional move
  IMPULSE_LN   — continuation leg (leg 2+ of an impulse)
  PB_L1        — first countertrend leg of a pullback
  PB_L2        — second countertrend leg (classic 2-legged PB terminal)
  PB_L3        — third countertrend leg (wedge/bull-bear flag terminal)
  REVERSAL     — structural reversal context
  UNLABELED    — not yet assigned
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).parent / "data" / "leg_labels"
DATA_DIR.mkdir(parents=True, exist_ok=True)

GT_FILE   = DATA_DIR / "ground_truth_labels.parquet"
LIVE_FILE = DATA_DIR / "live_call_log.parquet"

LEG_STATES = [
    "IMPULSE_L1",
    "IMPULSE_LN",
    "PB_L1",
    "PB_L2",
    "PB_L3",
    "REVERSAL",
    "UNLABELED",
]

_SCHEMA = {
    "leg_id":     "Int64",
    "start_dt":   "datetime64[ns]",
    "end_dt":     "datetime64[ns]",
    "direction":  "Int8",
    "leg_state":  "object",
    "labeler":    "object",
    "session":    "object",
    "notes":      "object",
    "labeled_at": "datetime64[ns]",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _empty() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype=t) for c, t in _SCHEMA.items()})
    return df


def _load(path: Path) -> pd.DataFrame:
    if not path.exists():
        return _empty()
    df = pd.read_parquet(path)
    # Ensure all schema columns exist
    for col, dtype in _SCHEMA.items():
        if col not in df.columns:
            df[col] = pd.Series(dtype=dtype)
    return df[list(_SCHEMA.keys())]


def _save(df: pd.DataFrame, path: Path) -> None:
    df = df.copy()
    df["start_dt"]   = pd.to_datetime(df["start_dt"])
    df["end_dt"]     = pd.to_datetime(df["end_dt"])
    df["labeled_at"] = pd.to_datetime(df["labeled_at"])
    df.to_parquet(path, index=False)


# ── Ground-truth store ────────────────────────────────────────────────────────

def load_ground_truth() -> pd.DataFrame:
    """Load ground-truth labels. Returns empty DataFrame if no file exists."""
    return _load(GT_FILE)


def upsert_ground_truth(
    rows: list[dict],
    labeler: str = "manual",
    session: str = "",
) -> pd.DataFrame:
    """
    Insert or update ground-truth label rows.

    Each dict in `rows` must have at minimum:
        leg_id (int), start_dt, end_dt, direction (int), leg_state (str)

    `leg_state` must be one of LEG_STATES.
    Existing rows with the same leg_id are overwritten (ground truth may be
    corrected retrospectively — spec §4.4).

    Returns the updated DataFrame.
    """
    now = datetime.utcnow()
    df  = load_ground_truth()

    new_rows = []
    for r in rows:
        state = r.get("leg_state", "UNLABELED")
        if state not in LEG_STATES:
            raise ValueError(f"Unknown leg_state '{state}'. Must be one of {LEG_STATES}")
        new_rows.append({
            "leg_id":     int(r["leg_id"]),
            "start_dt":   pd.Timestamp(r["start_dt"]),
            "end_dt":     pd.Timestamp(r["end_dt"]),
            "direction":  int(r["direction"]),
            "leg_state":  state,
            "labeler":    r.get("labeler", labeler),
            "session":    r.get("session", session),
            "notes":      r.get("notes", ""),
            "labeled_at": pd.Timestamp(now),
        })

    new_df = pd.DataFrame(new_rows)
    # Remove existing rows for these leg_ids
    updated_ids = new_df["leg_id"].tolist()
    df = df[~df["leg_id"].isin(updated_ids)]
    df = pd.concat([df, new_df], ignore_index=True).sort_values("leg_id")
    _save(df, GT_FILE)
    return df


def delete_ground_truth(leg_ids: list[int]) -> pd.DataFrame:
    """Remove labels for specific leg_ids from ground truth."""
    df = load_ground_truth()
    df = df[~df["leg_id"].isin(leg_ids)]
    _save(df, GT_FILE)
    return df


# ── Live call log ─────────────────────────────────────────────────────────────

def load_live_calls() -> pd.DataFrame:
    """Load live call log. Returns empty DataFrame if no file exists."""
    return _load(LIVE_FILE)


def append_live_call(
    leg_id: int,
    start_dt,
    end_dt,
    direction: int,
    leg_state: str,
    labeler: str = "indicator_v1",
    session: str = "",
    notes: str = "",
) -> None:
    """
    Append ONE live call to the log. NEVER modifies existing rows.

    This is the historical prediction record — frozen at call time,
    never corrected (spec §4.4).

    Raises ValueError if leg_id is already in the log (no overwrite).
    """
    df = load_live_calls()
    if leg_id in df["leg_id"].values:
        raise ValueError(
            f"leg_id {leg_id} already in live call log. "
            "Live calls are immutable — never overwrite."
        )
    if leg_state not in LEG_STATES:
        raise ValueError(f"Unknown leg_state '{leg_state}'.")

    new_row = pd.DataFrame([{
        "leg_id":     int(leg_id),
        "start_dt":   pd.Timestamp(start_dt),
        "end_dt":     pd.Timestamp(end_dt),
        "direction":  int(direction),
        "leg_state":  leg_state,
        "labeler":    labeler,
        "session":    session,
        "notes":      notes,
        "labeled_at": pd.Timestamp(datetime.utcnow()),
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    _save(df, LIVE_FILE)


# ── Edge measurement ──────────────────────────────────────────────────────────

def compute_edge(
    gt: pd.DataFrame | None = None,
    live: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Join ground-truth labels with live calls on leg_id and compute agreement.

    Returns a DataFrame with columns:
        leg_id, gt_state, live_state, correct (bool), direction
    """
    if gt is None:
        gt = load_ground_truth()
    if live is None:
        live = load_live_calls()

    if gt.empty or live.empty:
        return pd.DataFrame(columns=["leg_id", "gt_state", "live_state", "correct", "direction"])

    merged = gt[["leg_id", "leg_state", "direction"]].merge(
        live[["leg_id", "leg_state"]].rename(columns={"leg_state": "live_state"}),
        on="leg_id",
        how="inner",
    ).rename(columns={"leg_state": "gt_state"})

    merged["correct"] = merged["gt_state"] == merged["live_state"]
    return merged


# ── Draft labels from decomposition ──────────────────────────────────────────

def draft_from_decomp(legs: pd.DataFrame) -> pd.DataFrame:
    """
    Generate draft ground-truth label rows from leg_table() output.
    All states default to UNLABELED — user corrects them in the labeling UI.

    Parameters
    ----------
    legs : output of leg_decomp.leg_table()

    Returns the same DataFrame format as load_ground_truth(), not yet saved.
    """
    rows = []
    for _, leg in legs.iterrows():
        rows.append({
            "leg_id":     int(leg["leg_id"]),
            "start_dt":   pd.Timestamp(leg["start_dt"]),
            "end_dt":     pd.Timestamp(leg["end_dt"]),
            "direction":  int(leg["direction"]),
            "leg_state":  "UNLABELED",
            "labeler":    "draft_decomp",
            "session":    "",
            "notes":      "",
            "labeled_at": pd.Timestamp(datetime.utcnow()),
        })
    return pd.DataFrame(rows) if rows else _empty()
