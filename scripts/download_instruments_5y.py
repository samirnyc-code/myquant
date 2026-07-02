"""
download_instruments_5y.py — one-shot bulk build of 5M bars for all additional
instruments (NQ, YM, GC, CL, 6E, 6J), matching the app's "Download + Build Bars".

- YM (CBOT), GC (COMEX), CL (NYMEX): download missing daily gz from Massive S3,
  then build per-contract 5M bar parquets.
- NQ, 6E, 6J (CME): build from the existing flatfiles_cache (no download).

Idempotent: cached gz files and existing bar parquets are reused/overwritten.
Progress is printed line-buffered so it can be tailed from a log file.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root

import massive as m
from instruments import CATALOGS, INSTRUMENTS

# Order: cheap cache-builds first (NQ/6E/6J), then the big downloads (YM/GC/CL).
ORDER = ["NQ", "6E", "6J", "YM", "GC", "CL"]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    t0 = time.time()
    grand_built = 0
    grand_total = 0

    for key in ORDER:
        spec = INSTRUMENTS[key]
        catalog = CATALOGS[key]
        # Only contracts whose active window has started (skip pure-future ones).
        live = [c for c in catalog if date.fromisoformat(c.active_from) <= date.today()]
        _log(f"=== {key} ({spec.name}, {spec.exchange.upper()}) — "
             f"{len(live)}/{len(catalog)} contracts with data, "
             f"cache={spec.gz_subdir} ===")

        built = 0
        for i, c in enumerate(live, 1):
            k0 = time.time()
            # Resume support: skip contracts whose bar parquet already exists and
            # is non-empty (lets a killed run pick up where it left off).
            bp = m._bars_path(c.ticker)
            if bp.exists():
                try:
                    import pandas as pd
                    if len(pd.read_parquet(bp)) > 0:
                        _log(f"  [{key} {i}/{len(live)}] {c.ticker}: skip (already built)")
                        continue
                except Exception:
                    pass
            try:
                ok = m._instr_build_contract_bars(key, c)
            except Exception as e:  # keep going; report the failure
                _log(f"  [{key} {i}/{len(live)}] {c.ticker} ERROR: {e}")
                continue
            grand_total += 1
            if ok:
                built += 1
                grand_built += 1
                bp = m._bars_path(c.ticker)
                nbars = 0
                try:
                    import pandas as pd
                    nbars = len(pd.read_parquet(bp))
                except Exception:
                    pass
                _log(f"  [{key} {i}/{len(live)}] {c.ticker}: "
                     f"{nbars:,} bars ({time.time()-k0:.0f}s)")
            else:
                _log(f"  [{key} {i}/{len(live)}] {c.ticker}: no data")

        _log(f"=== {key} done: {built}/{len(live)} contracts built ===")

    _log(f"ALL DONE: {grand_built}/{grand_total} contracts built "
         f"in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
