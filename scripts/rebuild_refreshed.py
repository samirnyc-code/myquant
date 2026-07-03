"""
rebuild_refreshed.py — after refresh_stale_flatfiles.py --apply, rebuild only the
per-contract 5M bar parquets whose active window overlaps a just-refreshed daily
flatfile (detected by file mtime), then rebuild each instrument's continuous and
report gaps vs the ES reference.

Targeted, not a full run: only contracts touched by the refreshed dates rebuild.
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import massive as m           # noqa: E402
import pandas as pd           # noqa: E402
from instruments import INSTRUMENTS, CATALOGS  # noqa: E402

CUTOFF = time.time() - 3 * 60 * 60      # files touched in the last 3 hours
EX_DIR = {
    "flatfiles_cache":       ["NQ", "6E", "6J"],   # CME (ES managed separately)
    "flatfiles_cache_cbot":  ["YM"],
    "flatfiles_cache_comex": ["GC"],
    "flatfiles_cache_nymex": ["CL"],
}


def refreshed_dates(subdir: str) -> set[date]:
    out: set[date] = set()
    for f in (ROOT / "data" / subdir).glob("*.csv.gz"):
        if f.stat().st_mtime >= CUTOFF:
            out.add(date.fromisoformat(f.name[:-len(".csv.gz")]))
    return out


def main() -> None:
    t0 = time.time()
    for subdir, keys in EX_DIR.items():
        dates = refreshed_dates(subdir)
        print(f"[{subdir}] {len(dates)} refreshed date(s)", flush=True)
        if not dates:
            continue
        for key in keys:
            rebuilt = 0
            for c in CATALOGS[key]:
                af = date.fromisoformat(c.active_from)
                lt = date.fromisoformat(c.last_trade)
                if af > date.today():
                    continue
                if any(af <= d <= lt for d in dates):
                    m._instr_build_contract_bars(key, c)
                    rebuilt += 1
            print(f"    {key}: rebuilt {rebuilt} affected contract(s)", flush=True)

    # rebuild continuous + verify vs ES
    print("\n-- rebuilding continuous + verifying --", flush=True)
    es = pd.read_parquet(ROOT / "data/bars/_continuous.parquet")
    es_days = set(es["DateTime"].dt.date)
    for key in INSTRUMENTS:
        rolls = m._instr_load_rolls(key)
        df = m.build_instr_continuous(key, rolls)
        days = set(df["DateTime"].dt.date)
        lo = max(min(days), min(es_days))
        missing = sorted(d for d in es_days if d >= lo and d not in days)
        print(f"{key}: {len(df):,} bars, {len(days)} days | ES-has-we-lack: {len(missing)} "
              f"{[str(x) for x in missing[:6]]}", flush=True)

    print(f"\ndone in {(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
