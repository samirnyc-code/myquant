"""build_eth_levels.py — per-session overnight (ETH) High/Low for ES.

The traded series is RTH-only. RTH OHLC and prior-day H/L already exist canonically
in the continuous bars (`indicators.session_levels`: OOD/HOY/LOY). The ONLY thing
missing for the regime-ladder study is the overnight high/low — so this extracts
*just* ETH min/max (plus ETH open/close) from the raw daily flat files.

Roll/offset: reuses the project's own machinery — `get_active_contract(d, rolls)`
gives the front-month ticker and the cumulative back-adjustment `cum_offset`. ETH
prices get the SAME offset as the continuous series, so they're directly comparable
to the bars (verified: RTH H/L and RTH open from these ticks == continuous-bar
values exactly). No roll-day exclusion needed.

Session boundary: the CME session spans midnight (prev 17:00 CT → 16:00 CT, keyed
by `session_end_date`). ETH must therefore be split on the full DATETIME, not the
wall-clock time-of-day — `ct < (date + 08:30)` captures the whole overnight incl.
the prev-evening 17:00–23:59. (Splitting on `.time() < 08:30` is WRONG: it drops
the evening session from the min/max and mislabels 17:00 as "RTH".)

Output: `data/eth_levels.parquet` — Date, front, cum_offset, ETH_High, ETH_Low,
ETH_Open, ETH_Close, n_eth. Schema is matchable against an NT continuous-contract
CSV export (Date, ETH_High, ETH_Low) for validation.

Run: .venv/Scripts/python.exe scripts/build_eth_levels.py [--workers N] [--limit N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

OUT_PATH = "data/eth_levels.parquet"
_ROLLS: dict | None = None          # lazy per-worker globals
# ETH window matched to NinjaTrader's @ES session template (validated to the tick
# against an NT export). NT labels 15-min bars by their CLOSE time: first close 17:15
# (bar covers 17:00-17:15), last close 08:15 (covers 08:00-08:15). So the real window
# is [prev 17:00, 08:15) — ticks from the Globex open up to 08:15 (NOT 08:30).
_ETH_END_OFF = pd.Timedelta("08:15:00")       # NT ETH cutoff = last bar close
_CLOSE_OFF   = pd.Timedelta("15:15:00")       # RTH close — start of post-close tail


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _init() -> None:
    global _ROLLS
    os.chdir(_REPO)                       # workers spawn fresh; anchor to repo root
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    _ROLLS = json.load(open("rolls.json"))


def _extract_one(path: str) -> dict | None:
    from contracts import get_active_contract

    ds = os.path.basename(path).replace(".csv.gz", "")
    d = pd.to_datetime(ds).date()
    active = get_active_contract(d, _ROLLS)
    if active is None:
        return None
    try:
        # only the 4 columns we need, via pyarrow CSV (~4.5x faster than full read).
        # front month comes from the roll table (active["ticker"]), not volume, so
        # `size` isn't needed.
        raw = pd.read_csv(path, usecols=["ticker", "timestamp", "price", "correction"],
                          engine="pyarrow")
    except Exception as e:                                  # noqa: BLE001
        return {"_error": f"{ds}: {e}"}
    raw = raw[(raw["ticker"] == active["ticker"]) & (raw["correction"] == 0)]
    if raw.empty:
        return None

    ct = (pd.to_datetime(raw["timestamp"], unit="ns", utc=True)
          .dt.tz_convert("America/Chicago").dt.tz_localize(None))
    price = raw["price"].astype(float).values + active["cum_offset"]
    df = pd.DataFrame({"ct": ct.values, "p": price}).sort_values("ct")

    eth_end  = pd.Timestamp(ds) + _ETH_END_OFF             # NT cutoff 08:15
    close_dt = pd.Timestamp(ds) + _CLOSE_OFF               # this session's 15:15 RTH close
    eth = df[df["ct"] < eth_end]                           # Globex overnight (prev 17:00 -> 08:15)
    pc  = df[df["ct"] >= close_dt]                         # 15:15->16:00 post-close tail
    if eth.empty:
        return None
    out = {
        "Date":       d,
        "front":      active["ticker"],
        "cum_offset": float(active["cum_offset"]),
        # def A — Globex overnight (prev 17:00 -> 08:30)
        "ETH_High":   float(eth["p"].max()),
        "ETH_Low":    float(eth["p"].min()),
        "ETH_Open":   float(eth["p"].iloc[0]),
        "ETH_Close":  float(eth["p"].iloc[-1]),
        "n_eth":      int(len(eth)),
        # post-close tail (this date's 15:15->16:00) — feeds NEXT session's def-B overnight
        "PC_High":    float(pc["p"].max()) if len(pc) else float("nan"),
        "PC_Low":     float(pc["p"].min()) if len(pc) else float("nan"),
        "n_pc":       int(len(pc)),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    files = sorted(glob.glob("data/flatfiles_cache/*.csv.gz"))
    if args.limit:
        files = files[: args.limit]
    print(f"[eth] {len(files)} flat files, {args.workers} workers", flush=True)

    rows, errors, done = [], [], 0
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as ex:
        futs = {ex.submit(_extract_one, f): f for f in files}
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r and "_error" in r:
                errors.append(r["_error"])
            elif r:
                rows.append(r)
            if done % 100 == 0:
                print(f"[eth] {done}/{len(files)}  ({len(rows)} rows)", flush=True)

    out = pd.DataFrame(rows).sort_values("Date").reset_index(drop=True)
    out.to_parquet(args.out, index=False)
    print(f"[eth] wrote {len(out)} rows -> {args.out}", flush=True)
    if errors:
        print(f"[eth] {len(errors)} errors, e.g. {errors[:3]}", flush=True)
    print(out.head().to_string(), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
