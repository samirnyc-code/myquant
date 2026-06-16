"""
contracts.py — ES futures contract catalog and roll schedule management.

Catalog covers ESU1 (Sep 2021) → ESM6 (Jun 2026): ~5 years of front-month data,
matching Massive's availability window.

Roll dates follow NT's convention: roll_date = the date a contract BECOMES the
front month (the date you roll INTO it from the previous contract). Defaults
are pre-computed as (expiry − 8 calendar days) + 1 day of the PREVIOUS contract
— i.e. the day after the previous contract's nominal roll-out.

Roll offsets must be entered manually in the app — use the same value you enter
in NT's Instrument Manager for each ES_MAS contract:
    offset = new_contract_price − old_contract_price  (at the roll date)
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import json

ROLLS_FILE = Path(__file__).parent / "rolls.json"

_MONTH_TO_CODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
_MONTH_NAMES   = {3: "Mar", 6: "Jun", 9: "Sep", 12: "Dec"}


@dataclass(frozen=True)
class Contract:
    ticker:      str  # "ESM6"
    month:       int  # 6
    year:        int  # 2026
    last_trade:  str  # "2026-06-20"  (3rd Friday of contract month)
    roll_date:   str  # "2026-03-21"  (date THIS contract becomes front month — NT convention)
    active_from: str  # "2026-03-21"  (download window start; equals default roll_date)

    @property
    def nt_name(self) -> str:
        return f"ES_MAS {self.month:02d}-{self.year % 100:02d}"

    @property
    def label(self) -> str:
        return f"{_MONTH_NAMES[self.month]} {self.year}"

    @property
    def year2(self) -> str:
        return f"{self.year % 100:02d}"


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    days_to_fri = (4 - d.weekday()) % 7   # Friday = weekday 4
    return d + timedelta(days=days_to_fri + 14)  # 1st Friday + 2 weeks = 3rd Friday


def _build_catalog() -> list[Contract]:
    quarters = [
        (2021, 9), (2021, 12),
        (2022, 3), (2022, 6), (2022, 9), (2022, 12),
        (2023, 3), (2023, 6), (2023, 9), (2023, 12),
        (2024, 3), (2024, 6), (2024, 9), (2024, 12),
        (2025, 3), (2025, 6), (2025, 9), (2025, 12),
        (2026, 3), (2026, 6),
    ]

    contracts    = []
    prev_roll_dt: date | None = None

    for year, month in quarters:
        code       = _MONTH_TO_CODE[month]
        year_digit = str(year)[-1]
        ticker     = f"ES{code}{year_digit}"

        expiry    = _third_friday(year, month)
        roll_dt   = expiry - timedelta(days=8)
        from_dt   = (prev_roll_dt + timedelta(days=1)) if prev_roll_dt else date(2021, 6, 18)

        contracts.append(Contract(
            ticker      = ticker,
            month       = month,
            year        = year,
            last_trade  = expiry.isoformat(),
            roll_date   = from_dt.isoformat(),   # becomes-active date (NT convention)
            active_from = from_dt.isoformat(),
        ))
        prev_roll_dt = roll_dt

    return contracts


CATALOG:           list[Contract]       = _build_catalog()
CATALOG_BY_TICKER: dict[str, Contract] = {c.ticker: c for c in CATALOG}


# ── Roll schedule (stored in rolls.json, editable in the app) ─────────────────

def load_rolls() -> dict[str, dict]:
    """Return {ticker: {roll_date, offset}} — offset is None until the user enters it."""
    if not ROLLS_FILE.exists():
        return {}
    try:
        return json.loads(ROLLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_rolls(rolls: dict[str, dict]) -> None:
    ROLLS_FILE.write_text(json.dumps(rolls, indent=2), encoding="utf-8")


def ensure_rolls_file() -> None:
    """Create rolls.json with catalog defaults if it doesn't exist yet."""
    if ROLLS_FILE.exists():
        existing = load_rolls()
        # Add any new contracts missing from the file
        updated = False
        for c in CATALOG:
            if c.ticker not in existing:
                existing[c.ticker] = {"roll_date": c.roll_date, "offset": None}
                updated = True
        if updated:
            save_rolls(existing)
        return

    rolls = {
        c.ticker: {"roll_date": c.roll_date, "offset": None}
        for c in CATALOG
    }
    save_rolls(rolls)


def get_roll_date(ticker: str, rolls: dict) -> str:
    """User-edited roll date, else catalog default."""
    rd = rolls.get(ticker, {}).get("roll_date")
    return rd if rd else CATALOG_BY_TICKER[ticker].roll_date


def get_offset(ticker: str, rolls: dict) -> float | None:
    """Price offset when rolling INTO this contract from the previous one. None until entered."""
    val = rolls.get(ticker, {}).get("offset")
    return float(val) if val is not None else None


# ── Back-adjustment (Panama method, backward) ─────────────────────────────────

def apply_back_adjustment(
    bars_by_ticker: "dict[str, pd.DataFrame]",
    rolls: dict[str, dict],
) -> "pd.DataFrame":
    """
    Stitch per-contract 5M bar DataFrames into one back-adjusted continuous series.

    Roll date convention (matches NT's Instrument Manager):
        roll_date for contract X = the date X BECOMES the front month
        (i.e. the date you roll INTO X from the previous contract).
        This is the same value you enter in NT for each ES_MAS instrument.

    Offset convention (same as NT):
        offset for contract X = X_price − prev_price at X's roll date
        Positive offset means the new contract opened higher (typical for ES).

    Panama method: start from the newest contract (no adjustment), accumulate
    offsets going backwards, add the cumulative offset to each older contract.
    This means older prices are shifted UP in a generally rising market, keeping
    the most recent prices as-is (the anchor).

    Contracts without an offset entered are included with a 0 adjustment (gap visible).
    """
    import pandas as pd

    ordered = [c for c in CATALOG if c.ticker in bars_by_ticker]
    if not ordered:
        return pd.DataFrame()

    segments   = []
    cum_offset = 0.0

    for i in range(len(ordered) - 1, -1, -1):
        c  = ordered[i]
        df = bars_by_ticker[c.ticker].copy()

        # Lower bound: this contract's own roll date (when it becomes front month)
        own_roll = date.fromisoformat(get_roll_date(c.ticker, rolls))
        df = df[df["DateTime"].dt.date >= own_roll]

        # Upper bound: next contract's roll date (when this one hands off)
        if i < len(ordered) - 1:
            next_roll = date.fromisoformat(get_roll_date(ordered[i + 1].ticker, rolls))
            df = df[df["DateTime"].dt.date < next_roll]

        # Apply price adjustment
        if cum_offset != 0.0:
            for col in ("Open", "High", "Low", "Close"):
                if col in df.columns:
                    df[col] = (df[col] + cum_offset).round(2)

        df = df.copy()
        df["Contract"] = c.ticker
        segments.append(df)

        # Accumulate: the next older contract needs += this contract's offset
        if i > 0:
            off = get_offset(c.ticker, rolls)
            cum_offset += (off if off is not None else 0.0)

    if not segments:
        return pd.DataFrame()

    result = pd.concat(segments[::-1], ignore_index=True)
    result.sort_values("DateTime", inplace=True, ignore_index=True)
    return result
