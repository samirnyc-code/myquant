"""regime_filter.py — LOCKED multi-slice regime filter for WFA.

This is the VALIDATION counterpart to the *descriptive* Regime/Indicator
Expectancy tooling in ``bar_analysis.py``. It reuses the SAME tagging engine
(``indicators.tag_signals``) and the SAME bucket bin-edges (imported from
``bar_analysis`` — one definition shared between research and validation, so a
"keep the ≥+2σ tail" decision means the identical thing in both places).

DISCIPLINE (handoff S20 DIRECTION — non-negotiable):
  1. The filter is LOCKED before the WFA run and NEVER optimized / re-tuned
     against OOS results. WFA optimizes only T1 / T2 / PB per fold.
  2. Pre-commit a SMALL number of hypothesis-driven buckets; do not try many
     combinations and keep the survivors (multiple-testing).
  3. Prefer OPEN-ENDED tails (e.g. |VWAP σ| ≥ 2) over hand-drawn interior
     bands. Every kept / dropped bucket needs a structural *why*, not "it was
     red". ``is_open_ended`` exists so the UI can nudge toward this.

Nothing in this module optimizes anything. It tags signals and keeps a
pre-specified set of buckets — AND across the active indicators. A signal with
no reading (NaN) on an *active* indicator is DROPPED (we cannot confirm it is
in the kept regime — the conservative choice).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import indicators
# Single source of truth for the bins — same edges the descriptive expectancy
# tables use, so a locked bucket is byte-identical between research & validation.
from bar_analysis import (
    _PCT_EDGES, _PCT_LABELS,
    _VWAP_EDGES, _VWAP_LABELS,
    _RANGE_ATR_EDGES, _RANGE_ATR_LABELS,
    _ERI_EDGES, _ERI_LABELS,
    _time_concentration,
)

# Re-export under a public name so callers don't reach for the underscore form.
time_concentration = _time_concentration


@dataclass(frozen=True)
class RegimeIndicator:
    key: str            # stable id (session_state / spec key)
    label: str          # human label shown in the UI
    factor: str         # latent factor (mirrors bar_analysis._FACTOR_MAP)
    kind: str           # "numeric" | "categorical" | "directional"
    source_col: str     # column produced by tag_signals (level col if directional)
    edges: list = field(default=None)
    labels: list = field(default=None)
    ordered: bool = True  # buckets have a natural order → tail-preference applies


# ── The LOCKED orthogonal shortlist ─────────────────────────────────────────
# One indicator per latent factor (the S20 factor-redundancy analysis), so we
# never stack two filters that measure the same thing. Session value-area is
# included because the user finds it defensible (low-DoF 3-bucket, prior-day-
# fixed reference). The intraday-ER trio is a robustness set in research; here
# we expose the 60m member as the single representative.
SHORTLIST: list[RegimeIndicator] = [
    RegimeIndicator("vwap_sigma", "VWAP σ-deviation", "Displacement from value",
                    "numeric", "VWAP_dev", _VWAP_EDGES, _VWAP_LABELS, ordered=True),
    RegimeIndicator("range_atr", "Prior-day Range/ATR", "Volatility regime",
                    "numeric", "prior_RangeATR", _RANGE_ATR_EDGES, _RANGE_ATR_LABELS,
                    ordered=True),
    RegimeIndicator("adx_pct", "ADX percentile", "Trend strength",
                    "numeric", "prior_ADX_pct", _PCT_EDGES, _PCT_LABELS, ordered=True),
    RegimeIndicator("eri_60", "Intraday ER 60m", "Intraday efficiency",
                    "numeric", "ER_intra_12", _ERI_EDGES, _ERI_LABELS, ordered=True),
    RegimeIndicator("ema20_align", "20-EMA alignment", "Directional alignment",
                    "directional", "EMA_20", labels=["Aligned", "Misaligned"],
                    ordered=False),
    RegimeIndicator("session_va", "Session value-area location",
                    "Displacement from value", "categorical", "vaD_loc",
                    labels=["below", "inside", "above"], ordered=True),
]

_BY_KEY = {ind.key: ind for ind in SHORTLIST}

# price columns tag_signals itself prefers, for the directional alignment test
_PX_COLS = ("Price", "SignalPrice", "Close", "EntryPrice")


def _bucket_column(tagged: pd.DataFrame, ind: RegimeIndicator):
    """Categorical bucket Series for one indicator, or None if its source
    columns are absent on this signal set."""
    if ind.kind == "numeric":
        if ind.source_col not in tagged.columns:
            return None
        return pd.cut(tagged[ind.source_col], ind.edges, labels=ind.labels,
                      include_lowest=True)

    if ind.kind == "categorical":
        if ind.source_col not in tagged.columns:
            return None
        return pd.Categorical(tagged[ind.source_col].astype("object"),
                              categories=ind.labels, ordered=ind.ordered)

    if ind.kind == "directional":
        lvl = ind.source_col
        if lvl not in tagged.columns or "Direction" not in tagged.columns:
            return None
        px_col = next((c for c in _PX_COLS if c in tagged.columns), None)
        if px_col is None:
            return None
        px = tagged[px_col].astype(float)
        lv = tagged[lvl].astype(float)
        above = px > lv
        is_long = tagged["Direction"].astype(str).str.upper().str.startswith("L")
        aligned = (above & is_long) | (~above & ~is_long)
        lab = np.where(px.notna() & lv.notna(),
                       np.where(aligned, "Aligned", "Misaligned"), None)
        return pd.Categorical(lab, categories=["Aligned", "Misaligned"])

    return None


def tag_and_bucket(signals: pd.DataFrame, bars: pd.DataFrame):
    """Tag ``signals`` (``indicators.tag_signals``) and append one bucket column
    per shortlist indicator that can be computed on this set.

    Returns ``(tagged, bucket_cols)`` where ``bucket_cols`` maps indicator key →
    bucket column name. A stable ``_rf_id`` (input row position) is carried
    through so callers can map the result back to the original rows even though
    tag_signals sorts by DateTime.
    """
    sig = signals.copy()
    sig["_rf_id"] = np.arange(len(sig))
    tagged = indicators.tag_signals(sig, bars)

    bucket_cols: dict[str, str] = {}
    for ind in SHORTLIST:
        col = _bucket_column(tagged, ind)
        if col is None:
            continue
        bcol = f"_rf_{ind.key}"
        tagged[bcol] = col
        bucket_cols[ind.key] = bcol
    return tagged, bucket_cols


def present_buckets(tagged: pd.DataFrame, ind: RegimeIndicator, bcol: str) -> list:
    """Bucket labels that actually occur on this set, in canonical order."""
    return [b for b in ind.labels if (tagged[bcol] == b).any()]


def _is_active(ind: RegimeIndicator, kept, available: list) -> bool:
    """A constraint is active only if `kept` is a non-empty STRICT subset of the
    buckets available on this set. (All-selected or empty = filter off.)"""
    if not kept:
        return False
    return set(kept) < set(available)


def filter_mask(tagged: pd.DataFrame, bucket_cols: dict, spec: dict) -> pd.Series:
    """Boolean mask over ``tagged``. ``spec`` = {key: [kept buckets]}.

    AND across active indicators. Inactive (all-selected / empty / unknown key)
    constraints are skipped. NaN/unreadable rows fail any active constraint.
    """
    mask = pd.Series(True, index=tagged.index)
    for key, kept in spec.items():
        if key not in bucket_cols or key not in _BY_KEY:
            continue
        ind = _BY_KEY[key]
        bcol = bucket_cols[key]
        available = present_buckets(tagged, ind, bcol)
        if not _is_active(ind, kept, available):
            continue
        mask &= tagged[bcol].isin(kept)
    return mask


def active_spec(tagged: pd.DataFrame, bucket_cols: dict, spec: dict) -> dict:
    """Subset of ``spec`` whose constraints are actually active on this set."""
    out = {}
    for key, kept in spec.items():
        if key not in bucket_cols or key not in _BY_KEY:
            continue
        ind = _BY_KEY[key]
        if _is_active(ind, kept, present_buckets(tagged, ind, bucket_cols[key])):
            out[key] = list(kept)
    return out


def apply_regime_filter(signals: pd.DataFrame, bars: pd.DataFrame, spec: dict):
    """Return ``(filtered_signals, info)``.

    ``filtered_signals`` is the subset of the ORIGINAL ``signals`` frame (same
    columns & order) passing every active constraint. ``info`` records the
    active constraints, counts, and the kept-set time-spread flag.
    """
    if not spec:
        return signals.copy(), {"active": {}, "n_in": len(signals),
                                "n_out": len(signals), "time_flag": None}

    tagged, bucket_cols = tag_and_bucket(signals, bars)
    act = active_spec(tagged, bucket_cols, spec)
    if not act:
        return signals.copy(), {"active": {}, "n_in": len(signals),
                                "n_out": len(signals), "time_flag": None}

    mask = filter_mask(tagged, bucket_cols, act)
    kept_ids = set(tagged.loc[mask, "_rf_id"].tolist())

    sig = signals.copy()
    sig["_rf_id"] = np.arange(len(sig))
    out = sig[sig["_rf_id"].isin(kept_ids)].drop(columns="_rf_id").copy()

    tf = None
    if "DateTime" in out.columns and len(out):
        tf = time_concentration(out["DateTime"])
    info = {"active": act, "n_in": len(signals), "n_out": len(out), "time_flag": tf}
    return out, info


def is_open_ended(ind: RegimeIndicator, kept) -> bool:
    """True if ``kept`` is a contiguous run that touches one end of the ordered
    bucket list (a tail / threshold), not an interior hand-drawn band. Used by
    the UI to nudge toward rail #3. Non-ordered indicators are always 'fine'.
    """
    if not ind.ordered or not kept:
        return True
    order = ind.labels
    idx = sorted(order.index(b) for b in kept if b in order)
    if not idx:
        return True
    contiguous = idx == list(range(idx[0], idx[-1] + 1))
    touches_end = idx[0] == 0 or idx[-1] == len(order) - 1
    return contiguous and touches_end


def describe_spec(spec: dict) -> str:
    """Compact human/record string for the locked filter (for run notes)."""
    parts = []
    for ind in SHORTLIST:
        kept = spec.get(ind.key)
        if kept:
            parts.append(f"{ind.label}∈{{{', '.join(map(str, kept))}}}")
    return " AND ".join(parts) if parts else "none"
