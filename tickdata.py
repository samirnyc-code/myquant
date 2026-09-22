"""tickdata.py — THE canonical, mandatory access point for ES tick data.

⚠️ HARD RULE (user, 2026-09-13): NEVER run a test, backtest, study, or build a
chart from any other tick source. Every consumer of ES ticks imports from HERE.
Do not read the parquet dirs directly and do not introduce a second tick source.

TWO troves (both back-adjusted continuous front-month, roll-guarded):

  RTH_TROVE  data/ticks_continuous/       regular session 08:30–15:15 CT, 2021-06-18→,
             Massive-origin (2021→Jul-2026) then NT-fed; auto-expanded nightly.
  ETH_TROVE  data/ticks_continuous_eth/   FULL electronic session (~23h incl RTH),
             2025-07-16→, NT-origin; auto-expanded nightly. RTH is a subset of this.

Integrity: docs/reference/eth_store_manifest.csv (+ scripts/eth_store_manifest.py --check);
off-dir backup C:\\eth_trove_backup. Rebuild ETH: scripts/backfill_eth_from_nt.py.

Usage:
    import tickdata
    df   = tickdata.load_rth("2026-09-11")          # one day, RTH
    df   = tickdata.load_eth("2026-09-11")          # one day, full session
    df   = tickdata.load_range("2026-09-01", "2026-09-11", eth=True)
    days = tickdata.available("rth")                # sorted list of YYYY-MM-DD
Schema (both): DateTime (CT-naive), Price (float, back-adjusted), Volume (int64).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
RTH_TROVE = ROOT / "data" / "ticks_continuous"
ETH_TROVE = ROOT / "data" / "ticks_continuous_eth"


def _dir(eth: bool) -> Path:
    return ETH_TROVE if eth else RTH_TROVE


def available(which: str = "rth") -> list[str]:
    """Sorted YYYY-MM-DD day list present in a trove. which = 'rth' | 'eth'."""
    d = _dir(which.lower() == "eth")
    return sorted(p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_"))


def _load_one(day: str, eth: bool) -> pd.DataFrame:
    p = _dir(eth) / f"{day}.parquet"
    if not p.exists():
        raise FileNotFoundError(f"{'ETH' if eth else 'RTH'} trove has no {day} "
                                f"({p}). Use tickdata.available().")
    df = pd.read_parquet(p)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    return df


def load_rth(day: str) -> pd.DataFrame:
    return _load_one(day, eth=False)


def load_eth(day: str) -> pd.DataFrame:
    return _load_one(day, eth=True)


def load_range(start: str, end: str, eth: bool = False) -> pd.DataFrame:
    """Concatenate [start, end] inclusive from one trove, chronologically."""
    days = [d for d in available("eth" if eth else "rth") if start <= d <= end]
    if not days:
        raise FileNotFoundError(f"no {'ETH' if eth else 'RTH'} days in [{start},{end}]")
    return pd.concat((_load_one(d, eth) for d in days), ignore_index=True)


def coverage() -> dict:
    r, e = available("rth"), available("eth")
    return {"rth": {"days": len(r), "first": r[0] if r else None, "last": r[-1] if r else None},
            "eth": {"days": len(e), "first": e[0] if e else None, "last": e[-1] if e else None}}


if __name__ == "__main__":
    import json
    print(json.dumps(coverage(), indent=2))
