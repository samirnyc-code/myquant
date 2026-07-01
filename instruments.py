"""
instruments.py — Multi-instrument contract catalog for NQ, YM, GC, CL.

Mirrors contracts.py (which handles ES) but is generic across instruments.
Each instrument has:
  - A contract catalog built from its delivery-month cycle and expiry rule
  - A per-instrument rolls JSON  (rolls_{key}.json) for user overrides
  - Utility functions for back-adjustment matching the contracts.py API

Roll date convention (same as ES / NT's Instrument Manager):
    roll_date for contract X = the date X BECOMES the front month
    offset for contract X   = X_price − prev_contract_price at the roll date
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).parent

_MONTH_TO_CODE: dict[int, str] = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
_MONTH_NAMES: dict[int, str] = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


# ── Instrument specification ───────────────────────────────────────────────────

@dataclass(frozen=True)
class InstrumentSpec:
    key:          str        # "NQ"
    name:         str        # "E-mini Nasdaq 100"
    root:         str        # ticker root we use internally: "NQ", "YM", "GC", "CL"
    massive_root: str        # root as it appears in Massive gz files (e.g. "0YM" for YM)
    exchange:     str        # "cme" | "cbot" | "comex" | "nymex"
    s3_prefix:    str        # Massive S3 path prefix
    gz_subdir:    str        # subdir of data/ for downloaded gz files
    months:       tuple      # delivery months e.g. (3, 6, 9, 12)
    roll_days:    int        # calendar days before expiry = default roll-out date
    start_year:   int
    start_month:  int        # first delivery month included in catalog

    def rolls_path(self) -> Path:
        return _ROOT / f"rolls_{self.key}.json"


INSTRUMENTS: dict[str, InstrumentSpec] = {
    "NQ": InstrumentSpec(
        key="NQ", name="E-mini Nasdaq 100",
        root="NQ", massive_root="NQ",
        exchange="cme", s3_prefix="us_futures_cme/trades_v1",
        gz_subdir="flatfiles_cache",        # same CME files already on disk
        months=(3, 6, 9, 12), roll_days=8,
        start_year=2021, start_month=9,     # NQU1
    ),
    "YM": InstrumentSpec(
        key="YM", name="E-mini Dow Jones",
        root="YM", massive_root="0YM",      # CBOT gz files use leading-zero prefix
        exchange="cbot", s3_prefix="us_futures_cbot/trades_v1",
        gz_subdir="flatfiles_cache_cbot",
        months=(3, 6, 9, 12), roll_days=8,
        start_year=2021, start_month=9,     # YMU1
    ),
    "GC": InstrumentSpec(
        key="GC", name="Gold",
        root="GC", massive_root="GC",
        exchange="comex", s3_prefix="us_futures_comex/trades_v1",
        gz_subdir="flatfiles_cache_comex",
        months=(2, 4, 6, 8, 10, 12),        # bimonthly delivery months
        roll_days=5,
        start_year=2021, start_month=8,     # GCQ1 (Aug 2021)
    ),
    "CL": InstrumentSpec(
        key="CL", name="WTI Crude Oil",
        root="CL", massive_root="CL",
        exchange="nymex", s3_prefix="us_futures_nymex/trades_v1",
        gz_subdir="flatfiles_cache_nymex",
        months=tuple(range(1, 13)),         # all 12 months
        roll_days=5,
        start_year=2021, start_month=8,     # CLQ1 (Aug 2021; CLN1 Jul rolled ~Jun 22)
    ),
    "6E": InstrumentSpec(
        key="6E", name="Euro FX",
        root="6E", massive_root="6E",
        exchange="cme", s3_prefix="us_futures_cme/trades_v1",
        gz_subdir="flatfiles_cache",        # same CME files already on disk
        months=(3, 6, 9, 12), roll_days=8,
        start_year=2021, start_month=9,     # 6EU1
    ),
    "6J": InstrumentSpec(
        key="6J", name="Japanese Yen FX",
        root="6J", massive_root="6J",
        exchange="cme", s3_prefix="us_futures_cme/trades_v1",
        gz_subdir="flatfiles_cache",        # same CME files already on disk
        months=(3, 6, 9, 12), roll_days=8,
        start_year=2021, start_month=9,     # 6JU1
    ),
}


# ── Contract dataclass ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstContract:
    ticker:      str   # "NQM6"
    month:       int   # 6
    year:        int   # 2026
    last_trade:  str   # ISO date
    roll_date:   str   # date this contract becomes front month (catalog default)
    active_from: str   # same as roll_date


# ── Expiry calculators ─────────────────────────────────────────────────────────

def _third_friday(year: int, month: int) -> date:
    """3rd Friday of contract month (NQ and YM expiry rule)."""
    d = date(year, month, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def _last_business_day(year: int, month: int) -> date:
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    d = date(ny, nm, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _prev_n_business_days(d: date, n: int) -> date:
    for _ in range(n):
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
    return d


def _third_wednesday(year: int, month: int) -> date:
    """3rd Wednesday of contract month (CME FX futures settlement date)."""
    d = date(year, month, 1)
    return d + timedelta(days=(2 - d.weekday()) % 7 + 14)


def _gc_expiry(year: int, month: int) -> date:
    """GC: third-to-last business day of delivery month."""
    return _prev_n_business_days(_last_business_day(year, month), 2)


def _cl_expiry(year: int, month: int) -> date:
    """CL: business day prior to 25th calendar day of the month preceding delivery."""
    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    d = date(py, pm, 25) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


_EXPIRY_FN = {
    "NQ": _third_friday,
    "YM": _third_friday,
    "6E": _third_wednesday,
    "6J": _third_wednesday,
    "GC": _gc_expiry,
    "CL": _cl_expiry,
}


# ── Catalog builder ────────────────────────────────────────────────────────────

def build_catalog(key: str) -> list[InstContract]:
    """Generate all front-month contracts for an instrument up to 2 years from today."""
    spec      = INSTRUMENTS[key]
    expiry_fn = _EXPIRY_FN[key]
    end_year  = date.today().year + 2

    contracts: list[InstContract] = []
    prev_roll_dt: date | None = None
    started = False

    for year in range(spec.start_year, end_year + 1):
        for month in spec.months:
            if not started:
                if year == spec.start_year and month < spec.start_month:
                    continue
                started = True

            expiry   = expiry_fn(year, month)
            roll_dt  = expiry - timedelta(days=spec.roll_days)
            ticker   = f"{spec.root}{_MONTH_TO_CODE[month]}{str(year)[-1]}"
            from_dt  = (prev_roll_dt + timedelta(days=1)
                        if prev_roll_dt
                        else expiry - timedelta(days=90))

            contracts.append(InstContract(
                ticker      = ticker,
                month       = month,
                year        = year,
                last_trade  = expiry.isoformat(),
                roll_date   = from_dt.isoformat(),
                active_from = from_dt.isoformat(),
            ))
            prev_roll_dt = roll_dt

    return contracts


# Build and cache catalogs at import time
CATALOGS:            dict[str, list[InstContract]]       = {k: build_catalog(k) for k in INSTRUMENTS}
CATALOGS_BY_TICKER:  dict[str, dict[str, InstContract]]  = {
    k: {c.ticker: c for c in cats} for k, cats in CATALOGS.items()
}


# ── Rolls file management ──────────────────────────────────────────────────────

def load_rolls(key: str) -> dict:
    p = INSTRUMENTS[key].rolls_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_rolls(key: str, rolls: dict) -> None:
    INSTRUMENTS[key].rolls_path().write_text(
        json.dumps(rolls, indent=2), encoding="utf-8"
    )


def ensure_rolls_file(key: str) -> None:
    """Create rolls JSON with catalog defaults if missing; add any new contracts."""
    existing = load_rolls(key)
    updated  = False
    for c in CATALOGS[key]:
        if c.ticker not in existing:
            existing[c.ticker] = {"roll_date": c.roll_date, "offset": None}
            updated = True
    if updated or not INSTRUMENTS[key].rolls_path().exists():
        save_rolls(key, existing)


def get_roll_date(ticker: str, rolls: dict, key: str) -> str:
    rd  = rolls.get(ticker, {}).get("roll_date")
    cat = CATALOGS_BY_TICKER.get(key, {})
    return rd if rd else (cat[ticker].roll_date if ticker in cat else "")


def get_offset(ticker: str, rolls: dict) -> float | None:
    val = rolls.get(ticker, {}).get("offset")
    return float(val) if val is not None else None


# ── Back-adjustment (Panama method, same logic as contracts.py) ────────────────

def get_contract_windows(key: str, rolls: dict) -> list[dict]:
    """
    Build front-month windows + cumulative back-adjustment offsets for an instrument.
    Oldest → newest, same convention as contracts.get_contract_windows().
    """
    catalog    = CATALOGS[key]
    cum_offset = 0.0
    windows: list[dict] = []

    for i in range(len(catalog) - 1, -1, -1):
        c        = catalog[i]
        own_roll = date.fromisoformat(get_roll_date(c.ticker, rolls, key))
        next_roll = (date.fromisoformat(get_roll_date(catalog[i + 1].ticker, rolls, key))
                     if i < len(catalog) - 1 else None)

        windows.append({
            "ticker":     c.ticker,
            "start":      own_roll,
            "end":        next_roll,
            "cum_offset": cum_offset,
        })

        if i > 0:
            off = get_offset(c.ticker, rolls)
            cum_offset += (off if off is not None else 0.0)

    return windows[::-1]


def get_active_contract(key: str, d: date, rolls: dict) -> dict | None:
    for w in get_contract_windows(key, rolls):
        if w["start"] <= d and (w["end"] is None or d < w["end"]):
            return w
    return None


def apply_back_adjustment(
    key:            str,
    bars_by_ticker: dict[str, pd.DataFrame],
    rolls:          dict,
) -> pd.DataFrame:
    """
    Panama back-adjustment for any instrument.
    Newest contract is the anchor (no shift); older contracts are shifted up/down.
    """
    windows  = get_contract_windows(key, rolls)
    segments = []

    for w in windows:
        if w["ticker"] not in bars_by_ticker:
            continue
        df = bars_by_ticker[w["ticker"]].copy()
        df = df[df["DateTime"].dt.date >= w["start"]]
        if w["end"] is not None:
            df = df[df["DateTime"].dt.date < w["end"]]
        if w["cum_offset"] != 0.0:
            for col in ("Open", "High", "Low", "Close"):
                if col in df.columns:
                    df[col] = (df[col] + w["cum_offset"]).round(4)
        df["Contract"] = w["ticker"]
        segments.append(df)

    if not segments:
        return pd.DataFrame()

    result = pd.concat(segments, ignore_index=True)
    result.sort_values("DateTime", inplace=True, ignore_index=True)
    return result
