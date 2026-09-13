#!/usr/bin/env python
"""fix_rth_undercount.py — repair the RTH trove days that the drop_duplicates bug
left volume-undercounted, using the ALREADY-VALIDATED ETH trove as the source.

The ETH trove (data/ticks_continuous_eth/) has the correct full NT volume. Its RTH
slice [08:30,15:15) IS the correct RTH day. So for each day where the RTH trove is
materially lighter than the ETH RTH-slice, we replace the RTH trove day with that
slice. This touches ONLY NT-sourced undercounted days — never the Massive-era days
(they match or are heavier, so they are skipped), and never the 13 NT-light days
(ETH < RTH there, skipped).

Safety: each overwritten RTH day is first copied to data/ticks_continuous_rth_bak/.

  python scripts/fix_rth_undercount.py            # DRY-RUN: list days it would fix
  python scripts/fix_rth_undercount.py --apply     # back up + rewrite those days
"""
from __future__ import annotations

import argparse
import shutil
from datetime import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RTH = ROOT / "data" / "ticks_continuous"
ETH = ROOT / "data" / "ticks_continuous_eth"
BAK = ROOT / "data" / "ticks_continuous_rth_bak"
RTH_START, RTH_END = time(8, 30), time(15, 15)
THRESH = 1.05          # ETH RTH-slice vol must exceed RTH trove vol by >5% to count as undercounted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    eth_days = sorted(p.stem for p in ETH.glob("*.parquet") if not p.stem.startswith("_"))
    fixes = []
    for d in eth_days:
        rp = RTH / f"{d}.parquet"
        if not rp.exists():
            continue
        eth = pd.read_parquet(ETH / f"{d}.parquet")
        eth["DateTime"] = pd.to_datetime(eth["DateTime"])
        t = eth["DateTime"].dt.time
        slc = eth[(t >= RTH_START) & (t < RTH_END)][["DateTime", "Price", "Volume"]]
        ev = int(slc["Volume"].sum())
        rv = int(pd.read_parquet(rp)["Volume"].sum())
        if ev > rv * THRESH:
            fixes.append((d, rv, ev, slc))

    print(f"undercounted RTH days to repair: {len(fixes)} "
          f"(ETH RTH-slice vol > RTH trove vol x{THRESH})")
    for d, rv, ev, _ in fixes:
        print(f"  {d}: RTH trove {rv:>10,} -> corrected {ev:>10,}  (+{ev - rv:,}, {ev/rv:.2f}x)")
    if not fixes:
        print("nothing to repair."); return 0
    if not a.apply:
        print("\nDRY-RUN — nothing written. Re-run with --apply to back up + rewrite these days.")
        return 0

    BAK.mkdir(parents=True, exist_ok=True)
    for d, rv, ev, slc in fixes:
        rp = RTH / f"{d}.parquet"
        shutil.copy2(rp, BAK / f"{d}.parquet")      # reversible
        out = slc.sort_values("DateTime").reset_index(drop=True)
        out["Volume"] = out["Volume"].astype("int64")
        out.to_parquet(rp, index=False)
    print(f"\nrepaired {len(fixes)} days (originals backed up to {BAK}).")
    print("NEXT: rebuild the 5M cache -> python research/scalp_swing/build_5m.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
