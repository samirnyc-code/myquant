#!/usr/bin/env python
"""eth_store_manifest.py — integrity manifest for the locked ETH tick trove.

Writes one row per day (file, rows, volume, first/last ts, price lo/hi, sha1 of
the parquet bytes) so accidental erasure/corruption is detectable later: re-run
with --check to compare the live store against the committed manifest and report
any missing / changed / extra day. The manifest itself is committed (small);
the parquets are gitignored (large), so this is the durable fingerprint.

  python scripts/eth_store_manifest.py            # (re)write the manifest
  python scripts/eth_store_manifest.py --check     # verify store vs manifest
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ETH = ROOT / "data" / "ticks_continuous_eth"
MAN = ROOT / "docs" / "reference" / "eth_store_manifest.csv"


def sha1(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build():
    rows = []
    for p in sorted(ETH.glob("*.parquet")):
        if p.stem.startswith("_"):
            continue
        df = pd.read_parquet(p)
        t = pd.to_datetime(df["DateTime"])
        rows.append(dict(date=p.stem, rows=len(df), volume=int(df["Volume"].sum()),
                         first=str(t.min()), last=str(t.max()),
                         px_lo=round(float(df["Price"].min()), 2),
                         px_hi=round(float(df["Price"].max()), 2),
                         sha1=sha1(p)))
    m = pd.DataFrame(rows)
    MAN.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(MAN, index=False)
    print(f"manifest written: {len(m)} days ({m['date'].iloc[0]} .. {m['date'].iloc[-1]}), "
          f"{m['rows'].sum():,} ticks, {m['volume'].sum():,} volume -> {MAN}")


def check():
    if not MAN.exists():
        print("no manifest yet — run without --check first"); return 1
    man = pd.read_csv(MAN, dtype={"sha1": str}).set_index("date")
    live = {p.stem for p in ETH.glob("*.parquet") if not p.stem.startswith("_")}
    missing = sorted(set(man.index) - live)
    extra = sorted(live - set(man.index))
    changed = []
    for d in sorted(set(man.index) & live):
        if sha1(ETH / f"{d}.parquet") != man.loc[d, "sha1"]:
            changed.append(d)
    print(f"manifest {len(man)} days | live {len(live)} | missing {len(missing)} "
          f"| changed {len(changed)} | extra {len(extra)}")
    for lbl, xs in (("MISSING", missing), ("CHANGED", changed), ("EXTRA", extra)):
        if xs:
            print(f"  {lbl}: {', '.join(xs[:20])}{' ...' if len(xs) > 20 else ''}")
    ok = not (missing or changed)
    print("INTEGRITY OK" if ok else "*** INTEGRITY DRIFT — see above ***")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    raise SystemExit(check() if a.check else (build() or 0))
